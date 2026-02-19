import json
import textwrap

from nanocalibur.exporter import export_project


def test_export_project_writes_spec_and_logic_files(tmp_path):
    source = textwrap.dedent(
        """
        class Player(ActorModel):
            life: int
            x: int
            y: int

        def heal(player: Player["main_character"], amount: Global["heal"]):
            player.life = player.life + amount

        def is_dead(player: Player) -> bool:
            return player.life <= 0

        @condition(OnToolCall("boost_heal", "Increase heal amount by one"))
        def boost_heal(amount: Global["heal"]):
            amount = amount + 1

        game = Game()
        game.add_global("heal", 2)
        game.add_actor(Player, "main_character", life=1, x=5, y=6)
        game.add_rule(KeyboardCondition.on_press("A"), heal)
        game.add_rule(OnLogicalCondition(is_dead, Player), heal)
        game.set_map(
            TileMap(
                tile_size=16,
                grid=[[0, 1], [0, 0]],
                tiles={1: Tile(block_mask=2, color=Color(90, 90, 90))},
            )
        )
        game.set_camera(Camera.fixed(100, 200))
        """
    )

    export_project(source, str(tmp_path))

    spec_path = tmp_path / "game_spec.json"
    ir_path = tmp_path / "game_ir.json"
    ts_path = tmp_path / "game_logic.ts"
    js_path = tmp_path / "game_logic.js"
    esm_path = tmp_path / "game_logic.mjs"
    assert spec_path.exists()
    assert ir_path.exists()
    assert ts_path.exists()
    assert not js_path.exists()
    assert not esm_path.exists()

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    assert spec["schemas"]["Player"]["life"] == "int"
    assert spec["map"]["tile_size"] == 16
    assert spec["map"]["tile_grid"] == [[0, 1], [0, 0]]
    assert spec["map"]["tile_defs"]["1"]["block_mask"] == 2
    assert spec["camera"]["mode"] == "fixed"
    assert any(
        rule["condition"]["kind"] == "keyboard" and rule["condition"]["phase"] == "on"
        for rule in spec["rules"]
    )
    assert any(tool["name"] == "boost_heal" for tool in spec["tools"])
    assert spec["predicates"][0]["name"] == "is_dead"
    assert spec["predicates"][0]["params"][0]["kind"] == "actor"
    assert spec["contains_next_turn_call"] is False

    ir_data = json.loads(ir_path.read_text(encoding="utf-8"))
    assert ir_data["actions"][0]["name"] == "heal"
    assert ir_data["predicates"][0]["name"] == "is_dead"


def test_export_project_serializes_tile_grid_and_tile_defs(tmp_path):
    source = textwrap.dedent(
        """
        class Player(Actor):
            pass

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        scene.add_actor(Player(uid="hero", x=16, y=16))

        grass = Color(0, 180, 0, symbol=",", description="grass")
        wall = Tile(block_mask=3, color=grass)
        coin_tile = Tile(sprite="coin")

        scene.set_map(
            TileMap(
                tile_size=16,
                grid=[[1, 2], [0, 1]],
                tiles={1: wall, 2: coin_tile},
            )
        )
        """
    )

    export_project(source, str(tmp_path))
    spec = json.loads((tmp_path / "game_spec.json").read_text(encoding="utf-8"))
    tile_map = spec["map"]
    assert tile_map["tile_grid"] == [[1, 2], [0, 1]]
    assert tile_map["tile_defs"]["1"]["block_mask"] == 3
    assert tile_map["tile_defs"]["1"]["color"]["r"] == 0
    assert tile_map["tile_defs"]["1"]["color"]["g"] == 180
    assert tile_map["tile_defs"]["1"]["color"]["b"] == 0
    assert tile_map["tile_defs"]["1"]["color"]["symbol"] == ","
    assert tile_map["tile_defs"]["1"]["color"]["description"] == "grass"
    assert "mask" not in tile_map["tile_defs"]["1"]
    assert tile_map["tile_defs"]["2"]["block_mask"] is None
    assert tile_map["tile_defs"]["2"]["sprite"] == "coin"


def test_export_project_resolves_grid_file_relative_to_source_path(tmp_path):
    scene_dir = tmp_path / "scene_src"
    maps_dir = tmp_path / "maps"
    out_dir = tmp_path / "out"
    scene_dir.mkdir(parents=True, exist_ok=True)
    maps_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    (maps_dir / "level.txt").write_text(
        "0 1 0\n1 0 0\n",
        encoding="utf-8",
    )
    scene_path = scene_dir / "scene.py"

    source = textwrap.dedent(
        """
        class Player(Actor):
            pass

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        scene.add_actor(Player(uid="hero", x=16, y=16))
        scene.set_map(
            TileMap(
                tile_size=16,
                grid="../maps/level.txt",
                tiles={1: Tile(block_mask=2, color=Color(70, 70, 70))},
            )
        )
        """
    )

    export_project(source, str(out_dir), source_path=str(scene_path))
    spec = json.loads((out_dir / "game_spec.json").read_text(encoding="utf-8"))
    assert spec["map"]["tile_grid"] == [[0, 1, 0], [1, 0, 0]]


