"""#368 Task 5: SARIF-Audit-Sink."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from samuel.adapters.audit.sarif import SARIFAuditSink, is_finding
from samuel.core.events import PromptInjectionRiskDetected


def _doc(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


class TestIsFinding:
    def test_owasp_risk_is_finding(self):
        assert is_finding({"owasp_risk": "A01:2021"}) is True

    def test_finding_event_name(self):
        assert is_finding({"message_name": "TamperDetected"}) is True

    def test_plain_event_not_finding(self):
        assert is_finding({"message_name": "LLMCallCompleted"}) is False
        assert is_finding({}) is False


class TestSARIFAuditSink:
    def test_finding_written_as_result(self, tmp_path: Path):
        sink = SARIFAuditSink(tmp_path / "f.sarif")
        sink.write(
            {
                "payload": {
                    "message_name": "GateFailed",
                    "owasp_risk": "A05:2021",
                    "reason": "Destruktiver Diff",
                    "gate": "13b",
                    "correlation_id": "c1",
                    "files": ["a.py"],
                }
            }
        )
        doc = _doc(tmp_path / "f.sarif")
        assert doc["version"] == "2.1.0"
        results = doc["runs"][0]["results"]
        assert len(results) == 1
        r = results[0]
        assert r["ruleId"] == "A05:2021"
        assert r["level"] == "error"
        assert "Destruktiver Diff" in r["message"]["text"]
        assert r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "a.py"
        assert r["properties"]["correlation_id"] == "c1"

    def test_non_finding_ignored(self, tmp_path: Path):
        sink = SARIFAuditSink(tmp_path / "f.sarif")
        sink.write({"payload": {"message_name": "LLMCallCompleted", "tokens": 5}})
        assert not (tmp_path / "f.sarif").exists()

    def test_advisory_finding_is_warning(self, tmp_path: Path):
        sink = SARIFAuditSink(tmp_path / "f.sarif")
        sink.write(
            PromptInjectionRiskDetected(
                payload={
                    "message_name": "PromptInjectionRiskDetected",
                    "owasp_risk": "agent_goal_hijack",
                    "reason": "heuristic signal",
                    "disposition": "advisory",
                },
                correlation_id="corr-advisory",
            )
        )

        result = _doc(tmp_path / "f.sarif")["runs"][0]["results"][0]
        assert result["level"] == "warning"
        assert result["properties"]["disposition"] == "advisory"

    def test_results_accumulate(self, tmp_path: Path):
        sink = SARIFAuditSink(tmp_path / "f.sarif")
        sink.write({"payload": {"owasp_risk": "A01:2021", "reason": "secret"}})
        sink.write({"payload": {"owasp_risk": "A05:2021", "reason": "misconfig"}})
        doc = _doc(tmp_path / "f.sarif")
        assert len(doc["runs"][0]["results"]) == 2
        rule_ids = {r["id"] for r in doc["runs"][0]["tool"]["driver"]["rules"]}
        assert rule_ids == {"A01:2021", "A05:2021"}

    def test_query_returns_empty(self, tmp_path: Path):
        from samuel.core.types import AuditQuery

        sink = SARIFAuditSink(tmp_path / "f.sarif")
        assert sink.query(AuditQuery()) == []
