import ast
import copy
from typing import Dict, List, Optional

from nanocalibur.errors import DSLValidationError
from nanocalibur.game_model import MultiplayerLoopMode, RoleKind, VisibilityMode
from nanocalibur.typesys import DictType, FieldType, ListType, Prim, PrimType

class _StaticNameSubstituter(ast.NodeTransformer):
    def __init__(self, env: Dict[str, object]) -> None:
        self._env = env

    def visit_Name(self, node: ast.Name):
        if isinstance(node.ctx, ast.Load) and node.id in self._env:
            return ast.copy_location(_static_value_to_ast(self._env[node.id]), node)
        return node


def _substitute_static_names_in_node(node: ast.AST, env: Dict[str, object]) -> ast.AST:
    return ast.fix_missing_locations(_StaticNameSubstituter(env).visit(copy.deepcopy(node)))


def _static_value_to_ast(value: object) -> ast.AST:
    if value is None or isinstance(value, (bool, int, float, str)):
        return ast.Constant(value=value)
    if isinstance(value, list):
        return ast.List(elts=[_static_value_to_ast(item) for item in value], ctx=ast.Load())
    if isinstance(value, tuple):
        return ast.Tuple(
            elts=[_static_value_to_ast(item) for item in value],
            ctx=ast.Load(),
        )
    if isinstance(value, range):
        return ast.List(
            elts=[_static_value_to_ast(item) for item in value],
            ctx=ast.Load(),
        )
    if isinstance(value, dict):
        return ast.Dict(
            keys=[_static_value_to_ast(key) for key in value.keys()],
            values=[_static_value_to_ast(item) for item in value.values()],
        )
    raise DSLValidationError(
        f"Unsupported compile-time value type '{type(value).__name__}' in setup expansion."
    )


