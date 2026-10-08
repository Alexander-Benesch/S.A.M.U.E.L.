"""Installer-Hilfen: .env lesen/mergen + Doctor-Diagnose (reine Logik).

Bewusst ohne Netzwerk/Interaktion — der CLI-Wizard (``samuel setup``) und
``samuel doctor`` in ``cli.py`` liefern die I/O (input/print, SCM-Probe per
HTTP) und rufen diese testbaren Funktionen. So bleibt der Setup-Slice rein.
"""

from __future__ import annotations

import shlex
from collections.abc import Callable
from pathlib import Path

from samuel.core.config import (
    DEFAULT_SCM_REQUIRED_STATUS_CONTEXT,
    load_eval_config,
    resolve_scm_required_status_context,
)
from samuel.core.test_runner import (
    VerifierRunnerPolicy,
    check_test_runner_installation,
)

# LLM-Provider-Env-Keys, die der Doctor als "konfiguriert" akzeptiert.
LLM_PROVIDER_ENV = (
    "DEEPSEEK_API_KEY",
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENROUTER_API_KEY",
    "OLLAMA_URL",
    "LMSTUDIO_URL",
)

GITEA_REQUIRED_STATUS_CONTEXT = DEFAULT_SCM_REQUIRED_STATUS_CONTEXT


def gitea_release_policy_deviations(
    rules: dict,
    *,
    required_context: str = GITEA_REQUIRED_STATUS_CONTEXT,
) -> list[str]:
    """Return fail-closed deviations from the supported Gitea merge policy.

    The native branch rule is the single enforcement authority.  Direct and
    force pushes (including allowlists) are disabled, administrators cannot
    override merge requirements, and exactly the documented head-bound CI
    context is required.
    """

    deviations: list[str] = []
    expected_booleans = {
        "enable_push": False,
        "enable_push_whitelist": False,
        "enable_force_push": False,
        "enable_force_push_allowlist": False,
        "enable_status_check": True,
        "block_admin_merge_override": True,
    }
    for key, expected in expected_booleans.items():
        if rules.get(key) is not expected:
            deviations.append(f"{key} muss {str(expected).lower()} sein")

    empty_allowlists = (
        "push_whitelist_usernames",
        "push_whitelist_teams",
        "force_push_allowlist_usernames",
        "force_push_allowlist_teams",
    )
    for key in empty_allowlists:
        if rules.get(key) != []:
            deviations.append(f"{key} muss leer sein")
    for key in ("push_whitelist_deploy_keys", "force_push_allowlist_deploy_keys"):
        if rules.get(key) is not False:
            deviations.append(f"{key} muss false sein")

    contexts = rules.get("status_check_contexts")
    if contexts != [required_context]:
        deviations.append(f"status_check_contexts muss exakt [{required_context}] sein")
    return deviations


def github_release_policy_deviations(rules: dict, *, required_context: str) -> list[str]:
    """Evaluate native GitHub rules; unknown or bypassed protection stays closed."""
    deviations: list[str] = []
    object_fields = (
        "required_status_checks",
        "enforce_admins",
        "allow_force_pushes",
        "allow_deletions",
        "required_pull_request_reviews",
    )
    if any(not isinstance(rules.get(key), dict) for key in object_fields):
        return ["native GitHub-Branchschutz-Antwort fehlt oder ist ungueltig"]
    status = rules.get("required_status_checks") or {}
    contexts = status.get("contexts", [])
    checks = status.get("checks", [])
    if (
        not isinstance(contexts, list)
        or not all(isinstance(item, str) for item in contexts)
        or not isinstance(checks, list)
        or not all(
            isinstance(item, dict) and isinstance(item.get("context"), str) for item in checks
        )
    ):
        return ["native GitHub-Required-Check-Antwort ist ungueltig"]
    names = set(contexts) | {item.get("context") for item in checks if isinstance(item, dict)}
    if names != {required_context}:
        deviations.append(f"required_status_checks muss exakt [{required_context}] sein")
    if (rules.get("enforce_admins") or {}).get("enabled") is not True:
        deviations.append("enforce_admins muss true sein")
    for key in ("allow_force_pushes", "allow_deletions"):
        if (rules.get(key) or {}).get("enabled") is not False:
            deviations.append(f"{key} muss false sein")
    reviews = rules.get("required_pull_request_reviews") or {}
    if (
        type(reviews.get("required_approving_review_count")) is not int
        or reviews.get("required_approving_review_count", 0) < 1
    ):
        deviations.append("required_pull_request_reviews muss mindestens eine Freigabe verlangen")
    raw_bypass = reviews.get("bypass_pull_request_allowances", {})
    bypass = {} if raw_bypass is None else raw_bypass
    if not isinstance(bypass, dict):
        return ["native GitHub-Bypass-Antwort ist ungueltig"]
    if any(bypass.get(key, []) != [] for key in ("users", "teams", "apps")):
        deviations.append("bypass_pull_request_allowances muss leer sein")
    return deviations


