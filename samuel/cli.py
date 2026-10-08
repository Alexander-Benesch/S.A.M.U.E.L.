from __future__ import annotations

import argparse
import contextlib
import logging
import os
import shutil
import signal
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from types import FrameType
from typing import Any, NoReturn

from samuel import __build_info__, __version__
from samuel.core.bus import Bus

log = logging.getLogger(__name__)

RUNTIME_CONFIG_DIR_ENV = "SAMUEL_RUNTIME_CONFIG_DIR"
DEFAULT_CONFIG_DIR = "config"


class _SamuelHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Keep command syntax and examples readable in terminal help output."""

    def __init__(self, prog: str) -> None:
        super().__init__(prog, max_help_position=28)

    def _split_lines(self, text: str, width: int) -> list[str]:
        lines: list[str] = []
        for raw_line in text.splitlines():
            lines.extend(super()._split_lines(raw_line, width))
        return lines


_ROOT_HELP_EPILOG = """\
Notation:
  -h und --help sowie -V und --version sind jeweils gleichwertige Kurz-/Langformen.
  Globale Optionen stehen vor dem Befehl; befehlsspezifische Optionen danach.
  Bei 'run' sind --self und --allow-non-main auch nach dem Befehl erlaubt.

Schnellstart:
  samuel setup
  samuel doctor
  samuel dashboard --host 127.0.0.1 --port 7777
  samuel run 42
  samuel --self run 42
  samuel watch --once
  samuel audit verify
  samuel dlq list --limit 20
  samuel state status --json
  samuel retention dry-run --json
  samuel workspace list --json
  samuel resume list --json

Ausführliche Hilfe zu einem Befehl:
  samuel BEFEHL --help
"""


def _command_help(
    summary: str,
    syntax: str,
    *examples: str,
) -> dict[str, Any]:
    """Return consistent argparse metadata for one CLI subcommand."""
    example_lines = "\n".join(f"  {example}" for example in examples)
    return {
        "help": f"{summary}\nAufruf: samuel {syntax}",
        "description": summary,
        "epilog": f"Beispiele:\n{example_lines}",
        "formatter_class": _SamuelHelpFormatter,
    }


def _load_env_file(path: Path, *, override: bool) -> None:
    if not path.exists():
        return
    from samuel.slices.setup.env_io import parse_env

    for key, value in parse_env(path.read_text(encoding="utf-8")).items():
        if override or key not in os.environ:
            os.environ[key] = value


def _resolve_runtime_config_dir(
    explicit: str | None,
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Resolve one authoritative config directory for every CLI process.

    Container runtimes bind ``SAMUEL_RUNTIME_CONFIG_DIR`` once so the main
    process and Docker healthcheck cannot silently bootstrap different state.
    An explicit ``--config`` remains supported, but must name the same path
    when the runtime binding is present.
    """

    environment = os.environ if environ is None else environ
    bound = environment.get(RUNTIME_CONFIG_DIR_ENV, "").strip()
    if explicit is not None and not explicit.strip():
        raise ValueError("--config must not be empty")
    if RUNTIME_CONFIG_DIR_ENV in environment and not bound:
        raise ValueError(f"{RUNTIME_CONFIG_DIR_ENV} must not be empty")
    if explicit is not None and bound:
        explicit_path = Path(explicit).expanduser().resolve(strict=False)
        bound_path = Path(bound).expanduser().resolve(strict=False)
        if explicit_path != bound_path:
            raise ValueError(
                f"--config ({explicit_path}) conflicts with {RUNTIME_CONFIG_DIR_ENV} ({bound_path})"
            )
    return explicit if explicit is not None else (bound or DEFAULT_CONFIG_DIR)


def _check_self_run_branch(project_root: Path, allow_non_main: bool) -> bool:
    """Pre-check: --self run must operate on `main` so commits/cleanup land
    on the expected branch. Returns True if OK to proceed.

    Regression for #227: silent execution on the operator's working branch
    led to commits landing in the wrong place during self-mode runs.
    """
    from samuel.core import git as _git

    current = _git.current_branch(cwd=project_root)
    if current == "main":
        return True
    if allow_non_main:
        print(
            f"WARN: --self run auf '{current}' (nicht main) — durch --allow-non-main erlaubt",
            file=sys.stderr,
        )
        return True
    print(
        f"ERROR: --self run muss auf 'main' laufen, aktuell: '{current}'.\n"
        "       Wechsele auf main (`git checkout main`) oder benutze --allow-non-main.",
        file=sys.stderr,
    )
    return False


def _activate_self_mode(project_root: Path) -> Path | None:
    base_env = project_root / ".env"
    agent_env = project_root / ".env.agent"
    _load_env_file(base_env, override=False)
    if agent_env.exists():
        _load_env_file(agent_env, override=True)
        os.environ["SAMUEL_SELF_MODE"] = "1"
        os.environ["SAMUEL_ENV_FILE"] = str(agent_env)
        return agent_env
    os.environ["SAMUEL_SELF_MODE"] = "1"
    return None


def _configured_target_project(config_path: str | Path) -> Path | None:
    """Return the configured external project root for a standard run.

    ``samuel setup`` stores ``PROJECT_ROOT`` in the .env next to the config
    directory.  Load that same file before bootstrap so a missing or invalid
    target can be reported instead of publishing an event into an unusable
    workflow.
    """
    config_root = Path(config_path).expanduser().resolve().parent
    _load_env_file(config_root / ".env", override=False)
    raw = os.environ.get("PROJECT_ROOT", "").strip()
    if not raw:
        return None
    project_root = Path(raw).expanduser()
    if not project_root.is_absolute():
        project_root = config_root / project_root
    return project_root.resolve()


