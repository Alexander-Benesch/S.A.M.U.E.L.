from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.core.state import ObservationRecord

ROOT = Path(__file__).resolve().parents[1]


def _console_script() -> Path:
    script = Path(sys.prefix) / "bin" / "samuel"
    assert script.is_file()
    return script


def _config(tmp_path: Path) -> Path:
    config = tmp_path / "config"
    config.mkdir()
    (config / "agent.json").write_text(
        json.dumps(
            {
                "data_dir": "runtime",
                "workspace": {
                    "work_dir": "workspaces",
                    "minimum_free_mebibytes": 0,
                },
            }
        ),
        encoding="utf-8",
    )
    for name in ("privacy.json", "audit.json", "eval.json"):
        shutil.copyfile(ROOT / "config" / name, config / name)
    return config


def _run(config: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(_console_script()), "--config", str(config), "retention", *arguments, "--json"],
        check=False,
        capture_output=True,
        text=True,
    )


def test_retention_cli_dry_run_approval_and_managed_backup(tmp_path: Path) -> None:
    config = _config(tmp_path)
    workspace_dir = tmp_path / "workspaces"
    assert not workspace_dir.exists()

    initial = _run(config, "dry-run")
    assert initial.returncode == 0
    assert not workspace_dir.exists()
    initial_payload = json.loads(initial.stdout)["retention"]
    assert initial_payload["delete_capability_present"] is True
    assert initial_payload["active_enforcement_categories"] == []
    observations = next(
        row for row in initial_payload["categories"] if row["category"] == "observations"
    )
    assert observations["effective_mode"] == "report_only_pending_review"

    approval = _run(
        config,
        "approve",
        "--category",
        "observations",
        "--reason",
        "operator reviewed category policy",
    )
    assert approval.returncode == 0
    assert json.loads(approval.stdout)["retention"]["created"] is True

    approved = json.loads(_run(config, "dry-run").stdout)["retention"]
    observations = next(row for row in approved["categories"] if row["category"] == "observations")
    assert observations["effective_mode"] == "report_only"

    backup = _run(config, "backup")
    assert backup.returncode == 0
    backup_payload = json.loads(backup.stdout)["retention"]
    assert Path(backup_payload["path"]).is_file()
    assert Path(backup_payload["path"]).parent == tmp_path / "data" / "backups"


def test_retention_cli_replay_has_no_workflow_or_quality_side_effects(tmp_path: Path) -> None:
    config = _config(tmp_path)

    replay = _run(config, "replay-scores")

    assert replay.returncode == 0
    payload = json.loads(replay.stdout)["retention"]
    assert payload["observations"] == 0
    assert payload["workflow_events_published"] == 0
    assert payload["quality_metrics_updated"] == 0


def test_retention_cli_replays_multiple_versioned_eval_configs(tmp_path: Path) -> None:
    config = _config(tmp_path)
    store = SQLiteStateStore(tmp_path / "runtime")
    store.observations.put_observation(
        ObservationRecord(
            observation_key="sha256:" + "a" * 64,
            subject_key="sha256:" + "b" * 64,
            evidence_digest="sha256:" + "c" * 64,
            observation_schema="bound.v2",
            issue_number=667,
            payload={
                "evaluation_subject": {"repository": "example/repo"},
                "gate_results": [],
                "acceptance_evidence": {
                    "results": [
                        {"criterion_id": "AC-1", "tag": "TEST", "status": "passed"},
                        {"criterion_id": "AC-2", "tag": "DIFF", "status": "failed"},
                    ]
                },
            },
            observed_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
        )
    )
    policy_dirs = []
    for name, formula, weights in (
        (
            "formula-a",
            "bound-evidence.a",
            {"test_pass_rate": 0.9, "hallucination_free": 0.1},
        ),
        (
            "formula-b",
            "bound-evidence.b",
            {"test_pass_rate": 0.1, "hallucination_free": 0.9},
        ),
    ):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "eval.json").write_text(
            json.dumps(
                {
                    "policy_version": "policy.replay.v1",
                    "formula_version": formula,
                    "weights": weights,
                }
            ),
            encoding="utf-8",
        )
        policy_dirs.append(directory)

    replay = _run(
        config,
        "replay-scores",
        "--issue",
        "667",
        "--eval-config-dir",
        str(policy_dirs[0]),
        "--eval-config-dir",
        str(policy_dirs[1]),
    )

    assert replay.returncode == 0
    payload = json.loads(replay.stdout)["retention"]
    assert payload["policy_formula_pairs"] == 2
    assert payload["created"] == 2
    assert {row.score for row in store.observations.list_derivations(667)} == {0.1, 0.9}


def test_retention_cli_requires_explicit_review_plan_and_stop_release(tmp_path: Path) -> None:
    config = _config(tmp_path)
    privacy_path = config / "privacy.json"
    privacy = json.loads(privacy_path.read_text(encoding="utf-8"))
    privacy["retention"]["categories"]["score_derivations"]["mode"] = "enforce"
    privacy_path.write_text(json.dumps(privacy), encoding="utf-8")
    store = SQLiteStateStore(tmp_path / "runtime")
    observation_key = "sha256:" + "a" * 64
    score_key = "sha256:" + "b" * 64
    store.observations.put_observation(
        ObservationRecord(
            observation_key=observation_key,
            subject_key="sha256:" + "c" * 64,
            evidence_digest="sha256:" + "d" * 64,
            observation_schema="bound.v2",
            issue_number=673,
            payload={},
            observed_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
    )
    from samuel.core.state import ScoreDerivationRecord

    store.observations.put_derivation(
        ScoreDerivationRecord(
            score_key=score_key,
            observation_key=observation_key,
            scoring_policy_version="canary.v1",
            scoring_policy_digest="sha256:" + "e" * 64,
            formula_version="canary.v1",
            score=1.0,
            payload={},
            issue_number=673,
            derived_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
    )
    report = json.loads(_run(config, "dry-run").stdout)["retention"]
    category = next(row for row in report["categories"] if row["category"] == "score_derivations")
    common = (
        "--category",
        "score_derivations",
        "--plan-digest",
        category["plan_digest"],
        "--cutoff-utc",
        category["cutoff_utc"],
    )

    blocked = _run(config, "activate", *common, "--reason", "not reviewed")
    assert blocked.returncode == 1
    assert json.loads(blocked.stdout)["error"]["code"] == "retention_category_not_reviewed"
    assert (
        _run(
            config,
            "approve",
            "--category",
            "score_derivations",
            "--reason",
            "operator reviewed policy",
        ).returncode
        == 0
    )
    assert _run(config, "activate", *common, "--reason", "activate exact plan").returncode == 0
    stopped = _run(config, "execute", *common, "--reason", "still stopped")
    assert stopped.returncode == 1
    assert json.loads(stopped.stdout)["error"]["code"] == "state_retention_emergency_stop"
    assert _run(config, "unpause", "--reason", "execute canary").returncode == 0

    executed = _run(config, "execute", *common, "--reason", "execute exact plan")
    repeated = _run(config, "execute", *common, "--reason", "execute exact plan")

    assert executed.returncode == repeated.returncode == 0
    assert json.loads(executed.stdout)["retention"] == json.loads(repeated.stdout)["retention"]
    assert SQLiteStateStore(tmp_path / "runtime").observations.get_derivation(score_key) is None
