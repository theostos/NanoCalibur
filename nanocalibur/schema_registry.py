import copy
from typing import Any, Dict
from nanocalibur.typesys import FieldType


class SchemaRegistry:
    """
    Holds actor and role schemas for semantic validation.
    """

    def __init__(self):
        self.actor_fields: Dict[str, Dict[str, FieldType]] = {}
        self.role_fields: Dict[str, Dict[str, FieldType]] = {}
        self.role_local_fields: Dict[str, Dict[str, FieldType]] = {}
        self.role_local_defaults: Dict[str, Dict[str, Any]] = {}

    def register_actor(self, name: str, fields: Dict[str, FieldType]):
        if name in self.actor_fields:
            raise ValueError(f"Actor schema '{name}' already declared.")
        self.actor_fields[name] = fields

    def register_role(
        self,
        name: str,
        fields: Dict[str, FieldType],
        *,
        local_fields: Dict[str, FieldType] | None = None,
        local_defaults: Dict[str, Any] | None = None,
    ):
        if name in self.role_fields:
            raise ValueError(f"Role schema '{name}' already declared.")
        self.role_fields[name] = fields
        self.role_local_fields[name] = dict(local_fields or {})
        self.role_local_defaults[name] = copy.deepcopy(local_defaults or {})

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

    def has_role_local_field(self, role_type: str, field: str) -> bool:
        return field in self.role_local_fields.get(role_type, {})

    def role_local_field_type(self, role_type: str, field: str) -> FieldType:
        try:
            return self.role_local_fields[role_type][field]
        except KeyError as exc:
            raise KeyError(
                f"Unknown local field '{field}' on role '{role_type}'."
            ) from exc

    def role_local_defaults_for(self, role_type: str) -> Dict[str, Any]:
        return copy.deepcopy(self.role_local_defaults.get(role_type, {}))
