"""Public Python API for NanoCalibur.

The package exposes a small stable surface for compilation/export workflows and
HTTP tool bridging. DSL marker classes live in ``nanocalibur.dsl_markers``.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from nanocalibur.compiler import DSLCompiler
from nanocalibur.errors import DSLError, DSLValidationError
from nanocalibur.exporter import (
    compile_project,
    export_project,
    project_to_dict,
    project_to_ir_dict,
)
from nanocalibur.mcp_bridge import NanoCaliburHTTPClient, build_fastmcp_from_http
from nanocalibur.project_compiler import ProjectCompiler
from nanocalibur.ts_generator import TSGenerator

try:
    __version__: str = version("nanocalibur")
except PackageNotFoundError:  # pragma: no cover - editable local fallback
    __version__ = "0.1.0"


def about(*, print_output: bool = True) -> str:
    """Return and optionally print the engine semantic contract.

    Args:
        print_output: Whether to print the returned summary.

    Returns:
        Human-readable semantic summary string.

    Side Effects:
        Prints to stdout when ``print_output`` is True.

    Example:
        >>> from nanocalibur import about
        >>> text = about(print_output=False)
        >>> "Coordinate system" in text
        True
    """
    text = (
        f"NanoCalibur {__version__}\n"
        "Coordinate system: world origin at top-left, +x right, +y down.\n"
        "Actor position: x/y are actor center coordinates in world pixels.\n"
        "Time units: runtime physics uses seconds; scene.elapsed increments per tick.\n"
        "Loop order: physics integration -> rule/action evaluation -> post-action collision resolve -> render.\n"
        "Input semantics: keyboard/mouse are phase-based (begin/on/end) per fixed-step tick.\n"
        "Authority: server owns globals/actors/server role fields; Local[...] role fields are client-owned only."
    )
    if print_output:
        print(text)
    return text


__all__ = [
    "__version__",
    "about",
    "DSLCompiler",
    "DSLError",
    "DSLValidationError",
    "ProjectCompiler",
    "TSGenerator",
    "compile_project",
    "export_project",
    "NanoCaliburHTTPClient",
    "build_fastmcp_from_http",
    "project_to_dict",
    "project_to_ir_dict",
]

