# NanoCalibur

NanoCalibur is a deterministic Python DSL compiler for small game logic on top of Excalibur-style runtimes.

Core guarantees:
- Python source is parsed with `ast` and never executed.
- Only a restricted DSL subset is accepted.
- Compilation is deterministic (`AST -> IR -> TS/JS + JSON spec`).

## Repository Structure

```text
nanocalibur/
  __init__.py
  compiler.py          # Action + predicate compiler (AST -> IR)
  project_compiler.py  # Full game project compiler
  ir.py                # Intermediate representation
  game_model.py        # Project/rule/map/camera data models
  exporter.py          # JSON + TS/JS export pipeline
  ts_generator.py      # IR -> TypeScript/JavaScript codegen
  typesys.py           # Field type system
  schema_registry.py   # Actor schema registry
  dsl_markers.py       # Marker classes/helpers for DSL authoring
  runtime/
    interpreter.js     # Runtime rule interpreter (Excalibur-friendly JS)
tests/
  ...                  # Python unit and end-to-end tests
```

Root files (`compiler.py`, `ts_generator.py`, etc.) are compatibility shims that forward to `nanocalibur/*`.

## DSL Features

### Actor Schemas

```python
class Player(ActorModel):
    life: int
    x: int
    y: int
    inventory: List[str]
```

Allowed field types:
- `int`, `float`, `str`, `bool`
- `List[int|float|str|bool]`

### Action Function Bindings

- `Global["name"]`
- `Actor["ActorType"]`
- `Actor[index]`
- `Player["uid"]` / `Player[index]`
- `List[Actor]`
- `List[Player]`

Typed actor access is validated statically.

### Global Variables

Supported global values:
- primitives (`int`, `float`, `str`, `bool`)
- homogeneous primitive lists
- actor pointers via `WithUID(...)`:
  - `WithUID(Actor, "uid")`
  - `WithUID(Player, "uid")`

When a global pointer is typed (`WithUID(Player, ...)`), actions can safely access actor fields through that global binding.

### Conditions and Rules

Supported conditions:
- keyboard phases:
  - `KeyboardCondition.begin_press("A")`
  - `KeyboardCondition.on_press("A")`
  - `KeyboardCondition.end_press("A")`
- mouse phases:
  - `MouseCondition.begin_click("left")`
  - `MouseCondition.on_click("left")`
  - `MouseCondition.end_click("left")`
- `CollisionRelated(selector_a, selector_b)`
- `LogicalRelated(predicate_fn, selector)`

Selectors:
- `Any(Actor)` / `Any(Player)`
- `WithUID(Actor, "uid")` / `WithUID(Player, "uid")`

Logical predicates are declared as:

```python
def is_dead(player: Player) -> bool:
    return player.life <= 0
```

### Map and Camera

Map:
```python
game.set_map(TileMap(width=16, height=12, tile_size=32, solid=[(0, 0), (1, 1)]))
```

Camera:
```python
game.set_camera(Camera.fixed(100, 200))
game.set_camera(Camera.follow("main_character"))
```

## Compile and Export

```python
from exporter import export_project

source = """
class Player(ActorModel):
    life: int
    x: int
    y: int

def heal(player: Player["main_character"], amount: Global["heal"]):
    player.life = player.life + amount

game = Game()
game.add_global("heal", 2)
game.add_actor(Player, "main_character", life=1, x=5, y=7)
game.add_rule(KeyboardCondition.on_press("A"), heal)
game.set_camera(Camera.follow("main_character"))
game.set_map(TileMap(width=10, height=10, tile_size=16, solid=[(1, 1)]))
"""

export_project(source, "build")
```

Generated files:
- `build/game_spec.json`
- `build/game_ir.json`
- `build/game_logic.ts`
- `build/game_logic.js`
- `build/game_logic.mjs`

## Runtime Interpreter (JavaScript)

Use `nanocalibur/runtime/interpreter.js` with generated `game_spec.json` and `game_logic.js`.
For browser ES modules, use `nanocalibur/runtime/interpreter.mjs` with `game_logic.mjs`.

It supports:
- rule evaluation per tick (`keyboard`, `mouse`, `collision`, `logical`)
- action dispatch
- actor/global state updates
- map solid tile lookup (`isSolidAtWorld`)
- camera state (`fixed` / `follow`)

Per-frame input payload shape for phased input:

```json
{
  "keyboard": { "begin": ["A"], "on": ["A"], "end": [] },
  "mouse": { "begin": ["left"], "on": ["left"], "end": [] },
  "collisions": [{ "aUid": "player_1", "bUid": "enemy_1" }]
}
```

Interactive runtime smoke test:

```bash
node examples/interactive_runtime.js build/game_spec.json build/game_logic.js
```

## Excalibur Project Input Generation

Use `examples/build_web_scene.py` to compile a DSL scene into an input bundle for an Excalibur TypeScript project.

Example (targeting the local `sample-tiled-webpack` project):

```bash
python examples/build_web_scene.py path/to/scene.py --project ./sample-tiled-webpack
```

This generates a bundle (default: `build/nanocalibur_generated`) and copies it to:

`sample-tiled-webpack/src/nanocalibur_generated/`

Generated files include:
- `game_spec.json`
- `game_ir.json`
- `game_logic.ts`
- `interpreter.ts`
- `bridge.ts`
- `index.ts`

Then in your Excalibur entry file (for example `sample-tiled-webpack/src/main.ts`):

```ts
import { attachNanoCalibur } from './nanocalibur_generated';

const bridge = attachNanoCalibur(game.currentScene);
game.on('postupdate', () => {
  bridge.tick();
});
```

Full blank-project walkthrough:
- `docs/blank-excalibur-tutorial.md`

## Test Suite

```bash
python -m pytest -q
```

Current coverage includes:
- action compiler validation
- TS/JS code generation
- project compiler (globals/rules/conditions/map/camera)
- exporter outputs
- end-to-end Python -> exported JS -> Node runtime execution
