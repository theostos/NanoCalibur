"""Turn-based multiplayer example with explicit scene.next_turn()."""

from __future__ import annotations

import textwrap

from nanocalibur import compile_project


SOURCE = """
from nanocalibur.dsl_markers import *

class Player(Actor):
    speed: int

def act(player: Player["hero"], scene: Scene):
    player.x = player.x + player.speed
    scene.next_turn()

game = Game()
scene = Scene(gravity=False)
game.set_scene(scene)
game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
scene.add_actor(Player(uid="hero", x=32, y=32, speed=10))
scene.add_rule(KeyboardCondition.on_press("act", Role["human_1"]), act)
cam = Camera("cam_h1", Role["human_1"], width=24, height=16)
cam.follow("hero")
scene.add_camera(cam)
game.set_multiplayer(
    Multiplayer(
        default_loop="turn_based",
        allowed_loops=["turn_based"],
    )
)
"""


if __name__ == "__main__":
    project = compile_project(textwrap.dedent(SOURCE))
    loop_mode = project.multiplayer.default_loop.value if project.multiplayer else "none"
    print(f"ok: loop={loop_mode} contains_next_turn_call={project.contains_next_turn_call}")
