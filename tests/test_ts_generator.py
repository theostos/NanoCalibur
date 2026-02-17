import textwrap

from compiler import DSLCompiler
from ts_generator import TSGenerator


def compile_to_ts(source: str) -> str:
    compiler = DSLCompiler()
    actions = compiler.compile(textwrap.dedent(source))
    return TSGenerator().generate(actions)


def test_ts_preserves_string_constant_case():
    ts = compile_to_ts(
        """
        def rename(name: Global["name"]):
            name = "BossHP"
        """
    )

    assert '"BossHP"' in ts
    assert '"bosshp"' not in ts


def test_ts_writes_back_global_bindings():
    ts = compile_to_ts(
        """
        def increment(counter: Global["counter"]):
            counter = counter + 1
        """
    )

    assert 'let counter = ctx.globals["counter"];' in ts
    assert 'ctx.globals["counter"] = counter;' in ts


def test_ts_emits_actor_lookup_for_type_binding():
    ts = compile_to_ts(
        """
        class Player(ActorModel):
            life: int

        def heal(player: Actor["Player"]):
            player.life = player.life + 1
        """
    )

    assert "ctx.getActorByUid" in ts
    assert 'a?.uid === "Player"' in ts


def test_ts_emits_actor_lookup_for_typed_binding_head():
    ts = compile_to_ts(
        """
        class Player(ActorModel):
            life: int

        def heal(player: Player["hero"]):
            player.life = player.life + 1
        """
    )

    assert 'ctx.getActorByUid("hero")' in ts


def test_ts_emits_range_loop_with_negative_step():
    ts = compile_to_ts(
        """
        def countdown(counter: Global["counter"]):
            for i in range(10, 0, -1):
                counter = counter + i
        """
    )

    assert "const __step_i = (-1);" in ts
    assert "__step_i >= 0 ? i < 0 : i > 0" in ts


def test_ts_emits_while_and_for_over_list_bindings():
    ts = compile_to_ts(
        """
        class Player(ActorModel):
            life: int

        def tick(all_actors: List[Actor], all_players: List[Player], turns: Global["turns"]):
            i = 0
            while i < turns:
                i = i + 1
            for p in all_players:
                p.life = p.life - 1
            for actor in all_actors:
                turns = turns + 1
        """
    )

    assert "let all_actors = ctx.actors;" in ts
    assert 'let all_players = ctx.actors.filter((a: any) => a?.uid === "Player");' in ts
    assert "while ((i < turns)) {" in ts
    assert "for (let p of all_players) {" in ts
    assert "p.life = (p.life - 1);" in ts
    assert "for (let actor of all_actors) {" in ts


def test_generation_is_deterministic_for_same_source():
    source = """
    class Player(ActorModel):
        life: int

    def tick(player: Actor["Player"], dmg: Global["damage"]):
        if player.life > 0:
            player.life = player.life - dmg
    """

    first = compile_to_ts(source)
    second = compile_to_ts(source)
    assert first == second


def test_js_generation_outputs_commonjs_module():
    compiler = DSLCompiler()
    actions = compiler.compile(
        textwrap.dedent(
            """
            def increment(counter: Global["counter"]):
                counter = counter + 1
            """
        )
    )
    js_code = TSGenerator().generate_javascript(actions)
    assert "function increment(ctx) {" in js_code
    assert "module.exports = { increment };" in js_code


def test_esm_generation_exports_functions():
    compiler = DSLCompiler()
    actions = compiler.compile(
        textwrap.dedent(
            """
            def increment(counter: Global["counter"]):
                counter = counter + 1
            """
        )
    )
    esm_code = TSGenerator().generate_esm_javascript(actions)
    assert "export function increment(ctx) {" in esm_code
    assert "module.exports" not in esm_code
