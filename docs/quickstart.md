# Quickstart

## Install

```bash
python -m pip install -e .
```

Optional docs tooling:

```bash
python -m pip install -e ".[docs]"
```

## First Game

Create `main.py`:

```python
from nanocalibur.dsl_markers import (
    Actor,
    Camera,
    Game,
    HumanRole,
    KeyboardCondition,
    Role,
    RoleKind,
    Scene,
    unsafe_condition,
)


class Player(Actor):
    speed: int


@unsafe_condition(KeyboardCondition.on_press("move_right", Role["human_1"]))
def move_right(player: Player["hero"]):
    player.vx = player.speed


game = Game()
scene = Scene(gravity=False)
game.set_scene(scene)
game.add_role(HumanRole(id="human_1", required=True, kind=RoleKind.HUMAN))
scene.add_actor(Player(uid="hero", x=64, y=64, speed=120))
scene.add_rule(KeyboardCondition.on_press("move_right", Role["human_1"]), move_right)

camera = Camera("cam_h1", Role["human_1"], width=30, height=18)
camera.follow("hero")
scene.add_camera(camera)
```

Build generated runtime:

```bash
nanocalibur-build-game ./main.py --project ./nanocalibur-demo
```

Then run your web app (for the demo project, `cd nanocalibur-demo && npm run build`).

## Draw / Rendering

- Actors render as colored boxes by default.
- Add `Resource` + `Sprite` definitions for sprite-sheet rendering.
- Symbolic rendering is available in headless/session mode.

## Input

- Keyboard/mouse/tool/button conditions are **unsafe** (client-emitted).
- Use role-scoped conditions:
- `KeyboardCondition.on_press("move_up", Role["human_1"])`
- Built-in `HumanRole.keybinds` lets clients remap logical tokens.

## Collisions

- `OnOverlap(A, B)` for overlap checks.
- `OnContact(A, B)` for blocking contact checks.
- Blocking is controlled by `block_mask`.

## Audio

Built-in audio helpers are not part of the current stable DSL surface.
Use browser/web-project level audio for now.
