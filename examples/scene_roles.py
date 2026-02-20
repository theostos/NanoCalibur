from nanocalibur.dsl_markers import CodeBlock, Interface, Role, RoleKind

from .scene_shared import game, scene


CodeBlock.begin("multiplayer_roles")
"""Declare join slots: up to 4 humans + 1 optional AI dummy."""


class HeroRole(Role):
    score: int


for k in range(1, 5):
    game.add_role(
        HeroRole(
            id=f"human_{k}",
            required=(k == 1),
            kind=RoleKind.HUMAN,
            score=0,
        )
    )
game.add_role(Role(id="dummy_1", required=False, kind=RoleKind.AI))

scene.set_interface(Interface("ui/hud_human.html", HeroRole["human_1"]))
scene.set_interface(Interface("ui/hud_human.html", HeroRole["human_2"]))
scene.set_interface(Interface("ui/hud_human.html", HeroRole["human_3"]))
scene.set_interface(Interface("ui/hud_human.html", HeroRole["human_4"]))

CodeBlock.end("multiplayer_roles")
