import textwrap
import warnings

import pytest

from nanocalibur.errors import DSLValidationError
from nanocalibur.game_model import (
    ButtonConditionSpec,
    CollisionConditionSpec,
    CollisionMode,
    GlobalValueKind,
    InputPhase,
    KeyboardConditionSpec,
    MultiplayerLoopMode,
    MouseConditionSpec,
    RoleKind,
    ToolConditionSpec,
    VisibilityMode,
)
from nanocalibur.ir import Attr, BindingKind
from nanocalibur.project_compiler import ProjectCompiler


def compile_project(source: str, source_path: str | None = None, **kwargs):
    return ProjectCompiler().compile(
        textwrap.dedent(source),
        source_path=source_path,
        **kwargs,
    )


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
        game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
        scene = Scene(gravity=False)
        game.set_scene(scene)
        game.add_global("heal", 2)
        game.add_global("is_dead", False)
        game.add_actor(Player, "main_character", life=3, x=10, y=20)
        game.add_actor(Enemy, "enemy_1", life=5)

        cond_key = KeyboardCondition.on_press("A", id="human_1")
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
        main_camera = Camera("main_camera", Role["human_1"])
        main_camera.follow("main_character")
        scene.add_camera(main_camera)
        """
    )

    assert set(project.actor_schemas.keys()) == {"Player", "Enemy"}
    assert len(project.globals) == 2
    assert len(project.actors) == 2
    assert len(project.rules) == 3
    assert project.tile_map is not None
    assert project.tile_map.tile_grid == [[1, 0], [0, 1]]
    assert len(project.cameras) == 1
    assert project.cameras[0].target_uid == "main_character"
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
        game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
        scene = Scene(gravity=False)
        game.set_scene(scene)
        scene.add_actor(Player(uid="hero", x=0, y=0))
        scene.add_rule(KeyboardCondition.on_press("A", id="human_1"), noop)
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


def test_actor_base_fields_include_velocity_components():
    project = compile_project(
        """
        class Player(Actor):
            speed: int

        def noop(player: Player["hero"]):
            player.vx = player.speed

        game = Game()
        game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
        scene = Scene()
        game.set_scene(scene)
        scene.add_actor(
            Player(
                uid="hero",
                x=10,
                y=20,
                vx=12,
                vy=4,
                speed=42,
            )
        )
        scene.add_rule(KeyboardCondition.on_press("d", id="human_1"), noop)
        """
    )

    actor = project.actors[0]
    assert actor.fields["vx"] == 12
    assert actor.fields["vy"] == 4
    assert project.actor_schemas["Player"]["vx"] == "float"
    assert project.actor_schemas["Player"]["vy"] == "float"


def test_project_actor_schema_can_inherit_from_custom_actor_schema():
    project = compile_project(
        """
        class OwnedActor(Actor):
            owner_id: str

        class Unit(OwnedActor):
            hp: int
            max_hp: int

        game = Game()
        game.add_role(Role(id="ai_1", required=False, kind=RoleKind.AI))
        scene = Scene(gravity=False)
        game.set_scene(scene)
        scene.add_actor(
            Unit(
                uid="u1",
                x=32,
                y=48,
                owner_id="player_1",
                hp=35,
                max_hp=40,
            )
        )
        """
    )

    assert "OwnedActor" in project.actor_schemas
    assert "Unit" in project.actor_schemas
    assert project.actor_schemas["OwnedActor"]["owner_id"] == "str"
    assert project.actor_schemas["Unit"]["owner_id"] == "str"
    assert project.actor_schemas["Unit"]["hp"] == "int"
    assert project.actor_schemas["Unit"]["max_hp"] == "int"
    assert project.actors[0].actor_type == "Unit"
    assert project.actors[0].fields["owner_id"] == "player_1"


def test_turn_based_multiplayer_requires_next_turn_call():
    with pytest.raises(DSLValidationError, match="scene.next_turn"):
        compile_project(
            """
            class Player(Actor):
                pass

            def noop(player: Player["hero"]):
                player.x = player.x + 1

            game = Game()
            game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
            scene = Scene(gravity=False)
            game.set_scene(scene)
            scene.add_actor(Player(uid="hero", x=0, y=0))
            scene.add_rule(KeyboardCondition.on_press("A", id="human_1"), noop)
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
        game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
        scene = Scene(gravity=False)
        game.set_scene(scene)
        scene.add_actor(Player(uid="hero", x=0, y=0))
        scene.add_rule(KeyboardCondition.on_press("A", id="human_1"), advance)
        game.set_multiplayer(
            Multiplayer(
                default_loop="turn_based",
                allowed_loops=["turn_based"],
            )
        )
        """
    )

    assert project.contains_next_turn_call is True


def test_project_parses_roles_and_role_scoped_conditions():
    project = compile_project(
        """
        class Player(Actor):
            pass

        def move_right(player: Player["hero"]):
            player.x = player.x + 1

        def call_tool(player: Player["hero"]):
            \"\"\"bot move\"\"\"
            player.x = player.x + 2

        game = Game()
        game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
        scene = Scene(gravity=False)
        game.set_scene(scene)
        game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
        game.add_role(Role(id="ai_1", required=False, kind="AI"))
        scene.add_actor(Player(uid="hero", x=0, y=0))
        scene.add_rule(KeyboardCondition.on_press("d", id="human_1"), move_right)
        scene.add_rule(OnToolCall("bot_move", id="ai_1"), call_tool)
        """
    )

    assert [role.id for role in project.roles] == ["human_1", "ai_1"]
    assert project.roles[0].kind == RoleKind.HUMAN
    assert project.roles[1].kind == RoleKind.AI
    assert project.roles[0].role_type == "Role"
    assert project.roles[1].role_type == "Role"

    keyboard_rule = project.rules[0]
    assert isinstance(keyboard_rule.condition, KeyboardConditionSpec)
    assert keyboard_rule.condition.role_id == "human_1"

    tool_rule = project.rules[1]
    assert isinstance(tool_rule.condition, ToolConditionSpec)
    assert tool_rule.condition.role_id == "ai_1"
    assert tool_rule.condition.tool_docstring == "bot move"


def test_project_expands_top_level_role_loop_with_string_builders():
    project = compile_project(
        """
        class Player(Actor):
            pass

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)

        for k in range(1, 5):
            game.add_role(
                Role(
                    id="human_" + str(k),
                    required=(k == 1),
                    kind=RoleKind.HUMAN,
                )
            )

        for k in range(1, 3):
            game.add_role(Role(id=f"dummy_{k}", required=False, kind=RoleKind.AI))

        scene.add_actor(Player(uid="hero", x=0, y=0))
        """
    )

    assert [role.id for role in project.roles] == [
        "human_1",
        "human_2",
        "human_3",
        "human_4",
        "dummy_1",
        "dummy_2",
    ]
    assert [role.required for role in project.roles] == [
        True,
        False,
        False,
        False,
        False,
        False,
    ]


def test_project_parses_role_schema_and_role_bindings():
    project = compile_project(
        """
        class HeroRole(Role):
            score: int
            buffs: List[List[int]]

        class Player(Actor):
            pass

        def add_score(self_role: HeroRole["human_1"]):
            self_role.score = self_role.score + 1

        def can_win(player: Player, self_role: HeroRole["human_1"]) -> bool:
            return self_role.score >= 10

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        game.add_role(HeroRole(id="human_1", kind=RoleKind.HUMAN, score=3))
        scene.add_actor(Player(uid="hero", x=0, y=0))
        scene.add_rule(KeyboardCondition.on_press("d", id="human_1"), add_score)
        scene.add_rule(OnLogicalCondition(can_win, Player), add_score)
        """
    )

    assert "HeroRole" in project.role_schemas
    assert project.role_schemas["HeroRole"]["score"] == "int"
    assert project.role_schemas["HeroRole"]["buffs"] == "list[list[int]]"
    assert project.roles[0].id == "human_1"
    assert project.roles[0].role_type == "HeroRole"
    assert project.roles[0].fields["score"] == 3
    assert project.roles[0].fields["buffs"] == []

    add_score = project.actions[0]
    assert add_score.params[0].kind == BindingKind.ROLE
    assert add_score.params[0].role_selector is not None
    assert add_score.params[0].role_selector.id == "human_1"
    assert add_score.params[0].role_type == "HeroRole"


def test_project_supports_dict_field_types_for_roles_actors_and_globals():
    project = compile_project(
        """
        class HeroRole(Role):
            score_by_mode: Dict[str, int]

        class Player(Actor):
            inventory: Dict[str, List[int]]

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        game.add_global("score_by_mode", {"solo": 1} + {"duo": 2})
        game.add_role(HeroRole(id="human_1", kind=RoleKind.HUMAN, score_by_mode={"solo": 5}))
        scene.add_actor(Player(uid="hero", inventory={"coins": [1] + [2, 3]}))
        """
    )

    assert project.role_schemas["HeroRole"]["score_by_mode"] == "dict[str, int]"
    assert project.actor_schemas["Player"]["inventory"] == "dict[str, list[int]]"
    global_by_name = {g.name: g for g in project.globals}
    assert global_by_name["score_by_mode"].kind == GlobalValueKind.DICT
    assert global_by_name["score_by_mode"].value == {"solo": 1, "duo": 2}
    assert project.roles[0].fields["score_by_mode"] == {"solo": 5}
    assert project.actors[0].fields["inventory"] == {"coins": [1, 2, 3]}


def test_project_exposes_builtin_humanrole_local_keybind_schema():
    project = compile_project(
        """
        class Player(Actor):
            pass

        def move_right(player: Player["hero"]):
            player.x = player.x + 1

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        game.add_role(HumanRole(id="human_1", kind=RoleKind.HUMAN))
        scene.add_actor(Player(uid="hero", x=0, y=0))
        scene.add_rule(KeyboardCondition.on_press("move_right", id="human_1"), move_right)
        """
    )

    assert project.role_schemas["HumanRole"] == {}
    assert project.role_local_schemas["HumanRole"]["keybinds"] == "dict[str, str]"
    assert project.role_local_defaults["HumanRole"]["keybinds"] == {
        "move_up": "z",
        "move_left": "q",
        "move_down": "s",
        "move_right": "d",
    }


def test_project_supports_local_fields_in_role_schemas_and_defaults():
    project = compile_project(
        """
        class HeroRole(HumanRole):
            score: int
            quickbar: Local[List[str]] = local(["dash", "heal"])

        class Player(Actor):
            pass

        def move_right(player: Player["hero"], self_role: HeroRole["human_1"]):
            if self_role.score >= 0:
                player.x = player.x + 1

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        game.add_role(HeroRole(id="human_1", kind=RoleKind.HUMAN, score=1))
        scene.add_actor(Player(uid="hero", x=0, y=0))
        scene.add_rule(KeyboardCondition.on_press("move_right", id="human_1"), move_right)
        """
    )

    assert project.role_schemas["HeroRole"]["score"] == "int"
    assert project.role_local_schemas["HeroRole"]["keybinds"] == "dict[str, str]"
    assert project.role_local_schemas["HeroRole"]["quickbar"] == "list[str]"
    assert project.role_local_defaults["HeroRole"]["quickbar"] == ["dash", "heal"]
    assert project.role_local_defaults["HeroRole"]["keybinds"]["move_up"] == "z"


def test_project_rejects_local_field_provided_in_add_role():
    with pytest.raises(DSLValidationError, match="client-owned Local"):
        compile_project(
            """
            class HeroRole(HumanRole):
                quickbar: Local[List[str]] = local(["dash"])

            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            game.add_role(HeroRole(id="human_1", kind=RoleKind.HUMAN, quickbar=["heal"]))
            """
        )


def test_project_rejects_local_role_fields_in_server_logic():
    with pytest.raises(DSLValidationError, match="Local\\[\\.\\.\\.\\] \\(client-owned\\)"):
        compile_project(
            """
            class HeroRole(HumanRole):
                profile: Local[Dict[str, str]] = local({"lang": "fr"})

            class Player(Actor):
                pass

            def bad(self_role: HeroRole["human_1"], player: Player["hero"]):
                if self_role.profile["lang"] == "fr":
                    player.x = player.x + 1

            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            game.add_role(HeroRole(id="human_1", kind=RoleKind.HUMAN))
            scene.add_actor(Player(uid="hero", x=0, y=0))
            scene.add_rule(KeyboardCondition.on_press("move_right", id="human_1"), bad)
            """
        )


def test_project_requires_local_initializer_for_local_role_fields():
    with pytest.raises(DSLValidationError, match="must be initialized with local\\(\\.\\.\\.\\)"):
        compile_project(
            """
            class HeroRole(HumanRole):
                quickbar: Local[List[str]] = ["dash"]

            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            game.add_role(HeroRole(id="human_1", kind=RoleKind.HUMAN))
            """
        )


def test_role_binding_requires_declared_role_id():
    with pytest.raises(DSLValidationError, match="references unknown role id 'human_2'"):
        compile_project(
            """
            class HeroRole(Role):
                score: int

            class Player(Actor):
                pass

            def add_score(self_role: HeroRole["human_2"]):
                self_role.score = self_role.score + 1

            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            game.add_role(HeroRole(id="human_1", kind=RoleKind.HUMAN, score=3))
            scene.add_actor(Player(uid="hero", x=0, y=0))
            scene.add_rule(KeyboardCondition.on_press("d", id="human_1"), add_score)
            """
        )


def test_role_binding_rejects_type_mismatch_with_declared_role():
    with pytest.raises(DSLValidationError, match="expects role type 'HeroRole'"):
        compile_project(
            """
            class HeroRole(Role):
                score: int

            class AIRole(Role):
                score: int

            class Player(Actor):
                pass

            def add_score(self_role: HeroRole["human_1"]):
                self_role.score = self_role.score + 1

            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            game.add_role(AIRole(id="human_1", kind=RoleKind.HYBRID, score=3))
            scene.add_actor(Player(uid="hero", x=0, y=0))
            scene.add_rule(KeyboardCondition.on_press("d", id="human_1"), add_score)
            """
        )


def test_role_scoped_condition_requires_declared_role_id():
    with pytest.raises(DSLValidationError, match="references role id 'missing_role'"):
        compile_project(
            """
            class Player(Actor):
                pass

            def move_right(player: Player["hero"]):
                player.x = player.x + 1

            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            scene.add_actor(Player(uid="hero", x=0, y=0))
            scene.add_rule(KeyboardCondition.on_press("d", id="missing_role"), move_right)
            """
        )


def test_keyboard_condition_requires_role_id():
    with pytest.raises(DSLValidationError, match="KeyboardCondition\\.<phase>\\(\\.\\.\\.\\) requires role id"):
        compile_project(
            """
            class Player(Actor):
                pass

            def move_right(player: Player["hero"]):
                player.x = player.x + 1

            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
            scene.add_actor(Player(uid="hero", x=0, y=0))
            scene.add_rule(KeyboardCondition.on_press("d"), move_right)
            """
        )


def test_mouse_condition_requires_role_id():
    with pytest.raises(DSLValidationError, match="MouseCondition\\.<phase>\\(\\.\\.\\.\\) requires role id"):
        compile_project(
            """
            class Player(Actor):
                pass

            def noop(player: Player["hero"]):
                player.x = player.x + 0

            game = Game()
            game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
            game.add_actor(Player(uid="hero", x=0, y=0))
            game.add_rule(MouseCondition.begin_click("left"), noop)
            """
        )


def test_tool_condition_requires_role_id():
    with pytest.raises(DSLValidationError, match="OnToolCall\\(\\.\\.\\.\\) requires role id"):
        compile_project(
            """
            def noop(scene: Scene):
                scene.enable_gravity()

            game = Game()
            game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
            game.set_scene(Scene(gravity=False))
            game.add_rule(OnToolCall("spawn"), noop)
            """
        )


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
        game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
        scene = Scene(gravity=False)
        game.set_scene(scene)
        scene.add_actor(Player(uid="hero", x=10, y=20, speed=2))
        scene.add_rule(KeyboardCondition.on_press("D", id="human_1"), move_right)
        follow_camera = Camera("follow_camera", Role["human_1"])
        follow_camera.follow("hero")
        scene.add_camera(follow_camera)
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
    assert len(project.cameras) == 1
    assert project.cameras[0].target_uid == "hero"
    assert project.tile_map is not None
    assert project.tile_map.tile_size == 16


def test_scene_keyboard_aliases_are_parsed():
    project = compile_project(
        """
        class Player(Actor):
            pass

        game = Game()
        scene = Scene(
            gravity=False,
            keyboard_aliases={
                "z": ["w", "ArrowUp"],
                "q": "a",
                " ": ["Space"],
            },
        )
        game.set_scene(scene)
        """
    )

    assert project.scene is not None
    assert project.scene.keyboard_aliases == {
        "z": ["w", "ArrowUp"],
        "q": ["a"],
        " ": ["Space"],
    }


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
        game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
        scene = Scene(gravity=False)

        bind_scene = game.set_scene
        bind_scene(scene)

        ctor = Player
        hero = ctor(uid="hero", x=10, y=20, speed=2)

        add_actor = scene.add_actor
        add_actor(hero)

        keyboard_end = KeyboardCondition.end_press
        cond = keyboard_end(["d", "q"], id="human_1")

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
        game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
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
        follow_camera = Camera("follow_camera", Role["human_1"])
        follow_camera.follow("hero")

        scene.set_map(tile_map)
        scene.add_camera(follow_camera)
        """
    )

    assert project.tile_map is not None
    assert project.tile_map.tile_size == 16
    assert project.tile_map.tile_grid == [[1, 0, 0], [0, 0, 0], [0, 0, 1]]
    assert len(project.cameras) == 1
    assert project.cameras[0].target_uid == "hero"


