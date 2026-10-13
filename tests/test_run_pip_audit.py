from __future__ import annotations

import json
import subprocess
import sys

import pytest

from tools.run_pip_audit import parse_report, run_pip_audit


def _result(returncode: int, output: object, stderr: str = "") -> subprocess.CompletedProcess[str]:
    stdout = output if isinstance(output, str) else json.dumps(output)
    return subprocess.CompletedProcess(["pip-audit"], returncode, stdout, stderr)


def _clean_report() -> dict[str, object]:
    return {"dependencies": [{"name": "example", "version": "1.0", "vulns": []}]}


def test_success_is_not_retried(capsys: pytest.CaptureFixture[str]) -> None:
    calls = 0

    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        assert command == [
            sys.executable,
            "-m",
            "pip_audit",
            "--format=json",
            "--progress-spinner=off",
        ]
        return _result(0, _clean_report())

    assert run_pip_audit(runner=runner, sleeper=lambda delay: None) == 0
    assert calls == 1
    assert "attempt 1/3" in capsys.readouterr().out


def test_transient_failure_then_success_is_retried(
    capsys: pytest.CaptureFixture[str],
) -> None:
    outcomes = iter(
        [
            _result(1, "", "Temporary failure in name resolution"),
            _result(0, _clean_report()),
        ]
    )
    delays: list[float] = []

    assert (
        run_pip_audit(
            attempts=3,
            delay_seconds=0.25,
            runner=lambda command: next(outcomes),
            sleeper=delays.append,
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "attempt 1/3" in output
    assert "attempt 2/3" in output
    assert "Temporary failure in name resolution" in output
    assert delays == [0.25]


def test_persistent_operational_failure_remains_fail_closed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = 0

    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return _result(1, "not json", "service unavailable")

    assert run_pip_audit(attempts=2, runner=runner, sleeper=lambda delay: None) == 1
    assert calls == 2
    assert "failed after 2 attempts" in capsys.readouterr().out


def test_confirmed_vulnerability_fails_immediately(
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = 0
    report = {
        "dependencies": [
            {
                "name": "affected",
                "version": "1.2.3",
                "vulns": [{"id": "PYSEC-2026-1"}],
            }
        ]
    }

    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return _result(1, report)

    assert run_pip_audit(runner=runner, sleeper=lambda delay: None) == 1
    assert calls == 1
    output = capsys.readouterr().out
    assert "fails without retry" in output
    assert "affected 1.2.3: PYSEC-2026-1" in output


def test_zero_exit_without_valid_report_is_not_considered_green() -> None:
    assert (
        run_pip_audit(
            attempts=1,
            runner=lambda command: _result(0, "truncated output"),
            sleeper=lambda delay: None,
        )
        == 2
    )


def test_parse_report_rejects_incomplete_shape() -> None:
    assert parse_report("not json") is None
    assert parse_report('{"dependencies": [{"name": "missing-vulns"}]}') is None


def test_parse_report_accepts_explicitly_skipped_project_dependency() -> None:
    report = parse_report(
        json.dumps(
            {
                "dependencies": [
                    {"name": "samuel", "skip_reason": "not published"},
                    {"name": "example", "version": "1.0", "vulns": []},
                ]
            }
        )
    )
    assert report is not None
    assert report.dependency_count == 1
    assert report.skipped_count == 1
