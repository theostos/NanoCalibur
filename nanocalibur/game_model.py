from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union

from nanocalibur.ir import ActionIR, PredicateIR

PrimitiveValue = Union[int, float, str, bool]
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
    COLLISION = "collision"
    LOGICAL = "logical"


class InputPhase(Enum):
    BEGIN = "begin"
    ON = "on"
    END = "end"


@dataclass(frozen=True)
class KeyboardConditionSpec:
    key: str
    phase: InputPhase = InputPhase.ON


@dataclass(frozen=True)
class MouseConditionSpec:
    button: str
    phase: InputPhase = InputPhase.ON


@dataclass(frozen=True)
class CollisionConditionSpec:
    left: ActorSelectorSpec
    right: ActorSelectorSpec


@dataclass(frozen=True)
class LogicalConditionSpec:
    predicate_name: str
    target: ActorSelectorSpec


ConditionSpec = Union[
    KeyboardConditionSpec,
    MouseConditionSpec,
    CollisionConditionSpec,
    LogicalConditionSpec,
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
    solid_tiles: List[Tuple[int, int]]


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
class ProjectSpec:
    actor_schemas: Dict[str, Dict[str, str]]
    globals: List[GlobalVariableSpec]
    actors: List[ActorInstanceSpec]
    rules: List[RuleSpec]
    tile_map: Optional[TileMapSpec]
    camera: Optional[CameraSpec]
    actions: List[ActionIR]
    predicates: List[PredicateIR]
