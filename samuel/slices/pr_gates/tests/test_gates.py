from __future__ import annotations

from unittest.mock import patch

from samuel.core.acceptance import AcceptanceApproval, parse_acceptance_contract
from samuel.core.evaluation_subject import EvaluationSubject
from samuel.core.gate_metadata import GATE_NAMES
from samuel.core.types import GateContext, GateResult
from samuel.slices.pr_gates.gates import (
    GATE_REGISTRY,
    gate_1_branch_guard,
    gate_2_plan_comment,
    gate_3_metadata_block,
    gate_5_diff_not_empty,
    gate_6_self_consistency,
    gate_7_scope_guard,
    gate_7b_contract_scope,
    gate_8_slice_gate,
    gate_9_python_syntax,
    gate_11_ac_verification,
    gate_12_ready_to_close,
    gate_13a_branch_freshness,
    gate_13b_destructive_diff,
)


def _subject() -> EvaluationSubject:
    return EvaluationSubject(
        repository="owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        contract_hash="sha256:" + "c" * 64,
        policy_version="test.v1",
        policy_digest="sha256:" + "d" * 64,
    )


def _ctx(**overrides) -> GateContext:
    defaults = {
        "issue_number": 42,
        "branch": "feature/test",
        "changed_files": ["handler.py"],
        "diff": "+new line\n-old line\n",
        "plan_comment": "## Plan\nAgent-Metadaten\n- [ ] [DIFF] handler.py\n### Akzeptanzkriterien\n- [ ] AC1",
    }
    defaults.update(overrides)
    return GateContext(**defaults)


def _acceptance_evidence(
    *,
    statuses: list[str] | None = None,
    plan: str = "- [ ] [DIFF] handler.py — changed",
) -> tuple[EvaluationSubject, dict]:
    contract = parse_acceptance_contract(plan)
    subject = EvaluationSubject(
        repository="owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        contract_hash=contract.contract_hash,
        policy_version="test.v1",
        policy_digest="sha256:" + "d" * 64,
    )
    approved = contract.with_approval(
        AcceptanceApproval(
            state="approved",
            actor="alice",
            method="comment",
            source_id="comment:2",
            approved_at="2026-08-25T10:00:00Z",
            contract_hash=contract.contract_hash,
            plan_comment_id=1,
        )
    )
    resolved = statuses or ["passed"] * len(approved.criteria)
    results = [
        {
            "criterion_id": criterion.criterion_id,
            "status": status,
            "reason": status,
            "tag": criterion.tag,
            "evidence": (
                {
                    "human_receipt": {
                        "criterion_id": criterion.criterion_id,
                        "actor": "alice",
                        "source_id": "comment:3",
                        "contract_hash": contract.contract_hash,
                        "head_sha": subject.head_sha,
                    }
                }
                if criterion.mode == "manual" and status == "passed"
                else None
            ),
        }
        for criterion, status in zip(approved.criteria, resolved, strict=True)
    ]
    return subject, {
        "schema_version": 1,
        "evaluation_subject": subject.as_dict(),
        "contract": approved.as_dict(),
        "results": results,
    }


class TestGate1BranchGuard:
    def test_pass_feature_branch(self):
        assert gate_1_branch_guard(_ctx(branch="feature/test")).passed is True

    def test_fail_main(self):
        assert gate_1_branch_guard(_ctx(branch="main")).passed is False

    def test_fail_master(self):
        assert gate_1_branch_guard(_ctx(branch="master")).passed is False

    def test_fail_empty(self):
        assert gate_1_branch_guard(_ctx(branch="")).passed is False


class TestGate2PlanComment:
    def test_pass_with_plan(self):
        assert gate_2_plan_comment(_ctx()).passed is True

    def test_fail_no_plan(self):
        assert gate_2_plan_comment(_ctx(plan_comment=None)).passed is False

    def test_fail_short_plan(self):
        assert gate_2_plan_comment(_ctx(plan_comment="short")).passed is False


class TestGate3MetadataBlock:
    def test_pass_with_metadata(self):
        assert gate_3_metadata_block(_ctx()).passed is True

    def test_fail_no_metadata(self):
        assert gate_3_metadata_block(_ctx(plan_comment="## Plan\nkein Meta")).passed is False


class TestGate5DiffNotEmpty:
    def test_pass_with_diff(self):
        assert gate_5_diff_not_empty(_ctx()).passed is True

    def test_fail_empty_diff(self):
        assert gate_5_diff_not_empty(_ctx(diff="")).passed is False

    def test_fail_whitespace_diff(self):
        assert gate_5_diff_not_empty(_ctx(diff="   \n  ")).passed is False


