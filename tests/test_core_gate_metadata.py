from __future__ import annotations

import pytest

from samuel.core.gate_metadata import GATE_NAMES


def test_gate_names_are_read_only() -> None:
    with pytest.raises(TypeError):
        GATE_NAMES[1] = "DriftedName"  # type: ignore[index]
