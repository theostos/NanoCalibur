from nanocalibur.dsl_markers import CodeBlock, Interface, RoleKind

from .constants import (
    P1_RALLY_X,
    P1_RALLY_Y,
    P2_RALLY_X,
    P2_RALLY_Y,
    START_GAS,
    START_MINERALS,
    START_SUPPLY_CAP,
    START_SUPPLY_USED,
)
from .schemas import StarRole
from .shared import game, scene


CodeBlock.begin("starcraft_clone_roles")
"""Role slots and role-scoped HUD interfaces."""

game.add_role(
    StarRole(
        id="human_1",
        required=True,
        kind=RoleKind.HUMAN,
        minerals=START_MINERALS,
        gas=START_GAS,
        supply_used=START_SUPPLY_USED,
        supply_cap=START_SUPPLY_CAP,
        has_supply=False,
        has_barracks=False,
        has_refinery=False,
        has_factory=False,
        has_lab=False,
        upgrade_attack=0,
        upgrade_armor=0,
        command_mode="move",
        queue_armed=False,
        pending_build="",
        pending_set_rally=False,
        rally_x=P1_RALLY_X,
        rally_y=P1_RALLY_Y,
        selected_count=0,
        selected_building_uid="p1_hq",
        selected_building_type="hq",
        placement_preview_x=0.0,
        placement_preview_y=0.0,
        placement_valid=False,
        placement_reason="Click a build button, then left click map to place.",
        ui_show_hq_controls="flex",
        ui_show_barracks_controls="none",
        ui_show_factory_controls="none",
        ui_show_lab_controls="none",
        active_job_kind="",
        active_job_label="",
        active_job_payload="",
        active_job_target_uid="",
        active_job_scope="",
        active_job_total_ticks=0,
        active_job_remaining_ticks=0,
        active_job_progress_pct=0,
        active_job_spawn_x=0.0,
        active_job_spawn_y=0.0,
        visible_job_label="",
        visible_job_progress_pct=0,
        visible_job_remaining_ticks=0,
        visible_job_total_ticks=0,
    )
)

game.add_role(
    StarRole(
        id="human_2",
        required=True,
        kind=RoleKind.HUMAN,
        minerals=START_MINERALS,
        gas=START_GAS,
        supply_used=START_SUPPLY_USED,
        supply_cap=START_SUPPLY_CAP,
        has_supply=False,
        has_barracks=False,
        has_refinery=False,
        has_factory=False,
        has_lab=False,
        upgrade_attack=0,
        upgrade_armor=0,
        command_mode="move",
        queue_armed=False,
        pending_build="",
        pending_set_rally=False,
        rally_x=P2_RALLY_X,
        rally_y=P2_RALLY_Y,
        selected_count=0,
        selected_building_uid="p2_hq",
        selected_building_type="hq",
        placement_preview_x=0.0,
        placement_preview_y=0.0,
        placement_valid=False,
        placement_reason="Click a build button, then left click map to place.",
        ui_show_hq_controls="flex",
        ui_show_barracks_controls="none",
        ui_show_factory_controls="none",
        ui_show_lab_controls="none",
        active_job_kind="",
        active_job_label="",
        active_job_payload="",
        active_job_target_uid="",
        active_job_scope="",
        active_job_total_ticks=0,
        active_job_remaining_ticks=0,
        active_job_progress_pct=0,
        active_job_spawn_x=0.0,
        active_job_spawn_y=0.0,
        visible_job_label="",
        visible_job_progress_pct=0,
        visible_job_remaining_ticks=0,
        visible_job_total_ticks=0,
    )
)

scene.set_interface(Interface("ui/hud_h1.html", StarRole["human_1"]))
scene.set_interface(Interface("ui/hud_h2.html", StarRole["human_2"]))

CodeBlock.end("starcraft_clone_roles")
