from nanocalibur.dsl_markers import Actor, CodeBlock

from .shared import WORLD_HEIGHT_PX, WORLD_WIDTH_PX, scene


CodeBlock.begin("actors_and_spawn")
"""Shared RTS unit/building schema and initial ownership layout."""

PLAYER_1_ROLE_ID = "human_1"
PLAYER_2_ROLE_ID = "human_2"

P1_WORKER_UID = "p1_worker_1"
P2_WORKER_UID = "p2_worker_1"
P1_HQ_UID = "p1_hq"
P2_HQ_UID = "p2_hq"
P1_DRAG_RECT_UID = "p1_drag_rect"
P2_DRAG_RECT_UID = "p2_drag_rect"
MINERAL_NODE_1_UID = "mineral_node_1"
MINERAL_NODE_2_UID = "mineral_node_2"
GAS_NODE_1_UID = "gas_node_1"
GAS_NODE_2_UID = "gas_node_2"
P1_MINERAL_NODE_1_UID = "p1_mineral_node_1"
P1_MINERAL_NODE_2_UID = "p1_mineral_node_2"
P1_GAS_NODE_1_UID = "p1_gas_node_1"
P2_MINERAL_NODE_1_UID = "p2_mineral_node_1"
P2_MINERAL_NODE_2_UID = "p2_mineral_node_2"
P2_GAS_NODE_1_UID = "p2_gas_node_1"
SELECTION_MARKER_POOL_SIZE = 12


class RTSObject(Actor):
    owner_role_id: str
    team_id: int
    object_kind: str
    can_move: bool
    max_hp: int
    hp: int
    mineral_cost: int
    gas_cost: int
    supply_cost: int
    selection_name: str
    move_speed: int
    path_tiles_x: list[int]
    path_tiles_y: list[int]
    path_cursor: int
    path_len: int
    path_active: bool
    gather_active: bool
    gather_phase: str
    gather_resource_uid: str
    gather_hq_uid: str
    carrying_kind: str
    carrying_amount: int


class SelectionMarker(Actor):
    owner_role_id: str
    slot_index: int


class DragSelectionRect(Actor):
    owner_role_id: str


class ResourceNode(Actor):
    resource_kind: str
    amount: int
    max_amount: int
    selection_name: str


scene.add_actor(
    RTSObject(
        uid=P1_WORKER_UID,
        x=224,
        y=224,
        w=20,
        h=20,
        z=3,
        block_mask=1,
        owner_role_id=PLAYER_1_ROLE_ID,
        team_id=1,
        object_kind="worker",
        can_move=True,
        max_hp=45,
        hp=45,
        mineral_cost=50,
        gas_cost=0,
        supply_cost=1,
        selection_name="Worker",
        move_speed=220,
        path_tiles_x=[],
        path_tiles_y=[],
        path_cursor=0,
        path_len=0,
        path_active=False,
        gather_active=False,
        gather_phase="",
        gather_resource_uid="",
        gather_hq_uid="",
        carrying_kind="",
        carrying_amount=0,
        sprite="worker_p1",
    )
)
scene.add_actor(
    RTSObject(
        uid=P1_HQ_UID,
        x=256,
        y=336,
        w=64,
        h=64,
        z=2,
        block_mask=1,
        owner_role_id=PLAYER_1_ROLE_ID,
        team_id=1,
        object_kind="hq",
        can_move=False,
        max_hp=1500,
        hp=1500,
        mineral_cost=400,
        gas_cost=0,
        supply_cost=0,
        selection_name="HQ",
        move_speed=0,
        path_tiles_x=[],
        path_tiles_y=[],
        path_cursor=0,
        path_len=0,
        path_active=False,
        gather_active=False,
        gather_phase="",
        gather_resource_uid="",
        gather_hq_uid="",
        carrying_kind="",
        carrying_amount=0,
        sprite="hq_p1",
    )
)

scene.add_actor(
    RTSObject(
        uid=P2_WORKER_UID,
        x=WORLD_WIDTH_PX - 224,
        y=WORLD_HEIGHT_PX - 224,
        w=20,
        h=20,
        z=3,
        block_mask=1,
        owner_role_id=PLAYER_2_ROLE_ID,
        team_id=2,
        object_kind="worker",
        can_move=True,
        max_hp=45,
        hp=45,
        mineral_cost=50,
        gas_cost=0,
        supply_cost=1,
        selection_name="Worker",
        move_speed=220,
        path_tiles_x=[],
        path_tiles_y=[],
        path_cursor=0,
        path_len=0,
        path_active=False,
        gather_active=False,
        gather_phase="",
        gather_resource_uid="",
        gather_hq_uid="",
        carrying_kind="",
        carrying_amount=0,
        sprite="worker_p2",
    )
)
scene.add_actor(
    RTSObject(
        uid=P2_HQ_UID,
        x=WORLD_WIDTH_PX - 256,
        y=WORLD_HEIGHT_PX - 336,
        w=64,
        h=64,
        z=2,
        block_mask=1,
        owner_role_id=PLAYER_2_ROLE_ID,
        team_id=2,
        object_kind="hq",
        can_move=False,
        max_hp=1500,
        hp=1500,
        mineral_cost=400,
        gas_cost=0,
        supply_cost=0,
        selection_name="HQ",
        move_speed=0,
        path_tiles_x=[],
        path_tiles_y=[],
        path_cursor=0,
        path_len=0,
        path_active=False,
        gather_active=False,
        gather_phase="",
        gather_resource_uid="",
        gather_hq_uid="",
        carrying_kind="",
        carrying_amount=0,
        sprite="hq_p2",
    )
)

