import textwrap

import pytest

from nanocalibur.compiler import DSLCompiler
from nanocalibur.errors import DSLValidationError
from nanocalibur.ir import (
    Assign,
    Attr,
    Binary,
    BindingKind,
    CallExpr,
    CallStmt,
    Continue,
    Const,
    For,
    If,
    ListExpr,
    ObjectExpr,
    Range,
    SubscriptExpr,
    Unary,
    While,
    Yield,
)


def compile_source(source: str):
    compiler = DSLCompiler()
    return compiler.compile(textwrap.dedent(source))


def test_compile_valid_schema_and_action():
    actions = compile_source(
        """
        class Player(ActorModel):
            life: int
            alive: bool
            inventory: List[str]

        def tick(player: Actor["Player"], dmg: Global["damage"]):
            if player.life > 0 and player.alive:
                player.life = player.life - dmg
        """
    )

    assert len(actions) == 1
    action = actions[0]
    assert action.name == "tick"
    assert [param.kind for param in action.params] == [
        BindingKind.ACTOR,
        BindingKind.GLOBAL,
    ]
    assert isinstance(action.body[0], If)
    assert isinstance(action.body[0].condition, Binary)


def test_reject_import_statement():
    with pytest.raises(DSLValidationError, match="Unsupported top-level statement"):
        compile_source(
            """
            import os
            """
        )


def test_reject_unknown_actor_binding_schema():
    with pytest.raises(DSLValidationError, match="Unknown actor schema"):
        compile_source(
            """
            class Player(ActorModel):
                life: int

            def bad(player: Actor["Ghost"]):
                player.life = 1
            """
        )


def test_reject_unknown_actor_field_access():
    with pytest.raises(DSLValidationError, match="has no field"):
        compile_source(
            """
            class Player(ActorModel):
                life: int

            def bad(player: Actor["Player"]):
                player.mana = 0
            """
        )


def test_reject_actor_attribute_access_when_selector_is_index():
    with pytest.raises(DSLValidationError, match="must use Actor\\[\"Type\"\\]"):
        compile_source(
            """
            class Player(ActorModel):
                life: int

            def bad(player: Actor[-1]):
                player.life = 1
            """
        )


def test_reject_undefined_variable():
    with pytest.raises(DSLValidationError, match="Unknown variable"):
        compile_source(
            """
            class Player(ActorModel):
                life: int

            def bad(player: Actor["Player"]):
                player.life = missing_value
            """
        )


def test_reject_function_calls_outside_range():
    with pytest.raises(DSLValidationError, match="Function calls are not allowed"):
        compile_source(
            """
            class Player(ActorModel):
                life: int

            def bad(player: Actor["Player"]):
                x = foo()
            """
        )


def test_compiler_errors_include_location_and_source_snippet():
    with pytest.raises(DSLValidationError) as exc_info:
        compile_source(
            """
            class Player(ActorModel):
                life: int

            def bad(player: Player["hero"]):
                player.mana = 0
            """
        )

    message = str(exc_info.value)
    assert "Location: line" in message
    assert "player.mana = 0" in message


def test_compiler_reports_python_syntax_location_and_code():
    with pytest.raises(DSLValidationError) as exc_info:
        compile_source(
            """
            def broken(:
                pass
            """
        )

    message = str(exc_info.value)
    assert "Invalid Python syntax" in message
    assert "Location: line" in message
    assert "def broken(:" in message


def test_parse_range_with_all_supported_arity():
    actions = compile_source(
        """
        def loops(counter: Global["counter"]):
            for i in range(counter):
                counter = counter + i
            for j in range(1, counter):
                counter = counter + j
            for k in range(10, 0, -1):
                counter = counter + k
        """
    )

    loops = [stmt for stmt in actions[0].body if isinstance(stmt, For)]
    assert len(loops) == 3
    assert isinstance(loops[0].iterable, Range)
    assert len(loops[0].iterable.args) == 1
    assert len(loops[1].iterable.args) == 2
    assert len(loops[2].iterable.args) == 3
    assert isinstance(loops[2].iterable.args[2], Unary)


def test_reject_range_keyword_args():
    with pytest.raises(DSLValidationError, match="does not accept keyword arguments"):
        compile_source(
            """
            def bad(counter: Global["counter"]):
                for i in range(start=0, stop=10):
                    counter = counter + i
            """
        )


def test_accept_global_binding_with_explicit_primitive_type():
    actions = compile_source(
        """
        def increment(counter: Global["counter", int]):
            counter = counter + 1
        """
    )
    assert actions[0].params[0].kind == BindingKind.GLOBAL
    assert actions[0].params[0].global_name == "counter"