def _update_static_setup_env_from_stmt(
    stmt: ast.stmt,
    env: Dict[str, object],
) -> None:
    if isinstance(stmt, ast.Assign):
        if len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            target_name = stmt.targets[0].id
            try:
                env[target_name] = copy.deepcopy(_eval_static_expr(stmt.value, env))
            except DSLValidationError:
                env.pop(target_name, None)
        return

    if isinstance(stmt, ast.AnnAssign):
        if isinstance(stmt.target, ast.Name):
            target_name = stmt.target.id
            if stmt.value is None:
                env.pop(target_name, None)
            else:
                try:
                    env[target_name] = copy.deepcopy(_eval_static_expr(stmt.value, env))
                except DSLValidationError:
                    env.pop(target_name, None)
        return

    if isinstance(stmt, ast.AugAssign) and isinstance(stmt.target, ast.Name):
        target_name = stmt.target.id
        if target_name not in env:
            return
        try:
            right = _eval_static_expr(stmt.value, env)
            left = env[target_name]
            op = stmt.op
            if isinstance(op, ast.Add):
                if isinstance(left, list) and isinstance(right, list):
                    env[target_name] = [*left, *right]
                elif isinstance(left, dict) and isinstance(right, dict):
                    env[target_name] = {**left, **right}
                elif isinstance(left, str) and isinstance(right, str):
                    env[target_name] = left + right
                elif isinstance(left, bool) or isinstance(right, bool):
                    env.pop(target_name, None)
                elif isinstance(left, (int, float)) and isinstance(right, (int, float)):
                    env[target_name] = left + right
                else:
                    env.pop(target_name, None)
            elif isinstance(op, ast.Sub):
                if (
                    isinstance(left, (int, float))
                    and isinstance(right, (int, float))
                    and not isinstance(left, bool)
                    and not isinstance(right, bool)
                ):
                    env[target_name] = left - right
                else:
                    env.pop(target_name, None)
            elif isinstance(op, ast.Mult):
                if (
                    isinstance(left, (int, float))
                    and isinstance(right, (int, float))
                    and not isinstance(left, bool)
                    and not isinstance(right, bool)
                ):
                    env[target_name] = left * right
                elif isinstance(left, str) and isinstance(right, int):
                    env[target_name] = left * right
                elif isinstance(left, int) and isinstance(right, str):
                    env[target_name] = left * right
                elif isinstance(left, list) and isinstance(right, int):
                    env[target_name] = left * right
                elif isinstance(left, int) and isinstance(right, list):
                    env[target_name] = left * right
                else:
                    env.pop(target_name, None)
            elif isinstance(op, ast.Div):
                if (
                    isinstance(left, (int, float))
                    and isinstance(right, (int, float))
                    and not isinstance(left, bool)
                    and not isinstance(right, bool)
                ):
                    env[target_name] = left / right
                else:
                    env.pop(target_name, None)
            elif isinstance(op, ast.FloorDiv):
                if (
                    isinstance(left, (int, float))
                    and isinstance(right, (int, float))
                    and not isinstance(left, bool)
                    and not isinstance(right, bool)
                ):
                    env[target_name] = left // right
                else:
                    env.pop(target_name, None)
            elif isinstance(op, ast.Mod):
                if (
                    isinstance(left, (int, float))
                    and isinstance(right, (int, float))
                    and not isinstance(left, bool)
                    and not isinstance(right, bool)
                ):
                    env[target_name] = left % right
                elif isinstance(left, str):
                    env[target_name] = left % right
                else:
                    env.pop(target_name, None)
            else:
                env.pop(target_name, None)
        except (DSLValidationError, ZeroDivisionError):
            env.pop(target_name, None)
        return

    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        call = stmt.value
        if (
            isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id in env
        ):
            receiver_name = call.func.value.id
            method = call.func.attr
            try:
                args = [_eval_static_expr(arg, env) for arg in call.args]
            except DSLValidationError:
                return
            receiver = env.get(receiver_name)
            if method == "append" and isinstance(receiver, list) and len(args) == 1:
                env[receiver_name] = [*receiver, args[0]]
            elif method == "update" and isinstance(receiver, dict) and len(args) == 1:
                if isinstance(args[0], dict):
                    env[receiver_name] = {**receiver, **args[0]}
            elif method == "concat" and len(args) == 1:
                other = args[0]
                if isinstance(receiver, list) and isinstance(other, list):
                    env[receiver_name] = receiver + other
                elif isinstance(receiver, dict) and isinstance(other, dict):
                    env[receiver_name] = {**receiver, **other}
                elif isinstance(receiver, str) and isinstance(other, str):
                    env[receiver_name] = receiver + other
            elif method == "pop":
                if isinstance(receiver, list):
                    data = list(receiver)
                    try:
                        if len(args) == 0:
                            if not data:
                                return
                            data.pop()
                            env[receiver_name] = data
                        elif len(args) == 1 and isinstance(args[0], int):
                            data.pop(args[0])
                            env[receiver_name] = data
                    except (IndexError, TypeError):
                        return
                elif isinstance(receiver, dict):
                    data = dict(receiver)
                    if len(args) == 1:
                        data.pop(args[0], None)
                        env[receiver_name] = data
                    elif len(args) == 2:
                        data.pop(args[0], args[1])
                        env[receiver_name] = data


