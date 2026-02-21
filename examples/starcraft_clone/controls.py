from typing import List

from nanocalibur.dsl_markers import (
    AbstractCodeBlock,
    ButtonCondition,
    Camera,
    CodeBlock,
    Global,
    KeyboardCondition,
    MouseCondition,
    MouseInfo,
    Role,
    Scene,
    callable,
    unsafe_condition,
)

from .constants import (
    BUILD_TIME_BARRACKS,
    BUILD_TIME_FACTORY,
    BUILD_TIME_LAB,
    BUILD_TIME_REFINERY,
    BUILD_TIME_SUPPLY,
    COST_BARRACKS_G,
    COST_BARRACKS_M,
    COST_FACTORY_G,
    COST_FACTORY_M,
    COST_LAB_G,
    COST_LAB_M,
    COST_REFINERY_G,
    COST_REFINERY_M,
    COST_SUPPLY_G,
    COST_SUPPLY_M,
    CAMERA_PAN_SPEED,
    MAP_COLS,
    MAP_ROWS,
    TILE,
)
from .schemas import (
    Building,
    StarRole,
    Unit,
)


CodeBlock.begin("starcraft_clone_controls")
"""Mouse-driven RTS controls: build placement, drag selection, move/attack orders."""


@callable
def _build_half_size(pending_build: str):
    if pending_build == "supply":
        return 14
    if pending_build == "barracks":
        return 16
    if pending_build == "refinery":
        return 15
    if pending_build == "factory":
        return 17
    if pending_build == "lab":
        return 15
    return 16


@callable
def _placement_reason(
    scene: Scene,
    x: float,
    y: float,
    pending_build: str,
    player_state: StarRole,
    units: List[Unit],
    buildings: List[Building],
):
    if pending_build == "":
        return "No building queued."

    half_w = _build_half_size(pending_build)
    half_h = _build_half_size(pending_build)
    world_w = MAP_COLS * TILE
    world_h = MAP_ROWS * TILE
    left = x - half_w
    right = x + half_w
    top = y - half_h
    bottom = y + half_h

    if left < 0 or right >= world_w or top < 0 or bottom >= world_h:
        return "Out of map bounds."

    if scene.is_solid_at(left, top) or scene.is_solid_at(right, top):
        return "Blocked by terrain."
    if scene.is_solid_at(left, bottom) or scene.is_solid_at(right, bottom):
        return "Blocked by terrain."
    if scene.is_solid_at(x, y):
        return "Blocked by terrain."
    if scene.is_solid_at(x, top) or scene.is_solid_at(x, bottom):
        return "Blocked by terrain."
    if scene.is_solid_at(left, y) or scene.is_solid_at(right, y):
        return "Blocked by terrain."

    for unit in units:
        if not unit.active:
            continue
        if unit.block_mask is None or unit.block_mask <= 0:
            continue
        if unit.x + unit.w / 2 <= left:
            continue
        if unit.x - unit.w / 2 >= right:
            continue
        if unit.y + unit.h / 2 <= top:
            continue
        if unit.y - unit.h / 2 >= bottom:
            continue
        return "Blocked by unit."

    for building in buildings:
        if not building.active:
            continue
        if building.block_mask is None or building.block_mask <= 0:
            continue
        if building.x + building.w / 2 <= left:
            continue
        if building.x - building.w / 2 >= right:
            continue
        if building.y + building.h / 2 <= top:
            continue
        if building.y - building.h / 2 >= bottom:
            continue
        return "Blocked by building."

    if pending_build == "supply":
        if player_state.minerals < COST_SUPPLY_M:
            return "Not enough minerals."
        if player_state.gas < COST_SUPPLY_G:
            return "Not enough gas."
    elif pending_build == "barracks":
        if player_state.minerals < COST_BARRACKS_M:
            return "Not enough minerals."
        if player_state.gas < COST_BARRACKS_G:
            return "Not enough gas."
    elif pending_build == "refinery":
        if player_state.minerals < COST_REFINERY_M:
            return "Not enough minerals."
        if player_state.gas < COST_REFINERY_G:
            return "Not enough gas."
    elif pending_build == "factory":
        if player_state.minerals < COST_FACTORY_M:
            return "Not enough minerals."
        if player_state.gas < COST_FACTORY_G:
            return "Not enough gas."
    elif pending_build == "lab":
        if player_state.minerals < COST_LAB_M:
            return "Not enough minerals."
        if player_state.gas < COST_LAB_G:
            return "Not enough gas."

    return ""


