from typing import List

from nanocalibur.dsl_markers import (
    ButtonCondition,
    Camera,
    CodeBlock,
    KeyboardCondition,
    MouseCondition,
    MouseInfo,
    OnLogicalCondition,
    Scene,
    callable,
    safe_condition,
    unsafe_condition,
)

from .data import (
    PLAYER_1_ROLE_ID,
    PLAYER_2_ROLE_ID,
    DragSelectionRect,
    ResourceNode,
    RTSObject,
    SelectionMarker,
)
from .roles import RTSRole
from .shared import (
    HALF_VIEW_H_PX,
    HALF_VIEW_W_PX,
    MAP_HEIGHT_TILES,
    MAP_WIDTH_TILES,
    TILE_SIZE,
    WORLD_HEIGHT_PX,
    WORLD_WIDTH_PX,
)


CodeBlock.begin("selection_and_move_rules")
"""RTS controls: selection/pathing + timed gather/production/building/research."""

CAMERA_PAN_SPEED = 4
DRAG_SELECT_THRESHOLD_PX = 8
PHYSICS_STEP_HZ = 60
DIAGONAL_SPEED_FACTOR = 0.70710678
RESOURCE_INTERACT_RANGE = 42
RESOURCE_HARVEST_MINERAL = 8
RESOURCE_HARVEST_GAS = 6
PATH_BLOCK_SHRINK_STATIC_PX = 8
PATH_BLOCK_SHRINK_RESOURCE_PX = 8
PROGRESS_BAR_SEGMENTS = 20
BUILD_PLACEMENT_STEP_PX = 72

RESOURCE_MINE_DURATION_MINERAL_TICKS = PHYSICS_STEP_HZ * 3
RESOURCE_MINE_DURATION_GAS_TICKS = PHYSICS_STEP_HZ * 4
RESOURCE_UNLOAD_DURATION_TICKS = PHYSICS_STEP_HZ

WORKER_TRAIN_TIME_TICKS = PHYSICS_STEP_HZ * 4
WORKER_TRAIN_MINERAL_COST = 50
WORKER_TRAIN_GAS_COST = 0
WORKER_TRAIN_SUPPLY_COST = 1

BUILD_TIME_HQ_TICKS = PHYSICS_STEP_HZ * 10
BUILD_TIME_SUPPLY_DEPOT_TICKS = PHYSICS_STEP_HZ * 5
BUILD_TIME_BARRACKS_TICKS = PHYSICS_STEP_HZ * 7
BUILD_TIME_ACADEMY_TICKS = PHYSICS_STEP_HZ * 8
BUILD_TIME_STARPORT_TICKS = PHYSICS_STEP_HZ * 9

COST_HQ_MINERALS = 400
COST_HQ_GAS = 0
COST_SUPPLY_DEPOT_MINERALS = 100
COST_SUPPLY_DEPOT_GAS = 0
COST_BARRACKS_MINERALS = 150
COST_BARRACKS_GAS = 0
COST_ACADEMY_MINERALS = 150
COST_ACADEMY_GAS = 100
COST_STARPORT_MINERALS = 200
COST_STARPORT_GAS = 150
SUPPLY_DEPOT_SUPPLY_BONUS = 8

UPGRADE_TIME_ATTACK_TICKS = PHYSICS_STEP_HZ * 6
UPGRADE_TIME_ARMOR_TICKS = PHYSICS_STEP_HZ * 6
UPGRADE_COST_ATTACK_MINERALS = 100
UPGRADE_COST_ATTACK_GAS = 100
UPGRADE_COST_ARMOR_MINERALS = 100
UPGRADE_COST_ARMOR_GAS = 100
MAX_UPGRADE_LEVEL = 3


@callable
def abs_value(value: float) -> float:
    if value < 0:
        return -value
    return value


@callable
def clamp_camera_x(camera_x: float) -> float:
    if camera_x < HALF_VIEW_W_PX:
        return HALF_VIEW_W_PX
    if camera_x > WORLD_WIDTH_PX - HALF_VIEW_W_PX:
        return WORLD_WIDTH_PX - HALF_VIEW_W_PX
    return camera_x


@callable
def clamp_camera_y(camera_y: float) -> float:
    if camera_y < HALF_VIEW_H_PX:
        return HALF_VIEW_H_PX
    if camera_y > WORLD_HEIGHT_PX - HALF_VIEW_H_PX:
        return WORLD_HEIGHT_PX - HALF_VIEW_H_PX
    return camera_y


@callable
def camera_screen_to_world_x(camera_x: float, screen_x: float) -> float:
    return clamp_camera_x(camera_x) - HALF_VIEW_W_PX + screen_x


@callable
def camera_screen_to_world_y(camera_y: float, screen_y: float) -> float:
    return clamp_camera_y(camera_y) - HALF_VIEW_H_PX + screen_y


@callable
def is_drag_select(
    pressed_x: float,
    pressed_y: float,
    current_x: float,
    current_y: float,
) -> bool:
    return (
        abs_value(current_x - pressed_x) >= DRAG_SELECT_THRESHOLD_PX
        or abs_value(current_y - pressed_y) >= DRAG_SELECT_THRESHOLD_PX
    )


@callable
def world_to_tile_x(world_x: float) -> int:
    safe_x = world_x
    if safe_x < 0:
        safe_x = 0
    if safe_x > WORLD_WIDTH_PX - 1:
        safe_x = WORLD_WIDTH_PX - 1
    tile_x = 0
    edge_x = TILE_SIZE
    while edge_x <= safe_x and tile_x < MAP_WIDTH_TILES - 1:
        tile_x = tile_x + 1
        edge_x = edge_x + TILE_SIZE
    return tile_x


@callable
def world_to_tile_y(world_y: float) -> int:
    safe_y = world_y
    if safe_y < 0:
        safe_y = 0
    if safe_y > WORLD_HEIGHT_PX - 1:
        safe_y = WORLD_HEIGHT_PX - 1
    tile_y = 0
    edge_y = TILE_SIZE
    while edge_y <= safe_y and tile_y < MAP_HEIGHT_TILES - 1:
        tile_y = tile_y + 1
        edge_y = edge_y + TILE_SIZE
    return tile_y


@callable
def tile_center_x(tile_x: int) -> float:
    return (tile_x * TILE_SIZE) + (TILE_SIZE / 2)


@callable
def tile_center_y(tile_y: int) -> float:
    return (tile_y * TILE_SIZE) + (TILE_SIZE / 2)


@callable
def tile_node(tile_x: int, tile_y: int) -> int:
    return (tile_y * MAP_WIDTH_TILES) + tile_x


@callable
def mark_path_block_for_box(
    blocked_by_objects: dict,
    center_x: float,
    center_y: float,
    box_w: float,
    box_h: float,
    shrink_px: int,
):
    half_w = (box_w / 2) - shrink_px
    half_h = (box_h / 2) - shrink_px
    if half_w < 1:
        half_w = 1
    if half_h < 1:
        half_h = 1

    left_world = center_x - half_w + 1
    right_world = center_x + half_w - 1
    top_world = center_y - half_h + 1
    bottom_world = center_y + half_h - 1

    min_tile_x = world_to_tile_x(left_world)
    max_tile_x = world_to_tile_x(right_world)
    min_tile_y = world_to_tile_y(top_world)
    max_tile_y = world_to_tile_y(bottom_world)

    for block_tile_y in range(min_tile_y, max_tile_y + 1):
        for block_tile_x in range(min_tile_x, max_tile_x + 1):
            blocked_node = tile_node(block_tile_x, block_tile_y)
            blocked_by_objects[blocked_node] = 1


@callable
def node_to_tile_x(node: int) -> int:
    x = node
    while x >= MAP_WIDTH_TILES:
        x = x - MAP_WIDTH_TILES
    return x


@callable
def node_to_tile_y(node: int) -> int:
    y = 0
    remaining = node
    while remaining >= MAP_WIDTH_TILES:
        remaining = remaining - MAP_WIDTH_TILES
        y = y + 1
    return y


@callable
def is_static_blocked_tile(tile_x: int, tile_y: int) -> bool:
    if tile_x < 0 or tile_y < 0:
        return True
    if tile_x >= MAP_WIDTH_TILES or tile_y >= MAP_HEIGHT_TILES:
        return True

    if tile_x == 0 or tile_y == 0 or tile_x == MAP_WIDTH_TILES - 1 or tile_y == MAP_HEIGHT_TILES - 1:
        return True

    if tile_x >= 46 and tile_x <= 49 and tile_y >= 8 and tile_y <= 63:
        if tile_y < 31 or tile_y > 40:
            return True

    if tile_y >= 34 and tile_y <= 37 and tile_x >= 8 and tile_x <= 87:
        if tile_x < 43 or tile_x > 52:
            return True

    if tile_x >= 12 and tile_x <= 20 and tile_y >= 12 and tile_y <= 20:
        return True

    if tile_x >= 74 and tile_x <= 82 and tile_y >= 50 and tile_y <= 58:
        return True

    if tile_x >= 16 and tile_x <= 23 and tile_y >= 50 and tile_y <= 66:
        return True

    if tile_x >= 72 and tile_x <= 79 and tile_y >= 6 and tile_y <= 22:
        return True

    return False


@callable
def is_path_blocked_tile(
    tile_x: int,
    tile_y: int,
    blocked_by_objects: dict,
    goal_node: int,
) -> bool:
    if is_static_blocked_tile(tile_x, tile_y):
        return True
    node = tile_node(tile_x, tile_y)
    return blocked_by_objects.get(node, 0) == 1 and node != goal_node


@callable
def is_diagonal_corner_blocked(
    current_tile_x: int,
    current_tile_y: int,
    neighbor_tile_x: int,
    neighbor_tile_y: int,
    blocked_by_objects: dict,
) -> bool:
    side_a_x = current_tile_x
    side_a_y = neighbor_tile_y
    side_b_x = neighbor_tile_x
    side_b_y = current_tile_y

    if is_static_blocked_tile(side_a_x, side_a_y):
        return True
    if is_static_blocked_tile(side_b_x, side_b_y):
        return True
    if blocked_by_objects.get(tile_node(side_a_x, side_a_y), 0) == 1:
        return True
    if blocked_by_objects.get(tile_node(side_b_x, side_b_y), 0) == 1:
        return True
    return False


@callable
def clear_move_path(unit: RTSObject):
    unit.path_tiles_x = []
    unit.path_tiles_y = []
    unit.path_cursor = 0
    unit.path_len = 0
    unit.path_active = False
    unit.vx = 0
    unit.vy = 0


@callable
def squared_distance(x1: float, y1: float, x2: float, y2: float) -> float:
    dx = x2 - x1
    dy = y2 - y1
    return (dx * dx) + (dy * dy)