scene.add_actor(
    ResourceNode(
        uid=MINERAL_NODE_1_UID,
        x=1392,
        y=928,
        w=48,
        h=48,
        z=2,
        block_mask=1,
        resource_kind="mineral",
        amount=1500,
        max_amount=1500,
        selection_name="Mineral Field",
        sprite="mineral_node",
    )
)
scene.add_actor(
    ResourceNode(
        uid=MINERAL_NODE_2_UID,
        x=1664,
        y=992,
        w=48,
        h=48,
        z=2,
        block_mask=1,
        resource_kind="mineral",
        amount=1500,
        max_amount=1500,
        selection_name="Mineral Field",
        sprite="mineral_node",
    )
)
scene.add_actor(
    ResourceNode(
        uid=GAS_NODE_1_UID,
        x=1600,
        y=864,
        w=44,
        h=44,
        z=2,
        block_mask=1,
        resource_kind="gas",
        amount=1000,
        max_amount=1000,
        selection_name="Vespene Geyser",
        sprite="gas_node",
    )
)
scene.add_actor(
    ResourceNode(
        uid=GAS_NODE_2_UID,
        x=1536,
        y=1088,
        w=44,
        h=44,
        z=2,
        block_mask=1,
        resource_kind="gas",
        amount=1000,
        max_amount=1000,
        selection_name="Vespene Geyser",
        sprite="gas_node",
    )
)
scene.add_actor(
    ResourceNode(
        uid=P1_MINERAL_NODE_1_UID,
        x=368,
        y=336,
        w=48,
        h=48,
        z=2,
        block_mask=1,
        resource_kind="mineral",
        amount=1500,
        max_amount=1500,
        selection_name="Mineral Field",
        sprite="mineral_node",
    )
)
scene.add_actor(
    ResourceNode(
        uid=P1_MINERAL_NODE_2_UID,
        x=272,
        y=432,
        w=48,
        h=48,
        z=2,
        block_mask=1,
        resource_kind="mineral",
        amount=1500,
        max_amount=1500,
        selection_name="Mineral Field",
        sprite="mineral_node",
    )
)
scene.add_actor(
    ResourceNode(
        uid=P1_GAS_NODE_1_UID,
        x=368,
        y=432,
        w=44,
        h=44,
        z=2,
        block_mask=1,
        resource_kind="gas",
        amount=1000,
        max_amount=1000,
        selection_name="Vespene Geyser",
        sprite="gas_node",
    )
)
scene.add_actor(
    ResourceNode(
        uid=P2_MINERAL_NODE_1_UID,
        x=2704,
        y=1968,
        w=48,
        h=48,
        z=2,
        block_mask=1,
        resource_kind="mineral",
        amount=1500,
        max_amount=1500,
        selection_name="Mineral Field",
        sprite="mineral_node",
    )
)
scene.add_actor(
    ResourceNode(
        uid=P2_MINERAL_NODE_2_UID,
        x=2800,
        y=1872,
        w=48,
        h=48,
        z=2,
        block_mask=1,
        resource_kind="mineral",
        amount=1500,
        max_amount=1500,
        selection_name="Mineral Field",
        sprite="mineral_node",
    )
)
scene.add_actor(
    ResourceNode(
        uid=P2_GAS_NODE_1_UID,
        x=2704,
        y=1872,
        w=44,
        h=44,
        z=2,
        block_mask=1,
        resource_kind="gas",
        amount=1000,
        max_amount=1000,
        selection_name="Vespene Geyser",
        sprite="gas_node",
    )
)

for marker_idx in range(SELECTION_MARKER_POOL_SIZE):
    scene.add_actor(
        SelectionMarker(
            uid=f"p1_selection_marker_{marker_idx}",
            x=0,
            y=0,
            w=28,
            h=28,
            z=1,
            active=False,
            owner_role_id=PLAYER_1_ROLE_ID,
            slot_index=marker_idx,
            sprite="selection_marker_p1",
        )
    )
    scene.add_actor(
        SelectionMarker(
            uid=f"p2_selection_marker_{marker_idx}",
            x=0,
            y=0,
            w=28,
            h=28,
            z=1,
            active=False,
            owner_role_id=PLAYER_2_ROLE_ID,
            slot_index=marker_idx,
            sprite="selection_marker_p2",
        )
    )

scene.add_actor(
    DragSelectionRect(
        uid=P1_DRAG_RECT_UID,
        x=0,
        y=0,
        w=1,
        h=1,
        z=28,
        active=False,
        owner_role_id=PLAYER_1_ROLE_ID,
        sprite="drag_select_rect_p1",
    )
)
scene.add_actor(
    DragSelectionRect(
        uid=P2_DRAG_RECT_UID,
        x=0,
        y=0,
        w=1,
        h=1,
        z=28,
        active=False,
        owner_role_id=PLAYER_2_ROLE_ID,
        sprite="drag_select_rect_p2",
    )
)

CodeBlock.end("actors_and_spawn")
