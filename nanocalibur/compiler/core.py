import ast
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from nanocalibur.errors import DSLValidationError, dsl_node_context, dsl_source_context
from nanocalibur.ir import (
    ActionIR,
    ActorSelector,
    Assign,
    Attr,
    Binary,
    BindingKind,
    CallableIR,
    CallExpr,
    CallStmt,
    Continue,
    Const,
    Expr,
    For,
    If,
    ListExpr,
    ObjectExpr,
    ParamBinding,
    PredicateIR,
    Range,
    CameraSelector,
    RoleSelector,
    SubscriptExpr,
    Unary,
    Var,
    While,
    Yield,
)
from nanocalibur.schema_registry import SchemaRegistry
from nanocalibur.typesys import DictType, FieldType, ListType, Prim, PrimType

from .constants import (
    CALLABLE_EXPR_PREFIX,
    BASE_ACTOR_DEFAULT_OVERRIDES,
    BASE_ACTOR_FIELDS,
    BASE_ACTOR_NO_DEFAULT_FIELDS,
    _ALLOWED_BIN,
    _ALLOWED_BOOL,
    _ALLOWED_CMP,
    _ALLOWED_UNARY,
    _PRIM_NAMES,
)
from .helpers import (
    _expect_name,
    _format_syntax_error,
    _is_docstring_expr,
    _parse_actor_link_literal_value,
    _parse_global_binding_name,
    _parse_int_literal,
    _parse_typed_literal_value,
)


@dataclass
class ActionScope:
    defined_names: Set[str]
    actor_var_types: Dict[str, str]
    actor_list_var_types: Dict[str, Optional[str]]
    role_var_types: Dict[str, str]
    camera_vars: Set[str]
    scene_vars: Set[str]
    tick_vars: Set[str]
    spawn_actor_templates: Dict[str, tuple[str, Expr, Expr]]


