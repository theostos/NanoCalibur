# NanoCalibur LLM Guide (Canonical)

This file is the canonical context for coding assistants working on NanoCalibur games.
It is intentionally practical: what exists, how to use it, what is authoritative, and what fails at compile time.

## 1) What NanoCalibur Is

NanoCalibur is a deterministic 2D game engine pipeline with:

1. A Python DSL for authoring game logic.
2. An AST compiler (your Python is parsed, not executed).
3. Generated TypeScript runtime assets (`game_spec.json`, action/predicate TS, runtime glue).
4. Runtime targets:
- Browser canvas (human play)
- Headless/session HTTP runtime (LLM, bots, remote players)
- Symbolic rendering for LLM-friendly frame access

Design goal: easy game authoring, multiplayer-by-default architecture, and first-class remote agent integration.

## 2) Mental Model

Think in three layers:

1. Authoring layer (Python DSL): declare schemas, rules, assets, roles, maps, cameras, interface.
2. Compile layer (AST): validates and emits deterministic IR/spec; unsupported constructs fail compilation.
3. Runtime layer (TS): runs physics, rule evaluation, sessions, role-scoped views, rendering.

## 3) Deterministic Runtime Semantics

### Coordinate system and units

- Origin: top-left.
- Axis: `+x` to the right, `+y` down.
- Actor `x`/`y`: center position in world pixels.
- `vx`/`vy`: pixels per second.
- `scene.elapsed`: integer tick counter.

### Tick order (fixed-step)

Per simulation step:

1. Gather inputs/events (keyboard/mouse/tool/button payloads).
2. Integrate physics.
3. Evaluate rules and execute matching actions.
4. Resolve post-action collisions/constraints.
5. Update animation/render output.

### Physics/collision essentials

- Blocking uses `block_mask`.
- `OnOverlap` detects overlap.
- `OnContact` tracks blocking contact (same `block_mask` group behavior).
- Runtime skip rule: if two actors both expose `can_move=True`, have the same `team_id`, and at least one has moving intent (`path_active` or non-zero velocity), actor-vs-actor separation/contact is skipped for that pair.
- Parent attachment exists (`parent` field + attach/detach helpers).

## 4) Public API Surface (Stable)

Primary Python entrypoints (`nanocalibur`):

- `compile_project(source: str, ...)`
- `export_project(source: str, output_dir: str, ...)`
- `project_to_dict(project)`
- `project_to_ir_dict(project)`
- `about(print_output=True)`
- `__version__`

DSL authoring symbols (`nanocalibur.dsl_markers`):

- Core: `Game`, `Scene`, `Actor`, `Role`, `HumanRole`, `RoleKind`
- State bindings: `Global`, `GlobalVariable`, `Local`, `local`
- Assets/map: `Resource`, `Sprite`, `TileMap`, `Tile`, `Color`
- View/UI: `Camera`, `View`, `Interface`
- Multiplayer: `Multiplayer`
- Conditions: `KeyboardCondition`, `MouseCondition`, `ButtonCondition`, `OnOverlap`, `OnContact`, `OnLogicalCondition`, `OnToolCall`
- Rule decorators: `safe_condition`, `unsafe_condition`
- Helpers: `callable`, `Random`, `Tick`, `CodeBlock`, `AbstractCodeBlock`

## 5) Authoring Rules You Must Follow

### 5.1 AST-driven, not Python runtime

Your source is parsed by AST. The compiler does not execute arbitrary Python code. Use DSL constructs and static expressions.

### 5.2 Immutable engine classes

Do not monkey-patch or redefine core DSL classes (`Actor`, `Scene`, `Game`, `Sprite`, etc.).
If you need extra fields, create subclasses.
Compiler warns and ignores illegal additions.

### 5.3 Safety decorators are explicit

Use
- `@safe_condition(...)` for authoritative server-evaluated conditions.
- `@unsafe_condition(...)` for client-originated triggers.

Mismatch between decorator and condition kind is a compile error.

### 5.4 Function declarations: use `def`, not `lambda`

For DSL logic, use named functions with decorators:

- actions: `@safe_condition(...)` or `@unsafe_condition(...)`
- helper callables: `@callable`

`lambda` is not supported for DSL rule/callable declarations. Write a normal `def`.

