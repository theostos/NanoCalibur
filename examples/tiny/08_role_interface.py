"""Role-scoped interface with local and role placeholders."""

from __future__ import annotations

import textwrap

from nanocalibur import compile_project


SOURCE = """
from nanocalibur.dsl_markers import *

class HeroRole(HumanRole):
    score: int

class Player(Actor):
    pass

game = Game()
scene = Scene(gravity=False)
game.set_scene(scene)
game.add_role(HeroRole(id="human_1", required=True, kind=RoleKind.HUMAN, score=0))
scene.add_actor(Player(uid="hero", x=32, y=32))
cam = Camera("cam_h1", Role["human_1"], width=24, height=16)
cam.follow("hero")
scene.add_camera(cam)
scene.set_interface(
    \"\"\"
<div>
  <div>Score: {{role.score}}</div>
  <div>Up key: {{local.keybinds.move_up}}</div>
</div>
\"\"\",
    Role["human_1"],
)
"""


if __name__ == "__main__":
    project = compile_project(textwrap.dedent(SOURCE))
    print(f"ok: interfaces_by_role={list(project.interfaces_by_role.keys())}")
