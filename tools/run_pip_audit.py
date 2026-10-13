#!/usr/bin/env python3
"""Run pip-audit with bounded retries for operational failures.

A valid JSON report containing vulnerabilities fails immediately. Only
transport/tool failures without a conclusive vulnerability report are retried.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AuditReport:
    dependency_count: int
    skipped_count: int
    findings: tuple[str, ...]


CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - command is a fixed local executable
        command,
        check=False,
        capture_output=True,
        text=True,
    )


def parse_report(output: str) -> AuditReport | None:
    """Return a conclusive report, or ``None`` for invalid/incomplete output."""

    try:
        document: Any = json.loads(output)
    except json.JSONDecodeError:
        return None
    if not isinstance(document, dict) or not isinstance(document.get("dependencies"), list):
        return None

    findings: list[str] = []
    skipped_count = 0
    dependencies = document["dependencies"]
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            return None
        if isinstance(dependency.get("skip_reason"), str):
            skipped_count += 1
            continue
        if not isinstance(dependency.get("vulns"), list):
            return None
        package = str(dependency.get("name", "unknown-package"))
        version = str(dependency.get("version", "unknown-version"))
        for vulnerability in dependency["vulns"]:
            if not isinstance(vulnerability, dict):
                return None
            vulnerability_id = str(vulnerability.get("id", "unknown-vulnerability"))
            findings.append(f"{package} {version}: {vulnerability_id}")

    return AuditReport(len(dependencies) - skipped_count, skipped_count, tuple(findings))


def run_pip_audit(
    *,
    attempts: int = 3,
    delay_seconds: float = 5.0,
    runner: CommandRunner = _run_command,
    sleeper: Callable[[float], None] = time.sleep,
) -> int:
    """Run the audit and return a process exit code.

    Confirmed vulnerability reports are never retried. Operational failures
    are retried up to ``attempts`` times and remain fail-closed afterwards.
    """

    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if delay_seconds < 0:
        raise ValueError("delay_seconds must not be negative")

    command = [
        sys.executable,
        "-m",
        "pip_audit",
        "--format=json",
        "--progress-spinner=off",
    ]
    for attempt in range(1, attempts + 1):
        print(f"pip-audit attempt {attempt}/{attempts}", flush=True)
        completed = runner(command)
        report = parse_report(completed.stdout)

        if report is not None and report.findings:
            print("Confirmed vulnerability findings; audit fails without retry:")
            for finding in report.findings:
                print(f"- {finding}")
            return 1

        if completed.returncode == 0 and report is not None:
            print(
                "pip-audit succeeded: "
                f"{report.dependency_count} dependencies audited, "
                f"{report.skipped_count} skipped, no known vulnerabilities"
            )
            return 0

        detail = completed.stderr.strip() or completed.stdout.strip() or "no diagnostic output"
        print(f"Operational pip-audit failure (exit {completed.returncode}): {detail}")
        if attempt < attempts:
            print(f"Retrying in {delay_seconds:g} seconds", flush=True)
            sleeper(delay_seconds)

    print(f"pip-audit failed after {attempts} attempts; CI remains fail-closed")
    return completed.returncode or 2


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--delay-seconds", type=float, default=5.0)
    args = parser.parse_args(argv)
    return run_pip_audit(attempts=args.attempts, delay_seconds=args.delay_seconds)


if __name__ == "__main__":
    sys.exit(main())
