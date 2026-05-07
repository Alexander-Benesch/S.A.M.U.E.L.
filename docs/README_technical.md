# S.A.M.U.E.L. v2 — Technische Dokumentation

Detail-Beschreibung der Architektur, der Komponenten und der Erweiterungspunkte.
Fuer den High-Level-Einstieg siehe das Root-`README.md`.

---

## 1. Architektur-Prinzipien

S.A.M.U.E.L. ist ein **Event-Driven Monolith mit Vertical Slices** und konsequenter
**Ports-&-Adapters-Trennung**.

- **Vertical Slices** — jeder Anwendungsfall (Planning, Implementation, Eval, …)
  ist ein eigenes Verzeichnis mit Handler, Tests und domain-spezifischen Helpern.
- **Slice-Isolation** — kein Slice importiert einen anderen. Kommunikation laeuft
  ausschliesslich ueber den Bus via `Event` und `Command`. Erzwungen durch
  `tests/test_architecture_v2.py`.
- **Shared Kernel = `samuel.core`** — Bus, Events, Commands, Config, Ports,
  Workflow-Engine, Domain-Typen. Slices duerfen nur den Kernel importieren,
  niemals einen Adapter direkt.
- **Externe Systeme nur ueber Ports** — `samuel/core/ports.py` definiert 16
  abstrakte Interfaces. Adapter implementieren sie und werden im Bootstrap
  injiziert.
- **Tests beim Slice** — `samuel/slices/<slice>/tests/test_*.py`. Uebergreifende
  Tests (Architektur, Integration) liegen in `tests/`.

### Verzeichnisstruktur

```
samuel/
├── core/                  Shared Kernel
│   ├── bus.py               Bus + 6 Middlewares
│   ├── bootstrap.py         12-Step Startup-Sequenz
│   ├── commands.py          16 Command-Typen
│   ├── events.py            ~50 Event-Typen
│   ├── workflow.py          WorkflowEngine (JSON-Mapping Event→Command)
│   ├── config.py            FileConfig + Pydantic-Schemas
│   ├── ports.py             16 Interface-Definitionen
│   ├── types.py             Issue, PR, LLMResponse, GateContext, …
│   ├── errors.py            Error-Hierarchie
│   ├── http_client.py       HTTP-Abstraktion (httpx-Wrapper)
│   ├── git.py               Git-Helper (current_branch, diff, …)
│   ├── issue_context.py     Issue→Context-Extraktor
│   ├── project_files.py     Iter-Helper, CODE/CONFIG-Extension-Listen
│   ├── license.py           Ed25519-Lizenz-Verifikation (Premium)
│   ├── schedule.py          Tag/Nacht-Schedule
│   ├── ai_act.py + owasp.py Compliance-Mappings
│   ├── compliance/          OWASP-/AI-Act-JSONs (Package-Data)
│   └── prompts/             7 System-Prompts (analyst, planner, …)
├── adapters/              Externe Systeme (siehe §7)
├── slices/                Domain-Slices (siehe §6)
├── premium/               Optional: llm_routing, token_limit (siehe §12)
├── server.py              HTTP-Server + Dashboard-HTML
├── cli.py                 CLI-Entry-Point
└── __main__.py            python -m samuel
```

---

## 2. Bus + Middleware-Pipeline

`samuel.core.bus.Bus` ist die zentrale Pub/Sub- und Command-Dispatch-Komponente.
Jeder `bus.publish(event)` und `bus.send(command)` durchlaeuft eine **fixe
Middleware-Kette** (Reihenfolge ist signifikant):

| # | Middleware | Aufgabe | Failure-Verhalten |
|---|-----------|---------|-------------------|
| 1 | `IdempotencyMiddleware` | Deduplizierung via TTL-basiertem `IdempotencyStore` (JSON-File) | Duplicate → `CommandDeduplicated` Event, kein Handler-Aufruf |
| 2 | `SecurityMiddleware` | Blockiert verbotene Muster (rm -rf, force-push, DROP TABLE, …) | `SecurityTripwireTriggered`; Bus-Call abgebrochen |
| 3 | `PromptGuardMiddleware` | Erzwingt unveraenderliche Guard-Marker in LLM-Prompts | Block + Audit-Event |
| 4 | `AuditMiddleware` | Schreibt jeden Call mit Correlation-ID an konfigurierten Sink (JSONL via `AsyncAuditSink`) | Sink-Fehler wird verschluckt, Bus laeuft weiter |
| 5 | `ErrorMiddleware` | Faengt Exceptions, publiziert `WorkflowAborted` | Workflow stoppt graceful, kein Crash |
| 6 | `MetricsMiddleware` | Zaehlt Aufrufe, Fehler und Latenz pro Typ; im Dashboard sichtbar | Nie failt |

**Correlation-ID** wird im ersten Middleware erzeugt und durch alle Folge-Events
weitergereicht — Voraussetzung fuer die Audit-Suche pro Issue/Run.

---

## 3. Bootstrap (12-Step Startup-Sequenz)

`samuel.core.bootstrap.bootstrap(config_path)` baut den Bus auf und gibt ihn zurueck.

