import json
import subprocess
import textwrap
from pathlib import Path


def test_runtime_keyboard_and_mouse_phase_matching(tmp_path):
    root = Path(__file__).resolve().parent.parent
    runtime_ts_path = root / "nanocalibur" / "runtime" / "interpreter.ts"
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "npx",
            "-p",
            "typescript",
            "tsc",
            str(runtime_ts_path),
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

    script = textwrap.dedent(
        f"""
        const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});

        const spec = {{
          actors: [],
          globals: [
            {{ name: "kb_begin", kind: "int", value: 0 }},
            {{ name: "kb_on", kind: "int", value: 0 }},
            {{ name: "kb_end", kind: "int", value: 0 }},
            {{ name: "kb_end_any", kind: "int", value: 0 }},
            {{ name: "ms_begin", kind: "int", value: 0 }},
            {{ name: "ms_on", kind: "int", value: 0 }},
            {{ name: "ms_end", kind: "int", value: 0 }}
          ],
          predicates: [],
          rules: [
            {{ condition: {{ kind: "keyboard", phase: "begin", key: "A" }}, action: "inc_kb_begin" }},
            {{ condition: {{ kind: "keyboard", phase: "on", key: "A" }}, action: "inc_kb_on" }},
            {{ condition: {{ kind: "keyboard", phase: "end", key: "A" }}, action: "inc_kb_end" }},
            {{ condition: {{ kind: "keyboard", phase: "end", key: ["A", "B"] }}, action: "inc_kb_end_any" }},
            {{ condition: {{ kind: "mouse", phase: "begin", button: "left" }}, action: "inc_ms_begin" }},
            {{ condition: {{ kind: "mouse", phase: "on", button: "left" }}, action: "inc_ms_on" }},
            {{ condition: {{ kind: "mouse", phase: "end", button: "left" }}, action: "inc_ms_end" }}
          ]
        }};

        function makeInc(name) {{
          return (ctx) => {{
            ctx.globals[name] = ctx.globals[name] + 1;
          }};
        }}

        const actions = {{
          inc_kb_begin: makeInc("kb_begin"),
          inc_kb_on: makeInc("kb_on"),
          inc_kb_end: makeInc("kb_end"),
          inc_kb_end_any: makeInc("kb_end_any"),
          inc_ms_begin: makeInc("ms_begin"),
          inc_ms_on: makeInc("ms_on"),
          inc_ms_end: makeInc("ms_end")
        }};

        const i = new NanoCaliburInterpreter(spec, actions, {{}});
        i.tick({{ keyboard: {{ begin: ["A"], on: ["A"], end: [] }}, mouse: {{ begin: ["left"], on: ["left"], end: [] }} }});
        i.tick({{ keyboard: {{ begin: [], on: ["A"], end: [] }}, mouse: {{ begin: [], on: ["left"], end: [] }} }});
        i.tick({{ keyboard: {{ begin: [], on: [], end: ["A"] }}, mouse: {{ begin: [], on: [], end: ["left"] }} }});
        console.log(JSON.stringify(i.getState().globals));
        """
    )

    proc = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    values = json.loads(proc.stdout.strip())
    assert values["kb_begin"] == 1
    assert values["kb_on"] == 2
    assert values["kb_end"] == 1
    assert values["kb_end_any"] == 1
    assert values["ms_begin"] == 1
    assert values["ms_on"] == 2
    assert values["ms_end"] == 1


def test_runtime_keyboard_normalization_and_scene_aliases(tmp_path):
    root = Path(__file__).resolve().parent.parent
    runtime_ts_path = root / "nanocalibur" / "runtime" / "interpreter.ts"
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "npx",
            "-p",
            "typescript",
            "tsc",
            str(runtime_ts_path),
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

    script = textwrap.dedent(
        f"""
        const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});

        const spec = {{
          actors: [],
          globals: [
            {{ name: "arrow", kind: "int", value: 0 }},
            {{ name: "code", kind: "int", value: 0 }},
            {{ name: "layout", kind: "int", value: 0 }}
          ],
          scene: {{
            keyboard_aliases: {{
              z: ["w"]
            }}
          }},
          predicates: [],
          rules: [
            {{ condition: {{ kind: "keyboard", phase: "on", key: "up" }}, action: "inc_arrow" }},
            {{ condition: {{ kind: "keyboard", phase: "on", key: "d" }}, action: "inc_code" }},
            {{ condition: {{ kind: "keyboard", phase: "on", key: "z" }}, action: "inc_layout" }}
          ]
        }};

        function makeInc(name) {{
          return (ctx) => {{
            ctx.globals[name] = ctx.globals[name] + 1;
          }};
        }}

        const actions = {{
          inc_arrow: makeInc("arrow"),
          inc_code: makeInc("code"),
          inc_layout: makeInc("layout")
        }};

        const i = new NanoCaliburInterpreter(spec, actions, {{}});
        i.tick({{ keyboard: {{ on: ["ArrowUp"] }} }});
        i.tick({{ keyboard: {{ on: ["KeyD"] }} }});
        i.tick({{ keyboard: {{ on: ["w"] }} }});
        console.log(JSON.stringify(i.getState().globals));
        """
    )

    proc = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    values = json.loads(proc.stdout.strip())
    assert values["arrow"] == 1
    assert values["code"] == 1
    assert values["layout"] == 1


