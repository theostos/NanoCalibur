from nanocalibur.dsl_markers import Camera, CodeBlock, Color, Role, Sprite, Tile, TileMap

from .constants import (
    BM_NONE,
    BM_SOLID,
    BM_WALL,
    HQ_HP,
    P1_BASE_X,
    P1_BASE_Y,
    P1_GAS_X,
    P1_GAS_Y,
    P1_MINERAL_X,
    P1_MINERAL_Y,
    P2_BASE_X,
    P2_BASE_Y,
    P2_GAS_X,
    P2_GAS_Y,
    P2_MINERAL_X,
    P2_MINERAL_Y,
    RESOURCE_AMOUNT,
    RESOURCE_PER_TICK,
    SUPPLY_WORKER,
    TILE,
    WORKER_ARMOR,
    WORKER_ATTACK,
    WORKER_GATHER,
    WORKER_HP,
    WORKER_SPEED,
)
from .schemas import GasGeyser, HQ, MineralPatch, Worker
from .shared import scene


CodeBlock.begin("starcraft_clone_world")
"""Fixed map, role-scoped cameras, HQs, and initial worker/resource actors."""

scene.set_map(
    TileMap(
        tile_size=TILE,
        grid="maps/arena_1v1.txt",
        tiles={
            1: Tile(
                block_mask=BM_WALL,
                color=Color(48, 56, 76, symbol="#", description="solid wall"),
            ),
        },
    )
)

camera_h1 = Camera("camera_h1", Role["human_1"], width=52, height=32)
camera_h1.follow("p1_hq")
scene.add_camera(camera_h1)

camera_h2 = Camera("camera_h2", Role["human_2"], width=52, height=32)
camera_h2.follow("p2_hq")
scene.add_camera(camera_h2)

scene.add_actor(
    HQ(
        uid="p1_hq",
        x=P1_BASE_X,
        y=P1_BASE_Y,
        w=40,
        h=40,
        owner_id="human_1",
        visible_mask=1,
        hp=HQ_HP,
        max_hp=HQ_HP,
        supply_provided=10,
        block_mask=BM_SOLID,
        sprite=Sprite["hq"],
    )
)
scene.add_actor(
    HQ(
        uid="p2_hq",
        x=P2_BASE_X,
        y=P2_BASE_Y,
        w=40,
        h=40,
        owner_id="human_2",
        visible_mask=2,
        hp=HQ_HP,
        max_hp=HQ_HP,
        supply_provided=10,
        block_mask=BM_SOLID,
        sprite=Sprite["hq"],
    )
)

