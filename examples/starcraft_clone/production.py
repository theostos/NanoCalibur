from typing import List

from nanocalibur.dsl_markers import (
    AbstractCodeBlock,
    ButtonCondition,
    CodeBlock,
    Global,
    OnLogicalCondition,
    Random,
    Role,
    Scene,
    callable,
    safe_condition,
    unsafe_condition,
)

from .constants import (
    BARRACKS_HP,
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
    COST_MARAUDER_G,
    COST_MARAUDER_M,
    COST_MARINE_G,
    COST_MARINE_M,
    COST_MEDIC_G,
    COST_MEDIC_M,
    COST_REFINERY_G,
    COST_REFINERY_M,
    COST_SCOUT_G,
    COST_SCOUT_M,
    COST_SUPPLY_G,
    COST_SUPPLY_M,
    COST_TANK_G,
    COST_TANK_M,
    COST_UPGRADE_ARMOR_G,
    COST_UPGRADE_ARMOR_M,
    COST_UPGRADE_ATTACK_G,
    COST_UPGRADE_ATTACK_M,
    COST_WORKER_G,
    COST_WORKER_M,
    FACTORY_HP,
    LAB_HP,
    MARAUDER_ARMOR,
    MARAUDER_ATTACK,
    MARAUDER_HP,
    MARAUDER_SPEED,
    MARINE_ARMOR,
    MARINE_ATTACK,
    MARINE_HP,
    MARINE_SPEED,
    MEDIC_ARMOR,
    MEDIC_ATTACK,
    MEDIC_HEAL,
    MEDIC_HP,
    MEDIC_SPEED,
    REFINERY_HP,
    SCOUT_ARMOR,
    SCOUT_ATTACK,
    SCOUT_HP,
    SCOUT_SPEED,
    SUPPLY_DEPOT_BONUS,
    SUPPLY_DEPOT_HP,
    SUPPLY_MARAUDER,
    SUPPLY_MARINE,
    SUPPLY_MEDIC,
    SUPPLY_SCOUT,
    SUPPLY_TANK,
    SUPPLY_WORKER,
    TANK_ARMOR,
    TANK_ATTACK,
    TANK_HP,
    TANK_SPEED,
    TRAIN_TIME_MARAUDER,
    TRAIN_TIME_MARINE,
    TRAIN_TIME_MEDIC,
    TRAIN_TIME_SCOUT,
    TRAIN_TIME_TANK,
    TRAIN_TIME_WORKER,
    UPGRADE_TIME_ARMOR,
    UPGRADE_TIME_ATTACK,
    WORKER_ARMOR,
    WORKER_ATTACK,
    WORKER_GATHER,
    WORKER_HP,
    WORKER_SPEED,
    MAP_COLS,
    MAP_ROWS,
    TILE,
)
from .schemas import (
    Barracks,
    Building,
    Factory,
    HQ,
    Lab,
    Marauder,
    Marine,
    Medic,
    Refinery,
    Scout,
    StarRole,
    SupplyDepot,
    Tank,
    Unit,
    Worker,
)


CodeBlock.begin("starcraft_clone_production")
"""Reusable per-player production block: queueing, delays, completion spawn/research."""



def active_hq(hq: HQ) -> bool:
    return hq.active


@callable
def _set_visible_job(role_state: StarRole):
    if role_state.active_job_kind == "":
        role_state.visible_job_label = ""
        role_state.visible_job_progress_pct = 0
        role_state.visible_job_remaining_ticks = 0
        role_state.visible_job_total_ticks = 0
        return

    if (
        role_state.active_job_scope == "selected"
        and role_state.selected_building_uid != role_state.active_job_target_uid
    ):
        role_state.visible_job_label = "Select " + role_state.active_job_target_uid + " to view queue."
        role_state.visible_job_progress_pct = 0
        role_state.visible_job_remaining_ticks = 0
        role_state.visible_job_total_ticks = role_state.active_job_total_ticks
        return

    role_state.visible_job_label = role_state.active_job_label
    role_state.visible_job_progress_pct = role_state.active_job_progress_pct
    role_state.visible_job_remaining_ticks = role_state.active_job_remaining_ticks
    role_state.visible_job_total_ticks = role_state.active_job_total_ticks


@callable
def _start_job(
    role_state: StarRole,
    kind: str,
    payload: str,
    target_uid: str,
    scope: str,
    total_ticks: int,
    label: str,
):
    role_state.active_job_kind = kind
    role_state.active_job_payload = payload
    role_state.active_job_target_uid = target_uid
    role_state.active_job_scope = scope
    role_state.active_job_total_ticks = total_ticks
    role_state.active_job_remaining_ticks = total_ticks
    role_state.active_job_progress_pct = 0
    role_state.active_job_label = label
    _set_visible_job(role_state)


