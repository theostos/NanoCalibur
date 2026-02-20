from __future__ import annotations

import nanocalibur
import pytest

from nanocalibur.errors import DSLValidationError


def test_public_api_exposes_version_and_about() -> None:
    assert isinstance(nanocalibur.__version__, str)
    text = nanocalibur.about(print_output=False)
    assert "Coordinate system" in text
    assert "Authority" in text


def test_public_api_all_contains_core_exports() -> None:
    exported = set(nanocalibur.__all__)
    assert "compile_project" in exported
    assert "export_project" in exported
    assert "about" in exported
    assert "__version__" in exported


def test_compile_project_rejects_empty_source_with_actionable_message() -> None:
    with pytest.raises(DSLValidationError, match="Source is empty"):
        nanocalibur.compile_project("   ")
