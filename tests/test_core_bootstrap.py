from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from samuel.adapters.gitea.adapter import GiteaAdapter
from samuel.adapters.github.adapter import GitHubAdapter
from samuel.core.bootstrap import (
    _build_git_transport_auth,
    _build_scm_adapter,
    _resolve_project_root,
    bootstrap,
)
from samuel.core.bus import Bus
from samuel.core.config import SCMConfig
from samuel.core.events import AuthorityReconcileRequired
from samuel.core.git import current_branch
from samuel.core.state import HealingClaimRecord


def _write_workflow(
    config_dir: Path,
    *,
    name: str = "standard",
    max_risk: int = 3,
    max_parallel: int = 1,
) -> None:
    workflows = config_dir / "workflows"
    workflows.mkdir(exist_ok=True)
    (workflows / f"{name}.json").write_text(
        json.dumps(
            {
                "name": name,
                "steps": [{"on": "IssueReady", "send": "PlanIssue"}],
                "max_risk": max_risk,
                "max_parallel": max_parallel,
            }
        ),
        encoding="utf-8",
    )


def test_build_scm_adapter_honors_gitea_provider():
    adapter = _build_scm_adapter(
        SCMConfig(provider="gitea", url="https://gitea.test", token="t", repo="o/r")
    )
    assert isinstance(adapter, GiteaAdapter)


def test_build_scm_adapter_propagates_network_timeout():
    adapter = _build_scm_adapter(
        SCMConfig(provider="gitea", url="https://gitea.test", token="t", repo="o/r"),
        request_timeout=7.5,
    )
    assert adapter._api._timeout == 7.5


def test_build_scm_adapter_honors_github_provider():
    adapter = _build_scm_adapter(
        SCMConfig(provider="github", url="https://github.com", token="t", repo="o/r")
    )
    assert isinstance(adapter, GitHubAdapter)
    assert adapter._api._base_url == "https://api.github.com"


def test_build_scm_adapter_rejects_unknown_provider():
    config = SCMConfig(provider="gitlab", url="https://gitlab.test", token="t", repo="o/r")
    with pytest.raises(ValueError, match="Unsupported SCM provider"):
        _build_scm_adapter(config)


def test_build_git_transport_auth_uses_gitea_user(tmp_path: Path):
    config = SCMConfig(
        provider="gitea",
        url="https://gitea.test",
        token="t",
        repo="o/r",
        user="demo-bot",
    )
    adapter = _build_scm_adapter(config)
    transport = _build_git_transport_auth(config, adapter, adapter._api._auth)

    assert transport._username == "demo-bot"
    assert transport._expected_path == "/o/r"


def test_build_git_transport_auth_uses_github_token_username():
    config = SCMConfig(provider="github", url="https://github.com", token="t", repo="o/r")
    adapter = _build_scm_adapter(config)
    transport = _build_git_transport_auth(config, adapter, adapter._api._auth)

    assert transport._username == "x-access-token"
    assert transport._expected_path == "/o/r"


def test_bootstrap_returns_bus():
    with tempfile.TemporaryDirectory() as d:
        cfg = Path(d) / "agent.json"
        cfg.write_text(json.dumps({"log_level": "WARNING"}))
        (Path(d) / "audit.json").write_text('{"sinks": []}')
        _write_workflow(Path(d))
        bus = bootstrap(config_path=d)
        try:
            assert isinstance(bus, Bus)
        finally:
            bus.close()


def test_bootstrap_has_middlewares():
    with tempfile.TemporaryDirectory() as d:
        cfg = Path(d) / "agent.json"
        cfg.write_text(json.dumps({}))
        (Path(d) / "audit.json").write_text('{"sinks": []}')
        _write_workflow(Path(d))
        bus = bootstrap(config_path=d)
        try:
            assert len(bus._middlewares) == 4
            assert {type(middleware).__name__ for middleware in bus._middlewares} == {
                "IdempotencyMiddleware",
                "AuditMiddleware",
                "ErrorMiddleware",
                "MetricsMiddleware",
            }
        finally:
            bus.close()


