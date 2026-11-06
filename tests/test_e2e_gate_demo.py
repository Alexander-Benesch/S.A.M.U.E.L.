"""#368 Task 8: E2E-Demo + FP-Tracking.

Szenario: ein PR fuehrt bewusst (a) eine erfundene Funktion/Import und (b) eine
Workflow-Permission-Erweiterung ein. Erwartung: beide Findings werden VOR dem
Merge gefangen — durch den Symbol-Resolution-Gate (a) und den Path-Risk-Gate (b).
Anschliessend wird der SARIF-Export geprueft und das FP-Volumen aus dem
Audit-Trail aggregiert. Reproduzierbar via FixedResponseAdapter.
"""

from __future__ import annotations

import json
from pathlib import Path

from samuel.adapters.audit.sarif import SARIFAuditSink
from samuel.adapters.llm.fixed import FixedResponseAdapter
from samuel.core.types import GateContext
from samuel.slices.dashboard.data import get_finding_stats
from samuel.slices.path_risk.gate import PathRiskGate
from samuel.slices.pr_gates.gates import gate_7_scope_guard
from samuel.slices.symbol_resolution.gate import SymbolResolutionGate

PATH_RISK_CLASSES = [
    {"name": "secrets", "level": "block", "owasp": "A01:2021", "patterns": [".env"]},
    {
        "name": "workflow-permissions",
        "level": "warn",
        "owasp": "A05:2021",
        "patterns": [".github/workflows/", ".gitea/"],
    },
]

# Der "vom LLM erzeugte" Diff: erfundener Import + Workflow-Permission.
DEMO_DIFF = (
    "+++ b/samuel/feature.py\n"
    "+import totally_made_up_hallucination_pkg\n"
    "+def run():\n"
    "+    return totally_made_up_hallucination_pkg.go()\n"
    "+++ b/.github/workflows/deploy.yml\n"
    "+permissions: write-all\n"
)
DEMO_FILES = ["samuel/feature.py", ".github/workflows/deploy.yml"]


class _FakeBus:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)


def test_reproducible_llm_source():
    """FixedResponseAdapter macht das Szenario deterministisch."""
    llm = FixedResponseAdapter(
        "## WRITE: samuel/feature.py\nimport totally_made_up_hallucination_pkg\n## END_WRITE"
    )
    out1 = llm.complete([{"role": "user", "content": "impl"}]).text
    out2 = FixedResponseAdapter(llm._responses).complete([{"role": "user", "content": "impl"}]).text
    assert "totally_made_up_hallucination_pkg" in out1
    assert out1 == out2


def test_both_findings_caught_before_merge(tmp_path: Path):
    ctx = GateContext(issue_number=99, branch="feat/x", changed_files=DEMO_FILES, diff=DEMO_DIFF)

    # (b) Workflow-Permission -> Path-Risk warn
    pr = PathRiskGate(PATH_RISK_CLASSES).run(ctx)
    assert "workflow-permissions" in pr.reason

    # (a) erfundener Import -> Symbol-Resolution Finding (LLM09)
    bus = _FakeBus()
    sr = SymbolResolutionGate(bus=bus, project_root=tmp_path, config_dir=tmp_path).run(ctx)
    assert sr.owasp_risk == "LLM09:2025"
    unresolved = [e for e in bus.events if e.name == "UnresolvedSymbol"]
    assert unresolved
    assert "totally_made_up_hallucination_pkg" in unresolved[0].payload["symbols"]


def test_configured_path_risk_is_authoritative_and_blocks_private_keys() -> None:
    config_dir = Path(__file__).parents[1] / "config"
    path_risk = PathRiskGate.from_config(config_dir)
    assert path_risk is not None
    context = GateContext(
        issue_number=99,
        branch="feat/key-check",
        changed_files=["keys/server.pem", "keys/id_rsa"],
        diff="private key material",
        path_risk_configured=True,
    )

    assert gate_7_scope_guard(context).passed is True
    result = path_risk.run(context)
    assert result.passed is False
    assert "server.pem" in result.reason


def test_findings_exported_to_sarif(tmp_path: Path):
    sink = SARIFAuditSink(tmp_path / "findings.sarif")
    # Findings wie sie der Bus/Audit liefert (owasp_risk -> SARIF-Result).
    sink.write(
        {
            "payload": {
                "message_name": "UnresolvedSymbol",
                "owasp_risk": "LLM09:2025",
                "reason": "Nicht aufloesbare Imports: totally_made_up_hallucination_pkg",
                "issue": 99,
            }
        }
    )
    sink.write(
        {
            "payload": {
                "message_name": "GateFailed",
                "owasp_risk": "A05:2021",
                "reason": "workflow-permissions",
                "gate": "path_risk",
                "files": [".github/workflows/deploy.yml"],
            }
        }
    )
    doc = json.loads((tmp_path / "findings.sarif").read_text())
    rule_ids = {r["ruleId"] for r in doc["runs"][0]["results"]}
    assert rule_ids == {"LLM09:2025", "A05:2021"}


def test_fp_stats_from_audit_trail(tmp_path: Path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    rows = [
        {"payload": {"message_name": "UnresolvedSymbol", "owasp_risk": "LLM09:2025", "issue": 1}},
        {"payload": {"message_name": "GateFailed", "owasp_risk": "A05:2021", "issue": 1}},
        {"payload": {"message_name": "LLMCallCompleted", "tokens": 5}},  # kein Finding
    ]
    (log_dir / "agent.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    stats = get_finding_stats(str(tmp_path))
    assert stats["total"] == 2
    assert stats["by_event"]["UnresolvedSymbol"] == 1
    assert stats["issues_with_findings"] == 1