LLM_PROVIDER_ENV_KEYS = {
    "deepseek": "DEEPSEEK_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "ollama": "OLLAMA_URL",
    "lmstudio": "LMSTUDIO_URL",
    "manual": "",
}


def _decode_env_value(raw: str) -> str:
    stripped = raw.strip()
    try:
        decoded = shlex.split(stripped, comments=False, posix=True)
        return decoded[0] if len(decoded) == 1 else stripped
    except ValueError:
        return stripped.strip('"').strip("'")


def parse_env(text: str) -> dict[str, str]:
    """``.env``-Text → dict (Kommentare/Leerzeilen ignoriert).

    ``shlex`` decodes the shell-safe quoting emitted by :func:`merge_env`.
    Invalid legacy values remain readable as their unmodified right-hand side.
    """
    out: dict[str, str] = {}
    for line in (text or "").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = _decode_env_value(v)
    return out


def merge_env(existing: str, updates: dict[str, str]) -> str:
    """Aktualisiere/ergänze Keys in vorhandenem ``.env``-Text, ohne Kommentare
    oder unbeteiligte Zeilen zu verlieren. Neue Keys werden angehängt."""
    seen: set[str] = set()
    out: list[str] = []
    for line in existing.splitlines() if existing else []:
        s = line.strip()
        if "=" in s and not s.startswith("#"):
            k = s.split("=", 1)[0].strip()
            if k in updates:
                out.append(f"{k}={shlex.quote(str(updates[k]))}")
                seen.add(k)
                continue
        out.append(line)
    for k, v in updates.items():
        if k not in seen:
            out.append(f"{k}={shlex.quote(str(v))}")
    return "\n".join(out).rstrip("\n") + "\n"


