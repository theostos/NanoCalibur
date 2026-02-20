from __future__ import annotations

import ast
import copy
import warnings
from dataclasses import dataclass
from typing import Dict, List, Optional

from nanocalibur.errors import DSLValidationError, format_dsl_diagnostic


@dataclass
class _ActiveBlock:
    kind: str
    block_id: str
    descr: Optional[str]
    params: List[str]
    var_name: Optional[str]
    begin_node: ast.AST
    body: List[ast.stmt]


@dataclass
class _AbstractTemplate:
    block_id: str
    descr: Optional[str]
    params: List[str]
    var_name: Optional[str]
    begin_node: ast.AST
    body: List[ast.stmt]
    instantiate_count: int = 0


def preprocess_code_blocks(
    source: str,
    *,
    require_code_blocks: bool,
    unboxed_disable_flag: str,
) -> ast.Module:
    module = ast.parse(source)
    if not require_code_blocks and not _contains_code_block_markers(module):
        return module

    output_body: List[ast.stmt] = []
    active: Optional[_ActiveBlock] = None
    abstract_templates: Dict[str, _AbstractTemplate] = {}
    abstract_var_to_id: Dict[str, str] = {}

    for stmt in module.body:
        begin = _parse_begin(stmt)
        if begin is not None:
            if active is not None:
                raise DSLValidationError(
                    f"Cannot start block '{begin.block_id}' while block '{active.block_id}' is still open.",
                    node=stmt,
                )
            if begin.kind == "abstract" and begin.block_id in abstract_templates:
                raise DSLValidationError(
                    f"AbstractCodeBlock '{begin.block_id}' is already declared.",
                    node=stmt,
                )
            active = begin
            continue

        end_call = _parse_end_call(stmt, abstract_var_to_id, active=active)
        if end_call is not None:
            if active is None:
                raise DSLValidationError("CodeBlock.end(...) without matching begin(...).", node=stmt)
            if end_call["kind"] != active.kind:
                raise DSLValidationError(
                    f"Mismatched block end for '{active.block_id}'. Expected {active.kind} block end.",
                    node=stmt,
                )
            explicit_id = end_call["block_id"]
            if explicit_id is not None and explicit_id != active.block_id:
                raise DSLValidationError(
                    f"Code block end id '{explicit_id}' does not match open block '{active.block_id}'.",
                    node=stmt,
                )
            if active.descr is None or not active.descr.strip():
                marker_name = "CodeBlock" if active.kind == "code" else "AbstractCodeBlock"
                warnings.warn(
                    format_dsl_diagnostic(
                        "IMPORTANT: MISSING INFORMAL DESCRIPTION. "
                        f"{marker_name} '{active.block_id}' has no docstring description. "
                        "Add a string literal immediately after begin(...).",
                        node=active.begin_node,
                    ),
                    stacklevel=2,
                )
            if active.kind == "code":
                output_body.extend(active.body)
            else:
                template = _AbstractTemplate(
                    block_id=active.block_id,
                    descr=active.descr,
                    params=list(active.params),
                    var_name=active.var_name,
                    begin_node=active.begin_node,
                    body=list(active.body),
                )
                abstract_templates[template.block_id] = template
                if template.var_name:
                    abstract_var_to_id[template.var_name] = template.block_id
            active = None
            continue

        instantiate = _parse_instantiate(stmt, abstract_var_to_id)
        if instantiate is not None and active is None:
            block_id = instantiate["block_id"]
            template = abstract_templates.get(block_id)
            if template is None:
                raise DSLValidationError(
                    f"Unknown AbstractCodeBlock '{block_id}' in instantiate(...).",
                    node=stmt,
                )
            values = {
                name: _parse_static_macro_value(value_node, stmt)
                for name, value_node in instantiate["kwargs"].items()
            }
            missing = [name for name in template.params if name not in values]
            if missing:
                raise DSLValidationError(
                    f"AbstractCodeBlock '{block_id}' missing instantiate values for: {', '.join(missing)}.",
                    node=stmt,
                )
            unknown = sorted(set(values.keys()) - set(template.params))
            if unknown:
                raise DSLValidationError(
                    f"AbstractCodeBlock '{block_id}' instantiate(...) has unknown parameters: {unknown}.",
                    node=stmt,
                )

            template.instantiate_count += 1
            output_body.extend(
                _instantiate_template(
                    template,
                    values,
                    template.instantiate_count,
                )
            )
            continue

        if active is not None:
            if active.descr is None:
                maybe_doc = _parse_docstring_stmt(stmt)
                if maybe_doc is not None:
                    active.descr = maybe_doc
                    continue
            active.body.append(stmt)
            continue

        if _is_import_stmt(stmt):
            output_body.append(stmt)
            continue

        if require_code_blocks:
            warnings.warn(
                format_dsl_diagnostic(
                    "Ignoring top-level statement outside any CodeBlock. "
                    f"Wrap it inside CodeBlock.begin/end or pass '{unboxed_disable_flag}' "
                    "to build_game to disable strict block filtering.",
                    node=stmt,
                ),
                stacklevel=2,
            )
            continue

        output_body.append(stmt)

    if active is not None:
        raise DSLValidationError(
            f"Block '{active.block_id}' was opened but never closed with end(...).",
            node=active.begin_node,
        )

    for template in abstract_templates.values():
        if template.instantiate_count > 0:
            continue
        description = f" ({template.descr})" if template.descr else ""
        warnings.warn(
            format_dsl_diagnostic(
                f"AbstractCodeBlock '{template.block_id}' is never instantiated{description}.",
                node=template.begin_node,
            ),
            stacklevel=2,
        )

    transformed = ast.Module(body=output_body, type_ignores=[])
    ast.fix_missing_locations(transformed)
    return transformed