def test_accept_global_binding_with_nested_list_type():
    actions = compile_source(
        """
        def keep_grid(grid: Global["grid", List[List[int]]]):
            grid = grid
        """
    )
    assert actions[0].params[0].kind == BindingKind.GLOBAL
    assert actions[0].params[0].global_name == "grid"


def test_reject_global_binding_with_unsupported_explicit_type():
    with pytest.raises(DSLValidationError, match="Global typed binding only supports"):
        compile_source(
            """
            class Player(ActorModel):
                life: int

            def bad(counter: Global["counter", Player]):
                counter = counter
            """
        )


def test_reject_actor_schema_default_values():
    with pytest.raises(DSLValidationError, match="cannot have default values"):
        compile_source(
            """
            class Player(ActorModel):
                life: int = 10
            """
        )


def test_reject_actor_schema_methods():
    with pytest.raises(
        DSLValidationError, match="can only contain annotated fields"
    ):
        compile_source(
            """
            class Player(ActorModel):
                life: int

                def reset(self):
                    self.life = 10
            """
        )


def test_compiler_resets_schemas_between_compile_calls():
    compiler = DSLCompiler()
    compiler.compile(
        textwrap.dedent(
            """
            class Player(ActorModel):
                life: int
            """
        )
    )

    with pytest.raises(DSLValidationError, match="Unknown actor schema"):
        compiler.compile(
            textwrap.dedent(
                """
                def bad(player: Actor["Player"]):
                    x = 1
                """
            )
        )


def test_accept_typed_actor_binding_head():
    actions = compile_source(
        """
        class Player(ActorModel):
            life: int

        def heal(player: Player["hero"]):
            player.life = player.life + 1
        """
    )

    heal = actions[0]
    assert heal.params[0].kind == BindingKind.ACTOR
    assert heal.params[0].actor_type == "Player"
    assert heal.params[0].actor_selector.uid == "hero"


def test_accept_plain_typed_actor_binding():
    actions = compile_source(
        """
        class Player(ActorModel):
            life: int

        def heal(player: Player):
            player.life = player.life + 1
        """
    )

    heal = actions[0]
    assert heal.params[0].kind == BindingKind.ACTOR
    assert heal.params[0].actor_type == "Player"
    assert heal.params[0].actor_selector.uid == "Player"


def test_accept_actor_base_schema_and_builtin_fields():
    actions = compile_source(
        """
        class Player(Actor):
            speed: int

        def move(player: Player["hero"]):
            player.x = player.x + player.speed
        """
    )

    move = actions[0]
    assign = move.body[0]
    assert isinstance(assign, Assign)
    assert isinstance(assign.target, Attr)
    assert assign.target.field == "x"


def test_accept_actor_uid_field_access():
    actions = compile_source(
        """
        class Player(Actor):
            speed: int

        def copy_uid(player: Player["hero"], actor_uid: Global["actor_uid"]):
            actor_uid = player.uid
        """
    )

    copy_uid = actions[0]
    assign = copy_uid.body[0]
    assert isinstance(assign, Assign)
    assert isinstance(assign.value, Attr)
    assert assign.value.obj == "player"
    assert assign.value.field == "uid"


def test_accept_scene_instance_calls():
    actions = compile_source(
        """
        class Coin(Actor):
            pass

        def spawn_bonus(scene: Scene):
            scene.enable_gravity()
            scene.spawn(Coin(uid="coin_1", x=10, y=20))
        """
    )

    spawn_bonus = actions[0]
    assert isinstance(spawn_bonus.body[0], CallStmt)
    assert isinstance(spawn_bonus.body[1], CallStmt)
    assert spawn_bonus.body[0].name == "scene_set_gravity"
    assert spawn_bonus.body[1].name == "scene_spawn_actor"


def test_accept_scene_elapsed_read_access():
    actions = compile_source(
        """
        class Player(Actor):
            speed: int

        def read_elapsed(scene: Scene, score: Global["score"]):
            if scene.elapsed >= 0:
                score = score + 1
        """
    )

    action = actions[0]
    if_stmt = action.body[0]
    assert isinstance(if_stmt, If)
    assert isinstance(if_stmt.condition, Binary)


def test_reject_scene_elapsed_write_access():
    with pytest.raises(DSLValidationError, match="scene.elapsed is read-only"):
        compile_source(
            """
            class Player(Actor):
                speed: int

            def bad(scene: Scene):
                scene.elapsed = 1
            """
        )