def _eval_static_expr(node: ast.AST, env: Optional[Dict[str, object]] = None):
    if isinstance(node, ast.Constant):
        value = node.value
        if value is None:
            return None
        if isinstance(value, (bool, int, float, str)):
            return value
        raise DSLValidationError("Unsupported constant value in setup expression.")

    if isinstance(node, ast.Name):
        if env is not None and node.id in env:
            return copy.deepcopy(env[node.id])
        raise DSLValidationError(
            f"Unknown name '{node.id}' in setup expression."
        )

    if isinstance(node, ast.List):
        return [_eval_static_expr(item, env) for item in node.elts]

    if isinstance(node, ast.Tuple):
        return tuple(_eval_static_expr(item, env) for item in node.elts)

    if isinstance(node, ast.Dict):
        out: Dict[object, object] = {}
        for key_node, value_node in zip(node.keys, node.values):
            if key_node is None:
                raise DSLValidationError("Dict unpacking is not supported in setup expressions.")
            key = _eval_static_expr(key_node, env)
            if not isinstance(key, (str, int, float, bool)):
                raise DSLValidationError(
                    "Dict keys in setup expressions must be primitive constants."
                )
            out[key] = _eval_static_expr(value_node, env)
        return out

    if isinstance(node, ast.JoinedStr):
        chunks: List[str] = []
        for value_node in node.values:
            if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
                chunks.append(value_node.value)
                continue
            if isinstance(value_node, ast.FormattedValue):
                value = _eval_static_expr(value_node.value, env)
                if value_node.format_spec is not None:
                    spec_value = _eval_static_expr(value_node.format_spec, env)
                    spec = str(spec_value)
                else:
                    spec = ""
                if value_node.conversion == ord("r"):
                    rendered = repr(value)
                elif value_node.conversion == ord("a"):
                    rendered = ascii(value)
                else:
                    rendered = str(value)
                if spec:
                    rendered = format(value, spec)
                chunks.append(rendered)
                continue
            raise DSLValidationError("Unsupported f-string component in setup expression.")
        return "".join(chunks)

    if isinstance(node, ast.UnaryOp):
        operand = _eval_static_expr(node.operand, env)
        if isinstance(node.op, ast.Not):
            return not bool(operand)
        if isinstance(node.op, ast.UAdd):
            if isinstance(operand, bool) or not isinstance(operand, (int, float)):
                raise DSLValidationError("Unary '+' expects an int or float operand.")
            return +operand
        if isinstance(node.op, ast.USub):
            if isinstance(operand, bool) or not isinstance(operand, (int, float)):
                raise DSLValidationError("Unary '-' expects an int or float operand.")
            return -operand
        raise DSLValidationError(
            f"Unsupported unary operator in setup expression: {type(node.op).__name__}"
        )

    if isinstance(node, ast.BinOp):
        left = _eval_static_expr(node.left, env)
        right = _eval_static_expr(node.right, env)

        if isinstance(node.op, ast.Add):
            if isinstance(left, list) and isinstance(right, list):
                return left + right
            if isinstance(left, dict) and isinstance(right, dict):
                return {**left, **right}
            if isinstance(left, str) and isinstance(right, str):
                return left + right
            if isinstance(left, bool) or isinstance(right, bool):
                raise DSLValidationError("Operator '+' does not accept bool operands.")
            if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                return left + right
            raise DSLValidationError(
                "Unsupported '+' operands in setup expression. Use compatible "
                "int/float/str/list/dict values."
            )

        if isinstance(node.op, ast.Sub):
            if isinstance(left, bool) or isinstance(right, bool):
                raise DSLValidationError("Operator '-' does not accept bool operands.")
            if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                return left - right
            raise DSLValidationError("Operator '-' expects int/float operands.")

        if isinstance(node.op, ast.Mult):
            if isinstance(left, bool) or isinstance(right, bool):
                raise DSLValidationError("Operator '*' does not accept bool operands.")
            if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                return left * right
            if isinstance(left, str) and isinstance(right, int):
                return left * right
            if isinstance(left, int) and isinstance(right, str):
                return left * right
            if isinstance(left, list) and isinstance(right, int):
                return left * right
            if isinstance(left, int) and isinstance(right, list):
                return left * right
            raise DSLValidationError(
                "Unsupported '*' operands in setup expression."
            )

        if isinstance(node.op, ast.Div):
            if isinstance(left, bool) or isinstance(right, bool):
                raise DSLValidationError("Operator '/' does not accept bool operands.")
            if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                return left / right
            raise DSLValidationError("Operator '/' expects int/float operands.")

        if isinstance(node.op, ast.FloorDiv):
            if isinstance(left, bool) or isinstance(right, bool):
                raise DSLValidationError("Operator '//' does not accept bool operands.")
            if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                return left // right
            raise DSLValidationError("Operator '//' expects int/float operands.")

        if isinstance(node.op, ast.Mod):
            if isinstance(left, bool) or isinstance(right, bool):
                raise DSLValidationError("Operator '%' does not accept bool operands.")
            if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                return left % right
            if isinstance(left, str):
                return left % right
            raise DSLValidationError("Operator '%' expects numeric operands.")

        raise DSLValidationError(
            f"Unsupported binary operator in setup expression: {type(node.op).__name__}"
        )

    if isinstance(node, ast.BoolOp):
        if not node.values:
            raise DSLValidationError("Empty boolean expression is not supported.")
        if isinstance(node.op, ast.And):
            current = _eval_static_expr(node.values[0], env)
            for value_node in node.values[1:]:
                if not current:
                    return current
                current = _eval_static_expr(value_node, env)
            return current
        if isinstance(node.op, ast.Or):
            current = _eval_static_expr(node.values[0], env)
            for value_node in node.values[1:]:
                if current:
                    return current
                current = _eval_static_expr(value_node, env)
            return current
        raise DSLValidationError(
            f"Unsupported boolean operator in setup expression: {type(node.op).__name__}"
        )

    if isinstance(node, ast.Compare):
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise DSLValidationError("Chained comparisons are not supported in setup expressions.")
        left = _eval_static_expr(node.left, env)
        right = _eval_static_expr(node.comparators[0], env)
        op = node.ops[0]
        if isinstance(op, ast.Eq):
            return left == right
        if isinstance(op, ast.NotEq):
            return left != right
        if isinstance(op, ast.Lt):
            return left < right
        if isinstance(op, ast.LtE):
            return left <= right
        if isinstance(op, ast.Gt):
            return left > right
        if isinstance(op, ast.GtE):
            return left >= right
        if isinstance(op, ast.Is):
            return left is right
        if isinstance(op, ast.IsNot):
            return left is not right
        raise DSLValidationError(
            f"Unsupported comparison operator in setup expression: {type(op).__name__}"
        )

    if isinstance(node, ast.IfExp):
        condition = _eval_static_expr(node.test, env)
        if condition:
            return _eval_static_expr(node.body, env)
        return _eval_static_expr(node.orelse, env)

    if isinstance(node, ast.Call):
        if node.keywords:
            raise DSLValidationError("Keyword arguments are not supported in setup expression calls.")
        if isinstance(node.func, ast.Name):
            args = [_eval_static_expr(arg, env) for arg in node.args]
            if node.func.id == "str":
                if len(args) != 1:
                    raise DSLValidationError("str(...) expects exactly one argument.")
                return str(args[0])
            if node.func.id == "int":
                if len(args) != 1:
                    raise DSLValidationError("int(...) expects exactly one argument.")
                return int(args[0])
            if node.func.id == "float":
                if len(args) != 1:
                    raise DSLValidationError("float(...) expects exactly one argument.")
                return float(args[0])
            if node.func.id == "bool":
                if len(args) != 1:
                    raise DSLValidationError("bool(...) expects exactly one argument.")
                return bool(args[0])
            if node.func.id == "len":
                if len(args) != 1:
                    raise DSLValidationError("len(...) expects exactly one argument.")
                return len(args[0])
            if node.func.id == "range":
                if len(args) == 1:
                    return list(range(int(args[0])))
                if len(args) == 2:
                    return list(range(int(args[0]), int(args[1])))
                if len(args) == 3:
                    return list(range(int(args[0]), int(args[1]), int(args[2])))
                raise DSLValidationError("range(...) expects 1 to 3 arguments.")
            raise DSLValidationError(
                f"Unsupported setup builtin call '{node.func.id}(...)'."
            )
        if not isinstance(node.func, ast.Attribute):
            raise DSLValidationError(
                "Only collection helper calls are supported in setup expressions."
            )
        receiver = _eval_static_expr(node.func.value, env)
        args = [_eval_static_expr(arg, env) for arg in node.args]
        method = node.func.attr
        if method == "concat":
            if len(args) != 1:
                raise DSLValidationError("concat(...) expects exactly one argument.")
            other = args[0]
            if isinstance(receiver, list) and isinstance(other, list):
                return receiver + other
            if isinstance(receiver, dict) and isinstance(other, dict):
                return {**receiver, **other}
            if isinstance(receiver, str) and isinstance(other, str):
                return receiver + other
            raise DSLValidationError(
                "concat(...) is only supported for list/list, dict/dict, or str/str."
            )
        if method == "append":
            if len(args) != 1:
                raise DSLValidationError("append(...) expects exactly one argument.")
            if not isinstance(receiver, list):
                raise DSLValidationError("append(...) receiver must be a list.")
            return [*receiver, args[0]]
        if method == "pop":
            if isinstance(receiver, list):
                data = list(receiver)
                if len(args) == 0:
                    if not data:
                        raise DSLValidationError("pop() on empty list in setup expression.")
                    return data.pop()
                if len(args) == 1 and isinstance(args[0], int):
                    return data.pop(args[0])
                raise DSLValidationError("list.pop(...) expects no args or one int index.")
            if isinstance(receiver, dict):
                data = dict(receiver)
                if len(args) == 1:
                    return data.pop(args[0])
                if len(args) == 2:
                    return data.pop(args[0], args[1])
                raise DSLValidationError("dict.pop(...) expects key or key/default.")
            raise DSLValidationError("pop(...) receiver must be list or dict.")
        if method == "get":
            if not isinstance(receiver, dict):
                raise DSLValidationError("get(...) receiver must be a dict.")
            if len(args) == 1:
                return receiver.get(args[0])
            if len(args) == 2:
                return receiver.get(args[0], args[1])
            raise DSLValidationError("get(...) expects key or key/default.")
        if method == "keys":
            if not isinstance(receiver, dict):
                raise DSLValidationError("keys() receiver must be a dict.")
            if args:
                raise DSLValidationError("keys() does not accept arguments.")
            return list(receiver.keys())
        if method == "values":
            if not isinstance(receiver, dict):
                raise DSLValidationError("values() receiver must be a dict.")
            if args:
                raise DSLValidationError("values() does not accept arguments.")
            return list(receiver.values())
        if method == "items":
            if not isinstance(receiver, dict):
                raise DSLValidationError("items() receiver must be a dict.")
            if args:
                raise DSLValidationError("items() does not accept arguments.")
            return [[k, v] for k, v in receiver.items()]
        if method == "update":
            if not isinstance(receiver, dict):
                raise DSLValidationError("update(...) receiver must be a dict.")
            if len(args) != 1 or not isinstance(args[0], dict):
                raise DSLValidationError("update(...) expects exactly one dict argument.")
            return {**receiver, **args[0]}
        raise DSLValidationError(
            f"Unsupported setup expression method '{method}'."
        )

    raise DSLValidationError(f"Unsupported setup expression: {type(node).__name__}")


