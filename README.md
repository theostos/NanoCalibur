# NanoCalibur

NanoCalibur is a deterministic Python DSL compiler for tiny 2D games.

Core guarantees:
- Python source is parsed with `ast` and never executed.
- Only a restricted DSL subset is accepted.
- Compilation is deterministic (`AST -> IR -> TS + JSON spec`).

## Repository Structure

```text
nanocalibur/
  compiler.py          # Action + predicate compiler (AST -> IR)
  project_compiler.py  # Full game project compiler
  exporter.py          # JSON + TS export pipeline
  ts_generator.py      # IR -> TypeScript codegen
  dsl_markers.py       # Marker classes/helpers for DSL authoring
  runtime/
    interpreter.ts     # Runtime rule interpreter
    canvas_host.ts     # Standalone canvas runtime host
    canvas/            # Physics, renderer, assets, animation modules
  build_game.py        # Python main.py + local imports -> web bundle generator
  templates/web_bundle # bridge/index/readme templates used by build_game
examples/
  scene.py             # End-to-end DSL scene example
tests/
  ...                  # Unit and end-to-end tests
```

## DSL Overview

### Actor Schemas

```python
class Player(Actor):
    speed: int
```

Allowed custom field types:
- `int`, `float`, `str`, `bool`
- `List[int|float|str|bool]`

Built-in actor fields available on every actor:
- `uid`, `x`, `y`, `w`, `h`, `z`, `active`, `block_mask`, `parent`, `sprite`

### Actor Instance Methods

Animation/lifecycle calls are instance methods on actor bindings:

```python
def move_right(player: Player["hero"]):
    player.play("run")

def collect(last_coin: Coin[-1]):
    if last_coin is not None:
        last_coin.destroy()
```

Static forms like `Actor.play(player, ...)` and `Actor.destroy(player)` are not supported.

### Bindings in Action Signatures

- `Global["name"]`
- `Global["name", int|float|str|bool|List[...]]` (optional static hint)
- `Actor[index]`
- `Actor["TypeName"]`
- `Player`
- `Player["uid"]` / `Player[index]`
- `List[Actor]`
- `List[Player]`
- `Scene`
- `Role["role_id"]`
- `RoleType["role_id"]` (for role schema subclasses)

Role bindings are id-scoped only (no index selectors).

### Conditions

- `KeyboardCondition.begin_press("A", id="human_1")`
- `KeyboardCondition.on_press("A", id="human_1")`
- `KeyboardCondition.end_press("A", id="human_1")`
- `KeyboardCondition.end_press(["z", "q", "s", "d"], id="human_1")` (any key match)
- `MouseCondition.begin_click("left", id="human_1")`
- `MouseCondition.on_click("left", id="human_1")`
- `MouseCondition.end_click("left", id="human_1")`
- `OnOverlap(selector_a, selector_b)`
- `OnContact(selector_a, selector_b)`
- `OnLogicalCondition(predicate_fn, selector)`
- `OnToolCall("tool_name", "tool docstring", id="human_1")`
- `OnToolCall("tool_name", "tool docstring", id="ai_1")`
- `OnButton("button_name")`

`id` is mandatory for `KeyboardCondition`, `MouseCondition`, and `OnToolCall`.
The `id` value must match a role declared with `game.add_role(Role(...))`.

Rule declaration styles:
- `scene.add_rule(condition_expr, action_fn)` (preferred)
- `game.add_rule(condition_expr, action_fn)` (legacy-compatible)
- `@condition(condition_expr)` decorator on action functions
- `@callable` decorator on helper functions that can be called inside action/predicate expressions

Examples:
- `OnOverlap(Player["hero"], Coin)` for actor-vs-actor overlap
- `OnOverlap(Player["hero"], Tile)` for actor-vs-blocking-tile overlap
- `OnContact(Player["hero"], Coin)` for blocking contact events (equal `block_mask`)

### Scene/Game Split