@callable
def squared_distance_to_box(
    point_x: float,
    point_y: float,
    box_center_x: float,
    box_center_y: float,
    box_w: float,
    box_h: float,
) -> float:
    dx = abs_value(point_x - box_center_x) - (box_w / 2)
    dy = abs_value(point_y - box_center_y) - (box_h / 2)

    if dx < 0:
        dx = 0
    if dy < 0:
        dy = 0

    return (dx * dx) + (dy * dy)


@callable
def project_point_to_box_x(
    point_x: float,
    point_y: float,
    box_center_x: float,
    box_center_y: float,
    box_w: float,
    box_h: float,
) -> float:
    left = box_center_x - (box_w / 2)
    right = box_center_x + (box_w / 2)
    top = box_center_y - (box_h / 2)
    bottom = box_center_y + (box_h / 2)

    projected_x = point_x
    if projected_x < left:
        projected_x = left
    if projected_x > right:
        projected_x = right

    projected_y = point_y
    if projected_y < top:
        projected_y = top
    if projected_y > bottom:
        projected_y = bottom

    if (
        point_x >= left
        and point_x <= right
        and point_y >= top
        and point_y <= bottom
    ):
        dist_left = abs_value(point_x - left)
        dist_right = abs_value(right - point_x)
        dist_top = abs_value(point_y - top)
        dist_bottom = abs_value(bottom - point_y)
        best = dist_left
        projected_x = left
        if dist_right < best:
            best = dist_right
            projected_x = right
        if dist_top < best:
            best = dist_top
            projected_x = point_x
        if dist_bottom < best:
            projected_x = point_x
    elif point_x < left and point_y >= top and point_y <= bottom:
        projected_x = left
    elif point_x > right and point_y >= top and point_y <= bottom:
        projected_x = right
    elif point_y < top and point_x >= left and point_x <= right:
        projected_x = point_x
    elif point_y > bottom and point_x >= left and point_x <= right:
        projected_x = point_x
    else:
        projected_x = projected_x

    return projected_x


@callable
def project_point_to_box_y(
    point_x: float,
    point_y: float,
    box_center_x: float,
    box_center_y: float,
    box_w: float,
    box_h: float,
) -> float:
    left = box_center_x - (box_w / 2)
    right = box_center_x + (box_w / 2)
    top = box_center_y - (box_h / 2)
    bottom = box_center_y + (box_h / 2)

    projected_x = point_x
    if projected_x < left:
        projected_x = left
    if projected_x > right:
        projected_x = right

    projected_y = point_y
    if projected_y < top:
        projected_y = top
    if projected_y > bottom:
        projected_y = bottom

    if (
        point_x >= left
        and point_x <= right
        and point_y >= top
        and point_y <= bottom
    ):
        dist_left = abs_value(point_x - left)
        dist_right = abs_value(right - point_x)
        dist_top = abs_value(point_y - top)
        dist_bottom = abs_value(bottom - point_y)
        best = dist_left
        projected_y = point_y
        if dist_right < best:
            best = dist_right
            projected_y = point_y
        if dist_top < best:
            best = dist_top
            projected_y = top
        if dist_bottom < best:
            projected_y = bottom
    elif point_x < left and point_y >= top and point_y <= bottom:
        projected_y = point_y
    elif point_x > right and point_y >= top and point_y <= bottom:
        projected_y = point_y
    elif point_y < top and point_x >= left and point_x <= right:
        projected_y = top
    elif point_y > bottom and point_x >= left and point_x <= right:
        projected_y = bottom
    else:
        projected_y = projected_y

    return projected_y


@callable
def clamp_world_x_for_size(world_x: float, object_w: float) -> float:
    half_w = object_w / 2
    min_x = half_w
    max_x = WORLD_WIDTH_PX - half_w
    clamped = world_x
    if clamped < min_x:
        clamped = min_x
    if clamped > max_x:
        clamped = max_x
    return clamped


@callable
def clamp_world_y_for_size(world_y: float, object_h: float) -> float:
    half_h = object_h / 2
    min_y = half_h
    max_y = WORLD_HEIGHT_PX - half_h
    clamped = world_y
    if clamped < min_y:
        clamped = min_y
    if clamped > max_y:
        clamped = max_y
    return clamped


@callable
def clear_object_task(obj: RTSObject):
    obj.task_active = False
    obj.task_kind = ""
    obj.task_label = ""
    obj.task_elapsed_ticks = 0
    obj.task_total_ticks = 0
    obj.task_build_kind = ""
    obj.task_build_x = 0
    obj.task_build_y = 0
    obj.task_resource_kind = ""
    obj.task_resource_amount = 0


@callable
def start_object_task(obj: RTSObject, task_kind: str, task_label: str, total_ticks: int):
    if total_ticks <= 0:
        total_ticks = 1
    obj.task_active = True
    obj.task_kind = task_kind
    obj.task_label = task_label
    obj.task_elapsed_ticks = 0
    obj.task_total_ticks = total_ticks
    obj.task_build_kind = ""
    obj.task_build_x = 0
    obj.task_build_y = 0
    obj.task_resource_kind = ""
    obj.task_resource_amount = 0


@callable
def is_worker_gather_task(task_kind: str) -> bool:
    return task_kind == "gather_harvest" or task_kind == "gather_unload"


@callable
def task_progress_percent(obj: RTSObject) -> float:
    if obj.task_active == False:
        return 0
    if obj.task_total_ticks <= 0:
        return 0
    value = (obj.task_elapsed_ticks * 100.0) / obj.task_total_ticks
    if value < 0:
        return 0
    if value > 100:
        return 100
    return value


@callable
def build_progress_bar(percent: float) -> str:
    if percent < 0:
        percent = 0
    if percent > 100:
        percent = 100
    threshold = 100.0 / PROGRESS_BAR_SEGMENTS
    filled = 0
    while filled < PROGRESS_BAR_SEGMENTS:
        if ((filled + 1) * threshold) <= percent:
            filled = filled + 1
        else:
            break

    bar = "["
    idx = 0
    while idx < PROGRESS_BAR_SEGMENTS:
        if idx < filled:
            bar = bar + "#"
        else:
            bar = bar + "."
        idx = idx + 1
    bar = bar + "]"
    return bar


@callable
def object_kind_name(object_kind: str) -> str:
    if object_kind == "hq":
        return "HQ"
    if object_kind == "worker":
        return "Worker"
    if object_kind == "supply_depot":
        return "Supply Depot"
    if object_kind == "barracks":
        return "Barracks"
    if object_kind == "academy":
        return "Academy"
    if object_kind == "starport":
        return "Starport"
    return object_kind


@callable
def object_kind_w(object_kind: str) -> int:
    if object_kind == "worker":
        return 20
    if object_kind == "hq":
        return 64
    if object_kind == "supply_depot":
        return 48
    if object_kind == "barracks":
        return 56
    if object_kind == "academy":
        return 54
    if object_kind == "starport":
        return 60
    return 48


@callable
def object_kind_h(object_kind: str) -> int:
    return object_kind_w(object_kind)


@callable
def object_kind_hp(object_kind: str) -> int:
    if object_kind == "worker":
        return 45
    if object_kind == "hq":
        return 1500
    if object_kind == "supply_depot":
        return 500
    if object_kind == "barracks":
        return 1000
    if object_kind == "academy":
        return 700
    if object_kind == "starport":
        return 1100
    return 500


@callable
def object_kind_mineral_cost(object_kind: str) -> int:
    if object_kind == "worker":
        return WORKER_TRAIN_MINERAL_COST
    if object_kind == "hq":
        return COST_HQ_MINERALS
    if object_kind == "supply_depot":
        return COST_SUPPLY_DEPOT_MINERALS
    if object_kind == "barracks":
        return COST_BARRACKS_MINERALS
    if object_kind == "academy":
        return COST_ACADEMY_MINERALS
    if object_kind == "starport":
        return COST_STARPORT_MINERALS
    return 0


@callable
def object_kind_gas_cost(object_kind: str) -> int:
    if object_kind == "worker":
        return WORKER_TRAIN_GAS_COST
    if object_kind == "hq":
        return COST_HQ_GAS
    if object_kind == "supply_depot":
        return COST_SUPPLY_DEPOT_GAS
    if object_kind == "barracks":
        return COST_BARRACKS_GAS
    if object_kind == "academy":
        return COST_ACADEMY_GAS
    if object_kind == "starport":
        return COST_STARPORT_GAS
    return 0


@callable
def object_kind_sprite(object_kind: str, team_id: int) -> str:
    if object_kind == "worker":
        if team_id == 1:
            return "worker_p1"
        return "worker_p2"
    if object_kind == "hq":
        if team_id == 1:
            return "hq_p1"
        return "hq_p2"
    if object_kind == "supply_depot":
        if team_id == 1:
            return "supply_depot_p1"
        return "supply_depot_p2"
    if object_kind == "barracks":
        if team_id == 1:
            return "barracks_p1"
        return "barracks_p2"
    if object_kind == "academy":
        if team_id == 1:
            return "academy_p1"
        return "academy_p2"
    if object_kind == "starport":
        if team_id == 1:
            return "starport_p1"
        return "starport_p2"
    if team_id == 1:
        return "worker_p1"
    return "worker_p2"


@callable
def build_kind_time_ticks(build_kind: str) -> int:
    if build_kind == "hq":
        return BUILD_TIME_HQ_TICKS
    if build_kind == "supply_depot":
        return BUILD_TIME_SUPPLY_DEPOT_TICKS
    if build_kind == "barracks":
        return BUILD_TIME_BARRACKS_TICKS
    if build_kind == "academy":
        return BUILD_TIME_ACADEMY_TICKS
    if build_kind == "starport":
        return BUILD_TIME_STARPORT_TICKS
    return PHYSICS_STEP_HZ * 5


@callable
def has_owned_object_kind(owner_role_id: str, objects: List[RTSObject], object_kind: str) -> bool:
    for obj in objects:
        if obj.active == False:
            continue
        if obj.owner_role_id != owner_role_id:
            continue
        if obj.object_kind != object_kind:
            continue
        return True
    return False


@callable
def count_owned_object_kind(owner_role_id: str, objects: List[RTSObject], object_kind: str) -> int:
    count = 0
    for obj in objects:
        if obj.active == False:
            continue
        if obj.owner_role_id != owner_role_id:
            continue
        if obj.object_kind != object_kind:
            continue
        count = count + 1
    return count


@callable
def build_requirement_text(build_kind: str) -> str:
    if build_kind == "barracks":
        return "Supply Depot required."
    if build_kind == "academy":
        return "Barracks required."
    if build_kind == "starport":
        return "Barracks and Academy required."
    return ""


@callable
def has_build_requirements(owner_role_id: str, objects: List[RTSObject], build_kind: str) -> bool:
    if build_kind == "barracks":
        return has_owned_object_kind(owner_role_id, objects, "supply_depot")
    if build_kind == "academy":
        return has_owned_object_kind(owner_role_id, objects, "barracks")
    if build_kind == "starport":
        return (
            has_owned_object_kind(owner_role_id, objects, "barracks")
            and has_owned_object_kind(owner_role_id, objects, "academy")
        )
    return True


