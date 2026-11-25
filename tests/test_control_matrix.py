from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

import tools.control_matrix as control_matrix
from tools.control_matrix import OUTPUT_PATH, MatrixError, load_matrix, render, validate


def test_checked_in_capability_matrix_is_valid_and_fresh() -> None:
    matrix = load_matrix()

    validate(matrix)

    assert OUTPUT_PATH.read_text(encoding="utf-8") == render(matrix)


def test_workflow_command_drift_is_rejected() -> None:
    matrix = deepcopy(load_matrix())
    matrix["observed_workflows"]["standard"].append("UnreviewedCommand")

    with pytest.raises(MatrixError, match="workflow inventory drift"):
        validate(matrix)


def test_release_baseline_status_is_derived_from_control_readiness() -> None:
    matrix = deepcopy(load_matrix())
    current = matrix["release_baseline"]["status"]
    matrix["release_baseline"]["status"] = "blocked" if current == "ready" else "ready"

    with pytest.raises(MatrixError, match="release baseline status must be derived"):
        validate(matrix)


def test_real_reference_qualification_cannot_claim_success_with_missing_evidence() -> None:
    matrix = deepcopy(load_matrix())
    matrix["reference_qualification"]["status"] = "qualified"
    matrix["reference_qualification"]["qualified_release"] = "v2.0.0a8"
    matrix["reference_qualification"]["missing"] = ["positive path"]

    with pytest.raises(MatrixError, match="requires a release and no missing evidence"):
        validate(matrix)


def test_qualified_reference_renders_empty_missing_evidence_as_none() -> None:
    matrix = deepcopy(load_matrix())
    matrix["reference_qualification"]["status"] = "qualified"
    matrix["reference_qualification"]["qualified_release"] = "v2.0.0a15"
    matrix["reference_qualification"]["missing"] = []

    assert "| Für Qualification fehlt | — |" in render(matrix)


def test_audited_paths_exclude_untracked_local_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracked = tmp_path / "config" / "tracked.json"
    local = tmp_path / "config" / "license.json"
    tracked.parent.mkdir()
    tracked.write_text("{}", encoding="utf-8")
    local.write_text('{"local": true}', encoding="utf-8")
    monkeypatch.setattr(control_matrix, "ROOT", tmp_path)
    monkeypatch.setattr(control_matrix, "OUTPUT_PATH", tmp_path / "docs" / "output.md")
    monkeypatch.setattr(control_matrix, "MATRIX_PATH", tmp_path / "docs" / "matrix.json")
    monkeypatch.setattr(control_matrix, "_tracked_paths", lambda: {tracked})

    assert control_matrix._audited_paths() == [tracked]


def test_source_digest_tracks_changelog_but_not_local_or_generated_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    local = tmp_path / "config" / "license.json"
    output = tmp_path / "docs" / "CAPABILITY_MATRIX.md"
    runtime_reference = tmp_path / "docs" / "RUNTIME_REFERENCE.md"
    adr_index = tmp_path / "docs" / "adr" / "README.md"
    for path, content in (
        (changelog, "# Changelog\n\ninitial\n"),
        (local, '{"local": true}\n'),
        (output, "generated matrix\n"),
        (runtime_reference, "generated runtime reference\n"),
        (adr_index, "generated ADR index\n"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    monkeypatch.setattr(control_matrix, "ROOT", tmp_path)
    monkeypatch.setattr(control_matrix, "OUTPUT_PATH", output)
    monkeypatch.setattr(control_matrix, "RUNTIME_REFERENCE_PATH", runtime_reference)
    monkeypatch.setattr(control_matrix, "ADR_INDEX_PATH", adr_index)
    monkeypatch.setattr(control_matrix, "MATRIX_PATH", tmp_path / "docs" / "matrix.json")
    monkeypatch.setattr(
        control_matrix,
        "_tracked_paths",
        lambda: {changelog, output, runtime_reference, adr_index},
    )

    initial = control_matrix._source_digest()
    local.write_text('{"local": false}\n', encoding="utf-8")
    output.write_text("changed generated matrix\n", encoding="utf-8")
    runtime_reference.write_text("changed generated runtime reference\n", encoding="utf-8")
    adr_index.write_text("changed generated ADR index\n", encoding="utf-8")
    assert control_matrix._source_digest() == initial

    changelog.write_text("# Changelog\n\nchanged\n", encoding="utf-8")
    assert control_matrix._source_digest() != initial
