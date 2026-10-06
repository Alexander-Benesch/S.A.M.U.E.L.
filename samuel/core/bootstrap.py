from __future__ import annotations

import json
import logging
import os
import shlex
from pathlib import Path
from typing import Any

from samuel.core.bus import (
    AuditMiddleware,
    Bus,
    DeadLetterQueue,
    ErrorMiddleware,
    IdempotencyMiddleware,
    IdempotencyStore,
    MetricsMiddleware,
)
from samuel.core.config import (
    FileConfig,
    SCMConfig,
    load_eval_config,
    load_gates_config,
    load_scm_config,
    load_workflow_config,
    resolve_gate_profile,
    resolve_watch_parallelism,
    scm_policy_binding,
)
from samuel.core.logging import attach_audit_diagnostics, setup_logging
from samuel.core.ports import (
    IAuthProvider,
    IExternalGate,
    IGitTransportAuth,
    INotificationSink,
    IVersionControl,
)
from samuel.core.test_runner import VerifierRunnerPolicy

log = logging.getLogger(__name__)


def _decode_dotenv_value(raw: str) -> str:
    stripped = raw.strip()
    try:
        decoded = shlex.split(stripped, comments=False, posix=True)
        return decoded[0] if len(decoded) == 1 else stripped
    except ValueError:
        return stripped.strip('"').strip("'")


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = _decode_dotenv_value(value)
            if key and key not in os.environ:
                os.environ[key] = value


def _resolve_project_root(
    config_path: str | Path,
    project_root: str | Path | None,
) -> Path:
    """Resolve the project inspected and modified by code-facing slices."""
    if project_root is not None:
        return Path(project_root).expanduser().resolve()
    configured = os.environ.get("PROJECT_ROOT", "").strip()
    if not configured:
        return Path.cwd().resolve()
    candidate = Path(configured).expanduser()
    if not candidate.is_absolute():
        candidate = Path(config_path).expanduser().resolve().parent / candidate
    return candidate.resolve()


def _build_scm_adapter(
    scm_config: SCMConfig,
    project_root: Path | None = None,
    *,
    request_timeout: float = 60.0,
    auth_provider: IAuthProvider | None = None,
) -> IVersionControl:
    """Build the configured SCM adapter without silently changing provider."""

    from samuel.adapters.auth.static_token import StaticTokenAuth

    auth = auth_provider or StaticTokenAuth(scm_config.token)
    provider = scm_config.provider.strip().lower()
    if provider == "gitea":
        from samuel.adapters.gitea.adapter import GiteaAdapter

        return GiteaAdapter(
            scm_config.url,
            scm_config.repo,
            auth,
            bot_user=scm_config.bot_user,
            project_root=project_root,
            request_timeout=request_timeout,
        )
    if provider == "github":
        from samuel.adapters.github.adapter import GitHubAdapter

        return GitHubAdapter(
            scm_config.repo,
            auth,
            base_url=scm_config.url,
            project_root=project_root,
            request_timeout=request_timeout,
            bot_user=scm_config.bot_user,
        )
    raise ValueError(f"Unsupported SCM provider: {scm_config.provider!r}")


def _build_git_transport_auth(
    scm_config: SCMConfig,
    scm: IVersionControl,
    auth: IAuthProvider,
) -> IGitTransportAuth:
    """Build the single network-Git credential boundary for the SCM adapter."""

    from samuel.adapters.git_transport import HttpGitTransportAuth

    provider = scm_config.provider.strip().lower()
    if provider == "gitea":
        username = scm_config.user.strip() or scm_config.bot_user.strip()
    elif provider == "github":
        username = "x-access-token"
    else:
        raise ValueError(f"Unsupported SCM provider: {scm_config.provider!r}")
    return HttpGitTransportAuth(scm.repository_identity, username, auth)