@callable
def can_afford(role: RTSRole, mineral_cost: int, gas_cost: int) -> bool:
    return role.minerals >= mineral_cost and role.gas >= gas_cost


@callable
def compute_build_target_x(
    worker: RTSObject,
    owner_role_id: str,
    objects: List[RTSObject],
    build_kind: str,
) -> float:
    base_offset_x = 96
    if build_kind == "hq":
        base_offset_x = 128
    if build_kind == "starport":
        base_offset_x = 160

    existing_count = count_owned_object_kind(owner_role_id, objects, build_kind)
    column = existing_count
    while column >= 4:
        column = column - 4
    target_x = worker.x + base_offset_x + (column * BUILD_PLACEMENT_STEP_PX)
    return clamp_world_x_for_size(target_x, object_kind_w(build_kind))


@callable
def compute_build_target_y(
    worker: RTSObject,
    owner_role_id: str,
    objects: List[RTSObject],
    build_kind: str,
) -> float:
    base_offset_y = 0
    if build_kind == "hq":
        base_offset_y = 128
    if build_kind == "supply_depot":
        base_offset_y = -72
    if build_kind == "barracks":
        base_offset_y = 72
    if build_kind == "academy":
        base_offset_y = 144
    if build_kind == "starport":
        base_offset_y = -144

    existing_count = count_owned_object_kind(owner_role_id, objects, build_kind)
    row = 0
    while existing_count >= 4:
        existing_count = existing_count - 4
        row = row + 1
    target_y = worker.y + base_offset_y + (row * BUILD_PLACEMENT_STEP_PX)
    return clamp_world_y_for_size(target_y, object_kind_h(build_kind))


@callable
def start_hq_worker_training(hq: RTSObject):
    start_object_task(hq, "train_worker", "Training Worker", WORKER_TRAIN_TIME_TICKS)


@callable
def start_worker_build_task(
    worker: RTSObject,
    owner_role_id: str,
    objects: List[RTSObject],
    build_kind: str,
):
    task_label = "Building " + object_kind_name(build_kind)
    start_object_task(worker, "build_structure", task_label, build_kind_time_ticks(build_kind))
    worker.task_build_kind = build_kind
    worker.task_build_x = compute_build_target_x(worker, owner_role_id, objects, build_kind)
    worker.task_build_y = compute_build_target_y(worker, owner_role_id, objects, build_kind)


@callable
def start_academy_research_task(academy: RTSObject, research_kind: str):
    if research_kind == "attack":
        start_object_task(
            academy,
            "research_attack",
            "Researching Attack Upgrade",
            UPGRADE_TIME_ATTACK_TICKS,
        )
    else:
        start_object_task(
            academy,
            "research_armor",
            "Researching Armor Upgrade",
            UPGRADE_TIME_ARMOR_TICKS,
        )


@callable
def spawn_worker_from_hq(scene: Scene, hq: RTSObject):
    spawn_x = clamp_world_x_for_size(hq.x + (hq.w / 2) + 24, object_kind_w("worker"))
    spawn_y = clamp_world_y_for_size(hq.y + (hq.h / 2) + 24, object_kind_h("worker"))
    sprite_name = object_kind_sprite("worker", hq.team_id)
    scene.spawn(
        RTSObject(
            x=spawn_x,
            y=spawn_y,
            w=object_kind_w("worker"),
            h=object_kind_h("worker"),
            z=3,
            block_mask=1,
            owner_role_id=hq.owner_role_id,
            team_id=hq.team_id,
            object_kind="worker",
            can_move=True,
            max_hp=object_kind_hp("worker"),
            hp=object_kind_hp("worker"),
            mineral_cost=object_kind_mineral_cost("worker"),
            gas_cost=object_kind_gas_cost("worker"),
            supply_cost=1,
            selection_name=object_kind_name("worker"),
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
            task_active=False,
            task_kind="",
            task_label="",
            task_elapsed_ticks=0,
            task_total_ticks=0,
            task_build_kind="",
            task_build_x=0,
            task_build_y=0,
            task_resource_kind="",
            task_resource_amount=0,
            sprite=sprite_name,
        )
    )


@callable
def spawn_completed_structure(
    scene: Scene,
    owner_role_id: str,
    team_id: int,
    build_kind: str,
    spawn_x: float,
    spawn_y: float,
):
    scene.spawn(
        RTSObject(
            x=spawn_x,
            y=spawn_y,
            w=object_kind_w(build_kind),
            h=object_kind_h(build_kind),
            z=2,
            block_mask=1,
            owner_role_id=owner_role_id,
            team_id=team_id,
            object_kind=build_kind,
            can_move=False,
            max_hp=object_kind_hp(build_kind),
            hp=object_kind_hp(build_kind),
            mineral_cost=object_kind_mineral_cost(build_kind),
            gas_cost=object_kind_gas_cost(build_kind),
            supply_cost=0,
            selection_name=object_kind_name(build_kind),
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
            task_active=False,
            task_kind="",
            task_label="",
            task_elapsed_ticks=0,
            task_total_ticks=0,
            task_build_kind="",
            task_build_x=0,
            task_build_y=0,
            task_resource_kind="",
            task_resource_amount=0,
            sprite=object_kind_sprite(build_kind, team_id),
        )
    )


def should_process_timed_object_tasks(obj: RTSObject) -> bool:
    return (
        obj.active
        and obj.task_active
        and (
            obj.task_kind == "train_worker"
            or obj.task_kind == "build_structure"
            or obj.task_kind == "research_attack"
            or obj.task_kind == "research_armor"
        )
    )


@callable
def process_timed_object_task(
    obj: RTSObject,
    role: RTSRole,
    owner_role_id: str,
    scene: Scene,
):
    if obj.owner_role_id != owner_role_id:
        return
    if obj.task_active == False:
        return

    obj.task_elapsed_ticks = obj.task_elapsed_ticks + 1
    if obj.task_elapsed_ticks < obj.task_total_ticks:
        return

    finished_task = obj.task_kind
    finished_build_kind = obj.task_build_kind
    finished_build_x = obj.task_build_x
    finished_build_y = obj.task_build_y
    clear_object_task(obj)

    if finished_task == "train_worker":
        spawn_worker_from_hq(scene, obj)
        role.supply_used = role.supply_used + WORKER_TRAIN_SUPPLY_COST
        role.ui_status = "Worker ready."
        return

    if finished_task == "build_structure":
        spawn_completed_structure(
            scene,
            obj.owner_role_id,
            obj.team_id,
            finished_build_kind,
            finished_build_x,
            finished_build_y,
        )
        role.ui_status = object_kind_name(finished_build_kind) + " complete."
        if finished_build_kind == "supply_depot":
            role.supply_cap = role.supply_cap + SUPPLY_DEPOT_SUPPLY_BONUS
        return

    if finished_task == "research_attack":
        role.attack_upgrade_level = role.attack_upgrade_level + 1
        role.ui_status = "Attack upgrade complete."
        return

    if finished_task == "research_armor":
        role.armor_upgrade_level = role.armor_upgrade_level + 1
        role.ui_status = "Armor upgrade complete."
        return


@safe_condition(OnLogicalCondition(should_process_timed_object_tasks, RTSObject))
def process_timed_tasks_for_human_1(
    obj: RTSObject,
    role: RTSRole["human_1"],
    scene: Scene,
):
    process_timed_object_task(obj, role, PLAYER_1_ROLE_ID, scene)


@safe_condition(OnLogicalCondition(should_process_timed_object_tasks, RTSObject))
def process_timed_tasks_for_human_2(
    obj: RTSObject,
    role: RTSRole["human_2"],
    scene: Scene,
):
    process_timed_object_task(obj, role, PLAYER_2_ROLE_ID, scene)


@callable
def clear_worker_gather_loop(worker: RTSObject):
    worker.gather_active = False
    worker.gather_phase = ""
    worker.gather_resource_uid = ""
    worker.gather_hq_uid = ""
    worker.carrying_kind = ""
    worker.carrying_amount = 0
    if is_worker_gather_task(worker.task_kind):
        clear_object_task(worker)
    clear_move_path(worker)


@callable
def find_closest_hq_uid(owner_role_id: str, worker: RTSObject, objects: List[RTSObject]) -> str:
    closest_hq_uid = ""
    closest_dist_sq = 999999999999.0
    for obj in objects:
        if obj.active == False:
            continue
        if obj.owner_role_id != owner_role_id:
            continue
        if obj.object_kind != "hq":
            continue

        dist_sq = squared_distance(worker.x, worker.y, obj.x, obj.y)
        if dist_sq < closest_dist_sq:
            closest_hq_uid = obj.uid
            closest_dist_sq = dist_sq
    return closest_hq_uid


@callable
def find_clicked_resource_uid(
    target_world_x: float,
    target_world_y: float,
    resources: List[ResourceNode],
) -> str:
    clicked_uid = ""
    clicked_z = -999999
    for resource in resources:
        if resource.active == False:
            continue
        if resource.amount <= 0:
            continue

        half_w = resource.w / 2
        half_h = resource.h / 2
        inside = (
            target_world_x >= resource.x - half_w
            and target_world_x <= resource.x + half_w
            and target_world_y >= resource.y - half_h
            and target_world_y <= resource.y + half_h
        )
        if not inside:
            continue
        if resource.z < clicked_z:
            continue

        clicked_uid = resource.uid
        clicked_z = resource.z
    return clicked_uid


@callable
def start_worker_gather_loop(
    worker: RTSObject,
    objects: List[RTSObject],
    resources: List[ResourceNode],
    resource_uid: str,
):
    if worker.task_active and is_worker_gather_task(worker.task_kind) == False:
        return
    if is_worker_gather_task(worker.task_kind):
        clear_object_task(worker)

    target_resource_x = 0
    target_resource_y = 0
    found_resource = False

    for resource in resources:
        if resource.active == False:
            continue
        if resource.uid != resource_uid:
            continue
        if resource.amount <= 0:
            continue
        target_resource_x = resource.x
        target_resource_y = resource.y
        found_resource = True

    if not found_resource:
        clear_worker_gather_loop(worker)
        return

    nearest_hq_uid = find_closest_hq_uid(worker.owner_role_id, worker, objects)
    if nearest_hq_uid == "":
        clear_worker_gather_loop(worker)
        return

    worker.gather_active = True
    worker.gather_phase = "to_resource"
    worker.gather_resource_uid = resource_uid
    worker.gather_hq_uid = nearest_hq_uid
    worker.carrying_kind = ""
    worker.carrying_amount = 0
    build_worker_path(worker, objects, resources, target_resource_x, target_resource_y)