### 5.5 Undecorated top-level functions are ignored

A top-level function with no DSL decorator is ignored by the compiler (warning emitted).
If you want it compiled, decorate it with:

- `@safe_condition(...)` or `@unsafe_condition(...)` for rules
- `@callable` for helper callable functions

## 6) Game Structure: Game + Scene

- `Game` owns globals, resources, sprites, roles, multiplayer config, active scene.
- `Scene` owns actors, rules, map, cameras, interfaces, gravity toggle, spawning, turn progression (`next_turn`).

Minimal setup:

```python
from nanocalibur.dsl_markers import *

class Player(Actor):
    speed: int


game = Game()
scene = Scene(gravity=False)
game.set_scene(scene)
game.add_role(HumanRole(id="human_1", required=True, kind=RoleKind.HUMAN))
scene.add_actor(Player(uid="hero", x=64, y=64, speed=120))
```

## 7) Schemas and Types

### 7.1 Actor schemas

```python
class Player(Actor):
    speed: int
    inventory: dict[str, int]
```

### 7.2 Role schemas

```python
class HeroRole(HumanRole):
    score: int
    quickbar: Local[list[str]] = local(["dash", "heal"])
```

### 7.3 Supported field types

For actor/role/global declarations:

- Primitive: `int`, `float`, `str`, `bool`
- Containers: `list[...]`, `dict[str, ...]`
- Nested containers supported (for example `dict[str, list[int]]`)

If unsupported types/operations are used, compiler raises explicit errors.

## 8) Bindings and Selectors

### 8.1 Action/predicate parameter bindings

Common forms:

- `Player["hero"]`, `Coin["coin_1"]`
- `Player` (type selector)
- `List[Actor]` (all actor instances)
- `List[Player]` / `List[Unit]` (all instances of that exact actor schema)
- `Player[-1]` (special selector usage where supported)
- `Role["human_1"]`, `HeroRole["human_1"]`
- `Camera["camera_h1"]`
- `Global["global_score", int]`
- `Scene`
- `Tick`

Tick helpers:

- `tick.wait_tick(k)` in action bodies: pauses current action for `k` ticks.
- `tick_to_second(ticks)` in action/predicate expressions.
- `second_to_tick(seconds)` in action/predicate expressions.
- `Tick` is not allowed as a `@callable` parameter type.
- `tick_to_second` / `second_to_tick` are currently not allowed inside `@callable` helpers.

Example:

```python
@unsafe_condition(KeyboardCondition.begin_press("space", Role["human_1"]))
def dash_with_delay(hero: Player["hero_1"], tick: Tick):
    hero.vx = 300
    tick.wait_tick(6)  # equivalent to: for _ in range(6): yield tick
    hero.vx = 0
```

### 8.1.1 Actor list bindings (selector + type)

You can bind a function argument to a list of actors directly:

- `actors: List[Actor]` -> all actors in scene state.
- `units: List[Unit]` -> actors whose runtime type is exactly `Unit`.

This works in action/predicate/callable parameter bindings.

Example:

```python
@safe_condition(OnOverlap(Player["hero"], Coin))
def collect_coin_for_any_unit(
    units: List[Unit],
    coin: Coin,
):
    if len(units) > 0 and coin.active:
        coin.destroy()
```

Important:

- `List[Unit]` is exact schema filtering (not automatic polymorphic expansion to all subclasses).
- Multi-level actor inheritance is supported for schema declarations (subclass of subclass of `Actor` is valid).

### 8.2 Selector conventions

- Role selectors are id-based only (no role index semantics).
- Use explicit names for camera and role selectors.

## 9) Conditions and Rule Model

Rules are `condition -> action`.

### 9.1 Unsafe conditions (client/tool originated)

- `KeyboardCondition.begin_press(...)`
- `KeyboardCondition.on_press(...)`
- `KeyboardCondition.end_press(...)`
- `MouseCondition.begin_click(...)`
- `MouseCondition.on_click(...)`
- `MouseCondition.end_click(...)`
- `OnToolCall(...)`
- `ButtonCondition.begin(...)` / `ButtonCondition.on(...)` / `ButtonCondition.end(...)`
- `MouseCondition.*(..., view=View["..."])` for view-scoped pointer input
- `ButtonCondition.*(..., view=View["..."])` for view-scoped UI button input

