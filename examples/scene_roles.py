from nanocalibur.dsl_markers import CodeBlock, Role, RoleKind

from .scene_shared import game


CodeBlock.begin(
    "multiplayer_roles",
    descr="Declare join slots: up to 4 humans + 1 optional AI dummy.",
)

game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))
game.add_role(Role(id="human_2", required=False, kind=RoleKind.HUMAN))
game.add_role(Role(id="human_3", required=False, kind=RoleKind.HUMAN))
game.add_role(Role(id="human_4", required=False, kind=RoleKind.HUMAN))
game.add_role(Role(id="dummy_1", required=False, kind=RoleKind.AI))

CodeBlock.end("multiplayer_roles")