@callable
def _refresh_selection_ui(player_state: StarRole):
    player_state.ui_show_hq_controls = "none"
    player_state.ui_show_barracks_controls = "none"
    player_state.ui_show_factory_controls = "none"
    player_state.ui_show_lab_controls = "none"

    if player_state.selected_building_type == "hq":
        player_state.ui_show_hq_controls = "flex"
    elif player_state.selected_building_type == "barracks":
        player_state.ui_show_barracks_controls = "flex"
    elif player_state.selected_building_type == "factory":
        player_state.ui_show_factory_controls = "flex"
    elif player_state.selected_building_type == "lab":
        player_state.ui_show_lab_controls = "flex"


@callable
def _start_build_job(
    player_state: StarRole,
    build_kind: str,
    builder_uid: str,
    x: float,
    y: float,
    total_ticks: int,
):
    player_state.active_job_kind = "build"
    player_state.active_job_payload = build_kind
    player_state.active_job_target_uid = builder_uid
    player_state.active_job_scope = "global"
    player_state.active_job_total_ticks = total_ticks
    player_state.active_job_remaining_ticks = total_ticks
    player_state.active_job_progress_pct = 0
    player_state.active_job_spawn_x = x
    player_state.active_job_spawn_y = y
    player_state.active_job_label = "Construct " + build_kind
    player_state.visible_job_label = player_state.active_job_label
    player_state.visible_job_progress_pct = 0
    player_state.visible_job_remaining_ticks = total_ticks
    player_state.visible_job_total_ticks = total_ticks


player_controls = AbstractCodeBlock.begin(
    "starcraft_clone_player_controls",
    role_type=StarRole,
    role_selector=Role,
    owner_id=str,
    owner_bit=int,
    btn_mode_move=str,
    btn_mode_attack_move=str,
    btn_queue_next=str,
    btn_set_rally=str,
)
"""Per-player mouse control template."""


@unsafe_condition(ButtonCondition.begin(player_controls.btn_mode_move, player_controls.role_selector))
def set_mode_move(
    player_state: player_controls.role_type,
    state: Global["state", str],
):
    if state != "playing":
        return
    player_state.command_mode = "move"
    player_state.placement_reason = "Command mode: move."


@unsafe_condition(ButtonCondition.begin(player_controls.btn_mode_attack_move, player_controls.role_selector))
def set_mode_attack_move(
    player_state: player_controls.role_type,
    state: Global["state", str],
):
    if state != "playing":
        return
    player_state.command_mode = "attack_move"
    player_state.placement_reason = "Command mode: attack-move."


@unsafe_condition(ButtonCondition.begin(player_controls.btn_queue_next, player_controls.role_selector))
def arm_queue_order(
    player_state: player_controls.role_type,
    state: Global["state", str],
):
    if state != "playing":
        return
    player_state.queue_armed = True
    player_state.placement_reason = "Queue armed: next right-click is queued."


@unsafe_condition(ButtonCondition.begin(player_controls.btn_set_rally, player_controls.role_selector))
def arm_set_rally(
    player_state: player_controls.role_type,
    state: Global["state", str],
):
    if state != "playing":
        return
    player_state.pending_set_rally = True
    player_state.pending_build = ""
    player_state.placement_valid = False
    player_state.placement_reason = "Set rally: left click target point."


