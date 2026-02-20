import json
import subprocess
import textwrap
from pathlib import Path


def test_headless_symbolic_render_and_mcp_tool_call(tmp_path):
    root = Path(__file__).resolve().parent.parent
    runtime_dir = root / "nanocalibur" / "runtime"

    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "npx",
            "-p",
            "typescript",
            "tsc",
            str(runtime_dir / "headless_host.ts"),
            str(runtime_dir / "runtime_core.ts"),
            str(runtime_dir / "symbolic_renderer.ts"),
            str(runtime_dir / "interpreter.ts"),
            "--target",
            "ES2020",
            "--module",
            "commonjs",
            "--outDir",
            str(compiled_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    runtime_path = compiled_dir / "interpreter.js"
    headless_path = compiled_dir / "headless_host.js"

    script = textwrap.dedent(
        f"""
        const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});
        const {{ HeadlessHost, NanoCaliburMCPServer }} = require({json.dumps(str(headless_path))});

        const spec = {{
          schemas: {{
            Player: {{
              uid: "str",
              x: "float",
              y: "float",
              w: "float",
              h: "float",
              z: "float",
              active: "bool",
              block_mask: "int",
              parent: "str",
              sprite: "str"
            }}
          }},
          actors: [
            {{
              type: "Player",
              uid: "hero",
              fields: {{
                x: 16,
                y: 16,
                z: 1,
                active: true,
                sprite: "hero"
              }}
            }}
          ],
          globals: [{{ name: "count", kind: "int", value: 0 }}],
          predicates: [],
          tools: [
            {{ name: "nudge", tool_docstring: "Move hero right", action: "nudge" }}
          ],
          rules: [
            {{
              condition: {{ kind: "tool", name: "nudge", tool_docstring: "Move hero right" }},
              action: "nudge"
            }}
          ],
          map: {{
            width: 4,
            height: 3,
            tile_size: 16,
            tile_grid: [
              [0, 0, 0, 0],
              [0, 0, 0, 0],
              [1, 0, 0, 0]
            ],
            tile_defs: {{
              "1": {{
                sprite: null,
                color: {{ r: 40, g: 40, b: 40, symbol: "#", description: "wall tile" }}
              }}
            }}
          }},
          resources: [{{ name: "hero_sheet", path: "hero.png" }}],
          sprites: {{
            by_name: {{
              hero: {{
                resource: "hero_sheet",
                frame_width: 16,
                frame_height: 16,
                symbol: "@",
                description: "the player hero",
                clips: {{ idle: {{ frames: [0], ticks_per_frame: 8, loop: true }} }}
              }}
            }},
            by_uid: {{}},
            by_type: {{}}
          }}
        }};

        const actions = {{
          nudge: (ctx) => {{
            const hero = ctx.getActorByUid("hero");
            hero.x = hero.x + 16;
            ctx.globals.count = ctx.globals.count + 1;
          }}
        }};

        const interpreter = new NanoCaliburInterpreter(spec, actions, {{}});
        const host = new HeadlessHost(interpreter, {{}});

        const before = host.getSymbolicFrame();
        const after = host.callTool("nudge");
        const countAfterOneCall = host.getState().globals.count;

        const mcp = new NanoCaliburMCPServer(host);
        const listed = mcp.handle({{ id: 1, method: "tools/list" }});
        const called = mcp.handle({{ id: 2, method: "tools/call", params: {{ name: "nudge", arguments: {{}} }} }});

        console.log(JSON.stringify({{
          beforeRows: before.rows,
          afterRows: after.rows,
          countAfterOneCall,
          listedTool: listed.result.tools[0].name,
          countAfterTwoCalls: called.result.state.globals.count,
          legend: after.legend
        }}));
        """
    )

    proc = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )

    values = json.loads(proc.stdout.strip())
    assert values["beforeRows"][1][1] == "@"
    assert values["afterRows"][1][2] == "@"
    assert values["countAfterOneCall"] == 1
    assert values["listedTool"] == "nudge"
    assert values["countAfterTwoCalls"] == 2
    assert any(item["symbol"] == "@" for item in values["legend"])