def test_camera_binding_is_name_based_in_actions_and_predicates():
    project = compile_project(
        """
        class Player(Actor):
            speed: int

        def move_with_camera(player: Player["hero"], cam: Camera["main_cam"]):
            cam.translate(player.speed, 0)

        def camera_ready(cam: Camera["main_cam"], player: Player["hero"]) -> bool:
            return cam.x >= player.x

        game = Game()
        game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
        scene = Scene(gravity=False)
        game.set_scene(scene)
        scene.add_actor(Player(uid="hero", x=10, y=20, speed=2))
        cam = Camera("main_cam", Role["human_1"])
        scene.add_camera(cam)
        scene.add_rule(KeyboardCondition.on_press("D", id="human_1"), move_with_camera)
        scene.add_rule(OnLogicalCondition(camera_ready, Player["hero"]), move_with_camera)
        """
    )

    action = next(item for item in project.actions if item.name == "move_with_camera")
    predicate = next(item for item in project.predicates if item.name == "camera_ready")
    assert any(param.kind == BindingKind.CAMERA for param in action.params)
    assert any(param.kind == BindingKind.CAMERA for param in predicate.params)


def test_set_camera_is_removed_with_explicit_error():
    with pytest.raises(DSLValidationError, match="set_camera\\(\\.\\.\\.\\) was removed"):
        compile_project(
            """
            class Player(Actor):
                pass

            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            scene.set_camera(Camera("cam", Role["human_1"]))
            """
        )


