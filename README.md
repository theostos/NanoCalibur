# NanoCalibur

NanoCalibur is a tiny deterministic 2D game engine pipeline built around a Python DSL.

## 10-Line Overview

1. Write gameplay in Python DSL (`nanocalibur.dsl_markers`).
2. Source is parsed by AST and never executed.
3. Compiler outputs deterministic `game_spec.json` + IR + generated TypeScript.
4. Runtime supports browser canvas and headless HTTP/session mode.
5. Multiplayer is role-based (`Role`, `HumanRole`, AI/hybrid slots).
6. Conditions are split into `safe` (authoritative) and `unsafe` (client/tool).
7. Camera is explicit and role-scoped.
8. Symbolic rendering supports LLM/RL agents.
9. Local role state (`Local[...]`) is client-owned (not server authoritative).
10. Build with `nanocalibur-build-game` and run in any web project.

## 60-Second Hello World

```bash
cat > main.py <<'PY'
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
PY

nanocalibur-build-game ./main.py --project ./nanocalibur-demo
```

## Core Concepts

| Concept | Contract |
|---|---|
| Coordinates | World origin top-left, `+x` right, `+y` down; actor `x/y` are center coordinates in pixels. |
| Time | Physics uses seconds (`vx/vy` in px/s); `scene.elapsed` is tick-based integer time. |
| Rule model | Condition -> action; deterministic fixed-step execution. |
| Safety split | `@safe_condition` for authoritative checks; `@unsafe_condition` for client/tool/input events. |
| Ownership | Server owns globals/actors/server role fields; `Local[...]` role fields are client-owned only. |
| Rendering | Browser canvas rendering + symbolic grid rendering for remote agents. |
| Multiplayer | Explicit roles, role-scoped conditions, role-scoped cameras/interfaces. |

## Learn More

- Human docs: `docs/` (serve with `mkdocs serve`)
- API reference: `docs/api.md`
- LLM guide: `LLM.md`
- Agent maintenance guide: `agent.md`
- Multi-file scene example: `examples/scene/main.py`
- Monolithic scene example: `examples/scene/monolithic.py`
- Tiny runnable examples: `examples/tiny/`

## Repository Structure

```text
nanocalibur/
  compiler/            # Function-body compiler components (AST -> IR)
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
  scene/
    main.py            # End-to-end DSL scene example (multi-file entrypoint)
    monolithic.py      # Same example in one file / one CodeBlock
tests/
  ...                  # Unit and end-to-end tests
```

## Documentation

- Human docs (MkDocs): `docs/` + `mkdocs.yml`
- LLM guide: `LLM.md`
- Maintenance-agent guide: `agent.md`

Build/serve docs:

```bash
pip install -e ".[docs]"
mkdocs serve
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
- `OnToolCall("tool_name", id="human_1")`
- `OnToolCall("tool_name", id="ai_1")`
- `OnButton("button_name")`

`id` is mandatory for `KeyboardCondition`, `MouseCondition`, and `OnToolCall`.
The `id` value must match a role declared with `game.add_role(Role(...))`.

Rule declaration styles:
- `scene.add_rule(condition_expr, action_fn)` (preferred)
- `game.add_rule(condition_expr, action_fn)` (legacy-compatible)
- `@safe_condition(condition_expr)` marker for server-evaluated conditions (`OnOverlap`/`OnContact`/`OnLogicalCondition`)
- `@unsafe_condition(condition_expr)` marker for client-input-driven conditions (`KeyboardCondition`/`MouseCondition`/`OnToolCall`/`OnButton`)
- `@callable` decorator on helper functions that can be called inside action/predicate expressions

`@safe_condition` and `@unsafe_condition` do not change runtime translation; they add intent metadata and compiler errors on mismatches.

Examples:
- `OnOverlap(Player["hero"], Coin)` for actor-vs-actor overlap
- `OnOverlap(Player["hero"], Tile)` for actor-vs-blocking-tile overlap
- `OnContact(Player["hero"], Coin)` for blocking contact events (equal `block_mask`)

### Scene/Game Split

- `Game` manages globals, resources, sprites, and active scene.
- `Scene` manages actors, rules, map, camera, gravity toggle, spawn actions, and turn progression via `scene.next_turn()`.
- Keyboard matching is normalized in the runtime (`d`/`D`/`KeyD`, `ArrowUp`/`up`, etc.).
- You can add game-specific key aliases at scene level with `keyboard_aliases`.
- Role-scoped UI placeholders can use `{{role.field_name}}` in session mode.
- Client-local role placeholders can use `{{local.field_name}}` (for example `{{local.keybinds.move_up}}`).

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

Role schemas inherit from `Role` (or from built-in `HumanRole`) and support server fields plus client-local fields.

- Built-in immutable `HumanRole` exists by default with:
- `keybinds: Local[Dict[str, str]]` (client-owned, not synced by server)
- default keybinds:
- `move_up=z`, `move_left=q`, `move_down=s`, `move_right=d`

Use local fields with `Local[...]` and initialize with `local(...)`:

```python
class HeroRole(HumanRole):
    score: int
    quickbar: Local[List[str]] = local(["dash", "heal"])