def test_accept_scene_spawn_with_actor_constructor_variable_and_alias():
    actions = compile_source(
        """
        class Coin(Actor):
            pass

        def spawn_bonus(scene: Scene):
            coin = Coin(x=30, y=30, active=True)
            retest = coin
            scene.spawn(retest)
        """
    )

    spawn_bonus = actions[0]
    spawn_call = spawn_bonus.body[-1]
    assert isinstance(spawn_call, CallStmt)
    assert spawn_call.name == "scene_spawn_actor"
    assert isinstance(spawn_call.args[0], Const)
    assert spawn_call.args[0].value == "Coin"
    assert isinstance(spawn_call.args[2], ObjectExpr)
    fields = spawn_call.args[2].fields
    assert isinstance(fields["x"], Const)
    assert fields["x"].value == 30
    assert isinstance(fields["y"], Const)
    assert fields["y"].value == 30
    assert isinstance(fields["active"], Const)
    assert fields["active"].value is True


def test_accept_actor_list_bindings_and_typed_iteration():
    actions = compile_source(
        """
        class Player(ActorModel):
            life: int

        def tick(all_actors: List[Actor], all_players: List[Player], turns: Global["turns"]):
            i = 0
            while i < turns:
                i = i + 1
            for p in all_players:
                p.life = p.life - 1
            for any_actor in all_actors:
                turns = turns + 1
        """
    )

    tick = actions[0]
    assert [p.kind for p in tick.params[:2]] == [
        BindingKind.ACTOR_LIST,
        BindingKind.ACTOR_LIST,
    ]
    assert tick.params[0].actor_list_type is None
    assert tick.params[1].actor_list_type == "Player"

    typed_for = [stmt for stmt in tick.body if isinstance(stmt, For)][0]
    typed_assign = typed_for.body[0]
    assert isinstance(typed_assign.target, Attr)
    assert typed_assign.target.obj == "p"
    assert typed_assign.target.field == "life"


def test_reject_field_access_from_untyped_actor_list_iteration():
    with pytest.raises(DSLValidationError, match="must use Actor\\[\"Type\"\\]"):
        compile_source(
            """
            class Player(ActorModel):
                life: int

            def bad(all_actors: List[Actor]):
                for actor in all_actors:
                    actor.life = 0
            """
        )


def test_accept_pass_in_empty_action_body():
    actions = compile_source(
        """
        class Player(Actor):
            speed: int

        def noop(player: Player["hero"]):
            pass
        """
    )

    assert len(actions) == 1
    assert actions[0].name == "noop"
    assert actions[0].body == []


def test_accept_pass_inside_control_flow():
    actions = compile_source(
        """
        class Player(Actor):
            speed: int

        def maybe_move(player: Player["hero"]):
            if player.speed > 0:
                pass
            else:
                player.x = player.x + 1
        """
    )

    action = actions[0]
    assert len(action.body) == 1
    if_stmt = action.body[0]
    assert isinstance(if_stmt, If)
    assert if_stmt.body == []
    assert len(if_stmt.orelse) == 1


def test_accept_tick_binding_and_yield_statements():
    actions = compile_source(
        """
        class Player(Actor):
            speed: int

        def idle(wait_token: Tick, player: Player["hero"]):
            yield wait_token
            yield wait_token
            player.play("idle")
        """
    )

    idle = actions[0]
    assert [param.kind for param in idle.params] == [BindingKind.TICK, BindingKind.ACTOR]
    assert isinstance(idle.body[0], Yield)
    assert isinstance(idle.body[1], Yield)
    assert isinstance(idle.body[2], CallStmt)
    assert idle.body[2].name == "play_animation"


def test_reject_static_actor_play_calls():
    with pytest.raises(DSLValidationError, match="Unsupported call statement in action body"):
        compile_source(
            """
            class Player(Actor):
                speed: int

            def idle(player: Player["hero"]):
                Actor.play(player, "idle")
            """
        )


def test_reject_yield_for_non_tick_parameter():
    with pytest.raises(DSLValidationError, match="yield must reference a parameter annotated as Tick"):
        compile_source(
            """
            def bad(counter: Global["counter"]):
                yield counter
            """
        )


def test_accept_while_true():
    actions = compile_source(
        """
        class Player(Actor):
            speed: int

        def run_forever(player: Player["hero"]):
            while True:
                player.x = player.x + player.speed
        """
    )

    run_forever = actions[0]
    assert isinstance(run_forever.body[0], While)
    assert isinstance(run_forever.body[0].condition, Const)
    assert run_forever.body[0].condition.value is True


def test_accept_none_comparisons_on_actor_bindings():
    actions = compile_source(
        """
        class Coin(Actor):
            pass

        def maybe_destroy(last_coin: Coin[-1]):
            if last_coin is None:
                pass
            if last_coin is not None:
                last_coin.destroy()
        """
    )

    action = actions[0]
    first_if = action.body[0]
    second_if = action.body[1]
    assert isinstance(first_if, If)
    assert isinstance(first_if.condition, Binary)
    assert first_if.condition.op == "=="
    assert isinstance(second_if, If)
    assert isinstance(second_if.condition, Binary)
    assert second_if.condition.op == "!="
    assert len(second_if.body) == 1
    assert isinstance(second_if.body[0], CallStmt)
    assert second_if.body[0].name == "destroy_actor"