def _validate_target_project(project_root: Path | None) -> tuple[bool, str]:
    """Validate the minimum target contract needed by the standard workflow."""
    if project_root is None:
        return (
            False,
            "Kein Zielsystem konfiguriert und --self nicht gesetzt — nichts zu tun.\n"
            "       Konfiguriere PROJECT_ROOT mit `samuel setup` oder nutze "
            "`samuel run --self <nr>`.",
        )
    if not project_root.is_dir():
        return False, f"PROJECT_ROOT existiert nicht oder ist kein Verzeichnis: {project_root}"
    if not (project_root / ".git").exists():
        return False, f"PROJECT_ROOT ist kein Git-Repository: {project_root}"
    return True, ""


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="samuel",
        description="S.A.M.U.E.L. — Sicheres Autonomes Mehrschichtiges "
        "Ueberwachungs- und Entwicklungs-Logiksystem",
        epilog=_ROOT_HELP_EPILOG,
        formatter_class=_SamuelHelpFormatter,
    )
    p.add_argument(
        "--config",
        default=None,
        help=(
            "Pfad zum config-Verzeichnis "
            f"(default: ${RUNTIME_CONFIG_DIR_ENV} oder {DEFAULT_CONFIG_DIR})"
        ),
    )
    p.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log-Level (ueberschreibt config/agent.json)",
    )
    p.add_argument(
        "--self",
        dest="self_mode",
        action="store_true",
        help="Self-Mode: Agent arbeitet am eigenen Repo (lädt .env.agent-Override)",
    )
    p.add_argument(
        "--allow-non-main",
        action="store_true",
        help="Erlaubt --self run auf einer anderen Branch als main (Default: blockiert)",
    )
    p.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"samuel {__version__}",
    )

    sub = p.add_subparsers(
        dest="command",
        title="Befehle",
        metavar="BEFEHL",
        description="Verfügbare Befehle; Details mit: samuel BEFEHL --help",
    )

    # --- watch: Polling-Loop ---
    w = sub.add_parser(
        "watch",
        **_command_help(
            "Polling-Modus: Issues scannen und abarbeiten",
            "watch [--interval SEKUNDEN] [--once]",
            "samuel watch --interval 30",
            "samuel watch --once",
        ),
    )
    w.add_argument("--interval", type=int, default=60, help="Poll-Intervall in Sekunden")
    w.add_argument("--once", action="store_true", help="Einmal scannen, dann beenden")

    # --- run: Einzelnes Issue bearbeiten ---
    r = sub.add_parser(
        "run",
        **_command_help(
            "Einzelnes Issue durch einen Workflow schicken",
            "run ISSUE [--self] [OPTIONEN]",
            "samuel run 42",
            "samuel run --self 42",
            "samuel run 42 --workflow self",
        ),
    )
    r.add_argument("issue", type=int, help="Issue-Nummer (z.B. 136 für #136)")
    r.add_argument(
        "--workflow",
        default=None,
        help="Workflow-Name (override). Default: 'self' bei --self, sonst agent.mode aus config.",
    )
    # #424: Operator-facing mode flags belong naturally to `run`.  SUPPRESS
    # preserves a value parsed before the subcommand instead of overwriting it
    # with a second default, so both documented orders are equivalent.
    r.add_argument(
        "--self",
        dest="self_mode",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Self-Mode fuer diesen Lauf (auch global vor 'run' erlaubt)",
    )
    r.add_argument(
        "--allow-non-main",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Erlaubt einen Self-Run auf einer anderen Branch als main",
    )

    # --- replan: bestehenden Plan explizit widerrufen und ersetzen ---
    rp_plan = sub.add_parser(
        "replan",
        **_command_help(
            "Aktiven Plan widerrufen und mit neuer Freigaberunde ersetzen",
            "replan ISSUE --reason BEGRUENDUNG [--workflow NAME]",
            "samuel replan 42 --reason 'Akzeptanzkriterium fehlt'",
        ),
    )
    rp_plan.add_argument("issue", type=int, help="Issue-Nummer")
    rp_plan.add_argument("--reason", required=True, help="Begründung für den Planwiderruf")
    rp_plan.add_argument("--workflow", default=None, help="Workflow-Name (override)")

    # --- health: Health-Check ---
    sub.add_parser(
        "health",
        **_command_help(
            "Health-Check ausfuehren und Ergebnis ausgeben",
            "health",
            "samuel health",
        ),
    )

    # --- dashboard: HTTP-Server + Dashboard ---
    d = sub.add_parser(
        "dashboard",
        **_command_help(
            "HTTP-Server mit Dashboard und REST-API starten",
            "dashboard [--host HOST] [--port PORT]",
            "samuel dashboard --port 7777",
            "samuel dashboard --host 127.0.0.1 --port 8080",
        ),
    )
    d.add_argument(
        "--host", default=None, help="Bind-Adresse (default: DASHBOARD_HOST env oder 0.0.0.0)"
    )
    d.add_argument(
        "--port", type=int, default=None, help="Port (default: DASHBOARD_PORT env oder 7777)"
    )
    d.add_argument(
        "--configuration-mode",
        choices=["production", "setup"],
        default=None,
        help=("Operator-Konfigurationsgrenze; Default: SAMUEL_CONFIGURATION_MODE oder production"),
    )

    # --- setup: interaktiver Einrichtungs-Wizard (Installer, CLI) ---
    st = sub.add_parser(
        "setup",
        **_command_help(
            "Einrichtungs-Wizard fuer SCM, Verzeichnisse, Sicherheit und Labels",
            "setup [--non-interactive]",
            "samuel setup",
            "samuel setup --non-interactive",
        ),
    )
    st.add_argument(
        "--non-interactive",
        action="store_true",
        help="Ohne Prompts — Werte aus Env/.env (fuer install.sh/Docker/CI).",
    )

    # --- doctor: Diagnose (was ist konfiguriert, was fehlt) ---
    doctor = sub.add_parser(
        "doctor",
        **_command_help(
            "SCM, LLM, Verzeichnisse und Sicherheit diagnostizieren",
            "doctor",
            "samuel doctor",
        ),
    )
    doctor.add_argument(
        "--branch-protection-token-file",
        default="",
        help="Geschützte temporäre Token-Datei ausschließlich für den Branchschutz-GET",
    )

    # --- install-service: systemd-Unit generieren (Pfade/User automatisch) ---
    isvc = sub.add_parser(
        "install-service",
        **_command_help(
            "systemd-Unit mit echten Pfaden generieren",
            "install-service [--mode {watch,dashboard}] [--write] [--user USER] [--name NAME]",
            "samuel install-service --mode watch",
            "samuel install-service --mode dashboard --write",
        ),
    )
    isvc.add_argument(
        "--mode",
        default="watch",
        choices=["watch", "dashboard"],
        help="ExecStart-Modus (default: watch)",
    )
    isvc.add_argument(
        "--write",
        action="store_true",
        help="nach /etc/systemd/system/<name>.service schreiben (root)",
    )
    isvc.add_argument("--user", default=None, help="Service-User (default: aktueller User)")
    isvc.add_argument("--name", default=None, help="Unit-Name (default: samuel-<mode>)")

    # --- setup-labels: Gitea-Labels gemäß config/labels.json anlegen ---
    sub.add_parser(
        "setup-labels",
        **_command_help(
            "Workflow-, Risk- und Scope-Labels auf dem SCM anlegen",
            "setup-labels",
            "samuel setup-labels",
        ),
    )

    # --- refresh-pricing: OpenRouter-Modell-Preise aktualisieren (#311) ---
    sub.add_parser(
        "refresh-pricing",
        **_command_help(
            "OpenRouter-Modell- und Preis-Cache aktualisieren",
            "refresh-pricing",
            "samuel refresh-pricing",
        ),
    )

    # --- replay: Workflow aus Audit-Log rekonstruieren (#336) ---
    rp = sub.add_parser(
        "replay",
        **_command_help(
            "Workflow eines Issues side-effect-frei aus dem Audit-Log rekonstruieren",
            "replay --issue ISSUE [--run ID] [--publish]",
            "samuel replay --issue 42",
            "samuel replay --issue 42 --run CORRELATION_ID --publish",
        ),
    )
    rp.add_argument("--issue", type=int, required=True, help="Issue-Nummer")
    rp.add_argument("--run", default=None, help="optional: correlation_id eines konkreten Runs")
    rp.add_argument(
        "--publish",
        action="store_true",
        help="Events side-effect-frei an einen No-op-Bus re-publishen",
    )

    # --- audit: Audit-Log-HMAC-Chain verifizieren (#333) ---
    au = sub.add_parser(
        "audit",
        **_command_help(
            "Audit-Log auf Manipulationen pruefen",
            "audit verify",
            "samuel audit verify",
        ),
    )
    au.add_argument("action", choices=["verify"], help="verify = Chain pruefen")

    # --- dlq: Dead-Letter-Queue inspizieren / re-publishen (#334) ---
    dlq = sub.add_parser(
        "dlq",
        **_command_help(
            "Fehlgeschlagene Events in der Dead-Letter-Queue verwalten",
            "dlq {list,replay} [ID] [--limit ANZAHL]",
            "samuel dlq list --limit 20",
            "samuel dlq replay ENTRY_ID",
        ),
    )
    dlq.add_argument(
        "action",
        choices=["list", "replay"],
        help="list = anzeigen, replay = Event erneut publishen",
    )
    dlq.add_argument("id", nargs="?", default=None, help="Entry-ID (fuer replay)")
    dlq.add_argument("--limit", type=int, default=50, help="max. Eintraege bei list")

    # --- changelog: Aus git-log einen Changelog generieren (#163) ---
    c = sub.add_parser(
        "changelog",
        **_command_help(
            "Changelog aus git log seit einem Tag oder einer Phase generieren",
            "changelog [--since REV] [--phase NUMMER] [--post-to-issue ISSUE] [--out DATEI]",
            "samuel changelog --out CHANGELOG_DELTA.md",
            "samuel changelog --phase 13 --post-to-issue 250",
        ),
    )
    c.add_argument(
        "--since",
        default=None,
        help=("Start-Revision (Tag, Branch, Commit). Default: hoechster erreichbarer Produkt-Tag."),
    )
    c.add_argument(
        "--phase",
        type=int,
        default=None,
        help="Phasen-Nummer (mappt auf Tag 'phase-N-complete')",
    )
    c.add_argument(
        "--post-to-issue",
        type=int,
        default=None,
        help="Changelog zusaetzlich als Kommentar auf Gitea-Issue posten",
    )
    c.add_argument(
        "--out",
        default=None,
        help="Output in Datei schreiben (default: stdout)",
    )

    state = sub.add_parser(
        "state",
        **_command_help(
            "Versionierten Runtime-State diagnostizieren",
            "state {status,dump,reproject-runs,restore,reconcile-*} [--json]",
            "samuel state status --json",
            "samuel state dump --json",
            "samuel state restore --source /safe/backup.sqlite3 --json",
            "samuel state reconcile-scan --operation-id UUID --json",
        ),
    )
    state.add_argument(
        "action",
        choices=[
            "status",
            "dump",
            "reproject-runs",
            "abandon-healing",
            "restore",
            "reconcile-status",
            "reconcile-scan",
            "reconcile-classify",
            "reconcile-complete",
        ],
    )
    state.add_argument("--observation-key", default="")
    state.add_argument("--reason", default="")
    state.add_argument("--source", default="")
    state.add_argument("--operation-id", default="")
    state.add_argument("--supersede-operation-id", default="")
    state.add_argument("--object-type", default="")
    state.add_argument("--object-key", default="")
    state.add_argument(
        "--classification",
        choices=["verified_effect", "verified_absent", "abandoned"],
    )
    state.add_argument(
        "--json",
        action="store_true",
        help="maschinenlesbare, deterministische JSON-Ausgabe",
    )

    identity = sub.add_parser(
        "identity",
        **_command_help(
            "Lokale Dashboard-Identitäten initialisieren und wiederherstellen",
            "identity {status,bootstrap,cutover,recover} [OPTIONEN]",
            "samuel identity status --json",
            "samuel identity bootstrap --username admin --password-file /run/secrets/password",
            "samuel identity cutover --client-inventory-confirmed --reason 'clients migrated'",
        ),
    )
    identity.add_argument("action", choices=["status", "bootstrap", "cutover", "recover"])
    identity.add_argument("--username", default="")
    identity.add_argument("--password-file", default="")
    identity.add_argument("--reason", default="")
    identity.add_argument("--client-inventory-confirmed", action="store_true")
    identity.add_argument("--json", action="store_true")

    retention = sub.add_parser(
        "retention",
        **_command_help(
            "Retention inventarisieren und explizit operatorgefuehrt steuern",
            "retention {dry-run,approve,activate,suspend,pause,unpause,execute,backup,replay-scores} [OPTIONEN]",
            "samuel retention dry-run --json",
            "samuel retention approve --category observations --reason 'policy reviewed' --json",
            "samuel retention backup --json",
            "samuel retention replay-scores --json",
        ),
    )
    retention.add_argument(
        "action",
        choices=[
            "dry-run",
            "approve",
            "activate",
            "suspend",
            "pause",
            "unpause",
            "execute",
            "backup",
            "replay-scores",
        ],
    )
    retention.add_argument("--category", default="")
    retention.add_argument("--reason", default="")
    retention.add_argument("--plan-digest", default="")
    retention.add_argument("--cutoff-utc", default="")
    retention.add_argument("--issue", type=int, default=None)
    retention.add_argument(
        "--eval-config-dir",
        action="append",
        default=[],
        help="Verzeichnis mit eval.json; fuer Replay wiederholbar (Default: --config)",
    )
    retention.add_argument("--json", action="store_true")

    evidence = sub.add_parser(
        "evidence",
        **_command_help(
            "Vorhandene externe SCM-Check-Evidence advisory bewerten",
            "evidence assess --run-id ID --subject DATEI [OPTIONEN]",
            "samuel evidence assess --run-id 123 --subject subject.json --event pull_request --workflow .gitea/workflows/ci.yml --json",
        ),
    )
    evidence.add_argument("action", choices=["assess"])
    evidence.add_argument("--run-id", type=int, required=True)
    evidence.add_argument("--attempt", type=int, default=1)
    evidence.add_argument("--subject", required=True, help="JSON-Datei mit EvaluationSubject")
    evidence.add_argument("--workflow", default=None, help="erwarteter Workflow-Pfad")
    evidence.add_argument("--event", default=None, help="erwarteter Provider-Eventtyp")
    evidence.add_argument("--max-age-seconds", type=int, default=86400)
    evidence.add_argument("--issue", type=int, default=0)
    evidence.add_argument("--json", action="store_true")

    candidate = sub.add_parser(
        "candidate",
        **_command_help(
            "Git-Candidate passiv prüfen oder gebundene Provider-Verifikation beauftragen",
            "candidate {submit,request} ISSUE --head FULL_SHA [--new-request] [--json]",
            "samuel candidate submit 42 --head 0123456789abcdef0123456789abcdef01234567 --json",
            "samuel candidate request 42 --head 0123456789abcdef0123456789abcdef01234567 --json",
        ),
    )
    candidate.add_argument("action", choices=["submit", "request"])
    candidate.add_argument("issue", type=int, help="Issue-Zuordnung des aktiven Plans")
    candidate.add_argument("--head", required=True, help="vollständiger Candidate-Commit-SHA")
    candidate.add_argument(
        "--new-request",
        action="store_true",
        help="nach terminalem/gebundenem Lauf bewusst einen neuen Providerauftrag erzeugen",
    )
    candidate.add_argument("--json", action="store_true")

    workspace = sub.add_parser(
        "workspace",
        **_command_help(
            "Run- und Verifikations-Worktrees diagnostizieren",
            "workspace {list,inspect,prune,quarantine,discard} [WORKSPACE_ID] [--json]",
            "samuel workspace list --json",
            "samuel workspace inspect WORKSPACE_ID --json",
            "samuel workspace prune --json",
        ),
    )
    workspace.add_argument("action", choices=["list", "inspect", "prune", "quarantine", "discard"])
    workspace.add_argument("workspace_id", nargs="?", default="")
    workspace.add_argument("--reason", default="")
    workspace.add_argument("--json", action="store_true")

    resume = sub.add_parser(
        "resume",
        **_command_help(
            "Gebundene Finalisierungs-Checkpoints diagnostizieren und fortsetzen",
            "resume {list,inspect,attempt,resume,abandon,cleanup} [CHECKPOINT_KEY] [--json]",
            "samuel resume list --json",
            "samuel resume inspect CHECKPOINT_KEY --json",
            "samuel resume attempt CHECKPOINT_KEY --json",
            "samuel resume abandon CHECKPOINT_KEY --reason 'operator decision' --json",
        ),
    )
    resume.add_argument(
        "action",
        choices=["list", "inspect", "attempt", "resume", "abandon", "cleanup"],
    )
    resume.add_argument("checkpoint_key", nargs="?", default="")
    resume.add_argument("--reason", default="")
    resume.add_argument("--json", action="store_true")

    return p


def _cmd_watch(bus: Bus, args: argparse.Namespace) -> int:
    import time

    from samuel.core.commands import ScanIssuesCommand

    cfg = getattr(bus, "config", None)
    interval = args.interval
    poll_timeout = 0
    if cfg:
        interval = int(cfg.get("agent.auto.poll_interval", interval))
        poll_timeout = int(cfg.get("agent.auto.poll_timeout", 0))
    # CLI flag overrides config when explicitly provided
    if args.interval != 60:  # 60 is the argparse default
        interval = args.interval

    log.info(
        "Watch-Modus gestartet (interval=%ds, timeout=%ds, once=%s)",
        interval,
        poll_timeout,
        args.once,
    )
    elapsed = 0
    while True:
        cycle_failed = False
        try:
            cmd = ScanIssuesCommand(payload={})
            result = bus.send(cmd)
            log.info("Scan abgeschlossen: %s", result)
            if not isinstance(result, dict):
                cycle_failed = True
                log.error("Watch-Zyklus lieferte kein maschinenlesbares Ergebnis")
            elif int(result.get("dispatched_failed", 0)) > 0:
                cycle_failed = True
                log.error(
                    "Watch-Zyklus fail-closed: %d Dispatch(es) fehlgeschlagen",
                    result["dispatched_failed"],
                )
        except Exception:
            cycle_failed = True
            log.exception("Fehler im Watch-Loop")
        if args.once:
            return 1 if cycle_failed else 0
        if poll_timeout and elapsed >= poll_timeout:
            log.info("Poll-Timeout (%ds) erreicht, beende Watch-Loop", poll_timeout)
            break
        time.sleep(interval)
        elapsed += interval
    return 0