Use `@unsafe_condition(...)`.

### 9.2 Safe conditions (authoritative)

- `OnOverlap(...)`
- `OnContact(...)`
- `OnLogicalCondition(...)`

Use `@safe_condition(...)`.

### 9.3 Role scoping requirement

For keyboard/mouse/tool conditions, role must be explicit and declared.
Preferred form:

```python
KeyboardCondition.on_press("move_right", Role["human_1"])
OnToolCall("bot_move_right", Role["dummy_1"])
```

Legacy `id="..."` may still parse for compatibility, but role-selector form is preferred.

### 9.4 Tool descriptions from docstrings

`OnToolCall` description comes from the bound action docstring.
If missing, compiler warns loudly.

```python
@unsafe_condition(OnToolCall("bot_move_right", Role["dummy_1"]))
def bot_move_right(bot: Player["llm_dummy"]):
    """Move dummy bot right."""
    bot.vx = bot.speed
```

## 10) Expressions and Statements Inside Actions

Supported in action/predicate/callable bodies:

- Assignment / annotated assignment
- `if` / `while` / `for`
- `continue`
- arithmetic/comparison/boolean ops (compiler-supported subset)
- list/dict literals
- list/dict/string operations in supported subset (`append`, `pop`, `concat`, `+`, etc.)
- actor methods: `play`, `destroy`, `attached_to`, `detached`
- camera methods: `follow`, `detach`, `translate`
- scene methods: `spawn`, `next_turn`, gravity toggles

Unsupported syntax raises compile-time `DSLValidationError`.

## 11) Top-Level Setup Expressions (Outside Action Bodies)

Top-level setup supports static evaluation and expansion for common deterministic patterns:

- assignments and updates
- `if`/`for`/`while` with statically evaluable conditions/iterables
- f-strings and string composition in setup context

Example:

```python
for k in range(1, 5):
    game.add_role(Role(id=f"human_{k}", required=(k == 1), kind=RoleKind.HUMAN))
```

Use this for concise role/resource/entity setup.

## 12) Assets and Rendering

### 12.1 Resources and sprites

```python
game.add_resource(Resource("hero_sheet", "img/hero.png"))

game.add_sprite(
    Sprite(
        name="hero",
        resource=Resource["hero_sheet"],
        frame_width=16,
        frame_height=16,
        default_clip="idle",
        symbol="@",
        description="main hero",
        clips={
            "idle": {"frames": [0, 1, 2, 3], "ticks_per_frame": 8, "loop": True},
            "run": {"frames": [8, 9, 10, 11], "ticks_per_frame": 6, "loop": True},
        },
    )
)
```

Assign actor sprite by selector/name in actor instance fields.

Fallback constructors:

```python
game.add_sprite(
    BlockInSprite(
        name="hero",
        resource=Resource["hero_sheet"],
        frame_width=16,
        frame_height=16,
        color=Color(24, 140, 255, description="hero fallback box"),
        default_clip="idle",
        clips={"idle": [0]},
    )
)

game.add_sprite(
    ColorSprite(
        name="coin",
        frame_width=16,
        frame_height=16,
        color=Color(255, 210, 0, description="coin as color box"),
        symbol="$",
        description="coin",
    )
)
```

- `BlockInSprite`: if `resource` is not declared in `game.add_resource(...)`, compiler warns and falls back to colored box rendering.
- `ColorSprite`: pure colored box sprite (no resource/clips).
- For fallback sprites, provide `description` for better symbolic/LLM output.

### 12.2 Map and tiles

```python
scene.set_map(
    TileMap(
        tile_size=16,
        grid=[[1, 1, 1], [1, 0, 1], [1, 1, 1]],
        tiles={
            1: Tile(block_mask=2, color=Color(40, 40, 40, symbol="#", description="wall")),
        },
    )
)
```

### 12.3 Symbolic visibility and annotations

Symbolic rendering now supports actor-level visibility controls and bounded annotation text.

Actor-side fields used by the runtime:

- `view_id: str` or `view_ids: list[str]`
  - restricts where the actor is rendered (main/minimap or any custom view ids).
- `symbolic_visible: bool` (or `symbolic: bool`)
  - `False` hides actor from symbolic output while keeping normal canvas rendering.