scene.add_actor(
    Worker(
        uid="p1_worker_1",
        x=P1_BASE_X + 3 * TILE,
        y=P1_BASE_Y - TILE,
        w=18,
        h=18,
        owner_id="human_1",
        visible_mask=1,
        hp=WORKER_HP,
        max_hp=WORKER_HP,
        attack=WORKER_ATTACK,
        armor=WORKER_ARMOR,
        speed=WORKER_SPEED,
        supply=SUPPLY_WORKER,
        march_dir=+1,
        gather_per_tick=WORKER_GATHER,
        cargo_minerals=0,
        cargo_gas=0,
        harvest_target_uid="p1_minerals_a",
        harvest_resource="mineral",
        home_hq_uid="p1_hq",
        selected=False,
        order="move",
        target_x=P1_MINERAL_X,
        target_y=P1_MINERAL_Y,
        target_uid="p1_minerals_a",
        has_queued_order=False,
        queued_order="idle",
        queued_target_x=P1_MINERAL_X,
        queued_target_y=P1_MINERAL_Y,
        queued_target_uid="",
        block_mask=BM_SOLID,
        sprite=Sprite["worker"],
    )
)
scene.add_actor(
    Worker(
        uid="p1_worker_2",
        x=P1_BASE_X + 3 * TILE,
        y=P1_BASE_Y + TILE,
        w=18,
        h=18,
        owner_id="human_1",
        visible_mask=1,
        hp=WORKER_HP,
        max_hp=WORKER_HP,
        attack=WORKER_ATTACK,
        armor=WORKER_ARMOR,
        speed=WORKER_SPEED,
        supply=SUPPLY_WORKER,
        march_dir=+1,
        gather_per_tick=WORKER_GATHER,
        cargo_minerals=0,
        cargo_gas=0,
        harvest_target_uid="p1_minerals_b",
        harvest_resource="mineral",
        home_hq_uid="p1_hq",
        selected=False,
        order="move",
        target_x=P1_MINERAL_X + 2 * TILE,
        target_y=P1_MINERAL_Y - TILE,
        target_uid="p1_minerals_b",
        has_queued_order=False,
        queued_order="idle",
        queued_target_x=P1_MINERAL_X + 2 * TILE,
        queued_target_y=P1_MINERAL_Y - TILE,
        queued_target_uid="",
        block_mask=BM_SOLID,
        sprite=Sprite["worker"],
    )
)
scene.add_actor(
    Worker(
        uid="p2_worker_1",
        x=P2_BASE_X - 3 * TILE,
        y=P2_BASE_Y - TILE,
        w=18,
        h=18,
        owner_id="human_2",
        visible_mask=2,
        hp=WORKER_HP,
        max_hp=WORKER_HP,
        attack=WORKER_ATTACK,
        armor=WORKER_ARMOR,
        speed=WORKER_SPEED,
        supply=SUPPLY_WORKER,
        march_dir=-1,
        gather_per_tick=WORKER_GATHER,
        cargo_minerals=0,
        cargo_gas=0,
        harvest_target_uid="p2_minerals_a",
        harvest_resource="mineral",
        home_hq_uid="p2_hq",
        selected=False,
        order="move",
        target_x=P2_MINERAL_X,
        target_y=P2_MINERAL_Y,
        target_uid="p2_minerals_a",
        has_queued_order=False,
        queued_order="idle",
        queued_target_x=P2_MINERAL_X,
        queued_target_y=P2_MINERAL_Y,
        queued_target_uid="",
        block_mask=BM_SOLID,
        sprite=Sprite["worker"],
    )
)
scene.add_actor(
    Worker(
        uid="p2_worker_2",
        x=P2_BASE_X - 3 * TILE,
        y=P2_BASE_Y + TILE,
        w=18,
        h=18,
        owner_id="human_2",
        visible_mask=2,
        hp=WORKER_HP,
        max_hp=WORKER_HP,
        attack=WORKER_ATTACK,
        armor=WORKER_ARMOR,
        speed=WORKER_SPEED,
        supply=SUPPLY_WORKER,
        march_dir=-1,
        gather_per_tick=WORKER_GATHER,
        cargo_minerals=0,
        cargo_gas=0,
        harvest_target_uid="p2_minerals_b",
        harvest_resource="mineral",
        home_hq_uid="p2_hq",
        selected=False,
        order="move",
        target_x=P2_MINERAL_X - 2 * TILE,
        target_y=P2_MINERAL_Y - TILE,
        target_uid="p2_minerals_b",
        has_queued_order=False,
        queued_order="idle",
        queued_target_x=P2_MINERAL_X - 2 * TILE,
        queued_target_y=P2_MINERAL_Y - TILE,
        queued_target_uid="",
        block_mask=BM_SOLID,
        sprite=Sprite["worker"],
    )
)

