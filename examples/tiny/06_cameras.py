"""Role-scoped camera setup example."""

from __future__ import annotations

import textwrap

from nanocalibur import compile_project


SOURCE = """
from nanocalibur.dsl_markers import *

class Player(Actor):
    pass

game = Game()
scene = Scene(gravity=False)
game.set_scene(scene)
game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
scene.add_actor(Player(uid="hero", x=96, y=96))

cam = Camera("cam_h1", Role["human_1"], width=24, height=16)
cam.follow("hero")
scene.add_camera(cam)
"""


if __name__ == "__main__":
    project = compile_project(textwrap.dedent(SOURCE))
    camera_names = [camera.name for camera in project.cameras]
    print(f"ok: cameras={camera_names}")
