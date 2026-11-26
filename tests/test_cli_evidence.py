from __future__ import annotations

import json
import shutil
from argparse import Namespace
from pathlib import Path

from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.cli import _cmd_evidence
from samuel.core.external_evidence import (
    SCMCheckJob,
    SCMCheckObservation,
    SCMCommitStatus,
)


def _observation() -> SCMCheckObservation:
    return SCMCheckObservation(
        provider="gitea",
        provider_instance="https://gitea.example",
        repository="owner/repo",
        run_id=704,
        requested_attempt=1,
        reported_attempt=1,
        event="pull_request",
        head_sha="b" * 40,
        pull_request_number=7,
        pull_request_base_sha="a" * 40,
        pull_request_head_sha="b" * 40,
        head_branch="feature/evidence",
        status="completed",
        conclusion="success",
        started_at="2026-09-18T09:59:00Z",
        completed_at="2026-09-18T10:00:00Z",
        workflow_path=".gitea/workflows/ci.yml",
        workflow_ref="refs/pull/7/head",
        workflow_blob_sha="e" * 40,
        run_url="https://gitea.example/owner/repo/actions/runs/704",
        jobs=(
            SCMCheckJob(
                job_id=9,
                name="tests",
                status="completed",
                conclusion="success",
                runner_id=2,
                runner_name="runner",
                runner_labels=("linux",),
                started_at="2026-09-18T09:59:00Z",
                completed_at="2026-09-18T10:00:00Z",
                url=None,
            ),
        ),
        commit_statuses=(
            SCMCommitStatus(
                status_id=11,
                context="CI / tests (pull_request)",
                state="success",
                target_url="/owner/repo/actions/runs/704/jobs/9",
                creator="ci-bot",
                created_at="2026-09-18T10:00:00Z",
                updated_at="2026-09-18T10:00:00Z",
            ),
        ),
    )


def test_cli_persists_immutable_advisory_and_marks_retrieval_replay(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "agent.json").write_text(json.dumps({"data_dir": "runtime"}))
    subject = tmp_path / "subject.json"
    subject.write_text(
        json.dumps(
            {
                "repository": "https://gitea.example/owner/repo",
                "base_sha": "a" * 40,
                "head_sha": "b" * 40,
                "contract_hash": "sha256:" + "c" * 64,
                "policy_version": "gates.v1",
                "policy_digest": "sha256:" + "d" * 64,
            }
        )
    )
    monkeypatch.setenv("SCM_PROVIDER", "gitea")
    monkeypatch.setenv("SCM_URL", "https://gitea.example")
    monkeypatch.setenv("SCM_TOKEN", "secret")
    monkeypatch.setenv("SCM_REPO", "owner/repo")
    monkeypatch.setenv("SCM_REQUIRED_STATUS_CONTEXT", "CI / tests (pull_request)")
    monkeypatch.setattr(
        "samuel.adapters.gitea.adapter.GiteaAdapter.read_check_evidence",
        lambda _self, _reference: _observation(),
    )
    args = Namespace(
        config=str(config),
        action="assess",
        run_id=704,
        attempt=1,
        subject=str(subject),
        workflow=".gitea/workflows/ci.yml",
        event="pull_request",
        max_age_seconds=10**9,
        issue=520,
        json=True,
    )

    assert _cmd_evidence(args) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["assessment"]["role"] == "advisory"
    assert first["assessment"]["required_effect"] is False
    assert first["storage"] == {"inserted": True, "replayed": False}
    original_key = first["assessment"]["assessment_key"]
    assert _cmd_evidence(args) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["storage"] == {"inserted": False, "replayed": True}

    records = SQLiteStateStore(tmp_path / "runtime").observations.list_observations(520)
    assert len(records) == 1
    assert records[0].evidence_origin == "external_scm_advisory"
    assert records[0].payload["authority"] == "none"
    assert records[0].payload["in_toto_statement"]["predicate"]["requiredEffect"] is False

    restored_dir = tmp_path / "restored"
    shutil.copytree(tmp_path / "runtime", restored_dir)
    restored = SQLiteStateStore(restored_dir).observations.get_observation(original_key)
    assert restored is not None
    assert restored.payload["role"] == "advisory"
    assert restored.payload["authority"] == "none"
    assert restored.payload["required_effect"] is False

    monkeypatch.setenv("SCM_REQUIRED_STATUS_CONTEXT", "CI / changed (pull_request)")
    assert _cmd_evidence(args) == 1
    changed_profile = json.loads(capsys.readouterr().out)
    assert changed_profile["assessment"]["verdict"] == "advisory_rejected"
    records = SQLiteStateStore(tmp_path / "runtime").observations.list_observations(520)
    assert len(records) == 2
    historical = next(record for record in records if record.observation_key == original_key)
    assert historical.payload["authority"] == "none"
    assert historical.payload["required_effect"] is False


def test_cli_rejects_oversized_subject_before_provider_call(tmp_path: Path, capsys) -> None:
    config = tmp_path / "config"
    config.mkdir()
    subject = tmp_path / "subject.json"
    subject.write_text("{" + "x" * 65536)
    args = Namespace(
        config=str(config),
        action="assess",
        run_id=704,
        attempt=1,
        subject=str(subject),
        workflow=None,
        event=None,
        max_age_seconds=60,
        issue=0,
        json=True,
    )

    assert _cmd_evidence(args) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["error"]["code"] == "external_evidence_invalid"
    assert "65536" in output["error"]["detail"]
