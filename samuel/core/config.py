from __future__ import annotations

import ast
import json
import logging
import os
import re
import shlex
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from samuel.core.gate_metadata import GATE_NAMES
from samuel.core.ports import IConfig

log = logging.getLogger(__name__)


# --- Pydantic Schemas ---

WORKFLOW_BUILTIN_CONDITION_NAMES: frozenset[str] = frozenset(
    {"plan_without_clarification", "plan_with_clarification"}
)
SUPPORTED_WATCH_MAX_PARALLEL = 1


class WorkflowStepSchema(BaseModel):
    on: str = Field(min_length=1)
    send: str = Field(min_length=1)
    condition: str | None = None

    @field_validator("condition")
    @classmethod
    def validate_condition(cls, value: str | None) -> str | None:
        if value is None:
            return None
        condition = value.strip()
        if not condition:
            raise ValueError("workflow condition must not be empty")
        if condition in WORKFLOW_BUILTIN_CONDITION_NAMES:
            return condition
        try:
            expression = ast.parse(condition, mode="eval")
        except SyntaxError as exc:
            raise ValueError(f"invalid workflow condition syntax: {condition!r}") from exc
        unknown_names = {
            node.id
            for node in ast.walk(expression)
            if isinstance(node, ast.Name) and node.id not in {"event", "payload"}
        }
        if unknown_names:
            names = ", ".join(sorted(unknown_names))
            raise ValueError(f"unknown workflow condition name(s): {names}")
        return condition


class WorkflowSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    steps: list[WorkflowStepSchema]
    max_risk: int = Field(default=3, ge=1, le=4)
    max_parallel: int = Field(default=SUPPORTED_WATCH_MAX_PARALLEL, ge=1, le=1)

    @field_validator("max_parallel", mode="before")
    @classmethod
    def validate_max_parallel(cls, value: Any) -> int:
        return resolve_watch_parallelism(SUPPORTED_WATCH_MAX_PARALLEL, value)


def resolve_watch_parallelism(
    agent_max_parallel: Any,
    workflow_max_parallel: Any,
) -> int:
    """Validate the single supported in-process Watch dispatch mode.

    The synchronous bus has no dispatcher that could make values above one
    effective.  Each source is checked independently so the former
    ``min(agent, workflow)`` calculation cannot hide an unsupported value.
    """

    for source, raw_value in (
        ("agent.max_parallel", agent_max_parallel),
        ("workflow.max_parallel", workflow_max_parallel),
    ):
        if isinstance(raw_value, bool):
            raise ValueError(
                f"{source} must be exactly {SUPPORTED_WATCH_MAX_PARALLEL}; "
                "boolean values are not valid parallelism limits"
            )
        if isinstance(raw_value, int):
            value = raw_value
        elif isinstance(raw_value, str) and raw_value.strip().isdigit():
            value = int(raw_value.strip())
        else:
            raise ValueError(
                f"{source} must be exactly {SUPPORTED_WATCH_MAX_PARALLEL}; got {raw_value!r}"
            )
        if value != SUPPORTED_WATCH_MAX_PARALLEL:
            raise ValueError(
                f"{source} must be exactly {SUPPORTED_WATCH_MAX_PARALLEL}; "
                "Watch dispatch is synchronous and no in-process parallel dispatcher exists"
            )
    return SUPPORTED_WATCH_MAX_PARALLEL


