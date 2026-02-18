import ast
import contextvars
from contextlib import contextmanager
from typing import Iterator, Optional


_CURRENT_DSL_SOURCE: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "nanocalibur_current_dsl_source", default=None
)
_CURRENT_DSL_NODE: contextvars.ContextVar[Optional[ast.AST]] = contextvars.ContextVar(
    "nanocalibur_current_dsl_node", default=None
)


def _line_from_source(source: str, line_no: int) -> Optional[str]:
    if line_no <= 0:
        return None
    lines = source.splitlines()
    if line_no > len(lines):
        return None
    return lines[line_no - 1].strip()


def _format_with_context(
    message: str,
    *,
    source: Optional[str] = None,
    node: Optional[ast.AST] = None,
) -> str:
    source = source if source is not None else _CURRENT_DSL_SOURCE.get()
    node = node if node is not None else _CURRENT_DSL_NODE.get()
    if node is None:
        return message

    line = getattr(node, "lineno", None)
    col = getattr(node, "col_offset", None)
    if line is None:
        return message

    code: Optional[str] = None
    if source is not None:
        code = ast.get_source_segment(source, node) or _line_from_source(source, line)
        if code is not None:
            code = code.strip()

    details = [f"Location: line {line}, column {(col + 1) if col is not None else 1}"]
    if code:
        details.append(f"Code: {code}")
    return f"{message}\n" + "\n".join(details)


def format_dsl_diagnostic(message: str, *, node: Optional[ast.AST] = None) -> str:
    """Attach best-effort source context to a warning/info diagnostic string."""
    return _format_with_context(message, node=node)


@contextmanager
def dsl_source_context(source: str) -> Iterator[None]:
    token = _CURRENT_DSL_SOURCE.set(source)
    try:
        yield
    finally:
        _CURRENT_DSL_SOURCE.reset(token)


@contextmanager
def dsl_node_context(node: Optional[ast.AST]) -> Iterator[None]:
    token = _CURRENT_DSL_NODE.set(node)
    try:
        yield
    finally:
        _CURRENT_DSL_NODE.reset(token)


class DSLError(Exception):
    """Base DSL error."""


class DSLValidationError(DSLError):
    """Raised when DSL source violates rules."""

    def __init__(self, message: str, *, node: Optional[ast.AST] = None):
        super().__init__(_format_with_context(message, node=node))
