from typing import List

from nanocalibur.dsl_markers import CodeBlock, Global, OnContact, OnLogicalCondition, OnOverlap, callable, safe_condition

from .schemas import Building, Medic, StarRole, Unit


CodeBlock.begin("starcraft_clone_combat")
"""Authoritative order processing, combat, healing, and win conditions."""


def active_unit(unit: Unit) -> bool:
    return unit.active


@callable
def _min_damage(value: int):
    if value < 1:
        return 1
    return value


@callable
def _apply_supply_death(u: Unit, role_1: StarRole, role_2: StarRole):
    if not u.active:
        return
    if u.owner_id == "human_1":
        role_1.supply_used = role_1.supply_used - u.supply
    elif u.owner_id == "human_2":
        role_2.supply_used = role_2.supply_used - u.supply


@callable
def _dist2(ax: float, ay: float, bx: float, by: float):
    dx = ax - bx
    dy = ay - by
    return dx * dx + dy * dy


@callable
def _promote_queued_order(unit: Unit):
    if not unit.has_queued_order:
        return False
    unit.order = unit.queued_order
    unit.target_x = unit.queued_target_x
    unit.target_y = unit.queued_target_y
    unit.target_uid = unit.queued_target_uid
    unit.has_queued_order = False
    unit.queued_order = "idle"
    unit.queued_target_uid = ""
    return True


@callable
def _owner_supply_cap(owner_id: str, buildings: List[Building]):
    cap = 0
    for building in buildings:
        if not building.active:
            continue
        if building.owner_id != owner_id:
            continue
        cap = cap + building.supply_provided
    return cap


@callable
def _owner_has_building(owner_id: str, sprite_name: str, buildings: List[Building]):
    for building in buildings:
        if not building.active:
            continue
        if building.owner_id != owner_id:
            continue
        if building.sprite == sprite_name:
            return True
    return False


@safe_condition(OnLogicalCondition(active_unit, Unit))
def process_orders(
    unit: Unit,
    units: List[Unit],
    buildings: List[Building],
    state: Global["state", str],
):
    if state != "playing":
        return

    if (
        unit.order != "move"
        and unit.order != "manual_move"
        and unit.order != "attack"
        and unit.order != "attack_move"
    ):
        return

    if unit.order == "attack_move" and unit.target_uid == "":
        best_target_uid = ""
        best_dist2 = 999999999
        for other in units:
            if not other.active:
                continue
            if other.owner_id == unit.owner_id:
                continue
            d2 = _dist2(unit.x, unit.y, other.x, other.y)
            if d2 < best_dist2 and d2 <= 160 * 160:
                best_dist2 = d2
                best_target_uid = other.uid
        for building in buildings:
            if not building.active:
                continue
            if building.owner_id == unit.owner_id:
                continue
            d2 = _dist2(unit.x, unit.y, building.x, building.y)
            if d2 < best_dist2 and d2 <= 180 * 180:
                best_dist2 = d2
                best_target_uid = building.uid
        if best_target_uid != "":
            unit.target_uid = best_target_uid

    if unit.order == "attack_move" and unit.target_uid != "":
        found_target = False
        target_x = unit.target_x
        target_y = unit.target_y
        for other in units:
            if not other.active:
                continue
            if other.uid == unit.target_uid:
                target_x = other.x
                target_y = other.y
                found_target = True
        for building in buildings:
            if not building.active:
                continue
            if building.uid == unit.target_uid:
                target_x = building.x
                target_y = building.y
                found_target = True

        if not found_target:
            unit.target_uid = ""
        else:
            if (
                unit.x >= target_x - 24
                and unit.x <= target_x + 24
                and unit.y >= target_y - 24
                and unit.y <= target_y + 24
            ):
                unit.vx = 0
                unit.vy = 0
                return
            if unit.x < target_x:
                unit.vx = unit.speed
            elif unit.x > target_x:
                unit.vx = -unit.speed
            else:
                unit.vx = 0
            if unit.y < target_y:
                unit.vy = unit.speed
            elif unit.y > target_y:
                unit.vy = -unit.speed
            else:
                unit.vy = 0
            return

    if unit.order == "attack":
        found_target = False
        for other in units:
            if not other.active:
                continue
            if other.uid == unit.target_uid:
                unit.target_x = other.x
                unit.target_y = other.y
                found_target = True
        for building in buildings:
            if not building.active:
                continue
            if building.uid == unit.target_uid:
                unit.target_x = building.x
                unit.target_y = building.y
                found_target = True

        if not found_target:
            if _promote_queued_order(unit):
                return
            unit.order = "idle"
            unit.vx = 0
            unit.vy = 0
            return

        if (
            unit.x >= unit.target_x - 24
            and unit.x <= unit.target_x + 24
            and unit.y >= unit.target_y - 24
            and unit.y <= unit.target_y + 24
        ):
            unit.vx = 0
            unit.vy = 0
            return

    if (
        unit.x >= unit.target_x - 8
        and unit.x <= unit.target_x + 8
        and unit.y >= unit.target_y - 8
        and unit.y <= unit.target_y + 8
    ):
        unit.vx = 0
        unit.vy = 0
        if unit.order == "move" or unit.order == "attack_move":
            if _promote_queued_order(unit):
                return
            unit.order = "idle"
        elif unit.order == "manual_move":
            if _promote_queued_order(unit):
                return
        return

    if unit.x < unit.target_x:
        unit.vx = unit.speed
    elif unit.x > unit.target_x:
        unit.vx = -unit.speed
    else:
        unit.vx = 0

    if unit.y < unit.target_y:
        unit.vy = unit.speed
    elif unit.y > unit.target_y:
        unit.vy = -unit.speed
    else:
        unit.vy = 0


