from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

import pytest

from samuel.core.config import (
    AuditSchema,
    EvalSchema,
    FileConfig,
    GatesSchema,
    HooksSchema,
    WorkflowSchema,
    WorkflowStepSchema,
    load_gates_config,
    load_workflow_config,
    resolve_gate_profile,
    resolve_watch_parallelism,
)


def test_workflow_schema():
    ws = WorkflowSchema(
        name="default",
        steps=[WorkflowStepSchema(on="IssueReady", send="PlanIssue")],
    )
    assert ws.name == "default"
    assert len(ws.steps) == 1
    assert ws.max_risk == 3
    assert ws.max_parallel == 1


@pytest.mark.parametrize("condition", ["risk <= 1", "no_auto_issues", "lock_acquired"])
def test_workflow_schema_rejects_condition_names_not_available_at_runtime(condition):
    with pytest.raises(ValueError, match="unknown workflow condition name"):
        WorkflowStepSchema(on="IssueReady", send="PlanIssue", condition=condition)


def test_workflow_schema_accepts_payload_expression_condition():
    step = WorkflowStepSchema(
        on="IssueReady",
        send="PlanIssue",
        condition="payload.get('risk', 4) <= 1",
    )
    assert step.condition == "payload.get('risk', 4) <= 1"


def test_load_workflow_config_validates_and_returns_normalized_document(tmp_path):
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "night.json").write_text(
        json.dumps(
            {
                "name": "night",
                "steps": [{"on": "IssueReady", "send": "PlanIssue"}],
                "max_risk": 1,
                "max_parallel": 1,
            }
        ),
        encoding="utf-8",
    )

    definition = load_workflow_config(tmp_path, " night ")

    assert definition == {
        "name": "night",
        "steps": [{"on": "IssueReady", "send": "PlanIssue"}],
        "max_risk": 1,
        "max_parallel": 1,
    }


@pytest.mark.parametrize(
    ("agent_value", "workflow_value", "source"),
    [
        (2, 1, "agent.max_parallel"),
        (1, 2, "workflow.max_parallel"),
        (2, 2, "agent.max_parallel"),
        (0, 1, "agent.max_parallel"),
        (True, 1, "agent.max_parallel"),
    ],
)
def test_resolve_watch_parallelism_rejects_unsupported_sources(
    agent_value,
    workflow_value,
    source,
):
    with pytest.raises(ValueError, match=rf"{source} must be exactly 1"):
        resolve_watch_parallelism(agent_value, workflow_value)


def test_resolve_watch_parallelism_accepts_only_the_supported_mode():
    assert resolve_watch_parallelism(1, "1") == 1


def test_all_shipped_workflows_use_supported_parallelism():
    root = Path(__file__).resolve().parents[1]
    config_dir = root / "config"
    agent = json.loads((config_dir / "agent.json").read_text(encoding="utf-8"))

    for path in sorted((config_dir / "workflows").glob("*.json")):
        workflow = load_workflow_config(config_dir, path.stem)
        assert resolve_watch_parallelism(agent["max_parallel"], workflow["max_parallel"]) == 1