def _contains_code_block_markers(module: ast.Module) -> bool:
    for stmt in module.body:
        if _parse_begin(stmt) is not None:
            return True
        if _parse_end_call(stmt, {}) is not None:
            return True
        if _parse_instantiate(stmt, {}) is not None:
            return True
    return False


def _parse_begin(stmt: ast.stmt) -> Optional[_ActiveBlock]:
    assign_target: Optional[str] = None
    call: Optional[ast.Call] = None
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        call = stmt.value
    elif (
        isinstance(stmt, ast.Assign)
        and len(stmt.targets) == 1
        and isinstance(stmt.targets[0], ast.Name)
        and isinstance(stmt.value, ast.Call)
    ):
        assign_target = stmt.targets[0].id
        call = stmt.value
    else:
        return None

    if not isinstance(call.func, ast.Attribute) or not isinstance(call.func.value, ast.Name):
        return None
    cls_name = call.func.value.id
    method = call.func.attr
    if method != "begin" or cls_name not in {"CodeBlock", "AbstractCodeBlock"}:
        return None

    if not call.args:
        raise DSLValidationError(f"{cls_name}.begin(...) expects a block id.", node=stmt)
    first_arg = call.args[0]
    if not (isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str)):
        raise DSLValidationError(f"{cls_name}.begin(...) block id must be a string literal.", node=stmt)
    block_id = first_arg.value
    if not block_id:
        raise DSLValidationError(f"{cls_name}.begin(...) block id must be non-empty.", node=stmt)

    descr: Optional[str] = None
    params: List[str] = []

    if cls_name == "CodeBlock":
        for keyword in call.keywords:
            if keyword.arg is None:
                raise DSLValidationError(
                    "CodeBlock.begin(...) does not support **kwargs expansion.",
                    node=keyword,
                )
            if keyword.arg == "descr":
                raise DSLValidationError(
                    "CodeBlock.begin(..., descr=...) is no longer supported. "
                    "Use a docstring literal immediately after CodeBlock.begin(...).",
                    node=keyword,
                )
            raise DSLValidationError(
                f"CodeBlock.begin(...) does not support keyword '{keyword.arg}'.",
                node=keyword,
            )
        if len(call.args) != 1:
            raise DSLValidationError(
                "CodeBlock.begin(...) expects exactly one positional block id argument.",
                node=stmt,
            )
        return _ActiveBlock(
            kind="code",
            block_id=block_id,
            descr=descr,
            params=[],
            var_name=None,
            begin_node=stmt,
            body=[],
        )

    # AbstractCodeBlock
    if len(call.args) > 1:
        raise DSLValidationError(
            "AbstractCodeBlock.begin(...) expects block id as the only positional argument.",
            node=stmt,
        )

    for keyword in call.keywords:
        if keyword.arg is None:
            raise DSLValidationError(
                "AbstractCodeBlock.begin(...) does not support **kwargs expansion.",
                node=keyword,
            )
        if keyword.arg == "descr":
            raise DSLValidationError(
                "AbstractCodeBlock.begin(..., descr=...) is no longer supported. "
                "Use a docstring literal immediately after AbstractCodeBlock.begin(...).",
                node=keyword,
            )
        if keyword.arg == "params":
            if not isinstance(keyword.value, ast.Dict):
                raise DSLValidationError(
                    "AbstractCodeBlock.begin(..., params=...) must be a dict literal.",
                    node=keyword.value,
                )
            for key_node in keyword.value.keys:
                if key_node is None:
                    raise DSLValidationError(
                        "AbstractCodeBlock params keys cannot be omitted.",
                        node=keyword.value,
                    )
                if not (
                    isinstance(key_node, ast.Constant)
                    and isinstance(key_node.value, str)
                    and key_node.value
                ):
                    raise DSLValidationError(
                        "AbstractCodeBlock params keys must be non-empty strings.",
                        node=key_node,
                    )
                params.append(key_node.value)
            continue
        params.append(keyword.arg)

    if len(set(params)) != len(params):
        raise DSLValidationError(
            "AbstractCodeBlock.begin(...) has duplicated parameter names.",
            node=stmt,
        )

    return _ActiveBlock(
        kind="abstract",
        block_id=block_id,
        descr=descr,
        params=params,
        var_name=assign_target,
        begin_node=stmt,
        body=[],
    )


