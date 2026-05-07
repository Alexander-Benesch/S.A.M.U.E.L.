from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Any

from samuel import __version__

log = logging.getLogger(__name__)


def _load_env_file(path: Path, *, override: bool) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if override or key not in os.environ:
            os.environ[key] = value


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


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="samuel",
        description="S.A.M.U.E.L. — Sicheres Autonomes Mehrschichtiges "
        "Ueberwachungs- und Entwicklungs-Logiksystem",
    )
    p.add_argument(
        "--config", default="config", help="Pfad zum config-Verzeichnis (default: config)",
    )
    p.add_argument(
        "--log-level", default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log-Level (ueberschreibt config/agent.json)",
    )
    p.add_argument(
        "--self", dest="self_mode", action="store_true",
        help="Self-Mode: Agent arbeitet am eigenen Repo (lädt .env.agent-Override)",
    )
    p.add_argument(
        "--allow-non-main", action="store_true",
        help="Erlaubt --self run auf einer anderen Branch als main (Default: blockiert)",
    )
    p.add_argument(
        "-V", "--version",
        action="version",
        version=f"samuel {__version__}",
    )

    sub = p.add_subparsers(dest="command")

    # --- watch: Polling-Loop ---
    w = sub.add_parser("watch", help="Polling-Modus: Issues scannen und abarbeiten")
    w.add_argument("--interval", type=int, default=60, help="Poll-Intervall in Sekunden")
    w.add_argument("--once", action="store_true", help="Einmal scannen, dann beenden")

    # --- run: Einzelnes Issue bearbeiten ---
    r = sub.add_parser("run", help="Einzelnes Issue durch Workflow schicken")
    r.add_argument("issue", type=int, help="Issue-Nummer (z.B. 136 für #136)")
    r.add_argument(
        "--workflow",
        default=None,
        help="Workflow-Name (override). Default: 'self' bei --self, sonst agent.mode aus config.",
    )

    # --- health: Health-Check ---
    sub.add_parser("health", help="Health-Check ausfuehren und Ergebnis ausgeben")

    # --- dashboard: HTTP-Server + Dashboard ---
    d = sub.add_parser("dashboard", help="HTTP-Server mit Dashboard + REST-API starten")
    d.add_argument("--host", default="0.0.0.0", help="Bind-Adresse (default: 0.0.0.0)")
    d.add_argument("--port", type=int, default=7777, help="Port (default: 7777)")

    # --- setup-labels: Gitea-Labels gemäß config/labels.json anlegen ---
    sub.add_parser("setup-labels", help="Workflow-/Risk-/Scope-Labels auf SCM anlegen (idempotent)")

    # --- refresh-pricing: OpenRouter-Modell-Preise aktualisieren (#311) ---
    sub.add_parser("refresh-pricing", help="OpenRouter-Modell-Cache aktualisieren (350+ Modelle)")

    # --- changelog: Aus git-log einen Changelog generieren (#163) ---
    c = sub.add_parser(
        "changelog",
        help="Changelog aus git log seit letztem Tag/Phase generieren",
    )
    c.add_argument(
        "--since", default=None,
        help="Start-Revision (Tag, Branch, Commit). Default: letzter erreichbarer Tag.",
    )
    c.add_argument(
        "--phase", type=int, default=None,
        help="Phasen-Nummer (mappt auf Tag 'phase-N-complete')",
    )
    c.add_argument(
        "--post-to-issue", type=int, default=None,
        help="Changelog zusaetzlich als Kommentar auf Gitea-Issue posten",
    )
    c.add_argument(
        "--out", default=None,
        help="Output in Datei schreiben (default: stdout)",
    )

    return p


def _cmd_watch(bus, args) -> int:
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

    log.info("Watch-Modus gestartet (interval=%ds, timeout=%ds, once=%s)", interval, poll_timeout, args.once)
    elapsed = 0
    while True:
        try:
            cmd = ScanIssuesCommand(payload={})
            result = bus.send(cmd)
            log.info("Scan abgeschlossen: %s", result)
        except Exception:
            log.exception("Fehler im Watch-Loop")
        if args.once:
            break
        if poll_timeout and elapsed >= poll_timeout:
            log.info("Poll-Timeout (%ds) erreicht, beende Watch-Loop", poll_timeout)
            break
        time.sleep(interval)
        elapsed += interval
    return 0


def _cmd_run(bus, args) -> int:
    from samuel.core.events import Event

    event = Event(name="IssueReady", payload={"issue_number": args.issue})
    bus.publish(event)
    return 0