class TestGate6SelfConsistency:
    def test_always_passes(self):
        assert gate_6_self_consistency(_ctx()).passed is True

    def test_fails_when_most_plan_files_are_missing_from_diff(self):
        plan = "## Plan\n- samuel/a.py\n- samuel/b.py\n- samuel/c.py"
        result = gate_6_self_consistency(_ctx(plan_comment=plan, changed_files=["samuel/a.py"]))
        assert result.passed is False
        assert "b.py" in result.reason


class TestGate7ScopeGuard:
    def test_pass_normal_files(self):
        assert gate_7_scope_guard(_ctx()).passed is True

    def test_fail_env_file(self):
        assert gate_7_scope_guard(_ctx(changed_files=[".env"])).passed is False

    def test_fail_secrets(self):
        assert gate_7_scope_guard(_ctx(changed_files=["secrets.json"])).passed is False

    def test_fallback_blocks_private_key_paths(self):
        assert gate_7_scope_guard(_ctx(changed_files=["keys/server.pem"])).passed is False
        assert gate_7_scope_guard(_ctx(changed_files=["keys/id_rsa"])).passed is False

    def test_configured_path_risk_is_authoritative(self):
        result = gate_7_scope_guard(
            _ctx(changed_files=["keys/server.pem"], path_risk_configured=True)
        )
        assert result.passed is True
        assert "massgeblich" in result.reason

    def test_fail_no_files(self):
        assert gate_7_scope_guard(_ctx(changed_files=[])).passed is False

    def test_owasp_risk_on_failure(self):
        result = gate_7_scope_guard(_ctx(changed_files=[".env"]))
        assert result.owasp_risk == "A01:2021"


def _contract_scope_ctx(
    entries: str,
    *,
    changed_files: list[str],
    expansion: str = "disabled",
    architecture: dict | None = None,
) -> GateContext:
    plan = f"""### Änderungsscope
Scope-Schema: 1
{entries}
Architecture-Expansion: {expansion}

### Akzeptanzkriterien
- [ ] [DIFF] candidate
"""
    contract = parse_acceptance_contract(plan)
    subject = EvaluationSubject(
        repository="owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        contract_hash=contract.contract_hash,
        policy_version="test.v1",
        policy_digest="sha256:" + "d" * 64,
    )
    return _ctx(
        changed_files=changed_files,
        subject=subject,
        acceptance_contract=contract.as_dict(),
        architecture_policy=architecture,
    )