@callable
def _clear_job(role_state: StarRole):
    role_state.active_job_kind = ""
    role_state.active_job_payload = ""
    role_state.active_job_target_uid = ""
    role_state.active_job_scope = ""
    role_state.active_job_total_ticks = 0
    role_state.active_job_remaining_ticks = 0
    role_state.active_job_progress_pct = 0
    role_state.active_job_label = ""
    role_state.active_job_spawn_x = 0.0
    role_state.active_job_spawn_y = 0.0
    _set_visible_job(role_state)


@callable
def _job_busy(role_state: StarRole):
    return role_state.active_job_kind != ""


@callable
def _refresh_ui_from_selected_building(role_state: StarRole):
    role_state.ui_show_hq_controls = "none"
    role_state.ui_show_barracks_controls = "none"
    role_state.ui_show_factory_controls = "none"
    role_state.ui_show_lab_controls = "none"
    if role_state.selected_building_type == "hq":
        role_state.ui_show_hq_controls = "flex"
    elif role_state.selected_building_type == "barracks":
        role_state.ui_show_barracks_controls = "flex"
    elif role_state.selected_building_type == "factory":
        role_state.ui_show_factory_controls = "flex"
    elif role_state.selected_building_type == "lab":
        role_state.ui_show_lab_controls = "flex"


@callable
def _rollback_reserved_supply(role_state: StarRole, payload: str):
    if payload == "worker":
        role_state.supply_used = role_state.supply_used - SUPPLY_WORKER
    elif payload == "marine":
        role_state.supply_used = role_state.supply_used - SUPPLY_MARINE
    elif payload == "marauder":
        role_state.supply_used = role_state.supply_used - SUPPLY_MARAUDER
    elif payload == "medic":
        role_state.supply_used = role_state.supply_used - SUPPLY_MEDIC
    elif payload == "tank":
        role_state.supply_used = role_state.supply_used - SUPPLY_TANK
    elif payload == "scout":
        role_state.supply_used = role_state.supply_used - SUPPLY_SCOUT


@callable
def _build_half_size(payload: str):
    if payload == "supply":
        return 14
    if payload == "barracks":
        return 16
    if payload == "refinery":
        return 15
    if payload == "factory":
        return 17
    if payload == "lab":
        return 15
    return 16


@callable
def _is_spawn_open(
    scene: Scene,
    x: float,
    y: float,
    half: float,
    units: List[Unit],
    buildings: List[Building],
):
    world_w = MAP_COLS * TILE
    world_h = MAP_ROWS * TILE
    left = x - half
    right = x + half
    top = y - half
    bottom = y + half

    if left < 0 or right >= world_w or top < 0 or bottom >= world_h:
        return False

    if scene.is_solid_at(left, top) or scene.is_solid_at(right, top):
        return False
    if scene.is_solid_at(left, bottom) or scene.is_solid_at(right, bottom):
        return False
    if scene.is_solid_at(x, y):
        return False
    if scene.is_solid_at(x, top) or scene.is_solid_at(x, bottom):
        return False
    if scene.is_solid_at(left, y) or scene.is_solid_at(right, y):
        return False

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
        return False

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
        return False

    return True


player_rules = AbstractCodeBlock.begin(
    "starcraft_clone_player_rules",
    role_type=StarRole,
    role_selector=Role,
    owner_id=str,
    owner_bit=int,
    rally_x=int,
    rally_y=int,
    worker_spawn_x=int,
    worker_spawn_y=int,
    worker_harvest_x=int,
    worker_harvest_y=int,
    worker_harvest_uid=str,
    home_hq_uid=str,
    march_dir=int,
    enemy_base_x=int,
    enemy_base_y=int,
    btn_build_supply=str,
    btn_build_barracks=str,
    btn_build_refinery=str,
    btn_build_factory=str,
    btn_build_lab=str,
    btn_train_worker=str,
    btn_train_marine=str,
    btn_train_marauder=str,
    btn_train_medic=str,
    btn_train_tank=str,
    btn_train_scout=str,
    btn_upgrade_attack=str,
    btn_upgrade_armor=str,
)
"""Per-player production commands generated from one template."""


@unsafe_condition(ButtonCondition.begin(player_rules.btn_build_supply, player_rules.role_selector))
def queue_build_supply(
    player_state: player_rules.role_type,
    state: Global["state", str],
):
    if state != "playing":
        return
    if _job_busy(player_state):
        player_state.placement_reason = "Production queue busy."
        return
    player_state.pending_build = "supply"
    player_state.pending_set_rally = False
    player_state.placement_valid = False
    player_state.placement_reason = "Place Supply Depot: left click on map."


