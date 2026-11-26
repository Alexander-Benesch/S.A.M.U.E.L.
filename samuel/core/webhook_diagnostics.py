"""Bounded, passive webhook observations; never workflow/readiness authority (#905)."""

from __future__ import annotations

import ipaddress
import threading
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from samuel.core.permission_diagnostics import read_permission_diagnostic

_WINDOW_SECONDS = 3600
_EVENTS = {"issues", "issue_label", "issue_comment", "pull_request", "push"}


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def freshness(value: object, now: datetime) -> str:
    try:
        date = datetime.fromisoformat(str(value))
        age = (now - date).total_seconds()
    except (ValueError, TypeError):
        return "unknown"
    return "current" if 0 <= age <= _WINDOW_SECONDS else "stale"


class WebhookObservations:
    """Last bounded observation per stage in this process, without payloads/IDs."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stages: dict[str, dict[str, str]] = {}

    def record(self, stage: str, fields: dict[str, object]) -> None:
        if stage not in {"received", "signature", "mapping"}:
            return
        if stage == "signature":
            result = fields.get("result")
            outcome = str(result) if result in {"pass", "denied", "not_checked"} else "unknown"
        elif stage == "mapping":
            status = fields.get("status")
            outcome = (
                "ignored"
                if fields.get("result") == "ignored"
                else "handled"
                if type(status) is int and 200 <= status < 300
                else "denied"
            )
        else:
            outcome = "received"
        provider = fields.get("provider")
        with self._lock:
            self._stages[stage] = {
                "outcome": outcome,
                "observed_at": timestamp(),
                "provider": str(provider) if provider in {"gitea", "github"} else "unknown",
            }

    def snapshot(self) -> dict[str, dict[str, str]]:
        with self._lock:
            return {key: dict(value) for key, value in self._stages.items()}


def target_summary(value: object) -> dict[str, Any]:
    """No request/DNS lookup; credentials, queries and arbitrary paths stay private."""
    try:
        parsed = urlsplit(str(value))
        host = parsed.hostname or ""
        port = parsed.port
        if (
            parsed.scheme not in {"http", "https"}
            or not host
            or len(host) > 253
            or any(c.isspace() for c in host)
        ):
            raise ValueError("invalid target")
        private: bool | None
        try:
            private = not ipaddress.ip_address(host).is_global
        except ValueError:
            private = True if host == "localhost" or host.endswith(".localhost") else None
        authority = f"[{host}]" if ":" in host else host
        if port is not None:
            authority += f":{port}"
        correct_path = parsed.path == "/api/v1/webhook"
        return {
            "display": f"{parsed.scheme}://{authority}"
            + ("/api/v1/webhook" if correct_path else "/[anderer Pfad]"),
            "receiver_path": correct_path,
            "private_target": private,
            "credentials_or_query": bool(
                parsed.username or parsed.password or parsed.query or parsed.fragment
            ),
        }
    except (ValueError, TypeError):
        return {"display": "ungültiges Ziel", "receiver_path": False, "private_target": None}


def summarize_hooks(value: object, provider: str) -> list[dict[str, Any]] | None:
    if not isinstance(value, list) or any(not isinstance(h, dict) for h in value):
        return None
    required = _EVENTS if provider == "gitea" else _EVENTS - {"issue_label"}
    result = []
    for hook in value[:50]:
        config = hook.get("config")
        config = config if isinstance(config, dict) else {}
        events = hook.get("events")
        events = {e for e in events if isinstance(e, str)} if isinstance(events, list) else set()
        supported = (
            hook.get("type") == "gitea" if provider == "gitea" else hook.get("name") == "web"
        )
        result.append(
            {
                "active": hook.get("active") is True,
                "supported_type": supported,
                "target": target_summary(config.get("url", "")),
                "missing_events": sorted(required - events) if "*" not in events else [],
                "json_content": config.get("content_type") == "json",
            }
        )
    return result


def build_webhook_report(
    provider: str,
    signing_key_present: bool,
    *,
    hook_read: dict[str, Any] | None = None,
    observations: dict[str, dict[str, str]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    checks: list[dict[str, str]] = []

    def check(code: str, name: str, state: str, detail: str, fix: str, *, ok: bool = False) -> None:
        checks.append(
            dict(
                code=code,
                name=name,
                state=state,
                status="ok" if ok else "warn",
                detail=detail,
                fix=fix,
            )
        )

    check(
        "signing_key",
        "Webhook-Signaturschlüssel",
        "configured" if signing_key_present else "missing",
        "Schlüssel vorhanden; Gleichheit mit dem SCM-Secret nicht geprüft."
        if signing_key_present
        else "Kein Signaturschlüssel im geprüften Kontext vorhanden.",
        "SLICE_HMAC_KEY und SCM-Webhook-Secret im vorgesehenen Wartungsfenster abgleichen; keine Secrets veröffentlichen.",
        ok=signing_key_present,
    )
    read = hook_read or {}
    raw_hooks = read.get("hooks")
    hooks = raw_hooks if isinstance(raw_hooks, list) else []
    read_freshness = freshness(read.get("observed_at"), now)
    read_ok = read.get("state") == "read" and read_freshness == "current"
    check(
        "hook_configuration",
        "Webhook-Konfiguration im SCM",
        "read"
        if read_ok
        else "stale"
        if read_freshness == "stale"
        else str(read.get("state", "not_checked")),
        f"{len(hooks)} Hooks in der gelesenen ersten Seite (maximal 50); Zielzuordnung einzeln prüfen."
        if read_ok
        else "Kein aktueller lesbarer Hook-Konfigurationsnachweis.",
        "Repository-Operator: Ziel, Aktivierung und erforderliche Ereignisse prüfen; fehlt der passende Hook, über die SCM-Verwaltung einrichten."
        if read_ok
        else "Metadaten ausdrücklich lesen. Bei verweigertem Zugriff prüft der Repository-Operator die Hook-Konfiguration; Botrechte nicht pauschal erweitern.",
        ok=read_ok and bool(hooks),
    )
    observations = observations or {}
    labels = {
        "received": "Ingress-Empfang",
        "signature": "Signaturprüfung am Ingress",
        "mapping": "Event-Verarbeitung am Ingress",
    }
    for stage, name in labels.items():
        observation = observations.get(stage, {})
        if observation.get("provider") != provider:
            observation = {}
        age = freshness(observation.get("observed_at"), now)
        outcome = observation.get("outcome", "not_checked")
        state = outcome if age == "current" else "stale" if age == "stale" else "not_checked"
        detail = {
            "received": "Ein Request wurde am Ingress empfangen; externe Erreichbarkeit aus dem SCM nicht bewiesen.",
            "pass": "Die Signatur eines empfangenen Requests war gültig; auch ein synthetischer Sender kann diesen Nachweis erzeugen.",
            "denied": "Die letzte beobachtete Prüfung/Verarbeitung wurde abgewiesen.",
            "handled": "Der letzte Request wurde verarbeitet; das belegt keine fachliche Planfreigabe.",
            "ignored": "Der letzte Request wurde ignoriert; keine erfolgreiche Event-Verarbeitung ableiten.",
            "stale": "Letzte Beobachtung älter als eine Stunde oder zeitlich unplausibel; kein aktueller Nachweis.",
        }.get(
            state,
            "Keine aktuelle Beobachtung in diesem Prozess; Doctor liest keinen laufenden Receiver aus.",
        )
        check(
            stage,
            name,
            state,
            detail,
            "Receiver-Logs zum betreffenden Ereignis prüfen; Signatur, Eventtyp und fachliche Freigabe getrennt bewerten. Keinen Hook-Test auf laufenden Issues auslösen.",
            ok=state in {"received", "pass", "handled"},
        )
        checks[-1]["observed_at"] = observation.get("observed_at", "")
    check(
        "native_delivery",
        "Native SCM-Zustellung",
        "not_proven",
        "Kein gebundener nativer Ende-zu-Ende-Nachweis in dieser Diagnose. Hook-Metadaten, Signatur und HTTP-Erfolg ersetzen ihn nicht.",
        "SCM-Zustellprotokoll und Receiver-Logs derselben Zustellung abgleichen. DNS, TLS, Firewall und bei Gitea [webhook].ALLOWED_HOST_LIST prüfen. Reale Abnahme im getrennten Testziel durchführen.",
    )
    diagnostic = read_permission_diagnostic(read.get("permission_diagnostic"))
    return {
        "schema": "webhook-diagnostic.v1",
        "informational_only": True,
        "provider": provider if provider in {"gitea", "github"} else "unknown",
        "checks": checks,
        "hooks": hooks,
        "hook_observed_at": read.get("observed_at", ""),
        "hook_freshness": read_freshness,
        "permission_diagnostic": diagnostic.to_dict() if diagnostic else None,
        "note": "Nur Diagnose, keine zusätzliche Startsperre. Beobachtungen gelten höchstens eine Stunde und nur in diesem Prozess; sie werden nach Neustart nicht übernommen. Die Stufen können verschiedene Requests betreffen.",
    }
