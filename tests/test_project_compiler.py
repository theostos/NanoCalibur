import textwrap
import warnings

import pytest

from nanocalibur.errors import DSLValidationError
from nanocalibur.game_model import (
    ButtonConditionSpec,
    CollisionMode,
    InputPhase,
    KeyboardConditionSpec,
    MultiplayerLoopMode,
    MouseConditionSpec,
    ToolConditionSpec,
    VisibilityMode,
)
from nanocalibur.ir import Attr
from nanocalibur.project_compiler import ProjectCompiler


def compile_project(source: str, source_path: str | None = None):
    return ProjectCompiler().compile(textwrap.dedent(source), source_path=source_path)


def test_compile_project_with_conditions_map_and_camera():
    project = compile_project(
        """
        class Player(ActorModel):
            life: int
            x: int
            y: int

        class Enemy(ActorModel):
            life: int

        def heal(player: Player["main_character"], amount: Global["heal"]):
            player.life = player.life + amount

        def on_hit(hero: Player, enemy: Enemy):
            hero.life = hero.life - 1

        def mark_dead(player: Player["main_character"], dead: Global["is_dead"]):
            dead = True

        def is_dead(player: Player) -> bool:
            return player.life <= 0

        game = Game()
        game.add_global("heal", 2)
        game.add_global("is_dead", False)
        game.add_actor(Player, "main_character", life=3, x=10, y=20)
        game.add_actor(Enemy, "enemy_1", life=5)

        cond_key = KeyboardCondition.on_press("A")
        cond_collision = OnOverlap(Player["main_character"], Enemy)
        cond_logic = OnLogicalCondition(is_dead, Player)

        game.add_rule(cond_key, heal)
        game.add_rule(cond_collision, on_hit)
        game.add_rule(cond_logic, mark_dead)
        game.set_map(
            TileMap(
                tile_size=32,
                grid=[[1, 0], [0, 1]],
                tiles={1: Tile(color=Color(50, 50, 50))},
            )
        )
        game.set_camera(Camera.follow("main_character"))
        """
    )

    assert set(project.actor_schemas.keys()) == {"Player", "Enemy"}
    assert len(project.globals) == 2
    assert len(project.actors) == 2
    assert len(project.rules) == 3
    assert project.tile_map is not None
    assert project.tile_map.tile_grid == [[1, 0], [0, 1]]
    assert project.camera is not None
    assert project.camera.target_uid == "main_character"
    assert [predicate.name for predicate in project.predicates] == ["is_dead"]
    assert isinstance(project.rules[0].condition, KeyboardConditionSpec)
    assert project.rules[0].condition.phase == InputPhase.ON


def test_project_parses_multiplayer_configuration():
    project = compile_project(
        """
        class Player(Actor):
            pass

        def noop(player: Player["hero"]):
            player.x = player.x + 0

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        scene.add_actor(Player(uid="hero", x=0, y=0))
        scene.add_rule(KeyboardCondition.on_press("A"), noop)
        game.set_multiplayer(
            Multiplayer(
                default_loop="real_time",
                allowed_loops=["turn_based", "hybrid", "real_time"],
                default_visibility="role_filtered",
                tick_rate=30,
                turn_timeout_ms=12000,
                hybrid_window_ms=700,
                game_time_scale=0.5,
                max_catchup_steps=2,
            )
        )
        """
    )

    assert project.multiplayer is not None
    assert project.multiplayer.default_loop == MultiplayerLoopMode.REAL_TIME
    assert project.multiplayer.allowed_loops == [
        MultiplayerLoopMode.TURN_BASED,
        MultiplayerLoopMode.HYBRID,
        MultiplayerLoopMode.REAL_TIME,
    ]
    assert project.multiplayer.default_visibility == VisibilityMode.ROLE_FILTERED
    assert project.multiplayer.tick_rate == 30
    assert project.multiplayer.turn_timeout_ms == 12000
    assert project.multiplayer.hybrid_window_ms == 700
    assert project.multiplayer.game_time_scale == 0.5
    assert project.multiplayer.max_catchup_steps == 2