def _expect_string(node: ast.AST, label: str) -> str:
    value = _eval_static_expr(node)
    if isinstance(value, str):
        return value
    raise DSLValidationError(f"Expected {label} string.")


def _expect_string_list(node: ast.AST, label: str) -> List[str]:
    value = _eval_static_expr(node)
    if not isinstance(value, list):
        raise DSLValidationError(f"Expected {label} list.")
    out: List[str] = []
    for item in value:
        if not isinstance(item, str):
            raise DSLValidationError(f"Expected {label} list[str].")
        out.append(item)
    return out


def _expect_string_or_default(
    node: Optional[ast.AST],
    label: str,
    default: Optional[str],
) -> Optional[str]:
    if node is None:
        return default
    return _expect_string(node, label)


def _expect_single_character_or_default(
    node: Optional[ast.AST],
    label: str,
    default: Optional[str],
) -> Optional[str]:
    if node is None:
        return default
    value = _expect_string(node, label)
    if len(value) != 1:
        raise DSLValidationError(f"Expected {label} to be exactly one character.")
    return value


def _parse_multiplayer_loop_mode(value: str) -> MultiplayerLoopMode:
    for mode in MultiplayerLoopMode:
        if mode.value == value:
            return mode
    allowed = ", ".join(mode.value for mode in MultiplayerLoopMode)
    raise DSLValidationError(f"Unsupported multiplayer loop mode '{value}'. Expected one of: {allowed}.")