def _cmd_run(bus: Bus, args: argparse.Namespace) -> int:
    from samuel.core.events import Event
    from samuel.core.security_policy import redact_secrets

    rejected: list[dict] = []
    blocked: list[dict] = []
    event = Event(
        name="IssueReady",
        payload={
            "issue_number": args.issue,
            "clarification_continuation_authorized": True,
        },
    )

    def belongs_to_run(terminal_event: Event) -> bool:
        return (
            terminal_event.correlation_id == event.correlation_id
            and terminal_event.payload.get("issue") == args.issue
        )

    def record_rejection(terminal_event: Event) -> None:
        if belongs_to_run(terminal_event):
            rejected.append(terminal_event.payload)

    def record_block(terminal_event: Event) -> None:
        if belongs_to_run(terminal_event):
            blocked.append(terminal_event.payload)

    bus.subscribe("PlanReplanRejected", record_rejection)
    bus.subscribe("PlanBlocked", record_block)
    bus.publish(event)
    if rejected:
        print(
            f"Issue #{args.issue} besitzt bereits einen aktiven Plan; "
            "verwende 'samuel replan ISSUE --reason ...'.",
            file=sys.stderr,
        )
        return 1
    if blocked:
        reason = redact_secrets(str(blocked[-1].get("reason", "planning_blocked")))[:500]
        print(f"Planung für Issue #{args.issue} blockiert: {reason}", file=sys.stderr)
        return 1
    return 0


def _cmd_replan(bus: Bus, args: argparse.Namespace) -> int:
    from samuel.core.commands import ReplanIssueCommand

    result = bus.send(ReplanIssueCommand(issue_number=args.issue, reason=args.reason))
    if not isinstance(result, dict) or result.get("success") is False:
        reason = (
            result.get("reason", "replan_failed") if isinstance(result, dict) else "replan_failed"
        )
        print(f"Replan für Issue #{args.issue} fehlgeschlagen: {reason}", file=sys.stderr)
        return 1
    return 0


def _cmd_candidate(bus: Bus, args: argparse.Namespace) -> int:
    """Submit an existing immutable candidate to the passive evaluation path."""

    import json

    from samuel.core.commands import (
        RequestCandidateVerificationCommand,
        SubmitCandidateCommand,
    )

    if args.action == "request":
        result = bus.send(
            RequestCandidateVerificationCommand(
                issue_number=args.issue,
                head_sha=args.head,
                new_request=bool(args.new_request),
                payload={},
            )
        )
    else:
        if args.new_request:
            result = {
                "ok": False,
                "status": "candidate_submission_rejected",
                "reason_code": "new_request_requires_request_action",
                "reason": "--new-request is only valid with candidate request",
            }
        else:
            result = bus.send(
                SubmitCandidateCommand(
                    issue_number=args.issue,
                    head_sha=args.head,
                    payload={},
                )
            )
    if not isinstance(result, dict):
        result = {
            "ok": False,
            "status": "candidate_submission_rejected",
            "reason_code": "candidate_result_invalid",
            "reason": "Candidate submission returned no structured result",
        }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    else:
        print(
            f"Candidate #{args.issue}: {result.get('status', 'unknown')} "
            f"({result.get('reason_code', 'unknown')})"
        )
    if result.get("status") == "candidate_evaluation_completed":
        return 0
    if result.get("status") == "candidate_verification_pending":
        return 2
    return 1


def _cmd_replay(bus: Bus, args: argparse.Namespace) -> int:
    """#336: Workflow eines Issues aus dem Audit-Log rekonstruieren.

    Standardmaessig nur Rekonstruktion (Snapshot + Timeline). Mit --publish
    werden die Events side-effect-frei an einen FRISCHEN Bus (ohne Handler)
    re-publisht — niemals an den realen Bus, damit keine Commits/PRs ausgeloest
    werden.
    """
    import contextlib

    from samuel.core.replay import build_snapshot, load_run_events, replay_to_bus

    data_dir = "data"
    cfg = getattr(bus, "config", None)
    if cfg is not None:
        with contextlib.suppress(Exception):
            data_dir = str(cfg.get("agent.data_dir", "data"))

    events = load_run_events(data_dir, issue=args.issue, run_id=args.run)
    if not events:
        print(f"no audit events for issue #{args.issue}" + (f" run {args.run}" if args.run else ""))
        return 0

    snap = build_snapshot(events, issue=args.issue)
    print(
        f"Issue #{args.issue}: {snap['event_count']} events, status={snap['status']}"
        + (f" ({snap['terminal_event']})" if snap["terminal_event"] else "")
    )
    print(f"  {snap['first_ts']}  ->  {snap['last_ts']}")
    print("  Timeline:")
    for t in snap["timeline"]:
        msg = f"  {t['message']}" if t["message"] else ""
        print(f"    {(t['ts'] or '')[:19]}  {t['event']}{msg}")

    if args.publish:
        from samuel.core.bus import Bus

        replay_bus = Bus()  # frischer Bus ohne Handler => side-effect-frei
        seen: list = []
        replay_bus.subscribe("*", lambda e: seen.append(e.name))
        n = replay_to_bus(events, replay_bus)
        print(f"\n  replayed {n} events to a no-op bus (side-effect-free)")
    return 0


def _cmd_audit(bus: Bus, args: argparse.Namespace) -> int:
    """#333: Audit-Log-HMAC-Chain verifizieren. Bei Tampering ->
    IntegrityViolation publishen (sichtbar im Security-Tab, #208)."""
    import contextlib
    import os
    from pathlib import Path

    from samuel.adapters.audit.jsonl import verify_chain

    key = os.environ.get("SAMUEL_AUDIT_HMAC_KEY", "")
    if not key:
        _record_bus_qualification(
            bus,
            kind="audit_integrity",
            status="not_checked",
            summary={"reason": "signing_not_configured"},
            preserve_current_failure=True,
        )
        print("SAMUEL_AUDIT_HMAC_KEY not set — audit chain is not enabled (no signing).")
        return 1

    cfg = getattr(bus, "config", None)
    data_dir = "data"
    if cfg is not None:
        with contextlib.suppress(Exception):
            data_dir = str(cfg.get("agent.data_dir", "data"))
    log_dir = Path(data_dir) / "logs"
    files = sorted(log_dir.glob("agent*.jsonl"))
    if not files:
        _record_bus_qualification(
            bus,
            kind="audit_integrity",
            status="not_checked",
            summary={"reason": "audit_logs_missing"},
            preserve_current_failure=True,
        )
        print(f"no audit log files in {log_dir}")
        return 0

    all_ok = True
    total = 0
    failed_files = 0
    for fp in files:
        res = verify_chain(fp, key)
        total += res["records"]
        if res["ok"]:
            print(f"OK   {fp.name}: {res['records']} records, chain intact")
        else:
            all_ok = False
            failed_files += 1
            print(f"FAIL {fp.name}: {res['error']} (line {res['line']})")
            from samuel.core.events import IntegrityViolation

            with contextlib.suppress(Exception):
                bus.publish(
                    IntegrityViolation(
                        payload={
                            "files": [str(fp)],
                            "reason": f"audit chain verify failed: {res['error']}",
                            "line": res["line"],
                            "owasp_risk": "agentic_supply_chain",
                        }
                    )
                )
    print(
        f"\n{'VERIFIED' if all_ok else 'TAMPERING DETECTED'}: "
        f"{total} records across {len(files)} file(s)"
    )
    _record_bus_qualification(
        bus,
        kind="audit_integrity",
        status="passed" if all_ok else "failed",
        summary={
            "files_checked": len(files),
            "records_checked": total,
            "failed_files": failed_files,
        },
    )
    return 0 if all_ok else 1


def _record_bus_qualification(
    bus: Bus,
    *,
    kind: str,
    status: str,
    summary: dict[str, Any],
    preserve_current_failure: bool = False,
) -> None:
    """Persist a bounded qualification fact without changing command outcome."""

    from samuel.core.health_projection import record_projection

    store = getattr(bus, "run_projection_store", None)
    state = getattr(bus, "state_store", None)
    if store is None or state is None:
        return
    try:
        instance_uuid = str(state.status().authority_instance)
        record_projection(
            store,
            kind=kind,
            status=status,
            instance_uuid=instance_uuid,
            summary=summary,
            preserve_current_failure=preserve_current_failure,
        )
    except Exception as exc:  # noqa: BLE001 - qualification projection is non-blocking
        log.warning("Qualification projection unavailable: %s", type(exc).__name__)


def _cmd_dlq(bus: Bus, args: argparse.Namespace) -> int:
    """#334: Dead-Letter-Queue inspizieren und Events re-publishen."""
    dlq = getattr(bus, "dlq", None)
    if dlq is None:
        print("DLQ not configured")
        return 1
    if args.action == "list":
        rows = dlq.list(limit=args.limit)
        if not rows:
            print("DLQ empty")
            return 0
        print(f"{len(rows)} dead-letter entr{'y' if len(rows) == 1 else 'ies'} (newest first):")
        for r in rows:
            print(
                f"  {r.get('id', '?')}  {r.get('ts', '')}  {r.get('event_name', '?')}"
                f"  <- {r.get('handler', '?')}"
            )
            print(f"      error: {r.get('error', '')}")
        return 0
    # replay
    if not args.id:
        print("replay requires an entry id (see 'dlq list')")
        return 1
    entry = dlq.get(args.id)
    if entry is None:
        print(f"no DLQ entry with id {args.id}")
        return 1
    from samuel.core.events import Event

    bus.publish(
        Event(
            name=entry["event_name"],
            payload=entry.get("payload", {}),
            correlation_id=entry.get("correlation_id", "") or "",
        )
    )
    print(f"replayed {entry['event_name']} (id {args.id})")
    return 0


def _cmd_health(bus: Bus, _args: argparse.Namespace) -> int:
    from samuel.core.commands import HealthCheckCommand

    cmd = HealthCheckCommand(payload={})
    result = bus.send(cmd)
    if result:
        healthy = result.get("healthy", False)
        print(f"Technical health: {'passed' if healthy else 'failed'}")
        readiness = result.get("operational_readiness", {})
        qualification = result.get("qualification", {})
        print(f"Operational readiness: {readiness.get('status', 'unknown')}")
        print(f"Qualification: {qualification.get('status', 'not_checked')}")
        for k, v in result.items():
            if k not in {"healthy", "operational_readiness", "qualification"}:
                print(f"  {k}: {v}")
        return 0 if healthy else 1
    print("Technical health: no response")
    return 1