@callable
def build_worker_path(
    unit: RTSObject,
    objects: List[RTSObject],
    resources: List[ResourceNode],
    goal_world_x: float,
    goal_world_y: float,
):
    clear_move_path(unit)

    start_tile_x = world_to_tile_x(unit.x)
    start_tile_y = world_to_tile_y(unit.y)
    goal_tile_x = world_to_tile_x(goal_world_x)
    goal_tile_y = world_to_tile_y(goal_world_y)

    if is_static_blocked_tile(goal_tile_x, goal_tile_y):
        return

    start_node = tile_node(start_tile_x, start_tile_y)
    goal_node = tile_node(goal_tile_x, goal_tile_y)
    if start_node == goal_node:
        return

    blocked_by_objects = {}
    for obj in objects:
        if obj.active == False:
            continue
        if obj.uid == unit.uid:
            continue

        block_shrink_px = 0
        if obj.can_move == False:
            block_shrink_px = PATH_BLOCK_SHRINK_STATIC_PX

        mark_path_block_for_box(
            blocked_by_objects,
            obj.x,
            obj.y,
            obj.w,
            obj.h,
            block_shrink_px,
        )

    for resource in resources:
        if resource.active == False:
            continue

        mark_path_block_for_box(
            blocked_by_objects,
            resource.x,
            resource.y,
            resource.w,
            resource.h,
            PATH_BLOCK_SHRINK_RESOURCE_PX,
        )

    if blocked_by_objects.get(goal_node, 0) == 1:
        found_open_goal = False
        best_goal_tile_x = goal_tile_x
        best_goal_tile_y = goal_tile_y
        best_goal_node = goal_node
        for search_radius in range(1, 10):
            if found_open_goal:
                continue
            found_candidate_in_ring = False
            best_ring_goal_dist_sq = 999999999
            best_ring_start_dist_sq = 999999999
            min_search_x = goal_tile_x - search_radius
            max_search_x = goal_tile_x + search_radius
            min_search_y = goal_tile_y - search_radius
            max_search_y = goal_tile_y + search_radius

            for candidate_tile_y in range(min_search_y, max_search_y + 1):
                for candidate_tile_x in range(min_search_x, max_search_x + 1):
                    if (
                        candidate_tile_x < 0
                        or candidate_tile_y < 0
                        or candidate_tile_x >= MAP_WIDTH_TILES
                        or candidate_tile_y >= MAP_HEIGHT_TILES
                    ):
                        continue

                    is_border_of_ring = (
                        candidate_tile_x == min_search_x
                        or candidate_tile_x == max_search_x
                        or candidate_tile_y == min_search_y
                        or candidate_tile_y == max_search_y
                    )
                    if not is_border_of_ring:
                        continue

                    candidate_node = tile_node(candidate_tile_x, candidate_tile_y)
                    if is_static_blocked_tile(candidate_tile_x, candidate_tile_y):
                        continue
                    if blocked_by_objects.get(candidate_node, 0) == 1:
                        continue

                    goal_dx = candidate_tile_x - goal_tile_x
                    goal_dy = candidate_tile_y - goal_tile_y
                    goal_dist_sq = (goal_dx * goal_dx) + (goal_dy * goal_dy)

                    start_dx = candidate_tile_x - start_tile_x
                    start_dy = candidate_tile_y - start_tile_y
                    start_dist_sq = (start_dx * start_dx) + (start_dy * start_dy)

                    better_candidate = False
                    if not found_candidate_in_ring:
                        better_candidate = True
                    elif goal_dist_sq < best_ring_goal_dist_sq:
                        better_candidate = True
                    elif (
                        goal_dist_sq == best_ring_goal_dist_sq
                        and start_dist_sq < best_ring_start_dist_sq
                    ):
                        better_candidate = True

                    if better_candidate:
                        found_candidate_in_ring = True
                        best_ring_goal_dist_sq = goal_dist_sq
                        best_ring_start_dist_sq = start_dist_sq
                        best_goal_tile_x = candidate_tile_x
                        best_goal_tile_y = candidate_tile_y
                        best_goal_node = candidate_node

            if found_candidate_in_ring:
                found_open_goal = True
                goal_tile_x = best_goal_tile_x
                goal_tile_y = best_goal_tile_y
                goal_node = best_goal_node

        if not found_open_goal:
            return

    frontier_nodes = [start_node]
    frontier_size = 1
    frontier_head = 0

    visited = {}
    visited[start_node] = 1
    came_from = {}

    found_goal = False
    max_search_steps = MAP_WIDTH_TILES * MAP_HEIGHT_TILES
    search_steps = 0

    while frontier_head < frontier_size and search_steps < max_search_steps:
        current_node = frontier_nodes[frontier_head]
        frontier_head = frontier_head + 1
        search_steps = search_steps + 1

        if current_node == goal_node:
            found_goal = True
            frontier_head = frontier_size
        else:
            current_tile_x = node_to_tile_x(current_node)
            current_tile_y = node_to_tile_y(current_node)

            neighbor_tile_x = current_tile_x + 1
            neighbor_tile_y = current_tile_y
            if neighbor_tile_x >= 0 and neighbor_tile_x < MAP_WIDTH_TILES:
                neighbor_node = tile_node(neighbor_tile_x, neighbor_tile_y)
                if visited.get(neighbor_node, 0) == 0:
                    if not is_path_blocked_tile(
                        neighbor_tile_x,
                        neighbor_tile_y,
                        blocked_by_objects,
                        goal_node,
                    ):
                        visited[neighbor_node] = 1
                        came_from[neighbor_node] = current_node
                        frontier_nodes.append(neighbor_node)
                        frontier_size = frontier_size + 1

            neighbor_tile_x = current_tile_x - 1
            neighbor_tile_y = current_tile_y
            if neighbor_tile_x >= 0 and neighbor_tile_x < MAP_WIDTH_TILES:
                neighbor_node = tile_node(neighbor_tile_x, neighbor_tile_y)
                if visited.get(neighbor_node, 0) == 0:
                    if not is_path_blocked_tile(
                        neighbor_tile_x,
                        neighbor_tile_y,
                        blocked_by_objects,
                        goal_node,
                    ):
                        visited[neighbor_node] = 1
                        came_from[neighbor_node] = current_node
                        frontier_nodes.append(neighbor_node)
                        frontier_size = frontier_size + 1

            neighbor_tile_x = current_tile_x
            neighbor_tile_y = current_tile_y + 1
            if neighbor_tile_y >= 0 and neighbor_tile_y < MAP_HEIGHT_TILES:
                neighbor_node = tile_node(neighbor_tile_x, neighbor_tile_y)
                if visited.get(neighbor_node, 0) == 0:
                    if not is_path_blocked_tile(
                        neighbor_tile_x,
                        neighbor_tile_y,
                        blocked_by_objects,
                        goal_node,
                    ):
                        visited[neighbor_node] = 1
                        came_from[neighbor_node] = current_node
                        frontier_nodes.append(neighbor_node)
                        frontier_size = frontier_size + 1

            neighbor_tile_x = current_tile_x
            neighbor_tile_y = current_tile_y - 1
            if neighbor_tile_y >= 0 and neighbor_tile_y < MAP_HEIGHT_TILES:
                neighbor_node = tile_node(neighbor_tile_x, neighbor_tile_y)
                if visited.get(neighbor_node, 0) == 0:
                    if not is_path_blocked_tile(
                        neighbor_tile_x,
                        neighbor_tile_y,
                        blocked_by_objects,
                        goal_node,
                    ):
                        visited[neighbor_node] = 1
                        came_from[neighbor_node] = current_node
                        frontier_nodes.append(neighbor_node)
                        frontier_size = frontier_size + 1

            neighbor_tile_x = current_tile_x + 1
            neighbor_tile_y = current_tile_y + 1
            if (
                neighbor_tile_x >= 0
                and neighbor_tile_x < MAP_WIDTH_TILES
                and neighbor_tile_y >= 0
                and neighbor_tile_y < MAP_HEIGHT_TILES
            ):
                neighbor_node = tile_node(neighbor_tile_x, neighbor_tile_y)
                if visited.get(neighbor_node, 0) == 0:
                    if (
                        not is_diagonal_corner_blocked(
                            current_tile_x,
                            current_tile_y,
                            neighbor_tile_x,
                            neighbor_tile_y,
                            blocked_by_objects,
                        )
                        and not is_path_blocked_tile(
                            neighbor_tile_x,
                            neighbor_tile_y,
                            blocked_by_objects,
                            goal_node,
                        )
                    ):
                        visited[neighbor_node] = 1
                        came_from[neighbor_node] = current_node
                        frontier_nodes.append(neighbor_node)
                        frontier_size = frontier_size + 1

            neighbor_tile_x = current_tile_x + 1
            neighbor_tile_y = current_tile_y - 1
            if (
                neighbor_tile_x >= 0
                and neighbor_tile_x < MAP_WIDTH_TILES
                and neighbor_tile_y >= 0
                and neighbor_tile_y < MAP_HEIGHT_TILES
            ):
                neighbor_node = tile_node(neighbor_tile_x, neighbor_tile_y)
                if visited.get(neighbor_node, 0) == 0:
                    if (
                        not is_diagonal_corner_blocked(
                            current_tile_x,
                            current_tile_y,
                            neighbor_tile_x,
                            neighbor_tile_y,
                            blocked_by_objects,
                        )
                        and not is_path_blocked_tile(
                            neighbor_tile_x,
                            neighbor_tile_y,
                            blocked_by_objects,
                            goal_node,
                        )
                    ):
                        visited[neighbor_node] = 1
                        came_from[neighbor_node] = current_node
                        frontier_nodes.append(neighbor_node)
                        frontier_size = frontier_size + 1

            neighbor_tile_x = current_tile_x - 1
            neighbor_tile_y = current_tile_y + 1
            if (
                neighbor_tile_x >= 0
                and neighbor_tile_x < MAP_WIDTH_TILES
                and neighbor_tile_y >= 0
                and neighbor_tile_y < MAP_HEIGHT_TILES
            ):
                neighbor_node = tile_node(neighbor_tile_x, neighbor_tile_y)
                if visited.get(neighbor_node, 0) == 0:
                    if (
                        not is_diagonal_corner_blocked(
                            current_tile_x,
                            current_tile_y,
                            neighbor_tile_x,
                            neighbor_tile_y,
                            blocked_by_objects,
                        )
                        and not is_path_blocked_tile(
                            neighbor_tile_x,
                            neighbor_tile_y,
                            blocked_by_objects,
                            goal_node,
                        )
                    ):
                        visited[neighbor_node] = 1
                        came_from[neighbor_node] = current_node
                        frontier_nodes.append(neighbor_node)
                        frontier_size = frontier_size + 1

            neighbor_tile_x = current_tile_x - 1
            neighbor_tile_y = current_tile_y - 1
            if (
                neighbor_tile_x >= 0
                and neighbor_tile_x < MAP_WIDTH_TILES
                and neighbor_tile_y >= 0
                and neighbor_tile_y < MAP_HEIGHT_TILES
            ):
                neighbor_node = tile_node(neighbor_tile_x, neighbor_tile_y)
                if visited.get(neighbor_node, 0) == 0:
                    if (
                        not is_diagonal_corner_blocked(
                            current_tile_x,
                            current_tile_y,
                            neighbor_tile_x,
                            neighbor_tile_y,
                            blocked_by_objects,
                        )
                        and not is_path_blocked_tile(
                            neighbor_tile_x,
                            neighbor_tile_y,
                            blocked_by_objects,
                            goal_node,
                        )
                    ):
                        visited[neighbor_node] = 1
                        came_from[neighbor_node] = current_node
                        frontier_nodes.append(neighbor_node)
                        frontier_size = frontier_size + 1

    if not found_goal:
        return

    reverse_nodes = []
    reverse_size = 0
    trace_node = goal_node
    trace_steps = 0

    while trace_node != start_node and trace_steps < max_search_steps:
        reverse_nodes.append(trace_node)
        reverse_size = reverse_size + 1
        trace_node = came_from.get(trace_node, start_node)
        trace_steps = trace_steps + 1

    if reverse_size <= 0:
        return

    built_path_tiles_x = unit.path_tiles_x
    built_path_tiles_y = unit.path_tiles_y
    reverse_index = reverse_size - 1
    while reverse_index >= 0:
        path_node = reverse_nodes[reverse_index]
        built_path_tiles_x.append(node_to_tile_x(path_node))
        built_path_tiles_y.append(node_to_tile_y(path_node))
        reverse_index = reverse_index - 1

    unit.path_tiles_x = built_path_tiles_x
    unit.path_tiles_y = built_path_tiles_y
    unit.path_cursor = 0
    unit.path_len = reverse_size
    unit.path_active = True
    unit.vx = 0
    unit.vy = 0