@unsafe_condition(ButtonCondition.begin(player_rules.btn_build_barracks, player_rules.role_selector))
def queue_build_barracks(
    player_state: player_rules.role_type,
    state: Global["state", str],
):
    if state != "playing":
        return
    if _job_busy(player_state):
        player_state.placement_reason = "Production queue busy."
        return
    if not player_state.has_supply:
        player_state.placement_valid = False
        player_state.placement_reason = "Build Supply Depot first."
        return
    player_state.pending_build = "barracks"
    player_state.pending_set_rally = False
    player_state.placement_valid = False
    player_state.placement_reason = "Place Barracks: left click on map."


@unsafe_condition(ButtonCondition.begin(player_rules.btn_build_refinery, player_rules.role_selector))
def queue_build_refinery(
    player_state: player_rules.role_type,
    state: Global["state", str],
):
    if state != "playing":
        return
    if _job_busy(player_state):
        player_state.placement_reason = "Production queue busy."
        return
    if not player_state.has_supply:
        player_state.placement_valid = False
        player_state.placement_reason = "Build Supply Depot first."
        return
    player_state.pending_build = "refinery"
    player_state.pending_set_rally = False
    player_state.placement_valid = False
    player_state.placement_reason = "Place Refinery: left click on map."


@unsafe_condition(ButtonCondition.begin(player_rules.btn_build_factory, player_rules.role_selector))
def queue_build_factory(
    player_state: player_rules.role_type,
    state: Global["state", str],
):
    if state != "playing":
        return
    if _job_busy(player_state):
        player_state.placement_reason = "Production queue busy."
        return
    if (not player_state.has_barracks) or (not player_state.has_refinery):
        player_state.placement_valid = False
        player_state.placement_reason = "Need Barracks + Refinery first."
        return
    player_state.pending_build = "factory"
    player_state.pending_set_rally = False
    player_state.placement_valid = False
    player_state.placement_reason = "Place Factory: left click on map."


@unsafe_condition(ButtonCondition.begin(player_rules.btn_build_lab, player_rules.role_selector))
def queue_build_lab(
    player_state: player_rules.role_type,
    state: Global["state", str],
):
    if state != "playing":
        return
    if _job_busy(player_state):
        player_state.placement_reason = "Production queue busy."
        return
    if not player_state.has_factory:
        player_state.placement_valid = False
        player_state.placement_reason = "Need Factory first."
        return
    player_state.pending_build = "lab"
    player_state.pending_set_rally = False
    player_state.placement_valid = False
    player_state.placement_reason = "Place Lab: left click on map."


@unsafe_condition(ButtonCondition.begin(player_rules.btn_train_worker, player_rules.role_selector))
def train_worker(
    player_state: player_rules.role_type,
    state: Global["state", str],
):
    if state != "playing":
        return
    if _job_busy(player_state):
        return
    if player_state.selected_building_type != "hq" or player_state.selected_building_uid == "":
        player_state.placement_reason = "Select your HQ to train workers."
        return
    if player_state.minerals < COST_WORKER_M or player_state.gas < COST_WORKER_G:
        return
    if player_state.supply_used + SUPPLY_WORKER > player_state.supply_cap:
        return

    player_state.minerals = player_state.minerals - COST_WORKER_M
    player_state.gas = player_state.gas - COST_WORKER_G
    player_state.supply_used = player_state.supply_used + SUPPLY_WORKER
    _start_job(
        player_state,
        "unit",
        "worker",
        player_state.selected_building_uid,
        "selected",
        TRAIN_TIME_WORKER,
        "Training Worker",
    )


@unsafe_condition(ButtonCondition.begin(player_rules.btn_train_marine, player_rules.role_selector))
def train_marine(
    player_state: player_rules.role_type,
    state: Global["state", str],
):
    if state != "playing":
        return
    if _job_busy(player_state):
        return
    if player_state.selected_building_type != "barracks" or player_state.selected_building_uid == "":
        player_state.placement_reason = "Select your Barracks to train marines."
        return
    if not player_state.has_barracks:
        return
    if player_state.minerals < COST_MARINE_M or player_state.gas < COST_MARINE_G:
        return
    if player_state.supply_used + SUPPLY_MARINE > player_state.supply_cap:
        return

    player_state.minerals = player_state.minerals - COST_MARINE_M
    player_state.gas = player_state.gas - COST_MARINE_G
    player_state.supply_used = player_state.supply_used + SUPPLY_MARINE
    _start_job(
        player_state,
        "unit",
        "marine",
        player_state.selected_building_uid,
        "selected",
        TRAIN_TIME_MARINE,
        "Training Marine",
    )


