import textwrap

import pytest

from nanocalibur.compiler import DSLCompiler
from nanocalibur.errors import DSLValidationError
from nanocalibur.exporter import project_to_dict
from nanocalibur.ir import CallStmt
from nanocalibur.project_compiler import ProjectCompiler
from nanocalibur.ts_generator import TSGenerator


def _compile_project(source: str):
    return ProjectCompiler().compile(textwrap.dedent(source))


def test_project_compiler_collects_resources_and_sprites():
    project = _compile_project(
        """
        class Player(ActorModel):
            x: int
            y: int

        def animate(player: Player["hero"]):
            player.play("idle")

        game = Game()
        game.add_actor(Player, "hero", x=0, y=0)
        game.add_resource("hero_sheet", "res/hero.png")
        game.add_sprite(
            uid="hero",
            resource="hero_sheet",
            frame_width=16,
            frame_height=16,
            symbol="@",
            description="the player hero",
            default_clip="idle",
            clips={
                "idle": {"frames": [0, 1], "ticks_per_frame": 6, "loop": True},
                "run": {"frames": [2, 3], "ticks_per_frame": 4, "loop": True},
            },
        )
        game.add_rule(KeyboardCondition.on_press("A"), animate)
        """
    )

    assert len(project.resources) == 1
    assert project.resources[0].name == "hero_sheet"
    assert project.resources[0].path == "res/hero.png"

    assert len(project.sprites) == 1
    sprite = project.sprites[0]
    assert sprite.uid == "hero"
    assert sprite.resource == "hero_sheet"
    assert sprite.frame_width == 16
    assert sprite.symbol == "@"
    assert sprite.description == "the player hero"
    assert sprite.default_clip == "idle"
    assert {clip.name for clip in sprite.clips} == {"idle", "run"}


def test_compiler_emits_actor_play_call_stmt():
    compiler = DSLCompiler()
    actions = compiler.compile(
        textwrap.dedent(
            """
            class Player(ActorModel):
                x: int

            def animate(player: Player["hero"]):
                player.play("idle")
            """
        )
    )

    stmt = actions[0].body[0]
    assert isinstance(stmt, CallStmt)
    assert stmt.name == "play_animation"


def test_ts_generator_emits_runtime_animation_hook_call():
    compiler = DSLCompiler()
    actions = compiler.compile(
        textwrap.dedent(
            """
            class Player(ActorModel):
                x: int

            def animate(player: Player["hero"]):
                player.play("idle")
            """
        )
    )

    ts = TSGenerator().generate(actions)
    assert "playAnimation?: (actor: any, clipName: string) => void;" in ts
    assert "if (ctx.playAnimation) {" in ts
    assert "ctx.playAnimation(player, \"idle\");" in ts


def test_project_compiler_rejects_sprite_with_unknown_resource():
    with pytest.raises(DSLValidationError, match="unknown resource"):
        _compile_project(
            """
            class Player(ActorModel):
                x: int

            def noop(player: Player["hero"]):
                player.x = player.x

            game = Game()
            game.add_actor(Player, "hero", x=0)
            game.add_sprite(
                uid="hero",
                resource="missing_sheet",
                frame_width=16,
                frame_height=16,
                clips={"idle": [0]},
            )
            game.add_rule(KeyboardCondition.on_press("A"), noop)
            """
        )


def test_exporter_serializes_resources_and_sprites_into_spec():
    project = _compile_project(
        """
        class Player(ActorModel):
            x: int

        def animate(player: Player["hero"]):
            player.play("idle")

        game = Game()
        game.add_actor(Player, "hero", x=0)
        game.add_resource("hero_sheet", "res/hero.png")
        game.add_sprite(
            uid="hero",
            resource="hero_sheet",
            frame_width=16,
            frame_height=16,
            symbol="@",
            description="the player hero",
            clips={"idle": [0, 1, 2]},
        )
        game.add_rule(KeyboardCondition.on_press("A"), animate)
        """
    )

    spec = project_to_dict(project)
    assert spec["resources"] == [{"name": "hero_sheet", "path": "res/hero.png"}]
    assert spec["sprites"]["by_uid"]["hero"]["resource"] == "hero_sheet"
    assert spec["sprites"]["by_uid"]["hero"]["frame_width"] == 16
    assert spec["sprites"]["by_uid"]["hero"]["symbol"] == "@"
    assert spec["sprites"]["by_uid"]["hero"]["description"] == "the player hero"
    assert spec["sprites"]["by_uid"]["hero"]["clips"]["idle"]["frames"] == [0, 1, 2]


def test_exporter_serializes_named_sprites_for_actor_sprite_binding():
    project = _compile_project(
        """
        class Player(Actor):
            speed: int

        def animate(player: Player["hero"]):
            player.play("idle")

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
                clips={"idle": [0, 1, 2]},
            )
        )
        scene.add_rule(KeyboardCondition.on_press("A"), animate)
        """
    )

    spec = project_to_dict(project)
    assert "hero" in spec["sprites"]["by_name"]
    assert spec["sprites"]["by_name"]["hero"]["frame_width"] == 16


def test_compiler_supports_actor_instance_play_and_destroy_calls():
    compiler = DSLCompiler()
    actions = compiler.compile(
        textwrap.dedent(
            """
            class Player(ActorModel):
                x: int

            def animate(player: Player["hero"]):
                player.play("run")
                player.destroy()
            """
        )
    )

    play_stmt = actions[0].body[0]
    destroy_stmt = actions[0].body[1]
    assert isinstance(play_stmt, CallStmt)
    assert play_stmt.name == "play_animation"
    assert isinstance(destroy_stmt, CallStmt)
    assert destroy_stmt.name == "destroy_actor"


def test_compiler_supports_scene_binding_gravity_and_spawn():
    compiler = DSLCompiler()
    actions = compiler.compile(
        textwrap.dedent(
            """
            class Coin(ActorModel):
                x: int
                y: int

            def setup(scene: Scene):
                Scene.enable_gravity(scene)
                Scene.spawn(scene, Coin, "coin_2", x=10, y=20)
            """
        )
    )

    gravity_stmt = actions[0].body[0]
    spawn_stmt = actions[0].body[1]
    assert isinstance(gravity_stmt, CallStmt)
    assert gravity_stmt.name == "scene_set_gravity"
    assert isinstance(spawn_stmt, CallStmt)
    assert spawn_stmt.name == "scene_spawn_actor"


def test_project_compiler_parses_sprite_object_and_scene_config():
    project = _compile_project(
        """
        class Player(ActorModel):
            x: int
            y: int

        def noop(player: Player["hero"]):
            player.play("idle")

        game = Game()
        game.set_scene(Scene(gravity=True))
        game.add_actor(Player, "hero", x=0, y=0)
        game.add_resource("hero_sheet", "res/hero.png")
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

    spec = project_to_dict(project)
    assert spec["scene"] == {"gravity_enabled": True}
