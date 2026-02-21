from typing import List

from nanocalibur.dsl_markers import CodeBlock, Global, OnContact, OnOverlap, callable, safe_condition

from .constants import WORKER_CARGO_CAP
from .schemas import GasGeyser, HQ, MineralPatch, StarRole, Worker


CodeBlock.begin("starcraft_clone_economy")
"""Authoritative economy rules: workers harvest, return to HQ, then go back to nodes."""


@callable
def _same_owner_or_neutral(node_owner_id: str, worker_owner_id: str):
    if node_owner_id == "":
        return True
    if node_owner_id == worker_owner_id:
        return True
    return False


@callable
def _owner_has_refinery(owner_id: str, role_1: StarRole, role_2: StarRole):
    if owner_id == "human_1":
        return role_1.has_refinery
    if owner_id == "human_2":
        return role_2.has_refinery
    return False


@callable
def _set_move(worker: Worker, target_uid: str, target_x: float, target_y: float):
    worker.order = "move"
    worker.target_uid = target_uid
    worker.target_x = target_x
    worker.target_y = target_y
    worker.vx = 0
    worker.vy = 0


@callable
def _is_manual_move(worker: Worker):
    if worker.order == "manual_move":
        return True
    if worker.order != "move":
        return False
    return worker.target_uid == ""


@callable
def _send_worker_to_home_hq(worker: Worker, hqs: List[HQ]):
    if worker.home_hq_uid == "":
        return
    for hq in hqs:
        if not hq.active:
            continue
        if hq.uid != worker.home_hq_uid:
            continue
        _set_move(worker, hq.uid, hq.x, hq.y)
        return


@callable
def _send_worker_to_resource(
    worker: Worker,
    minerals: List[MineralPatch],
    gases: List[GasGeyser],
    role_1: StarRole,
    role_2: StarRole,
):
    if worker.harvest_target_uid == "":
        worker.order = "idle"
        return

    for mineral in minerals:
        if (not mineral.active) or mineral.amount <= 0:
            continue
        if mineral.uid != worker.harvest_target_uid:
            continue
        if not _same_owner_or_neutral(mineral.owner_id, worker.owner_id):
            worker.order = "idle"
            return
        _set_move(worker, mineral.uid, mineral.x, mineral.y)
        return

    for gas in gases:
        if (not gas.active) or gas.amount <= 0:
            continue
        if gas.uid != worker.harvest_target_uid:
            continue
        if not _same_owner_or_neutral(gas.owner_id, worker.owner_id):
            worker.order = "idle"
            return
        if not _owner_has_refinery(worker.owner_id, role_1, role_2):
            worker.order = "idle"
            return
        _set_move(worker, gas.uid, gas.x, gas.y)
        return

    worker.order = "idle"


@safe_condition(OnOverlap(Worker, MineralPatch))
def gather_minerals(
    worker: Worker,
    node: MineralPatch,
    hqs: List[HQ],
    role_1: StarRole["human_1"],
    role_2: StarRole["human_2"],
    state: Global["state", str],
):
    if state != "playing":
        return
    if _is_manual_move(worker):
        return
    if (not worker.active) or (not node.active):
        return
    if not _same_owner_or_neutral(node.owner_id, worker.owner_id):
        return
    if node.amount <= 0:
        return
    if worker.order == "attack" or worker.order == "attack_move":
        return

    cargo_total = worker.cargo_minerals + worker.cargo_gas
    if cargo_total >= WORKER_CARGO_CAP:
        _send_worker_to_home_hq(worker, hqs)
        return

    gather = worker.gather_per_tick
    cap_left = WORKER_CARGO_CAP - cargo_total
    if gather > cap_left:
        gather = cap_left
    if gather > node.amount:
        gather = node.amount
    if gather <= 0:
        return

    worker.cargo_minerals = worker.cargo_minerals + gather
    worker.harvest_target_uid = node.uid
    worker.harvest_resource = "mineral"
    node.amount = node.amount - gather

    if worker.cargo_minerals + worker.cargo_gas >= WORKER_CARGO_CAP or node.amount <= 0:
        _send_worker_to_home_hq(worker, hqs)


@safe_condition(OnOverlap(Worker, GasGeyser))
def gather_gas(
    worker: Worker,
    node: GasGeyser,
    hqs: List[HQ],
    role_1: StarRole["human_1"],
    role_2: StarRole["human_2"],
    state: Global["state", str],
):
    if state != "playing":
        return
    if _is_manual_move(worker):
        return
    if (not worker.active) or (not node.active):
        return
    if not _same_owner_or_neutral(node.owner_id, worker.owner_id):
        return
    if node.amount <= 0:
        return
    if worker.order == "attack" or worker.order == "attack_move":
        return

    if not _owner_has_refinery(worker.owner_id, role_1, role_2):
        return

    cargo_total = worker.cargo_minerals + worker.cargo_gas
    if cargo_total >= WORKER_CARGO_CAP:
        _send_worker_to_home_hq(worker, hqs)
        return

    gather = worker.gather_per_tick
    cap_left = WORKER_CARGO_CAP - cargo_total
    if gather > cap_left:
        gather = cap_left
    if gather > node.amount:
        gather = node.amount
    if gather <= 0:
        return

    worker.cargo_gas = worker.cargo_gas + gather
    worker.harvest_target_uid = node.uid
    worker.harvest_resource = "gas"
    node.amount = node.amount - gather

    if worker.cargo_minerals + worker.cargo_gas >= WORKER_CARGO_CAP or node.amount <= 0:
        _send_worker_to_home_hq(worker, hqs)


@safe_condition(OnContact(Worker, HQ))
def deposit_cargo(
    worker: Worker,
    hq: HQ,
    minerals: List[MineralPatch],
    gases: List[GasGeyser],
    role_1: StarRole["human_1"],
    role_2: StarRole["human_2"],
    state: Global["state", str],
):
    if state != "playing":
        return
    if _is_manual_move(worker):
        return
    if (not worker.active) or (not hq.active):
        return
    if worker.owner_id != hq.owner_id:
        return

    cargo_m = worker.cargo_minerals
    cargo_g = worker.cargo_gas
    if cargo_m <= 0 and cargo_g <= 0:
        return

    if worker.owner_id == "human_1":
        role_1.minerals = role_1.minerals + cargo_m
        role_1.gas = role_1.gas + cargo_g
    elif worker.owner_id == "human_2":
        role_2.minerals = role_2.minerals + cargo_m
        role_2.gas = role_2.gas + cargo_g

    worker.cargo_minerals = 0
    worker.cargo_gas = 0
    _send_worker_to_resource(worker, minerals, gases, role_1, role_2)


CodeBlock.end("starcraft_clone_economy")
