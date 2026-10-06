"""Planning-Skeleton-Integration ueber den realen Adapter (#433)."""

from __future__ import annotations

from samuel.adapters.skeleton.python_ast import PythonASTBuilder
from samuel.slices.planning.handler import (
    _collect_plan_skeleton,
    _render_plan_skeleton,
    _serialize_plan_skeleton,
)


def test_real_python_builder_populates_planning_context(tmp_path) -> None:
    source = tmp_path / "module.py"
    source.write_text(
        "def real_planning_symbol():\n    pass\n\ndef unrelated_symbol():\n    pass\n",
    )

    skeleton = _collect_plan_skeleton([PythonASTBuilder()], tmp_path)
    rendered = _render_plan_skeleton(skeleton, ["real_planning_symbol"])
    serialized = _serialize_plan_skeleton(skeleton)

    assert "module.py" in skeleton
    assert "real_planning_symbol" in rendered
    assert "unrelated_symbol" not in rendered
    assert serialized is not None
    assert {entry["name"] for entry in serialized["module.py"]} == {
        "real_planning_symbol",
        "unrelated_symbol",
    }
