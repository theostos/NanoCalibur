import ast
import copy
from typing import Dict, List, Optional, Tuple, cast

from nanocalibur.compiler import DSLCompiler
from nanocalibur.compiler.constants import CALLABLE_EXPR_PREFIX
from nanocalibur.errors import DSLValidationError
from nanocalibur.game_model import InputPhase
from nanocalibur.ir import (
    ActionIR,
    Assign,
    Attr,
    Binary,
    CallExpr,
    CallableIR,
    CallStmt,
    Const,
    Continue,
    For,
    If,
    ListExpr,
    ObjectExpr,
    PredicateIR,
    Range,
    Return,
    SubscriptExpr,
    Unary,
    Var,
    While,
    Yield,
)

def _format_syntax_error(exc: SyntaxError, source: str) -> str:
    line = exc.lineno or 0
    col = exc.offset or 0
    snippet = (exc.text or "").strip()
    if not snippet and line > 0:
        lines = source.splitlines()
        if line <= len(lines):
            snippet = lines[line - 1].strip()
    message = f"Invalid Python syntax: {exc.msg}"
    if line > 0:
        message += f"\nLocation: line {line}, column {col if col > 0 else 1}"
    if snippet:
        message += f"\nCode: {snippet}"
    return message


def _resolve_name_alias(name: str, name_aliases: Dict[str, str]) -> str:
    resolved = name
    visited: set[str] = set()
    while True:
        next_name = name_aliases.get(resolved)
        if next_name is None or next_name == resolved or next_name in visited:
            return resolved
        visited.add(resolved)
        resolved = next_name


class _NameAliasNormalizer(ast.NodeTransformer):
    def __init__(self, name_aliases: Dict[str, str]):
        self._name_aliases = name_aliases

    def visit_Name(self, node: ast.Name) -> ast.AST:
        resolved = _resolve_name_alias(node.id, self._name_aliases)
        if resolved == node.id:
            return node
        return ast.copy_location(ast.Name(id=resolved, ctx=node.ctx), node)


def _resolve_name_aliases_in_node(node: ast.AST, name_aliases: Dict[str, str]) -> ast.AST:
    normalizer = _NameAliasNormalizer(name_aliases)
    return cast(ast.AST, normalizer.visit(copy.deepcopy(node)))


def _resolve_callable_reference(
    node: ast.AST,
    name_aliases: Dict[str, str],
    callable_aliases: Dict[str, ast.AST],
) -> Optional[ast.AST]:
    if isinstance(node, ast.Name):
        resolved_name = _resolve_name_alias(node.id, name_aliases)
        aliased_callable = callable_aliases.get(resolved_name)
        if aliased_callable is None:
            return None
        return _resolve_name_aliases_in_node(aliased_callable, name_aliases)

    if isinstance(node, ast.Attribute):
        resolved_value = _resolve_name_aliases_in_node(node.value, name_aliases)
        if not isinstance(resolved_value, (ast.Name, ast.Attribute)):
            return None
        return ast.copy_location(
            ast.Attribute(value=resolved_value, attr=node.attr, ctx=node.ctx),
            node,
        )

    return None


def _resolve_call_aliases(
    call: ast.Call,
    name_aliases: Dict[str, str],
    callable_aliases: Dict[str, ast.AST],
) -> ast.Call:
    resolved_func = _resolve_callable_reference(call.func, name_aliases, callable_aliases)
    if resolved_func is None:
        if isinstance(call.func, ast.Name):
            resolved_name = _resolve_name_alias(call.func.id, name_aliases)
            resolved_func = ast.copy_location(
                ast.Name(id=resolved_name, ctx=call.func.ctx), call.func
            )
        elif isinstance(call.func, ast.Attribute):
            resolved_value = _resolve_name_aliases_in_node(call.func.value, name_aliases)
            resolved_func = ast.copy_location(
                ast.Attribute(
                    value=resolved_value,
                    attr=call.func.attr,
                    ctx=call.func.ctx,
                ),
                call.func,
            )
        else:
            resolved_func = _resolve_name_aliases_in_node(call.func, name_aliases)

    return ast.copy_location(
        ast.Call(
            func=resolved_func,
            args=[
                _resolve_name_aliases_in_node(arg, name_aliases)
                for arg in call.args
            ],
            keywords=[
                ast.keyword(
                    arg=keyword.arg,
                    value=_resolve_name_aliases_in_node(keyword.value, name_aliases),
                )
                for keyword in call.keywords
            ],
        ),
        call,
    )


