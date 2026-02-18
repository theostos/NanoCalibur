from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Union

from nanocalibur.ir import ActionIR, PredicateIR

PrimitiveValue = Union[int, float, str, bool, None]
ListValue = List[PrimitiveValue]


class SelectorKind(Enum):
    ANY = "any"
    WITH_UID = "with_uid"


@dataclass(frozen=True)
class ActorSelectorSpec:
    kind: SelectorKind
    actor_type: Optional[str] = None
    uid: Optional[str] = None


class ConditionKind(Enum):
    KEYBOARD = "keyboard"
    MOUSE = "mouse"
    BUTTON = "button"
    COLLISION = "collision"
    LOGICAL = "logical"
    TOOL = "tool"


class InputPhase(Enum):
    BEGIN = "begin"
    ON = "on"
    END = "end"


@dataclass(frozen=True)
class KeyboardConditionSpec:
    key: Union[str, List[str]]
    phase: InputPhase = InputPhase.ON


@dataclass(frozen=True)
class MouseConditionSpec:
    button: str
    phase: InputPhase = InputPhase.ON


@dataclass(frozen=True)
class ButtonConditionSpec:
    name: str


@dataclass(frozen=True)
class CollisionConditionSpec:
    left: ActorSelectorSpec
    right: ActorSelectorSpec


@dataclass(frozen=True)
class LogicalConditionSpec:
    predicate_name: str
    target: ActorSelectorSpec


@dataclass(frozen=True)
class ToolConditionSpec:
    name: str
    tool_docstring: str


ConditionSpec = Union[
    KeyboardConditionSpec,
    MouseConditionSpec,
    ButtonConditionSpec,
    CollisionConditionSpec,
    LogicalConditionSpec,
    ToolConditionSpec,
]


class GlobalValueKind(Enum):
    INT = "int"
    FLOAT = "float"
    STR = "str"
    BOOL = "bool"
    LIST = "list"
    ACTOR_REF = "actor_ref"


@dataclass(frozen=True)
class ActorRefValue:
    uid: str
    actor_type: Optional[str] = None


@dataclass(frozen=True)
class GlobalVariableSpec:
    name: str
    kind: GlobalValueKind
    value: Union[PrimitiveValue, ListValue, ActorRefValue]
    list_elem_kind: Optional[str] = None


@dataclass(frozen=True)
class ActorInstanceSpec:
    actor_type: str
    uid: str
    fields: Dict[str, Union[PrimitiveValue, ListValue]]


@dataclass(frozen=True)
class RuleSpec:
    condition: ConditionSpec
    action_name: str


@dataclass(frozen=True)
class TileMapSpec:
    width: int
    height: int
    tile_size: int
    tile_grid: List[List[int]]
    tile_defs: Dict[int, "TileSpec"] = field(default_factory=dict)


@dataclass(frozen=True)
class ColorSpec:
    r: int
    g: int
    b: int
    symbol: Optional[str] = None
    description: Optional[str] = None


@dataclass(frozen=True)
class TileSpec:
    block_mask: Optional[int] = None
    color: Optional[ColorSpec] = None
    sprite: Optional[str] = None


class CameraMode(Enum):
    FIXED = "fixed"
    FOLLOW = "follow"


@dataclass(frozen=True)
class CameraSpec:
    mode: CameraMode
    x: Optional[int] = None
    y: Optional[int] = None
    target_uid: Optional[str] = None


@dataclass(frozen=True)
class ResourceSpec:
    name: str
    path: str


@dataclass(frozen=True)
class AnimationClipSpec:
    name: str
    frames: List[int]
    ticks_per_frame: int = 8
    loop: bool = True


@dataclass(frozen=True)
class SpriteSpec:
    resource: str
    frame_width: int
    frame_height: int
    clips: List[AnimationClipSpec]
    name: Optional[str] = None
    uid: Optional[str] = None
    actor_type: Optional[str] = None
    default_clip: Optional[str] = None
    row: int = 0
    scale: float = 1.0
    flip_x: bool = True
    offset_x: float = 0.0
    offset_y: float = 0.0
    symbol: Optional[str] = None
    description: Optional[str] = None


@dataclass(frozen=True)
class SceneSpec:
    gravity_enabled: bool = False


@dataclass(frozen=True)
class ProjectSpec:
    actor_schemas: Dict[str, Dict[str, str]]
    globals: List[GlobalVariableSpec]
    actors: List[ActorInstanceSpec]
    rules: List[RuleSpec]
    tile_map: Optional[TileMapSpec]
    camera: Optional[CameraSpec]
    actions: List[ActionIR]
    predicates: List[PredicateIR]
    resources: List[ResourceSpec]
    sprites: List[SpriteSpec]
    scene: Optional[SceneSpec]
    interface_html: Optional[str] = None
