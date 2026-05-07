from __future__ import annotations

from pathlib import Path
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import EvaluateCommand
from samuel.core.events import Event
from samuel.core.ports import IVersionControl
from samuel.core.types import Comment, Issue
from samuel.slices.evaluation.handler import EvaluationHandler


class MockSCM(IVersionControl):
    def __init__(self) -> None:
        self.posted: list[tuple[int, str]] = []

    def get_issue(self, number: int) -> Issue:
        return Issue(number=number, title="Test", body="body", state="open")

    def get_comments(self, number: int) -> list[Comment]:
        return []

    def post_comment(self, number: int, body: str) -> Comment:
        self.posted.append((number, body))
        return Comment(id=1, body=body, user="bot")

    def create_pr(self, head: str, base: str, title: str, body: str) -> Any:
        raise NotImplementedError

    def swap_label(self, number: int, remove: str, add: str) -> None:
        pass

    def list_issues(self, labels: list[str]) -> list[Issue]:
        return []

    def close_issue(self, number: int) -> None:
        pass

    def merge_pr(self, pr_id: int) -> bool:
        return True

    def issue_url(self, number: int) -> str:
        return ""

    def pr_url(self, pr_id: int) -> str:
        return ""

    def branch_url(self, branch: str) -> str:
        return ""

    def list_labels(self) -> list[dict]:
        return []

    def create_label(self, name: str, color: str, description: str = "") -> dict:
        return {"id": 0, "name": name, "color": color, "description": description}


def _collect_events(bus: Bus) -> list[Event]:
    events: list[Event] = []
    bus.subscribe("*", lambda e: events.append(e))
    return events


def _eval_config_dir(tmp_path: Path) -> Path:
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "eval.json").write_text(
        '{"weights": {"test_pass_rate": 0.3, "syntax_valid": 0.2, '
        '"hallucination_free": 0.3, "scope_compliant": 0.2}, '
        '"baseline": 0.8, "fail_fast_on": ["syntax_valid"]}'
    )
    return cfg


ALL_PASS = {
    "test_pass_rate": 1.0,
    "syntax_valid": 1.0,
    "hallucination_free": 1.0,
    "scope_compliant": 1.0,
}


