from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Union

from nanocalibur.ir import ActionIR, CallableIR, PredicateIR

PrimitiveValue = Union[int, float, str, bool, None]
StructuredValue = Union[PrimitiveValue, "ListValue", "DictValue"]
ListValue = List[StructuredValue]
DictValue = Dict[str, StructuredValue]

try:
    from enum import StrEnum  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - Python < 3.11 fallback
    class StrEnum(str, Enum):
        pass


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


class CollisionMode(Enum):
    OVERLAP = "overlap"
    CONTACT = "contact"


class InputPhase(Enum):
    BEGIN = "begin"
    ON = "on"
    END = "end"


@dataclass(frozen=True)
class KeyboardConditionSpec:
    key: Union[str, List[str]]
    phase: InputPhase = InputPhase.ON
    role_id: Optional[str] = None


@dataclass(frozen=True)
class MouseConditionSpec:
    button: str
    phase: InputPhase = InputPhase.ON
    role_id: Optional[str] = None


@dataclass(frozen=True)
class ButtonConditionSpec:
    name: str


@dataclass(frozen=True)
class CollisionConditionSpec:
    left: ActorSelectorSpec
    right: ActorSelectorSpec
    mode: CollisionMode = CollisionMode.OVERLAP


@dataclass(frozen=True)
class LogicalConditionSpec:
    predicate_name: str
    target: ActorSelectorSpec


@dataclass(frozen=True)
class ToolConditionSpec:
    name: str
    tool_docstring: str
    role_id: Optional[str] = None


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
    DICT = "dict"
    ACTOR_REF = "actor_ref"


@dataclass(frozen=True)
class ActorRefValue:
    uid: str
    actor_type: Optional[str] = None


@dataclass(frozen=True)
class GlobalVariableSpec:
    name: str
    kind: GlobalValueKind
    value: Union[PrimitiveValue, ListValue, DictValue, ActorRefValue]
    list_elem_kind: Optional[str] = None


@dataclass(frozen=True)
class ActorInstanceSpec:
    actor_type: str
    uid: str
    fields: Dict[str, Union[PrimitiveValue, ListValue, DictValue]]


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


class MultiplayerLoopMode(Enum):
    REAL_TIME = "real_time"
    TURN_BASED = "turn_based"
    HYBRID = "hybrid"


class VisibilityMode(Enum):
    SHARED = "shared"
    ROLE_FILTERED = "role_filtered"


class RoleKind(StrEnum):
    HUMAN = "human"
    AI = "ai"
    HYBRID = "hybrid"


@dataclass(frozen=True)
class CameraSpec:
    name: str
    role_id: str
    x: float = 0.0
    y: float = 0.0
    width: Optional[int] = None
    height: Optional[int] = None
    target_uid: Optional[str] = None
    offset_x: float = 0.0
    offset_y: float = 0.0


@dataclass(frozen=True)
class MultiplayerSpec:
    default_loop: MultiplayerLoopMode = MultiplayerLoopMode.REAL_TIME
    allowed_loops: List[MultiplayerLoopMode] = field(
        default_factory=lambda: [MultiplayerLoopMode.REAL_TIME]
    )
    default_visibility: VisibilityMode = VisibilityMode.SHARED
    tick_rate: int = 20
    turn_timeout_ms: int = 15_000
    hybrid_window_ms: int = 500
    game_time_scale: float = 1.0
    max_catchup_steps: int = 1


@dataclass(frozen=True)
class RoleSpec:
    id: str
    required: bool = True
    kind: RoleKind = RoleKind.HYBRID
    role_type: str = "Role"
    fields: Dict[str, Union[PrimitiveValue, ListValue, DictValue]] = field(default_factory=dict)


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
    keyboard_aliases: Dict[str, List[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class ProjectSpec:
    actor_schemas: Dict[str, Dict[str, str]]
    role_schemas: Dict[str, Dict[str, str]]
    globals: List[GlobalVariableSpec]
    actors: List[ActorInstanceSpec]
    rules: List[RuleSpec]
    tile_map: Optional[TileMapSpec]
    cameras: List[CameraSpec]
    actions: List[ActionIR]
    predicates: List[PredicateIR]
    callables: List[CallableIR]
    resources: List[ResourceSpec]
    sprites: List[SpriteSpec]
    scene: Optional[SceneSpec]
    interface_html: Optional[str] = None
    interfaces_by_role: Dict[str, str] = field(default_factory=dict)
    multiplayer: Optional[MultiplayerSpec] = None
    roles: List[RoleSpec] = field(default_factory=list)
    contains_next_turn_call: bool = False