- `symbolic_stack: bool`
  - `False` excludes actor from `frame.stacks`.
- `symbolic_id: str`
  - stable symbolic identifier emitted in both annotations and stacks.
- `symbolic_note: str`
  - short per-actor note shown in symbolic output.
- `symbolic_note_priority: int`
  - numeric ordering for annotation selection (higher first).

Symbolic frame payload includes:

- `rows`
- `legend`
- `stacks`
- `annotations` (root and per-view subframes)
- `prefix` (optional top-of-frame instruction text)

Annotation anti-flood limits can be tuned at runtime via authoritative globals:

- `symbolic_annotations_max_count`
- `symbolic_annotations_max_chars`

Symbolic prefix text can be tuned at runtime via authoritative globals:

- `symbolic_prefix_text`
- `symbolic_prefix_max_chars`

Symbolic prefix can also be scoped:

- by role globals: `symbolic_prefix_text_by_role` (dict role_id -> text)
- by view globals: `symbolic_prefix_text_by_view` (dict view_id -> text)
- by role+view globals: `symbolic_prefix_text_by_role_view` (nested dict or flat key map)
- by role fields: `role.symbolic_prefix_text`, `role.symbolic_prefix_by_view`

If globals are missing, renderer falls back to runtime defaults/options.

## 13) Cameras and Views (Role-Scoped by Design)

Camera is explicit and bound to a role.

```python
cam = Camera("camera_h1", Role["human_1"], width=30, height=18)
cam.follow("hero_1")
scene.add_camera(cam)
```

Runtime camera control in actions/callables:

```python
@callable
def shake(cam: Camera["camera_h1"]):
    cam.detach()
    cam.translate(4, 0)
```

Notes:

- Human role without camera triggers compile warning.
- AI role requesting frame without camera receives empty grid.
- Views map screen regions to cameras (for example main viewport + minimap).
- Actors with no `view_id`/`view_ids` render in all views; set these fields when you need strict view partitioning.

```python
scene.add_view(View("main", Role["human_1"], camera=Camera["camera_h1"]))
scene.add_view(
    View(
        "minimap",
        Role["human_1"],
        camera=Camera["camera_h1_minimap"],
        x=0.78,
        y=0.72,
        width=0.20,
        height=0.24,
        z=5,
    )
)
```

## 14) Interfaces (Role-Scoped + Dynamic)

Interface is scene-managed and can be changed at runtime.

### 14.1 Static setup

```python
scene.set_interface(Interface("ui/hud_h1.html", Role["human_1"]))
scene.set_interface(Interface("ui/minimap_overlay.html", Role["human_1"], View["minimap"]))
```

Inline HTML:

```python
scene.set_interface(
    Interface(
        """
<div>
  <div>Actors: {{__actors_count}}</div>
  <div>Global: {{global_score}}</div>
  <div>Role score: {{role.score}}</div>
  <div>Move up key: {{local.keybinds.move_up}}</div>
</div>
""",
        Role["human_1"],
        from_file=False,
    )
)
```

### 14.2 Dynamic interface changes

You can call `scene.set_interface(...)` inside an action to swap UI state during play.

### 14.3 UI button events

`ButtonCondition.begin("name")` fires when UI emits matching button event (`data-button="name"`).
For view-specific panels, scope conditions with `view=View["..."]`.

### 14.4 Attribute placeholders

Template placeholders work in text nodes and HTML attributes.

- Standard placeholders: `{{global_like_path}}`, `{{role.some_field}}`, `{{local.some_field}}`
- Boolean attributes such as `hidden` and `disabled` are interpreted as booleans from rendered values.
- This enables direct UI state wiring such as:
  - `hidden="{{role.hide_train_worker}}"`
  - `disabled="{{role.disable_train_worker}}"`

## 15) Local vs Authoritative State

### 15.1 Authoritative (server-owned)

- globals
- actors and physics
- server role fields (normal role attributes)
- safe-condition evaluation

### 15.2 Local (client-owned)

- role fields declared as `Local[...]`
- not stored/synchronized by authoritative server state
- intended for UI/input mapping

Compiler guardrail:

- Using `Local[...]` in authoritative server logic causes compile error.

## 16) HumanRole Keybinds (Built-in Local State)

`HumanRole` includes:

