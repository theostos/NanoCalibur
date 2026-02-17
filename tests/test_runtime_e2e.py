import json
import subprocess
import textwrap
from pathlib import Path

from exporter import export_project


def test_end_to_end_python_to_js_runtime(tmp_path):
    source = textwrap.dedent(
        """
        class Player(ActorModel):
            life: int
            x: int
            y: int

        def heal(target: Global["target_player"], amount: Global["heal_amount"]):
            target.life = target.life + amount

        def on_collision(player: Player["main_character"]):
            player.life = player.life - 1

        def mark_dead(player: Player["main_character"], flag: Global["is_dead"]):
            flag = True

        def is_dead(player: Player) -> bool:
            return player.life <= 0

        game = Game()
        game.add_global("target_player", WithUID(Player, "main_character"))
        game.add_global("heal_amount", 2)
        game.add_global("is_dead", False)
        game.add_actor(Player, "main_character", life=1, x=5, y=7)
        game.add_actor(Player, "enemy_1", life=2, x=0, y=0)

        game.add_rule(KeyboardCondition.begin_press("A"), heal)
        game.add_rule(CollisionRelated(WithUID(Player, "main_character"), Any(Player)), on_collision)
        game.add_rule(LogicalRelated(is_dead, Any(Player)), mark_dead)

        game.set_camera(Camera.follow("main_character"))
        game.set_map(TileMap(width=10, height=10, tile_size=16, solid=[(1, 1)]))
        """
    )

    export_project(source, str(tmp_path))

    runtime_path = (
        Path(__file__).resolve().parent.parent
        / "nanocalibur"
        / "runtime"
        / "interpreter.js"
    )
    runner_path = tmp_path / "run_runtime_test.js"
    runner_path.write_text(
        textwrap.dedent(
            f"""
            const spec = require({json.dumps(str(tmp_path / "game_spec.json"))});
            const logic = require({json.dumps(str(tmp_path / "game_logic.js"))});
            const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});

            const actions = {{
              heal: logic.heal,
              on_collision: logic.on_collision,
              mark_dead: logic.mark_dead
            }};
            const predicates = {{
              is_dead: logic.is_dead
            }};

            const interpreter = new NanoCaliburInterpreter(spec, actions, predicates);

            interpreter.tick({{
              keyboard: {{ begin: ["A"], on: ["A"], end: [] }},
              collisions: [{{ aUid: "main_character", bUid: "enemy_1" }}]
            }});
            interpreter.tick({{
              keyboard: {{ begin: [], on: ["A"], end: [] }},
              collisions: [{{ aUid: "main_character", bUid: "enemy_1" }}]
            }});
            interpreter.tick({{
              keyboard: {{ begin: [], on: [], end: ["A"] }},
              collisions: [{{ aUid: "main_character", bUid: "enemy_1" }}]
            }});

            const state = interpreter.getState();
            const result = {{
              life: state.actors.find((a) => a.uid === "main_character").life,
              is_dead: state.globals.is_dead,
              camera: interpreter.getCameraState(),
              solid_16_16: interpreter.isSolidAtWorld(16, 16)
            }};
            console.log(JSON.stringify(result));
            """
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        ["node", str(runner_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(proc.stdout.strip())
    assert result["life"] == 0
    assert result["is_dead"] is True
    assert result["camera"]["mode"] == "follow"
    assert result["camera"]["x"] == 5
    assert result["camera"]["y"] == 7
    assert result["solid_16_16"] is True