def test_headless_symbolic_crop_and_tile_palette(tmp_path):
    root = Path(__file__).resolve().parent.parent
    runtime_dir = root / "nanocalibur" / "runtime"

    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "npx",
            "-p",
            "typescript",
            "tsc",
            str(runtime_dir / "headless_host.ts"),
            str(runtime_dir / "runtime_core.ts"),
            str(runtime_dir / "symbolic_renderer.ts"),
            str(runtime_dir / "interpreter.ts"),
            "--target",
            "ES2020",
            "--module",
            "commonjs",
            "--outDir",
            str(compiled_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    runtime_path = compiled_dir / "interpreter.js"
    headless_path = compiled_dir / "headless_host.js"

    script = textwrap.dedent(
        f"""
        const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});
        const {{ HeadlessHost }} = require({json.dumps(str(headless_path))});

        const spec = {{
          schemas: {{
            Player: {{
              uid: "str",
              x: "float",
              y: "float",
              w: "float",
              h: "float",
              z: "float",
              active: "bool",
              block_mask: "int",
              parent: "str",
              sprite: "str"
            }}
          }},
          actors: [
            {{
              type: "Player",
              uid: "hero",
              fields: {{
                x: 80,
                y: 16,
                z: 1,
                active: true,
                sprite: "hero"
              }}
            }}
          ],
          globals: [],
          predicates: [],
          tools: [],
          rules: [],
          cameras: [
            {{ name: "cam", role_id: "human_1", x: 80, y: 16 }}
          ],
          map: {{
            width: 6,
            height: 4,
            tile_size: 16,
            tile_grid: [
              [0, 0, 0, 1, 1, 2],
              [0, 0, 0, 1, 0, 0],
              [0, 0, 0, 0, 0, 0],
              [0, 0, 0, 0, 0, 0]
            ],
            tile_defs: {{
              "1": {{
                sprite: null,
                color: {{ r: 20, g: 70, b: 180, symbol: "~", description: "water tile" }}
              }},
              "2": {{
                sprite: "coin",
                color: null
              }}
            }}
          }},
          resources: [
            {{ name: "hero_sheet", path: "hero.png" }},
            {{ name: "coin_sheet", path: "coin.png" }}
          ],
          sprites: {{
            by_name: {{
              hero: {{
                resource: "hero_sheet",
                frame_width: 16,
                frame_height: 16,
                symbol: "@",
                description: "hero actor",
                clips: {{ idle: {{ frames: [0], ticks_per_frame: 8, loop: true }} }}
              }},
              coin: {{
                resource: "coin_sheet",
                frame_width: 16,
                frame_height: 16,
                symbol: "c",
                description: "coin tile",
                clips: {{ idle: {{ frames: [0], ticks_per_frame: 8, loop: true }} }}
              }}
            }},
            by_uid: {{}},
            by_type: {{}}
          }}
        }};

        const interpreter = new NanoCaliburInterpreter(spec, {{}}, {{}});
        const host = new HeadlessHost(interpreter, {{
          symbolic: {{ cropWidth: 3, cropHeight: 2 }}
        }});

        const frame = host.getSymbolicFrame();
        console.log(JSON.stringify(frame));
        """
    )

    proc = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )

    frame = json.loads(proc.stdout.strip())
    assert frame["width"] == 3
    assert frame["height"] == 2
    assert frame["rows"] == ["~~c", "~.@"]
    legend = {item["symbol"]: item["description"] for item in frame["legend"]}
    assert legend["~"] == "water tile"
    assert legend["c"] == "coin tile"
    assert legend["@"] == "hero actor"


