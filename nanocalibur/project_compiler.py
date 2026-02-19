import ast
import copy
import warnings
from dataclasses import replace
from pathlib import Path
from typing import Dict, List, Optional, Tuple, cast

from nanocalibur.compiler import (
    BASE_ACTOR_DEFAULT_OVERRIDES,
    BASE_ACTOR_NO_DEFAULT_FIELDS,
    CALLABLE_EXPR_PREFIX,
    DSLCompiler,
)
from nanocalibur.codeblocks import preprocess_code_blocks
from nanocalibur.errors import (
    DSLValidationError,
    dsl_node_context,
    dsl_source_context,
    format_dsl_diagnostic,
)
from nanocalibur.game_model import (
    AnimationClipSpec,
    ActorInstanceSpec,
    ActorRefValue,
    ActorSelectorSpec,
    ButtonConditionSpec,
    CameraMode,
    CameraSpec,
    CollisionMode,
    ColorSpec,
    CollisionConditionSpec,
    ConditionSpec,
    GlobalValueKind,
    GlobalVariableSpec,
    InputPhase,
    KeyboardConditionSpec,
    LogicalConditionSpec,
    MultiplayerLoopMode,
    MultiplayerSpec,
    MouseConditionSpec,
    ProjectSpec,
    RoleKind,
    RoleSpec,
    ResourceSpec,
    RuleSpec,
    SceneSpec,
    SelectorKind,
    SpriteSpec,
    TileSpec,
    TileMapSpec,
    ToolConditionSpec,
    VisibilityMode,
)
from nanocalibur.ir import (
    ActionIR,
    ActorSelector,
    Attr,
    Assign,
    BindingKind,
    Binary,
    CallableIR,
    CallExpr,
    CallStmt,
    Const,
    Continue,
    For,
    If,
    ListExpr,
    ObjectExpr,
    ParamBinding,
    PredicateIR,
    Range,
    SubscriptExpr,
    Unary,
    Var,
    While,
    Yield,
)
from nanocalibur.typesys import DictType, FieldType, ListType, Prim, PrimType


COLLISION_LEFT_BINDING_UID = "__nanocalibur_collision_left__"
COLLISION_RIGHT_BINDING_UID = "__nanocalibur_collision_right__"
LOGICAL_TARGET_BINDING_UID = "__nanocalibur_logical_target__"


