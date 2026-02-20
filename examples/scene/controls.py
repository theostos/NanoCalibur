from nanocalibur.dsl_markers import (
    AbstractCodeBlock,
    CodeBlock,
    KeyboardCondition,
    OnToolCall,
    Role,
    unsafe_condition,
)

from .entities import Player


human_controls = AbstractCodeBlock.begin(
    "human_player_controls",
    role=Role,
    hero=Player,
    key_up=str,
    key_left=str,
    key_down=str,
    key_right=str,
)
"""Reusable movement block for one human role/hero binding."""


@unsafe_condition(KeyboardCondition.on_press(human_controls.key_right, human_controls.role))
def move_right(player: human_controls.hero):
    player.vx = player.speed
    player.play("run")


@unsafe_condition(KeyboardCondition.on_press(human_controls.key_left, human_controls.role))
def move_left(player: human_controls.hero):
    player.vx = -player.speed
    player.play("run")


@unsafe_condition(KeyboardCondition.on_press(human_controls.key_up, human_controls.role))
def move_up(player: human_controls.hero):
    player.vy = -player.speed
    player.play("run")


@unsafe_condition(KeyboardCondition.on_press(human_controls.key_down, human_controls.role))
def move_down(player: human_controls.hero):
    player.vy = player.speed
    player.play("run")


@unsafe_condition(
    KeyboardCondition.end_press(
        [human_controls.key_left, human_controls.key_right],
        human_controls.role,
    )
)
def stop_horizontal(player: human_controls.hero):
    player.vx = 0
    if player.vy == 0:
        player.play("idle")


@unsafe_condition(
    KeyboardCondition.end_press(
        [human_controls.key_up, human_controls.key_down],
        human_controls.role,
    )
)
def stop_vertical(player: human_controls.hero):
    player.vy = 0
    if player.vx == 0:
        player.play("idle")


human_controls.end()


human_controls.instantiate(
    role=Role["human_1"],
    hero=Player["hero_1"],
    key_up="z",
    key_left="q",
    key_down="s",
    key_right="d",
)
human_controls.instantiate(
    role=Role["human_2"],
    hero=Player["hero_2"],
    key_up="i",
    key_left="j",
    key_down="k",
    key_right="l",
)
human_controls.instantiate(
    role=Role["human_3"],
    hero=Player["hero_3"],
    key_up="ArrowUp",
    key_left="ArrowLeft",
    key_down="ArrowDown",
    key_right="ArrowRight",
)
human_controls.instantiate(
    role=Role["human_4"],
    hero=Player["hero_4"],
    key_up="t",
    key_left="f",
    key_down="g",
    key_right="h",
)


CodeBlock.begin("dummy_ai_controls")
"""Optional tool-controlled bot controls (dummy external client role)."""


@unsafe_condition(OnToolCall("llm_dummy_move_right", Role["dummy_1"]))
def llm_dummy_move_right(bot: Player["llm_dummy"]):
    """Move llm_dummy right."""
    bot.vx = bot.speed
    bot.play("run")


@unsafe_condition(OnToolCall("llm_dummy_move_left", Role["dummy_1"]))
def llm_dummy_move_left(bot: Player["llm_dummy"]):
    """Move llm_dummy left."""
    bot.vx = -bot.speed
    bot.play("run")


@unsafe_condition(OnToolCall("llm_dummy_move_up", Role["dummy_1"]))
def llm_dummy_move_up(bot: Player["llm_dummy"]):
    """Move llm_dummy up."""
    bot.vy = -bot.speed
    bot.play("run")


@unsafe_condition(OnToolCall("llm_dummy_move_down", Role["dummy_1"]))
def llm_dummy_move_down(bot: Player["llm_dummy"]):
    """Move llm_dummy down."""
    bot.vy = bot.speed
    bot.play("run")


@unsafe_condition(OnToolCall("llm_dummy_idle", Role["dummy_1"]))
def llm_dummy_idle(bot: Player["llm_dummy"]):
    """Set llm_dummy to idle animation."""
    bot.vx = 0
    bot.vy = 0
    bot.play("idle")


CodeBlock.end("dummy_ai_controls")
