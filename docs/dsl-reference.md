# DSL Reference

## Core Objects

- `Game`: globals, resources, sprites, roles, multiplayer config, active `Scene`.
- `Scene`: actors, rules, map, cameras, interface, turn progression (`next_turn`).
- `Actor` subclasses: gameplay entities.
- `Role` / `HumanRole` subclasses: player/agent identities and role-owned fields.

## Conditions

Use:

- `@unsafe_condition(...)` for client-triggered input/events:
- `KeyboardCondition.*`
- `MouseCondition.*`
- `OnToolCall(...)`
- `OnButton(...)`
- `@safe_condition(...)` for authoritative server-evaluated conditions:
- `OnOverlap(...)`
- `OnContact(...)`
- `OnLogicalCondition(...)`

`KeyboardCondition`, `MouseCondition`, and `OnToolCall` require a declared role id.

## Role Scoping

Selectors:

- `Role["human_1"]`
- `MyRoleType["human_1"]`

Role bindings are id-based only (no index semantics).

## Local Role Fields

Role fields can be server-owned or client-owned:

- server-owned: normal annotations (`score: int`)
- client-owned: `Local[...]` with `local(...)` initializer

Example:

```python
class HeroRole(HumanRole):
    score: int
    quickbar: Local[List[str]] = local(["dash", "heal"])
```

Rules:

- `Local[...]` is never synchronized to server state.
- `Local[...]` is valid in UI/client logic only.
- using `Local[...]` inside server-authoritative logic raises compile errors.
- `add_role(...)` cannot set local fields.

## HumanRole

Built-in immutable role type:

- `HumanRole`
- local field: `keybinds: Local[Dict[str, str]]`

Default keybinds:

- `move_up -> z`
- `move_left -> q`
- `move_down -> s`
- `move_right -> d`

You can bind conditions to logical tokens:

```python
@unsafe_condition(KeyboardCondition.on_press("move_up", Role["human_1"]))
def move_up(player: Player["hero"]):
    player.vy = -player.speed
```

## Interfaces

Scene-managed and role-scoped:

```python
scene.set_interface(Interface("ui/hud_h1.html", Role["human_1"]))
```

Placeholders:

- `{{__actors_count}}`
- `{{__scene_elapsed}}`
- `{{role.some_server_field}}`
- `{{local.some_local_field}}`

Nested local access works for dict-like values, for example:

- `{{local.keybinds.move_up}}`

## Camera Model

Camera is explicit and role-bound:

```python
cam = Camera("cam_h1", Role["human_1"], width=30, height=18)
cam.follow("hero_1")
scene.add_camera(cam)
```

Runtime camera controls available from actions/callables:

- `camera.follow(uid)`
- `camera.detach()`
- `camera.translate(dx, dy)`
