from nanocalibur.dsl_markers import CodeBlock, HumanRole, Interface, RoleKind

from .shared import MAP_HEIGHT_TILES, MAP_WIDTH_TILES, game, scene


CodeBlock.begin("multiplayer_roles")
"""Two-player setup with shared RTS resources and per-role selection state."""

FOG_TILE_COUNT = MAP_WIDTH_TILES * MAP_HEIGHT_TILES


class RTSRole(HumanRole):
    minerals: int
    gas: int
    supply_used: int
    supply_cap: int
    selected_uid: str
    selected_name: str
    selected_count: int
    selected_uids: list[str]
    selected_kind: str
    selected_hp: int
    selected_max_hp: int
    selected_task_active: bool
    selected_task_label: str
    selected_task_percent: int
    selected_task_bar: str
    selected_task_seconds_left: float
    can_train_worker: bool
    can_build_hq: bool
    can_build_supply_depot: bool
    can_build_barracks: bool
    can_build_academy: bool
    can_build_starport: bool
    can_upgrade_attack: bool
    can_upgrade_armor: bool
    can_cancel_construction: bool
    attack_upgrade_level: int
    armor_upgrade_level: int
    has_hq: bool
    has_supply_depot: bool
    has_barracks: bool
    has_academy: bool
    has_starport: bool
    pending_build_kind: str
    pending_build_worker_uid: str
    pending_build_name: str
    build_placement_active: bool
    hide_train_worker: bool
    hide_build_hq: bool
    hide_build_supply_depot: bool
    hide_build_barracks: bool
    hide_build_academy: bool
    hide_build_starport: bool
    hide_upgrade_attack: bool
    hide_upgrade_armor: bool
    hide_cancel_construction: bool
    disable_train_worker: bool
    disable_build_hq: bool
    disable_build_supply_depot: bool
    disable_build_barracks: bool
    disable_build_academy: bool
    disable_build_starport: bool
    disable_upgrade_attack: bool
    disable_upgrade_armor: bool
    disable_cancel_construction: bool
    fog_visible_tiles: list[int]
    fog_explored_tiles: list[int]
    fog_memory_tiles: list[str]
    ui_status: str


game.add_role(
    RTSRole(
        id="human_1",
        required=True,
        kind=RoleKind.HUMAN,
        minerals=1500,
        gas=0,
        supply_used=1,
        supply_cap=10,
        selected_uid="",
        selected_name="None",
        selected_count=0,
        selected_uids=[],
        selected_kind="none",
        selected_hp=0,
        selected_max_hp=0,
        selected_task_active=False,
        selected_task_label="Idle",
        selected_task_percent=0,
        selected_task_bar="[....................]",
        selected_task_seconds_left=0.0,
        can_train_worker=False,
        can_build_hq=False,
        can_build_supply_depot=False,
        can_build_barracks=False,
        can_build_academy=False,
        can_build_starport=False,
        can_upgrade_attack=False,
        can_upgrade_armor=False,
        can_cancel_construction=False,
        attack_upgrade_level=0,
        armor_upgrade_level=0,
        has_hq=True,
        has_supply_depot=False,
        has_barracks=False,
        has_academy=False,
        has_starport=False,
        pending_build_kind="",
        pending_build_worker_uid="",
        pending_build_name="",
        build_placement_active=False,
        hide_train_worker=True,
        hide_build_hq=True,
        hide_build_supply_depot=True,
        hide_build_barracks=True,
        hide_build_academy=True,
        hide_build_starport=True,
        hide_upgrade_attack=True,
        hide_upgrade_armor=True,
        hide_cancel_construction=True,
        disable_train_worker=True,
        disable_build_hq=True,
        disable_build_supply_depot=True,
        disable_build_barracks=True,
        disable_build_academy=True,
        disable_build_starport=True,
        disable_upgrade_attack=True,
        disable_upgrade_armor=True,
        disable_cancel_construction=True,
        fog_visible_tiles=[0] * FOG_TILE_COUNT,
        fog_explored_tiles=[0] * FOG_TILE_COUNT,
        fog_memory_tiles=[""] * FOG_TILE_COUNT,
        ui_status="Ready",
    )
)
game.add_role(
    RTSRole(
        id="human_2",
        required=False,
        kind=RoleKind.HUMAN,
        minerals=1500,
        gas=0,
        supply_used=1,
        supply_cap=10,
        selected_uid="",
        selected_name="None",
        selected_count=0,
        selected_uids=[],
        selected_kind="none",
        selected_hp=0,
        selected_max_hp=0,
        selected_task_active=False,
        selected_task_label="Idle",
        selected_task_percent=0,
        selected_task_bar="[....................]",
        selected_task_seconds_left=0.0,
        can_train_worker=False,
        can_build_hq=False,
        can_build_supply_depot=False,
        can_build_barracks=False,
        can_build_academy=False,
        can_build_starport=False,
        can_upgrade_attack=False,
        can_upgrade_armor=False,
        can_cancel_construction=False,
        attack_upgrade_level=0,
        armor_upgrade_level=0,
        has_hq=True,
        has_supply_depot=False,
        has_barracks=False,
        has_academy=False,
        has_starport=False,
        pending_build_kind="",
        pending_build_worker_uid="",
        pending_build_name="",
        build_placement_active=False,
        hide_train_worker=True,
        hide_build_hq=True,
        hide_build_supply_depot=True,
        hide_build_barracks=True,
        hide_build_academy=True,
        hide_build_starport=True,
        hide_upgrade_attack=True,
        hide_upgrade_armor=True,
        hide_cancel_construction=True,
        disable_train_worker=True,
        disable_build_hq=True,
        disable_build_supply_depot=True,
        disable_build_barracks=True,
        disable_build_academy=True,
        disable_build_starport=True,
        disable_upgrade_attack=True,
        disable_upgrade_armor=True,
        disable_cancel_construction=True,
        fog_visible_tiles=[0] * FOG_TILE_COUNT,
        fog_explored_tiles=[0] * FOG_TILE_COUNT,
        fog_memory_tiles=[""] * FOG_TILE_COUNT,
        ui_status="Ready",
    )
)

scene.set_interface(Interface("ui/hud_human.html", RTSRole["human_1"]))
scene.set_interface(Interface("ui/hud_human.html", RTSRole["human_2"]))

CodeBlock.end("multiplayer_roles")