class DSLCompiler:
    def __init__(self, global_actor_types: Optional[Dict[str, Optional[str]]] = None):
        """Create a DSL compiler for action/predicate source snippets."""
        self.schemas = SchemaRegistry()
        self.global_actor_types: Dict[str, Optional[str]] = dict(global_actor_types or {})
        self.callable_signatures: Dict[str, int] = {}

    def set_callable_signatures(self, signatures: Dict[str, int]) -> None:
        """Register callable helper signatures available in expressions."""
        self.callable_signatures = dict(signatures)

    def compile(
        self,
        source: str,
        global_actor_types: Optional[Dict[str, Optional[str]]] = None,
    ) -> List[ActionIR]:
        """Compile DSL source into action IR nodes.

        This pass also registers actor schemas declared in the same source.
        """
        # Reset per-compilation state for deterministic behavior across calls.
        self.schemas = SchemaRegistry()
        if global_actor_types is not None:
            self.global_actor_types = dict(global_actor_types)

        with dsl_source_context(source):
            try:
                module = ast.parse(source)
            except SyntaxError as exc:
                raise DSLValidationError(_format_syntax_error(exc, source)) from exc

            actions: List[ActionIR] = []

            # Pass 1: collect schemas so action bindings can reference them.
            for node in module.body:
                with dsl_node_context(node):
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
                with dsl_node_context(node):
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
        with dsl_node_context(node):
            if node.decorator_list:
                raise DSLValidationError("Decorators are not allowed on actor schemas.")

            if len(node.bases) != 1:
                raise DSLValidationError(
                    "Schema class must inherit from Actor, ActorModel, or Role."
                )

            base = node.bases[0]
            if not isinstance(base, ast.Name):
                raise DSLValidationError(
                    "Schema class must inherit from Actor, ActorModel, or Role."
                )

            if base.id in {"Actor", "ActorModel"}:
                fields: Dict[str, FieldType] = dict(BASE_ACTOR_FIELDS)
                for stmt in node.body:
                    with dsl_node_context(stmt):
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
                            raise DSLValidationError(
                                "Actor schema field target must be a name."
                            )

                        field_name = stmt.target.id
                        if field_name in fields and field_name not in BASE_ACTOR_FIELDS:
                            raise DSLValidationError(
                                f"Duplicate field '{field_name}' in actor '{node.name}'."
                            )
                        fields[field_name] = self._parse_field_type(stmt.annotation)

                self.schemas.register_actor(node.name, fields)
                return

            if base.id == "Role":
                fields: Dict[str, FieldType] = {}
                reserved = {"id", "required", "kind"}
                for stmt in node.body:
                    with dsl_node_context(stmt):
                        if isinstance(stmt, ast.Pass):
                            continue
                        if not isinstance(stmt, ast.AnnAssign):
                            raise DSLValidationError(
                                "Role schema body can only contain annotated fields."
                            )
                        if stmt.value is not None:
                            raise DSLValidationError(
                                "Role schema fields cannot have default values."
                            )
                        if not isinstance(stmt.target, ast.Name):
                            raise DSLValidationError(
                                "Role schema field target must be a name."
                            )
                        field_name = stmt.target.id
                        if field_name in reserved:
                            raise DSLValidationError(
                                f"Role schema field '{field_name}' is reserved."
                            )
                        if field_name in fields:
                            raise DSLValidationError(
                                f"Duplicate field '{field_name}' in role '{node.name}'."
                            )
                        fields[field_name] = self._parse_field_type(stmt.annotation)
                self.schemas.register_role(node.name, fields)
                return

            raise DSLValidationError("Only Actor, ActorModel, or Role subclasses are allowed.")

    def _parse_field_type(self, annotation: ast.AST) -> FieldType:
        return self._parse_container_field_type(annotation)

    def _parse_container_field_type(self, node: ast.AST) -> FieldType:
        if isinstance(node, ast.Name) and node.id in _PRIM_NAMES:
            return PrimType(_PRIM_NAMES[node.id])

        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            container_name = node.value.id
            if container_name in {"List", "list"}:
                return ListType(self._parse_container_field_type(node.slice))
            if container_name in {"Dict", "dict"}:
                if not isinstance(node.slice, ast.Tuple) or len(node.slice.elts) != 2:
                    raise DSLValidationError(
                        "Dict[...] field types must be declared as Dict[str, value_type]."
                    )
                key_type = self._parse_container_field_type(node.slice.elts[0])
                if not isinstance(key_type, PrimType) or key_type.prim != Prim.STR:
                    raise DSLValidationError(
                        "Dict[...] keys must be str in field type declarations."
                    )
                value_type = self._parse_container_field_type(node.slice.elts[1])
                return DictType(key=key_type, value=value_type)

        raise DSLValidationError(
            "Field type must be int, float, str, bool, List[...], or Dict[str, ...]."
        )

    def _compile_action(self, fn: ast.FunctionDef) -> ActionIR:
        with dsl_node_context(fn):
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
                with dsl_node_context(arg):
                    if arg.annotation is None:
                        raise DSLValidationError("All action parameters must have bindings.")
                    params.append(self._parse_binding(arg))

            actor_var_types: Dict[str, str] = {}
            actor_list_var_types: Dict[str, Optional[str]] = {}
            role_var_types: Dict[str, str] = {}
            camera_vars: Set[str] = set()
            for param in params:
                if param.kind == BindingKind.ACTOR and param.actor_type is not None:
                    actor_var_types[param.name] = param.actor_type
                if param.kind == BindingKind.ACTOR_LIST:
                    actor_list_var_types[param.name] = param.actor_list_type
                if param.kind == BindingKind.ROLE and param.role_type is not None:
                    role_var_types[param.name] = param.role_type
                if param.kind == BindingKind.CAMERA:
                    camera_vars.add(param.name)
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
                role_var_types=role_var_types,
                camera_vars=camera_vars,
                scene_vars={p.name for p in params if p.kind == BindingKind.SCENE},
                tick_vars={p.name for p in params if p.kind == BindingKind.TICK},
                spawn_actor_templates={},
            )
            body = []
            for stmt in fn.body:
                compiled = self._compile_stmt(stmt, scope, loop_depth=0)
                if compiled is not None:
                    body.append(compiled)
            return ActionIR(fn.name, params, body)

    def _compile_predicate(self, fn: ast.FunctionDef) -> PredicateIR:
        with dsl_node_context(fn):
            if fn.decorator_list:
                raise DSLValidationError("Decorators are not allowed on predicate functions.")
            if fn.args.vararg is not None or fn.args.kwarg is not None:
                raise DSLValidationError("Variadic predicate parameters are not allowed.")
            if fn.args.posonlyargs or fn.args.kwonlyargs or fn.args.kw_defaults:
                raise DSLValidationError("Predicate must use regular positional parameters.")
            if not (
                isinstance(fn.returns, ast.Name)
                and fn.returns.id == "bool"
            ):
                raise DSLValidationError("Predicate function must have return type 'bool'.")

            params: List[ParamBinding] = []
            for arg in fn.args.args:
                with dsl_node_context(arg):
                    if arg.annotation is None:
                        raise DSLValidationError(
                            "All predicate parameters must have bindings."
                        )
                    params.append(self._parse_binding(arg))

            actor_var_types: Dict[str, str] = {}
            actor_list_var_types: Dict[str, Optional[str]] = {}
            role_var_types: Dict[str, str] = {}
            camera_vars: Set[str] = set()
            for param in params:
                if param.kind == BindingKind.ACTOR and param.actor_type is not None:
                    actor_var_types[param.name] = param.actor_type
                if param.kind == BindingKind.ACTOR_LIST:
                    actor_list_var_types[param.name] = param.actor_list_type
                if param.kind == BindingKind.ROLE and param.role_type is not None:
                    role_var_types[param.name] = param.role_type
                if param.kind == BindingKind.CAMERA:
                    camera_vars.add(param.name)
                if (
                    param.kind == BindingKind.GLOBAL
                    and param.global_name in self.global_actor_types
                    and self.global_actor_types[param.global_name] is not None
                ):
                    actor_var_types[param.name] = self.global_actor_types[param.global_name]

            anchor_param = next(
                (param for param in params if param.kind == BindingKind.ACTOR),
                None,
            )
            if anchor_param is None:
                raise DSLValidationError(
                    "Logical predicate must declare at least one actor binding parameter."
                )

            if len(fn.body) != 1 or not isinstance(fn.body[0], ast.Return):
                raise DSLValidationError(
                    "Predicate body must be a single return statement."
                )
            if fn.body[0].value is None:
                raise DSLValidationError("Predicate return statement must return a value.")

            scope = ActionScope(
                defined_names={p.name for p in params},
                actor_var_types=actor_var_types,
                actor_list_var_types=actor_list_var_types,
                role_var_types=role_var_types,
                camera_vars=camera_vars,
                scene_vars={p.name for p in params if p.kind == BindingKind.SCENE},
                tick_vars={p.name for p in params if p.kind == BindingKind.TICK},
                spawn_actor_templates={},
            )
            expr = self._compile_expr(fn.body[0].value, scope, allow_range_call=False)
            return PredicateIR(
                name=fn.name,
                params=params,
                body=expr,
                param_name=anchor_param.name,
                actor_type=anchor_param.actor_type,
            )

    def _compile_callable(self, fn: ast.FunctionDef) -> CallableIR:
        with dsl_node_context(fn):
            if fn.decorator_list:
                raise DSLValidationError("Decorators are not allowed on callable functions.")
            if fn.args.vararg is not None or fn.args.kwarg is not None:
                raise DSLValidationError("Variadic callable parameters are not allowed.")
            if fn.args.posonlyargs or fn.args.kwonlyargs or fn.args.kw_defaults:
                raise DSLValidationError("Callable must use regular positional parameters.")

            params: List[str] = []
            actor_var_types: Dict[str, str] = {}
            actor_list_var_types: Dict[str, Optional[str]] = {}
            role_var_types: Dict[str, str] = {}
            camera_vars: Set[str] = set()
            scene_vars: Set[str] = set()
            tick_vars: Set[str] = set()

            for arg in fn.args.args:
                with dsl_node_context(arg):
                    if arg.annotation is None:
                        raise DSLValidationError(
                            "All callable parameters must have type annotations."
                        )
                    params.append(arg.arg)
                    ann = arg.annotation
                    if isinstance(ann, ast.Name):
                        if ann.id == "Scene":
                            scene_vars.add(arg.arg)
                        elif ann.id == "Tick":
                            tick_vars.add(arg.arg)
                        elif ann.id in self.schemas.actor_fields:
                            actor_var_types[arg.arg] = ann.id
                        elif ann.id in self.schemas.role_fields:
                            role_var_types[arg.arg] = ann.id
                        elif ann.id == "Camera":
                            camera_vars.add(arg.arg)
                        continue

                    if isinstance(ann, ast.Subscript) and isinstance(ann.value, ast.Name):
                        head = ann.value.id
                        if head == "Scene":
                            scene_vars.add(arg.arg)
                        elif head == "Tick":
                            tick_vars.add(arg.arg)
                        elif head in self.schemas.actor_fields:
                            actor_var_types[arg.arg] = head
                        elif head in self.schemas.role_fields:
                            role_var_types[arg.arg] = head
                        elif head == "Camera":
                            camera_vars.add(arg.arg)
                        elif head in {"List", "list"} and isinstance(ann.slice, ast.Name):
                            if ann.slice.id == "Actor":
                                actor_list_var_types[arg.arg] = None
                            elif ann.slice.id in self.schemas.actor_fields:
                                actor_list_var_types[arg.arg] = ann.slice.id
                        continue

                    raise DSLValidationError(
                        "Callable parameter annotations must use a name or T[...] form."
                    )

            if not fn.body:
                raise DSLValidationError("Callable body cannot be empty.")
            if not isinstance(fn.body[-1], ast.Return):
                raise DSLValidationError(
                    "Callable must end with an explicit return statement."
                )

            scope = ActionScope(
                defined_names=set(params),
                actor_var_types=actor_var_types,
                actor_list_var_types=actor_list_var_types,
                role_var_types=role_var_types,
                camera_vars=camera_vars,
                scene_vars=scene_vars,
                tick_vars=tick_vars,
                spawn_actor_templates={},
            )
            body = []
            for stmt in fn.body[:-1]:
                with dsl_node_context(stmt):
                    if isinstance(stmt, ast.Return):
                        raise DSLValidationError(
                            "Return statements are only allowed as the last callable statement."
                        )
                    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Yield):
                        raise DSLValidationError("yield is not allowed inside callable functions.")
                compiled = self._compile_stmt(stmt, scope, loop_depth=0)
                if compiled is not None:
                    body.append(compiled)

            return_stmt = fn.body[-1]
            if return_stmt.value is None:
                raise DSLValidationError("Callable return statement must return a value.")
            return_expr = self._compile_expr(
                return_stmt.value, scope, allow_range_call=False
            )
            return CallableIR(
                name=fn.name,
                params=params,
                body=body,
                return_expr=return_expr,
            )

    def _parse_binding(self, arg: ast.arg) -> ParamBinding:
        with dsl_node_context(arg):
            ann = arg.annotation
            if isinstance(ann, ast.Name) and ann.id == "Scene":
                return ParamBinding(name=arg.arg, kind=BindingKind.SCENE)
            if isinstance(ann, ast.Name) and ann.id == "Tick":
                return ParamBinding(name=arg.arg, kind=BindingKind.TICK)
            if isinstance(ann, ast.Name) and ann.id in self.schemas.actor_fields:
                return ParamBinding(
                    name=arg.arg,
                    kind=BindingKind.ACTOR,
                    actor_selector=ActorSelector(uid=ann.id),
                    actor_type=ann.id,
                )
            if isinstance(ann, ast.Name) and ann.id == "Camera":
                raise DSLValidationError('Camera binding must be Camera["camera_name"].')
            if isinstance(ann, ast.Name) and ann.id == "Role":
                raise DSLValidationError('Role binding must be Role["role_id"].')
            if isinstance(ann, ast.Name) and ann.id in self.schemas.role_fields:
                raise DSLValidationError(
                    f'{ann.id} role binding must be {ann.id}["role_id"].'
                )

            if not isinstance(ann, ast.Subscript):
                raise DSLValidationError("Binding annotation must use T[...] syntax.")
            if not isinstance(ann.value, ast.Name):
                raise DSLValidationError("Binding annotation head must be a name.")

            head = ann.value.id
            selector = ann.slice

            if head == "Scene":
                return ParamBinding(name=arg.arg, kind=BindingKind.SCENE)

            if head == "Tick":
                return ParamBinding(name=arg.arg, kind=BindingKind.TICK)

            if head == "Global":
                global_name = _parse_global_binding_name(selector)
                return ParamBinding(
                    name=arg.arg,
                    kind=BindingKind.GLOBAL,
                    global_name=global_name,
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

            if head == "Role":
                role_id: Optional[str] = None
                if isinstance(selector, ast.Constant) and isinstance(selector.value, str):
                    role_id = selector.value
                elif _parse_int_literal(selector) is not None:
                    raise DSLValidationError(
                        'Role binding does not support index selectors. Use Role["role_id"].'
                    )
                if role_id is None:
                    raise DSLValidationError('Role binding must be Role["role_id"].')
                return ParamBinding(
                    name=arg.arg,
                    kind=BindingKind.ROLE,
                    role_selector=RoleSelector(id=role_id),
                )

            if head == "Camera":
                camera_name: Optional[str] = None
                if isinstance(selector, ast.Constant) and isinstance(selector.value, str):
                    camera_name = selector.value
                elif _parse_int_literal(selector) is not None:
                    raise DSLValidationError(
                        'Camera binding does not support index selectors. Use Camera["camera_name"].'
                    )
                if camera_name is None:
                    raise DSLValidationError('Camera binding must be Camera["camera_name"].')
                if not camera_name:
                    raise DSLValidationError("Camera binding name must be non-empty.")
                return ParamBinding(
                    name=arg.arg,
                    kind=BindingKind.CAMERA,
                    camera_selector=CameraSelector(name=camera_name),
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

            if head in self.schemas.role_fields:
                role_id: Optional[str] = None
                if isinstance(selector, ast.Constant) and isinstance(selector.value, str):
                    role_id = selector.value
                elif _parse_int_literal(selector) is not None:
                    raise DSLValidationError(
                        f'{head} binding does not support index selectors. Use {head}["role_id"].'
                    )
                if role_id is None:
                    raise DSLValidationError(
                        f'{head} binding must be {head}["role_id"].'
                    )
                return ParamBinding(
                    name=arg.arg,
                    kind=BindingKind.ROLE,
                    role_selector=RoleSelector(id=role_id),
                    role_type=head,
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

    def _compile_stmt(self, stmt: ast.stmt, scope: ActionScope, loop_depth: int):
        with dsl_node_context(stmt):
            if isinstance(stmt, ast.Assign):
                if len(stmt.targets) != 1:
                    raise DSLValidationError("Chained assignment is not allowed.")
                target = self._compile_assign_target(stmt.targets[0], scope)
                if (
                    isinstance(target, Var)
                    and isinstance(stmt.value, ast.Call)
                    and isinstance(stmt.value.func, ast.Name)
                    and stmt.value.func.id in self.schemas.actor_fields
                ):
                    (
                        actor_type_name,
                        uid_expr,
                        fields_payload_json,
                    ) = self._compile_actor_ctor_template(
                        stmt.value,
                        scope,
                        source_name=f"{target.name} = {stmt.value.func.id}(...)",
                    )
                    scope.defined_names.add(target.name)
                    scope.actor_var_types.pop(target.name, None)
                    scope.actor_list_var_types.pop(target.name, None)
                    scope.spawn_actor_templates[target.name] = (
                        actor_type_name,
                        uid_expr,
                        fields_payload_json,
                    )
                    return None
                value = self._compile_expr(stmt.value, scope, allow_range_call=False)
                if isinstance(target, Var):
                    scope.defined_names.add(target.name)
                    self._sync_var_types_on_assign(target.name, value, scope)
                return Assign(target=target, value=value)

            if isinstance(stmt, ast.AnnAssign):
                if stmt.value is None:
                    raise DSLValidationError("Annotated assignment must assign a value.")
                target = self._compile_assign_target(stmt.target, scope)
                value = self._compile_expr(stmt.value, scope, allow_range_call=False)
                if isinstance(target, Var):
                    scope.defined_names.add(target.name)
                    self._sync_var_types_on_assign(target.name, value, scope)
                return Assign(target=target, value=value)

            if isinstance(stmt, ast.If):
                body = []
                for child in stmt.body:
                    compiled = self._compile_stmt(child, scope, loop_depth=loop_depth)
                    if compiled is not None:
                        body.append(compiled)
                orelse = []
                for child in stmt.orelse:
                    compiled = self._compile_stmt(child, scope, loop_depth=loop_depth)
                    if compiled is not None:
                        orelse.append(compiled)
                return If(
                    condition=self._compile_expr(stmt.test, scope, allow_range_call=False),
                    body=body,
                    orelse=orelse,
                )

            if isinstance(stmt, ast.While):
                body = []
                for child in stmt.body:
                    compiled = self._compile_stmt(child, scope, loop_depth=loop_depth + 1)
                    if compiled is not None:
                        body.append(compiled)
                return While(
                    condition=self._compile_expr(stmt.test, scope, allow_range_call=False),
                    body=body,
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
                body = []
                for child in stmt.body:
                    compiled = self._compile_stmt(child, scope, loop_depth=loop_depth + 1)
                    if compiled is not None:
                        body.append(compiled)
                return For(
                    var=stmt.target.id,
                    iterable=iterable,
                    body=body,
                )

            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Yield):
                return self._compile_yield_stmt(stmt.value, scope)

            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                return self._compile_call_stmt(stmt.value, scope)

            if isinstance(stmt, ast.Pass):
                return None

            if isinstance(stmt, ast.Continue):
                if loop_depth <= 0:
                    raise DSLValidationError("'continue' is only allowed inside loops.")
                return Continue()

            raise DSLValidationError(f"Unsupported statement: {type(stmt).__name__}")

    def _compile_yield_stmt(self, expr: ast.Yield, scope: ActionScope) -> Yield:
        if expr.value is None:
            raise DSLValidationError("yield must return a Tick binding variable.")
        value = self._compile_expr(expr.value, scope, allow_range_call=False)
        if not isinstance(value, Var) or value.name not in scope.tick_vars:
            raise DSLValidationError(
                "yield must reference a parameter annotated as Tick."
            )
        return Yield(value=value)

    def _compile_call_stmt(self, expr: ast.Call, scope: ActionScope):
        if not (
            isinstance(expr.func, ast.Attribute)
            and isinstance(expr.func.value, ast.Name)
        ):
            raise DSLValidationError("Unsupported call statement in action body.")

        owner = expr.func.value.id
        method = expr.func.attr

        if owner in scope.actor_var_types:
            if method == "play":
                return self._compile_actor_instance_play_call(expr, scope, owner)
            if method == "destroy":
                return self._compile_actor_instance_destroy_call(expr, owner)
            if method == "attached_to":
                return self._compile_actor_instance_attach_call(expr, scope, owner)
            if method == "detached":
                return self._compile_actor_instance_detach_call(expr, scope, owner)

        if owner in scope.camera_vars:
            return self._compile_camera_instance_call(expr, scope, owner)

        if owner in scope.scene_vars:
            return self._compile_scene_instance_call(expr, scope, owner)

        if owner == "Scene":
            return self._compile_static_scene_call(expr, scope)

        if owner in scope.defined_names:
            return self._compile_collection_call_stmt(expr, scope, owner)

        raise DSLValidationError("Unsupported call statement in action body.")

    def _compile_camera_instance_call(
        self,
        expr: ast.Call,
        scope: ActionScope,
        owner: str,
    ) -> CallStmt:
        method = expr.func.attr
        if method == "follow":
            if expr.keywords:
                raise DSLValidationError(
                    f"{owner}.follow(...) does not accept keyword arguments."
                )
            if len(expr.args) != 1:
                raise DSLValidationError(f"{owner}.follow(...) expects one target uid.")
            target_expr = self._compile_expr(expr.args[0], scope, allow_range_call=False)
            if isinstance(target_expr, Const) and not isinstance(target_expr.value, str):
                raise DSLValidationError(f"{owner}.follow(...) target uid must be a string.")
            return CallStmt(name="camera_follow", args=[Var(owner), target_expr])

        if method == "detach":
            if expr.keywords or expr.args:
                raise DSLValidationError(
                    f"{owner}.detach(...) does not accept arguments."
                )
            return CallStmt(name="camera_detach", args=[Var(owner)])

        if method == "translate":
            if expr.keywords:
                raise DSLValidationError(
                    f"{owner}.translate(...) does not accept keyword arguments."
                )
            if len(expr.args) != 2:
                raise DSLValidationError(
                    f"{owner}.translate(...) expects dx and dy arguments."
                )
            return CallStmt(
                name="camera_translate",
                args=[
                    Var(owner),
                    self._compile_expr(expr.args[0], scope, allow_range_call=False),
                    self._compile_expr(expr.args[1], scope, allow_range_call=False),
                ],
            )

        raise DSLValidationError(
            f"Unsupported camera method '{owner}.{method}(...)'. "
            "Supported methods: follow, detach, translate."
        )

    def _compile_actor_instance_attach_call(
        self, expr: ast.Call, scope: ActionScope, owner: str
    ) -> Assign:
        if expr.keywords:
            raise DSLValidationError(
                f"{owner}.attached_to(...) does not accept keyword arguments."
            )
        if len(expr.args) != 1:
            raise DSLValidationError(f"{owner}.attached_to(...) expects one argument.")

        parent_expr = self._compile_expr(expr.args[0], scope, allow_range_call=False)
        if isinstance(parent_expr, Var):
            if parent_expr.name not in scope.actor_var_types:
                raise DSLValidationError(
                    f"{owner}.attached_to(...) argument must be a typed actor variable or uid string."
                )
            parent_uid_expr = Attr(obj=parent_expr.name, field="uid")
        elif isinstance(parent_expr, Const) and isinstance(parent_expr.value, str):
            parent_uid_expr = parent_expr
        else:
            raise DSLValidationError(
                f"{owner}.attached_to(...) argument must be a typed actor variable or uid string."
            )

        return Assign(target=Attr(obj=owner, field="parent"), value=parent_uid_expr)

    def _compile_actor_instance_detach_call(
        self, expr: ast.Call, scope: ActionScope, owner: str
    ) -> Assign:
        if expr.keywords or expr.args:
            raise DSLValidationError(
                f"{owner}.detached(...) does not accept arguments."
            )
        return Assign(target=Attr(obj=owner, field="parent"), value=Const(""))

    def _compile_actor_instance_play_call(
        self, expr: ast.Call, scope: ActionScope, owner: str
    ) -> CallStmt:
        if expr.keywords:
            raise DSLValidationError(
                f"{owner}.play(...) does not accept keyword arguments."
            )
        if len(expr.args) != 1:
            raise DSLValidationError(f"{owner}.play(...) expects one clip name argument.")

        clip_arg = self._compile_expr(expr.args[0], scope, allow_range_call=False)
        if isinstance(clip_arg, Const) and not isinstance(clip_arg.value, str):
            raise DSLValidationError(f"{owner}.play(...) clip name must be a string.")
        return CallStmt(name="play_animation", args=[Var(owner), clip_arg])

    def _compile_actor_instance_destroy_call(
        self, expr: ast.Call, owner: str
    ) -> CallStmt:
        if expr.keywords or expr.args:
            raise DSLValidationError(
                f"{owner}.destroy(...) does not accept arguments."
            )
        return CallStmt(name="destroy_actor", args=[Var(owner)])

    def _compile_collection_call_stmt(
        self, expr: ast.Call, scope: ActionScope, owner: str
    ) -> CallStmt:
        method = expr.func.attr
        if expr.keywords:
            raise DSLValidationError(
                f"{owner}.{method}(...) does not accept keyword arguments."
            )

        if method == "append":
            if len(expr.args) != 1:
                raise DSLValidationError(
                    f"{owner}.append(...) expects exactly one argument."
                )
            return CallStmt(
                name="list_append",
                args=[
                    Var(owner),
                    self._compile_expr(expr.args[0], scope, allow_range_call=False),
                ],
            )

        if method == "update":
            if len(expr.args) != 1:
                raise DSLValidationError(
                    f"{owner}.update(...) expects exactly one argument."
                )
            return CallStmt(
                name="dict_update",
                args=[
                    Var(owner),
                    self._compile_expr(expr.args[0], scope, allow_range_call=False),
                ],
            )

        if method == "pop":
            if len(expr.args) > 1:
                raise DSLValidationError(
                    f"{owner}.pop(...) expects zero or one positional argument."
                )
            index_expr = (
                self._compile_expr(expr.args[0], scope, allow_range_call=False)
                if expr.args
                else Const(None)
            )
            return CallStmt(
                name="collection_pop_discard",
                args=[Var(owner), index_expr],
            )

        if method == "concat":
            raise DSLValidationError(
                f"{owner}.concat(...) returns a value. Assign the result to a variable."
            )

        raise DSLValidationError(
            f"Unsupported call statement '{owner}.{method}(...)'. "
            "Supported mutating methods: append, pop, update."
        )

    def _compile_scene_instance_call(
        self, expr: ast.Call, scope: ActionScope, owner: str
    ) -> CallStmt:
        method = expr.func.attr
        if method in {"enable_gravity", "disable_gravity"}:
            if expr.args or expr.keywords:
                raise DSLValidationError(f"{owner}.{method}(...) does not accept arguments.")
            return CallStmt(
                name="scene_set_gravity",
                args=[Const(method == "enable_gravity")],
            )
        if method == "set_interface":
            if expr.keywords:
                raise DSLValidationError(
                    f"{owner}.set_interface(...) does not accept keyword args."
                )
            if len(expr.args) != 1:
                raise DSLValidationError(
                    f"{owner}.set_interface(...) expects one HTML string argument."
                )
            html_expr = self._compile_expr(expr.args[0], scope, allow_range_call=False)
            if isinstance(html_expr, Const) and not isinstance(html_expr.value, str):
                raise DSLValidationError(
                    f"{owner}.set_interface(...) HTML must be a string."
                )
            return CallStmt(name="scene_set_interface", args=[html_expr])
        if method == "next_turn":
            if expr.args or expr.keywords:
                raise DSLValidationError(f"{owner}.next_turn(...) does not accept arguments.")
            return CallStmt(name="scene_next_turn", args=[])
        if method == "spawn":
            return self._compile_scene_spawn_call(
                args=expr.args,
                keywords=expr.keywords,
                scope=scope,
                source_name=f"{owner}.spawn(...)",
            )
        raise DSLValidationError("Unsupported Scene method call in action body.")

    def _compile_static_scene_call(self, expr: ast.Call, scope: ActionScope) -> CallStmt:
        method = expr.func.attr
        if method in {"enable_gravity", "disable_gravity"}:
            if expr.keywords:
                raise DSLValidationError(f"Scene.{method}(...) does not accept keyword args.")
            if len(expr.args) != 1:
                raise DSLValidationError(f"Scene.{method}(...) expects a scene argument.")
            scene_arg = self._compile_expr(expr.args[0], scope, allow_range_call=False)
            self._require_scene_var(scene_arg, scope, f"Scene.{method}(...)")
            return CallStmt(
                name="scene_set_gravity",
                args=[Const(method == "enable_gravity")],
            )
        if method == "set_interface":
            if expr.keywords:
                raise DSLValidationError(
                    "Scene.set_interface(...) does not accept keyword args."
                )
            if len(expr.args) != 2:
                raise DSLValidationError(
                    "Scene.set_interface(...) expects scene and html arguments."
                )
            scene_arg = self._compile_expr(expr.args[0], scope, allow_range_call=False)
            self._require_scene_var(scene_arg, scope, "Scene.set_interface(...)")
            html_expr = self._compile_expr(expr.args[1], scope, allow_range_call=False)
            if isinstance(html_expr, Const) and not isinstance(html_expr.value, str):
                raise DSLValidationError(
                    "Scene.set_interface(...) HTML must be a string."
                )
            return CallStmt(name="scene_set_interface", args=[html_expr])
        if method == "next_turn":
            if expr.keywords:
                raise DSLValidationError("Scene.next_turn(...) does not accept keyword args.")
            if len(expr.args) != 1:
                raise DSLValidationError("Scene.next_turn(...) expects a scene argument.")
            scene_arg = self._compile_expr(expr.args[0], scope, allow_range_call=False)
            self._require_scene_var(scene_arg, scope, "Scene.next_turn(...)")
            return CallStmt(name="scene_next_turn", args=[])
        if method == "spawn":
            if not expr.args:
                raise DSLValidationError(
                    "Scene.spawn(...) expects scene, actor type and uid."
                )
            scene_arg = self._compile_expr(expr.args[0], scope, allow_range_call=False)
            self._require_scene_var(scene_arg, scope, "Scene.spawn(...)")
            return self._compile_scene_spawn_call(
                args=expr.args[1:],
                keywords=expr.keywords,
                scope=scope,
                source_name="Scene.spawn(...)",
            )
        raise DSLValidationError("Unsupported Scene method call in action body.")

    def _compile_scene_spawn_call(
        self,
        args: List[ast.AST],
        keywords: List[ast.keyword],
        scope: ActionScope,
        source_name: str,
    ) -> CallStmt:
        actor_type_name: str
        uid_expr: Expr
        fields_expr: Expr

        if len(args) == 1:
            if keywords:
                raise DSLValidationError(
                    f"{source_name} constructor-style actor argument does not accept extra keyword arguments."
                )
            if isinstance(args[0], ast.Call):
                (
                    actor_type_name,
                    uid_expr,
                    fields_expr,
                ) = self._compile_actor_ctor_template(
                    args[0], scope, source_name
                )
            elif isinstance(args[0], ast.Name):
                template = scope.spawn_actor_templates.get(args[0].id)
                if template is None:
                    raise DSLValidationError(
                        f"{source_name} variable '{args[0].id}' must be assigned from ActorType(...)."
                    )
                actor_type_name, uid_expr, fields_expr = template
            else:
                raise DSLValidationError(
                    f"{source_name} expects ActorType(...) or a variable assigned from ActorType(...)."
                )
        else:
            if len(args) != 2:
                raise DSLValidationError(
                    f"{source_name} expects ActorType(uid=...) constructor or actor type + uid positional arguments."
                )
            actor_type_name = _expect_name(args[0], "actor type")
            if actor_type_name not in self.schemas.actor_fields:
                raise DSLValidationError(
                    f"{source_name} actor type must reference a declared schema."
                )
            uid_expr = self._compile_expr(args[1], scope, allow_range_call=False)
            if isinstance(uid_expr, Const) and not isinstance(uid_expr.value, str):
                raise DSLValidationError(f"{source_name} uid must be a string.")
            field_nodes = {
                keyword.arg: keyword.value for keyword in keywords if keyword.arg is not None
            }
            fields_expr = self._build_scene_spawn_fields_expr(
                actor_type_name=actor_type_name,
                field_nodes=field_nodes,
                scope=scope,
                source_name=source_name,
            )

        return CallStmt(
            name="scene_spawn_actor",
            args=[
                Const(actor_type_name),
                uid_expr,
                fields_expr,
            ],
        )

    def _compile_actor_ctor_template(
        self,
        ctor_call: ast.Call,
        scope: ActionScope,
        source_name: str,
    ) -> tuple[str, Expr, Expr]:
        actor_type_name, uid_expr, field_nodes = self._parse_actor_ctor_call(
            ctor_call, scope, source_name
        )
        fields_expr = self._build_scene_spawn_fields_expr(
            actor_type_name=actor_type_name,
            field_nodes=field_nodes,
            scope=scope,
            source_name=source_name,
        )
        return actor_type_name, uid_expr, fields_expr

    def _build_scene_spawn_fields_expr(
        self,
        actor_type_name: str,
        field_nodes: Dict[str, ast.AST],
        scope: ActionScope,
        source_name: str,
    ) -> ObjectExpr:
        schema_fields = self.schemas.actor_fields[actor_type_name]
        fields_expr: Dict[str, Expr] = {}
        for field_name, field_node in field_nodes.items():
            if field_name not in schema_fields:
                raise DSLValidationError(
                    f"{source_name} unknown field '{field_name}' for '{actor_type_name}'."
                )
            if field_name == "parent":
                fields_expr[field_name] = self._compile_parent_field_expr(
                    field_node, scope, source_name
                )
            else:
                fields_expr[field_name] = self._compile_expr(
                    field_node, scope, allow_range_call=False
                )
        return ObjectExpr(fields=fields_expr)

    def _compile_parent_field_expr(
        self,
        node: ast.AST,
        scope: ActionScope,
        source_name: str,
    ) -> Expr:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return Const(node.value)

        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            owner = node.value.id
            if owner != "Actor" and owner not in self.schemas.actor_fields:
                raise DSLValidationError(
                    f"{source_name} parent selector references unknown actor schema '{owner}'."
                )
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                return Const(node.slice.value)
            raise DSLValidationError(
                f'{source_name} parent selector must be ActorType["uid"].'
            )

        compiled = self._compile_expr(node, scope, allow_range_call=False)
        if isinstance(compiled, Var) and compiled.name in scope.actor_var_types:
            return Attr(obj=compiled.name, field="uid")
        return compiled

    def _parse_actor_ctor_call(
        self,
        ctor_call: ast.Call,
        scope: ActionScope,
        source_name: str,
    ) -> tuple[str, Expr, Dict[str, ast.AST]]:
        if not isinstance(ctor_call.func, ast.Name):
            raise DSLValidationError(
                f"{source_name} actor constructor must reference a declared actor schema."
            )
        actor_type_name = ctor_call.func.id
        if actor_type_name not in self.schemas.actor_fields:
            raise DSLValidationError(
                f"{source_name} actor constructor must reference a declared actor schema."
            )
        if len(ctor_call.args) > 1:
            raise DSLValidationError(
                f"{source_name} actor constructor accepts at most one positional uid argument."
            )

        field_nodes: Dict[str, ast.AST] = {}
        uid_node: ast.AST | None = ctor_call.args[0] if ctor_call.args else None
        for keyword in ctor_call.keywords:
            if keyword.arg is None:
                raise DSLValidationError(
                    f"{source_name} actor constructor does not support **kwargs expansion."
                )
            if keyword.arg == "uid":
                if uid_node is not None:
                    raise DSLValidationError(
                        f"{source_name} actor constructor uid cannot be provided both positionally and by keyword."
                    )
                uid_node = keyword.value
            else:
                if keyword.arg in field_nodes:
                    raise DSLValidationError(
                        f"{source_name} duplicate actor field '{keyword.arg}'."
                    )
                field_nodes[keyword.arg] = keyword.value

        if uid_node is None:
            uid_expr: Expr = Const("")
        else:
            uid_expr = self._compile_expr(uid_node, scope, allow_range_call=False)
            if isinstance(uid_expr, Const) and not isinstance(uid_expr.value, str):
                raise DSLValidationError(
                    f"{source_name} actor constructor uid must be a string."
                )
        return actor_type_name, uid_expr, field_nodes

    def _require_scene_var(
        self, expr, scope: ActionScope, source_name: str
    ) -> None:
        if not isinstance(expr, Var):
            raise DSLValidationError(
                f"{source_name} scene argument must be a Scene binding variable."
            )
        if expr.name not in scope.scene_vars:
            raise DSLValidationError(
                f"{source_name} scene argument must reference a Scene binding variable."
            )

    def _compile_assign_target(self, target: ast.AST, scope: ActionScope):
        if isinstance(target, ast.Name):
            return Var(target.id)
        if isinstance(target, ast.Attribute):
            compiled = self._compile_attr(target, scope)
            if (
                isinstance(compiled, Attr)
                and compiled.obj in scope.scene_vars
                and compiled.field == "elapsed"
            ):
                raise DSLValidationError("scene.elapsed is read-only.")
            if (
                isinstance(compiled, Attr)
                and compiled.obj in scope.tick_vars
                and compiled.field == "elapsed"
            ):
                raise DSLValidationError("tick.elapsed is read-only.")
            return compiled
        if isinstance(target, ast.Subscript):
            if isinstance(target.slice, ast.Slice):
                raise DSLValidationError("Slice assignment is not supported.")
            return SubscriptExpr(
                value=self._compile_expr(target.value, scope, allow_range_call=False),
                index=self._compile_expr(target.slice, scope, allow_range_call=False),
            )
        raise DSLValidationError("Assignment target must be a variable or actor/role field.")

    # ---------------- Expressions ----------------

    def _compile_expr(self, expr: ast.AST, scope: ActionScope, allow_range_call: bool):
        with dsl_node_context(expr):
            if isinstance(expr, ast.Constant):
                if expr.value is None:
                    return Const(None)
                if isinstance(expr.value, bool):
                    return Const(expr.value)
                if isinstance(expr.value, (int, float, str)):
                    return Const(expr.value)
                raise DSLValidationError(
                    "Only int, float, str, bool, and None constants are allowed."
                )

            if isinstance(expr, ast.List):
                return ListExpr(
                    items=[
                        self._compile_expr(item, scope, allow_range_call=False)
                        for item in expr.elts
                    ]
                )

            if isinstance(expr, ast.Dict):
                fields: Dict[str, Expr] = {}
                for key_node, value_node in zip(expr.keys, expr.values):
                    if key_node is None:
                        raise DSLValidationError("Dict unpacking is not supported.")
                    key_expr = self._compile_expr(key_node, scope, allow_range_call=False)
                    if not isinstance(key_expr, Const) or not isinstance(key_expr.value, str):
                        raise DSLValidationError(
                            "Dict literal keys must be constant strings."
                        )
                    fields[key_expr.value] = self._compile_expr(
                        value_node, scope, allow_range_call=False
                    )
                return ObjectExpr(fields=fields)

            if isinstance(expr, ast.Name):
                if expr.id not in scope.defined_names:
                    raise DSLValidationError(f"Unknown variable '{expr.id}'.")
                return Var(expr.id)

            if isinstance(expr, ast.Attribute):
                return self._compile_attr(expr, scope)

            if isinstance(expr, ast.Subscript):
                if isinstance(expr.slice, ast.Slice):
                    raise DSLValidationError("Slice expressions are not supported.")
                return SubscriptExpr(
                    value=self._compile_expr(expr.value, scope, allow_range_call=False),
                    index=self._compile_expr(expr.slice, scope, allow_range_call=False),
                )

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
                left_expr = self._compile_expr(expr.left, scope, allow_range_call=False)
                right_expr = self._compile_expr(
                    expr.comparators[0], scope, allow_range_call=False
                )
                op_node = type(expr.ops[0])
                if op_node in {ast.Is, ast.IsNot}:
                    left_is_none = isinstance(left_expr, Const) and left_expr.value is None
                    right_is_none = isinstance(right_expr, Const) and right_expr.value is None
                    if not (left_is_none or right_is_none):
                        raise DSLValidationError(
                            "'is'/'is not' comparisons are only supported with None."
                        )
                op = _ALLOWED_CMP.get(op_node)
                if op is None:
                    raise DSLValidationError(
                        f"Unsupported comparison operator: {type(expr.ops[0]).__name__}"
                    )
                return Binary(
                    op=op,
                    left=left_expr,
                    right=right_expr,
                )

            if isinstance(expr, ast.Call):
                if allow_range_call:
                    return self._compile_range_call(expr, scope)
                return self._compile_builtin_expr_call(expr, scope)

            raise DSLValidationError(f"Unsupported expression: {type(expr).__name__}")

    def _compile_builtin_expr_call(self, expr: ast.Call, scope: ActionScope) -> CallExpr:
        if (
            isinstance(expr.func, ast.Attribute)
            and isinstance(expr.func.value, ast.Name)
            and expr.func.value.id == "Random"
        ):
            if expr.keywords:
                raise DSLValidationError("Random.*(...) does not accept keyword arguments.")

            method = expr.func.attr
            if method == "int":
                if len(expr.args) != 2:
                    raise DSLValidationError("Random.int(...) expects min and max.")
                return CallExpr(
                    name="random_int",
                    args=[
                        self._compile_expr(arg, scope, allow_range_call=False)
                        for arg in expr.args
                    ],
                )

            if method == "bool":
                if len(expr.args) != 0:
                    raise DSLValidationError("Random.bool(...) expects no arguments.")
                return CallExpr(name="random_bool", args=[])

            if method == "string":
                if len(expr.args) not in {1, 2}:
                    raise DSLValidationError(
                        "Random.string(...) expects length and optional alphabet."
                    )
                return CallExpr(
                    name="random_string",
                    args=[
                        self._compile_expr(arg, scope, allow_range_call=False)
                        for arg in expr.args
                    ],
                )

            if method in {"float", "uniform"}:
                if len(expr.args) != 2:
                    raise DSLValidationError(
                        f"Random.{method}(...) expects min and max."
                    )
                return CallExpr(
                    name="random_float_uniform",
                    args=[
                        self._compile_expr(arg, scope, allow_range_call=False)
                        for arg in expr.args
                    ],
                )

            if method == "normal":
                if len(expr.args) != 2:
                    raise DSLValidationError(
                        "Random.normal(...) expects mean and standard deviation."
                    )
                return CallExpr(
                    name="random_float_normal",
                    args=[
                        self._compile_expr(arg, scope, allow_range_call=False)
                        for arg in expr.args
                    ],
                )

            raise DSLValidationError(f"Unsupported Random method '{method}'.")

        if isinstance(expr.func, ast.Attribute):
            return self._compile_collection_expr_call(expr, scope)

        if isinstance(expr.func, ast.Name) and expr.func.id in self.callable_signatures:
            if expr.keywords:
                raise DSLValidationError(
                    f"{expr.func.id}(...) does not accept keyword arguments."
                )
            expected_arity = self.callable_signatures[expr.func.id]
            if len(expr.args) != expected_arity:
                raise DSLValidationError(
                    f"{expr.func.id}(...) expects exactly {expected_arity} positional arguments."
                )
            return CallExpr(
                name=f"{CALLABLE_EXPR_PREFIX}{expr.func.id}",
                args=[
                    self._compile_expr(arg, scope, allow_range_call=False)
                    for arg in expr.args
                ],
            )

        raise DSLValidationError("Function calls are not allowed.")

    def _compile_collection_expr_call(self, expr: ast.Call, scope: ActionScope) -> CallExpr:
        if not (
            isinstance(expr.func, ast.Attribute)
            and isinstance(expr.func.value, ast.Name)
        ):
            raise DSLValidationError("Unsupported method call expression.")
        owner_name = expr.func.value.id
        if owner_name not in scope.defined_names:
            raise DSLValidationError(
                "Method call expression receiver must be a declared variable."
            )
        if expr.keywords:
            raise DSLValidationError(
                f"{owner_name}.{expr.func.attr}(...) does not accept keyword arguments."
            )

        owner_expr: Expr = Var(owner_name)
        args = [self._compile_expr(arg, scope, allow_range_call=False) for arg in expr.args]
        method = expr.func.attr

        if method == "pop":
            if len(args) > 1:
                raise DSLValidationError(
                    f"{owner_name}.pop(...) expects zero or one positional argument."
                )
            index_expr = args[0] if args else Const(None)
            return CallExpr(name="collection_pop", args=[owner_expr, index_expr])

        if method == "concat":
            if len(args) != 1:
                raise DSLValidationError(
                    f"{owner_name}.concat(...) expects exactly one argument."
                )
            return CallExpr(name="collection_concat", args=[owner_expr, args[0]])

        if method == "get":
            if len(args) not in {1, 2}:
                raise DSLValidationError(
                    f"{owner_name}.get(...) expects key or key/default arguments."
                )
            default_expr = args[1] if len(args) == 2 else Const(None)
            return CallExpr(name="dict_get", args=[owner_expr, args[0], default_expr])

        if method == "keys":
            if args:
                raise DSLValidationError(f"{owner_name}.keys(...) does not accept arguments.")
            return CallExpr(name="dict_keys", args=[owner_expr])

        if method == "values":
            if args:
                raise DSLValidationError(
                    f"{owner_name}.values(...) does not accept arguments."
                )
            return CallExpr(name="dict_values", args=[owner_expr])

        if method == "items":
            if args:
                raise DSLValidationError(
                    f"{owner_name}.items(...) does not accept arguments."
                )
            return CallExpr(name="dict_items", args=[owner_expr])

        raise DSLValidationError(
            f"Unsupported method call expression '{owner_name}.{method}(...)'. "
            "Supported expression methods: pop, concat, get, keys, values, items."
        )

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

        if obj_name in scope.scene_vars:
            if expr.attr != "elapsed":
                raise DSLValidationError(
                    "Scene bindings only expose read-only 'elapsed'."
                )
            return Attr(obj=obj_name, field="elapsed")

        if obj_name in scope.tick_vars:
            if expr.attr != "elapsed":
                raise DSLValidationError(
                    "Tick bindings only expose read-only 'elapsed'."
                )
            return Attr(obj=obj_name, field="elapsed")

        if obj_name in scope.camera_vars:
            if expr.attr not in {
                "name",
                "role_id",
                "x",
                "y",
                "width",
                "height",
                "target_uid",
                "offset_x",
                "offset_y",
            }:
                raise DSLValidationError(
                    f"Camera has no field '{expr.attr}'."
                )
            return Attr(obj=obj_name, field=expr.attr)

        actor_type = scope.actor_var_types.get(obj_name)
        role_type = scope.role_var_types.get(obj_name)
        if role_type is not None:
            if not self.schemas.has_role_field(role_type, expr.attr):
                raise DSLValidationError(
                    f"Role '{role_type}' has no field '{expr.attr}'."
                )
            return Attr(obj=obj_name, field=expr.attr)

        if actor_type is None:
            raise DSLValidationError(
                f"Actor variable '{obj_name}' must use Actor[\"Type\"] or "
                "Type[...] binding to allow field access. "
                "Role fields require RoleType[\"role_id\"] bindings."
            )
        if not self.schemas.has_actor_field(actor_type, expr.attr):
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
            if value.name in scope.role_var_types:
                scope.role_var_types[target_name] = scope.role_var_types[value.name]
            else:
                scope.role_var_types.pop(target_name, None)
            if value.name in scope.camera_vars:
                scope.camera_vars.add(target_name)
            else:
                scope.camera_vars.discard(target_name)
            if value.name in scope.spawn_actor_templates:
                scope.spawn_actor_templates[target_name] = scope.spawn_actor_templates[
                    value.name
                ]
            else:
                scope.spawn_actor_templates.pop(target_name, None)
            return

        scope.actor_var_types.pop(target_name, None)
        scope.actor_list_var_types.pop(target_name, None)
        scope.role_var_types.pop(target_name, None)
        scope.camera_vars.discard(target_name)
        scope.spawn_actor_templates.pop(target_name, None)

    def _iterated_actor_type(self, iterable, scope: ActionScope) -> Optional[str]:
        if isinstance(iterable, Var):
            return scope.actor_list_var_types.get(iterable.name)
        return None