def _cmd_health(bus, _args) -> int:
    from samuel.core import license as _lic
    from samuel.core.commands import HealthCheckCommand

    cmd = HealthCheckCommand(payload={})
    result = bus.send(cmd)
    if result:
        healthy = result.get("healthy", False)
        print(f"Health: {'healthy' if healthy else 'unhealthy'}")
        for k, v in result.items():
            if k != "healthy":
                print(f"  {k}: {v}")
        # #294: Premium-Status nach Health-Output
        st = _lic.license_status()
        if st.get("active"):
            feats = ", ".join(st.get("features", []))
            email = st.get("email", "")
            print(f"Premium: active (license: {email}, features: {feats})")
        else:
            reason = st.get("reason", "no license")
            print(f"Premium: free mode ({reason})")
        return 0 if healthy else 1
    print("Health: no response")
    return 1


def _cmd_setup_labels(bus, args) -> int:
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

    print(f"Labels sync: {len(created)} created, {len(skipped)} existing, {len(errors)} errors (of {total})")
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


def _cmd_refresh_pricing(bus, _args) -> int:
    """#311: OpenRouter-Modell-Cache aktualisieren (350+ Modelle mit Preisen)."""
    from samuel.adapters.llm.costs import refresh_pricing

    result = refresh_pricing()
    if result.get("error"):
        print(f"Fehler: {result['error']}")
        return 1
    import datetime as _dt
    fetched_at = _dt.datetime.fromtimestamp(result.get("fetched_at", 0)).isoformat()
    print(f"OpenRouter-Cache aktualisiert: {result.get('count', 0)} Modelle ({fetched_at})")
    return 0


def _cmd_changelog(bus, args) -> int:
    """#163: Generate a changelog from git log between a start-rev and HEAD.

    Resolves the start-rev in this order:
    1. ``--phase=N`` -> tag ``phase-N-complete``
    2. ``--since=<rev>`` (literal)
    3. ``latest_tag()`` reachable from HEAD
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
                "Kein Git-Tag gefunden. Nutze --since=<rev> oder --phase=<n>.",
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


def _cmd_dashboard(bus, args) -> int:
    from samuel.server import create_server

    server = create_server(
        bus, host=args.host, port=args.port,
        scm=getattr(bus, "scm", None),
        config=getattr(bus, "config", None),
    )
    log.info("Dashboard: http://%s:%d/", args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.self_mode:
        project_root = Path(args.config).resolve().parent
        agent_env = _activate_self_mode(project_root)
        log.info("Self-Mode aktiviert (root=%s, env_override=%s)", project_root, agent_env)

        if args.command == "run" and not _check_self_run_branch(
            project_root, args.allow_non_main,
        ):
            sys.exit(1)

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

    if args.log_level:
        logging.getLogger().setLevel(args.log_level)

    bus = bootstrap(config_path=args.config)
    if args.self_mode and getattr(bus, "config", None):
        bus.config._overrides["agent.mode"] = "self"
        bus.config._overrides["agent.self_mode"] = True
    log.info("S.A.M.U.E.L. gestartet (config=%s%s)", args.config, ", self-mode" if args.self_mode else "")

    shutdown = False

    def _signal_handler(signum, _frame):
        nonlocal shutdown
        sig_name = signal.Signals(signum).name
        log.info("Signal %s empfangen, fahre herunter...", sig_name)
        shutdown = True

    signal.signal(signal.SIGINT, _signal_handler)
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, _signal_handler)

    if args.command == "watch":
        rc = _cmd_watch(bus, args)
    elif args.command == "run":
        rc = _cmd_run(bus, args)
    elif args.command == "health":
        rc = _cmd_health(bus, args)
    elif args.command == "dashboard":
        rc = _cmd_dashboard(bus, args)
    elif args.command == "setup-labels":
        rc = _cmd_setup_labels(bus, args)
    elif args.command == "refresh-pricing":
        rc = _cmd_refresh_pricing(bus, args)
    elif args.command == "changelog":
        rc = _cmd_changelog(bus, args)
    else:
        parser.print_help()
        rc = 0

    _shutdown_audit_sinks(bus)
    sys.exit(rc)


def _shutdown_audit_sinks(bus: Any) -> None:
    """Drain async audit sinks before process exit (#257).

    Without this, ``AsyncAuditSink``'s daemon worker thread is killed by
    ``sys.exit`` with un-drained events still in the queue. ``atexit``
    catches that path too, but calling ``stop()`` here ensures deterministic
    flushing before the rest of CLI shutdown.
    """
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