def test_human_role_without_camera_warns():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        compile_project(
            """
            class Player(Actor):
                pass

            game = Game()
            game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
            game.add_role(Role(id="dummy_1", required=False, kind=RoleKind.AI))
            scene = Scene(gravity=False)
            game.set_scene(scene)
            scene.add_actor(Player(uid="hero", x=0, y=0))
            ai_cam = Camera("ai_cam", Role["dummy_1"])
            scene.add_camera(ai_cam)
            """
        )
    assert any("has no camera" in str(item.message) for item in caught)


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
        game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
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
            scene.add_rule(KeyboardCondition.on_press("A", id="human_1"), noop)
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
        game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
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
        game.add_rule(KeyboardCondition.on_press("A", id="human_1"), noop)
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
        game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
        scene = Scene(gravity=False)
        game.set_scene(scene)
        game.add_actor(Player(uid="hero", x=10, y=20, speed=2))

        tile_map = TileMap(
            tile_size=24,
            grid=[
                [1, 0],
                [0, 0],
            ],
            tiles={1: Tile(color=Color(60, 60, 60))},
        )
        fixed_camera = Camera("fixed_camera", Role["human_1"], x=100, y=200)

        game.set_map(tile_map)
        scene.add_camera(fixed_camera)
        """
    )

    assert project.tile_map is not None
    assert project.tile_map.width == 2
    assert project.tile_map.height == 2
    assert project.tile_map.tile_size == 24
    assert project.tile_map.tile_grid == [[1, 0], [0, 0]]
    assert len(project.cameras) == 1
    assert project.cameras[0].x == 100
    assert project.cameras[0].y == 200


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
            scene.add_rule(KeyboardCondition.on_press("D", id="human_1"), move_right)
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
        game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
        game.add_actor(Player, "main", life=1)
        game.add_rule(KeyboardCondition.begin_press("A", id="human_1"), noop)
        game.add_rule(KeyboardCondition.on_press("A", id="human_1"), noop)
        game.add_rule(KeyboardCondition.end_press("A", id="human_1"), noop)
        game.add_rule(MouseCondition.begin_click("left", id="human_1"), noop)
        game.add_rule(MouseCondition.on_click("left", id="human_1"), noop)
        game.add_rule(MouseCondition.end_click("left", id="human_1"), noop)
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
        game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
        game.add_actor(Player, "main", life=1)
        game.add_rule(KeyboardCondition.end_press(["z", "q", "s", "d"], id="human_1"), noop)
        """
    )

    condition = project.rules[0].condition
    assert isinstance(condition, KeyboardConditionSpec)
    assert condition.phase == InputPhase.END
    assert condition.key == ["z", "q", "s", "d"]


