"""Operator-facing CLI help contract for issue #439."""

from __future__ import annotations

from pathlib import Path

import pytest

from samuel.cli import (
    RUNTIME_CONFIG_DIR_ENV,
    _build_parser,
    _cmd_candidate,
    _resolve_runtime_config_dir,
    main,
)

COMMANDS = (
    "watch",
    "run",
    "replan",
    "health",
    "dashboard",
    "setup",
    "doctor",
    "install-service",
    "setup-labels",
    "refresh-pricing",
    "replay",
    "audit",
    "dlq",
    "changelog",
    "state",
    "candidate",
)


def test_root_help_lists_commands_syntax_notation_and_examples() -> None:
    help_text = _build_parser().format_help()
    normalized_help = " ".join(help_text.split())

    for command in COMMANDS:
        assert command in help_text
    assert "Aufruf: samuel dashboard [--host HOST] [--port PORT]" in normalized_help
    assert "Aufruf: samuel run ISSUE [--self] [OPTIONEN]" in normalized_help
    assert "Globale Optionen stehen vor dem Befehl" in normalized_help
    assert "-h und --help sowie -V und --version" in normalized_help
    assert "samuel dashboard --host 127.0.0.1 --port 7777" in normalized_help
    assert "samuel BEFEHL --help" in normalized_help


@pytest.mark.parametrize(
    ("command", "expected"),
    (
        ("watch", "samuel watch --once"),
        ("run", "samuel run 42 --workflow self"),
        ("replan", "samuel replan 42 --reason 'Akzeptanzkriterium fehlt'"),
        ("health", "samuel health"),
        ("dashboard", "samuel dashboard --host 127.0.0.1 --port 8080"),
        ("setup", "samuel setup --non-interactive"),
        ("doctor", "samuel doctor"),
        ("install-service", "samuel install-service --mode dashboard --write"),
        ("setup-labels", "samuel setup-labels"),
        ("refresh-pricing", "samuel refresh-pricing"),
        ("replay", "samuel replay --issue 42"),
        ("audit", "samuel audit verify"),
        ("dlq", "samuel dlq list --limit 20"),
        ("changelog", "samuel changelog --out CHANGELOG_DELTA.md"),
        ("state", "samuel state dump --json"),
        (
            "candidate",
            "samuel candidate submit 42 --head 0123456789abcdef0123456789abcdef01234567 --json",
        ),
    ),
)
def test_every_subcommand_help_contains_an_example(
    command: str,
    expected: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser = _build_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args([command, "--help"])

    assert exc_info.value.code == 0
    assert expected in capsys.readouterr().out


def test_dashboard_help_documents_host_port_and_effective_defaults(
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser = _build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["dashboard", "--help"])

    help_text = capsys.readouterr().out
    normalized = " ".join(help_text.split())
    assert "--host HOST" in help_text
    assert "DASHBOARD_HOST env oder 0.0.0.0" in normalized
    assert "--port PORT" in help_text
    assert "DASHBOARD_PORT env oder 7777" in normalized
    assert "--configuration-mode {production,setup}" in normalized
    assert "SAMUEL_CONFIGURATION_MODE oder production" in normalized


def test_main_without_command_prints_help_before_bootstrap(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main([])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "Schnellstart:" in captured.out
    assert "Bitte einen BEFEHL angeben" in captured.err


def test_runtime_config_binding_is_the_cli_default() -> None:
    assert _resolve_runtime_config_dir(None, environ={}) == "config"
    assert (
        _resolve_runtime_config_dir(
            None,
            environ={RUNTIME_CONFIG_DIR_ENV: "/qualification/config"},
        )
        == "/qualification/config"
    )


def test_explicit_config_must_match_runtime_binding(tmp_path: Path) -> None:
    config = tmp_path / "config"
    equivalent = config / ".." / "config"

    assert _resolve_runtime_config_dir(
        str(equivalent),
        environ={RUNTIME_CONFIG_DIR_ENV: str(config)},
    ) == str(equivalent)

    with pytest.raises(ValueError, match="conflicts with SAMUEL_RUNTIME_CONFIG_DIR"):
        _resolve_runtime_config_dir(
            "/app/config",
            environ={RUNTIME_CONFIG_DIR_ENV: "/qualification/config"},
        )


def test_empty_runtime_config_binding_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        _resolve_runtime_config_dir(None, environ={RUNTIME_CONFIG_DIR_ENV: "  "})
    with pytest.raises(ValueError, match="--config must not be empty"):
        _resolve_runtime_config_dir("", environ={})


def test_global_and_command_options_use_documented_order() -> None:
    parser = _build_parser()

    args = parser.parse_args(["--self", "run", "439", "--workflow", "self"])

    assert args.self_mode is True
    assert args.command == "run"
    assert args.issue == 439
    assert args.workflow == "self"


def test_run_accepts_self_after_subcommand() -> None:
    parser = _build_parser()

    args = parser.parse_args(["run", "--self", "424"])

    assert args.self_mode is True
    assert args.command == "run"
    assert args.issue == 424


def test_replan_requires_reason_and_parses_exact_issue() -> None:
    parser = _build_parser()

    args = parser.parse_args(["replan", "767", "--reason", "Plan ist unvollständig"])

    assert args.command == "replan"
    assert args.issue == 767
    assert args.reason == "Plan ist unvollständig"


def test_run_without_local_self_flag_preserves_global_value() -> None:
    parser = _build_parser()

    args = parser.parse_args(["--self", "run", "424"])

    assert args.self_mode is True


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("candidate_evaluation_completed", 0),
        ("candidate_verification_pending", 2),
        ("candidate_submission_rejected", 1),
    ],
)
def test_candidate_cli_exit_statuses(status: str, expected: int, capsys) -> None:
    class _Bus:
        def send(self, command):
            assert command.issue_number == 521
            assert command.head_sha == "a" * 40
            assert command.payload == {}
            return {"ok": expected == 0, "status": status, "reason_code": "test"}

    args = _build_parser().parse_args(["candidate", "submit", "521", "--head", "a" * 40, "--json"])

    assert _cmd_candidate(_Bus(), args) == expected  # type: ignore[arg-type]
    assert status in capsys.readouterr().out
