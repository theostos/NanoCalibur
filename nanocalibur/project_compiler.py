import ast
from typing import Dict, List, Optional, Tuple, cast

from nanocalibur.compiler import DSLCompiler
from nanocalibur.errors import DSLValidationError
from nanocalibur.game_model import (
    ActorInstanceSpec,
    ActorRefValue,
    ActorSelectorSpec,
    CameraMode,
    CameraSpec,
    CollisionConditionSpec,
    ConditionSpec,
    GlobalValueKind,
    GlobalVariableSpec,
    InputPhase,
    KeyboardConditionSpec,
    LogicalConditionSpec,
    MouseConditionSpec,
    ProjectSpec,
    RuleSpec,
    SelectorKind,
    TileMapSpec,
)
from nanocalibur.ir import ActionIR, PredicateIR
from nanocalibur.typesys import FieldType, ListType, Prim, PrimType


class ProjectCompiler:
    def compile(self, source: str) -> ProjectSpec:
        module = ast.parse(source)
        compiler = DSLCompiler()

        game_var = self._discover_game_variable(module)
        self._register_actor_schemas(module, compiler)

        globals_spec = self._collect_globals(module, game_var, compiler)
        global_actor_types = {
            g.name: g.value.actor_type if isinstance(g.value, ActorRefValue) else None
            for g in globals_spec
        }
        compiler.global_actor_types = global_actor_types

        actions, predicates = self._compile_functions(module, compiler)
        conditions, actors, rules, tile_map, camera = self._collect_game_setup(
            module=module,
            game_var=game_var,
            compiler=compiler,
            actions=actions,
            predicates=predicates,
        )

        actor_schemas = {
            actor_type: {
                field_name: _field_type_label(field_type)
                for field_name, field_type in fields.items()
            }
            for actor_type, fields in compiler.schemas.actor_fields.items()
        }

        return ProjectSpec(
            actor_schemas=actor_schemas,
            globals=globals_spec,
            actors=actors,
            rules=rules,
            tile_map=tile_map,
            camera=camera,
            actions=list(actions.values()),
            predicates=list(predicates.values()),
        )

    def _discover_game_variable(self, module: ast.Module) -> str:
        for node in module.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            if not (
                isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == "Game"
            ):
                continue
            return target.id
        raise DSLValidationError(
            "Project must declare a game object with 'game = Game()'."
        )

    def _register_actor_schemas(self, module: ast.Module, compiler: DSLCompiler) -> None:
        for node in module.body:
            if isinstance(node, ast.ClassDef):
                compiler._register_actor_schema(node)

    def _collect_globals(
        self,
        module: ast.Module,
        game_var: str,
        compiler: DSLCompiler,
    ) -> List[GlobalVariableSpec]:
        globals_spec: Dict[str, GlobalVariableSpec] = {}

        for node in module.body:
            if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
                continue

            method = _as_game_method_call(node.value, game_var)
            if method is None:
                continue
            method_name, args, kwargs = method
            if method_name not in {"add_global", "addGlobal", "add"}:
                continue
            if kwargs:
                raise DSLValidationError("add_global(...) does not accept keyword args.")
            if len(args) != 2:
                raise DSLValidationError(
                    "add_global(...) expects exactly 2 positional arguments."
                )

            global_name = _expect_string(args[0], "global variable name")
            value = self._parse_global_value(args[1], compiler)
            globals_spec[global_name] = GlobalVariableSpec(
                name=global_name,
                kind=value[0],
                value=value[1],
                list_elem_kind=value[2],
            )

        return list(globals_spec.values())

    def _compile_functions(
        self, module: ast.Module, compiler: DSLCompiler
    ) -> Tuple[Dict[str, ActionIR], Dict[str, PredicateIR]]:
        actions: Dict[str, ActionIR] = {}
        predicates: Dict[str, PredicateIR] = {}

        for node in module.body:
            if not isinstance(node, ast.FunctionDef):
                continue

            if _looks_like_predicate(node, compiler):
                predicates[node.name] = compiler._compile_predicate(node)
            elif _looks_like_action(node):
                actions[node.name] = compiler._compile_action(node)
            else:
                raise DSLValidationError(
                    f"Unsupported function signature for '{node.name}'."
                )

        return actions, predicates

    def _collect_game_setup(
        self,
        module: ast.Module,
        game_var: str,
        compiler: DSLCompiler,
        actions: Dict[str, ActionIR],
        predicates: Dict[str, PredicateIR],
    ) -> Tuple[
        Dict[str, ConditionSpec],
        List[ActorInstanceSpec],
        List[RuleSpec],
        Optional[TileMapSpec],
        Optional[CameraSpec],
    ]:
        condition_vars: Dict[str, ConditionSpec] = {}
        actors: List[ActorInstanceSpec] = []
        rules: List[RuleSpec] = []
        tile_map: Optional[TileMapSpec] = None
        camera: Optional[CameraSpec] = None

        for node in module.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name) and isinstance(node.value, ast.Call):
                    if (
                        isinstance(node.value.func, ast.Name)
                        and node.value.func.id == "Game"
                    ):
                        continue

                    if self._is_condition_expr(node.value):
                        condition_vars[target.id] = self._parse_condition(
                            node.value, compiler, predicates
                        )
                        continue

            if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
                continue

            method = _as_game_method_call(node.value, game_var)
            if method is None:
                continue
            method_name, args, kwargs = method

            if method_name in {"add_actor", "addActor"}:
                actors.append(self._parse_actor_instance(args, kwargs, compiler))
                continue

            if method_name in {"add_rule", "addRules"}:
                if kwargs:
                    raise DSLValidationError("add_rule(...) does not accept keyword args.")
                if len(args) != 2:
                    raise DSLValidationError(
                        "add_rule(...) expects exactly 2 positional arguments."
                    )
                condition = self._resolve_condition_arg(
                    args[0], condition_vars, compiler, predicates
                )
                action_name = _expect_name(args[1], "action function")
                if action_name not in actions:
                    raise DSLValidationError(
                        f"Unknown action '{action_name}' in add_rule(...)."
                    )
                rules.append(RuleSpec(condition=condition, action_name=action_name))
                continue

            if method_name in {"set_map", "setMap"}:
                if kwargs:
                    raise DSLValidationError("set_map(...) does not accept keyword args.")
                if len(args) != 1:
                    raise DSLValidationError("set_map(...) expects one argument.")
                tile_map = self._parse_tile_map(args[0])
                continue

            if method_name in {"set_camera", "setCamera"}:
                if kwargs:
                    raise DSLValidationError(
                        "set_camera(...) does not accept keyword args."
                    )
                if len(args) != 1:
                    raise DSLValidationError("set_camera(...) expects one argument.")
                camera = self._parse_camera(args[0])
                continue

            if method_name in {"add_global", "addGlobal", "add"}:
                continue

            raise DSLValidationError(f"Unsupported game method '{method_name}'.")

        return condition_vars, actors, rules, tile_map, camera

    def _parse_global_value(
        self, node: ast.AST, compiler: DSLCompiler
    ) -> Tuple[GlobalValueKind, object, Optional[str]]:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return GlobalValueKind.BOOL, node.value, None
            if isinstance(node.value, int):
                return GlobalValueKind.INT, node.value, None
            if isinstance(node.value, float):
                return GlobalValueKind.FLOAT, node.value, None
            if isinstance(node.value, str):
                return GlobalValueKind.STR, node.value, None
            raise DSLValidationError("Unsupported constant type in global value.")

        if isinstance(node, ast.List):
            values = [_expect_primitive_constant(e) for e in node.elts]
            list_kind = _infer_primitive_list_kind(values)
            return GlobalValueKind.LIST, values, list_kind

        if isinstance(node, ast.Call):
            selector = self._parse_selector(node, compiler)
            if selector.kind != SelectorKind.WITH_UID or selector.uid is None:
                raise DSLValidationError(
                    "Global actor pointer must use WithUID(ActorType, \"uid\")."
                )
            return (
                GlobalValueKind.ACTOR_REF,
                ActorRefValue(uid=selector.uid, actor_type=selector.actor_type),
                None,
            )

        raise DSLValidationError("Unsupported global value.")

    def _parse_actor_instance(
        self,
        args: List[ast.AST],
        kwargs: Dict[str, ast.AST],
        compiler: DSLCompiler,
    ) -> ActorInstanceSpec:
        if not args:
            raise DSLValidationError("add_actor(...) expects actor type as first argument.")

        actor_type = _expect_name(args[0], "actor type")
        if actor_type not in compiler.schemas.actor_fields:
            raise DSLValidationError(f"Unknown actor schema '{actor_type}'.")

        uid: Optional[str] = None
        if len(args) > 1:
            uid = _expect_string(args[1], "actor uid")
        if "uid" in kwargs:
            uid = _expect_string(kwargs["uid"], "actor uid")
        if uid is None:
            raise DSLValidationError("add_actor(...) requires an actor uid.")

        schema_fields = compiler.schemas.actor_fields[actor_type]
        values: Dict[str, object] = {}
        for key, value_node in kwargs.items():
            if key == "uid":
                continue
            if key not in schema_fields:
                raise DSLValidationError(
                    f"Unknown field '{key}' for actor type '{actor_type}'."
                )
            values[key] = _parse_typed_value(value_node, schema_fields[key])

        for field_name, field_type in schema_fields.items():
            if field_name in values:
                continue
            values[field_name] = _default_value_for_type(field_type)

        return ActorInstanceSpec(
            actor_type=actor_type,
            uid=uid,
            fields=cast(Dict[str, object], values),  # only primitive/list values stored
        )

    def _is_condition_expr(self, node: ast.Call) -> bool:
        if isinstance(node.func, ast.Name):
            return node.func.id in {"CollisionRelated", "LogicalRelated"}
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            return node.func.value.id in {
                "KeyboardCondition",
                "KeyBoardCondition",
                "MouseCondition",
                "MouseRelated",
            }
        return False

    def _resolve_condition_arg(
        self,
        node: ast.AST,
        conditions: Dict[str, ConditionSpec],
        compiler: DSLCompiler,
        predicates: Dict[str, PredicateIR],
    ) -> ConditionSpec:
        if isinstance(node, ast.Name):
            if node.id not in conditions:
                raise DSLValidationError(f"Unknown condition variable '{node.id}'.")
            return conditions[node.id]
        if isinstance(node, ast.Call):
            return self._parse_condition(node, compiler, predicates)
        raise DSLValidationError("add_rule(...) condition must be a condition expression.")

    def _parse_condition(
        self,
        node: ast.Call,
        compiler: DSLCompiler,
        predicates: Dict[str, PredicateIR],
    ) -> ConditionSpec:
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            owner = node.func.value.id
            method = node.func.attr

            if owner in {"KeyboardCondition", "KeyBoardCondition"}:
                phase = _parse_keyboard_phase(method)
                if phase is None:
                    raise DSLValidationError("Unsupported keyboard condition method.")
                if len(node.args) != 1 or node.keywords:
                    raise DSLValidationError(
                        "KeyboardCondition.<phase>(...) expects one argument."
                    )
                return KeyboardConditionSpec(
                    key=_expect_string(node.args[0], "keyboard key"),
                    phase=phase,
                )

            if owner in {"MouseCondition", "MouseRelated"}:
                phase = _parse_mouse_phase(method)
                if phase is None:
                    raise DSLValidationError("Unsupported mouse condition method.")
                if node.keywords:
                    raise DSLValidationError(
                        "MouseCondition.<phase>(...) does not accept keyword args."
                    )
                if len(node.args) == 0:
                    return MouseConditionSpec(button="left", phase=phase)
                if len(node.args) == 1:
                    return MouseConditionSpec(
                        button=_expect_string(node.args[0], "mouse button"),
                        phase=phase,
                    )
                raise DSLValidationError(
                    "MouseCondition.<phase>(...) accepts zero or one argument."
                )

        if isinstance(node.func, ast.Name) and node.func.id == "CollisionRelated":
            if len(node.args) != 2 or node.keywords:
                raise DSLValidationError("CollisionRelated(...) expects two selectors.")
            left = self._parse_selector(node.args[0], compiler)
            right = self._parse_selector(node.args[1], compiler)
            return CollisionConditionSpec(left=left, right=right)

        if isinstance(node.func, ast.Name) and node.func.id == "LogicalRelated":
            if len(node.args) != 2 or node.keywords:
                raise DSLValidationError(
                    "LogicalRelated(...) expects predicate and selector."
                )
            predicate_name = _expect_name(node.args[0], "logical predicate function")
            if predicate_name not in predicates:
                raise DSLValidationError(
                    f"Unknown predicate function '{predicate_name}'."
                )
            selector = self._parse_selector(node.args[1], compiler)
            predicate = predicates[predicate_name]
            if (
                selector.actor_type is not None
                and selector.actor_type != predicate.actor_type
            ):
                raise DSLValidationError(
                    f"LogicalRelated selector type '{selector.actor_type}' does not "
                    f"match predicate actor type '{predicate.actor_type}'."
                )
            return LogicalConditionSpec(predicate_name=predicate_name, target=selector)

        raise DSLValidationError("Unsupported condition expression.")

    def _parse_selector(
        self, node: ast.AST, compiler: DSLCompiler
    ) -> ActorSelectorSpec:
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            raise DSLValidationError("Selector must be Any(...) or WithUID(...).")

        if node.func.id == "Any":
            if len(node.args) != 1 or node.keywords:
                raise DSLValidationError("Any(...) expects one actor type.")
            actor_type = self._parse_actor_type_ref(node.args[0], compiler)
            return ActorSelectorSpec(kind=SelectorKind.ANY, actor_type=actor_type)

        if node.func.id == "WithUID":
            if len(node.args) != 2 or node.keywords:
                raise DSLValidationError("WithUID(...) expects actor type and uid.")
            actor_type = self._parse_actor_type_ref(node.args[0], compiler)
            uid = _expect_string(node.args[1], "actor uid")
            return ActorSelectorSpec(
                kind=SelectorKind.WITH_UID,
                actor_type=actor_type,
                uid=uid,
            )

        raise DSLValidationError("Unknown selector helper.")

    def _parse_actor_type_ref(
        self, node: ast.AST, compiler: DSLCompiler
    ) -> Optional[str]:
        actor_name = _expect_name(node, "actor type")
        if actor_name == "Actor":
            return None
        if actor_name not in compiler.schemas.actor_fields:
            raise DSLValidationError(f"Unknown actor schema '{actor_name}'.")
        return actor_name

    def _parse_tile_map(self, node: ast.AST) -> TileMapSpec:
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            raise DSLValidationError("set_map(...) expects TileMap(...).")
        if node.func.id != "TileMap":
            raise DSLValidationError("set_map(...) expects TileMap(...).")
        if node.args:
            raise DSLValidationError("TileMap(...) only supports keyword arguments.")

        kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg is not None}
        required = {"width", "height", "tile_size", "solid"}
        missing = required - set(kwargs.keys())
        if missing:
            raise DSLValidationError(f"TileMap(...) missing arguments: {sorted(missing)}")

        width = _expect_int(kwargs["width"], "map width")
        height = _expect_int(kwargs["height"], "map height")
        tile_size = _expect_int(kwargs["tile_size"], "map tile_size")
        solid_tiles = _expect_xy_list(kwargs["solid"], "map solid tiles")
        return TileMapSpec(
            width=width,
            height=height,
            tile_size=tile_size,
            solid_tiles=solid_tiles,
        )

    def _parse_camera(self, node: ast.AST) -> CameraSpec:
        if not isinstance(node, ast.Call):
            raise DSLValidationError("set_camera(...) expects Camera.fixed/follow call.")
        if not (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "Camera"
        ):
            raise DSLValidationError("set_camera(...) expects Camera.fixed/follow call.")

        method = node.func.attr
        if method == "fixed":
            if len(node.args) != 2 or node.keywords:
                raise DSLValidationError("Camera.fixed(...) expects x and y.")
            return CameraSpec(
                mode=CameraMode.FIXED,
                x=_expect_int(node.args[0], "camera x"),
                y=_expect_int(node.args[1], "camera y"),
            )

        if method == "follow":
            if len(node.args) != 1 or node.keywords:
                raise DSLValidationError("Camera.follow(...) expects target uid.")
            return CameraSpec(
                mode=CameraMode.FOLLOW,
                target_uid=_expect_string(node.args[0], "camera target uid"),
            )

        raise DSLValidationError("Unsupported camera configuration.")


