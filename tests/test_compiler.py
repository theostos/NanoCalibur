import textwrap

import pytest

from compiler import DSLCompiler
from errors import DSLValidationError
from ir import Attr, Binary, BindingKind, For, If, Range, Unary


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
