import json

from nanocalibur.errors import DSLValidationError
from nanocalibur.ir import (
    ActionIR,
    Assign,
    Attr,
    Binary,
    BindingKind,
    CallExpr,
    CallStmt,
    Const,
    For,
    If,
    ObjectExpr,
    PredicateIR,
    Range,
    Unary,
    Var,
    While,
    Yield,
)


class TSGenerator:
    def generate(
        self,
        actions,
        predicates=None,
    ):
        predicates = predicates or []
        out = [self._emit_prelude_ts()]
        for action in actions:
            out.append(self._emit_action(action, typed=True, exported=True))
        for predicate in predicates:
            out.append(self._emit_predicate(predicate, typed=True, exported=True))
        return "\n\n".join(out)

    def _emit_prelude_ts(self):
        return """\
export interface RuntimeSceneContext {
  gravityEnabled?: boolean;
  setGravityEnabled?: (enabled: boolean) => void;
  spawnActor?: (actorType: string, uid: string, fields?: Record<string, any>) => any;
}

export interface GameContext {
  globals: Record<string, any>;
  actors: any[];
  tick: number;
  getActorByUid?: (uid: string) => any;
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

    def _emit_action(self, action: ActionIR, typed: bool, exported: bool):
        is_generator = self._action_uses_yield(action)
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
            if selector.index is not None:
                index_value = selector.index
                if param.actor_type is not None:
                    actor_type = json.dumps(param.actor_type)
                    filtered_var = f"__actors_{param.name}"
                    lines.append(
                        f"  const {filtered_var} = "
                        f"ctx.actors.filter((a{': any' if typed else ''}) => a?.type === {actor_type});"
                    )
                    if index_value >= 0:
                        lines.append(f"  let {param.name} = {filtered_var}[{index_value}];")
                    else:
                        lines.append(
                            f"  let {param.name} = {filtered_var}[{filtered_var}.length + ({index_value})];"
                        )
                    continue

                if index_value >= 0:
                    lines.append(f"  let {param.name} = ctx.actors[{index_value}];")
                else:
                    lines.append(
                        f"  let {param.name} = ctx.actors[ctx.actors.length + ({index_value})];"
                    )
                continue
            if selector.uid is not None:
                uid = json.dumps(selector.uid)
                if param.actor_type is not None and selector.uid == param.actor_type:
                    actor_type = json.dumps(param.actor_type)
                    lines.append(
                        f"  let {param.name} = "
                        f"ctx.actors.find((a{': any' if typed else ''}) => a?.type === {actor_type});"
                    )
                    continue
                lines.append(
                    f"  let {param.name} = "
                    f"(ctx.getActorByUid ? ctx.getActorByUid({uid}) : "
                    f"ctx.actors.find((a{': any' if typed else ''}) => a?.uid === {uid}));"
                )
                continue
            raise DSLValidationError(f"Unsupported actor selector for '{param.name}'.")

        for stmt in action.body:
            lines.extend(self._emit_stmt(stmt, indent=1))

        for param_name, global_name in global_bindings:
            lines.append(f'  ctx.globals[{json.dumps(global_name)}] = {param_name};')

        lines.append("}")
        return "\n".join(lines)

    def _emit_predicate(self, predicate: PredicateIR, typed: bool, exported: bool):
        if typed:
            prefix = "export " if exported else ""
            lines = [
                f"{prefix}function {predicate.name}({predicate.param_name}: any): boolean {{"
            ]
        else:
            prefix = "export " if exported else ""
            lines = [f"{prefix}function {predicate.name}({predicate.param_name}) {{"]
        lines.append(f"  return {self._emit_expr(predicate.body)};")
        lines.append("}")
        return "\n".join(lines)

    def _emit_stmt(self, stmt, indent):
        pad = "  " * indent

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
            raise DSLValidationError(f"Unsupported call statement: {stmt.name}")

        if isinstance(stmt, If):
            lines = [pad + f"if ({self._emit_expr(stmt.condition)}) {{"]
            for child in stmt.body:
                lines.extend(self._emit_stmt(child, indent + 1))
            lines.append(pad + "}")
            if stmt.orelse:
                lines.append(pad + "else {")
                for child in stmt.orelse:
                    lines.extend(self._emit_stmt(child, indent + 1))
                lines.append(pad + "}")
            return lines

        if isinstance(stmt, While):
            lines = [pad + f"while ({self._emit_expr(stmt.condition)}) {{"]
            for child in stmt.body:
                lines.extend(self._emit_stmt(child, indent + 1))
            lines.append(pad + "}")
            return lines

        if isinstance(stmt, For):
            if isinstance(stmt.iterable, Range):
                return self._emit_range_for(stmt, indent)

            lines = [pad + f"for (let {stmt.var} of {self._emit_expr(stmt.iterable)}) {{"]
            for child in stmt.body:
                lines.extend(self._emit_stmt(child, indent + 1))
            lines.append(pad + "}")
            return lines

        if isinstance(stmt, Yield):
            return [pad + f"yield {self._emit_expr(stmt.value)};"]

        raise DSLValidationError(f"Unsupported statement IR node: {type(stmt).__name__}")

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

    def _emit_range_for(self, stmt: For, indent: int):
        pad = "  " * indent
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
            lines.extend(self._emit_stmt(child, indent + 1))
        lines.append(pad + "}")
        return lines

    def _emit_expr(self, expr):
        if isinstance(expr, Const):
            value = expr.value
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