def test_condition_decorator_adds_rule_without_add_rule_call():
    project = compile_project(
        """
        @unsafe_condition(KeyboardCondition.begin_press("g", id="human_1"))
        def enable_gravity(scene: Scene):
            Scene.enable_gravity(scene)

        game = Game()
        game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
        game.set_scene(Scene(gravity=False))
        """
    )

    assert len(project.rules) == 1
    assert project.rules[0].action_name == "enable_gravity"
    assert isinstance(project.rules[0].condition, KeyboardConditionSpec)
    assert project.rules[0].condition.phase == InputPhase.BEGIN
    assert project.rules[0].condition.key == "g"


def test_unsafe_condition_decorator_adds_rule_without_add_rule_call():
    project = compile_project(
        """
        @unsafe_condition(KeyboardCondition.begin_press("g", id="human_1"))
        def enable_gravity(scene: Scene):
            Scene.enable_gravity(scene)

        game = Game()
        game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
        game.set_scene(Scene(gravity=False))
        """
    )

    assert len(project.rules) == 1
    assert project.rules[0].action_name == "enable_gravity"
    assert isinstance(project.rules[0].condition, KeyboardConditionSpec)
    assert project.rules[0].condition.phase == InputPhase.BEGIN
    assert project.rules[0].condition.key == "g"


