from nanocalibur.dsl_markers import (
    AbstractCodeBlock,
    CodeBlock,
    KeyboardCondition,
    OnToolCall,
    condition,
)

from .scene_entities import Player


AbstractCodeBlock.begin(
    "human_player_controls",
    role_id=str,
    hero_uid=str,
    key_up=str,
    key_left=str,
    key_down=str,
    key_right=str,
)
"""Reusable movement block for one human role/hero binding."""


@condition(KeyboardCondition.on_press(key_right, id=role_id))
def move_right(player: Player[hero_uid]):
    player.vx = player.speed
    player.play("run")


@condition(KeyboardCondition.on_press(key_left, id=role_id))
def move_left(player: Player[hero_uid]):
    player.vx = -player.speed
    player.play("run")


@condition(KeyboardCondition.on_press(key_up, id=role_id))
def move_up(player: Player[hero_uid]):
    player.vy = -player.speed
    player.play("run")


@condition(KeyboardCondition.on_press(key_down, id=role_id))
def move_down(player: Player[hero_uid]):
    player.vy = player.speed
    player.play("run")


@condition(KeyboardCondition.end_press([key_left, key_right], id=role_id))
def stop_horizontal(player: Player[hero_uid]):
    player.vx = 0
    if player.vy == 0:
        player.play("idle")


@condition(KeyboardCondition.end_press([key_up, key_down], id=role_id))
def stop_vertical(player: Player[hero_uid]):
    player.vy = 0
    if player.vx == 0:
        player.play("idle")


AbstractCodeBlock.end("human_player_controls")


AbstractCodeBlock.instantiate(
    "human_player_controls",
    role_id="human_1",
    hero_uid="hero_1",
    key_up="z",
    key_left="q",
    key_down="s",
    key_right="d",
)
AbstractCodeBlock.instantiate(
    "human_player_controls",
    role_id="human_2",
    hero_uid="hero_2",
    key_up="i",
    key_left="j",
    key_down="k",
    key_right="l",
)
AbstractCodeBlock.instantiate(
    "human_player_controls",
    role_id="human_3",
    hero_uid="hero_3",
    key_up="ArrowUp",
    key_left="ArrowLeft",
    key_down="ArrowDown",
    key_right="ArrowRight",
)
AbstractCodeBlock.instantiate(
    "human_player_controls",
    role_id="human_4",
    hero_uid="hero_4",
    key_up="t",
    key_left="f",
    key_down="g",
    key_right="h",
)


CodeBlock.begin("dummy_ai_controls")
"""Optional tool-controlled bot controls (dummy external client role)."""


@condition(OnToolCall("llm_dummy_move_right", id="dummy_1"))
def llm_dummy_move_right(bot: Player["llm_dummy"]):
    """Move llm_dummy right."""
    bot.vx = bot.speed
    bot.play("run")


@condition(OnToolCall("llm_dummy_move_left", id="dummy_1"))
def llm_dummy_move_left(bot: Player["llm_dummy"]):
    """Move llm_dummy left."""
    bot.vx = -bot.speed
    bot.play("run")


@condition(OnToolCall("llm_dummy_move_up", id="dummy_1"))
def llm_dummy_move_up(bot: Player["llm_dummy"]):
    """Move llm_dummy up."""
    bot.vy = -bot.speed
    bot.play("run")


@condition(OnToolCall("llm_dummy_move_down", id="dummy_1"))
def llm_dummy_move_down(bot: Player["llm_dummy"]):
    """Move llm_dummy down."""
    bot.vy = bot.speed
    bot.play("run")


@condition(OnToolCall("llm_dummy_idle", id="dummy_1"))
def llm_dummy_idle(bot: Player["llm_dummy"]):
    """Set llm_dummy to idle animation."""
    bot.vx = 0
    bot.vy = 0
    bot.play("idle")


CodeBlock.end("dummy_ai_controls")
