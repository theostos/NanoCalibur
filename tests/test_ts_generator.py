import textwrap

from nanocalibur.compiler import DSLCompiler
from nanocalibur.ts_generator import TSGenerator


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

    assert "ctx.getActorByUid" not in ts
    assert 'a?.type === "Player"' in ts


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
    assert 'let all_players = ctx.actors.filter((a: any) => a?.type === "Player");' in ts
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


def test_ts_generation_exports_functions():
    compiler = DSLCompiler()
    actions = compiler.compile(
        textwrap.dedent(
            """
            def increment(counter: Global["counter"]):
                counter = counter + 1
            """
        )
    )
    ts_code = TSGenerator().generate(actions)
    assert "export function increment(ctx: GameContext): void {" in ts_code
    assert "module.exports" not in ts_code


def test_ts_emits_generator_action_for_tick_yield():
    ts = compile_to_ts(
        """
        class Player(Actor):
            speed: int

        def idle(player: Player["hero"], wait_tick: Tick):
            yield wait_tick
            Actor.play(player, "idle")
        """
    )

    assert "export function* idle(ctx: GameContext): Generator<number, void, unknown> {" in ts
    assert "let wait_tick = ctx.tick;" in ts
    assert "yield wait_tick;" in ts


def test_ts_emits_random_helpers_and_calls():
    ts = compile_to_ts(
        """
        class Player(Actor):
            luck: int

        def randomize(player: Player["hero"], score: Global["score"]):
            player.luck = Random.int(1, 10)
            score = Random.normal(0, 1)
        """
    )

    assert "function __nc_random_int(" in ts
    assert "function __nc_random_float_normal(" in ts
    assert "__nc_random_int(1, 10)" in ts
    assert "__nc_random_float_normal(0, 1)" in ts


def test_ts_emits_actor_attach_and_detach_as_parent_assignments():
    ts = compile_to_ts(
        """
        class Player(Actor):
            speed: int

        class Coin(Actor):
            pass

        def bind(hero: Player["hero"], coin: Coin["coin_pet"]):
            coin.attached_to(hero)
            coin.detached()
        """
    )

    assert "coin.parent = hero.uid;" in ts
    assert 'coin.parent = "";' in ts


def test_ts_emits_scene_spawn_with_expression_fields():
    ts = compile_to_ts(
        """
        class Coin(Actor):
            pass

        def spawn(scene: Scene, last_coin: Coin[-1]):
            coin = Coin(x=last_coin.x + 32, y=224, active=True, sprite="coin")
            scene.spawn(coin)
        """
    )

    assert 'ctx.scene.spawnActor("Coin", "", { "x": (last_coin.x + 32), "y": 224, "active": true, "sprite": "coin" });' in ts


def test_ts_emits_negative_index_lookup_for_typed_actor_binding():
    ts = compile_to_ts(
        """
        class Coin(Actor):
            pass

        def use_last(last_coin: Coin[-1]):
            Actor.destroy(last_coin)
        """
    )

    assert 'const __actors_last_coin = ctx.actors.filter((a: any) => a?.type === "Coin");' in ts
    assert "let last_coin = __actors_last_coin[__actors_last_coin.length + (-1)];" in ts
