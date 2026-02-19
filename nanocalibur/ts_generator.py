import json

from nanocalibur.errors import DSLValidationError
from nanocalibur.ir import (
    ActionIR,
    Assign,
    Attr,
    Binary,
    BindingKind,
    CallableIR,
    CallExpr,
    CallStmt,
    Continue,
    Const,
    For,
    If,
    ListExpr,
    ObjectExpr,
    PredicateIR,
    Range,
    SubscriptExpr,
    Unary,
    Var,
    While,
    Yield,
)

CALLABLE_EXPR_PREFIX = "__nc_callable__:"


class TSGenerator:
    def generate(
        self,
        actions,
        predicates=None,
        callables=None,
    ):
        predicates = predicates or []
        callables = callables or []
        out = [self._emit_prelude_ts()]
        for helper in callables:
            out.append(self._emit_callable(helper, typed=True, exported=True))
        for action in actions:
            out.append(self._emit_action(action, typed=True, exported=True))
        for predicate in predicates:
            out.append(self._emit_predicate(predicate, typed=True, exported=True))
        return "\n\n".join(out)

    def _emit_prelude_ts(self):
        return """\
export interface RuntimeSceneContext {
  gravityEnabled?: boolean;
  elapsed?: number;
  setGravityEnabled?: (enabled: boolean) => void;
  setInterfaceHtml?: (html: string) => void;
  spawnActor?: (actorType: string, uid: string, fields?: Record<string, any>) => any;
  nextTurn?: () => void;
}

export interface GameContext {
  globals: Record<string, any>;
  actors: any[];
  roles?: Record<string, any>;
  self?: any;
  tick: number;
  elapsed?: number;
  getActorByUid?: (uid: string) => any;
  getRoleById?: (id: string) => any;
  playAnimation?: (actor: any, clipName: string) => void;
  destroyActor?: (actor: any) => void;
  scene?: RuntimeSceneContext;
}

const __NC_DEFAULT_RANDOM_ALPHABET =
  "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";

function __nc_random_int(minInclusive: number, maxInclusive: number): number {
  const lo = Math.ceil(Math.min(minInclusive, maxInclusive));
  const hi = Math.floor(Math.max(minInclusive, maxInclusive));
  return Math.floor(Math.random() * (hi - lo + 1)) + lo;
}

function __nc_random_bool(): boolean {
  return Math.random() < 0.5;
}

function __nc_random_string(length: number, alphabet: string = __NC_DEFAULT_RANDOM_ALPHABET): string {
  const size = Math.max(0, Math.floor(length));
  if (alphabet.length === 0) {
    return "";
  }
  let out = "";
  for (let i = 0; i < size; i += 1) {
    const idx = Math.floor(Math.random() * alphabet.length);
    out += alphabet[idx];
  }
  return out;
}

function __nc_random_float_uniform(minValue: number, maxValue: number): number {
  const lo = Math.min(minValue, maxValue);
  const hi = Math.max(minValue, maxValue);
  return lo + Math.random() * (hi - lo);
}

function __nc_random_float_normal(mean: number, stddev: number): number {
  // Box-Muller transform.
  let u = 0;
  let v = 0;
  while (u === 0) {
    u = Math.random();
  }
  while (v === 0) {
    v = Math.random();
  }
  const z = Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
  return mean + z * stddev;
}
"""

    def _emit_callable(self, helper: CallableIR, typed: bool, exported: bool):
        prefix = "export " if exported else ""
        if typed:
            params = ", ".join(f"{name}: any" for name in helper.params)
            lines = [f"{prefix}function {helper.name}({params}): any {{"]
        else:
            params = ", ".join(helper.params)
            lines = [f"{prefix}function {helper.name}({params}) {{"]

        helper_local_names = [
            name
            for name in self._collect_assigned_var_names(helper.body)
            if name not in set(helper.params)
        ]
        for local_name in helper_local_names:
            if typed:
                lines.append(f"  let {local_name}: any;")
            else:
                lines.append(f"  let {local_name};")

        for stmt in helper.body:
            lines.extend(self._emit_stmt(stmt, indent=1))
        lines.append(f"  return {self._emit_expr(helper.return_expr)};")
        lines.append("}")
        return "\n".join(lines)

    def _emit_action(self, action: ActionIR, typed: bool, exported: bool):
        previous_tick_vars = getattr(self, "_tick_vars", set())
        previous_scene_vars = getattr(self, "_scene_vars", set())
        self._tick_vars = {
            param.name for param in action.params if param.kind == BindingKind.TICK
        }
        self._scene_vars = {
            param.name for param in action.params if param.kind == BindingKind.SCENE
        }
        is_generator = self._action_uses_yield(action)
        try:
            if typed:
                prefix = "export " if exported else ""
                if is_generator:
                    lines = [
                        f"{prefix}function* {action.name}(ctx: GameContext): Generator<number, void, unknown> {{"
                    ]
                else:
                    lines = [f"{prefix}function {action.name}(ctx: GameContext): void {{"]
            else:
                prefix = "export " if exported else ""
                fn_keyword = "function*" if is_generator else "function"
                lines = [f"{prefix}{fn_keyword} {action.name}(ctx) {{"]

            global_bindings = []
            post_yield_refresh_calls: list[str] = []
            action_param_names = {param.name for param in action.params}
            for param in action.params:
                if param.kind == BindingKind.SCENE:
                    lines.append(f"  let {param.name} = ctx.scene;")
                    continue

                if param.kind == BindingKind.TICK:
                    lines.append(f"  let {param.name} = ctx.tick;")
                    continue

                if param.kind == BindingKind.GLOBAL:
                    lines.append(
                        f'  let {param.name} = ctx.globals[{json.dumps(param.global_name)}];'
                    )
                    global_bindings.append((param.name, param.global_name))
                    continue

                if param.kind == BindingKind.ROLE:
                    selector = param.role_selector
                    if selector is None:
                        raise DSLValidationError(
                            f"Role binding missing selector for '{param.name}'."
                        )
                    lines.extend(
                        self._emit_role_binding_lines(
                            param_name=param.name,
                            role_id=selector.id,
                            role_type=param.role_type,
                        )
                    )
                    continue

                if param.kind == BindingKind.ACTOR_LIST:
                    if param.actor_list_type is None:
                        lines.append(f"  let {param.name} = ctx.actors;")
                    else:
                        actor_type = json.dumps(param.actor_list_type)
                        lines.append(
                            f"  let {param.name} = "
                            f"ctx.actors.filter((a{': any' if typed else ''}) => a?.type === {actor_type});"
                        )
                    continue

                selector = param.actor_selector
                if selector is None:
                    raise DSLValidationError(f"Actor binding missing selector for '{param.name}'.")
                if is_generator:
                    if typed:
                        lines.append(f"  let {param.name}: any;")
                    else:
                        lines.append(f"  let {param.name};")
                    refresh_fn = f"__nc_refresh_binding_{param.name}"
                    lines.append(f"  const {refresh_fn} = () => {{")
                    for binding_line in self._emit_actor_binding_lines(
                        param,
                        typed,
                        declare_with_let=False,
                    ):
                        lines.append(f"    {binding_line}")
                    lines.append("  };")
                    lines.append(f"  {refresh_fn}();")
                    post_yield_refresh_calls.append(refresh_fn)
                    continue

                for binding_line in self._emit_actor_binding_lines(
                    param,
                    typed,
                    declare_with_let=True,
                ):
                    lines.append(f"  {binding_line}")

            action_local_names = [
                name
                for name in self._collect_assigned_var_names(action.body)
                if name not in action_param_names
            ]
            for local_name in action_local_names:
                if typed:
                    lines.append(f"  let {local_name}: any;")
                else:
                    lines.append(f"  let {local_name};")

            for stmt in action.body:
                lines.extend(
                    self._emit_stmt(
                        stmt,
                        indent=1,
                        post_yield_refresh_calls=post_yield_refresh_calls,
                    )
                )

            for param_name, global_name in global_bindings:
                lines.append(f'  ctx.globals[{json.dumps(global_name)}] = {param_name};')

            lines.append("}")
            return "\n".join(lines)
        finally:
            self._tick_vars = previous_tick_vars
            self._scene_vars = previous_scene_vars

    def _emit_actor_binding_lines(
        self,
        param,
        typed: bool,
        declare_with_let: bool,
    ) -> list[str]:
        selector = param.actor_selector
        if selector is None:
            raise DSLValidationError(f"Actor binding missing selector for '{param.name}'.")

        prefix = "let " if declare_with_let else ""

        if selector.index is not None:
            index_value = selector.index
            if param.actor_type is not None:
                actor_type = json.dumps(param.actor_type)
                filtered_var = f"__actors_{param.name}"
                out = [
                    f"const {filtered_var} = "
                    f"ctx.actors.filter((a{': any' if typed else ''}) => a?.type === {actor_type});"
                ]
                if index_value >= 0:
                    out.append(f"{prefix}{param.name} = {filtered_var}[{index_value}];")
                else:
                    out.append(
                        f"{prefix}{param.name} = {filtered_var}[{filtered_var}.length + ({index_value})];"
                    )
                return out

            if index_value >= 0:
                return [f"{prefix}{param.name} = ctx.actors[{index_value}];"]
            return [
                f"{prefix}{param.name} = ctx.actors[ctx.actors.length + ({index_value})];"
            ]

        if selector.uid is not None:
            uid = json.dumps(selector.uid)
            if param.actor_type is not None and selector.uid == param.actor_type:
                actor_type = json.dumps(param.actor_type)
                return [
                    f"{prefix}{param.name} = "
                    f"ctx.actors.find((a{': any' if typed else ''}) => a?.type === {actor_type});"
                ]
            return [
                f"{prefix}{param.name} = "
                f"(ctx.getActorByUid ? ctx.getActorByUid({uid}) : "
                f"ctx.actors.find((a{': any' if typed else ''}) => a?.uid === {uid}));"
            ]

        raise DSLValidationError(f"Unsupported actor selector for '{param.name}'.")

    def _emit_role_binding_lines(
        self,
        param_name: str,
        role_id: str,
        role_type: str | None,
    ) -> list[str]:
        escaped_id = json.dumps(role_id)
        out = [f"  let {param_name} = (ctx.getRoleById ? ctx.getRoleById({escaped_id}) : null);"]
        if role_type is not None:
            escaped_type = json.dumps(role_type)
            out.append(
                f"  if ({param_name} && {param_name}.type !== {escaped_type}) {{ {param_name} = null; }}"
            )
        return out

    def _emit_predicate(self, predicate: PredicateIR, typed: bool, exported: bool):
        previous_tick_vars = getattr(self, "_tick_vars", set())
        previous_scene_vars = getattr(self, "_scene_vars", set())
        self._tick_vars = {
            param.name for param in predicate.params if param.kind == BindingKind.TICK
        }
        self._scene_vars = {
            param.name for param in predicate.params if param.kind == BindingKind.SCENE
        }
        try:
            if typed:
                prefix = "export " if exported else ""
                lines = [f"{prefix}function {predicate.name}(ctx: GameContext): boolean {{"]
            else:
                prefix = "export " if exported else ""
                lines = [f"{prefix}function {predicate.name}(ctx) {{"]

            for param in predicate.params:
                if param.kind == BindingKind.SCENE:
                    lines.append(f"  let {param.name} = ctx.scene;")
                    continue

                if param.kind == BindingKind.TICK:
                    lines.append(f"  let {param.name} = ctx.tick;")
                    continue

                if param.kind == BindingKind.GLOBAL:
                    lines.append(
                        f'  let {param.name} = ctx.globals[{json.dumps(param.global_name)}];'
                    )
                    continue

                if param.kind == BindingKind.ROLE:
                    selector = param.role_selector
                    if selector is None:
                        raise DSLValidationError(
                            f"Role binding missing selector for '{param.name}'."
                        )
                    lines.extend(
                        self._emit_role_binding_lines(
                            param_name=param.name,
                            role_id=selector.id,
                            role_type=param.role_type,
                        )
                    )
                    continue

                if param.kind == BindingKind.ACTOR_LIST:
                    if param.actor_list_type is None:
                        lines.append(f"  let {param.name} = ctx.actors;")
                    else:
                        actor_type = json.dumps(param.actor_list_type)
                        lines.append(
                            f"  let {param.name} = "
                            f"ctx.actors.filter((a{': any' if typed else ''}) => a?.type === {actor_type});"
                        )
                    continue

                for binding_line in self._emit_actor_binding_lines(
                    param,
                    typed,
                    declare_with_let=True,
                ):
                    lines.append(f"  {binding_line}")

            lines.append(f"  return {self._emit_expr(predicate.body)};")
            lines.append("}")
            return "\n".join(lines)
        finally:
            self._tick_vars = previous_tick_vars
            self._scene_vars = previous_scene_vars

    def _emit_stmt(self, stmt, indent, post_yield_refresh_calls=None):
        pad = "  " * indent
        post_yield_refresh_calls = post_yield_refresh_calls or []

        if isinstance(stmt, Assign):
            return [pad + f"{self._emit_expr(stmt.target)} = {self._emit_expr(stmt.value)};"]

        if isinstance(stmt, CallStmt):
            if stmt.name == "play_animation":
                if len(stmt.args) != 2:
                    raise DSLValidationError(
                        "play_animation call must have exactly 2 arguments."
                    )
                actor_expr = self._emit_expr(stmt.args[0])
                clip_expr = self._emit_expr(stmt.args[1])
                return [
                    pad + "if (ctx.playAnimation) {",
                    pad + f"  ctx.playAnimation({actor_expr}, {clip_expr});",
                    pad + "}",
                ]
            if stmt.name == "destroy_actor":
                if len(stmt.args) != 1:
                    raise DSLValidationError(
                        "destroy_actor call must have exactly 1 argument."
                    )
                actor_expr = self._emit_expr(stmt.args[0])
                return [
                    pad + "if (ctx.destroyActor) {",
                    pad + f"  ctx.destroyActor({actor_expr});",
                    pad + "} else {",
                    pad + f"  {actor_expr}.active = false;",
                    pad + "}",
                ]
            if stmt.name == "scene_set_gravity":
                if len(stmt.args) != 1:
                    raise DSLValidationError(
                        "scene_set_gravity call must have exactly 1 argument."
                    )
                enabled_expr = self._emit_expr(stmt.args[0])
                return [
                    pad + "if (ctx.scene && ctx.scene.setGravityEnabled) {",
                    pad + f"  ctx.scene.setGravityEnabled(Boolean({enabled_expr}));",
                    pad + "}",
                ]
            if stmt.name == "scene_set_interface":
                if len(stmt.args) != 1:
                    raise DSLValidationError(
                        "scene_set_interface call must have exactly 1 argument."
                    )
                html_expr = self._emit_expr(stmt.args[0])
                return [
                    pad + "if (ctx.scene && ctx.scene.setInterfaceHtml) {",
                    pad + f"  ctx.scene.setInterfaceHtml(String({html_expr}));",
                    pad + "}",
                ]
            if stmt.name == "scene_spawn_actor":
                if len(stmt.args) != 3:
                    raise DSLValidationError(
                        "scene_spawn_actor call must have exactly 3 arguments."
                    )
                actor_type_expr = self._emit_expr(stmt.args[0])
                uid_expr = self._emit_expr(stmt.args[1])
                fields_expr = self._emit_spawn_fields_expr(stmt.args[2])
                return [
                    pad + "if (ctx.scene && ctx.scene.spawnActor) {",
                    pad
                    + f"  ctx.scene.spawnActor({actor_type_expr}, {uid_expr}, {fields_expr});",
                    pad + "}",
                ]
            if stmt.name == "scene_next_turn":
                if stmt.args:
                    raise DSLValidationError(
                        "scene_next_turn call must not have arguments."
                    )
                return [
                    pad + "if (ctx.scene && ctx.scene.nextTurn) {",
                    pad + "  ctx.scene.nextTurn();",
                    pad + "}",
                ]
            raise DSLValidationError(f"Unsupported call statement: {stmt.name}")

        if isinstance(stmt, If):
            lines = [pad + f"if ({self._emit_expr(stmt.condition)}) {{"]
            for child in stmt.body:
                lines.extend(
                    self._emit_stmt(
                        child,
                        indent + 1,
                        post_yield_refresh_calls=post_yield_refresh_calls,
                    )
                )
            lines.append(pad + "}")
            if stmt.orelse:
                lines.append(pad + "else {")
                for child in stmt.orelse:
                    lines.extend(
                        self._emit_stmt(
                            child,
                            indent + 1,
                            post_yield_refresh_calls=post_yield_refresh_calls,
                        )
                    )
                lines.append(pad + "}")
            return lines

        if isinstance(stmt, While):
            lines = [pad + f"while ({self._emit_expr(stmt.condition)}) {{"]
            for child in stmt.body:
                lines.extend(
                    self._emit_stmt(
                        child,
                        indent + 1,
                        post_yield_refresh_calls=post_yield_refresh_calls,
                    )
                )
            lines.append(pad + "}")
            return lines

        if isinstance(stmt, For):
            if isinstance(stmt.iterable, Range):
                return self._emit_range_for(
                    stmt,
                    indent,
                    post_yield_refresh_calls=post_yield_refresh_calls,
                )

            lines = [pad + f"for (let {stmt.var} of {self._emit_expr(stmt.iterable)}) {{"]
            for child in stmt.body:
                lines.extend(
                    self._emit_stmt(
                        child,
                        indent + 1,
                        post_yield_refresh_calls=post_yield_refresh_calls,
                    )
                )
            lines.append(pad + "}")
            return lines

        if isinstance(stmt, Yield):
            lines = [pad + f"yield {self._emit_expr(stmt.value)};"]
            for refresh_fn in post_yield_refresh_calls:
                lines.append(pad + f"{refresh_fn}();")
            return lines

        if isinstance(stmt, Continue):
            return [pad + "continue;"]

        raise DSLValidationError(f"Unsupported statement IR node: {type(stmt).__name__}")

    def _collect_assigned_var_names(self, stmts) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()

        def add(name: str) -> None:
            if name in seen:
                return
            seen.add(name)
            ordered.append(name)

        def visit_stmt(stmt) -> None:
            if isinstance(stmt, Assign):
                if isinstance(stmt.target, Var):
                    add(stmt.target.name)
                return
            if isinstance(stmt, If):
                for child in stmt.body:
                    visit_stmt(child)
                for child in stmt.orelse:
                    visit_stmt(child)
                return
            if isinstance(stmt, While):
                for child in stmt.body:
                    visit_stmt(child)
                return
            if isinstance(stmt, For):
                for child in stmt.body:
                    visit_stmt(child)
                return

        for stmt in stmts:
            visit_stmt(stmt)
        return ordered

    def _action_uses_yield(self, action: ActionIR) -> bool:
        return any(self._stmt_contains_yield(stmt) for stmt in action.body)

    def _stmt_contains_yield(self, stmt) -> bool:
        if isinstance(stmt, Yield):
            return True
        if isinstance(stmt, If):
            return any(self._stmt_contains_yield(child) for child in stmt.body) or any(
                self._stmt_contains_yield(child) for child in stmt.orelse
            )
        if isinstance(stmt, While):
            return any(self._stmt_contains_yield(child) for child in stmt.body)
        if isinstance(stmt, For):
            return any(self._stmt_contains_yield(child) for child in stmt.body)
        return False

    def _emit_range_for(self, stmt: For, indent: int, post_yield_refresh_calls=None):
        pad = "  " * indent
        post_yield_refresh_calls = post_yield_refresh_calls or []
        args = stmt.iterable.args
        if len(args) == 1:
            start_expr = "0"
            stop_expr = self._emit_expr(args[0])
            step_expr = "1"
        elif len(args) == 2:
            start_expr = self._emit_expr(args[0])
            stop_expr = self._emit_expr(args[1])
            step_expr = "1"
        elif len(args) == 3:
            start_expr = self._emit_expr(args[0])
            stop_expr = self._emit_expr(args[1])
            step_expr = self._emit_expr(args[2])
        else:
            raise DSLValidationError("Range IR must have between 1 and 3 args.")

        step_var = f"__step_{stmt.var}"
        lines = [pad + f"const {step_var} = {step_expr};"]
        lines.append(
            pad
            + f"for (let {stmt.var} = {start_expr}; "
            + f"{step_var} >= 0 ? {stmt.var} < {stop_expr} : {stmt.var} > {stop_expr}; "
            + f"{stmt.var} += {step_var}) {{"
        )
        for child in stmt.body:
            lines.extend(
                self._emit_stmt(
                    child,
                    indent + 1,
                    post_yield_refresh_calls=post_yield_refresh_calls,
                )
            )
        lines.append(pad + "}")
        return lines

    def _emit_expr(self, expr):
        if isinstance(expr, Const):
            value = expr.value
            if value is None:
                return "null"
            if isinstance(value, bool):
                return "true" if value else "false"
            if isinstance(value, str):
                return json.dumps(value)
            if isinstance(value, (int, float)):
                return repr(value)
            raise DSLValidationError(f"Unsupported constant value: {value!r}")

        if isinstance(expr, Var):
            return expr.name

        if isinstance(expr, Attr):
            tick_vars = getattr(self, "_tick_vars", set())
            if expr.obj in tick_vars and expr.field == "elapsed":
                return "(ctx.elapsed ?? ctx.tick)"
            scene_vars = getattr(self, "_scene_vars", set())
            if expr.obj in scene_vars and expr.field == "elapsed":
                return f"({expr.obj}?.elapsed ?? ctx.elapsed ?? ctx.tick)"
            return f"{expr.obj}.{expr.field}"

        if isinstance(expr, Binary):
            return f"({self._emit_expr(expr.left)} {expr.op} {self._emit_expr(expr.right)})"

        if isinstance(expr, Unary):
            return f"({expr.op}{self._emit_expr(expr.value)})"

        if isinstance(expr, Range):
            raise DSLValidationError("Range expressions are only valid inside for loops.")

        if isinstance(expr, ObjectExpr):
            if not expr.fields:
                return "{}"
            field_chunks = [
                f"{json.dumps(key)}: {self._emit_expr(value)}"
                for key, value in expr.fields.items()
            ]
            return "{ " + ", ".join(field_chunks) + " }"

        if isinstance(expr, ListExpr):
            return "[" + ", ".join(self._emit_expr(item) for item in expr.items) + "]"

        if isinstance(expr, SubscriptExpr):
            value_expr = self._emit_expr(expr.value)
            if isinstance(expr.index, Const) and isinstance(expr.index.value, int):
                if expr.index.value < 0:
                    return f"{value_expr}[{value_expr}.length + ({expr.index.value})]"
            if (
                isinstance(expr.index, Unary)
                and expr.index.op == "-"
                and isinstance(expr.index.value, Const)
                and isinstance(expr.index.value.value, int)
                and not isinstance(expr.index.value.value, bool)
            ):
                neg_index = -int(expr.index.value.value)
                return f"{value_expr}[{value_expr}.length + ({neg_index})]"
            return f"{value_expr}[{self._emit_expr(expr.index)}]"

        if isinstance(expr, CallExpr):
            args = [self._emit_expr(arg) for arg in expr.args]
            if expr.name == "random_int":
                return f"__nc_random_int({args[0]}, {args[1]})"
            if expr.name == "random_bool":
                return "__nc_random_bool()"
            if expr.name == "random_string":
                if len(args) == 1:
                    return f"__nc_random_string({args[0]})"
                if len(args) == 2:
                    return f"__nc_random_string({args[0]}, {args[1]})"
            if expr.name == "random_float_uniform":
                return f"__nc_random_float_uniform({args[0]}, {args[1]})"
            if expr.name == "random_float_normal":
                return f"__nc_random_float_normal({args[0]}, {args[1]})"
            if expr.name.startswith(CALLABLE_EXPR_PREFIX):
                helper_name = expr.name[len(CALLABLE_EXPR_PREFIX) :]
                return f"{helper_name}({', '.join(args)})"
            raise DSLValidationError(f"Unsupported builtin expression call: {expr.name}")

        raise DSLValidationError(f"Unsupported expression IR node: {type(expr).__name__}")

    def _emit_spawn_fields_expr(self, expr) -> str:
        if isinstance(expr, ObjectExpr):
            return self._emit_expr(expr)
        if isinstance(expr, Const) and isinstance(expr.value, str):
            try:
                payload = json.loads(expr.value)
            except json.JSONDecodeError as exc:
                raise DSLValidationError(
                    "scene_spawn_actor fields payload must be valid JSON."
                ) from exc
            if not isinstance(payload, dict):
                raise DSLValidationError(
                    "scene_spawn_actor fields payload must decode to an object."
                )
            return json.dumps(payload)
        raise DSLValidationError(
            "scene_spawn_actor fields payload must be a constant JSON string."
        )
