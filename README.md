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
  build_web_scene.py   # Python scene -> web bundle generator
  templates/web_bundle # bridge/index/readme templates used by build_web_scene
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

### Conditions

- `KeyboardCondition.begin_press("A")`
- `KeyboardCondition.on_press("A")`
- `KeyboardCondition.end_press("A")`
- `KeyboardCondition.end_press(["z", "q", "s", "d"])` (any key match)
- `MouseCondition.begin_click("left")`
- `MouseCondition.on_click("left")`
- `MouseCondition.end_click("left")`
- `CollisionRelated(selector_a, selector_b)`
- `LogicalRelated(predicate_fn, selector)`
- `ToolCalling("tool_name", "tool docstring")`

Rule declaration styles:
- `scene.add_rule(condition_expr, action_fn)` (preferred)
- `game.add_rule(condition_expr, action_fn)` (legacy-compatible)
- `@condition(condition_expr)` decorator on action functions

### Scene/Game Split

- `Game` manages globals, resources, sprites, and active scene.
- `Scene` manages actors, rules, map, camera, gravity toggle, and spawn actions.

```python
game = Game()
scene = Scene(gravity=False)
game.set_scene(scene)
```

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
scene.add_actor(Player(uid="hero", x=100, y=100, speed=4))
scene.add_rule(KeyboardCondition.on_press("d"), move_right)
scene.set_camera(Camera.follow("hero"))
"""

export_project(source, "build")
```

Generated files:
- `build/game_spec.json`
- `build/game_ir.json`
- `build/game_logic.ts`

## Build Web Bundle

Use `nanocalibur/build_web_scene.py` to compile a Python scene and generate a browser-ready TypeScript bundle.

```bash
python nanocalibur/build_web_scene.py examples/scene.py --project ./my-web-game
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

const host = attachNanoCalibur(canvas, {
  showHud: true,
});

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
- HTTP endpoint layer for remote clients (`HeadlessHttpServer`)
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