def load_workflow_config(
    config_dir: Path | str,
    name: str,
) -> dict[str, Any]:
    """Load one shipped/operator workflow without path traversal or silent fallback."""

    normalized = name.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", normalized):
        raise ValueError(f"Invalid workflow name: {name!r}")
    path = Path(config_dir) / "workflows" / f"{normalized}.json"
    if not path.is_file():
        raise ValueError(f"Workflow definition not found: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        workflow = WorkflowSchema.model_validate(document)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"Invalid workflow definition {path}: {exc}") from exc
    if workflow.name != normalized:
        raise ValueError(
            f"Workflow name mismatch in {path}: expected {normalized!r}, got {workflow.name!r}"
        )
    document = workflow.model_dump(exclude_none=True)
    return document


def resolve_gate_profile(
    workflow_mode: str,
    requested_profile: str | None = None,
) -> str:
    """Resolve the gate profile for the single bound-authority runtime.

    The self workflow is a closed profile: an unrelated environment value
    cannot replace its gate contract. Non-self workflows retain only the
    documented stricter ``audit`` opt-in in addition to the shipped default.
    """

    if workflow_mode.strip().lower() == "self":
        return "self"

    raw_profile = (
        os.environ.get(_GATES_PROFILE_ENV, "") if requested_profile is None else requested_profile
    )
    profile = str(raw_profile).strip().lower()
    if not profile or profile == "default":
        return "default"
    if profile == "audit":
        return profile
    raise ValueError(
        f"Gate profile {profile!r} is incompatible with the bound-authority "
        f"workflow {workflow_mode!r}; "
        "expected 'default' or 'audit'"
    )


class GateSchema(BaseModel):
    id: int | str
    name: str
    enabled: bool = True
    owasp_risk: str | None = None


class GatesSchema(BaseModel):
    gates: list[GateSchema] = []


class GateParametersSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_diff_bytes: int = Field(default=2_000_000, ge=1, le=100_000_000)
    max_quality_file_bytes: int = Field(default=1_000_000, ge=1, le=10_000_000)


class GatesConfigSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_version: str = Field(default="2026-08-28.bound.v2", min_length=1)
    required: list[int | str] = [1, 2, 3, 7, "7b", 8, 9, 11, "13b"]
    optional: list[int | str] = [5, 6, 12, "13a"]
    disabled: list[int | str] = []
    custom: list[dict[str, Any]] = []
    parameters: GateParametersSchema = Field(default_factory=GateParametersSchema)

    @model_validator(mode="after")
    def validate_gate_sets(self) -> GatesConfigSchema:
        groups = {
            "required": self.required,
            "optional": self.optional,
            "disabled": self.disabled,
        }
        for name, values in groups.items():
            if len(values) != len(set(values)):
                raise ValueError(f"{name} contains duplicate gate IDs")
            unknown = sorted(set(values) - set(GATE_NAMES), key=str)
            if unknown:
                raise ValueError(f"{name} contains unknown or retired gate IDs: {unknown}")
        for left, right in (
            ("required", "optional"),
            ("required", "disabled"),
            ("optional", "disabled"),
        ):
            overlap = sorted(set(groups[left]) & set(groups[right]), key=str)
            if overlap:
                raise ValueError(f"gate IDs occur in both {left} and {right}: {overlap}")
        return self


class EvalCriterionSchema(BaseModel):
    name: str
    weight: float = 1.0
    threshold: float = 0.5


class EvalSchema(BaseModel):
    policy_version: str = Field(default="2026-08-28.v1", min_length=1)
    formula_version: str = Field(default="bound-evidence.v1", min_length=1)
    test_policy_version: str = Field(default="2026-08-29.runner.v1", min_length=1)
    criteria: list[EvalCriterionSchema] = Field(
        default_factory=list,
        json_schema_extra={"deprecated": True},
    )
    weights: dict[str, float] = {
        "test_pass_rate": 0.3,
        "syntax_valid": 0.2,
        "hallucination_free": 0.3,
        "scope_compliant": 0.2,
    }
    baseline: float = 0.8
    fail_fast_on: list[str] = []
    test_cmd: str | None = None
    test_timeout: int = Field(default=60, ge=1, le=3600)

    @field_validator("test_cmd")
    @classmethod
    def validate_test_cmd(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if "{test}" not in normalized:
            raise ValueError("test_cmd must contain the {test} placeholder")
        try:
            parts = shlex.split(normalized)
        except ValueError as exc:
            raise ValueError("test_cmd must use valid shell-like quoting") from exc
        if not parts:
            raise ValueError("test_cmd must contain an executable")
        return normalized

    def model_post_init(self, __context: Any) -> None:
        if self.criteria:
            log.warning(
                "eval.json::criteria is deprecated and has no scoring effect; "
                "configure eval.json::weights instead"
            )
        total = sum(self.weights.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"weights must sum to 1.0, got {total:.4f}")
        known = set(self.weights)
        bad = [n for n in self.fail_fast_on if n not in known]
        if bad:
            raise ValueError(f"fail_fast_on references unknown checks: {bad}")


class AuditSinkSchema(BaseModel):
    type: str
    path: str | None = None
    url: str | None = None
    auth: str | None = None
    host: str | None = None
    index: str | None = None
    rotation: str | None = None


class AuditSchema(BaseModel):
    sinks: list[AuditSinkSchema] = []

    @classmethod
    def default(cls) -> AuditSchema:
        return cls(
            sinks=[AuditSinkSchema(type="jsonl", path="data/logs/agent.jsonl", rotation="daily")]
        )


class HookSchema(BaseModel):
    event: str
    action: str
    config: dict[str, Any] = {}


class HooksSchema(BaseModel):
    hooks: list[HookSchema] = []


# --- SCM Config ---

_LEGACY_MAP = {
    "GITEA_URL": "SCM_URL",
    "GITEA_TOKEN": "SCM_TOKEN",
    "GITEA_REPO": "SCM_REPO",
    "GITEA_USER": "SCM_USER",
    "GITEA_BOT_USER": "SCM_BOT_USER",
}

SCM_REQUIRED_STATUS_CONTEXT_ENV = "SCM_REQUIRED_STATUS_CONTEXT"
DEFAULT_SCM_REQUIRED_STATUS_CONTEXT = "CI / lint-and-test (pull_request)"


def resolve_scm_required_status_context(
    get: Callable[[str], str | None] | None = None,
) -> tuple[str, str]:
    """Resolve the single expected SCM check and report its visible source."""

    getter = get or os.environ.get
    raw = getter(SCM_REQUIRED_STATUS_CONTEXT_ENV)
    if raw is None:
        return DEFAULT_SCM_REQUIRED_STATUS_CONTEXT, "shipped_default"
    value = str(raw).strip()
    if not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f"{SCM_REQUIRED_STATUS_CONTEXT_ENV} must be a non-empty single line")
    return value, "configured"


class SCMConfig(BaseModel):
    provider: str = "gitea"
    url: str
    token: str
    repo: str
    user: str = ""
    bot_user: str = ""
    required_status_context: str = DEFAULT_SCM_REQUIRED_STATUS_CONTEXT

    @field_validator("required_status_context")
    @classmethod
    def validate_required_status_context(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or any(ord(char) < 32 or ord(char) == 127 for char in normalized):
            raise ValueError("required_status_context must be a non-empty single line")
        return normalized


def scm_policy_binding(config: SCMConfig | None) -> dict[str, str] | None:
    if config is None:
        return None
    return {
        "provider": config.provider.strip().lower(),
        "required_status_context": config.required_status_context,
    }


def load_scm_config() -> SCMConfig:
    required_status_context, _source = resolve_scm_required_status_context()
    if os.environ.get("SCM_PROVIDER") or os.environ.get("SCM_URL"):
        if not all(os.environ.get(key, "").strip() for key in ("SCM_URL", "SCM_TOKEN", "SCM_REPO")):
            raise ValueError("SCM not configured: SCM_URL, SCM_TOKEN and SCM_REPO are required")
        return SCMConfig(
            provider=os.environ.get("SCM_PROVIDER", "gitea"),
            url=os.environ["SCM_URL"],
            token=os.environ["SCM_TOKEN"],
            repo=os.environ["SCM_REPO"],
            user=os.environ.get("SCM_USER", ""),
            bot_user=os.environ.get("SCM_BOT_USER", ""),
            required_status_context=required_status_context,
        )
    if os.environ.get("GITEA_URL"):
        if not all(
            os.environ.get(key, "").strip() for key in ("GITEA_URL", "GITEA_TOKEN", "GITEA_REPO")
        ):
            raise ValueError(
                "SCM not configured: GITEA_URL, GITEA_TOKEN and GITEA_REPO are required"
            )
        log.info("Legacy GITEA_* env vars detected, mapping to SCM_*")
        return SCMConfig(
            provider="gitea",
            url=os.environ["GITEA_URL"],
            token=os.environ.get("GITEA_TOKEN", ""),
            repo=os.environ.get("GITEA_REPO", ""),
            user=os.environ.get("GITEA_USER", ""),
            bot_user=os.environ.get("GITEA_BOT_USER", ""),
            required_status_context=required_status_context,
        )
    raise ValueError(
        "SCM not configured. Set SCM_PROVIDER+SCM_URL+SCM_TOKEN+SCM_REPO "
        "or legacy GITEA_URL+GITEA_TOKEN+GITEA_REPO."
    )


# --- IConfig Implementation ---


class FileConfig(IConfig):
    def __init__(self, config_dir: Path | str):
        self._config_dir = Path(config_dir)
        self._data: dict[str, Any] = {}
        self._overrides: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        for json_file in self._config_dir.glob("*.json"):
            try:
                with open(json_file) as f:
                    self._data[json_file.stem] = json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("Failed to load %s: %s", json_file, exc)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._overrides:
            return self._overrides[key]
        parts = key.split(".")
        current: Any = self._data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
                if current is None:
                    return default
            else:
                return default
        return current

    def feature_flag(self, name: str) -> bool:
        return bool(self.get(f"features.{name}", False))

    def set_override(self, key: str, value: Any) -> None:
        """Set a process-local value without mutating the persisted JSON files."""

        self._overrides[key] = value

    def reload(self) -> None:
        self._data.clear()
        self._load()


_GATES_PROFILE_ENV = "SAMUEL_GATES_PROFILE"


def load_gates_config(
    config_dir: Path | str,
    profile: str | None = None,
) -> GatesConfigSchema:
    """Load the explicit gate profile without silently changing authority.

    ``profile`` (or ``SAMUEL_GATES_PROFILE``) selects
    ``gates.<profile>.json``. A named but missing profile is a startup error;
    an omitted or explicit ``default`` selection uses ``gates.json``.
    """
    cdir = Path(config_dir)
    selected_profile = profile if profile is not None else os.environ.get(_GATES_PROFILE_ENV, "")
    profile = selected_profile.strip().lower()
    path = cdir / "gates.json"
    if profile and profile != "default":
        ppath = cdir / f"gates.{profile}.json"
        if ppath.exists():
            path = ppath
        else:
            raise ValueError(f"Gate profile {profile!r} not found: {ppath}")
    if not path.exists():
        defaults = GatesConfigSchema()
        log.info(
            "No gates config found, using schema defaults (required=%s, optional=%s, disabled=%s)",
            defaults.required,
            defaults.optional,
            defaults.disabled,
        )
        return defaults
    try:
        with open(path) as f:
            data = json.load(f)
        return GatesConfigSchema(**data)
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"Invalid gates config {path.name}: {exc}") from exc
    except Exception as exc:
        raise ValueError(f"Gates config validation failed: {exc}") from exc


def load_eval_config(config_dir: Path | str) -> EvalSchema:
    path = Path(config_dir) / "eval.json"
    if not path.exists():
        log.info("No eval.json found, using defaults")
        return EvalSchema()
    try:
        with open(path) as f:
            data = json.load(f)
        return EvalSchema(**data)
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"Invalid eval.json: {exc}") from exc
    except Exception as exc:
        raise ValueError(f"Eval config validation failed: {exc}") from exc


def load_audit_config(config_dir: Path | str) -> AuditSchema:
    path = Path(config_dir) / "audit.json"
    if not path.exists():
        log.info("No audit.json found, using default JSONL sink")
        return AuditSchema.default()
    try:
        with open(path) as f:
            data = json.load(f)
        return AuditSchema(**data)
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"Invalid audit.json: {exc}") from exc
    except Exception as exc:
        raise ValueError(f"Audit config validation failed: {exc}") from exc
