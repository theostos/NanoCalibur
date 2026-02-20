from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Union


class BindingKind(Enum):
    GLOBAL = "global"
    ACTOR = "actor"
    ACTOR_LIST = "actor_list"
    ROLE = "role"
    SCENE = "scene"
    TICK = "tick"


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
class RoleSelector:
    id: str


@dataclass(frozen=True)
class ParamBinding:
    name: str
    kind: BindingKind
    global_name: Optional[str] = None
    actor_selector: Optional[ActorSelector] = None
    actor_type: Optional[str] = None
    actor_list_type: Optional[str] = None
    role_selector: Optional[RoleSelector] = None
    role_type: Optional[str] = None


# Expressions

class Expr:
    pass


@dataclass(frozen=True)
class Const(Expr):
    value: Union[int, float, str, bool, None]


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


@dataclass(frozen=True)
class CallExpr(Expr):
    name: str
    args: List[Expr]


@dataclass(frozen=True)
class ObjectExpr(Expr):
    fields: Dict[str, Expr]


@dataclass(frozen=True)
class ListExpr(Expr):
    items: List[Expr]


@dataclass(frozen=True)
class SubscriptExpr(Expr):
    value: Expr
    index: Expr


# Statements

class Stmt:
    pass


@dataclass(frozen=True)
class Assign(Stmt):
    target: Expr
    value: Expr


@dataclass(frozen=True)
class CallStmt(Stmt):
    name: str
    args: List[Expr]


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
class Yield(Stmt):
    value: Expr


@dataclass(frozen=True)
class Continue(Stmt):
    pass


@dataclass(frozen=True)
class ActionIR:
    name: str
    params: List[ParamBinding]
    body: List[Stmt]


@dataclass(frozen=True)
class PredicateIR:
    name: str
    params: List[ParamBinding]
    body: Expr
    param_name: Optional[str] = None
    actor_type: Optional[str] = None


@dataclass(frozen=True)
class CallableIR:
    name: str
    params: List[str]
    body: List[Stmt]
    return_expr: Expr
