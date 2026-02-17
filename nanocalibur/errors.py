class DSLError(Exception):
    """Base DSL error."""

class DSLValidationError(DSLError):
    """Raised when DSL source violates rules."""
