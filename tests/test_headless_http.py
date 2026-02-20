import json
import subprocess
import textwrap
import time
import urllib.request
from pathlib import Path


def _http_get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _http_post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def test_headless_http_server_allows_tool_call_via_http_client(tmp_path):
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
            str(runtime_dir / "headless_http_server.ts"),
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
    http_server_path = compiled_dir / "headless_http_server.js"

    server_script = tmp_path / "run_server.js"
    server_script.write_text(
        textwrap.dedent(
            f"""
            const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});
            const {{ HeadlessHost }} = require({json.dumps(str(headless_path))});
            const {{ HeadlessHttpServer }} = require({json.dumps(str(http_server_path))});

            (async () => {{
              const spec = {{
                actors: [
                  {{ type: "Player", uid: "hero", fields: {{ x: 16, y: 16, sprite: "hero" }} }}
                ],
                globals: [{{ name: "count", kind: "int", value: 0 }}],
                predicates: [],
                tools: [{{ name: "nudge", tool_docstring: "Move hero right", action: "nudge" }}],
                rules: [
                  {{ condition: {{ kind: "tool", name: "nudge", tool_docstring: "Move hero right" }}, action: "nudge" }}
                ],
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
              const httpServer = new HeadlessHttpServer(host);
              const port = await httpServer.start({{ host: "127.0.0.1", port: 0 }});

              process.stdout.write(String(port) + "\\n");
              process.stdin.resume();
              process.stdin.on("end", async () => {{
                await httpServer.stop();
                process.exit(0);
              }});
            }})().catch((error) => {{
              console.error(error);
              process.exit(1);
            }});
            """
        ),
        encoding="utf-8",
    )

    proc = subprocess.Popen(
        ["node", str(server_script)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        port_line = proc.stdout.readline().strip()
        assert port_line
        port = int(port_line)
        base_url = f"http://127.0.0.1:{port}"

        tools = _http_get_json(base_url + "/tools")
        assert tools["tools"][0]["name"] == "nudge"

        frame_before = _http_get_json(base_url + "/frame")
        assert frame_before["frame"]["rows"][1][1] == "@"

        call_result = _http_post_json(
            base_url + "/tools/call",
            {"name": "nudge", "arguments": {}},
        )
        assert call_result["state"]["globals"]["count"] == 1

        state = _http_get_json(base_url + "/state")
        assert state["state"]["globals"]["count"] == 1
        assert state["state"]["actors"][0]["x"] == 32

        frame_after = _http_get_json(base_url + "/frame")
        assert frame_after["frame"]["rows"][1][2] == "@"
    finally:
        if proc.stdin:
            proc.stdin.close()
        proc.wait(timeout=5)
        if proc.returncode != 0:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise AssertionError(f"Server process exited with code {proc.returncode}: {stderr}")


def test_headless_http_server_session_endpoints_support_join_start_and_commands(tmp_path):
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
            str(runtime_dir / "headless_http_server.ts"),
            str(runtime_dir / "headless_host.ts"),
            str(runtime_dir / "runtime_core.ts"),
            str(runtime_dir / "symbolic_renderer.ts"),
            str(runtime_dir / "interpreter.ts"),
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
    http_server_path = compiled_dir / "headless_http_server.js"
    session_manager_path = compiled_dir / "session_manager.js"

    server_script = tmp_path / "run_session_server.js"
    server_script.write_text(
        textwrap.dedent(
            f"""
            const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});
            const {{ HeadlessHost }} = require({json.dumps(str(headless_path))});
            const {{ HeadlessHttpServer }} = require({json.dumps(str(http_server_path))});
            const {{ SessionManager }} = require({json.dumps(str(session_manager_path))});

            function createHost() {{
              const spec = {{
                actors: [],
                globals: [{{ name: "count", kind: "int", value: 0 }}],
                predicates: [],
                tools: [{{ name: "nudge", tool_docstring: "Move count", action: "nudge" }}],
                rules: [
                  {{ condition: {{ kind: "tool", name: "nudge" }}, action: "nudge" }}
                ]
              }};
              const actions = {{
                nudge: (ctx) => {{
                  ctx.globals.count = ctx.globals.count + 1;
                }}
              }};
              return new HeadlessHost(new NanoCaliburInterpreter(spec, actions, {{}}), {{}});
            }}

            (async () => {{
              const manager = new SessionManager();
              const httpServer = new HeadlessHttpServer(createHost(), manager, createHost);
              const port = await httpServer.start({{ host: "127.0.0.1", port: 0 }});

              process.stdout.write(String(port) + "\\n");
              process.stdin.resume();
              process.stdin.on("end", async () => {{
                await httpServer.stop();
                process.exit(0);
              }});
            }})().catch((error) => {{
              console.error(error);
              process.exit(1);
            }});
            """
        ),
        encoding="utf-8",
    )

    proc = subprocess.Popen(
        ["node", str(server_script)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        port_line = proc.stdout.readline().strip()
        assert port_line
        port = int(port_line)
        base_url = f"http://127.0.0.1:{port}"

        created = _http_post_json(
            base_url + "/sessions",
            {
                "session_id": "sess_1",
                "roles": [{"id": "llm_1", "required": True}],
                "loop_mode": "turn_based",
            },
        )
        assert isinstance(created["session_id"], str)
        assert created["session_id"]
        assert created["session_id"] != "sess_1"
        assert created["admin_token"]
        assert created["loop_mode"] == "real_time"
        assert any(role["role_id"] == "llm_1" for role in created["roles"])
        session_id = created["session_id"]
        invite_token = created["invites"][0]["invite_token"]

        open_roles = _http_get_json(base_url + "/open-roles")
        assert any(entry["session_id"] == session_id for entry in open_roles["sessions"])

        sessions_payload = _http_get_json(base_url + "/sessions")
        assert any(entry["session_id"] == session_id for entry in sessions_payload["sessions"])
        listed = next(
            entry for entry in sessions_payload["sessions"] if entry["session_id"] == session_id
        )
        assert listed["loop_mode"] == "real_time"
        assert any(role["role_id"] == "llm_1" for role in listed["roles"])

        joined = _http_post_json(base_url + "/join", {"invite_token": invite_token})
        assert joined["session_id"] == session_id
        assert joined["role_id"] == "llm_1"
        assert joined["access_token"]

        started = _http_post_json(
            base_url + f"/sessions/{session_id}/start",
            {"admin_token": created["admin_token"]},
        )
        assert started["status"] == "running"

        command_result = _http_post_json(
            base_url + f"/sessions/{session_id}/commands",
            {
                "access_token": joined["access_token"],
                "commands": [{"kind": "tool", "name": "nudge"}],
            },
        )
        assert command_result["state"]["globals"]["count"] == 1

        session_open_roles = _http_get_json(base_url + f"/sessions/{session_id}/open-roles")
        assert session_open_roles["roles"] == []
    finally:
        if proc.stdin:
            proc.stdin.close()
        proc.wait(timeout=5)
        if proc.returncode != 0:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise AssertionError(f"Server process exited with code {proc.returncode}: {stderr}")


def test_headless_http_server_running_session_ticks_without_stream_subscribers(tmp_path):
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
            str(runtime_dir / "headless_http_server.ts"),
            str(runtime_dir / "headless_host.ts"),
            str(runtime_dir / "runtime_core.ts"),
            str(runtime_dir / "symbolic_renderer.ts"),
            str(runtime_dir / "interpreter.ts"),
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
    http_server_path = compiled_dir / "headless_http_server.js"
    session_manager_path = compiled_dir / "session_manager.js"

    server_script = tmp_path / "run_session_server_ticking.js"
    server_script.write_text(
        textwrap.dedent(
            f"""
            const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});
            const {{ HeadlessHost }} = require({json.dumps(str(headless_path))});
            const {{ HeadlessHttpServer }} = require({json.dumps(str(http_server_path))});
            const {{ SessionManager }} = require({json.dumps(str(session_manager_path))});

            function createHost() {{
              const spec = {{
                actors: [],
                globals: [{{ name: "count", kind: "int", value: 0 }}],
                predicates: [],
                tools: [],
                rules: []
              }};
              return new HeadlessHost(new NanoCaliburInterpreter(spec, {{}}, {{}}), {{}});
            }}

            (async () => {{
              const manager = new SessionManager();
              const httpServer = new HeadlessHttpServer(createHost(), manager, createHost);
              const port = await httpServer.start({{ host: "127.0.0.1", port: 0 }});

              process.stdout.write(String(port) + "\\n");
              process.stdin.resume();
              process.stdin.on("end", async () => {{
                await httpServer.stop();
                process.exit(0);
              }});
            }})().catch((error) => {{
              console.error(error);
              process.exit(1);
            }});
            """
        ),
        encoding="utf-8",
    )

    proc = subprocess.Popen(
        ["node", str(server_script)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        port_line = proc.stdout.readline().strip()
        assert port_line
        port = int(port_line)
        base_url = f"http://127.0.0.1:{port}"

        created = _http_post_json(
            base_url + "/sessions",
            {"roles": [{"id": "human_1", "required": True}]},
        )
        session_id = created["session_id"]
        invite_token = created["invites"][0]["invite_token"]
        joined = _http_post_json(base_url + "/join", {"invite_token": invite_token})

        _http_post_json(
            base_url + f"/sessions/{session_id}/start",
            {"admin_token": created["admin_token"]},
        )

        snapshot_1 = _http_get_json(
            base_url
            + f"/sessions/{session_id}/snapshot?access_token={joined['access_token']}"
        )
        elapsed_1 = snapshot_1["state"]["scene"]["elapsed"]
        time.sleep(0.25)
        snapshot_2 = _http_get_json(
            base_url
            + f"/sessions/{session_id}/snapshot?access_token={joined['access_token']}"
        )
        elapsed_2 = snapshot_2["state"]["scene"]["elapsed"]

        assert isinstance(elapsed_1, (int, float))
        assert isinstance(elapsed_2, (int, float))
        assert elapsed_2 > elapsed_1
    finally:
        if proc.stdin:
            proc.stdin.close()
        proc.wait(timeout=5)
        if proc.returncode != 0:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise AssertionError(f"Server process exited with code {proc.returncode}: {stderr}")


def test_headless_http_server_session_commands_can_enqueue_without_tick(tmp_path):
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
            str(runtime_dir / "headless_http_server.ts"),
            str(runtime_dir / "headless_host.ts"),
            str(runtime_dir / "runtime_core.ts"),
            str(runtime_dir / "symbolic_renderer.ts"),
            str(runtime_dir / "interpreter.ts"),
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
    http_server_path = compiled_dir / "headless_http_server.js"
    session_manager_path = compiled_dir / "session_manager.js"

    server_script = tmp_path / "run_session_server.js"
    server_script.write_text(
        textwrap.dedent(
            f"""
            const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});
            const {{ HeadlessHost }} = require({json.dumps(str(headless_path))});
            const {{ HeadlessHttpServer }} = require({json.dumps(str(http_server_path))});
            const {{ SessionManager }} = require({json.dumps(str(session_manager_path))});

            function createHost() {{
              const spec = {{
                actors: [],
                globals: [{{ name: "count", kind: "int", value: 0 }}],
                predicates: [],
                tools: [{{ name: "nudge", tool_docstring: "Move count", action: "nudge" }}],
                rules: [
                  {{ condition: {{ kind: "tool", name: "nudge" }}, action: "nudge" }}
                ]
              }};
              const actions = {{
                nudge: (ctx) => {{
                  ctx.globals.count = ctx.globals.count + 1;
                }}
              }};
              return new HeadlessHost(new NanoCaliburInterpreter(spec, actions, {{}}), {{}});
            }}

            (async () => {{
              const manager = new SessionManager();
              const httpServer = new HeadlessHttpServer(createHost(), manager, createHost);
              const port = await httpServer.start({{ host: "127.0.0.1", port: 0 }});

              process.stdout.write(String(port) + "\\n");
              process.stdin.resume();
              process.stdin.on("end", async () => {{
                await httpServer.stop();
                process.exit(0);
              }});
            }})().catch((error) => {{
              console.error(error);
              process.exit(1);
            }});
            """
        ),
        encoding="utf-8",
    )

    proc = subprocess.Popen(
        ["node", str(server_script)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        port_line = proc.stdout.readline().strip()
        assert port_line
        port = int(port_line)
        base_url = f"http://127.0.0.1:{port}"

        created = _http_post_json(
            base_url + "/sessions",
            {
                "roles": [{"id": "llm_1", "required": True}],
                "loop_mode": "turn_based",
            },
        )
        session_id = created["session_id"]
        invite_token = created["invites"][0]["invite_token"]
        joined = _http_post_json(base_url + "/join", {"invite_token": invite_token})

        _http_post_json(
            base_url + f"/sessions/{session_id}/start",
            {"admin_token": created["admin_token"]},
        )

        enqueue_only = _http_post_json(
            base_url + f"/sessions/{session_id}/commands",
            {
                "access_token": joined["access_token"],
                "tick": False,
                "commands": [{"kind": "tool", "name": "nudge"}],
            },
        )
        assert enqueue_only["state"]["globals"]["count"] == 0

        applied = _http_post_json(
            base_url + f"/sessions/{session_id}/commands",
            {
                "access_token": joined["access_token"],
                "commands": [],
            },
        )
        assert applied["state"]["globals"]["count"] == 1
    finally:
        if proc.stdin:
            proc.stdin.close()
        proc.wait(timeout=5)
        if proc.returncode != 0:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise AssertionError(f"Server process exited with code {proc.returncode}: {stderr}")


def test_headless_http_server_session_keyboard_begin_command_applies_role_scoped_rule(tmp_path):
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
            str(runtime_dir / "headless_http_server.ts"),
            str(runtime_dir / "headless_host.ts"),
            str(runtime_dir / "runtime_core.ts"),
            str(runtime_dir / "symbolic_renderer.ts"),
            str(runtime_dir / "interpreter.ts"),
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
    http_server_path = compiled_dir / "headless_http_server.js"
    session_manager_path = compiled_dir / "session_manager.js"

    server_script = tmp_path / "run_session_server_keyboard.js"
    server_script.write_text(
        textwrap.dedent(
            f"""
            const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});
            const {{ HeadlessHost }} = require({json.dumps(str(headless_path))});
            const {{ HeadlessHttpServer }} = require({json.dumps(str(http_server_path))});
            const {{ SessionManager }} = require({json.dumps(str(session_manager_path))});

            function createHost() {{
              const spec = {{
                actors: [],
                globals: [{{ name: "count", kind: "int", value: 0 }}],
                predicates: [],
                rules: [
                  {{
                    condition: {{ kind: "keyboard", phase: "begin", key: "g", role_id: "human_1" }},
                    action: "toggle_gravity"
                  }}
                ]
              }};
              const actions = {{
                toggle_gravity: (ctx) => {{
                  ctx.globals.count = ctx.globals.count + 1;
                }}
              }};
              return new HeadlessHost(new NanoCaliburInterpreter(spec, actions, {{}}), {{}});
            }}

            (async () => {{
              const manager = new SessionManager();
              const httpServer = new HeadlessHttpServer(createHost(), manager, createHost);
              const port = await httpServer.start({{ host: "127.0.0.1", port: 0 }});

              process.stdout.write(String(port) + "\\n");
              process.stdin.resume();
              process.stdin.on("end", async () => {{
                await httpServer.stop();
                process.exit(0);
              }});
            }})().catch((error) => {{
              console.error(error);
              process.exit(1);
            }});
            """
        ),
        encoding="utf-8",
    )

    proc = subprocess.Popen(
        ["node", str(server_script)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        port_line = proc.stdout.readline().strip()
        assert port_line
        port = int(port_line)
        base_url = f"http://127.0.0.1:{port}"

        created = _http_post_json(
            base_url + "/sessions",
            {
                "roles": [{"id": "human_1", "required": True}],
            },
        )
        session_id = created["session_id"]
        invite_token = created["invites"][0]["invite_token"]
        joined = _http_post_json(base_url + "/join", {"invite_token": invite_token})

        _http_post_json(
            base_url + f"/sessions/{session_id}/start",
            {"admin_token": created["admin_token"]},
        )

        result = _http_post_json(
            base_url + f"/sessions/{session_id}/commands",
            {
                "access_token": joined["access_token"],
                "commands": [
                    {"kind": "input", "keyboard": {"begin": ["g"]}},
                ],
            },
        )
        assert result["state"]["globals"]["count"] == 1
    finally:
        if proc.stdin:
            proc.stdin.close()
        proc.wait(timeout=5)
        if proc.returncode != 0:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise AssertionError(f"Server process exited with code {proc.returncode}: {stderr}")


def test_headless_http_server_role_clients_only_receive_their_own_role_state(tmp_path):
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
            str(runtime_dir / "headless_http_server.ts"),
            str(runtime_dir / "headless_host.ts"),
            str(runtime_dir / "runtime_core.ts"),
            str(runtime_dir / "symbolic_renderer.ts"),
            str(runtime_dir / "interpreter.ts"),
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
    http_server_path = compiled_dir / "headless_http_server.js"
    session_manager_path = compiled_dir / "session_manager.js"

    server_script = tmp_path / "run_session_server_roles.js"
    server_script.write_text(
        textwrap.dedent(
            f"""
            const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});
            const {{ HeadlessHost }} = require({json.dumps(str(headless_path))});
            const {{ HeadlessHttpServer }} = require({json.dumps(str(http_server_path))});
            const {{ SessionManager }} = require({json.dumps(str(session_manager_path))});

            function createHost() {{
              const spec = {{
                actors: [],
                globals: [],
                roles: [
                  {{
                    id: "human_1",
                    kind: "human",
                    required: true,
                    type: "HumanRole",
                    fields: {{ score: 1 }}
                  }},
                  {{
                    id: "human_2",
                    kind: "human",
                    required: true,
                    type: "HumanRole",
                    fields: {{ score: 5 }}
                  }}
                ],
                predicates: [],
                rules: [
                  {{
                    condition: {{ kind: "keyboard", phase: "begin", key: "e", role_id: "human_1" }},
                    action: "inc"
                  }}
                ]
              }};
              const actions = {{
                inc: (ctx) => {{
                  const self = ctx.getRoleById("human_1");
                  self.score = self.score + 1;
                }}
              }};
              return new HeadlessHost(new NanoCaliburInterpreter(spec, actions, {{}}), {{}});
            }}

            (async () => {{
              const manager = new SessionManager();
              const httpServer = new HeadlessHttpServer(createHost(), manager, createHost);
              const port = await httpServer.start({{ host: "127.0.0.1", port: 0 }});

              process.stdout.write(String(port) + "\\n");
              process.stdin.resume();
              process.stdin.on("end", async () => {{
                await httpServer.stop();
                process.exit(0);
              }});
            }})().catch((error) => {{
              console.error(error);
              process.exit(1);
            }});
            """
        ),
        encoding="utf-8",
    )

    proc = subprocess.Popen(
        ["node", str(server_script)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        port_line = proc.stdout.readline().strip()
        assert port_line
        port = int(port_line)
        base_url = f"http://127.0.0.1:{port}"

        created = _http_post_json(
            base_url + "/sessions",
            {
                "roles": [
                    {"id": "human_1", "required": True, "kind": "human"},
                    {"id": "human_2", "required": True, "kind": "human"},
                ],
            },
        )
        session_id = created["session_id"]
        invite_h1 = next(
            invite["invite_token"]
            for invite in created["invites"]
            if invite["role_id"] == "human_1"
        )
        invite_h2 = next(
            invite["invite_token"]
            for invite in created["invites"]
            if invite["role_id"] == "human_2"
        )
        joined_h1 = _http_post_json(base_url + "/join", {"invite_token": invite_h1})
        joined_h2 = _http_post_json(base_url + "/join", {"invite_token": invite_h2})

        _http_post_json(
            base_url + f"/sessions/{session_id}/start",
            {"admin_token": created["admin_token"]},
        )

        role_result = _http_post_json(
            base_url + f"/sessions/{session_id}/commands",
            {
                "access_token": joined_h1["access_token"],
                "commands": [{"kind": "input", "keyboard": {"begin": ["e"]}}],
            },
        )
        assert role_result["state"]["self"]["id"] == "human_1"
        assert role_result["state"]["self"]["score"] == 2
        assert set(role_result["state"]["roles"].keys()) == {"human_1"}
        assert "human_2" not in role_result["state"]["roles"]

        other_role_state = _http_get_json(
            base_url
            + f"/sessions/{session_id}/state?access_token={joined_h2['access_token']}"
        )
        assert other_role_state["state"]["self"]["id"] == "human_2"
        assert other_role_state["state"]["self"]["score"] == 5
        assert set(other_role_state["state"]["roles"].keys()) == {"human_2"}

        admin_state = _http_get_json(
            base_url
            + f"/sessions/{session_id}/state?admin_token={created['admin_token']}"
        )
        assert set(admin_state["state"]["roles"].keys()) == {"human_1", "human_2"}
        assert admin_state["state"]["self"] is None
    finally:
        if proc.stdin:
            proc.stdin.close()
        proc.wait(timeout=5)
        if proc.returncode != 0:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise AssertionError(f"Server process exited with code {proc.returncode}: {stderr}")