class TestGate7bContractScope:
    def test_exact_file_and_path_scope_pass(self):
        ctx = _contract_scope_ctx(
            "- [FILE] `README.md`\n- [PATH] `samuel/core/`",
            changed_files=["README.md", "samuel/core/types.py"],
        )

        result = gate_7b_contract_scope(ctx)

        assert result.passed is True
        assert result.status == "passed"
        assert ctx.subject is not None
        assert result.tool and result.tool["head_sha"] == ctx.subject.head_sha
        assert result.tool["diff_bytes"] == len(ctx.diff.encode("utf-8"))
        assert result.tool["diff_digest"].startswith("sha256:")

    def test_out_of_scope_blocks_with_structured_evidence(self):
        ctx = _contract_scope_ctx(
            "- [FILE] `README.md`",
            changed_files=["README.md", "samuel/core/sneaky.py"],
        )

        result = gate_7b_contract_scope(ctx)

        assert result.passed is False
        assert result.status == "failed"
        assert result.tool and result.tool["out_of_scope"] == ["samuel/core/sneaky.py"]

    def test_missing_scope_is_missing_evidence(self):
        contract = parse_acceptance_contract("- [ ] [DIFF] candidate.py")
        subject = EvaluationSubject(
            "owner/repo",
            "a" * 40,
            "b" * 40,
            contract.contract_hash,
            "test.v1",
            "sha256:" + "d" * 64,
        )
        result = gate_7b_contract_scope(
            _ctx(
                subject=subject,
                changed_files=["candidate.py"],
                acceptance_contract=contract.as_dict(),
            )
        )

        assert result.passed is False
        assert result.status == "missing_evidence"

    def test_stale_contract_is_missing_evidence(self):
        ctx = _contract_scope_ctx("- [FILE] `candidate.py`", changed_files=["candidate.py"])
        assert ctx.subject is not None
        ctx.subject = EvaluationSubject(
            ctx.subject.repository,
            ctx.subject.base_sha,
            ctx.subject.head_sha,
            "sha256:" + "e" * 64,
            ctx.subject.policy_version,
            ctx.subject.policy_digest,
        )

        result = gate_7b_contract_scope(ctx)

        assert result.passed is False
        assert result.status == "missing_evidence"

    def test_architecture_expansion_allows_addition_but_blocked_scope_wins(self):
        architecture = {
            "modules": [{"path": "samuel/core/", "role": "shared-kernel"}],
            "expansion_policy": {
                "shared-kernel": {
                    "allowed_scopes": ["samuel/core/", "tests/"],
                    "blocked_scopes": ["samuel/core/private/"],
                }
            },
        }
        passing = _contract_scope_ctx(
            "- [FILE] `samuel/core/types.py`",
            changed_files=["samuel/core/types.py", "tests/test_types.py"],
            expansion="allowed",
            architecture=architecture,
        )
        blocked = _contract_scope_ctx(
            "- [FILE] `samuel/core/types.py`",
            changed_files=["samuel/core/types.py", "samuel/core/private/key.py"],
            expansion="allowed",
            architecture=architecture,
        )

        assert gate_7b_contract_scope(passing).passed is True
        result = gate_7b_contract_scope(blocked)
        assert result.passed is False
        assert result.tool and result.tool["out_of_scope"] == ["samuel/core/private/key.py"]

    def test_missing_or_invalid_architecture_is_not_evaluated(self):
        missing = _contract_scope_ctx(
            "- [FILE] `candidate.py`",
            changed_files=["candidate.py", "tests/test_candidate.py"],
            expansion="allowed",
        )
        invalid = _contract_scope_ctx(
            "- [FILE] `candidate.py`",
            changed_files=["candidate.py", "tests/test_candidate.py"],
            expansion="allowed",
            architecture={"modules": "invalid", "expansion_policy": {}},
        )
        unresolved = _contract_scope_ctx(
            "- [FILE] `README.md`",
            changed_files=["README.md"],
            expansion="allowed",
            architecture={"modules": [], "expansion_policy": {}},
        )

        assert gate_7b_contract_scope(missing).status == "not_evaluated"
        assert gate_7b_contract_scope(invalid).status == "not_evaluated"
        assert gate_7b_contract_scope(unresolved).status == "not_evaluated"

    def test_traversal_and_duplicate_changed_files_are_not_evaluated(self):
        traversal = _contract_scope_ctx(
            "- [PATH] `samuel/`",
            changed_files=["samuel/../escape.py"],
        )
        duplicate = _contract_scope_ctx(
            "- [PATH] `samuel/`",
            changed_files=["samuel/a.py", "samuel/a.py"],
        )

        assert gate_7b_contract_scope(traversal).status == "not_evaluated"
        assert gate_7b_contract_scope(duplicate).status == "not_evaluated"