@unsafe_condition(ButtonCondition.begin(player_rules.btn_train_marauder, player_rules.role_selector))
def train_marauder(
    player_state: player_rules.role_type,
    state: Global["state", str],
):
    if state != "playing":
        return
    if _job_busy(player_state):
        return
    if player_state.selected_building_type != "barracks" or player_state.selected_building_uid == "":
        player_state.placement_reason = "Select your Barracks to train marauders."
        return
    if (not player_state.has_barracks) or (not player_state.has_refinery):
        return
    if player_state.minerals < COST_MARAUDER_M or player_state.gas < COST_MARAUDER_G:
        return
    if player_state.supply_used + SUPPLY_MARAUDER > player_state.supply_cap:
        return

    player_state.minerals = player_state.minerals - COST_MARAUDER_M
    player_state.gas = player_state.gas - COST_MARAUDER_G
    player_state.supply_used = player_state.supply_used + SUPPLY_MARAUDER
    _start_job(
        player_state,
        "unit",
        "marauder",
        player_state.selected_building_uid,
        "selected",
        TRAIN_TIME_MARAUDER,
        "Training Marauder",
    )


@unsafe_condition(ButtonCondition.begin(player_rules.btn_train_medic, player_rules.role_selector))
def train_medic(
    player_state: player_rules.role_type,
    state: Global["state", str],
):
    if state != "playing":
        return
    if _job_busy(player_state):
        return
    if player_state.selected_building_type != "barracks" or player_state.selected_building_uid == "":
        player_state.placement_reason = "Select your Barracks to train medics."
        return
    if (not player_state.has_barracks) or (not player_state.has_refinery):
        return
    if player_state.minerals < COST_MEDIC_M or player_state.gas < COST_MEDIC_G:
        return
    if player_state.supply_used + SUPPLY_MEDIC > player_state.supply_cap:
        return

    player_state.minerals = player_state.minerals - COST_MEDIC_M
    player_state.gas = player_state.gas - COST_MEDIC_G
    player_state.supply_used = player_state.supply_used + SUPPLY_MEDIC
    _start_job(
        player_state,
        "unit",
        "medic",
        player_state.selected_building_uid,
        "selected",
        TRAIN_TIME_MEDIC,
        "Training Medic",
    )


@unsafe_condition(ButtonCondition.begin(player_rules.btn_train_tank, player_rules.role_selector))
def train_tank(
    player_state: player_rules.role_type,
    state: Global["state", str],
):
    if state != "playing":
        return
    if _job_busy(player_state):
        return
    if player_state.selected_building_type != "factory" or player_state.selected_building_uid == "":
        player_state.placement_reason = "Select your Factory to train tanks."
        return
    if not player_state.has_factory:
        return
    if player_state.minerals < COST_TANK_M or player_state.gas < COST_TANK_G:
        return
    if player_state.supply_used + SUPPLY_TANK > player_state.supply_cap:
        return

    player_state.minerals = player_state.minerals - COST_TANK_M
    player_state.gas = player_state.gas - COST_TANK_G
    player_state.supply_used = player_state.supply_used + SUPPLY_TANK
    _start_job(
        player_state,
        "unit",
        "tank",
        player_state.selected_building_uid,
        "selected",
        TRAIN_TIME_TANK,
        "Training Tank",
    )


@unsafe_condition(ButtonCondition.begin(player_rules.btn_train_scout, player_rules.role_selector))
def train_scout(
    player_state: player_rules.role_type,
    state: Global["state", str],
):
    if state != "playing":
        return
    if _job_busy(player_state):
        return
    if player_state.selected_building_type != "factory" or player_state.selected_building_uid == "":
        player_state.placement_reason = "Select your Factory to train scouts."
        return
    if not player_state.has_lab:
        return
    if player_state.minerals < COST_SCOUT_M or player_state.gas < COST_SCOUT_G:
        return
    if player_state.supply_used + SUPPLY_SCOUT > player_state.supply_cap:
        return

    player_state.minerals = player_state.minerals - COST_SCOUT_M
    player_state.gas = player_state.gas - COST_SCOUT_G
    player_state.supply_used = player_state.supply_used + SUPPLY_SCOUT
    _start_job(
        player_state,
        "unit",
        "scout",
        player_state.selected_building_uid,
        "selected",
        TRAIN_TIME_SCOUT,
        "Training Scout",
    )


@unsafe_condition(ButtonCondition.begin(player_rules.btn_upgrade_attack, player_rules.role_selector))
def upgrade_attack(
    player_state: player_rules.role_type,
    state: Global["state", str],
):
    if state != "playing":
        return
    if _job_busy(player_state):
        return
    if player_state.selected_building_type != "lab" or player_state.selected_building_uid == "":
        player_state.placement_reason = "Select your Lab to research attack."
        return
    if not player_state.has_lab:
        return
    if player_state.minerals < COST_UPGRADE_ATTACK_M or player_state.gas < COST_UPGRADE_ATTACK_G:
        return

    player_state.minerals = player_state.minerals - COST_UPGRADE_ATTACK_M
    player_state.gas = player_state.gas - COST_UPGRADE_ATTACK_G
    _start_job(
        player_state,
        "upgrade",
        "attack",
        player_state.selected_building_uid,
        "selected",
        UPGRADE_TIME_ATTACK,
        "Researching Attack",
    )