class TestEvaluationHandler:
    def test_eval_pass(self, tmp_path: Path):
        cfg = _eval_config_dir(tmp_path)
        data = tmp_path / "data"
        bus = Bus()
        events = _collect_events(bus)
        scm = MockSCM()

        handler = EvaluationHandler(bus, scm=scm, config_dir=str(cfg), data_dir=str(data))
        result = handler.handle(EvaluateCommand(
            issue_number=42,
            payload={"criteria_scores": ALL_PASS},
        ))

        assert result["passed"] is True
        assert result["score"] == 1.0
        assert any(e.name == "EvalCompleted" for e in events)
        assert not any(e.name == "EvalFailed" for e in events)
        assert len(scm.posted) == 1
        assert "PASS" in scm.posted[0][1]

    def test_eval_fail_low_score(self, tmp_path: Path):
        cfg = _eval_config_dir(tmp_path)
        data = tmp_path / "data"
        bus = Bus()
        events = _collect_events(bus)

        handler = EvaluationHandler(bus, config_dir=str(cfg), data_dir=str(data))
        result = handler.handle(EvaluateCommand(
            issue_number=42,
            payload={"criteria_scores": {
                "test_pass_rate": 0.3,
                "syntax_valid": 0.9,
                "hallucination_free": 0.3,
                "scope_compliant": 0.3,
            }},
        ))

        assert result["passed"] is False
        assert any(e.name == "EvalFailed" for e in events)

    def test_fail_fast_blocks_despite_high_total(self, tmp_path: Path):
        cfg = _eval_config_dir(tmp_path)
        data = tmp_path / "data"
        bus = Bus()
        events = _collect_events(bus)

        handler = EvaluationHandler(bus, config_dir=str(cfg), data_dir=str(data))
        result = handler.handle(EvaluateCommand(
            issue_number=42,
            payload={"criteria_scores": {
                "test_pass_rate": 1.0,
                "syntax_valid": 0.5,
                "hallucination_free": 1.0,
                "scope_compliant": 1.0,
            }},
        ))

        assert result["passed"] is False
        assert "syntax_valid" in result["fail_fast_blocked"]
        assert result["score"] > 0.8
        fail_event = next(e for e in events if e.name == "EvalFailed")
        assert "syntax_valid" in fail_event.payload["fail_fast_blocked"]

    def test_no_criteria_scores_blocks_workflow(self, tmp_path: Path):
        """Regression #228 (reverses #181): default_passed=True kaschierte einen
        toten Eval-Mechanismus — jeder Self-Mode-Run lief 'passed' obwohl nichts
        ausgewertet wurde. Jetzt: EvalFailed(reason='no_scores_provided'), damit
        das Symptom sichtbar wird, bis #232 (Score-Producer aus AC-Verifikation)
        echte criteria_scores liefert."""
        cfg = _eval_config_dir(tmp_path)
        data = tmp_path / "data"
        bus = Bus()
        events = _collect_events(bus)

        handler = EvaluationHandler(bus, config_dir=str(cfg), data_dir=str(data))
        result = handler.handle(EvaluateCommand(issue_number=42))

        assert result is not None
        assert result["passed"] is False
        assert result["score"] == 0.0
        assert result["reason"] == "no_scores_provided"
        assert any(e.name == "EvalFailed" for e in events)
        assert not any(e.name == "EvalCompleted" for e in events)
        failed = next(e for e in events if e.name == "EvalFailed")
        assert failed.payload["reason"] == "no_scores_provided"

    def test_score_history_written(self, tmp_path: Path):
        cfg = _eval_config_dir(tmp_path)
        data = tmp_path / "data"
        bus = Bus()

        handler = EvaluationHandler(bus, config_dir=str(cfg), data_dir=str(data))
        handler.handle(EvaluateCommand(
            issue_number=42,
            payload={"criteria_scores": ALL_PASS},
        ))

        import json
        history = json.loads((data / "score_history.json").read_text())
        assert len(history) == 1
        assert history[0]["issue"] == 42
        assert history[0]["score"] == 1.0

    def test_correlation_id_flows(self, tmp_path: Path):
        cfg = _eval_config_dir(tmp_path)
        data = tmp_path / "data"
        bus = Bus()
        events = _collect_events(bus)

        handler = EvaluationHandler(bus, config_dir=str(cfg), data_dir=str(data))
        handler.handle(EvaluateCommand(
            issue_number=42,
            payload={"criteria_scores": ALL_PASS},
            correlation_id="eval-corr-1",
        ))

        for e in events:
            assert e.correlation_id == "eval-corr-1"

    def test_no_scm_still_works(self, tmp_path: Path):
        cfg = _eval_config_dir(tmp_path)
        data = tmp_path / "data"
        bus = Bus()
        events = _collect_events(bus)

        handler = EvaluationHandler(bus, scm=None, config_dir=str(cfg), data_dir=str(data))
        result = handler.handle(EvaluateCommand(
            issue_number=42,
            payload={"criteria_scores": ALL_PASS},
        ))

        assert result["passed"] is True
        assert any(e.name == "EvalCompleted" for e in events)

    def test_invalid_config_uses_defaults(self, tmp_path: Path):
        cfg = tmp_path / "config"
        cfg.mkdir()
        data = tmp_path / "data"
        bus = Bus()

        handler = EvaluationHandler(bus, config_dir=str(cfg), data_dir=str(data))
        result = handler.handle(EvaluateCommand(
            issue_number=42,
            payload={"criteria_scores": ALL_PASS},
        ))

        assert result["passed"] is True