@unsafe_condition(MouseCondition.on_click("left", player_controls.role_selector))
def update_build_preview(
    scene: Scene,
    mouse: MouseInfo,
    player_state: player_controls.role_type,
    units: List[Unit],
    buildings: List[Building],
    state: Global["state", str],
):
    if state != "playing":
        return
    if player_state.pending_build == "" and (not player_state.pending_set_rally):
        return

    player_state.placement_preview_x = mouse.x
    player_state.placement_preview_y = mouse.y
    if player_state.pending_set_rally:
        player_state.placement_valid = True
        player_state.placement_reason = "Rally point preview."
        return

    reason = _placement_reason(
        scene,
        mouse.x,
        mouse.y,
        player_state.pending_build,
        player_state,
        units,
        buildings,
    )
    player_state.placement_valid = reason == ""
    if reason == "":
        player_state.placement_reason = "Placement valid."
    else:
        player_state.placement_reason = reason


@unsafe_condition(MouseCondition.end_click("left", player_controls.role_selector))
def handle_left_mouse(
    scene: Scene,
    mouse: MouseInfo,
    player_state: player_controls.role_type,
    units: List[Unit],
    buildings: List[Building],
    state: Global["state", str],
):
    if state != "playing":
        return

    if player_state.pending_set_rally:
        player_state.rally_x = mouse.x
        player_state.rally_y = mouse.y
        player_state.pending_set_rally = False
        player_state.placement_preview_x = mouse.x
        player_state.placement_preview_y = mouse.y
        player_state.placement_valid = True
        player_state.placement_reason = "Rally point updated."
        return

    if player_state.pending_build != "":
        x = mouse.x
        y = mouse.y
        player_state.placement_preview_x = x
        player_state.placement_preview_y = y
        selected_worker_uid = ""
        for unit in units:
            if not unit.active:
                continue
            if unit.owner_id != player_controls.owner_id:
                continue
            if unit.sprite != "worker":
                continue
            if unit.selected and selected_worker_uid == "":
                selected_worker_uid = unit.uid
        if selected_worker_uid == "":
            clicked_worker_uid = ""
            clicked_worker_d2 = 999999999
            for unit in units:
                if not unit.active:
                    continue
                if unit.owner_id != player_controls.owner_id:
                    continue
                if unit.sprite != "worker":
                    continue
                half_w = unit.w / 2 + 6
                half_h = unit.h / 2 + 6
                if unit.x < x - half_w or unit.x > x + half_w:
                    continue
                if unit.y < y - half_h or unit.y > y + half_h:
                    continue
                dx = unit.x - x
                dy = unit.y - y
                d2 = dx * dx + dy * dy
                if d2 < clicked_worker_d2:
                    clicked_worker_d2 = d2
                    clicked_worker_uid = unit.uid
            if clicked_worker_uid != "":
                for unit in units:
                    if not unit.active:
                        continue
                    if unit.owner_id != player_controls.owner_id:
                        continue
                    unit.selected = unit.uid == clicked_worker_uid
                player_state.selected_count = 1
                player_state.selected_building_uid = ""
                player_state.selected_building_type = ""
                _refresh_selection_ui(player_state)
                player_state.placement_reason = "Worker selected. Left click map to place building."
                return
            player_state.placement_valid = False
            player_state.placement_reason = "Select a worker first."
            return

        reason = _placement_reason(
            scene,
            x,
            y,
            player_state.pending_build,
            player_state,
            units,
            buildings,
        )
        if reason != "":
            player_state.placement_valid = False
            player_state.placement_reason = reason
            return

        if player_state.active_job_kind != "":
            player_state.placement_valid = False
            player_state.placement_reason = "Production queue busy."
            return

        builder_uid = ""
        for unit in units:
            if not unit.active:
                continue
            if unit.owner_id != player_controls.owner_id:
                continue
            if unit.sprite != "worker":
                continue
            if not unit.selected:
                continue
            if builder_uid == "":
                builder_uid = unit.uid
        if builder_uid == "":
            player_state.placement_valid = False
            player_state.placement_reason = "Select a worker first."
            return

        if player_state.pending_build == "supply":
            if player_state.minerals < COST_SUPPLY_M or player_state.gas < COST_SUPPLY_G:
                return
            player_state.minerals = player_state.minerals - COST_SUPPLY_M
            player_state.gas = player_state.gas - COST_SUPPLY_G
            _start_build_job(player_state, "supply", builder_uid, x, y, BUILD_TIME_SUPPLY)
        elif player_state.pending_build == "barracks":
            if player_state.minerals < COST_BARRACKS_M or player_state.gas < COST_BARRACKS_G:
                return
            player_state.minerals = player_state.minerals - COST_BARRACKS_M
            player_state.gas = player_state.gas - COST_BARRACKS_G
            _start_build_job(player_state, "barracks", builder_uid, x, y, BUILD_TIME_BARRACKS)
        elif player_state.pending_build == "refinery":
            if player_state.minerals < COST_REFINERY_M or player_state.gas < COST_REFINERY_G:
                return
            player_state.minerals = player_state.minerals - COST_REFINERY_M
            player_state.gas = player_state.gas - COST_REFINERY_G
            _start_build_job(player_state, "refinery", builder_uid, x, y, BUILD_TIME_REFINERY)
        elif player_state.pending_build == "factory":
            if player_state.minerals < COST_FACTORY_M or player_state.gas < COST_FACTORY_G:
                return
            player_state.minerals = player_state.minerals - COST_FACTORY_M
            player_state.gas = player_state.gas - COST_FACTORY_G
            _start_build_job(player_state, "factory", builder_uid, x, y, BUILD_TIME_FACTORY)
        elif player_state.pending_build == "lab":
            if player_state.minerals < COST_LAB_M or player_state.gas < COST_LAB_G:
                return
            player_state.minerals = player_state.minerals - COST_LAB_M
            player_state.gas = player_state.gas - COST_LAB_G
            _start_build_job(player_state, "lab", builder_uid, x, y, BUILD_TIME_LAB)

        built_name = player_state.pending_build
        player_state.pending_build = ""
        player_state.pending_set_rally = False
        player_state.placement_valid = True
        player_state.placement_reason = "Started construction: " + built_name + "."
        return

    min_x = mouse.pressed_x
    max_x = mouse.x
    min_y = mouse.pressed_y
    max_y = mouse.y
    if min_x > max_x:
        tmp = min_x
        min_x = max_x
        max_x = tmp
    if min_y > max_y:
        tmp = min_y
        min_y = max_y
        max_y = tmp

    drag_w = max_x - min_x
    drag_h = max_y - min_y
    selected_count = 0

    if drag_w <= 6 and drag_h <= 6:
        clicked_unit_uid = ""
        clicked_unit_d2 = 999999999
        for unit in units:
            if not unit.active:
                continue
            if unit.owner_id != player_controls.owner_id:
                continue
            half_w = unit.w / 2 + 6
            half_h = unit.h / 2 + 6
            if unit.x < mouse.x - half_w or unit.x > mouse.x + half_w:
                continue
            if unit.y < mouse.y - half_h or unit.y > mouse.y + half_h:
                continue
            dx = unit.x - mouse.x
            dy = unit.y - mouse.y
            d2 = dx * dx + dy * dy
            if d2 < clicked_unit_d2:
                clicked_unit_d2 = d2
                clicked_unit_uid = unit.uid

        if clicked_unit_uid != "":
            for unit in units:
                if not unit.active:
                    continue
                if unit.owner_id != player_controls.owner_id:
                    continue
                unit.selected = unit.uid == clicked_unit_uid
            player_state.selected_count = 1
            player_state.placement_reason = "Selected unit."
            player_state.selected_building_uid = ""
            player_state.selected_building_type = ""
            _refresh_selection_ui(player_state)
            return

        clicked_building_uid = ""
        clicked_building_type = ""
        clicked_building_d2 = 999999999
        for building in buildings:
            if not building.active:
                continue
            if building.owner_id != player_controls.owner_id:
                continue
            half_w = building.w / 2 + 6
            half_h = building.h / 2 + 6
            if building.x < mouse.x - half_w or building.x > mouse.x + half_w:
                continue
            if building.y < mouse.y - half_h or building.y > mouse.y + half_h:
                continue
            dx = building.x - mouse.x
            dy = building.y - mouse.y
            d2 = dx * dx + dy * dy
            if d2 < clicked_building_d2:
                clicked_building_d2 = d2
                clicked_building_uid = building.uid
                clicked_building_type = building.sprite

        if clicked_building_uid != "":
            for unit in units:
                if not unit.active:
                    continue
                if unit.owner_id != player_controls.owner_id:
                    continue
                unit.selected = False
            player_state.selected_count = 0
            player_state.selected_building_uid = clicked_building_uid
            player_state.selected_building_type = clicked_building_type
            _refresh_selection_ui(player_state)
            player_state.placement_reason = "Selected " + clicked_building_type + "."
            return

        for unit in units:
            if not unit.active:
                continue
            if unit.owner_id != player_controls.owner_id:
                continue
            unit.selected = False
    else:
        for unit in units:
            if not unit.active:
                continue
            if unit.owner_id != player_controls.owner_id:
                continue
            if unit.x >= min_x and unit.x <= max_x and unit.y >= min_y and unit.y <= max_y:
                unit.selected = True
                selected_count = selected_count + 1
            else:
                unit.selected = False

    player_state.selected_building_uid = ""
    player_state.selected_building_type = ""
    _refresh_selection_ui(player_state)
    player_state.selected_count = selected_count