def test_safe_condition_decorator_adds_overlap_rule():
    project = compile_project(
        """
        class Player(Actor):
            pass

        class Coin(Actor):
            pass

        @safe_condition(OnOverlap(Player["hero"], Coin))
        def collect(player: Player, coin: Coin):
            coin.destroy()

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        scene.add_actor(Player(uid="hero", x=0, y=0))
        scene.add_actor(Coin(uid="coin_1", x=0, y=0))
        """
    )

    assert len(project.rules) == 1
    assert project.rules[0].action_name == "collect"
    assert isinstance(project.rules[0].condition, CollisionConditionSpec)
    assert project.rules[0].condition.mode == CollisionMode.OVERLAP


def test_safe_condition_errors_when_used_with_unsafe_condition_kind():
    with pytest.raises(
        DSLValidationError,
        match="@safe_condition on action 'enable_gravity' cannot wrap KeyboardCondition",
    ):
        compile_project(
            """
            @safe_condition(KeyboardCondition.begin_press("g", id="human_1"))
            def enable_gravity(scene: Scene):
                Scene.enable_gravity(scene)

            game = Game()
            game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
            game.set_scene(Scene(gravity=False))
            """
        )


def test_unsafe_condition_errors_when_used_with_safe_condition_kind():
    with pytest.raises(
        DSLValidationError,
        match="@unsafe_condition on action 'collect' cannot wrap OnOverlap",
    ):
        compile_project(
            """
            class Player(Actor):
                pass

            class Coin(Actor):
                pass

            @unsafe_condition(OnOverlap(Player["hero"], Coin))
            def collect(player: Player, coin: Coin):
                coin.destroy()

            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            scene.add_actor(Player(uid="hero", x=0, y=0))
            scene.add_actor(Coin(uid="coin_1", x=0, y=0))
            """
        )


def test_unknown_condition_decorator_is_rejected():
    with pytest.raises(
        DSLValidationError,
        match="Decorators are not allowed on actions",
    ):
        compile_project(
            """
            @legacy_condition(KeyboardCondition.begin_press("g", id="human_1"))
            def enable_gravity(scene: Scene):
                Scene.enable_gravity(scene)

            game = Game()
            game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
            game.set_scene(Scene(gravity=False))
            """
        )


def test_condition_decorator_supports_tool_calling():
    project = compile_project(
        """
        @unsafe_condition(OnToolCall("spawn_bonus", id="human_1"))
        def spawn(scene: Scene):
            \"\"\"Spawn one bonus coin\"\"\"
            scene.enable_gravity()

        game = Game()
        game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
        game.set_scene(Scene(gravity=False))
        """
    )

    assert len(project.rules) == 1
    assert project.rules[0].action_name == "spawn"
    assert isinstance(project.rules[0].condition, ToolConditionSpec)
    assert project.rules[0].condition.name == "spawn_bonus"
    assert project.rules[0].condition.tool_docstring == "Spawn one bonus coin"


def test_condition_decorator_tool_call_warns_without_action_docstring():
    with pytest.warns(UserWarning, match="MISSING INFORMAL DESCRIPTION"):
        project = compile_project(
            """
            @unsafe_condition(OnToolCall("spawn_bonus", id="human_1"))
            def spawn(scene: Scene):
                scene.enable_gravity()

            game = Game()
            game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
            game.set_scene(Scene(gravity=False))
            """
        )

    assert len(project.rules) == 1
    condition = project.rules[0].condition
    assert isinstance(condition, ToolConditionSpec)
    assert condition.tool_docstring == ""