def _looks_like_action(fn: ast.FunctionDef) -> bool:
    if fn.returns is not None:
        return False
    return all(arg.annotation is not None and isinstance(arg.annotation, ast.Subscript) for arg in fn.args.args)


def _looks_like_predicate(fn: ast.FunctionDef, compiler: DSLCompiler) -> bool:
    if len(fn.args.args) != 1:
        return False
    arg = fn.args.args[0]
    if not isinstance(arg.annotation, ast.Name):
        return False
    if arg.annotation.id not in compiler.schemas.actor_fields:
        return False
    return isinstance(fn.returns, ast.Name) and fn.returns.id == "bool"


def _as_game_method_call(
    call: ast.Call, game_var: str
) -> Optional[Tuple[str, List[ast.AST], Dict[str, ast.AST]]]:
    if not (
        isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == game_var
    ):
        return None
    kwargs = {kw.arg: kw.value for kw in call.keywords if kw.arg is not None}
    return call.func.attr, list(call.args), kwargs


def _parse_keyboard_phase(method: str) -> InputPhase | None:
    begin_methods = {"begin_press", "just_pressed", "on_begin_press", "pressed_begin"}
    on_methods = {"on_press", "is_pressed", "pressed"}
    end_methods = {"end_press", "released", "just_released", "on_end_press"}
    if method in begin_methods:
        return InputPhase.BEGIN
    if method in on_methods:
        return InputPhase.ON
    if method in end_methods:
        return InputPhase.END
    return None