- `Game` manages globals, resources, sprites, and active scene.
- `Scene` manages actors, rules, map, camera, gravity toggle, spawn actions, and turn progression via `scene.next_turn()`.
- Keyboard matching is normalized in the runtime (`d`/`D`/`KeyD`, `ArrowUp`/`up`, etc.).
- You can add game-specific key aliases at scene level with `keyboard_aliases`.
- Role-scoped UI placeholders can use `{{self.field_name}}` in session mode.

```python
game = Game()
scene = Scene(
    gravity=False,
    keyboard_aliases={
        "z": ["w"],  # optional layout alias (for this game only)
    },
)
game.set_scene(scene)
```

### Role Schemas

Role schemas are declared like actors, but inherit from `Role` and only support primitive/List fields.

```python
class HumanRole(Role):
    score: int
    inventory: List[str]

game.add_role(HumanRole(id="human_1", kind=RoleKind.HUMAN, score=0))

def add_point(self_role: HumanRole["human_1"]):
    self_role.score = self_role.score + 1
```

### Multiplayer Loop Configuration

Configure default loop mode and pacing with `game.set_multiplayer(...)`.

```python
game.set_multiplayer(
    Multiplayer(
        default_loop="hybrid",
        allowed_loops=["turn_based", "hybrid", "real_time"],
        default_visibility="shared",
        tick_rate=20,
        turn_timeout_ms=15000,
        hybrid_window_ms=600,
        game_time_scale=0.75,
        max_catchup_steps=1,
    )
)
```

Rules:
- If `default_loop` is `turn_based` or `hybrid`, at least one action must call `scene.next_turn()`.
- `game_time_scale` slows game-time progression for remote/LLM compute budgets (`> 0` and `<= 1.0`).
- Exported specs include `multiplayer` and `contains_next_turn_call`.

### Multiplayer Roles

Declare joinable roles in DSL and reference them from role-scoped conditions:

```python
game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
game.add_role(Role(id="dummy_1", required=True, kind=RoleKind.AI))
```

Rules:
- Condition `id="..."` on `KeyboardCondition`, `MouseCondition`, and `OnToolCall` must match a declared role id.
- Compiler raises an error if a role-scoped condition references an unknown role id.

### Interface Overlay (Optional)

`scene.set_interface(...)` is optional. If omitted, no HTML overlay is created.

```python
scene.set_interface(
    "<div>Score: {{score}}</div><div>Actors: {{__actors_count}}</div>"
)
```

Use `OnButton("spawn_bonus")` conditions only when your interface includes a matching `data-button` entry.
You can update the overlay at runtime from an action with `scene.set_interface(...)` (for example to show/hide a panel based on game state).
Built-in dynamic placeholders available in interface HTML:
- `{{__actors_count}}`
- `{{__scene_elapsed}}`

### Code Blocks (Vibe Coding Workflow)

`build_game.py` enables strict top-level filtering by default:
- non-import top-level statements **outside** any `CodeBlock` are ignored with warnings
- warnings explicitly mention `--allow-unboxed` if you want to disable this behavior

Use structural blocks:

```python
CodeBlock.begin("player_controls", descr="keyboard movement")

@condition(KeyboardCondition.on_press("d", id="human_1"))
def move_right(player: Player["hero"]):
    player.x = player.x + player.speed

CodeBlock.end("player_controls")
```

Template blocks are supported via `AbstractCodeBlock`:

```python
AbstractCodeBlock.begin("player_controls", id=str, hero_name=str, descr="reusable controls")
# ... rules/actions using `id` and `hero_name` ...
AbstractCodeBlock.end("player_controls")

AbstractCodeBlock.instantiate("player_controls", id="human_1", hero_name="hero_1")
AbstractCodeBlock.instantiate("player_controls", id="human_2", hero_name="hero_2")
```