def _parse_visibility_mode(value: str) -> VisibilityMode:
    for mode in VisibilityMode:
        if mode.value == value:
            return mode
    allowed = ", ".join(mode.value for mode in VisibilityMode)
    raise DSLValidationError(f"Unsupported multiplayer visibility '{value}'. Expected one of: {allowed}.")


def _parse_role_kind(node: Optional[ast.AST]) -> RoleKind:
    if node is None:
        return RoleKind.HYBRID

    if isinstance(node, ast.Attribute):
        if isinstance(node.value, ast.Name) and node.value.id == "RoleKind":
            attr = node.attr.upper()
            for kind in RoleKind:
                if kind.name == attr:
                    return kind
            allowed = ", ".join(kind.name for kind in RoleKind)
            raise DSLValidationError(
                f"Unsupported RoleKind member '{node.attr}'. Expected one of: {allowed}."
            )

    kind_label = _expect_string(node, "role kind")
    normalized = kind_label.strip().lower()
    if normalized == "ai":
        return RoleKind.AI
    if normalized == "human":
        return RoleKind.HUMAN
    if normalized == "hybrid":
        return RoleKind.HYBRID
    allowed = ", ".join(kind.value for kind in RoleKind)
    raise DSLValidationError(
        f"Unsupported role kind '{kind_label}'. Expected one of: {allowed}."
    )