def _cmd_evidence(args: argparse.Namespace) -> int:
    """Pull one existing SCM run into an immutable advisory observation."""

    import json

    from samuel.adapters.auth.static_token import StaticTokenAuth
    from samuel.adapters.gitea.adapter import GiteaAdapter
    from samuel.adapters.gitea.api import GiteaAPIError
    from samuel.adapters.state.sqlite import SQLiteStateStore, resolve_data_dir
    from samuel.core.bootstrap import _load_dotenv
    from samuel.core.config import FileConfig, load_scm_config
    from samuel.core.evaluation_observation import canonical_digest
    from samuel.core.evaluation_subject import EvaluationSubject
    from samuel.core.external_evidence import (
        SCM_CHECK_ASSESSMENT_SCHEMA,
        SCMCheckExpectations,
        SCMCheckReference,
        assess_scm_check_evidence,
    )
    from samuel.core.state import ObservationRecord

    config_dir = Path(args.config).expanduser().resolve()
    _load_dotenv(config_dir.parent / ".env")
    try:
        subject_path = Path(args.subject).expanduser().resolve()
        if subject_path.stat().st_size > 65536:
            raise ValueError("subject file exceeds 65536 bytes")
        raw_subject = json.loads(subject_path.read_text(encoding="utf-8"))
        if not isinstance(raw_subject, dict):
            raise ValueError("subject file must contain one JSON object")
        subject = EvaluationSubject.from_dict(raw_subject)
        scm_config = load_scm_config()
        if scm_config.provider.strip().lower() != "gitea":
            raise ValueError("the first advisory evidence adapter supports provider=gitea")
        reference = SCMCheckReference(
            provider="gitea",
            repository=scm_config.repo,
            run_id=args.run_id,
            attempt=args.attempt,
        )
        expectations = SCMCheckExpectations(
            status_context=scm_config.required_status_context,
            workflow_path=args.workflow,
            event=args.event,
            max_age_seconds=args.max_age_seconds,
        )
        reader = GiteaAdapter(
            scm_config.url,
            scm_config.repo,
            StaticTokenAuth(scm_config.token),
        )
        observation = reader.read_check_evidence(reference)
        assessment = assess_scm_check_evidence(
            observation,
            reference=reference,
            subject=subject,
            expectations=expectations,
        )
        config = FileConfig(config_dir)
        data_dir = resolve_data_dir(config.get("agent.data_dir", "data"), config_dir=config_dir)
        store = SQLiteStateStore(data_dir)
        payload = assessment.as_dict()
        payload["in_toto_statement"] = assessment.as_in_toto_statement()
        inserted = store.observations.put_observation(
            ObservationRecord(
                observation_key=assessment.assessment_key,
                subject_key=canonical_digest(subject.as_dict()),
                evidence_digest=observation.evidence_digest,
                observation_schema=SCM_CHECK_ASSESSMENT_SCHEMA,
                payload=payload,
                issue_number=args.issue,
                evidence_origin="external_scm_advisory",
            )
        )
        output = {
            "ok": assessment.verdict == "advisory_qualified",
            "storage": {"inserted": inserted, "replayed": not inserted},
            "assessment": payload,
        }
    except (OSError, TypeError, ValueError, GiteaAPIError) as exc:
        output = {
            "ok": False,
            "error": {"code": "external_evidence_invalid", "detail": str(exc)[:500]},
        }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if output["ok"] else 1


def _read_identity_password(path_value: str) -> str:
    if not path_value:
        raise ValueError("--password-file is required")
    return _read_protected_secret_file(path_value, "password")


def _read_protected_secret_file(path_value: str, purpose: str) -> str:
    import stat

    if not path_value:
        raise ValueError(f"{purpose} file is required")
    path = Path(path_value).expanduser()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"{purpose} file cannot be opened safely") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"{purpose} file must be a regular file")
        if metadata.st_uid != os.geteuid():
            raise ValueError(f"{purpose} file must be owned by the current OS user")
        if metadata.st_mode & 0o077:
            raise ValueError(f"{purpose} file permissions must be 0600 or stricter")
        if metadata.st_size > 4096:
            raise ValueError(f"{purpose} file exceeds 4096 bytes")
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            descriptor = -1
            password = stream.read(4097).rstrip("\r\n")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not password:
        raise ValueError(f"{purpose} file is empty")
    return password


