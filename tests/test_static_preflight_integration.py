"""Real path-risk/fallback integration across local and provider verification."""

from __future__ import annotations

import json

import pytest

from samuel.core.bus import Bus
from samuel.core.commands import RequestCandidateVerificationCommand
from samuel.core.types import GateResult
from samuel.slices.path_risk.gate import PathRiskGate
from samuel.slices.pr_gates.handler import PRGatesHandler
from samuel.slices.pr_gates.tests.test_handler import (
    TestPreflightGateOrdering as _PreflightFixtures,
)
from samuel.slices.pr_gates.tests.test_handler import (
    _candidate_authority,
    _CandidateSCM,
    _collect_events,
    _ProviderCoordinator,
    _reference_command,
    _VerificationSpy,
)


@pytest.mark.parametrize("mode", ["local", "reference_provider", "foreign_candidate"])
@pytest.mark.parametrize("outcome", ["pass", "finding", "exception", "skipped"])
def test_real_path_risk_precedes_candidate_and_preserves_evidence(tmp_path, mode, outcome):
    _PreflightFixtures._write_gates(tmp_path, required=[7, 11])
    (tmp_path / "path_risk.json").write_text(
        json.dumps({"classes": [{"name": "secrets", "level": "block", "patterns": [".env"]}]})
    )
    scanner = PathRiskGate.from_config(tmp_path)
    assert scanner is not None
    run_scanner = scanner.run
    trace = []

    def scan(ctx):
        trace.append("scanner")
        if outcome == "exception":
            raise RuntimeError("synthetic unavailable scanner")
        if outcome == "skipped":
            return GateResult(
                gate="path_risk",
                passed=None,
                executed=False,
                status="skipped_precondition",
                reason="scanner prerequisite absent",
            )
        return run_scanner(ctx)

    scanner.run = scan
    bus = Bus()
    events = _collect_events(bus)
    verifier = _VerificationSpy()

    def verify(cmd):
        trace.append("candidate")
        return verifier(cmd)

    bus.register_command("VerifyAC", verify)

    class Provider(_ProviderCoordinator):
        def request(self, **kwargs):
            trace.append("candidate")
            return super().request(**kwargs)

    provider = Provider() if mode != "local" else None
    scm = _CandidateSCM()
    scm.changed_files = (".env",) if outcome == "finding" else ("h.py",)
    handler = PRGatesHandler(
        bus,
        scm=scm,
        config_dir=tmp_path,
        external_gates=[scanner],
        provider_verification=provider,
        authority_store=_candidate_authority(tmp_path, scm),
    )
    if mode == "foreign_candidate":
        result = handler.handle_provider_candidate(
            RequestCandidateVerificationCommand(issue_number=521, head_sha=scm.HEAD_SHA)
        )
    else:
        result = handler.handle(_reference_command(scm))
    assert trace == (["scanner", "candidate"] if outcome == "pass" else ["scanner"])
    if outcome != "pass":
        assert verifier.calls == 0
        assert provider is None or provider.calls == []
        assert scm.pr_calls == 0
        assert not any(e.name in {"PRCreated", "HealingSuggested"} for e in events)
        if mode != "foreign_candidate":
            evidence = result["gate_results"]
            assert sum(g["gate"] == 7 for g in evidence) == 1
            assert sum(g["gate"] == "path_risk" for g in evidence) == 1
            gate11 = next(g for g in evidence if g["gate"] == 11)
            assert (gate11["executed"], gate11["passed"], gate11["status"]) == (
                False,
                None,
                "skipped_precondition",
            )
            assert len([e for e in events if e.name == "GateEvaluationCompleted"]) == 1
