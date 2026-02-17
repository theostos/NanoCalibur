import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict

from nanocalibur.game_model import (
    ActorRefValue,
    CameraMode,
    CameraSpec,
    CollisionConditionSpec,
    ConditionSpec,
    GlobalVariableSpec,
    KeyboardConditionSpec,
    LogicalConditionSpec,
    MouseConditionSpec,
    ProjectSpec,
    RuleSpec,
    SelectorKind,
)
from nanocalibur.project_compiler import ProjectCompiler
from nanocalibur.ts_generator import TSGenerator


def compile_project(source: str) -> ProjectSpec:
    return ProjectCompiler().compile(source)


def project_to_dict(project: ProjectSpec) -> Dict[str, Any]:
    return {
        "schemas": project.actor_schemas,
        "globals": [_global_to_dict(g) for g in project.globals],
        "actors": [
            {
                "type": actor.actor_type,
                "uid": actor.uid,
                "fields": actor.fields,
            }
            for actor in project.actors
        ],
        "rules": [_rule_to_dict(rule) for rule in project.rules],
        "map": _map_to_dict(project.tile_map),
        "camera": _camera_to_dict(project.camera),
        "actions": [action.name for action in project.actions],
        "predicates": [
            {
                "name": predicate.name,
                "actor_type": predicate.actor_type,
            }
            for predicate in project.predicates
        ],
    }


def export_project(source: str, output_dir: str) -> ProjectSpec:
    project = compile_project(source)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    spec_path = out_dir / "game_spec.json"
    ir_path = out_dir / "game_ir.json"
    ts_path = out_dir / "game_logic.ts"
    js_path = out_dir / "game_logic.js"
    esm_path = out_dir / "game_logic.mjs"

    spec_path.write_text(
        json.dumps(project_to_dict(project), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    ir_path.write_text(
        json.dumps(project_to_ir_dict(project), indent=2, sort_keys=True),
        encoding="utf-8",
    )

    generator = TSGenerator()
    ts_path.write_text(
        generator.generate(project.actions, project.predicates), encoding="utf-8"
    )
    js_path.write_text(
        generator.generate_javascript(project.actions, project.predicates),
        encoding="utf-8",
    )
    esm_path.write_text(
        generator.generate_esm_javascript(project.actions, project.predicates),
        encoding="utf-8",
    )

    return project


def project_to_ir_dict(project: ProjectSpec) -> Dict[str, Any]:
    return {
        "actions": [_serialize_ir(action) for action in project.actions],
        "predicates": [_serialize_ir(predicate) for predicate in project.predicates],
    }


def _selector_to_dict(selector):
    return {
        "kind": selector.kind.value,
        "actor_type": selector.actor_type,
        "uid": selector.uid,
    }


def _condition_to_dict(condition: ConditionSpec) -> Dict[str, Any]:
    if isinstance(condition, KeyboardConditionSpec):
        return {
            "kind": "keyboard",
            "phase": condition.phase.value,
            "key": condition.key,
        }
    if isinstance(condition, MouseConditionSpec):
        return {
            "kind": "mouse",
            "phase": condition.phase.value,
            "button": condition.button,
        }
    if isinstance(condition, CollisionConditionSpec):
        return {
            "kind": "collision",
            "left": _selector_to_dict(condition.left),
            "right": _selector_to_dict(condition.right),
        }
    if isinstance(condition, LogicalConditionSpec):
        return {
            "kind": "logical",
            "predicate": condition.predicate_name,
            "target": _selector_to_dict(condition.target),
        }
    raise TypeError(f"Unsupported condition: {condition!r}")


def _rule_to_dict(rule: RuleSpec) -> Dict[str, Any]:
    return {
        "condition": _condition_to_dict(rule.condition),
        "action": rule.action_name,
    }


def _global_to_dict(global_var: GlobalVariableSpec) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "name": global_var.name,
        "kind": global_var.kind.value,
        "list_elem_kind": global_var.list_elem_kind,
    }
    if isinstance(global_var.value, ActorRefValue):
        payload["value"] = {
            "uid": global_var.value.uid,
            "actor_type": global_var.value.actor_type,
        }
    else:
        payload["value"] = global_var.value
    return payload


def _map_to_dict(map_spec):
    if map_spec is None:
        return None
    return {
        "width": map_spec.width,
        "height": map_spec.height,
        "tile_size": map_spec.tile_size,
        "solid_tiles": map_spec.solid_tiles,
    }


def _camera_to_dict(camera: CameraSpec | None):
    if camera is None:
        return None
    if camera.mode == CameraMode.FIXED:
        return {
            "mode": camera.mode.value,
            "x": camera.x,
            "y": camera.y,
        }
    return {
        "mode": camera.mode.value,
        "target_uid": camera.target_uid,
    }


def _serialize_ir(value):
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        data = asdict(value)
        return {k: _serialize_ir(v) for k, v in data.items()}
    if isinstance(value, list):
        return [_serialize_ir(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _serialize_ir(v) for k, v in value.items()}
    return value
