from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import Command, HealthCheckCommand
from samuel.core.events import StartupBlocked
from samuel.core.health_projection import record_projection, snapshot
from samuel.core.ports import (
    IConfig,
    ILLMProvider,
    IRunProjectionStore,
    IStateDiagnostics,
    IVersionControl,
)
from samuel.core.state import StateStoreError

log = logging.getLogger(__name__)

_GIT_GUIDANCE = "Git in der S.A.M.U.E.L.-Runtime installieren und den Health-Check wiederholen."


def _git_runtime_status() -> dict[str, Any]:
    executable = shutil.which("git")
    if executable is None:
        return {
            "passed": False,
            "status": "executable_missing",
            "required_executable": "git",
            "guidance": _GIT_GUIDANCE,
        }
    try:
        completed = subprocess.run(  # noqa: S603 - resolved executable, fixed argument
            [executable, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {
            "passed": False,
            "status": "probe_failed",
            "required_executable": "git",
            "guidance": _GIT_GUIDANCE,
        }
    output = completed.stdout.strip()
    match = re.fullmatch(r"git version (\S+)", output)
    if completed.returncode != 0 or match is None:
        return {
            "passed": False,
            "status": "probe_failed",
            "required_executable": "git",
            "guidance": _GIT_GUIDANCE,
        }
    return {
        "passed": True,
        "status": "ready",
        "version": match.group(1),
    }


class HealthHandler:
    def __init__(
        self,
        bus: Bus,
        scm: IVersionControl | None = None,
        llm: ILLMProvider | None = None,
        config: IConfig | None = None,
        state: IStateDiagnostics | None = None,
        resume_status: Callable[[], dict[str, Any]] | None = None,
        execution_provider_status: dict[str, Any] | None = None,
        projection_store: IRunProjectionStore | None = None,
    ) -> None:
        self._bus = bus
        self._scm = scm
        self._llm = llm
        self._config = config
        self._state = state
        self._resume_status = resume_status
        self._execution_provider_status = execution_provider_status
        self._projection_store = projection_store

    def handle(self, cmd: Command) -> Any:
        assert isinstance(cmd, HealthCheckCommand)
        correlation_id = cmd.correlation_id or ""

        checks: dict[str, dict[str, Any]] = {}

        checks["python"] = {
            "passed": True,
            "version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        }
        checks["git"] = _git_runtime_status()

        checks["config"] = {"passed": self._config is not None}
        checks["execution_provider"] = dict(
            self._execution_provider_status
            or {
                "passed": True,
                "configured": False,
                "enabled": False,
                "required_qualified": False,
                "status": "not_configured",
            }
        )

        checks["state"] = {"passed": self._state is not None}
        instance_uuid = "unavailable"
        if self._state is not None:
            try:
                state_status = self._state.status().as_dict()
                instance_uuid = str(state_status.get("authority", {}).get("instance", ""))
                checks["state"].update(state_status)
                authority = state_status.get("authority", {})
                reconcile_required = bool(authority.get("reconcile_required", False))
                checks["authority"] = {
                    "passed": not reconcile_required,
                    "epoch": authority.get("epoch", 0),
                    "witness_epoch": authority.get("witness_epoch", -1),
                    "reconcile_required": reconcile_required,
                    "reconcile_reason": authority.get("reconcile_reason"),
                    "active_restore_operation": authority.get("active_restore_operation"),
                    "restore_scan_status": authority.get("restore_scan_status"),
                    "restore_sentinel_present": bool(
                        authority.get("restore_sentinel_present", False)
                    ),
                    "retention_emergency_stop": bool(
                        authority.get("retention_emergency_stop", True)
                    ),
                    "retention_category_states": list(
                        authority.get("retention_category_states", [])
                    ),
                    "retention_last_execution": authority.get("retention_last_execution"),
                    "retention_future_enforcement_blocked": bool(
                        authority.get("retention_emergency_stop", True) or reconcile_required
                    ),
                    "resume_enabled": authority.get("resume_enabled", False),
                }
                if self._resume_status is not None:
                    resume = self._resume_status()
                    checks["authority"].update(
                        {
                            "resume_enabled": bool(resume.get("enabled")),
                            "resume_pending": int(resume.get("pending", 0)),
                            "resume_blocked": int(resume.get("blocked", 0)),
                            "resume_last_outcome": dict(resume.get("last_outcome", {})),
                        }
                    )
            except StateStoreError as exc:
                checks["state"] = {
                    "passed": False,
                    "error": {"code": exc.code, "message": exc.safe_message},
                }
                checks["authority"] = {
                    "passed": False,
                    "reconcile_required": True,
                    "reconcile_reason": exc.code,
                    "resume_enabled": False,
                }
        else:
            checks["authority"] = {
                "passed": False,
                "reconcile_required": True,
                "reconcile_reason": "state_unavailable",
                "resume_enabled": False,
            }

        checks["scm"] = {"passed": self._scm is not None}
        if self._scm:
            try:
                self._scm.list_issues(labels=[])
                checks["scm"]["reachable"] = True
            except Exception as exc:
                checks["scm"]["passed"] = False
                checks["scm"]["reachable"] = False
                checks["scm"]["error"] = str(exc)
                log.warning("SCM health check failed: %s", exc)

        if self._llm is None:
            checks["llm"] = {
                "passed": False,
                "status": "adapter_unavailable",
                "guidance": "LLM-Providerkonfiguration prüfen und Samuel neu starten.",
            }
        else:
            readiness_resolver = getattr(self._llm, "readiness_status_resolver", None)
            try:
                readiness = (
                    readiness_resolver()
                    if callable(readiness_resolver)
                    else getattr(self._llm, "readiness_status", None)
                )
            except Exception:
                # Provider/config exceptions can carry credential-adjacent
                # transport details.  Health exposes only the bounded status
                # below and deliberately omits the raw exception from logs.
                log.error("LLM readiness evaluation failed")
                readiness = {
                    "passed": False,
                    "status": "readiness_evaluation_failed",
                    "guidance": (
                        "LLM-Konfiguration und Modellkatalog prüfen und Health wiederholen."
                    ),
                    "live_probe": "not_performed",
                }
            checks["llm"] = (
                dict(readiness)
                if isinstance(readiness, dict)
                else {
                    "passed": True,
                    "status": "adapter_present_readiness_unknown",
                    "live_probe": "not_performed",
                }
            )

        # An active dashboard self-check supplies only a bounded, already
        # redacted probe summary. The normal Health command deliberately
        # omits it, so ordinary CLI/Health calls cannot claim a provider live
        # probe merely from static configuration evidence.
        probe = cmd.payload.get("provider_probe") if isinstance(cmd.payload, dict) else None
        if isinstance(probe, dict) and probe.get("schema") == "samuel-provider-probe.v1":
            raw_routes = probe.get("routes")
            routes = raw_routes if isinstance(raw_routes, list) else []
            route_names = sorted(
                {
                    str(row.get("task", ""))
                    for row in routes
                    if isinstance(row, dict) and str(row.get("task", ""))
                }
            )
            failed_routes = sorted(
                {
                    str(row.get("task", ""))
                    for row in routes
                    if isinstance(row, dict)
                    and str(row.get("task", ""))
                    and not bool(row.get("passed"))
                }
            )
            probe_passed = bool(probe.get("performed")) and bool(routes) and not failed_routes
            checks["llm"] = {
                **checks["llm"],
                "live_probe": "performed",
                "probed_routes": route_names,
                "failed_live_probe_routes": failed_routes,
            }
            if not probe_passed:
                checks["llm"] = {
                    **checks["llm"],
                    "passed": False,
                    "status": "live_probe_failed",
                }

        all_passed = all(c["passed"] for c in checks.values())
        critical_passed = (
            checks["config"]["passed"]
            and checks["state"]["passed"]
            and checks["authority"]["passed"]
        )

        if not critical_passed:
            self._bus.publish(
                StartupBlocked(
                    payload={"reason": "critical health checks failed", "checks": checks},
                    correlation_id=correlation_id,
                )
            )

        technical_status = "passed" if all_passed else "failed"
        readiness_status = "ready"
        readiness_reasons: list[str] = []
        if (
            not critical_passed
            or not checks["scm"].get("passed")
            or not checks["llm"].get("passed")
        ):
            readiness_status = "blocked"
            readiness_reasons.append("required technical prerequisite failed")
        elif checks["llm"].get("live_probe") != "performed":
            readiness_status = "unknown"
            readiness_reasons.append("external LLM availability was not probed")
        technical = {
            "status": technical_status,
            "scope": "process_config_state_and_bounded_connectivity",
            "external_provider_qualification": False,
            "checks": {name: bool(value.get("passed")) for name, value in checks.items()},
        }
        readiness = {
            "status": readiness_status,
            "purpose": "workflow_execution",
            "reasons": readiness_reasons,
        }
        if self._projection_store is not None:
            try:
                record_projection(
                    self._projection_store,
                    kind="technical_health",
                    status=technical_status,
                    instance_uuid=instance_uuid,
                    summary=technical,
                )
                # A passive Health run has no new provider fact. It may
                # report ``unknown`` in its own response, but must not
                # overwrite a current active provider-probe result.
                existing_readiness = snapshot(self._projection_store, instance_uuid=instance_uuid)[
                    "operational_readiness"
                ]
                preserve_active_probe = (
                    readiness_status == "unknown"
                    and existing_readiness.get("current") is True
                    and existing_readiness.get("status") in {"ready", "blocked"}
                )
                if not preserve_active_probe:
                    record_projection(
                        self._projection_store,
                        kind="operational_readiness",
                        status=readiness_status,
                        instance_uuid=instance_uuid,
                        summary=readiness,
                    )
            except Exception as exc:  # noqa: BLE001 - projection is explicitly non-blocking
                code = exc.code if isinstance(exc, StateStoreError) else type(exc).__name__
                log.warning("Health projection unavailable: %s", code)
        projected = snapshot(self._projection_store, instance_uuid=instance_uuid)
        return {
            "healthy": all_passed,
            "critical": critical_passed,
            "checks": checks,
            "technical_health": technical,
            "operational_readiness": readiness,
            "qualification": projected["qualification"],
        }
