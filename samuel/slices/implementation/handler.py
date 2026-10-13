from __future__ import annotations

import hashlib
import logging
import os
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from samuel.core.acceptance import (
    AcceptanceApproval,
    AcceptanceContract,
    PlanningSourceSnapshot,
    clarification_evidence_failure,
    issue_revision_digest,
    latest_active_plan,
    parse_acceptance_contract,
)
from samuel.core.bus import Bus
from samuel.core.commands import Command, ImplementCommand
from samuel.core.errors import ProviderUnavailable
from samuel.core.evaluation_subject import EvaluationSubject
from samuel.core.events import (
    CodeGenerated,
    TokenLimitHit,
    WorkflowBlocked,
)
from samuel.core.issue_context import current_budget_admission, issue_scope
from samuel.core.ports import (
    IAuthorityStateStore,
    IConfig,
    IGitTransportAuth,
    ILLMProvider,
    IPromptRiskAnalyzer,
    ISkeletonBuilder,
    IVersionControl,
    IWorkspaceManager,
)
from samuel.core.security_policy import PROMPT_GUARD_MARKERS
from samuel.core.state import (
    AuthorityLeaseRecord,
    OperationIntentRecord,
    StateStoreError,
    WorkflowCheckpointRecord,
    authority_event_binding,
)
from samuel.core.types import WorkflowCheckpoint
from samuel.core.workspaces import WorkspaceError
from samuel.slices.implementation.context_builder import build_full_context
from samuel.slices.implementation.context_validator import validate_context
from samuel.slices.implementation.llm_loop import run_llm_loop
from samuel.slices.implementation.workspace_transaction import WorkspaceRollbackError

log = logging.getLogger(__name__)


def _build_implement_prompt(
    issue_number: int,
    issue_title: str,
    issue_body: str,
    plan_text: str,
    context: dict[str, str] | None = None,
) -> str:
    safe_title = f"<user-content>{issue_title}</user-content>"
    safe_body = f"<user-content>{issue_body}</user-content>"
    ctx = context or {}

    parts = [
        PROMPT_GUARD_MARKERS[0],
        PROMPT_GUARD_MARKERS[1],
        "",
        f"# Implementierung für Issue #{issue_number}",
        "",
        f"## Issue-Titel\n{safe_title}",
        "",
        f"## Issue-Beschreibung\n{safe_body}",
        "",
        f"## Plan\n{plan_text}" if plan_text else "",
    ]

    if ctx.get("keywords"):
        parts += ["", f"## Suchbegriffe aus Issue/Plan\n{ctx['keywords']}"]
    if ctx.get("plan_files"):
        parts += ["", f"## Plan-referenzierte Dateien\n{ctx['plan_files']}"]
    if ctx.get("module_context"):
        parts += ["", ctx["module_context"]]
    if ctx.get("skeleton"):
        parts += ["", ctx["skeleton"]]
    if ctx.get("grep"):
        parts += ["", ctx["grep"]]
    if ctx.get("relevant_files"):
        parts += ["", ctx["relevant_files"]]
    if ctx.get("constraints"):
        parts += ["", ctx["constraints"]]
    # #239: heal_hint nach allen anderen Sections, direkt vor Aufgabe — der
    # LLM sieht zuletzt warum die letzte Runde scheiterte und was zu aendern ist.
    if ctx.get("heal_hint"):
        parts += ["", ctx["heal_hint"]]

    parts += [
        "",
        "## Aufgabe",
        "Implementiere die Änderungen gemäß dem Plan. Nutze bevorzugt REPLACE LINES "
        "(Zeilennummern siehe Skeleton oben) oder SEARCH/REPLACE:",
        "",
        "Fehlt dir der konkrete Code einer großen Datei (nur Skeleton-TOC gezeigt)? "
        "Fordere ihn gezielt an — insgesamt sind maximal drei Slice-Runden mit "
        "bis zu fünf Anfragen je Runde innerhalb des maximal fünf Runden langen "
        "LLM-Loops möglich. Die Zeilen kommen in der nächsten Antwort:",
        "SLICE: datei.py:100-200",
        "",
        "REPLACE LINES Format (bevorzugt):",
        "## datei.py",
        "REPLACE LINES 10-25",
        "[neuer Code]",
        "END REPLACE",
        "",
        "SEARCH/REPLACE Format:",
        "## datei.py",
        "<<<<<<< SEARCH",
        "[alter Code — exakt wie im Skeleton bzw. oben angezeigt]",
        "=======",
        "[neuer Code]",
        ">>>>>>> REPLACE",
        "",
        "WRITE Format (nur für neue Dateien):",
        "## WRITE: neue_datei.py",
        "[vollständiger Inhalt]",
        "## END_WRITE",
    ]
    return "\n".join(p for p in parts if p != "")