def test_turn_based_multiplayer_requires_next_turn_call():
    with pytest.raises(DSLValidationError, match="scene.next_turn"):
        compile_project(
            """
            class Player(Actor):
                pass

            def noop(player: Player["hero"]):
                player.x = player.x + 1

            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            scene.add_actor(Player(uid="hero", x=0, y=0))
            scene.add_rule(KeyboardCondition.on_press("A"), noop)
            game.set_multiplayer(
                Multiplayer(
                    default_loop="turn_based",
                    allowed_loops=["turn_based"],
                )
            )
            """
        )


def test_turn_based_multiplayer_accepts_next_turn_call():
    project = compile_project(
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
                default_loop="turn_based",
                allowed_loops=["turn_based"],
            )
        )
        """
    )

    assert project.contains_next_turn_call is True


def test_logical_predicate_accepts_multiple_binding_types():
    project = compile_project(
        """
        class Player(Actor):
            life: int

        def mark_dead(flag: Global["is_dead"]):
            flag = True

        def should_mark(
            scene: Scene,
            score: Global["score"],
            wait_tick: Tick,
            player: Player,
            hero: Player["hero"],
        ) -> bool:
            return player.life <= score and scene.elapsed >= 0 and wait_tick == wait_tick and hero.uid == "hero"

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        game.add_global("is_dead", False)
        game.add_global("score", 1)
        scene.add_actor(Player(uid="hero", life=1))
        scene.add_rule(OnLogicalCondition(should_mark, Player), mark_dead)
        """
    )

    assert len(project.predicates) == 1
    predicate = project.predicates[0]
    assert predicate.name == "should_mark"
    assert len(predicate.params) == 5
    assert predicate.params[0].kind.value == "scene"
    assert predicate.params[1].kind.value == "global"
    assert predicate.params[2].kind.value == "tick"
    assert predicate.params[3].kind.value == "actor"
    assert predicate.params[3].actor_selector is not None
    assert predicate.params[3].actor_selector.uid == "__nanocalibur_logical_target__"
    assert predicate.params[4].kind.value == "actor"
    assert predicate.params[4].actor_selector is not None
    assert predicate.params[4].actor_selector.uid == "hero"


def test_logical_predicate_requires_actor_binding_parameter():
    with pytest.raises(DSLValidationError, match="must declare at least one actor binding parameter"):
        compile_project(
            """
            class Player(Actor):
                life: int

            def mark_dead(flag: Global["is_dead"]):
                flag = True

            def invalid(score: Global["score"]) -> bool:
                return score > 0

            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            game.add_global("is_dead", False)
            game.add_global("score", 1)
            scene.add_actor(Player(uid="hero", life=1))
            scene.add_rule(OnLogicalCondition(invalid, Player), mark_dead)
            """
        )


def test_compile_project_with_scene_managed_actors_rules_map_and_camera():
    project = compile_project(
        """
        class Player(Actor):
            speed: int

        def move_right(player: Player["hero"]):
            player.x = player.x + player.speed

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        scene.add_actor(Player(uid="hero", x=10, y=20, speed=2))
        scene.add_rule(KeyboardCondition.on_press("D"), move_right)
        scene.set_camera(Camera.follow("hero"))
        scene.set_map(
            TileMap(
                tile_size=16,
                grid=[[0, 0], [0, 1]],
                tiles={1: Tile(color=Color(100, 100, 100))},
            )
        )
        """
    )

    assert project.scene is not None
    assert project.scene.gravity_enabled is False
    assert len(project.actors) == 1
    assert len(project.rules) == 1
    assert project.camera is not None
    assert project.camera.target_uid == "hero"
    assert project.tile_map is not None
    assert project.tile_map.tile_size == 16


def test_add_actor_constructor_form_generates_uid_and_parent_link():
    project = compile_project(
        """
        class Player(Actor):
            speed: int

        class Coin(Actor):
            pass

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        scene.add_actor(Player(uid="hero", x=10, y=20, speed=2))
        scene.add_actor(Coin(parent=Player["hero"], x=12, y=21))
        """
    )

    assert len(project.actors) == 2
    hero = project.actors[0]
    coin = project.actors[1]
    assert hero.uid == "hero"
    assert hero.fields["active"] is True
    assert "block_mask" not in hero.fields
    assert hero.fields["z"] == 0.0
    assert coin.uid == "coin_1"
    assert "block_mask" not in coin.fields
    assert coin.fields["parent"] == "hero"


def test_add_actor_constructor_rejects_removed_block_solid_field():
    with pytest.raises(DSLValidationError, match="Unknown field 'block_solid'"):
        compile_project(
            """
            class Coin(Actor):
                pass

            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            scene.add_actor(Coin(uid="coin_1", x=12, y=21, block_solid=False))
            """
        )


def test_scene_add_actor_accepts_named_actor_constructor_variable():
    project = compile_project(
        """
        class Player(Actor):
            speed: int

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)

        hero_player = Player(
            uid="hero",
            x=480,
            y=624,
            w=32,
            h=32,
            speed=5,
            z=1,
            sprite="hero",
        )

        scene.add_actor(hero_player)
        """
    )

    assert len(project.actors) == 1
    hero = project.actors[0]
    assert hero.actor_type == "Player"
    assert hero.uid == "hero"
    assert hero.fields["x"] == 480.0
    assert hero.fields["y"] == 624.0
    assert hero.fields["w"] == 32.0
    assert hero.fields["h"] == 32.0
    assert hero.fields["speed"] == 5
    assert hero.fields["z"] == 1.0
    assert hero.fields["sprite"] == "hero"
    assert "uid" not in hero.fields


def test_scene_add_actor_accepts_alias_of_named_actor_variable():
    project = compile_project(
        """
        class Coin(Actor):
            value: int

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)

        coin = Coin(uid="coin_1", x=860, y=628, active=True, value=3, sprite="coin")
        retest = coin
        alias2 = retest
        scene.add_actor(alias2)
        """
    )

    assert len(project.actors) == 1
    coin = project.actors[0]
    assert coin.actor_type == "Coin"
    assert coin.uid == "coin_1"
    assert coin.fields["x"] == 860.0
    assert coin.fields["y"] == 628.0
    assert coin.fields["active"] is True
    assert coin.fields["value"] == 3
    assert coin.fields["sprite"] == "coin"


def test_general_top_level_aliasing_for_calls_and_callables():
    project = compile_project(
        """
        class Player(Actor):
            speed: int

        def move_right(player: Player["hero"]):
            player.x = player.x + player.speed

        game = Game()
        scene = Scene(gravity=False)

        bind_scene = game.set_scene
        bind_scene(scene)

        ctor = Player
        hero = ctor(uid="hero", x=10, y=20, speed=2)

        add_actor = scene.add_actor
        add_actor(hero)

        keyboard_end = KeyboardCondition.end_press
        cond = keyboard_end(["d", "q"])

        action = move_right
        add_rule = scene.add_rule
        add_rule(cond, action)
        """
    )

    assert len(project.actors) == 1
    assert project.actors[0].uid == "hero"
    assert len(project.rules) == 1
    condition = project.rules[0].condition
    assert isinstance(condition, KeyboardConditionSpec)
    assert condition.phase == InputPhase.END
    assert condition.key == ["d", "q"]
    assert project.rules[0].action_name == "move_right"


def test_project_errors_include_location_and_source_snippet():
    with pytest.raises(DSLValidationError) as exc_info:
        compile_project(
            """
            class Player(Actor):
                speed: int

            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            scene.add_actor(Player(uid="hero", speed=2, unknown=1))
            """
        )

    message = str(exc_info.value)
    assert "Location: line" in message
    assert 'scene.add_actor(Player(uid="hero", speed=2, unknown=1))' in message


def test_scene_set_map_and_camera_accept_named_variables():
    project = compile_project(
        """
        class Player(Actor):
            speed: int

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        scene.add_actor(Player(uid="hero", x=10, y=20, speed=2))

        tile_map = TileMap(
            tile_size=16,
            grid=[
                [1, 0, 0],
                [0, 0, 0],
                [0, 0, 1],
            ],
            tiles={1: Tile(color=Color(90, 90, 90))},
        )
        follow_camera = Camera.follow("hero")

        scene.set_map(tile_map)
        scene.set_camera(follow_camera)
        """
    )

    assert project.tile_map is not None
    assert project.tile_map.tile_size == 16
    assert project.tile_map.tile_grid == [[1, 0, 0], [0, 0, 0], [0, 0, 1]]
    assert project.camera is not None
    assert project.camera.target_uid == "hero"


def test_tile_map_grid_parses_non_zero_tiles():
    project = compile_project(
        """
        class Player(Actor):
            speed: int

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        scene.add_actor(Player(uid="hero", x=10, y=20, speed=2, block_mask=1))
        scene.set_map(
            TileMap(
                tile_size=16,
                grid=[
                    [0, 2, 0],
                    [1, 0, 0],
                ],
                tiles={
                    1: Tile(block_mask=2, color=Color(120, 120, 120)),
                    2: Tile(sprite="torch"),
                },
            )
        )
        """
    )

    assert project.tile_map is not None
    assert project.tile_map.tile_grid == [[0, 2, 0], [1, 0, 0]]
    assert set(project.tile_map.tile_defs.keys()) == {1, 2}
    assert project.tile_map.tile_defs[1].block_mask == 2
    assert project.tile_map.tile_defs[2].block_mask is None


def test_tile_map_grid_can_load_from_relative_text_file(tmp_path):
    scene_dir = tmp_path / "scene_src"
    maps_dir = tmp_path / "maps"
    scene_dir.mkdir(parents=True, exist_ok=True)
    maps_dir.mkdir(parents=True, exist_ok=True)

    (maps_dir / "level.txt").write_text(
        "0 1 0\n1 0 2\n",
        encoding="utf-8",
    )
    scene_path = scene_dir / "scene.py"

    project = compile_project(
        """
        class Player(Actor):
            pass

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        scene.add_actor(Player(uid="hero", x=10, y=20))

        scene.set_map(
            TileMap(
                tile_size=16,
                grid="../maps/level.txt",
                tiles={
                    1: Tile(block_mask=2, color=Color(120, 120, 120)),
                    2: Tile(sprite="torch"),
                },
            )
        )
        """,
        source_path=str(scene_path),
    )

    assert project.tile_map is not None
    assert project.tile_map.tile_grid == [[0, 1, 0], [1, 0, 2]]
    assert project.tile_map.tile_defs[1].block_mask == 2
    assert project.tile_map.tile_defs[2].sprite == "torch"


def test_tile_map_grid_palette_supports_color_and_sprite_tiles():
    project = compile_project(
        """
        class Player(Actor):
            pass

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        scene.add_actor(Player(uid="hero", x=10, y=20))

        grass = Color(10, 120, 20, symbol=",", description="grass tile")
        wall = Tile(block_mask=3, color=grass)
        torch = Tile(sprite="torch")

        scene.set_map(
            TileMap(
                tile_size=16,
                grid=[
                    [1, 0, 2],
                    [0, 1, 0],
                ],
                tiles={
                    1: wall,
                    2: torch,
                },
            )
        )
        """
    )

    assert project.tile_map is not None
    assert project.tile_map.width == 3
    assert project.tile_map.height == 2
    assert project.tile_map.tile_size == 16
    assert project.tile_map.tile_grid == [[1, 0, 2], [0, 1, 0]]
    assert set(project.tile_map.tile_defs.keys()) == {1, 2}
    assert project.tile_map.tile_defs[1].block_mask == 3
    assert project.tile_map.tile_defs[1].color is not None
    assert project.tile_map.tile_defs[1].color.r == 10
    assert project.tile_map.tile_defs[1].color.g == 120
    assert project.tile_map.tile_defs[1].color.b == 20
    assert project.tile_map.tile_defs[1].color.symbol == ","
    assert project.tile_map.tile_defs[1].color.description == "grass tile"
    assert project.tile_map.tile_defs[1].sprite is None
    assert project.tile_map.tile_defs[2].block_mask is None
    assert project.tile_map.tile_defs[2].sprite == "torch"
    assert project.tile_map.tile_defs[2].color is None


def test_tile_map_rejects_legacy_solid_argument():
    with pytest.raises(DSLValidationError, match="unsupported arguments"):
        compile_project(
            """
            class Player(Actor):
                speed: int

            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            scene.add_actor(Player(uid="hero", x=10, y=20, speed=2, block_mask=1))
            scene.set_map(TileMap(width=8, height=8, tile_size=16, solid=[(1, 1)]))
            """
        )


def test_add_actor_constructor_form_supports_block_mask():
    project = compile_project(
        """
        class Player(Actor):
            speed: int

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        scene.add_actor(Player(uid="hero", x=10, y=20, speed=2))
        scene.add_actor(Player(uid="hero_2", x=20, y=20, speed=2, block_mask=3))
        """
    )

    first = project.actors[0]
    second = project.actors[1]
    assert "block_mask" not in first.fields
    assert second.fields["block_mask"] == 3


def test_add_sprite_accepts_named_sprite_variable():
    project = compile_project(
        """
        class Player(Actor):
            speed: int

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        scene.add_actor(Player(uid="hero", x=10, y=20, speed=2, sprite="hero"))
        game.add_resource("hero_sheet", "hero.png")

        hero_sprite = Sprite(
            name="hero",
            resource="hero_sheet",
            frame_width=16,
            frame_height=16,
            default_clip="idle",
            symbol="@",
            description="hero player",
            clips={
                "idle": {"frames": [0, 1], "ticks_per_frame": 8, "loop": True},
            },
        )

        game.add_sprite(hero_sprite)
        """
    )

    assert len(project.sprites) == 1
    sprite = project.sprites[0]
    assert sprite.name == "hero"
    assert sprite.resource == "hero_sheet"
    assert sprite.frame_width == 16
    assert sprite.frame_height == 16
    assert sprite.default_clip == "idle"
    assert sprite.symbol == "@"
    assert sprite.description == "hero player"
    assert [clip.name for clip in sprite.clips] == ["idle"]


def test_add_sprite_rejects_unknown_resource():
    with pytest.raises(DSLValidationError, match="unknown resource"):
        compile_project(
            """
            class Player(Actor):
                speed: int

            def noop(player: Player["hero"]):
                player.x = player.x + 0

            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            scene.add_actor(Player(uid="hero", x=10, y=20, speed=2, sprite="hero"))

            game.add_sprite(
                Sprite(
                    name="hero",
                    resource="missing_sheet",
                    frame_width=16,
                    frame_height=16,
                    default_clip="idle",
                    clips={"idle": [0]},
                )
            )
            scene.add_rule(KeyboardCondition.on_press("A"), noop)
            """
        )


def test_add_sprite_accepts_bind_selector_and_scene_gravity():
    project = compile_project(
        """
        class Player(Actor):
            speed: int

        def noop(player: Player["hero"]):
            player.play("idle")

        game = Game()
        game.set_scene(Scene(gravity=True))
        game.add_actor(Player(uid="hero", x=0, y=0, speed=1))
        game.add_resource("hero_sheet", "hero.png")
        game.add_sprite(
            Sprite(
                bind=Player["hero"],
                resource="hero_sheet",
                frame_width=16,
                frame_height=16,
                clips={"idle": [0, 1]},
            )
        )
        game.add_rule(KeyboardCondition.on_press("A"), noop)
        """
    )

    assert project.scene is not None
    assert project.scene.gravity_enabled is True
    assert len(project.sprites) == 1
    assert project.sprites[0].uid == "hero"


def test_game_set_map_and_camera_accept_named_variables():
    project = compile_project(
        """
        class Player(Actor):
            speed: int

        game = Game()
        game.add_actor(Player(uid="hero", x=10, y=20, speed=2))

        tile_map = TileMap(
            tile_size=24,
            grid=[
                [1, 0],
                [0, 0],
            ],
            tiles={1: Tile(color=Color(60, 60, 60))},
        )
        fixed_camera = Camera.fixed(100, 200)

        game.set_map(tile_map)
        game.set_camera(fixed_camera)
        """
    )

    assert project.tile_map is not None
    assert project.tile_map.width == 2
    assert project.tile_map.height == 2
    assert project.tile_map.tile_size == 24
    assert project.tile_map.tile_grid == [[1, 0], [0, 0]]
    assert project.camera is not None
    assert project.camera.x == 100
    assert project.camera.y == 200


def test_scene_methods_require_game_set_scene_binding():
    with pytest.raises(DSLValidationError, match="must be passed to game.set_scene"):
        compile_project(
            """
            class Player(Actor):
                speed: int

            def move_right(player: Player["hero"]):
                player.x = player.x + player.speed

            game = Game()
            scene = Scene(gravity=False)
            scene.add_actor(Player, "hero", x=10, y=20, speed=2)
            scene.add_rule(KeyboardCondition.on_press("D"), move_right)
            """
        )


def test_keyboard_and_mouse_condition_phases():
    project = compile_project(
        """
        class Player(ActorModel):
            life: int

        def noop(player: Player["main"]):
            player.life = player.life

        game = Game()
        game.add_actor(Player, "main", life=1)
        game.add_rule(KeyboardCondition.begin_press("A"), noop)
        game.add_rule(KeyboardCondition.on_press("A"), noop)
        game.add_rule(KeyboardCondition.end_press("A"), noop)
        game.add_rule(MouseCondition.begin_click("left"), noop)
        game.add_rule(MouseCondition.on_click("left"), noop)
        game.add_rule(MouseCondition.end_click("left"), noop)
        """
    )

    phases = [rule.condition.phase for rule in project.rules if isinstance(rule.condition, KeyboardConditionSpec)]
    assert phases == [InputPhase.BEGIN, InputPhase.ON, InputPhase.END]
    mouse_phases = [rule.condition.phase for rule in project.rules if isinstance(rule.condition, MouseConditionSpec)]
    assert mouse_phases == [InputPhase.BEGIN, InputPhase.ON, InputPhase.END]


def test_keyboard_condition_accepts_key_lists():
    project = compile_project(
        """
        class Player(ActorModel):
            life: int

        def noop(player: Player["main"]):
            player.life = player.life

        game = Game()
        game.add_actor(Player, "main", life=1)
        game.add_rule(KeyboardCondition.end_press(["z", "q", "s", "d"]), noop)
        """
    )

    condition = project.rules[0].condition
    assert isinstance(condition, KeyboardConditionSpec)
    assert condition.phase == InputPhase.END
    assert condition.key == ["z", "q", "s", "d"]


def test_condition_decorator_adds_rule_without_add_rule_call():
    project = compile_project(
        """
        @condition(KeyboardCondition.begin_press("g"))
        def enable_gravity(scene: Scene):
            Scene.enable_gravity(scene)

        game = Game()
        game.set_scene(Scene(gravity=False))
        """
    )

    assert len(project.rules) == 1
    assert project.rules[0].action_name == "enable_gravity"
    assert isinstance(project.rules[0].condition, KeyboardConditionSpec)
    assert project.rules[0].condition.phase == InputPhase.BEGIN
    assert project.rules[0].condition.key == "g"


def test_condition_decorator_supports_tool_calling():
    project = compile_project(
        """
        @condition(OnToolCall("spawn_bonus", "Spawn one bonus coin"))
        def spawn(scene: Scene):
            scene.enable_gravity()

        game = Game()
        game.set_scene(Scene(gravity=False))
        """
    )

    assert len(project.rules) == 1
    assert project.rules[0].action_name == "spawn"
    assert isinstance(project.rules[0].condition, ToolConditionSpec)
    assert project.rules[0].condition.name == "spawn_bonus"
    assert project.rules[0].condition.tool_docstring == "Spawn one bonus coin"


def test_tool_calling_name_cannot_bind_multiple_actions():
    with pytest.raises(DSLValidationError, match="already bound to action"):
        compile_project(
            """
            @condition(OnToolCall("toggle", "Enable gravity"))
            def enable(scene: Scene):
                scene.enable_gravity()

            @condition(OnToolCall("toggle", "Disable gravity"))
            def disable(scene: Scene):
                scene.disable_gravity()

            game = Game()
            game.set_scene(Scene(gravity=False))
            """
        )


def test_global_actor_pointer_typed_allows_field_access():
    project = compile_project(
        """
        class Player(ActorModel):
            life: int

        def heal(target: Global["target_player"]):
            target.life = target.life + 1

        game = Game()
        game.add_global("target_player", Player["main_character"])
        game.add_actor(Player, "main_character", life=3)
        game.add_rule(KeyboardCondition.on_press("A"), heal)
        """
    )

    action = next(action for action in project.actions if action.name == "heal")
    assign = action.body[0]
    assert isinstance(assign.target, Attr)
    assert assign.target.obj == "target"
    assert assign.target.field == "life"


def test_global_actor_pointer_any_rejects_field_access():
    with pytest.raises(DSLValidationError, match="must use Actor\\[\"Type\"\\]"):
        compile_project(
            """
            class Player(ActorModel):
                life: int

            def bad(target: Global["target_actor"]):
                target.life = 0

            game = Game()
            game.add_global("target_actor", Actor["main_character"])
            game.add_actor(Player, "main_character", life=3)
            game.add_rule(KeyboardCondition.on_press("A"), bad)
            """
        )


def test_collision_rule_rebinds_first_two_action_parameters_and_warns():
    with pytest.warns(UserWarning) as caught:
        project = compile_project(
            """
            class Player(ActorModel):
                life: int

            class Coin(ActorModel):
                active: bool

            def collect(hero: Player["some_other_uid"], coin: Coin["other_coin"], score: Global["score"]):
                if coin.active:
                    score = score + 1

            game = Game()
            game.add_global("score", 0)
            game.add_actor(Player, "hero", life=1)
            game.add_actor(Coin, "coin_1", active=True)
            game.add_rule(OnOverlap(Player["hero"], Coin), collect)
            """
        )

    messages = [str(w.message) for w in caught]
    imposes_messages = [
        msg for msg in messages if "OnOverlap/OnContact imposes actor bindings" in msg
    ]
    assert imposes_messages
    assert "Location: line" in imposes_messages[0]
    assert "game.add_rule(OnOverlap(Player[\"hero\"], Coin), collect)" in imposes_messages[0]

    action = next(action for action in project.actions if action.name == "collect")
    assert action.params[0].actor_selector is not None
    assert action.params[1].actor_selector is not None
    assert action.params[0].actor_selector.uid == "__nanocalibur_collision_left__"
    assert action.params[1].actor_selector.uid == "__nanocalibur_collision_right__"


def test_collision_rule_plain_typed_actor_params_do_not_warn():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        compile_project(
            """
            class Player(ActorModel):
                life: int

            class Coin(ActorModel):
                active: bool

            def collect(hero: Player, coin: Coin, score: Global["score"]):
                if coin.active:
                    score = score + 1

            game = Game()
            game.add_global("score", 0)
            game.add_actor(Player, "hero", life=1)
            game.add_actor(Coin, "coin_1", active=True)
            game.add_rule(OnOverlap(Player["hero"], Coin), collect)
            """
        )
    assert not caught


def test_collision_rule_requires_first_two_action_parameters_to_be_actors():
    with pytest.raises(DSLValidationError, match="first two parameters must be actor bindings"):
        compile_project(
            """
            class Player(ActorModel):
                life: int

            def bad(score: Global["score"], hero: Player):
                score = score

            game = Game()
            game.add_global("score", 0)
            game.add_actor(Player, "hero", life=1)
            game.add_rule(OnOverlap(Player["hero"], Player), bad)
            """
        )


def test_on_overlap_and_on_contact_conditions_set_collision_mode():
    project = compile_project(
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

    assert project.rules[0].condition.mode == CollisionMode.OVERLAP
    assert project.rules[1].condition.mode == CollisionMode.CONTACT


def test_on_overlap_allows_tile_selector():
    project = compile_project(
        """
        class Player(Actor):
            life: int

        def on_tile_overlap(hero: Player, tile: Actor[-1]):
            hero.life = hero.life + 1

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        scene.add_actor(Player(uid="hero", life=1))
        scene.add_rule(OnOverlap(Player["hero"], Tile), on_tile_overlap)
        """
    )

    condition = project.rules[0].condition
    assert condition.right.actor_type == "Tile"


def test_global_variable_object_is_accepted_in_add_global_forms():
    project = compile_project(
        """
        class Player(Actor):
            pass

        game = Game()
        score = GlobalVariable(int, "score", 0)
        rescore = score
        game.add_global(rescore)
        game.add_global(GlobalVariable(List[List[int]], "grid_state", [[1, 2], [3, 4]]))
        """
    )

    by_name = {global_var.name: global_var for global_var in project.globals}
    assert by_name["score"].kind.value == "int"
    assert by_name["score"].value == 0
    assert by_name["grid_state"].kind.value == "list"
    assert by_name["grid_state"].value == [[1, 2], [3, 4]]
    assert by_name["grid_state"].list_elem_kind == "list[list[int]]"


def test_scene_declared_actor_attached_to_and_detached_methods():
    project = compile_project(
        """
        class Player(Actor):
            speed: int

        class Coin(Actor):
            pass

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)

        hero = Player(uid="hero", x=100, y=100, speed=2)
        coin = Coin(uid="coin_pet", x=120, y=100)
        coin.attached_to(hero)
        coin.detached()
        coin.attached_to(Player["hero"])

        scene.add_actor(hero)
        scene.add_actor(coin)
        """
    )

    actors = {actor.uid: actor for actor in project.actors}
    assert actors["coin_pet"].fields["parent"] == "hero"


def test_scene_declared_actor_attached_to_requires_target_uid():
    with pytest.raises(DSLValidationError, match="must have an explicit uid"):
        compile_project(
            """
            class Player(Actor):
                speed: int

            class Coin(Actor):
                pass

            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)

            hero = Player(x=100, y=100, speed=2)
            coin = Coin(uid="coin_pet", x=120, y=100)
            coin.attached_to(hero)
            """
        )


def test_on_button_condition_helper_registers_button_rule():
    project = compile_project(
        """
        @condition(OnButton("spawn_bonus"))
        def spawn(scene: Scene):
            scene.enable_gravity()

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        """
    )

    assert len(project.rules) == 1
    condition = project.rules[0].condition
    assert isinstance(condition, ButtonConditionSpec)
    assert condition.name == "spawn_bonus"


def test_set_interface_accepts_literal_and_alias_variable():
    project = compile_project(
        '''
        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        hud = "<div>Score: {{score}}</div><button data-button=\\"spawn_bonus\\">Spawn</button>"
        alias_hud = hud
        game.set_interface(alias_hud)
        '''
    )

    assert project.interface_html is not None
    assert "Score: {{score}}" in project.interface_html
    assert 'data-button="spawn_bonus"' in project.interface_html


def test_legacy_condition_helpers_are_rejected():
    with pytest.raises(DSLValidationError, match="Unsupported condition expression"):
        compile_project(
            """
            class Player(Actor):
                pass

            def noop(player: Player):
                pass

            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            scene.add_actor(Player(uid="hero", x=0, y=0))
            scene.add_rule(CollisionRelated(Player["hero"], Player), noop)
            """
        )


def test_callable_helper_can_be_used_from_action_and_is_exported():
    project = compile_project(
        """
        class Coin(Actor):
            pass

        @callable
        def next_x(x: float, offset: int) -> float:
            return x + offset

        @condition(KeyboardCondition.begin_press("e"))
        def spawn(scene: Scene, last_coin: Coin[-1]):
            if last_coin is not None:
                x = next_x(last_coin.x, 32)
                scene.spawn(Coin(x=x, y=0, active=True))

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        scene.add_actor(Coin(uid="coin_1", x=0, y=0, active=True))
        """
    )

    assert len(project.callables) == 1
    assert project.callables[0].name == "next_x"
    assert len(project.actions) == 1
    assert project.actions[0].name == "spawn"


def test_callable_selector_annotations_warn_and_are_ignored():
    with pytest.warns(UserWarning, match="Selector annotation on callable parameter"):
        project = compile_project(
            """
            class Player(Actor):
                speed: int

            @callable
            def get_speed(hero: Player["hero"]) -> int:
                return hero.speed

            @condition(KeyboardCondition.on_press("d"))
            def move(hero: Player["hero"]):
                hero.x = hero.x + get_speed(hero)

            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            scene.add_actor(Player(uid="hero", x=0, y=0, speed=1))
            """
        )

    assert project.callables[0].name == "get_speed"


def test_unreferenced_functions_emit_ignore_warnings():
    with pytest.warns(UserWarning, match="ignored"):
        compile_project(
            """
            class Player(Actor):
                pass

            def helper(flag: bool):
                flag = not flag

            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            scene.add_actor(Player(uid="hero", x=0, y=0))
            """
        )


def test_callable_dependency_chain_is_retained_when_referenced():
    project = compile_project(
        """
        class Coin(Actor):
            pass

        @callable
        def add_one(x: int) -> int:
            return x + 1

        @callable
        def add_two(x: int) -> int:
            return add_one(x) + 1

        @condition(KeyboardCondition.begin_press("e"))
        def spawn(scene: Scene, last_coin: Coin[-1]):
            if last_coin is not None:
                new_x = add_two(last_coin.x)
                scene.spawn(Coin(x=new_x, y=0, active=True))

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        scene.add_actor(Coin(uid="coin_1", x=0, y=0, active=True))
        """
    )

    callable_names = sorted(callable_fn.name for callable_fn in project.callables)
    assert callable_names == ["add_one", "add_two"]