class ProjectCompiler:
    def __init__(self) -> None:
        self._source_dir = Path.cwd()

    def compile(
        self,
        source: str,
        source_path: str | Path | None = None,
        *,
        require_code_blocks: bool = False,
        unboxed_disable_flag: str = "--allow-unboxed",
    ) -> ProjectSpec:
        """Compile a full DSL project source into structured project metadata."""
        if source_path is not None:
            self._source_dir = Path(source_path).resolve().parent
        else:
            self._source_dir = Path.cwd()

        with dsl_source_context(source):
            preprocessed_source = preprocess_code_blocks(
                source,
                require_code_blocks=require_code_blocks,
                unboxed_disable_flag=unboxed_disable_flag,
            )
        with dsl_source_context(preprocessed_source):
            try:
                module = ast.parse(preprocessed_source)
            except SyntaxError as exc:
                raise DSLValidationError(_format_syntax_error(exc, preprocessed_source)) from exc

            compiler = DSLCompiler()

            game_var = self._discover_game_variable(module)
            self._register_actor_schemas(module, compiler)

            globals_spec = self._collect_globals(module, game_var, compiler)
            global_actor_types = {
                g.name: g.value.actor_type if isinstance(g.value, ActorRefValue) else None
                for g in globals_spec
            }
            compiler.global_actor_types = global_actor_types

            actions, predicates, callables = self._compile_functions(module, compiler)
            (
                conditions,
                actors,
                rules,
                tile_map,
                camera,
                resources,
                sprites,
                scene,
                interface_html,
                multiplayer,
                roles,
            ) = self._collect_game_setup(
                module=module,
                game_var=game_var,
                compiler=compiler,
                actions=actions,
                predicates=predicates,
                callables=callables,
            )

            function_nodes = {
                node.name: node
                for node in module.body
                if isinstance(node, ast.FunctionDef)
            }

            used_action_names = {rule.action_name for rule in rules}
            ignored_action_names = sorted(
                name for name in actions.keys() if name not in used_action_names
            )
            for action_name in ignored_action_names:
                node = function_nodes.get(action_name)
                warnings.warn(
                    format_dsl_diagnostic(
                        f"Function '{action_name}' is ignored because no rule references it.",
                        node=node,
                    ),
                    stacklevel=2,
                )
            actions = {
                name: action
                for name, action in actions.items()
                if name in used_action_names
            }

            used_predicate_names = {
                rule.condition.predicate_name
                for rule in rules
                if isinstance(rule.condition, LogicalConditionSpec)
            }
            ignored_predicate_names = sorted(
                name for name in predicates.keys() if name not in used_predicate_names
            )
            for predicate_name in ignored_predicate_names:
                node = function_nodes.get(predicate_name)
                warnings.warn(
                    format_dsl_diagnostic(
                        f"Function '{predicate_name}' is ignored because no OnLogicalCondition(...) references it.",
                        node=node,
                    ),
                    stacklevel=2,
                )
            predicates = {
                name: predicate
                for name, predicate in predicates.items()
                if name in used_predicate_names
            }

            used_callable_names = _collect_used_callable_names(
                actions=list(actions.values()),
                predicates=list(predicates.values()),
                callables=callables,
            )
            ignored_callable_names = sorted(
                name for name in callables.keys() if name not in used_callable_names
            )
            for callable_name in ignored_callable_names:
                node = function_nodes.get(callable_name)
                warnings.warn(
                    format_dsl_diagnostic(
                        f"Callable '{callable_name}' is ignored because it is never called by any compiled action/predicate/callable.",
                        node=node,
                    ),
                    stacklevel=2,
                )
            callables = {
                name: callable_ir
                for name, callable_ir in callables.items()
                if name in used_callable_names
            }

            actor_schemas = {
                actor_type: {
                    field_name: _field_type_label(field_type)
                    for field_name, field_type in fields.items()
                }
                for actor_type, fields in compiler.schemas.actor_fields.items()
            }
            role_schemas = {
                role_type: {
                    field_name: _field_type_label(field_type)
                    for field_name, field_type in fields.items()
                }
                for role_type, fields in compiler.schemas.role_fields.items()
            }
            contains_next_turn_call = any(
                _action_contains_next_turn(action) for action in actions.values()
            )
            self._validate_condition_role_ids(rules, roles)
            self._validate_role_bindings(actions, predicates, roles)
            if (
                multiplayer is not None
                and multiplayer.default_loop
                in {
                    MultiplayerLoopMode.TURN_BASED,
                    MultiplayerLoopMode.HYBRID,
                }
                and not contains_next_turn_call
            ):
                raise DSLValidationError(
                    "Multiplayer default_loop is turn_based/hybrid but no action calls scene.next_turn()."
                )

            return ProjectSpec(
                actor_schemas=actor_schemas,
                role_schemas=role_schemas,
                globals=globals_spec,
                actors=actors,
                rules=rules,
                tile_map=tile_map,
                camera=camera,
                actions=list(actions.values()),
                predicates=list(predicates.values()),
                callables=list(callables.values()),
                resources=resources,
                sprites=sprites,
                scene=scene,
                interface_html=interface_html,
                multiplayer=multiplayer,
                roles=roles,
                contains_next_turn_call=contains_next_turn_call,
            )

    def _discover_game_variable(self, module: ast.Module) -> str:
        name_aliases: Dict[str, str] = {}
        callable_aliases: Dict[str, ast.AST] = {}
        for node in module.body:
            with dsl_node_context(node):
                if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                    continue
                target = node.targets[0]
                if not isinstance(target, ast.Name):
                    continue
                if isinstance(node.value, ast.Call):
                    resolved_ctor = _resolve_call_aliases(
                        node.value, name_aliases, callable_aliases
                    )
                    if (
                        isinstance(resolved_ctor.func, ast.Name)
                        and resolved_ctor.func.id == "Game"
                    ):
                        return target.id
                _track_top_level_assignment_alias(
                    target=target.id,
                    value=node.value,
                    name_aliases=name_aliases,
                    callable_aliases=callable_aliases,
                )
        raise DSLValidationError(
            "Project must declare a game object with 'game = Game()'."
        )

    def _register_actor_schemas(self, module: ast.Module, compiler: DSLCompiler) -> None:
        for node in module.body:
            with dsl_node_context(node):
                if isinstance(node, ast.ClassDef):
                    compiler._register_actor_schema(node)

    def _collect_globals(
        self,
        module: ast.Module,
        game_var: str,
        compiler: DSLCompiler,
    ) -> List[GlobalVariableSpec]:
        globals_spec: Dict[str, GlobalVariableSpec] = {}
        declared_global_vars: Dict[str, ast.Call] = {}
        name_aliases: Dict[str, str] = {}
        callable_aliases: Dict[str, ast.AST] = {}

        for node in module.body:
            with dsl_node_context(node):
                if isinstance(node, ast.Assign) and len(node.targets) == 1:
                    target = node.targets[0]
                    if isinstance(target, ast.Name):
                        resolved_call = (
                            _resolve_call_aliases(
                                node.value, name_aliases, callable_aliases
                            )
                            if isinstance(node.value, ast.Call)
                            else None
                        )
                        if (
                            resolved_call is not None
                            and isinstance(resolved_call.func, ast.Name)
                            and resolved_call.func.id == "GlobalVariable"
                        ):
                            declared_global_vars[target.id] = resolved_call
                        elif isinstance(node.value, ast.Name):
                            source_name = _resolve_name_alias(node.value.id, name_aliases)
                            template = declared_global_vars.get(source_name)
                            if template is not None:
                                declared_global_vars[target.id] = copy.deepcopy(template)
                            else:
                                declared_global_vars.pop(target.id, None)
                        else:
                            declared_global_vars.pop(target.id, None)
                        _track_top_level_assignment_alias(
                            target=target.id,
                            value=node.value,
                            name_aliases=name_aliases,
                            callable_aliases=callable_aliases,
                        )
                    continue

                if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
                    continue

                resolved_call = _resolve_call_aliases(
                    node.value, name_aliases, callable_aliases
                )
                method = _as_game_method_call(resolved_call, game_var)
                if method is None:
                    continue
                method_name, args, kwargs = method
                if method_name != "add_global":
                    continue
                if kwargs:
                    raise DSLValidationError("add_global(...) does not accept keyword args.")

                if len(args) == 1:
                    global_decl = self._resolve_global_variable_arg(
                        args[0],
                        declared_global_vars,
                    )
                    global_spec = self._parse_global_variable_decl(global_decl)
                    globals_spec[global_spec.name] = global_spec
                    continue

                if len(args) == 2:
                    global_name = _expect_string(args[0], "global variable name")
                    value = self._parse_global_value(args[1], compiler)
                    globals_spec[global_name] = GlobalVariableSpec(
                        name=global_name,
                        kind=value[0],
                        value=value[1],
                        list_elem_kind=value[2],
                    )
                    continue

                raise DSLValidationError(
                    "add_global(...) expects either (name, value) or (GlobalVariable(...))."
                )

        return list(globals_spec.values())

    def _resolve_global_variable_arg(
        self,
        node: ast.AST,
        declared_global_vars: Dict[str, ast.Call],
    ) -> ast.Call:
        if isinstance(node, ast.Name):
            resolved = declared_global_vars.get(node.id)
            if resolved is None:
                raise DSLValidationError(
                    f"Unknown GlobalVariable variable '{node.id}' in add_global(...)."
                )
            return resolved
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "GlobalVariable":
                return node
        raise DSLValidationError(
            "add_global(...) single-argument form expects GlobalVariable(...) or a variable bound to it."
        )

    def _parse_global_variable_decl(self, node: ast.Call) -> GlobalVariableSpec:
        if not isinstance(node.func, ast.Name) or node.func.id != "GlobalVariable":
            raise DSLValidationError("Expected GlobalVariable(...) declaration.")
        if node.keywords:
            raise DSLValidationError("GlobalVariable(...) does not accept keyword args.")
        if len(node.args) != 3:
            raise DSLValidationError(
                "GlobalVariable(...) expects (type, name, value)."
            )

        field_type = _parse_global_type_expr(node.args[0])
        global_name = _expect_string(node.args[1], "global variable name")
        value = _parse_typed_value(node.args[2], field_type)

        if isinstance(field_type, PrimType):
            if field_type.prim == Prim.INT:
                kind = GlobalValueKind.INT
            elif field_type.prim == Prim.FLOAT:
                kind = GlobalValueKind.FLOAT
            elif field_type.prim == Prim.STR:
                kind = GlobalValueKind.STR
            else:
                kind = GlobalValueKind.BOOL
            return GlobalVariableSpec(
                name=global_name,
                kind=kind,
                value=value,
                list_elem_kind=None,
            )

        if isinstance(field_type, ListType):
            return GlobalVariableSpec(
                name=global_name,
                kind=GlobalValueKind.LIST,
                value=value,
                list_elem_kind=_field_type_label(field_type),
            )

        if isinstance(field_type, DictType):
            return GlobalVariableSpec(
                name=global_name,
                kind=GlobalValueKind.DICT,
                value=value,
                list_elem_kind=_field_type_label(field_type),
            )

        raise DSLValidationError(
            "GlobalVariable(...) type must be primitive, List[...], or Dict[str, ...]."
        )

    def _compile_functions(
        self, module: ast.Module, compiler: DSLCompiler
    ) -> Tuple[Dict[str, ActionIR], Dict[str, PredicateIR], Dict[str, CallableIR]]:
        actions: Dict[str, ActionIR] = {}
        predicates: Dict[str, PredicateIR] = {}
        callables: Dict[str, CallableIR] = {}

        callable_signatures: Dict[str, int] = {}
        normalized_callables: Dict[str, ast.FunctionDef] = {}
        for node in module.body:
            with dsl_node_context(node):
                if not isinstance(node, ast.FunctionDef):
                    continue
                if self._has_plain_decorator(node, "callable"):
                    if self._has_condition_decorator(node):
                        raise DSLValidationError(
                            f"Function '{node.name}' cannot use both @callable and @condition decorators."
                        )
                    normalized = self._normalize_callable_function(node, compiler)
                    callable_signatures[node.name] = len(normalized.args.args)
                    normalized_callables[node.name] = normalized

        compiler.set_callable_signatures(callable_signatures)

        for node in module.body:
            with dsl_node_context(node):
                if not isinstance(node, ast.FunctionDef):
                    continue

                if node.name in normalized_callables:
                    callables[node.name] = compiler._compile_callable(
                        normalized_callables[node.name]
                    )
                    continue

                if _looks_like_predicate(node, compiler):
                    predicates[node.name] = compiler._compile_predicate(node)
                elif _looks_like_action(node, compiler):
                    normalized_fn = self._strip_condition_decorators(node)
                    actions[node.name] = compiler._compile_action(normalized_fn)
                else:
                    continue

        return actions, predicates, callables

    def _collect_game_setup(
        self,
        module: ast.Module,
        game_var: str,
        compiler: DSLCompiler,
        actions: Dict[str, ActionIR],
        predicates: Dict[str, PredicateIR],
        callables: Dict[str, CallableIR],
    ) -> Tuple[
        Dict[str, ConditionSpec],
        List[ActorInstanceSpec],
        List[RuleSpec],
        Optional[TileMapSpec],
        Optional[CameraSpec],
        List[ResourceSpec],
        List[SpriteSpec],
        Optional[SceneSpec],
        Optional[str],
        Optional[MultiplayerSpec],
        List[RoleSpec],
    ]:
        condition_vars: Dict[str, ConditionSpec] = {}
        actors: List[ActorInstanceSpec] = []
        rules: List[RuleSpec] = []
        tile_map: Optional[TileMapSpec] = None
        camera: Optional[CameraSpec] = None
        resources_by_name: Dict[str, ResourceSpec] = {}
        sprites: List[SpriteSpec] = []
        scene: Optional[SceneSpec] = None
        interface_html: Optional[str] = None
        multiplayer: Optional[MultiplayerSpec] = None
        roles_by_id: Dict[str, RoleSpec] = {}
        declared_scene_vars: Dict[str, SceneSpec] = {}
        declared_multiplayer_vars: Dict[str, ast.Call] = {}
        declared_role_vars: Dict[str, ast.Call] = {}
        declared_interface_vars: Dict[str, str] = {}
        active_scene_vars: set[str] = set()
        declared_actor_vars: Dict[str, ast.Call] = {}
        declared_tile_map_vars: Dict[str, ast.Call] = {}
        declared_camera_vars: Dict[str, ast.Call] = {}
        declared_sprite_vars: Dict[str, ast.Call] = {}
        declared_color_vars: Dict[str, ast.Call] = {}
        declared_tile_vars: Dict[str, ast.Call] = {}
        collision_bound_actions: set[str] = set()
        non_collision_actions: set[str] = set()
        collision_warning_actions: set[str] = set()
        logical_warning_predicates: set[str] = set()
        tool_action_by_name: Dict[str, str] = {}
        name_aliases: Dict[str, str] = {}
        callable_aliases: Dict[str, ast.AST] = {}

        def clear_declared_value(name: str) -> None:
            declared_actor_vars.pop(name, None)
            declared_tile_map_vars.pop(name, None)
            declared_camera_vars.pop(name, None)
            declared_sprite_vars.pop(name, None)
            declared_color_vars.pop(name, None)
            declared_tile_vars.pop(name, None)
            declared_scene_vars.pop(name, None)
            declared_multiplayer_vars.pop(name, None)
            declared_role_vars.pop(name, None)
            active_scene_vars.discard(name)

        def register_rule(
            condition: ConditionSpec,
            action_name: str,
            source_node: Optional[ast.AST] = None,
        ) -> None:
            if action_name not in actions:
                raise DSLValidationError(
                    f"Unknown action '{action_name}' in add_rule(...)."
                )

            if isinstance(condition, CollisionConditionSpec):
                if action_name in non_collision_actions:
                    raise DSLValidationError(
                        f"Action '{action_name}' cannot be used by both collision and non-collision rules."
                    )
                actions[action_name] = self._bind_collision_action_params(
                    action_name=action_name,
                    action=actions[action_name],
                    condition=condition,
                    warned_actions=collision_warning_actions,
                    source_node=source_node,
                )
                collision_bound_actions.add(action_name)
            else:
                if action_name in collision_bound_actions:
                    raise DSLValidationError(
                        f"Action '{action_name}' cannot be used by both collision and non-collision rules."
                    )
                non_collision_actions.add(action_name)

            if isinstance(condition, LogicalConditionSpec):
                predicate_name = condition.predicate_name
                if predicate_name not in predicates:
                    raise DSLValidationError(
                        f"Unknown predicate '{predicate_name}' in OnLogicalCondition(...)."
                    )
                predicates[predicate_name] = self._bind_logical_predicate_params(
                    predicate_name=predicate_name,
                    predicate=predicates[predicate_name],
                    condition=condition,
                    warned_predicates=logical_warning_predicates,
                    source_node=source_node,
                )

            rules.append(RuleSpec(condition=condition, action_name=action_name))
            if isinstance(condition, ToolConditionSpec):
                existing = tool_action_by_name.get(condition.name)
                if existing is not None and existing != action_name:
                    raise DSLValidationError(
                        f"OnToolCall('{condition.name}', ...) is already bound to "
                        f"action '{existing}' and cannot be rebound to '{action_name}'."
                    )
                tool_action_by_name[condition.name] = action_name

        # Pass 1: collect named conditions and declared scenes.
        for node in module.body:
            with dsl_node_context(node):
                if isinstance(node, ast.Assign) and len(node.targets) == 1:
                    target = node.targets[0]
                    if isinstance(target, ast.Name):
                        resolved_call: Optional[ast.Call] = None
                        if isinstance(node.value, ast.Call):
                            resolved_call = _resolve_call_aliases(
                                node.value, name_aliases, callable_aliases
                            )
                            if (
                                isinstance(resolved_call.func, ast.Name)
                                and resolved_call.func.id == "Scene"
                            ):
                                declared_scene_vars[target.id] = self._parse_scene(
                                    resolved_call
                                )
                            if (
                                isinstance(resolved_call.func, ast.Name)
                                and resolved_call.func.id == "Multiplayer"
                            ):
                                declared_multiplayer_vars[target.id] = resolved_call
                            if (
                                isinstance(resolved_call.func, ast.Name)
                                and (
                                    resolved_call.func.id == "Role"
                                    or resolved_call.func.id in compiler.schemas.role_fields
                                )
                            ):
                                declared_role_vars[target.id] = resolved_call
                            if self._is_condition_expr(resolved_call):
                                condition_vars[target.id] = self._parse_condition(
                                    resolved_call, compiler, predicates
                                )
                        _track_top_level_assignment_alias(
                            target=target.id,
                            value=node.value,
                            name_aliases=name_aliases,
                            callable_aliases=callable_aliases,
                        )

        # Pass 2: parse setup statements/rules/actors/resources.
        name_aliases = {}
        callable_aliases = {}

        for node in module.body:
            with dsl_node_context(node):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    continue

                if not isinstance(node, (ast.FunctionDef, ast.Assign, ast.Expr, ast.ClassDef)):
                    warnings.warn(
                        format_dsl_diagnostic(
                            f"Top-level {type(node).__name__} is ignored during setup compilation.",
                            node=node,
                        ),
                        stacklevel=2,
                    )
                    continue

                if isinstance(node, ast.FunctionDef):
                    if node.name in actions:
                        for decorated_condition in self._parse_decorator_conditions(
                            node=node,
                            condition_vars=condition_vars,
                            compiler=compiler,
                            predicates=predicates,
                            name_aliases=name_aliases,
                            callable_aliases=callable_aliases,
                        ):
                            register_rule(decorated_condition, node.name, node)
                    elif node.name in callables:
                        pass
                    elif node.decorator_list:
                        raise DSLValidationError(
                            f"Unsupported decorators on function '{node.name}'. Use @condition(...) for actions or @callable for helper functions."
                        )
                    elif node.name not in predicates:
                        warnings.warn(
                            format_dsl_diagnostic(
                                f"Function '{node.name}' is ignored because it has no DSL decorator and is not referenced by rules.",
                                node=node,
                            ),
                            stacklevel=2,
                        )
                    continue

                if isinstance(node, ast.Assign) and len(node.targets) == 1:
                    target = node.targets[0]
                    if isinstance(target, ast.Name):
                        resolved_call = (
                            _resolve_call_aliases(node.value, name_aliases, callable_aliases)
                            if isinstance(node.value, ast.Call)
                            else None
                        )
                        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                            declared_interface_vars[target.id] = node.value.value
                        elif isinstance(node.value, ast.Name):
                            source_name = _resolve_name_alias(node.value.id, name_aliases)
                            if source_name in declared_interface_vars:
                                declared_interface_vars[target.id] = declared_interface_vars[source_name]
                            else:
                                declared_interface_vars.pop(target.id, None)
                        else:
                            declared_interface_vars.pop(target.id, None)
                        if resolved_call is not None:
                            if (
                                isinstance(resolved_call.func, ast.Name)
                                and resolved_call.func.id in compiler.schemas.actor_fields
                            ):
                                declared_actor_vars[target.id] = resolved_call
                                declared_tile_map_vars.pop(target.id, None)
                                declared_camera_vars.pop(target.id, None)
                                declared_sprite_vars.pop(target.id, None)
                                declared_color_vars.pop(target.id, None)
                                declared_tile_vars.pop(target.id, None)
                                declared_scene_vars.pop(target.id, None)
                                active_scene_vars.discard(target.id)
                            elif (
                                isinstance(resolved_call.func, ast.Name)
                                and resolved_call.func.id == "TileMap"
                            ):
                                declared_tile_map_vars[target.id] = resolved_call
                                declared_actor_vars.pop(target.id, None)
                                declared_camera_vars.pop(target.id, None)
                                declared_sprite_vars.pop(target.id, None)
                                declared_color_vars.pop(target.id, None)
                                declared_tile_vars.pop(target.id, None)
                                declared_scene_vars.pop(target.id, None)
                                active_scene_vars.discard(target.id)
                            elif (
                                isinstance(resolved_call.func, ast.Name)
                                and resolved_call.func.id == "Sprite"
                            ):
                                declared_sprite_vars[target.id] = resolved_call
                                declared_actor_vars.pop(target.id, None)
                                declared_tile_map_vars.pop(target.id, None)
                                declared_camera_vars.pop(target.id, None)
                                declared_color_vars.pop(target.id, None)
                                declared_tile_vars.pop(target.id, None)
                                declared_scene_vars.pop(target.id, None)
                                active_scene_vars.discard(target.id)
                            elif (
                                isinstance(resolved_call.func, ast.Name)
                                and resolved_call.func.id == "Color"
                            ):
                                declared_color_vars[target.id] = resolved_call
                                declared_actor_vars.pop(target.id, None)
                                declared_tile_map_vars.pop(target.id, None)
                                declared_camera_vars.pop(target.id, None)
                                declared_sprite_vars.pop(target.id, None)
                                declared_tile_vars.pop(target.id, None)
                                declared_scene_vars.pop(target.id, None)
                                active_scene_vars.discard(target.id)
                            elif (
                                isinstance(resolved_call.func, ast.Name)
                                and resolved_call.func.id == "Tile"
                            ):
                                declared_tile_vars[target.id] = resolved_call
                                declared_actor_vars.pop(target.id, None)
                                declared_tile_map_vars.pop(target.id, None)
                                declared_camera_vars.pop(target.id, None)
                                declared_sprite_vars.pop(target.id, None)
                                declared_color_vars.pop(target.id, None)
                                declared_scene_vars.pop(target.id, None)
                                active_scene_vars.discard(target.id)
                            elif (
                                isinstance(resolved_call.func, ast.Attribute)
                                and isinstance(resolved_call.func.value, ast.Name)
                                and resolved_call.func.value.id == "Camera"
                            ):
                                declared_camera_vars[target.id] = resolved_call
                                declared_actor_vars.pop(target.id, None)
                                declared_tile_map_vars.pop(target.id, None)
                                declared_sprite_vars.pop(target.id, None)
                                declared_color_vars.pop(target.id, None)
                                declared_tile_vars.pop(target.id, None)
                                declared_scene_vars.pop(target.id, None)
                                active_scene_vars.discard(target.id)
                            elif (
                                isinstance(resolved_call.func, ast.Name)
                                and resolved_call.func.id == "Scene"
                            ):
                                declared_scene_vars[target.id] = self._parse_scene(resolved_call)
                                declared_actor_vars.pop(target.id, None)
                                declared_tile_map_vars.pop(target.id, None)
                                declared_camera_vars.pop(target.id, None)
                                declared_sprite_vars.pop(target.id, None)
                                declared_color_vars.pop(target.id, None)
                                declared_tile_vars.pop(target.id, None)
                                active_scene_vars.discard(target.id)
                            elif (
                                isinstance(resolved_call.func, ast.Name)
                                and resolved_call.func.id == "Multiplayer"
                            ):
                                declared_multiplayer_vars[target.id] = resolved_call
                                declared_actor_vars.pop(target.id, None)
                                declared_tile_map_vars.pop(target.id, None)
                                declared_camera_vars.pop(target.id, None)
                                declared_sprite_vars.pop(target.id, None)
                                declared_color_vars.pop(target.id, None)
                                declared_tile_vars.pop(target.id, None)
                                declared_scene_vars.pop(target.id, None)
                                active_scene_vars.discard(target.id)
                            elif (
                                isinstance(resolved_call.func, ast.Name)
                                and (
                                    resolved_call.func.id == "Role"
                                    or resolved_call.func.id in compiler.schemas.role_fields
                                )
                            ):
                                declared_role_vars[target.id] = resolved_call
                                declared_actor_vars.pop(target.id, None)
                                declared_tile_map_vars.pop(target.id, None)
                                declared_camera_vars.pop(target.id, None)
                                declared_sprite_vars.pop(target.id, None)
                                declared_color_vars.pop(target.id, None)
                                declared_tile_vars.pop(target.id, None)
                                declared_scene_vars.pop(target.id, None)
                                declared_multiplayer_vars.pop(target.id, None)
                                active_scene_vars.discard(target.id)
                            else:
                                clear_declared_value(target.id)
                        else:
                            clear_declared_value(target.id)

                        _track_top_level_assignment_alias(
                            target=target.id,
                            value=node.value,
                            name_aliases=name_aliases,
                            callable_aliases=callable_aliases,
                        )
                    continue

                if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
                    continue

                resolved_call = _resolve_call_aliases(
                    node.value, name_aliases, callable_aliases
                )
                method = _as_game_method_call(resolved_call, game_var)
                if method is not None:
                    method_name, args, kwargs = method

                    if method_name == "add_actor":
                        actors.append(
                            self._parse_actor_instance(
                                args,
                                kwargs,
                                compiler,
                                actors,
                                declared_actor_vars,
                            )
                        )
                        continue

                    if method_name == "add_resource":
                        resource = self._parse_resource(args, kwargs)
                        resources_by_name[resource.name] = resource
                        continue

                    if method_name == "add_sprite":
                        sprites.append(
                            self._parse_sprite(
                                args,
                                kwargs,
                                compiler,
                                declared_sprite_vars=declared_sprite_vars,
                            )
                        )
                        continue

                    if method_name == "add_rule":
                        if kwargs:
                            raise DSLValidationError(
                                "add_rule(...) does not accept keyword args."
                            )
                        if len(args) != 2:
                            raise DSLValidationError(
                                "add_rule(...) expects exactly 2 positional arguments."
                            )
                        condition = self._resolve_condition_arg(
                            args[0], condition_vars, compiler, predicates
                        )
                        action_name = _expect_name(args[1], "action function")
                        register_rule(condition, action_name, node)
                        continue

                    if method_name == "set_map":
                        if kwargs:
                            raise DSLValidationError(
                                "set_map(...) does not accept keyword args."
                            )
                        if len(args) != 1:
                            raise DSLValidationError("set_map(...) expects one argument.")
                        tile_map = self._parse_tile_map(
                            self._resolve_tile_map_arg(args[0], declared_tile_map_vars),
                            declared_color_vars=declared_color_vars,
                            declared_tile_vars=declared_tile_vars,
                        )
                        continue

                    if method_name == "set_camera":
                        if kwargs:
                            raise DSLValidationError(
                                "set_camera(...) does not accept keyword args."
                            )
                        if len(args) != 1:
                            raise DSLValidationError("set_camera(...) expects one argument.")
                        camera = self._parse_camera(
                            self._resolve_camera_arg(args[0], declared_camera_vars)
                        )
                        continue

                    if method_name == "set_scene":
                        if kwargs:
                            raise DSLValidationError(
                                "set_scene(...) does not accept keyword args."
                            )
                        if len(args) != 1:
                            raise DSLValidationError("set_scene(...) expects one argument.")
                        scene, scene_var = self._resolve_scene_binding_arg(
                            args[0], declared_scene_vars
                        )
                        if scene_var is not None:
                            active_scene_vars.add(scene_var)
                        continue

                    if method_name == "set_multiplayer":
                        if kwargs:
                            raise DSLValidationError(
                                "set_multiplayer(...) does not accept keyword args."
                            )
                        if len(args) != 1:
                            raise DSLValidationError("set_multiplayer(...) expects one argument.")
                        multiplayer = self._parse_multiplayer(
                            self._resolve_multiplayer_arg(
                                args[0],
                                declared_multiplayer_vars,
                            )
                        )
                        continue

                    if method_name == "add_role":
                        if kwargs:
                            raise DSLValidationError("add_role(...) does not accept keyword args.")
                        if len(args) != 1:
                            raise DSLValidationError("add_role(...) expects one argument.")
                        role = self._parse_role(
                            self._resolve_role_arg(args[0], declared_role_vars),
                            compiler,
                        )
                        existing = roles_by_id.get(role.id)
                        if existing is not None and existing != role:
                            raise DSLValidationError(
                                f"Role '{role.id}' is already declared with different settings."
                            )
                        roles_by_id[role.id] = role
                        continue

                    if method_name == "add_global":
                        continue

                    if method_name == "set_interface":
                        raise DSLValidationError(
                            "game.set_interface(...) is no longer supported; use scene.set_interface(...)."
                        )

                    raise DSLValidationError(f"Unsupported game method '{method_name}'.")

                if not (
                    isinstance(resolved_call.func, ast.Attribute)
                    and isinstance(resolved_call.func.value, ast.Name)
                ):
                    continue
                owner = resolved_call.func.value.id

                actor_method = _as_owner_method_call(resolved_call, owner)
                if actor_method is not None and owner in declared_actor_vars:
                    actor_method_name, actor_args, actor_kwargs = actor_method
                    self._apply_declared_actor_method_call(
                        owner=owner,
                        method_name=actor_method_name,
                        args=actor_args,
                        kwargs=actor_kwargs,
                        compiler=compiler,
                        declared_actor_vars=declared_actor_vars,
                    )
                    continue

                scene_method = _as_owner_method_call(resolved_call, owner)
                if scene_method is None:
                    continue
                scene_method_name, scene_args, scene_kwargs = scene_method
                if owner in declared_scene_vars and owner not in active_scene_vars:
                    raise DSLValidationError(
                        f"Scene variable '{owner}' must be passed to game.set_scene(...) before using '{owner}.{scene_method_name}(...)'."
                    )
                if owner not in active_scene_vars:
                    continue

                if scene_method_name == "add_actor":
                    actors.append(
                        self._parse_actor_instance(
                            scene_args,
                            scene_kwargs,
                            compiler,
                            actors,
                            declared_actor_vars,
                        )
                    )
                    continue

                if scene_method_name == "add_rule":
                    if scene_kwargs:
                        raise DSLValidationError("scene.add_rule(...) does not accept keyword args.")
                    if len(scene_args) != 2:
                        raise DSLValidationError(
                            "scene.add_rule(...) expects exactly 2 positional arguments."
                        )
                    condition = self._resolve_condition_arg(
                        scene_args[0], condition_vars, compiler, predicates
                    )
                    action_name = _expect_name(scene_args[1], "action function")
                    register_rule(condition, action_name, node)
                    continue

                if scene_method_name == "set_map":
                    if scene_kwargs:
                        raise DSLValidationError("scene.set_map(...) does not accept keyword args.")
                    if len(scene_args) != 1:
                        raise DSLValidationError("scene.set_map(...) expects one argument.")
                    tile_map = self._parse_tile_map(
                        self._resolve_tile_map_arg(scene_args[0], declared_tile_map_vars),
                        declared_color_vars=declared_color_vars,
                        declared_tile_vars=declared_tile_vars,
                    )
                    continue

                if scene_method_name == "set_camera":
                    if scene_kwargs:
                        raise DSLValidationError(
                            "scene.set_camera(...) does not accept keyword args."
                        )
                    if len(scene_args) != 1:
                        raise DSLValidationError("scene.set_camera(...) expects one argument.")
                    camera = self._parse_camera(
                        self._resolve_camera_arg(scene_args[0], declared_camera_vars)
                    )
                    continue

                if scene_method_name == "set_interface":
                    if scene_kwargs:
                        raise DSLValidationError(
                            "scene.set_interface(...) does not accept keyword args."
                        )
                    if len(scene_args) != 1:
                        raise DSLValidationError(
                            "scene.set_interface(...) expects one argument."
                        )
                    interface_html = self._resolve_interface_html_arg(
                        scene_args[0], declared_interface_vars
                    )
                    continue

                raise DSLValidationError(
                    f"Unsupported scene method '{scene_method_name}'."
                )

        self._validate_sprite_targets(actors, sprites, compiler)
        self._validate_sprite_resources(resources_by_name, sprites)
        return (
            condition_vars,
            actors,
            rules,
            tile_map,
            camera,
            list(resources_by_name.values()),
            sprites,
            scene,
            interface_html,
            multiplayer,
            list(roles_by_id.values()),
        )

    def _apply_declared_actor_method_call(
        self,
        owner: str,
        method_name: str,
        args: List[ast.AST],
        kwargs: Dict[str, ast.AST],
        compiler: DSLCompiler,
        declared_actor_vars: Dict[str, ast.Call],
    ) -> None:
        if method_name == "attached_to":
            if kwargs:
                raise DSLValidationError(
                    f"{owner}.attached_to(...) does not accept keyword args."
                )
            if len(args) != 1:
                raise DSLValidationError(
                    f"{owner}.attached_to(...) expects exactly one argument."
                )
            parent_uid = self._resolve_declared_actor_parent_uid(
                args[0], compiler, declared_actor_vars
            )
            self._set_declared_actor_parent(owner, parent_uid, declared_actor_vars)
            return

        if method_name == "detached":
            if kwargs or args:
                raise DSLValidationError(
                    f"{owner}.detached(...) does not accept arguments."
                )
            self._clear_declared_actor_parent(owner, declared_actor_vars)
            return

        raise DSLValidationError(
            f"Unsupported actor method '{method_name}'. Only attached_to/detached are allowed in setup."
        )

    def _resolve_declared_actor_parent_uid(
        self,
        node: ast.AST,
        compiler: DSLCompiler,
        declared_actor_vars: Dict[str, ast.Call],
    ) -> str:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value

        if isinstance(node, ast.Name):
            ctor = declared_actor_vars.get(node.id)
            if ctor is None:
                raise DSLValidationError(
                    f"attached_to(...) unknown actor variable '{node.id}'."
                )
            uid = _extract_declared_actor_ctor_uid(ctor)
            if uid is None:
                raise DSLValidationError(
                    "attached_to(...) target actor must have an explicit uid in its constructor."
                )
            return uid

        if isinstance(node, (ast.Subscript, ast.Call)):
            selector = self._parse_selector(node, compiler)
            if selector.kind == SelectorKind.WITH_UID and selector.uid is not None:
                return selector.uid

        raise DSLValidationError(
            "attached_to(...) expects actor uid string, actor variable, or ActorType[\"uid\"] selector."
        )

    def _set_declared_actor_parent(
        self,
        owner: str,
        parent_uid: str,
        declared_actor_vars: Dict[str, ast.Call],
    ) -> None:
        ctor = declared_actor_vars.get(owner)
        if ctor is None:
            raise DSLValidationError(
                f"Unknown actor variable '{owner}' for attached_to(...)."
            )

        updated_keywords = [
            kw for kw in ctor.keywords if kw.arg is not None and kw.arg != "parent"
        ]
        updated_keywords.append(ast.keyword(arg="parent", value=ast.Constant(parent_uid)))
        declared_actor_vars[owner] = ast.copy_location(
            ast.Call(func=ctor.func, args=list(ctor.args), keywords=updated_keywords),
            ctor,
        )

    def _clear_declared_actor_parent(
        self,
        owner: str,
        declared_actor_vars: Dict[str, ast.Call],
    ) -> None:
        ctor = declared_actor_vars.get(owner)
        if ctor is None:
            raise DSLValidationError(
                f"Unknown actor variable '{owner}' for detached(...)."
            )

        updated_keywords = [
            kw for kw in ctor.keywords if kw.arg is not None and kw.arg != "parent"
        ]
        declared_actor_vars[owner] = ast.copy_location(
            ast.Call(func=ctor.func, args=list(ctor.args), keywords=updated_keywords),
            ctor,
        )

    def _resolve_scene_binding_arg(
        self,
        node: ast.AST,
        declared_scene_vars: Dict[str, SceneSpec],
    ) -> Tuple[SceneSpec, Optional[str]]:
        if isinstance(node, ast.Name):
            if node.id not in declared_scene_vars:
                raise DSLValidationError(
                    f"Unknown scene variable '{node.id}' passed to game.set_scene(...)."
                )
            return declared_scene_vars[node.id], node.id
        if isinstance(node, ast.Call):
            return self._parse_scene(node), None
        raise DSLValidationError("set_scene(...) expects Scene(...) or a scene variable.")

    def _resolve_tile_map_arg(
        self, node: ast.AST, declared_tile_map_vars: Dict[str, ast.Call]
    ) -> ast.AST:
        if isinstance(node, ast.Name):
            if node.id not in declared_tile_map_vars:
                raise DSLValidationError(
                    f"Unknown TileMap variable '{node.id}' in set_map(...)."
                )
            return declared_tile_map_vars[node.id]
        return node

    def _resolve_camera_arg(
        self, node: ast.AST, declared_camera_vars: Dict[str, ast.Call]
    ) -> ast.AST:
        if isinstance(node, ast.Name):
            if node.id not in declared_camera_vars:
                raise DSLValidationError(
                    f"Unknown camera variable '{node.id}' in set_camera(...)."
                )
            return declared_camera_vars[node.id]
        return node

    def _resolve_interface_html_arg(
        self,
        node: ast.AST,
        declared_interface_vars: Dict[str, str],
    ) -> str:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in declared_interface_vars:
                raise DSLValidationError(
                    f"Unknown interface HTML variable '{node.id}' in set_interface(...)."
                )
            return declared_interface_vars[node.id]
        raise DSLValidationError(
            "set_interface(...) expects an HTML string or a variable bound to a string."
        )

    def _resolve_multiplayer_arg(
        self,
        node: ast.AST,
        declared_multiplayer_vars: Dict[str, ast.Call],
    ) -> ast.AST:
        if isinstance(node, ast.Name):
            if node.id not in declared_multiplayer_vars:
                raise DSLValidationError(
                    f"Unknown Multiplayer variable '{node.id}' in set_multiplayer(...)."
                )
            return declared_multiplayer_vars[node.id]
        return node

    def _parse_multiplayer(self, node: ast.AST) -> MultiplayerSpec:
        if not isinstance(node, ast.Call):
            raise DSLValidationError("set_multiplayer(...) expects Multiplayer(...).")
        if not isinstance(node.func, ast.Name) or node.func.id != "Multiplayer":
            raise DSLValidationError("set_multiplayer(...) expects Multiplayer(...).")
        if node.args:
            raise DSLValidationError("Multiplayer(...) only supports keyword arguments.")

        kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg is not None}
        allowed = {
            "default_loop",
            "allowed_loops",
            "default_visibility",
            "tick_rate",
            "turn_timeout_ms",
            "hybrid_window_ms",
            "game_time_scale",
            "max_catchup_steps",
        }
        unexpected = sorted(set(kwargs.keys()) - allowed)
        if unexpected:
            raise DSLValidationError(
                f"Multiplayer(...) received unsupported arguments: {unexpected}"
            )

        default_loop_label = _expect_string_or_default(
            kwargs.get("default_loop"),
            "multiplayer default_loop",
            MultiplayerLoopMode.REAL_TIME.value,
        )
        if default_loop_label is None:
            default_loop_label = MultiplayerLoopMode.REAL_TIME.value
        default_loop = _parse_multiplayer_loop_mode(default_loop_label)

        allowed_loops_node = kwargs.get("allowed_loops")
        if allowed_loops_node is None:
            allowed_loops = [default_loop]
        else:
            labels = _expect_string_list(allowed_loops_node, "multiplayer allowed_loops")
            if not labels:
                raise DSLValidationError("Multiplayer allowed_loops cannot be empty.")
            allowed_loops = []
            for label in labels:
                mode = _parse_multiplayer_loop_mode(label)
                if mode not in allowed_loops:
                    allowed_loops.append(mode)

        if default_loop not in allowed_loops:
            raise DSLValidationError(
                "Multiplayer default_loop must be included in allowed_loops."
            )

        default_visibility_label = _expect_string_or_default(
            kwargs.get("default_visibility"),
            "multiplayer default_visibility",
            VisibilityMode.SHARED.value,
        )
        if default_visibility_label is None:
            default_visibility_label = VisibilityMode.SHARED.value
        default_visibility = _parse_visibility_mode(default_visibility_label)

        tick_rate = _expect_int_or_default(kwargs.get("tick_rate"), "multiplayer tick_rate", 20)
        if tick_rate <= 0:
            raise DSLValidationError("Multiplayer tick_rate must be > 0.")

        turn_timeout_ms = _expect_int_or_default(
            kwargs.get("turn_timeout_ms"),
            "multiplayer turn_timeout_ms",
            15_000,
        )
        if turn_timeout_ms <= 0:
            raise DSLValidationError("Multiplayer turn_timeout_ms must be > 0.")

        hybrid_window_ms = _expect_int_or_default(
            kwargs.get("hybrid_window_ms"),
            "multiplayer hybrid_window_ms",
            500,
        )
        if hybrid_window_ms <= 0:
            raise DSLValidationError("Multiplayer hybrid_window_ms must be > 0.")

        game_time_scale = _expect_float_or_default(
            kwargs.get("game_time_scale"),
            "multiplayer game_time_scale",
            1.0,
        )
        if game_time_scale <= 0 or game_time_scale > 1.0:
            raise DSLValidationError(
                "Multiplayer game_time_scale must be > 0 and <= 1.0."
            )

        max_catchup_steps = _expect_int_or_default(
            kwargs.get("max_catchup_steps"),
            "multiplayer max_catchup_steps",
            1,
        )
        if max_catchup_steps <= 0:
            raise DSLValidationError("Multiplayer max_catchup_steps must be > 0.")

        return MultiplayerSpec(
            default_loop=default_loop,
            allowed_loops=allowed_loops,
            default_visibility=default_visibility,
            tick_rate=tick_rate,
            turn_timeout_ms=turn_timeout_ms,
            hybrid_window_ms=hybrid_window_ms,
            game_time_scale=game_time_scale,
            max_catchup_steps=max_catchup_steps,
        )

    def _resolve_role_arg(
        self,
        node: ast.AST,
        declared_role_vars: Dict[str, ast.Call],
    ) -> ast.AST:
        if isinstance(node, ast.Name):
            if node.id not in declared_role_vars:
                raise DSLValidationError(
                    f"Unknown Role variable '{node.id}' in add_role(...)."
                )
            return declared_role_vars[node.id]
        return node

    def _parse_role(self, node: ast.AST, compiler: DSLCompiler) -> RoleSpec:
        if not isinstance(node, ast.Call):
            raise DSLValidationError("add_role(...) expects Role(...).")
        if not isinstance(node.func, ast.Name):
            raise DSLValidationError("add_role(...) expects Role(...).")
        role_type = node.func.id
        if role_type != "Role" and role_type not in compiler.schemas.role_fields:
            raise DSLValidationError(
                "add_role(...) expects Role(...) or RoleSchema(...)."
            )
        if node.args:
            raise DSLValidationError("Role(...) only supports keyword arguments.")

        kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg is not None}
        role_schema_fields = compiler.schemas.role_fields.get(role_type, {})
        allowed = {"id", "required", "kind", *role_schema_fields.keys()}
        unexpected = sorted(set(kwargs.keys()) - allowed)
        if unexpected:
            raise DSLValidationError(
                f"{role_type}(...) received unsupported arguments: {unexpected}"
            )
        if "id" not in kwargs:
            raise DSLValidationError(f"{role_type}(...) missing required argument: ['id']")

        role_id = _expect_string(kwargs["id"], "role id")
        if not role_id:
            raise DSLValidationError("Role id must be a non-empty string.")

        required = _expect_bool_or_default(kwargs.get("required"), "role required", True)
        kind = _parse_role_kind(kwargs.get("kind"))
        fields: Dict[str, object] = {}
        for field_name, field_type in role_schema_fields.items():
            if field_name in kwargs:
                fields[field_name] = _parse_typed_value(kwargs[field_name], field_type)
            else:
                fields[field_name] = _default_value_for_type(field_type)
        return RoleSpec(
            id=role_id,
            required=required,
            kind=kind,
            role_type=role_type,
            fields=cast(Dict[str, object], fields),
        )

    def _validate_condition_role_ids(
        self,
        rules: List[RuleSpec],
        roles: List[RoleSpec],
    ) -> None:
        declared = {role.id for role in roles}
        for rule in rules:
            condition = rule.condition
            role_id: Optional[str] = None
            if isinstance(condition, KeyboardConditionSpec):
                role_id = condition.role_id
            elif isinstance(condition, MouseConditionSpec):
                role_id = condition.role_id
            elif isinstance(condition, ToolConditionSpec):
                role_id = condition.role_id

            if role_id is None:
                continue
            if role_id in declared:
                continue
            if not declared:
                raise DSLValidationError(
                    f"Condition for action '{rule.action_name}' references role id '{role_id}', "
                    "but no roles were declared via game.add_role(...)."
                )
            declared_list = ", ".join(sorted(declared))
            raise DSLValidationError(
                f"Condition for action '{rule.action_name}' references unknown role id '{role_id}'. "
                f"Declared roles: {declared_list}."
            )

    def _validate_role_bindings(
        self,
        actions: Dict[str, ActionIR],
        predicates: Dict[str, PredicateIR],
        roles: List[RoleSpec],
    ) -> None:
        declared = {role.id: role for role in roles}
        declared_ids = sorted(declared.keys())

        def validate_param(owner: str, param: ParamBinding) -> None:
            if param.kind != BindingKind.ROLE:
                return
            selector = param.role_selector
            role_id = selector.id if selector is not None else ""
            if not role_id:
                raise DSLValidationError(
                    f"{owner} role binding '{param.name}' is missing a role id."
                )
            target = declared.get(role_id)
            if target is None:
                if not declared:
                    raise DSLValidationError(
                        f"{owner} role binding '{param.name}' references role id '{role_id}', "
                        "but no roles were declared via game.add_role(...)."
                    )
                raise DSLValidationError(
                    f"{owner} role binding '{param.name}' references unknown role id '{role_id}'. "
                    f"Declared roles: {', '.join(declared_ids)}."
                )
            if param.role_type is not None and target.role_type != param.role_type:
                raise DSLValidationError(
                    f"{owner} role binding '{param.name}' expects role type "
                    f"'{param.role_type}' but role '{role_id}' has type '{target.role_type}'."
                )

        for action in actions.values():
            for param in action.params:
                validate_param(f"Action '{action.name}'", param)
        for predicate in predicates.values():
            for param in predicate.params:
                validate_param(f"Predicate '{predicate.name}'", param)

    def _parse_global_value(
        self, node: ast.AST, compiler: DSLCompiler
    ) -> Tuple[GlobalValueKind, object, Optional[str]]:
        static_value = None
        has_static_value = False
        try:
            static_value = _eval_static_expr(node)
            has_static_value = True
        except DSLValidationError:
            has_static_value = False

        if has_static_value:
            if isinstance(static_value, bool):
                return GlobalValueKind.BOOL, static_value, None
            if isinstance(static_value, int) and not isinstance(static_value, bool):
                return GlobalValueKind.INT, static_value, None
            if isinstance(static_value, float):
                return GlobalValueKind.FLOAT, static_value, None
            if isinstance(static_value, str):
                return GlobalValueKind.STR, static_value, None
            if isinstance(static_value, list):
                list_kind = _infer_primitive_list_kind(static_value)
                return GlobalValueKind.LIST, static_value, list_kind
            if isinstance(static_value, dict):
                dict_kind = _infer_primitive_dict_kind(static_value)
                return GlobalValueKind.DICT, static_value, dict_kind

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

        if isinstance(node, (ast.Call, ast.Subscript, ast.Name)):
            selector = self._parse_selector(node, compiler)
            if selector.kind != SelectorKind.WITH_UID or selector.uid is None:
                raise DSLValidationError(
                    'Global actor pointer must use ActorType["uid"] or Actor["uid"].'
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
        existing_actors: List[ActorInstanceSpec],
        declared_actor_vars: Dict[str, ast.Call] | None = None,
    ) -> ActorInstanceSpec:
        existing_uids = {actor.uid for actor in existing_actors}

        if len(args) == 1 and not kwargs:
            actor_arg = args[0]
            if isinstance(actor_arg, ast.Call):
                return self._parse_actor_instance_constructor(
                    ctor=actor_arg,
                    compiler=compiler,
                    existing_uids=existing_uids,
                    source_name="add_actor(...)",
                )
            if (
                isinstance(actor_arg, ast.Name)
                and declared_actor_vars is not None
                and actor_arg.id in declared_actor_vars
            ):
                return self._parse_actor_instance_constructor(
                    ctor=declared_actor_vars[actor_arg.id],
                    compiler=compiler,
                    existing_uids=existing_uids,
                    source_name=f"add_actor({actor_arg.id})",
                )

        if not args:
            raise DSLValidationError(
                "add_actor(...) expects Actor(...) or actor type as first argument."
            )

        actor_type = _expect_name(args[0], "actor type")
        if actor_type not in compiler.schemas.actor_fields:
            raise DSLValidationError(f"Unknown actor schema '{actor_type}'.")

        uid: Optional[str] = None
        if len(args) > 2:
            raise DSLValidationError(
                "add_actor(...) supports at most actor type and uid positional arguments."
            )
        if len(args) > 1:
            uid = _expect_string(args[1], "actor uid")
        if "uid" in kwargs:
            kw_uid = _expect_string(kwargs["uid"], "actor uid")
            if uid is not None and uid != kw_uid:
                raise DSLValidationError(
                    "add_actor(...) received conflicting uid positional and keyword values."
                )
            uid = kw_uid

        schema_fields = compiler.schemas.actor_fields[actor_type]
        values: Dict[str, object] = {}
        for key, value_node in kwargs.items():
            if key == "uid":
                continue
            if key not in schema_fields:
                raise DSLValidationError(
                    f"Unknown field '{key}' for actor type '{actor_type}'."
                )
            values[key] = self._parse_actor_field_value(
                value_node=value_node,
                field_name=key,
                field_type=schema_fields[key],
                compiler=compiler,
                source_name=f"add_actor({actor_type}, ...)",
            )

        uid = self._resolve_actor_uid(actor_type, uid, existing_uids, "add_actor(...)")
        self._fill_actor_default_fields(values, schema_fields)

        return ActorInstanceSpec(
            actor_type=actor_type,
            uid=uid,
            fields=cast(Dict[str, object], values),  # only primitive/list values stored
        )

    def _parse_actor_instance_constructor(
        self,
        ctor: ast.Call,
        compiler: DSLCompiler,
        existing_uids: set[str],
        source_name: str,
    ) -> ActorInstanceSpec:
        if not isinstance(ctor.func, ast.Name):
            raise DSLValidationError(
                f"{source_name} constructor argument must be ActorType(...)."
            )
        actor_type = ctor.func.id
        if actor_type not in compiler.schemas.actor_fields:
            raise DSLValidationError(f"Unknown actor schema '{actor_type}'.")
        if len(ctor.args) > 1:
            raise DSLValidationError(
                f"{source_name} actor constructor accepts at most one positional uid argument."
            )

        uid: Optional[str] = None
        if ctor.args:
            uid = _expect_string(ctor.args[0], "actor uid")

        schema_fields = compiler.schemas.actor_fields[actor_type]
        values: Dict[str, object] = {}
        for keyword in ctor.keywords:
            if keyword.arg is None:
                raise DSLValidationError(
                    f"{source_name} actor constructor does not support **kwargs expansion."
                )
            if keyword.arg == "uid":
                kw_uid = _expect_string(keyword.value, "actor uid")
                if uid is not None and uid != kw_uid:
                    raise DSLValidationError(
                        f"{source_name} actor constructor received conflicting uid values."
                    )
                uid = kw_uid
                continue
            if keyword.arg not in schema_fields:
                raise DSLValidationError(
                    f"Unknown field '{keyword.arg}' for actor type '{actor_type}'."
                )
            values[keyword.arg] = self._parse_actor_field_value(
                value_node=keyword.value,
                field_name=keyword.arg,
                field_type=schema_fields[keyword.arg],
                compiler=compiler,
                source_name=f"{actor_type}(...)",
            )

        uid = self._resolve_actor_uid(actor_type, uid, existing_uids, source_name)
        self._fill_actor_default_fields(values, schema_fields)

        return ActorInstanceSpec(
            actor_type=actor_type,
            uid=uid,
            fields=cast(Dict[str, object], values),
        )

    def _parse_actor_field_value(
        self,
        value_node: ast.AST,
        field_name: str,
        field_type: FieldType,
        compiler: DSLCompiler,
        source_name: str,
    ) -> object:
        if field_name == "parent":
            return self._parse_parent_uid(value_node, compiler, source_name)
        if field_name == "block_mask":
            return _expect_optional_int(value_node, "actor block_mask")
        return _parse_typed_value(value_node, field_type)

    def _parse_parent_uid(
        self, value_node: ast.AST, compiler: DSLCompiler, source_name: str
    ) -> str:
        if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
            return value_node.value
        if isinstance(value_node, (ast.Name, ast.Subscript)):
            selector = self._parse_selector(value_node, compiler)
            if selector.kind == SelectorKind.WITH_UID and selector.uid:
                return selector.uid
        raise DSLValidationError(
            f"{source_name} parent field must be uid string or ActorType[\"uid\"]."
        )

    def _fill_actor_default_fields(
        self,
        values: Dict[str, object],
        schema_fields: Dict[str, FieldType],
    ) -> None:
        for field_name, field_type in schema_fields.items():
            if field_name in values:
                continue
            if field_name in BASE_ACTOR_NO_DEFAULT_FIELDS:
                continue
            if field_name in BASE_ACTOR_DEFAULT_OVERRIDES:
                values[field_name] = BASE_ACTOR_DEFAULT_OVERRIDES[field_name]
                continue
            values[field_name] = _default_value_for_type(field_type)

    def _resolve_actor_uid(
        self,
        actor_type: str,
        uid: Optional[str],
        existing_uids: set[str],
        source_name: str,
    ) -> str:
        if uid is not None:
            if uid in existing_uids:
                raise DSLValidationError(
                    f"{source_name} received duplicate actor uid '{uid}'."
                )
            return uid
        index = 1
        prefix = actor_type.lower()
        while True:
            candidate = f"{prefix}_{index}"
            if candidate not in existing_uids:
                return candidate
            index += 1

    def _is_condition_expr(self, node: ast.Call) -> bool:
        if isinstance(node.func, ast.Name):
            return node.func.id in {
                "OnOverlap",
                "OnContact",
                "OnLogicalCondition",
                "OnToolCall",
                "OnButton",
            }
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            return node.func.value.id in {"KeyboardCondition", "MouseCondition"}
        return False

    def _has_plain_decorator(self, fn: ast.FunctionDef, name: str) -> bool:
        return any(
            isinstance(decorator, ast.Name) and decorator.id == name
            for decorator in fn.decorator_list
        )

    def _has_condition_decorator(self, fn: ast.FunctionDef) -> bool:
        for decorator in fn.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if isinstance(decorator.func, ast.Name) and decorator.func.id == "condition":
                return True
        return False

    def _normalize_callable_function(
        self,
        fn: ast.FunctionDef,
        compiler: DSLCompiler,
    ) -> ast.FunctionDef:
        cloned = copy.deepcopy(fn)
        cloned.decorator_list = [
            decorator
            for decorator in cloned.decorator_list
            if not (isinstance(decorator, ast.Name) and decorator.id == "callable")
        ]

        for arg in cloned.args.args:
            ann = arg.annotation
            if not (
                isinstance(ann, ast.Subscript) and isinstance(ann.value, ast.Name)
            ):
                continue
            head = ann.value.id
            if head in {"List", "list"}:
                continue
            if (
                head in {"Scene", "Tick", "Actor", "Role", "Global"}
                or head in compiler.schemas.actor_fields
                or head in compiler.schemas.role_fields
            ):
                warnings.warn(
                    format_dsl_diagnostic(
                        f"Selector annotation on callable parameter '{arg.arg}' is ignored; callable parameters are fully determined by the caller.",
                        node=ann,
                    ),
                    stacklevel=2,
                )
                arg.annotation = ast.copy_location(
                    ast.Name(id=head, ctx=ast.Load()),
                    ann,
                )
        return cloned

    def _strip_condition_decorators(self, fn: ast.FunctionDef) -> ast.FunctionDef:
        if not fn.decorator_list:
            return fn

        stripped = []
        removed = False
        for decorator in fn.decorator_list:
            if isinstance(decorator, ast.Name) and decorator.id == "callable":
                stripped.append(decorator)
                continue
            if not isinstance(decorator, ast.Call):
                stripped.append(decorator)
                continue
            if (
                isinstance(decorator.func, ast.Name)
                and decorator.func.id == "condition"
            ):
                removed = True
                continue
            stripped.append(decorator)

        if not removed:
            return fn
        cloned = copy.deepcopy(fn)
        cloned.decorator_list = stripped
        return cloned

    def _parse_decorator_conditions(
        self,
        node: ast.FunctionDef,
        condition_vars: Dict[str, ConditionSpec],
        compiler: DSLCompiler,
        predicates: Dict[str, PredicateIR],
        name_aliases: Dict[str, str],
        callable_aliases: Dict[str, ast.AST],
    ) -> List[ConditionSpec]:
        conditions: List[ConditionSpec] = []
        for decorator in node.decorator_list:
            with dsl_node_context(decorator):
                if not isinstance(decorator, ast.Call):
                    raise DSLValidationError(
                        f"Unsupported decorator on action '{node.name}'. Use @condition(...)."
                    )
                if isinstance(decorator.func, ast.Name) and decorator.func.id == "condition":
                    if len(decorator.args) != 1 or decorator.keywords:
                        raise DSLValidationError(
                            "@condition(...) expects exactly one positional condition argument."
                        )
                    raw_condition = decorator.args[0]
                    if isinstance(raw_condition, ast.Call):
                        resolved_condition_arg = _resolve_call_aliases(
                            raw_condition, name_aliases, callable_aliases
                        )
                    else:
                        resolved_condition_arg = _resolve_name_aliases_in_node(
                            raw_condition, name_aliases
                        )
                    conditions.append(
                        self._resolve_condition_arg(
                            resolved_condition_arg, condition_vars, compiler, predicates
                        )
                    )
                    continue

                raise DSLValidationError(
                    f"Unsupported decorator on action '{node.name}'. Use @condition(...)."
                )
        return conditions

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

            if owner == "KeyboardCondition":
                phase = _parse_keyboard_phase(method)
                if phase is None:
                    raise DSLValidationError("Unsupported keyboard condition method.")
                kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg is not None}
                unexpected = sorted(set(kwargs.keys()) - {"id"})
                if unexpected:
                    raise DSLValidationError(
                        "KeyboardCondition.<phase>(...) only accepts keyword 'id'."
                    )
                if len(node.args) not in {1, 2}:
                    raise DSLValidationError(
                        "KeyboardCondition.<phase>(...) expects key and required role id."
                    )
                role_id = _expect_string(node.args[1], "condition role id") if len(node.args) == 2 else None
                if len(node.args) == 2 and "id" in kwargs:
                    raise DSLValidationError(
                        "KeyboardCondition.<phase>(...) role id must be provided once."
                    )
                if role_id is None and "id" in kwargs:
                    role_id = _expect_string(kwargs["id"], "condition role id")
                if role_id is None:
                    raise DSLValidationError(
                        "KeyboardCondition.<phase>(...) requires role id. "
                        "Use id=\"<role_id>\" and declare it with game.add_role(Role(...))."
                    )
                return KeyboardConditionSpec(
                    key=_expect_string_or_string_list(node.args[0], "keyboard key"),
                    phase=phase,
                    role_id=role_id,
                )

            if owner == "MouseCondition":
                phase = _parse_mouse_phase(method)
                if phase is None:
                    raise DSLValidationError("Unsupported mouse condition method.")
                kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg is not None}
                unexpected = sorted(set(kwargs.keys()) - {"id"})
                if unexpected:
                    raise DSLValidationError(
                        "MouseCondition.<phase>(...) only accepts keyword 'id'."
                    )
                if len(node.args) > 2:
                    raise DSLValidationError(
                        "MouseCondition.<phase>(...) accepts button and required role id."
                    )
                button = "left"
                if len(node.args) >= 1:
                    button = _expect_string(node.args[0], "mouse button")
                role_id = _expect_string(node.args[1], "condition role id") if len(node.args) == 2 else None
                if len(node.args) == 2 and "id" in kwargs:
                    raise DSLValidationError(
                        "MouseCondition.<phase>(...) role id must be provided once."
                    )
                if role_id is None and "id" in kwargs:
                    role_id = _expect_string(kwargs["id"], "condition role id")
                if role_id is None:
                    raise DSLValidationError(
                        "MouseCondition.<phase>(...) requires role id. "
                        "Use id=\"<role_id>\" and declare it with game.add_role(Role(...))."
                    )
                return MouseConditionSpec(
                    button=button,
                    phase=phase,
                    role_id=role_id,
                )

        if (
            isinstance(node.func, ast.Name)
            and node.func.id in {"OnOverlap", "OnContact"}
        ):
            if len(node.args) != 2 or node.keywords:
                raise DSLValidationError(
                    f"{node.func.id}(...) expects two selectors."
                )
            left = self._parse_selector(node.args[0], compiler)
            right = self._parse_selector(node.args[1], compiler)
            if node.func.id == "OnContact":
                mode = CollisionMode.CONTACT
            else:
                mode = CollisionMode.OVERLAP
            return CollisionConditionSpec(left=left, right=right, mode=mode)

        if isinstance(node.func, ast.Name) and node.func.id == "OnLogicalCondition":
            if len(node.args) != 2 or node.keywords:
                raise DSLValidationError(
                    "OnLogicalCondition(...) expects predicate and selector."
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
                    f"OnLogicalCondition selector type '{selector.actor_type}' does not "
                    f"match predicate actor type '{predicate.actor_type}'."
                )
            return LogicalConditionSpec(predicate_name=predicate_name, target=selector)

        if isinstance(node.func, ast.Name) and node.func.id == "OnToolCall":
            kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg is not None}
            unexpected = sorted(set(kwargs.keys()) - {"id"})
            if unexpected:
                raise DSLValidationError(
                    "OnToolCall(...) only accepts keyword 'id'."
                )
            if len(node.args) not in {2, 3}:
                raise DSLValidationError(
                    "OnToolCall(...) expects tool name, docstring, and required role id."
                )
            role_id = _expect_string(node.args[2], "condition role id") if len(node.args) == 3 else None
            if len(node.args) == 3 and "id" in kwargs:
                raise DSLValidationError("OnToolCall(...) role id must be provided once.")
            if role_id is None and "id" in kwargs:
                role_id = _expect_string(kwargs["id"], "condition role id")
            if role_id is None:
                raise DSLValidationError(
                    "OnToolCall(...) requires role id. "
                    "Use id=\"<role_id>\" and declare it with game.add_role(Role(...))."
                )
            return ToolConditionSpec(
                name=_expect_string(node.args[0], "tool name"),
                tool_docstring=_expect_string(node.args[1], "tool docstring"),
                role_id=role_id,
            )

        if isinstance(node.func, ast.Name) and node.func.id == "OnButton":
            if len(node.args) != 1 or node.keywords:
                raise DSLValidationError("OnButton(...) expects one button name argument.")
            return ButtonConditionSpec(name=_expect_string(node.args[0], "button name"))

        raise DSLValidationError("Unsupported condition expression.")

    def _parse_selector(
        self, node: ast.AST, compiler: DSLCompiler
    ) -> ActorSelectorSpec:
        if isinstance(node, ast.Name):
            actor_type = self._parse_actor_type_ref(node, compiler)
            return ActorSelectorSpec(kind=SelectorKind.ANY, actor_type=actor_type)

        if isinstance(node, ast.Subscript):
            if not isinstance(node.value, ast.Name):
                raise DSLValidationError(
                    'Selector must be ActorType or ActorType["uid"].'
                )
            actor_type = self._parse_actor_type_ref(node.value, compiler)
            uid = _expect_string(node.slice, "actor uid")
            return ActorSelectorSpec(
                kind=SelectorKind.WITH_UID,
                actor_type=actor_type,
                uid=uid,
            )

        raise DSLValidationError('Selector must be ActorType or ActorType["uid"].')

    def _parse_actor_type_ref(
        self, node: ast.AST, compiler: DSLCompiler
    ) -> Optional[str]:
        actor_name = _expect_name(node, "actor type")
        if actor_name == "Tile":
            return "Tile"
        if actor_name == "Actor":
            return None
        if actor_name not in compiler.schemas.actor_fields:
            raise DSLValidationError(f"Unknown actor schema '{actor_name}'.")
        return actor_name

    def _parse_tile_map(
        self,
        node: ast.AST,
        *,
        declared_color_vars: Optional[Dict[str, ast.Call]] = None,
        declared_tile_vars: Optional[Dict[str, ast.Call]] = None,
    ) -> TileMapSpec:
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            raise DSLValidationError("set_map(...) expects TileMap(...).")
        if node.func.id != "TileMap":
            raise DSLValidationError("set_map(...) expects TileMap(...).")
        if node.args:
            raise DSLValidationError("TileMap(...) only supports keyword arguments.")

        declared_color_vars = declared_color_vars or {}
        declared_tile_vars = declared_tile_vars or {}
        kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg is not None}
        allowed = {"width", "height", "tile_size", "grid", "tiles"}
        unexpected = sorted(set(kwargs.keys()) - allowed)
        if unexpected:
            raise DSLValidationError(
                f"TileMap(...) received unsupported arguments: {unexpected}"
            )

        required = {"tile_size", "grid", "tiles"}
        missing = required - set(kwargs.keys())
        if missing:
            raise DSLValidationError(f"TileMap(...) missing arguments: {sorted(missing)}")

        tile_size = _expect_int(kwargs["tile_size"], "map tile_size")
        if tile_size <= 0:
            raise DSLValidationError("map tile_size must be > 0.")

        tile_grid = self._parse_tile_grid(kwargs["grid"])
        if not tile_grid:
            raise DSLValidationError("map grid must contain at least one row.")
        width = len(tile_grid[0])
        if width <= 0:
            raise DSLValidationError("map grid rows must contain at least one tile.")
        if any(len(row) != width for row in tile_grid):
            raise DSLValidationError("map grid must be rectangular.")
        height = len(tile_grid)
        for row in tile_grid:
            for tile_id in row:
                if tile_id < 0:
                    raise DSLValidationError("map grid tile ids must be >= 0.")

        if "width" in kwargs and _expect_int(kwargs["width"], "map width") != width:
            raise DSLValidationError(
                "TileMap width must match the number of columns in grid."
            )
        if "height" in kwargs and _expect_int(kwargs["height"], "map height") != height:
            raise DSLValidationError(
                "TileMap height must match the number of rows in grid."
            )

        tile_defs = self._parse_tile_palette(
            kwargs["tiles"],
            declared_color_vars=declared_color_vars,
            declared_tile_vars=declared_tile_vars,
        )
        for tile_y, row in enumerate(tile_grid):
            for tile_x, tile_id in enumerate(row):
                if tile_id == 0:
                    continue
                if tile_id not in tile_defs:
                    raise DSLValidationError(
                        f"map grid references tile id '{tile_id}' at ({tile_x}, {tile_y}) "
                        "but this id is not defined in tiles."
                    )

        return TileMapSpec(
            width=width,
            height=height,
            tile_size=tile_size,
            tile_grid=tile_grid,
            tile_defs=tile_defs,
        )

    def _parse_tile_grid(self, node: ast.AST) -> List[List[int]]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return self._load_tile_grid_from_file(node.value)
        return _expect_int_matrix(node, "map grid")

    def _load_tile_grid_from_file(self, path_value: str) -> List[List[int]]:
        raw_path = path_value.strip()
        if not raw_path:
            raise DSLValidationError("map grid file path cannot be empty.")

        candidate = Path(raw_path)
        resolved = candidate if candidate.is_absolute() else (self._source_dir / candidate)

        try:
            text = resolved.read_text(encoding="utf-8")
        except OSError as exc:
            raise DSLValidationError(
                f"Cannot read map grid file '{raw_path}': {exc}."
            ) from exc

        rows: List[List[int]] = []
        for line_no, raw_line in enumerate(text.splitlines(), start=1):
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            tokens = stripped.replace(",", " ").split()
            if not tokens:
                continue

            row: List[int] = []
            for token in tokens:
                try:
                    value = int(token, 10)
                except ValueError as exc:
                    raise DSLValidationError(
                        f"Invalid map grid value '{token}' in '{raw_path}' at line {line_no}. "
                        "Expected integers."
                    ) from exc
                row.append(value)
            rows.append(row)

        if not rows:
            raise DSLValidationError(
                f"Map grid file '{raw_path}' does not contain any integer rows."
            )

        row_width = len(rows[0])
        if row_width == 0:
            raise DSLValidationError(f"Map grid file '{raw_path}' contains an empty first row.")
        if any(len(row) != row_width for row in rows):
            raise DSLValidationError(
                f"Map grid file '{raw_path}' must be rectangular."
            )
        for row in rows:
            for value in row:
                if value < 0:
                    raise DSLValidationError(
                        f"Map grid file '{raw_path}' contains negative tile id {value}."
                    )

        return rows

    def _parse_tile_palette(
        self,
        node: Optional[ast.AST],
        *,
        declared_color_vars: Dict[str, ast.Call],
        declared_tile_vars: Dict[str, ast.Call],
    ) -> Dict[int, TileSpec]:
        if node is None:
            return {}
        if not isinstance(node, ast.Dict):
            raise DSLValidationError(
                "TileMap(..., tiles=...) expects dict[int, Tile(...)]."
            )

        out: Dict[int, TileSpec] = {}
        for key_node, value_node in zip(node.keys, node.values):
            if key_node is None:
                raise DSLValidationError("TileMap tiles keys cannot be null.")
            tile_id = _expect_int(key_node, "tile id")
            if tile_id <= 0:
                raise DSLValidationError(
                    "TileMap tiles keys must be > 0. Use 0 in grid for empty tiles."
                )
            if tile_id in out:
                raise DSLValidationError(f"Duplicate tile id '{tile_id}' in tiles map.")

            tile_expr = value_node
            if isinstance(tile_expr, ast.Name):
                if tile_expr.id not in declared_tile_vars:
                    raise DSLValidationError(
                        f"Unknown Tile variable '{tile_expr.id}' in tiles map."
                    )
                tile_expr = declared_tile_vars[tile_expr.id]
            out[tile_id] = self._parse_tile_definition(
                tile_expr,
                declared_color_vars=declared_color_vars,
            )
        return out

    def _parse_tile_definition(
        self,
        node: ast.AST,
        *,
        declared_color_vars: Dict[str, ast.Call],
    ) -> TileSpec:
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            raise DSLValidationError("Tile definition must be Tile(...).")
        if node.func.id != "Tile":
            raise DSLValidationError("Tile definition must be Tile(...).")
        if node.args:
            raise DSLValidationError("Tile(...) only supports keyword arguments.")

        kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg is not None}
        allowed = {"block_mask", "color", "sprite"}
        unexpected = sorted(set(kwargs.keys()) - allowed)
        if unexpected:
            raise DSLValidationError(
                f"Tile(...) received unsupported arguments: {unexpected}"
            )

        has_color = "color" in kwargs
        has_sprite = "sprite" in kwargs
        if has_color == has_sprite:
            raise DSLValidationError("Tile(...) requires exactly one of color or sprite.")
        block_mask = (
            _expect_optional_int(kwargs["block_mask"], "tile block_mask")
            if "block_mask" in kwargs
            else None
        )
        if block_mask is not None and block_mask < 0:
            raise DSLValidationError("Tile block_mask must be >= 0.")

        if has_color:
            color = self._parse_tile_color(
                kwargs["color"],
                declared_color_vars=declared_color_vars,
            )
            return TileSpec(block_mask=block_mask, color=color, sprite=None)

        sprite = _expect_string(kwargs["sprite"], "tile sprite")
        return TileSpec(block_mask=block_mask, color=None, sprite=sprite)

    def _parse_tile_color(
        self,
        node: ast.AST,
        *,
        declared_color_vars: Dict[str, ast.Call],
    ) -> ColorSpec:
        color_expr = node
        if isinstance(color_expr, ast.Name):
            if color_expr.id not in declared_color_vars:
                raise DSLValidationError(
                    f"Unknown Color variable '{color_expr.id}' in Tile(...)."
                )
            color_expr = declared_color_vars[color_expr.id]

        if not isinstance(color_expr, ast.Call) or not isinstance(color_expr.func, ast.Name):
            raise DSLValidationError("Tile color must be Color(...).")
        if color_expr.func.id != "Color":
            raise DSLValidationError("Tile color must be Color(...).")

        kwargs = {kw.arg: kw.value for kw in color_expr.keywords if kw.arg is not None}
        allowed = {"r", "g", "b", "symbol", "description"}
        unexpected = sorted(set(kwargs.keys()) - allowed)
        if unexpected:
            raise DSLValidationError(
                f"Color(...) received unsupported arguments: {unexpected}"
            )

        if len(color_expr.args) not in {0, 3}:
            raise DSLValidationError("Color(...) expects either 3 positional args or keyword r/g/b.")

        channel_nodes: Dict[str, ast.AST] = {}
        if color_expr.args:
            channel_nodes["r"] = color_expr.args[0]
            channel_nodes["g"] = color_expr.args[1]
            channel_nodes["b"] = color_expr.args[2]

        for channel in ("r", "g", "b"):
            if channel in kwargs:
                if channel in channel_nodes:
                    raise DSLValidationError(
                        f"Color(...) channel '{channel}' cannot be both positional and keyword."
                    )
                channel_nodes[channel] = kwargs[channel]

        missing = [channel for channel in ("r", "g", "b") if channel not in channel_nodes]
        if missing:
            raise DSLValidationError(
                f"Color(...) missing channels: {missing}"
            )

        r = _expect_int(channel_nodes["r"], "color red")
        g = _expect_int(channel_nodes["g"], "color green")
        b = _expect_int(channel_nodes["b"], "color blue")
        for label, value in (("red", r), ("green", g), ("blue", b)):
            if value < 0 or value > 255:
                raise DSLValidationError(f"Color {label} must be between 0 and 255.")

        symbol = _expect_single_character_or_default(
            kwargs.get("symbol"),
            "color symbol",
            None,
        )
        description = _expect_string_or_default(
            kwargs.get("description"),
            "color description",
            None,
        )

        return ColorSpec(
            r=r,
            g=g,
            b=b,
            symbol=symbol,
            description=description,
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

    def _parse_scene(self, node: ast.AST) -> SceneSpec:
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            raise DSLValidationError("set_scene(...) expects Scene(...).")
        if node.func.id != "Scene":
            raise DSLValidationError("set_scene(...) expects Scene(...).")
        if node.args:
            raise DSLValidationError("Scene(...) only supports keyword arguments.")

        kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg is not None}
        allowed = {"gravity", "keyboard_aliases"}
        unexpected = sorted(set(kwargs.keys()) - allowed)
        if unexpected:
            raise DSLValidationError(
                f"Scene(...) received unsupported arguments: {unexpected}"
            )

        gravity_node = kwargs.get("gravity")
        gravity_enabled = _expect_bool_or_default(
            gravity_node,
            "scene gravity_enabled",
            False,
        )
        keyboard_aliases = _expect_string_to_string_list_dict_or_default(
            kwargs.get("keyboard_aliases"),
            "scene keyboard_aliases",
            {},
        )
        return SceneSpec(
            gravity_enabled=gravity_enabled,
            keyboard_aliases=keyboard_aliases,
        )

    def _parse_resource(
        self, args: List[ast.AST], kwargs: Dict[str, ast.AST]
    ) -> ResourceSpec:
        if kwargs:
            raise DSLValidationError("add_resource(...) does not accept keyword args.")
        if len(args) != 2:
            raise DSLValidationError(
                "add_resource(...) expects name and path arguments."
            )
        return ResourceSpec(
            name=_expect_string(args[0], "resource name"),
            path=_expect_string(args[1], "resource path"),
        )

    def _parse_sprite(
        self,
        args: List[ast.AST],
        kwargs: Dict[str, ast.AST],
        compiler: DSLCompiler,
        declared_sprite_vars: Dict[str, ast.Call] | None = None,
    ) -> SpriteSpec:
        sprite_kwargs = kwargs
        source_name = "add_sprite(...)"
        if args:
            if len(args) != 1 or kwargs:
                raise DSLValidationError(
                    "add_sprite(...) expects either keyword args or one Sprite(...) object."
                )
            sprite_arg = args[0]
            if (
                isinstance(sprite_arg, ast.Name)
                and declared_sprite_vars is not None
                and sprite_arg.id in declared_sprite_vars
            ):
                sprite_kwargs = self._extract_sprite_kwargs(
                    declared_sprite_vars[sprite_arg.id]
                )
                source_name = f"add_sprite({sprite_arg.id})"
            else:
                sprite_kwargs = self._extract_sprite_kwargs(sprite_arg)
                source_name = "Sprite(...)"

        return self._parse_sprite_from_kwargs(
            sprite_kwargs=sprite_kwargs,
            compiler=compiler,
            source_name=source_name,
        )

    def _extract_sprite_kwargs(self, node: ast.AST) -> Dict[str, ast.AST]:
        if not isinstance(node, ast.Call):
            raise DSLValidationError(
                "add_sprite(...) positional argument must be Sprite(...)."
            )
        if not isinstance(node.func, ast.Name) or node.func.id != "Sprite":
            raise DSLValidationError(
                "add_sprite(...) positional argument must be Sprite(...)."
            )
        if node.args:
            raise DSLValidationError("Sprite(...) only supports keyword arguments.")
        return {kw.arg: kw.value for kw in node.keywords if kw.arg is not None}

    def _parse_sprite_from_kwargs(
        self,
        sprite_kwargs: Dict[str, ast.AST],
        compiler: DSLCompiler,
        source_name: str,
    ) -> SpriteSpec:
        allowed = {
            "name",
            "uid",
            "actor_type",
            "bind",
            "resource",
            "frame_width",
            "frame_height",
            "clips",
            "default_clip",
            "row",
            "scale",
            "flip_x",
            "offset_x",
            "offset_y",
            "symbol",
            "description",
        }
        unexpected = sorted(set(sprite_kwargs.keys()) - allowed)
        if unexpected:
            raise DSLValidationError(
                f"{source_name} received unsupported arguments: {unexpected}"
            )

        required = {"resource", "frame_width", "frame_height", "clips"}
        missing = required - set(sprite_kwargs.keys())
        if missing:
            raise DSLValidationError(
                f"{source_name} missing required arguments: {sorted(missing)}"
            )

        name = None
        if "name" in sprite_kwargs:
            name = _expect_string(sprite_kwargs["name"], "sprite name")

        uid, actor_type = self._parse_sprite_binding(
            sprite_kwargs, compiler, source_name, sprite_name=name
        )

        clips = self._parse_sprite_clips(sprite_kwargs["clips"])
        default_clip = None
        if "default_clip" in sprite_kwargs:
            default_clip = _expect_string(
                sprite_kwargs["default_clip"],
                "default clip name",
            )
            if default_clip not in {clip.name for clip in clips}:
                raise DSLValidationError(
                    f"Unknown default clip '{default_clip}' in {source_name}."
                )

        return SpriteSpec(
            name=name,
            uid=uid,
            actor_type=actor_type,
            resource=_expect_string(sprite_kwargs["resource"], "sprite resource name"),
            frame_width=_expect_int(sprite_kwargs["frame_width"], "sprite frame_width"),
            frame_height=_expect_int(
                sprite_kwargs["frame_height"],
                "sprite frame_height",
            ),
            clips=clips,
            default_clip=default_clip,
            row=_expect_int_or_default(sprite_kwargs.get("row"), "sprite row", 0),
            scale=_expect_float_or_default(sprite_kwargs.get("scale"), "sprite scale", 1.0),
            flip_x=_expect_bool_or_default(
                sprite_kwargs.get("flip_x"),
                "sprite flip_x",
                True,
            ),
            offset_x=_expect_float_or_default(
                sprite_kwargs.get("offset_x"),
                "sprite offset_x",
                0.0,
            ),
            offset_y=_expect_float_or_default(
                sprite_kwargs.get("offset_y"),
                "sprite offset_y",
                0.0,
            ),
            symbol=_expect_single_character_or_default(
                sprite_kwargs.get("symbol"),
                "sprite symbol",
                None,
            ),
            description=_expect_string_or_default(
                sprite_kwargs.get("description"),
                "sprite description",
                None,
            ),
        )

    def _parse_sprite_binding(
        self,
        sprite_kwargs: Dict[str, ast.AST],
        compiler: DSLCompiler,
        source_name: str,
        sprite_name: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        uid: Optional[str] = None
        actor_type: Optional[str] = None

        if "uid" in sprite_kwargs:
            uid = _expect_string(sprite_kwargs["uid"], "sprite uid")

        if "actor_type" in sprite_kwargs:
            actor_type = self._parse_actor_type_ref(sprite_kwargs["actor_type"], compiler)
            if actor_type is None:
                raise DSLValidationError(
                    f"{source_name} actor_type cannot be generic Actor."
                )

        bind_node = sprite_kwargs.get("bind")
        if bind_node is not None:
            bind_uid, bind_type = self._parse_sprite_bind_expr(bind_node, compiler, source_name)
            if bind_uid is not None:
                if uid is not None and uid != bind_uid:
                    raise DSLValidationError(
                        f"{source_name} has conflicting uid and bind target values."
                    )
                uid = bind_uid
            if bind_type is not None:
                if actor_type is not None and actor_type != bind_type:
                    raise DSLValidationError(
                        f"{source_name} has conflicting actor_type and bind target values."
                    )
                actor_type = bind_type

        if uid is None and actor_type is None:
            if sprite_name is not None:
                return None, None
            raise DSLValidationError(
                f"{source_name} requires exactly one binding target (uid, actor_type, or bind) "
                "unless a sprite name is provided."
            )
        if uid is not None and actor_type is not None:
            raise DSLValidationError(
                f"{source_name} requires exactly one binding target (uid, actor_type, or bind)."
            )

        return uid, actor_type

    def _parse_sprite_bind_expr(
        self,
        node: ast.AST,
        compiler: DSLCompiler,
        source_name: str,
    ) -> Tuple[Optional[str], Optional[str]]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value, None

        if isinstance(node, (ast.Name, ast.Subscript)):
            selector = self._parse_selector(node, compiler)
            if selector.kind == SelectorKind.WITH_UID and selector.uid is not None:
                return selector.uid, None
            if selector.kind == SelectorKind.ANY and selector.actor_type is not None:
                return None, selector.actor_type

        raise DSLValidationError(
            f'{source_name} bind target must be uid string, actor schema name, or ActorType["uid"].'
        )

    def _parse_sprite_clips(self, node: ast.AST) -> List[AnimationClipSpec]:
        raw_value = _eval_static_expr(node)
        if not isinstance(raw_value, dict):
            raise DSLValidationError(
                "add_sprite(..., clips=...) expects a dict of clip definitions."
            )
        clips: List[AnimationClipSpec] = []
        seen_names: set[str] = set()
        for raw_key, raw_clip in raw_value.items():
            if not isinstance(raw_key, str):
                raise DSLValidationError("Clip names must be strings.")
            clip_name = raw_key
            if clip_name in seen_names:
                raise DSLValidationError(f"Duplicate clip '{clip_name}'.")
            seen_names.add(clip_name)

            if isinstance(raw_clip, list):
                frames = self._expect_int_values(
                    raw_clip, f"frames for clip '{clip_name}'"
                )
                clips.append(AnimationClipSpec(name=clip_name, frames=frames))
                continue

            if isinstance(raw_clip, dict):
                if "frames" not in raw_clip:
                    raise DSLValidationError(
                        f"Clip '{clip_name}' missing required 'frames'."
                    )
                frames = self._expect_int_values(
                    raw_clip["frames"], f"frames for clip '{clip_name}'"
                )
                ticks_raw = raw_clip.get("ticks_per_frame", 8)
                if not isinstance(ticks_raw, int) or isinstance(ticks_raw, bool):
                    raise DSLValidationError(
                        f"ticks_per_frame for clip '{clip_name}' must be an integer."
                    )
                ticks_per_frame = ticks_raw
                if ticks_per_frame <= 0:
                    raise DSLValidationError(
                        f"ticks_per_frame for clip '{clip_name}' must be > 0."
                    )
                loop_raw = raw_clip.get("loop", True)
                if not isinstance(loop_raw, bool):
                    raise DSLValidationError(
                        f"loop for clip '{clip_name}' must be a bool."
                    )
                loop = loop_raw
                clips.append(
                    AnimationClipSpec(
                        name=clip_name,
                        frames=frames,
                        ticks_per_frame=ticks_per_frame,
                        loop=loop,
                    )
                )
                continue

            raise DSLValidationError(
                f"Clip '{clip_name}' must be a list of frames or a dict config."
            )

        if not clips:
            raise DSLValidationError("add_sprite(..., clips=...) cannot be empty.")
        return clips

    def _expect_int_values(self, raw_value: object, label: str) -> List[int]:
        if not isinstance(raw_value, list):
            raise DSLValidationError(f"Expected {label} as list[int].")
        values: List[int] = []
        for item in raw_value:
            if isinstance(item, int) and not isinstance(item, bool):
                values.append(item)
                continue
            raise DSLValidationError(f"Expected {label} as list[int].")
        if not values:
            raise DSLValidationError(f"Expected {label} to contain at least one frame.")
        return values

    def _bind_collision_action_params(
        self,
        action_name: str,
        action: ActionIR,
        condition: CollisionConditionSpec,
        warned_actions: set[str],
        source_node: Optional[ast.AST] = None,
    ) -> ActionIR:
        if len(action.params) < 2:
            raise DSLValidationError(
                f"Collision action '{action_name}' must declare at least 2 parameters "
                "(left actor, right actor)."
            )

        left_param = action.params[0]
        right_param = action.params[1]
        if left_param.kind != BindingKind.ACTOR or right_param.kind != BindingKind.ACTOR:
            raise DSLValidationError(
                f"Collision action '{action_name}' first two parameters must be actor bindings."
            )

        left_selector = left_param.actor_selector
        right_selector = right_param.actor_selector
        left_has_explicit_selector = (
            left_selector is not None
            and (
                left_selector.index is not None
                or (
                    left_selector.uid is not None
                    and (
                        left_param.actor_type is None
                        or left_selector.uid != left_param.actor_type
                    )
                )
            )
        )
        right_has_explicit_selector = (
            right_selector is not None
            and (
                right_selector.index is not None
                or (
                    right_selector.uid is not None
                    and (
                        right_param.actor_type is None
                        or right_selector.uid != right_param.actor_type
                    )
                )
            )
        )
        if action_name not in warned_actions and (
            left_has_explicit_selector or right_has_explicit_selector
        ):
            warnings.warn(
                format_dsl_diagnostic(
                    f"OnOverlap/OnContact imposes actor bindings for the first two parameters "
                    f"of action '{action_name}'. Explicit selector annotations on those "
                    "parameters are ignored.",
                    node=source_node,
                ),
                stacklevel=2,
            )
            warned_actions.add(action_name)

        if left_param.actor_type != condition.left.actor_type and condition.left.actor_type:
            warnings.warn(
                format_dsl_diagnostic(
                    f"Collision action '{action_name}' first parameter annotation "
                    f"'{left_param.actor_type}' differs from collision selector type "
                    f"'{condition.left.actor_type}'. Runtime collision binding takes precedence.",
                    node=source_node,
                ),
                stacklevel=2,
            )
        if right_param.actor_type != condition.right.actor_type and condition.right.actor_type:
            warnings.warn(
                format_dsl_diagnostic(
                    f"Collision action '{action_name}' second parameter annotation "
                    f"'{right_param.actor_type}' differs from collision selector type "
                    f"'{condition.right.actor_type}'. Runtime collision binding takes precedence.",
                    node=source_node,
                ),
                stacklevel=2,
            )

        left_actor_type = left_param.actor_type or condition.left.actor_type
        right_actor_type = right_param.actor_type or condition.right.actor_type

        rebound_left = ParamBinding(
            name=left_param.name,
            kind=BindingKind.ACTOR,
            actor_selector=ActorSelector(uid=COLLISION_LEFT_BINDING_UID),
            actor_type=left_actor_type,
        )
        rebound_right = ParamBinding(
            name=right_param.name,
            kind=BindingKind.ACTOR,
            actor_selector=ActorSelector(uid=COLLISION_RIGHT_BINDING_UID),
            actor_type=right_actor_type,
        )

        params = list(action.params)
        params[0] = rebound_left
        params[1] = rebound_right
        return replace(action, params=params)

    def _bind_logical_predicate_params(
        self,
        predicate_name: str,
        predicate: PredicateIR,
        condition: LogicalConditionSpec,
        warned_predicates: set[str],
        source_node: Optional[ast.AST] = None,
    ) -> PredicateIR:
        params = list(predicate.params)
        actor_param_index = next(
            (idx for idx, param in enumerate(params) if param.kind == BindingKind.ACTOR),
            None,
        )
        if actor_param_index is None:
            raise DSLValidationError(
                f"Logical predicate '{predicate_name}' must declare at least one actor parameter."
            )

        actor_param = params[actor_param_index]
        actor_selector = actor_param.actor_selector
        has_explicit_selector = (
            actor_selector is not None
            and (
                actor_selector.index is not None
                or (
                    actor_selector.uid is not None
                    and (
                        actor_param.actor_type is None
                        or actor_selector.uid != actor_param.actor_type
                    )
                )
            )
        )
        if predicate_name not in warned_predicates and has_explicit_selector:
            warnings.warn(
                format_dsl_diagnostic(
                    f"OnLogicalCondition imposes actor binding for predicate '{predicate_name}' "
                    f"parameter '{actor_param.name}'. Explicit selector annotation on that "
                    "parameter is ignored.",
                    node=source_node,
                ),
                stacklevel=2,
            )
            warned_predicates.add(predicate_name)

        if (
            actor_param.actor_type is not None
            and condition.target.actor_type is not None
            and actor_param.actor_type != condition.target.actor_type
        ):
            raise DSLValidationError(
                f"OnLogicalCondition selector type '{condition.target.actor_type}' does not "
                f"match predicate actor parameter type '{actor_param.actor_type}'."
            )

        bound_actor_type = actor_param.actor_type or condition.target.actor_type
        params[actor_param_index] = ParamBinding(
            name=actor_param.name,
            kind=BindingKind.ACTOR,
            actor_selector=ActorSelector(uid=LOGICAL_TARGET_BINDING_UID),
            actor_type=bound_actor_type,
        )

        return replace(
            predicate,
            params=params,
            param_name=actor_param.name,
            actor_type=bound_actor_type,
        )

    def _validate_sprite_targets(
        self,
        actors: List[ActorInstanceSpec],
        sprites: List[SpriteSpec],
        compiler: DSLCompiler,
    ) -> None:
        actor_uids = {actor.uid for actor in actors}
        for sprite in sprites:
            if sprite.uid is not None and sprite.uid not in actor_uids:
                raise DSLValidationError(
                    f"add_sprite(...) references unknown actor uid '{sprite.uid}'."
                )
            if (
                sprite.actor_type is not None
                and sprite.actor_type not in compiler.schemas.actor_fields
            ):
                raise DSLValidationError(
                    f"add_sprite(...) references unknown actor_type '{sprite.actor_type}'."
                )

    def _validate_sprite_resources(
        self,
        resources: Dict[str, ResourceSpec],
        sprites: List[SpriteSpec],
    ) -> None:
        for sprite in sprites:
            if sprite.resource not in resources:
                raise DSLValidationError(
                    f"add_sprite(...) references unknown resource '{sprite.resource}'."
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
        if annotation.id in {"Scene", "Tick", "Actor", "Role"}:
            return True
        return (
            annotation.id in compiler.schemas.actor_fields
            or annotation.id in compiler.schemas.role_fields
        )

    if isinstance(annotation, ast.Subscript) and isinstance(annotation.value, ast.Name):
        head = annotation.value.id
        if head in {"Scene", "Tick", "Actor", "Role", "Global", "List", "list"}:
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


def _eval_static_expr(node: ast.AST):
    if isinstance(node, ast.Constant):
        value = node.value
        if value is None:
            return None
        if isinstance(value, (bool, int, float, str)):
            return value
        raise DSLValidationError("Unsupported constant value in setup expression.")

    if isinstance(node, ast.List):
        return [_eval_static_expr(item) for item in node.elts]

    if isinstance(node, ast.Tuple):
        return tuple(_eval_static_expr(item) for item in node.elts)

    if isinstance(node, ast.Dict):
        out: Dict[object, object] = {}
        for key_node, value_node in zip(node.keys, node.values):
            if key_node is None:
                raise DSLValidationError("Dict unpacking is not supported in setup expressions.")
            key = _eval_static_expr(key_node)
            if not isinstance(key, (str, int, float, bool)):
                raise DSLValidationError(
                    "Dict keys in setup expressions must be primitive constants."
                )
            out[key] = _eval_static_expr(value_node)
        return out

    if isinstance(node, ast.UnaryOp):
        operand = _eval_static_expr(node.operand)
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
        left = _eval_static_expr(node.left)
        right = _eval_static_expr(node.right)

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
            current = _eval_static_expr(node.values[0])
            for value_node in node.values[1:]:
                if not current:
                    return current
                current = _eval_static_expr(value_node)
            return current
        if isinstance(node.op, ast.Or):
            current = _eval_static_expr(node.values[0])
            for value_node in node.values[1:]:
                if current:
                    return current
                current = _eval_static_expr(value_node)
            return current
        raise DSLValidationError(
            f"Unsupported boolean operator in setup expression: {type(node.op).__name__}"
        )

    if isinstance(node, ast.Compare):
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise DSLValidationError("Chained comparisons are not supported in setup expressions.")
        left = _eval_static_expr(node.left)
        right = _eval_static_expr(node.comparators[0])
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

    if isinstance(node, ast.Call):
        if node.keywords:
            raise DSLValidationError("Keyword arguments are not supported in setup expression calls.")
        if not isinstance(node.func, ast.Attribute):
            raise DSLValidationError(
                "Only collection helper calls are supported in setup expressions."
            )
        receiver = _eval_static_expr(node.func.value)
        args = [_eval_static_expr(arg) for arg in node.args]
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
