"""Authoritative safe collision rule example."""

from __future__ import annotations

import textwrap

from nanocalibur import compile_project


SOURCE = """
from nanocalibur.dsl_markers import *

class Player(Actor):
    pass

class Coin(Actor):
    pass

@safe_condition(OnOverlap(Player["hero"], Coin))
def collect(hero: Player, coin: Coin, score: Global["score", int]):
    if coin.active:
        coin.destroy()
        score = score + 1

game = Game()
scene = Scene(gravity=False)
game.set_scene(scene)
game.add_role(HumanRole(id="human_1", required=True, kind=RoleKind.HUMAN))
game.add_global("score", 0)
scene.add_actor(Player(uid="hero", x=64, y=64))
scene.add_actor(Coin(uid="coin_1", x=64, y=64))
cam = Camera("cam_h1", Role["human_1"], width=24, height=16)
cam.follow("hero")
scene.add_camera(cam)
"""


if __name__ == "__main__":
    project = compile_project(textwrap.dedent(SOURCE))
    print(f"ok: predicates={len(project.predicates)} rules={len(project.rules)} globals={len(project.globals)}")
