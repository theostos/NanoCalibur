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


@dataclass(frozen=True)
class DictType(FieldType):
    key: FieldType
    value: FieldType


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
    if isinstance(ft, DictType):
        return f"Record<{to_ts_type(ft.key)}, {to_ts_type(ft.value)}>"
    raise AssertionError("Unknown field type")
