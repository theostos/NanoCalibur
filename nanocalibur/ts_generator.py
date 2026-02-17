import json

from nanocalibur.errors import DSLValidationError
from nanocalibur.ir import (
    ActionIR,
    Assign,
    Attr,
    Binary,
    BindingKind,
    Const,
    For,
    If,
    PredicateIR,
    Range,
    Unary,
    Var,
    While,
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

    def generate_javascript(self, actions, predicates=None):
        predicates = predicates or []
        out = []
        exported_names = []
        for action in actions:
            out.append(self._emit_action(action, typed=False, exported=False))
            exported_names.append(action.name)
        for predicate in predicates:
            out.append(self._emit_predicate(predicate, typed=False, exported=False))
            exported_names.append(predicate.name)
        out.append(f"module.exports = {{ {', '.join(exported_names)} }};")
        return "\n\n".join(out)

    def generate_esm_javascript(self, actions, predicates=None):
        predicates = predicates or []
        out = []
        for action in actions:
            out.append(self._emit_action(action, typed=False, exported=True))
        for predicate in predicates:
            out.append(self._emit_predicate(predicate, typed=False, exported=True))
        return "\n\n".join(out)

    def _emit_prelude_ts(self):
        return """\
export interface GameContext {
  globals: Record<string, any>;
  actors: any[];
  getActorByUid?: (uid: string) => any;
}
"""

    def _emit_action(self, action: ActionIR, typed: bool, exported: bool):
        if typed:
            prefix = "export " if exported else ""
            lines = [f"{prefix}function {action.name}(ctx: GameContext): void {{"]
        else:
            prefix = "export " if exported else ""
            lines = [f"{prefix}function {action.name}(ctx) {{"]

        global_bindings = []
        for param in action.params:
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
                        f"ctx.actors.filter((a{': any' if typed else ''}) => a?.uid === {actor_type});"
                    )
                continue

            selector = param.actor_selector
            if selector is None:
                raise DSLValidationError(f"Actor binding missing selector for '{param.name}'.")
            if selector.index is not None:
                lines.append(f"  let {param.name} = ctx.actors[{selector.index}];")
                continue
            if selector.uid is not None:
                uid = json.dumps(selector.uid)
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

        raise DSLValidationError(f"Unsupported statement IR node: {type(stmt).__name__}")

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

        raise DSLValidationError(f"Unsupported expression IR node: {type(expr).__name__}")