def test_tool_call_rejects_legacy_docstring_argument():
    with pytest.raises(DSLValidationError, match="only positional argument"):
        compile_project(
            """
            def spawn(scene: Scene):
                \"\"\"Spawn helper.\"\"\"
                scene.enable_gravity()

            game = Game()
            game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
            game.set_scene(Scene(gravity=False))
            game.add_rule(OnToolCall("spawn_bonus", "legacy desc", id="human_1"), spawn)
            """
        )


def test_tool_calling_name_cannot_bind_multiple_actions():
    with pytest.raises(DSLValidationError, match="already bound to action"):
        compile_project(
            """
            @unsafe_condition(OnToolCall("toggle", id="human_1"))
            def enable(scene: Scene):
                \"\"\"Enable gravity\"\"\"
                scene.enable_gravity()

            @unsafe_condition(OnToolCall("toggle", id="human_1"))
            def disable(scene: Scene):
                \"\"\"Disable gravity\"\"\"
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
        game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
        game.add_global("target_player", Player["main_character"])
        game.add_actor(Player, "main_character", life=3)
        game.add_rule(KeyboardCondition.on_press("A", id="human_1"), heal)
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
            game.add_rule(KeyboardCondition.on_press("A", id="human_1"), bad)
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
        @unsafe_condition(OnButton("spawn_bonus"))
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


def test_scene_set_interface_accepts_literal_and_alias_variable():
    project = compile_project(
        '''
        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        hud = "<div>Score: {{score}}</div><button data-button=\\"spawn_bonus\\">Spawn</button>"
        alias_hud = hud
        scene.set_interface(alias_hud)
        '''
    )

    assert project.interface_html is not None
    assert "Score: {{score}}" in project.interface_html
    assert 'data-button="spawn_bonus"' in project.interface_html


def test_scene_set_interface_accepts_role_selector():
    project = compile_project(
        '''
        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
        scene.set_interface("<div>P1 HUD</div>", Role["human_1"])
        '''
    )

    assert project.interfaces_by_role == {"human_1": "<div>P1 HUD</div>"}


def test_scene_set_interface_accepts_interface_constructor_inline():
    project = compile_project(
        '''
        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
        scene.set_interface(Interface("<div>P1 HUD</div>", Role["human_1"], from_file=False))
        '''
    )

    assert project.interfaces_by_role == {"human_1": "<div>P1 HUD</div>"}


def test_scene_set_interface_accepts_interface_variable_from_file(tmp_path):
    hud_path = tmp_path / "hud_h1.html"
    hud_path.write_text("<div>P1 SCORE: {{role.personal_score}}</div>", encoding="utf-8")
    source_path = tmp_path / "scene.py"

    project = compile_project(
        f'''
        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
        hud_h1 = Interface("{hud_path.name}", Role["human_1"])
        scene.set_interface(hud_h1)
        ''',
        source_path=str(source_path),
    )

    assert project.interfaces_by_role == {
        "human_1": "<div>P1 SCORE: {{role.personal_score}}</div>"
    }


def test_scene_set_interface_rejects_duplicate_role_in_interface_and_call():
    with pytest.raises(DSLValidationError, match="role is provided twice"):
        compile_project(
            '''
            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
            scene.set_interface(
                Interface("<div>P1 HUD</div>", Role["human_1"], from_file=False),
                Role["human_1"],
            )
            '''
        )


def test_warns_when_editing_immutable_dsl_class_definition():
    with pytest.warns(UserWarning) as records:
        compile_project(
            """
            class Actor:
                hp: int

                def jump(self):
                    pass

            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            """
        )

    messages = "\n".join(str(record.message) for record in records)
    assert "Ignoring class definition 'Actor'" in messages
    assert "Ignoring attribute 'hp' added to immutable DSL class 'Actor'" in messages
    assert "Define a subclass instead" in messages
    assert "Ignoring method 'jump' added to immutable DSL class 'Actor'" in messages


def test_warns_when_monkey_patching_immutable_dsl_class():
    with pytest.warns(UserWarning) as records:
        compile_project(
            """
            def helper(self):
                return None

            Actor.debug_flag = True
            Scene.recenter = helper
            setattr(Game, "hot_reload", True)
            setattr(Sprite, "swap", helper)

            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            """
        )

    messages = "\n".join(str(record.message) for record in records)
    assert "Ignoring attribute 'debug_flag' added to immutable DSL class 'Actor'" in messages
    assert "Ignoring method 'recenter' added to immutable DSL class 'Scene'" in messages
    assert "Ignoring attribute 'hot_reload' added to immutable DSL class 'Game'" in messages
    assert "Ignoring method 'swap' added to immutable DSL class 'Sprite'" in messages


def test_scene_set_interface_rejects_unknown_role_selector():
    with pytest.raises(DSLValidationError, match="unknown role id 'human_9'"):
        compile_project(
            '''
            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
            scene.set_interface("<div>P9 HUD</div>", Role["human_9"])
            '''
        )


def test_setup_sprite_arguments_allow_static_expressions():
    project = compile_project(
        """
        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        game.add_resource("hero_sheet", "hero.png")
        game.add_sprite(
            Sprite(
                name="hero" + "_alt",
                resource="hero_sheet",
                frame_width=16,
                frame_height=16,
                default_clip="idle",
                clips={
                    "idle": {"frames": [0, 1, 2, 3] + [4, 5], "ticks_per_frame": 8, "loop": True},
                },
            )
        )
        """
    )

    assert project.sprites[0].name == "hero_alt"
    assert project.sprites[0].clips[0].frames == [0, 1, 2, 3, 4, 5]


def test_setup_supports_resource_and_sprite_selectors():
    project = compile_project(
        """
        class Player(Actor):
            pass

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        hero_res = Resource("hero_sheet", "hero.png")
        game.add_resource(hero_res)
        game.add_sprite(
            Sprite(
                name="hero",
                resource=Resource["hero_sheet"],
                frame_width=16,
                frame_height=16,
                default_clip="idle",
                clips={"idle": {"frames": [0, 1], "ticks_per_frame": 8, "loop": True}},
            )
        )
        scene.add_actor(Player(uid="hero_1", x=0, y=0, sprite=Sprite["hero"]))
        """
    )

    assert project.resources[0].name == "hero_sheet"
    assert project.sprites[0].resource == "hero_sheet"
    assert project.actors[0].fields["sprite"] == "hero"


def test_conditions_accept_role_selector_arguments():
    project = compile_project(
        """
        class Player(Actor):
            pass

        @unsafe_condition(KeyboardCondition.on_press("d", Role["human_1"]))
        def move(player: Player["hero"]):
            player.x = player.x + 1

        @unsafe_condition(OnToolCall("bot_move", Role["dummy_1"]))
        def bot_move(player: Player["hero"]):
            \"\"\"move\"\"\"
            player.x = player.x + 2

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
        game.add_role(Role(id="dummy_1", required=False, kind=RoleKind.AI))
        scene.add_actor(Player(uid="hero", x=0, y=0))
        """
    )

    assert isinstance(project.rules[0].condition, KeyboardConditionSpec)
    assert project.rules[0].condition.role_id == "human_1"  # type: ignore[attr-defined]
    assert isinstance(project.rules[1].condition, ToolConditionSpec)
    assert project.rules[1].condition.role_id == "dummy_1"  # type: ignore[attr-defined]


def test_game_set_interface_is_rejected():
    with pytest.raises(
        DSLValidationError,
        match="game.set_interface\\(\\.\\.\\.\\) is no longer supported; use scene.set_interface\\(\\.\\.\\.\\)",
    ):
        compile_project(
            '''
            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            game.set_interface("<div>Legacy</div>")
            '''
        )


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

        @unsafe_condition(KeyboardCondition.begin_press("e", id="human_1"))
        def spawn(scene: Scene, last_coin: Coin[-1]):
            if last_coin is not None:
                x = next_x(last_coin.x, 32)
                scene.spawn(Coin(x=x, y=0, active=True))

        game = Game()
        game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
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

            @unsafe_condition(KeyboardCondition.on_press("d", id="human_1"))
            def move(hero: Player["hero"]):
                hero.x = hero.x + get_speed(hero)

            game = Game()
            game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
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

        @unsafe_condition(KeyboardCondition.begin_press("e", id="human_1"))
        def spawn(scene: Scene, last_coin: Coin[-1]):
            if last_coin is not None:
                new_x = add_two(last_coin.x)
                scene.spawn(Coin(x=new_x, y=0, active=True))

        game = Game()
        game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
        scene = Scene(gravity=False)
        game.set_scene(scene)
        scene.add_actor(Coin(uid="coin_1", x=0, y=0, active=True))
        """
    )

    callable_names = sorted(callable_fn.name for callable_fn in project.callables)
    assert callable_names == ["add_one", "add_two"]


