import json
import subprocess
import textwrap
from pathlib import Path

from nanocalibur.exporter import export_project


def test_end_to_end_python_to_ts_runtime(tmp_path):
    source = textwrap.dedent(
        """
        class Player(ActorModel):
            life: int
            x: int
            y: int

        def heal(target: Global["target_player"], amount: Global["heal_amount"]):
            target.life = target.life + amount

        def on_collision(hero: Player, enemy: Player):
            hero.life = hero.life - 1

        def mark_dead(player: Player["main_character"], flag: Global["is_dead"]):
            flag = True

        def is_dead(player: Player) -> bool:
            return player.life <= 0

        game = Game()
        game.add_global("target_player", Player["main_character"])
        game.add_global("heal_amount", 2)
        game.add_global("is_dead", False)
        game.add_actor(Player, "main_character", life=1, x=5, y=7)
        game.add_actor(Player, "enemy_1", life=2, x=0, y=0)

        game.add_rule(KeyboardCondition.begin_press("A"), heal)
        game.add_rule(CollisionRelated(Player["main_character"], Player), on_collision)
        game.add_rule(LogicalRelated(is_dead, Player), mark_dead)

        game.set_camera(Camera.follow("main_character"))
        game.set_map(
            TileMap(
                tile_size=16,
                grid=[
                    [0, 0, 0],
                    [0, 1, 0],
                    [0, 0, 0],
                ],
                tiles={
                    1: Tile(block_mask=2, color=Color(40, 40, 40)),
                },
            )
        )
        """
    )

    export_project(source, str(tmp_path))

    runtime_ts_path = (
        Path(__file__).resolve().parent.parent
        / "nanocalibur"
        / "runtime"
        / "interpreter.ts"
    )
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "npx",
            "-p",
            "typescript",
            "tsc",
            str(tmp_path / "game_logic.ts"),
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
    logic_js_path = compiled_dir / "game_logic.js"
    runtime_path = compiled_dir / "interpreter.js"
    runner_path = tmp_path / "run_runtime_test.js"
    runner_path.write_text(
        textwrap.dedent(
            f"""
            const spec = require({json.dumps(str(tmp_path / "game_spec.json"))});
            const logic = require({json.dumps(str(logic_js_path))});
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


def test_logical_predicate_with_multi_bindings_and_elapsed(tmp_path):
    source = textwrap.dedent(
        """
        class Player(Actor):
            life: int

        def mark_dead(flag: Global["is_dead"]):
            flag = True

        def is_dead(scene: Scene, threshold: Global["threshold"], wait_tick: Tick, player: Player) -> bool:
            return player.life <= threshold and scene.elapsed >= 2 and wait_tick == wait_tick

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        game.add_global("is_dead", False)
        game.add_global("threshold", 1)
        scene.add_actor(Player(uid="hero", life=1))
        scene.add_rule(LogicalRelated(is_dead, Player), mark_dead)
        """
    )

    export_project(source, str(tmp_path))

    runtime_ts_path = (
        Path(__file__).resolve().parent.parent
        / "nanocalibur"
        / "runtime"
        / "interpreter.ts"
    )
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "npx",
            "-p",
            "typescript",
            "tsc",
            str(tmp_path / "game_logic.ts"),
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
    logic_js_path = compiled_dir / "game_logic.js"
    runtime_path = compiled_dir / "interpreter.js"
    runner_path = tmp_path / "run_runtime_logical_elapsed.js"
    runner_path.write_text(
        textwrap.dedent(
            f"""
            const spec = require({json.dumps(str(tmp_path / "game_spec.json"))});
            const logic = require({json.dumps(str(logic_js_path))});
            const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});

            const actions = {{
              mark_dead: logic.mark_dead
            }};
            const predicates = {{
              is_dead: logic.is_dead
            }};

            const interpreter = new NanoCaliburInterpreter(spec, actions, predicates);
            interpreter.tick({{}});
            interpreter.tick({{}});
            const beforeDead = interpreter.getState().globals.is_dead;
            interpreter.tick({{}});
            const after = interpreter.getState();

            console.log(JSON.stringify({{
              before_dead: beforeDead,
              after_dead: after.globals.is_dead,
              elapsed: after.scene.elapsed
            }}));
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
    assert result["before_dead"] is False
    assert result["after_dead"] is True
    assert result["elapsed"] == 3


def test_generator_actor_binding_rebinds_after_yield(tmp_path):
    source = textwrap.dedent(
        """
        class Coin(Actor):
            pass

        def spawn_after_wait(scene: Scene, tick: Tick, last_coin: Coin[-1]):
            for _ in range(2):
                yield tick
            if last_coin is not None:
                scene.spawn(Coin(x=last_coin.x + 1, y=0, active=True))

        def remove_last(last_coin: Coin[-1]):
            if last_coin is not None:
                last_coin.destroy()

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        scene.add_actor(Coin(uid="coin_1", x=10, y=0, active=True))
        scene.add_rule(KeyboardCondition.begin_press("E"), spawn_after_wait)
        scene.add_rule(KeyboardCondition.begin_press("D"), remove_last)
        """
    )

    export_project(source, str(tmp_path))

    runtime_ts_path = (
        Path(__file__).resolve().parent.parent
        / "nanocalibur"
        / "runtime"
        / "interpreter.ts"
    )
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "npx",
            "-p",
            "typescript",
            "tsc",
            str(tmp_path / "game_logic.ts"),
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
    logic_js_path = compiled_dir / "game_logic.js"
    runtime_path = compiled_dir / "interpreter.js"
    runner_path = tmp_path / "run_runtime_rebind_test.js"
    runner_path.write_text(
        textwrap.dedent(
            f"""
            const spec = require({json.dumps(str(tmp_path / "game_spec.json"))});
            const logic = require({json.dumps(str(logic_js_path))});
            const {{ NanoCaliburInterpreter }} = require({json.dumps(str(runtime_path))});

            const actions = {{
              spawn_after_wait: logic.spawn_after_wait,
              remove_last: logic.remove_last
            }};
            const interpreter = new NanoCaliburInterpreter(spec, actions, {{}});

            // Start generator (captures Coin[-1] binding, then yields).
            interpreter.tick({{
              keyboard: {{ begin: ["E"], on: ["E"], end: [] }}
            }});
            // Advance generator one step, then remove the coin in the same frame.
            interpreter.tick({{
              keyboard: {{ begin: ["D"], on: ["D"], end: [] }}
            }});
            // Resume generator after removal. With rebind, no spawn should happen.
            interpreter.tick({{
              keyboard: {{ begin: [], on: [], end: [] }}
            }});

            const state = interpreter.getState();
            console.log(JSON.stringify({{
              actor_count: state.actors.length
            }}));
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
    assert result["actor_count"] == 0