def _expect_string_or_string_list(node: ast.AST, label: str) -> str | List[str]:
    value = _eval_static_expr(node)
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        values: List[str] = []
        for item in value:
            if not isinstance(item, str):
                raise DSLValidationError(f"Expected {label} list[str].")
            values.append(item)
        if not values:
            raise DSLValidationError(f"Expected {label} list to contain at least one key.")
        return values
    raise DSLValidationError(f"Expected {label} string or list[str].")


def _expect_string_to_string_list_dict_or_default(
    node: Optional[ast.AST],
    label: str,
    default: Dict[str, List[str]],
) -> Dict[str, List[str]]:
    if node is None:
        return dict(default)
    parsed = _eval_static_expr(node)
    if not isinstance(parsed, dict):
        raise DSLValidationError(f"Expected {label} dict[str, str | list[str]].")

    out: Dict[str, List[str]] = {}
    for raw_key, raw_value in parsed.items():
        key = raw_key if isinstance(raw_key, str) else None
        if key is None:
            raise DSLValidationError(f"Expected {label} keys to be strings.")
        if not key:
            raise DSLValidationError(f"Expected {label} key to be non-empty.")
        if isinstance(raw_value, str):
            raw_values: str | List[str] = raw_value
        elif isinstance(raw_value, list):
            raw_values = raw_value
        else:
            raise DSLValidationError(f"Expected {label} value string or list[str].")
        values = [raw_values] if isinstance(raw_values, str) else raw_values
        deduped: List[str] = []
        seen: set[str] = set()
        for value in values:
            if not value:
                raise DSLValidationError(
                    f"Expected {label} values for key '{key}' to be non-empty strings."
                )
            if value in seen:
                continue
            seen.add(value)
            deduped.append(value)
        out[key] = deduped
    return out


def _expect_int(node: ast.AST, label: str) -> int:
    value = _eval_static_expr(node)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise DSLValidationError(f"Expected {label} integer.")


def _expect_int_or_default(node: Optional[ast.AST], label: str, default: int) -> int:
    if node is None:
        return default
    return _expect_int(node, label)


def _expect_number(node: ast.AST, label: str) -> float:
    value = _eval_static_expr(node)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    raise DSLValidationError(f"Expected {label} number.")


def _expect_number_or_default(
    node: Optional[ast.AST], label: str, default: float
) -> float:
    if node is None:
        return default
    return _expect_number(node, label)


def _expect_float_or_default(
    node: Optional[ast.AST], label: str, default: float
) -> float:
    if node is None:
        return default
    value = _eval_static_expr(node)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    raise DSLValidationError(f"Expected {label} float.")


def _expect_bool_or_default(node: Optional[ast.AST], label: str, default: bool) -> bool:
    if node is None:
        return default
    value = _eval_static_expr(node)
    if isinstance(value, bool):
        return value
    raise DSLValidationError(f"Expected {label} bool.")


def _expect_int_list(node: ast.AST, label: str) -> List[int]:
    values_raw = _eval_static_expr(node)
    if not isinstance(values_raw, list):
        raise DSLValidationError(f"Expected {label} as list[int].")
    values: List[int] = []
    for item in values_raw:
        if isinstance(item, int) and not isinstance(item, bool):
            values.append(item)
            continue
        raise DSLValidationError(f"Expected {label} as list[int].")
    if not values:
        raise DSLValidationError(f"Expected {label} to contain at least one frame.")
    return values


