import ast
from typing import Dict

from nanocalibur.typesys import FieldType, Prim, PrimType

_ALLOWED_BIN = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.Mod: "%",
}

_ALLOWED_BOOL = {
    ast.And: "&&",
    ast.Or: "||",
}

_ALLOWED_CMP = {
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
    ast.Is: "==",
    ast.IsNot: "!=",
}

_ALLOWED_UNARY = {
    ast.Not: "!",
    ast.UAdd: "+",
    ast.USub: "-",
}

_PRIM_NAMES = {
    "int": Prim.INT,
    "float": Prim.FLOAT,
    "str": Prim.STR,
    "bool": Prim.BOOL,
}

BASE_ACTOR_FIELDS: Dict[str, FieldType] = {
    "uid": PrimType(Prim.STR),
    "x": PrimType(Prim.FLOAT),
    "y": PrimType(Prim.FLOAT),
    "vx": PrimType(Prim.FLOAT),
    "vy": PrimType(Prim.FLOAT),
    "w": PrimType(Prim.FLOAT),
    "h": PrimType(Prim.FLOAT),
    "z": PrimType(Prim.FLOAT),
    "active": PrimType(Prim.BOOL),
    "block_mask": PrimType(Prim.INT),
    "parent": PrimType(Prim.STR),
    "sprite": PrimType(Prim.STR),
}

BASE_ACTOR_NO_DEFAULT_FIELDS = {"uid", "w", "h", "parent", "sprite", "block_mask"}
BASE_ACTOR_DEFAULT_OVERRIDES = {
    "active": True,
    "z": 0.0,
    "x": 0.0,
    "y": 0.0,
    "vx": 0.0,
    "vy": 0.0,
}

CALLABLE_EXPR_PREFIX = "__nc_callable__:"

__all__ = [
    "_ALLOWED_BIN",
    "_ALLOWED_BOOL",
    "_ALLOWED_CMP",
    "_ALLOWED_UNARY",
    "_PRIM_NAMES",
    "BASE_ACTOR_FIELDS",
    "BASE_ACTOR_NO_DEFAULT_FIELDS",
    "BASE_ACTOR_DEFAULT_OVERRIDES",
    "CALLABLE_EXPR_PREFIX",
]