@safe_condition(OnContact(Unit, Unit))
def unit_vs_unit(
    left: Unit,
    right: Unit,
    role_1: StarRole["human_1"],
    role_2: StarRole["human_2"],
    state: Global["state", str],
):
    if state != "playing":
        return
    if (not left.active) or (not right.active):
        return
    if left.owner_id == right.owner_id:
        return

    left.vx = 0
    right.vx = 0

    left_attack_bonus = 0
    left_armor_bonus = 0
    right_attack_bonus = 0
    right_armor_bonus = 0

    if left.owner_id == "human_1":
        left_attack_bonus = role_1.upgrade_attack
        left_armor_bonus = role_1.upgrade_armor
    elif left.owner_id == "human_2":
        left_attack_bonus = role_2.upgrade_attack
        left_armor_bonus = role_2.upgrade_armor

    if right.owner_id == "human_1":
        right_attack_bonus = role_1.upgrade_attack
        right_armor_bonus = role_1.upgrade_armor
    elif right.owner_id == "human_2":
        right_attack_bonus = role_2.upgrade_attack
        right_armor_bonus = role_2.upgrade_armor

    damage_left_to_right = _min_damage(
        (left.attack + left_attack_bonus) - (right.armor + right_armor_bonus)
    )
    damage_right_to_left = _min_damage(
        (right.attack + right_attack_bonus) - (left.armor + left_armor_bonus)
    )

    right.hp = right.hp - damage_left_to_right
    left.hp = left.hp - damage_right_to_left

    if right.hp <= 0:
        _apply_supply_death(right, role_1, role_2)
        right.destroy()
    if left.hp <= 0:
        _apply_supply_death(left, role_1, role_2)
        left.destroy()


@safe_condition(OnContact(Unit, Building))
def unit_vs_building(
    unit: Unit,
    building: Building,
    buildings: List[Building],
    role_1: StarRole["human_1"],
    role_2: StarRole["human_2"],
    state: Global["state", str],
    winner: Global["winner", str],
):
    if state != "playing":
        return
    if (not unit.active) or (not building.active):
        return
    if unit.owner_id == building.owner_id:
        return

    unit.vx = 0

    attack_bonus = 0
    if unit.owner_id == "human_1":
        attack_bonus = role_1.upgrade_attack
    elif unit.owner_id == "human_2":
        attack_bonus = role_2.upgrade_attack

    damage = _min_damage(unit.attack + attack_bonus)
    building.hp = building.hp - damage

    if building.hp > 0:
        return

    building.destroy()

    if building.uid == "p1_hq":
        state = "ended"
        winner = "human_2"
    elif building.uid == "p2_hq":
        state = "ended"
        winner = "human_1"

    if building.owner_id == "human_1":
        role_1.supply_cap = _owner_supply_cap("human_1", buildings)
        role_1.has_supply = _owner_has_building("human_1", "supply", buildings)
        role_1.has_barracks = _owner_has_building("human_1", "barracks", buildings)
        role_1.has_refinery = _owner_has_building("human_1", "refinery", buildings)
        role_1.has_factory = _owner_has_building("human_1", "factory", buildings)
        role_1.has_lab = _owner_has_building("human_1", "lab", buildings)
    elif building.owner_id == "human_2":
        role_2.supply_cap = _owner_supply_cap("human_2", buildings)
        role_2.has_supply = _owner_has_building("human_2", "supply", buildings)
        role_2.has_barracks = _owner_has_building("human_2", "barracks", buildings)
        role_2.has_refinery = _owner_has_building("human_2", "refinery", buildings)
        role_2.has_factory = _owner_has_building("human_2", "factory", buildings)
        role_2.has_lab = _owner_has_building("human_2", "lab", buildings)


@safe_condition(OnOverlap(Medic, Unit))
def medic_heal(medic: Medic, target: Unit, state: Global["state", str]):
    if state != "playing":
        return
    if (not medic.active) or (not target.active):
        return
    if medic.owner_id != target.owner_id:
        return
    if medic.heal_per_tick <= 0:
        return
    if target.hp >= target.max_hp:
        return

    target.hp = target.hp + medic.heal_per_tick
    if target.hp > target.max_hp:
        target.hp = target.max_hp


CodeBlock.end("starcraft_clone_combat")
