# LLM Quick Reference

This is the short version for prompt context.  
Full guide: `LLM.md`.

## Authoring Rules

- Write deterministic DSL Python only.
- Do not execute dynamic Python at compile time.
- Use explicit roles and role-scoped conditions.
- Use `@safe_condition` for server-authoritative triggers.
- Use `@unsafe_condition` for client/tool/button/input triggers.

## Core Pattern

```python
class Player(Actor):
    speed: int

def move_right(player: Player["hero"]):
    player.vx = player.speed

game = Game()
scene = Scene(gravity=False)
game.set_scene(scene)
game.add_role(HumanRole(id="human_1", kind=RoleKind.HUMAN, required=True))
scene.add_actor(Player(uid="hero", x=0, y=0, speed=120))
scene.add_rule(KeyboardCondition.on_press("move_right", Role["human_1"]), move_right)
```

## Local Role Variables

- define with `Local[...] = local(...)` in role schema
- available in interface templates as `local.*`
- never trusted server-side

## Build Command

```bash
nanocalibur-build-game ./main.py --project ./nanocalibur-demo
```
