import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict

from nanocalibur.game_model import (
    AnimationClipSpec,
    ActorRefValue,
    ButtonConditionSpec,
    CameraMode,
    CameraSpec,
    CollisionConditionSpec,
    ConditionSpec,
    GlobalVariableSpec,
    KeyboardConditionSpec,
    LogicalConditionSpec,
    MouseConditionSpec,
    MultiplayerSpec,
    ProjectSpec,
    RoleSpec,
    ResourceSpec,
    RuleSpec,
    SceneSpec,
    SelectorKind,
    SpriteSpec,
    ToolConditionSpec,
)
from nanocalibur.project_compiler import ProjectCompiler
from nanocalibur.ts_generator import TSGenerator
from nanocalibur.ir import ParamBinding


def compile_project(
    source: str,
    source_path: str | None = None,
    *,
    require_code_blocks: bool = False,
    unboxed_disable_flag: str = "--allow-unboxed",
) -> ProjectSpec:
    """Compile DSL source into a :class:`ProjectSpec`."""
    return ProjectCompiler().compile(
        source,
        source_path=source_path,
        require_code_blocks=require_code_blocks,
        unboxed_disable_flag=unboxed_disable_flag,
    )


def project_to_dict(project: ProjectSpec) -> Dict[str, Any]:
    """Serialize a :class:`ProjectSpec` into the JSON game spec payload."""
    return {
        "schemas": project.actor_schemas,
        "role_schemas": project.role_schemas,
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
        "tools": _tools_to_dict(project.rules),
        "map": _map_to_dict(project.tile_map),
        "camera": _camera_to_dict(project.camera),
        "scene": _scene_to_dict(project.scene),
        "multiplayer": _multiplayer_to_dict(project.multiplayer),
        "roles": [_role_to_dict(role) for role in project.roles],
        "interface_html": project.interface_html,
        "resources": [_resource_to_dict(resource) for resource in project.resources],
        "sprites": {
            "by_name": {
                sprite.name: _sprite_to_dict(sprite)
                for sprite in project.sprites
                if sprite.name is not None
            },
            "by_uid": {
                sprite.uid: _sprite_to_dict(sprite)
                for sprite in project.sprites
                if sprite.uid is not None
            },
            "by_type": {
                sprite.actor_type: _sprite_to_dict(sprite)
                for sprite in project.sprites
                if sprite.actor_type is not None
            },
        },
        "actions": [action.name for action in project.actions],
        "predicates": [
            {
                "name": predicate.name,
                "actor_type": predicate.actor_type,
                "params": [_param_binding_to_dict(param) for param in predicate.params],
            }
            for predicate in project.predicates
        ],
        "callables": [callable_fn.name for callable_fn in project.callables],
        "contains_next_turn_call": project.contains_next_turn_call,
    }


def export_project(
    source: str,
    output_dir: str,
    source_path: str | None = None,
    *,
    require_code_blocks: bool = False,
    unboxed_disable_flag: str = "--allow-unboxed",
) -> ProjectSpec:
    """Compile and write spec/IR/TypeScript outputs to ``output_dir``."""
    project = compile_project(
        source,
        source_path=source_path,
        require_code_blocks=require_code_blocks,
        unboxed_disable_flag=unboxed_disable_flag,
    )
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    spec_path = out_dir / "game_spec.json"
    ir_path = out_dir / "game_ir.json"
    ts_path = out_dir / "game_logic.ts"

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
        generator.generate(project.actions, project.predicates, project.callables),
        encoding="utf-8",
    )

    return project