def test_require_code_blocks_ignores_unboxed_statements_and_hints_flag():
    with pytest.warns(UserWarning, match="--allow-unboxed"):
        with pytest.raises(DSLValidationError, match="must declare a game object"):
            compile_project(
                """
                import math

                class Player(Actor):
                    pass

                game = Game()
                scene = Scene(gravity=False)
                game.set_scene(scene)
                scene.add_actor(Player(uid="hero", x=0, y=0))
                """,
                require_code_blocks=True,
            )


def test_require_code_blocks_keeps_imports_and_compiles_boxed_statements():
    project = compile_project(
        """
        import math

        CodeBlock.begin("core")
        \"\"\"main setup\"\"\"

        class Player(Actor):
            pass

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        scene.add_actor(Player(uid="hero", x=0, y=0))

        CodeBlock.end("core")
        """,
        require_code_blocks=True,
    )

    assert len(project.actors) == 1
    assert project.actors[0].uid == "hero"


def test_code_block_rejects_legacy_descr_keyword():
    with pytest.raises(DSLValidationError, match="no longer supported"):
        compile_project(
            """
            CodeBlock.begin("core", descr="legacy")
            CodeBlock.end("core")
            """,
            require_code_blocks=True,
        )


def test_abstract_code_block_rejects_legacy_descr_keyword():
    with pytest.raises(DSLValidationError, match="no longer supported"):
        compile_project(
            """
            AbstractCodeBlock.begin("controls", role_id=str, descr="legacy")
            AbstractCodeBlock.end("controls")
            """,
            require_code_blocks=True,
        )


def test_code_block_warns_when_missing_docstring_description():
    with pytest.warns(UserWarning, match="MISSING INFORMAL DESCRIPTION"):
        project = compile_project(
            """
            CodeBlock.begin("core")

            class Player(Actor):
                pass

            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            scene.add_actor(Player(uid="hero", x=0, y=0))

            CodeBlock.end("core")
            """,
            require_code_blocks=True,
        )

    assert len(project.actors) == 1


