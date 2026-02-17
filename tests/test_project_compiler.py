import textwrap

import pytest

from errors import DSLValidationError
from ir import Attr
from project_compiler import ProjectCompiler
from nanocalibur.game_model import InputPhase, KeyboardConditionSpec, MouseConditionSpec


def compile_project(source: str):
    return ProjectCompiler().compile(textwrap.dedent(source))


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

        def on_hit(player: Player["main_character"]):
            player.life = player.life - 1

        def mark_dead(player: Player["main_character"], dead: Global["is_dead"]):
            dead = True

        def is_dead(player: Player) -> bool:
            return player.life <= 0

        game = Game()
        game.add_global("heal", 2)
        game.add_global("is_dead", False)
        game.add_actor(Player, "main_character", life=3, x=10, y=20)
        game.add_actor(Enemy, "enemy_1", life=5)

        cond_key = KeyboardCondition.is_pressed("A")
        cond_collision = CollisionRelated(WithUID(Player, "main_character"), Any(Player))
        cond_logic = LogicalRelated(is_dead, Any(Player))

        game.add_rule(cond_key, heal)
        game.add_rule(cond_collision, on_hit)
        game.add_rule(cond_logic, mark_dead)
        game.set_map(TileMap(width=16, height=12, tile_size=32, solid=[(0, 0), (1, 1)]))
        game.set_camera(Camera.follow("main_character"))
        """
    )

    assert set(project.actor_schemas.keys()) == {"Player", "Enemy"}
    assert len(project.globals) == 2
    assert len(project.actors) == 2
    assert len(project.rules) == 3
    assert project.tile_map is not None
    assert project.tile_map.solid_tiles == [(0, 0), (1, 1)]
    assert project.camera is not None
    assert project.camera.target_uid == "main_character"
    assert [predicate.name for predicate in project.predicates] == ["is_dead"]
    assert isinstance(project.rules[0].condition, KeyboardConditionSpec)
    assert project.rules[0].condition.phase == InputPhase.ON


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


def test_global_actor_pointer_typed_allows_field_access():
    project = compile_project(
        """
        class Player(ActorModel):
            life: int

        def heal(target: Global["target_player"]):
            target.life = target.life + 1

        game = Game()
        game.add_global("target_player", WithUID(Player, "main_character"))
        game.add_actor(Player, "main_character", life=3)
        game.add_rule(KeyboardCondition.is_pressed("A"), heal)
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
            game.add_global("target_actor", WithUID(Actor, "main_character"))
            game.add_actor(Player, "main_character", life=3)
            game.add_rule(KeyboardCondition.is_pressed("A"), bad)
            """
        )