def should_follow_path(obj: RTSObject) -> bool:
    return obj.active and obj.can_move and obj.path_active


@safe_condition(OnLogicalCondition(should_follow_path, RTSObject))
def follow_unit_path(obj: RTSObject):
    if obj.path_cursor >= obj.path_len:
        clear_move_path(obj)
        return

    next_tile_x = obj.path_tiles_x[obj.path_cursor]
    next_tile_y = obj.path_tiles_y[obj.path_cursor]
    next_world_x = tile_center_x(next_tile_x)
    next_world_y = tile_center_y(next_tile_y)

    dx = next_world_x - obj.x
    dy = next_world_y - obj.y
    snap_distance = (obj.move_speed / PHYSICS_STEP_HZ) + 0.5
    dist_sq = (dx * dx) + (dy * dy)

    if dist_sq <= (snap_distance * snap_distance):
        obj.x = next_world_x
        obj.y = next_world_y
        obj.path_cursor = obj.path_cursor + 1
        obj.vx = 0
        obj.vy = 0
        if obj.path_cursor >= obj.path_len:
            clear_move_path(obj)
        return

    obj.vx = 0
    obj.vy = 0
    abs_dx = abs_value(dx)
    abs_dy = abs_value(dy)
    if abs_dx > 0 and abs_dy > 0:
        diagonal_speed = obj.move_speed * DIAGONAL_SPEED_FACTOR
        if dx > 0:
            obj.vx = diagonal_speed
        else:
            obj.vx = -diagonal_speed
        if dy > 0:
            obj.vy = diagonal_speed
        else:
            obj.vy = -diagonal_speed
    elif abs_dx > 0:
        if dx > 0:
            obj.vx = obj.move_speed
        else:
            obj.vx = -obj.move_speed
    else:
        if dy > 0:
            obj.vy = obj.move_speed
        else:
            obj.vy = -obj.move_speed


def should_process_gather(worker: RTSObject) -> bool:
    return worker.active and worker.can_move and worker.gather_active


@callable
def process_worker_gather(
    worker: RTSObject,
    role: RTSRole,
    owner_role_id: str,
    objects: List[RTSObject],
    resources: List[ResourceNode],
):
    if worker.gather_active == False:
        return
    if worker.owner_role_id != owner_role_id:
        return

    resource_uid = worker.gather_resource_uid
    target_resource_x = 0
    target_resource_y = 0
    target_resource_w = 0
    target_resource_h = 0
    target_resource_kind = ""
    target_resource_amount = 0
    resource_found = False

    for resource in resources:
        if resource.active == False:
            continue
        if resource.uid != resource_uid:
            continue
        if resource.amount <= 0:
            continue
        target_resource_x = resource.x
        target_resource_y = resource.y
        target_resource_w = resource.w
        target_resource_h = resource.h
        target_resource_kind = resource.resource_kind
        target_resource_amount = resource.amount
        resource_found = True

    if not resource_found:
        clear_worker_gather_loop(worker)
        return

    hq_uid = worker.gather_hq_uid
    hq_found = False
    hq_x = 0
    hq_y = 0
    hq_w = 0
    hq_h = 0
    for obj in objects:
        if obj.active == False:
            continue
        if obj.uid != hq_uid:
            continue
        if obj.owner_role_id != worker.owner_role_id:
            continue
        if obj.object_kind != "hq":
            continue
        hq_x = obj.x
        hq_y = obj.y
        hq_w = obj.w
        hq_h = obj.h
        hq_found = True

    if not hq_found:
        new_hq_uid = find_closest_hq_uid(worker.owner_role_id, worker, objects)
        worker.gather_hq_uid = new_hq_uid
        if new_hq_uid == "":
            clear_worker_gather_loop(worker)
            return
        for obj in objects:
            if obj.active == False:
                continue
            if obj.uid != new_hq_uid:
                continue
            if obj.owner_role_id != worker.owner_role_id:
                continue
            if obj.object_kind != "hq":
                continue
            hq_x = obj.x
            hq_y = obj.y
            hq_w = obj.w
            hq_h = obj.h
            hq_found = True

    if not hq_found:
        clear_worker_gather_loop(worker)
        return

    hq_contact_x = project_point_to_box_x(
        target_resource_x,
        target_resource_y,
        hq_x,
        hq_y,
        hq_w,
        hq_h,
    )
    hq_contact_y = project_point_to_box_y(
        target_resource_x,
        target_resource_y,
        hq_x,
        hq_y,
        hq_w,
        hq_h,
    )
    resource_contact_x = project_point_to_box_x(
        hq_x,
        hq_y,
        target_resource_x,
        target_resource_y,
        target_resource_w,
        target_resource_h,
    )
    resource_contact_y = project_point_to_box_y(
        hq_x,
        hq_y,
        target_resource_x,
        target_resource_y,
        target_resource_w,
        target_resource_h,
    )

    if worker.gather_phase == "to_resource":
        if worker.path_active:
            return

        if squared_distance_to_box(
            worker.x,
            worker.y,
            target_resource_x,
            target_resource_y,
            target_resource_w,
            target_resource_h,
        ) <= (
            RESOURCE_INTERACT_RANGE * RESOURCE_INTERACT_RANGE
        ):
            if worker.task_active == False:
                harvest_amount = RESOURCE_HARVEST_MINERAL
                harvest_ticks = RESOURCE_MINE_DURATION_MINERAL_TICKS
                harvest_label = "Mining Minerals"
                if target_resource_kind == "gas":
                    harvest_amount = RESOURCE_HARVEST_GAS
                    harvest_ticks = RESOURCE_MINE_DURATION_GAS_TICKS
                    harvest_label = "Extracting Gas"
                if target_resource_amount < harvest_amount:
                    harvest_amount = target_resource_amount
                if harvest_amount <= 0:
                    clear_worker_gather_loop(worker)
                    return
                start_object_task(worker, "gather_harvest", harvest_label, harvest_ticks)
                worker.task_resource_kind = target_resource_kind
                worker.task_resource_amount = harvest_amount
                return

            if worker.task_kind != "gather_harvest":
                clear_object_task(worker)
                return

            worker.task_elapsed_ticks = worker.task_elapsed_ticks + 1
            if worker.task_elapsed_ticks < worker.task_total_ticks:
                return

            harvest_amount = worker.task_resource_amount
            actual_harvest = 0
            for resource in resources:
                if resource.uid != resource_uid:
                    continue
                if resource.amount <= 0:
                    continue
                actual_harvest = harvest_amount
                if resource.amount < actual_harvest:
                    actual_harvest = resource.amount
                resource.amount = resource.amount - actual_harvest
            if actual_harvest <= 0:
                clear_worker_gather_loop(worker)
                return

            worker.carrying_kind = target_resource_kind
            worker.carrying_amount = actual_harvest
            clear_object_task(worker)
            worker.gather_phase = "to_hq"
            build_worker_path(worker, objects, resources, hq_contact_x, hq_contact_y)
        else:
            if is_worker_gather_task(worker.task_kind):
                clear_object_task(worker)
            build_worker_path(
                worker,
                objects,
                resources,
                resource_contact_x,
                resource_contact_y,
            )
        return

    if worker.gather_phase == "to_hq":
        if worker.path_active:
            return

        if squared_distance_to_box(
            worker.x,
            worker.y,
            hq_x,
            hq_y,
            hq_w,
            hq_h,
        ) <= (
            RESOURCE_INTERACT_RANGE * RESOURCE_INTERACT_RANGE
        ):
            if worker.carrying_amount <= 0:
                clear_object_task(worker)
                worker.gather_phase = "to_resource"
                build_worker_path(
                    worker,
                    objects,
                    resources,
                    resource_contact_x,
                    resource_contact_y,
                )
                return

            if worker.task_active == False:
                start_object_task(
                    worker,
                    "gather_unload",
                    "Unloading Resources",
                    RESOURCE_UNLOAD_DURATION_TICKS,
                )
                worker.task_resource_kind = worker.carrying_kind
                worker.task_resource_amount = worker.carrying_amount
                return

            if worker.task_kind != "gather_unload":
                clear_object_task(worker)
                return

            worker.task_elapsed_ticks = worker.task_elapsed_ticks + 1
            if worker.task_elapsed_ticks < worker.task_total_ticks:
                return

            deposit_amount = worker.task_resource_amount
            if worker.carrying_amount < deposit_amount:
                deposit_amount = worker.carrying_amount
            if deposit_amount > 0:
                if worker.task_resource_kind == "gas":
                    role.gas = role.gas + deposit_amount
                else:
                    role.minerals = role.minerals + deposit_amount

            worker.carrying_amount = worker.carrying_amount - deposit_amount
            if worker.carrying_amount < 0:
                worker.carrying_amount = 0
            if worker.carrying_amount <= 0:
                worker.carrying_kind = ""
            clear_object_task(worker)
            if target_resource_amount <= 0:
                clear_worker_gather_loop(worker)
                return

            worker.gather_phase = "to_resource"
            build_worker_path(
                worker,
                objects,
                resources,
                resource_contact_x,
                resource_contact_y,
            )
        else:
            if is_worker_gather_task(worker.task_kind):
                clear_object_task(worker)
            build_worker_path(worker, objects, resources, hq_contact_x, hq_contact_y)
        return

    if is_worker_gather_task(worker.task_kind):
        clear_object_task(worker)
    worker.gather_phase = "to_resource"
    build_worker_path(
        worker,
        objects,
        resources,
        resource_contact_x,
        resource_contact_y,
    )


