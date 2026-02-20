import ast
import copy
import warnings
from dataclasses import replace
from pathlib import Path
from typing import Dict, List, Optional, Tuple, cast

from nanocalibur.compiler import DSLCompiler
from nanocalibur.compiler.constants import (
    BASE_ACTOR_DEFAULT_OVERRIDES,
    BASE_ACTOR_NO_DEFAULT_FIELDS,
    CALLABLE_EXPR_PREFIX,
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

from nanocalibur.project_compiler_ast import (
    _action_contains_next_turn,
    _as_game_method_call,
    _as_owner_method_call,
    _collect_used_callable_names,
    _expect_name,
    _extract_declared_actor_ctor_uid,
    _extract_informal_docstring,
    _format_syntax_error,
    _is_supported_action_binding_annotation,
    _looks_like_action,
    _looks_like_predicate,
    _parse_keyboard_phase,
    _parse_mouse_phase,
    _resolve_call_aliases,
    _resolve_name_alias,
    _resolve_name_aliases_in_node,
    _track_top_level_assignment_alias,
)
from nanocalibur.project_compiler_values import (
    _default_value_for_type,
    _eval_static_expr,
    _expect_bool_or_default,
    _expect_float_or_default,
    _expect_int,
    _expect_int_list,
    _expect_int_matrix,
    _expect_int_or_default,
    _expect_number,
    _expect_number_or_default,
    _expect_optional_int,
    _expect_primitive_or_nested_list_constant,
    _expect_single_character_or_default,
    _expect_string,
    _expect_string_list,
    _expect_string_or_default,
    _expect_string_or_string_list,
    _expect_string_to_string_list_dict_or_default,
    _field_type_label,
    _infer_primitive_dict_kind,
    _infer_primitive_list_kind,
    _parse_global_type_expr,
    _parse_multiplayer_loop_mode,
    _parse_role_kind,
    _parse_typed_runtime_value,
    _parse_typed_value,
    _parse_visibility_mode,
    _substitute_static_names_in_node,
    _update_static_setup_env_from_stmt,
)


COLLISION_LEFT_BINDING_UID = "__nanocalibur_collision_left__"
COLLISION_RIGHT_BINDING_UID = "__nanocalibur_collision_right__"
LOGICAL_TARGET_BINDING_UID = "__nanocalibur_logical_target__"
CONDITION_DECORATOR_NAMES = {"safe_condition", "unsafe_condition"}
IMMUTABLE_DSL_CLASS_NAMES = {
    "Actor",
    "ActorModel",
    "Local",
    "Role",
    "HumanRole",
    "Scene",
    "Game",
    "Sprite",
    "Resource",
    "Interface",
    "Camera",
    "Tile",
    "TileMap",
    "Color",
    "Global",
    "GlobalVariable",
    "KeyboardCondition",
    "MouseCondition",
    "Random",
    "CodeBlock",
    "AbstractCodeBlock",
}


class ProjectCompiler:
    """Compile full DSL modules into :class:`ProjectSpec`.

    This compiler resolves scene setup, roles, camera bindings, conditions, and
    references between actions/predicates/callables. Source is parsed from AST and
    never executed.
    """

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
        """Compile a DSL module into validated metadata and IR inputs.

        Args:
            source: Full Python DSL source text.
            source_path: Optional path used for diagnostics and relative file resolution.
            require_code_blocks: Whether top-level setup must be wrapped in
                ``CodeBlock`` / ``AbstractCodeBlock``.
            unboxed_disable_flag: Flag name displayed in code-block warnings.

        Returns:
            Compiled project specification.

        Raises:
            DSLValidationError: If source contains unsupported syntax or invalid DSL.

        Side Effects:
            Emits warnings for ignored DSL fragments and non-fatal misuse.

        Example:
            >>> compiler = ProjectCompiler()
            >>> spec = compiler.compile("game = Game()\\nscene = Scene()\\ngame.set_scene(scene)")
            >>> spec.scene is not None
            True
        """
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
            module = self._expand_top_level_static_control_flow(module)
            self._warn_immutable_dsl_edits(module)

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
                cameras,
                resources,
                sprites,
                scene,
                interface_html,
                interfaces_by_role,
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
            used_role_types = {
                role.role_type
                for role in roles
                if isinstance(role.role_type, str) and role.role_type and role.role_type != "Role"
            }
            for action in actions.values():
                for param in action.params:
                    if param.role_type:
                        used_role_types.add(param.role_type)
            for predicate in predicates.values():
                for param in predicate.params:
                    if param.role_type:
                        used_role_types.add(param.role_type)
            role_schemas = {
                role_type: {
                    field_name: _field_type_label(field_type)
                    for field_name, field_type in fields.items()
                }
                for role_type, fields in compiler.schemas.role_fields.items()
                if role_type in used_role_types
            }
            role_local_schemas = {
                role_type: {
                    field_name: _field_type_label(field_type)
                    for field_name, field_type in fields.items()
                }
                for role_type, fields in compiler.schemas.role_local_fields.items()
                if role_type in used_role_types and fields
            }
            role_local_defaults = {
                role_type: compiler.schemas.role_local_defaults_for(role_type)
                for role_type in role_local_schemas.keys()
            }
            contains_next_turn_call = any(
                _action_contains_next_turn(action) for action in actions.values()
            )
            self._validate_condition_role_ids(rules, roles)
            self._validate_interface_role_ids(interfaces_by_role, roles)
            self._validate_role_bindings(actions, predicates, roles)
            self._validate_camera_bindings(actions, predicates, cameras)
            self._validate_role_cameras(roles, cameras)
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
                role_local_schemas=role_local_schemas,
                role_local_defaults=role_local_defaults,
                globals=globals_spec,
                actors=actors,
                rules=rules,
                tile_map=tile_map,
                cameras=cameras,
                actions=list(actions.values()),
                predicates=list(predicates.values()),
                callables=list(callables.values()),
                resources=resources,
                sprites=sprites,
                scene=scene,
                interface_html=interface_html,
                interfaces_by_role=interfaces_by_role,
                multiplayer=multiplayer,
                roles=roles,
                contains_next_turn_call=contains_next_turn_call,
            )

    def _expand_top_level_static_control_flow(self, module: ast.Module) -> ast.Module:
        env: Dict[str, object] = {}
        max_setup_steps = 20_000
        max_loop_iterations = 10_000
        executed_steps = 0

        def expand_block(statements: List[ast.stmt]) -> List[ast.stmt]:
            out: List[ast.stmt] = []
            for statement in statements:
                out.extend(expand_stmt(statement))
            return out

        def expand_stmt(statement: ast.stmt) -> List[ast.stmt]:
            nonlocal executed_steps
            executed_steps += 1
            if executed_steps > max_setup_steps:
                raise DSLValidationError(
                    "Top-level setup expansion exceeded maximum step budget. "
                    "Simplify setup loops/conditions."
                )

            with dsl_node_context(statement):
                if isinstance(statement, (ast.Import, ast.ImportFrom)):
                    return [statement]

                if isinstance(statement, ast.ClassDef):
                    env.pop(statement.name, None)
                    return [statement]

                if isinstance(statement, ast.FunctionDef):
                    env.pop(statement.name, None)
                    return [statement]

                if isinstance(statement, ast.If):
                    try:
                        condition = _eval_static_expr(statement.test, env)
                    except DSLValidationError as exc:
                        raise DSLValidationError(
                            "Top-level if condition must be statically evaluable."
                        ) from exc
                    selected = statement.body if bool(condition) else statement.orelse
                    return expand_block(selected)

                if isinstance(statement, ast.For):
                    if not isinstance(statement.target, ast.Name):
                        raise DSLValidationError(
                            "Top-level for loop target must be a simple variable name."
                        )
                    try:
                        iterable = _eval_static_expr(statement.iter, env)
                    except DSLValidationError as exc:
                        raise DSLValidationError(
                            "Top-level for iterable must be statically evaluable."
                        ) from exc
                    if isinstance(iterable, range):
                        values = list(iterable)
                    elif isinstance(iterable, (list, tuple)):
                        values = list(iterable)
                    else:
                        raise DSLValidationError(
                            "Top-level for only supports iterating over range(...), list, or tuple."
                        )

                    output: List[ast.stmt] = []
                    had_previous = statement.target.id in env
                    previous_value = env.get(statement.target.id)
                    for idx, value in enumerate(values):
                        if idx >= max_loop_iterations:
                            raise DSLValidationError(
                                "Top-level for exceeded maximum iteration budget."
                            )
                        env[statement.target.id] = copy.deepcopy(value)
                        output.extend(expand_block(statement.body))
                    if statement.orelse:
                        output.extend(expand_block(statement.orelse))
                    if had_previous:
                        env[statement.target.id] = previous_value
                    else:
                        env.pop(statement.target.id, None)
                    return output

                if isinstance(statement, ast.While):
                    output: List[ast.stmt] = []
                    loop_count = 0
                    while True:
                        try:
                            condition = _eval_static_expr(statement.test, env)
                        except DSLValidationError as exc:
                            raise DSLValidationError(
                                "Top-level while condition must be statically evaluable."
                            ) from exc
                        if not bool(condition):
                            break
                        loop_count += 1
                        if loop_count > max_loop_iterations:
                            raise DSLValidationError(
                                "Top-level while exceeded maximum iteration budget."
                            )
                        output.extend(expand_block(statement.body))
                    if statement.orelse:
                        output.extend(expand_block(statement.orelse))
                    return output

                transformed = _substitute_static_names_in_node(statement, env)
                _update_static_setup_env_from_stmt(transformed, env)
                return [transformed]

        expanded = ast.Module(body=expand_block(module.body), type_ignores=module.type_ignores)
        ast.fix_missing_locations(expanded)
        return expanded

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
                    if node.name in IMMUTABLE_DSL_CLASS_NAMES:
                        continue
                    compiler._register_actor_schema(node)

    def _warn_immutable_dsl_edits(self, module: ast.Module) -> None:
        top_level_functions = {
            node.name for node in module.body if isinstance(node, ast.FunctionDef)
        }

        for node in module.body:
            with dsl_node_context(node):
                if isinstance(node, ast.ClassDef) and node.name in IMMUTABLE_DSL_CLASS_NAMES:
                    warnings.warn(
                        format_dsl_diagnostic(
                            f"Ignoring class definition '{node.name}'. "
                            "Engine DSL classes are non-editable.",
                            node=node,
                        ),
                        stacklevel=2,
                    )
                    self._warn_immutable_class_body_edits(node)
                    continue

                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        self._warn_immutable_target_assignment(
                            target=target,
                            value=node.value,
                            function_names=top_level_functions,
                        )
                    continue

                if isinstance(node, ast.AnnAssign):
                    self._warn_immutable_target_assignment(
                        target=node.target,
                        value=node.value,
                        function_names=top_level_functions,
                    )
                    continue

                if isinstance(node, ast.AugAssign):
                    self._warn_immutable_target_assignment(
                        target=node.target,
                        value=None,
                        function_names=top_level_functions,
                    )
                    continue

                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                    self._warn_immutable_setattr_call(
                        call=node.value,
                        function_names=top_level_functions,
                    )

    def _warn_immutable_class_body_edits(self, node: ast.ClassDef) -> None:
        class_name = node.name
        for stmt in node.body:
            with dsl_node_context(stmt):
                if isinstance(stmt, ast.Pass):
                    continue
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(
                    stmt.value.value, str
                ):
                    continue
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    warnings.warn(
                        format_dsl_diagnostic(
                            f"Ignoring method '{stmt.name}' added to immutable DSL class "
                            f"'{class_name}'. Methods cannot be added to engine classes.",
                            node=stmt,
                        ),
                        stacklevel=2,
                    )
                    continue
                if isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                    attr_name: Optional[str] = None
                    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                        attr_name = stmt.target.id
                    elif isinstance(stmt, ast.AugAssign) and isinstance(stmt.target, ast.Name):
                        attr_name = stmt.target.id
                    elif isinstance(stmt, ast.Assign):
                        for target in stmt.targets:
                            if isinstance(target, ast.Name):
                                attr_name = target.id
                                break
                    if attr_name:
                        warnings.warn(
                            format_dsl_diagnostic(
                                f"Ignoring attribute '{attr_name}' added to immutable DSL class "
                                f"'{class_name}'. Define a subclass instead and add fields there.",
                                node=stmt,
                            ),
                            stacklevel=2,
                        )
                        continue
                warnings.warn(
                    format_dsl_diagnostic(
                        f"Ignoring statement inside immutable DSL class '{class_name}'.",
                        node=stmt,
                    ),
                    stacklevel=2,
                )

    def _warn_immutable_target_assignment(
        self,
        *,
        target: ast.AST,
        value: ast.AST | None,
        function_names: set[str],
    ) -> None:
        if not isinstance(target, ast.Attribute) or not isinstance(target.value, ast.Name):
            return
        owner = target.value.id
        if owner not in IMMUTABLE_DSL_CLASS_NAMES:
            return
        attr_name = target.attr
        if self._looks_like_function_assignment(value, function_names):
            warnings.warn(
                format_dsl_diagnostic(
                    f"Ignoring method '{attr_name}' added to immutable DSL class '{owner}'. "
                    "Methods cannot be added to engine classes.",
                    node=target,
                ),
                stacklevel=2,
            )
            return
        warnings.warn(
            format_dsl_diagnostic(
                f"Ignoring attribute '{attr_name}' added to immutable DSL class '{owner}'. "
                "Define a subclass instead and add fields there.",
                node=target,
            ),
            stacklevel=2,
        )

    def _warn_immutable_setattr_call(
        self,
        *,
        call: ast.Call,
        function_names: set[str],
    ) -> None:
        if not isinstance(call.func, ast.Name) or call.func.id not in {"setattr", "delattr"}:
            return
        if len(call.args) < 2:
            return
        owner_node = call.args[0]
        attr_node = call.args[1]
        if not isinstance(owner_node, ast.Name) or owner_node.id not in IMMUTABLE_DSL_CLASS_NAMES:
            return
        if not isinstance(attr_node, ast.Constant) or not isinstance(attr_node.value, str):
            return
        owner = owner_node.id
        attr_name = attr_node.value
        if call.func.id == "setattr":
            value_node = call.args[2] if len(call.args) >= 3 else None
            if self._looks_like_function_assignment(value_node, function_names):
                warnings.warn(
                    format_dsl_diagnostic(
                        f"Ignoring method '{attr_name}' added to immutable DSL class '{owner}'. "
                        "Methods cannot be added to engine classes.",
                        node=call,
                    ),
                    stacklevel=2,
                )
                return
            warnings.warn(
                format_dsl_diagnostic(
                    f"Ignoring attribute '{attr_name}' added to immutable DSL class '{owner}'. "
                    "Define a subclass instead and add fields there.",
                    node=call,
                ),
                stacklevel=2,
            )
            return

        warnings.warn(
            format_dsl_diagnostic(
                f"Ignoring attribute '{attr_name}' mutation on immutable DSL class '{owner}'.",
                node=call,
            ),
            stacklevel=2,
        )

    def _looks_like_function_assignment(
        self,
        value: ast.AST | None,
        function_names: set[str],
    ) -> bool:
        if value is None:
            return False
        if isinstance(value, ast.Name) and value.id in function_names:
            return True
        if isinstance(value, ast.Lambda):
            return True
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id in {"staticmethod", "classmethod"}
            and len(value.args) == 1
            and isinstance(value.args[0], ast.Name)
            and value.args[0].id in function_names
        ):
            return True
        return False

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
                            f"Function '{node.name}' cannot use both @callable and "
                            "@safe_condition/@unsafe_condition decorators."
                        )
                    normalized = self._normalize_callable_function(node, compiler)
                    normalized = self._strip_function_docstring(normalized)
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
                    predicates[node.name] = compiler._compile_predicate(
                        self._strip_function_docstring(node)
                    )
                elif _looks_like_action(node, compiler):
                    normalized_fn = self._strip_condition_decorators(node)
                    normalized_fn = self._strip_function_docstring(normalized_fn)
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
        List[CameraSpec],
        List[ResourceSpec],
        List[SpriteSpec],
        Optional[SceneSpec],
        Optional[str],
        Dict[str, str],
        Optional[MultiplayerSpec],
        List[RoleSpec],
    ]:
        condition_vars: Dict[str, ConditionSpec] = {}
        actors: List[ActorInstanceSpec] = []
        rules: List[RuleSpec] = []
        tile_map: Optional[TileMapSpec] = None
        cameras: List[CameraSpec] = []
        resources_by_name: Dict[str, ResourceSpec] = {}
        sprites: List[SpriteSpec] = []
        scene: Optional[SceneSpec] = None
        interface_html: Optional[str] = None
        interfaces_by_role: Dict[str, str] = {}
        multiplayer: Optional[MultiplayerSpec] = None
        roles_by_id: Dict[str, RoleSpec] = {}
        declared_scene_vars: Dict[str, SceneSpec] = {}
        declared_multiplayer_vars: Dict[str, ast.Call] = {}
        declared_role_vars: Dict[str, ast.Call] = {}
        declared_interface_vars: Dict[str, Tuple[str, Optional[str]]] = {}
        active_scene_vars: set[str] = set()
        declared_actor_vars: Dict[str, ast.Call] = {}
        declared_tile_map_vars: Dict[str, ast.Call] = {}
        declared_camera_vars: Dict[str, CameraSpec] = {}
        declared_resource_vars: Dict[str, ast.Call] = {}
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
        function_nodes: Dict[str, ast.FunctionDef] = {
            node.name: node for node in module.body if isinstance(node, ast.FunctionDef)
        }

        def clear_declared_value(name: str) -> None:
            declared_actor_vars.pop(name, None)
            declared_tile_map_vars.pop(name, None)
            declared_camera_vars.pop(name, None)
            declared_resource_vars.pop(name, None)
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

            if isinstance(condition, ToolConditionSpec) and not condition.tool_docstring.strip():
                action_node = function_nodes.get(action_name)
                action_docstring = _extract_informal_docstring(action_node)
                if action_docstring:
                    condition = replace(condition, tool_docstring=action_docstring)
                else:
                    warning_node = action_node or source_node
                    warnings.warn(
                        format_dsl_diagnostic(
                            "IMPORTANT: MISSING INFORMAL DESCRIPTION. "
                            f"OnToolCall('{condition.name}', Role[...]) bound to action "
                            f"'{action_name}' requires an action docstring to work as intended.",
                            node=warning_node,
                        ),
                        stacklevel=2,
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
                            f"Unsupported decorators on function '{node.name}'. Use "
                            "@safe_condition(...) or @unsafe_condition(...) "
                            "for actions, or @callable for helper functions."
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
                            declared_interface_vars[target.id] = (node.value.value, None)
                        elif isinstance(node.value, ast.Name):
                            source_name = _resolve_name_alias(node.value.id, name_aliases)
                            if source_name in declared_interface_vars:
                                declared_interface_vars[target.id] = declared_interface_vars[source_name]
                            else:
                                declared_interface_vars.pop(target.id, None)
                        else:
                            declared_interface_vars.pop(target.id, None)
                        if (
                            resolved_call is not None
                            and isinstance(resolved_call.func, ast.Name)
                            and resolved_call.func.id == "Interface"
                        ):
                            declared_interface_vars[target.id] = self._parse_interface_constructor(
                                resolved_call,
                                compiler=compiler,
                                source_name=f"Interface variable '{target.id}'",
                            )
                        if resolved_call is not None:
                            if (
                                isinstance(resolved_call.func, ast.Name)
                                and resolved_call.func.id in compiler.schemas.actor_fields
                            ):
                                declared_actor_vars[target.id] = resolved_call
                                declared_tile_map_vars.pop(target.id, None)
                                declared_camera_vars.pop(target.id, None)
                                declared_resource_vars.pop(target.id, None)
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
                                declared_resource_vars.pop(target.id, None)
                                declared_sprite_vars.pop(target.id, None)
                                declared_color_vars.pop(target.id, None)
                                declared_tile_vars.pop(target.id, None)
                                declared_scene_vars.pop(target.id, None)
                                active_scene_vars.discard(target.id)
                            elif (
                                isinstance(resolved_call.func, ast.Name)
                                and resolved_call.func.id == "Resource"
                            ):
                                declared_resource_vars[target.id] = resolved_call
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
                                and resolved_call.func.id == "Sprite"
                            ):
                                declared_sprite_vars[target.id] = resolved_call
                                declared_actor_vars.pop(target.id, None)
                                declared_tile_map_vars.pop(target.id, None)
                                declared_camera_vars.pop(target.id, None)
                                declared_resource_vars.pop(target.id, None)
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
                                declared_resource_vars.pop(target.id, None)
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
                                declared_resource_vars.pop(target.id, None)
                                declared_sprite_vars.pop(target.id, None)
                                declared_color_vars.pop(target.id, None)
                                declared_scene_vars.pop(target.id, None)
                                active_scene_vars.discard(target.id)
                            elif (
                                isinstance(resolved_call.func, ast.Name)
                                and resolved_call.func.id == "Camera"
                            ):
                                declared_camera_vars[target.id] = self._parse_camera_constructor(
                                    resolved_call,
                                    compiler=compiler,
                                )
                                declared_actor_vars.pop(target.id, None)
                                declared_tile_map_vars.pop(target.id, None)
                                declared_sprite_vars.pop(target.id, None)
                                declared_resource_vars.pop(target.id, None)
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
                                declared_resource_vars.pop(target.id, None)
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
                                declared_resource_vars.pop(target.id, None)
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
                                declared_resource_vars.pop(target.id, None)
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
                        resource = self._parse_resource(
                            self._resolve_resource_arg(
                                args,
                                declared_resource_vars=declared_resource_vars,
                            ),
                            kwargs,
                        )
                        resources_by_name[resource.name] = resource
                        continue

                    if method_name == "add_sprite":
                        sprites.append(
                            self._parse_sprite(
                                args,
                                kwargs,
                                compiler,
                                declared_sprite_vars=declared_sprite_vars,
                                declared_resource_vars=declared_resource_vars,
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
                        raise DSLValidationError(
                            "game.set_camera(...) was removed. Use Camera(...) + scene.add_camera(...)."
                        )

                    if method_name == "add_camera":
                        raise DSLValidationError(
                            "game.add_camera(...) is not supported. Use scene.add_camera(...)."
                        )

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

                camera_method = _as_owner_method_call(resolved_call, owner)
                if camera_method is not None and owner in declared_camera_vars:
                    camera_method_name, camera_args, camera_kwargs = camera_method
                    self._apply_declared_camera_method_call(
                        owner=owner,
                        method_name=camera_method_name,
                        args=camera_args,
                        kwargs=camera_kwargs,
                        declared_camera_vars=declared_camera_vars,
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
                    raise DSLValidationError(
                        "scene.set_camera(...) was removed. Use scene.add_camera(camera)."
                    )

                if scene_method_name == "add_camera":
                    if scene_kwargs:
                        raise DSLValidationError(
                            "scene.add_camera(...) does not accept keyword args."
                        )
                    if len(scene_args) != 1:
                        raise DSLValidationError("scene.add_camera(...) expects one argument.")
                    camera_spec = self._resolve_camera_binding_arg(
                        scene_args[0],
                        declared_camera_vars=declared_camera_vars,
                        compiler=compiler,
                    )
                    if any(existing.name == camera_spec.name for existing in cameras):
                        raise DSLValidationError(
                            f"Camera '{camera_spec.name}' is already added to the scene."
                        )
                    cameras.append(copy.deepcopy(camera_spec))
                    continue

                if scene_method_name == "set_interface":
                    if scene_kwargs:
                        raise DSLValidationError(
                            "scene.set_interface(...) does not accept keyword args."
                        )
                    if len(scene_args) not in {1, 2}:
                        raise DSLValidationError(
                            "scene.set_interface(...) expects html and optional role selector."
                        )
                    html, role_id = self._resolve_interface_arg(
                        scene_args[0],
                        declared_interface_vars,
                        compiler=compiler,
                        source_name="scene.set_interface(...) first argument",
                    )
                    if len(scene_args) == 1 and role_id is None:
                        interface_html = html
                    else:
                        if len(scene_args) == 2:
                            if role_id is not None:
                                raise DSLValidationError(
                                    "scene.set_interface(...) role is provided twice. "
                                    "Either use scene.set_interface(Interface(..., Role[...])) "
                                    "or scene.set_interface(html, Role[...])."
                                )
                            role_id = self._parse_role_selector_id(
                                scene_args[1],
                                compiler=compiler,
                                source_name="scene.set_interface role",
                                allow_plain_string=True,
                            )
                        if role_id is None:
                            raise DSLValidationError(
                                "scene.set_interface(...) role selector is required when the "
                                "first argument is not a plain html string."
                            )
                        interfaces_by_role[role_id] = html
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
            cameras,
            list(resources_by_name.values()),
            sprites,
            scene,
            interface_html,
            interfaces_by_role,
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

    def _apply_declared_camera_method_call(
        self,
        owner: str,
        method_name: str,
        args: List[ast.AST],
        kwargs: Dict[str, ast.AST],
        declared_camera_vars: Dict[str, CameraSpec],
    ) -> None:
        camera = declared_camera_vars.get(owner)
        if camera is None:
            raise DSLValidationError(
                f"Unknown camera variable '{owner}'."
            )

        if method_name == "follow":
            if kwargs:
                raise DSLValidationError(f"{owner}.follow(...) does not accept keyword args.")
            if len(args) != 1:
                raise DSLValidationError(f"{owner}.follow(...) expects one target uid.")
            target_uid = _expect_string(args[0], "camera follow target uid")
            declared_camera_vars[owner] = replace(
                camera,
                target_uid=target_uid,
                offset_x=0.0,
                offset_y=0.0,
            )
            return

        if method_name == "detach":
            if kwargs or args:
                raise DSLValidationError(f"{owner}.detach(...) does not accept arguments.")
            declared_camera_vars[owner] = replace(
                camera,
                target_uid=None,
                offset_x=0.0,
                offset_y=0.0,
            )
            return

        if method_name == "translate":
            if kwargs:
                raise DSLValidationError(f"{owner}.translate(...) does not accept keyword args.")
            if len(args) != 2:
                raise DSLValidationError(f"{owner}.translate(...) expects dx and dy.")
            dx = _expect_number(args[0], "camera translate dx")
            dy = _expect_number(args[1], "camera translate dy")
            if camera.target_uid:
                declared_camera_vars[owner] = replace(
                    camera,
                    offset_x=camera.offset_x + dx,
                    offset_y=camera.offset_y + dy,
                )
            else:
                declared_camera_vars[owner] = replace(
                    camera,
                    x=camera.x + dx,
                    y=camera.y + dy,
                )
            return

        raise DSLValidationError(
            f"Unsupported camera method '{method_name}'. "
            "Only follow/detach/translate are allowed in setup."
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

    def _resolve_resource_arg(
        self,
        args: List[ast.AST],
        *,
        declared_resource_vars: Dict[str, ast.Call],
    ) -> List[ast.AST]:
        if len(args) != 1:
            return args
        if not isinstance(args[0], ast.Name):
            return args
        resource_var = args[0].id
        if resource_var not in declared_resource_vars:
            return args
        return [declared_resource_vars[resource_var]]

    def _resolve_camera_binding_arg(
        self,
        node: ast.AST,
        declared_camera_vars: Dict[str, CameraSpec],
        compiler: DSLCompiler,
    ) -> CameraSpec:
        if isinstance(node, ast.Name):
            if node.id not in declared_camera_vars:
                raise DSLValidationError(
                    f"Unknown camera variable '{node.id}' in scene.add_camera(...)."
                )
            return declared_camera_vars[node.id]
        if isinstance(node, ast.Call):
            return self._parse_camera_constructor(node, compiler=compiler)
        raise DSLValidationError(
            "scene.add_camera(...) expects Camera(...) or a camera variable."
        )

    def _resolve_interface_arg(
        self,
        node: ast.AST,
        declared_interface_vars: Dict[str, Tuple[str, Optional[str]]],
        *,
        compiler: DSLCompiler,
        source_name: str,
    ) -> Tuple[str, Optional[str]]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value, None
        if isinstance(node, ast.Name):
            if node.id not in declared_interface_vars:
                raise DSLValidationError(
                    f"Unknown interface variable '{node.id}' in set_interface(...)."
                )
            return declared_interface_vars[node.id]
        if isinstance(node, ast.Call):
            return self._parse_interface_constructor(
                node,
                compiler=compiler,
                source_name=source_name,
            )
        raise DSLValidationError(
            "set_interface(...) expects HTML string, Interface(...), or a variable bound to one."
        )

    def _parse_interface_constructor(
        self,
        node: ast.Call,
        *,
        compiler: DSLCompiler,
        source_name: str,
    ) -> Tuple[str, Optional[str]]:
        if not isinstance(node.func, ast.Name) or node.func.id != "Interface":
            raise DSLValidationError(
                f"{source_name} must be Interface(...), an html string, or an interface variable."
            )
        if any(keyword.arg is None for keyword in node.keywords):
            raise DSLValidationError("Interface(...) does not support **kwargs expansion.")
        kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg is not None}
        allowed = {"role", "from_file"}
        unexpected = sorted(set(kwargs.keys()) - allowed)
        if unexpected:
            raise DSLValidationError(
                f"Interface(...) received unsupported arguments: {unexpected}."
            )
        if len(node.args) not in {1, 2}:
            raise DSLValidationError(
                "Interface(...) expects source path/html and optional role selector."
            )
        if len(node.args) == 2 and "role" in kwargs:
            raise DSLValidationError(
                "Interface(...) role must be provided once (positional or keyword)."
            )

        source = _expect_string(node.args[0], "Interface source")
        from_file = _expect_bool_or_default(
            kwargs.get("from_file"),
            "Interface from_file",
            True,
        )
        html = self._load_interface_html_from_file(source) if from_file else source

        role_node: Optional[ast.AST]
        if len(node.args) == 2:
            role_node = node.args[1]
        else:
            role_node = kwargs.get("role")
        role_id: Optional[str] = None
        if role_node is not None:
            role_id = self._parse_role_selector_id(
                role_node,
                compiler=compiler,
                source_name="Interface role",
                allow_plain_string=True,
            )
        return html, role_id

    def _load_interface_html_from_file(self, path_value: str) -> str:
        raw_path = path_value.strip()
        if not raw_path:
            raise DSLValidationError("Interface(...) file path cannot be empty.")

        candidate = Path(raw_path)
        resolved = candidate if candidate.is_absolute() else (self._source_dir / candidate)

        try:
            return resolved.read_text(encoding="utf-8")
        except OSError as exc:
            raise DSLValidationError(
                f"Cannot read interface file '{raw_path}': {exc}."
            ) from exc

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
        role_local_fields = compiler.schemas.role_local_fields.get(role_type, {})
        local_arg_names = sorted(name for name in role_local_fields.keys() if name in kwargs)
        if local_arg_names:
            raise DSLValidationError(
                f"{role_type}(...) local fields {local_arg_names} are client-owned Local[...] "
                "and cannot be provided in add_role(...). Configure them on the client side."
            )
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

    def _validate_interface_role_ids(
        self,
        interfaces_by_role: Dict[str, str],
        roles: List[RoleSpec],
    ) -> None:
        if not interfaces_by_role:
            return
        declared = {role.id for role in roles}
        for role_id in interfaces_by_role.keys():
            if role_id in declared:
                continue
            if not declared:
                raise DSLValidationError(
                    f"scene.set_interface(..., Role['{role_id}']) references role id '{role_id}', "
                    "but no roles were declared via game.add_role(...)."
                )
            declared_list = ", ".join(sorted(declared))
            raise DSLValidationError(
                f"scene.set_interface(..., Role['{role_id}']) references unknown role id '{role_id}'. "
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

    def _validate_camera_bindings(
        self,
        actions: Dict[str, ActionIR],
        predicates: Dict[str, PredicateIR],
        cameras: List[CameraSpec],
    ) -> None:
        declared_names = {camera.name for camera in cameras}
        declared_sorted = sorted(declared_names)

        def validate_param(owner: str, param: ParamBinding) -> None:
            if param.kind != BindingKind.CAMERA:
                return
            selector = param.camera_selector
            camera_name = selector.name if selector is not None else ""
            if not camera_name:
                raise DSLValidationError(
                    f"{owner} camera binding '{param.name}' is missing a camera name."
                )
            if camera_name in declared_names:
                return
            if not declared_names:
                raise DSLValidationError(
                    f"{owner} camera binding '{param.name}' references camera '{camera_name}', "
                    "but no camera was added via scene.add_camera(...)."
                )
            raise DSLValidationError(
                f"{owner} camera binding '{param.name}' references unknown camera '{camera_name}'. "
                f"Declared cameras: {', '.join(declared_sorted)}."
            )

        for action in actions.values():
            for param in action.params:
                validate_param(f"Action '{action.name}'", param)
        for predicate in predicates.values():
            for param in predicate.params:
                validate_param(f"Predicate '{predicate.name}'", param)

    def _validate_role_cameras(
        self,
        roles: List[RoleSpec],
        cameras: List[CameraSpec],
    ) -> None:
        role_by_id = {role.id: role for role in roles}
        camera_by_name: Dict[str, CameraSpec] = {}
        for camera in cameras:
            if camera.name in camera_by_name:
                raise DSLValidationError(
                    f"Duplicate camera name '{camera.name}' is not allowed."
                )
            camera_by_name[camera.name] = camera
            if camera.role_id not in role_by_id:
                if not role_by_id:
                    raise DSLValidationError(
                        f"Camera '{camera.name}' references role '{camera.role_id}', "
                        "but no roles were declared via game.add_role(...)."
                    )
                declared_roles = ", ".join(sorted(role_by_id.keys()))
                raise DSLValidationError(
                    f"Camera '{camera.name}' references unknown role '{camera.role_id}'. "
                    f"Declared roles: {declared_roles}."
                )

        cameras_by_role: Dict[str, List[CameraSpec]] = {}
        for camera in cameras:
            cameras_by_role.setdefault(camera.role_id, []).append(camera)

        for role in roles:
            if role.kind != RoleKind.HUMAN:
                continue
            if role.id in cameras_by_role:
                continue
            warnings.warn(
                format_dsl_diagnostic(
                    "Human role '{role_id}' has no camera. Add one via "
                    "scene.add_camera(Camera(..., Role['{role_id}'])).".format(
                        role_id=role.id
                    ),
                    node=None,
                ),
                stacklevel=2,
            )

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
        if field_name == "sprite":
            return self._parse_sprite_name_selector(
                value_node,
                source_name=f"{source_name} sprite",
            )
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
            if (
                isinstance(decorator.func, ast.Name)
                and decorator.func.id in CONDITION_DECORATOR_NAMES
            ):
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
                and decorator.func.id in CONDITION_DECORATOR_NAMES
            ):
                removed = True
                continue
            stripped.append(decorator)

        if not removed:
            return fn
        cloned = copy.deepcopy(fn)
        cloned.decorator_list = stripped
        return cloned

    def _strip_function_docstring(self, fn: ast.FunctionDef) -> ast.FunctionDef:
        if not fn.body:
            return fn
        first = fn.body[0]
        if not (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            return fn
        cloned = copy.deepcopy(fn)
        cloned.body = cloned.body[1:]
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
                        f"Unsupported decorator on action '{node.name}'. "
                        "Use @safe_condition(...) or @unsafe_condition(...)."
                    )
                if (
                    isinstance(decorator.func, ast.Name)
                    and decorator.func.id in CONDITION_DECORATOR_NAMES
                ):
                    if len(decorator.args) != 1 or decorator.keywords:
                        raise DSLValidationError(
                            f"@{decorator.func.id}(...) expects exactly one positional "
                            "condition argument."
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
                    condition = self._resolve_condition_arg(
                        resolved_condition_arg, condition_vars, compiler, predicates
                    )
                    self._validate_condition_decorator_scope(
                        decorator_name=decorator.func.id,
                        condition=condition,
                        action_name=node.name,
                        node=decorator,
                    )
                    conditions.append(condition)
                    continue

                raise DSLValidationError(
                    f"Unsupported decorator on action '{node.name}'. "
                    "Use @safe_condition(...) or @unsafe_condition(...)."
                )
        return conditions

    def _validate_condition_decorator_scope(
        self,
        *,
        decorator_name: str,
        condition: ConditionSpec,
        action_name: str,
        node: ast.AST,
    ) -> None:
        if decorator_name not in {"safe_condition", "unsafe_condition"}:
            return

        local_safe = isinstance(condition, (CollisionConditionSpec, LogicalConditionSpec))
        remote_unsafe = isinstance(
            condition,
            (
                KeyboardConditionSpec,
                MouseConditionSpec,
                ToolConditionSpec,
                ButtonConditionSpec,
            ),
        )

        if decorator_name == "safe_condition" and not local_safe:
            condition_name = self._condition_decorator_label(condition)
            raise DSLValidationError(
                f"@safe_condition on action '{action_name}' cannot wrap {condition_name}. "
                f"{condition_name} is client-event-driven (remote). "
                "Fix: replace @safe_condition(...) with @unsafe_condition(...).",
                node=node,
            )

        if decorator_name == "unsafe_condition" and not remote_unsafe:
            condition_name = self._condition_decorator_label(condition)
            raise DSLValidationError(
                f"@unsafe_condition on action '{action_name}' cannot wrap {condition_name}. "
                f"{condition_name} is server-evaluated (local). "
                "Fix: replace @unsafe_condition(...) with @safe_condition(...).",
                node=node,
            )

    def _condition_decorator_label(self, condition: ConditionSpec) -> str:
        if isinstance(condition, KeyboardConditionSpec):
            return "KeyboardCondition"
        if isinstance(condition, MouseConditionSpec):
            return "MouseCondition"
        if isinstance(condition, ToolConditionSpec):
            return "OnToolCall"
        if isinstance(condition, ButtonConditionSpec):
            return "OnButton"
        if isinstance(condition, LogicalConditionSpec):
            return "OnLogicalCondition"
        if isinstance(condition, CollisionConditionSpec):
            if condition.mode == CollisionMode.CONTACT:
                return "OnContact"
            return "OnOverlap"
        return "condition"

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
                        "KeyboardCondition.<phase>(...) expects key and role selector."
                    )
                role_id = (
                    self._parse_role_selector_id(
                        node.args[1],
                        compiler=compiler,
                        source_name="KeyboardCondition role",
                        allow_plain_string=True,
                    )
                    if len(node.args) == 2
                    else None
                )
                if len(node.args) == 2 and "id" in kwargs:
                    raise DSLValidationError(
                        "KeyboardCondition.<phase>(...) role id must be provided once."
                    )
                if role_id is None and "id" in kwargs:
                    role_id = _expect_string(kwargs["id"], "condition role id")
                if role_id is None:
                    raise DSLValidationError(
                        "KeyboardCondition.<phase>(...) requires role id. "
                        "Use Role[\"<role_id>\"] or id=\"<role_id>\" and declare it with game.add_role(Role(...))."
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
                        "MouseCondition.<phase>(...) accepts button and role selector."
                    )
                button = "left"
                role_id: Optional[str] = None
                if len(node.args) == 1:
                    try:
                        role_id = self._parse_role_selector_id(
                            node.args[0],
                            compiler=compiler,
                            source_name="MouseCondition role",
                            allow_plain_string=False,
                        )
                    except DSLValidationError:
                        button = _expect_string(node.args[0], "mouse button")
                elif len(node.args) == 2:
                    button = _expect_string(node.args[0], "mouse button")
                    role_id = self._parse_role_selector_id(
                        node.args[1],
                        compiler=compiler,
                        source_name="MouseCondition role",
                        allow_plain_string=True,
                    )
                if len(node.args) == 2 and "id" in kwargs:
                    raise DSLValidationError(
                        "MouseCondition.<phase>(...) role id must be provided once."
                    )
                if role_id is None and "id" in kwargs:
                    role_id = _expect_string(kwargs["id"], "condition role id")
                if role_id is None:
                    raise DSLValidationError(
                        "MouseCondition.<phase>(...) requires role id. "
                        "Use Role[\"<role_id>\"] or id=\"<role_id>\" and declare it with game.add_role(Role(...))."
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
            if any(keyword.arg is None for keyword in node.keywords):
                raise DSLValidationError(
                    "OnToolCall(...) does not support **kwargs expansion."
                )
            kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg is not None}
            unexpected = sorted(set(kwargs.keys()) - {"id"})
            if unexpected:
                raise DSLValidationError(
                    "OnToolCall(...) only accepts keyword 'id'."
                )
            if (
                len(node.args) == 2
                and "id" in kwargs
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
            ):
                raise DSLValidationError(
                    "OnToolCall(...) only positional argument is tool name. "
                    "Provide action docstring for tool description."
                )
            if len(node.args) not in {1, 2}:
                raise DSLValidationError(
                    "OnToolCall(...) expects tool name and role selector."
                )
            role_id = (
                self._parse_role_selector_id(
                    node.args[1],
                    compiler=compiler,
                    source_name="OnToolCall role",
                    allow_plain_string=True,
                )
                if len(node.args) == 2
                else None
            )
            if len(node.args) == 2 and "id" in kwargs:
                raise DSLValidationError(
                    "OnToolCall(...) role id must be provided once."
                )
            if role_id is None and "id" not in kwargs:
                raise DSLValidationError(
                    "OnToolCall(...) requires role id. "
                    "Use Role[\"<role_id>\"] or id=\"<role_id>\" and declare it with game.add_role(Role(...))."
                )
            if role_id is None:
                role_id = _expect_string(kwargs["id"], "condition role id")
            return ToolConditionSpec(
                name=_expect_string(node.args[0], "tool name"),
                tool_docstring="",
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

        sprite = self._parse_sprite_name_selector(
            kwargs["sprite"],
            source_name="Tile(...) sprite",
        )
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

    def _parse_camera_constructor(
        self,
        node: ast.AST,
        *,
        compiler: DSLCompiler,
    ) -> CameraSpec:
        if not isinstance(node, ast.Call):
            raise DSLValidationError("Camera declaration expects Camera(...).")
        if not isinstance(node.func, ast.Name) or node.func.id != "Camera":
            raise DSLValidationError("Camera declaration expects Camera(...).")
        if len(node.args) != 2:
            raise DSLValidationError(
                "Camera(...) expects exactly two positional args: name and role selector."
            )

        kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg is not None}
        allowed = {"x", "y", "width", "height"}
        unexpected = sorted(set(kwargs.keys()) - allowed)
        if unexpected:
            raise DSLValidationError(
                f"Camera(...) received unsupported arguments: {unexpected}"
            )

        name = _expect_string(node.args[0], "camera name")
        if not name:
            raise DSLValidationError("Camera name must be a non-empty string.")
        role_id = self._parse_camera_role_selector(node.args[1], compiler)
        x = _expect_number_or_default(kwargs.get("x"), "camera x", 0.0)
        y = _expect_number_or_default(kwargs.get("y"), "camera y", 0.0)

        width: int | None = None
        if "width" in kwargs:
            width = _expect_int(kwargs["width"], "camera width")
            if width <= 0:
                raise DSLValidationError("Camera width must be > 0.")

        height: int | None = None
        if "height" in kwargs:
            height = _expect_int(kwargs["height"], "camera height")
            if height <= 0:
                raise DSLValidationError("Camera height must be > 0.")

        return CameraSpec(
            name=name,
            role_id=role_id,
            x=x,
            y=y,
            width=width,
            height=height,
            target_uid=None,
            offset_x=0.0,
            offset_y=0.0,
        )

    def _parse_camera_role_selector(
        self,
        node: ast.AST,
        compiler: DSLCompiler,
    ) -> str:
        return self._parse_role_selector_id(
            node,
            compiler=compiler,
            source_name="Camera role selector",
            allow_plain_string=True,
        )

    def _parse_role_selector_id(
        self,
        node: ast.AST,
        *,
        compiler: DSLCompiler,
        source_name: str,
        allow_plain_string: bool,
    ) -> str:
        if allow_plain_string and isinstance(node, ast.Constant) and isinstance(node.value, str):
            if not node.value:
                raise DSLValidationError(f"{source_name} must be non-empty.")
            return node.value

        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            owner = node.value.id
            if owner != "Role" and owner not in compiler.schemas.role_fields:
                raise DSLValidationError(
                    f"{source_name} must use Role[\"id\"] or RoleType[\"id\"]."
                )
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, int):
                raise DSLValidationError(
                    f"{source_name} does not support index selectors; use Role[\"id\"]."
                )
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                if not node.slice.value:
                    raise DSLValidationError(f"{source_name} must be non-empty.")
                return node.slice.value

        if allow_plain_string:
            raise DSLValidationError(
                f"{source_name} must be role id string, Role[\"id\"], or RoleType[\"id\"]."
            )
        raise DSLValidationError(
            f"{source_name} must be Role[\"id\"] or RoleType[\"id\"]."
        )

    def _parse_resource_name_selector(
        self,
        node: ast.AST,
        *,
        source_name: str,
        declared_resource_vars: Dict[str, ast.Call] | None = None,
    ) -> str:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            if declared_resource_vars is not None and node.id in declared_resource_vars:
                return self._parse_resource_name_selector(
                    declared_resource_vars[node.id],
                    source_name=source_name,
                    declared_resource_vars=declared_resource_vars,
                )
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            if node.value.id == "Resource":
                return _expect_string(node.slice, f"{source_name} resource name")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Resource":
            if node.keywords:
                raise DSLValidationError("Resource(...) does not accept keyword args.")
            if len(node.args) != 2:
                raise DSLValidationError("Resource(...) expects name and path arguments.")
            return _expect_string(node.args[0], f"{source_name} resource name")
        raise DSLValidationError(
            f"{source_name} must be resource name string or Resource[\"name\"]."
        )

    def _parse_sprite_name_selector(
        self,
        node: ast.AST,
        *,
        source_name: str,
    ) -> str:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            if node.value.id == "Sprite":
                return _expect_string(node.slice, f"{source_name} sprite name")
        raise DSLValidationError(
            f"{source_name} must be sprite name string or Sprite[\"name\"]."
        )

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
        if len(args) == 2:
            return ResourceSpec(
                name=_expect_string(args[0], "resource name"),
                path=_expect_string(args[1], "resource path"),
            )
        if len(args) == 1:
            resource_node = args[0]
            if not isinstance(resource_node, ast.Call):
                raise DSLValidationError(
                    "add_resource(...) expects Resource(...) or name/path arguments."
                )
            if not isinstance(resource_node.func, ast.Name) or resource_node.func.id != "Resource":
                raise DSLValidationError(
                    "add_resource(...) expects Resource(...) or name/path arguments."
                )
            if resource_node.keywords:
                raise DSLValidationError("Resource(...) does not accept keyword args.")
            if len(resource_node.args) != 2:
                raise DSLValidationError("Resource(...) expects name and path arguments.")
            return ResourceSpec(
                name=_expect_string(resource_node.args[0], "resource name"),
                path=_expect_string(resource_node.args[1], "resource path"),
            )
        raise DSLValidationError(
            "add_resource(...) expects Resource(...) or name/path arguments."
        )

    def _parse_sprite(
        self,
        args: List[ast.AST],
        kwargs: Dict[str, ast.AST],
        compiler: DSLCompiler,
        declared_sprite_vars: Dict[str, ast.Call] | None = None,
        declared_resource_vars: Dict[str, ast.Call] | None = None,
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
            declared_resource_vars=declared_resource_vars,
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
        declared_resource_vars: Dict[str, ast.Call] | None = None,
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
            resource=self._parse_resource_name_selector(
                sprite_kwargs["resource"],
                source_name=f"{source_name} resource",
                declared_resource_vars=declared_resource_vars,
            ),
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