def bootstrap(
    config_path: str | Path = "config",
    project_root: str | Path | None = None,
    *,
    auto_resume: bool = True,
) -> Bus:
    # Step 0: .env laden (überschreibt keine bestehenden Env-Vars)
    config_path = Path(config_path).expanduser().resolve()
    _load_dotenv(config_path.parent / ".env")
    resolved_project_root = _resolve_project_root(config_path, project_root)

    # Step 1: Config laden + Pydantic-Validierung
    config = FileConfig(config_path)
    # ``--config``/``config_path`` is the runtime source of truth.  Persisted
    # agent.config_dir values may be relative or belong to a previous host;
    # pinning the normalized path here keeps every existing consumer aligned.
    config.set_override("agent.config_dir", str(config_path))
    resume_enabled = config.get("agent.resume.enabled", False)
    resume_lease_seconds = config.get("agent.resume.lease_seconds", 60)
    if not isinstance(resume_enabled, bool):
        raise ValueError("agent.resume.enabled must be a boolean")
    if (
        isinstance(resume_lease_seconds, bool)
        or not isinstance(resume_lease_seconds, int)
        or not 5 <= resume_lease_seconds <= 3600
    ):
        raise ValueError("agent.resume.lease_seconds must be an integer between 5 and 3600")
    removed_authority = os.environ.get("SAMUEL_AUTHORITY_MODE") or config.get(
        "agent.authority_mode"
    )
    if removed_authority not in (None, ""):
        raise ValueError(
            "SAMUEL_AUTHORITY_MODE/agent.authority_mode was removed after 2.0.0a4; "
            "remove the stale setting and use the bound gate profiles"
        )
    workflow_mode = os.environ.get("SAMUEL_WORKFLOW_OVERRIDE") or str(
        config.get("agent.mode", "standard")
    )
    # The explicitly selected config directory is authoritative.  An absolute
    # path persisted in agent.json may belong to the machine on which setup was
    # originally run and must not make an otherwise portable installation fail.
    workflow_definition = load_workflow_config(config_path, workflow_mode)
    review_required = any(
        isinstance(step, dict) and step.get("on") == "PRCreated" and step.get("send") == "Review"
        for step in workflow_definition.get("steps", [])
    )
    watch_max_parallel = resolve_watch_parallelism(
        config.get("agent.max_parallel", 1),
        workflow_definition.get("max_parallel", 1),
    )
    gates_profile = resolve_gate_profile(workflow_mode)
    gates_config = load_gates_config(config_path, profile=gates_profile)
    eval_config = load_eval_config(config_path)

    # The SCM API and network-Git subprocesses share one credential source but
    # retain separate, narrow ports.  Construction performs no network access.
    try:
        loaded_scm_config = load_scm_config()
    except ValueError:
        scm_config = None
        scm = None
        scm_auth = None
        git_transport_auth = None
        log.warning("SCM not configured, running without version control")
    else:
        from samuel.adapters.auth.static_token import StaticTokenAuth

        scm_config = loaded_scm_config
        scm_auth = StaticTokenAuth(scm_config.token)
        scm = _build_scm_adapter(
            scm_config,
            resolved_project_root,
            request_timeout=float(config.get("agent.network.timeout", 60)),
            auth_provider=scm_auth,
        )
        git_transport_auth = _build_git_transport_auth(scm_config, scm, scm_auth)
    effective_scm_policy = scm_policy_binding(scm_config)

    # Step 2: Logging
    log_level = config.get("agent.log_level", "INFO")
    log_file = config.get("agent.log_file")
    max_log_mb = int(config.get("agent.logging.max_log_size_mb", 10))
    setup_logging(level=str(log_level), log_file=log_file, max_log_size_mb=max_log_mb)

    # Step 3: Bus + Middleware-Kette aufbauen
    bus = Bus()

    from samuel.adapters.state.sqlite import SQLiteStateStore, resolve_data_dir

    data_dir = resolve_data_dir(config.get("agent.data_dir", "data"), config_dir=config_path)
    config.set_override("agent.data_dir", str(data_dir))
    state_store = SQLiteStateStore(data_dir)
    from samuel.adapters.workspace.git import GitWorktreeManager, resolve_work_dir

    work_dir = resolve_work_dir(
        config.get("agent.workspace.work_dir", "../samuel-workspaces"),
        config_dir=config_path,
    )
    config.set_override("agent.workspace.work_dir", str(work_dir))
    workspace_manager = GitWorktreeManager(
        work_dir,
        data_dir=data_dir,
        reserve_bytes=int(config.get("agent.workspace.reserve_mebibytes", 128)) * 1024 * 1024,
        minimum_free_bytes=int(config.get("agent.workspace.minimum_free_mebibytes", 512))
        * 1024
        * 1024,
        quarantine_max_count=int(config.get("agent.workspace.quarantine_max_count", 8)),
        quarantine_max_bytes=int(config.get("agent.workspace.quarantine_max_mebibytes", 2048))
        * 1024
        * 1024,
        quarantine_retention_hours=int(
            config.get("agent.workspace.quarantine_retention_hours", 168)
        ),
        git_timeout=int(config.get("agent.git.timeout", 30)),
        transport_auth=git_transport_auth,
    )
    store_path = data_dir / "idempotency.json"
    bus.add_middleware(IdempotencyMiddleware(IdempotencyStore(path=store_path)))
    # #334: Dead-Letter-Queue — Event-Handler-Crashes landen in data/dlq.jsonl
    bus.dlq = DeadLetterQueue(path=data_dir / "dlq.jsonl")
    bus.workspace_manager = workspace_manager
    bus.add_middleware(AuditMiddleware())
    bus.add_middleware(ErrorMiddleware(bus=bus))
    bus.add_middleware(MetricsMiddleware())

    # Step 4: Audit-Sinks verdrahten (muss vor Health-Check stehen)
    audit_sink = None
    audit_jsonl_paths: list[Path] = []
    try:
        from samuel.adapters.audit.async_sink import AsyncAuditSink
        from samuel.adapters.audit.jsonl import JSONLAuditSink
        from samuel.core.config import load_audit_config

        audit_config = load_audit_config(config_path)
        # #333: Optionaler HMAC-Key fuer tamper-evidente Audit-Logs. Ohne Key
        # bleibt das Format unveraendert (keine Chain-Felder).
        import os as _os

        hmac_key = _os.environ.get("SAMUEL_AUDIT_HMAC_KEY", "")
        # #368 Task 5: alle konfigurierten Sinks bauen (jsonl + sarif), bei
        # mehreren ueber FanOutAuditSink fanen. JSONL bleibt das Volltranskript,
        # SARIF exportiert nur Findings (owasp_risk).
        built_sinks: list = []
        for sink_cfg in audit_config.sinks:
            if sink_cfg.type == "jsonl":
                path = sink_cfg.path or "data/logs/agent.jsonl"
                audit_jsonl_paths.append(Path(path).expanduser().resolve(strict=False))
                inner = JSONLAuditSink(
                    path=path, rotation=sink_cfg.rotation or "daily", hmac_key=hmac_key
                )
                fallback = JSONLAuditSink(
                    path=f"{path}.fallback", rotation="none", hmac_key=hmac_key
                )
                built_sinks.append(AsyncAuditSink(inner=inner, fallback=fallback))
            elif sink_cfg.type == "sarif":
                from samuel.adapters.audit.sarif import SARIFAuditSink

                built_sinks.append(SARIFAuditSink(path=sink_cfg.path or "data/logs/findings.sarif"))
        if len(built_sinks) == 1:
            audit_sink = built_sinks[0]
        elif len(built_sinks) > 1:
            from samuel.adapters.audit.fanout import FanOutAuditSink

            audit_sink = FanOutAuditSink(built_sinks)
        if audit_sink:
            for mw in bus._middlewares:
                if isinstance(mw, AuditMiddleware):
                    mw._sink = audit_sink
                    break
            log.info(
                "Audit: sink configured (%s)",
                audit_config.sinks[0].type if audit_config.sinks else "none",
            )
    except Exception as exc:
        log.warning("Audit sinks not configured: %s", exc)

    # #429: from this point on every WARNING/ERROR log outside the event flow
    # is mirrored as DiagnosticRaised through AuditMiddleware.  Audit/bus
    # internals are excluded by the handler to prevent recursive failures.
    bus.audit_diagnostic_handler = attach_audit_diagnostics(bus)

    from samuel.adapters.state.sqlite import audit_authority_high_watermark

    state_store.compare_audit_authority_epoch(audit_authority_high_watermark(audit_jsonl_paths))

    from samuel.adapters.state.legacy import LegacyStateMigrator

    try:
        legacy_report = LegacyStateMigrator(state_store).migrate()
        if legacy_report["imported_sources"]:
            log.info("Legacy runtime-state sources migrated: %s", legacy_report["sources"])
    except Exception:
        # Historical observation failures are observable but never release
        # authority. The source remains active-named for operator recovery.
        log.exception("Legacy runtime-state migration failed")
    authority_legacy_report = LegacyStateMigrator(state_store).migrate_authority()
    if authority_legacy_report["imported_sources"]:
        log.info(
            "Legacy authority-state source migrated: %s",
            authority_legacy_report["sources"],
        )
    authority_status = state_store.authority.authority_status()

    # Step 5: SCM adapter was built before the workspace manager so both share
    # the same auth provider without a second credential source.
    if scm_config is not None:
        log.info("SCM: %s adapter for %s", scm_config.provider, scm_config.repo)
    # #153/#627: Quality-Metrics sind eine seriengebundene SQLite-Projektion.
    quality_registry = state_store.quality_metrics

    # Step 6: LLM-Adapter + Circuit Breaker
    llm = None
    try:
        from samuel.adapters.llm.factory import create_llm_adapter
        from samuel.adapters.secrets.env_secrets import EnvSecretsProvider

        llm = create_llm_adapter(
            config,
            EnvSecretsProvider(),
            bus=bus,
            quality_lookup=quality_registry.score_for,
            authority_store=state_store.authority,
        )
        bus.llm_activity_resolver = getattr(llm, "call_activity_status", None)
        routing = getattr(llm, "routing_summary", {})
        log.info(
            "LLM: adapter created (default=%s, fallbacks=%s, task_routes=%s)",
            routing.get(
                "default",
                os.environ.get("SAMUEL_LLM_PROVIDER")
                or config.get("llm.default.provider", "ollama"),
            ),
            routing.get("fallbacks", []),
            routing.get("tasks", {}),
        )
    except Exception as exc:
        log.warning("LLM not configured: %s", exc)
    # Step 7: Slices registrieren
    from samuel.adapters.skeleton.registry import SKELETON_BUILDERS as _SK
    from samuel.core.workflow import plan_approval_required
    from samuel.slices.architecture.handler import ArchitectureHandler
    from samuel.slices.implementation.handler import ImplementationHandler
    from samuel.slices.planning.handler import PlanningHandler
    from samuel.slices.security.handler import SecurityHandler

    _arch = ArchitectureHandler(bus, project_root=resolved_project_root)
    from samuel.core.evaluation_subject import gate_policy_binding
    from samuel.core.llm_budget import bound_digest

    architecture_policy: dict[str, Any] | None = None
    try:
        loaded_architecture = json.loads((config_path / "architecture.json").read_text("utf-8"))
        if isinstance(loaded_architecture, dict):
            architecture_policy = loaded_architecture
    except (OSError, ValueError):
        pass
    resume_policy_binding = gate_policy_binding(
        gates_config,
        eval_config,
        architecture_policy,
        scm_policy=effective_scm_policy,
    )
    resume_owner_id = f"pid:{os.getpid()}:{os.urandom(16).hex()}"
    security = SecurityHandler(bus, config=config)
    _exclude_dirs = set(config.get("agent.context.exclude_dirs", []) or [])
    _kw_ext = set(config.get("agent.context.keyword_extensions", []) or [])

    # #237: PlanningHandler bekommt dieselben Builder/Constraints wie
    # ImplementationHandler — Plan-Stage muss Code-Kontext sehen.
    planning = PlanningHandler(
        bus,
        scm=scm,
        llm=llm,
        project_root=resolved_project_root,
        skeleton_builders=list(_SK.values()),
        architecture_constraints=_arch.get_constraints(),
        architecture_policy=architecture_policy,
        exclude_dirs=_exclude_dirs or None,
        keyword_extensions=_kw_ext or None,
        max_skeleton_file_size_kb=int(config.get("agent.context.max_skeleton_file_size_kb", 20)),
        prompt_risk_analyzer=security,
        plan_approval_required=plan_approval_required(workflow_definition),
        workspace_manager=workspace_manager,
        base_ref=str(config.get("agent.default_branch", "main")),
        test_runner_policy=VerifierRunnerPolicy.from_eval_config(eval_config),
        authority_store=state_store.authority,
        workflow_budget_policy=(
            getattr(llm, "workflow_budget_policy", None) if llm is not None else None
        ),
        workflow_policy_digest=(
            bound_digest(
                {
                    "workflow": workflow_definition,
                    "budget": getattr(llm, "workflow_budget_policy", None),
                }
            )
            if llm is not None
            else ""
        ),
        clarification_wait_seconds=config.get("agent.planning.clarification_wait_seconds"),
    )
    bus.register_command("PlanIssue", planning.handle)
    bus.register_command("ReplanIssue", planning.handle)

    implementation = ImplementationHandler(
        bus,
        scm=scm,
        llm=llm,
        project_root=resolved_project_root,
        skeleton_builders=list(_SK.values()),
        architecture_constraints=_arch.get_constraints(),
        exclude_dirs=_exclude_dirs or None,
        keyword_extensions=_kw_ext or None,
        config=config,
        prompt_risk_analyzer=security,
        authority_store=state_store.authority,
        workspace_manager=workspace_manager,
        git_transport_auth=git_transport_auth,
        resume_policy_binding=resume_policy_binding,
        resume_owner_id=resume_owner_id,
        resume_lease_seconds=resume_lease_seconds,
    )
    bus.register_command("Implement", implementation.handle)

    from samuel import __build_info__
    from samuel.core.attribution import commit_trailers
    from samuel.slices.pr_gates.handler import PRGatesHandler

    provider_verification = None
    execution_config_path = config_path / "execution.json"
    execution_provider_status: dict[str, Any] = {
        "passed": True,
        "configured": execution_config_path.is_file(),
        "enabled": False,
        "required_qualified": False,
        "status": "disabled",
    }
    if execution_config_path.is_file():
        from samuel.adapters.gitea.execution_provider import (
            GiteaExecutionProfile,
            GiteaExecutionProvider,
        )

        execution_profile = GiteaExecutionProfile.from_file(execution_config_path)
        if execution_profile is not None:
            if (
                scm_config is None
                or scm_auth is None
                or scm_config.provider.strip().lower() != "gitea"
                or scm_config.repo != execution_profile.repository
            ):
                raise ValueError(
                    "qualified Gitea execution profile differs from configured SCM repository"
                )
            execution_raw = json.loads(execution_config_path.read_text(encoding="utf-8"))
            key_env = str(execution_raw.get("integrity_key_env", "")).strip()
            integrity_key = os.environ.get(key_env, "") if key_env else ""
            if len(integrity_key.encode("utf-8")) < 32:
                raise ValueError(
                    "qualified execution provider integrity key is missing or too short"
                )
            from samuel.adapters.gitea.api import GiteaAPI
            from samuel.slices.provider_verification.coordinator import (
                ProviderVerificationCoordinator,
            )

            execution_provider = GiteaExecutionProvider(
                GiteaAPI(
                    scm_config.url,
                    scm_auth,
                    timeout=float(config.get("agent.network.timeout", 60)),
                ),
                base_url=scm_config.url,
                profile=execution_profile,
                integrity_key=integrity_key.encode("utf-8"),
            )
            provider_verification = ProviderVerificationCoordinator(
                provider=execution_provider,
                authority_store=state_store.authority,
                provider_profile=execution_profile.name,
                provider_profile_digest=execution_profile.profile_digest,
            )
            execution_provider_status = {
                "passed": True,
                "configured": True,
                "enabled": True,
                "required_qualified": True,
                "status": "enabled_qualified",
                "profile": execution_profile.name,
                "profile_digest": execution_profile.profile_digest,
            }
            log.info(
                "Execution provider: qualified Gitea profile %s enabled",
                execution_profile.name,
            )

    _gates_config_dir = str(config.get("agent.config_dir", config_path))
    # #368 Task 2: Path-Risk-Classifier als External-Gate (nur wenn
    # config/path_risk.json existiert; sonst greift Gate 7 als Fallback).
    from samuel.slices.path_risk.gate import PathRiskGate

    _external_gates: list[IExternalGate] = []
    # Deterministic candidate-secret policy: always evaluates the complete
    # immutable diff and blocks before a positive gate/PR result.
    from samuel.slices.security.gate import DiffSecretGate

    _external_gates.append(DiffSecretGate(security))
    _path_risk = PathRiskGate.from_config(_gates_config_dir)
    if _path_risk is not None:
        _external_gates.append(_path_risk)
    # #368 Task 3: Symbol-Resolution-Gate (warn-only; publisht LockfileChanged
    # + UnresolvedSymbol). Bus injiziert, damit es Findings auf den Bus legt.
    from samuel.slices.symbol_resolution.gate import SymbolResolutionGate

    _external_gates.append(
        SymbolResolutionGate(
            bus=bus,
            project_root=resolved_project_root,
            config_dir=_gates_config_dir,
        )
    )
    # #368 Task 7: Coverage-Diff-Gate (warn-only; No-op ohne coverage.xml).
    from samuel.slices.coverage_gate.gate import CoverageDiffGate

    _external_gates.append(
        CoverageDiffGate(
            coverage_path=str(config.get("agent.coverage_xml", "coverage.xml")),
        )
    )

    pr_gates = PRGatesHandler(
        bus,
        scm=scm,
        config_dir=_gates_config_dir,
        project_root=resolved_project_root,
        external_gates=_external_gates,
        ai_attribution_fn=lambda: commit_trailers(
            system_version=__build_info__.product_version,
            build_revision=__build_info__.revision or "",
            build_dirty=bool(__build_info__.dirty),
            external_visible=False,
        ),
        gates_profile=gates_profile,
        gates_config=gates_config,
        eval_config=eval_config,
        authority_store=state_store.authority,
        observation_store=state_store.observations,
        scm_policy=effective_scm_policy,
        provider_verification=provider_verification,
        review_required=review_required,
    )
    bus.register_command("CreatePR", pr_gates.handle)
    bus.register_command("SubmitCandidate", pr_gates.handle_candidate)
    bus.register_command("RequestCandidateVerification", pr_gates.handle_provider_candidate)

    from samuel.slices.evaluation.handler import EvaluationHandler

    evaluation = EvaluationHandler(
        bus,
        scm=scm,
        config_dir=str(config.get("agent.config_dir", config_path)),
        data_dir=str(config.get("agent.data_dir", "data")),
        config=config,
        eval_config=eval_config,
        observation_store=state_store.observations,
    )
    evaluation.register_bound_observer()

    from samuel.slices.run_projection.handler import RunProjectionHandler

    run_projection = RunProjectionHandler(bus, state_store.projections)
    try:
        run_projection.backfill_audit(data_dir)
    except Exception:
        log.exception("Runtime run-projection backfill failed")
    run_projection.register()

    from samuel.slices.evaluation.presentation import ScorePresentationHandler

    score_presentation = ScorePresentationHandler(
        bus,
        scm=scm,
        request_timeout=float(config.get("agent.network.timeout", 60)),
    )
    score_presentation.register()

    from samuel.slices.watch.handler import WatchHandler

    watch = WatchHandler(
        bus,
        scm=scm,
        config=config,
        max_parallel=watch_max_parallel,
        max_risk=int(workflow_definition.get("max_risk", 3)),
        workflow_name=workflow_mode,
        authority_store=state_store.authority,
    )
    bus.register_command("ScanIssues", watch.handle)

    from samuel.slices.resume.handler import ResumeCoordinator

    resume = ResumeCoordinator(
        bus,
        authority_store=state_store.authority,
        workspace_manager=workspace_manager,
        config=config,
        owner_id=resume_owner_id,
        projection_store=state_store.projections,
        provider_verification=provider_verification,
    )
    bus.register_command("ResumePending", resume.handle)
    bus.resume_coordinator = resume

    from samuel.slices.healing.bound import BoundHealingCoordinator

    bound_healing = BoundHealingCoordinator(
        bus,
        llm=llm,
        config=config,
        authority_store=state_store.authority,
        prompt_risk_analyzer=security,
    )
    bound_healing.register()

    from samuel.slices.health.handler import HealthHandler

    health = HealthHandler(
        bus,
        scm=scm,
        llm=llm,
        config=config,
        state=state_store,
        resume_status=resume.status,
        execution_provider_status=execution_provider_status,
        projection_store=state_store.projections,
    )
    bus.register_command("HealthCheck", health.handle)

    from samuel.adapters.quality.registry import (
        get_all_unique_checks,
        load_registry_from_config,
    )
    from samuel.slices.quality.handler import QualityHandler

    hooks_path = Path(str(config.get("agent.config_dir", config_path))) / "hooks.json"
    load_registry_from_config(hooks_path if hooks_path.exists() else None)

    quality = QualityHandler(
        bus,
        checks=get_all_unique_checks(),
        project_root=resolved_project_root,
    )
    bus.register_command("RunQuality", quality.handle)

    # #153/#399: passive attribution consumes only versioned ScoreObserved.
    from samuel.slices.quality_metrics.handler import QualityMetricsHandler

    quality_metrics = QualityMetricsHandler(
        bus,
        quality_registry,
    )
    quality_metrics.register()

    from samuel.slices.ac_verification.handler import ACVerificationHandler

    ac_verify = ACVerificationHandler(
        bus,
        project_root=resolved_project_root,
        eval_config=eval_config,
        workspace_manager=workspace_manager,
    )
    bus.register_command("VerifyAC", ac_verify.handle)

    from samuel.adapters.skeleton.registry import SKELETON_BUILDERS
    from samuel.slices.context.handler import ContextHandler

    _skeleton_builders = list(SKELETON_BUILDERS.values())

    context = ContextHandler(
        bus,
        project_root=resolved_project_root,
        config=config,
        skeleton_builders=_skeleton_builders,
    )
    bus.register_command("BuildContext", context.handle)

    from samuel.slices.privacy.handler import PrivacyHandler
    from samuel.slices.review.handler import ReviewHandler

    privacy = PrivacyHandler(bus, config=config, config_dir=config_path)

    review = ReviewHandler(
        bus,
        scm=scm,
        llm=llm,
        prompt_risk_analyzer=security,
        prompt_sanitizer=privacy.sanitizer.sanitize,
        authority_store=state_store.authority,
        observation_store=state_store.observations,
        auto_merge_enabled=config.feature_flag("auto_merge_pr"),
        expected_head_merge_qualified=config.feature_flag("expected_head_merge_qualified"),
    )
    bus.register_command("Review", review.handle)
    bus.subscribe("PullRequestMerged", review.observe_merge)

    from samuel.slices.changelog.handler import ChangelogHandler

    changelog = ChangelogHandler(bus, scm=scm)
    bus.register_command("Changelog", changelog.handle)

    bus.register_command("CheckRetention", lambda cmd: privacy.check_retention())
    if privacy.retention is not None:
        from samuel.slices.privacy.retention import RetentionCoordinator

        bus.retention_coordinator = RetentionCoordinator(
            policy=privacy.retention,
            state=state_store.retention,
            authority=state_store.authority,
            execution=state_store.retention_execution,
        )

    from samuel.slices.setup.handler import SetupHandler

    setup = SetupHandler(bus, config=config)
    setup.ensure_directories()

    from samuel.slices.labels.handler import LabelsHandler

    labels = LabelsHandler(bus, scm=scm)
    labels.register()
    bus.labels = labels

    from samuel.slices.session.handler import SessionHandler

    session = SessionHandler(bus, config=config, authority_store=state_store.authority)
    bus.session = session

    from samuel.slices.sequence.handler import SequenceHandler

    sequence = SequenceHandler(
        bus,
        mode=config.get("agent.sequence_validator", "warn"),
        patterns_path=Path(str(config.get("agent.config_dir", config_path))) / "repo_patterns.json",
    )

    def record_sequence_event(event: Any) -> None:
        sequence.record_event(event.name)

    bus.subscribe("*", record_sequence_event)
    bus.sequence = sequence

    # Step 8: Startup-Validation (Health-Check)
    from samuel.core.commands import HealthCheckCommand

    health_result = bus.send(HealthCheckCommand(payload={}))
    if health_result:
        if not health_result.get("critical", True):
            log.error("Critical health checks failed: %s", health_result.get("checks"))
        else:
            log.info(
                "Health: critical=%s, healthy=%s",
                health_result.get("critical"),
                health_result.get("healthy"),
            )

    # Step 9: Das vor dem Watch-Wiring validierte Profil aktivieren. Dadurch
    # verwenden Watch-Limits und Workflow-Engine garantiert dasselbe Dokument.
    from samuel.core.workflow import WorkflowEngine

    WorkflowEngine(bus, workflow_definition, config=config)
    log.info(
        "Workflow '%s' geladen (%d steps, max_risk=%d, max_parallel=%d)",
        workflow_mode,
        len(workflow_definition.get("steps", [])),
        int(workflow_definition.get("max_risk", 3)),
        watch_max_parallel,
    )
    from samuel.core.workflow_outcome import TERMINAL_WORKFLOW_EVENTS

    for terminal_event in TERMINAL_WORKFLOW_EVENTS:
        bus.subscribe(terminal_event, resume.observe_terminal)

    # Step 10: Notification-Sinks laden
    try:
        notifications_path = (
            Path(str(config.get("agent.config_dir", config_path))) / "notifications.json"
        )
        if notifications_path.exists():
            import json as _json

            with open(notifications_path) as f:
                notif_data = _json.load(f)
            for adapter_cfg in notif_data.get("adapters", []):
                if not adapter_cfg.get("enabled", False):
                    continue
                atype = adapter_cfg.get("type", "")
                sink: INotificationSink
                if atype == "slack":
                    from samuel.adapters.notifications.slack import SlackNotifier

                    sink = SlackNotifier(
                        webhook_url=adapter_cfg["webhook_url"], channel=adapter_cfg.get("channel")
                    )
                    bus.subscribe("*", sink.notify)
                    log.info("Notification sink: Slack")
                elif atype == "teams":
                    from samuel.adapters.notifications.teams import TeamsNotifier

                    sink = TeamsNotifier(webhook_url=adapter_cfg["webhook_url"])
                    bus.subscribe("*", sink.notify)
                    log.info("Notification sink: Teams")
                elif atype == "generic_webhook":
                    from samuel.adapters.notifications.generic_webhook import GenericWebhookNotifier

                    sink = GenericWebhookNotifier(
                        url=adapter_cfg["url"], headers=adapter_cfg.get("headers", {})
                    )
                    bus.subscribe("*", sink.notify)
                    log.info("Notification sink: generic webhook")
    except Exception as exc:
        log.warning("Notification sinks not loaded: %s", exc)

    if authority_status.get("reconcile_required"):
        from samuel.core.events import AuthorityReconcileRequired
        from samuel.core.state import authority_event_binding

        bus.publish(
            AuthorityReconcileRequired(
                payload={
                    "cat": "state",
                    "evt": "authority_reconcile_required",
                    "reason": authority_status.get("reconcile_reason"),
                    **authority_event_binding(authority_status),
                    "resume_enabled": False,
                }
            )
        )

    # Step 11: Signal-Handler + Graceful Shutdown werden in cli.py registriert

    bus.audit_sink = audit_sink
    bus.scm = scm
    bus.config = config
    bus.state_store = state_store
    bus.observation_store = state_store.observations
    bus.run_projection_store = state_store.projections
    bus.quality_registry = quality_registry
    bus.authority_state_store = state_store.authority
    if auto_resume and resume.enabled:
        from samuel.core.commands import ResumePendingCommand

        bus.send(ResumePendingCommand(payload={"source": "bootstrap"}))
    return bus