@safe_condition(OnLogicalCondition(should_process_gather, RTSObject))
def process_gather_for_human_1(
    worker: RTSObject,
    role: RTSRole["human_1"],
    objects: List[RTSObject],
    resources: List[ResourceNode],
):
    process_worker_gather(worker, role, PLAYER_1_ROLE_ID, objects, resources)


@safe_condition(OnLogicalCondition(should_process_gather, RTSObject))
def process_gather_for_human_2(
    worker: RTSObject,
    role: RTSRole["human_2"],
    objects: List[RTSObject],
    resources: List[ResourceNode],
):
    process_worker_gather(worker, role, PLAYER_2_ROLE_ID, objects, resources)


@callable
def refresh_selection_markers(
    owner_role_id: str,
    markers: List[SelectionMarker],
    objects: List[RTSObject],
    selected_uids: list[str],
    selected_count: int,
):
    for marker in markers:
        if marker.owner_role_id != owner_role_id:
            continue
        marker.active = False
        marker.parent = ""

    for slot_idx in range(selected_count):
        target_uid = selected_uids[slot_idx]
        target_x = 0
        target_y = 0
        target_w = 0
        target_h = 0
        found_target = False

        for obj in objects:
            if obj.active == False:
                continue
            if obj.uid != target_uid:
                continue
            target_x = obj.x
            target_y = obj.y
            target_w = obj.w
            target_h = obj.h
            found_target = True

        if not found_target:
            continue

        for marker in markers:
            if marker.owner_role_id != owner_role_id:
                continue
            if marker.slot_index != slot_idx:
                continue
            marker.active = True
            marker.parent = ""
            marker.x = target_x
            marker.y = target_y
            marker.w = target_w + 10
            marker.h = target_h + 10


def should_refresh_marker_slots(_drag_rect: DragSelectionRect) -> bool:
    return True


@safe_condition(OnLogicalCondition(should_refresh_marker_slots, DragSelectionRect))
def refresh_selection_markers_human_1(
    drag_rect: DragSelectionRect,
    self_role: RTSRole["human_1"],
    markers: List[SelectionMarker],
    objects: List[RTSObject],
):
    if drag_rect.owner_role_id != PLAYER_1_ROLE_ID:
        return
    refresh_selection_markers(
        PLAYER_1_ROLE_ID,
        markers,
        objects,
        self_role.selected_uids,
        self_role.selected_count,
    )


@safe_condition(OnLogicalCondition(should_refresh_marker_slots, DragSelectionRect))
def refresh_selection_markers_human_2(
    drag_rect: DragSelectionRect,
    self_role: RTSRole["human_2"],
    markers: List[SelectionMarker],
    objects: List[RTSObject],
):
    if drag_rect.owner_role_id != PLAYER_2_ROLE_ID:
        return
    refresh_selection_markers(
        PLAYER_2_ROLE_ID,
        markers,
        objects,
        self_role.selected_uids,
        self_role.selected_count,
    )


@callable
def clear_role_action_flags(self_role: RTSRole):
    self_role.can_train_worker = False
    self_role.can_build_hq = False
    self_role.can_build_supply_depot = False
    self_role.can_build_barracks = False
    self_role.can_build_academy = False
    self_role.can_build_starport = False
    self_role.can_upgrade_attack = False
    self_role.can_upgrade_armor = False


@callable
def refresh_role_interface_state(
    self_role: RTSRole,
    owner_role_id: str,
    objects: List[RTSObject],
):
    self_role.has_hq = has_owned_object_kind(owner_role_id, objects, "hq")
    self_role.has_supply_depot = has_owned_object_kind(owner_role_id, objects, "supply_depot")
    self_role.has_barracks = has_owned_object_kind(owner_role_id, objects, "barracks")
    self_role.has_academy = has_owned_object_kind(owner_role_id, objects, "academy")
    self_role.has_starport = has_owned_object_kind(owner_role_id, objects, "starport")
    clear_role_action_flags(self_role)

    valid_selected_uids = []
    valid_selected_count = 0
    first_selected_name = "None"
    for selected_uid in self_role.selected_uids:
        found_selected = False
        selected_name = "None"
        for obj in objects:
            if obj.active == False:
                continue
            if obj.uid != selected_uid:
                continue
            if obj.owner_role_id != owner_role_id:
                continue
            found_selected = True
            selected_name = obj.selection_name
        if found_selected:
            valid_selected_uids.append(selected_uid)
            valid_selected_count = valid_selected_count + 1
            if valid_selected_count == 1:
                first_selected_name = selected_name

    self_role.selected_uids = valid_selected_uids
    self_role.selected_count = valid_selected_count
    if self_role.selected_count <= 0:
        self_role.selected_uid = ""
        self_role.selected_name = "None"
    elif self_role.selected_count == 1:
        self_role.selected_uid = valid_selected_uids[0]
        self_role.selected_name = first_selected_name
    else:
        self_role.selected_uid = valid_selected_uids[0]
        self_role.selected_name = "Units"

    self_role.selected_kind = "none"
    self_role.selected_hp = 0
    self_role.selected_max_hp = 0
    self_role.selected_task_active = False
    self_role.selected_task_label = "Idle"
    self_role.selected_task_percent = 0
    self_role.selected_task_bar = build_progress_bar(0)
    self_role.selected_task_seconds_left = 0

    if self_role.selected_count > 1:
        self_role.selected_kind = "group"
        self_role.selected_task_label = "Multiple units selected"
        return
    if self_role.selected_count <= 0:
        return

    selected_uid = self_role.selected_uid
    found_selected_obj = False
    for obj in objects:
        if obj.active == False:
            continue
        if obj.uid != selected_uid:
            continue
        if obj.owner_role_id != owner_role_id:
            continue

        found_selected_obj = True
        self_role.selected_kind = obj.object_kind
        self_role.selected_hp = obj.hp
        self_role.selected_max_hp = obj.max_hp
        if obj.task_active:
            self_role.selected_task_active = True
            self_role.selected_task_label = obj.task_label
            self_role.selected_task_percent = task_progress_percent(obj)
            self_role.selected_task_bar = build_progress_bar(self_role.selected_task_percent)
            ticks_left = obj.task_total_ticks - obj.task_elapsed_ticks
            if ticks_left < 0:
                ticks_left = 0
            seconds_left = 0
            while ticks_left > 0:
                seconds_left = seconds_left + 1
                ticks_left = ticks_left - PHYSICS_STEP_HZ
            self_role.selected_task_seconds_left = seconds_left

        if obj.object_kind == "hq":
            self_role.can_train_worker = (
                obj.task_active == False
                and can_afford(self_role, WORKER_TRAIN_MINERAL_COST, WORKER_TRAIN_GAS_COST)
                and (self_role.supply_used + WORKER_TRAIN_SUPPLY_COST) <= self_role.supply_cap
            )

        if obj.object_kind == "worker":
            can_build_now = obj.task_active == False
            self_role.can_build_hq = (
                can_build_now
                and has_build_requirements(owner_role_id, objects, "hq")
                and can_afford(self_role, COST_HQ_MINERALS, COST_HQ_GAS)
            )
            self_role.can_build_supply_depot = (
                can_build_now
                and has_build_requirements(owner_role_id, objects, "supply_depot")
                and can_afford(self_role, COST_SUPPLY_DEPOT_MINERALS, COST_SUPPLY_DEPOT_GAS)
            )
            self_role.can_build_barracks = (
                can_build_now
                and has_build_requirements(owner_role_id, objects, "barracks")
                and can_afford(self_role, COST_BARRACKS_MINERALS, COST_BARRACKS_GAS)
            )
            self_role.can_build_academy = (
                can_build_now
                and has_build_requirements(owner_role_id, objects, "academy")
                and can_afford(self_role, COST_ACADEMY_MINERALS, COST_ACADEMY_GAS)
            )
            self_role.can_build_starport = (
                can_build_now
                and has_build_requirements(owner_role_id, objects, "starport")
                and can_afford(self_role, COST_STARPORT_MINERALS, COST_STARPORT_GAS)
            )

        if obj.object_kind == "academy":
            can_research_now = obj.task_active == False
            self_role.can_upgrade_attack = (
                can_research_now
                and self_role.attack_upgrade_level < MAX_UPGRADE_LEVEL
                and can_afford(
                    self_role,
                    UPGRADE_COST_ATTACK_MINERALS,
                    UPGRADE_COST_ATTACK_GAS,
                )
            )
            self_role.can_upgrade_armor = (
                can_research_now
                and self_role.armor_upgrade_level < MAX_UPGRADE_LEVEL
                and can_afford(
                    self_role,
                    UPGRADE_COST_ARMOR_MINERALS,
                    UPGRADE_COST_ARMOR_GAS,
                )
            )

    if not found_selected_obj:
        self_role.selected_uid = ""
        self_role.selected_name = "None"
        self_role.selected_count = 0
        self_role.selected_uids = []
        self_role.selected_kind = "none"


@callable
def issue_train_worker_for_role(
    self_role: RTSRole,
    owner_role_id: str,
    objects: List[RTSObject],
):
    if self_role.selected_count != 1:
        self_role.ui_status = "Select one HQ."
        return

    selected_uid = self_role.selected_uid
    for obj in objects:
        if obj.active == False:
            continue
        if obj.uid != selected_uid:
            continue
        if obj.owner_role_id != owner_role_id:
            continue
        if obj.object_kind != "hq":
            self_role.ui_status = "Select HQ to train Worker."
            return
        if obj.task_active:
            self_role.ui_status = "HQ is busy."
            return
        if (self_role.supply_used + WORKER_TRAIN_SUPPLY_COST) > self_role.supply_cap:
            self_role.ui_status = "Need more Supply."
            return
        if can_afford(self_role, WORKER_TRAIN_MINERAL_COST, WORKER_TRAIN_GAS_COST) == False:
            self_role.ui_status = "Not enough resources for Worker."
            return

        self_role.minerals = self_role.minerals - WORKER_TRAIN_MINERAL_COST
        self_role.gas = self_role.gas - WORKER_TRAIN_GAS_COST
        start_hq_worker_training(obj)
        self_role.ui_status = "Training Worker..."
        return

    self_role.ui_status = "Select one HQ."


