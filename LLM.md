# LLM Contract: NanoCalibur

Use this as canonical context when generating or editing NanoCalibur games.

## Core Loop and Lifecycle

Per fixed simulation tick:

1. Collect input phases (`begin` / `on` / `end`).
2. Integrate physics.
3. Evaluate rules (`condition -> action`).
4. Apply post-action collision/blocking resolution.
5. Update animation state.
6. Render (browser host) or stream symbolic frame (headless/session).

## Coordinate System and Units

- Origin: top-left of world.
- Axes: `+x` right, `+y` down.
- Actor `x`/`y`: center coordinates in world pixels.
- Velocity `vx`/`vy`: pixels per second.
- `scene.elapsed`: integer tick count.

## Stable Public API (Python)

From `nanocalibur`:

- `compile_project(source, ...)`
- `export_project(source, output_dir, ...)`
- `project_to_dict(project)`
- `project_to_ir_dict(project)`
- `about(print_output=True)`
- `__version__`

From `nanocalibur.dsl_markers` (authoring DSL):

- Core: `Game`, `Scene`, `Actor`, `Role`, `HumanRole`, `RoleKind`
- Map/camera/ui: `TileMap`, `Tile`, `Color`, `Camera`, `Interface`
- Assets: `Resource`, `Sprite`
- Conditions: `KeyboardCondition`, `MouseCondition`, `OnOverlap`, `OnContact`, `OnLogicalCondition`, `OnToolCall`, `OnButton`
- Decorators/helpers: `safe_condition`, `unsafe_condition`, `callable`, `Local`, `local`, `Global`, `GlobalVariable`

## Safety and Ownership Rules

- Use `@safe_condition(...)` for authoritative server checks:
- `OnOverlap`, `OnContact`, `OnLogicalCondition`
- Use `@unsafe_condition(...)` for client/tool-originated events:
- `KeyboardCondition`, `MouseCondition`, `OnToolCall`, `OnButton`
- Role id scoping is mandatory for keyboard/mouse/tool conditions.
- `Local[...]` role fields are client-owned and not authoritative server state.

## Do / Don’t

Do:

- Keep role scoping explicit (`Role["human_1"]`).
- Keep cameras explicit and role-bound (`Camera("name", Role["id"])` + `scene.add_camera(...)`).
- Use deterministic, simple rules.
- Keep setup in `CodeBlock` when strict boxing is enabled.

Don’t:

- Don’t use removed APIs (`@condition`, `scene.set_camera`, `game.set_camera`).
- Don’t use role index selectors.
- Don’t read `Local[...]` fields in authoritative server logic.
- Don’t assume client state is trusted.

## Copy-Paste Templates

### 1) Minimal Game

```python
from nanocalibur.dsl_markers import *

class Player(Actor):
    speed: int

def move_right(player: Player["hero"]):
    player.vx = player.speed

game = Game()
scene = Scene(gravity=False)
game.set_scene(scene)
game.add_role(HumanRole(id="human_1", required=True, kind=RoleKind.HUMAN))
scene.add_actor(Player(uid="hero", x=64, y=64, speed=120))
scene.add_rule(KeyboardCondition.on_press("move_right", Role["human_1"]), move_right)
cam = Camera("cam_h1", Role["human_1"], width=30, height=18)
cam.follow("hero")
scene.add_camera(cam)
```

### 2) Sprite + Resource

```python
game.add_resource(Resource("hero_sheet", "img/hero.png"))
game.add_sprite(
    Sprite(
        name="hero",
        resource=Resource["hero_sheet"],
        frame_width=16,
        frame_height=16,
        default_clip="idle",
        clips={"idle": {"frames": [0, 1, 2, 3], "ticks_per_frame": 8, "loop": True}},
        symbol="@",
        description="hero",
    )
)
```

### 3) Input + Safe Collision Rule

```python
@unsafe_condition(KeyboardCondition.on_press("move_up", Role["human_1"]))
def move_up(player: Player["hero"]):
    player.vy = -player.speed

@safe_condition(OnOverlap(Player["hero"], Coin))
def collect(hero: Player, coin: Coin, score: Global["global_score", int]):
    if coin.active:
        coin.destroy()
        score = score + 1
```

## Build Command

```bash
nanocalibur-build-game ./main.py --project ./nanocalibur-demo
```
