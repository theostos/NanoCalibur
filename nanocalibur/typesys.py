from dataclasses import dataclass
from enum import Enum


class Prim(Enum):
    INT = "int"
    FLOAT = "float"
    STR = "str"
    BOOL = "bool"


@dataclass(frozen=True)
class FieldType:
    pass


@dataclass(frozen=True)
class PrimType(FieldType):
    prim: Prim


@dataclass(frozen=True)
class ListType(FieldType):
    elem: FieldType


def to_ts_type(ft: FieldType) -> str:
    if isinstance(ft, PrimType):
        if ft.prim in (Prim.INT, Prim.FLOAT):
            return "number"
        if ft.prim == Prim.STR:
            return "string"
        if ft.prim == Prim.BOOL:
            return "boolean"
    if isinstance(ft, ListType):
        return f"Array<{to_ts_type(ft.elem)}>"
    raise AssertionError("Unknown field type")