game.add_role(HeroRole(id="human_1", kind=RoleKind.HUMAN, score=0))

def add_point(self_role: HeroRole["human_1"]):
    self_role.score = self_role.score + 1
```

Local-field rules:
- `Local[...]` fields are never stored/synced by server state.
- they are available to client/UI logic (`local.*` placeholders).
- compiler error if a `Local[...]` field is used in server-authoritative logic (actions/predicates/callables).
- `add_role(...)` cannot set local-field values (client owns them).
- client keyboard input can target logical tokens (for example `KeyboardCondition.on_press("move_up", id="human_1")`) and map them through `local.keybinds`.

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
- `OnToolCall(...)` informal tool description is taken from the bound action function docstring.
- Compiler raises an error if a role-scoped condition references an unknown role id.

### Interface Overlay (Optional)

`scene.set_interface(...)` is optional. If omitted, no HTML overlay is created.

```python
# Inline HTML
scene.set_interface("<div>Score: {{score}}</div><div>Actors: {{__actors_count}}</div>")

# File-backed and role-scoped
hud_h1 = Interface("ui/hud_human.html", Role["human_1"])
scene.set_interface(hud_h1)
```

Use `OnButton("spawn_bonus")` conditions only when your interface includes a matching `data-button` entry.
You can update the overlay at runtime from an action with `scene.set_interface(...)` (for example to show/hide a panel based on game state).
Built-in dynamic placeholders available in interface HTML:
- `{{__actors_count}}`
- `{{__scene_elapsed}}`
- `{{role.<field>}}` for role-scoped values (for example `{{role.personal_score}}`)
- `{{local.<field>}}` for client-local role values (for example `{{local.keybinds.move_up}}`)

### Code Blocks (Vibe Coding Workflow)

`build_game.py` enables strict top-level filtering by default:
- non-import top-level statements **outside** any `CodeBlock` are ignored with warnings
- warnings explicitly mention `--allow-unboxed` if you want to disable this behavior

Use structural blocks:

```python
CodeBlock.begin("player_controls")
"""keyboard movement"""

@unsafe_condition(KeyboardCondition.on_press("d", id="human_1"))
def move_right(player: Player["hero"]):
    player.x = player.x + player.speed

CodeBlock.end("player_controls")
```

Template blocks are supported via `AbstractCodeBlock`:

```python
AbstractCodeBlock.begin("player_controls", id=str, hero_name=str)
"""reusable controls"""
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
main_camera = Camera("main_camera", Role["human_1"], width=30, height=18)
main_camera.follow("hero")
scene.add_camera(main_camera)
"""

export_project(source, "build")
```

Generated files:
- `build/game_spec.json`
- `build/game_ir.json`
- `build/game_logic.ts`

## Build Web Bundle

Use `nanocalibur-build-game` (installed CLI) to compile a Python game entry file and generate a browser-ready TypeScript bundle.

```bash
nanocalibur-build-game examples/scene/main.py --project ./my-web-game
```

Monolithic variant:

```bash
nanocalibur-build-game examples/scene/monolithic.py --project ./my-web-game
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