@callable
def issue_build_command_for_role(
    self_role: RTSRole,
    owner_role_id: str,
    objects: List[RTSObject],
    build_kind: str,
):
    if self_role.selected_count != 1:
        self_role.ui_status = "Select one Worker."
        return

    selected_uid = self_role.selected_uid
    for obj in objects:
        if obj.active == False:
            continue
        if obj.uid != selected_uid:
            continue
        if obj.owner_role_id != owner_role_id:
            continue
        if obj.object_kind != "worker":
            self_role.ui_status = "Select Worker to build structures."
            return
        if obj.task_active:
            self_role.ui_status = "Worker is busy."
            return
        if has_build_requirements(owner_role_id, objects, build_kind) == False:
            self_role.ui_status = build_requirement_text(build_kind)
            return

        mineral_cost = object_kind_mineral_cost(build_kind)
        gas_cost = object_kind_gas_cost(build_kind)
        if can_afford(self_role, mineral_cost, gas_cost) == False:
            self_role.ui_status = "Not enough resources for " + object_kind_name(build_kind) + "."
            return

        self_role.minerals = self_role.minerals - mineral_cost
        self_role.gas = self_role.gas - gas_cost
        clear_worker_gather_loop(obj)
        start_worker_build_task(obj, owner_role_id, objects, build_kind)
        self_role.ui_status = "Constructing " + object_kind_name(build_kind) + "..."
        return

    self_role.ui_status = "Select one Worker."


@callable
def issue_upgrade_command_for_role(
    self_role: RTSRole,
    owner_role_id: str,
    objects: List[RTSObject],
    upgrade_kind: str,
):
    if self_role.selected_count != 1:
        self_role.ui_status = "Select one Academy."
        return

    selected_uid = self_role.selected_uid
    for obj in objects:
        if obj.active == False:
            continue
        if obj.uid != selected_uid:
            continue
        if obj.owner_role_id != owner_role_id:
            continue
        if obj.object_kind != "academy":
            self_role.ui_status = "Select Academy for upgrades."
            return
        if obj.task_active:
            self_role.ui_status = "Academy is busy."
            return

        if upgrade_kind == "attack":
            if self_role.attack_upgrade_level >= MAX_UPGRADE_LEVEL:
                self_role.ui_status = "Attack already maxed."
                return
            if can_afford(
                self_role,
                UPGRADE_COST_ATTACK_MINERALS,
                UPGRADE_COST_ATTACK_GAS,
            ) == False:
                self_role.ui_status = "Not enough resources for Attack upgrade."
                return
            self_role.minerals = self_role.minerals - UPGRADE_COST_ATTACK_MINERALS
            self_role.gas = self_role.gas - UPGRADE_COST_ATTACK_GAS
            start_academy_research_task(obj, "attack")
            self_role.ui_status = "Researching Attack..."
            return

        if self_role.armor_upgrade_level >= MAX_UPGRADE_LEVEL:
            self_role.ui_status = "Armor already maxed."
            return
        if can_afford(
            self_role,
            UPGRADE_COST_ARMOR_MINERALS,
            UPGRADE_COST_ARMOR_GAS,
        ) == False:
            self_role.ui_status = "Not enough resources for Armor upgrade."
            return
        self_role.minerals = self_role.minerals - UPGRADE_COST_ARMOR_MINERALS
        self_role.gas = self_role.gas - UPGRADE_COST_ARMOR_GAS
        start_academy_research_task(obj, "armor")
        self_role.ui_status = "Researching Armor..."
        return

    self_role.ui_status = "Select one Academy."


@safe_condition(OnLogicalCondition(should_refresh_marker_slots, DragSelectionRect))
def refresh_role_interface_human_1(
    drag_rect: DragSelectionRect,
    self_role: RTSRole["human_1"],
    objects: List[RTSObject],
):
    if drag_rect.owner_role_id != PLAYER_1_ROLE_ID:
        return
    refresh_role_interface_state(self_role, PLAYER_1_ROLE_ID, objects)


@safe_condition(OnLogicalCondition(should_refresh_marker_slots, DragSelectionRect))
def refresh_role_interface_human_2(
    drag_rect: DragSelectionRect,
    self_role: RTSRole["human_2"],
    objects: List[RTSObject],
):
    if drag_rect.owner_role_id != PLAYER_2_ROLE_ID:
        return
    refresh_role_interface_state(self_role, PLAYER_2_ROLE_ID, objects)


@callable
def select_for_role(
    self_role: RTSRole,
    owner_role_id: str,
    objects: List[RTSObject],
    start_world_x: float,
    start_world_y: float,
    end_world_x: float,
    end_world_y: float,
    drag_select: bool,
):
    if drag_select:
        min_x = start_world_x
        max_x = end_world_x
        min_y = start_world_y
        max_y = end_world_y
        if min_x > max_x:
            min_x = end_world_x
            max_x = start_world_x
        if min_y > max_y:
            min_y = end_world_y
            max_y = start_world_y

        selected_uids = []
        selected_count = 0
        first_selected_name = "None"

        for obj in objects:
            if obj.active == False:
                continue
            if obj.owner_role_id != owner_role_id:
                continue
            if not obj.can_move:
                continue

            overlaps_box = (
                obj.x + (obj.w / 2) >= min_x
                and obj.x - (obj.w / 2) <= max_x
                and obj.y + (obj.h / 2) >= min_y
                and obj.y - (obj.h / 2) <= max_y
            )
            if not overlaps_box:
                continue

            selected_uids.append(obj.uid)
            selected_count = selected_count + 1
            if selected_count == 1:
                first_selected_name = obj.selection_name

        self_role.selected_uids = selected_uids
        self_role.selected_count = selected_count
        if selected_count <= 0:
            self_role.selected_uid = ""
            self_role.selected_name = "None"
        elif selected_count == 1:
            self_role.selected_uid = selected_uids[0]
            self_role.selected_name = first_selected_name
        else:
            self_role.selected_uid = selected_uids[0]
            self_role.selected_name = "Units"
        return

    clicked_world_x = end_world_x
    clicked_world_y = end_world_y

    clicked_own_uid = ""
    clicked_own_name = "None"
    clicked_any_ownable = False
    clicked_own_z = -999999

    for obj in objects:
        if obj.active == False:
            continue
        half_w = obj.w / 2
        half_h = obj.h / 2
        inside = (
            clicked_world_x >= obj.x - half_w
            and clicked_world_x <= obj.x + half_w
            and clicked_world_y >= obj.y - half_h
            and clicked_world_y <= obj.y + half_h
        )
        if not inside:
            continue

        clicked_any_ownable = True
        if obj.owner_role_id != owner_role_id:
            continue
        if obj.z < clicked_own_z:
            continue

        clicked_own_uid = obj.uid
        clicked_own_name = obj.selection_name
        clicked_own_z = obj.z

    if clicked_own_uid != "":
        self_role.selected_uid = clicked_own_uid
        self_role.selected_name = clicked_own_name
        self_role.selected_count = 1
        self_role.selected_uids = [clicked_own_uid]
    elif not clicked_any_ownable:
        self_role.selected_uid = ""
        self_role.selected_name = "None"
        self_role.selected_count = 0
        self_role.selected_uids = []


@callable
def command_selected_units_for_role(
    self_role: RTSRole,
    owner_role_id: str,
    objects: List[RTSObject],
    resources: List[ResourceNode],
    target_world_x: float,
    target_world_y: float,
):
    if self_role.selected_count <= 0:
        return

    clicked_resource_uid = find_clicked_resource_uid(
        target_world_x,
        target_world_y,
        resources,
    )

    selected_uids = self_role.selected_uids
    for obj in objects:
        if obj.active == False:
            continue
        if obj.owner_role_id != owner_role_id:
            continue
        if not obj.can_move:
            continue

        is_selected = False
        for selected_uid in selected_uids:
            if selected_uid == obj.uid:
                is_selected = True

        if not is_selected:
            continue
        if obj.task_active and is_worker_gather_task(obj.task_kind) == False:
            continue
        if clicked_resource_uid != "":
            start_worker_gather_loop(
                obj,
                objects,
                resources,
                clicked_resource_uid,
            )
        else:
            clear_worker_gather_loop(obj)
            build_worker_path(obj, objects, resources, target_world_x, target_world_y)


@callable
def update_drag_rect(
    drag_rect: DragSelectionRect,
    start_world_x: float,
    start_world_y: float,
    end_world_x: float,
    end_world_y: float,
):
    min_x = start_world_x
    max_x = end_world_x
    min_y = start_world_y
    max_y = end_world_y
    if min_x > max_x:
        min_x = end_world_x
        max_x = start_world_x
    if min_y > max_y:
        min_y = end_world_y
        max_y = start_world_y

    drag_rect.x = (min_x + max_x) / 2
    drag_rect.y = (min_y + max_y) / 2
    drag_rect.w = max_x - min_x
    drag_rect.h = max_y - min_y
    if drag_rect.w < 2:
        drag_rect.w = 2
    if drag_rect.h < 2:
        drag_rect.h = 2


@unsafe_condition(ButtonCondition.begin("train_worker", id="human_1"))
def ui_train_worker_human_1(
    self_role: RTSRole["human_1"],
    objects: List[RTSObject],
):
    issue_train_worker_for_role(self_role, PLAYER_1_ROLE_ID, objects)


@unsafe_condition(ButtonCondition.begin("build_hq", id="human_1"))
def ui_build_hq_human_1(
    self_role: RTSRole["human_1"],
    objects: List[RTSObject],
):
    issue_build_command_for_role(self_role, PLAYER_1_ROLE_ID, objects, "hq")


@unsafe_condition(ButtonCondition.begin("build_supply_depot", id="human_1"))
def ui_build_supply_depot_human_1(
    self_role: RTSRole["human_1"],
    objects: List[RTSObject],
):
    issue_build_command_for_role(self_role, PLAYER_1_ROLE_ID, objects, "supply_depot")


@unsafe_condition(ButtonCondition.begin("build_barracks", id="human_1"))
def ui_build_barracks_human_1(
    self_role: RTSRole["human_1"],
    objects: List[RTSObject],
):
    issue_build_command_for_role(self_role, PLAYER_1_ROLE_ID, objects, "barracks")


@unsafe_condition(ButtonCondition.begin("build_academy", id="human_1"))
def ui_build_academy_human_1(
    self_role: RTSRole["human_1"],
    objects: List[RTSObject],
):
    issue_build_command_for_role(self_role, PLAYER_1_ROLE_ID, objects, "academy")


@unsafe_condition(ButtonCondition.begin("build_starport", id="human_1"))
def ui_build_starport_human_1(
    self_role: RTSRole["human_1"],
    objects: List[RTSObject],
):
    issue_build_command_for_role(self_role, PLAYER_1_ROLE_ID, objects, "starport")


@unsafe_condition(ButtonCondition.begin("upgrade_attack", id="human_1"))
def ui_upgrade_attack_human_1(
    self_role: RTSRole["human_1"],
    objects: List[RTSObject],
):
    issue_upgrade_command_for_role(self_role, PLAYER_1_ROLE_ID, objects, "attack")


