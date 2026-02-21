from nanocalibur.dsl_markers import Actor, CodeBlock, HumanRole


CodeBlock.begin("starcraft_clone_schemas")
"""Role and actor schemas for the StarCraft clone gameplay."""


class StarRole(HumanRole):
    minerals: int
    gas: int
    supply_used: int
    supply_cap: int

    has_supply: bool
    has_barracks: bool
    has_refinery: bool
    has_factory: bool
    has_lab: bool

    upgrade_attack: int
    upgrade_armor: int
    command_mode: str
    queue_armed: bool
    pending_build: str
    pending_set_rally: bool
    rally_x: float
    rally_y: float
    selected_count: int
    selected_building_uid: str
    selected_building_type: str
    placement_preview_x: float
    placement_preview_y: float
    placement_valid: bool
    placement_reason: str
    ui_show_hq_controls: str
    ui_show_barracks_controls: str
    ui_show_factory_controls: str
    ui_show_lab_controls: str
    active_job_kind: str
    active_job_label: str
    active_job_payload: str
    active_job_target_uid: str
    active_job_scope: str
    active_job_total_ticks: int
    active_job_remaining_ticks: int
    active_job_progress_pct: int
    active_job_spawn_x: float
    active_job_spawn_y: float
    visible_job_label: str
    visible_job_progress_pct: int
    visible_job_remaining_ticks: int
    visible_job_total_ticks: int


class OwnedActor(Actor):
    owner_id: str
    visible_mask: int


class Unit(OwnedActor):
    hp: int
    max_hp: int
    attack: int
    armor: int
    speed: int
    supply: int
    march_dir: int
    selected: bool
    order: str
    target_x: float
    target_y: float
    target_uid: str
    has_queued_order: bool
    queued_order: str
    queued_target_x: float
    queued_target_y: float
    queued_target_uid: str


class Worker(Unit):
    gather_per_tick: int
    cargo_minerals: int
    cargo_gas: int
    harvest_target_uid: str
    harvest_resource: str
    home_hq_uid: str


class CombatUnit(Unit):
    pass


class Marine(CombatUnit):
    pass


class Marauder(CombatUnit):
    pass


class Medic(CombatUnit):
    heal_per_tick: int


class Tank(CombatUnit):
    pass


class Scout(CombatUnit):
    pass


class Building(OwnedActor):
    hp: int
    max_hp: int
    supply_provided: int


class HQ(Building):
    pass


class SupplyDepot(Building):
    pass


class Barracks(Building):
    pass


class Refinery(Building):
    pass


class Factory(Building):
    pass


class Lab(Building):
    pass


class ResourceNode(OwnedActor):
    amount: int
    per_tick: int


class MineralPatch(ResourceNode):
    pass


class GasGeyser(ResourceNode):
    pass


CodeBlock.end("starcraft_clone_schemas")