@unsafe_condition(MouseCondition.begin_click("right", player_controls.role_selector))
def issue_order(
    mouse: MouseInfo,
    player_state: player_controls.role_type,
    units: List[Unit],
    buildings: List[Building],
    state: Global["state", str],
):
    if state != "playing":
        return
    if player_state.pending_build != "":
        player_state.pending_build = ""
        player_state.pending_set_rally = False
        player_state.placement_valid = False
        player_state.placement_reason = "Build placement canceled."
        return

    selected_count = 0
    for unit in units:
        if not unit.active:
            continue
        if unit.owner_id != player_controls.owner_id:
            continue
        if not unit.selected:
            continue
        selected_count = selected_count + 1

    player_state.selected_count = selected_count
    if selected_count <= 0:
        return

    target_uid = ""

    for unit in units:
        if not unit.active:
            continue
        if unit.owner_id == player_controls.owner_id:
            continue
        if unit.x >= mouse.x - 24 and unit.x <= mouse.x + 24 and unit.y >= mouse.y - 24 and unit.y <= mouse.y + 24 and target_uid == "":
            target_uid = unit.uid

    for building in buildings:
        if target_uid != "":
            continue
        if not building.active:
            continue
        if building.owner_id == player_controls.owner_id:
            continue
        if building.x >= mouse.x - 32 and building.x <= mouse.x + 32 and building.y >= mouse.y - 32 and building.y <= mouse.y + 32:
            target_uid = building.uid

    can_attack_target = player_state.command_mode == "attack_move" and target_uid != ""

    slot_index = 0
    columns = 4
    if selected_count < columns:
        columns = selected_count
    if columns <= 0:
        columns = 1
    total_rows = 1
    remaining = selected_count
    while remaining > columns:
        remaining = remaining - columns
        total_rows = total_rows + 1
    row = 0
    col = 0
    for unit in units:
        if not unit.active:
            continue
        if unit.owner_id != player_controls.owner_id:
            continue
        if not unit.selected:
            continue

        if can_attack_target:
            if player_state.queue_armed:
                unit.has_queued_order = True
                unit.queued_order = "attack"
                unit.queued_target_uid = target_uid
                unit.queued_target_x = unit.target_x
                unit.queued_target_y = unit.target_y
            else:
                unit.order = "attack"
                unit.target_uid = target_uid
                unit.vx = 0
                unit.vy = 0
            slot_index = slot_index + 1
            continue

        col_center = col - (columns - 1) / 2
        row_center = row - (total_rows - 1) / 2
        next_order = "manual_move"
        if player_state.command_mode == "attack_move":
            next_order = "attack_move"

        if player_state.queue_armed:
            unit.has_queued_order = True
            unit.queued_order = next_order
            unit.queued_target_x = mouse.x + col_center * 24
            unit.queued_target_y = mouse.y + row_center * 24
            unit.queued_target_uid = ""
        else:
            unit.order = next_order
            unit.target_x = mouse.x + col_center * 24
            unit.target_y = mouse.y + row_center * 24
            unit.target_uid = ""
            unit.vx = 0
            unit.vy = 0
        slot_index = slot_index + 1
        col = col + 1
        if col >= columns:
            col = 0
            row = row + 1

    if player_state.queue_armed:
        player_state.queue_armed = False
        player_state.placement_reason = "Queued one order."

    player_state.selected_count = slot_index


