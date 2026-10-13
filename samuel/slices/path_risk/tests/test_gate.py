"""#368 Task 2: Path-Risk-Classifier-Gate."""

from __future__ import annotations

import json
from pathlib import Path

from samuel.core.path_risk import DEFAULT_SECRET_PATH_PATTERNS
from samuel.core.types import GateContext
from samuel.slices.path_risk.gate import (
    PathRiskGate,
    classify_paths,
    load_path_risk_classes,
)

CLASSES = [
    {
        "name": "secrets",
        "level": "block",
        "owasp": "A01:2021",
        "patterns": [".env", "secrets", "*.pem"],
    },
    {
        "name": "workflow-permissions",
        "level": "warn",
        "owasp": "A05:2021",
        "patterns": [".github/workflows/", ".gitea/"],
    },
    {"name": "iac", "level": "warn", "owasp": "A05:2021", "patterns": ["*.tf", "k8s/"]},
]


def _ctx(files):
    return GateContext(issue_number=1, branch="b", changed_files=files, diff="")


class TestClassifyPaths:
    def test_matches_substring_and_glob(self):
        hits = classify_paths(
            [".github/workflows/ci.yml", "infra/main.tf", "src/app.py"],
            CLASSES,
        )
        assert hits["workflow-permissions"] == [".github/workflows/ci.yml"]
        assert hits["iac"] == ["infra/main.tf"]
        assert "secrets" not in hits


class TestPathRiskGate:
    def test_blocks_on_secret_class(self):
        res = PathRiskGate(CLASSES).run(_ctx(["config/.env"]))
        assert res.passed is False
        assert res.owasp_risk == "A01:2021"
        assert "secrets" in res.reason

    def test_pem_glob_blocks(self):
        res = PathRiskGate(CLASSES).run(_ctx(["keys/server.pem"]))
        assert res.passed is False

    def test_warn_class_passes_but_reports(self):
        res = PathRiskGate(CLASSES).run(_ctx([".gitea/workflows/x.yml", "k8s/dep.yaml"]))
        assert res.passed is True
        assert "warn" in res.reason
        assert "workflow-permissions" in res.reason

    def test_no_risky_paths_passes(self):
        res = PathRiskGate(CLASSES).run(_ctx(["src/app.py", "README.md"]))
        assert res.passed is True
        assert "Keine riskanten" in res.reason

    def test_block_takes_precedence_over_warn(self):
        res = PathRiskGate(CLASSES).run(_ctx(["main.tf", ".env"]))
        assert res.passed is False  # secret blockt, trotz warn-Treffer


class TestFromConfig:
    def test_loads_from_config_dir(self, tmp_path: Path):
        (tmp_path / "path_risk.json").write_text(json.dumps({"classes": CLASSES}))
        gate = PathRiskGate.from_config(tmp_path)
        assert gate is not None
        assert gate.run(_ctx([".env"])).passed is False

    def test_missing_config_returns_none(self, tmp_path: Path):
        assert PathRiskGate.from_config(tmp_path) is None
        assert load_path_risk_classes(tmp_path) == []

    def test_shipped_secret_class_matches_builtin_fallback(self):
        project_root = Path(__file__).resolve().parents[4]
        classes = load_path_risk_classes(project_root / "config")
        secrets = next(item for item in classes if item.get("name") == "secrets")

        assert secrets["level"] == "block"
        assert tuple(secrets["patterns"]) == DEFAULT_SECRET_PATH_PATTERNS
