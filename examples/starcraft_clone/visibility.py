from typing import List

from nanocalibur.dsl_markers import CodeBlock, Global, OnLogicalCondition, callable, safe_condition

from .schemas import Building, GasGeyser, HQ, MineralPatch, Unit


CodeBlock.begin("starcraft_clone_visibility")
"""Server-side fog-of-war visibility mask updates."""


def active_hq(hq: HQ) -> bool:
    return hq.active


@callable
def _dist2(ax: float, ay: float, bx: float, by: float):
    dx = ax - bx
    dy = ay - by
    return dx * dx + dy * dy


@callable
def _add_visibility(mask: int, bit: int):
    if mask == 0:
        return bit
    if mask == bit:
        return mask
    return 3


@safe_condition(OnLogicalCondition(active_hq, HQ))
def update_visibility(
    anchor: HQ,
    units: List[Unit],
    buildings: List[Building],
    minerals: List[MineralPatch],
    gases: List[GasGeyser],
    state: Global["state", str],
):
    if state != "playing" and state != "ended":
        return
    if anchor.uid != "p1_hq":
        return

    for unit in units:
        unit.visible_mask = 0
    for building in buildings:
        building.visible_mask = 0
    for mineral in minerals:
        mineral.visible_mask = 0
    for gas in gases:
        gas.visible_mask = 0

    for unit in units:
        if not unit.active:
            continue
        if unit.owner_id == "human_1":
            unit.visible_mask = 1
        elif unit.owner_id == "human_2":
            unit.visible_mask = 2
    for building in buildings:
        if not building.active:
            continue
        if building.owner_id == "human_1":
            building.visible_mask = 1
        elif building.owner_id == "human_2":
            building.visible_mask = 2

    for observer in units:
        if not observer.active:
            continue
        bit = 0
        if observer.owner_id == "human_1":
            bit = 1
        elif observer.owner_id == "human_2":
            bit = 2
        if bit == 0:
            continue

        vision2 = 190 * 190

        for unit in units:
            if not unit.active:
                continue
            if _dist2(observer.x, observer.y, unit.x, unit.y) <= vision2:
                unit.visible_mask = _add_visibility(unit.visible_mask, bit)

        for building in buildings:
            if not building.active:
                continue
            if _dist2(observer.x, observer.y, building.x, building.y) <= vision2:
                building.visible_mask = _add_visibility(building.visible_mask, bit)

        for mineral in minerals:
            if not mineral.active:
                continue
            if _dist2(observer.x, observer.y, mineral.x, mineral.y) <= vision2:
                mineral.visible_mask = _add_visibility(mineral.visible_mask, bit)

        for gas in gases:
            if not gas.active:
                continue
            if _dist2(observer.x, observer.y, gas.x, gas.y) <= vision2:
                gas.visible_mask = _add_visibility(gas.visible_mask, bit)

    for observer in buildings:
        if not observer.active:
            continue
        bit = 0
        if observer.owner_id == "human_1":
            bit = 1
        elif observer.owner_id == "human_2":
            bit = 2
        if bit == 0:
            continue

        vision2 = 230 * 230

        for unit in units:
            if not unit.active:
                continue
            if _dist2(observer.x, observer.y, unit.x, unit.y) <= vision2:
                unit.visible_mask = _add_visibility(unit.visible_mask, bit)

        for building in buildings:
            if not building.active:
                continue
            if _dist2(observer.x, observer.y, building.x, building.y) <= vision2:
                building.visible_mask = _add_visibility(building.visible_mask, bit)

        for mineral in minerals:
            if not mineral.active:
                continue
            if _dist2(observer.x, observer.y, mineral.x, mineral.y) <= vision2:
                mineral.visible_mask = _add_visibility(mineral.visible_mask, bit)

        for gas in gases:
            if not gas.active:
                continue
            if _dist2(observer.x, observer.y, gas.x, gas.y) <= vision2:
                gas.visible_mask = _add_visibility(gas.visible_mask, bit)


CodeBlock.end("starcraft_clone_visibility")