player_controls.end()


player_controls.instantiate(
    role_type=StarRole["human_1"],
    role_selector=Role["human_1"],
    owner_id="human_1",
    owner_bit=1,
    btn_mode_move="h1_mode_move",
    btn_mode_attack_move="h1_mode_attack_move",
    btn_queue_next="h1_queue_next",
    btn_set_rally="h1_set_rally",
)

player_controls.instantiate(
    role_type=StarRole["human_2"],
    role_selector=Role["human_2"],
    owner_id="human_2",
    owner_bit=2,
    btn_mode_move="h2_mode_move",
    btn_mode_attack_move="h2_mode_attack_move",
    btn_queue_next="h2_queue_next",
    btn_set_rally="h2_set_rally",
)


camera_controls = AbstractCodeBlock.begin(
    "starcraft_clone_camera_controls",
    role_selector=Role,
    camera_selector=Camera,
    follow_uid=str,
    key_up=str,
    key_left=str,
    key_down=str,
    key_right=str,
    key_reset=str,
)
"""Per-role camera panning controls (fog of war remains enforced server-side)."""


@unsafe_condition(KeyboardCondition.on_press(camera_controls.key_up, camera_controls.role_selector))
def camera_pan_up(camera: camera_controls.camera_selector, state: Global["state", str]):
    if state != "playing" and state != "ended":
        return
    camera.translate(0, -CAMERA_PAN_SPEED)