@unsafe_condition(ButtonCondition.begin(player_rules.btn_upgrade_armor, player_rules.role_selector))
def upgrade_armor(
    player_state: player_rules.role_type,
    state: Global["state", str],
):
    if state != "playing":
        return
    if _job_busy(player_state):
        return
    if player_state.selected_building_type != "lab" or player_state.selected_building_uid == "":
        player_state.placement_reason = "Select your Lab to research armor."
        return
    if not player_state.has_lab:
        return
    if player_state.minerals < COST_UPGRADE_ARMOR_M or player_state.gas < COST_UPGRADE_ARMOR_G:
        return

    player_state.minerals = player_state.minerals - COST_UPGRADE_ARMOR_M
    player_state.gas = player_state.gas - COST_UPGRADE_ARMOR_G
    _start_job(
        player_state,
        "upgrade",
        "armor",
        player_state.selected_building_uid,
        "selected",
        UPGRADE_TIME_ARMOR,
        "Researching Armor",
    )


@safe_condition(OnLogicalCondition(active_hq, HQ))
def progress_role_job(
    scene: Scene,
    player_state: player_rules.role_type,
    units: List[Unit],
    buildings: List[Building],
    state: Global["state", str],
):
    if state != "playing":
        return

    if player_state.selected_building_uid != "":
        selected_exists = False
        selected_type = ""
        for building in buildings:
            if not building.active:
                continue
            if building.owner_id != player_rules.owner_id:
                continue
            if building.uid != player_state.selected_building_uid:
                continue
            selected_exists = True
            selected_type = building.sprite
        if not selected_exists:
            player_state.selected_building_uid = ""
            player_state.selected_building_type = ""
        else:
            player_state.selected_building_type = selected_type
        _refresh_ui_from_selected_building(player_state)

    if player_state.active_job_kind == "":
        _set_visible_job(player_state)
        return

    kind = player_state.active_job_kind
    payload = player_state.active_job_payload
    can_progress = True

    if kind == "build":
        builder_uid = player_state.active_job_target_uid
        if builder_uid == "":
            for unit in units:
                if not unit.active:
                    continue
                if unit.owner_id != player_rules.owner_id:
                    continue
                if unit.sprite != "worker":
                    continue
                if not unit.selected:
                    continue
                if builder_uid == "":
                    builder_uid = unit.uid
            if builder_uid != "":
                player_state.active_job_target_uid = builder_uid

        if builder_uid == "":
            can_progress = False
            player_state.placement_reason = "Build paused: select a worker to continue."
        else:
            build_half = _build_half_size(payload)
            build_margin = build_half + 14
            builder_exists = False
            builder_ready = False
            for unit in units:
                if not unit.active:
                    continue
                if unit.owner_id != player_rules.owner_id:
                    continue
                if unit.uid != builder_uid:
                    continue
                if unit.sprite != "worker":
                    continue
                builder_exists = True
                unit.order = "move"
                unit.target_uid = ""
                unit.target_x = player_state.active_job_spawn_x
                unit.target_y = player_state.active_job_spawn_y
                if (
                    unit.x >= player_state.active_job_spawn_x - build_margin
                    and unit.x <= player_state.active_job_spawn_x + build_margin
                    and unit.y >= player_state.active_job_spawn_y - build_margin
                    and unit.y <= player_state.active_job_spawn_y + build_margin
                ):
                    builder_ready = True
                    unit.order = "idle"
                    unit.vx = 0
                    unit.vy = 0

            if not builder_exists:
                can_progress = False
                player_state.active_job_target_uid = ""
                player_state.placement_reason = "Build paused: assigned worker missing."
            elif not builder_ready:
                can_progress = False
                player_state.placement_reason = "Build paused: worker en route."

    if can_progress:
        player_state.active_job_remaining_ticks = player_state.active_job_remaining_ticks - 1
        if player_state.active_job_remaining_ticks < 0:
            player_state.active_job_remaining_ticks = 0

    if player_state.active_job_total_ticks > 0:
        done_ticks = player_state.active_job_total_ticks - player_state.active_job_remaining_ticks
        if done_ticks < 0:
            done_ticks = 0
        player_state.active_job_progress_pct = (done_ticks * 100) / player_state.active_job_total_ticks
    else:
        player_state.active_job_progress_pct = 100

    _set_visible_job(player_state)

    if (not can_progress) or player_state.active_job_remaining_ticks > 0:
        return

    if kind == "upgrade":
        if payload == "attack":
            player_state.upgrade_attack = player_state.upgrade_attack + 1
        elif payload == "armor":
            player_state.upgrade_armor = player_state.upgrade_armor + 1
        _clear_job(player_state)
        return

    if kind == "build":
        x = player_state.active_job_spawn_x
        y = player_state.active_job_spawn_y
        uid = player_rules.owner_id + "_" + payload + "_" + Random.string(8, "abcdefghijklmnopqrstuvwxyz0123456789")

        if payload == "supply":
            scene.spawn(
                SupplyDepot(
                    uid=uid,
                    x=x,
                    y=y,
                    w=28,
                    h=28,
                    owner_id=player_rules.owner_id,
                    visible_mask=player_rules.owner_bit,
                    hp=SUPPLY_DEPOT_HP,
                    max_hp=SUPPLY_DEPOT_HP,
                    supply_provided=8,
                    block_mask=1,
                    sprite="supply",
                )
            )
            player_state.has_supply = True
            player_state.supply_cap = player_state.supply_cap + SUPPLY_DEPOT_BONUS
        elif payload == "barracks":
            scene.spawn(
                Barracks(
                    uid=uid,
                    x=x,
                    y=y,
                    w=32,
                    h=32,
                    owner_id=player_rules.owner_id,
                    visible_mask=player_rules.owner_bit,
                    hp=BARRACKS_HP,
                    max_hp=BARRACKS_HP,
                    supply_provided=0,
                    block_mask=1,
                    sprite="barracks",
                )
            )
            player_state.has_barracks = True
        elif payload == "refinery":
            scene.spawn(
                Refinery(
                    uid=uid,
                    x=x,
                    y=y,
                    w=30,
                    h=30,
                    owner_id=player_rules.owner_id,
                    visible_mask=player_rules.owner_bit,
                    hp=REFINERY_HP,
                    max_hp=REFINERY_HP,
                    supply_provided=0,
                    block_mask=1,
                    sprite="refinery",
                )
            )
            player_state.has_refinery = True
        elif payload == "factory":
            scene.spawn(
                Factory(
                    uid=uid,
                    x=x,
                    y=y,
                    w=34,
                    h=34,
                    owner_id=player_rules.owner_id,
                    visible_mask=player_rules.owner_bit,
                    hp=FACTORY_HP,
                    max_hp=FACTORY_HP,
                    supply_provided=0,
                    block_mask=1,
                    sprite="factory",
                )
            )
            player_state.has_factory = True
        elif payload == "lab":
            scene.spawn(
                Lab(
                    uid=uid,
                    x=x,
                    y=y,
                    w=30,
                    h=30,
                    owner_id=player_rules.owner_id,
                    visible_mask=player_rules.owner_bit,
                    hp=LAB_HP,
                    max_hp=LAB_HP,
                    supply_provided=0,
                    block_mask=1,
                    sprite="lab",
                )
            )
            player_state.has_lab = True

        _clear_job(player_state)
        return

    if kind == "unit":
        producer_x = player_rules.worker_spawn_x
        producer_y = player_rules.worker_spawn_y
        producer_w = 32
        producer_h = 32
        producer_found = False
        for building in buildings:
            if not building.active:
                continue
            if building.owner_id != player_rules.owner_id:
                continue
            if building.uid != player_state.active_job_target_uid:
                continue
            producer_x = building.x
            producer_y = building.y
            producer_w = building.w
            producer_h = building.h
            producer_found = True

        if not producer_found:
            _rollback_reserved_supply(player_state, payload)
            _clear_job(player_state)
            return

        half = 11
        edge_x = producer_w / 2 + half + 2
        edge_y = producer_h / 2 + half + 2
        spawn_x = producer_x + edge_x
        spawn_y = producer_y
        found_spawn = _is_spawn_open(scene, spawn_x, spawn_y, half, units, buildings)
        if not found_spawn:
            spawn_x = producer_x - edge_x
            spawn_y = producer_y
            found_spawn = _is_spawn_open(scene, spawn_x, spawn_y, half, units, buildings)
        if not found_spawn:
            spawn_x = producer_x
            spawn_y = producer_y + edge_y
            found_spawn = _is_spawn_open(scene, spawn_x, spawn_y, half, units, buildings)
        if not found_spawn:
            spawn_x = producer_x
            spawn_y = producer_y - edge_y
            found_spawn = _is_spawn_open(scene, spawn_x, spawn_y, half, units, buildings)
        if not found_spawn:
            spawn_x = producer_x + edge_x
            spawn_y = producer_y + edge_y
            found_spawn = _is_spawn_open(scene, spawn_x, spawn_y, half, units, buildings)
        if not found_spawn:
            spawn_x = producer_x + edge_x
            spawn_y = producer_y - edge_y
            found_spawn = _is_spawn_open(scene, spawn_x, spawn_y, half, units, buildings)
        if not found_spawn:
            spawn_x = producer_x - edge_x
            spawn_y = producer_y + edge_y
            found_spawn = _is_spawn_open(scene, spawn_x, spawn_y, half, units, buildings)
        if not found_spawn:
            spawn_x = producer_x - edge_x
            spawn_y = producer_y - edge_y
            found_spawn = _is_spawn_open(scene, spawn_x, spawn_y, half, units, buildings)
        if not found_spawn:
            _rollback_reserved_supply(player_state, payload)
            player_state.placement_reason = "Spawn blocked near " + player_state.active_job_target_uid + "."
            _clear_job(player_state)
            return

        uid = player_rules.owner_id + "_" + payload + "_" + Random.string(8, "abcdefghijklmnopqrstuvwxyz0123456789")

        if payload == "worker":
            scene.spawn(
                Worker(
                    uid=uid,
                    x=spawn_x,
                    y=spawn_y,
                    w=18,
                    h=18,
                    owner_id=player_rules.owner_id,
                    hp=WORKER_HP,
                    max_hp=WORKER_HP,
                    attack=WORKER_ATTACK,
                    armor=WORKER_ARMOR,
                    speed=WORKER_SPEED,
                    supply=SUPPLY_WORKER,
                    visible_mask=player_rules.owner_bit,
                    march_dir=player_rules.march_dir,
                    gather_per_tick=WORKER_GATHER,
                    cargo_minerals=0,
                    cargo_gas=0,
                    harvest_target_uid=player_rules.worker_harvest_uid,
                    harvest_resource="mineral",
                    home_hq_uid=player_rules.home_hq_uid,
                    selected=False,
                    order="move",
                    target_x=player_rules.worker_harvest_x,
                    target_y=player_rules.worker_harvest_y,
                    target_uid=player_rules.worker_harvest_uid,
                    has_queued_order=False,
                    queued_order="idle",
                    queued_target_x=player_rules.worker_harvest_x,
                    queued_target_y=player_rules.worker_harvest_y,
                    queued_target_uid="",
                    block_mask=1,
                    sprite="worker",
                )
            )
        elif payload == "marine":
            scene.spawn(
                Marine(
                    uid=uid,
                    x=spawn_x,
                    y=spawn_y,
                    w=18,
                    h=18,
                    owner_id=player_rules.owner_id,
                    hp=MARINE_HP,
                    max_hp=MARINE_HP,
                    attack=MARINE_ATTACK,
                    armor=MARINE_ARMOR,
                    speed=MARINE_SPEED,
                    supply=SUPPLY_MARINE,
                    visible_mask=player_rules.owner_bit,
                    march_dir=player_rules.march_dir,
                    selected=False,
                    order="move",
                    target_x=player_state.rally_x,
                    target_y=player_state.rally_y,
                    target_uid="",
                    has_queued_order=False,
                    queued_order="idle",
                    queued_target_x=player_state.rally_x,
                    queued_target_y=player_state.rally_y,
                    queued_target_uid="",
                    block_mask=1,
                    sprite="marine",
                )
            )
        elif payload == "marauder":
            scene.spawn(
                Marauder(
                    uid=uid,
                    x=spawn_x,
                    y=spawn_y,
                    w=20,
                    h=20,
                    owner_id=player_rules.owner_id,
                    hp=MARAUDER_HP,
                    max_hp=MARAUDER_HP,
                    attack=MARAUDER_ATTACK,
                    armor=MARAUDER_ARMOR,
                    speed=MARAUDER_SPEED,
                    supply=SUPPLY_MARAUDER,
                    visible_mask=player_rules.owner_bit,
                    march_dir=player_rules.march_dir,
                    selected=False,
                    order="move",
                    target_x=player_state.rally_x,
                    target_y=player_state.rally_y,
                    target_uid="",
                    has_queued_order=False,
                    queued_order="idle",
                    queued_target_x=player_state.rally_x,
                    queued_target_y=player_state.rally_y,
                    queued_target_uid="",
                    block_mask=1,
                    sprite="marauder",
                )
            )
        elif payload == "medic":
            scene.spawn(
                Medic(
                    uid=uid,
                    x=spawn_x,
                    y=spawn_y,
                    w=18,
                    h=18,
                    owner_id=player_rules.owner_id,
                    hp=MEDIC_HP,
                    max_hp=MEDIC_HP,
                    attack=MEDIC_ATTACK,
                    armor=MEDIC_ARMOR,
                    speed=MEDIC_SPEED,
                    heal_per_tick=MEDIC_HEAL,
                    supply=SUPPLY_MEDIC,
                    visible_mask=player_rules.owner_bit,
                    march_dir=player_rules.march_dir,
                    selected=False,
                    order="move",
                    target_x=player_state.rally_x,
                    target_y=player_state.rally_y,
                    target_uid="",
                    has_queued_order=False,
                    queued_order="idle",
                    queued_target_x=player_state.rally_x,
                    queued_target_y=player_state.rally_y,
                    queued_target_uid="",
                    block_mask=1,
                    sprite="medic",
                )
            )
        elif payload == "tank":
            scene.spawn(
                Tank(
                    uid=uid,
                    x=spawn_x,
                    y=spawn_y,
                    w=22,
                    h=22,
                    owner_id=player_rules.owner_id,
                    hp=TANK_HP,
                    max_hp=TANK_HP,
                    attack=TANK_ATTACK,
                    armor=TANK_ARMOR,
                    speed=TANK_SPEED,
                    supply=SUPPLY_TANK,
                    visible_mask=player_rules.owner_bit,
                    march_dir=player_rules.march_dir,
                    selected=False,
                    order="move",
                    target_x=player_state.rally_x,
                    target_y=player_state.rally_y,
                    target_uid="",
                    has_queued_order=False,
                    queued_order="idle",
                    queued_target_x=player_state.rally_x,
                    queued_target_y=player_state.rally_y,
                    queued_target_uid="",
                    block_mask=1,
                    sprite="tank",
                )
            )
        elif payload == "scout":
            scene.spawn(
                Scout(
                    uid=uid,
                    x=spawn_x,
                    y=spawn_y,
                    w=18,
                    h=18,
                    owner_id=player_rules.owner_id,
                    hp=SCOUT_HP,
                    max_hp=SCOUT_HP,
                    attack=SCOUT_ATTACK,
                    armor=SCOUT_ARMOR,
                    speed=SCOUT_SPEED,
                    supply=SUPPLY_SCOUT,
                    visible_mask=player_rules.owner_bit,
                    march_dir=player_rules.march_dir,
                    selected=False,
                    order="move",
                    target_x=player_state.rally_x,
                    target_y=player_state.rally_y,
                    target_uid="",
                    has_queued_order=False,
                    queued_order="idle",
                    queued_target_x=player_state.rally_x,
                    queued_target_y=player_state.rally_y,
                    queued_target_uid="",
                    block_mask=1,
                    sprite="scout",
                )
            )

        _clear_job(player_state)