def _parse_mouse_phase(method: str) -> InputPhase | None:
    begin_methods = {"begin_click", "just_clicked", "on_begin_click"}
    on_methods = {"on_click", "clicked", "is_clicked"}
    end_methods = {"end_click", "click_released", "on_end_click"}
    if method in begin_methods:
        return InputPhase.BEGIN
    if method in on_methods:
        return InputPhase.ON
    if method in end_methods:
        return InputPhase.END
    return None


def _expect_name(node: ast.AST, label: str) -> str:
    if isinstance(node, ast.Name):
        return node.id
    raise DSLValidationError(f"Expected {label} name.")


def _expect_string(node: ast.AST, label: str) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    raise DSLValidationError(f"Expected {label} string.")


def _expect_int(node: ast.AST, label: str) -> int:
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
    ):
        return node.value
    raise DSLValidationError(f"Expected {label} integer.")


def _expect_xy_list(node: ast.AST, label: str) -> List[Tuple[int, int]]:
    if not isinstance(node, ast.List):
        raise DSLValidationError(f"Expected {label} as a list of (x, y) tuples.")
    tiles: List[Tuple[int, int]] = []
    for elem in node.elts:
        if (
            not isinstance(elem, ast.Tuple)
            or len(elem.elts) != 2
        ):
            raise DSLValidationError(f"Expected {label} as list[(int, int)].")
        tiles.append(
            (_expect_int(elem.elts[0], "tile x"), _expect_int(elem.elts[1], "tile y"))
        )
    return tiles


