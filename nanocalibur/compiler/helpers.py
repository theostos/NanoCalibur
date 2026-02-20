import ast
from typing import Dict

from nanocalibur.errors import DSLValidationError
from nanocalibur.typesys import DictType, FieldType, ListType, Prim, PrimType


def _is_docstring_expr(node: ast.AST) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(
        node.value.value, str
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


def _parse_global_binding_name(selector: ast.AST) -> str:
    # Supports both:
    #   Global["name"]
    #   Global["name", int]
    if isinstance(selector, ast.Constant) and isinstance(selector.value, str):
        return selector.value

    if isinstance(selector, ast.Tuple) and len(selector.elts) == 2:
        name_node, type_node = selector.elts
        if not isinstance(name_node, ast.Constant) or not isinstance(name_node.value, str):
            raise DSLValidationError(
                'Global binding must be Global["name"] or Global["name", type].'
            )
        _validate_global_binding_type(type_node)
        return name_node.value

    raise DSLValidationError(
        'Global binding must be Global["name"] or Global["name", type].'
    )


def _validate_global_binding_type(node: ast.AST) -> None:
    if _is_supported_global_binding_type(node):
        return

    raise DSLValidationError(
        "Global typed binding only supports int, float, str, bool, List[...], or Dict[str, ...] with supported primitive/container elements."
    )


def _is_supported_global_binding_type(node: ast.AST) -> bool:
    if isinstance(node, ast.Name) and node.id in {"int", "float", "str", "bool"}:
        return True
    if (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id in {"List", "list"}
    ):
        return _is_supported_global_binding_type(node.slice)
    if (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id in {"Dict", "dict"}
    ):
        if not isinstance(node.slice, ast.Tuple) or len(node.slice.elts) != 2:
            return False
        key_node, value_node = node.slice.elts
        return (
            isinstance(key_node, ast.Name)
            and key_node.id == "str"
            and _is_supported_global_binding_type(value_node)
        )
    return False


def _expect_name(node: ast.AST, label: str) -> str:
    if isinstance(node, ast.Name):
        return node.id
    raise DSLValidationError(f"Expected {label} name.")


def _parse_typed_literal_value(
    node: ast.AST,
    field_type: FieldType,
    source_name: str,
):
    if isinstance(field_type, PrimType):
        if field_type.prim == Prim.BOOL:
            if isinstance(node, ast.Constant) and isinstance(node.value, bool):
                return node.value
            raise DSLValidationError(f"{source_name} expected bool literal value.")

        if field_type.prim == Prim.INT:
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, int)
                and not isinstance(node.value, bool)
            ):
                return node.value
            raise DSLValidationError(f"{source_name} expected int literal value.")

        if field_type.prim == Prim.FLOAT:
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                if isinstance(node.value, bool):
                    raise DSLValidationError(
                        f"{source_name} expected float literal value."
                    )
                return float(node.value)
            raise DSLValidationError(f"{source_name} expected float literal value.")

        if field_type.prim == Prim.STR:
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                return node.value
            raise DSLValidationError(f"{source_name} expected string literal value.")

    if isinstance(field_type, ListType):
        if not isinstance(node, ast.List):
            raise DSLValidationError(f"{source_name} expected list literal value.")
        return [
            _parse_typed_literal_value(elem, field_type.elem, source_name)
            for elem in node.elts
        ]

    if isinstance(field_type, DictType):
        if not isinstance(node, ast.Dict):
            raise DSLValidationError(f"{source_name} expected dict literal value.")
        out: dict[str, object] = {}
        for key_node, value_node in zip(node.keys, node.values):
            if key_node is None:
                raise DSLValidationError(f"{source_name} dict key cannot be omitted.")
            key_value = _parse_typed_literal_value(key_node, field_type.key, source_name)
            if not isinstance(key_value, str):
                raise DSLValidationError(f"{source_name} dict keys must be strings.")
            out[key_value] = _parse_typed_literal_value(
                value_node, field_type.value, source_name
            )
        return out

    raise DSLValidationError(f"{source_name} uses unsupported field type.")


def _parse_actor_link_literal_value(
    node: ast.AST,
    actor_fields: Dict[str, Dict[str, FieldType]],
    source_name: str,
) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value

    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
        owner = node.value.id
        if owner != "Actor" and owner not in actor_fields:
            raise DSLValidationError(
                f"{source_name} parent selector references unknown actor schema '{owner}'."
            )
        if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            return node.slice.value
        raise DSLValidationError(
            f'{source_name} parent selector must be ActorType["uid"].'
        )

    raise DSLValidationError(
        f"{source_name} parent field must be a uid string or ActorType[\"uid\"] selector."
    )


__all__ = [
    "_is_docstring_expr",
    "_format_syntax_error",
    "_parse_int_literal",
    "_parse_global_binding_name",
    "_validate_global_binding_type",
    "_is_supported_global_binding_type",
    "_expect_name",
    "_parse_typed_literal_value",
    "_parse_actor_link_literal_value",
]