player_rules.end()


player_rules.instantiate(
    role_type=StarRole["human_1"],
    role_selector=Role["human_1"],
    owner_id="human_1",
    owner_bit=1,
    rally_x=448,
    rally_y=576,
    worker_spawn_x=256,
    worker_spawn_y=576,
    worker_harvest_x=288,
    worker_harvest_y=416,
    worker_harvest_uid="p1_minerals_a",
    home_hq_uid="p1_hq",
    march_dir=1,
    enemy_base_x=1824,
    enemy_base_y=576,
    btn_build_supply="h1_build_supply",
    btn_build_barracks="h1_build_barracks",
    btn_build_refinery="h1_build_refinery",
    btn_build_factory="h1_build_factory",
    btn_build_lab="h1_build_lab",
    btn_train_worker="h1_train_worker",
    btn_train_marine="h1_train_marine",
    btn_train_marauder="h1_train_marauder",
    btn_train_medic="h1_train_medic",
    btn_train_tank="h1_train_tank",
    btn_train_scout="h1_train_scout",
    btn_upgrade_attack="h1_upg_attack",
    btn_upgrade_armor="h1_upg_armor",
)

player_rules.instantiate(
    role_type=StarRole["human_2"],
    role_selector=Role["human_2"],
    owner_id="human_2",
    owner_bit=2,
    rally_x=1600,
    rally_y=576,
    worker_spawn_x=1792,
    worker_spawn_y=576,
    worker_harvest_x=1760,
    worker_harvest_y=416,
    worker_harvest_uid="p2_minerals_a",
    home_hq_uid="p2_hq",
    march_dir=-1,
    enemy_base_x=224,
    enemy_base_y=576,
    btn_build_supply="h2_build_supply",
    btn_build_barracks="h2_build_barracks",
    btn_build_refinery="h2_build_refinery",
    btn_build_factory="h2_build_factory",
    btn_build_lab="h2_build_lab",
    btn_train_worker="h2_train_worker",
    btn_train_marine="h2_train_marine",
    btn_train_marauder="h2_train_marauder",
    btn_train_medic="h2_train_medic",
    btn_train_tank="h2_train_tank",
    btn_train_scout="h2_train_scout",
    btn_upgrade_attack="h2_upg_attack",
    btn_upgrade_armor="h2_upg_armor",
)


CodeBlock.end("starcraft_clone_production")