def _expect_int_matrix(node: ast.AST, label: str) -> List[List[int]]:
    rows_raw = _eval_static_expr(node)
    if not isinstance(rows_raw, list):
        raise DSLValidationError(f"Expected {label} as list[list[int]].")
    rows: List[List[int]] = []
    for row_node in rows_raw:
        if not isinstance(row_node, list):
            raise DSLValidationError(f"Expected {label} rows as list[int].")
        row_values: List[int] = []
        for cell in row_node:
            if isinstance(cell, int) and not isinstance(cell, bool):
                row_values.append(cell)
                continue
            raise DSLValidationError(f"Expected {label} cell integer.")
        rows.append(row_values)
    return rows


def _expect_optional_int(node: ast.AST, label: str) -> Optional[int]:
    value = _eval_static_expr(node)
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise DSLValidationError(f"Expected {label} integer.")


def _expect_primitive_or_nested_list_constant(node: ast.AST):
    if isinstance(node, ast.List):
        return [_expect_primitive_or_nested_list_constant(elem) for elem in node.elts]
    if not isinstance(node, ast.Constant):
        raise DSLValidationError(
            "List global values can only contain primitive constants or nested lists of primitives."
        )
    if isinstance(node.value, bool):
        return node.value
    if isinstance(node.value, (int, float, str)):
        return node.value
    raise DSLValidationError("Unsupported primitive value in list.")


def _infer_primitive_list_kind(values: List[object]) -> str:
    if not values:
        return "any"
    if all(isinstance(v, list) for v in values):
        nested = [_infer_primitive_list_kind(v) for v in values if isinstance(v, list)]
        if not nested:
            return "list[any]"
        first = nested[0]
        if any(kind != first for kind in nested[1:]):
            raise DSLValidationError("Global list values must have homogeneous element types.")
        return f"list[{first}]"
    if all(isinstance(v, bool) for v in values):
        return "bool"
    if all(isinstance(v, int) and not isinstance(v, bool) for v in values):
        return "int"
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
        return "float"
    if all(isinstance(v, str) for v in values):
        return "str"
    if all(isinstance(v, dict) for v in values):
        dict_kinds = [
            _infer_primitive_dict_kind(v) for v in values if isinstance(v, dict)
        ]
        first = dict_kinds[0]
        if any(kind != first for kind in dict_kinds[1:]):
            raise DSLValidationError("Global list values must have homogeneous dict element types.")
        return first
    raise DSLValidationError("Global list values must have homogeneous primitive types.")


def _infer_primitive_dict_kind(values: Dict[object, object]) -> str:
    if not values:
        return "dict[str, any]"
    key_types: set[str] = set()
    value_types: List[str] = []

    for key, value in values.items():
        if not isinstance(key, str):
            raise DSLValidationError("Global dict values must use string keys.")
        key_types.add("str")

        if isinstance(value, bool):
            value_types.append("bool")
            continue
        if isinstance(value, int) and not isinstance(value, bool):
            value_types.append("int")
            continue
        if isinstance(value, float):
            value_types.append("float")
            continue
        if isinstance(value, str):
            value_types.append("str")
            continue
        if isinstance(value, list):
            value_types.append(f"list[{_infer_primitive_list_kind(value)}]")
            continue
        if isinstance(value, dict):
            value_types.append(_infer_primitive_dict_kind(value))
            continue
        raise DSLValidationError("Global dict values must contain primitive/list/dict values.")

    value_type = value_types[0]
    if any(kind != value_type for kind in value_types[1:]):
        raise DSLValidationError("Global dict values must have homogeneous value types.")
    return f"dict[str, {value_type}]"


def _parse_typed_value(node: ast.AST, field_type: FieldType):
    value = _eval_static_expr(node)

    if isinstance(field_type, PrimType):
        if field_type.prim == Prim.BOOL:
            if isinstance(value, bool):
                return value
            raise DSLValidationError("Expected bool value.")
        if field_type.prim == Prim.INT:
            if isinstance(value, int) and not isinstance(value, bool):
                return value
            raise DSLValidationError("Expected int value.")
        if field_type.prim == Prim.FLOAT:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
            raise DSLValidationError("Expected float value.")
        if field_type.prim == Prim.STR:
            if isinstance(value, str):
                return value
            raise DSLValidationError("Expected str value.")

    if isinstance(field_type, ListType):
        if not isinstance(value, list):
            raise DSLValidationError("Expected list value.")
        parsed_list = []
        for elem in value:
            parsed_list.append(_parse_typed_runtime_value(elem, field_type.elem))
        return parsed_list

    if isinstance(field_type, DictType):
        if not isinstance(value, dict):
            raise DSLValidationError("Expected dict value.")
        parsed_dict: Dict[str, object] = {}
        for key, item in value.items():
            parsed_key = _parse_typed_runtime_value(key, field_type.key)
            if not isinstance(parsed_key, str):
                raise DSLValidationError("Dict keys must be strings.")
            parsed_dict[parsed_key] = _parse_typed_runtime_value(item, field_type.value)
        return parsed_dict

    raise DSLValidationError("Unsupported field type in actor instance.")