def test_abstract_code_block_warns_when_missing_docstring_description():
    with pytest.warns(UserWarning, match="MISSING INFORMAL DESCRIPTION"):
        project = compile_project(
            """
            AbstractCodeBlock.begin("controls", role_id=str, hero_uid=str)

            @unsafe_condition(KeyboardCondition.on_press("d", id=role_id))
            def move_right(player: Player[hero_uid]):
                player.x = player.x + 1

            AbstractCodeBlock.end("controls")

            AbstractCodeBlock.instantiate("controls", role_id="human_1", hero_uid="hero_1")

            CodeBlock.begin("main")
            \"\"\"main\"\"\"

            class Player(Actor):
                pass

            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
            scene.add_actor(Player(uid="hero_1", x=0, y=0))

            CodeBlock.end("main")
            """,
            require_code_blocks=True,
        )

    assert len(project.rules) == 1


def test_abstract_code_block_instantiation_expands_rules_and_selectors():
    project = compile_project(
        """
        AbstractCodeBlock.begin(
            "player_controls",
            id=str,
            hero_name=str,
        )
        \"\"\"keyboard movement\"\"\"

        @unsafe_condition(KeyboardCondition.on_press("d", id=id))
        def move_right(player: Player[hero_name]):
            player.x = player.x + 1

        AbstractCodeBlock.end("player_controls")

        AbstractCodeBlock.instantiate(
            "player_controls",
            id="human_1",
            hero_name="hero_1",
        )
        AbstractCodeBlock.instantiate(
            "player_controls",
            id="human_2",
            hero_name="hero_2",
        )

        CodeBlock.begin("main")

        class Player(Actor):
            pass

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
        game.add_role(Role(id="human_2", required=True, kind=RoleKind.HUMAN))
        scene.add_actor(Player(uid="hero_1", x=0, y=0))
        scene.add_actor(Player(uid="hero_2", x=1, y=0))

        CodeBlock.end("main")
        """,
        require_code_blocks=True,
    )

    assert len(project.rules) == 2
    role_ids = sorted(rule.condition.role_id for rule in project.rules)  # type: ignore[attr-defined]
    assert role_ids == ["human_1", "human_2"]
    assert len(project.actions) == 2
    assert project.actions[0].name != project.actions[1].name


def test_abstract_code_block_supports_selector_macro_values():
    project = compile_project(
        """
        AbstractCodeBlock.begin(
            "player_controls",
            role=Role,
            hero=Player,
        )
        \"\"\"keyboard movement\"\"\"

        @unsafe_condition(KeyboardCondition.on_press("d", role))
        def move_right(player: hero):
            player.x = player.x + 1

        AbstractCodeBlock.end("player_controls")

        AbstractCodeBlock.instantiate(
            "player_controls",
            role=Role["human_1"],
            hero=Player["hero_1"],
        )

        CodeBlock.begin("main")
        \"\"\"main\"\"\"

        class Player(Actor):
            pass

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
        scene.add_actor(Player(uid="hero_1", x=0, y=0))

        CodeBlock.end("main")
        """,
        require_code_blocks=True,
    )

    assert len(project.rules) == 1
    assert isinstance(project.rules[0].condition, KeyboardConditionSpec)
    assert project.rules[0].condition.role_id == "human_1"  # type: ignore[attr-defined]


def test_abstract_code_block_supports_attribute_style_macro_values():
    project = compile_project(
        """
        controls = AbstractCodeBlock.begin(
            "player_controls",
            role=Role,
            hero=Player,
            key_right=str,
        )
        \"\"\"keyboard movement\"\"\"

        @unsafe_condition(KeyboardCondition.on_press(controls.key_right, controls.role))
        def move_right(player: controls.hero):
            player.x = player.x + 1

        controls.end()

        controls.instantiate(
            role=Role["human_1"],
            hero=Player["hero_1"],
            key_right="d",
        )

        CodeBlock.begin("main")
        \"\"\"main\"\"\"

        class Player(Actor):
            pass

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
        scene.add_actor(Player(uid="hero_1", x=0, y=0))

        CodeBlock.end("main")
        """,
        require_code_blocks=True,
    )

    assert len(project.rules) == 1
    assert isinstance(project.rules[0].condition, KeyboardConditionSpec)
    assert project.rules[0].condition.role_id == "human_1"  # type: ignore[attr-defined]


def test_abstract_code_block_warns_when_not_instantiated():
    with pytest.warns(UserWarning, match="never instantiated"):
        compile_project(
            """
            AbstractCodeBlock.begin("unused", id=str)
            \"\"\"unused template\"\"\"

            @unsafe_condition(KeyboardCondition.on_press("d", id=id))
            def move_right(player: Player["hero"]):
                player.x = player.x + 1

            AbstractCodeBlock.end("unused")

            CodeBlock.begin("main")

            class Player(Actor):
                pass

            game = Game()
            scene = Scene(gravity=False)
            game.set_scene(scene)
            game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
            scene.add_actor(Player(uid="hero", x=0, y=0))

            CodeBlock.end("main")
            """,
            require_code_blocks=True,
        )


def test_code_block_without_end_raises_error():
    with pytest.raises(DSLValidationError, match="never closed"):
        compile_project(
            """
            CodeBlock.begin("main")

            class Player(Actor):
                pass
            """,
            require_code_blocks=True,
        )