class ImplementationHandler:
    def __init__(
        self,
        bus: Bus,
        scm: IVersionControl | None = None,
        llm: ILLMProvider | None = None,
        project_root: Path | None = None,
        checkpoint_store: dict[int, WorkflowCheckpoint] | None = None,
        skeleton_builders: list[ISkeletonBuilder] | None = None,
        architecture_constraints: list[str] | None = None,
        exclude_dirs: set[str] | None = None,
        keyword_extensions: set[str] | None = None,
        enforce_context_quality: bool = True,
        config: IConfig | None = None,
        prompt_risk_analyzer: IPromptRiskAnalyzer | None = None,
        authority_store: IAuthorityStateStore | None = None,
        workspace_manager: IWorkspaceManager | None = None,
        git_transport_auth: IGitTransportAuth | None = None,
        resume_policy_binding: dict[str, Any] | None = None,
        resume_owner_id: str | None = None,
        resume_lease_seconds: int = 60,
    ) -> None:
        self._bus = bus
        self._scm = scm
        self._llm = llm
        self._project_root = project_root
        self._checkpoints = checkpoint_store if checkpoint_store is not None else {}
        self._skeleton_builders = skeleton_builders or []
        self._architecture_constraints = architecture_constraints or []
        self._exclude_dirs = exclude_dirs
        self._keyword_extensions = keyword_extensions
        self._enforce_context_quality = enforce_context_quality
        self._config = config
        self._prompt_risk_analyzer = prompt_risk_analyzer
        self._authority = authority_store
        self._workspace_manager = workspace_manager
        self._git_transport_auth = git_transport_auth
        self._resume_policy_binding = dict(resume_policy_binding or {})
        self._resume_owner_id = resume_owner_id or f"pid:{os.getpid()}:{uuid4()}"
        self._resume_lease_seconds = max(5, int(resume_lease_seconds))

    @staticmethod
    def _authority_key(kind: str, *parts: str) -> str:
        value = "\x00".join((kind, *parts)).encode("utf-8")
        return f"{kind}:sha256:{hashlib.sha256(value).hexdigest()}"

    def _repository_identity(self) -> str:
        if self._scm is None:
            return ""
        try:
            return self._scm.repository_identity
        except Exception:  # noqa: BLE001 - diagnostic binding remains explicitly incomplete
            log.warning("SCM repository identity unavailable for diagnostic authority binding")
            return ""

    def _authority_event_binding(self, authority_epoch: int | None) -> dict[str, Any]:
        if authority_epoch is None:
            return {}
        if self._authority is None:
            raise StateStoreError(
                "state_authority_binding_invalid",
                "Authority event cannot be bound without an authority store",
            )
        return authority_event_binding(
            self._authority.authority_status(),
            authority_epoch=authority_epoch,
        )

    def _checkpoint_key(self, correlation_id: str, issue_number: int) -> str:
        return self._authority_key(
            "checkpoint", correlation_id or str(issue_number), str(issue_number)
        )

    def _resume_binding(self, plan_text: str) -> dict[str, Any]:
        contract = parse_acceptance_contract(plan_text)
        binding = dict(self._resume_policy_binding)
        binding["contract_hash"] = contract.contract_hash
        if contract.source_snapshot is not None:
            binding["source_snapshot"] = contract.source_snapshot.as_dict()
        return binding

    def _planning_source(
        self,
        issue_number: int,
        cmd: ImplementCommand,
    ) -> PlanningSourceSnapshot:
        """Load and verify the system-owned planning source before mutation."""

        if self._scm is None:
            raise ValueError("planning_source_scm_unavailable")
        comments = self._scm.get_comments(issue_number)
        active = latest_active_plan(comments)
        if active is None:
            raise ValueError("planning_contract_missing")
        plan_comment, contract = active
        source = contract.source_snapshot
        if source is None:
            raise ValueError("planning_source_missing")
        supplied = cmd.payload.get("acceptance_contract")
        if isinstance(supplied, dict):
            supplied_contract = AcceptanceContract.from_dict(supplied)
            if supplied_contract.contract_hash != contract.contract_hash:
                raise ValueError("planning_contract_changed")
        supplied_approval = cmd.payload.get("acceptance_approval")
        if isinstance(supplied_approval, dict):
            approval = AcceptanceApproval.from_dict(supplied_approval)
            if (
                approval.state != "approved"
                or approval.contract_hash != contract.contract_hash
                or approval.plan_comment_id != plan_comment.id
            ):
                raise ValueError("planning_approval_changed")
        if source.repository != self._scm.repository_identity:
            raise ValueError("planning_repository_changed")
        issue = self._scm.get_issue(issue_number)
        clarification_failure = clarification_evidence_failure(contract, issue, comments)
        if clarification_failure is not None:
            raise ValueError(clarification_failure)
        observed_issue_digest = issue_revision_digest(
            number=issue.number,
            title=issue.title,
            body=issue.body,
        )
        if observed_issue_digest != source.issue_digest:
            raise ValueError("planning_issue_changed")
        if self._scm.resolve_ref(source.base_ref) != source.base_sha:
            raise ValueError("planning_base_changed")
        return source

    def _block_planning_source(
        self,
        issue_number: int,
        correlation_id: str,
        reason: str,
    ) -> dict[str, Any]:
        self._bus.publish(
            WorkflowBlocked(
                payload={"issue": issue_number, "reason": reason},
                correlation_id=correlation_id,
            )
        )
        return {"success": False, "reason": reason, "patches_applied": []}

    def _claim_resume_lease(self, workspace_id: str, *, takeover: bool) -> AuthorityLeaseRecord:
        if self._authority is None:
            raise StateStoreError(
                "resume_authority_unavailable",
                "Authority state is required for a resumable finalization",
            )
        now = datetime.now(timezone.utc)
        current = self._authority.get_lease(workspace_id)
        if current is None:
            record = AuthorityLeaseRecord(
                resource_key=workspace_id,
                owner_id=self._resume_owner_id,
                expires_at=now + timedelta(seconds=self._resume_lease_seconds),
                version=1,
            )
            self._authority.acquire_lease(record)
            return record
        if current.owner_id == self._resume_owner_id:
            record = AuthorityLeaseRecord(
                resource_key=workspace_id,
                owner_id=self._resume_owner_id,
                expires_at=now + timedelta(seconds=self._resume_lease_seconds),
                version=current.version + 1,
            )
            self._authority.acquire_lease(record, expected_version=current.version)
            return record
        if not takeover or current.expires_at > now:
            raise StateStoreError(
                "resume_lease_live",
                "The persisted workspace lease has not expired",
            )
        record = AuthorityLeaseRecord(
            resource_key=workspace_id,
            owner_id=self._resume_owner_id,
            expires_at=now + timedelta(seconds=self._resume_lease_seconds),
            version=current.version + 1,
        )
        self._authority.acquire_lease(record, expected_version=current.version)
        return record

    def _persist_finalization_checkpoint(
        self,
        *,
        issue_number: int,
        correlation_id: str,
        boundary: str,
        branch: str,
        base_ref: str,
        head_sha: str,
        workspace_id: str,
        evaluation_subject: dict[str, Any],
        payload: dict[str, Any],
    ) -> int | None:
        if self._authority is None:
            return None
        return self._authority.put_checkpoint(
            WorkflowCheckpointRecord(
                checkpoint_key=self._checkpoint_key(correlation_id, issue_number),
                issue_number=issue_number,
                correlation_id=correlation_id,
                workflow="implementation_finalization",
                boundary=boundary,
                repository=self._repository_identity(),
                branch=branch,
                base_ref=base_ref,
                head_sha=head_sha,
                workspace_id=workspace_id,
                evaluation_subject=evaluation_subject,
                resume_eligible=True,
                payload={
                    **payload,
                    **(
                        {"budget_admission_key": current_budget_admission()}
                        if current_budget_admission()
                        else {}
                    ),
                },
            )
        ).authority_epoch

    def _put_intent(
        self,
        *,
        operation: str,
        issue_number: int,
        correlation_id: str,
        subject_key: str,
        payload: dict[str, Any],
    ) -> tuple[str, int] | None:
        if self._authority is None:
            return None
        key = self._authority_key(operation, correlation_id, subject_key)
        result = self._authority.put_intent(
            OperationIntentRecord(
                intent_key=key,
                operation=operation,
                status="pending",
                issue_number=issue_number,
                correlation_id=correlation_id,
                subject_key=subject_key,
                payload=payload,
            )
        )
        return key, result.authority_epoch

    def _finish_intent(
        self,
        intent: tuple[str, int] | None,
        *,
        status: str,
        postcondition: dict[str, Any],
    ) -> int | None:
        if self._authority is None or intent is None:
            return None
        result = self._authority.finish_intent(
            intent[0],
            status=status,
            postcondition=postcondition,
        )
        return result.authority_epoch

    def handle(self, cmd: Command) -> Any:
        assert isinstance(cmd, ImplementCommand)
        issue_number = cmd.issue_number
        with issue_scope(
            issue_number,
            cmd.correlation_id,
            cmd.payload.get("budget_admission_key"),
        ):
            return self._handle_inner(cmd, issue_number)

    def _append_self_mode_metrics(
        self,
        *,
        issue_number: int,
        duration_seconds: float,
        result: dict[str, Any],
    ) -> None:
        """#319: Per-run Self-Mode-Health-Record — fuer Hang-Pattern-Analyse.

        Persistent in ``<agent.data_dir>/logs/self_mode_metrics.jsonl`` (auch
        nach /tmp-Cleanup verfuegbar). Schema:
        ``{issue, ts, duration_seconds, rounds, success, reason,
            patches_applied, rounds_stats: [...]}``.
        """
        import datetime as _dt
        import json as _json
        from pathlib import Path as _Path

        rounds_stats = result.get("rounds_stats") or []
        record = {
            "issue": issue_number,
            "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "duration_seconds": round(duration_seconds, 2),
            "rounds": result.get("round", 0),
            "success": bool(result.get("success", False)),
            "reason": result.get("reason", "unknown"),
            "patches_applied": len(result.get("patches_applied", [])),
            "input_tokens": result.get("input_tokens", 0),
            "output_tokens": result.get("output_tokens", 0),
            "rounds_stats": rounds_stats,
        }
        data_dir: Any = "data"
        if self._config is not None:
            data_dir = self._config.get("agent.data_dir", "data")
        if not isinstance(data_dir, (str, _Path)) or not str(data_dir).strip():
            data_dir = "data"
        log_dir = _Path(data_dir) / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        fp = log_dir / "self_mode_metrics.jsonl"
        with fp.open("a", encoding="utf-8") as f:
            f.write(_json.dumps(record, ensure_ascii=False) + "\n")

    def _attribution_enabled(self) -> bool:
        """#270: Externe-Sichtbarkeits-Ebene aktiv? (Inline-Marker +
        ``Co-Authored-By``). Default ``True`` ohne Config — die Audit-Ebene ist
        davon unberuehrt und immer aktiv."""
        if self._config is None:
            return True
        return bool(self._config.feature_flag("llm_attribution"))

    def _build_attribution_cfg(self, issue_number: int) -> dict[str, Any] | None:
        """#270: Marker-Konfiguration fuer ``run_llm_loop`` (oder ``None``)."""
        if not self._attribution_enabled():
            return None
        import datetime as _dt

        verbosity = "minimal"
        if self._config is not None:
            verbosity = str(self._config.get("privacy.attribution.verbosity", "minimal"))
        return {
            "enabled": True,
            "verbosity": verbosity,
            "version": "",
            "issue": issue_number,
            "date": _dt.date.today().isoformat(),
        }

    def _handle_inner(self, cmd: ImplementCommand, issue_number: int) -> Any:
        project = self._project_root or Path(".")
        resume_finalization = bool(cmd.payload.get("resume_finalization"))
        if resume_finalization and self._workspace_manager is None:
            self._bus.publish(
                WorkflowBlocked(
                    payload={"issue": issue_number, "reason": "resume_workspace_unavailable"},
                    correlation_id=cmd.correlation_id or "",
                )
            )
            return {
                "success": False,
                "resumed": False,
                "reason": "resume_workspace_unavailable",
                "patches_applied": [],
            }
        if not resume_finalization and (
            self._workspace_manager is None
            or (self._config and not self._config.feature_flag("auto_implement_llm"))
            or self._llm is None
        ):
            return self._handle_in_project(
                cmd,
                issue_number,
                project=project,
                branch_ready=False,
                workspace_id="",
            )

        workspace_manager = self._workspace_manager
        assert workspace_manager is not None

        correlation_id = cmd.correlation_id or str(issue_number)
        source_snapshot: PlanningSourceSnapshot | None = None
        if not resume_finalization:
            try:
                source_snapshot = self._planning_source(issue_number, cmd)
            except Exception as exc:  # noqa: BLE001 - source verification fails closed
                reason = (
                    str(exc)
                    if isinstance(exc, ValueError)
                    else str(getattr(exc, "code", "planning_source_unavailable"))
                )
                log.warning(
                    "Planning source verification blocked issue #%d: %s (%s)",
                    issue_number,
                    reason,
                    type(exc).__name__,
                )
                return self._block_planning_source(issue_number, correlation_id, reason)
        branch_name = str(cmd.payload.get("branch") or f"samuel/issue-{issue_number}")
        resume_head_sha = str(cmd.payload.get("resume_head_sha") or "")
        workspace_id = self._authority_key(
            "run-workspace",
            self._repository_identity(),
            correlation_id,
            branch_name,
        )
        supplied_workspace_id = str(cmd.payload.get("workspace_id") or "")
        if supplied_workspace_id and supplied_workspace_id != workspace_id:
            self._bus.publish(
                WorkflowBlocked(
                    payload={
                        "issue": issue_number,
                        "reason": "workspace_identity_mismatch",
                        "branch": branch_name,
                    },
                    correlation_id=cmd.correlation_id or "",
                )
            )
            return {
                "success": False,
                "reason": "workspace_identity_mismatch",
                "patches_applied": [],
            }
        try:
            workspace = (
                workspace_manager.acquire_existing_run(
                    repository_root=project,
                    workspace_id=workspace_id,
                    branch=branch_name,
                )
                if resume_finalization
                else workspace_manager.acquire_run(
                    repository_root=project,
                    workspace_id=workspace_id,
                    branch=branch_name,
                    base_ref=(source_snapshot.base_ref if source_snapshot is not None else "main"),
                    expected_head=resume_head_sha,
                    expected_base_sha=(
                        source_snapshot.base_sha if source_snapshot is not None else ""
                    ),
                )
            )
        except WorkspaceError as exc:
            # A competing resume must not terminalize the active run's issue.
            # ResumeCoordinator publishes ResumeBlocked for this expected guard.
            if not (resume_finalization and exc.code == "workspace_owned"):
                self._bus.publish(
                    WorkflowBlocked(
                        payload={
                            "issue": issue_number,
                            "reason": exc.code,
                            "branch": branch_name,
                        },
                        correlation_id=cmd.correlation_id or "",
                    )
                )
            return {"success": False, "reason": exc.code, "patches_applied": []}

        try:
            if resume_finalization:
                result = self._resume_finalization(
                    cmd,
                    issue_number,
                    project=workspace.path,
                    workspace_id=workspace.workspace_id,
                )
            else:
                result = self._handle_in_project(
                    cmd,
                    issue_number,
                    project=workspace.path,
                    branch_ready=True,
                    workspace_id=workspace.workspace_id,
                )
        except BaseException:
            checkpoint = (
                self._authority.get_checkpoint(self._checkpoint_key(correlation_id, issue_number))
                if self._authority is not None
                else None
            )
            if checkpoint is not None and checkpoint.resume_eligible:
                workspace_manager.detach(workspace.workspace_id)
            else:
                workspace_manager.quarantine(
                    workspace.workspace_id,
                    reason="implementation_process_aborted",
                )
            raise
        checkpoint = (
            self._authority.get_checkpoint(self._checkpoint_key(correlation_id, issue_number))
            if self._authority is not None
            else None
        )
        if checkpoint is not None and checkpoint.resume_eligible:
            workspace_manager.detach(workspace.workspace_id)
        else:
            workspace_manager.release(workspace.workspace_id)
        return result

    def _handle_in_project(
        self,
        cmd: ImplementCommand,
        issue_number: int,
        *,
        project: Path,
        branch_ready: bool,
        workspace_id: str,
    ) -> Any:
        correlation_id = cmd.correlation_id or ""

        if self._config and not self._config.feature_flag("auto_implement_llm"):
            log.info(
                "auto_implement_llm disabled — skipping implementation for #%d",
                issue_number,
            )
            self._bus.publish(
                WorkflowBlocked(
                    payload={"issue": issue_number, "reason": "auto_implement_llm disabled"},
                    correlation_id=correlation_id,
                )
            )
            return None

        if not self._llm:
            self._bus.publish(
                WorkflowBlocked(
                    payload={"issue": issue_number, "reason": "no LLM configured"},
                    correlation_id=correlation_id,
                )
            )
            return None

        issue_title = ""
        issue_body = ""
        plan_text = ""

        if self._scm:
            issue = self._scm.get_issue(issue_number)
            issue_title = issue.title
            issue_body = issue.body
            comments = self._scm.get_comments(issue_number)
            active = latest_active_plan(comments)
            if active is not None:
                plan_text = active[0].body

        planning_base_ref = "main"
        if plan_text:
            try:
                planning_contract = parse_acceptance_contract(plan_text)
                if planning_contract.source_snapshot is not None:
                    planning_base_ref = planning_contract.source_snapshot.base_ref
            except ValueError:
                pass

        branch_name = str(cmd.payload.get("branch") or f"samuel/issue-{issue_number}")
        resume_head_sha = str(cmd.payload.get("resume_head_sha") or "")
        if resume_head_sha and not branch_ready:
            from samuel.core import git as _git

            if not _git.prepare_branch_at_head(
                branch_name,
                resume_head_sha,
                cwd=project,
                transport_auth=self._git_transport_auth,
            ):
                self._bus.publish(
                    WorkflowBlocked(
                        payload={
                            "issue": issue_number,
                            "reason": "healing_candidate_unavailable",
                            "branch": branch_name,
                            "expected_head": resume_head_sha,
                        },
                        correlation_id=correlation_id,
                    )
                )
                return {
                    "success": False,
                    "reason": "healing_candidate_unavailable",
                    "patches_applied": [],
                }
        context = build_full_context(
            issue_number=issue_number,
            issue_title=issue_title,
            issue_body=issue_body,
            plan_text=plan_text,
            project_root=project,
            skeleton_builders=self._skeleton_builders,
            architecture_constraints=self._architecture_constraints,
            exclude_dirs=self._exclude_dirs,
            keyword_extensions=self._keyword_extensions,
        )
        # #239: heal_hint aus HealingSuggested-Trigger durchreichen — gibt
        # dem Implement-LLM Kontext "diese Variante hat zuletzt 0.5 erreicht,
        # versuche jetzt X". Bus-Resilient: kein heal_hint -> normaler Pfad.
        heal_hint = cmd.payload.get("heal_hint") or ""
        if heal_hint:
            context = dict(context or {})
            context["heal_hint"] = "## Heal-Hint (Korrektur-Kontext aus Self-Healing)\n" + str(
                heal_hint
            )
        prompt = _build_implement_prompt(issue_number, issue_title, issue_body, plan_text, context)

        prompt_tokens_est = 0
        if self._enforce_context_quality:
            validation = validate_context(
                issue_title=issue_title,
                issue_body=issue_body,
                plan_text=plan_text,
                context=context,
                prompt=prompt,
            )
            for warn in validation.warnings:
                log.warning("Context-Validator: %s", warn)
            if not validation.ok:
                log.error(
                    "Context-Validator blocked LLM call for issue #%d: %s",
                    issue_number,
                    "; ".join(validation.issues),
                )
                self._bus.publish(
                    WorkflowBlocked(
                        payload={
                            "issue": issue_number,
                            "reason": "context_insufficient",
                            "issues": validation.issues,
                            "prompt_tokens_est": validation.prompt_tokens_est,
                            "breakdown": validation.breakdown,
                        },
                        correlation_id=correlation_id,
                    )
                )
                return None
            log.info(
                "Context-Validator OK for #%d: ~%d tokens, %d warnings",
                issue_number,
                validation.prompt_tokens_est,
                len(validation.warnings),
            )
            prompt_tokens_est = validation.prompt_tokens_est

        def on_token_limit(
            round_num: int,
            total_tokens: int,
            rollback: dict[str, Any],
        ) -> None:
            self._bus.publish(
                TokenLimitHit(
                    payload={
                        "issue": issue_number,
                        "round": round_num,
                        "tokens": total_tokens,
                        "rollback_status": rollback.get("status", "unknown"),
                        "files_restored": rollback.get("files_restored", 0),
                        "files_removed": rollback.get("files_removed", 0),
                    },
                    correlation_id=correlation_id,
                )
            )

        def on_round(round_num: int, patch_count: int, failure_count: int) -> None:
            self._checkpoints[issue_number] = WorkflowCheckpoint(
                issue=issue_number,
                phase="implementing",
                step=f"round_{round_num}",
                state={"round": round_num, "patches": patch_count, "failures": failure_count},
            )
            if self._authority is not None:
                from samuel.core import git as _git

                self._authority.put_checkpoint(
                    WorkflowCheckpointRecord(
                        checkpoint_key=self._authority_key(
                            "checkpoint", correlation_id or str(issue_number), str(issue_number)
                        ),
                        issue_number=issue_number,
                        correlation_id=correlation_id,
                        workflow="implementation",
                        boundary=f"round_{round_num}",
                        repository=self._repository_identity(),
                        branch=branch_name,
                        base_ref=planning_base_ref,
                        head_sha=_git.head_sha(project),
                        workspace_id=str(project.resolve()),
                        evaluation_subject={},
                        resume_eligible=False,
                        payload={
                            "round": round_num,
                            "patches": patch_count,
                            "failures": failure_count,
                            **(
                                {"budget_admission_key": current_budget_admission()}
                                if current_budget_admission()
                                else {}
                            ),
                        },
                    )
                )

        def on_prompt(round_num: int, current_prompt: str) -> None:
            if self._prompt_risk_analyzer is None:
                return
            try:
                self._prompt_risk_analyzer.inspect_text(
                    issue_number=issue_number,
                    source=f"implementation_prompt_round_{round_num}",
                    text=current_prompt,
                    correlation_id=correlation_id,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "Prompt-risk analysis failed for implementation #%d round %d: %s",
                    issue_number,
                    round_num,
                    exc,
                )

        tools_loaded = sorted({type(b).__name__ for b in self._skeleton_builders})
        context_sections = sorted([k for k, v in context.items() if v])
        guards = ["prompt_guards"]
        if self._enforce_context_quality:
            guards.append("context_validator")

        # #319: Self-Mode-Health-Metriken — start-time fuer dauer-tracking
        import time as _time

        _llm_loop_started = _time.time()

        # #270: Externe-Sichtbarkeits-Ebene — Inline-Marker an LLM-erzeugten
        # Bloecken, gated auf das Feature-Flag ``llm_attribution`` (die
        # Audit-Ebene/Trailer bleibt davon unberuehrt). Verbosity aus
        # config/privacy.json. ``run_llm_loop`` setzt das echte Modell pro Runde.
        attribution_cfg = self._build_attribution_cfg(issue_number)

        # #152: Slice-Resolver fuer den SLICE-Request-Loop (gezieltes Nachladen
        # von Zeilen aus grossen Files, skeleton-validiert).
        from samuel.slices.implementation.context_builder import resolve_slice_request

        def _slice_resolver(rel: str, start: int, end: int) -> str | None:
            return resolve_slice_request(
                project,
                rel,
                start,
                end,
                builders=self._skeleton_builders,
            )

        try:
            result = run_llm_loop(
                self._llm,
                prompt,
                project_root=project,
                on_round=on_round,
                on_token_limit=on_token_limit,
                llm_kwargs={
                    "task": "implementation",
                    "tools_loaded": tools_loaded,
                    "context_sections": context_sections,
                    "guards": guards,
                    "prompt_tokens_est": prompt_tokens_est,
                },
                attribution=attribution_cfg,
                slice_resolver=_slice_resolver,
                on_prompt=on_prompt,
            )
        except ProviderUnavailable as exc:
            # run_llm_loop has already rolled back its workspace transaction.
            provider_error: dict[str, Any] = {
                "code": exc.code,
                "retryable": exc.retryable,
            }
            if exc.status is not None:
                provider_error["status"] = exc.status
            result = {
                "success": False,
                "reason": "provider_unavailable",
                "round": 0,
                "patches_applied": [],
                "failures": [],
                "input_tokens": 0,
                "output_tokens": 0,
                "rounds_stats": [],
                "model": "",
                "provider_error": provider_error,
            }
        except WorkspaceRollbackError as exc:
            result = {
                "success": False,
                "reason": "workspace_rollback_failed",
                "trigger_reason": exc.trigger_reason,
                "round": 0,
                "patches_applied": [],
                "patches_rolled_back": 0,
                "failures": ["workspace_rollback_failed"],
                "input_tokens": 0,
                "output_tokens": 0,
                "rounds_stats": [],
                "model": "",
                "rollback": exc.rollback,
            }
        if not result.get("success"):
            # Round checkpoints carry no persisted prompt/candidate state and
            # therefore cannot authorize a resume after an atomic rollback.
            self._checkpoints.pop(issue_number, None)
            if self._authority is not None:
                try:
                    self._authority.clear_checkpoint(
                        self._authority_key(
                            "checkpoint", correlation_id or str(issue_number), str(issue_number)
                        )
                    )
                except StateStoreError:
                    result["reason"] = "authority_checkpoint_clear_failed"
                    self._bus.publish(
                        WorkflowBlocked(
                            payload={
                                "issue": issue_number,
                                "reason": "authority_checkpoint_clear_failed",
                                "branch": branch_name,
                            },
                            correlation_id=correlation_id,
                        )
                    )
                    return result

        # #319: Append per-run metrics to data/logs/self_mode_metrics.jsonl
        # — persistent fuer Self-Mode-Health-Tab + Pattern-Analyse.
        try:
            self._append_self_mode_metrics(
                issue_number=issue_number,
                duration_seconds=_time.time() - _llm_loop_started,
                result=result,
            )
        except Exception:  # noqa: BLE001
            log.exception("Self-mode metrics write failed (non-fatal)")

        # #319: Bei no_progress-Abbruch publish WorkflowBlocked + frueher return
        if result["reason"] == "no_progress":
            blocked_payload = {
                "issue": issue_number,
                "reason": "self_mode_no_progress",
                "round": result["round"],
                "rounds_stats": result.get("rounds_stats", []),
                "rollback": result.get("rollback", {}),
                "patches_rolled_back": result.get("patches_rolled_back", 0),
            }
            if "diagnostic" in result:
                blocked_payload["diagnostic"] = result["diagnostic"]
            self._bus.publish(
                WorkflowBlocked(
                    payload=blocked_payload,
                    correlation_id=correlation_id,
                )
            )
            return result

        if result["reason"] == "token_limit":
            self._bus.publish(
                WorkflowBlocked(
                    payload={
                        "issue": issue_number,
                        "reason": "token_limit",
                        "round": result["round"],
                        "rollback": result.get("rollback", {}),
                        "patches_rolled_back": result.get("patches_rolled_back", 0),
                    },
                    correlation_id=correlation_id,
                )
            )
            return result

        if result["success"]:
            from samuel.core import git as _git

            patched_files = sorted({p["file"] for p in result["patches_applied"] if p.get("file")})

            if (
                not branch_ready
                and not resume_head_sha
                and not _git.create_branch(
                    branch_name,
                    "main",
                    cwd=project,
                    transport_auth=self._git_transport_auth,
                )
            ):
                current = _git.current_branch(cwd=project)
                log.error(
                    "Issue #%d: create_branch(%s) failed; worktree on %r — aborting",
                    issue_number,
                    branch_name,
                    current,
                )
                self._bus.publish(
                    WorkflowBlocked(
                        payload={
                            "issue": issue_number,
                            "reason": "branch_setup_failed",
                            "branch": branch_name,
                            "current_branch": current,
                        },
                        correlation_id=correlation_id,
                    )
                )
                return result

            if patched_files:
                staged = _git.stage_files(patched_files, cwd=project)
            else:
                staged = _git.stage_files([], cwd=project)
            if not staged:
                return self._block_git_finalization(
                    issue_number,
                    branch_name,
                    "git_stage_failed",
                    result,
                    correlation_id,
                )
            expected_parent = _git.head_sha(cwd=project)
            expected_tree = _git.index_tree(cwd=project)
            if not expected_parent or not expected_tree:
                return self._block_git_finalization(
                    issue_number,
                    branch_name,
                    "git_intent_subject_failed",
                    result,
                    correlation_id,
                )
            # #270: AI-Generated-By IMMER (Audit/Art. 50). Co-Authored-By (von
            # GitHub sichtbar gerendert) nur bei aktiver externer Sichtbarkeit
            # und bekanntem Modell. co_author_email aus config/privacy.json.
            from samuel import __build_info__
            from samuel.core.attribution import commit_trailers

            co_email = "noreply@samuel.local"
            if self._config is not None:
                co_email = str(
                    self._config.get(
                        "privacy.attribution.co_author_email",
                        co_email,
                    )
                )
            trailers = commit_trailers(
                model=result.get("model", ""),
                system_version=__build_info__.product_version,
                build_revision=__build_info__.revision or "",
                build_dirty=bool(__build_info__.dirty),
                external_visible=self._attribution_enabled(),
                co_author_email=co_email,
            )
            commit_message = (
                f"feat: Issue #{issue_number} — LLM-generierte Implementierung\n\n"
                f"Patches: {len(result['patches_applied'])}\n"
                f"Rounds: {result['round']}\n"
                f"{trailers}"
            )
            if (
                not workspace_id
                or self._authority is None
                or not {
                    "policy_version",
                    "policy_digest",
                    "gate_schema_version",
                    "observation_schema_version",
                }.issubset(self._resume_policy_binding)
            ):
                return self._legacy_finalize_candidate(
                    cmd=cmd,
                    issue_number=issue_number,
                    project=project,
                    workspace_id=workspace_id,
                    branch_name=branch_name,
                    expected_parent=expected_parent,
                    expected_tree=expected_tree,
                    commit_message=commit_message,
                    result=result,
                )
            try:
                resume_binding = self._resume_binding(plan_text)
            except ValueError:
                return self._block_git_finalization(
                    issue_number,
                    branch_name,
                    "resume_binding_unavailable",
                    result,
                    correlation_id,
                )
            return self._finalize_candidate(
                cmd=cmd,
                issue_number=issue_number,
                project=project,
                workspace_id=workspace_id,
                branch_name=branch_name,
                base_ref=planning_base_ref,
                expected_parent=expected_parent,
                expected_tree=expected_tree,
                commit_message=commit_message,
                resume_binding=resume_binding,
                result=result,
                resumed=False,
            )
        else:
            blocked_payload = {
                "issue": issue_number,
                "task": "implementation",
                "reason": result["reason"],
                "failures": result["failures"],
            }
            if "diagnostic" in result:
                blocked_payload["diagnostic"] = result["diagnostic"]
            if "rollback" in result:
                blocked_payload["rollback"] = result["rollback"]
                blocked_payload["patches_rolled_back"] = result.get("patches_rolled_back", 0)
            if "trigger_reason" in result:
                blocked_payload["trigger_reason"] = result["trigger_reason"]
            if "provider_error" in result:
                blocked_payload["provider_error"] = result["provider_error"]
            self._bus.publish(
                WorkflowBlocked(
                    payload=blocked_payload,
                    correlation_id=correlation_id,
                )
            )

        return result

    def _legacy_finalize_candidate(
        self,
        *,
        cmd: ImplementCommand,
        issue_number: int,
        project: Path,
        workspace_id: str,
        branch_name: str,
        expected_parent: str,
        expected_tree: str,
        commit_message: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """Compatibility boundary for direct, non-product handler construction.

        Bootstrap always injects the bound resume policy and workspace manager.
        Small slice tests and third-party embeddings may still instantiate the
        handler without those product services; they retain the pre-#633 path.
        """

        from samuel.core import git as _git

        correlation_id = cmd.correlation_id or ""
        commit_intent: tuple[str, int] | None = None
        if self._authority is not None:
            try:
                commit_intent = self._put_intent(
                    operation="commit",
                    issue_number=issue_number,
                    correlation_id=correlation_id,
                    subject_key=f"{branch_name}:{expected_parent}:{expected_tree}",
                    payload={
                        "repository": self._repository_identity(),
                        "branch": branch_name,
                        "workspace_id": workspace_id,
                        "expected_parent": expected_parent,
                        "expected_tree": expected_tree,
                        "recovery_authority": "diagnostic_only",
                    },
                )
            except StateStoreError:
                return self._block_git_finalization(
                    issue_number,
                    branch_name,
                    "authority_intent_write_failed",
                    result,
                    correlation_id,
                )
        committed_head = _git.commit_tree_transaction(
            commit_message,
            expected_parent=expected_parent,
            expected_tree=expected_tree,
            cwd=project,
            signing_required=self._signing_required(),
            signing_key=self._signing_key() or None,
        )
        if not committed_head:
            return self._block_git_finalization(
                issue_number, branch_name, "git_commit_failed", result, correlation_id
            )
        push_intent: tuple[str, int] | None = None
        authority_epoch: int | None = None
        if self._authority is not None:
            try:
                authority_epoch = self._finish_intent(
                    commit_intent,
                    status="applied",
                    postcondition={
                        "commit_created": True,
                        "head_sha": committed_head,
                        "parent_sha": _git.revision_parent(cwd=project),
                        "tree_sha": _git.revision_tree(cwd=project),
                    },
                )
                push_intent = self._put_intent(
                    operation="push",
                    issue_number=issue_number,
                    correlation_id=correlation_id,
                    subject_key=f"{branch_name}:{committed_head}",
                    payload={
                        "repository": self._repository_identity(),
                        "branch": branch_name,
                        "expected_head": committed_head,
                        "recovery_authority": "diagnostic_only",
                    },
                )
            except StateStoreError:
                return self._block_git_finalization(
                    issue_number,
                    branch_name,
                    "authority_intent_write_failed",
                    result,
                    correlation_id,
                )
        if not _git.push(branch_name, cwd=project, transport_auth=self._git_transport_auth):
            return self._block_git_finalization(
                issue_number, branch_name, "git_push_failed", result, correlation_id
            )
        if self._authority is not None:
            remote_head = ""
            if self._scm is not None:
                with suppress(Exception):
                    remote_head = self._scm.resolve_ref(branch_name)
            try:
                authority_epoch = self._finish_intent(
                    push_intent,
                    status=("applied" if remote_head == committed_head else "unresolved"),
                    postcondition={
                        "push_succeeded": True,
                        "expected_head": committed_head,
                        "remote_head": remote_head,
                    },
                )
                authority_epoch = self._authority.clear_checkpoint(
                    self._checkpoint_key(correlation_id, issue_number)
                ).authority_epoch
            except StateStoreError:
                return self._block_git_finalization(
                    issue_number,
                    branch_name,
                    "authority_intent_write_failed",
                    result,
                    correlation_id,
                )
        self._checkpoints.pop(issue_number, None)
        event_payload = {
            "issue": issue_number,
            "patches_applied": len(result.get("patches_applied", [])),
            "rounds": int(result.get("round") or 0),
            "branch": branch_name,
            **({"workspace_id": workspace_id} if workspace_id else {}),
            **self._authority_event_binding(authority_epoch),
            **(
                {"acceptance_approval": cmd.payload["acceptance_approval"]}
                if "acceptance_approval" in cmd.payload
                else {}
            ),
            **(
                {"healing_origin_observation_key": cmd.payload["healing_origin_observation_key"]}
                if "healing_origin_observation_key" in cmd.payload
                else {}
            ),
        }
        self._bus.publish(CodeGenerated(payload=event_payload, correlation_id=correlation_id))
        return result

    def _resume_finalization(
        self,
        cmd: ImplementCommand,
        issue_number: int,
        *,
        project: Path,
        workspace_id: str,
    ) -> dict[str, Any]:
        if self._authority is None or self._scm is None:
            return {"success": False, "resumed": False, "reason": "resume_authority_unavailable"}
        checkpoint_key = str(cmd.payload.get("checkpoint_key") or "")
        checkpoint = self._authority.get_checkpoint(checkpoint_key)
        if (
            checkpoint is None
            or not checkpoint.resume_eligible
            or checkpoint.issue_number != issue_number
            or checkpoint.correlation_id != (cmd.correlation_id or "")
            or checkpoint.workspace_id != workspace_id
            or checkpoint.repository != self._repository_identity()
            or checkpoint.branch != str(cmd.payload.get("branch") or "")
        ):
            return self._quarantine_resume(
                checkpoint,
                workspace_id=workspace_id,
                reason="resume_checkpoint_binding_mismatch",
            )
        authority_status = self._authority.authority_status()
        if authority_status.get("reconcile_required"):
            return {
                "success": False,
                "resumed": False,
                "pending": True,
                "reason": "authority_reconcile_required",
            }
        try:
            self._claim_resume_lease(workspace_id, takeover=True)
        except StateStoreError as exc:
            return {
                "success": False,
                "resumed": False,
                "pending": exc.code == "resume_lease_live",
                "reason": exc.code,
            }

        plan_text = ""
        try:
            comments = self._scm.get_comments(issue_number)
            active = latest_active_plan(comments)
            if active is None:
                raise ValueError("planning_contract_missing")
            plan_text = active[0].body
            current_binding = self._resume_binding(plan_text)
        except (OSError, ValueError):
            return self._quarantine_resume(
                checkpoint,
                workspace_id=workspace_id,
                reason="resume_contract_unavailable",
            )
        expected_binding = checkpoint.evaluation_subject
        if any(
            expected_binding.get(key) != current_binding.get(key)
            for key in (
                "contract_hash",
                "policy_version",
                "policy_digest",
                "gate_schema_version",
                "observation_schema_version",
            )
        ):
            return self._quarantine_resume(
                checkpoint,
                workspace_id=workspace_id,
                reason="resume_policy_or_contract_changed",
            )
        payload = checkpoint.payload
        try:
            base_sha = self._scm.resolve_ref(checkpoint.base_ref)
        except Exception:  # noqa: BLE001 - unavailable SCM can be retried without mutation
            return {
                "success": False,
                "resumed": False,
                "pending": True,
                "reason": "resume_scm_unavailable",
            }
        if base_sha != str(payload.get("base_sha") or ""):
            return self._quarantine_resume(
                checkpoint,
                workspace_id=workspace_id,
                reason="resume_base_changed",
            )
        signing_key = self._signing_key()
        signing_digest = hashlib.sha256(signing_key.encode("utf-8")).hexdigest()
        if (
            bool(payload.get("signing_required")) != self._signing_required()
            or str(payload.get("signing_key_digest") or "") != signing_digest
        ):
            return self._quarantine_resume(
                checkpoint,
                workspace_id=workspace_id,
                reason="resume_signing_policy_changed",
            )
        git_reason = self._resume_git_state_reason(project, payload)
        if git_reason:
            return self._quarantine_resume(
                checkpoint,
                workspace_id=workspace_id,
                reason=git_reason,
            )
        result = {
            "success": True,
            "reason": "resume_finalization",
            "patches_applied": [
                {"file": path} for path in payload.get("patched_files", []) if isinstance(path, str)
            ],
            "round": int(payload.get("rounds") or 0),
            "model": str(payload.get("model") or ""),
            "failures": [],
        }
        return self._finalize_candidate(
            cmd=cmd,
            issue_number=issue_number,
            project=project,
            workspace_id=workspace_id,
            branch_name=checkpoint.branch,
            base_ref=checkpoint.base_ref,
            expected_parent=str(payload.get("expected_parent") or ""),
            expected_tree=str(payload.get("expected_tree") or ""),
            commit_message=str(payload.get("commit_message") or ""),
            resume_binding=current_binding,
            result=result,
            resumed=True,
            persisted_payload=payload,
        )

    @staticmethod
    def _resume_git_state_reason(project: Path, payload: dict[str, Any]) -> str:
        from samuel.core import git as _git

        expected_parent = str(payload.get("expected_parent") or "")
        expected_tree = str(payload.get("expected_tree") or "")
        current_head = _git.head_sha(project)
        if _git.index_tree(project) != expected_tree:
            return "resume_index_changed"
        if current_head == expected_parent:
            status = _git.status_porcelain(project)
            if status is None or not _git.staged_candidate_clean(project):
                return "resume_worktree_changed"
            digest = hashlib.sha256(status.encode("utf-8")).hexdigest()
            if digest != str(payload.get("staged_status_digest") or ""):
                return "resume_worktree_changed"
            return ""
        if (
            _git.revision_parent(cwd=project) != expected_parent
            or _git.revision_tree(cwd=project) != expected_tree
        ):
            return "resume_head_changed"
        return "" if _git.worktree_clean(project) else "resume_worktree_changed"

    def _signing_required(self) -> bool:
        return bool(
            self._config.get("agent.git.signing_required", False)
            if self._config is not None
            else False
        )

    def _signing_key(self) -> str:
        raw = self._config.get("agent.git.signing_key", "") if self._config is not None else ""
        return str(raw).strip() if raw is not None else ""

    def _finalize_candidate(
        self,
        *,
        cmd: ImplementCommand,
        issue_number: int,
        project: Path,
        workspace_id: str,
        branch_name: str,
        base_ref: str,
        expected_parent: str,
        expected_tree: str,
        commit_message: str,
        resume_binding: dict[str, Any],
        result: dict[str, Any],
        resumed: bool,
        persisted_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from samuel.core import git as _git

        correlation_id = cmd.correlation_id or ""
        if self._authority is None or self._scm is None or not workspace_id:
            return self._block_git_finalization(
                issue_number,
                branch_name,
                "resume_authority_unavailable",
                result,
                correlation_id,
            )
        try:
            resolved_base_sha = self._scm.resolve_ref(base_ref)
        except Exception:  # noqa: BLE001
            log.warning("Resume deferred because the base ref could not be resolved")
            result.update(
                success=False, resumed=False, pending=True, reason="resume_scm_unavailable"
            )
            return result
        source_value = resume_binding.get("source_snapshot")
        source_snapshot = (
            PlanningSourceSnapshot.from_dict(source_value)
            if isinstance(source_value, dict)
            else None
        )
        if source_snapshot is not None:
            try:
                issue = self._scm.get_issue(issue_number)
                current_issue_digest = issue_revision_digest(
                    number=issue.number,
                    title=issue.title,
                    body=issue.body,
                )
            except Exception:  # noqa: BLE001 - finalization must fail closed
                log.warning(
                    "Planning source could not be revalidated before finalizing issue #%d",
                    issue_number,
                )
                return self._block_git_finalization(
                    issue_number,
                    branch_name,
                    "planning_source_unavailable",
                    result,
                    correlation_id,
                )
            if (
                source_snapshot.repository != self._repository_identity()
                or source_snapshot.base_ref != base_ref
                or source_snapshot.base_sha != resolved_base_sha
                or source_snapshot.issue_digest != current_issue_digest
            ):
                return self._block_git_finalization(
                    issue_number,
                    branch_name,
                    "planning_source_changed",
                    result,
                    correlation_id,
                )
        if persisted_payload is not None:
            base_sha = str(persisted_payload.get("base_sha") or "")
            if resolved_base_sha != base_sha:
                return self._quarantine_resume(
                    self._authority.get_checkpoint(
                        self._checkpoint_key(correlation_id, issue_number)
                    ),
                    workspace_id=workspace_id,
                    reason="resume_base_changed",
                    result=result,
                )
        else:
            base_sha = resolved_base_sha
            supplied_subject = cmd.payload.get("evaluation_subject")
            if isinstance(supplied_subject, dict):
                expected_subject = {
                    "repository": self._repository_identity(),
                    "base_sha": base_sha,
                    "contract_hash": str(resume_binding.get("contract_hash") or ""),
                    "policy_version": str(resume_binding.get("policy_version") or ""),
                    "policy_digest": str(resume_binding.get("policy_digest") or ""),
                }
                if any(
                    str(supplied_subject.get(key) or "") != value
                    for key, value in expected_subject.items()
                ):
                    return self._quarantine_resume(
                        self._authority.get_checkpoint(
                            self._checkpoint_key(correlation_id, issue_number)
                        ),
                        workspace_id=workspace_id,
                        reason="healing_evaluation_subject_changed",
                        result=result,
                        issue_number=issue_number,
                        correlation_id=correlation_id,
                    )
        current_status = _git.status_porcelain(project)
        if current_status is None:
            result.update(success=False, resumed=False, pending=True, reason="git_status_failed")
            return result
        status_digest = hashlib.sha256(current_status.encode("utf-8")).hexdigest()
        if persisted_payload is None and not _git.staged_candidate_clean(project):
            return self._quarantine_resume(
                self._authority.get_checkpoint(self._checkpoint_key(correlation_id, issue_number)),
                workspace_id=workspace_id,
                reason="resume_worktree_changed",
                result=result,
                issue_number=issue_number,
                correlation_id=correlation_id,
            )
        event_payload = dict(
            (persisted_payload or {}).get("event_payload")
            or {
                "issue": issue_number,
                "patches_applied": len(result.get("patches_applied", [])),
                "rounds": int(result.get("round") or 0),
                "branch": branch_name,
                "workspace_id": workspace_id,
                **(
                    {"acceptance_approval": cmd.payload["acceptance_approval"]}
                    if "acceptance_approval" in cmd.payload
                    else {}
                ),
                **(
                    {
                        "healing_origin_observation_key": cmd.payload[
                            "healing_origin_observation_key"
                        ]
                    }
                    if "healing_origin_observation_key" in cmd.payload
                    else {}
                ),
            }
        )
        checkpoint_payload = {
            **dict(persisted_payload or {}),
            "base_sha": base_sha,
            "expected_parent": expected_parent,
            "expected_tree": expected_tree,
            "staged_status_digest": str(
                (persisted_payload or {}).get("staged_status_digest") or status_digest
            ),
            "commit_message": commit_message,
            "patched_files": sorted(
                {
                    str(item.get("file"))
                    for item in result.get("patches_applied", [])
                    if isinstance(item, dict) and item.get("file")
                }
            ),
            "rounds": int(result.get("round") or 0),
            "model": str(result.get("model") or ""),
            "signing_required": self._signing_required(),
            "signing_key_digest": hashlib.sha256(self._signing_key().encode("utf-8")).hexdigest(),
            "event_payload": event_payload,
            "resume_status": "pending",
        }
        try:
            self._claim_resume_lease(workspace_id, takeover=resumed)
            authority_epoch = self._persist_finalization_checkpoint(
                issue_number=issue_number,
                correlation_id=correlation_id,
                boundary="commit_pending",
                branch=branch_name,
                base_ref=base_ref,
                head_sha=expected_parent,
                workspace_id=workspace_id,
                evaluation_subject=resume_binding,
                payload=checkpoint_payload,
            )
        except StateStoreError as exc:
            result.update(success=False, resumed=False, pending=True, reason=exc.code)
            return result

        commit_subject = f"{branch_name}:{expected_parent}:{expected_tree}"
        commit_intent = self._put_intent(
            operation="commit",
            issue_number=issue_number,
            correlation_id=correlation_id,
            subject_key=commit_subject,
            payload={
                "repository": self._repository_identity(),
                "branch": branch_name,
                "workspace_id": workspace_id,
                "expected_parent": expected_parent,
                "expected_tree": expected_tree,
                "recovery_authority": "content_identity",
            },
        )
        assert commit_intent is not None
        current_head = _git.head_sha(project)
        current_index = _git.index_tree(project)
        if current_index != expected_tree:
            return self._quarantine_resume(
                self._authority.get_checkpoint(self._checkpoint_key(correlation_id, issue_number)),
                workspace_id=workspace_id,
                reason="resume_index_changed",
                result=result,
            )
        if current_head == expected_parent:
            if not _git.staged_candidate_clean(project) or status_digest != str(
                checkpoint_payload["staged_status_digest"]
            ):
                return self._quarantine_resume(
                    self._authority.get_checkpoint(
                        self._checkpoint_key(correlation_id, issue_number)
                    ),
                    workspace_id=workspace_id,
                    reason="resume_worktree_changed",
                    result=result,
                )
            committed_head = _git.commit_tree_transaction(
                commit_message,
                expected_parent=expected_parent,
                expected_tree=expected_tree,
                cwd=project,
                signing_required=self._signing_required(),
                signing_key=self._signing_key() or None,
            )
            if not committed_head:
                result.update(
                    success=False,
                    resumed=False,
                    pending=True,
                    reason="git_commit_failed",
                )
                return result
        else:
            committed_head = current_head
            if not _git.worktree_clean(project):
                return self._quarantine_resume(
                    self._authority.get_checkpoint(
                        self._checkpoint_key(correlation_id, issue_number)
                    ),
                    workspace_id=workspace_id,
                    reason="resume_worktree_changed",
                    result=result,
                )
        committed_parent = _git.revision_parent(cwd=project)
        committed_tree = _git.revision_tree(cwd=project)
        if committed_parent != expected_parent or committed_tree != expected_tree:
            return self._quarantine_resume(
                self._authority.get_checkpoint(self._checkpoint_key(correlation_id, issue_number)),
                workspace_id=workspace_id,
                reason="resume_head_changed",
                result=result,
            )
        existing_commit = self._authority.get_intent(commit_intent[0])
        if existing_commit is not None and existing_commit.status == "pending":
            authority_epoch = self._finish_intent(
                commit_intent,
                status="applied",
                postcondition={
                    "commit_created": True,
                    "head_sha": committed_head,
                    "parent_sha": committed_parent,
                    "tree_sha": committed_tree,
                },
            )
        elif existing_commit is None or existing_commit.status != "applied":
            return self._quarantine_resume(
                self._authority.get_checkpoint(self._checkpoint_key(correlation_id, issue_number)),
                workspace_id=workspace_id,
                reason="resume_commit_intent_mismatch",
                result=result,
            )

        checkpoint_payload["committed_head"] = committed_head
        authority_epoch = self._persist_finalization_checkpoint(
            issue_number=issue_number,
            correlation_id=correlation_id,
            boundary="push_pending",
            branch=branch_name,
            base_ref=base_ref,
            head_sha=committed_head,
            workspace_id=workspace_id,
            evaluation_subject=resume_binding,
            payload=checkpoint_payload,
        )
        push_intent = self._put_intent(
            operation="push",
            issue_number=issue_number,
            correlation_id=correlation_id,
            subject_key=f"{branch_name}:{committed_head}",
            payload={
                "repository": self._repository_identity(),
                "branch": branch_name,
                "expected_head": committed_head,
                "recovery_authority": "remote_revision",
            },
        )
        assert push_intent is not None
        try:
            remote_head = self._scm.resolve_ref_optional(branch_name)
        except Exception:  # noqa: BLE001
            log.warning("Resume deferred because the remote candidate ref is unavailable")
            result.update(
                success=False, resumed=False, pending=True, reason="resume_scm_unavailable"
            )
            return result
        if remote_head not in {None, committed_head}:
            return self._quarantine_resume(
                self._authority.get_checkpoint(self._checkpoint_key(correlation_id, issue_number)),
                workspace_id=workspace_id,
                reason="resume_remote_changed",
                result=result,
            )
        if remote_head is None and not _git.push(
            branch_name, cwd=project, transport_auth=self._git_transport_auth
        ):
            result.update(success=False, resumed=False, pending=True, reason="git_push_failed")
            return result
        try:
            confirmed_remote = self._scm.resolve_ref(branch_name)
        except Exception:  # noqa: BLE001
            log.warning("Resume deferred because the pushed revision could not be confirmed")
            result.update(
                success=False, resumed=False, pending=True, reason="resume_scm_unavailable"
            )
            return result
        if confirmed_remote != committed_head:
            return self._quarantine_resume(
                self._authority.get_checkpoint(self._checkpoint_key(correlation_id, issue_number)),
                workspace_id=workspace_id,
                reason="resume_remote_changed",
                result=result,
            )
        existing_push = self._authority.get_intent(push_intent[0])
        if existing_push is not None and existing_push.status == "pending":
            authority_epoch = self._finish_intent(
                push_intent,
                status="applied",
                postcondition={
                    "push_succeeded": True,
                    "expected_head": committed_head,
                    "remote_head": confirmed_remote,
                },
            )
        elif existing_push is None or existing_push.status != "applied":
            return self._quarantine_resume(
                self._authority.get_checkpoint(self._checkpoint_key(correlation_id, issue_number)),
                workspace_id=workspace_id,
                reason="resume_push_intent_mismatch",
                result=result,
            )

        subject = EvaluationSubject(
            repository=self._repository_identity(),
            base_sha=base_sha,
            head_sha=committed_head,
            contract_hash=str(resume_binding["contract_hash"]),
            policy_version=str(resume_binding["policy_version"]),
            policy_digest=str(resume_binding["policy_digest"]),
        )
        event_payload["evaluation_subject"] = subject.as_dict()
        event_payload.update(self._authority_event_binding(authority_epoch))
        checkpoint_payload["event_payload"] = event_payload
        self._persist_finalization_checkpoint(
            issue_number=issue_number,
            correlation_id=correlation_id,
            boundary="gates_pending",
            branch=branch_name,
            base_ref=base_ref,
            head_sha=committed_head,
            workspace_id=workspace_id,
            evaluation_subject=resume_binding,
            payload=checkpoint_payload,
        )
        self._checkpoints.pop(issue_number, None)
        self._bus.publish(CodeGenerated(payload=event_payload, correlation_id=correlation_id))
        result.update(
            success=True,
            resumed=resumed,
            pending=False,
            boundary="gates_pending",
            authority_epoch=authority_epoch,
        )
        return result

    def _quarantine_resume(
        self,
        checkpoint: WorkflowCheckpointRecord | None,
        *,
        workspace_id: str,
        reason: str,
        result: dict[str, Any] | None = None,
        issue_number: int = 0,
        correlation_id: str = "",
    ) -> dict[str, Any]:
        if self._workspace_manager is not None:
            try:
                self._workspace_manager.quarantine(workspace_id, reason=reason)
            except WorkspaceError:
                log.exception("Failed to quarantine a non-resumable workspace")
        if checkpoint is not None and self._authority is not None:
            try:
                self._authority.put_checkpoint(
                    WorkflowCheckpointRecord(
                        **{
                            **checkpoint.__dict__,
                            "boundary": "blocked",
                            "resume_eligible": False,
                            "payload": {
                                **checkpoint.payload,
                                "resume_status": "blocked",
                                "resume_reason": reason,
                            },
                        }
                    )
                )
            except StateStoreError:
                log.exception("Failed to persist blocked resume checkpoint")
        payload = dict(result or {})
        payload.update(success=False, resumed=False, pending=False, reason=reason)
        self._bus.publish(
            WorkflowBlocked(
                payload={
                    "issue": checkpoint.issue_number if checkpoint is not None else issue_number,
                    "reason": reason,
                    "workspace_id": workspace_id,
                },
                correlation_id=(
                    checkpoint.correlation_id if checkpoint is not None else correlation_id
                ),
            )
        )
        return payload

    def _block_git_finalization(
        self,
        issue_number: int,
        branch: str,
        reason: str,
        result: dict[str, Any],
        correlation_id: str,
    ) -> dict[str, Any]:
        """Stop before CodeGenerated when the candidate was not durably pushed."""

        result["success"] = False
        result["reason"] = reason
        self._bus.publish(
            WorkflowBlocked(
                payload={"issue": issue_number, "reason": reason, "branch": branch},
                correlation_id=correlation_id,
            )
        )
        return result
