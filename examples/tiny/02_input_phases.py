"""Keyboard begin/on/end phase example."""

from __future__ import annotations

import textwrap

from nanocalibur import compile_project


SOURCE = """
from nanocalibur.dsl_markers import *

class Player(Actor):
    speed: int

def start_move(player: Player["hero"]):
    player.vx = player.speed

def keep_move(player: Player["hero"]):
    player.vx = player.speed

def stop_move(player: Player["hero"]):
    player.vx = 0

game = Game()
scene = Scene(gravity=False)
game.set_scene(scene)
game.add_role(HumanRole(id="human_1", required=True, kind=RoleKind.HUMAN))
scene.add_actor(Player(uid="hero", x=64, y=64, speed=120))
scene.add_rule(KeyboardCondition.begin_press("move_right", Role["human_1"]), start_move)
scene.add_rule(KeyboardCondition.on_press("move_right", Role["human_1"]), keep_move)
scene.add_rule(KeyboardCondition.end_press("move_right", Role["human_1"]), stop_move)
cam = Camera("cam_h1", Role["human_1"], width=24, height=16)
cam.follow("hero")
scene.add_camera(cam)
"""


if __name__ == "__main__":
    project = compile_project(textwrap.dedent(SOURCE))
    print(f"ok: compiled {len(project.rules)} keyboard phase rules")