| Step | Aktion |
|------|--------|
| 0 | `.env` laden (ohne ueberschreiben bestehender Env-Vars) |
| 1 | `FileConfig` mit Pydantic-Validierung |
| 2 | Logging-Setup (Level, File, Rotation) |
| 3 | Bus + 6 Middlewares verdrahten |
| 4 | Audit-Sinks (JSONL via `AsyncAuditSink` mit Fallback) |
| 5 | SCM-Adapter (Gitea oder GitHub via `SCM_PROVIDER`) |
| 6 | LLM-Adapter inkl. Circuit-Breaker und Sanitizer |
| 7 | Skeleton-Builder-Registry (5 Sprachen) |
| 8 | Quality-Check-Registry |
| 9 | Notification-Sinks |
| 10 | Workflow-Engine laedt `config/workflows/<mode>.json` und verdrahtet Events↔Commands |
| 11 | Slice-Handler registrieren ihre Subscriber |
| 12 | Premium-Slot laden (Ed25519-Lizenz pruefen, ggf. `RoutingLLMProvider` aktivieren) |

`agent.mode` aus `config/agent.json` bestimmt den Default-Workflow; CLI-Flags
`--workflow` und `--self` setzen `SAMUEL_WORKFLOW_OVERRIDE` _vor_ Bootstrap.

---

## 4. Events (~50) und Commands (16)

### Commands (Imperative, immer mit Handler-Antwort)

`ScanIssuesCommand`, `PlanIssueCommand`, `ImplementCommand`, `CreatePRCommand`,
`ScoreCommand`, `EvaluateCommand`, `HealCommand`, `ReviewCommand`,
`HealthCheckCommand`, `ReloadConfigCommand`, `ShutdownCommand`,
`BuildContextCommand`, `RunQualityCommand`, `VerifyACCommand`,
`ChangelogCommand`, `CheckRetentionCommand`.

Definitionen in `samuel/core/commands.py`. Jeder Command ist ein
`@dataclass(frozen=True)` mit `payload: dict`.

### Events (Pub/Sub, fan-out)

Kategorisiert (Auswahl):

- **Lifecycle:** `IssueReady`, `WorkflowBlocked`, `WorkflowAborted`,
  `IssueSkipped`, `ConfigReloaded`, `StartupBlocked`
- **Plan:** `PlanCreated`, `PlanValidated`, `PlanBlocked`, `PlanPosted`,
  `PlanApproved`, `PlanFeedbackReceived`, `PlanRetry`, `PlanRevised`,
  `PlanContextLoaded`, `PlanPreCheckCompleted`, `PlanComplexityWarn`
- **Code:** `CodeGenerated`, `BranchCreated`, `BranchDeleted`,
  `SkeletonRebuilt`, `ImplementationFailed`
- **Quality/AC:** `QualityPassed`, `QualityFailed`, `QualityRetry`,
  `ACVerified`, `ACFailed`, `TestRunCompleted`, `PreCommitCheckCompleted`
- **Eval:** `Scored`, `EvalCompleted`, `EvalFailed`
- **PR:** `GatesPassed`, `GateFailedEvent`, `PRCreated`, `PRMerged`
- **LLM/Routing:** `LLMCallCompleted`, `LLMUnavailable`, `TokenLimitHit`,
  `ProviderCircuitOpen`, `ProviderFallbackUsed`
- **Healing:** `HealingSuggested`, `HealingAttemptStarted`,
  `HealingAttemptCompleted`, `HealingAborted`, `HealingFailed`
- **Audit/Security:** `AuditEvent`, `SecurityTripwireTriggered`,
  `HookIntegrityFailed`, `CommandDeduplicated`, `UnhandledCommand`
- **Misc:** `CheckpointSaved`, `ConfigValidationFailed`

Definitionen in `samuel/core/events.py`.

---

## 5. Workflow-Engine

`WorkflowEngine` (`samuel/core/workflow.py`) liest `config/workflows/<name>.json`
und verdrahtet Events auf Commands. Ein Step-Eintrag mappt `event` → `command`,
optional mit Filter und Payload-Transform.

```json
{
  "name": "standard",
  "concurrency": 1,
  "steps": [
    {"event": "IssueReady",     "command": "PlanIssueCommand"},
    {"event": "PlanValidated",  "command": "ImplementCommand"},
    {"event": "CodeGenerated",  "command": "EvaluateCommand"},
    {"event": "EvalCompleted",  "command": "CreatePRCommand",
     "filter": "score >= 0.7"}
  ]
}
```

### Vordefinierte Workflows

| Workflow | Concurrency | Charakteristikum |
|----------|-------------|------------------|
| `standard` | 1 | Einfacher End-to-End-Lauf |
| `watch` | 2 | Polling-Loop, mehrere Issues parallel |
| `autonomous` | 1 | Vollautonom mit Self-Healing |
| `chat` | 1 | Plan-Approval-Schritt vor Implement |
| `night` | 3 | Hoher Budget-Cap, lokale LLMs bevorzugt |
| `patch` | 1 | Nur Patch-Anwendung, kein neuer LLM-Call |
| `self` | 1 | Self-Mode: Agent bearbeitet eigene Issues (siehe §11) |

