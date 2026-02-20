from nanocalibur.dsl_markers import (
    CodeBlock,
    Global,
    KeyboardCondition,
    OnOverlap,
    OnToolCall,
    Scene,
    Tick,
    safe_condition,
    unsafe_condition,
)

from .scene_entities import Coin, Player
from .scene_roles import HeroRole


CodeBlock.begin("gameplay_rules")
"""Shared gameplay rules: coin collection, gravity toggles, and bonus spawn."""


@safe_condition(OnOverlap(Player["hero_1"], Coin))
def collect_coin_for_player_1(
    hero: Player,
    coin: Coin,
    role: HeroRole["human_1"],
    global_score: Global["global_score", int],
):
    if coin.active and coin.uid != "coin_pet":
        coin.destroy()
        role.score = role.score + 1
        global_score = global_score + 1


@safe_condition(OnOverlap(Player["hero_2"], Coin))
def collect_coin_for_player_2(
    hero: Player,
    coin: Coin,
    role: HeroRole["human_2"],
    global_score: Global["global_score", int],
):
    if coin.active and coin.uid != "coin_pet":
        coin.destroy()
        role.score = role.score + 1
        global_score = global_score + 1


@safe_condition(OnOverlap(Player["hero_3"], Coin))
def collect_coin_for_player_3(
    hero: Player,
    coin: Coin,
    role: HeroRole["human_3"],
    global_score: Global["global_score", int],
):
    if coin.active and coin.uid != "coin_pet":
        coin.destroy()
        role.score = role.score + 1
        global_score = global_score + 1


@safe_condition(OnOverlap(Player["hero_4"], Coin))
def collect_coin_for_player_4(
    hero: Player,
    coin: Coin,
    role: HeroRole["human_4"],
    global_score: Global["global_score", int],
):
    if coin.active and coin.uid != "coin_pet":
        coin.destroy()
        role.score = role.score + 1
        global_score = global_score + 1


@unsafe_condition(KeyboardCondition.begin_press("g", id="human_1"))
def enable_gravity(scene: Scene):
    scene.enable_gravity()


@unsafe_condition(KeyboardCondition.begin_press("h", id="human_1"))
def disable_gravity(scene: Scene):
    scene.disable_gravity()


@unsafe_condition(KeyboardCondition.begin_press("e", id="human_1"))
@unsafe_condition(OnToolCall("spawn_bonus", id="human_1"))
def spawn_bonus(scene: Scene, tick: Tick, last_coin: Coin[-1]):
    """Spawn one bonus coin near hero_1."""
    for _ in range(20):
        yield tick
    if last_coin is not None and scene.elapsed > 300:
        scene.spawn(
            Coin(
                x=last_coin.x + 32,
                y=224,
                active=True,
                sprite="coin",
            )
        )
    scene.next_turn()


@unsafe_condition(OnToolCall("llm_dummy_next_turn", id="dummy_1"))
def llm_dummy_next_turn(scene: Scene):
    """Advance scene turn."""
    scene.next_turn()


CodeBlock.end("gameplay_rules")