def _default_value_for_type(field_type: FieldType):
    if isinstance(field_type, PrimType):
        if field_type.prim == Prim.BOOL:
            return False
        if field_type.prim == Prim.INT:
            return 0
        if field_type.prim == Prim.FLOAT:
            return 0.0
        if field_type.prim == Prim.STR:
            return ""
    if isinstance(field_type, ListType):
        return []
    if isinstance(field_type, DictType):
        return {}
    raise DSLValidationError("Unsupported field type for default value.")


def _field_type_label(field_type: FieldType) -> str:
    if isinstance(field_type, PrimType):
        return field_type.prim.value
    if isinstance(field_type, ListType):
        return f"list[{_field_type_label(field_type.elem)}]"
    if isinstance(field_type, DictType):
        return f"dict[{_field_type_label(field_type.key)}, {_field_type_label(field_type.value)}]"
    raise DSLValidationError("Unsupported field type in schema export.")


def _parse_global_type_expr(node: ast.AST) -> FieldType:
    if isinstance(node, ast.Name):
        if node.id == "int":
            return PrimType(Prim.INT)
        if node.id == "float":
            return PrimType(Prim.FLOAT)
        if node.id == "str":
            return PrimType(Prim.STR)
        if node.id == "bool":
            return PrimType(Prim.BOOL)
        raise DSLValidationError(
            "GlobalVariable type must be int, float, str, bool, List[...], or Dict[str, ...]."
        )

    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
        if node.value.id in {"List", "list"}:
            return ListType(_parse_global_type_expr(node.slice))
        if node.value.id in {"Dict", "dict"}:
            if not isinstance(node.slice, ast.Tuple) or len(node.slice.elts) != 2:
                raise DSLValidationError(
                    "GlobalVariable Dict type must be Dict[str, value_type]."
                )
            key_type = _parse_global_type_expr(node.slice.elts[0])
            if not isinstance(key_type, PrimType) or key_type.prim != Prim.STR:
                raise DSLValidationError("GlobalVariable dict keys must be str.")
            value_type = _parse_global_type_expr(node.slice.elts[1])
            return DictType(key=key_type, value=value_type)

    raise DSLValidationError(
        "GlobalVariable type must be int, float, str, bool, List[...], or Dict[str, ...]."
    )


def _parse_typed_runtime_value(value, field_type: FieldType):
    if isinstance(field_type, PrimType):
        if field_type.prim == Prim.BOOL:
            if isinstance(value, bool):
                return value
            raise DSLValidationError("Expected bool value.")
        if field_type.prim == Prim.INT:
            if isinstance(value, int) and not isinstance(value, bool):
                return value
            raise DSLValidationError("Expected int value.")
        if field_type.prim == Prim.FLOAT:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
            raise DSLValidationError("Expected float value.")
        if field_type.prim == Prim.STR:
            if isinstance(value, str):
                return value
            raise DSLValidationError("Expected str value.")

    if isinstance(field_type, ListType):
        if not isinstance(value, list):
            raise DSLValidationError("Expected list value.")
        return [_parse_typed_runtime_value(item, field_type.elem) for item in value]

    if isinstance(field_type, DictType):
        if not isinstance(value, dict):
            raise DSLValidationError("Expected dict value.")
        parsed: Dict[str, object] = {}
        for key, item in value.items():
            parsed_key = _parse_typed_runtime_value(key, field_type.key)
            if not isinstance(parsed_key, str):
                raise DSLValidationError("Dict keys must be strings.")
            parsed[parsed_key] = _parse_typed_runtime_value(item, field_type.value)
        return parsed

    raise DSLValidationError("Unsupported field type in actor instance.")