---

## 6. Slice-Katalog (23 Slices)

Jeder Slice hat einen Handler (`handler.py`), der Events/Commands subscribed,
und eigene Tests. Slices sind isoliert — kein Cross-Slice-Import.

| Slice | Aufgabe |
|-------|---------|
| `planning` | Issue → LLM-Plan; `validate_plan()`-Score, Retry bei 50-80%, Plan als Issue-Kommentar |
| `implementation` | Plan → Code via Multi-Round LLM-Loop (5 Runden), Patch-Parsing, Branch-Push |
| `context` | Code-Skeleton + File-Slices fuer LLM-Kontext, TOC-Mode bei grossen Files |
| `pr_gates` | 14 Gates pruefen (siehe §9) und PR erstellen |
| `evaluation` | Gewichtetes Scoring + History, Hard-Block-Schwellwerte, Markdown-Comment |
| `scoring` | Score-Berechnung (eigentliches Mathematik-Modul; `evaluation` orchestriert) |
| `ac_verification` | Akzeptanzkriterien-Verifier (siehe §10) |
| `healing` | Self-Healing via LLM mit Token-/Versuch-Budget |
| `review` | LLM-basiertes Code-Review (separates Modell moeglich) |
| `quality` | Plugin-basierte Quality-Checks pro Datei-Extension |
| `security` | Secret-Scan, Prompt-Injection-Detection, Command-Safety |
| `privacy` | PII-Scrubber, DSGVO-Drittland-Transfer-Check, AI-Act-Codes |
| `audit_trail` | Audit-Bridge + OWASP-Mapping |
| `architecture` | Konfig-getriebene Scope-Regeln (`config/architecture.json`) |
| `code_analysis` | Statische Code-Analyse (Imports, Dependencies) |
| `changelog` | Changelog-Generierung aus Kategorien-Labels |
| `dashboard` | Status-, Metrik- und Health-Aggregation fuer das HTTP-Frontend |
| `health` | System-Health-Checks (Python, Config, SCM, LLM, Disk, Audit) |
| `session` | Token-/Zeit-Budget pro Run + Workflow-Checkpoints |
| `sequence` | Event-Sequenz-Tracking + Muster-Analyse (warn/block/off) |
| `setup` | Verzeichnisse anlegen, Env-Var-Validierung, Label-Sync |
| `labels` | Workflow-Label-Transitionen (idempotent) |
| `watch` | Issue-Polling mit Semaphore-Concurrency |

---

## 7. Adapter-Katalog

Adapter implementieren die Ports aus `samuel/core/ports.py`. Sie werden im
Bootstrap injiziert und sind die einzige Bruecke zur Aussenwelt.

| Adapter | Implementierte Ports | Notizen |
|---------|---------------------|---------|
| `adapters/api/` | `IExternalEventSink`, `IExternalTrigger` | REST-API + Webhook-Ingress mit Signatur-Validierung |
| `adapters/audit/` | `IAuditSink` | `JSONLAuditSink` + `AsyncAuditSink` (Worker-Thread, Fallback-Sink) |
| `adapters/auth/` | `IAuthProvider` | `StaticTokenAuth` |
| `adapters/gitea/` | `IVersionControl` | Issue/Comment/PR/Label/Branch via Gitea-REST |
| `adapters/github/` | `IVersionControl` | inkl. `GitHubAppAuth` (JWT mit Ed25519/RS256) |
| `adapters/llm/` | `ILLMProvider` | 8 Provider (siehe §8) |
| `adapters/notifications/` | `INotificationSink` | Slack, Teams, Generic Webhook |
| `adapters/quality/` | `IQualityCheck` (Registry) | Pylint, Mypy, Ruff, … via `config/hooks.json` |
| `adapters/secrets/` | `ISecretsProvider` | `EnvSecretsProvider` |
| `adapters/skeleton/` | `ISkeletonBuilder` (Registry) | 5 Builder: Python, TypeScript, Go, SQL, Config |

### Ports im Detail

`IVersionControl` (Auszug): `get_issue`, `get_comments`, `post_comment`,
`create_pr`, `swap_label`, `list_labels`, `create_label`, `list_issues`,
`close_issue`, `merge_pr`, `issue_url`, `pr_url`, `branch_url`, `capabilities`.

Die 16 Ports gesamt: `IVersionControl`, `ILLMProvider`, `IAuthProvider`,
`IAuditLog`, `IConfig`, `IAuditSink`, `ISecretsProvider`, `ISkeletonBuilder`,
`IPatchApplier`, `INotificationSink`, `IQualityCheck`, `IExternalGate`,
`IExternalEventSink`, `IExternalTrigger`, `IDashboardRenderer`, `IProjectRegistry`.

---

## 8. LLM-Stack

