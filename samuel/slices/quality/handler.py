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

        for f in files:
            path = self._root / f
            if not path.exists():
                results.append({"file": f, "passed": False, "reason": "not found"})
                all_passed = False
                continue

            content = path.read_text()
            for check in self._checks:
                exts = check.supported_extensions
                if "*" in exts or path.suffix in exts:
                    try:
                        result = check.run(path, content, {})
                        passed = result.get("passed", True) if isinstance(result, dict) else bool(result)
                        results.append({"file": f, "check": type(check).__name__, "passed": passed})
                        if not passed:
                            all_passed = False
                    except Exception as exc:
                        results.append({"file": f, "check": type(check).__name__, "passed": False, "error": str(exc)})
                        all_passed = False

        if all_passed:
            self._bus.publish(QualityPassed(
                payload={**carried, "issue": issue_number, "files": files},
                correlation_id=correlation_id,
            ))
        else:
            self._bus.publish(QualityFailed(
                payload={
                    **carried,
                    "issue": issue_number,
                    "files": files,
                    "failures": [r for r in results if not r.get("passed")],
                },
                correlation_id=correlation_id,
            ))

        return {"passed": all_passed, "results": results}