def test_runtime_tool_condition_and_tools_metadata(tmp_path):
    root = Path(__file__).resolve().parent.parent
    runtime_ts_path = root / "nanocalibur" / "runtime" / "interpreter.ts"
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "npx",
            "-p",
            "typescript",
            "tsc",
            str(runtime_ts_path),
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

    script = textwrap.dedent(
        f"""
        const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});

        const spec = {{
          actors: [],
          globals: [{{ name: "count", kind: "int", value: 0 }}],
          predicates: [],
          tools: [
            {{ name: "spawn_bonus", tool_docstring: "Spawn a bonus coin", action: "inc" }}
          ],
          rules: [
            {{
              condition: {{
                kind: "tool",
                name: "spawn_bonus",
                tool_docstring: "Spawn a bonus coin"
              }},
              action: "inc"
            }}
          ]
        }};

        const actions = {{
          inc: (ctx) => {{
            ctx.globals.count = ctx.globals.count + 1;
          }}
        }};

        const i = new NanoCaliburInterpreter(spec, actions, {{}});
        i.tick({{ toolCalls: ["spawn_bonus"] }});
        i.tick({{ toolCalls: [{{ name: "unknown", payload: {{}} }}] }});
        i.tick({{ toolCalls: [{{ name: "spawn_bonus", payload: {{ amount: 1 }} }}] }});

        console.log(JSON.stringify({{
          count: i.getState().globals.count,
          tools: i.getTools()
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
    assert values["count"] == 2
    assert values["tools"][0]["name"] == "spawn_bonus"


def test_runtime_role_scoped_input_and_tool_conditions(tmp_path):
    root = Path(__file__).resolve().parent.parent
    runtime_ts_path = root / "nanocalibur" / "runtime" / "interpreter.ts"
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "npx",
            "-p",
            "typescript",
            "tsc",
            str(runtime_ts_path),
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

    script = textwrap.dedent(
        f"""
        const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});

        const spec = {{
          actors: [],
          globals: [
            {{ name: "kb", kind: "int", value: 0 }},
            {{ name: "tool", kind: "int", value: 0 }}
          ],
          predicates: [],
          tools: [
            {{ name: "bot_move", tool_docstring: "bot move", action: "inc_tool", role_id: "dummy_1" }}
          ],
          rules: [
            {{
              condition: {{ kind: "keyboard", phase: "on", key: "d", role_id: "human_1" }},
              action: "inc_kb"
            }},
            {{
              condition: {{ kind: "tool", name: "bot_move", role_id: "dummy_1" }},
              action: "inc_tool"
            }}
          ]
        }};

        const actions = {{
          inc_kb: (ctx) => {{
            ctx.globals.kb = ctx.globals.kb + 1;
          }},
          inc_tool: (ctx) => {{
            ctx.globals.tool = ctx.globals.tool + 1;
          }}
        }};

        const i = new NanoCaliburInterpreter(spec, actions, {{}});

        i.tick({{
          keyboard: {{ on: ["d"] }},
          role_id: "dummy_1"
        }});
        i.tick({{
          keyboard: {{ on: ["d"] }},
          role_id: "human_1"
        }});
        i.tick({{
          toolCalls: [{{ name: "bot_move", payload: {{}}, role_id: "human_1" }}]
        }});
        i.tick({{
          toolCalls: [{{ name: "bot_move", payload: {{}}, role_id: "dummy_1" }}]
        }});

        console.log(JSON.stringify(i.getState().globals));
        """
    )

    proc = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    values = json.loads(proc.stdout.strip())
    assert values["kb"] == 1
    assert values["tool"] == 1


def test_runtime_scene_next_turn_updates_turn_state(tmp_path):
    root = Path(__file__).resolve().parent.parent
    runtime_ts_path = root / "nanocalibur" / "runtime" / "interpreter.ts"
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "npx",
            "-p",
            "typescript",
            "tsc",
            str(runtime_ts_path),
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

    script = textwrap.dedent(
        f"""
        const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});

        const spec = {{
          actors: [],
          globals: [],
          predicates: [],
          rules: [
            {{ condition: {{ kind: "keyboard", phase: "begin", key: "A" }}, action: "advance" }}
          ],
          multiplayer: {{
            default_loop: "turn_based"
          }}
        }};

        const actions = {{
          advance: (ctx) => {{
            ctx.scene.nextTurn();
          }}
        }};

        const i = new NanoCaliburInterpreter(spec, actions, {{}});
        i.tick({{ keyboard: {{ begin: ["A"], on: [], end: [] }} }});
        const first = i.getState().scene;
        i.tick({{}});
        const second = i.getState().scene;

        console.log(JSON.stringify({{
          first_turn: first.turn,
          first_changed: first.turnChangedThisStep,
          second_turn: second.turn,
          second_changed: second.turnChangedThisStep,
          mode: first.loopMode
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
    assert values["first_turn"] == 1
    assert values["first_changed"] is True
    assert values["second_turn"] == 1
    assert values["second_changed"] is False
    assert values["mode"] == "turn_based"


def test_runtime_parent_binding_moves_children_with_parent(tmp_path):
    root = Path(__file__).resolve().parent.parent
    runtime_ts_path = root / "nanocalibur" / "runtime" / "interpreter.ts"
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "npx",
            "-p",
            "typescript",
            "tsc",
            str(runtime_ts_path),
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

    script = textwrap.dedent(
        f"""
        const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});
        const spec = {{
          actors: [
            {{ type: "Player", uid: "hero", fields: {{ x: 10, y: 20, z: 1, active: true }} }},
            {{ type: "Coin", uid: "pet", fields: {{ x: 12, y: 22, z: 3, parent: "hero", active: true }} }}
          ],
          globals: [],
          predicates: [],
          rules: [
            {{ condition: {{ kind: "keyboard", phase: "on", key: "D" }}, action: "move_parent" }}
          ]
        }};

        const actions = {{
          move_parent: (ctx) => {{
            const hero = ctx.getActorByUid("hero");
            hero.x = hero.x + 5;
            hero.y = hero.y + 2;
            hero.z = hero.z + 1;
          }}
        }};

        const i = new NanoCaliburInterpreter(spec, actions, {{}});
        i.tick({{ keyboard: {{ begin: [], on: ["D"], end: [] }} }});
        const state = i.getState();
        const pet = state.actors.find((a) => a.uid === "pet");
        console.log(JSON.stringify({{ x: pet.x, y: pet.y, z: pet.z }}));
        """
    )

    proc = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    values = json.loads(proc.stdout.strip())
    assert values["x"] == 17
    assert values["y"] == 24
    assert values["z"] == 4


def test_runtime_spawn_defaults_keep_optional_size_unset(tmp_path):
    root = Path(__file__).resolve().parent.parent
    runtime_ts_path = root / "nanocalibur" / "runtime" / "interpreter.ts"
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "npx",
            "-p",
            "typescript",
            "tsc",
            str(runtime_ts_path),
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

    script = textwrap.dedent(
        f"""
        const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});
        const spec = {{
          schemas: {{
            Coin: {{
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
          actors: [],
          globals: [],
          predicates: [],
          rules: [
            {{ condition: {{ kind: "keyboard", phase: "begin", key: "E" }}, action: "spawn_coin" }}
          ]
        }};

        const actions = {{
          spawn_coin: (ctx) => {{
            ctx.scene.spawnActor("Coin", "", {{ x: 120, y: 220, sprite: "coin" }});
          }}
        }};

        const i = new NanoCaliburInterpreter(spec, actions, {{}});
        i.tick({{ keyboard: {{ begin: ["E"], on: ["E"], end: [] }} }});

        const actor = i.getState().actors[0];
        console.log(JSON.stringify({{
          uid: actor.uid,
          hasW: Object.prototype.hasOwnProperty.call(actor, "w"),
          hasH: Object.prototype.hasOwnProperty.call(actor, "h"),
          blockMask: actor.block_mask,
          x: actor.x,
          y: actor.y
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
    assert values["uid"] == "coin_1"
    assert values["hasW"] is False
    assert values["hasH"] is False
    assert values["blockMask"] is None
    assert values["x"] == 120
    assert values["y"] == 220


def test_runtime_tick_generator_action_delays_execution(tmp_path):
    root = Path(__file__).resolve().parent.parent
    runtime_ts_path = root / "nanocalibur" / "runtime" / "interpreter.ts"
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "npx",
            "-p",
            "typescript",
            "tsc",
            str(runtime_ts_path),
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

    script = textwrap.dedent(
        f"""
        const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});

        const spec = {{
          actors: [],
          globals: [{{ name: "count", kind: "int", value: 0 }}],
          predicates: [],
          rules: [
            {{ condition: {{ kind: "keyboard", phase: "begin", key: "E" }}, action: "delayed_inc" }}
          ]
        }};

        const actions = {{
          delayed_inc: function* (ctx) {{
            yield ctx.tick;
            yield ctx.tick;
            ctx.globals.count = ctx.globals.count + 1;
          }}
        }};

        const i = new NanoCaliburInterpreter(spec, actions, {{}});
        const counts = [];
        i.tick({{ keyboard: {{ begin: ["E"], on: ["E"], end: [] }} }});
        counts.push(i.getState().globals.count);
        i.tick({{ keyboard: {{ begin: [], on: [], end: [] }} }});
        counts.push(i.getState().globals.count);
        i.tick({{ keyboard: {{ begin: [], on: [], end: [] }} }});
        counts.push(i.getState().globals.count);
        i.tick({{ keyboard: {{ begin: [], on: [], end: [] }} }});
        counts.push(i.getState().globals.count);
        console.log(JSON.stringify(counts));
        """
    )

    proc = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    counts = json.loads(proc.stdout.strip())
    assert counts == [0, 0, 0, 1]


def test_runtime_button_condition_matches_ui_buttons(tmp_path):
    root = Path(__file__).resolve().parent.parent
    runtime_ts_path = root / "nanocalibur" / "runtime" / "interpreter.ts"
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "npx",
            "-p",
            "typescript",
            "tsc",
            str(runtime_ts_path),
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

    script = textwrap.dedent(
        f"""
        const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});

        const spec = {{
          actors: [],
          globals: [{{ name: "count", kind: "int", value: 0 }}],
          predicates: [],
          rules: [
            {{ condition: {{ kind: "button", name: "spawn_bonus" }}, action: "inc" }}
          ]
        }};

        const actions = {{
          inc: (ctx) => {{
            ctx.globals.count = ctx.globals.count + 1;
          }}
        }};

        const i = new NanoCaliburInterpreter(spec, actions, {{}});
        i.tick({{ uiButtons: ["other"] }});
        i.tick({{ uiButtons: ["spawn_bonus"] }});
        console.log(JSON.stringify(i.getState().globals.count));
        """
    )

    proc = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    count = json.loads(proc.stdout.strip())
    assert count == 1


def test_runtime_collision_modes_distinguish_overlap_and_contact(tmp_path):
    root = Path(__file__).resolve().parent.parent
    runtime_ts_path = root / "nanocalibur" / "runtime" / "interpreter.ts"
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "npx",
            "-p",
            "typescript",
            "tsc",
            str(runtime_ts_path),
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

    script = textwrap.dedent(
        f"""
        const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});

        const spec = {{
          actors: [
            {{ type: "Player", uid: "hero", fields: {{ x: 10, y: 10, active: true }} }},
            {{ type: "Coin", uid: "coin_1", fields: {{ x: 10, y: 10, active: true }} }}
          ],
          globals: [
            {{ name: "overlap_count", kind: "int", value: 0 }},
            {{ name: "contact_count", kind: "int", value: 0 }}
          ],
          predicates: [],
          rules: [
            {{
              condition: {{
                kind: "collision",
                mode: "overlap",
                left: {{ kind: "with_uid", actor_type: "Player", uid: "hero" }},
                right: {{ kind: "any", actor_type: "Coin", uid: null }}
              }},
              action: "on_overlap"
            }},
            {{
              condition: {{
                kind: "collision",
                mode: "contact",
                left: {{ kind: "with_uid", actor_type: "Player", uid: "hero" }},
                right: {{ kind: "any", actor_type: "Coin", uid: null }}
              }},
              action: "on_contact"
            }}
          ]
        }};

        const actions = {{
          on_overlap: (ctx) => {{
            ctx.globals.overlap_count = ctx.globals.overlap_count + 1;
          }},
          on_contact: (ctx) => {{
            ctx.globals.contact_count = ctx.globals.contact_count + 1;
          }}
        }};

        const i = new NanoCaliburInterpreter(spec, actions, {{}});
        i.tick({{
          collisions: [{{ aUid: "hero", bUid: "coin_1" }}],
          contacts: []
        }});
        i.tick({{
          collisions: [],
          contacts: [{{ aUid: "hero", bUid: "coin_1" }}]
        }});

        console.log(JSON.stringify(i.getState().globals));
        """
    )

    proc = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    values = json.loads(proc.stdout.strip())
    assert values["overlap_count"] == 1
    assert values["contact_count"] == 1