```
                    ┌──────────────────┐
                    │  LLMFactory      │  liest config/llm/*.json
                    └─────────┬────────┘
                              ▼
                    ┌──────────────────┐
                    │ RoutingLLMProvider│ (Premium) — per task_type
                    └─────────┬────────┘
                              ▼
                    ┌──────────────────┐
                    │ Sanitizer        │ — strip PII, prompt-injection scrub
                    └─────────┬────────┘
                              ▼
                    ┌──────────────────┐
                    │ CircuitBreaker   │ — open/half-open/closed pro Provider
                    └─────────┬────────┘
                              ▼
                    ┌──────────────────┐
                    │ Provider-Adapter │ — Ollama / OpenRouter / DeepSeek / …
                    └──────────────────┘
```

### Provider-Adapter

| Datei | Provider | Auth | Hinweis |
|-------|----------|------|---------|
| `ollama.py` | Ollama | – | Lokal |
| `lmstudio.py` | LM Studio | – | OpenAI-kompatibel; `/v1`-Suffix wird automatisch ergaenzt (#328) |
| `openrouter.py` | OpenRouter | API-Key | 350+ Modelle, Balance-Abruf, einheitliches Billing |
| `deepseek.py` | DeepSeek | API-Key | Cloud |
| `claude.py` | Anthropic | API-Key | benoetigt `anthropic`-Extra |
| `gemini.py` | Google Gemini | API-Key | – |
| `openai.py` | OpenAI direkt | API-Key | benoetigt `openai`-Extra |
| `manual.py` | Manual-Stub | – | deterministisch, fuer Unit-Tests |

### Querschnittsmodule

- `factory.py` — Provider-Wahl per Config + ENV
- `circuit_breaker.py` — Open-Circuit nach `circuit_breaker.threshold` Fehlern
- `sanitizer.py` — PII-/Prompt-Injection-Scrubbing pre-/post-Call
- `prompts.py` — System-Prompts laden (`samuel/core/prompts/*.md`)
- `costs.py` + `metering.py` — OpenRouter-Modell-Cache, Token-Verbrauch je Run
- `task_routing.py` — pro Task-Typ ein Provider/Modell-Mapping
- `scheduled_routing.py` — Tag/Nacht-Schedule (Premium)
- `openai_compat.py` — Shared-Helper fuer OpenAI-kompatible Endpoints
- `http.py` — gemeinsamer httpx-Wrapper

---

## 9. PR-Gates (14)

`samuel/slices/pr_gates/gates.py` definiert das `GATE_REGISTRY`. Jeder Gate ist
eine Funktion `(GateContext) -> GateResult`. Status pro Gate kommt aus
`config/gates.json` (`required` / `optional` / `disabled`).

| # | Funktion | Pruefung | Default |
|---|----------|----------|---------|
| 1 | `gate_1_branch_guard` | Branch ist nicht `main`/`master` | Required |
| 2 | `gate_2_plan_comment` | Plan-Kommentar > 20 Zeichen vorhanden | Required |
| 3 | `gate_3_metadata_block` | Agent-Metadaten im Plan (Modell, Run-ID, Timestamp) | Required |
| 4 | `gate_4_eval_timestamp` | Eval-Timestamp ist juenger als Branch | Required |
| 5 | `gate_5_diff_not_empty` | Diff ist nicht leer | Required |
| 6 | `gate_6_self_consistency` | Plan-Aussagen vs. Diff-Realitaet | Optional |
| 7 | `gate_7_scope_guard` | Keine `.env`/`secrets`/`credentials` im Diff; Scope passt zur Rolle | Required |
| 8 | `gate_8_slice_gate` | Slice-Isolation respektiert (kein Cross-Slice-Import) | Required |
| 9 | `gate_9_quality_pipeline` | Quality-Checks (Lint, Type) bestanden | Required |
| 10 | `gate_10_eval_score` | Eval-Score >= Schwellwert aus `eval.json` | Required |
| 11 | `gate_11_ac_verification` | Alle AC bestanden | Required |
| 12 | `gate_12_ready_to_close` | Issue-Body explizit `ready-to-close: true` (optional) | Optional |
| 13a | `gate_13a_branch_freshness` | Branch nicht aelter als N Tage | Optional |
| 13b | `gate_13b_destructive_diff` | Loeschungen ≤ 3× Hinzufuegungen | Optional |

Optional/Disabled-Gates produzieren nur einen Audit-Event, kein PR-Block.

---

## 10. Akzeptanzkriterien-Verifier

`samuel/slices/ac_verification/handler.py` liest AC aus dem Issue-Body und
verifiziert sie maschinell vor PR-Erstellung.

### AC-Typen

| Tag | Pruefung | Beispiel |
|-----|----------|----------|
| `[DIFF]` | Diff enthaelt Pattern (regex) | `[DIFF] tests/.*test_handler\.py` |
| `[GREP]` | Pattern existiert im Code | `[GREP] def handle_idempotency` |
| `[GREP:NOT]` | Pattern existiert NICHT (Negativ-AC) | `[GREP:NOT] print\(` |
| `[IMPORT]` | Modul ist importierbar (`__import__`) | `[IMPORT] samuel.slices.foo` |
| `[TEST]` | Test-Name laeuft erfolgreich | `[TEST] test_idempotent_call` |
| `[PYTEST]` | Direkte pytest-Spec mit Datei | `[PYTEST] tests/test_x.py::test_y` |

### Test-Runner-Auto-Detection

| Marker-Datei | Runner |
|--------------|--------|
| `pyproject.toml` / `pytest.ini` / `setup.cfg` | `python -m pytest -q -k {test}` |
| `package.json` | `npx jest -t {test}` |
| `go.mod` | `go test -run {test} ./...` |
| `Cargo.toml` | `cargo test {test}` |
| `pom.xml` | `mvn test -Dtest={test}` |

Override per `config/eval.json` → `test_cmd` (mit `{test}`-Platzhalter) und
`test_timeout`.

---

## 11. Self-Mode

`samuel --self <cmd>` aktiviert den Self-Mode. Unterschiede zur Production:

- `.env.agent` wird ueberlagernd geladen (override = True), `.env` als Default.
- `SAMUEL_SELF_MODE=1` und `SAMUEL_ENV_FILE` werden gesetzt.
- `agent.mode` und `agent.self_mode` werden im Config-Override-Layer auf `self`
  bzw. `True` gepinnt.
- `--self run` darf nur auf `main` laufen — `_check_self_run_branch()` failt
  sonst (Regression-Schutz fuer #227). Override per `--allow-non-main`.
- Default-Workflow ist `self.json` (concurrency=1, mit AC-Pflicht und
  Plan-Pre-Check).

Self-Mode wird verwendet, damit der Agent eigene Backlog-Issues abarbeiten
kann, ohne dass dabei versehentlich der falsche Workflow oder das falsche Repo
trifft.

---

## 12. Premium-Architektur

Premium-Plug-ins liegen in `samuel/premium/`, sind optional und werden via
**Ed25519-Lizenz** entsperrt.

### Lizenz-Verifikation (`samuel/core/license.py`)

- Public-Key in `LICENSE_PUBLIC_KEY_HEX` (32 Bytes hex), generiert mit
  `tools/generate_keypair.py`.
- Lizenz-Datei in `config/license.json` (Pfad konfigurierbar via
  `SAMUEL_CONFIG_DIR`).
- Payload: `{email, features: [list], issued_at, signature}`.
- Signatur ist Ed25519 ueber den kanonischen JSON-String _ohne_ Signatur-Feld.
- Ohne valide Lizenz: Free-Modus, `license_status() → {active: False}`.

### Premium-Plug-ins

| Plug-in | Aktiviert via `feature` | Funktion |
|---------|------------------------|----------|
| `llm_routing` | `llm_routing_advanced` | `RoutingLLMProvider` waehlt pro `task_type` (plan/implement/review/eval/heal/changelog/health) ein anderes Modell. Tag/Nacht-Schedule (`NIGHT_HOURS = 0..7`). |
| `token_limit` | `token_limit` | Hartes Token-Budget pro Run; bei Ueberschreitung `TokenLimitHit` Event und Workflow-Abort. |

Plug-ins werden im Bootstrap-Step 12 dynamisch geladen, wenn das passende
`feature` in der Lizenz steht. Der Free-Modus laeuft mit dem default
`ollama`-Provider und ohne Token-Cap.

---

## 13. Security-Model

### Prompt-Injection-Detection (`samuel/slices/security`)

7 Muster werden vor jedem LLM-Call gegen den User-Input gematcht:
- `ignore (previous|all) instructions`
- `disregard (previous|the) (rules|system)`
- `system prompt`
- `you are now`
- `act as (a|an)?`
- `pretend (to be|you are)`
- Variationen mit Unicode-Look-Alikes

### Secret-Scan

Regex-basierte Erkennung von:
- API-Keys (`sk-…`, `gh[ps]_…`, `AKIA…`)
- JWTs
- Private Keys (`-----BEGIN [A-Z ]+PRIVATE KEY-----`)
- Generischen Tokens (Heuristik nach Entropie + Laenge)

Trifft sowohl Diff (vor PR) als auch LLM-Output (vor Patch-Apply). Fail-Closed.

### Command-Safety

Block-Liste fuer destructive Patterns: `DROP TABLE`, `DELETE FROM` (ohne WHERE),
`TRUNCATE`, `rm -rf`, `git push --force`, `git push -f`,
`git reset --hard origin/main`.

### HMAC-Signierung

- **Webhook-Payloads** (Gitea + GitHub) werden gegen `SLICE_HMAC_KEY` validiert.
- **Context-Slices** zwischen Bus und externen Workern sind signiert (Replay-
  und Tampering-Schutz).

### Prompt Guard

Jeder LLM-Prompt enthaelt unveraenderliche Header-Marker (z.B. `[SAMUEL/GUARD]`).
`PromptGuardMiddleware` prueft pre-call die Marker-Praesenz, post-call das
Fehlen von `[/SAMUEL/GUARD]`-Echo (Anzeichen fuer Prompt-Echo-Injection).

---

## 14. Audit-Trail

Asynchrones JSONL-Logging via `AsyncAuditSink` (Worker-Thread + Queue +
Fallback-Sink).

### Event-Schema (Auszug)

```json
{
  "ts": "2026-05-05T22:13:01.123Z",
  "correlation_id": "abc12345",
  "issue_number": 136,
  "type": "PlanCreated",
  "owasp_risk": "LLM-01",
  "ai_act_code": "Art.10-data-quality",
  "payload": {"score": 0.83, "model": "qwen2.5-coder:7b"}
}
```

### Querweise

- Filtern nach `correlation_id` → kompletter Run-Trace.
- Filtern nach `owasp_risk` → Compliance-Reports.
- Filtern nach `issue_number` → Multi-Run-History (Issue mehrfach abgearbeitet).

Klassifikation in `samuel/core/owasp.py` (LLM-01..10) und `samuel/core/ai_act.py`
(EU-AI-Act-Artikel-Mapping). Compliance-JSON-Dateien sind als Package-Data
mitgeliefert (`samuel/core/compliance/*.json`).

---

## 15. Persistenz

`config/agent.json` → `agent.data_dir` (Default: `data/`). Alle persistenten
Artefakte landen darunter:

| Verzeichnis/Datei | Inhalt |
|-------------------|--------|
| `data/idempotency.json` | Idempotency-Store (TTL-basiert) |
| `data/logs/agent.jsonl` + `.fallback` | Audit-Trail |
| `data/eval_history/<issue>.jsonl` | Eval-History pro Issue (Score-Trend) |
| `data/workflow_runs/<issue>/<run_id>/` | Plan, Diff, Eval pro Run (#277 in Vorbereitung) |
| `data/checkpoints/` | Workflow-Checkpoints (CheckpointSaved Events) |
| `data/health.jsonl` | Self-Mode Health-Metrics |
| `data/sequence/` | Sequence-Validator-State |

---

## 16. CLI-Reference

`samuel.cli` baut den Bus via `bootstrap()` und dispatched einen Subcommand.
Globale Flags vor dem Subcommand:

| Flag | Wirkung |
|------|---------|
| `--config <dir>` | Pfad zum Config-Verzeichnis (Default `config`) |
| `--log-level DEBUG\|INFO\|WARNING\|ERROR` | Override `agent.log_level` |
| `--self` | Self-Mode aktivieren (laedt `.env.agent` overlayend, setzt `SAMUEL_SELF_MODE=1`, default-workflow `self`) |
| `--allow-non-main` | Erlaubt `--self run` auf einer anderen Branch als `main` (Default: blockiert; Schutz gegen #227-Regression) |
| `-V`, `--version` | Version drucken und beenden |

### Subcommands

| Subcommand | Aufgabe | Wichtige Flags |
|------------|---------|----------------|
| `health` | Health-Check (Python, Config, SCM, LLM, Premium-Status). Exit 0 bei healthy, sonst 1. | – |
| `run <issue>` | `IssueReady`-Event fuer Issue publizieren (durchlaeuft den aktiven Workflow) | `--workflow <name>` (Override) |
| `watch` | Polling-Loop, scannt nach Issues mit Workflow-Label | `--once`, `--interval <s>` |
| `dashboard` | HTTP-Server mit Web-Dashboard und REST-API | `--host`, `--port` (Default 7777) |
| `setup-labels` | Workflow-/Risk-/Scope-Labels auf dem SCM anlegen (idempotent, liest `config/labels.json`) | – |
| `refresh-pricing` | OpenRouter-Modell-Cache aktualisieren (350+ Modelle mit Preisen, Dump in `data/`) | – |
| `changelog` | Markdown-Changelog aus git log seit letztem Tag/Phase generieren (`feat`/`fix`/`refactor`/...-Commits mit `(#NNN)`-Ref). Default-Start ist `git describe --tags --abbrev=0`. | `--since <rev>`, `--phase <n>` (mappt auf `phase-n-complete`), `--post-to-issue <n>` (Kommentar in Gitea-Issue), `--out <file>` |

### Praxis-Beispiele

```bash
# Issue #136 manuell durch den Standard-Workflow
python -m samuel run 136

# Watch-Loop alle 30 s, Timeout aus config/agent.json:agent.auto.poll_timeout
python -m samuel watch --interval 30

# Einmaliger Scan ohne Loop (CI/Cron-Pattern)
python -m samuel watch --once

# Self-Mode: Agent bearbeitet ein eigenes Issue
python -m samuel --self run 136

# Self-Mode auf Branch ausserhalb main (gefaehrlich, nur fuer manuelle Runs)
python -m samuel --self --allow-non-main run 136

# Workflow override (z.B. night-Workflow ad-hoc)
python -m samuel --workflow night run 42

# Dashboard auf localhost only
python -m samuel dashboard --host 127.0.0.1 --port 8080

# Verbose Logs (CLI uebersteuert config/agent.json)
python -m samuel --log-level DEBUG run 42

# Changelog seit letztem Tag, in Datei
python -m samuel changelog --out CHANGELOG.md

# Changelog seit Phase 13, zusaetzlich als Kommentar zu Issue 250
python -m samuel changelog --phase 13 --post-to-issue 250
```

### Workflow-Wahl: Reihenfolge

1. `--workflow X` (explizit am CLI)
2. `--self` → Workflow `self`
3. `agent.mode` aus `config/agent.json`

Override-Mechanik: vor `bootstrap()` wird `SAMUEL_WORKFLOW_OVERRIDE` gesetzt, weil
der Bootstrap das Workflow-File zur Lade-Zeit aussucht (#260).

### Audit-Sink-Drainage beim Shutdown

Beim Beenden ruft die CLI `_shutdown_audit_sinks(bus)`, das alle `AsyncAuditSink`
deterministisch flushed bevor `sys.exit` greift (#257). Ohne diesen Schritt
werden Daemon-Worker-Threads unsanft gekillt und queued Events gehen verloren.

---

## 17. Dashboard-Reference

Web-Frontend auf `http://<host>:<port>/`. Auto-Refresh alle 10 Sekunden.

### Tabs / Sektionen

| Sektion | Quelle / API | Inhalt |
|---------|--------------|--------|
| Status-Karten | `dashboard`-Slice | Aktueller Modus, SCM-Verbindung, Premium-Lizenz-Status |
| Metriken-Tabelle | `MetricsMiddleware` | Pro Command/Event: Count, Errors, Avg Latency |
| Health | `HealthCheckCommand` | Python, Config, SCM, LLM-Reachability, Disk, Audit-Sink |
| Workflow-Runs | `data/workflow_runs/` | History pro Issue mit Plan/Code/Eval-Status (#277 in Vorbereitung) |
| System-Prompts | `samuel/core/prompts/*.md` | 7 Prompts (planner, analyst, reviewer, healer, log_analyst, docs_writer, senior_python) — Read-Only im Free-Mode, Edit nur mit Premium-Feature `system_prompts_edit` |
| Schedule | `config/llm/schedule.json` | Tag-/Nacht-Routing-Einstellungen (Premium `llm_routing_advanced`) |
| Test-Connection | LLM-Adapter | Manueller Provider-Reachability-Check inkl. Balance-Abruf (OpenRouter) |

### REST-API

Siehe §18 (`api/v1/...`).

### Auth

- `Authorization: Bearer <SAMUEL_API_KEY>` oder
- `X-API-Key: <key>` Header

Read-Only-Endpunkte (`/api/v1/dashboard/status`, `/api/v1/dashboard/metrics`)
sind ohne Auth zugaenglich; Trigger-Endpunkte (`POST`) brauchen den Key.

### Webhook-Endpunkt

`POST /api/v1/webhook` empfaengt Gitea- oder GitHub-Webhooks. HMAC-Signatur
wird gegen `SLICE_HMAC_KEY` (Gitea: `X-Gitea-Signature`, GitHub:
`X-Hub-Signature-256`) validiert. Akzeptierte Events: `issue-opened`,
`issue-closed`, `pull_request-merged` (Webhook-Erweiterung in #230).

---

## 18. API-Endpoints

| Methode | Pfad | Beschreibung | Auth |
|---------|------|--------------|------|
| GET | `/` | Dashboard HTML | Nein |
| GET | `/api/v1/health` | Health-Check (`HealthCheckCommand`) | Bearer |
| GET | `/api/v1/dashboard/status` | Status + Metriken | Nein (read-only) |
| GET | `/api/v1/dashboard/metrics` | Bus-Metriken (Count, Errors, Avg Latency) | Nein |
| GET | `/api/metrics` | Prometheus-kompatibler Export | Bearer |
| POST | `/api/v1/issues/{id}/plan` | `PlanIssueCommand` triggern | Bearer |
| POST | `/api/v1/issues/{id}/implement` | `ImplementCommand` triggern | Bearer |
| POST | `/api/v1/scan` | `ScanIssuesCommand` triggern | Bearer |
| POST | `/api/v1/webhook` | Gitea/GitHub Webhook-Empfang | HMAC-Signatur |

**Auth:** `Authorization: Bearer <SAMUEL_API_KEY>` oder `X-API-Key: <key>`.
**Webhook-Signatur:** `X-Gitea-Signature` bzw. `X-Hub-Signature-256` gegen
`SLICE_HMAC_KEY`.

---

## 19. Konfigurations-Dateien

| Datei | Schema (in `samuel/core/config.py`) | Zweck |
|-------|-------------------------------------|-------|
| `.env` | – | SCM-Token, LLM-Keys, `SAMUEL_API_KEY`, `SLICE_HMAC_KEY` |
| `.env.agent` | – | Self-Mode-Override (laden mit `override=True`) |
| `config/agent.json` | `AgentConfigSchema` | Modus, Polling, Datenverzeichnis, Logging, Sequence-Validator |
| `config/llm.json` + `config/llm/*.json` | `LLMConfigSchema` | Provider-Liste, Defaults, Routing |
| `config/gates.json` | `GatesConfigSchema` | Required/Optional/Disabled Gates |
| `config/eval.json` | `EvalSchema` | Kriterien-Gewichte, `test_cmd`, `test_timeout`, Hard-Block-Schwellwerte |
| `config/architecture.json` | – | Rollen + Scopes (Pipeline-Scope-Guard, Gate 7) |
| `config/hooks.json` | – | Quality-Check-Konfiguration pro Extension |
| `config/audit.json` | `AuditConfigSchema` | Sink-Type (jsonl), Pfad, Rotation |
| `config/notifications.json` | – | Slack/Teams/Webhook |
| `config/privacy.json` | `PrivacyConfigSchema` | PII-Scrubber, DSGVO-Drittland-Transfer, Retention |
| `config/repo_patterns.json` | – | Erwartete Event-Sequenzen pro Repo-Typ |
| `config/labels.json` | – | Workflow-/Risk-/Scope-Labels (`samuel setup-labels`) |
| `config/license.json` | – | Premium-Lizenz (signiertes JSON) |
| `config/features.json` | – | Feature-Flags |
| `config/workflows/*.json` | – | 7 Workflow-Definitionen |

---

## 20. Deployment

### Systemd

```bash
sudo cp samuel.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now samuel
sudo journalctl -u samuel -f
```

`samuel.service` setzt `WorkingDirectory`, `ExecStart=/path/.venv/bin/python -m samuel watch`,
`Restart=on-failure` und Environment-File auf `.env`.

### Docker

```bash
docker compose up -d
docker compose logs -f samuel
```

`Dockerfile` baut Python 3.12-slim mit `pip install -e ".[all]"`. Volume-Mounts:
`./config`, `./data`, `./.env`.

### Reverse-Proxy (nginx)

```nginx
location /samuel/ {
    proxy_pass http://127.0.0.1:7777/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

---

## 21. Entwicklung

### Test-Strategie

```bash
# Alles
.venv/bin/python -m pytest tests/ samuel/ -q

# Slice-Tests (lokal beim Slice)
.venv/bin/python -m pytest samuel/slices/planning/tests/

# Architektur-Validierung (zwingt Slice-Isolation)
.venv/bin/python -m pytest tests/test_architecture_v2.py

# E2E
.venv/bin/python -m pytest tests/test_integration_e2e.py
```

**Baseline:** 1240 Tests, ruff 0 errors. Mypy ist nicht CI-Pflicht.

### Slice-Isolation-Regel

`tests/test_architecture_v2.py` schlaegt fehl, wenn:
- Ein Slice einen anderen Slice importiert (`from samuel.slices.X` in Slice Y)
- Ein Slice direkt einen Adapter importiert (`from samuel.adapters.X`)

Wenn ein Slice einen Adapter braucht, geht das ueber Dependency-Injection im
Bootstrap (`server.py`) oder via Resolver-Funktion (z.B. `_balance_resolver` in
`server.py`).

### Self-Mode-Workflow (Pflicht bei `chat_mode_pr=true`)

Code-Aenderungen am Agent-Repo selbst laufen ueber den `--chat-workflow`
(siehe `feedback_self_workflow_mandatory` in der Memory). Direktes Editieren
ist nur fuer Doku-/Config-Files erlaubt.

---

## 22. Erweiterung

### Neuen Slice anlegen

```
samuel/slices/<name>/
├── __init__.py
├── handler.py          # subscribed Events/Commands im Bus
└── tests/
    └── test_handler.py
```

Im Bootstrap registrieren (Step 11). Architektur-Test laeuft automatisch
gegen den neuen Slice.

### Neuen LLM-Provider hinzufuegen

1. `samuel/adapters/llm/<provider>.py` — implementiert `ILLMProvider`.
2. In `factory.py` registrieren (Provider-Name → Klasse).
3. Optional: Eintrag in `config/llm.json` und ENV-Variable im `.env.example`.
4. Tests in `samuel/adapters/llm/tests/test_<provider>.py` (Mock-HTTP-Layer
   via `unittest.mock`).

### Neuen Gate hinzufuegen

1. Funktion `gate_X_<name>(ctx: GateContext) -> GateResult` in
   `samuel/slices/pr_gates/gates.py`.
2. In `GATE_REGISTRY` eintragen.
3. Default-Status in `config/gates.json` setzen.
4. Test in `samuel/slices/pr_gates/tests/test_gates.py`.

### Neue Sprache fuer Skeleton

1. Neuer Builder in `samuel/adapters/skeleton/<lang>.py` (implementiert
   `ISkeletonBuilder`).
2. In Skeleton-Registry (Bootstrap Step 7) eintragen.
3. Optional: tree-sitter-Grammar als Extra in `pyproject.toml`.

### Neue Architektur-Regel

`config/architecture.json` editieren — kein Code noetig. Pipeline-Scope-Guard
(Gate 7) liest die Datei zur Laufzeit.

---

*Stand 2026-05-05. Bei Pipeline-Aenderungen siehe Pflege-Regel in
`technische Beschreibungen/README.md`: zuerst Code, dann Doc — im gleichen PR.*

---

## Lizenz

Apache License 2.0. Optionale Premium-Plug-ins (`llm_routing`, `token_limit`)
sind kostenpflichtig und finanzieren die Weiterentwicklung; alle Kern-Features
sind im Free-Mode ohne Einschraenkung nutzbar.
