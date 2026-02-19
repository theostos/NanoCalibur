import json
import subprocess
import textwrap
from pathlib import Path


def _compile_runtime(tmp_path: Path) -> tuple[Path, Path, Path]:
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
            str(runtime_dir / "interpreter.ts"),
            str(runtime_dir / "headless_host.ts"),
            str(runtime_dir / "runtime_core.ts"),
            str(runtime_dir / "symbolic_renderer.ts"),
            str(runtime_dir / "session_runtime.ts"),
            str(runtime_dir / "session_manager.ts"),
            str(runtime_dir / "replay_store_sqlite.ts"),
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

    return (
        compiled_dir / "interpreter.js",
        compiled_dir / "headless_host.js",
        compiled_dir / "session_runtime.js",
    )


def test_turn_based_runtime_allows_multiple_commands_until_next_turn(tmp_path):
    runtime_path, headless_path, session_runtime_path = _compile_runtime(tmp_path)

    script = textwrap.dedent(
        f"""
        const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});
        const {{ HeadlessHost }} = require({json.dumps(str(headless_path))});
        const {{ SessionRuntime }} = require({json.dumps(str(session_runtime_path))});

        const spec = {{
          actors: [],
          globals: [{{ name: "count", kind: "int", value: 0 }}],
          predicates: [],
          tools: [
            {{ name: "inc", tool_docstring: "inc", action: "inc" }},
            {{ name: "end", tool_docstring: "end", action: "end" }}
          ],
          rules: [
            {{ condition: {{ kind: "tool", name: "inc" }}, action: "inc" }},
            {{ condition: {{ kind: "tool", name: "end" }}, action: "end" }}
          ],
          multiplayer: {{ default_loop: "turn_based" }}
        }};

        const actions = {{
          inc: (ctx) => {{
            ctx.globals.count = ctx.globals.count + 1;
          }},
          end: (ctx) => {{
            ctx.scene.nextTurn();
          }}
        }};

        const interpreter = new NanoCaliburInterpreter(spec, actions, {{}});
        const host = new HeadlessHost(interpreter, {{}});
        const runtime = new SessionRuntime(host, {{ loopMode: "turn_based", roleOrder: ["p1"] }});

        runtime.enqueue("p1", {{ kind: "tool", name: "inc" }});
        runtime.enqueue("p1", {{ kind: "tool", name: "inc" }});
        runtime.tick();
        const afterFirst = host.getState().scene;
        const countAfterFirst = host.getState().globals.count;

        runtime.enqueue("p1", {{ kind: "tool", name: "end" }});
        runtime.enqueue("p1", {{ kind: "tool", name: "inc" }});
        runtime.tick();
        const afterSecond = host.getState().scene;
        const countAfterSecond = host.getState().globals.count;

        console.log(JSON.stringify({{
          countAfterFirst,
          firstTurn: afterFirst.turn,
          countAfterSecond,
          secondTurn: afterSecond.turn
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
    assert values["countAfterFirst"] == 2
    assert values["firstTurn"] == 0
    assert values["countAfterSecond"] == 2
    assert values["secondTurn"] == 1


def test_hybrid_runtime_stops_processing_cycle_when_next_turn_called(tmp_path):
    runtime_path, headless_path, session_runtime_path = _compile_runtime(tmp_path)

    script = textwrap.dedent(
        f"""
        const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});
        const {{ HeadlessHost }} = require({json.dumps(str(headless_path))});
        const {{ SessionRuntime }} = require({json.dumps(str(session_runtime_path))});

        const spec = {{
          actors: [],
          globals: [{{ name: "count", kind: "int", value: 0 }}],
          predicates: [],
          tools: [
            {{ name: "add_a", tool_docstring: "", action: "add_a" }},
            {{ name: "end_b", tool_docstring: "", action: "end_b" }},
            {{ name: "add_b", tool_docstring: "", action: "add_b" }}
          ],
          rules: [
            {{ condition: {{ kind: "tool", name: "add_a" }}, action: "add_a" }},
            {{ condition: {{ kind: "tool", name: "end_b" }}, action: "end_b" }},
            {{ condition: {{ kind: "tool", name: "add_b" }}, action: "add_b" }}
          ],
          multiplayer: {{ default_loop: "hybrid" }}
        }};

        const actions = {{
          add_a: (ctx) => {{ ctx.globals.count = ctx.globals.count + 1; }},
          end_b: (ctx) => {{ ctx.globals.count = ctx.globals.count + 10; ctx.scene.nextTurn(); }},
          add_b: (ctx) => {{ ctx.globals.count = ctx.globals.count + 100; }}
        }};

        const interpreter = new NanoCaliburInterpreter(spec, actions, {{}});
        const host = new HeadlessHost(interpreter, {{}});
        const runtime = new SessionRuntime(host, {{ loopMode: "hybrid", roleOrder: ["a", "b"] }});

        runtime.enqueue("a", {{ kind: "tool", name: "add_a" }});
        runtime.enqueue("b", {{ kind: "tool", name: "end_b" }});
        runtime.enqueue("b", {{ kind: "tool", name: "add_b" }});
        runtime.tick();
        const firstCount = host.getState().globals.count;
        const firstTurn = host.getState().scene.turn;

        runtime.tick();
        const secondCount = host.getState().globals.count;
        const secondTurn = host.getState().scene.turn;

        console.log(JSON.stringify({{
          firstCount,
          firstTurn,
          secondCount,
          secondTurn
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
    assert values["firstCount"] == 11
    assert values["firstTurn"] == 1
    assert values["secondCount"] == 111
    assert values["secondTurn"] == 1


def test_session_runtime_passes_role_id_for_scoped_keyboard_conditions(tmp_path):
    runtime_path, headless_path, session_runtime_path = _compile_runtime(tmp_path)

    script = textwrap.dedent(
        f"""
        const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});
        const {{ HeadlessHost }} = require({json.dumps(str(headless_path))});
        const {{ SessionRuntime }} = require({json.dumps(str(session_runtime_path))});

        const spec = {{
          actors: [],
          globals: [{{ name: "moves", kind: "int", value: 0 }}],
          predicates: [],
          rules: [
            {{
              condition: {{ kind: "keyboard", phase: "on", key: "d", role_id: "human_1" }},
              action: "move"
            }}
          ]
        }};

        const actions = {{
          move: (ctx) => {{
            ctx.globals.moves = ctx.globals.moves + 1;
          }}
        }};

        const interpreter = new NanoCaliburInterpreter(spec, actions, {{}});
        const host = new HeadlessHost(interpreter, {{}});
        const runtime = new SessionRuntime(host, {{
          loopMode: "real_time",
          roleOrder: ["human_1", "dummy_1"]
        }});

        runtime.enqueue("dummy_1", {{
          kind: "input",
          keyboard: {{ on: ["d"] }}
        }});
        runtime.enqueue("human_1", {{
          kind: "input",
          keyboard: {{ on: ["d"] }}
        }});
        runtime.tick();

        console.log(JSON.stringify(host.getState().globals));
        """
    )

    proc = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    values = json.loads(proc.stdout.strip())
    assert values["moves"] == 1


def test_session_runtime_keeps_velocity_set_by_action(tmp_path):
    runtime_path, headless_path, session_runtime_path = _compile_runtime(tmp_path)

    script = textwrap.dedent(
        f"""
        const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});
        const {{ HeadlessHost }} = require({json.dumps(str(headless_path))});
        const {{ SessionRuntime }} = require({json.dumps(str(session_runtime_path))});

        const spec = {{
          actors: [
            {{
              type: "Player",
              uid: "hero",
              fields: {{ x: 100, y: 100, w: 32, h: 32, vx: 0, vy: 0, speed: 120, active: true }}
            }}
          ],
          globals: [],
          predicates: [],
          rules: [
            {{
              condition: {{ kind: "keyboard", phase: "on", key: "d", role_id: "human_1" }},
              action: "move_right"
            }}
          ],
          multiplayer: {{ default_loop: "hybrid" }}
        }};

        const actions = {{
          move_right: (ctx) => {{
            const hero = ctx.getActorByUid("hero");
            hero.vx = hero.speed;
          }}
        }};

        const interpreter = new NanoCaliburInterpreter(spec, actions, {{}});
        const host = new HeadlessHost(interpreter, {{}});
        const runtime = new SessionRuntime(host, {{
          loopMode: "hybrid",
          roleOrder: ["human_1", "dummy_1"],
          defaultStepSeconds: 0.05
        }});

        const beforeX = host.getState().actors.find((actor) => actor.uid === "hero").x;
        runtime.enqueue("human_1", {{ kind: "input", keyboard: {{ on: ["d"] }} }});
        runtime.tick();
        const afterInput = host.getState().actors.find((actor) => actor.uid === "hero");
        const afterInputX = afterInput.x;
        const afterInputVx = afterInput.vx;
        runtime.tick();
        runtime.tick();
        const afterPassiveX = host.getState().actors.find((actor) => actor.uid === "hero").x;

        console.log(JSON.stringify({{
          beforeX,
          afterInputX,
          afterPassiveX,
          afterInputVx
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
    assert values["afterInputVx"] == 120
    assert values["afterInputX"] > values["beforeX"]
    assert values["afterPassiveX"] > values["afterInputX"]


def test_parent_bound_child_follows_parent_physics_motion(tmp_path):
    runtime_path, headless_path, session_runtime_path = _compile_runtime(tmp_path)

    script = textwrap.dedent(
        f"""
        const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});
        const {{ HeadlessHost }} = require({json.dumps(str(headless_path))});
        const {{ SessionRuntime }} = require({json.dumps(str(session_runtime_path))});

        const spec = {{
          actors: [
            {{
              type: "Player",
              uid: "hero",
              fields: {{ x: 100, y: 100, w: 32, h: 32, vx: 0, vy: 0, speed: 120, active: true }}
            }},
            {{
              type: "Coin",
              uid: "pet",
              fields: {{ x: 132, y: 100, w: 16, h: 16, vx: 0, vy: 0, parent: "hero", active: true }}
            }}
          ],
          globals: [],
          predicates: [],
          rules: [
            {{
              condition: {{ kind: "keyboard", phase: "on", key: "d", role_id: "human_1" }},
              action: "move_right"
            }}
          ],
          multiplayer: {{ default_loop: "hybrid" }}
        }};

        const actions = {{
          move_right: (ctx) => {{
            const hero = ctx.getActorByUid("hero");
            hero.vx = hero.speed;
          }}
        }};

        const interpreter = new NanoCaliburInterpreter(spec, actions, {{}});
        const host = new HeadlessHost(interpreter, {{}});
        const runtime = new SessionRuntime(host, {{
          loopMode: "hybrid",
          roleOrder: ["human_1", "dummy_1"],
          defaultStepSeconds: 0.05
        }});

        const before = host.getState().actors;
        const heroBeforeX = before.find((actor) => actor.uid === "hero").x;
        const petBeforeX = before.find((actor) => actor.uid === "pet").x;

        runtime.enqueue("human_1", {{ kind: "input", keyboard: {{ on: ["d"] }} }});
        runtime.tick();
        runtime.tick();
        runtime.tick();

        const after = host.getState().actors;
        const heroAfter = after.find((actor) => actor.uid === "hero");
        const petAfter = after.find((actor) => actor.uid === "pet");

        console.log(JSON.stringify({{
          heroDx: heroAfter.x - heroBeforeX,
          petDx: petAfter.x - petBeforeX
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
    assert values["heroDx"] > 0
    assert values["petDx"] == values["heroDx"]


def test_session_manager_enforces_unique_seeds(tmp_path):
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
            str(runtime_dir / "interpreter.ts"),
            str(runtime_dir / "headless_host.ts"),
            str(runtime_dir / "runtime_core.ts"),
            str(runtime_dir / "symbolic_renderer.ts"),
            str(runtime_dir / "session_runtime.ts"),
            str(runtime_dir / "session_manager.ts"),
            str(runtime_dir / "replay_store_sqlite.ts"),
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
    manager_path = compiled_dir / "session_manager.js"

    script = textwrap.dedent(
        f"""
        const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});
        const {{ HeadlessHost }} = require({json.dumps(str(headless_path))});
        const {{ SessionManager }} = require({json.dumps(str(manager_path))});

        const spec = {{ actors: [], globals: [], predicates: [], rules: [] }};
        const makeHost = () => new HeadlessHost(new NanoCaliburInterpreter(spec, {{}}, {{}}), {{}});

        const manager = new SessionManager();
        const s1 = manager.createSession("s1", makeHost(), {{ seed: "seed-fixed" }});

        let duplicateRejected = false;
        try {{
          manager.createSession("s2", makeHost(), {{ seed: "seed-fixed" }});
        }} catch (_error) {{
          duplicateRejected = true;
        }}

        const s3 = manager.createSession("s3", makeHost(), {{}});
        const s4 = manager.createSession("s4", makeHost(), {{}});

        console.log(JSON.stringify({{
          s1Seed: s1.seed,
          duplicateRejected,
          autoDifferent: s3.seed !== s4.seed
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
    assert values["s1Seed"] == "seed-fixed"
    assert values["duplicateRejected"] is True
    assert values["autoDifferent"] is True


def test_session_runtime_pacing_limits_elapsed_progression(tmp_path):
    runtime_path, headless_path, session_runtime_path = _compile_runtime(tmp_path)

    script = textwrap.dedent(
        f"""
        (async () => {{
          const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});
          const {{ HeadlessHost }} = require({json.dumps(str(headless_path))});
          const {{ SessionRuntime }} = require({json.dumps(str(session_runtime_path))});

          const spec = {{ actors: [], globals: [], predicates: [], rules: [] }};
          const interpreter = new NanoCaliburInterpreter(spec, {{}}, {{}});
          const host = new HeadlessHost(interpreter, {{}});
          const runtime = new SessionRuntime(host, {{
            loopMode: "real_time",
            roleOrder: ["p1"],
            defaultStepSeconds: 0.05,
            pace: {{ gameTimeScale: 0.1, maxCatchupSteps: 1 }}
          }});

          runtime.tick();
          const firstElapsed = host.getState().scene.elapsed;

          runtime.tick();
          const secondElapsed = host.getState().scene.elapsed;

          runtime.setPace({{ gameTimeScale: 1.0 }});
          await new Promise((resolve) => setTimeout(resolve, 70));
          runtime.tick();
          const thirdElapsed = host.getState().scene.elapsed;

          console.log(JSON.stringify({{
            firstElapsed,
            secondElapsed,
            thirdElapsed
          }}));
        }})().catch((error) => {{
          console.error(error);
          process.exit(1);
        }});
        """
    )

    proc = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    values = json.loads(proc.stdout.strip())
    assert values["firstElapsed"] == 1
    assert values["secondElapsed"] == 1
    assert values["thirdElapsed"] >= 2
