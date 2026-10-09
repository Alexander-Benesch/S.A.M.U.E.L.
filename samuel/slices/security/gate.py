"""Commit-bound security gates backed by the security policy slice."""

from __future__ import annotations

from samuel.core.ports import IExternalGate
from samuel.core.types import GateContext, GateResult
from samuel.slices.security.handler import SecurityHandler


class DiffSecretGate(IExternalGate):
    """Fail closed on secrets added by the complete candidate diff."""

    name = "diff_secret_scan"

    def __init__(self, security: SecurityHandler) -> None:
        self._security = security

    def run(self, context: GateContext) -> GateResult:
        findings = self._security.scan_diff_for_secrets(context.diff or "")
        blocking = [finding for finding in findings if finding["disposition"] == "blocking"]
        advisory = [finding for finding in findings if finding["disposition"] == "advisory"]
        self._security.publish_advisory_secret_findings(context, advisory)
        if blocking:
            summary = ", ".join(
                f"{finding['rule_id']}@{finding['line']}" for finding in blocking[:5]
            )
            return GateResult(
                gate=self.name,
                passed=False,
                reason=f"Blockierende Secret-Muster in hinzugefügten Diff-Zeilen: {summary}",
                owasp_risk="agentic_supply_chain",
            )
        if advisory:
            summary = ", ".join(
                f"{finding['rule_id']}@{finding['line']}" for finding in advisory[:5]
            )
            return GateResult(
                gate=self.name,
                passed=True,
                reason=f"Advisory Secret-Formsignale: {summary}",
                owasp_risk="agentic_supply_chain",
            )
        return GateResult(
            gate=self.name,
            passed=True,
            reason="Keine Secret-Muster in hinzugefügten Diff-Zeilen",
        )
