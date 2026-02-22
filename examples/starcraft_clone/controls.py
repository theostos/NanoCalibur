from typing import List

from nanocalibur.dsl_markers import (
    Camera,
    CodeBlock,
    KeyboardCondition,
    MouseCondition,
    MouseInfo,
    OnLogicalCondition,
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
"""Sandbox feature #1: ownership-based selection + pathfinding worker movement."""

CAMERA_PAN_SPEED = 4
DRAG_SELECT_THRESHOLD_PX = 8
PHYSICS_STEP_HZ = 60
DIAGONAL_SPEED_FACTOR = 0.70710678
RESOURCE_INTERACT_RANGE = 42
RESOURCE_HARVEST_MINERAL = 8
RESOURCE_HARVEST_GAS = 6


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
def clear_worker_gather_loop(worker: RTSObject):
    worker.gather_active = False
    worker.gather_phase = ""
    worker.gather_resource_uid = ""
    worker.gather_hq_uid = ""
    worker.carrying_kind = ""
    worker.carrying_amount = 0
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

        left_world = obj.x - (obj.w / 2) + 1
        right_world = obj.x + (obj.w / 2) - 1
        top_world = obj.y - (obj.h / 2) + 1
        bottom_world = obj.y + (obj.h / 2) - 1

        min_tile_x = world_to_tile_x(left_world)
        max_tile_x = world_to_tile_x(right_world)
        min_tile_y = world_to_tile_y(top_world)
        max_tile_y = world_to_tile_y(bottom_world)

        for block_tile_y in range(min_tile_y, max_tile_y + 1):
            for block_tile_x in range(min_tile_x, max_tile_x + 1):
                blocked_node = tile_node(block_tile_x, block_tile_y)
                blocked_by_objects[blocked_node] = 1

    for resource in resources:
        if resource.active == False:
            continue

        left_world = resource.x - (resource.w / 2) + 1
        right_world = resource.x + (resource.w / 2) - 1
        top_world = resource.y - (resource.h / 2) + 1
        bottom_world = resource.y + (resource.h / 2) - 1

        min_tile_x = world_to_tile_x(left_world)
        max_tile_x = world_to_tile_x(right_world)
        min_tile_y = world_to_tile_y(top_world)
        max_tile_y = world_to_tile_y(bottom_world)

        for block_tile_y in range(min_tile_y, max_tile_y + 1):
            for block_tile_x in range(min_tile_x, max_tile_x + 1):
                blocked_node = tile_node(block_tile_x, block_tile_y)
                blocked_by_objects[blocked_node] = 1

    if blocked_by_objects.get(goal_node, 0) == 1:
        found_open_goal = False
        for search_radius in range(1, 10):
            min_search_x = goal_tile_x - search_radius
            max_search_x = goal_tile_x + search_radius
            min_search_y = goal_tile_y - search_radius
            max_search_y = goal_tile_y + search_radius

            for candidate_tile_y in range(min_search_y, max_search_y + 1):
                for candidate_tile_x in range(min_search_x, max_search_x + 1):
                    if found_open_goal:
                        continue
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

                    goal_tile_x = candidate_tile_x
                    goal_tile_y = candidate_tile_y
                    goal_node = candidate_node
                    found_open_goal = True

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
            hq_found = True

    if not hq_found:
        clear_worker_gather_loop(worker)
        return

    if worker.gather_phase == "to_resource":
        if worker.path_active:
            return

        if squared_distance(worker.x, worker.y, target_resource_x, target_resource_y) <= (
            RESOURCE_INTERACT_RANGE * RESOURCE_INTERACT_RANGE
        ):
            harvest_amount = RESOURCE_HARVEST_MINERAL
            if target_resource_kind == "gas":
                harvest_amount = RESOURCE_HARVEST_GAS
            if target_resource_amount < harvest_amount:
                harvest_amount = target_resource_amount
            if harvest_amount <= 0:
                clear_worker_gather_loop(worker)
                return

            for resource in resources:
                if resource.uid == resource_uid and resource.amount > 0:
                    resource.amount = resource.amount - harvest_amount

            worker.carrying_kind = target_resource_kind
            worker.carrying_amount = harvest_amount
            worker.gather_phase = "to_hq"
            build_worker_path(worker, objects, resources, hq_x, hq_y)
        else:
            build_worker_path(worker, objects, resources, target_resource_x, target_resource_y)
        return

    if worker.gather_phase == "to_hq":
        if worker.path_active:
            return

        if squared_distance(worker.x, worker.y, hq_x, hq_y) <= (
            RESOURCE_INTERACT_RANGE * RESOURCE_INTERACT_RANGE
        ):
            if worker.carrying_amount > 0:
                if worker.carrying_kind == "gas":
                    role.gas = role.gas + worker.carrying_amount
                else:
                    role.minerals = role.minerals + worker.carrying_amount

            worker.carrying_amount = 0
            worker.carrying_kind = ""
            if target_resource_amount <= 0:
                clear_worker_gather_loop(worker)
                return

            worker.gather_phase = "to_resource"
            build_worker_path(worker, objects, resources, target_resource_x, target_resource_y)
        else:
            build_worker_path(worker, objects, resources, hq_x, hq_y)
        return

    worker.gather_phase = "to_resource"
    build_worker_path(worker, objects, resources, target_resource_x, target_resource_y)


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
            marker.parent = target_uid
            marker.x = target_x
            marker.y = target_y
            marker.w = target_w + 10
            marker.h = target_h + 10


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
    target_world_x = camera_screen_to_world_x(camera.x, mouse.x)
    target_world_y = camera_screen_to_world_y(camera.y, mouse.y)
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
    target_world_x = camera_screen_to_world_x(camera.x, mouse.x)
    target_world_y = camera_screen_to_world_y(camera.y, mouse.y)
    command_selected_units_for_role(
        self_role,
        PLAYER_2_ROLE_ID,
        objects,
        resources,
        target_world_x,
        target_world_y,
    )


CodeBlock.end("selection_and_move_rules")