def project_to_ir_dict(project: ProjectSpec) -> Dict[str, Any]:
    """Serialize action/predicate IR payloads."""
    return {
        "actions": [_serialize_ir(action) for action in project.actions],
        "predicates": [_serialize_ir(predicate) for predicate in project.predicates],
        "callables": [_serialize_ir(callable_fn) for callable_fn in project.callables],
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
            "role_id": condition.role_id,
        }
    if isinstance(condition, MouseConditionSpec):
        return {
            "kind": "mouse",
            "phase": condition.phase.value,
            "button": condition.button,
            "role_id": condition.role_id,
        }
    if isinstance(condition, ButtonConditionSpec):
        return {
            "kind": "button",
            "name": condition.name,
        }
    if isinstance(condition, CollisionConditionSpec):
        return {
            "kind": "collision",
            "mode": condition.mode.value,
            "left": _selector_to_dict(condition.left),
            "right": _selector_to_dict(condition.right),
        }
    if isinstance(condition, LogicalConditionSpec):
        return {
            "kind": "logical",
            "predicate": condition.predicate_name,
            "target": _selector_to_dict(condition.target),
        }
    if isinstance(condition, ToolConditionSpec):
        return {
            "kind": "tool",
            "name": condition.name,
            "tool_docstring": condition.tool_docstring,
            "role_id": condition.role_id,
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
    tile_defs_payload: Dict[str, Any] = {}
    for tile_id, tile_def in map_spec.tile_defs.items():
        tile_defs_payload[str(tile_id)] = {
            "block_mask": tile_def.block_mask,
            "sprite": tile_def.sprite,
            "color": (
                {
                    "r": tile_def.color.r,
                    "g": tile_def.color.g,
                    "b": tile_def.color.b,
                    "symbol": tile_def.color.symbol,
                    "description": tile_def.color.description,
                }
                if tile_def.color is not None
                else None
            ),
        }
    return {
        "width": map_spec.width,
        "height": map_spec.height,
        "tile_size": map_spec.tile_size,
        "tile_grid": map_spec.tile_grid,
        "tile_defs": tile_defs_payload,
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


def _resource_to_dict(resource: ResourceSpec) -> Dict[str, Any]:
    return {
        "name": resource.name,
        "path": resource.path,
    }


def _role_to_dict(role: RoleSpec) -> Dict[str, Any]:
    return {
        "id": role.id,
        "required": role.required,
        "kind": role.kind.value,
        "type": role.role_type,
        "fields": role.fields,
    }


def _scene_to_dict(scene: SceneSpec | None) -> Dict[str, Any] | None:
    if scene is None:
        return None
    return {
        "gravity_enabled": scene.gravity_enabled,
        "keyboard_aliases": scene.keyboard_aliases,
    }


def _multiplayer_to_dict(multiplayer: MultiplayerSpec | None) -> Dict[str, Any] | None:
    if multiplayer is None:
        return None
    return {
        "default_loop": multiplayer.default_loop.value,
        "allowed_loops": [mode.value for mode in multiplayer.allowed_loops],
        "default_visibility": multiplayer.default_visibility.value,
        "tick_rate": multiplayer.tick_rate,
        "turn_timeout_ms": multiplayer.turn_timeout_ms,
        "hybrid_window_ms": multiplayer.hybrid_window_ms,
        "game_time_scale": multiplayer.game_time_scale,
        "max_catchup_steps": multiplayer.max_catchup_steps,
    }


def _clip_to_dict(clip: AnimationClipSpec) -> Dict[str, Any]:
    return {
        "frames": clip.frames,
        "ticks_per_frame": clip.ticks_per_frame,
        "loop": clip.loop,
    }


def _sprite_to_dict(sprite: SpriteSpec) -> Dict[str, Any]:
    return {
        "resource": sprite.resource,
        "frame_width": sprite.frame_width,
        "frame_height": sprite.frame_height,
        "row": sprite.row,
        "scale": sprite.scale,
        "flip_x": sprite.flip_x,
        "offset_x": sprite.offset_x,
        "offset_y": sprite.offset_y,
        "symbol": sprite.symbol,
        "description": sprite.description,
        "default_clip": sprite.default_clip,
        "clips": {clip.name: _clip_to_dict(clip) for clip in sprite.clips},
    }


def _param_binding_to_dict(param: ParamBinding) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "name": param.name,
        "kind": param.kind.value,
        "global_name": param.global_name,
        "actor_type": param.actor_type,
        "actor_list_type": param.actor_list_type,
        "role_type": param.role_type,
    }
    if param.actor_selector is None:
        payload["actor_selector"] = None
    else:
        payload["actor_selector"] = {
            "uid": param.actor_selector.uid,
            "index": param.actor_selector.index,
        }
    if param.role_selector is None:
        payload["role_selector"] = None
    else:
        payload["role_selector"] = {
            "id": param.role_selector.id,
        }
    return payload


def _tools_to_dict(rules: list[RuleSpec]) -> list[Dict[str, Any]]:
    tools: list[Dict[str, Any]] = []
    seen: set[str] = set()
    for rule in rules:
        condition = rule.condition
        if not isinstance(condition, ToolConditionSpec):
            continue
        if condition.name in seen:
            continue
        seen.add(condition.name)
        tools.append(
            {
                "name": condition.name,
                "tool_docstring": condition.tool_docstring,
                "role_id": condition.role_id,
                "action": rule.action_name,
            }
        )
    return tools


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
