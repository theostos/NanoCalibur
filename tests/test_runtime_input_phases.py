import json
import subprocess
import textwrap
from pathlib import Path


def test_runtime_keyboard_and_mouse_phase_matching():
    runtime_path = (
        Path(__file__).resolve().parent.parent
        / "nanocalibur"
        / "runtime"
        / "interpreter.js"
    )

    script = textwrap.dedent(
        f"""
        const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});

        const spec = {{
          actors: [],
          globals: [
            {{ name: "kb_begin", kind: "int", value: 0 }},
            {{ name: "kb_on", kind: "int", value: 0 }},
            {{ name: "kb_end", kind: "int", value: 0 }},
            {{ name: "ms_begin", kind: "int", value: 0 }},
            {{ name: "ms_on", kind: "int", value: 0 }},
            {{ name: "ms_end", kind: "int", value: 0 }}
          ],
          predicates: [],
          rules: [
            {{ condition: {{ kind: "keyboard", phase: "begin", key: "A" }}, action: "inc_kb_begin" }},
            {{ condition: {{ kind: "keyboard", phase: "on", key: "A" }}, action: "inc_kb_on" }},
            {{ condition: {{ kind: "keyboard", phase: "end", key: "A" }}, action: "inc_kb_end" }},
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
    assert values["ms_begin"] == 1
    assert values["ms_on"] == 2
    assert values["ms_end"] == 1
