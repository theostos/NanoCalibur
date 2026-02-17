from typing import Dict
from nanocalibur.typesys import FieldType


class SchemaRegistry:
    """
    Holds actor schemas for semantic validation.
    """

    def __init__(self):
        self.actor_fields: Dict[str, Dict[str, FieldType]] = {}

    def register_actor(self, name: str, fields: Dict[str, FieldType]):
        if name in self.actor_fields:
            raise ValueError(f"Actor schema '{name}' already declared.")
        self.actor_fields[name] = fields

    def has_field(self, actor_type: str, field: str) -> bool:
        return field in self.actor_fields.get(actor_type, {})

    def field_type(self, actor_type: str, field: str) -> FieldType:
        try:
            return self.actor_fields[actor_type][field]
        except KeyError as exc:
            raise KeyError(f"Unknown field '{field}' on actor '{actor_type}'.") from exc
