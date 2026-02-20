"""Tool-call condition example for remote AI agents."""

from __future__ import annotations

import textwrap

from nanocalibur import compile_project


SOURCE = """
from nanocalibur.dsl_markers import *

class Bot(Actor):
    speed: int

@unsafe_condition(OnToolCall("bot_move_right", Role["dummy_1"]))
def bot_move_right(bot: Bot["bot_1"]):
    \"\"\"Move bot one step to the right.\"\"\"
    bot.x = bot.x + bot.speed

game = Game()
scene = Scene(gravity=False)
game.set_scene(scene)
game.add_role(Role(id="dummy_1", required=True, kind=RoleKind.AI))
scene.add_actor(Bot(uid="bot_1", x=32, y=32, speed=8))
"""


if __name__ == "__main__":
    project = compile_project(textwrap.dedent(SOURCE))
    tools = [rule.condition.name for rule in project.rules if hasattr(rule.condition, "name")]
    print(f"ok: tool-rules={len(project.rules)} tool-names={tools}")
