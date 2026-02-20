"""Client-local role field example."""

from __future__ import annotations

import textwrap

from nanocalibur import compile_project


SOURCE = """
from nanocalibur.dsl_markers import *

class HeroRole(HumanRole):
    score: int
    quickbar: Local[list[str]] = local(["dash", "heal"])

class Player(Actor):
    pass

def gain_score(player: Player["hero"], self_role: HeroRole["human_1"]):
    self_role.score = self_role.score + 1

game = Game()
scene = Scene(gravity=False)
game.set_scene(scene)
game.add_role(HeroRole(id="human_1", required=True, kind=RoleKind.HUMAN, score=0))
scene.add_actor(Player(uid="hero", x=32, y=32))
scene.add_rule(KeyboardCondition.on_press("score_up", Role["human_1"]), gain_score)
cam = Camera("cam_h1", Role["human_1"], width=24, height=16)
cam.follow("hero")
scene.add_camera(cam)
"""


if __name__ == "__main__":
    project = compile_project(textwrap.dedent(SOURCE))
    print(f"ok: role_local_schemas={project.role_local_schemas}")
