from __future__ import annotations

import logging
from typing import Any

from samuel.core.bus import Bus, HandledCommandFailure, MetricsMiddleware
from samuel.core.commands import (
    HealthCheckCommand,
    ImplementCommand,
    PlanIssueCommand,
    ScanIssuesCommand,
)

log = logging.getLogger(__name__)


def _configuration_result_status(result: dict[str, Any]) -> int:
    return 409 if result.get("code") == "configuration_frozen" else 400


class RestAPI:
    def __init__(
        self,
        bus: Bus,
        auth_middleware: Any | None = None,
        setup_handler: Any | None = None,
        dashboard_handler: Any | None = None,
    ) -> None:
        self._bus = bus
        self._auth = auth_middleware
        self._setup = setup_handler
        self._dashboard = dashboard_handler

    def handle_request(
        self, method: str, path: str, body: dict | None = None, headers: dict | None = None
    ) -> dict[str, Any]:
        if self._auth and not self._auth.authenticate(headers or {}):
            return {"status": 401, "error": "unauthorized"}

        route = f"{method.upper()} {path}"

        if route == "POST /api/v1/setup/labels":
            if self._setup is None:
                return {"status": 503, "error": "setup handler not available"}
            guard = getattr(self._setup, "configuration_mutation_blocked", None)
            blocked = guard() if callable(guard) else None
            if blocked is not None:
                return {"status": 409, "data": blocked}
            result = self._setup.sync_labels()
            return {"status": 200, "data": result}

        if route == "POST /api/v1/settings/flag":
            if self._dashboard is None:
                return {"status": 503, "error": "dashboard handler not available"}
            name = (body or {}).get("name", "")
            enabled = (body or {}).get("enabled")
            if not name or enabled is None:
                return {"status": 400, "error": "name and enabled required"}
            result = self._dashboard.set_feature_flag(str(name), bool(enabled))
            if not result.get("updated"):
                return {"status": _configuration_result_status(result), "data": result}
            return {"status": 200, "data": result}

        # #374: Deployment-Risikoklasse setzen (Compliance-Tab).
        if route == "POST /api/v1/settings/risk-class":
            if self._dashboard is None:
                return {"status": 503, "error": "dashboard handler not available"}
            value = (body or {}).get("risk_class", "")
            if not value:
                return {"status": 400, "error": "risk_class required"}
            result = self._dashboard.set_risk_class(str(value))
            if not result.get("updated"):
                return {"status": _configuration_result_status(result), "data": result}
            return {"status": 200, "data": result}

        # #270: LLM-Code-Kennzeichnung (externe Sichtbarkeit) setzen. Der Handler
        # sperrt bei Deployment-Risikoklasse high_risk (Art. 50 Pflicht).
        if route == "POST /api/v1/settings/attribution":
            if self._dashboard is None:
                return {"status": 503, "error": "dashboard handler not available"}
            if not body or "enabled" not in body:
                return {"status": 400, "error": "enabled required"}
            result = self._dashboard.set_attribution(
                bool(body.get("enabled")),
                body.get("verbosity"),
            )
            if not result.get("updated"):
                # high_risk-Sperre -> 409 Conflict, sonst 400
                status = (
                    409
                    if result.get("locked") or result.get("code") == "configuration_frozen"
                    else 400
                )
                return {"status": status, "data": result}
            return {"status": 200, "data": result}

        if route == "POST /api/v1/settings/extensions/documentation":
            if self._dashboard is None:
                return {"status": 503, "error": "dashboard handler not available"}
            result = self._dashboard.set_extension_configuration(body or {})
            if not result.get("updated"):
                return {"status": _configuration_result_status(result), "data": result}
            return {"status": 200, "data": result}

        # #309: Globale und aufgabenspezifische LLM-Konfiguration.
        if route == "POST /api/v1/settings/llm/global":
            if self._dashboard is None:
                return {"status": 503, "error": "dashboard handler not available"}
            result = self._dashboard.set_llm_global_config(body or {})
            if not result.get("updated"):
                return {"status": _configuration_result_status(result), "data": result}
            return {"status": 200, "data": result}

        if route == "POST /api/v1/settings/llm/task":
            if self._dashboard is None:
                return {"status": 503, "error": "dashboard handler not available"}
            task = str((body or {}).get("task", ""))
            cfg = (body or {}).get("config", {})
            if not task:
                return {"status": 400, "error": "task name required"}
            result = self._dashboard.set_llm_task_config(task, cfg)
            if not result.get("updated"):
                return {"status": _configuration_result_status(result), "data": result}
            return {"status": 200, "data": result}

        # #314: Test-Connection — temporaeren Adapter mit Form-Werten validieren
        if route == "POST /api/v1/dashboard/llm/test-connection":
            if self._dashboard is None:
                return {"status": 503, "error": "dashboard handler not available"}
            provider = str((body or {}).get("provider", ""))
            cfg = (body or {}).get("config", {})
            if not provider:
                return {"status": 400, "error": "provider required"}
            result = self._dashboard.test_connection(provider, cfg)
            return {"status": 200, "data": result}

        if route.startswith("POST /api/v1/issues/") and route.endswith("/plan"):
            issue_id = self._extract_issue_id(path)
            if issue_id is None:
                return {"status": 400, "error": "invalid issue id"}
            result = self._bus.send(PlanIssueCommand(issue_number=issue_id))
            return self._command_response(result, success_status=202)

        if route.startswith("POST /api/v1/issues/") and route.endswith("/implement"):
            issue_id = self._extract_issue_id(path)
            if issue_id is None:
                return {"status": 400, "error": "invalid issue id"}
            result = self._bus.send(ImplementCommand(issue_number=issue_id))
            return self._command_response(result, success_status=202)

        if route == "GET /api/v1/health":
            result = self._bus.send(HealthCheckCommand())
            return self._command_response(result, success_status=200)

        if route == "GET /api/metrics":
            metrics = self._get_metrics()
            return {"status": 200, "data": metrics}

        if route == "POST /api/v1/scan":
            result = self._bus.send(ScanIssuesCommand())
            return self._command_response(result, success_status=202)

        return {"status": 404, "error": f"not found: {route}"}

    @staticmethod
    def _command_response(result: Any, *, success_status: int) -> dict[str, Any]:
        if not isinstance(result, HandledCommandFailure):
            return {"status": success_status, "data": result}

        status, title, detail = {
            "not_found": (404, "Command target not found", "The command target is unavailable."),
            "aborted": (409, "Command rejected", "The workflow rejected the command."),
            "internal": (500, "Command failed", "The command failed before it was accepted."),
        }[result.error_class]
        problem: dict[str, Any] = {
            "type": f"urn:samuel:problem:{result.reason_code.replace('_', '-')}",
            "title": title,
            "status": status,
            "detail": detail,
            "code": result.reason_code,
            "correlation_id": result.correlation_id,
            "command": result.command_name,
        }
        if result.issue is not None:
            problem["issue"] = result.issue
        return {"status": status, "data": problem}

    def _extract_issue_id(self, path: str) -> int | None:
        parts = path.strip("/").split("/")
        for i, part in enumerate(parts):
            if part == "issues" and i + 1 < len(parts):
                try:
                    return int(parts[i + 1])
                except ValueError:
                    return None
        return None

    def _get_metrics(self) -> dict[str, Any]:
        if self._dashboard is not None:
            metrics = self._dashboard.get_metrics()
            return metrics if isinstance(metrics, dict) else {}
        # Fallback for setups without a dashboard handler (tests, minimal API)
        for mw in self._bus._middlewares:
            if isinstance(mw, MetricsMiddleware):
                return {
                    "counts": dict(mw.counts),
                    "errors": dict(mw.errors),
                    "total_ms": {k: round(v, 2) for k, v in mw.total_ms.items()},
                }
        return {"counts": {}, "errors": {}, "total_ms": {}}