Rules:
- every `CodeBlock.begin(...)` / `AbstractCodeBlock.begin(...)` must be closed by `end(...)`
- uninstantiated abstract blocks emit warnings
- instantiate values must be static constants (`int/float/str/bool/list/dict`)

### Callable Helpers

Use `@callable` for reusable expression helpers:

```python
@callable
def next_x(x: float, offset: int) -> float:
    return x + offset
```

Notes:
- Callable helpers are usable in action and predicate expressions.
- Selector annotations inside callable params are ignored and emitted as compiler warnings.
- Undecorated or unreferenced functions are ignored with line-aware warnings.

## Compile and Export (Python)

```python
from nanocalibur import export_project

source = """
class Player(Actor):
    speed: int

def move_right(player: Player["hero"]):
    player.x = player.x + player.speed

game = Game()
scene = Scene(gravity=False)
game.set_scene(scene)
game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
scene.add_actor(Player(uid="hero", x=100, y=100, speed=4))
scene.add_rule(KeyboardCondition.on_press("d", id="human_1"), move_right)
scene.set_camera(Camera.follow("hero"))
"""

export_project(source, "build")
```

Generated files:
- `build/game_spec.json`
- `build/game_ir.json`
- `build/game_logic.ts`

## Build Web Bundle

Use `nanocalibur/build_game.py` to compile a Python game entry file and generate a browser-ready TypeScript bundle.

```bash
python nanocalibur/build_game.py examples/scene.py --project ./my-web-game
```

This generates a bundle (default `build/nanocalibur_generated/src/nanocalibur_generated`) and, with `--project`, copies it to:

- `my-web-game/src/nanocalibur_generated/`

Generated runtime files include:
- `game_spec.json`
- `game_ir.json`
- `game_logic.ts`
- `interpreter.ts`
- `runtime_core.ts`
- `canvas_host.ts`
- `headless_host.ts`
- `headless_http_server.ts`
- `session_runtime.ts`
- `session_manager.ts`
- `replay_store_sqlite.ts`
- `symbolic_renderer.ts`
- `canvas/*.ts`
- `bridge.ts`
- `index.ts`

Minimal usage in your web app (`src/main.ts`):

```ts
import { attachNanoCalibur } from './nanocalibur_generated';

const canvas = document.getElementById('game');
if (!(canvas instanceof HTMLCanvasElement)) {
  throw new Error('Canvas element #game not found.');
}

const host = attachNanoCalibur(canvas);

void host.start();
```

Detailed walkthrough:
- `docs/blank-web-canvas-tutorial.md`

## Runtime Summary

The standalone TypeScript runtime supports:
- fixed-step update loop
- keyboard/mouse phase inputs
- rule evaluation (`keyboard`, `mouse`, `collision`, `logical`, `tool`)
- scene gravity toggle + actor spawn
- mask-based tile/actor blocking
- sprite animation playback and image preloading
- z-ordered rendering
- headless symbolic rendering (`HeadlessHost`)
- session runtime scheduling (`SessionRuntime`) with `real_time`/`turn_based`/`hybrid` loop modes
- session orchestration (`SessionManager`) with role invites/tokens and unique per-session seed allocation
- HTTP endpoint layer for remote clients (`HeadlessHttpServer`) including session endpoints (`GET/POST /sessions`, `/join`, `/open-roles`, `/sessions/{id}/commands`, `/sessions/{id}/stream`, `/sessions/{id}/pace`)
- minimal MCP-style tool bridge (`NanoCaliburMCPServer`)

Python MCP adapter:
- `nanocalibur.mcp_bridge.NanoCaliburHTTPClient`
- `nanocalibur.mcp_bridge.build_fastmcp_from_http(...)` to generate a FastMCP server from a running headless HTTP instance

## Tests

```bash
PYTHONPATH=. pytest -q
```

Coverage includes:
- compiler validation
- project compiler and schema checks
- exporter outputs
- runtime behavior (input phases, collisions, parenting, animation/assets)
- end-to-end Python -> exported TS -> Node runtime execution
