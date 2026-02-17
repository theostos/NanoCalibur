import json
import subprocess
import sys
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BUILD_SCRIPT = ROOT / "examples" / "build_web_scene.py"


def _write_scene(path: Path) -> None:
    path.write_text(
        textwrap.dedent(
            """
            class Player(ActorModel):
                x: int
                y: int
                speed: int


            def move_right(player: Player["main_character"]):
                player.x = player.x + player.speed


            game = Game()
            game.add_actor(Player, "main_character", x=10, y=20, speed=2)
            game.add_rule(KeyboardCondition.on_press("ArrowRight"), move_right)
            game.set_camera(Camera.follow("main_character"))
            """
        ),
        encoding="utf-8",
    )


def test_build_web_scene_generates_excalibur_input_bundle(tmp_path):
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

    expected_files = {
        "game_spec.json",
        "game_ir.json",
        "game_logic.ts",
        "game_logic.js",
        "game_logic.mjs",
        "interpreter.ts",
        "interpreter.js",
        "interpreter.mjs",
        "bridge.ts",
        "index.ts",
        "README.generated.md",
    }
    actual_files = {p.name for p in output_dir.iterdir() if p.is_file()}
    assert expected_files.issubset(actual_files)

    spec = json.loads((output_dir / "game_spec.json").read_text(encoding="utf-8"))
    assert spec["camera"]["mode"] == "follow"
    assert spec["rules"][0]["condition"]["kind"] == "keyboard"

    bridge_code = (output_dir / "bridge.ts").read_text(encoding="utf-8")
    assert "class NanoCaliburBridge" in bridge_code


def test_build_web_scene_syncs_bundle_into_excalibur_project(tmp_path):
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