def _cmd_identity(args: argparse.Namespace) -> int:
    """Run the bounded local bootstrap/recovery path without starting providers."""

    import json
    import tempfile

    from samuel.adapters.auth.local import LocalIdentityService
    from samuel.adapters.state.sqlite import SQLiteStateStore, resolve_data_dir
    from samuel.core.config import FileConfig
    from samuel.core.identity import IdentityError
    from samuel.slices.audit_trail.bridge import log_event, set_jsonl_path

    config_dir = Path(args.config).expanduser().resolve()
    config = FileConfig(config_dir)
    output: dict[str, Any]
    try:
        data_dir = resolve_data_dir(
            config.get("agent.data_dir", "data"),
            config_dir=config_dir,
        )
        store = SQLiteStateStore(data_dir)
        set_jsonl_path(data_dir / "logs" / "agent.jsonl")

        def audit(event: str, actor: str, metadata: dict[str, Any]) -> None:
            log_event(
                event,
                "identity",
                event.replace("_", " "),
                trigger=actor,
                source="local_cli",
                meta={"actor": actor, **metadata},
            )

        service = LocalIdentityService(
            store.identity,
            instance_uuid=lambda: store.status().authority_instance,
            audit=audit,
        )
        if args.action == "status":
            payload: dict[str, Any] = {
                "status": service.status(),
                "principals": [
                    {
                        "principal_id": principal.principal_id,
                        "username": principal.username,
                        "kind": principal.kind,
                        "disabled": principal.disabled,
                        "roles": list(principal.roles),
                    }
                    for principal in service.list_principals()
                ],
            }
        elif args.action == "bootstrap":
            principal = service.bootstrap(
                args.username,
                _read_identity_password(args.password_file),
            )
            payload = {
                "status": service.status(),
                "principal_id": principal.principal_id,
                "username": principal.username,
                "roles": list(principal.roles),
            }
        elif args.action == "recover":
            if not args.reason.strip():
                raise ValueError("recover requires --reason")
            principal = service.recover(
                args.username,
                _read_identity_password(args.password_file),
                reason=args.reason.strip(),
            )
            payload = {
                "status": service.status(),
                "principal_id": principal.principal_id,
                "username": principal.username,
                "roles": list(principal.roles),
            }
        else:
            if not args.client_inventory_confirmed or not args.reason.strip():
                raise ValueError("cutover requires --client-inventory-confirmed and --reason")
            if service.status() != "active" or not any(
                not principal.disabled
                and principal.kind == "user"
                and "administrator" in principal.roles
                for principal in service.list_principals()
            ):
                raise ValueError("cutover requires an active local administrator")
            auth_path = config_dir / "auth.json"
            document = json.loads(auth_path.read_text(encoding="utf-8"))
            if not isinstance(document, dict) or document.get("access_mode") not in {
                "legacy_api_key",
                "local_identity",
            }:
                raise ValueError("auth configuration is invalid")
            already_local = document["access_mode"] == "local_identity"
            if not already_local:
                document["access_mode"] = "local_identity"
                encoded = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
                with store.lifecycle_lock(exclusive=True):
                    auth_path.parent.mkdir(parents=True, exist_ok=True)
                    with tempfile.NamedTemporaryFile(
                        mode="w",
                        encoding="utf-8",
                        dir=auth_path.parent,
                        prefix=f".{auth_path.name}.",
                        delete=False,
                    ) as temporary:
                        temporary.write(encoded)
                        temporary.flush()
                        os.fsync(temporary.fileno())
                        temporary_path = Path(temporary.name)
                    os.chmod(temporary_path, 0o600)
                    os.replace(temporary_path, auth_path)
                audit(
                    "identity_cutover",
                    f"os:{os.geteuid()}",
                    {"reason": args.reason.strip(), "client_inventory_confirmed": True},
                )
            payload = {
                "status": service.status(),
                "access_mode": "local_identity",
                "changed": not already_local,
            }
        output = {"ok": True, "identity": payload}
        code = 0
    except (IdentityError, OSError, ValueError, json.JSONDecodeError) as exc:
        error_code = exc.code if isinstance(exc, IdentityError) else "identity_command_invalid"
        output = {"ok": False, "error": {"code": error_code, "detail": str(exc)}}
        code = 1
    if args.json:
        print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))
    elif output["ok"]:
        print(json.dumps(output["identity"], ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(f"ERROR: {output['error']['code']}: {output['error']['detail']}", file=sys.stderr)
    return code


def _cmd_state(args: argparse.Namespace) -> int:
    """Inspect state without bootstrapping SCM, LLM or workflow handlers."""

    import json

    from samuel.adapters.state.sqlite import (
        SQLiteStateStore,
        audit_authority_high_watermark,
        resolve_data_dir,
    )
    from samuel.core.bootstrap import _build_scm_adapter, _load_dotenv
    from samuel.core.config import FileConfig, load_audit_config, load_scm_config
    from samuel.core.state import StateStoreError
    from samuel.core.workspaces import WorkspaceError

    config_dir = Path(args.config).expanduser().resolve()
    _load_dotenv(config_dir.parent / ".env")
    config = FileConfig(config_dir)
    try:
        data_dir = resolve_data_dir(
            config.get("agent.data_dir", "data"),
            config_dir=config_dir,
        )
        store = SQLiteStateStore(data_dir)
        audit_paths: list[Path] = []
        audit_epoch = 0
        if args.action in {"restore", "reconcile-complete"}:
            try:
                audit_config = load_audit_config(config_dir)
            except ValueError as exc:
                raise StateStoreError(
                    "state_audit_config_invalid",
                    "Audit configuration is required to determine the authority high-water mark",
                ) from exc
            for sink in audit_config.sinks:
                if sink.type != "jsonl":
                    continue
                candidate = Path(sink.path or "data/logs/agent.jsonl").expanduser()
                if not candidate.is_absolute():
                    candidate = config_dir.parent / candidate
                audit_paths.append(candidate.resolve(strict=False))
            audit_epoch = audit_authority_high_watermark(audit_paths)
        if args.action == "status":
            payload = store.status().as_dict()
        elif args.action == "dump":
            payload = store.dump()
        elif args.action == "reproject-runs":
            from samuel.core.bus import Bus
            from samuel.slices.run_projection.handler import RunProjectionHandler

            payload = RunProjectionHandler(Bus(), store.projections).reconcile_existing()
        elif args.action == "abandon-healing":
            if not args.observation_key or not args.reason.strip():
                raise StateStoreError(
                    "state_claim_arguments_required",
                    "abandon-healing requires --observation-key and --reason",
                )
            transition = store.authority.finish_healing(
                args.observation_key,
                status="abandoned",
                reason=args.reason.strip(),
            )
            payload = {
                "observation_key": args.observation_key,
                "status": "abandoned",
                "authority_epoch": transition.authority_epoch,
            }
        elif args.action == "restore":
            if not args.source:
                raise StateStoreError(
                    "state_restore_source_required",
                    "restore requires --source",
                )
            operation = store.restore(
                Path(args.source),
                audit_epoch=audit_epoch,
                supersede_operation_id=(args.supersede_operation_id or None),
                reason=(args.reason.strip() or None),
            )
            payload = {
                "operation_id": operation.operation_id,
                "status": operation.status,
                "scan_status": operation.scan_status,
                "source_digest": operation.source_digest,
                "restored_from_uuid": operation.restored_from_uuid,
                "instance_uuid": operation.instance_uuid,
                "pre_restore_epoch_highwater": operation.pre_restore_epoch_highwater,
                "supersedes_operation_id": operation.supersedes_operation_id,
            }
        else:
            from samuel.adapters.workspace.git import GitWorktreeManager, resolve_work_dir
            from samuel.slices.state_reconcile import StateReconcileCoordinator

            operation_id = args.operation_id or str(
                store.authority.authority_status().get("active_restore_operation") or ""
            )
            if not operation_id:
                raise StateStoreError(
                    "state_reconcile_operation_required",
                    "reconcile action requires --operation-id or one active restore",
                )
            manager = None
            scm = None
            if args.action == "reconcile-scan":
                manager = GitWorktreeManager(
                    resolve_work_dir(
                        config.get("agent.workspace.work_dir", "../samuel-workspaces"),
                        config_dir=config_dir,
                    ),
                    data_dir=data_dir,
                    reserve_bytes=int(config.get("agent.workspace.reserve_mebibytes", 128))
                    * 1024
                    * 1024,
                    minimum_free_bytes=int(
                        config.get("agent.workspace.minimum_free_mebibytes", 512)
                    )
                    * 1024
                    * 1024,
                    quarantine_max_count=int(config.get("agent.workspace.quarantine_max_count", 8)),
                    quarantine_max_bytes=int(
                        config.get("agent.workspace.quarantine_max_mebibytes", 2048)
                    )
                    * 1024
                    * 1024,
                    quarantine_retention_hours=int(
                        config.get("agent.workspace.quarantine_retention_hours", 168)
                    ),
                    git_timeout=int(config.get("agent.git.timeout", 30)),
                )
                try:
                    scm_config = load_scm_config()
                except ValueError as exc:
                    raise StateStoreError(
                        "state_reconcile_scm_unavailable",
                        "SCM configuration is required for reconcile scan",
                    ) from exc
                scm = _build_scm_adapter(
                    scm_config,
                    _configured_target_project(config_dir),
                    request_timeout=float(config.get("agent.network.timeout", 60)),
                )
            coordinator = StateReconcileCoordinator(
                authority_store=store.authority,
                workspace_manager=manager,
                scm=scm,
            )
            if args.action == "reconcile-status":
                payload = coordinator.status(operation_id)
            elif args.action == "reconcile-scan":
                payload = coordinator.scan(operation_id)
            elif args.action == "reconcile-classify":
                if (
                    not args.object_type
                    or not args.object_key
                    or not args.classification
                    or not args.reason.strip()
                ):
                    raise StateStoreError(
                        "state_reconcile_arguments_required",
                        "reconcile-classify requires object identity, classification and reason",
                    )
                payload = coordinator.classify(
                    operation_id,
                    args.object_type,
                    args.object_key,
                    classification=args.classification,
                    reason=args.reason.strip(),
                )
            else:
                payload = coordinator.complete(operation_id, audit_epoch=audit_epoch)
        if args.action in {"status", "dump"}:
            status_payload = payload["status"] if args.action == "dump" else payload
            authority = status_payload.get("authority", {})
            checkpoints = store.authority.list_checkpoints()
            projections = store.projections.list_projections(series="resume")
            resume_payload = {
                "enabled": bool(config.get("agent.resume.enabled", False))
                and not bool(authority.get("reconcile_required")),
                "configured": bool(config.get("agent.resume.enabled", False)),
                "reconcile_required": bool(authority.get("reconcile_required")),
                "pending": sum(1 for row in checkpoints if row.resume_eligible),
                "blocked": sum(
                    1
                    for row in checkpoints
                    if row.boundary in {"blocked", "abandoned"}
                    or str(row.payload.get("resume_status", "")) in {"blocked", "abandoned"}
                ),
                "last_outcome": (dict(projections[-1].payload) if projections else {}),
            }
            payload["resume"] = resume_payload
            authority["resume_enabled"] = resume_payload["enabled"]
            authority["resume_pending"] = resume_payload["pending"]
            authority["resume_blocked"] = resume_payload["blocked"]
            authority["resume_last_outcome"] = resume_payload["last_outcome"]
        result = {"action": args.action, "ok": True, "state": payload}
        exit_code = 0
    except (StateStoreError, WorkspaceError) as exc:
        result = {
            "action": args.action,
            "ok": False,
            "error": {"code": exc.code, "message": exc.safe_message},
        }
        exit_code = 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    elif result["ok"]:
        state = result["state"]
        if args.action == "abandon-healing":
            print(
                f"Healing claim {state['observation_key']}: abandoned "
                f"(authority epoch {state['authority_epoch']})"
            )
        elif args.action in {"status", "dump"}:
            status = state["status"] if args.action == "dump" else state
            authority = status.get("authority", {})
            if authority.get("reconcile_required", False):
                print(
                    f"State: reconcile required (schema {status['schema_version']}, "
                    f"reason {authority.get('reconcile_reason') or 'unknown'})"
                )
            else:
                print(f"State: healthy (schema {status['schema_version']})")
            print(f"  path: {status['path']}")
            print(f"  filesystem: {status['filesystem']['type']} ({status['filesystem']['mount']})")
            print(f"  journal: {status['journal_mode']}, vacuum: {status['auto_vacuum']}")
            print(
                f"  authority: epoch {authority.get('epoch', 0)}, "
                f"witness {authority.get('witness_epoch', -1)}, "
                f"resume {'enabled' if authority.get('resume_enabled', False) else 'disabled'}"
            )
        else:
            print(f"State {args.action}: {state}")
    else:
        error = result["error"]
        print(f"State: unhealthy ({error['code']}): {error['message']}", file=sys.stderr)
    return exit_code


def _cmd_workspace(args: argparse.Namespace) -> int:
    """Inspect workspace state without bootstrapping SCM or LLM handlers."""

    import json

    from samuel.adapters.state.sqlite import resolve_data_dir
    from samuel.adapters.workspace.git import GitWorktreeManager, resolve_work_dir
    from samuel.core.config import FileConfig
    from samuel.core.workspaces import WorkspaceError

    config_dir = Path(args.config).expanduser().resolve()
    config = FileConfig(config_dir)
    try:
        data_dir = resolve_data_dir(config.get("agent.data_dir", "data"), config_dir=config_dir)
        manager = GitWorktreeManager(
            resolve_work_dir(
                config.get("agent.workspace.work_dir", "../samuel-workspaces"),
                config_dir=config_dir,
            ),
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
        )
        if args.action == "list":
            payload: Any = [record.as_dict() for record in manager.list_workspaces()]
        elif args.action == "inspect":
            if not args.workspace_id:
                raise WorkspaceError(
                    "workspace_id_required",
                    "inspect requires a workspace identity",
                )
            record = manager.inspect(args.workspace_id)
            if record is None:
                raise WorkspaceError("workspace_missing", "Workspace identity was not found")
            payload = record.as_dict()
        elif args.action == "quarantine":
            if not args.workspace_id or not args.reason.strip():
                raise WorkspaceError(
                    "workspace_quarantine_arguments_required",
                    "quarantine requires a workspace identity and --reason",
                )
            manager.quarantine(args.workspace_id, reason=args.reason.strip())
            record = manager.inspect(args.workspace_id)
            payload = record.as_dict() if record is not None else {}
        elif args.action == "discard":
            if not args.workspace_id or not args.reason.strip():
                raise WorkspaceError(
                    "workspace_discard_arguments_required",
                    "discard requires a workspace identity and --reason",
                )
            manager.discard_quarantine(args.workspace_id, reason=args.reason.strip())
            record = manager.inspect(args.workspace_id)
            payload = record.as_dict() if record is not None else {}
        else:
            payload = manager.prune()
        result = {"action": args.action, "ok": True, "workspace": payload}
        exit_code = 0
    except WorkspaceError as exc:
        result = {
            "action": args.action,
            "ok": False,
            "error": {"code": exc.code, "message": exc.safe_message},
        }
        exit_code = 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    elif result["ok"]:
        print(f"Workspace {args.action}: {result['workspace']}")
    else:
        error = result["error"]
        print(f"Workspace: unhealthy ({error['code']}): {error['message']}", file=sys.stderr)
    return exit_code


def _cmd_retention(args: argparse.Namespace) -> int:
    """Run retention operations without SCM/LLM bootstrap or a scheduler."""

    import json
    from datetime import datetime

    from samuel.adapters.state.sqlite import SQLiteStateStore, resolve_data_dir
    from samuel.adapters.workspace.git import read_workspace_registry, resolve_work_dir
    from samuel.core.config import FileConfig, load_audit_config, load_eval_config
    from samuel.core.retention import RetentionError, RetentionPolicyConfig
    from samuel.core.state import StateStoreError
    from samuel.core.workspaces import WorkspaceError
    from samuel.slices.evaluation.replay import ScoreReplay
    from samuel.slices.privacy.retention import RetentionCoordinator, create_managed_backup

    config_dir = Path(args.config).expanduser().resolve()
    config = FileConfig(config_dir)
    try:
        data_dir = resolve_data_dir(config.get("agent.data_dir", "data"), config_dir=config_dir)
        store = SQLiteStateStore(data_dir)
        policy = RetentionPolicyConfig.load(
            config_dir / "privacy.json", project_root=config_dir.parent
        )
        audit_files: list[Path] = []
        for sink in load_audit_config(config_dir).sinks:
            if sink.type != "jsonl":
                continue
            base = Path(sink.path or "data/logs/agent.jsonl").expanduser()
            if not base.is_absolute():
                base = config_dir.parent / base
            audit_files.extend(sorted(base.parent.glob(f"{base.stem}*{base.suffix or '.jsonl'}")))

        workspaces = []
        if args.action == "dry-run":
            workspaces = read_workspace_registry(
                resolve_work_dir(
                    config.get("agent.workspace.work_dir", "../samuel-workspaces"),
                    config_dir=config_dir,
                )
            )

        coordinator = RetentionCoordinator(
            policy=policy,
            state=store.retention,
            authority=store.authority,
            execution=store.retention_execution,
            audit_files=audit_files,
            workspaces=workspaces,
        )
        if args.action == "dry-run":
            payload: Any = coordinator.dry_run()
        elif args.action == "approve":
            if not args.category:
                raise RetentionError(
                    "retention_approval_category_required",
                    "Retention approval requires --category",
                )
            payload = coordinator.approve(args.category, reason=args.reason)
        elif args.action in {"activate", "execute"}:
            if not args.category or not args.plan_digest or not args.cutoff_utc:
                raise RetentionError(
                    "retention_execution_arguments_required",
                    "Retention activation and execution require --category, --plan-digest and --cutoff-utc",
                )
            normalized_cutoff = args.cutoff_utc.strip().replace("Z", "+00:00")
            try:
                cutoff = datetime.fromisoformat(normalized_cutoff)
            except ValueError as exc:
                raise RetentionError(
                    "retention_timestamp_invalid",
                    "Retention cutoff must be an ISO-8601 timestamp",
                ) from exc
            if cutoff.tzinfo is None or cutoff.utcoffset() is None:
                raise RetentionError(
                    "retention_timestamp_invalid",
                    "Retention cutoff must include a timezone",
                )
            if args.action == "activate":
                payload = coordinator.activate(
                    args.category,
                    plan_digest=args.plan_digest,
                    cutoff_utc=cutoff,
                    reason=args.reason,
                )
            else:
                payload = coordinator.execute(
                    args.category,
                    plan_digest=args.plan_digest,
                    cutoff_utc=cutoff,
                    reason=args.reason,
                )
        elif args.action == "suspend":
            if not args.category:
                raise RetentionError(
                    "retention_category_required",
                    "Retention suspension requires --category",
                )
            payload = coordinator.suspend(args.category, reason=args.reason)
        elif args.action in {"pause", "unpause"}:
            payload = coordinator.set_emergency_stop(
                args.action == "pause",
                reason=args.reason,
            )
        elif args.action == "backup":
            backup = create_managed_backup(
                policy=policy,
                diagnostics=store,
                state=store.retention,
            )
            payload = {
                "backup_id": backup.backup_id,
                "path": str(backup.path),
                "digest": backup.digest,
                "instance_uuid": backup.instance_uuid,
                "authority_epoch": backup.authority_epoch,
                "created_at": backup.created_at.isoformat(),
            }
        else:
            replay_config_dirs = [
                Path(value).expanduser().resolve() for value in args.eval_config_dir
            ] or [config_dir]
            payload = ScoreReplay(
                store.observations,
                [load_eval_config(directory) for directory in replay_config_dirs],
            ).replay(issue_number=args.issue)
        result = {"action": args.action, "ok": True, "retention": payload}
        exit_code = 0
    except (RetentionError, StateStoreError, WorkspaceError, ValueError) as exc:
        code = getattr(exc, "code", "retention_invalid")
        message = getattr(exc, "safe_message", str(exc))
        result = {
            "action": args.action,
            "ok": False,
            "error": {"code": code, "message": message},
        }
        exit_code = 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    elif result["ok"]:
        print(f"Retention {args.action}: {result['retention']}")
    else:
        error = result["error"]
        print(f"Retention: unhealthy ({error['code']}): {error['message']}", file=sys.stderr)
    return exit_code


def _cmd_resume(bus: Bus, args: argparse.Namespace) -> int:
    """Operate only on restart-persistent, bound finalization checkpoints."""

    import json

    from samuel.core.commands import ResumePendingCommand
    from samuel.core.state import StateStoreError
    from samuel.core.workspaces import WorkspaceError

    coordinator = getattr(bus, "resume_coordinator", None)
    try:
        if coordinator is None:
            raise StateStoreError(
                "resume_coordinator_unavailable",
                "The bound resume coordinator is not available",
            )
        if args.action == "list":
            payload: Any = {
                "status": coordinator.status(),
                "checkpoints": coordinator.list(),
            }
        elif args.action == "inspect":
            if not args.checkpoint_key:
                raise StateStoreError(
                    "resume_checkpoint_key_required",
                    "inspect requires a checkpoint identity",
                )
            payload = coordinator.inspect(args.checkpoint_key)
        elif args.action in {"attempt", "resume"}:
            payload = bus.send(
                ResumePendingCommand(
                    payload={"checkpoint_key": args.checkpoint_key, "source": "operator"}
                )
            )
        elif args.action == "abandon":
            if not args.checkpoint_key or not args.reason.strip():
                raise StateStoreError(
                    "resume_abandon_arguments_required",
                    "abandon requires a checkpoint identity and --reason",
                )
            payload = coordinator.abandon(args.checkpoint_key, reason=args.reason)
        else:
            if not args.checkpoint_key or not args.reason.strip():
                raise StateStoreError(
                    "resume_cleanup_arguments_required",
                    "cleanup requires a checkpoint identity and --reason",
                )
            payload = coordinator.cleanup(args.checkpoint_key, reason=args.reason)
        result = {"action": args.action, "ok": True, "resume": payload}
        exit_code = 0
        if args.action in {"attempt", "resume"} and isinstance(payload, dict):
            if int(payload.get("blocked", 0)) > 0:
                exit_code = 1
    except (StateStoreError, WorkspaceError) as exc:
        result = {
            "action": args.action,
            "ok": False,
            "error": {"code": exc.code, "message": exc.safe_message},
        }
        exit_code = 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    elif result["ok"]:
        print(f"Resume {args.action}: {result['resume']}")
    else:
        error = result["error"]
        print(f"Resume: blocked ({error['code']}): {error['message']}", file=sys.stderr)
    return exit_code


def _cmd_setup_labels(bus: Bus, args: argparse.Namespace) -> int:
    from samuel.slices.setup.handler import SetupHandler

    scm = getattr(bus, "scm", None)
    if scm is None:
        print("SCM adapter not available — check SCM_URL/SCM_TOKEN/SCM_REPO")
        return 1

    handler = SetupHandler(bus, project_root=Path(args.config).parent.resolve(), scm=scm)
    result = handler.sync_labels(Path(args.config) / "labels.json")

    total = result.get("total", 0)
    created = result.get("created", [])
    skipped = result.get("skipped", [])
    errors = result.get("errors", [])

    print(
        f"Labels sync: {len(created)} created, {len(skipped)} existing, {len(errors)} errors (of {total})"
    )
    for name in created:
        print(f"  + {name}")
    for name in skipped:
        print(f"  = {name}")
    for err in errors:
        print(f"  ! {err}")

    if not result.get("synced"):
        err = result.get("error")
        if err:
            print(f"Error: {err}")
        return 1
    return 0


def _cmd_refresh_pricing(bus: Bus, _args: argparse.Namespace) -> int:
    """#311: OpenRouter-Modell-Cache aktualisieren (350+ Modelle mit Preisen)."""
    from samuel.adapters.llm.costs import refresh_pricing

    result = refresh_pricing(config=bus.config)
    if result.get("error"):
        print(f"Fehler: {result['error']}")
        return 1
    import datetime as _dt

    fetched_at = _dt.datetime.fromtimestamp(result.get("fetched_at", 0)).isoformat()
    print(f"OpenRouter-Cache aktualisiert: {result.get('count', 0)} Modelle ({fetched_at})")
    benchmark_error = result.get("benchmark_error")
    if benchmark_error:
        print(f"Benchmarks nicht aktualisiert: {benchmark_error}")
    else:
        print(f"Benchmarks aktualisiert: {result.get('benchmark_count', 0)} Modelle")
    return 0


def _cmd_changelog(bus: Bus, args: argparse.Namespace) -> int:
    """#163: Generate a changelog from git log between a start-rev and HEAD.

    Resolves the start-rev in this order:
    1. ``--phase=N`` -> tag ``phase-N-complete``
    2. ``--since=<rev>`` (literal)
    3. highest canonical product tag reachable from HEAD
    Then aggregates conventional-commit subjects and dispatches a
    ``ChangelogCommand`` so the existing handler renders + optionally posts.
    """
    from samuel.core.commands import ChangelogCommand
    from samuel.slices.changelog.aggregate import (
        aggregate_from_git,
        latest_tag,
        phase_tag,
    )

    project_root = Path(args.config).resolve().parent

    if args.phase is not None:
        since_rev = phase_tag(args.phase)
    elif args.since:
        since_rev = args.since
    else:
        since_rev = latest_tag(project_root)
        if not since_rev:
            print(
                "Kein Produkt-Tag gefunden. Nutze --since=<rev> oder --phase=<n>.",
                file=sys.stderr,
            )
            return 1

    entries = aggregate_from_git(project_root, since_rev=since_rev)
    if not entries:
        print(
            f"Keine Changelog-Eintraege seit {since_rev} "
            "(Commits muessen Format 'feat: ... (#NNN)' haben).",
            file=sys.stderr,
        )
        return 1

    payload: dict[str, Any] = {"entries": entries}
    if args.post_to_issue is not None:
        payload["post_to_issue"] = args.post_to_issue

    result = bus.send(ChangelogCommand(payload=payload))
    if not result or not result.get("generated"):
        print("Changelog konnte nicht generiert werden.", file=sys.stderr)
        return 1

    body = result.get("changelog", "")
    if args.out:
        Path(args.out).write_text(body, encoding="utf-8")
        print(
            f"Changelog geschrieben: {args.out} "
            f"({result.get('entry_count')} Eintraege seit {since_rev})",
            file=sys.stderr,
        )
    else:
        print(body)
    return 0


def _resolve_dashboard_bind(arg_host: str | None, arg_port: int | None) -> tuple[str, int]:
    """#402: CLI-Flag > Env (DASHBOARD_HOST/PORT, vom setup-Wizard geschrieben)
    > Default. Ungueltiger Env-Port faellt auf 7777 zurueck."""
    host = arg_host or os.environ.get("DASHBOARD_HOST") or "0.0.0.0"
    if arg_port:
        return host, int(arg_port)
    try:
        return host, int(os.environ.get("DASHBOARD_PORT", "7777"))
    except ValueError:
        return host, 7777


def _dashboard_display_host(bind_host: str) -> str:
    """Return a browser target for a server wildcard bind (#421).

    ``0.0.0.0``/``::`` describe where the server listens, not where a browser
    can navigate. Prefer the address selected by the host's IPv4 route and
    fall back to localhost when no usable LAN route is available.
    """
    if bind_host not in {"", "0.0.0.0", "::"}:
        return f"[{bind_host}]" if ":" in bind_host and not bind_host.startswith("[") else bind_host

    import ipaddress
    import socket

    candidates: list[str] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            # UDP connect selects a route without sending application data.
            sock.connect(("192.0.2.1", 9))
            candidates.append(str(sock.getsockname()[0]))
    except OSError:
        pass
    with contextlib.suppress(OSError):
        candidates.append(socket.gethostbyname(socket.gethostname()))
    for candidate in candidates:
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if address.version == 4 and not address.is_unspecified and not address.is_loopback:
            return candidate
    return "127.0.0.1"


def _cmd_dashboard(bus: Bus, args: argparse.Namespace) -> int:
    from samuel.server import create_server

    host, port = _resolve_dashboard_bind(args.host, args.port)

    server = create_server(
        bus,
        host=host,
        port=port,
        scm=getattr(bus, "scm", None),
        config=getattr(bus, "config", None),
        configuration_mode=args.configuration_mode,
    )
    display_host = _dashboard_display_host(host)
    bound_port = int(server.server_address[1])
    log.info("Dashboard: http://%s:%d/", display_host, bound_port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _make_signal_handler(
    hard_exit: Callable[[int], NoReturn] | None = None,
) -> Callable[[int, FrameType | None], None]:
    """Create the two-stage process signal handler used by long-running CLI modes.

    The first signal unwinds blocking loops through ``KeyboardInterrupt`` so
    their ``finally`` blocks can close sockets and flush audit data. A second
    signal is the explicit emergency exit requested by #420.
    """
    if hard_exit is None:
        hard_exit = os._exit
    signal_count = 0

    def _signal_handler(signum: int, _frame: FrameType | None) -> None:
        nonlocal signal_count
        signal_count += 1
        sig_name = signal.Signals(signum).name
        if signal_count >= 2:
            log.error("Zweites Signal %s empfangen, erzwinge Prozessende", sig_name)
            hard_exit(128 + signum)
            return
        log.info("Signal %s empfangen, fahre herunter...", sig_name)
        raise KeyboardInterrupt

    return _signal_handler


# ---------------------------------------------------------------------------
# Installer: CLI-Setup-Wizard + Doctor (Etappe 1)
# ---------------------------------------------------------------------------


def _box(title: str, lines: list[str], w: int = 66) -> None:
    inner = w - 4
    hr = "═" * (w - 2)
    print(f"\n╔{hr}╗")
    print(f"║  {title:<{inner}}║")
    print(f"╠{hr}╣")
    for ln in lines:
        print(f"║  {ln:<{inner}}║")
    print(f"╚{hr}╝\n")


def _ask(prompt: str, default: str = "") -> str:
    disp = f" [{default}]" if default else ""
    try:
        val = input(f"  {prompt}{disp}: ").strip()
    except EOFError:
        val = ""
    return val or default


def _normalize_url(url: str) -> str:
    url = url.strip()
    if url and not url.startswith(("http://", "https://")):
        url = "http://" + url
    return url.rstrip("/")


def _scm_probe(
    provider: str,
    url: str,
    token: str,
    repo: str = "",
    *,
    branch_protection_token: str | None = None,
) -> dict:
    """Live-Verbindungstest gegen das SCM. Ist ``repo`` bekannt, wird der
    Repo-Endpoint geprueft (braucht nur ``repo``-Scope) — sonst ``/user``.

    Nuance: HTTP 401 = ungueltiger Token/URL (Fehler). HTTP 403 gegen ``/user``
    = Token gueltig, aber ohne ``user``-Scope → als OK gewertet (der Token
    funktioniert, nur dieser Endpoint braucht mehr Rechte)."""
    import json
    import urllib.error
    import urllib.request

    if not (url and token):
        return {"ok": False, "detail": "URL/Token fehlt"}
    from samuel.adapters.github.adapter import normalize_github_api_url

    base = normalize_github_api_url(url) if provider == "github" else f"{url.rstrip('/')}/api/v1"
    api = f"{base}/repos/{repo}" if repo else f"{base}/user"
    try:
        req = urllib.request.Request(api, headers={"Authorization": f"token {token}"})
        with urllib.request.urlopen(req, timeout=8) as r:  # noqa: S310
            data = json.loads(r.read())
        if repo:
            result = {"ok": True, "detail": f"Repo {data.get('full_name', repo)} erreichbar"}
            if provider in {"gitea", "github"}:
                result["branch_protection"] = _branch_protection_probe(
                    provider,
                    url,
                    branch_protection_token or token,
                    repo,
                    str(data.get("default_branch") or "main"),
                    protected=branch_protection_token is not None,
                )
            return result
        return {"ok": True, "detail": f"eingeloggt als {data.get('login', '?')}"}
    except urllib.error.HTTPError as exc:
        if exc.code == 403 and not repo:
            return {"ok": True, "detail": "Token gueltig (Endpoint ohne user-Scope)"}
        return {"ok": False, "detail": f"HTTP {exc.code}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": f"SCM-Probe fehlgeschlagen ({type(exc).__name__})"}


def _gitea_branch_protection_probe(
    url: str,
    token: str,
    repo: str,
    branch: str,
) -> dict[str, Any]:
    return _branch_protection_probe("gitea", url, token, repo, branch)


def _branch_protection_probe(
    provider: str,
    url: str,
    token: str,
    repo: str,
    branch: str,
    *,
    protected: bool = False,
) -> dict[str, Any]:
    """Read native SCM rules through the existing provider clients.

    Normal runtime work and this operator rule-read are separate capabilities.
    A denied read alone does not identify the missing token scope or role.
    The probe keeps
    SCM connectivity separate from release readiness; ``build_doctor_report``
    evaluates missing access or a deviating rule fail-closed (#423, #528).
    """
    import urllib.error
    import urllib.parse
    import urllib.request

    from samuel.adapters.auth.static_token import StaticTokenAuth
    from samuel.adapters.gitea.api import GiteaAPI, GiteaAPIError
    from samuel.adapters.github.adapter import normalize_github_api_url
    from samuel.adapters.github.api import GitHubAPI, GitHubAPIError

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
            raise urllib.error.HTTPError(req.full_url, code, "redirect rejected", headers, fp)

    safe_branch = urllib.parse.quote(branch, safe="")
    repo_parts = repo.split("/")
    if len(repo_parts) != 2 or any(not part or part in {".", ".."} for part in repo_parts):
        return {"access": "unknown", "detail": "ungueltiges Zielrepository"}
    safe_repo = "/".join(urllib.parse.quote(part, safe="") for part in repo_parts)
    try:
        opener = urllib.request.build_opener(NoRedirect()) if protected else None
        auth = StaticTokenAuth(token)
        if provider == "github":
            client = GitHubAPI(
                auth, base_url=normalize_github_api_url(url), timeout=8, opener=opener
            )
            rules = client.request("GET", f"/repos/{safe_repo}/branches/{safe_branch}/protection")
        else:
            rules = GiteaAPI(url, auth, timeout=8, opener=opener).request(
                "GET", f"/repos/{safe_repo}/branch_protections/{safe_branch}"
            )
        if not isinstance(rules, dict):
            return {"access": "unknown", "detail": "ungueltige Regelantwort"}
        return {
            "access": "ok",
            "configured": True,
            "branch": branch,
            "rules": rules,
            "detail": f"Regeln fuer {branch} lesbar",
        }
    except (GiteaAPIError, GitHubAPIError) as exc:
        if exc.status == 403:
            return {
                "access": "restricted",
                "detail": "Branchschutz-Read abgewiesen (HTTP 403); Operator prueft gezielt Endpoint und Credential. Erforderliches Mindestrecht unbekannt.",
            }
        if exc.status == 404:
            return {
                "access": "ok",
                "configured": False,
                "branch": branch,
                "detail": f"Keine Regel fuer {branch} konfiguriert",
            }
        return {"access": "unknown", "detail": f"HTTP {exc.status} beim Branchschutz-Read"}
    except Exception as exc:  # noqa: BLE001
        return {
            "access": "unknown",
            "detail": f"Branchschutz-Read fehlgeschlagen ({type(exc).__name__})",
        }


def _list_gitea_repos(url: str, token: str, limit: int = 15) -> list[str]:
    import json
    import urllib.request

    try:
        req = urllib.request.Request(
            f"{url.rstrip('/')}/api/v1/repos/search?limit={limit}&sort=updated",
            headers={"Authorization": f"token {token}"},
        )
        with urllib.request.urlopen(req, timeout=8) as r:  # noqa: S310
            return [x["full_name"] for x in json.loads(r.read()).get("data", [])]
    except Exception as exc:  # noqa: BLE001
        log.warning("Gitea repository list unavailable: %s", type(exc).__name__)
        return []


def _detect_timezone() -> str:
    try:
        p = Path("/etc/timezone")
        if p.exists():
            return p.read_text(encoding="utf-8").strip() or "UTC"
    except OSError:
        pass
    try:
        link = os.readlink("/etc/localtime")
        if "zoneinfo/" in link:
            return link.split("zoneinfo/", 1)[1]
    except OSError:
        pass
    return "UTC"


def _write_agent_timezone(config_dir: Path, tz: str) -> None:
    import json

    p = config_dir / "agent.json"
    data: dict = {}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    data["timezone"] = tz
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _cmd_doctor(args: argparse.Namespace) -> int:
    from samuel.slices.setup.env_io import build_doctor_report, parse_env

    config_dir = Path(args.config).resolve()
    env_path = Path(".env")
    dotenv = parse_env(env_path.read_text(encoding="utf-8")) if env_path.exists() else {}

    def get(key: str) -> str | None:
        if key in os.environ:
            return os.environ[key]
        return dotenv.get(key)

    scm_probe = None
    scm_url = get("SCM_URL")
    scm_token = get("SCM_TOKEN")
    branch_token = None
    token_file = getattr(args, "branch_protection_token_file", "")
    if token_file:
        try:
            branch_token = _read_protected_secret_file(token_file, "branch protection token")
            if any(c.isspace() for c in branch_token):
                raise ValueError("branch protection token must not contain whitespace")
        except (ValueError, OSError, UnicodeError) as exc:
            print(f"Doctor: {exc}", file=sys.stderr)
            return 1
    if scm_url and scm_token:
        scm_probe = _scm_probe(
            get("SCM_PROVIDER") or "gitea",
            scm_url,
            scm_token,
            repo=get("SCM_REPO") or "",
            branch_protection_token=branch_token,
        )

    checks = build_doctor_report(get, config_dir, scm_probe)
    icons = {"ok": "✅", "warn": "⚠️ ", "fail": "❌"}
    print("\n" + "═" * 66)
    print("  S.A.M.U.E.L. — Doctor")
    print("═" * 66)
    print(f"  Produktversion                      {__build_info__.product_version}")
    revision = __build_info__.revision or "nicht verfügbar"
    dirty = " (dirty)" if __build_info__.dirty else ""
    print(f"  Build-Revision                      {revision}{dirty}")
    for c in checks:
        print(f"  {icons.get(c['status'], '? ')} {c['name']:<34} {c['detail']}")
        if c.get("fix") and c["status"] != "ok":
            print(f"        → {c['fix']}")
    n_ok = sum(c["status"] == "ok" for c in checks)
    n_warn = sum(c["status"] == "warn" for c in checks)
    n_fail = sum(c["status"] == "fail" for c in checks)
    print("─" * 66)
    print(f"  ✅ {n_ok}   ⚠️  {n_warn}   ❌ {n_fail}\n")
    _record_doctor_qualification(
        config_dir,
        status="failed" if n_fail else "passed",
        summary={
            "checks": len(checks),
            "passed": n_ok,
            "warnings": n_warn,
            "failed": n_fail,
            "failed_checks": [str(c["name"]) for c in checks if c["status"] == "fail"],
        },
    )
    return 1 if n_fail else 0


def _record_doctor_qualification(
    config_dir: Path,
    *,
    status: str,
    summary: dict[str, Any],
) -> None:
    """Record doctor evidence only when the runtime state already exists."""

    from samuel.adapters.state.sqlite import DATABASE_FILENAME, SQLiteStateStore, resolve_data_dir
    from samuel.core.config import FileConfig
    from samuel.core.health_projection import record_projection

    try:
        config = FileConfig(config_dir)
        data_dir = resolve_data_dir(config.get("agent.data_dir", "data"), config_dir=config_dir)
        if not (data_dir / DATABASE_FILENAME).is_file():
            return
        state = SQLiteStateStore(data_dir)
        record_projection(
            state.projections,
            kind="doctor",
            status=status,
            instance_uuid=state.status().authority_instance,
            summary=summary,
        )
    except Exception as exc:  # noqa: BLE001 - doctor result remains authoritative
        log.warning("Doctor qualification projection unavailable: %s", type(exc).__name__)


def _cmd_setup(args: argparse.Namespace) -> int:
    import secrets as _secrets

    from samuel.core.config import (
        DEFAULT_SCM_REQUIRED_STATUS_CONTEXT,
        resolve_scm_required_status_context,
    )
    from samuel.slices.setup.env_io import merge_env, parse_env

    config_dir = Path(args.config).resolve()
    env_path = Path(".env")
    prefill = parse_env(env_path.read_text(encoding="utf-8")) if env_path.exists() else {}
    nonint = getattr(args, "non_interactive", False)

    def field(prompt: str, key: str, fallback: str = "") -> str:
        """Wert beziehen: non-interaktiv aus .env/Env/Fallback, sonst per Prompt.
        Macht den Wizard scriptbar (install.sh / Docker / CI)."""
        default = prefill.get(key) or os.environ.get(key) or fallback
        return default if nonint else _ask(prompt, default)

    try:
        if not nonint:
            _box(
                "S.A.M.U.E.L. — Setup-Wizard",
                [
                    "Richtet die Basis ein: SCM-Verbindung, Verzeichnisse,",
                    "Sicherheit, Workflow-Labels.",
                    "LLM-Provider werden danach im Dashboard konfiguriert.",
                    "",
                    "Abbrechen jederzeit mit Strg+C.",
                ],
            )
            _box(
                "Schritt 1/4 — SCM-Verbindung",
                [
                    "URL, Benutzer und API-Token (Gitea oder GitHub).",
                    "Token-Rechte: issue R+W · repository R+W · user R",
                ],
            )

        # Schritt 1 — SCM
        provider = (field("Provider (gitea/github)", "SCM_PROVIDER", "gitea") or "gitea").lower()
        url = _normalize_url(field("SCM URL", "SCM_URL"))
        user = field("Benutzername", "SCM_USER")
        token = field("API-Token", "SCM_TOKEN")
        while True:
            res = _scm_probe(provider, url, token)
            if res["ok"]:
                print(f"  ✅ Verbindung OK — {res['detail']}\n")
                break
            print(f"  ❌ Verbindungsfehler: {res['detail']}")
            if nonint or _ask("Erneut versuchen? (j/n)", "j").lower() not in ("j", "y", ""):
                print("  ⚠️  Fortfahren trotz Fehler.\n")
                break
            url = _normalize_url(_ask("SCM URL", url))
            user = _ask("Benutzername", user)
            token = _ask("API-Token", token)

        # Schritt 2 — Repository + Bot-User
        if not nonint:
            _box(
                "Schritt 2/4 — Repository",
                [
                    "Welches Repo soll SAMUEL ueberwachen? Format: owner/name",
                ],
            )
            if provider == "gitea" and url and token:
                repos = _list_gitea_repos(url, token)
                if repos:
                    print("  Verfuegbare Repositories:")
                    for r in repos[:12]:
                        print(f"    • {r}")
                    print()
        repo = field("Repository (owner/name)", "SCM_REPO").strip().strip("`'\"")
        bot = field("Bot-User (Akteur-Zuordnung im Activity-Tab)", "SCM_BOT_USER", user)
        required_status_context_raw = field(
            "Erwarteter Required Check",
            "SCM_REQUIRED_STATUS_CONTEXT",
            DEFAULT_SCM_REQUIRED_STATUS_CONTEXT,
        )
        try:
            required_status_context, _source = resolve_scm_required_status_context(
                lambda _key: required_status_context_raw
            )
        except ValueError as exc:
            print(f"  ❌ Ungueltiger Required Check: {exc}\n")
            return 1

        # Schritt 3 — Zielprojekt / Verzeichnisse
        if not nonint:
            _box(
                "Schritt 3/4 — Zielprojekt",
                [
                    "PROJECT_ROOT = lokaler Pfad des ueberwachten Projekts.",
                    "Leer lassen, wenn SAMUEL im Projekt selbst laeuft.",
                ],
            )
        project_root = field("PROJECT_ROOT (optional)", "PROJECT_ROOT")

        # Schritt 4 — Sicherheit, Zeitzone, Dashboard
        if not nonint:
            _box(
                "Schritt 4/4 — Sicherheit & Dashboard",
                [
                    "HMAC-/API-Schluessel werden automatisch generiert (falls leer).",
                ],
            )
        hmac_key = (
            prefill.get("SLICE_HMAC_KEY")
            or os.environ.get("SLICE_HMAC_KEY")
            or _secrets.token_hex(32)
        )
        api_key = (
            prefill.get("SAMUEL_API_KEY")
            or os.environ.get("SAMUEL_API_KEY")
            or _secrets.token_hex(24)
        )
        audit_key = (
            prefill.get("SAMUEL_AUDIT_HMAC_KEY")
            or os.environ.get("SAMUEL_AUDIT_HMAC_KEY")
            or _secrets.token_hex(32)
        )
        tz = field("Zeitzone (IANA)", "TZ", _detect_timezone())
        try:
            from zoneinfo import ZoneInfo

            ZoneInfo(tz)
        except Exception:  # noqa: BLE001
            print(f"  ⚠️  '{tz}' unbekannt — verwende UTC.")
            tz = "UTC"
        port = field("Dashboard-Port", "DASHBOARD_PORT", "7777")

        # .env schreiben (merge, chmod 600)
        updates = {
            "SCM_PROVIDER": provider,
            "SCM_URL": url,
            "SCM_USER": user,
            "SCM_TOKEN": token,
            "SCM_REPO": repo,
            "SCM_BOT_USER": bot,
            "SCM_REQUIRED_STATUS_CONTEXT": required_status_context,
            "SLICE_HMAC_KEY": hmac_key,
            "SAMUEL_API_KEY": api_key,
            "SAMUEL_AUDIT_HMAC_KEY": audit_key,
            "DASHBOARD_PORT": port,
        }
        if project_root:
            updates["PROJECT_ROOT"] = project_root
        existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
        env_path.write_text(merge_env(existing, updates), encoding="utf-8")
        with contextlib.suppress(OSError):
            env_path.chmod(0o600)
        print(f"  ✅ .env geschrieben: {env_path.resolve()} (chmod 600)\n")

        _write_agent_timezone(config_dir, tz)

        # Verzeichnisse anlegen
        from samuel.core.bus import Bus
        from samuel.slices.setup.handler import SetupHandler

        sh = SetupHandler(Bus(), project_root=config_dir.parent)
        created = sh.ensure_directories()
        if created:
            print(f"  ✅ Verzeichnisse angelegt: {', '.join(created)}\n")

        # Labels anlegen (neue .env laden → SCM bauen)
        _load_env_file(env_path, override=True)
        if provider == "gitea" and repo and url and token:
            print("  Lege Workflow-Labels an ...")
            try:
                from samuel.adapters.auth.static_token import StaticTokenAuth
                from samuel.adapters.gitea.adapter import GiteaAdapter

                scm = GiteaAdapter(url, repo, StaticTokenAuth(token))
                lr = SetupHandler(Bus(), project_root=config_dir.parent, scm=scm).sync_labels(
                    config_dir / "labels.json"
                )
                print(
                    f"  ✅ Labels: {len(lr.get('created', []))} neu, "
                    f"{len(lr.get('skipped', []))} vorhanden, "
                    f"{len(lr.get('errors', []))} Fehler\n"
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  ⚠️  Labels-Sync uebersprungen: {exc}\n")

        # Abschluss-Diagnose
        doctor_result = _cmd_doctor(args)

        _box(
            "KONFIGURATION GESPEICHERT",
            [
                (
                    "Doctor/Qualification: bestanden"
                    if doctor_result == 0
                    else "Doctor/Qualification: nicht bestanden — Details oben beheben"
                ),
                "Die Konfiguration allein belegt keine Betriebs- oder Release-Qualification.",
                "",
                "Naechste Schritte:",
                f"  1) samuel dashboard --port {port}",
                f"     → http://<host>:{port}/  (LLM-Provider + Keys einrichten)",
                "  2) samuel watch        (Polling-Ueberwachung starten)",
                "",
                "Dashboard/REST-Auth: konfiguriert (Credential bleibt in .env).",
            ],
        )
        return 0
    except KeyboardInterrupt:
        print("\n\n  Setup abgebrochen.\n")
        return 130


_SYSTEMD_UNIT_TEMPLATE = """\
[Unit]
Description=S.A.M.U.E.L. ({mode})
After=network.target

[Service]
Type=simple
User={user}
WorkingDirectory={workdir}
EnvironmentFile={workdir}/.env
ExecStart={executable} {command}
Restart=on-failure
RestartSec=10
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
"""


def _render_systemd_unit(*, user: str, workdir: str, executable: str, mode: str) -> str:
    """#402: systemd-Unit mit echten Pfaden/User (ersetzt die hartkodierte
    Beispiel-Datei). Rein + testbar."""
    command = f"{mode} --configuration-mode production" if mode == "dashboard" else mode
    return _SYSTEMD_UNIT_TEMPLATE.format(
        user=user,
        workdir=workdir,
        executable=executable,
        mode=mode,
        command=command,
    )


def _resolve_console_entrypoint() -> Path | None:
    """Resolve the installed console script without falling back to ``python -m``."""

    stable = os.environ.get("SAMUEL_STABLE_ENTRYPOINT", "").strip()
    if stable:
        stable_path = Path(stable).expanduser()
        if stable_path.is_absolute() and stable_path.is_file() and os.access(stable_path, os.X_OK):
            resolved_stable = stable_path.resolve()
            resolved_runtime = Path(sys.executable).with_name("samuel").resolve()
            if resolved_stable.parent.parent == resolved_runtime.parent.parent.parent:
                # Preserve the stable ``current`` path in generated units.  The
                # immutable release launcher sets this value and the equality
                # check prevents it from naming a different executable.
                return stable_path

    candidates: list[Path] = []
    invoked = shutil.which(sys.argv[0]) if Path(sys.argv[0]).name == "samuel" else None
    if invoked:
        candidates.append(Path(invoked))
    candidates.append(Path(sys.executable).with_name("samuel"))
    discovered = shutil.which("samuel")
    if discovered:
        candidates.append(Path(discovered))

    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return resolved
    return None


def _cmd_install_service(args: argparse.Namespace) -> int:
    import getpass

    user = args.user or getpass.getuser()
    workdir = str(Path.cwd().resolve())
    executable = _resolve_console_entrypoint()
    if executable is None:
        print("  ❌ Installierter Console-Entry-Point `samuel` wurde nicht gefunden.")
        print(
            "     Installation aktivieren/erneuern und `samuel install-service` erneut ausfuehren."
        )
        return 1
    mode = args.mode
    unit = _render_systemd_unit(
        user=user,
        workdir=workdir,
        executable=str(executable),
        mode=mode,
    )
    name = args.name or f"samuel-{mode}"
    target = Path(f"/etc/systemd/system/{name}.service")

    if not args.write:
        print(f"# systemd-Unit ({name}.service) — Vorschau.")
        print(f"# Schreiben:  samuel install-service --mode {mode} --write   (root noetig)")
        print(f"# Oder manuell nach {target} kopieren.\n")
        print(unit)
        return 0
    try:
        target.write_text(unit, encoding="utf-8")
        print(f"  ✅ {target} geschrieben.")
        print(f"     sudo systemctl daemon-reload && sudo systemctl enable --now {name}")
        return 0
    except PermissionError:
        print(f"  ❌ Keine Schreibrechte fuer {target}.")
        print("     Mit sudo erneut, oder Vorschau (ohne --write) manuell kopieren.")
        return 1
    except OSError as exc:
        print(f"  ❌ Schreiben fehlgeschlagen: {exc}")
        return 1


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        parser.exit(2, "\nFehler: Bitte einen BEFEHL angeben.\n")

    try:
        args.config = _resolve_runtime_config_dir(args.config)
    except ValueError as exc:
        parser.error(str(exc))

    # Installer-Commands laufen OHNE Bootstrap (Config/.env existieren beim
    # Erst-Setup noch nicht): eigene, leichtgewichtige Pfade.
    if args.command == "setup":
        sys.exit(_cmd_setup(args))
    if args.command == "doctor":
        sys.exit(_cmd_doctor(args))
    if args.command == "install-service":
        sys.exit(_cmd_install_service(args))
    if args.command == "state":
        sys.exit(_cmd_state(args))
    if args.command == "identity":
        sys.exit(_cmd_identity(args))
    if args.command == "workspace":
        sys.exit(_cmd_workspace(args))
    if args.command == "retention":
        sys.exit(_cmd_retention(args))
    if args.command == "evidence":
        sys.exit(_cmd_evidence(args))
    if args.command == "candidate" and args.self_mode:
        print("ERROR: passive candidate submission is unavailable in --self mode", file=sys.stderr)
        sys.exit(2)

    project_root: Path | None = None
    if args.self_mode:
        project_root = Path(args.config).resolve().parent
        agent_env = _activate_self_mode(project_root)
        log.info("Self-Mode aktiviert (root=%s, env_override=%s)", project_root, agent_env)

        if args.command in {"run", "replan"} and not _check_self_run_branch(
            project_root,
            args.allow_non_main,
        ):
            sys.exit(1)
    elif args.command in {"run", "replan", "resume", "candidate"}:
        project_root = _configured_target_project(args.config)
        target_ok, target_error = _validate_target_project(project_root)
        if not target_ok:
            print(f"ERROR: {target_error}", file=sys.stderr)
            sys.exit(2)

    # #260: Workflow-Mode VOR bootstrap setzen, weil bootstrap zur Lade-Zeit
    # `agent.mode` liest und das Workflow-File aussucht. Reihenfolge:
    #   1. `--workflow X` (explizit)
    #   2. `--self` → workflow "self"
    #   3. config-default `agent.mode`
    if getattr(args, "workflow", None):
        os.environ["SAMUEL_WORKFLOW_OVERRIDE"] = args.workflow
    elif args.self_mode:
        os.environ["SAMUEL_WORKFLOW_OVERRIDE"] = "self"

    from samuel.core.bootstrap import bootstrap
    from samuel.core.state import StateStoreError
    from samuel.core.workspaces import WorkspaceError

    if args.log_level:
        logging.getLogger().setLevel(args.log_level)

    try:
        # Health checks inspect this runtime but must never resume its live workspaces.
        # Docker invokes this command in a separate process while the dashboard may
        # still own a resumable finalization checkpoint.
        if args.command in {"resume", "health"}:
            bus = bootstrap(
                config_path=args.config,
                project_root=project_root,
                auto_resume=False,
            )
        else:
            bus = bootstrap(config_path=args.config, project_root=project_root)
    except (StateStoreError, WorkspaceError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
    if args.self_mode and getattr(bus, "config", None):
        bus.config.set_override("agent.mode", "self")
        bus.config.set_override("agent.self_mode", True)
    log.info(
        "S.A.M.U.E.L. gestartet (config=%s%s)", args.config, ", self-mode" if args.self_mode else ""
    )

    _signal_handler = _make_signal_handler()
    signal.signal(signal.SIGINT, _signal_handler)
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, _signal_handler)

    try:
        if args.command == "watch":
            rc = _cmd_watch(bus, args)
        elif args.command == "run":
            rc = _cmd_run(bus, args)
        elif args.command == "replan":
            rc = _cmd_replan(bus, args)
        elif args.command == "candidate":
            rc = _cmd_candidate(bus, args)
        elif args.command == "health":
            rc = _cmd_health(bus, args)
        elif args.command == "dashboard":
            rc = _cmd_dashboard(bus, args)
        elif args.command == "setup-labels":
            rc = _cmd_setup_labels(bus, args)
        elif args.command == "refresh-pricing":
            rc = _cmd_refresh_pricing(bus, args)
        elif args.command == "dlq":
            rc = _cmd_dlq(bus, args)
        elif args.command == "audit":
            rc = _cmd_audit(bus, args)
        elif args.command == "replay":
            rc = _cmd_replay(bus, args)
        elif args.command == "changelog":
            rc = _cmd_changelog(bus, args)
        elif args.command == "resume":
            rc = _cmd_resume(bus, args)
        else:
            parser.print_help()
            rc = 0
    except KeyboardInterrupt:
        rc = 0
    finally:
        _shutdown_audit_sinks(bus)
    sys.exit(rc)


def _shutdown_audit_sinks(bus: Any) -> None:
    """Drain async audit sinks before process exit (#257).

    Without this, ``AsyncAuditSink``'s daemon worker thread is killed by
    ``sys.exit`` with un-drained events still in the queue. ``atexit``
    catches that path too, but calling ``stop()`` here ensures deterministic
    flushing before the rest of CLI shutdown.
    """
    close = getattr(bus, "close", None)
    if callable(close):
        close()
        return

    # Compatibility for minimal/fake buses used by external callers.
    for mw in getattr(bus, "_middlewares", []):
        sink = getattr(mw, "_sink", None)
        if sink is None:
            continue
        stop = getattr(sink, "stop", None)
        if callable(stop):
            try:
                stop()
            except Exception:
                log.exception("Audit-Sink stop() failed")