def test_bootstrap_notifies_when_authority_reconcile_is_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from samuel.adapters.notifications.generic_webhook import GenericWebhookNotifier
    from samuel.adapters.state.sqlite import SQLiteStateStore

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    data_dir = tmp_path / "data"
    (config_dir / "agent.json").write_text(
        json.dumps({"data_dir": str(data_dir), "log_level": "WARNING"}),
        encoding="utf-8",
    )
    (config_dir / "audit.json").write_text('{"sinks": []}', encoding="utf-8")
    (config_dir / "notifications.json").write_text(
        json.dumps(
            {
                "adapters": [
                    {
                        "type": "generic_webhook",
                        "enabled": True,
                        "url": "https://notification.invalid/reconcile",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    _write_workflow(config_dir)

    store = SQLiteStateStore(data_dir)
    store.authority.claim_healing(HealingClaimRecord("obs-reconcile", 629, "run-629"))
    witness = json.loads(store.authority_witness_path.read_text(encoding="utf-8"))
    witness["authority_epoch"] = 0
    store.authority_witness_path.write_text(json.dumps(witness), encoding="utf-8")

    notifications: list[AuthorityReconcileRequired] = []

    def capture(_self: GenericWebhookNotifier, event: object) -> None:
        if isinstance(event, AuthorityReconcileRequired):
            notifications.append(event)

    monkeypatch.setattr(GenericWebhookNotifier, "notify", capture)

    bus = bootstrap(config_path=config_dir)
    try:
        assert len(notifications) == 1
        assert notifications[0].payload == {
            "cat": "state",
            "evt": "authority_reconcile_required",
            "reason": "state_authority_witness_lag",
            "authority_series": "authority.v2",
            "instance_uuid": store.status().authority_instance,
            "authority_epoch": 2,
            "resume_enabled": False,
        }
    finally:
        bus.close()


def test_resolve_project_root_uses_configured_relative_path(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    monkeypatch.setenv("PROJECT_ROOT", "target")

    assert _resolve_project_root(config_dir, None) == target.resolve()


def test_bootstrap_injects_explicit_project_root_into_code_slices(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "agent.json").write_text('{"log_level": "WARNING"}')
    (config_dir / "audit.json").write_text('{"sinks": []}')
    _write_workflow(config_dir)
    target = tmp_path / "target"
    target.mkdir()

    bus = bootstrap(config_path=config_dir, project_root=target)

    try:
        assert bus._command_handlers["PlanIssue"].__self__._project_root == target.resolve()
        assert bus._command_handlers["Implement"].__self__._project_root == target.resolve()
        assert bus._command_handlers["RunQuality"].__self__._root == target.resolve()
        assert bus._command_handlers["VerifyAC"].__self__._root == target.resolve()
        assert bus._command_handlers["BuildContext"].__self__._root == target.resolve()
        planning = bus._command_handlers["PlanIssue"].__self__
        implementation = bus._command_handlers["Implement"].__self__
        review = bus._command_handlers["Review"].__self__
        pr_gates = bus._command_handlers["CreatePR"].__self__
        assert planning._prompt_risk_analyzer is not None
        assert implementation._prompt_risk_analyzer is planning._prompt_risk_analyzer
        assert review._prompt_risk_analyzer is planning._prompt_risk_analyzer
        assert any(gate.name == "diff_secret_scan" for gate in pr_gates._external_gates)
        from samuel import __build_info__

        attribution = pr_gates._ai_attribution_fn()
        assert f"AI-Generated-By: S.A.M.U.E.L.@{__build_info__.product_version}" in attribution
        if __build_info__.revision:
            assert f"SAMUEL-Build-Revision: {__build_info__.revision}" in attribution
    finally:
        bus.close()


def test_bootstrap_binds_one_eval_policy_snapshot_to_evaluation_and_ac_verifier(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "agent.json").write_text('{"log_level":"WARNING"}')
    (config_dir / "audit.json").write_text('{"sinks":[]}')
    (config_dir / "eval.json").write_text(
        json.dumps(
            {
                "policy_version": "test.control-plane.v1",
                "test_policy_version": "test.runner.v2",
                "test_cmd": "trusted-runner {test}",
                "test_timeout": 37,
            }
        )
    )
    _write_workflow(config_dir)

    bus = bootstrap(config_path=config_dir, project_root=tmp_path)

    try:
        verifier = bus._command_handlers["VerifyAC"].__self__
        evaluation = next(
            handler.__self__
            for handler in bus._subscribers["GateEvaluationCompleted"]
            if handler.__self__.__class__.__name__ == "EvaluationHandler"
        )
        assert verifier._test_runner_policy.policy_version == evaluation._config.test_policy_version
        assert verifier._test_runner_policy.test_cmd == evaluation._config.test_cmd
        assert verifier._test_runner_policy.test_timeout == evaluation._config.test_timeout
    finally:
        bus.close()


def test_closed_bootstrap_does_not_persist_later_test_warning(tmp_path):
    """Regression #457: a finished runtime must not capture later logs."""

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    audit_path = tmp_path / "audit.jsonl"
    (config_dir / "agent.json").write_text(
        json.dumps({"log_level": "WARNING", "data_dir": str(tmp_path / "data")})
    )
    (config_dir / "audit.json").write_text(
        json.dumps({"sinks": [{"type": "jsonl", "path": str(audit_path), "rotation": "none"}]})
    )
    _write_workflow(config_dir)

    bus = bootstrap(config_path=config_dir)
    bus.close()
    before = audit_path.read_bytes() if audit_path.exists() else b""

    failed = type("Result", (), {"stdout": "", "stderr": "simulated", "returncode": 1})()
    with patch("subprocess.run", return_value=failed):
        assert current_branch() == ""

    assert (audit_path.read_bytes() if audit_path.exists() else b"") == before
    assert not any(
        handler.__class__.__name__ == "AuditDiagnosticHandler"
        for handler in logging.getLogger("samuel").handlers
    )


def test_bootstrap_uses_selected_workflow_limits_for_watch(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    stale_config_dir = tmp_path / "stale-config"
    # A stale persisted config_dir must not override the explicit --config path.
    (config_dir / "agent.json").write_text(
        json.dumps(
            {
                "log_level": "WARNING",
                "config_dir": str(stale_config_dir),
                "max_parallel": 1,
                "mode": "night",
            }
        ),
        encoding="utf-8",
    )
    (config_dir / "audit.json").write_text('{"sinks": []}', encoding="utf-8")
    _write_workflow(config_dir, name="night", max_risk=1, max_parallel=1)
    monkeypatch.delenv("SAMUEL_WORKFLOW_OVERRIDE", raising=False)
    monkeypatch.setenv("SAMUEL_CONFIGURATION_MODE", "setup")

    bus = bootstrap(config_path=config_dir)
    try:
        watch = bus._command_handlers["ScanIssues"].__self__
        assert watch._workflow_name == "night"
        assert watch._max_risk == 1
        assert watch._max_parallel == 1
        assert bus.config.get("agent.config_dir") == str(config_dir.resolve())

        from samuel.slices.dashboard.handler import DashboardHandler

        dashboard = DashboardHandler(bus, config=bus.config)
        result = dashboard.set_llm_task_config(
            "planning", {"provider": "ollama", "model": "local-model"}
        )
        assert result["updated"] is True
        saved = json.loads((config_dir / "llm" / "defaults.json").read_text(encoding="utf-8"))
        assert saved["tasks"]["planning"]["model"] == "local-model"
        assert not stale_config_dir.exists()
    finally:
        bus.close()


def test_bootstrap_rejects_unsupported_agent_parallelism_before_wiring(tmp_path, monkeypatch):
    (tmp_path / "agent.json").write_text(
        json.dumps({"log_level": "WARNING", "mode": "standard", "max_parallel": 2}),
        encoding="utf-8",
    )
    _write_workflow(tmp_path, max_parallel=1)
    monkeypatch.delenv("SAMUEL_WORKFLOW_OVERRIDE", raising=False)

    with pytest.raises(ValueError, match="agent.max_parallel must be exactly 1"):
        bootstrap(config_path=tmp_path)


def test_bootstrap_override_rejects_selected_parallel_workflow(tmp_path, monkeypatch):
    (tmp_path / "agent.json").write_text(
        json.dumps({"log_level": "WARNING", "mode": "standard", "max_parallel": 1}),
        encoding="utf-8",
    )
    _write_workflow(tmp_path, name="standard", max_parallel=1)
    _write_workflow(tmp_path, name="watch", max_parallel=2)
    monkeypatch.setenv("SAMUEL_WORKFLOW_OVERRIDE", "watch")

    with pytest.raises(ValueError, match="workflow.max_parallel must be exactly 1"):
        bootstrap(config_path=tmp_path)


def test_bootstrap_fails_clearly_when_workflow_is_missing(tmp_path, monkeypatch):
    (tmp_path / "agent.json").write_text('{"mode":"missing"}', encoding="utf-8")
    monkeypatch.delenv("SAMUEL_WORKFLOW_OVERRIDE", raising=False)

    with pytest.raises(ValueError, match="Workflow definition not found"):
        bootstrap(config_path=tmp_path)


def test_every_shipped_workflow_command_has_a_registered_handler(tmp_path, monkeypatch):
    (tmp_path / "agent.json").write_text('{"log_level":"WARNING"}', encoding="utf-8")
    (tmp_path / "audit.json").write_text('{"sinks":[]}', encoding="utf-8")
    _write_workflow(tmp_path)
    monkeypatch.delenv("SAMUEL_WORKFLOW_OVERRIDE", raising=False)

    bus = bootstrap(config_path=tmp_path)
    try:
        for workflow_path in Path("config/workflows").glob("*.json"):
            definition = json.loads(workflow_path.read_text(encoding="utf-8"))
            for step in definition["steps"]:
                assert bus.has_handler(step["send"]), (
                    f"{workflow_path.name}: no handler for {step['send']}"
                )
    finally:
        bus.close()


def test_bootstrap_wires_only_bound_gate_authority(tmp_path, monkeypatch):
    (tmp_path / "agent.json").write_text(
        json.dumps({"log_level": "WARNING"}),
        encoding="utf-8",
    )
    (tmp_path / "audit.json").write_text('{"sinks":[]}', encoding="utf-8")
    (tmp_path / "gates.json").write_text(
        '{"required":[1],"optional":[],"disabled":[],"custom":[]}',
        encoding="utf-8",
    )
    _write_workflow(tmp_path)
    monkeypatch.delenv("SAMUEL_AUTHORITY_MODE", raising=False)
    monkeypatch.delenv("SAMUEL_GATES_PROFILE", raising=False)

    bus = bootstrap(config_path=tmp_path)
    try:
        gates = bus._command_handlers["CreatePR"].__self__
        coordinators = [
            handler.__self__
            for handler in bus._subscribers["GateEvaluationCompleted"]
            if handler.__self__.__class__.__name__ == "BoundHealingCoordinator"
        ]
        assert gates._gates_profile == "default"
        assert len(coordinators) == 1
        assert not any(bus.has_handler(name) for name in ("Score", "Evaluate", "Heal"))
        assert "ScoreObserved" in bus._subscribers
    finally:
        bus.close()


@pytest.mark.parametrize(
    ("source", "value"),
    [("environment", "legacy_score_authority"), ("config", "bound_gate_authority")],
)
def test_removed_authority_switch_blocks_startup(tmp_path, monkeypatch, source, value):
    document = {"log_level": "WARNING"}
    if source == "config":
        document["authority_mode"] = value
        monkeypatch.delenv("SAMUEL_AUTHORITY_MODE", raising=False)
    else:
        monkeypatch.setenv("SAMUEL_AUTHORITY_MODE", value)
    (tmp_path / "agent.json").write_text(json.dumps(document), encoding="utf-8")
    (tmp_path / "audit.json").write_text('{"sinks":[]}', encoding="utf-8")
    _write_workflow(tmp_path)

    with patch("samuel.core.bootstrap.Bus") as bus_class:
        with pytest.raises(ValueError, match="was removed after 2.0.0a4"):
            bootstrap(config_path=tmp_path)
        bus_class.assert_not_called()


def test_bound_standard_preserves_explicit_audit_profile(tmp_path, monkeypatch):
    (tmp_path / "agent.json").write_text(
        json.dumps({"log_level": "WARNING"}),
        encoding="utf-8",
    )
    (tmp_path / "audit.json").write_text('{"sinks":[]}', encoding="utf-8")
    (tmp_path / "gates.json").write_text(
        '{"required":[1],"optional":[],"disabled":[],"custom":[]}',
        encoding="utf-8",
    )
    (tmp_path / "gates.audit.json").write_text(
        '{"required":[1,5],"optional":[],"disabled":[],"custom":[]}',
        encoding="utf-8",
    )
    _write_workflow(tmp_path)
    monkeypatch.delenv("SAMUEL_WORKFLOW_OVERRIDE", raising=False)
    monkeypatch.delenv("SAMUEL_AUTHORITY_MODE", raising=False)
    monkeypatch.setenv("SAMUEL_GATES_PROFILE", "audit")

    bus = bootstrap(config_path=tmp_path)
    try:
        gates = bus._command_handlers["CreatePR"].__self__
        assert gates._gates_profile == "audit"
        assert gates._gates_config.required == [1, 5]
        assert gates._gates_config.disabled == []
    finally:
        bus.close()


@pytest.mark.parametrize("requested_profile", ["audit", "legacy", "unknown"])
def test_self_authority_uses_self_profile_independent_of_environment(
    tmp_path, monkeypatch, requested_profile
):
    (tmp_path / "agent.json").write_text(
        json.dumps(
            {
                "log_level": "WARNING",
                "mode": "self",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "audit.json").write_text('{"sinks":[]}', encoding="utf-8")
    (tmp_path / "gates.json").write_text(
        '{"required":[1],"optional":[],"disabled":[],"custom":[]}',
        encoding="utf-8",
    )
    (tmp_path / "gates.self.json").write_text(
        '{"required":[1,9],"optional":[],"disabled":[],"custom":[]}',
        encoding="utf-8",
    )
    (tmp_path / "gates.audit.json").write_text(
        '{"required":[1,5],"optional":[],"disabled":[],"custom":[]}',
        encoding="utf-8",
    )
    _write_workflow(tmp_path, name="self")
    monkeypatch.delenv("SAMUEL_WORKFLOW_OVERRIDE", raising=False)
    monkeypatch.delenv("SAMUEL_AUTHORITY_MODE", raising=False)
    monkeypatch.setenv("SAMUEL_GATES_PROFILE", requested_profile)

    bus = bootstrap(config_path=tmp_path)
    try:
        gates = bus._command_handlers["CreatePR"].__self__
        assert gates._gates_profile == "self"
        assert gates._gates_config.required == [1, 9]
    finally:
        bus.close()


@pytest.mark.parametrize("requested_profile", ["legacy", "self", "unknown"])
def test_bound_standard_rejects_incompatible_profile_before_bus_wiring(
    tmp_path, monkeypatch, requested_profile
):
    (tmp_path / "agent.json").write_text(
        '{"log_level":"WARNING"}',
        encoding="utf-8",
    )
    (tmp_path / "audit.json").write_text('{"sinks":[]}', encoding="utf-8")
    _write_workflow(tmp_path)
    monkeypatch.delenv("SAMUEL_AUTHORITY_MODE", raising=False)
    monkeypatch.setenv("SAMUEL_GATES_PROFILE", requested_profile)

    with patch("samuel.core.bootstrap.Bus") as bus_class:
        with pytest.raises(ValueError, match="incompatible with the bound-authority workflow"):
            bootstrap(config_path=tmp_path)
        bus_class.assert_not_called()


@pytest.mark.parametrize(
    ("workflow_mode", "requested_profile", "filename"),
    [
        ("standard", "audit", "gates.audit.json"),
        ("self", "ignored", "gates.self.json"),
    ],
)
def test_bootstrap_rejects_missing_selected_gate_profile(
    tmp_path,
    monkeypatch,
    workflow_mode,
    requested_profile,
    filename,
):
    (tmp_path / "agent.json").write_text(
        json.dumps(
            {
                "log_level": "WARNING",
                "mode": workflow_mode,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "audit.json").write_text('{"sinks":[]}', encoding="utf-8")
    _write_workflow(tmp_path, name=workflow_mode)
    monkeypatch.delenv("SAMUEL_AUTHORITY_MODE", raising=False)
    monkeypatch.delenv("SAMUEL_WORKFLOW_OVERRIDE", raising=False)
    monkeypatch.setenv("SAMUEL_GATES_PROFILE", requested_profile)

    with pytest.raises(ValueError, match=rf"Gate profile .* not found: .*{filename}"):
        bootstrap(config_path=tmp_path)


def test_bound_default_without_gates_file_uses_documented_schema_fallback(tmp_path, monkeypatch):
    (tmp_path / "agent.json").write_text(
        '{"log_level":"WARNING"}',
        encoding="utf-8",
    )
    (tmp_path / "audit.json").write_text('{"sinks":[]}', encoding="utf-8")
    _write_workflow(tmp_path)
    monkeypatch.delenv("SAMUEL_AUTHORITY_MODE", raising=False)
    monkeypatch.delenv("SAMUEL_GATES_PROFILE", raising=False)

    bus = bootstrap(config_path=tmp_path)
    try:
        gates = bus._command_handlers["CreatePR"].__self__
        assert gates._gates_profile == "default"
        assert gates._gates_config.required == [1, 2, 3, 7, "7b", 8, 9, 11, "13b"]
    finally:
        bus.close()


@pytest.mark.parametrize(
    ("workflow_mode", "requested_profile", "filename"),
    [
        ("standard", "default", "gates.json"),
        ("standard", "audit", "gates.audit.json"),
        ("self", "ignored", "gates.self.json"),
    ],
)
def test_bootstrap_rejects_invalid_selected_gate_profile(
    tmp_path,
    monkeypatch,
    workflow_mode,
    requested_profile,
    filename,
):
    (tmp_path / "agent.json").write_text(
        json.dumps(
            {
                "log_level": "WARNING",
                "mode": workflow_mode,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "audit.json").write_text('{"sinks":[]}', encoding="utf-8")
    (tmp_path / filename).write_text("{invalid-json", encoding="utf-8")
    _write_workflow(tmp_path, name=workflow_mode)
    monkeypatch.delenv("SAMUEL_AUTHORITY_MODE", raising=False)
    monkeypatch.delenv("SAMUEL_WORKFLOW_OVERRIDE", raising=False)
    monkeypatch.setenv("SAMUEL_GATES_PROFILE", requested_profile)

    with pytest.raises(ValueError, match=rf"Invalid gates config {filename}"):
        bootstrap(config_path=tmp_path)


def test_fresh_noninteractive_setup_bootstraps_without_scm(tmp_path, monkeypatch):
    monkeypatch.setenv("SCM_PROVIDER", "gitea")
    for key in ("SCM_URL", "SCM_TOKEN", "SCM_REPO"):
        monkeypatch.setenv(key, "")
    (tmp_path / "agent.json").write_text(json.dumps({"data_dir": str(tmp_path / "data")}))
    (tmp_path / "audit.json").write_text('{"sinks": []}')
    _write_workflow(tmp_path)
    with patch("samuel.core.bootstrap._build_scm_adapter") as adapter:
        bus = bootstrap(config_path=str(tmp_path))
        try:
            assert isinstance(bus, Bus)
            adapter.assert_not_called()
        finally:
            bus.close()
