import dataclasses

import pytest

from typesys import FieldType, ListType, Prim, PrimType, to_ts_type


def test_to_ts_type_for_primitives():
    assert to_ts_type(PrimType(Prim.INT)) == "number"
    assert to_ts_type(PrimType(Prim.FLOAT)) == "number"
    assert to_ts_type(PrimType(Prim.STR)) == "string"
    assert to_ts_type(PrimType(Prim.BOOL)) == "boolean"


def test_to_ts_type_for_primitive_lists():
    assert to_ts_type(ListType(PrimType(Prim.INT))) == "Array<number>"
    assert to_ts_type(ListType(PrimType(Prim.STR))) == "Array<string>"


def test_to_ts_type_rejects_unknown_field_type():
    @dataclasses.dataclass(frozen=True)
    class UnknownType(FieldType):
        pass

    with pytest.raises(AssertionError, match="Unknown field type"):
        to_ts_type(UnknownType())
