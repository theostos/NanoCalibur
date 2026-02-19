import textwrap

from nanocalibur.compiler import DSLCompiler
from nanocalibur.project_compiler import ProjectCompiler
from nanocalibur.ts_generator import TSGenerator


def compile_to_ts(source: str) -> str:
    compiler = DSLCompiler()
    actions = compiler.compile(textwrap.dedent(source))
    return TSGenerator().generate(actions)


def compile_project_to_ts(source: str) -> str:
    project = ProjectCompiler().compile(textwrap.dedent(source))
    return TSGenerator().generate(project.actions, project.predicates, project.callables)


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
            player.play("idle")
        """
    )

    assert "export function* idle(ctx: GameContext): Generator<number, void, unknown> {" in ts
    assert "let wait_tick = ctx.tick;" in ts
    assert "yield wait_tick;" in ts
    assert "playAnimation?: (actor: any, clipName: string) => void;" in ts
    assert "if (ctx.playAnimation) {" in ts
    assert 'ctx.playAnimation(player, "idle");' in ts


def test_ts_refreshes_actor_selector_bindings_after_yield():
    ts = compile_to_ts(
        """
        class Coin(Actor):
            pass

        def spawn(scene: Scene, tick: Tick, last_coin: Coin[-1]):
            yield tick
            if last_coin is not None:
                scene.spawn(Coin(x=last_coin.x + 1, y=0))
        """
    )

    assert "const __nc_refresh_binding_last_coin = () => {" in ts
    assert "let last_coin: any;" in ts
    assert "__nc_refresh_binding_last_coin();" in ts
    assert "yield tick;" in ts
    assert "yield tick;\n  __nc_refresh_binding_last_coin();" in ts


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
            last_coin.destroy()
        """
    )

    assert 'const __actors_last_coin = ctx.actors.filter((a: any) => a?.type === "Coin");' in ts
    assert "let last_coin = __actors_last_coin[__actors_last_coin.length + (-1)];" in ts


def test_ts_emits_null_checks_for_none_comparisons():
    ts = compile_to_ts(
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

    assert "if ((last_coin == null)) {" in ts
    assert "if ((last_coin != null)) {" in ts


def test_ts_emits_continue_statement():
    ts = compile_to_ts(
        """
        class Player(Actor):
            speed: int

        def skip_steps(player: Player["hero"]):
            for i in range(0, 4):
                continue
        """
    )

    assert "continue;" in ts


def test_ts_emits_predicate_with_context_bindings():
    ts = compile_project_to_ts(
        """
        class Player(Actor):
            life: int

        def mark_dead(flag: Global["is_dead"]):
            flag = True

        def should_mark(scene: Scene, score: Global["score"], wait_tick: Tick, player: Player) -> bool:
            return player.life <= score and scene.elapsed >= 0 and wait_tick == wait_tick

        game = Game()
        scene = Scene(gravity=False)
        game.set_scene(scene)
        game.add_global("is_dead", False)
        game.add_global("score", 1)
        scene.add_actor(Player(uid="hero", life=1))
        scene.add_rule(OnLogicalCondition(should_mark, Player), mark_dead)
        """
    )

    assert "export function should_mark(ctx: GameContext): boolean {" in ts
    assert "let scene = ctx.scene;" in ts
    assert 'let score = ctx.globals["score"];' in ts
    assert "let wait_tick = ctx.tick;" in ts
    assert "__nanocalibur_logical_target__" in ts
    assert "(scene?.elapsed ?? ctx.elapsed ?? ctx.tick)" in ts


def test_ts_emits_tick_elapsed_expression():
    ts = compile_to_ts(
        """
        class Coin(Actor):
            pass

        def spawn(scene: Scene, tick: Tick, last_coin: Coin[-1]):
            if last_coin is not None:
                should_spawn = tick.elapsed > 10
                scene.spawn(Coin(x=last_coin.x + 1, y=0, active=should_spawn))
        """
    )

    assert "should_spawn = ((ctx.elapsed ?? ctx.tick) > 10);" in ts


def test_ts_emits_list_literals_and_subscript_access():
    ts = compile_to_ts(
        """
        def mutate(values: Global["values"]):
            last = values[-1]
            values = [last, 1, 2]
        """
    )

    assert "let last: any;" in ts
    assert "last = values[values.length + (-1)];" in ts
    assert "values = [last, 1, 2];" in ts


def test_ts_emits_callable_helpers_and_invocations():
    ts = compile_project_to_ts(
        """
        class Coin(Actor):
            pass

        @callable
        def next_x(x: float, offset: int) -> float:
            return x + offset

        @condition(KeyboardCondition.begin_press("e", id="human_1"))
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

    assert "export function next_x(x: any, offset: any): any {" in ts
    assert "let x: any;" in ts
    assert "x = next_x(last_coin.x, 32);" in ts