def test_headless_symbolic_default_crop_uses_default_screen_size(tmp_path):
    root = Path(__file__).resolve().parent.parent
    runtime_dir = root / "nanocalibur" / "runtime"

    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "npx",
            "-p",
            "typescript",
            "tsc",
            str(runtime_dir / "headless_host.ts"),
            str(runtime_dir / "runtime_core.ts"),
            str(runtime_dir / "symbolic_renderer.ts"),
            str(runtime_dir / "interpreter.ts"),
            "--target",
            "ES2020",
            "--module",
            "commonjs",
            "--outDir",
            str(compiled_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    runtime_path = compiled_dir / "interpreter.js"
    headless_path = compiled_dir / "headless_host.js"

    script = textwrap.dedent(
        f"""
        const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});
        const {{ HeadlessHost }} = require({json.dumps(str(headless_path))});

        const spec = {{
          schemas: {{
            Player: {{
              uid: "str",
              x: "float",
              y: "float",
              w: "float",
              h: "float",
              z: "float",
              active: "bool",
              block_mask: "int",
              parent: "str",
              sprite: "str"
            }}
          }},
          actors: [
            {{
              type: "Player",
              uid: "hero",
              fields: {{
                x: 32,
                y: 32,
                active: true,
                sprite: "hero"
              }}
            }}
          ],
          globals: [],
          predicates: [],
          tools: [],
          rules: [],
          map: {{
            width: 40,
            height: 30,
            tile_size: 32,
            tile_grid: Array.from({{ length: 30 }}, () => Array.from({{ length: 40 }}, () => 0)),
            tile_defs: {{}}
          }},
          resources: [{{ name: "hero_sheet", path: "hero.png" }}],
          sprites: {{
            by_name: {{
              hero: {{
                resource: "hero_sheet",
                frame_width: 32,
                frame_height: 32,
                symbol: "@",
                description: "hero",
                clips: {{ idle: {{ frames: [0], ticks_per_frame: 8, loop: true }} }}
              }}
            }},
            by_uid: {{}},
            by_type: {{}}
          }}
        }};

        const interpreter = new NanoCaliburInterpreter(spec, {{}}, {{}});
        const host = new HeadlessHost(interpreter, {{}});
        const frame = host.getSymbolicFrame();
        console.log(JSON.stringify({{ width: frame.width, height: frame.height }}));
        """
    )

    proc = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    values = json.loads(proc.stdout.strip())
    assert values["width"] == 30
    assert values["height"] == 17


def test_headless_symbolic_ai_without_camera_gets_empty_frame(tmp_path):
    root = Path(__file__).resolve().parent.parent
    runtime_dir = root / "nanocalibur" / "runtime"

    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "npx",
            "-p",
            "typescript",
            "tsc",
            str(runtime_dir / "headless_host.ts"),
            str(runtime_dir / "runtime_core.ts"),
            str(runtime_dir / "symbolic_renderer.ts"),
            str(runtime_dir / "interpreter.ts"),
            "--target",
            "ES2020",
            "--module",
            "commonjs",
            "--outDir",
            str(compiled_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    runtime_path = compiled_dir / "interpreter.js"
    headless_path = compiled_dir / "headless_host.js"

    script = textwrap.dedent(
        f"""
        const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});
        const {{ HeadlessHost }} = require({json.dumps(str(headless_path))});

        const spec = {{
          actors: [
            {{ type: "Player", uid: "hero", fields: {{ x: 16, y: 16, active: true }} }}
          ],
          globals: [],
          predicates: [],
          tools: [],
          rules: [],
          roles: [
            {{ id: "dummy_1", kind: "ai", required: true, type: "Role", fields: {{}} }}
          ],
          cameras: [],
          map: {{
            width: 4,
            height: 3,
            tile_size: 16,
            tile_grid: [
              [0, 0, 0, 0],
              [0, 0, 0, 0],
              [0, 0, 0, 0]
            ],
            tile_defs: {{}}
          }}
        }};

        const interpreter = new NanoCaliburInterpreter(spec, {{}}, {{}});
        const host = new HeadlessHost(interpreter, {{}});
        const frame = host.getSymbolicFrame({{ roleId: "dummy_1", roleKind: "ai" }});
        console.log(JSON.stringify(frame));
        """
    )

    proc = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    frame = json.loads(proc.stdout.strip())
    assert frame["width"] == 0
    assert frame["height"] == 0
    assert frame["rows"] == []