class TestGate8SliceGate:
    def _diff_block(self, file_path: str, added_lines: list[str]) -> str:
        """Build a unified-diff fragment for one file with given added lines."""
        header = (
            f"diff --git a/{file_path} b/{file_path}\n--- a/{file_path}\n+++ b/{file_path}\n@@\n"
        )
        body = "\n".join(f"+{l}" for l in added_lines) + "\n"
        return header + body

    def test_gate_8_empty_diff_passes(self):
        result = gate_8_slice_gate(_ctx(changed_files=[], diff=""))
        assert result.passed is True

    def test_gate_8_per_file_attribution(self):
        """Cross-Slice-Import IN einer Slice-Datei: Verstoss."""
        diff = self._diff_block(
            "samuel/slices/ac_verification/handler.py",
            ["from samuel.slices.audit_trail.owasp import OWASP_RISK_MAP"],
        )
        result = gate_8_slice_gate(
            _ctx(
                changed_files=["samuel/slices/ac_verification/handler.py"],
                diff=diff,
            )
        )
        assert result.passed is False
        assert "ac_verification" in result.reason
        assert "audit_trail" in result.reason

    def test_gate_8_global_test_import_allowed(self):
        """Globaler Test (tests/) darf cross-slice importieren — kein Verstoss.

        Pflaster aus #246 (string-concat 'from ' + 'samuel.slices...') wurde
        in #250 zurückgebaut — die String-Heuristik in gate_8_slice_gate
        unterscheidet jetzt String-Inhalt von echten Imports.
        """
        diff = self._diff_block(
            "tests/test_event_mapping_complete.py",
            [
                "from samuel.slices.audit_trail.owasp import OWASP_RISK_MAP",
                "from samuel.slices.evaluation.scoring import compute_score",
            ],
        )
        # Combined with a slice file in changed_files (real-world mix):
        result = gate_8_slice_gate(
            _ctx(
                changed_files=[
                    "samuel/slices/ac_verification/handler.py",
                    "tests/test_event_mapping_complete.py",
                ],
                diff=diff,
            )
        )
        assert result.passed is True

    def test_gate_8_real_cross_slice_violation_caught(self):
        """Echter Verstoss: Slice A importiert aus Slice B in produktiver Datei."""
        diff = self._diff_block(
            "samuel/slices/dashboard/data.py",
            ["from samuel.slices.healing.handler import HealingHandler"],
        )
        result = gate_8_slice_gate(
            _ctx(
                changed_files=["samuel/slices/dashboard/data.py"],
                diff=diff,
            )
        )
        assert result.passed is False
        assert "dashboard" in result.reason
        assert "healing" in result.reason

    def test_gate_8_same_slice_import_allowed(self):
        """X imports from X — kein Verstoss."""
        diff = self._diff_block(
            "samuel/slices/dashboard/data.py",
            ["from samuel.slices.dashboard.handler import DashboardHandler"],
        )
        result = gate_8_slice_gate(
            _ctx(
                changed_files=["samuel/slices/dashboard/data.py"],
                diff=diff,
            )
        )
        assert result.passed is True

    def test_gate_8_adapter_cross_slice_allowed(self):
        """Adapter unter samuel/adapters/ duerfen aus Slices importieren."""
        diff = self._diff_block(
            "samuel/adapters/api/rest.py",
            ["from samuel.slices.dashboard.data import get_status"],
        )
        result = gate_8_slice_gate(
            _ctx(
                changed_files=["samuel/adapters/api/rest.py"],
                diff=diff,
            )
        )
        assert result.passed is True

    def test_gate_8_only_added_lines_count(self):
        """Removed-Zeilen mit Slice-Imports zaehlen NICHT als Verstoss."""
        # Diff zeigt einen entfernten cross-slice-Import in einer Slice-Datei.
        path = "samuel/slices/ac_verification/handler.py"
        diff = (
            f"diff --git a/{path} b/{path}\n"
            f"--- a/{path}\n"
            f"+++ b/{path}\n"
            f"@@\n"
            f"-from samuel.slices.audit_trail.owasp import OWASP_RISK_MAP\n"
            f"+# removed\n"
        )
        result = gate_8_slice_gate(
            _ctx(
                changed_files=[path],
                diff=diff,
            )
        )
        assert result.passed is True

    def test_gate_8_string_fixture_in_slice_test_not_flagged(self):
        """#250: String-Literal-Inhalt in Slice-Test-Datei wird NICHT als
        Cross-Slice-Import gewertet. Vorher (#246) musste man das via
        string-concat-Pflaster umgehen."""
        path = "samuel/slices/pr_gates/tests/test_gates.py"
        diff = self._diff_block(
            path,
            [
                # Diese Zeilen sind STRING-Inhalt in einem Test-Fixture, kein Code.
                '                "from samuel.slices.evaluation.scoring import compute_score",',
                '                "from samuel.slices.healing.handler import HealingHandler",',
            ],
        )
        result = gate_8_slice_gate(
            _ctx(
                changed_files=[path],
                diff=diff,
            )
        )
        assert result.passed is True, (
            f"String-Literal sollte nicht als Import gewertet werden: {result.reason}"
        )

    def test_gate_8_comment_with_import_not_flagged(self):
        """#250: ``# from samuel.slices.X import Y`` ist Kommentar, kein Code."""
        path = "samuel/slices/ac_verification/handler.py"
        diff = self._diff_block(
            path,
            [
                "# from samuel.slices.audit_trail.owasp import OWASP_RISK_MAP",
                "    # indented comment about samuel.slices.healing.handler",
            ],
        )
        result = gate_8_slice_gate(
            _ctx(
                changed_files=[path],
                diff=diff,
            )
        )
        assert result.passed is True

    def test_gate_8_real_import_still_caught_after_string_heuristic(self):
        """#250: Regression-Test — die String-Heuristik darf echte Verstösse
        NICHT durchwinken. Echter Import am Zeilenanfang muss weiter rot sein."""
        path = "samuel/slices/dashboard/data.py"
        diff = self._diff_block(
            path,
            ["from samuel.slices.healing.handler import HealingHandler"],
        )
        result = gate_8_slice_gate(
            _ctx(
                changed_files=[path],
                diff=diff,
            )
        )
        assert result.passed is False
        assert "dashboard" in result.reason
        assert "healing" in result.reason

    def test_gate_8_indented_real_import_caught(self):
        """#250: auch eingerückter import (z.B. lokaler Import in Funktion)
        muss als Verstoss erkannt werden."""
        path = "samuel/slices/dashboard/data.py"
        diff = self._diff_block(
            path,
            ["    from samuel.slices.healing.handler import HealingHandler"],
        )
        result = gate_8_slice_gate(
            _ctx(
                changed_files=[path],
                diff=diff,
            )
        )
        assert result.passed is False, f"Indented real import should be caught: {result.reason}"