def _parse_end_call(
    stmt: ast.stmt,
    abstract_var_to_id: Dict[str, str],
    *,
    active: _ActiveBlock | None = None,
) -> Optional[Dict[str, Optional[str]]]:
    if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
        return None
    call = stmt.value
    if not isinstance(call.func, ast.Attribute):
        return None

    if isinstance(call.func.value, ast.Name) and call.func.attr == "end":
        owner = call.func.value.id
        if owner == "CodeBlock" or owner == "AbstractCodeBlock":
            if call.keywords:
                raise DSLValidationError(f"{owner}.end(...) does not accept keyword args.", node=stmt)
            block_id: Optional[str] = None
            if call.args:
                if len(call.args) != 1:
                    raise DSLValidationError(
                        f"{owner}.end(...) expects zero or one block id argument.",
                        node=stmt,
                    )
                if not (
                    isinstance(call.args[0], ast.Constant)
                    and isinstance(call.args[0].value, str)
                ):
                    raise DSLValidationError(
                        f"{owner}.end(...) block id must be a string literal.",
                        node=call.args[0],
                    )
                block_id = call.args[0].value
            return {
                "kind": "code" if owner == "CodeBlock" else "abstract",
                "block_id": block_id,
            }

        if call.func.attr == "end" and owner in abstract_var_to_id:
            if call.args or call.keywords:
                raise DSLValidationError(
                    f"{owner}.end(...) does not accept arguments.",
                    node=stmt,
                )
            return {
                "kind": "abstract",
                "block_id": abstract_var_to_id[owner],
            }
        if (
            call.func.attr == "end"
            and active is not None
            and active.kind == "abstract"
            and active.var_name is not None
            and owner == active.var_name
        ):
            if call.args or call.keywords:
                raise DSLValidationError(
                    f"{owner}.end(...) does not accept arguments.",
                    node=stmt,
                )
            return {
                "kind": "abstract",
                "block_id": active.block_id,
            }
    return None


def _parse_instantiate(
    stmt: ast.stmt,
    abstract_var_to_id: Dict[str, str],
) -> Optional[Dict[str, object]]:
    if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
        return None
    call = stmt.value
    if not isinstance(call.func, ast.Attribute):
        return None
    if call.func.attr != "instantiate":
        return None

    kwargs = {kw.arg: kw.value for kw in call.keywords if kw.arg is not None}
    if any(kw.arg is None for kw in call.keywords):
        raise DSLValidationError(
            "instantiate(...) does not support **kwargs expansion.",
            node=stmt,
        )

    if isinstance(call.func.value, ast.Name) and call.func.value.id in abstract_var_to_id:
        if call.args:
            raise DSLValidationError(
                "instance.instantiate(...) does not accept positional args.",
                node=stmt,
            )
        return {
            "block_id": abstract_var_to_id[call.func.value.id],
            "kwargs": kwargs,
        }

    if (
        isinstance(call.func.value, ast.Name)
        and call.func.value.id == "AbstractCodeBlock"
    ):
        if not call.args:
            raise DSLValidationError(
                "AbstractCodeBlock.instantiate(...) expects block id as first positional arg.",
                node=stmt,
            )
        if len(call.args) != 1:
            raise DSLValidationError(
                "AbstractCodeBlock.instantiate(...) expects exactly one positional block id arg.",
                node=stmt,
            )
        block_arg = call.args[0]
        if not (isinstance(block_arg, ast.Constant) and isinstance(block_arg.value, str)):
            raise DSLValidationError(
                "AbstractCodeBlock.instantiate(...) block id must be a string literal.",
                node=block_arg,
            )
        return {
            "block_id": block_arg.value,
            "kwargs": kwargs,
        }

    return None


