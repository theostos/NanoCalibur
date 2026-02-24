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

## Runtime Notes

- Interface placeholders work in text and attributes (including boolean `hidden`/`disabled`).
- Actor blocking is `block_mask`-based, with optional same-team moving pass-through when actors expose `can_move=True` and shared `team_id`.
- Actor render scoping supports `view_id` / `view_ids`.
- Symbolic visibility supports `symbolic_visible=False` (or `symbolic=False`) and optional `symbolic_stack=False`.
- Symbolic annotations are actor-driven with:
  - `symbolic_note`
  - `symbolic_note_mode` (`focus`/`alert`/`always`)
  - `symbolic_note_priority`
- Symbolic annotation limits are runtime globals:
  - `symbolic_annotations_max_count`
  - `symbolic_annotations_max_chars`
- Symbolic prefix text can be set at runtime:
  - `symbolic_prefix_text`
  - `symbolic_prefix_max_chars`
  - `symbolic_prefix_text_by_role`
  - `symbolic_prefix_text_by_view`
  - `symbolic_prefix_text_by_role_view`

## Build Command

```bash
nanocalibur-build-game ./main.py --project ./nanocalibur-demo
```
