import json
import subprocess
import textwrap
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