- `keybinds: Local[dict[str, str]]`

Default values:

- `move_up: z`
- `move_left: q`
- `move_down: s`
- `move_right: d`

Use logical actions in conditions:

```python
@unsafe_condition(KeyboardCondition.on_press("move_up", Role["human_1"]))
def move_up(player: Player["hero_1"]):
    player.vy = -player.speed
```

Client can remap logical tokens locally through UI/client layer without changing server-authoritative logic.

## 17) Multiplayer Configuration and Turn Semantics

Configure multiplayer defaults with `game.set_multiplayer(...)`.

```python
game.set_multiplayer(
    Multiplayer(
        default_loop="hybrid",
        allowed_loops=["turn_based", "hybrid", "real_time"],
        tick_rate=20,
        turn_timeout_ms=15000,
        hybrid_window_ms=600,
        game_time_scale=0.75,
        max_catchup_steps=1,
    )
)
```

Loop modes:

- `real_time`: regular fixed-step tick progression.
- `turn_based`: turn advances only when an action calls `scene.next_turn()`.
- `hybrid`: command window + explicit turn advance via `scene.next_turn()`.

Compile rule:

- If default loop is `turn_based` or `hybrid`, at least one action must call `scene.next_turn()`.

## 18) Sessions, Seeds, and Pacing

Session runtime is HTTP-based and multiplayer oriented.

- Sessions have a seed.
- If seed omitted, server generates one.
- Seeds are unique per session and persisted for replay.
- Pacing can be updated live (`PATCH /sessions/{id}/pace`).

Key endpoints:

- `POST /sessions`
- `POST /join`
- `POST /sessions/{id}/start`
- `POST /sessions/{id}/commands`
- `GET /sessions/{id}/stream`
- `GET /sessions/{id}/frame`
- `GET /sessions/{id}/state`

## 19) CodeBlock / AbstractCodeBlock Workflow

`build_game` defaults to strict code boxing:

- non-import top-level statements outside a `CodeBlock` are ignored with warnings
- disable with `--allow-unboxed`

### 19.1 CodeBlock

```python
CodeBlock.begin("player_controls")
"""Movement rules for the main hero."""

@unsafe_condition(KeyboardCondition.on_press("move_right", Role["human_1"]))
def move_right(player: Player["hero_1"]):
    player.vx = player.speed

CodeBlock.end("player_controls")
```

### 19.2 AbstractCodeBlock

`AbstractCodeBlock` is a compile-time template system.
Think of it as a macro with typed placeholders (`role=Role`, `hero=Player`, `key_up=str`, ...).
`instantiate(...)` duplicates the template logic with constant substitutions.

Small example:

```python
controls = AbstractCodeBlock.begin(
    "controls_template",
    role=Role,
    hero=Player,
    key_right=str,
)
"""Reusable right-move control block."""

@unsafe_condition(KeyboardCondition.on_press(controls.key_right, controls.role))
def move_right(player: controls.hero):
    player.vx = player.speed

AbstractCodeBlock.end("controls_template")

AbstractCodeBlock.instantiate(
    "controls_template",
    role=Role["human_1"],
    hero=Player["hero_1"],
    key_right="d",
)
```

After instantiation, this behaves as if you wrote a concrete `move_right` rule for `human_1`/`hero_1`.

```python
controls = AbstractCodeBlock.begin(
    "human_controls",
    role=Role,
    hero=Player,
    key_up=str,
    key_down=str,
)
"""Reusable controls block."""

@unsafe_condition(KeyboardCondition.on_press(controls.key_up, controls.role))
def go_up(player: controls.hero):
    player.vy = -player.speed

@unsafe_condition(KeyboardCondition.on_press(controls.key_down, controls.role))
def go_down(player: controls.hero):
    player.vy = player.speed

AbstractCodeBlock.end("human_controls")

AbstractCodeBlock.instantiate(
    "human_controls",
    role=Role["human_1"],
    hero=Player["hero_1"],
    key_up="move_up",
    key_down="move_down",
)
```

Rules:

- begin/end must match.
- block and abstract block require informal docstring descriptions.
- uninstantiated abstract blocks warn.

## 20) Minimal Templates (Copy/Paste)

### A) Minimal playable setup