def test_export_project_serializes_interface_html_and_button_condition(tmp_path):
    source = textwrap.dedent(
        '''
        @condition(OnButton("spawn_bonus"))
        def spawn(scene: Scene):
            scene.enable_gravity()

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        game.set_interface("<div>Score: {{score}}</div><button data-button=\\"spawn_bonus\\">Spawn</button>")
        '''
    )

    export_project(source, str(tmp_path))
    spec = json.loads((tmp_path / "game_spec.json").read_text(encoding="utf-8"))
    assert spec["interface_html"] is not None
    assert "Score: {{score}}" in spec["interface_html"]
    assert spec["rules"][0]["condition"]["kind"] == "button"
    assert spec["rules"][0]["condition"]["name"] == "spawn_bonus"


def test_export_project_serializes_overlap_and_contact_modes(tmp_path):
    source = textwrap.dedent(
        """
        class Player(Actor):
            life: int

        class Coin(Actor):
            active: bool

        def on_overlap(hero: Player, coin: Coin):
            hero.life = hero.life + 1

        def on_contact(hero: Player, coin: Coin):
            hero.life = hero.life - 1

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        scene.add_actor(Player(uid="hero", life=1))
        scene.add_actor(Coin(uid="coin_1", active=True))
        scene.add_rule(OnOverlap(Player["hero"], Coin), on_overlap)
        scene.add_rule(OnContact(Player["hero"], Coin), on_contact)
        """
    )

    export_project(source, str(tmp_path))
    spec = json.loads((tmp_path / "game_spec.json").read_text(encoding="utf-8"))
    assert spec["rules"][0]["condition"]["kind"] == "collision"
    assert spec["rules"][0]["condition"]["mode"] == "overlap"
    assert spec["rules"][1]["condition"]["kind"] == "collision"
    assert spec["rules"][1]["condition"]["mode"] == "contact"


def test_export_project_serializes_sprite_bindings_resources_and_callables(tmp_path):
    source = textwrap.dedent(
        """
        class Player(Actor):
            speed: int

        @callable
        def next_speed(speed: int) -> int:
            return speed + 1

        @condition(KeyboardCondition.on_press("d"))
        def boost(player: Player["hero"]):
            player.speed = next_speed(player.speed)
            player.play("run")

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        scene.add_actor(Player(uid="hero", x=0, y=0, speed=1, sprite="hero"))
        game.add_resource("hero_sheet", "res/hero.png")
        game.add_sprite(
            Sprite(
                name="hero",
                resource="hero_sheet",
                frame_width=16,
                frame_height=16,
                symbol="@",
                description="hero sprite",
                default_clip="idle",
                clips={"idle": [0, 1], "run": [2, 3]},
            )
        )
        """
    )

    export_project(source, str(tmp_path))
    spec = json.loads((tmp_path / "game_spec.json").read_text(encoding="utf-8"))

    assert spec["resources"] == [{"name": "hero_sheet", "path": "res/hero.png"}]
    assert spec["sprites"]["by_name"]["hero"]["resource"] == "hero_sheet"
    assert spec["sprites"]["by_name"]["hero"]["symbol"] == "@"
    assert spec["sprites"]["by_name"]["hero"]["description"] == "hero sprite"
    assert spec["sprites"]["by_name"]["hero"]["clips"]["run"]["frames"] == [2, 3]
    assert spec["callables"] == ["next_speed"]


def test_export_project_serializes_multiplayer_and_next_turn_metadata(tmp_path):
    source = textwrap.dedent(
        """
        class Player(Actor):
            pass

        def advance(scene: Scene, player: Player["hero"]):
            player.x = player.x + 1
            scene.next_turn()

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        scene.add_actor(Player(uid="hero", x=0, y=0))
        scene.add_rule(KeyboardCondition.on_press("A"), advance)
        game.set_multiplayer(
            Multiplayer(
                default_loop="hybrid",
                allowed_loops=["turn_based", "hybrid"],
                default_visibility="role_filtered",
                tick_rate=15,
                turn_timeout_ms=25000,
                hybrid_window_ms=1200,
                game_time_scale=0.75,
                max_catchup_steps=3,
            )
        )
        """
    )

    export_project(source, str(tmp_path))
    spec = json.loads((tmp_path / "game_spec.json").read_text(encoding="utf-8"))

    assert spec["contains_next_turn_call"] is True
    assert spec["multiplayer"] is not None
    assert spec["multiplayer"]["default_loop"] == "hybrid"
    assert spec["multiplayer"]["allowed_loops"] == ["turn_based", "hybrid"]
    assert spec["multiplayer"]["default_visibility"] == "role_filtered"
    assert spec["multiplayer"]["tick_rate"] == 15
    assert spec["multiplayer"]["turn_timeout_ms"] == 25000
    assert spec["multiplayer"]["hybrid_window_ms"] == 1200
    assert spec["multiplayer"]["game_time_scale"] == 0.75
    assert spec["multiplayer"]["max_catchup_steps"] == 3