class TestGate9PythonSyntax:
    def test_non_python_candidate_is_explicitly_not_applicable(self):
        result = gate_9_python_syntax(_ctx(changed_files=["README.md"]))

        assert result.passed is True
        assert result.status == "not_applicable"

    def test_candidate_bound_valid_python_file_passes(self):
        result = gate_9_python_syntax(
            _ctx(
                changed_files=["valid.py"],
                subject=_subject(),
                read_candidate_file=lambda path: "answer = 42\n",
            )
        )

        assert result.passed is True
        assert result.status == "passed"
        assert result.tool and result.tool["name"] == "cpython.ast"

    def test_candidate_bound_invalid_python_file_fails(self):
        result = gate_9_python_syntax(
            _ctx(
                changed_files=["invalid.py"],
                subject=_subject(),
                read_candidate_file=lambda path: "def broken(:\n",
            )
        )

        assert result.passed is False
        assert result.status == "failed"
        assert "Syntaxprüfung fehlgeschlagen" in result.reason

    def test_unexpected_missing_python_file_fails(self):
        result = gate_9_python_syntax(
            _ctx(
                changed_files=["missing.py"],
                subject=_subject(),
                read_candidate_file=lambda path: None,
            )
        )

        assert result.passed is False
        assert "unexpected_missing_file" in result.reason

    def test_deleted_python_file_is_not_applicable(self):
        result = gate_9_python_syntax(
            _ctx(
                changed_files=["deleted.py"],
                diff="diff --git a/deleted.py b/deleted.py\n--- a/deleted.py\n+++ /dev/null\n",
                subject=_subject(),
                read_candidate_file=lambda path: None,
            )
        )

        assert result.passed is True
        assert result.status == "not_applicable"

    def test_mixed_files_report_checked_and_deleted_separately(self):
        contents = {"valid.py": "answer = 42\n", "deleted.py": None}
        result = gate_9_python_syntax(
            _ctx(
                changed_files=["valid.py", "deleted.py", "README.md"],
                diff="diff --git a/deleted.py b/deleted.py\n--- a/deleted.py\n+++ /dev/null\n",
                subject=_subject(),
                read_candidate_file=contents.get,
            )
        )

        assert result.passed is True
        assert result.status == "passed"
        assert "1 Candidate-Python-Datei" in result.reason
        assert "1 Löschung" in result.reason

    def test_candidate_reader_is_required_for_python(self):
        result = gate_9_python_syntax(
            _ctx(changed_files=["valid.py"], subject=_subject(), read_candidate_file=None)
        )

        assert result.passed is False
        assert result.status == "failed"