def test_load_workflow_config_rejects_parallelism_without_dispatcher(tmp_path):
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "watch.json").write_text(
        json.dumps(
            {
                "name": "watch",
                "steps": [{"on": "IssueReady", "send": "PlanIssue"}],
                "max_parallel": 2,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="workflow.max_parallel must be exactly 1"):
        load_workflow_config(tmp_path, "watch")


def test_load_workflow_config_rejects_missing_profile(tmp_path):
    with pytest.raises(ValueError, match="Workflow definition not found"):
        load_workflow_config(tmp_path, "missing")


def test_load_workflow_config_rejects_retired_legacy_steps(tmp_path):
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "standard.json").write_text(
        json.dumps(
            {
                "name": "standard",
                "steps": [{"on": "CodeGenerated", "send": "CreatePR"}],
                "legacy_steps": [{"on": "CodeGenerated", "send": "Score"}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="legacy_steps"):
        load_workflow_config(tmp_path, "standard")


@pytest.mark.parametrize(
    ("workflow_mode", "requested_profile", "expected"),
    [
        ("standard", None, "default"),
        ("standard", "", "default"),
        ("standard", " DEFAULT ", "default"),
        ("standard", " AuDiT ", "audit"),
        (" SELF ", "audit", "self"),
        ("self", "legacy", "self"),
        ("self", "unknown", "self"),
    ],
)
def test_authority_gate_profile_matrix(
    monkeypatch,
    workflow_mode,
    requested_profile,
    expected,
):
    monkeypatch.delenv("SAMUEL_GATES_PROFILE", raising=False)

    assert resolve_gate_profile(workflow_mode, requested_profile=requested_profile) == expected


@pytest.mark.parametrize("profile", ["legacy", "self", "unknown"])
def test_bound_standard_rejects_incompatible_gate_profile(profile):
    with pytest.raises(ValueError, match="incompatible with the bound-authority workflow"):
        resolve_gate_profile("standard", requested_profile=profile)


def test_authority_gate_profile_reads_environment_only_for_bound_standard(monkeypatch):
    monkeypatch.setenv("SAMUEL_GATES_PROFILE", "audit")

    assert resolve_gate_profile("standard") == "audit"
    assert resolve_gate_profile("self") == "self"


@pytest.mark.parametrize("name", ["../secret", "foo/bar", "", "night.json"])
def test_load_workflow_config_rejects_unsafe_name(tmp_path, name):
    with pytest.raises(ValueError, match="Invalid workflow name"):
        load_workflow_config(tmp_path, name)


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ("{not-json", "Invalid workflow definition"),
        ('{"name":"night","steps":[],"max_risk":0}', "Invalid workflow definition"),
        (
            '{"name":"other","steps":[{"on":"IssueReady","send":"PlanIssue"}]}',
            "Workflow name mismatch",
        ),
    ],
)
def test_load_workflow_config_rejects_invalid_document(tmp_path, document, message):
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "night.json").write_text(document, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_workflow_config(tmp_path, "night")


def test_gates_schema():
    gs = GatesSchema(gates=[])
    assert gs.gates == []


def test_eval_schema_defaults():
    es = EvalSchema()
    assert es.baseline == 0.8
    assert es.criteria == []


def test_audit_schema():
    a = AuditSchema()
    assert a.sinks == []


def test_hooks_schema():
    h = HooksSchema()
    assert h.hooks == []


def test_file_config_load():
    with tempfile.TemporaryDirectory() as d:
        cfg = Path(d) / "agent.json"
        cfg.write_text(json.dumps({"log_level": "DEBUG", "features": {"healing": True}}))
        config = FileConfig(d)
        assert config.get("agent.log_level") == "DEBUG"
        assert config.get("agent.features.healing") is True
        assert (
            config.feature_flag("healing") is False
        )  # feature_flag looks at top-level "features" key


def test_file_config_nested_key():
    with tempfile.TemporaryDirectory() as d:
        cfg = Path(d) / "scm.json"
        cfg.write_text(json.dumps({"provider": "gitea", "url": "http://localhost:3001"}))
        config = FileConfig(d)
        assert config.get("scm.provider") == "gitea"
        assert config.get("scm.missing", "default") == "default"


def test_file_config_missing_dir():
    config = FileConfig("/nonexistent/path")
    assert config.get("anything") is None


def test_file_config_reload():
    with tempfile.TemporaryDirectory() as d:
        cfg = Path(d) / "agent.json"
        cfg.write_text(json.dumps({"val": 1}))
        config = FileConfig(d)
        assert config.get("agent.val") == 1
        cfg.write_text(json.dumps({"val": 2}))
        config.reload()
        assert config.get("agent.val") == 2


def test_file_config_runtime_override_survives_reload(tmp_path):
    (tmp_path / "agent.json").write_text('{"config_dir":"stale"}', encoding="utf-8")
    config = FileConfig(tmp_path)

    config.set_override("agent.config_dir", str(tmp_path))
    config.reload()

    assert config.get("agent.config_dir") == str(tmp_path)


def test_load_gates_profile_audit(tmp_path, monkeypatch):
    monkeypatch.delenv("SAMUEL_GATES_PROFILE", raising=False)
    (tmp_path / "gates.json").write_text(
        '{"required": [1], "optional": [2], "disabled": [], "custom": []}'
    )
    (tmp_path / "gates.audit.json").write_text(
        '{"required": [1, 2, 3], "optional": [], "disabled": [], "custom": []}'
    )
    audit = load_gates_config(tmp_path, profile="audit")
    assert audit.required == [1, 2, 3] and audit.optional == []
    default = load_gates_config(tmp_path)
    assert default.optional == [2]


def test_explicit_default_profile_ignores_environment(tmp_path, monkeypatch):
    (tmp_path / "gates.json").write_text(
        '{"required": [1], "optional": [], "disabled": [], "custom": []}'
    )
    (tmp_path / "gates.audit.json").write_text(
        '{"required": [9], "optional": [], "disabled": [], "custom": []}'
    )
    monkeypatch.setenv("SAMUEL_GATES_PROFILE", "audit")

    assert load_gates_config(tmp_path, profile="default").required == [1]


def test_gates_profile_env(tmp_path, monkeypatch):
    (tmp_path / "gates.json").write_text(
        '{"required": [1], "optional": [], "disabled": [], "custom": []}'
    )
    (tmp_path / "gates.audit.json").write_text(
        '{"required": [9, 9], "optional": [], "disabled": [], "custom": []}'
    )
    monkeypatch.setenv("SAMUEL_GATES_PROFILE", "audit")
    with pytest.raises(ValueError, match="duplicate gate IDs"):
        load_gates_config(tmp_path)


def test_missing_profile_is_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv("SAMUEL_GATES_PROFILE", raising=False)
    (tmp_path / "gates.json").write_text(
        '{"required": [5], "optional": [], "disabled": [], "custom": []}'
    )
    with pytest.raises(ValueError, match="Gate profile 'nonexistent' not found"):
        load_gates_config(tmp_path, profile="nonexistent")


def test_missing_gates_config_logs_actual_schema_defaults(tmp_path, caplog):
    with caplog.at_level(logging.INFO, logger="samuel.core.config"):
        cfg = load_gates_config(tmp_path)

    assert cfg.required == [1, 2, 3, 7, "7b", 8, 9, 11, "13b"]
    assert cfg.optional == [5, 6, 12, "13a"]
    assert cfg.disabled == []
    assert caplog.messages == [
        "No gates config found, using schema defaults "
        "(required=[1, 2, 3, 7, '7b', 8, 9, 11, '13b'], "
        "optional=[5, 6, 12, '13a'], disabled=[])"
    ]


def test_default_profile_has_only_bound_gates_and_keeps_destructive_required():
    cfg = load_gates_config("config")
    assert 4 not in cfg.required + cfg.optional + cfg.disabled
    assert 10 not in cfg.required + cfg.optional + cfg.disabled
    assert "13b" in cfg.required


def test_removed_legacy_profile_is_rejected():
    with pytest.raises(ValueError, match="Gate profile 'legacy' not found"):
        load_gates_config("config", profile="legacy")


def test_self_profile_contains_only_bound_gates():
    cfg = load_gates_config("config", profile="self")
    assert cfg.required == [1, 2, 3, 7, "7b", 8, 9, 11, "13b"]
    assert cfg.optional == [5, 6, 12, "13a"]
    assert cfg.disabled == []