def _track_top_level_assignment_alias(
    target: str,
    value: ast.AST,
    name_aliases: Dict[str, str],
    callable_aliases: Dict[str, ast.AST],
) -> None:
    name_aliases.pop(target, None)
    callable_aliases.pop(target, None)

    if isinstance(value, ast.Name):
        resolved_name = _resolve_name_alias(value.id, name_aliases)
        if resolved_name != target:
            name_aliases[target] = resolved_name
        if resolved_name in callable_aliases:
            callable_aliases[target] = copy.deepcopy(callable_aliases[resolved_name])
        return

    resolved_callable = _resolve_callable_reference(value, name_aliases, callable_aliases)
    if resolved_callable is not None:
        callable_aliases[target] = resolved_callable


def _looks_like_action(fn: ast.FunctionDef, compiler: DSLCompiler) -> bool:
    if fn.returns is not None:
        return False
    for arg in fn.args.args:
        if arg.annotation is None:
            return False
        if _is_supported_action_binding_annotation(arg.annotation, compiler):
            continue
        return False
    return True


def _is_supported_action_binding_annotation(
    annotation: ast.AST,
    compiler: DSLCompiler,
) -> bool:
    if isinstance(annotation, ast.Name):
        if annotation.id in {"Scene", "Tick", "Actor", "Role", "Camera"}:
            return True
        return (
            annotation.id in compiler.schemas.actor_fields
            or annotation.id in compiler.schemas.role_fields
        )

    if isinstance(annotation, ast.Subscript) and isinstance(annotation.value, ast.Name):
        head = annotation.value.id
        if head in {"Scene", "Tick", "Actor", "Role", "Camera", "Global", "List", "list"}:
            return True
        return head in compiler.schemas.actor_fields or head in compiler.schemas.role_fields

    return False


def _looks_like_predicate(fn: ast.FunctionDef, compiler: DSLCompiler) -> bool:
    if not (isinstance(fn.returns, ast.Name) and fn.returns.id == "bool"):
        return False
    if fn.args.vararg is not None or fn.args.kwarg is not None:
        return False
    if fn.args.posonlyargs or fn.args.kwonlyargs or fn.args.kw_defaults:
        return False
    for arg in fn.args.args:
        if arg.annotation is None:
            return False
        if isinstance(arg.annotation, (ast.Name, ast.Subscript)):
            continue
        return False
    return True


def _action_contains_next_turn(action: ActionIR) -> bool:
    return any(_stmt_contains_next_turn(stmt) for stmt in action.body)


def _stmt_contains_next_turn(stmt: object) -> bool:
    if isinstance(stmt, CallStmt):
        return stmt.name == "scene_next_turn"
    if isinstance(stmt, If):
        return any(_stmt_contains_next_turn(child) for child in stmt.body) or any(
            _stmt_contains_next_turn(child) for child in stmt.orelse
        )
    if isinstance(stmt, While):
        return any(_stmt_contains_next_turn(child) for child in stmt.body)
    if isinstance(stmt, For):
        return any(_stmt_contains_next_turn(child) for child in stmt.body)
    return False


def _as_game_method_call(
    call: ast.Call, game_var: str
) -> Optional[Tuple[str, List[ast.AST], Dict[str, ast.AST]]]:
    return _as_owner_method_call(call, game_var)


def _as_owner_method_call(
    call: ast.Call, owner_var: str
) -> Optional[Tuple[str, List[ast.AST], Dict[str, ast.AST]]]:
    if not (
        isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == owner_var
    ):
        return None
    kwargs = {kw.arg: kw.value for kw in call.keywords if kw.arg is not None}
    return call.func.attr, list(call.args), kwargs


def _parse_keyboard_phase(method: str) -> InputPhase | None:
    if method == "begin_press":
        return InputPhase.BEGIN
    if method == "on_press":
        return InputPhase.ON
    if method == "end_press":
        return InputPhase.END
    return None


def _parse_mouse_phase(method: str) -> InputPhase | None:
    if method == "begin_click":
        return InputPhase.BEGIN
    if method == "on_click":
        return InputPhase.ON
    if method == "end_click":
        return InputPhase.END
    return None


