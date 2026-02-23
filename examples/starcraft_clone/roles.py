from nanocalibur.dsl_markers import CodeBlock, HumanRole, Interface, RoleKind

from .shared import game, scene


CodeBlock.begin("multiplayer_roles")
"""Two-player setup with shared RTS resources and per-role selection state."""


class RTSRole(HumanRole):
    minerals: int
    gas: int
    supply_used: int
    supply_cap: int
    selected_uid: str
    selected_name: str
    selected_count: int
    selected_uids: list[str]
    left_select_armed: bool


game.add_role(
    RTSRole(
        id="human_1",
        required=True,
        kind=RoleKind.HUMAN,
        minerals=50,
        gas=0,
        supply_used=1,
        supply_cap=10,
        selected_uid="",
        selected_name="None",
        selected_count=0,
        selected_uids=[],
        left_select_armed=False,
    )
)
game.add_role(
    RTSRole(
        id="human_2",
        required=False,
        kind=RoleKind.HUMAN,
        minerals=50,
        gas=0,
        supply_used=1,
        supply_cap=10,
        selected_uid="",
        selected_name="None",
        selected_count=0,
        selected_uids=[],
        left_select_armed=False,
    )
)

scene.set_interface(Interface("ui/hud_human.html", RTSRole["human_1"]))
scene.set_interface(Interface("ui/hud_human.html", RTSRole["human_2"]))

CodeBlock.end("multiplayer_roles")