@unsafe_condition(KeyboardCondition.on_press(camera_controls.key_left, camera_controls.role_selector))
def camera_pan_left(camera: camera_controls.camera_selector, state: Global["state", str]):
    if state != "playing" and state != "ended":
        return
    camera.translate(-CAMERA_PAN_SPEED, 0)


@unsafe_condition(KeyboardCondition.on_press(camera_controls.key_down, camera_controls.role_selector))
def camera_pan_down(camera: camera_controls.camera_selector, state: Global["state", str]):
    if state != "playing" and state != "ended":
        return
    camera.translate(0, CAMERA_PAN_SPEED)


@unsafe_condition(KeyboardCondition.on_press(camera_controls.key_right, camera_controls.role_selector))
def camera_pan_right(camera: camera_controls.camera_selector, state: Global["state", str]):
    if state != "playing" and state != "ended":
        return
    camera.translate(CAMERA_PAN_SPEED, 0)


@unsafe_condition(KeyboardCondition.begin_press(camera_controls.key_reset, camera_controls.role_selector))
def camera_recenter(camera: camera_controls.camera_selector, state: Global["state", str]):
    if state != "playing" and state != "ended":
        return
    camera.follow(camera_controls.follow_uid)


camera_controls.end()

camera_controls.instantiate(
    role_selector=Role["human_1"],
    camera_selector=Camera["camera_h1"],
    follow_uid="p1_hq",
    key_up="ArrowUp",
    key_left="ArrowLeft",
    key_down="ArrowDown",
    key_right="ArrowRight",
    key_reset="f",
)

camera_controls.instantiate(
    role_selector=Role["human_2"],
    camera_selector=Camera["camera_h2"],
    follow_uid="p2_hq",
    key_up="ArrowUp",
    key_left="ArrowLeft",
    key_down="ArrowDown",
    key_right="ArrowRight",
    key_reset="f",
)


CodeBlock.end("starcraft_clone_controls")