class TestEvalPayloadCarryThrough:
    """Regression #187: branch/base/patches_applied/rounds aus EvaluateCommand
    müssen in EvalCompleted/EvalFailed durchgereicht werden, sonst bricht
    CreatePR an Gate 1 ('Branch ist main/master') und Gate 7."""

    def test_branch_carried_to_failed_no_scores(self, tmp_path: Path):
        """Auch im Block-Pfad (no_scores_provided) muss branch/base mitkommen,
        damit ein nachgelagerter Healing-/Reroute-Step weiss, was reparieren."""
        cfg = _eval_config_dir(tmp_path)
        bus = Bus()
        events = _collect_events(bus)
        handler = EvaluationHandler(bus, config_dir=str(cfg), data_dir=str(tmp_path / "d"))
        handler.handle(EvaluateCommand(
            issue_number=42,
            payload={"branch": "samuel/issue-42", "base": "main"},
        ))
        failed = next(e for e in events if e.name == "EvalFailed")
        assert failed.payload["branch"] == "samuel/issue-42"
        assert failed.payload["base"] == "main"
        assert failed.payload["reason"] == "no_scores_provided"

    def test_branch_carried_to_completed_real_pass(self, tmp_path: Path):
        cfg = _eval_config_dir(tmp_path)
        bus = Bus()
        events = _collect_events(bus)
        handler = EvaluationHandler(bus, config_dir=str(cfg), data_dir=str(tmp_path / "d"))
        handler.handle(EvaluateCommand(
            issue_number=42,
            payload={"branch": "samuel/issue-42", "criteria_scores": ALL_PASS},
        ))
        completed = next(e for e in events if e.name == "EvalCompleted")
        assert completed.payload["branch"] == "samuel/issue-42"

    def test_branch_carried_to_failed(self, tmp_path: Path):
        cfg = _eval_config_dir(tmp_path)
        bus = Bus()
        events = _collect_events(bus)
        handler = EvaluationHandler(bus, config_dir=str(cfg), data_dir=str(tmp_path / "d"))
        handler.handle(EvaluateCommand(
            issue_number=42,
            payload={
                "branch": "samuel/issue-42",
                "criteria_scores": {
                    "syntax_valid": 0.0, "test_pass_rate": 0.0,
                    "hallucination_free": 0.0, "scope_compliant": 0.0,
                },
            },
        ))
        failed = next(e for e in events if e.name == "EvalFailed")
        assert failed.payload["branch"] == "samuel/issue-42"

    def test_unknown_payload_keys_not_carried(self, tmp_path: Path):
        """Defensive: nur explizit gewollte Keys übernehmen, kein Dump.
        Geprüft auf dem Failed-Pfad, da no-scores jetzt blockt."""
        cfg = _eval_config_dir(tmp_path)
        bus = Bus()
        events = _collect_events(bus)
        handler = EvaluationHandler(bus, config_dir=str(cfg), data_dir=str(tmp_path / "d"))
        handler.handle(EvaluateCommand(
            issue_number=42,
            payload={"branch": "x", "user_secret": "hush"},
        ))
        failed = next(e for e in events if e.name == "EvalFailed")
        assert "branch" in failed.payload
        assert "user_secret" not in failed.payload


