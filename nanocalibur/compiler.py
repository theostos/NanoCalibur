import ast
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from nanocalibur.errors import DSLValidationError
from nanocalibur.ir import (
    ActionIR,
    ActorSelector,
    Assign,
    Attr,
    Binary,
    BindingKind,
    Const,
    For,
    If,
    ParamBinding,
    PredicateIR,
    Range,
    Unary,
    Var,
    While,
)
from nanocalibur.schema_registry import SchemaRegistry
from nanocalibur.typesys import FieldType, ListType, Prim, PrimType


_ALLOWED_BIN = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.Mod: "%",
}

_ALLOWED_BOOL = {
    ast.And: "&&",
    ast.Or: "||",
}

_ALLOWED_CMP = {
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
}

_ALLOWED_UNARY = {
    ast.Not: "!",
    ast.UAdd: "+",
    ast.USub: "-",
}

_PRIM_NAMES = {
    "int": Prim.INT,
    "float": Prim.FLOAT,
    "str": Prim.STR,
    "bool": Prim.BOOL,
}


@dataclass
class ActionScope:
    defined_names: Set[str]
    actor_var_types: Dict[str, str]
    actor_list_var_types: Dict[str, Optional[str]]


class DSLCompiler:
    def __init__(self, global_actor_types: Optional[Dict[str, Optional[str]]] = None):
        self.schemas = SchemaRegistry()
        self.global_actor_types: Dict[str, Optional[str]] = dict(global_actor_types or {})

    def compile(
        self,
        source: str,
        global_actor_types: Optional[Dict[str, Optional[str]]] = None,
    ) -> List[ActionIR]:
        # Reset per-compilation state for deterministic behavior across calls.
        self.schemas = SchemaRegistry()
        if global_actor_types is not None:
            self.global_actor_types = dict(global_actor_types)
        module = ast.parse(source)
        actions: List[ActionIR] = []

        # Pass 1: collect schemas so action bindings can reference them.
        for node in module.body:
            if _is_docstring_expr(node):
                continue
            if isinstance(node, ast.ClassDef):
                self._register_actor_schema(node)
                continue
            if isinstance(node, ast.FunctionDef):
                continue
            raise DSLValidationError(
                f"Unsupported top-level statement: {type(node).__name__}"
            )

        # Pass 2: compile actions.
        for node in module.body:
            if isinstance(node, ast.FunctionDef):
                actions.append(self._compile_action(node))
            elif isinstance(node, ast.ClassDef):
                continue
            elif _is_docstring_expr(node):
                continue
            else:
                raise DSLValidationError(
                    f"Unsupported top-level statement: {type(node).__name__}"
                )

        return actions

    def _register_actor_schema(self, node: ast.ClassDef) -> None:
        if node.decorator_list:
            raise DSLValidationError("Decorators are not allowed on actor schemas.")

        if len(node.bases) != 1:
            raise DSLValidationError("Actor schema must inherit from ActorModel only.")

        base = node.bases[0]
        if not isinstance(base, ast.Name) or base.id != "ActorModel":
            raise DSLValidationError("Only ActorModel subclasses are allowed.")

        fields: Dict[str, FieldType] = {}
        for stmt in node.body:
            if isinstance(stmt, ast.Pass):
                continue
            if not isinstance(stmt, ast.AnnAssign):
                raise DSLValidationError(
                    "Actor schema body can only contain annotated fields."
                )
            if stmt.value is not None:
                raise DSLValidationError(
                    "Actor schema fields cannot have default values."
                )
            if not isinstance(stmt.target, ast.Name):
                raise DSLValidationError("Actor schema field target must be a name.")

            field_name = stmt.target.id
            if field_name in fields:
                raise DSLValidationError(
                    f"Duplicate field '{field_name}' in actor '{node.name}'."
                )
            fields[field_name] = self._parse_field_type(stmt.annotation)

        self.schemas.register_actor(node.name, fields)

    def _parse_field_type(self, annotation: ast.AST) -> FieldType:
        if isinstance(annotation, ast.Name) and annotation.id in _PRIM_NAMES:
            return PrimType(_PRIM_NAMES[annotation.id])

        if isinstance(annotation, ast.Subscript):
            if not isinstance(annotation.value, ast.Name) or annotation.value.id != "List":
                raise DSLValidationError("Only List[...] container types are allowed.")

            elem = annotation.slice
            if isinstance(elem, ast.Name) and elem.id in _PRIM_NAMES:
                return ListType(PrimType(_PRIM_NAMES[elem.id]))
            raise DSLValidationError(
                "List element type must be one of int, float, str, bool."
            )

        raise DSLValidationError(
            "Field type must be int, float, str, bool, or List[...]"
        )

    def _compile_action(self, fn: ast.FunctionDef) -> ActionIR:
        if fn.decorator_list:
            raise DSLValidationError("Decorators are not allowed on actions.")
        if fn.returns is not None:
            raise DSLValidationError("Action return annotations are not allowed.")
        if fn.args.vararg is not None or fn.args.kwarg is not None:
            raise DSLValidationError("Variadic action parameters are not allowed.")
        if fn.args.posonlyargs or fn.args.kwonlyargs or fn.args.kw_defaults:
            raise DSLValidationError("Only regular positional parameters are allowed.")

        params: List[ParamBinding] = []
        for arg in fn.args.args:
            if arg.annotation is None:
                raise DSLValidationError("All action parameters must have bindings.")
            params.append(self._parse_binding(arg))

        actor_var_types: Dict[str, str] = {}
        actor_list_var_types: Dict[str, Optional[str]] = {}
        for param in params:
            if param.kind == BindingKind.ACTOR and param.actor_type is not None:
                actor_var_types[param.name] = param.actor_type
            if param.kind == BindingKind.ACTOR_LIST:
                actor_list_var_types[param.name] = param.actor_list_type
            if (
                param.kind == BindingKind.GLOBAL
                and param.global_name in self.global_actor_types
                and self.global_actor_types[param.global_name] is not None
            ):
                actor_var_types[param.name] = self.global_actor_types[param.global_name]

        scope = ActionScope(
            defined_names={p.name for p in params},
            actor_var_types=actor_var_types,
            actor_list_var_types=actor_list_var_types,
        )
        body = [self._compile_stmt(stmt, scope) for stmt in fn.body]
        return ActionIR(fn.name, params, body)

    def _compile_predicate(self, fn: ast.FunctionDef) -> PredicateIR:
        if fn.decorator_list:
            raise DSLValidationError("Decorators are not allowed on predicate functions.")
        if len(fn.args.args) != 1:
            raise DSLValidationError("Logical predicate must accept exactly one actor argument.")
        if fn.args.vararg is not None or fn.args.kwarg is not None:
            raise DSLValidationError("Variadic predicate parameters are not allowed.")
        if fn.args.posonlyargs or fn.args.kwonlyargs or fn.args.kw_defaults:
            raise DSLValidationError("Predicate must use regular positional parameters.")
        if not (
            isinstance(fn.returns, ast.Name)
            and fn.returns.id == "bool"
        ):
            raise DSLValidationError("Predicate function must have return type 'bool'.")

        param = fn.args.args[0]
        if not isinstance(param.annotation, ast.Name):
            raise DSLValidationError("Predicate parameter must be an actor schema type.")
        actor_type = param.annotation.id
        if actor_type not in self.schemas.actor_fields:
            raise DSLValidationError(
                f"Unknown actor schema '{actor_type}' in predicate '{fn.name}'."
            )
        if len(fn.body) != 1 or not isinstance(fn.body[0], ast.Return):
            raise DSLValidationError(
                "Predicate body must be a single return statement."
            )
        if fn.body[0].value is None:
            raise DSLValidationError("Predicate return statement must return a value.")

        scope = ActionScope(
            defined_names={param.arg},
            actor_var_types={param.arg: actor_type},
            actor_list_var_types={},
        )
        expr = self._compile_expr(fn.body[0].value, scope, allow_range_call=False)
        return PredicateIR(
            name=fn.name,
            param_name=param.arg,
            actor_type=actor_type,
            body=expr,
        )

    def _parse_binding(self, arg: ast.arg) -> ParamBinding:
        ann = arg.annotation
        if not isinstance(ann, ast.Subscript):
            raise DSLValidationError("Binding annotation must use T[...] syntax.")
        if not isinstance(ann.value, ast.Name):
            raise DSLValidationError("Binding annotation head must be a name.")

        head = ann.value.id
        selector = ann.slice

        if head == "Global":
            if not isinstance(selector, ast.Constant) or not isinstance(
                selector.value, str
            ):
                raise DSLValidationError('Global binding must be Global["name"].')
            return ParamBinding(
                name=arg.arg,
                kind=BindingKind.GLOBAL,
                global_name=selector.value,
            )

        if head == "Actor":
            actor_index = _parse_int_literal(selector)
            if actor_index is not None:
                return ParamBinding(
                    name=arg.arg,
                    kind=BindingKind.ACTOR,
                    actor_selector=ActorSelector(index=actor_index),
                )

            if isinstance(selector, ast.Constant) and isinstance(selector.value, str):
                actor_type = selector.value
                if actor_type not in self.schemas.actor_fields:
                    raise DSLValidationError(
                        f"Unknown actor schema '{actor_type}' in Actor binding."
                    )
                return ParamBinding(
                    name=arg.arg,
                    kind=BindingKind.ACTOR,
                    actor_selector=ActorSelector(uid=actor_type),
                    actor_type=actor_type,
                )

        # Typed actor binding using actor schema name as the binding head:
        #   player: Player["hero_uid"] or player: Player[-1]
        if head in self.schemas.actor_fields:
            actor_index = _parse_int_literal(selector)
            if actor_index is not None:
                return ParamBinding(
                    name=arg.arg,
                    kind=BindingKind.ACTOR,
                    actor_selector=ActorSelector(index=actor_index),
                    actor_type=head,
                )

            if isinstance(selector, ast.Constant) and isinstance(selector.value, str):
                return ParamBinding(
                    name=arg.arg,
                    kind=BindingKind.ACTOR,
                    actor_selector=ActorSelector(uid=selector.value),
                    actor_type=head,
                )

            raise DSLValidationError(
                f'{head} binding must be {head}["uid"] or {head}[index].'
            )

        if head in {"List", "list"}:
            if not isinstance(selector, ast.Name):
                raise DSLValidationError(
                    "Actor list binding must be List[Actor] or List[ActorType]."
                )

            if selector.id == "Actor":
                return ParamBinding(
                    name=arg.arg,
                    kind=BindingKind.ACTOR_LIST,
                )

            if selector.id in self.schemas.actor_fields:
                return ParamBinding(
                    name=arg.arg,
                    kind=BindingKind.ACTOR_LIST,
                    actor_list_type=selector.id,
                )

            raise DSLValidationError(
                "List[...] binding element must be Actor or a declared actor schema."
            )

        raise DSLValidationError("Unsupported binding annotation.")

    # ---------------- Statements ----------------

    def _compile_stmt(self, stmt: ast.stmt, scope: ActionScope):
        if isinstance(stmt, ast.Assign):
            if len(stmt.targets) != 1:
                raise DSLValidationError("Chained assignment is not allowed.")
            target = self._compile_assign_target(stmt.targets[0], scope)
            value = self._compile_expr(stmt.value, scope, allow_range_call=False)
            if isinstance(target, Var):
                scope.defined_names.add(target.name)
                self._sync_var_types_on_assign(target.name, value, scope)
            return Assign(target=target, value=value)

        if isinstance(stmt, ast.If):
            return If(
                condition=self._compile_expr(stmt.test, scope, allow_range_call=False),
                body=[self._compile_stmt(s, scope) for s in stmt.body],
                orelse=[self._compile_stmt(s, scope) for s in stmt.orelse],
            )

        if isinstance(stmt, ast.While):
            return While(
                condition=self._compile_expr(stmt.test, scope, allow_range_call=False),
                body=[self._compile_stmt(s, scope) for s in stmt.body],
            )

        if isinstance(stmt, ast.For):
            if stmt.orelse:
                raise DSLValidationError("for-else is not supported.")
            if not isinstance(stmt.target, ast.Name):
                raise DSLValidationError("for loop target must be a simple name.")

            iterable = self._compile_expr(stmt.iter, scope, allow_range_call=True)
            scope.defined_names.add(stmt.target.id)
            iter_actor_type = self._iterated_actor_type(iterable, scope)
            if iter_actor_type is None:
                scope.actor_var_types.pop(stmt.target.id, None)
            else:
                scope.actor_var_types[stmt.target.id] = iter_actor_type
            scope.actor_list_var_types.pop(stmt.target.id, None)
            return For(
                var=stmt.target.id,
                iterable=iterable,
                body=[self._compile_stmt(s, scope) for s in stmt.body],
            )

        if isinstance(stmt, ast.Pass):
            raise DSLValidationError("pass is not supported in actions.")

        raise DSLValidationError(f"Unsupported statement: {type(stmt).__name__}")

    def _compile_assign_target(self, target: ast.AST, scope: ActionScope):
        if isinstance(target, ast.Name):
            return Var(target.id)
        if isinstance(target, ast.Attribute):
            return self._compile_attr(target, scope)
        raise DSLValidationError("Assignment target must be a variable or actor field.")

    # ---------------- Expressions ----------------

    def _compile_expr(self, expr: ast.AST, scope: ActionScope, allow_range_call: bool):
        if isinstance(expr, ast.Constant):
            if isinstance(expr.value, bool):
                return Const(expr.value)
            if isinstance(expr.value, (int, float, str)):
                return Const(expr.value)
            raise DSLValidationError("Only int, float, str, bool constants are allowed.")

        if isinstance(expr, ast.Name):
            if expr.id not in scope.defined_names:
                raise DSLValidationError(f"Unknown variable '{expr.id}'.")
            return Var(expr.id)

        if isinstance(expr, ast.Attribute):
            return self._compile_attr(expr, scope)

        if isinstance(expr, ast.BinOp):
            op = _ALLOWED_BIN.get(type(expr.op))
            if op is None:
                raise DSLValidationError(
                    f"Unsupported binary operator: {type(expr.op).__name__}"
                )
            return Binary(
                op=op,
                left=self._compile_expr(expr.left, scope, allow_range_call=False),
                right=self._compile_expr(expr.right, scope, allow_range_call=False),
            )

        if isinstance(expr, ast.BoolOp):
            op = _ALLOWED_BOOL.get(type(expr.op))
            if op is None:
                raise DSLValidationError(
                    f"Unsupported boolean operator: {type(expr.op).__name__}"
                )
            compiled_values = [
                self._compile_expr(v, scope, allow_range_call=False) for v in expr.values
            ]
            combined = compiled_values[0]
            for value in compiled_values[1:]:
                combined = Binary(op=op, left=combined, right=value)
            return combined

        if isinstance(expr, ast.UnaryOp):
            op = _ALLOWED_UNARY.get(type(expr.op))
            if op is None:
                raise DSLValidationError(
                    f"Unsupported unary operator: {type(expr.op).__name__}"
                )
            return Unary(
                op=op,
                value=self._compile_expr(expr.operand, scope, allow_range_call=False),
            )

        if isinstance(expr, ast.Compare):
            if len(expr.ops) != 1 or len(expr.comparators) != 1:
                raise DSLValidationError("Chained comparisons are not supported.")
            op = _ALLOWED_CMP.get(type(expr.ops[0]))
            if op is None:
                raise DSLValidationError(
                    f"Unsupported comparison operator: {type(expr.ops[0]).__name__}"
                )
            return Binary(
                op=op,
                left=self._compile_expr(expr.left, scope, allow_range_call=False),
                right=self._compile_expr(
                    expr.comparators[0], scope, allow_range_call=False
                ),
            )

        if isinstance(expr, ast.Call):
            if not allow_range_call:
                raise DSLValidationError("Function calls are not allowed.")
            return self._compile_range_call(expr, scope)

        raise DSLValidationError(f"Unsupported expression: {type(expr).__name__}")

    def _compile_range_call(self, expr: ast.Call, scope: ActionScope) -> Range:
        if not isinstance(expr.func, ast.Name) or expr.func.id != "range":
            raise DSLValidationError("Only range(...) calls are allowed in for loops.")
        if expr.keywords:
            raise DSLValidationError("range(...) does not accept keyword arguments.")
        if not 1 <= len(expr.args) <= 3:
            raise DSLValidationError("range(...) expects 1 to 3 positional arguments.")

        return Range(
            args=[
                self._compile_expr(arg, scope, allow_range_call=False)
                for arg in expr.args
            ]
        )

    def _compile_attr(self, expr: ast.Attribute, scope: ActionScope) -> Attr:
        if not isinstance(expr.value, ast.Name):
            raise DSLValidationError(
                "Nested attribute access is not allowed; use actor.field only."
            )
        obj_name = expr.value.id
        if obj_name not in scope.defined_names:
            raise DSLValidationError(f"Unknown variable '{obj_name}'.")

        actor_type = scope.actor_var_types.get(obj_name)
        if actor_type is None:
            raise DSLValidationError(
                f"Actor variable '{obj_name}' must use Actor[\"Type\"] or "
                "Type[...] binding to allow field access."
            )
        if not self.schemas.has_field(actor_type, expr.attr):
            raise DSLValidationError(
                f"Actor '{actor_type}' has no field '{expr.attr}'."
            )

        return Attr(obj=obj_name, field=expr.attr)

    def _sync_var_types_on_assign(self, target_name: str, value, scope: ActionScope):
        if isinstance(value, Var):
            if value.name in scope.actor_var_types:
                scope.actor_var_types[target_name] = scope.actor_var_types[value.name]
            else:
                scope.actor_var_types.pop(target_name, None)

            if value.name in scope.actor_list_var_types:
                scope.actor_list_var_types[target_name] = scope.actor_list_var_types[
                    value.name
                ]
            else:
                scope.actor_list_var_types.pop(target_name, None)
            return

        scope.actor_var_types.pop(target_name, None)
        scope.actor_list_var_types.pop(target_name, None)

    def _iterated_actor_type(self, iterable, scope: ActionScope) -> Optional[str]:
        if isinstance(iterable, Var):
            return scope.actor_list_var_types.get(iterable.name)
        return None


def _is_docstring_expr(node: ast.AST) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(
        node.value.value, str
    )


def _parse_int_literal(node: ast.AST) -> int | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(
        node.value, bool
    ):
        return node.value

    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, int)
        and not isinstance(node.operand.value, bool)
    ):
        return -node.operand.value

    return None