@unsafe_condition(ButtonCondition.begin("upgrade_armor", id="human_1"))
def ui_upgrade_armor_human_1(
    self_role: RTSRole["human_1"],
    objects: List[RTSObject],
):
    issue_upgrade_command_for_role(self_role, PLAYER_1_ROLE_ID, objects, "armor")


@unsafe_condition(ButtonCondition.begin("train_worker", id="human_2"))
def ui_train_worker_human_2(
    self_role: RTSRole["human_2"],
    objects: List[RTSObject],
):
    issue_train_worker_for_role(self_role, PLAYER_2_ROLE_ID, objects)


@unsafe_condition(ButtonCondition.begin("build_hq", id="human_2"))
def ui_build_hq_human_2(
    self_role: RTSRole["human_2"],
    objects: List[RTSObject],
):
    issue_build_command_for_role(self_role, PLAYER_2_ROLE_ID, objects, "hq")


@unsafe_condition(ButtonCondition.begin("build_supply_depot", id="human_2"))
def ui_build_supply_depot_human_2(
    self_role: RTSRole["human_2"],
    objects: List[RTSObject],
):
    issue_build_command_for_role(self_role, PLAYER_2_ROLE_ID, objects, "supply_depot")


@unsafe_condition(ButtonCondition.begin("build_barracks", id="human_2"))
def ui_build_barracks_human_2(
    self_role: RTSRole["human_2"],
    objects: List[RTSObject],
):
    issue_build_command_for_role(self_role, PLAYER_2_ROLE_ID, objects, "barracks")


@unsafe_condition(ButtonCondition.begin("build_academy", id="human_2"))
def ui_build_academy_human_2(
    self_role: RTSRole["human_2"],
    objects: List[RTSObject],
):
    issue_build_command_for_role(self_role, PLAYER_2_ROLE_ID, objects, "academy")


@unsafe_condition(ButtonCondition.begin("build_starport", id="human_2"))
def ui_build_starport_human_2(
    self_role: RTSRole["human_2"],
    objects: List[RTSObject],
):
    issue_build_command_for_role(self_role, PLAYER_2_ROLE_ID, objects, "starport")


@unsafe_condition(ButtonCondition.begin("upgrade_attack", id="human_2"))
def ui_upgrade_attack_human_2(
    self_role: RTSRole["human_2"],
    objects: List[RTSObject],
):
    issue_upgrade_command_for_role(self_role, PLAYER_2_ROLE_ID, objects, "attack")


@unsafe_condition(ButtonCondition.begin("upgrade_armor", id="human_2"))
def ui_upgrade_armor_human_2(
    self_role: RTSRole["human_2"],
    objects: List[RTSObject],
):
    issue_upgrade_command_for_role(self_role, PLAYER_2_ROLE_ID, objects, "armor")


@unsafe_condition(KeyboardCondition.on_press("d", id="human_1"))
def pan_camera_right_human_1(camera: Camera["camera_human_1"]):
    camera.translate(CAMERA_PAN_SPEED, 0)
    camera.x = clamp_camera_x(camera.x)
    camera.y = clamp_camera_y(camera.y)


@unsafe_condition(KeyboardCondition.on_press("q", id="human_1"))
def pan_camera_left_human_1(camera: Camera["camera_human_1"]):
    camera.translate(-CAMERA_PAN_SPEED, 0)
    camera.x = clamp_camera_x(camera.x)
    camera.y = clamp_camera_y(camera.y)


@unsafe_condition(KeyboardCondition.on_press("z", id="human_1"))
def pan_camera_up_human_1(camera: Camera["camera_human_1"]):
    camera.translate(0, -CAMERA_PAN_SPEED)
    camera.x = clamp_camera_x(camera.x)
    camera.y = clamp_camera_y(camera.y)


@unsafe_condition(KeyboardCondition.on_press("s", id="human_1"))
def pan_camera_down_human_1(camera: Camera["camera_human_1"]):
    camera.translate(0, CAMERA_PAN_SPEED)
    camera.x = clamp_camera_x(camera.x)
    camera.y = clamp_camera_y(camera.y)


@unsafe_condition(KeyboardCondition.on_press("d", id="human_2"))
def pan_camera_right_human_2(camera: Camera["camera_human_2"]):
    camera.translate(CAMERA_PAN_SPEED, 0)
    camera.x = clamp_camera_x(camera.x)
    camera.y = clamp_camera_y(camera.y)


@unsafe_condition(KeyboardCondition.on_press("q", id="human_2"))
def pan_camera_left_human_2(camera: Camera["camera_human_2"]):
    camera.translate(-CAMERA_PAN_SPEED, 0)
    camera.x = clamp_camera_x(camera.x)
    camera.y = clamp_camera_y(camera.y)


@unsafe_condition(KeyboardCondition.on_press("z", id="human_2"))
def pan_camera_up_human_2(camera: Camera["camera_human_2"]):
    camera.translate(0, -CAMERA_PAN_SPEED)
    camera.x = clamp_camera_x(camera.x)
    camera.y = clamp_camera_y(camera.y)


@unsafe_condition(KeyboardCondition.on_press("s", id="human_2"))
def pan_camera_down_human_2(camera: Camera["camera_human_2"]):
    camera.translate(0, CAMERA_PAN_SPEED)
    camera.x = clamp_camera_x(camera.x)
    camera.y = clamp_camera_y(camera.y)


@unsafe_condition(MouseCondition.on_click("left", id="human_1"))
def update_drag_rect_human_1(
    camera: Camera["camera_human_1"],
    drag_rect: DragSelectionRect["p1_drag_rect"],
    mouse: MouseInfo,
):
    drag_select = is_drag_select(mouse.pressed_x, mouse.pressed_y, mouse.x, mouse.y)
    if not drag_select:
        drag_rect.active = False
        return

    start_world_x = camera_screen_to_world_x(camera.x, mouse.pressed_x)
    start_world_y = camera_screen_to_world_y(camera.y, mouse.pressed_y)
    end_world_x = camera_screen_to_world_x(camera.x, mouse.x)
    end_world_y = camera_screen_to_world_y(camera.y, mouse.y)
    update_drag_rect(
        drag_rect,
        start_world_x,
        start_world_y,
        end_world_x,
        end_world_y,
    )
    drag_rect.active = True


@unsafe_condition(MouseCondition.end_click("left", id="human_1"))
def select_for_human_1(
    self_role: RTSRole["human_1"],
    camera: Camera["camera_human_1"],
    drag_rect: DragSelectionRect["p1_drag_rect"],
    objects: List[RTSObject],
    markers: List[SelectionMarker],
    mouse: MouseInfo,
):
    drag_select = is_drag_select(mouse.pressed_x, mouse.pressed_y, mouse.x, mouse.y)
    start_world_x = camera_screen_to_world_x(camera.x, mouse.pressed_x)
    start_world_y = camera_screen_to_world_y(camera.y, mouse.pressed_y)
    end_world_x = camera_screen_to_world_x(camera.x, mouse.x)
    end_world_y = camera_screen_to_world_y(camera.y, mouse.y)

    select_for_role(
        self_role,
        PLAYER_1_ROLE_ID,
        objects,
        start_world_x,
        start_world_y,
        end_world_x,
        end_world_y,
        drag_select,
    )
    refresh_selection_markers(
        PLAYER_1_ROLE_ID,
        markers,
        objects,
        self_role.selected_uids,
        self_role.selected_count,
    )
    drag_rect.active = False


@unsafe_condition(MouseCondition.begin_click("right", id="human_1"))
def command_selected_units_for_human_1(
    self_role: RTSRole["human_1"],
    camera: Camera["camera_human_1"],
    objects: List[RTSObject],
    resources: List[ResourceNode],
    mouse: MouseInfo,
):
    target_world_x = camera_screen_to_world_x(camera.x, mouse.pressed_x)
    target_world_y = camera_screen_to_world_y(camera.y, mouse.pressed_y)
    command_selected_units_for_role(
        self_role,
        PLAYER_1_ROLE_ID,
        objects,
        resources,
        target_world_x,
        target_world_y,
    )


@unsafe_condition(MouseCondition.on_click("left", id="human_2"))
def update_drag_rect_human_2(
    camera: Camera["camera_human_2"],
    drag_rect: DragSelectionRect["p2_drag_rect"],
    mouse: MouseInfo,
):
    drag_select = is_drag_select(mouse.pressed_x, mouse.pressed_y, mouse.x, mouse.y)
    if not drag_select:
        drag_rect.active = False
        return

    start_world_x = camera_screen_to_world_x(camera.x, mouse.pressed_x)
    start_world_y = camera_screen_to_world_y(camera.y, mouse.pressed_y)
    end_world_x = camera_screen_to_world_x(camera.x, mouse.x)
    end_world_y = camera_screen_to_world_y(camera.y, mouse.y)
    update_drag_rect(
        drag_rect,
        start_world_x,
        start_world_y,
        end_world_x,
        end_world_y,
    )
    drag_rect.active = True


@unsafe_condition(MouseCondition.end_click("left", id="human_2"))
def select_for_human_2(
    self_role: RTSRole["human_2"],
    camera: Camera["camera_human_2"],
    drag_rect: DragSelectionRect["p2_drag_rect"],
    objects: List[RTSObject],
    markers: List[SelectionMarker],
    mouse: MouseInfo,
):
    drag_select = is_drag_select(mouse.pressed_x, mouse.pressed_y, mouse.x, mouse.y)
    start_world_x = camera_screen_to_world_x(camera.x, mouse.pressed_x)
    start_world_y = camera_screen_to_world_y(camera.y, mouse.pressed_y)
    end_world_x = camera_screen_to_world_x(camera.x, mouse.x)
    end_world_y = camera_screen_to_world_y(camera.y, mouse.y)

    select_for_role(
        self_role,
        PLAYER_2_ROLE_ID,
        objects,
        start_world_x,
        start_world_y,
        end_world_x,
        end_world_y,
        drag_select,
    )
    refresh_selection_markers(
        PLAYER_2_ROLE_ID,
        markers,
        objects,
        self_role.selected_uids,
        self_role.selected_count,
    )
    drag_rect.active = False


@unsafe_condition(MouseCondition.begin_click("right", id="human_2"))
def command_selected_units_for_human_2(
    self_role: RTSRole["human_2"],
    camera: Camera["camera_human_2"],
    objects: List[RTSObject],
    resources: List[ResourceNode],
    mouse: MouseInfo,
):
    target_world_x = camera_screen_to_world_x(camera.x, mouse.pressed_x)
    target_world_y = camera_screen_to_world_y(camera.y, mouse.pressed_y)
    command_selected_units_for_role(
        self_role,
        PLAYER_2_ROLE_ID,
        objects,
        resources,
        target_world_x,
        target_world_y,
    )


CodeBlock.end("selection_and_move_rules")
