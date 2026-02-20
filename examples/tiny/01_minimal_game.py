"""Minimal game example with one role, one actor, and one keyboard rule."""

from __future__ import annotations

import textwrap

from nanocalibur import compile_project


SOURCE = """
from nanocalibur.dsl_markers import *

class Player(Actor):
    speed: int

def move_right(player: Player["hero"]):
    player.vx = player.speed

game = Game()
scene = Scene(gravity=False)
game.set_scene(scene)
game.add_role(HumanRole(id="human_1", required=True, kind=RoleKind.HUMAN))
scene.add_actor(Player(uid="hero", x=64, y=64, speed=120))
scene.add_rule(KeyboardCondition.on_press("move_right", Role["human_1"]), move_right)
cam = Camera("cam_h1", Role["human_1"], width=24, height=16)
cam.follow("hero")
scene.add_camera(cam)
"""


if __name__ == "__main__":
    project = compile_project(textwrap.dedent(SOURCE))
    print(f"ok: actors={len(project.actors)} rules={len(project.rules)} roles={len(project.roles)}")