def build_doctor_report(
    get: Callable[[str], str | None],
    config_dir: Path,
    scm_probe: dict | None = None,
) -> list[dict]:
    """Strukturierte Diagnose. ``get(key)`` liefert den effektiven Wert
    (env oder .env), ``scm_probe`` ist das Ergebnis des Live-Verbindungstests
    (``{"ok": bool, "detail": str}``) oder ``None`` (nicht getestet).

    Jeder Check: ``{name, status: ok|warn|fail, detail, fix}``.
    """
    checks: list[dict] = []

    def chk(name: str, status: str, detail: str = "", fix: str = "") -> None:
        checks.append({"name": name, "status": status, "detail": detail, "fix": fix})

    # 1. SCM-Konfiguration
    scm_url, scm_token, scm_repo = get("SCM_URL"), get("SCM_TOKEN"), get("SCM_REPO")
    provider = (get("SCM_PROVIDER") or "gitea").lower()
    if scm_url and scm_token and scm_repo:
        chk("SCM-Konfiguration", "ok", f"{scm_url} · {scm_repo}")
    else:
        missing = [
            k
            for k, v in (("SCM_URL", scm_url), ("SCM_TOKEN", scm_token), ("SCM_REPO", scm_repo))
            if not v
        ]
        chk("SCM-Konfiguration", "fail", f"fehlt: {', '.join(missing)}", "samuel setup ausführen")

    required_context: str | None = None
    if provider in {"gitea", "github"}:
        try:
            required_context, required_context_source = resolve_scm_required_status_context(get)
        except ValueError as exc:
            chk(
                "SCM Required Check (Soll)",
                "fail",
                str(exc),
                "SCM_REQUIRED_STATUS_CONTEXT auf genau einen Checknamen setzen",
            )
        else:
            source_label = (
                "SCM_REQUIRED_STATUS_CONTEXT"
                if required_context_source == "configured"
                else "ausgelieferter Default"
            )
            chk(
                "SCM Required Check (Soll)",
                "ok",
                f"{required_context} · Quelle: {source_label}",
            )

    # 2. SCM-Verbindung (live)
    if scm_probe is not None:
        if scm_probe.get("ok"):
            chk("SCM-Verbindung", "ok", scm_probe.get("detail", ""))
        else:
            chk("SCM-Verbindung", "fail", scm_probe.get("detail", ""), "SCM_URL / SCM_TOKEN prüfen")

        branch_protection = scm_probe.get("branch_protection") or {}
        access = branch_protection.get("access")
        if provider in {"gitea", "github"} and access == "restricted":
            chk(
                "Branch-Protection (Release)",
                "fail",
                branch_protection.get(
                    "detail", "Branchschutz-Read abgewiesen; Mindestrecht unbekannt"
                ),
                "Operator prueft Endpoint und Credential gezielt; ohne lesbaren Nachweis keine Freigabe",
            )
        elif (
            provider in {"gitea", "github"}
            and access == "ok"
            and not branch_protection.get("configured")
        ):
            chk(
                "Branch-Protection (Release)",
                "fail",
                branch_protection.get("detail", "keine Regel konfiguriert"),
                "native Branch-Protection gemaess docs/INSTALL.md konfigurieren",
            )
        elif provider in {"gitea", "github"} and access == "ok":
            evaluate_rules = (
                gitea_release_policy_deviations
                if provider == "gitea"
                else github_release_policy_deviations
            )
            deviations = (
                evaluate_rules(
                    branch_protection.get("rules") or {},
                    required_context=required_context,
                )
                if required_context is not None
                else ["konfigurierter Required-Check-Sollwert ist ungueltig"]
            )
            branch = branch_protection.get("branch", "main")
            if deviations:
                chk(
                    "Branch-Protection (Release)",
                    "fail",
                    f"{branch}: {'; '.join(deviations)}",
                    "native Branch-Protection gemaess docs/INSTALL.md korrigieren",
                )
            else:
                chk(
                    "Branch-Protection (Release)",
                    "ok",
                    f"{branch}: Direkt-/Force-Push gesperrt, "
                    f"exakter Required Check [{required_context}] aktiv",
                )
        elif provider in {"gitea", "github"} and access == "unknown":
            chk(
                "Branch-Protection (Release)",
                "fail",
                branch_protection.get("detail", "nicht prüfbar"),
                "Endpoint und Credential gezielt pruefen; Mindestrecht nicht aus HTTP-Fehler ableiten",
            )
        elif provider in {"gitea", "github"}:
            chk(
                "Branch-Protection (Release)",
                "fail",
                "kein auswertbarer Branch-Protection-Nachweis",
                "SCM-Probe und native Gitea-Branch-Protection gemaess docs/INSTALL.md pruefen",
            )

    # 3. LLM-Provider (mind. einer)
    present = [k for k in LLM_PROVIDER_ENV if get(k)]
    if present:
        chk("LLM-Provider", "ok", ", ".join(present))
    else:
        chk(
            "LLM-Provider",
            "warn",
            "kein Provider-Key gesetzt",
            "im Dashboard (Tab LLM & Kosten) konfigurieren",
        )

    # 4. Sicherheit
    chk(
        "Webhook-Signaturschlüssel (SLICE_HMAC_KEY)",
        "ok" if get("SLICE_HMAC_KEY") else "warn",
        (
            "Schlüssel konfiguriert — Signaturprüfung und native SCM-Delivery nicht geprüft"
            if get("SLICE_HMAC_KEY")
            else "nicht gesetzt — Webhook ungesichert; native SCM-Delivery nicht nachgewiesen"
        ),
        "" if get("SLICE_HMAC_KEY") else "samuel setup generiert ihn automatisch",
    )
    chk(
        "Dashboard-Auth (SAMUEL_API_KEY)",
        "ok" if get("SAMUEL_API_KEY") else "warn",
        "gesetzt" if get("SAMUEL_API_KEY") else "nicht gesetzt — Dashboard/API ohne Auth",
        "" if get("SAMUEL_API_KEY") else "samuel setup generiert ihn automatisch",
    )

    # 5. Verzeichnisse
    for d in ("config", "data", "data/logs"):
        p = config_dir.parent / d if d != "config" else config_dir
        chk(
            f"Verzeichnis {d}",
            "ok" if p.exists() else "fail",
            str(p),
            "" if p.exists() else "samuel setup legt es an",
        )

    # 6. Default-Configs
    agent_cfg = config_dir / "agent.json"
    chk(
        "Default-Configs",
        "ok" if agent_cfg.exists() else "warn",
        str(config_dir),
        "" if agent_cfg.exists() else "config/ unvollständig (git clone?)",
    )

    # 7. PROJECT_ROOT (optional; without it runtime and Doctor use cwd)
    configured_root = get("PROJECT_ROOT")
    if configured_root:
        raw_root = Path(configured_root).expanduser()
        project_root = (
            raw_root if raw_root.is_absolute() else (config_dir.parent / raw_root).resolve()
        )
        project_root_ok = project_root.is_dir()
        chk(
            "PROJECT_ROOT",
            "ok" if project_root_ok else "warn",
            str(project_root),
            "" if project_root_ok else "Pfad existiert nicht",
        )
    else:
        project_root = Path.cwd().resolve()
        project_root_ok = project_root.is_dir()

    # 8. Effective TEST runner.  This is the same shared resolver used by
    # Planning and Gate 11; Doctor only inspects and never executes it.
    try:
        eval_config = load_eval_config(config_dir)
        runner_policy = VerifierRunnerPolicy.from_eval_config(eval_config)
        readiness = check_test_runner_installation(
            project_root if project_root_ok else None,
            runner_policy,
        )
    except ValueError as exc:
        chk(
            "TEST-Runner (Planning/Gate 11)",
            "fail",
            f"eval.json ungueltig: {exc}",
            "config/eval.json korrigieren und Runtime neu starten",
        )
    else:
        if readiness.get("passed"):
            kind = str(readiness.get("runner_kind", "custom"))
            selector = {
                "pytest": "logischer Name oder Pytest-Node-ID",
                "unittest": "gepunkteter Python-Modul-/Klassen-/Methodenname",
            }.get(kind, "runner-kompatibler logischer Name")
            chk(
                "TEST-Runner (Planning/Gate 11)",
                "ok",
                (
                    f"{readiness.get('runner', 'unknown')} / {kind}; "
                    f"Selektor: {selector}; Policy {runner_policy.policy_version}"
                ),
            )
        else:
            chk(
                "TEST-Runner (Planning/Gate 11)",
                "fail",
                str(readiness.get("reason", "Runner nicht pruefbar")),
                (
                    "test_cmd mit {test} in config/eval.json konfigurieren oder "
                    "unter PROJECT_ROOT einen unterstuetzten Marker bereitstellen; "
                    "Toolchain separat installieren"
                ),
            )

    return checks
