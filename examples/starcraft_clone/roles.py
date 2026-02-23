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
    selected_kind: str
    selected_hp: int
    selected_max_hp: int
    selected_task_active: bool
    selected_task_label: str
    selected_task_percent: float
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
    attack_upgrade_level: int
    armor_upgrade_level: int
    has_hq: bool
    has_supply_depot: bool
    has_barracks: bool
    has_academy: bool
    has_starport: bool
    ui_status: str


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
        selected_kind="none",
        selected_hp=0,
        selected_max_hp=0,
        selected_task_active=False,
        selected_task_label="Idle",
        selected_task_percent=0.0,
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
        attack_upgrade_level=0,
        armor_upgrade_level=0,
        has_hq=True,
        has_supply_depot=False,
        has_barracks=False,
        has_academy=False,
        has_starport=False,
        ui_status="Ready",
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
        selected_kind="none",
        selected_hp=0,
        selected_max_hp=0,
        selected_task_active=False,
        selected_task_label="Idle",
        selected_task_percent=0.0,
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
        attack_upgrade_level=0,
        armor_upgrade_level=0,
        has_hq=True,
        has_supply_depot=False,
        has_barracks=False,
        has_academy=False,
        has_starport=False,
        ui_status="Ready",
    )
)

scene.set_interface(Interface("ui/hud_human.html", RTSRole["human_1"]))
scene.set_interface(Interface("ui/hud_human.html", RTSRole["human_2"]))

CodeBlock.end("multiplayer_roles")
