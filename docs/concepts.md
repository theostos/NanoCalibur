# Concepts

## Engine Model

NanoCalibur separates authoring and runtime:

1. Author a constrained Python DSL.
2. Compile to deterministic IR/spec.
3. Execute generated runtime in browser or headless mode.

## Coordinate System and Units

- Origin: top-left of world/map.
- Axis: +x to the right, +y downward.
- Position: actor `x`/`y` represent actor center in world pixels.
- Velocity: `vx`/`vy` in pixels per second.
- Runtime timestep: fixed-step seconds in runtime core.
- Scene elapsed: integer tick count (`scene.elapsed`).

## Lifecycle and Order

Per simulation tick:

1. Gather input phases (`begin`/`on`/`end`).
2. Integrate physics.
3. Evaluate rules and run actions.
4. Resolve post-action collisions/constraints.
5. Update animation state.
6. Render frame (browser host).

## Safe vs Unsafe Conditions

- Safe: server-authoritative (`OnOverlap`, `OnContact`, `OnLogicalCondition`).
- Unsafe: client/tool-originated (`KeyboardCondition`, `MouseCondition`, `OnToolCall`, `OnButton`).

Use:

- `@safe_condition(...)`
- `@unsafe_condition(...)`

## State Ownership

- Server-authoritative:
- globals
- actors
- server role fields
- physics and safe-condition evaluation
- Client-local:
- role `Local[...]` fields (for UI/input mapping)

Local role values are not trusted server state.

## Roles, Cameras, and Views

- Roles are explicit multiplayer slots.
- Cameras are explicit objects, bound to roles.
- Human roles without cameras trigger compile warnings.
- AI roles without cameras receive empty symbolic grids.

## Patterns

- Prefer small actions and explicit rule bindings.
- Use role-scoped interfaces for per-player HUDs.
- Use `@callable` helpers for reusable expressions inside actions/predicates.
- Keep DSL deterministic and side-effect constrained.