class TestGate11ACVerification:
    def test_pass_with_acs(self):
        subject, evidence = _acceptance_evidence()
        assert (
            gate_11_ac_verification(_ctx(subject=subject, acceptance_evidence=evidence)).passed
            is True
        )

    def test_fail_no_plan(self):
        assert gate_11_ac_verification(_ctx(plan_comment=None)).passed is False

    def test_fail_no_acs_in_plan(self):
        assert gate_11_ac_verification(_ctx(plan_comment="## Plan\nJust text")).passed is False

    def test_checked_checkbox_without_evidence_still_fails(self):
        assert gate_11_ac_verification(_ctx(plan_comment="- [x] [TEST] test_one")).passed is False

    def test_stale_head_evidence_fails_closed(self):
        subject, evidence = _acceptance_evidence()
        evidence["evaluation_subject"]["head_sha"] = "e" * 40
        result = gate_11_ac_verification(_ctx(subject=subject, acceptance_evidence=evidence))
        assert result.passed is False
        assert result.status == "missing_evidence"

    def test_manual_pending_and_verifier_error_fail(self):
        plan = "- [ ] [MANUAL] dashboard\n- [ ] [TEST] test_one"
        subject, pending = _acceptance_evidence(
            plan=plan,
            statuses=["manual_pending", "passed"],
        )
        assert (
            gate_11_ac_verification(_ctx(subject=subject, acceptance_evidence=pending)).status
            == "manual_pending"
        )
        subject, error = _acceptance_evidence(plan=plan, statuses=["passed", "error"])
        assert (
            gate_11_ac_verification(_ctx(subject=subject, acceptance_evidence=error)).status
            == "error"
        )

    def test_forged_manual_pass_without_human_receipt_fails(self):
        subject, evidence = _acceptance_evidence(
            plan="- [x] [MANUAL] dashboard",
            statuses=["passed"],
        )
        evidence["results"][0]["evidence"] = None

        result = gate_11_ac_verification(_ctx(subject=subject, acceptance_evidence=evidence))

        assert result.passed is False
        assert result.status == "missing_evidence"


class TestGate12ReadyToClose:
    def test_fail_unchecked_acs(self):
        subject, evidence = _acceptance_evidence(statuses=["manual_pending"])
        assert (
            gate_12_ready_to_close(_ctx(subject=subject, acceptance_evidence=evidence)).passed
            is False
        )

    def test_pass_all_checked(self):
        subject, evidence = _acceptance_evidence()
        assert (
            gate_12_ready_to_close(_ctx(subject=subject, acceptance_evidence=evidence)).passed
            is True
        )

    def test_missing_plan_is_not_ready(self):
        assert gate_12_ready_to_close(_ctx(plan_comment=None)).passed is False

    def test_no_evidence_is_not_ready(self):
        assert gate_12_ready_to_close(_ctx(plan_comment="Just a plan")).passed is False


class TestGate13aBranchFreshness:
    def test_missing_subject_fails_closed(self):
        assert gate_13a_branch_freshness(_ctx()).passed is False

    def test_uses_exact_subject_commits(self):
        subject = EvaluationSubject(
            repository="https://scm.example/owner/repo",
            base_sha="a" * 40,
            head_sha="b" * 40,
            contract_hash="sha256:" + "c" * 64,
            policy_version="v1",
            policy_digest="sha256:" + "d" * 64,
        )
        with patch("subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "0"
            result = gate_13a_branch_freshness(_ctx(subject=subject))

        assert result.passed is True
        assert run.call_args.args[0][-1] == f"{subject.head_sha}..{subject.base_sha}"

    def test_blocks_when_subject_head_is_more_than_fifty_commits_behind(self):
        subject = EvaluationSubject(
            repository="https://scm.example/owner/repo",
            base_sha="a" * 40,
            head_sha="b" * 40,
            contract_hash="sha256:" + "c" * 64,
            policy_version="v1",
            policy_digest="sha256:" + "d" * 64,
        )
        with patch("subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "51"
            result = gate_13a_branch_freshness(_ctx(subject=subject))

        assert result.passed is False
        assert "51 Commits" in result.reason


class TestGate13bDestructiveDiff:
    def test_pass_normal_diff(self):
        assert gate_13b_destructive_diff(_ctx()).passed is True

    def test_pass_no_diff(self):
        assert gate_13b_destructive_diff(_ctx(diff="")).passed is True

    def test_fail_massive_deletion(self):
        diff = "\n".join([f"-deleted line {i}" for i in range(200)])
        diff += "\n+one added line"
        assert gate_13b_destructive_diff(_ctx(diff=diff)).passed is False


class TestGateRegistry:
    def test_all_13_active_gates_registered(self):
        expected = {1, 2, 3, 5, 6, 7, "7b", 8, 9, 11, 12, "13a", "13b"}
        assert set(GATE_REGISTRY.keys()) == expected

    def test_registry_and_shared_display_names_have_same_gate_ids(self):
        assert set(GATE_REGISTRY) == set(GATE_NAMES)
        assert all(name.strip() for name in GATE_NAMES.values())

    def test_all_gates_return_gate_result(self):
        ctx = _ctx()
        for gate_id, fn in GATE_REGISTRY.items():
            result = fn(ctx)
            assert isinstance(result, GateResult), f"Gate {gate_id} returned {type(result)}"
