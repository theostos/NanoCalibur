import json
import subprocess
import sys
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BUILD_SCRIPT = ROOT / "nanocalibur" / "build_game.py"


def _write_scene(path: Path) -> None:
    path.write_text(
        textwrap.dedent(
            """
            CodeBlock.begin("main_game")
            \"\"\"Main game assembly\"\"\"

            class Player(ActorModel):
                x: int
                y: int
                speed: int


            def move_right(player: Player["main_character"]):
                player.x = player.x + player.speed


            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
            scene.add_actor(Player(uid="main_character", x=10, y=20, speed=2))
            scene.add_rule(KeyboardCondition.on_press("ArrowRight", id="human_1"), move_right)
            scene.set_camera(Camera.follow("main_character"))

            CodeBlock.end("main_game")
            """
        ),
        encoding="utf-8",
    )


def test_build_game_generates_excalibur_input_bundle(tmp_path):
    scene_path = tmp_path / "scene.py"
    output_dir = tmp_path / "bundle"
    _write_scene(scene_path)

    subprocess.run(
        [
            sys.executable,
            str(BUILD_SCRIPT),
            str(scene_path),
            "--output",
            str(output_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    generated_dir = output_dir / "src" / "nanocalibur_generated"

    expected_files = {
        "game_spec.json",
        "game_ir.json",
        "game_logic.ts",
        "interpreter.ts",
        "runtime_core.ts",
        "canvas_host.ts",
        "headless_host.ts",
        "headless_http_server.ts",
        "session_runtime.ts",
        "session_manager.ts",
        "replay_store_sqlite.ts",
        "symbolic_renderer.ts",
        "bridge.ts",
        "index.ts",
        "node.ts",
    }
    actual_files = {p.name for p in generated_dir.iterdir() if p.is_file()}
    assert expected_files.issubset(actual_files)
    assert (generated_dir / "canvas").exists()
    assert (output_dir / "README.generated.md").exists()

    spec = json.loads((generated_dir / "game_spec.json").read_text(encoding="utf-8"))
    assert spec["camera"]["mode"] == "follow"
    assert spec["rules"][0]["condition"]["kind"] == "keyboard"

    bridge_code = (generated_dir / "bridge.ts").read_text(encoding="utf-8")
    assert "CanvasHost" in bridge_code
    assert "HeadlessHost" in bridge_code
    assert "ControllerConfig" not in bridge_code

    index_code = (generated_dir / "index.ts").read_text(encoding="utf-8")
    assert "createNanoCaliburMCPServer" in index_code
    assert "HeadlessHttpServer" not in index_code
    assert "ControllerConfig" not in index_code

    node_code = (generated_dir / "node.ts").read_text(encoding="utf-8")
    assert "HeadlessHttpServer" in node_code

    types_code = (generated_dir / "canvas" / "types.ts").read_text(encoding="utf-8")
    assert "controllers?:" not in types_code
    assert "gravity?:" in types_code
    assert "gravityScale" not in types_code


def test_build_game_syncs_bundle_into_excalibur_project(tmp_path):
    scene_path = tmp_path / "scene.py"
    output_dir = tmp_path / "bundle"
    project_dir = tmp_path / "sample-tiled-webpack"
    (project_dir / "src").mkdir(parents=True, exist_ok=True)
    _write_scene(scene_path)

    subprocess.run(
        [
            sys.executable,
            str(BUILD_SCRIPT),
            str(scene_path),
            "--output",
            str(output_dir),
            "--project",
            str(project_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    synced_dir = project_dir / "src" / "nanocalibur_generated"
    assert synced_dir.exists()
    assert (synced_dir / "index.ts").exists()
    assert (synced_dir / "game_spec.json").exists()


def test_build_game_allows_unboxed_mode_via_flag(tmp_path):
    scene_path = tmp_path / "main.py"
    scene_path.write_text(
        textwrap.dedent(
            """
            class Player(ActorModel):
                x: int
                y: int
                speed: int

            def move_right(player: Player["main_character"]):
                player.x = player.x + player.speed

            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
            scene.add_actor(Player(uid="main_character", x=10, y=20, speed=2))
            scene.add_rule(KeyboardCondition.on_press("ArrowRight", id="human_1"), move_right)
            """
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "bundle"

    subprocess.run(
        [
            sys.executable,
            str(BUILD_SCRIPT),
            str(scene_path),
            "--allow-unboxed",
            "--output",
            str(output_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    spec = json.loads(
        (output_dir / "src" / "nanocalibur_generated" / "game_spec.json").read_text(
            encoding="utf-8"
        )
    )
    assert spec["actors"][0]["uid"] == "main_character"


def test_build_game_resolves_local_relative_imports(tmp_path):
    output_dir = tmp_path / "bundle"
    (tmp_path / "entities.py").write_text(
        textwrap.dedent(
            """
            CodeBlock.begin("entities")
            \"\"\"entities\"\"\"

            class Player(ActorModel):
                x: int
                y: int
                speed: int

            CodeBlock.end("entities")
            """
        ),
        encoding="utf-8",
    )
    (tmp_path / "controls.py").write_text(
        textwrap.dedent(
            """
            from .entities import Player

            CodeBlock.begin("controls")
            \"\"\"controls\"\"\"

            @remote_condition(KeyboardCondition.on_press("ArrowRight", id="human_1"))
            def move_right(player: Player["main_character"]):
                player.x = player.x + player.speed

            CodeBlock.end("controls")
            """
        ),
        encoding="utf-8",
    )
    (tmp_path / "main.py").write_text(
        textwrap.dedent(
            """
            from .entities import Player
            from .controls import move_right

            CodeBlock.begin("main")
            \"\"\"main\"\"\"

            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
            scene.add_actor(Player(uid="main_character", x=10, y=20, speed=2))
            scene.add_rule(KeyboardCondition.on_press("ArrowRight", id="human_1"), move_right)

            CodeBlock.end("main")
            """
        ),
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            str(BUILD_SCRIPT),
            str(tmp_path / "main.py"),
            "--output",
            str(output_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    spec = json.loads(
        (output_dir / "src" / "nanocalibur_generated" / "game_spec.json").read_text(
            encoding="utf-8"
        )
    )
    assert "Player" in spec["schemas"]
    assert spec["rules"][0]["action"] == "move_right"
