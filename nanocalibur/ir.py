from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Union


class BindingKind(Enum):
    GLOBAL = "global"
    ACTOR = "actor"
    ACTOR_LIST = "actor_list"


@dataclass(frozen=True)
class ActorSelector:
    index: Optional[int] = None
    uid: Optional[str] = None

    def __post_init__(self):
        has_index = self.index is not None
        has_uid = self.uid is not None
        if has_index == has_uid:
            raise ValueError("ActorSelector must have exactly one selector.")


@dataclass(frozen=True)
class ParamBinding:
    name: str
    kind: BindingKind
    global_name: Optional[str] = None
    actor_selector: Optional[ActorSelector] = None
    actor_type: Optional[str] = None
    actor_list_type: Optional[str] = None


# Expressions

class Expr:
    pass


@dataclass(frozen=True)
class Const(Expr):
    value: Union[int, float, str, bool]


@dataclass(frozen=True)
class Var(Expr):
    name: str


@dataclass(frozen=True)
class Attr(Expr):
    obj: str
    field: str


@dataclass(frozen=True)
class Unary(Expr):
    op: str
    value: Expr


@dataclass(frozen=True)
class Binary(Expr):
    op: str
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Range(Expr):
    args: List[Expr]


# Statements

class Stmt:
    pass


@dataclass(frozen=True)
class Assign(Stmt):
    target: Expr
    value: Expr


@dataclass(frozen=True)
class If(Stmt):
    condition: Expr
    body: List[Stmt]
    orelse: List[Stmt]


@dataclass(frozen=True)
class While(Stmt):
    condition: Expr
    body: List[Stmt]


@dataclass(frozen=True)
class For(Stmt):
    var: str
    iterable: Expr
    body: List[Stmt]


@dataclass(frozen=True)
class ActionIR:
    name: str
    params: List[ParamBinding]
    body: List[Stmt]


@dataclass(frozen=True)
class PredicateIR:
    name: str
    param_name: str
    actor_type: str
    body: Expr