def _parse_static_macro_value(node: ast.AST, context_node: ast.AST):
    try:
        value = ast.literal_eval(node)
    except Exception as exc:  # pragma: no cover - ast error formatting
        if _is_supported_selector_macro_expr(node):
            return copy.deepcopy(node)
        raise DSLValidationError(
            "AbstractCodeBlock.instantiate(...) values must be static constants "
            "(int/float/str/bool/list/dict) or selector expressions like Role[\"id\"].",
            node=context_node,
        ) from exc
    if _is_supported_macro_value(value):
        return value
    raise DSLValidationError(
        "AbstractCodeBlock.instantiate(...) values must be static constants "
        "(int/float/str/bool/list/dict) or selector expressions like Role[\"id\"].",
        node=context_node,
    )


def _is_supported_macro_value(value) -> bool:
    if value is None:
        return True
    if isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, list):
        return all(_is_supported_macro_value(item) for item in value)
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                return False
            if not _is_supported_macro_value(item):
                return False
        return True
    return False


def _is_supported_selector_macro_expr(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return True
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
        if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            return True
    return False


def _instantiate_template(
    template: _AbstractTemplate,
    values: Dict[str, object],
    instance_index: int,
) -> List[ast.stmt]:
    macro_values_ast = {name: _macro_value_to_ast(value) for name, value in values.items()}

    name_map: Dict[str, str] = {}
    for stmt in template.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name_map[stmt.name] = f"{stmt.name}__{template.block_id}_{instance_index}"
        elif isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    name_map[target.id] = f"{target.id}__{template.block_id}_{instance_index}"
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            name_map[stmt.target.id] = (
                f"{stmt.target.id}__{template.block_id}_{instance_index}"
            )

    replacer = _TemplateReplacer(
        macro_values_ast=macro_values_ast,
        name_map=name_map,
        template_var_name=template.var_name,
    )
    out: List[ast.stmt] = []
    for stmt in template.body:
        cloned = copy.deepcopy(stmt)
        rewritten = replacer.visit(cloned)
        ast.fix_missing_locations(rewritten)
        out.append(rewritten)
    return out


class _TemplateReplacer(ast.NodeTransformer):
    def __init__(
        self,
        *,
        macro_values_ast: Dict[str, ast.AST],
        name_map: Dict[str, str],
        template_var_name: str | None,
    ) -> None:
        self._macro_values_ast = macro_values_ast
        self._name_map = name_map
        self._template_var_name = template_var_name

    def visit_FunctionDef(self, node: ast.FunctionDef):
        node = self.generic_visit(node)
        if node.name in self._name_map:
            node.name = self._name_map[node.name]
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        node = self.generic_visit(node)
        if node.name in self._name_map:
            node.name = self._name_map[node.name]
        return node

    def visit_ClassDef(self, node: ast.ClassDef):
        node = self.generic_visit(node)
        if node.name in self._name_map:
            node.name = self._name_map[node.name]
        return node

    def visit_Name(self, node: ast.Name):
        if isinstance(node.ctx, ast.Load):
            if node.id in self._macro_values_ast:
                return copy.deepcopy(self._macro_values_ast[node.id])
            if node.id in self._name_map:
                return ast.copy_location(ast.Name(id=self._name_map[node.id], ctx=node.ctx), node)
        elif isinstance(node.ctx, ast.Store):
            if node.id in self._name_map:
                node.id = self._name_map[node.id]
        return node

    def visit_Attribute(self, node: ast.Attribute):
        node = self.generic_visit(node)
        if (
            isinstance(node.ctx, ast.Load)
            and self._template_var_name is not None
            and isinstance(node.value, ast.Name)
            and node.value.id == self._template_var_name
            and node.attr in self._macro_values_ast
        ):
            return copy.deepcopy(self._macro_values_ast[node.attr])
        return node


def _macro_value_to_ast(value) -> ast.AST:
    if isinstance(value, ast.AST):
        return copy.deepcopy(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return ast.Constant(value=value)
    if isinstance(value, list):
        return ast.List(elts=[_macro_value_to_ast(item) for item in value], ctx=ast.Load())
    if isinstance(value, dict):
        keys = [ast.Constant(value=key) for key in value.keys()]
        values = [_macro_value_to_ast(item) for item in value.values()]
        return ast.Dict(keys=keys, values=values)
    raise DSLValidationError("Unsupported macro value for AbstractCodeBlock instantiation.")


def _is_import_stmt(stmt: ast.stmt) -> bool:
    return isinstance(stmt, (ast.Import, ast.ImportFrom))


def _parse_docstring_stmt(stmt: ast.stmt) -> Optional[str]:
    if not isinstance(stmt, ast.Expr):
        return None
    if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
        return stmt.value.value.strip()
    return None