```python
from nanocalibur.dsl_markers import *

class Player(Actor):
    speed: int

@unsafe_condition(KeyboardCondition.on_press("move_right", Role["human_1"]))
def move_right(player: Player["hero"]):
    player.vx = player.speed

@unsafe_condition(KeyboardCondition.end_press("move_right", Role["human_1"]))
def stop_x(player: Player["hero"]):
    player.vx = 0


game = Game()
scene = Scene(gravity=False)
game.set_scene(scene)
game.add_role(HumanRole(id="human_1", required=True, kind=RoleKind.HUMAN))
scene.add_actor(Player(uid="hero", x=64, y=64, speed=120))
cam = Camera("cam_h1", Role["human_1"], width=24, height=16)
cam.follow("hero")
scene.add_camera(cam)
```

### B) Safe collision + global score

```python
class Coin(Actor):
    pass

@safe_condition(OnOverlap(Player["hero"], Coin))
def collect(hero: Player, coin: Coin, global_score: Global["global_score", int]):
    if coin.active:
        coin.destroy()
        global_score = global_score + 1


game.add_global("global_score", 0)
scene.add_actor(Coin(uid="coin_1", x=96, y=64))
```

### C) LLM tool-controlled bot

```python
class Bot(Actor):
    speed: int

@unsafe_condition(OnToolCall("bot_move_left", Role["dummy_1"]))
def bot_move_left(bot: Bot["bot_1"]):
    """Move bot left."""
    bot.vx = -bot.speed


game.add_role(Role(id="dummy_1", required=False, kind=RoleKind.AI))
scene.add_actor(Bot(uid="bot_1", x=200, y=64, speed=100))
```

### D) Turn-based action

```python
def act(player: Player["hero"], scene: Scene):
    player.x = player.x + 16
    scene.next_turn()

scene.add_rule(KeyboardCondition.on_press("act", Role["human_1"]), act)
game.set_multiplayer(Multiplayer(default_loop="turn_based", allowed_loops=["turn_based"]))
```

### E) Role-scoped HUD with local + server fields

```python
class HeroRole(HumanRole):
    score: int


game.add_role(HeroRole(id="human_1", required=True, kind=RoleKind.HUMAN, score=0))

scene.set_interface(
    Interface(
        """
<div>
  <div>Role score: {{role.score}}</div>
  <div>Global score: {{global_score}}</div>
  <div>Up: {{local.keybinds.move_up}}</div>
</div>
""",
        Role["human_1"],
        from_file=False,
    )
)
```

## 21) Security Model (Practical)

- Safe conditions are evaluated against authoritative server state/physics.
- Unsafe conditions are client/tool-originated and must be treated as untrusted triggers.
- Clients cannot directly mutate authoritative state; they submit commands/events.
- Server state is broadcast/scoped back to clients.
- Role-scoped state views are enforced in session API responses.

## 22) Build and Run

Build from entry file with local imports:

```bash
nanocalibur-build-game ./main.py --project ./nanocalibur-demo
```

Strict boxing is default. To keep unboxed top-level statements:

```bash
nanocalibur-build-game ./main.py --project ./nanocalibur-demo --allow-unboxed
```

## 23) LLM Agent Working Rules (Recommended)

When generating/modifying game code:

1. Prefer explicit role-scoped conditions and cameras.
2. Use `safe_condition` only for server-authoritative triggers.
3. Keep game state authoritative unless clearly UI/client-local (`Local[...]`).
4. Use `CodeBlock`/`AbstractCodeBlock` for maintainable modular logic.
5. Keep setup deterministic; expect compile-time errors for unsupported syntax.
6. Never manually edit generated TS as source-of-truth; edit Python DSL and rebuild.

## 24) Common Compile Errors and Fixes

- Unknown role in keyboard/mouse/tool condition:
  - Add matching `game.add_role(...)` or fix selector id.
- `turn_based`/`hybrid` without `scene.next_turn()`:
  - Add explicit `scene.next_turn()` in at least one action.
- Missing OnToolCall description:
  - Add action docstring.
- Local field used in authoritative logic:
  - Move usage to UI/client logic or convert to server role/global field.
- Statement ignored outside CodeBlock:
  - Wrap in `CodeBlock.begin/end` or build with `--allow-unboxed`.

---

If you need a very short context for prompts, use `docs/llm-quick-reference.md`.
