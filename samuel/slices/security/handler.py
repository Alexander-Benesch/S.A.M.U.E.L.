from __future__ import annotations

import logging
import re
from typing import Any

from samuel.core.bus import Bus
from samuel.core.command_safety import validate_command_text
from samuel.core.events import PromptInjectionRiskDetected, SecretRiskDetected
from samuel.core.ports import IConfig, IPromptRiskAnalyzer
from samuel.core.security_policy import SECRET_RULES, normalize_prompt_signal_text
from samuel.core.types import GateContext

log = logging.getLogger(__name__)

_INJECTION_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ignore_previous_instructions", re.compile(r"\bignore\s+previous\s+instructions\b")),
    ("ignore_all_instructions", re.compile(r"\bignore\s+all\s+instructions\b")),
    ("ignore_your_instructions", re.compile(r"\bignore\s+your\s+instructions\b")),
    ("disregard_your", re.compile(r"\bdisregard\s+your\b")),
    ("you_are_now", re.compile(r"\byou\s+are\s+now\b")),
    ("new_instructions", re.compile(r"\bnew\s+instructions\s*:")),
    ("system_prompt", re.compile(r"\bsystem\s+prompt\s*:")),
    ("role_takeover_act_as", re.compile(r"\bact\s+as(?:\s+(?:a|an))?\b")),
    ("role_takeover_pretend", re.compile(r"\bpretend\s+(?:to\s+be|you\s+are)\b")),
)


class SecurityHandler(IPromptRiskAnalyzer):
    def __init__(
        self,
        bus: Bus,
        config: IConfig | None = None,
    ) -> None:
        self._bus = bus
        self._config = config

    def scan_for_secrets(self, content: str) -> list[dict[str, Any]]:
        return self._scan_lines(enumerate(content.splitlines(), 1))

    def scan_diff_for_secrets(self, diff: str) -> list[dict[str, Any]]:
        """Scan added candidate lines while allowing removal of old secrets."""

        added_lines = (
            (line_number, line[1:])
            for line_number, line in enumerate(diff.splitlines(), 1)
            if line.startswith("+") and not line.startswith("+++")
        )
        return self._scan_lines(added_lines)

    @staticmethod
    def _scan_lines(lines: Any) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        for i, line in lines:
            for rule in SECRET_RULES:
                if rule.scan and rule.detector.search(line):
                    findings.append(
                        {
                            "line": i,
                            "rule_id": rule.rule_id,
                            "severity": rule.severity,
                            "disposition": rule.disposition,
                        }
                    )
                    break
        return findings

    def check_prompt_injection(self, text: str) -> dict[str, Any]:
        indicators: list[str] = []
        normalized = normalize_prompt_signal_text(text)

        for rule_id, pattern in _INJECTION_RULES:
            if pattern.search(normalized):
                indicators.append(rule_id)

        return {
            "suspicious": len(indicators) > 0,
            "indicators": indicators,
        }

    def publish_advisory_secret_findings(
        self,
        context: GateContext,
        findings: list[dict[str, Any]],
    ) -> None:
        """Publish commit-bound evidence without copying a matched secret."""

        if not findings:
            return
        payload: dict[str, Any] = {
            "issue": context.issue_number,
            "cat": "security",
            "evt": "secret_shape_signal",
            "severity": "warning",
            "disposition": "advisory",
            "reason": "Candidate diff matched advisory secret-shape rules",
            "rule_ids": sorted({str(finding["rule_id"]) for finding in findings}),
            "lines": sorted({int(finding["line"]) for finding in findings})[:20],
            "owasp_risk": "agentic_supply_chain",
            "ai_act_article": "Art. 15",
        }
        if context.subject is not None:
            payload["evaluation_subject"] = context.subject.as_dict()
        self._bus.publish(
            SecretRiskDetected(
                payload=payload,
                correlation_id=context.correlation_id,
            )
        )

    def inspect_issue_text(
        self,
        *,
        issue_number: int,
        title: str,
        body: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        """Publish bounded advisory evidence before issue text reaches the LLM."""

        return self.inspect_text(
            issue_number=issue_number,
            source="planning_issue_input",
            text=f"{title}\n{body}",
            correlation_id=correlation_id,
        )

    def inspect_text(
        self,
        *,
        issue_number: int,
        source: str,
        text: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        """Publish bounded advisory evidence for one named LLM input."""

        result = self.check_prompt_injection(text)
        if result["suspicious"]:
            self._bus.publish(
                PromptInjectionRiskDetected(
                    payload={
                        "issue": issue_number,
                        "cat": "security",
                        "evt": "prompt_injection_signal",
                        "severity": "warning",
                        "disposition": "advisory",
                        "reason": "LLM input matched prompt-injection phrase heuristics",
                        "input_source": source,
                        "indicators": result["indicators"],
                        "owasp_risk": "agent_goal_hijack",
                        "ai_act_article": "Art. 15",
                    },
                    correlation_id=correlation_id,
                )
            )
        return result

    def validate_command_safety(self, command_text: str) -> dict[str, Any]:
        return validate_command_text(command_text)
