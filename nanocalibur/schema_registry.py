from typing import Dict
from nanocalibur.typesys import FieldType


class SchemaRegistry:
    """
    Holds actor and role schemas for semantic validation.
    """

    def __init__(self):
        self.actor_fields: Dict[str, Dict[str, FieldType]] = {}
        self.role_fields: Dict[str, Dict[str, FieldType]] = {}

    def register_actor(self, name: str, fields: Dict[str, FieldType]):
        if name in self.actor_fields:
            raise ValueError(f"Actor schema '{name}' already declared.")
        self.actor_fields[name] = fields

    def register_role(self, name: str, fields: Dict[str, FieldType]):
        if name in self.role_fields:
            raise ValueError(f"Role schema '{name}' already declared.")
        self.role_fields[name] = fields

    def has_actor_field(self, actor_type: str, field: str) -> bool:
        return field in self.actor_fields.get(actor_type, {})

    def actor_field_type(self, actor_type: str, field: str) -> FieldType:
        try:
            return self.actor_fields[actor_type][field]
        except KeyError as exc:
            raise KeyError(f"Unknown field '{field}' on actor '{actor_type}'.") from exc

    def has_role_field(self, role_type: str, field: str) -> bool:
        return field in self.role_fields.get(role_type, {})

    def role_field_type(self, role_type: str, field: str) -> FieldType:
        try:
            return self.role_fields[role_type][field]
        except KeyError as exc:
            raise KeyError(f"Unknown field '{field}' on role '{role_type}'.") from exc