def _expect_name(node: ast.AST, label: str) -> str:
    if isinstance(node, ast.Name):
        return node.id
    raise DSLValidationError(f"Expected {label} name.")


def _extract_declared_actor_ctor_uid(ctor: ast.Call) -> Optional[str]:
    if ctor.args:
        first = ctor.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
        return None
    for keyword in ctor.keywords:
        if keyword.arg == "uid":
            if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                return keyword.value.value
            return None
    return None


def _extract_informal_docstring(fn: Optional[ast.FunctionDef]) -> str:
    if fn is None:
        return ""
    docstring = ast.get_docstring(fn, clean=True)
    if not docstring:
        return ""
    return docstring.strip()


def _collect_used_callable_names(
    *,
    actions: List[ActionIR],
    predicates: List[PredicateIR],
    callables: Dict[str, CallableIR],
) -> set[str]:
    discovered: set[str] = set()
    for action in actions:
        for stmt in action.body:
            discovered.update(_callable_names_in_stmt(stmt))
    for predicate in predicates:
        discovered.update(_callable_names_in_expr(predicate.body))

    used: set[str] = set()
    pending = list(discovered)
    while pending:
        callable_name = pending.pop()
        if callable_name in used:
            continue
        used.add(callable_name)
        helper = callables.get(callable_name)
        if helper is None:
            continue
        nested: set[str] = set()
        for stmt in helper.body:
            nested.update(_callable_names_in_stmt(stmt))
        nested.update(_callable_names_in_expr(helper.return_expr))
        for nested_name in nested:
            if nested_name not in used:
                pending.append(nested_name)

    return used


def _callable_names_in_stmt(stmt) -> set[str]:
    if isinstance(stmt, Assign):
        names = _callable_names_in_expr(stmt.value)
        names.update(_callable_names_in_expr(stmt.target))
        return names
    if isinstance(stmt, CallStmt):
        names: set[str] = set()
        for arg in stmt.args:
            names.update(_callable_names_in_expr(arg))
        return names
    if isinstance(stmt, If):
        names = _callable_names_in_expr(stmt.condition)
        for child in stmt.body:
            names.update(_callable_names_in_stmt(child))
        for child in stmt.orelse:
            names.update(_callable_names_in_stmt(child))
        return names
    if isinstance(stmt, While):
        names = _callable_names_in_expr(stmt.condition)
        for child in stmt.body:
            names.update(_callable_names_in_stmt(child))
        return names
    if isinstance(stmt, For):
        names = _callable_names_in_expr(stmt.iterable)
        for child in stmt.body:
            names.update(_callable_names_in_stmt(child))
        return names
    if isinstance(stmt, Yield):
        return _callable_names_in_expr(stmt.value)
    if isinstance(stmt, Return):
        if stmt.value is None:
            return set()
        return _callable_names_in_expr(stmt.value)
    if isinstance(stmt, Continue):
        return set()
    return set()


def _callable_names_in_expr(expr) -> set[str]:
    if isinstance(expr, (Const, Var, Attr)):
        return set()
    if isinstance(expr, Unary):
        return _callable_names_in_expr(expr.value)
    if isinstance(expr, Binary):
        names = _callable_names_in_expr(expr.left)
        names.update(_callable_names_in_expr(expr.right))
        return names
    if isinstance(expr, Range):
        names: set[str] = set()
        for arg in expr.args:
            names.update(_callable_names_in_expr(arg))
        return names
    if isinstance(expr, ObjectExpr):
        names: set[str] = set()
        for value in expr.fields.values():
            names.update(_callable_names_in_expr(value))
        return names
    if isinstance(expr, ListExpr):
        names: set[str] = set()
        for item in expr.items:
            names.update(_callable_names_in_expr(item))
        return names
    if isinstance(expr, SubscriptExpr):
        names = _callable_names_in_expr(expr.value)
        names.update(_callable_names_in_expr(expr.index))
        return names
    if isinstance(expr, CallExpr):
        names: set[str] = set()
        if expr.name.startswith(CALLABLE_EXPR_PREFIX):
            names.add(expr.name[len(CALLABLE_EXPR_PREFIX) :])
        for arg in expr.args:
            names.update(_callable_names_in_expr(arg))
        return names
    return set()