scene.add_actor(
    MineralPatch(
        uid="p1_minerals_a",
        x=P1_MINERAL_X,
        y=P1_MINERAL_Y,
        w=18,
        h=18,
        owner_id="human_1",
        visible_mask=1,
        amount=RESOURCE_AMOUNT,
        per_tick=RESOURCE_PER_TICK,
        block_mask=BM_NONE,
        sprite=Sprite["mineral"],
    )
)
scene.add_actor(
    MineralPatch(
        uid="p1_minerals_b",
        x=P1_MINERAL_X + 2 * TILE,
        y=P1_MINERAL_Y - TILE,
        w=18,
        h=18,
        owner_id="human_1",
        visible_mask=1,
        amount=RESOURCE_AMOUNT,
        per_tick=RESOURCE_PER_TICK,
        block_mask=BM_NONE,
        sprite=Sprite["mineral"],
    )
)
scene.add_actor(
    MineralPatch(
        uid="p1_minerals_c",
        x=P1_MINERAL_X + TILE,
        y=P1_MINERAL_Y + 2 * TILE,
        w=18,
        h=18,
        owner_id="human_1",
        visible_mask=1,
        amount=RESOURCE_AMOUNT,
        per_tick=RESOURCE_PER_TICK,
        block_mask=BM_NONE,
        sprite=Sprite["mineral"],
    )
)
scene.add_actor(
    GasGeyser(
        uid="p1_gas_a",
        x=P1_GAS_X,
        y=P1_GAS_Y,
        w=18,
        h=18,
        owner_id="human_1",
        visible_mask=1,
        amount=RESOURCE_AMOUNT,
        per_tick=RESOURCE_PER_TICK,
        block_mask=BM_NONE,
        sprite=Sprite["gas"],
    )
)
scene.add_actor(
    GasGeyser(
        uid="p1_gas_b",
        x=P1_GAS_X + 2 * TILE,
        y=P1_GAS_Y - 2 * TILE,
        w=18,
        h=18,
        owner_id="human_1",
        visible_mask=1,
        amount=RESOURCE_AMOUNT,
        per_tick=RESOURCE_PER_TICK,
        block_mask=BM_NONE,
        sprite=Sprite["gas"],
    )
)
scene.add_actor(
    MineralPatch(
        uid="p2_minerals_a",
        x=P2_MINERAL_X,
        y=P2_MINERAL_Y,
        w=18,
        h=18,
        owner_id="human_2",
        visible_mask=2,
        amount=RESOURCE_AMOUNT,
        per_tick=RESOURCE_PER_TICK,
        block_mask=BM_NONE,
        sprite=Sprite["mineral"],
    )
)
scene.add_actor(
    MineralPatch(
        uid="p2_minerals_b",
        x=P2_MINERAL_X - 2 * TILE,
        y=P2_MINERAL_Y - TILE,
        w=18,
        h=18,
        owner_id="human_2",
        visible_mask=2,
        amount=RESOURCE_AMOUNT,
        per_tick=RESOURCE_PER_TICK,
        block_mask=BM_NONE,
        sprite=Sprite["mineral"],
    )
)
scene.add_actor(
    MineralPatch(
        uid="p2_minerals_c",
        x=P2_MINERAL_X - TILE,
        y=P2_MINERAL_Y + 2 * TILE,
        w=18,
        h=18,
        owner_id="human_2",
        visible_mask=2,
        amount=RESOURCE_AMOUNT,
        per_tick=RESOURCE_PER_TICK,
        block_mask=BM_NONE,
        sprite=Sprite["mineral"],
    )
)
scene.add_actor(
    GasGeyser(
        uid="p2_gas_a",
        x=P2_GAS_X,
        y=P2_GAS_Y,
        w=18,
        h=18,
        owner_id="human_2",
        visible_mask=2,
        amount=RESOURCE_AMOUNT,
        per_tick=RESOURCE_PER_TICK,
        block_mask=BM_NONE,
        sprite=Sprite["gas"],
    )
)
scene.add_actor(
    GasGeyser(
        uid="p2_gas_b",
        x=P2_GAS_X - 2 * TILE,
        y=P2_GAS_Y - 2 * TILE,
        w=18,
        h=18,
        owner_id="human_2",
        visible_mask=2,
        amount=RESOURCE_AMOUNT,
        per_tick=RESOURCE_PER_TICK,
        block_mask=BM_NONE,
        sprite=Sprite["gas"],
    )
)
scene.add_actor(
    MineralPatch(
        uid="mid_minerals_a",
        x=(P1_BASE_X + P2_BASE_X) / 2,
        y=P1_BASE_Y - 6 * TILE,
        w=18,
        h=18,
        owner_id="",
        visible_mask=0,
        amount=RESOURCE_AMOUNT,
        per_tick=RESOURCE_PER_TICK,
        block_mask=BM_NONE,
        sprite=Sprite["mineral"],
    )
)
scene.add_actor(
    MineralPatch(
        uid="mid_minerals_b",
        x=(P1_BASE_X + P2_BASE_X) / 2,
        y=P1_BASE_Y + 6 * TILE,
        w=18,
        h=18,
        owner_id="",
        visible_mask=0,
        amount=RESOURCE_AMOUNT,
        per_tick=RESOURCE_PER_TICK,
        block_mask=BM_NONE,
        sprite=Sprite["mineral"],
    )
)
scene.add_actor(
    GasGeyser(
        uid="mid_gas_a",
        x=(P1_BASE_X + P2_BASE_X) / 2 - 4 * TILE,
        y=P1_BASE_Y,
        w=18,
        h=18,
        owner_id="",
        visible_mask=0,
        amount=RESOURCE_AMOUNT,
        per_tick=RESOURCE_PER_TICK,
        block_mask=BM_NONE,
        sprite=Sprite["gas"],
    )
)
scene.add_actor(
    GasGeyser(
        uid="mid_gas_b",
        x=(P1_BASE_X + P2_BASE_X) / 2 + 4 * TILE,
        y=P1_BASE_Y,
        w=18,
        h=18,
        owner_id="",
        visible_mask=0,
        amount=RESOURCE_AMOUNT,
        per_tick=RESOURCE_PER_TICK,
        block_mask=BM_NONE,
        sprite=Sprite["gas"],
    )
)

CodeBlock.end("starcraft_clone_world")
