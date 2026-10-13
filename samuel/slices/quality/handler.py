from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import Command, RunQualityCommand
from samuel.core.events import QualityFailed, QualityPassed
from samuel.core.ports import IQualityCheck

log = logging.getLogger(__name__)


class QualityHandler:
    def __init__(
        self,
        bus: Bus,
        checks: list[IQualityCheck] | None = None,
        project_root: Path | None = None,
    ) -> None:
        self._bus = bus
        self._checks = checks or []
        self._root = project_root or Path(".")

    def handle(self, cmd: Command) -> Any:
        assert isinstance(cmd, RunQualityCommand)
        correlation_id = cmd.correlation_id or ""

        files: list[str] = cmd.payload.get("files", [])
        issue_number = cmd.payload.get("issue", 0)

        # #274: Workflow-Felder aus Upstream-Event durchreichen, sonst geht
        # `branch` zwischen CodeGenerated und CreatePR verloren — Gate 1
        # (BranchGuard) flaggt dann fälschlich `Branch ist main/master`.
        carry_keys = ("branch", "base", "patches_applied", "rounds")
        carried = {k: cmd.payload[k] for k in carry_keys if k in cmd.payload}

        results: list[dict[str, Any]] = []
        all_passed = True
        applied_checks = 0

        for f in files:
            path = self._root / f
            if not path.exists():
                results.append(
                    {"file": f, "passed": False, "status": "failed", "reason": "not found"}
                )
                all_passed = False
                continue

            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                results.append(
                    {
                        "file": f,
                        "passed": False,
                        "status": "failed",
                        "reason": f"file_read_failed:{type(exc).__name__}",
                    }
                )
                all_passed = False
                continue
            matching_checks = [
                check
                for check in self._checks
                if "*" in check.supported_extensions or path.suffix in check.supported_extensions
            ]
            if not matching_checks:
                results.append(
                    {
                        "file": f,
                        "passed": True,
                        "status": "not_applicable",
                        "reason": "no configured check for file extension",
                    }
                )
                continue
            for check in matching_checks:
                check_name = type(check).__name__
                try:
                    raw_result = check.run(path, content, {})
                    if not isinstance(raw_result, dict) or not isinstance(
                        raw_result.get("passed"), bool
                    ):
                        raise ValueError("quality check returned no explicit boolean result")
                    status = str(
                        raw_result.get("status", "passed" if raw_result["passed"] else "failed")
                    )
                    if status not in {"passed", "failed", "not_applicable"}:
                        raise ValueError(f"quality check returned invalid status {status!r}")
                    passed = bool(raw_result["passed"]) and status != "failed"
                    if status == "not_applicable":
                        passed = True
                    else:
                        applied_checks += 1
                    result = {
                        "file": f,
                        "check": check_name,
                        "passed": passed,
                        "status": status,
                    }
                    if raw_result.get("reason"):
                        result["reason"] = str(raw_result["reason"])
                    results.append(result)
                    if not passed:
                        all_passed = False
                except Exception as exc:
                    results.append(
                        {
                            "file": f,
                            "check": check_name,
                            "passed": False,
                            "status": "failed",
                            "error": str(exc),
                        }
                    )
                    all_passed = False

        overall_status = (
            "failed" if not all_passed else ("passed" if applied_checks else "not_applicable")
        )
        summary = {
            "status": overall_status,
            "checks_passed": sum(1 for result in results if result.get("status") == "passed"),
            "checks_failed": sum(1 for result in results if result.get("status") == "failed"),
            "checks_not_applicable": sum(
                1 for result in results if result.get("status") == "not_applicable"
            ),
        }

        if all_passed:
            self._bus.publish(
                QualityPassed(
                    payload={
                        **carried,
                        "issue": issue_number,
                        "files": files,
                        "quality_summary": summary,
                    },
                    correlation_id=correlation_id,
                )
            )
        else:
            self._bus.publish(
                QualityFailed(
                    payload={
                        **carried,
                        "issue": issue_number,
                        "files": files,
                        "quality_summary": summary,
                        "failures": [r for r in results if not r.get("passed")],
                    },
                    correlation_id=correlation_id,
                )
            )

        return {"passed": all_passed, "status": overall_status, "results": results}
