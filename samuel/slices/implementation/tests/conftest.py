from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_default_runtime_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Direct handler tests must never write default runtime data into the repository."""

    monkeypatch.chdir(tmp_path)