def test_accept_continue_inside_loops():
    actions = compile_source(
        """
        class Player(Actor):
            speed: int

        def skip_steps(player: Player["hero"]):
            for i in range(0, 5):
                continue
            while player.speed > 0:
                continue
        """
    )

    action = actions[0]
    assert isinstance(action.body[0], For)
    assert isinstance(action.body[0].body[0], Continue)
    assert isinstance(action.body[1], While)
    assert isinstance(action.body[1].body[0], Continue)


def test_reject_continue_outside_loop():
    with pytest.raises(DSLValidationError, match="only allowed inside loops"):
        compile_source(
            """
            class Player(Actor):
                speed: int

            def bad(player: Player["hero"]):
                continue
            """
        )


def test_reject_is_comparison_without_none():
    with pytest.raises(DSLValidationError, match="only supported with None"):
        compile_source(
            """
            class Player(Actor):
                speed: int

            def bad(a: Player["hero"], b: Player["hero"]):
                if a is b:
                    pass
            """
        )


def test_accept_actor_attach_and_detach_calls():
    actions = compile_source(
        """
        class Player(Actor):
            speed: int

        class Coin(Actor):
            pass

        def bind_pet(hero: Player["hero"], coin: Coin["coin_pet"]):
            coin.attached_to(hero)
            coin.detached()
        """
    )

    bind_pet = actions[0]
    attach_stmt = bind_pet.body[0]
    detach_stmt = bind_pet.body[1]
    assert isinstance(attach_stmt, Assign)
    assert isinstance(attach_stmt.target, Attr)
    assert attach_stmt.target.obj == "coin"
    assert attach_stmt.target.field == "parent"
    assert isinstance(detach_stmt, Assign)
    assert isinstance(detach_stmt.value, Const)
    assert detach_stmt.value.value == ""


def test_accept_random_expression_calls():
    actions = compile_source(
        """
        class Player(Actor):
            luck: int

        def randomize(player: Player["hero"], score: Global["score"]):
            player.luck = Random.int(1, 10)
            score = Random.float(0, 1)
        """
    )

    randomize = actions[0]
    first_assign = randomize.body[0]
    second_assign = randomize.body[1]
    assert isinstance(first_assign, Assign)
    assert isinstance(first_assign.value, CallExpr)
    assert first_assign.value.name == "random_int"
    assert isinstance(second_assign, Assign)
    assert isinstance(second_assign.value, CallExpr)
    assert second_assign.value.name == "random_float_uniform"


def test_accept_nested_list_field_types():
    actions = compile_source(
        """
        class Player(Actor):
            path: List[List[int]]

        def keep(player: Player["hero"]):
            pass
        """
    )

    keep = actions[0]
    assert keep.body == []


def test_accept_scene_spawn_with_constructor_expression_fields():
    actions = compile_source(
        """
        class Coin(Actor):
            pass

        def spawn(scene: Scene, last_coin: Coin[-1]):
            coin = Coin(x=last_coin.x + 32, y=224, active=True, sprite="coin")
            scene.spawn(coin)
        """
    )

    spawn = actions[0]
    spawn_call = spawn.body[-1]
    assert isinstance(spawn_call, CallStmt)
    assert spawn_call.name == "scene_spawn_actor"


def test_accept_list_literals_and_subscript_expressions():
    actions = compile_source(
        """
        def mutate(values: Global["values"]):
            last = values[-1]
            values = [last, 1, 2]
        """
    )

    mutate = actions[0]
    first_assign = mutate.body[0]
    second_assign = mutate.body[1]
    assert isinstance(first_assign, Assign)
    assert isinstance(first_assign.value, SubscriptExpr)
    assert isinstance(second_assign, Assign)
    assert isinstance(second_assign.value, ListExpr)


def test_accept_tick_elapsed_read_access():
    actions = compile_source(
        """
        class Coin(Actor):
            pass

        def spawn(scene: Scene, tick: Tick, last_coin: Coin[-1]):
            if tick.elapsed >= 0 and last_coin is not None:
                scene.spawn(Coin(x=last_coin.x + 1, y=0, active=True))
        """
    )

    spawn = actions[0]
    if_stmt = spawn.body[0]
    assert isinstance(if_stmt, If)
    assert isinstance(if_stmt.condition, Binary)


def test_reject_tick_elapsed_write_access():
    with pytest.raises(DSLValidationError, match="tick.elapsed is read-only"):
        compile_source(
            """
            def bad(tick: Tick):
                tick.elapsed = 1
            """
        )