def _expect_primitive_constant(node: ast.AST):
    if not isinstance(node, ast.Constant):
        raise DSLValidationError("List global values can only contain constants.")
    if isinstance(node.value, bool):
        return node.value
    if isinstance(node.value, (int, float, str)):
        return node.value
    raise DSLValidationError("Unsupported primitive value in list.")


def _infer_primitive_list_kind(values: List[object]) -> str:
    if not values:
        return "any"
    if all(isinstance(v, bool) for v in values):
        return "bool"
    if all(isinstance(v, int) and not isinstance(v, bool) for v in values):
        return "int"
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
        return "float"
    if all(isinstance(v, str) for v in values):
        return "str"
    raise DSLValidationError("Global list values must have homogeneous primitive types.")


def _parse_typed_value(node: ast.AST, field_type: FieldType):
    if isinstance(field_type, PrimType):
        if field_type.prim == Prim.BOOL:
            if isinstance(node, ast.Constant) and isinstance(node.value, bool):
                return node.value
            raise DSLValidationError("Expected bool value.")
        if field_type.prim == Prim.INT:
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, int)
                and not isinstance(node.value, bool)
            ):
                return node.value
            raise DSLValidationError("Expected int value.")
        if field_type.prim == Prim.FLOAT:
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                if isinstance(node.value, bool):
                    raise DSLValidationError("Expected float value.")
                return float(node.value)
            raise DSLValidationError("Expected float value.")
        if field_type.prim == Prim.STR:
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                return node.value
            raise DSLValidationError("Expected str value.")

    if isinstance(field_type, ListType):
        if not isinstance(node, ast.List):
            raise DSLValidationError("Expected list value.")
        return [_parse_typed_value(elem, field_type.elem) for elem in node.elts]

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
    raise DSLValidationError("Unsupported field type for default value.")


def _field_type_label(field_type: FieldType) -> str:
    if isinstance(field_type, PrimType):
        return field_type.prim.value
    if isinstance(field_type, ListType):
        return f"list[{field_type.elem.prim.value}]"
    raise DSLValidationError("Unsupported field type in schema export.")