class TestAntiRegression:
    """Issue #213: persistierte Per-Issue-Baseline und Anti-Regression-Check."""

    def test_first_pass_promotes_baseline_to_score(self, tmp_path: Path):
        cfg = _eval_config_dir(tmp_path)
        data = tmp_path / "d"
        bus = Bus()
        events = _collect_events(bus)
        handler = EvaluationHandler(bus, config_dir=str(cfg), data_dir=str(data))
        handler.handle(EvaluateCommand(
            issue_number=42, payload={"criteria_scores": ALL_PASS},
        ))
        completed = next(e for e in events if e.name == "EvalCompleted")
        assert completed.payload["score"] == 1.0
        assert completed.payload["baseline"] == 1.0  # promoted from config 0.8 → score 1.0

        import json
        baselines = json.loads((data / "eval_baselines.json").read_text())
        assert baselines == {"42": 1.0}

    def test_second_pass_with_lower_score_fails_due_to_regression(self, tmp_path: Path):
        cfg = _eval_config_dir(tmp_path)
        data = tmp_path / "d"
        bus = Bus()
        events = _collect_events(bus)
        handler = EvaluationHandler(bus, config_dir=str(cfg), data_dir=str(data))

        # First eval: high score → baseline becomes 1.0
        handler.handle(EvaluateCommand(
            issue_number=42, payload={"criteria_scores": ALL_PASS},
        ))
        # Second eval: still passes config-baseline (0.8) but regresses
        # against the persisted 1.0
        result = handler.handle(EvaluateCommand(
            issue_number=42,
            payload={"criteria_scores": {
                "test_pass_rate": 0.9, "syntax_valid": 0.9,
                "hallucination_free": 0.9, "scope_compliant": 0.9,
            }},
        ))
        assert result["passed"] is False
        assert result["regression"] is True
        failed = [e for e in events if e.name == "EvalFailed"]
        assert len(failed) == 1
        assert failed[0].payload.get("regression") is True
        assert "regression" in failed[0].payload["reason"]
        # Baseline must NOT regress
        import json
        baselines = json.loads((data / "eval_baselines.json").read_text())
        assert baselines == {"42": 1.0}

    def test_second_pass_with_equal_score_still_passes(self, tmp_path: Path):
        cfg = _eval_config_dir(tmp_path)
        data = tmp_path / "d"
        bus = Bus()
        handler = EvaluationHandler(bus, config_dir=str(cfg), data_dir=str(data))

        handler.handle(EvaluateCommand(
            issue_number=42, payload={"criteria_scores": ALL_PASS},
        ))
        result = handler.handle(EvaluateCommand(
            issue_number=42, payload={"criteria_scores": ALL_PASS},
        ))
        assert result["passed"] is True
        assert result["regression"] is False
        assert result["score"] == 1.0

    def test_baselines_isolated_per_issue(self, tmp_path: Path):
        cfg = _eval_config_dir(tmp_path)
        data = tmp_path / "d"
        bus = Bus()
        handler = EvaluationHandler(bus, config_dir=str(cfg), data_dir=str(data))

        handler.handle(EvaluateCommand(
            issue_number=42, payload={"criteria_scores": ALL_PASS},
        ))
        # Issue #99 has no history → uses config baseline 0.8 only
        result = handler.handle(EvaluateCommand(
            issue_number=99,
            payload={"criteria_scores": {
                "test_pass_rate": 0.85, "syntax_valid": 0.85,
                "hallucination_free": 0.85, "scope_compliant": 0.85,
            }},
        ))
        assert result["passed"] is True
        assert result["regression"] is False

        import json
        baselines = json.loads((data / "eval_baselines.json").read_text())
        assert baselines["42"] == 1.0
        assert baselines["99"] == 0.85

    def test_no_criteria_uses_persisted_baseline_in_failed_event(self, tmp_path: Path):
        """Auch der Block-Pfad muss die persistierte Per-Issue-Baseline kennen
        und durchreichen — sonst startet ein nachfolgender Run (mit echten
        criteria_scores nach #232) wieder bei der niedrigen Config-Baseline."""
        cfg = _eval_config_dir(tmp_path)
        data = tmp_path / "d"
        bus = Bus()
        events = _collect_events(bus)
        handler = EvaluationHandler(bus, config_dir=str(cfg), data_dir=str(data))

        # First a real pass → baseline persisted to 1.0
        handler.handle(EvaluateCommand(
            issue_number=42, payload={"criteria_scores": ALL_PASS},
        ))
        events.clear()
        # No-criteria call now blocks but must report the persisted baseline.
        result = handler.handle(EvaluateCommand(issue_number=42))
        assert result["passed"] is False
        assert result["baseline"] == 1.0
        failed = next(e for e in events if e.name == "EvalFailed")
        assert failed.payload["baseline"] == 1.0

    def test_min_score_field_removed_from_eval_schema(self):
        """Sanity: min_score Dead-Code wirklich raus."""
        from samuel.core.config import EvalSchema
        es = EvalSchema()
        assert not hasattr(es, "min_score")
