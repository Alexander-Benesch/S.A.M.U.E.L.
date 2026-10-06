# S.A.M.U.E.L. v2 — Technische Dokumentation

Detail-Beschreibung der Architektur, der Komponenten und der Erweiterungspunkte.
Fuer den High-Level-Einstieg siehe das Root-`README.md`.

> **Wirksamkeitsstatus:** Code und ausgelieferte Konfiguration bestimmen das
> Verhalten. Die gegen Code, Profile, Workflows und Tests geprüfte Bewertung
> jeder Kontrolle steht in der
> [Capability-/Wirksamkeitsmatrix](CAPABILITY_MATRIX.md). Ein Klassenname oder
> Registry-Eintrag belegt allein keine wirksame Schranke.
>
> Wiederholbare Runtime-Fakten stehen in der aus Code und ausgelieferter
> Konfiguration erzeugten [Runtime-Referenz](RUNTIME_REFERENCE.md). Die
> Dokumentklassifikation und abschnittsbezogene Quellenbindung liegen in
> `docs/capabilities/document-contract.json` und werden gemeinsam mit der
> Capability-Matrix durch `tools/control_matrix.py` geprüft.
>
> Den durchgängigen Nutzerpfad mit Werkzeug-, Authority-, Status- und
> Evidence-Zuordnung beschreibt die
> [Pipeline-Übersicht](../technische%20Beschreibungen/README.md). Dort sind die
> für `v2.0.0a15` erhaltenen realen #658-Teilnachweise getrennt von
> automatisierten Tests ausgewiesen. Wegen des Bot-Merges des Golden-PRs
> bestätigen sie keinen vollständigen D0-PASS. Die gebundene Evidence gilt nur
> für ihre benannte Kombination und ist keine allgemeine Betriebsfreigabe.

> **Developmentdelta auf `main@41340e75` (29.09.2026):** Die technische
> MANUAL-Receipt-Fortsetzung ist durch #910/PR #911 mit gebundener
> Watch-Reevaluation und Regressionen integriert. Ebenso sind native signierte
> Gitea-Freigabe (#904), Health-/Resume-Konkurrenzgrenzen (#906/#913),
> Providerfehlerbehandlung (#912/#918) und unmoegliches `GREP:NOT` (#916)
> korrigiert. Die historischen Development-E2E-Subjects #1/#2/#3 bleiben
> Failure-Evidence; ein neuer zusammenhaengender positiver Lauf fehlt (#859).
> Der bestehende #693-Health-/Self-Check-Vertrag bleibt erhalten; #921 umfasst
> nur die fehlende Full-System-Aggregation und den kritischen Preflight.

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
  Workflow-Engine, Domain-Typen sowie die gemeinsame Security-Policy. Slices
  duerfen nur den Kernel importieren, niemals einen Adapter direkt.
- **Externe Systeme nur ueber Ports** — `samuel/core/ports.py` definiert 28
  abstrakte Interfaces. Adapter implementieren sie und werden im Bootstrap
  injiziert.
- **Tests beim Slice** — `samuel/slices/<slice>/tests/test_*.py`. Uebergreifende
  Tests (Architektur, Integration) liegen in `tests/`.

### Verzeichnisstruktur

```
samuel/
├── core/                  Shared Kernel
│   ├── bus.py               Bus + 4 Middlewares
│   ├── bootstrap.py         12-Step Startup-Sequenz
│   ├── commands.py          17 Command-Typen
│   ├── events.py            82 Event-Typen
│   ├── workflow.py          WorkflowEngine (JSON-Mapping Event→Command)
│   ├── config.py            FileConfig + Pydantic-Schemas
│   ├── ports.py             30 Interface-Definitionen
│   ├── state.py             State-Records + redigierte Fehler-Taxonomie
│   ├── types.py             Issue, PR, LLMResponse, GateContext, …
│   ├── errors.py            Error-Hierarchie
│   ├── http_client.py       HTTP-Abstraktion (httpx-Wrapper)
│   ├── git.py               Git-Helper (current_branch, diff, …)
│   ├── issue_context.py     Issue→Context-Extraktor
│   ├── project_files.py     Iter-Helper, CODE/CONFIG-Extension-Listen
│   ├── schedule.py          Tag/Nacht-Schedule
│   ├── ai_act.py + owasp.py Compliance-Mappings
│   ├── compliance/          OWASP-/AI-Act-JSONs (Package-Data)
│   └── prompts/             7 System-Prompts (analyst, planner, …)
├── adapters/              Externe Systeme (siehe §7)
├── slices/                Domain-Slices (siehe §6)
├── server.py              HTTP-Server + Dashboard-HTML
├── cli.py                 CLI-Entry-Point
└── __main__.py            nur vertrauenswürdiger Source-Checkout; kein Betriebs-Entrypoint
```

---

## 2. Bus + Middleware-Pipeline

`samuel.core.bus.Bus` ist die zentrale Pub/Sub- und Command-Dispatch-Komponente.
Jeder `bus.publish(event)` und `bus.send(command)` durchlaeuft eine **fixe
Middleware-Kette** (Reihenfolge ist signifikant):

| # | Middleware | Aufgabe | Failure-Verhalten |
|---|-----------|---------|-------------------|
| 1 | `IdempotencyMiddleware` | Deduplizierung via TTL-basiertem `IdempotencyStore` (JSON-File) | Duplicate → `CommandDeduplicated` Event, kein Handler-Aufruf |
| 2 | `AuditMiddleware` | Schreibt jeden Call mit Correlation-ID an konfigurierten Sink (JSONL via `AsyncAuditSink`) | Sink-Fehler wird verschluckt, Bus laeuft weiter |
| 3 | `ErrorMiddleware` | Faengt Exceptions, publiziert `WorkflowAborted` | Workflow stoppt graceful, kein Crash |
| 4 | `MetricsMiddleware` | Zaehlt Aufrufe, Fehler und Latenz pro Typ; im Dashboard sichtbar | Nie failt |

Security-Policies sind bewusst nicht mehr als wirkungslose Command-Namens-
Middleware modelliert: Issue-Input wird vor dem Planning-LLM analysiert, der
Candidate-Diff im PR-Gate und Git-Aktionen direkt vor dem Subprozess.

**Correlation-ID** entsteht beim Erzeugen von Command/Event und wird durch
Folge-Events weitergereicht — Voraussetzung fuer die Audit-Suche pro
Issue/Run.

---

## 3. Bootstrap (12-Step Startup-Sequenz)

`samuel.core.bootstrap.bootstrap(config_path)` baut den Bus auf und gibt ihn zurueck.

| Step | Aktion |
|------|--------|
| 0 | `.env` laden (ohne ueberschreiben bestehender Env-Vars) |
| 1 | `FileConfig` mit Pydantic-Validierung |
| 2 | Logging-Setup (Level, File, Rotation) |
| 3 | Bus + 4 Middlewares verdrahten |
| 4 | Audit-Sinks (JSONL via `AsyncAuditSink` mit Fallback) |
| 5 | SCM-Adapter (Gitea oder GitHub via `SCM_PROVIDER`) |
| 6 | LLM-Adapter inkl. Task-Routing, geordneter Provider-Fallback-Kette, Circuit-Breaker und Sanitizer |
| 7 | Slice-Handler einschließlich Skeleton-, Gate- und Quality-Registry registrieren |
| 8 | Startup-Validation über den Health-Check |
| 9 | Workflow-Engine lädt das bereits validierte `config/workflows/<mode>.json` und verdrahtet Events↔Commands |
| 10 | Notification-Sinks laden |
| 11 | Signal-Handler und Graceful Shutdown werden in `cli.py` registriert |

`agent.mode` aus `config/agent.json` bestimmt den Default-Workflow; CLI-Flags
`--workflow` und `--self` setzen `SAMUEL_WORKFLOW_OVERRIDE` _vor_ Bootstrap.

---

## 4. Events (104) und Commands (20)

### Commands (imperative Typdefinitionen)

`ScanIssuesCommand`, `PlanIssueCommand`, `ReplanIssueCommand`, `ImplementCommand`, `CreatePRCommand`,
`SubmitCandidateCommand`, `RequestCandidateVerificationCommand`, `ScoreCommand`, `EvaluateCommand`, `HealCommand`, `ReviewCommand`,
`HealthCheckCommand`, `ReloadConfigCommand`, `ShutdownCommand`,
`BuildContextCommand`, `RunQualityCommand`, `VerifyACCommand`,
`ChangelogCommand`, `CheckRetentionCommand`, `ResumePendingCommand`.

Definitionen in `samuel/core/commands.py`. Jeder Command ist ein
`@dataclass(frozen=True)` mit `payload: dict`. Der Bootstrap registriert davon
13 Runtime-Handler. `ScoreCommand`, `EvaluateCommand` und `HealCommand` bleiben
für direkte Kompatibilitätsaufrufe lesbar, sind aber weder registriert noch in
einem ausgelieferten Workflow verdrahtet. `ReloadConfigCommand` und
`ShutdownCommand` sind ebenfalls keine Bootstrap-Command-Handler.

### Events (Pub/Sub, fan-out)

Kategorisiert (Auswahl):

- **Lifecycle:** `IssueReady`, `WorkflowBlocked`, `WorkflowAborted`,
  `IssueSkipped`, `ConfigReloaded`, `StartupBlocked`
- **Plan:** `PlanCreated`, `PlanValidated`, `PlanBlocked`, `PlanPosted`,
  `PlanReplanRejected`, `PlanRevoked`, `PlanApproved`, `PlanFeedbackReceived`,
  `PlanRetry`, `PlanRetryEvaluated`, `PlanRevised`, `ClarificationRequested`,
  `ClarificationWaiting`, `ClarificationAccepted`, `ClarificationSuperseded`,
  `PlanContextLoaded`, `PlanPreCheckCompleted`, `PlanComplexityWarn`
- **Code:** `CodeGenerated`, `BranchCreated`, `BranchDeleted`,
  `SkeletonRebuilt`, `ImplementationFailed`
- **Quality/AC:** `QualityPassed`, `QualityFailed`, `QualityRetry`,
  `ACVerified`, `ACFailed`, `ACManualPending`, `TestRunCompleted`,
  `PreCommitCheckCompleted`
- **Eval:** `ScoreObserved`; `Scored`, `EvalCompleted` und `EvalFailed` bleiben
  als historische Event-Schemata lesbar, lösen im aktiven Pfad aber nichts aus
- **PR:** `GateEvaluationCompleted`, `GateEvaluationUnavailable`, `GatesPassed`, `GateFailedEvent`,
  `PRCreated`, `PRCreationFailed`, `EvaluationSubjectInvalidated`, `PRMerged`
- **Passive Candidate:** `CandidateVerificationPending`,
  `CandidateEvaluationCompleted`, `CandidateEvaluationFailed`,
  `CandidateSubmissionRejected`
- **Execution Provider:** `ProviderVerificationRequested`,
  `ProviderVerificationPending`, `ProviderVerificationBlocked`,
  `ProviderGateEvaluationCompleted`
- **LLM/Routing:** `LLMCallCompleted`, `LLMUnavailable`, `TokenLimitHit`,
  `WorkflowBudgetAdmitted`, `LLMBudgetAttemptReserved`,
  `LLMBudgetAttemptSettled`, `LLMBudgetBlocked`, `ProviderCircuitOpen`,
  `ProviderFallbackUsed`
- **Healing:** `HealingSuggested`, `HealingClassified`, `HealingAttemptStarted`,
  `HealingAttemptCompleted`, `HealingAborted`, `HealingFailed`
- **Resume:** `ResumeAttempted`, `ResumeCompleted`, `ResumeBlocked`
- **Audit/Security:** `AuditEvent`, `SecurityTripwireTriggered`,
  `HookIntegrityFailed`, `CommandDeduplicated`, `UnhandledCommand`
- **Misc:** `CheckpointSaved`, `ConfigValidationFailed`

Definitionen in `samuel/core/events.py`.

---

## 5. Workflow-Engine

`WorkflowEngine` (`samuel/core/workflow.py`) liest `config/workflows/<name>.json`
und verdrahtet Events auf Commands. Ein Step mappt `on` (Eventname) auf `send`
(registrierter Commandname); `condition` ist optional. Der Bootstrap validiert
das komplette Profil vor dem Verdrahten. Fehlende, ungueltige oder unter einem
abweichenden Namen gespeicherte Profile beenden den Start mit einer klaren
Fehlermeldung statt still auf ein anderes Profil zurueckzufallen.

```json
{
  "name": "standard",
  "steps": [
    {"on": "IssueReady",     "send": "PlanIssue"},
    {"on": "PlanApproved",  "send": "Implement"},
    {"on": "CodeGenerated",    "send": "CreatePR"},
    {"on": "HealingSuggested", "send": "Implement"},
    {"on": "PRCreated",        "send": "Review"}
  ],
  "max_risk": 3,
  "max_parallel": 1
}
```

Es gibt genau einen Autoritätspfad: `steps` führt über das profilierte,
commitgebundene PR-Gate-System und Evidence-Healing. Ein Nicht-Self-Lauf
akzeptiert ausschließlich `default` oder das strengere Opt-in `audit`; `self`,
`legacy` und unbekannte explizite Profilwerte blockieren den Start vor dem
Bus-Wiring. Der Self-Workflow erzwingt `gates.self.json`. Eine fehlende oder
ungültige aktiv ausgewählte Profildatei blockiert ebenfalls fail-closed.
`SAMUEL_AUTHORITY_MODE` und `agent.authority_mode` sind nach dem a4-
Rollbackfenster pensioniert und werden beim Start ausdrücklich abgelehnt.

`max_risk` begrenzt im Watch-Scan die Issues anhand der Labels `risk:low` (1),
`risk:medium` (2), `risk:high` (3) und `risk:critical` (4). Bei mehreren
Risk-Labels gilt das hoechste Risiko; ohne Risk-Label gilt ein Issue
vorsichtshalber als `high` (3). Der heutige synchrone Watch-Pfad unterstützt
ausschließlich `agent.max_parallel=1` und `workflow.max_parallel=1`; beide
Quellen werden einzeln geprüft. Höhere Werte blockieren den Start und werden
nicht durch ein Minimum verdeckt. Die prozesslokale Semaphore erzeugt weder
einen parallelen Dispatcher noch Koordination zwischen mehreren Prozessen. Ein explizites
`samuel run <issue>` ist kein Scan und umgeht deshalb den labelbasierten
Watch-Filter; der Operator hat dieses konkrete Issue bereits ausgewaehlt. Ein
bereits vorhandener autoritativer Plan mit der kanonischen Planüberschrift
blockiert diesen Aufruf vor LLM- und SCM-Schreibzugriffen. Status- und
Blockkommentare bleiben auch mit
Agentmetadaten nichtautoritative Evidence.
`samuel replan <issue> --reason <text>` ist der einzige Ersatzpfad: Er schreibt
zuerst einen an Kommentar-ID und Contract-Hash gebundenen Widerruf, entfernt
`status:approved` und `status:plan`, prüft den SCM-Zustand erneut und erzeugt
erst dann den Ersatzplan. Der angegebene Grund wird ausschließlich diesem
Ersatzplan als abgegrenztes, nicht authority-erweiterndes Replan-Feedback
mitgegeben. Teilausfälle bleiben
ohne Ersatzplan blockiert. Ein abgelehnter impliziter Replan wird als
`PlanReplanRejected` revisionsfest protokolliert und beendet genau diesen Run
im Dashboard als blockiert; `PlanRevoked` bleibt bis zum Ersatzplan ein
nichtterminales Zwischenereignis.

Eine beobachtete menschliche Planfreigabe wird vor `PlanApproved` im bestehenden
Authority-State als create-only `plan_approval.v1` gespeichert. Der Record
bindet die Plan-/Contract-/SCM-Quellenidentität und bleibt über Gatefehler,
MANUAL-Wartezustand, Statuslabelwechsel und Prozessrestart erhalten.
`status:approved`, `status:failed` und die übrigen Statuslabels projizieren den
Workflowzustand; sie erzeugen oder widerrufen keine bereits materialisierte
Approvalauthority. Polling revalidiert das ursprüngliche attributable
Label-Timeline-Ereignis. Der Webhookpfad materialisiert Authority ausschließlich
nach erfolgreicher HMAC-Prüfung. Native Gitea-Labelwebhooks verlangen zusätzlich
genau ein zum Triggerzeitpunkt passendes menschliches Timeline-ADD und binden
dessen Source-ID sowie die Delivery-ID, ohne den Authority-Transport von
`signed_webhook` auf Polling umzudeuten. Explizites Replan beziehungsweise ein anderer
aktiver Plan, Contract, Subject oder Source Snapshot blockiert den alten Record.
Fehlt der Authority-Store, blockieren Watch, Gates und Review; SCM-Evidence wird
nicht als Ersatzauthority rekonstruiert. Webhook und Polling dürfen dieselbe
Labelentscheidung kanalübergreifend wiederholen: Actor, Zeitpunkt, Plan und
Contract müssen identisch sein, und der zuerst persistierte Receipt bleibt
kanonisch. Abweichende Wiederholungen blockieren als Authoritykonflikt.

### Vordefinierte Workflows

| Workflow | Risiko | Parallel | Freigabe und Ablauf |
|----------|-------:|---------:|---------------------|
| `standard` | 3 | 1 | Menschliche Plan-Freigabe; gebundene PR-Gates, Evidence-Healing und Review |
| `watch` | 3 | 1 | Periodischer, sequenzieller Scan; menschliche Plan-Freigabe; gebundene PR-Gates |
| `autonomous` | 2 | 1 | Klare Issues nach Planvalidierung unbeaufsichtigt; Klärungspläne benötigen menschliche Freigabe; PR und anschliessender Review |
| `chat` | 3 | 1 | Menschliche Plan-Freigabe; gebundene PR-Gates |
| `night` | 1 | 1 | Nur Low-Risk-Scan; klare Issues nach Planvalidierung unbeaufsichtigt, Klärungspläne mit menschlicher Freigabe; gebundene PR-Gates |
| `patch` | 2 | 1 | Bis Medium-Risk; klare Issues nach Planvalidierung unbeaufsichtigt, Klärungspläne mit menschlicher Freigabe; voller Plan-/Implement-/Gate-Ablauf |
| `self` | 2 | 1 | Menschliche Plan-Freigabe; eigenes gebundenes Gate-Profil, kein Self-Parity-Score |

### Gebundener Klärungsdialog (#575)

Vor dem ersten Planner-Aufruf klassifiziert eine deterministische Prüfung die
Issue-Quelle als `ready`, `needs_clarification` oder `blocked`. Nur leere oder
ungültige Quellen, ausdrücklich offene Marker und beweisbare
GREP/GREP:NOT-Widersprüche entscheiden diesen Status; ein LLM-Score beweist
keine Vollständigkeit. Ein klares Issue verwendet unverändert den gewählten
Workflow.

Für `needs_clarification` muss der Operator
`agent.planning.clarification_wait_seconds` explizit auf 1 bis 2.592.000
Sekunden setzen. Es gibt höchstens drei Fragen je Runde und zwei Runden. Die
Serie liegt in `planning_clarifications`, bindet Source-Snapshot und dieselbe
#549-Budgetzulassung und überlebt Restart. Die Runtime liest den markierten
SCM-Antwortkommentar erneut und bindet ID, Body-Digest, Akteur sowie Erstell-
und Änderungsrevision. Doppel-, Spät- und Edit-Fälle sowie Timeout,
Rundenerschöpfung und Source-Supersession blockieren ohne partiellen Contract.
Eine neue Serie nach einem terminalen Zustand benötigt ein explizites
`samuel run ISSUE`.

Die angenommene Frage-/Antwortbasis wird sichtbar und maschinenlesbar Teil des
Acceptance Contract v3. Watch, Webhook und Implementation prüfen die mutable
SCM-Evidence erneut. In `autonomous`, `night` und `patch` läuft ein solcher
Plan deshalb ausschließlich über `PlanApproved`; nur ein Plan ohne
Klärungsbasis darf direkt von `PlanValidated` nach `Implement` wechseln. Die
vier Clarification-Events projizieren IDs, Digests, Runden und Status in Audit
und Dashboard, niemals die Antworttexte.

---

## 6. Slice-Katalog (31 Slices)

Jeder Slice hat einen Handler (`handler.py`), der Events/Commands subscribed,
und eigene Tests. Slices sind isoliert — kein Cross-Slice-Import.

| Slice | Aufgabe |
|-------|---------|
| `planning` | Deterministische Issue-Readiness; bei expliziten Lücken höchstens zwei revisionsgebundene Klärungsrunden mit endlicher Operatorfrist, sonst Issue → LLM-Plan; Score <50 blockiert, Score <80 oder negativer Pre-Check erhält genau einen Retry, danach nur `overall_pass=true` → `PlanValidated`; Plan als Issue-Kommentar |
| `implementation` | Plan → Code via Multi-Round LLM-Loop (5 Runden), Patch-Parsing, Branch-Push |
| `context` | Code-Skeleton + File-Slices fuer LLM-Kontext, TOC-Mode bei grossen Files |
| `pr_gates` | 13 registrierte Gates pruefen (siehe §9) und PR erstellen |
| `evaluation` | Passiver Subscriber auf terminale Gate-Evidence; idempotente Rohbeobachtung, replaybare nicht bindende Score-Ableitung und entkoppelte Darstellung; alter Command-Handler nur direkt und nicht verdrahtet |
| `scoring` | Working-Tree-Score-Producer für direkte Kompatibilitätsaufrufe; nicht Teil eines ausgelieferten Workflows |
| `ac_verification` | Akzeptanzkriterien-Verifier (siehe §10) |
| `healing` | Genau ein kriteriumsweiser Healing-Versuch aus gebundener Gate-11-Evidence am fehlgeschlagenen Head; alter Score-Healing-Handler ist nicht verdrahtet |
| `resume` | Busgebundener Koordinator für restartfähige Commit-/Push-/Gate-/PR-Finalisierung; klassifiziert Worktrees, dispatcht bestehende Commands und bietet Status/Operatoraktionen ohne eigene Git-/SCM-Kopplung |
| `state_reconcile` | Portgebundener Restore-Abgleich: inventarisiert persistierte Autorität, Workspaces und bekannte SCM-Wirkungen, persistiert vier Klassifikationen und autorisiert selbst weder Healing noch Resume |
| `review` | LLM-basiertes Code-Review (separates Modell moeglich) |
| `quality` | Plugin-basierte Quality-Checks pro Datei-Extension |
| `quality_metrics` | Gemessene LLM-Qualitaet pro (Provider, Modell, Task): korreliert den letzten LLMCallCompleted eines Issues mit vollständig gekennzeichnetem `ScoreObserved`; alte `EvalCompleted`-Events werden ignoriert; EWMA-Reihen und Dashboard-Calls sind nach Herkunft, Scoring-Policy und Formel getrennt, unattribuierte/andere Serien werden separat ausgewiesen (#153/#589) |
| `run_projection` | Passiver Wildcard-Subscriber; materialisiert redigierte, idempotente Issue-/Run-Ereignisse in SQLite. Workflowgebundene LLM-Telemetrie übernimmt über den Core-Kontext dieselbe Korrelation; Standalone-Aufrufe kennzeichnen die fehlende Bindung. Fehler bleiben nicht freigabeblockierend und landen über Bus/DLQ/Health in der Diagnose (#627/#675) |
| `path_risk` | Konfigurierbarer Pfad-Risiko-Classifier als External-Gate (secrets=block, workflow/container/iac=warn), `config/path_risk.json` (#368) |
| `symbol_resolution` | Halluzinations-Erkennung: neue Imports gegen 5 Quellen (Diff/Generator/Lockfile/Stdlib/First-Party), warn-only, OWASP LLM09 (#368) |
| `coverage_gate` | Coverage-Diff-Gate auf `coverage.py`-XML: modifizierte Datei ohne Test-Treffer → warn (#368) |
| `security` | Advisory Injection-Signal vor Planning; commitgebundener, blockierender Diff-Secret-Gate; gemeinsame aktionsnahe Command-Policy für den Core-Git-Pfad |
| `privacy` | PII-Scrubber, Retention-Katalog/Dry-Run, deaktiviert ausgeliefertes operatorgeführtes 5c-Fundament, Managed Backups, DSGVO-Drittland-Transfer-Check |
| `audit_trail` | Audit-Bridge + OWASP-Mapping |
| `architecture` | Konfig-getriebene Scope-Regeln (`config/architecture.json`) |
| `code_analysis` | Statische Code-Analyse (Imports, Dependencies) |
| `changelog` | Changelog-Generierung aus Kategorien-Labels |
| `dashboard` | Status-, Metrik- und Health-Aggregation fuer das HTTP-Frontend |
| `health` | Aktiver technischer Check für Python, Git-Runtime, Config, versionierten State, Authority/Reconcile/Retention-Notabschaltung, SCM und effektive LLM-Taskrouten. Er projiziert getrennt technische Gesundheit und zweckgebundene Workflow-Readiness; ohne LLM-Liveprobe bleibt Readiness `unknown`. Instanzgebundene Doctor-/Audit-Qualification wird separat aus ihren Fachprüfungen projiziert. Passive Dashboard-/Viewerpfade führen keine Providerprobe aus. |
| `session` | Token-/Zeit-Budget pro Run + Workflow-Checkpoints |
| `sequence` | Event-Sequenz-Tracking + Muster-Analyse (warn/block/off) |
| `setup` | Verzeichnisse anlegen, Env-Var-Validierung, Label-Sync |
| `labels` | Workflow-Label-Transitionen; erfolgreicher Healing-PR räumt `status:failed` nur mit exakt passender Issue-/Korrelations-/Origin-Evidence auf |
| `watch` | Sequenzielles Issue-Polling mit einem prozesslokalen, per `try/finally` freigegebenen Slot |

Der produktive Vertrag aller sieben Promptdateien einschließlich der drei
Prompt-Library-Einträge ohne Runtime-Consumer ist im
[`Prompt-Contract-Audit`](PROMPT_CONTRACT_AUDIT.md) festgehalten.

---

### SCM-Labelstatus bei Evidence-Healing

Ein `GateFailedEvent` setzt den sichtbaren SCM-Status zunächst fail-closed auf
`status:failed`. `HealingAttemptStarted` merkt ausschließlich pro Issue und
Workflow-`correlation_id` den gebundenen `observation_key`. Nur wenn ein späteres
`PRCreated` denselben Lauf und diesen Schlüssel als
`healing_origin_observation_key` bestätigt, entfernt der Labels-Slice den
Fehlerstatus; das Endbild ist `status:wip` plus `needs-review`. Ein Gate-Re-Fail,
`WorkflowBlocked`, `PRCreationFailed` oder `EvaluationSubjectInvalidated`
verwirft diese Recovery-Berechtigung und behält `status:failed`. Ein PR aus
einer anderen Korrelation oder ohne passende Origin-Evidence darf einen
fremden Fehlerstatus nicht löschen.

Dashboard-Zeitdarstellung (#944) konsumiert die bereits vom Setup gespeicherte
`agent.timezone` aus der effektiven `IConfig`. Die öffentliche HTML-Shell und
Status-API binden dieselbe Zone; die UI zeigt absolute Zeitpunkte mit Offset
und IANA-Zone statt Roh-UTC oder der zufälligen Browserzone. Fehlende/ungültige
Konfiguration fällt sichtbar auf UTC zurück. Ein Browser ohne die konfigurierte
Zone zeigt UTC mit ausdrücklichem Fallbackhinweis; ältere Werte ohne Offset
bleiben unverändert und als „Zeitzone unbekannt“ markiert. Backend-/Audit-/API-
Zeitwerte und Freshness-/Workflowauthority werden nicht umgerechnet.

Die Workflow-Stages des Dashboards werden getrennt aus der persistenten
SQLite-Run-Projektion abgeleitet,
nicht aus diesen SCM-Labels. Dabei ist ein Command-Dispatch kein Erfolg:
`PlanReplanRejected` beendet den abgelehnten Run als `blocked`, löst im
Labels-Slice aber bewusst keine Transition aus, weil der bestehende Plan samt
Workflowlabels weiterhin autoritativ bleibt. `PlanRevoked` gehört zum
expliziten Ersatzlauf und bleibt nichtterminal.
`CreatePR` allein bleibt `pending`. `PRCreated` schließt die PR-Stufe; in einem
Workflow mit `review_required=true` bleibt die Review-Stufe bis
`ReviewCompleted`, `ReviewBlocked`, `MergeOutcomeUnknown` oder `PRMerged`
offen. Blockiert `GateEvaluationCompleted` den Candidate
ohne PR-Outcome, bleibt die Gates-Stufe `failed` und die PR-Stufe ist `blocked`;
das vollständige terminale Gate-Event kann einen vorherigen `GateFailed`-Eintrag
nicht als Erfolg übermalen. Die Healing-Stufe zählt nur
`HealingAttemptStarted` beziehungsweise korrespondierende abgeschlossene
Attempt-Evidence. Eine reine `HealingClassified`-Nichtheilbarkeit ohne Attempt
erscheint als `not_attempted` mit Zähler 0 und nicht als fehlgeschlagener
Heilungsversuch (#578). Diese Gate-, PR- und Healing-Outcomes werden bei
vorhandener Korrelation nur innerhalb des jeweiligen Workflow-Laufs
ausgewertet.

Auch der zusammenfassende Issue-Status in Listen- und Detailansicht wird aus
dem neuesten korrelierten Lauf gemeinsam abgeleitet. Maßgeblich sind die
fachlichen Ereignisse und ihre Eventzeit, nicht die physische JSONL-
Schreibreihenfolge: Bei synchron verschachteltem Dispatch darf ein außen erst
nach `PlanPosted`/`PlanValidated` persistiertes `IssueReady` den erreichten
Planstatus nicht auf `ready` zurückstufen. `last_event` und sein Zeitstempel
benennen deshalb die Evidence, die den sichtbaren Status begründet. Ein neuer,
noch unvollständiger Lauf bleibt `unknown` und erbt weder PR-Erfolg noch einen
anderen optimistischen Zustand aus einem älteren Lauf (#738).

`attempts_used` folgt derselben fachlichen Grenze: Vor
`HealingAttemptStarted` sind null Versuche verbraucht, danach genau einer,
auch wenn Provider, Truncation-/Budgetprüfung oder Claim-Finalisierung
terminal fehlschlagen. Interne Transport-Retries eines Provideradapters zählen
nicht zusätzlich. `total_tokens` enthält nur durch eine erhaltene Antwort
belegte Nutzung; bei einem Providerfehler ohne Usage-Evidence bleibt der Wert
`0`.

Ein nicht truncierter Implementation-Call ohne strukturiert oder textuell
parsbaren Patch publiziert `WorkflowBlocked` mit
`task=implementation`, `reason=no_parseable_patches`, einer nichtleeren
maschinenlesbaren Fehlerkennung und ausschließlich inhaltsfreier Diagnose
(`round`, `patch_count`, `applied_patch_count`). Das Dashboard ordnet diesen
Block der Implementierungsstufe zu; der LLM-Antworttext ist kein Bestandteil
dieser Terminaldiagnose (#588).

Lehnt der Applier einen gültig geparsten und sicher aufgelösten Patch ab,
führt der Loop die konkrete Ursache bis zum terminalen Ergebnis. Bei
`no_progress` und `partial_failure` enthält `diagnostic` pro betroffenem Patch
einen stabilen Fehlercode, das kanonische relative Ziel und eine auf 500
Zeichen begrenzte, secret-bereinigte Detailmeldung. Der frühe
`WorkflowBlocked`-Pfad für `no_progress` übernimmt diese Diagnose mit derselben
Workflow-Korrelation. Modellantwort und unredigierte Appliermeldung werden
nicht in die terminale Evidence kopiert; der historische Blockgrund
`self_mode_no_progress` bleibt aus Kompatibilitätsgründen auch im Standardmodus
unverändert (#828).

Der Implementation-LLM-Loop behandelt alle von ihm erstmals berührten Pfade
als eine prozesslokale Transaktion. Nur `success=true` übernimmt die Änderungen.
Tokenlimit, `no_parseable_patches`, `no_progress`, `partial_failure` und eine
Exception stellen Inhalt, Existenz und Modus der betroffenen Dateien auf den
Zustand vor dem Loop zurück; neue, danach leere Verzeichnisse werden entfernt.
Die inhaltsfreie Rollback-Evidence nennt Status und Anzahlen. Ein nicht
vollständig möglicher Restore wird nicht als ursprünglicher Fehler kaschiert,
sondern blockiert als `workspace_rollback_failed` mit `trigger_reason`. Das ist
weder ein Git-Reset noch ein restart-fähiger Checkpoint: abrupter Prozessverlust
(#482), die spätere Git-Finalisierung und die vorgelagerte kumulative
Tokenzulassung (#549) liegen außerhalb dieser Loop-Grenze (#598). Die mutationsfreie fachliche
Patchablehnung (#601) und die zulässige Zielmenge einschließlich
Git-Control-Plane (#600, #603) sind eigene vorgelagerte Controls.

Vor dieser Transaktion validiert `patch_targets.resolve_patch_target()` alle
Ziele einer Modellantwort vollständig. Zulässig sind ausschließlich
normalisierte relative POSIX-Pfade, deren kanonisches Ziel innerhalb der
aufgelösten Projektwurzel liegt. Absolute POSIX-/Windows-/UNC-Pfade, `..`,
nicht portable Backslashes, Steuerzeichen und Symlink-Ausbrüche beenden den
Loop vor dem ersten Apply als `unsafe_patch_target`. Ein zulässiger Symlink
wird auf sein kanonisches, weiterhin internes Ziel festgelegt; der kanonische
relative Pfad fließt in Apply-Ergebnis und Git-Staging. `WorkflowBlocked`
enthält nur Reason-Codes, Zähler und Rollback-Evidence, nie den abgelehnten
LLM-Pfad. Normale neue Unterverzeichnisse und Nicht-Python-Dateien bleiben
zulässig (#600). Zusätzlich ist jeder `.git`-Pfadbestandteil unabhängig von
Groß-/Kleinschreibung reserviert. Ein read-only Core-Git-Aufruf ermittelt
einmal pro Loop die effektiven absoluten Git-/Common-/Index-/Object-Pfade;
dadurch sind auch linked worktrees, separate Git-Dirs und von Git wirksam
aufgelöste `GIT_*`-Overrides vor Excerpt-Read, Snapshot und Write geschützt.
Normale Dotfiles außerhalb dieser Verwaltungspfade bleiben zulässig (#603).

SEARCH/REPLACE erhält den vorhandenen EOF-Zeilenumbruch und terminale
Leerzeilen der Ausgangsdatei; eine Datei ohne EOF-Abschluss erhält keinen
künstlich erzwungenen Abschluss (#937). Dies gilt für die gemeinsame
Line-/Python-/JSON-/YAML-Kandidatenfunktion. WRITE und REPLACE-LINES behalten
ihre bisherigen Operationen; Syntax-/JSON-Prüfung und Rollbackgrenzen bleiben
unverändert.

Für JSON-SEARCH/REPLACE und -REPLACE-LINES berechnet der Applier den
vollständigen Kandidaten schreibfrei, validiert ihn mit `json.loads()` und
schreibt erst bei Erfolg. Eine fachliche Ablehnung verändert deshalb weder
Inhalt noch Inode, Modus, Größe oder MTime und der Retry liest den letzten
gültigen Zustand. Die übrigen vorhandenen Line-/Python-/YAML-Fehlerpfade
schreiben ebenfalls erst nach erfolgreicher Candidate-Prüfung. Das ist keine
Zusage für während eines OS-Writes auftretende I/O-Fehler; diese propagieren
als Exception in die Loop-Transaktion. Python-WRITE verwendet nun denselben
`ast.parse()`-Hook vor Verzeichnisanlage und Write wie die beiden partiellen
Python-Operationen (#601, #606).

Die Loop-Transaktion erfasst vor dem Apply weiterhin vorsorglich den
Vorzustand, damit eine Write-Exception restaurierbar bleibt. Meldet der
Applier fachlich `False`, wird dieser Snapshot nur dann freigegeben, wenn
Existenz, Inhalt und Modus nachweislich unverändert sind. Ein terminaler
Rollback schreibt diesen unveränderten Pfad dadurch nicht erneut und verändert
seine MTime nicht; bei jeder Abweichung bleibt die Wiederherstellungsbasis
erhalten (#606).

### Gemeinsamer Worktree-Manager (#618)

Der Bootstrap erzeugt genau einen `GitWorktreeManager` hinter dem
`IWorkspaceManager`-Port. Vor Kontextaufbau und Implementation entsteht ein
mutierbarer Run-Worktree, gebunden an Repository, Correlation/Run, Issue-Branch
und `origin/main`. Der Hauptcheckout bleibt unverändert. Ein Healing-Nachlauf
verifiziert den erwarteten Remote-Head und verwendet denselben Branch; Gate 11
erzeugt für den commitgebundenen Head parallel einen detached
Verifikations-Worktree desselben Managers.

`agent.workspace.work_dir` liegt getrennt von Projektwurzel und `data_dir`.
Seine SQLite-Registry ist Workspace-Betriebszustand und ausdrücklich kein
Runtime-State-Backup. Vor Mutation prüft der Adapter ein lokales Dateisystem,
Freiplatz samt konservativer Registrybuchung und Quarantänegrenzen. Ein
Branch-`flock` plus Gits eigene Worktree-Sperre verhindert konkurrierende
Eigentümer. Unerwartete Prozessabbrüche bleiben zunächst unverändert erhalten.
Der Resume-Koordinator klassifiziert sie nach vollständigem Wiring: Nur ein
gebundener Finalisierungs-Checkpoint darf übernommen werden, ein verwaister
Baum ohne Resume-Autorität wird begründet quarantänisiert. Terminale Bäume dürfen kontrolliert entfernt werden;
aktive oder quarantänisierte Einträge schützen `git worktree prune`.

Ein frischer Baum übernimmt keine `.env`, `data/`, `.venv`, HOME- oder
Cachedateien. Die Referenzmessung ergab für gleichzeitig vorhandenen Run- und
Verifikationsbaum 36.760 KiB sowie 179 ms und 114 ms Erzeugungszeit; das ist
Hardware-Evidence, kein globales Kapazitätsversprechen. Ein Worktree ist keine
Prozess-, Hostdatei-, Netzwerk- oder Ressourcensandbox. Der aktuelle lokale
Verifier bleibt bis zum atomaren Provider-Cutover als Legacy-Risiko sichtbar;
das Ziel ist externe Candidate-Ausführung mit gebundener Evidence nach #679,
nicht ein eigener S.A.M.U.E.L.-Sandboxbau.

Nach dem Staging bindet der Commit-Intent `workspace_id`, Parent und
`git write-tree`. `git commit-tree` erzeugt den Commit ohne geerbte Hooks;
unmittelbar vor `git update-ref --stdin` wird der Index-Tree erneut geprüft.
Der Ref-Move verwendet CAS und Reflog. `agent.git.signing_required=true`
verlangt einen expliziten `signing_key` und blockiert sonst fail-closed.
Formatierung durch fremde Hooks findet nicht mehr still statt. Author und
Committer stammen aus einem vollständigen
`SAMUEL_GIT_AUTHOR_NAME`/`SAMUEL_GIT_AUTHOR_EMAIL`-Paar. Fehlt das Paar
vollständig, verwendet die Referenzimplementation stabil
`S.A.M.U.E.L. Reference Agent <samuel-reference@localhost.invalid>`; ein
partielles Paar blockiert. Diese Metadaten sind Attribution, keine Authority,
und werden weder in globale noch lokale Git-Konfiguration geschrieben.
Netzwerk-Git verwendet zusätzlich genau einen `IGitTransportAuth`-Port für
die Fetch-Pfade des Managers und die Fetch-/Push-Pfade aus `core/git.py`.
Der ausgelieferte HTTP-Adapter autorisiert ausschließlich die konfigurierte
Repository-URL und `fetch` beziehungsweise `push`. Er delegiert Benutzername
und Token über den installierten absoluten `samuel-git-askpass`-Helper nur an
den jeweiligen Netzwerk-Git-Kindprozess. Token in Argv (`http.extraHeader`),
Remote-URL oder Git-Konfiguration sind verboten; interaktive und globale
Credential-Fallbacks sind deaktiviert. Lokale Git- und Candidateprozesse
erhalten diese Werte nicht. Bei Gitea muss `SCM_USER` das zum Token gehörende
Konto nennen; GitHub verwendet den providerspezifischen Token-Benutzer
`x-access-token`.

Der Token steht während des Netzwerkaufrufs weiterhin im Environment des
Git-Kindprozesses; seine bestehende `IAuthProvider`-Quelle verbleibt außerdem
in der vertrauenswürdigen Runtime und kann beim Env-Provider als `SCM_TOKEN`
vorliegen. Ein anderer Prozess desselben Service-Accounts kann Runtime- oder
Kindprozessdaten auf Systemen mit entsprechend lesbarem
`/proc/<pid>/environ` möglicherweise beobachten. Nachgewiesen sind daher Argv-, URL-, Config-, Log- und
Candidate-Redaktion im Single-Service-Account-Profil, keine vollständige
Mehrbenutzer- oder Prozesssandbox.
Quarantänen speichern eine ausgelieferte Operatorfrist von 168 Stunden in der
Registry. Die Frist löscht nichts automatisch; erst ein begründetes
`workspace discard` terminalisiert geprüfte Evidence, danach darf `prune`
aufräumen.

```bash
samuel workspace list --json
samuel workspace inspect WORKSPACE_ID --json
samuel workspace quarantine WORKSPACE_ID --reason 'operator finding' --json
samuel workspace discard WORKSPACE_ID --reason 'evidence reviewed' --json
samuel workspace prune --json
```

---

## 7. Adapter-Katalog

Adapter implementieren die Ports aus `samuel/core/ports.py`. Sie werden im
Bootstrap injiziert und sind die einzige Bruecke zur Aussenwelt.

| Adapter | Implementierte Ports | Notizen |
|---------|---------------------|---------|
| `adapters/api/` | `IExternalEventSink`, `IExternalTrigger` | REST-API + Webhook-Ingress mit Signatur-Validierung |
| `adapters/audit/` | `IAuditSink` | `JSONLAuditSink` (Volltranskript, HMAC-Chain) + `AsyncAuditSink` + `SARIFAuditSink` (nur Findings, #368) + `FanOutAuditSink` (parallele Sinks) |
| `adapters/auth/` | `IAuthProvider` | `StaticTokenAuth` |
| `adapters/git_transport/` | `IGitTransportAuth` | repository- und operationsgebundene HTTP-Authentisierung über installierten Askpass-Helper; keine Credential-Plattform |
| `adapters/gitea/` | `IVersionControl`, `ISCMCheckEvidenceReader`, `IExecutionProvider` | Issue/Comment/PR/Label/Branch, begrenzter Pull-only-Actions-Check-Read sowie der deaktiviert ausgelieferte requestgebundene Gitea-Actions-Referenzprovider |
| `adapters/github/` | `IVersionControl` | inkl. `GitHubAppAuth` (JWT mit RS256) |
| `adapters/llm/` | `ILLMProvider` | 8 Provider (siehe §8) + `FixedResponseAdapter` (deterministisch, fuer reproduzierbare E2E-Runs, #368) |
| `adapters/notifications/` | `INotificationSink` | Slack, Teams, Generic Webhook |
| `adapters/quality/` | `IQualityCheck` | Pylint/Mypy/Ruff via `config/hooks.json`; der File-EWMA-Adapter bleibt nur als Legacyformat lesbar |
| `adapters/secrets/` | `ISecretsProvider` | `EnvSecretsProvider` |
| `adapters/skeleton/` | `ISkeletonBuilder` (Registry) | 5 Builder: Python, TypeScript, Go, SQL, Config |
| `adapters/state/` | `IObservationStore`, `IRunProjectionStore`, `IQualityMetricsRegistry`, `IAuthorityStateStore`, `IIdentityStateStore`, `IRetentionStateStore`, `IRetentionExecutionStore`, `IStateDiagnostics` | lokales SQLite-Schema v10; Evaluation-/Quality-/Run-Projektion, Autoritäts-, Workflow-Budget-, Planning-Klärungs- und Identityzustand, Restore/Reconcile, Retention-Katalog, Kategorie-Autorität, Ausführungsbelege und Managed-Backup-Registry |
| `adapters/workspace/` | `IWorkspaceManager` | gemeinsamer Git-Worktree-Lifecycle für mutierbare Run- und detached Verifikationsprofile; Registry/Locks/Quarantäne/Prune, ausdrücklich keine Prozesssandbox |

### Ports im Detail

`IExecutionProvider` hält nur `dispatch`, `reconcile` und `read_evidence`.
Scheduling, Runner, Queue und providerinterner Lifecycle bleiben beim Provider.
Der Core-Vertrag bindet Request, Run/Attempt und kriteriumsweise Evidence; er
ist keine allgemeine Jobplattform.

`IVersionControl` (Auszug): `get_issue`, `get_comments`, `post_comment`,
`create_pr`, `swap_label`, `list_labels`, `create_label`, `list_issues`,
`close_issue`, `merge_pr`, `merge_pr_expected`, `issue_url`, `pr_url`,
`branch_url`, `capabilities`.

Die 31 Ports gesamt: `IVersionControl`, `ISCMCheckEvidenceReader`,
`IExecutionProvider`,
`IProviderVerificationRecovery`, `IProviderVerificationCoordinator`,
`ILLMProvider`, `IAuthProvider`,
`IGitTransportAuth`,
`IAuditLog`, `IConfig`, `IAuditSink`, `ISecretsProvider`, `ISkeletonBuilder`,
`IPatchApplier`, `INotificationSink`, `IQualityCheck`, `IExternalGate`,
`IQualityMetricsRegistry`, `IExternalEventSink`, `IExternalTrigger`,
`IDashboardRenderer`, `IProjectRegistry`, `IPromptRiskAnalyzer`,
`IObservationStore`, `IRunProjectionStore`, `IAuthorityStateStore`,
`IIdentityStateStore`,
`IRetentionStateStore`, `IRetentionExecutionStore`, `IStateDiagnostics`,
`IWorkspaceManager`.

---

## 8. LLM-Stack

```
                    ┌──────────────────┐
                    │  LLMFactory      │  liest config/llm/*.json
                    └─────────┬────────┘
                              ▼
                    ┌──────────────────┐
                    │ Scheduled/Task   │ — validierte Zeit-/Task-Routen
                    │ Routing Adapter  │
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
| `gemini.py` | Google Gemini | API-Key | Authentisierung über `x-goog-api-key`, nicht über URL-Query |
| `openai.py` | OpenAI direkt | API-Key | benoetigt `openai`-Extra |
| `manual.py` | Manual-Dateibruecke | – | wartet auf eine durch Mensch oder Tool publizierte Response-Datei |
| `fixed.py` | FixedResponse (Test/Demo) | – | deterministische Antworten fuer reproduzierbare Tests, kein Factory-Provider |

Der gemeinsame OpenAI-kompatible Adapter akzeptiert einen normalen Call nur,
wenn der erste Choice ein Objekt mit Message und nicht leerem String-Content
ist. Meldet der Provider jedoch ausdrücklich `length`, `max_tokens` oder
`token_limit`, bleibt auch bei noch leerem sichtbarem Content dieser
Truncation-Grund zusammen mit den realen numerischen Usage-Zählern erhalten.
Der aufrufende Slice blockiert dann über seinen vorhandenen
`llm_response_truncated`-Pfad. Der Adapter übernimmt dabei weder
`reasoning_content` noch Raw-Payload in Ergebnis oder Evidence und erhöht das
Budget nicht automatisch. Die nativen Claude-, Gemini- und Ollama-Adapter
prüfen analog ihre jeweiligen offiziellen Content-/Block-/Errorformen; ein
leerer oder strukturell unbrauchbarer Response ohne expliziten
Truncation-Grund wird nicht als erfolgreicher LLM-Call gezählt.
Provider-Errorobjekte sowie HTTP-/Transportfehler werden über denselben
schmalen Adapterhelfer ohne Raw-Payload oder Providermeldung in den bestehenden
Core-Vertrag `ProviderUnavailable` mit begrenztem Code, optionalem Status und
expliziter Retrybarkeit normalisiert. Fehlende, leere oder strukturell
ungültige Inhalte ohne explizite Truncation sind permanent fehlerhaft; 429,
die unterstützten 5xx-/529-Statuscodes und Transportausfälle sind transient.
`RetryLLMAdapter` wiederholt nur diese transienten Fehler innerhalb der
konfigurierten Grenze.
Nach Ausschöpfung publiziert Planning mit Issue und Workflow-Korrelation
`LLMUnavailable` sowie `PlanBlocked`; `MeteringLLMAdapter` erzeugt für den
fehlgeschlagenen Call kein `LLMCallCompleted`. Eine explizit leere
Fallbackliste bleibt leer.

Endet eine Planning-Antwort explizit am Ausgabetokenlimit, blockiert der
Workflow weiterhin mit `TokenLimitHit` und `PlanBlocked`. Der Issue-Kommentar
ordnet diesen Fall getrennt von einem inhaltlich schwachen Plan ein: Er
verweist auf das wirksame `max_tokens`- und Modelllimit, die ausdrückliche
Modell-/Prompt-Eignung und einen bewusst neu gestarteten Planning-Lauf. Er
fordert nicht pauschal neue Akzeptanzkriterien und aktiviert weder stillen
Retry noch unkonfigurierten Fallback.

Die reale isolierte D0-Evidence aus #701 belegt Ollama in beiden Richtungen:
Der positive Lauf auf dem unveröffentlichten `main`-Kandidaten `7fac8e7`
erzeugte mit echten Input-/Output-Zählern und `stop_reason=stop` einen
validierten Plan (Plan-/Acceptance-Score 100, 5/5 Checks). Dieser Score misst
die Struktur und Prüfbarkeit des Plans, nicht die Qualität des Modells. Der
reale a15-Dashboard-Quality-Pfad kennzeichnet `qwen2.5-coder:3b` zugleich als
`below_min` zur konfigurierten lokalen 7B-Warnschwelle; der unattribuierte Call
besitzt weder einen gebundenen Modellqualitätsdurchschnitt noch einen EWMA.
Die Parameterwarnung bleibt informativ und begründet keine Blockier- oder
Routingentscheidung. Bei absichtlich nicht erreichbarem Ollama-Endpunkt
erzeugte a15 nach genau zwei Retry-Warnungen korreliert
`LLMUnavailable` und `PlanBlocked`, ohne `LLMCallCompleted` und ohne Fallback.
Claude und Gemini bleiben als providergetreue Fixture-Evidence gekennzeichnet.
Dieser Nachweis behauptet weder allgemeine Providerverfügbarkeit noch eine
bestimmte lokale Modellperformance und veröffentlicht keinen neuen Release.

Der optionale OpenRouter-Kostenhinweis aus #454 bleibt davon getrennt und rein
advisory. `config/llm/defaults.json::tasks.<task>` führt dafür
`cost_advisory_enabled` und die relative
`overqualification_margin_ratio` (ausgeliefert `0.20`). Die Klassifikation
verwendet ausschließlich den bestehenden Taskindex und die explizite
Taskschwelle; bei Schwelle 50 beginnt `overqualified` ab 60. Ein alternativer
Modellhinweis setzt dieselbe frische Cache-/Benchmarkgeneration, dieselbe
Schwelle, positive Prompt- und Completionpreise, keine zusätzlichen
Preiskomponenten und strikte Pareto-Dominanz voraus. `no_data`,
`below_threshold`, kreuzende Preisachsen und inkompatible Generationen bleiben
ohne Empfehlung. Cache-Schema 3 bewahrt nichtleere zusätzliche
Preiskomponenten; ältere Cache-Schemata sind für diesen Hinweis
`upgrade_required` und verlangen `samuel refresh-pricing`. Bei mehreren
Kandidaten dient die lexikografische Modell-ID
nur als reproduzierbarer Präsentations-Tie-Break; sie behauptet kein
workloadabhängiges Kostenoptimum. Auswahl, Routing, Budget, Gate und Freigabe
bleiben unverändert.

Der Taskeditor liest den Freshness-Hinweis aus seiner eigenen
Modelllisten-Antwort. Ein nichtleerer Katalog wird auch ohne Cache-Metadaten
gerendert; bei `needs_refresh` zeigen die Modellhinweise den veralteten
Katalogstand an. Ein erfolgreicher Listenaufbau bestätigt keine
Endpoint-/Kontoverfügbarkeit und verändert keine gespeicherte Taskroute.
Verspätete Antworten eines früheren Providerwechsels oder eines geschlossenen
Editors werden verworfen. Eine bisher ausgewählte, inzwischen nicht gelistete
Modell-ID bleibt als nicht bestätigt sichtbar; leere Listen und Ladefehler
behaupten ebenfalls keine Verfügbarkeit und ersetzen keine gespeicherte Route.

Die Adapterprüfung folgt den offiziellen Protokollen für
[Claude-Messages und API-Fehler](https://platform.claude.com/docs/en/api/errors),
[Gemini `GenerateContentResponse`](https://ai.google.dev/api/generate-content)
und [Ollama-Generate-/Error-Antworten](https://docs.ollama.com/api/errors).
Diese Quellen bestimmen nur das jeweilige Transport-/Antwortschema; Retry-,
Fallback- und Workflowauthority bleiben der oben beschriebene Samuel-Vertrag.

#### Manual-Dateibrueckenprotokoll

`ManualAdapter` schreibt Besitzer-Sidecar und Request jeweils zuerst vollständig
in eine eindeutige temporäre Datei **im selben Verzeichnis**. Der Sidecar wird
zuerst atomar als `req_<id>.pid`, danach der vollständige JSON-Request atomar
als `req_<id>.json` publiziert. Damit ist der finale Requestpfad selbst das
Readiness-Signal und kein Consumer kann eine sichtbare leere/partielle
Request-Datei lesen. Scheitert das Publish, bleiben weder konsumierbarer
Request noch verwaister Besitzer-Sidecar zurück.

Danach wartet der Adapter in `llm.manual.data_dir` (Default
`data/manual_llm`) auf `resp_<id>.json`. Ein Producer schreibt die Antwort
ebenfalls zuerst vollstaendig in eine temporaere Datei **im selben
Verzeichnis** und publiziert sie danach mit einem atomischen Rename, zum
Beispiel:

```python
response = {
    "text": "Antwortinhalt",
    "input_tokens": 0,
    "output_tokens": 0,
    "cached_tokens": 0,
    "stop_reason": "end_turn",
    "model_used": "manual",
}
temporary = data_dir / f"resp_{request_id}.json.tmp"
final = data_dir / f"resp_{request_id}.json"
temporary.write_text(json.dumps(response), encoding="utf-8")
os.replace(temporary, final)
```

Jede Seite besitzt ihre temporaere Datei und entfernt sie bei einem
Schreibfehler selbst. Die Response-Wurzel ist ein JSON-Objekt; fehlende
optionale Tokenfelder werden als `0`, `stop_reason` als `end_turn` und
`model_used` als `manual` gelesen. Zur Absicherung nicht atomarer
Human-/Tool-Writer behandelt der Reader eine sichtbare leere, syntaktisch
unvollstaendige, unlesbare oder an der JSON-Wurzel protokollwidrige Response bis
zum konfigurierten `llm.manual.timeout` als noch nicht fertig und pollt mit
`llm.manual.poll_interval` weiter; das Intervall muss groesser als `0` sein.
Bei Ablauf endet der Call fail-closed mit dem letzten konkreten
Lese-/Parsefehler. Bei Erfolg werden Request, Response und PID-Sidecar entfernt;
bei Timeout bleibt der Request sowie eine vorhandene ungueltige Response zur
Diagnose erhalten, der PID-Sidecar wird entfernt. Die Startup-Orphan-Bereinigung
aus #248 bleibt davon unberuehrt.

Fuer deterministische Unit-/E2E-Tests ist `FixedResponseAdapter` vorgesehen;
`ManualAdapter` wartet absichtlich auf einen externen Producer und ist daher
nicht deterministisch.

### Querschnittsmodule

- `factory.py` — Provider-Wahl per Config + ENV
- `circuit_breaker.py` — Open-Circuit nach `circuit_breaker.threshold` Fehlern
- `sanitizer.py` — HTML-/Längenbereinigung und konfigurierbares PII-Scrubbing von User-Nachrichten; kein allgemeiner Secret-/Injection-Filter
- `prompts.py` — System-Prompts laden (`samuel/core/prompts/*.md`)
- `costs.py` + `metering.py` — OpenRouter-Modell-/Benchmark-/Preis-Cache,
  taskbezogene rein informative Eignungs-/Paretohinweise und Token-Verbrauch
  je Run
- `task_routing.py` — pro Task-Typ ein Provider/Modell-Mapping
- `scheduled_routing.py` — validierte Tag/Nacht-Schedules
- `provider_errors.py` + Provideradapter — gemeinsamer begrenzter
  `ProviderUnavailable`-Fehlervertrag; das jeweilige Response-Schema bleibt im
  Adapter
- `http.py` — gemeinsamer httpx-Wrapper

---

## 9. PR-Gates (13)

`samuel/slices/pr_gates/gates.py` definiert das `GATE_REGISTRY`. Jeder Gate ist
eine Funktion `(GateContext) -> GateResult`. Status pro Gate kommt aus
`config/gates.json` (`required` / `optional` / `disabled`).

`GateResult` verwendet seit #620 Schema v2: ausgeführte Gates tragen
`executed=true` und einen booleschen `passed`-Wert; ein wegen gescheiterter
Vorbedingung nicht ausgeführtes Gate trägt ausschließlich
`executed=false`, `passed=null`, `status=skipped_precondition`. Jeder Eintrag
trägt zusätzlich einen stabilen `reason_code`, `required|optional`-Authority
und denselben `EvaluationSubject`. Der Handler
führt 7b, 8, 9, 13a und 13b vor jeder Candidate-Ausführung aus. Blockiert eines
dieser Gates als `required`, werden alle nachgelagerten internen und externen
Gates vollständig als SKIP in das eine terminale Event aufgenommen. Optionales
Preflight-Evidence blockiert weiterhin nicht.

Vor der Ausführung bindet der Handler einen unveränderlichen
`EvaluationSubject` aus Repository, vollständigem Base-/Head-SHA,
Acceptance-Contract-Hash und Gate-Policy-Version/-Digest. Dateiliste und
vollständiger Diff stammen aus genau diesem Commit-Paar. Das Ressourcenlimit
`parameters.max_diff_bytes` (Default 2.000.000 Bytes) blockiert bei
Überschreitung als `not_evaluated`; der Prüfpfad kürzt nicht. Der tatsächliche
PR-Head wird vor `PRCreated` und nach einem strukturierten Review-Pass nochmals
vor dem Mergeintent abgeglichen (#515/#468).
Gate 9 liest Candidate-Dateien über den SCM-Port aus genau diesem Head;
`parameters.max_quality_file_bytes` (Default 1.000.000 Bytes je Datei) ist
fail-closed und Teil des Policy-Digests.

| # | Funktion | Pruefung | Default |
|---|----------|----------|---------|
| 1 | `gate_1_branch_guard` | Branch ist nicht `main`/`master` | Required |
| 2 | `gate_2_plan_comment` | Plan-Kommentar > 20 Zeichen vorhanden | Required |
| 3 | `gate_3_metadata_block` | Substring `Agent-Metadaten` ist vorhanden | Required |
| 5 | `gate_5_diff_not_empty` | Diff ist nicht leer | Optional |
| 6 | `gate_6_self_consistency` | Mehr als die Hälfte extrahierter Plan-Basenames ist im Diff | Optional |
| 7 | `gate_7_scope_guard` / `ForbiddenPathGuard` | Verbotene Fallback-Pfade; delegiert bei PathRisk und prüft keinen Contract-Scope | Required |
| 7b | `gate_7b_contract_scope` / `ContractScope` | Vollständige Changed-Files gegen Contract-Scope Schema 2; optionale Ergänzungen nur aus `architecture.json`, fehlende/stale Evidence blockiert | Required |
| 8 | `gate_8_slice_gate` | Neu hinzugefügte Python-`from samuel.slices.X import`-Zeilen zwischen Slices | Required |
| 9 | `gate_9_python_syntax` | CPython-AST des exakten Candidate-Blobs; Nicht-Python/Löschung = `not_applicable`, Missing/Fehler = Fail | Required |
| 11 | `gate_11_ac_verification` | Alle Required-ACs mit strukturierter Evidence für exakt Contract/Head/Policy bestanden | Required |
| 12 | `gate_12_ready_to_close` / `AcceptanceReadiness` | Vollständigkeitsstatus derselben Evidence; keine eigene Verifikation | Optional |
| 13a | `gate_13a_branch_freshness` | Head höchstens 50 Commits hinter gebundener Base; nicht prüfbar = fail | Optional |
| 13b | `gate_13b_destructive_diff` | Loeschungen ≤ 3× Hinzufuegungen | Required |

Fehlgeschlagene optionale Gates werden in `GateEvaluationCompleted` und im
Reviewer-Briefing erfasst, blockieren aber nicht. `disabled`-Gates werden
nicht ausgeführt und erzeugen kein Gate-Ergebnis.

**Profile (#368/#399):** `config/gates.json` ist das Standardprofil,
`config/gates.self.json` das fest an den Self-Workflow gebundene Profil und
`config/gates.audit.json` das strikte Opt-in-Profil via
`SAMUEL_GATES_PROFILE=audit`. Die ungebundenen Gates 4 und 10 sowie
`config/gates.legacy.json` sind entfernt. Unbekannte oder pensionierte Gate-IDs,
Doppelbelegungen und Profilüberschneidungen werden fail-closed abgelehnt. Gate
13b bleibt in allen drei Profilen required. Vollständige Ist-Bewertung:
`docs/CAPABILITY_MATRIX.md`; der alte Pfad
`docs/GATE_COMPLIANCE_MATRIX.md` verweist dorthin.

**External-Gates** (`IExternalGate`): Der Bootstrap verdrahtet immer
`diff_secret_scan`, `symbol_resolution` und `coverage_diff`; `path_risk` kommt
bei auswertbarer `config/path_risk.json` hinzu. Der Handler behandelt
Adapterfehler und `passed=false` als blockierend. `symbol_resolution` und
`coverage_diff` sowie warn-Klassen des PathRisk-Adapters melden ihre Findings
bewusst mit `passed=true` und bleiben dadurch advisory. `diff_secret_scan` und
PathRisk-`block`-Klassen können den PR stoppen. Exakte Aktivierung,
Positiv-/Negativbeispiele und Grenzen stehen in der
[PR-Gate-Pipeline](../technische%20Beschreibungen/pipeline_pr_gates.md#external-gates-im-detail).

### Review und erwarteter Head

`ReviewHandler` erhält den vollständigen Diff und denselben
`EvaluationSubject`, Acceptance Contract und GateResult-Satz aus `PRCreated`.
Der Provider muss genau ein geschlossenes JSON-Dokument mit `pass`, `block`
oder `indeterminate` liefern. Das Dokument wiederholt Subject, Diff-SHA-256,
Policy, Toolvertrag und Prompt-SHA-256; unbekannte Felder, Freitext,
unvollständige Bindungen und ein bloß erfolgreicher Call werden
`ReviewBlocked`. `ReviewCompleted` ist nur Evidence für einen validierten
Reviewentscheid und ersetzt keine Planfreigabe.

`auto_merge_pr` ist default-off. Bei Aktivierung verlangt der Mergepfad nach
einem Review-Pass erneut den aktiven unveränderten Plan, eine menschliche
Approvalquelle, vollständig gebundene Required-Gates und das exakte PR-Paar.
Nur Adapter mit `native_expected_head_merge` und eine Installation mit dem
separaten default-off Nachweis `expected_head_merge_qualified` werden
automatisch verwendet; Gitea sendet den erwarteten Head als `head_commit_id`.
Vor dem Call wird ein deterministischer, an PR, Subject und Review-Digest
gebundener `merge_pr`-Intent im bestehenden Authority-State angelegt.
Erfolg, Head-Race und unbekannter Transportausgang werden genau einmal gegen
Mergedstatus und Revision des realen PR reconciliert. `MergeOutcomeUnknown`
bleibt terminal blockiert und wird nicht automatisch erneut gesendet.
Profile ohne Reviewschritt schließen weiter bei `PRCreated`; bei
`review_required=true` bleibt der Lauf bis `ReviewCompleted`, `ReviewBlocked`,
`MergeOutcomeUnknown` oder `PRMerged` offen.

---

## 10. Akzeptanzkriterien-Verifier

`samuel/slices/ac_verification/handler.py` wertet die AC-Tags im
Planning-Dry-Run und im Legacy-Scoring sowie autoritativ im PR-Gate-Pfad aus.
Der CreatePR-Handler fordert den gebundenen Lauf genau einmal **nach** den
statischen Preflight-Gates und nur bei bestandenem Required-Preflight an;
Gate 11 validiert die dabei erzeugte Evidence und startet keinen zweiten
Verifier-Lauf. Der gebundene Lauf erzeugt dafür einen
temporären, detached Git-Worktree des exakten
`EvaluationSubject.head_sha`. `DIFF` verwendet die unveränderliche
Base-/Head-Comparison; die übrigen automatischen Checks sehen ausschließlich
diesen Candidate-Checkout. IMPORT- und TEST-Kindprozesse erhalten dieselbe
versionierte Core-Allowlist statt des Parent-Environments; HOME, TMP und XDG
sind kurzlebige managererzeugte Verzeichnisse. Worktree- und
Environment-Bindung sind keine Prozesssandbox. Setup- oder Verifierfehler
werden `error`, nicht PASS.

Der Plan ist zugleich Acceptance Contract Schema v2 und enthält vor den ACs
genau einen Scope nach Schema v1:

```markdown
### Änderungsscope
Scope-Schema: 1
- [FILE] `samuel/core/types.py`
- [PATH] `tests/`
Architecture-Expansion: disabled
```

`FILE` gilt exakt, `PATH` als Repository-Präfix; beide erlauben auch neue
Dateien. Relative POSIX-Pfade sind Pflicht, Traversal, Backslashes, leere oder
mehrdeutige Einträge werden nicht ausgewertet. `Architecture-Expansion:
allowed` erlaubt zusätzliche Pfade ausschließlich gemäß den Rollen und
`allowed_scopes` aus `config/architecture.json`; `blocked_scopes` gewinnen.
Der Core-Parser kann historische Verträge ohne Scope weiterhin als fehlende
Evidence darstellen. Ein neu erzeugter Planning-Entwurf darf dagegen ohne
genau einen gültigen Scope niemals `PlanPosted` erreichen. Nennt ein Issue
konkrete Repository-Pfade, autorisieren gleiche Dateinamen oder Stichwörter
keine weiteren Pfade.
Der Planning-Scope-Guard vergleicht bei einem gültigen strukturierten Vertrag
ausschließlich dessen `[FILE]`-Einträge mit der Issue-Verankerung. Pfade, die
nur in Erläuterungen, Negativsätzen oder `[TEST]`-Evidence stehen, erweitern
keine Mutationsautorität. Fehlt ein auswertbarer FILE-Scope, bleibt für
historische Entwürfe die konservative Freitext-Pfaderkennung aktiv.
Ein formal ungültiger Erstentwurf darf ausschließlich den ohnehin vorhandenen
einmaligen Planning-Retry mit der konkreten Parserdiagnose auslösen. Er erhält
weder SCM-Kommentar noch Acceptance-Authority. Der Retry-Entwurf wird auch bei
unverändertem oder geringerem numerischem Score erneut kanonisch geparst. Ist
er weiterhin ungültig oder scheitert sein Pre-Check, blockiert der Lauf ohne
zweiten LLM-Aufruf; nur der terminal verworfene Entwurf wird ausdrücklich als
nicht autoritativ sichtbar gemacht (#731). Erstentwurf und Korrekturaufruf
verwenden beide die effektive LLM-Taskroute `planning`; `planning_retry`
bleibt eine Auditphase und kann keinen unkonfigurierten Defaultmodellwechsel
auslösen (#733).
Kann der freigegebene Scope keiner Architekturrolle zugeordnet werden, bleibt
die Prüfung `not_evaluated`.
Gate 7b bindet die Scope-Evidence an denselben Repository-/Base-/Head-/Contract-
und Policy-Subject wie Gate 11.

### AC-Typen

<!-- docs-contract:ac-tags:start -->
| Tag | Prüfung | Beispiel |
|-----|----------|----------|
| `[DIFF]` | Pfad ist in `RevisionComparison.changed_files` | `[DIFF] tests/test_handler.py` |
| `[EXISTS]` | Pfad existiert im gebundenen Candidate-Checkout | `[EXISTS] config/app.json` |
| `[GREP]` | Pattern existiert repositoryweit in einer unterstützten Code-/Konfigurationsdatei des gebundenen Candidate-Checkouts | `[GREP] "def handle_idempotency"` |
| `[GREP:NOT]` | Pattern existiert repositoryweit in keiner unterstützten Code-/Konfigurationsdatei | `[GREP:NOT] 'token = "legacy"'` |
| `[IMPORT]` | Python-Modul ist im Candidate-Checkout importierbar | `[IMPORT] samuel.slices.foo` |
| `[MANUAL]` | benötigt einen gebundenen menschlichen Receipt | `[MANUAL] UI-Verhalten geprüft` |
| `[TEST]` | Runner-kompatibler sicherer Selektor läuft mit dem aufgelösten projektspezifischen Runner | Pytest: `[TEST] tests/test_x.py::test_y`; Unittest: `[TEST] tests.test_x` |

**Quellenbindung:**
- `samuel/slices/ac_verification/handler.py`
- `samuel/core/test_runner.py`
- `samuel/core/acceptance.py::parse_grep_criterion_argument`
- `samuel/core/acceptance.py::parse_test_criterion_argument`
- `samuel/slices/planning/handler.py::_VALID_AC_TAGS`
- Vertrag: `docs/capabilities/document-contract.json::technical-ac-tags`
<!-- docs-contract:ac-tags:end -->

`GREP` besitzt bewusst kein Pfadargument. Nach einem gequoteten Pattern sind
nur das Zeilenende oder ein expliziter Beschreibungstrenner (`—`, `–`, `:`
oder `--`, jeweils von Leerzeichen umgeben) zulässig. Ein scheinbarer
Pfadsuffix wie `[GREP] "marker" src/modul.py` macht einen neuen Acceptance-
Contract vor `PlanPosted` ungültig, statt still repositoryweit zu suchen.
Der äußere Pattern-Delimiter darf doppelt oder einfach sein. Enthält das
Pattern doppelte Anführungszeichen, wird es außen einfach gequotet (und
umgekehrt); Backslash-Escapes für den äußeren Delimiter gehören nicht zur
Grammatik. Enthält das Pattern beide Anführungszeichenarten, wird ein
fokussierter `[TEST]` verwendet. Dateigebundenes Verhalten wird ebenfalls mit
einem fokussierten `[TEST]` belegt.

Der ungebundene Post-Implementation-Lauf ist nur noch direkt aufrufbarer
Kompatibilitätscode. Seine
Zähler `automatic_total`, `automatic_passed`, `automatic_failed` und
`manual_pending` sowie die älteren Felder `total`/`passed` und
`ac_total`/`ac_verified` besitzen im Zielmodus keine Freigabeautorität.

Im `self`-Workflow geht `CodeGenerated` wie in den anderen Zielworkflows
direkt in den vollständigen PR-Gate-Lauf; `gates.self.json` ist das eigene
Profil. Es gibt weder eine vorgelagerte Score-Schwelle noch eine
`self_parity_ok`-Bedingung. Ein `[TEST]`, der wegen eines fehlenden Runners
nicht ausgeführt werden kann, bleibt im gebundenen Gate 11 ein automatischer
Fehler und wird nicht mit `[MANUAL]` gleichgesetzt. Ein MANUAL-Kriterium wird nur durch einen
menschlichen SCM-Kommentar in dieser exakten Form erfüllt:

```text
/samuel accept AC-<16-hex> --contract sha256:<64-hex> --head <vollständige-commit-id>
```

Kriteriums-ID, Contract-Hash und Head-SHA stehen in der Acceptance-Evidence.
Am tatsächlichen MANUAL-Haltepunkt veröffentlicht S.A.M.U.E.L. diese Bindung
mit dem bereits fertigen Befehl je noch offenem Kriterium im Issue. Die
vorgelagerte Planfreigabe über `status:approved` oder den eingerichteten
Approval-Kommentartransport akzeptiert keine MANUAL-Kriterien. Bei einem neuen
Plan oder Candidate darf ein alter Befehl nicht als dessen Freigabe verwendet werden.
Der Kommentar muss nach dem Plan von einem anderen SCM-Akteur als dem
Plan-Autor stammen. Checkboxzustand und LLM-Ausgabe werden ignoriert.

Zulässige Ergebniszustände sind `passed`, `failed`, `manual_pending`,
`not_applicable`, `missing_evidence` und `error`. Für ein erforderliches
Kriterium ist ausschließlich `passed` erfolgreich; unbekannte oder fehlende
Zustände blockieren.

Automatische Resultate mit `passed` oder `failed` tragen ein versioniertes,
Verifier-spezifisches `evidence`-Objekt. Der umgebende
`AcceptanceEvidence`-Vertrag bindet es an Candidate-Head, Contract und stabile
Kriteriums-ID:

| Tag | Evidence-Kern |
|---|---|
| `DIFF` | Pfad und `changed` |
| `EXISTS` | Pfad und `exists` |
| `IMPORT` | Modul, `importable`, Exit-Code und Candidate-Prozessumgebungsprofil |
| `GREP` / `GREP:NOT` | repositoryweites Pattern, Fund-/Abwesenheitsstatus und optionaler tatsächlicher Fundpfad |
| `TEST` | Testname, Runner, Control-Plane-Policy-Ursprung/-Version, Candidate-Prozessumgebungsprofil, Exit-Code, Laufzeit und auf 500 Zeichen begrenzter, gegen bekannte Secret-Muster redigierter Output-Auszug |

Infrastruktur-, Eingabe- und Nichtprüfbarkeitsfehler erhalten dagegen
`error` beziehungsweise `missing_evidence` und werden nicht als heilbarer
Test-/Codefehler ausgegeben. Bound Healing akzeptiert nicht irgendein
Dictionary, sondern nur Schema 1 mit zum AC-Tag passendem Evidence-Kern.

### Test-Runner-Auto-Detection

Planning löst für jedes `[TEST]` bereits vor `PlanPosted` dieselbe einzelne
Runner-Authority wie Gate 11 auf. Es prüft nur Installation und bekannte
Selektorgrammar; der Test selbst bleibt bis zur gebundenen
Candidate-Verifikation deferred. Der Planprompt erhält aus dieser Auflösung
nur Runnerart und zulässige Selektorform, niemals den Control-Plane-Befehl;
dadurch gelten dieselben Beispiele auch im einzigen Retry. Ein fehlender
Runner, eine fehlende Toolchain oder eine Pytest-Node-ID bei aufgelöstem
Unittest-Runner blockiert nach dem einen vorhandenen Planning-Retry.
Selektoren werden nicht umgeschrieben, Werkzeuge nicht installiert und ein
anderer Runner oder die gesamte Suite nicht als Fallback gestartet. `samuel
doctor` verwendet für die betriebliche Vorabdiagnose denselben Core-Resolver.

| Marker-Datei | Runner |
|--------------|--------|
| `pyproject.toml` / `pytest.ini` / `setup.cfg` | Node-ID: `python -m pytest -q {node_id}`; einfacher Name: `python -m pytest -q -k {test}` |
| `package.json` | `npx jest -t {test}` |
| `go.mod` | `go test -run {test} ./...` |
| `Cargo.toml` | `cargo test {test}` |
| `pom.xml` | `mvn test -Dtest={test}` |

`test_cmd` (mit `{test}`-Platzhalter), `test_timeout` und
`test_policy_version` stammen aus dem beim Bootstrap normalisierten
Control-Plane-`config/eval.json`. Dieser Snapshot wird Evaluation, PR-Gates
und AC-Verifier injiziert; sein Runner-Teil liegt im Policy-Digest des
`EvaluationSubject`. Ein Candidate-`config/eval.json` wird nicht gelesen.
Projektmarker wählen nur die obigen festen Templates. Änderungen der
Control-Plane-Policy werden erst nach einem Runtime-Neustart wirksam.

Die explizite Policy hat Vorrang vor allen Markern. Für
`python -m unittest {test}` sind gepunktete Modul-, Klassen- oder
Methodennamen erforderlich; eine Pytest-Node-ID mit `/` und `::` ist damit
deterministisch inkompatibel. Bei Pytest sind sichere logische Namen und
Node-IDs zulässig. Bei anderen beziehungsweise eigenen Runnern bleibt der
Selektor ein sicherer runner-spezifischer logischer Name.
Ein Pytest-Node-ID ist nur ausführbar, wenn `{test}` im effektiven Kommando als
direktes Positionsargument gebunden wird; ein `-k {test}`-Template bleibt auf
logische Keyword-Ausdrücke begrenzt.

IMPORT und TEST starten mit Environment-Profil `verifier-sterile.v1`. Die
exakte Allowlist wird aus `samuel/core/process_environment.py` in
`docs/RUNTIME_REFERENCE.md` generiert. Relative Runner werden nur im Pfad des
aktiven Python-Interpreters und in festen Systempfaden gesucht; ein außerhalb
davon installiertes Tool muss in der Control-Plane-Policy als absoluter Pfad
stehen; Toolchains, die ihre Laufzeit nur aus einem Benutzerprofil oder dem
realen HOME beziehen, sind nicht Teil dieses Profils. Parent-`PATH`, `HOME`,
`PYTHONPATH`, Git-/Askpass-/SSH-/Signing-/Cloud-
und LLM-Werte sowie Shellprofilvariablen werden nicht übernommen. Fehler beim
Aufbau blockieren ohne Environment-Inhalt. Gleichwohl kann Candidate-Code mit
demselben OS-Benutzer weiterhin anderweitig lesbare Hostdateien oder
plattformabhängige Prozessdaten lesen und das Netzwerk nutzen. #679 verlagert
diese Ausführung perspektivisch in einen externen Execution-/CI-Provider;
dessen wirksame Isolation wird als Providerprofil nachgewiesen und nicht vom
Core selbst als Sandbox behauptet.

---

## 11. Self-Mode

`samuel --self <cmd>` aktiviert den Self-Mode. Unterschiede zur Production:

- `.env.agent` wird ueberlagernd geladen (override = True), `.env` als Default.
- `SAMUEL_SELF_MODE=1` und `SAMUEL_ENV_FILE` werden gesetzt.
- `agent.mode` und `agent.self_mode` werden im Config-Override-Layer auf `self`
  bzw. `True` gepinnt.
- `--self run` darf nur auf `main` laufen — `_check_self_run_branch()` failt
  sonst (Regression-Schutz fuer #227). Override per `--allow-non-main`.
- Default-Workflow ist `self.json` (`max_parallel=1`, mit AC-Pflicht und
  Plan-Pre-Check).

Self-Mode wird verwendet, damit der Agent eigene Backlog-Issues abarbeiten
kann, ohne dass dabei versehentlich der falsche Workflow oder das falsche Repo
trifft.

---

## 12. Routing, Schedules und Budgets

Es gibt genau einen produktiven Routingpfad unter `samuel/adapters/llm/`:
statische Task-Routen und validierte Schedule-Blöcke werden von `factory.py`
in `TaskRoutingLLMAdapter` und `ScheduledTaskRoutingAdapter` umgesetzt. Die
frühere parallele Implementierung unter `samuel/premium/` sowie der
Entitlement- und Bootstrap-Aktivierungspfad sind entfernt (#477).

`TokenBudgetLLMAdapter` begrenzt die sichtbare Ausgabe eines einzelnen
LLM-Aufrufs. Der Multi-Round-Loop behandelt Truncation und besitzt ein
Versuchslimit. Davon getrennt erzeugt Planning vor seinem ersten LLM-Aufruf
eine persistente `workflow-budget.v1`-Zulassung aus Repository, Issue,
Invocation, Source-Snapshot und Workflow-/Budgetpolicy. Der exakte
Acceptance-Contract bindet später Watch- und Webhook-Approval an dieselbe
Zulassung. `WorkflowTokenBudgetLLMAdapter` reserviert vor jedem physischen
Retry-/Fallback-Attempt atomar einen konservativen Eingabe-Bound plus den vom
Call-Adapter erzwungenen `max_tokens`-Bound. Verlässlich gemeldete Usage wird
abgerechnet; Timeout, verlorene Antwort oder unbekannte Usage halten die volle
Reservation. Resume-Checkpoints tragen den Zulassungsschlüssel weiter.
`workflow_budget.token_limit` ist ein positiver, bindender Tokenwert. Preise
bleiben Meteringdaten und bilden keinen Rechnungs- oder Geldkosten-Hardcap.
Reale Provider-Qualification für Timeout, Retry und Fallback bleibt als
Abschluss-Evidence von #549 offen. Der frühere unverdrahtete
`TokenLimitHandler` bleibt entfernt.

Schreibende Dashboard-Funktionen für Routing und Prompts bleiben über den
globalen `SAMUEL_API_KEY` authentisiert. Die Handler validieren Provider,
Felder, Schedule-Zeiten, Pfade, Scopes und Inhalte zusätzlich serverseitig.
Eine echte Rollenautorisierung ist weiterhin separater Scope von #422.

---

## 13. Security-Model

### Prozessherkunft / Import-Shadowing

Der einzige unterstützte Betriebsaufruf ist das durch
`pyproject.toml [project.scripts]` installierte Console-Script `samuel`. Ein
Zielrepository darf Working Directory und `PROJECT_ROOT` stellen, erhält
dadurch aber keine Importauthority über den Produktprozess. `python -m samuel`
ist aus einem fremden Repository unsicher, weil Python ein dort liegendes
Top-Level-Paket `samuel` vor dem beabsichtigten Paket auswählen kann, noch
bevor eigener Schutzcode läuft. Der Modulpfad ist deshalb nur ein nicht
garantierter Komfortpfad in einem bewusst vertrauenswürdigen Source-Checkout.

systemd-Generator, Runtime-Image und Healthcheck verwenden direkt das
installierte Script. Der Generator blockiert, wenn er keinen ausführbaren
Console-Entry-Point auflösen kann. Manipuliertes `PYTHONPATH`, eine
kompromittierte Installation oder ein ersetztes Script bleiben vorgelagerte
Supply-Chain-/Betreibergrenzen. Dauerhafte Entscheidung: ADR-0583.

### Prompt-Injection-Detection (`samuel/slices/security`)

Neun begrenzte Phrasen-/Rollenmuster werden nach NFKC, Casefold, Entfernung
unsichtbarer Formatzeichen und einer kleinen ASCII-Confusable-Abbildung für
jeden Prompt von Planning, Implementation, Healing und Review ausgewertet. Ein Treffer erzeugt
`PromptInjectionRiskDetected` mit Indicator-IDs, OWASP-/AI-Act-Zuordnung und
`disposition=advisory`; der rohe LLM-Input wird nicht in dieses Event kopiert.
Die Heuristik blockiert nicht allein und beansprucht weder vollständige UTS-39-
noch Paraphrasen-Abdeckung.

### Secret-Scan

Der ausgelieferte Basisscanner verwendet dieselbe versionierte Regelquelle wie
die Audit-Redaktion. Zugewiesene Secret-Werte, lange Bearer-Werte,
GitHub-/`sk-`-Präfixe und PEM-Private-Key-Marker sind blockierend; JWT-Formen
und `AKIA…`-Access-Key-IDs sind advisory.
`DiffSecretGate` prüft ausschließlich hinzugefügte Zeilen des vollständigen
`EvaluationSubject`-Diffs. Blockierende Funde und Scannerfehler stoppen vor
`GatesPassed`/PR-Erstellung; advisory Treffer erzeugen wertfreie
`SecretRiskDetected`-Evidence und dürfen passieren. Entfernte Secret-Zeilen
dürfen bereinigt werden. Eine generische Entropie-Heuristik ist bewusst nicht
eingebaut; breite Erkennung bleibt Aufgabe spezialisierter Scanner. Der
#520-Pfad liest SCM-Check-Facts und ist kein Scanner-/SARIF-Ingest.

### Command-Safety

`samuel.core.git._run()` bewertet den tokenisierten Argumentvektor direkt vor
`subprocess.run`. `git push --force`, `git push -f` und `git reset --hard`
werden blockiert, ohne einen Prozess zu starten. Die Textdiagnose des
Security-Slice nutzt dieselbe Git-Policy und meldet `DELETE FROM` nur ohne
`WHERE`; andere Subprozesspfade sind nicht umfasst.

### HMAC-Signierung

- **Webhook-Payloads** (Gitea + GitHub) werden nur bei gesetztem
  `SLICE_HMAC_KEY` validiert; ohne Schlüssel ist die Prüfung deaktiviert.
  Die vorhandene Ingress-Observation meldet dann `not_checked`, nicht `pass`.
  Bei konfiguriertem Schlüssel bleibt das Ergebnis `pass` oder `denied`;
  Schlüsselpräsenz im Doctor ist kein Nachweis einer nativen SCM-Delivery.
- **Context-Ausgaben** können signiert werden, aber ein konsumierender
  Signaturprüfer ist derzeit nicht verdrahtet.

### Prompt Guard

Vier Slice-Prompts verwenden gemeinsame Header-Marker aus dem Core. Die frühere
`PromptGuardMiddleware` für den nicht ausgelieferten Command `LLMCall` wurde
entfernt; sie erzeugte keine Schutzwirkung. Marker bleiben eine weiche
Prompt-Layer-Maßnahme. Ein Post-Call-Echo-Check der generischen Marker wurde
verworfen, weil weder Echo noch Echo-Abwesenheit eine Injection belastbar
belegen; echte Canaries sind davon getrennt zu behandeln.

---

## 14. Audit-Trail

Asynchrones JSONL-Logging via `AsyncAuditSink` (Worker-Thread + Queue +
Fallback-Sink). Die HMAC-Chain ist nur bei gesetztem
`SAMUEL_AUDIT_HMAC_KEY` tamper-evident. Der signierte `JSONLAuditSink` nutzt
auf dem lokalen POSIX-Dateisystem `flock` direkt auf der aktuellen
Rotationsdatei, liest und verifiziert unter dem exklusiven Lock den letzten
Record und berechnet erst danach den nächsten HMAC. Damit besitzen Dashboard,
Docker-Healthcheck und Einmal-CLI keinen prozesslokalen Neben-Kettenkopf.
Fehlende Lock-Unterstützung, ein ungültiger beziehungsweise manipulierter Tail
oder ein Schreibfehler verweigern den signierten Append. Eine vorhandene
beschädigte Datei wird weder repariert noch still neu begonnen. Ein keyloser
Writer darf weiterhin eine neue unsigned Rotationsdatei anlegen, verweigert
aber unter demselben dateibezogenen Lock jeden Append an eine bereits signierte
Chain vor der Mutation. Der
`agent.jsonl.fallback` ist ein separates, explizit zu verifizierendes
Transkript und ersetzt keine fehlenden Records des Hauptlogs. Sinks
werden aus `config/audit.json` gebaut; bei mehreren fant `FanOutAuditSink`
parallel. Zusaetzlich (#368) der `SARIFAuditSink`: exportiert **nur Findings**
(Events mit `owasp_risk`) ins SARIF-2.1.0-Format (`data/logs/findings.sarif`,
Beispiel `docs/examples/findings.sarif`) — das JSONL bleibt das Volltranskript.
Findings-Volumen pro Typ/Issue: `get_finding_stats` (FP-Raten-Grundlage).

### Externe SCM-Check-Evidence (advisory)

`ISCMCheckEvidenceReader` trennt den Providerabruf von der fachlichen
Bewertung. Der erste Adapter liest einen expliziten Gitea-Run samt Attempt,
PR-Base/-Head, terminalem Run-/Jobstatus, Workflow-Pfad und Blob-SHA sowie den
Commit-Status für den konfigurierten Sollkontext. Joblogs, Workflowinhalt und
beliebige unbekannte Payloadwerte werden nicht gespeichert; HTTP-Antworten und
Subject-Dateien besitzen feste Größenlimits.

`SCMCheckObservation` enthält ausschließlich projizierte Providerfacts.
`EvidenceAssessment` vergleicht sie mit dem vollständigen
`EvaluationSubject` und operatorseitigen Erwartungen. Fehlende Run-/Runner-,
Toolchain-, Signatur-, Transport- oder Verification-Request-Bindung sowie
Stale und widersprüchliche Evidence bleiben getrennte Findings. Der
versionierte Assessment-Payload und sein in-toto-Statement-v1-Rahmen werden
über den vorhandenen `IObservationStore` mit
`evidence_origin=external_scm_advisory` dedupliziert. Historische Payloads
bleiben unverändert.

Dieser Pfad ist nicht an `IExternalGate` angeschlossen. `role=advisory`,
`authority=none` und alle drei Wirkungsfelder `required_effect`,
`dispatch_effect`, `mutation_effect` sind fest `false`. Die erste Stufe
beauftragt keine Verifikation und bewertet keinen Runner oder Producer als
Trust Root. Requestbindung, trusted execution und jede Required-Wirkung sind
Restscope #679; SARIF bleibt weiterhin ein separater write-only Export.

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

- Filtern nach einer gebundenen Workflow-`correlation_id` → kompletter
  Run-Trace; `workflow_correlation_bound=false` kennzeichnet Standalone-
  LLM-Telemetrie ohne diese Aussage (#675).
- Filtern nach `owasp_risk` → Compliance-Reports.
- Filtern nach `issue_number` → Multi-Run-History (Issue mehrfach abgearbeitet).

Klassifikation in `samuel/core/owasp.py` (LLM-01..10) und `samuel/core/ai_act.py`
(EU-AI-Act-Artikel-Mapping). Compliance-JSON-Dateien sind als Package-Data
mitgeliefert (`samuel/core/compliance/*.json`).

---

## 15. Persistenz

`config/agent.json` → `agent.data_dir` (Default: `data/`). Wichtige dort
persistierte Laufzeitartefakte sind:

<!-- docs-contract:persistence-artifacts:start -->
| Verzeichnis/Datei | Inhalt | Herkunft |
|---|---|---|
| `<data_dir>/idempotency.json` | Idempotency-Store | `samuel/core/bootstrap.py`; codegebundener Dateiname |
| `<data_dir>/dlq.jsonl` | Dead-Letter-Queue für fehlgeschlagene Subscriber | `samuel/core/bootstrap.py`; codegebundener Dateiname |
| `<data_dir>/samuel-state.sqlite3` | versionierte Beobachtungen, Ableitungen, Quality-/Run-Projektionen und Autoritätszustand | `samuel/adapters/state/sqlite.py`; Schema v10; Claims/Checkpoints/Intents/Leases/Restore/Reconcile/Epoch, Retention-Katalog, Kategorie-Autorität und Ausführungsbelege aktiv |
| `<data_dir>/samuel-state-authority.json` | synchrone UUID-/Epoch-Hochwassermarke außerhalb des DB-Backup-Artefakts | `samuel/adapters/state/sqlite.py`; 0600, atomar ersetzt; Abweichung führt in Reconcile |
| `<data_dir>/.samuel-state-authority.lock` | lokaler Mehrprozess-Lock für monotone Witness-Synchronisierung | `samuel/adapters/state/sqlite.py`; 0600; Laufzeit-Lock, kein Backup- oder Autoritätsartefakt |
| `data/backups` | SQLite-konsistente, registrierte Runtime-State-Backups | `config/privacy.json`; einzige technisch verwaltete Backup-Retentiongrenze; externe Kopien bleiben Betreiberverantwortung |
| `data/logs/agent.jsonl` | Audit-Trail; ausgelieferte Rotation `daily`; bei gesetztem HMAC-Key ein per POSIX-`flock` serialisierter Dateikopf für alle lokalen Prozesse | `config/audit.json`; ausgeliefert konfiguriert; signierte Appends verweigern beschädigte Tails |
| `data/logs/agent.jsonl.fallback` | synchroner Audit-Fallback bei Queue-Überlauf oder Schreibfehler; eigenständige Kette, kein Vollständigkeitsnachweis für das Haupttranskript | `samuel/core/bootstrap.py`; aus konfiguriertem JSONL-Pfad abgeleitet und separat zu verifizieren |
| `data/logs/findings.sarif` | SARIF-Findings-Export | `config/audit.json`; ausgeliefert konfiguriert |
| `<data_dir>/score_history.json.migrated-<sha256>` | checksumarchivierte ungebundene Legacy-Eval-History | `samuel/adapters/state/legacy.py`; einseitiger Import; kein aktiver Runtime-Writer |
| `<data_dir>/eval_baselines.json.migrated-<sha256>` | checksumarchivierte High-Water-Legacywerte ohne Runtime-Autorität | `samuel/adapters/state/legacy.py`; einseitiger Import als Legacy-Projektion |
| `<data_dir>/evaluation_observations.json.migrated-<sha256>` | checksumarchivierte gebundene Legacy-Beobachtungen und Ableitungen | `samuel/adapters/state/legacy.py`; einseitiger Import; aktive Daten liegen in SQLite |
| `<data_dir>/bound_healing_attempts.json.migrated-<sha256>` | checksumarchivierter früherer At-most-once-Nachweis | `samuel/adapters/state/legacy.py`; Claims liegen nach einseitigem Import in SQLite |
| `<data_dir>/quality_metrics.json.migrated-<sha256>` | checksumarchivierte Legacy-EWMA je Provider, Modell und Task | `samuel/adapters/state/legacy.py`; einseitiger Import; aktive Serienprojektion liegt in SQLite |
| `<data_dir>/scm_activity_poll.json` | Cursor für optionales SCM-Activity-Polling | `samuel/slices/watch/handler.py`; codegebundener Dateiname, featureabhängig |
| `<work_dir>/workspaces.sqlite3` | lokale Registry für Run-/Verifikations-Worktrees und Quarantäne | `samuel/adapters/workspace/git.py`; getrennt von data_dir und vom State-Backup ausgeschlossen |
| `<work_dir>/trees/` | mutierbare Run- und detached Verifikations-Worktrees | `samuel/adapters/workspace/git.py`; unvertrauenswürdiger Candidatezustand; kein Backup-Artefakt |
| `<work_dir>/locks/` | prozessunabhängige Branch-/Workspace-flock-Dateien | `samuel/adapters/workspace/git.py`; lokale Ownership-Evidence; kein Sandbox-Ersatz |

**Quellenbindung:**
- `config/agent.json#/data_dir`
- `config/agent.json#/workspace`
- `config/audit.json`
- `config/privacy.json`
- `samuel/core/bootstrap.py::bootstrap`
- `samuel/slices/resume/handler.py`
- `samuel/adapters/state/sqlite.py`
- `samuel/adapters/state/legacy.py`
- `samuel/adapters/workspace/git.py`
- `samuel/slices/evaluation/handler.py::EvaluationHandler.observe`
- `samuel/slices/run_projection/handler.py`
- `samuel/slices/healing/bound.py`
- `samuel/slices/quality_metrics/handler.py`
- `samuel/slices/dashboard/data.py`
- `samuel/slices/watch/handler.py::WatchHandler._poll_scm_activity`
- Vertrag: `docs/capabilities/document-contract.json::technical-persistence-artifacts`
<!-- docs-contract:persistence-artifacts:end -->

Session- und Implementation-Checkpoints für LLM-Runden werden ab Schema v3
diagnostisch in SQLite gespiegelt und bleiben mit `resume_eligible=false` ohne
Fortsetzungsautorität. Zusätzlich persistieren Implementation und PR-Gates
die gebundenen Finalisierungsgrenzen `commit_pending`, `push_pending`,
`gates_pending` und `pr_pending` mit `resume_eligible=true`. Das Eventlog des Sequence-Validators liegt weiterhin
nur im Prozessspeicher. Der
Sequence-Validator lädt bekannte Muster aus `config/repo_patterns.json`.
Workflow-Runs und gebundene Qualitätsserien liegen dagegen in SQLite und
überleben Auditrotation; Audit-JSONL bleibt Compliance-Evidence und Quelle des
einmaligen initialen Backfills, nicht die dauerhafte Runtime-Datenbank. Für die
weiterhin prozesslokalen Zustände wird keine Neustartpersistenz behauptet.

### Versionierter State-Store (Stufen 3/4/5a/5b/5c-Fundament, #629/#633/#666/#667/#673)

Der Bootstrap initialisiert `<data_dir>/samuel-state.sqlite3` als lokales
Schema v10. Die fachlichen Portansichten besitzen bewusst verschiedene
Fehlerverträge: Beobachtungen sind sichtbar fehlschlagende Telemetrie,
Run-Projektionen sind nachholbar und nicht freigabeblockierend,
Autoritätswrites müssen vor einem späteren unsicheren Schritt fail-closed
behandelt werden. Evaluation schreibt immutable Rohbeobachtungen, getrennte
Formelableitungen und nicht scorebare Terminalzustände über den Observation-
Port. Quality-EWMA und Dashboard-Run-History sind gespeicherte, nach Herkunft,
Observation-Schema, Policy und Formel getrennte Projektionen. Der
`run_projection`-Subscriber entfernt bekannte Secretfelder rekursiv; seine
Fehler blockieren keinen Gate-/PR-Pfad, bleiben aber in DLQ, Auditdiagnose und
`state.status.projections` sichtbar. Bei parallelen HTTP-Requests wird sein
kurzer Read/Modify/Write-Schritt innerhalb des Runtime-Prozesses serialisiert,
damit verschiedene Events desselben Runs nicht gegenseitig überschrieben
werden. Planning, Implementation, gebundenes
Healing und Review binden ihre LLM-Aufrufe über `issue_scope(issue,
correlation_id)` an den bereits laufenden Workflow. Ein budgetgeschützter
CreatePR-/Review-Wiedereintritt nach einer MANUAL-Pause liest ausschließlich
die bereits an Repository, Issue, aktiven Planvertrag und Plan-Kommentar
gebundene Admission aus demselben Authority-State; er erzeugt keinen zweiten
Budgettopf und übernimmt weder eine fremde noch eine fehlende Admission. Der Metering-Adapter setzt
dieselbe Korrelation auf `LLMCallCompleted` und weist die Bindung mit
`workflow_correlation_bound=true` aus. Standalone-Aufrufe erhalten weiterhin
eine unabhängige Event-ID und `false`; sie werden nicht über Zeitnähe oder die
Issue-Nummer zu einem Workflow-Run hochgestuft (#675).

`samuel/core/workflow_outcome.py` ist die gemeinsame Statusreduktion für
Run-Projektion, Dashboard und Audit-Replay. Sie leitet den Ausgang jedes Runs
aus der vollständig sortierten Ereignisfolge ab: Subject-Invalidierung
widerruft Erfolg. `PRCreated` beendet nur Profile ohne nachgelagerten Review;
`ReviewCompleted` ergibt `reviewed` und `PRMerged` ergibt `merged`.
`ReviewBlocked` und `MergeOutcomeUnknown` blockieren terminal. Diese Ausgänge
überholen frühere heilbare Fehlerevidence; daneben sind nur `PlanBlocked`,
`PlanReplanRejected`, korreliertes
`LLMUnavailable`, `WorkflowBlocked`, `WorkflowAborted` sowie
`PRCreationFailed`, `CandidateEvaluationFailed` und
`CandidateSubmissionRejected` sind weitere terminale Fehler. Ein
`CandidateEvaluationCompleted` ist ein terminaler passiver Erfolg. Ein
`GateEvaluationCompleted` mit ausschließlich offenem `manual_pending` bleibt
ein nichtterminaler Wartezustand; der gebundene Checkpoint übersteht Restart
und der öffentliche Watch-Pfad setzt nach gültigem SCM-Receipt dasselbe
Subject fort;
der native `IssueCommented`-Eingang weckt denselben vorhandenen
Reevaluation-Pfad gezielt für das kommentierte Issue. Der Event allein ist
keine Acceptance: Der Consumer liest den SCM-Receipt erneut und verlangt
weiterhin AC-/Contract-/Head-/Humanbindung. Andere Issues werden dabei nicht
gescannt. Der öffentliche Watch-Pfad bleibt als Polling-/Recoverypfad erhalten.
`CandidateVerificationPending` und `ProviderVerificationPending` bleiben
nichtterminal; `ProviderVerificationBlocked` ist ein terminaler, fail-closed
Provider-/Trustausgang. `PlanRevoked` bleibt als
Teil eines expliziten Ersatzlaufs nichtterminal. `GateFailed`, `EvalFailed`,
`TokenLimitHit` und `HealingAborted` bleiben nicht terminale Stage-Evidence. Ausschließlich
ungebundene LLM-Telemetrie wird als `unbound` persistiert und aus Runzahl und
Trend ausgeschlossen. Bootstrap und `samuel state reproject-runs --json`
reklassifizieren vorhandene Projektionen idempotent, ohne Audit-Payloads
auszugeben (#672).

Ein natives `PullRequestMerged` wird nur nach SCM-Readback von `merged` und
exaktem Candidate-Head an den vorhandenen Create-PR-Intent samt EvaluationSubject
gebunden als `PRMerged` projiziert. Das beobachtet den menschlichen Merge;
es löst keinen Merge aus und schließt kein Issue automatisch. Der ursprüngliche
Subject behält seine Base, obwohl der SCM-Basisbranch nach Merge vorgerückt ist.
Für den noch aktuellen Plan entfernt diese Beobachtung die WIP-/Reviewlabels
und projiziert `status:done`; ein neuer aktiver Contract wird dadurch nicht
abgeschlossen. Ein idempotenter Issue-Kommentar nennt PR, Candidate und
Contract sowie den passenden Planumfang. Issue-Schließung bleibt getrennt.
Eine gebundene LLM-Budgetreservation ohne Workflowabschluss erscheint als
`running` statt `unknown`; fehlende oder ungebundene Fakten bleiben unbekannt.
Eine beim Merge nicht beobachtete separate Quality-Stage erscheint als
`not_attempted`, ohne Gates oder CI zu einem Quality-PASS umzudeuten.
Trendwerte vergleichen abgeschlossene Run-Ausgänge; `reviewed` ist ein
erfolgreicher Reviewausgang, kein vollständiger E2E-/Golden-Claim. Unvollständige
und MANUAL-wartende Runs ergeben keinen Fehlertrend. Acceptance-Historie bleibt
sichtbar; frühere Ergebnisse werden anhand Criterion, Subject und Korrelation
als historisch von der aktuellen Gate-Evaluation getrennt.

Vor einem optionalen nativen Merge persistiert der Reviewpfad einen
`merge_pr`-Intent mit PR, EvaluationSubject, erwartetem Head und
Review-Digest. Nur ein `pending`-Intent erhält einen terminalen historischen
Status; spätere Zustandsabgleiche lesen die reale PR-Postcondition und können
einen inzwischen sichtbaren Merge bestätigen, ohne den Effekt erneut
auszulösen oder den früheren unbekannten Ausgang umzuschreiben (#468).

Beim ersten Bootstrap importiert `LegacyStateMigrator`
`evaluation_observations.json`, `quality_metrics.json`, `score_history.json`
und `eval_baselines.json` idempotent und checksumgebunden. Ungebundene Werte
bleiben als Legacy-Serie gekennzeichnet. Erst nach erfolgreichem DB-Marker wird
die Quelle atomar nach `<name>.migrated-<sha256>` verschoben und `0400`
gesetzt; eine wieder auftauchende, abweichende aktive Quelle wird nicht still
übernommen. Stufe 3 migriert `bound_healing_attempts.json` zusammen mit dem
Importmarker transaktional und archiviert die Quelle checksumbenannt. Claims
folgen `claimed -> attempted | abandoned`; nur das Operator-Kommando
`samuel state abandon-healing --observation-key ... --reason ...` setzt
`abandoned`.

Implementation-Runden speichern diagnostische, ausdrücklich nicht
resumefähige Checkpoints. Commit, Push und PR-Erstellung schreiben vor der
Wirkung einen Intent und danach den unmittelbar beobachtbaren Zustand. Stufe 4
setzt ausschließlich ihre sicheren Finalisierungsgrenzen fort: OS-Lock des
vorhandenen Run-Worktrees, abgelaufenes Lease per CAS, vollständige
Repository-/Run-/Workspace-/PlanningSource-/Contract-/Policy-/Schema- und
Signing-Bindung,
lokales Git-Prädikat und SCM-Postcondition. Commit-Recovery bindet Parent und
Tree; Push-Recovery die exakte Remote-Revision; PR-Recovery verwendet zuerst
die persistierte Nummer und nur im API-/Notierungsfenster einen
Head-/Base-/Revision-gebundenen Marker. Drift wird quarantänisiert, nie
zurückgesetzt oder force-gepusht.

Der optionale Execution-Provider verwendet dieselben State-Primitiven ohne
neue Tabelle: `verification_request.v1` ist ein typisierter AuthorityRecord,
`provider_dispatch.v1` ein vor der Wirkung persistierter Intent und
`provider_verification` ein eigener resumefähiger Checkpoint. `applied`
bedeutet ausschließlich bestätigten Dispatch, nicht fertige Evidence oder
bestandene Gates. Unbekannte Dispatchausgänge bleiben mit demselben Request
reconcilebar; ein leerer Suchtreffer startet keinen zweiten Run. Resume führt
Provider-Checkpoints nicht über `Implement`, sondern liest denselben
Run/Attempt weiter und setzt beim Referenz-Worker erst mit gebundener Evidence
an `CreatePR` fort. Reconcile klassifiziert diese Records ausdrücklich;
Retention schützt offene Intents und resumefähige Checkpoints weiter, ohne
eine neue Löschkategorie zu aktivieren.

Der Bootstrap startet die Prüfung erst nach vollständigem Wiring. Watch prüft
vor jedem Zyklus erneut, damit ein zunächst lebendes Lease nach Ablauf
übernommen werden kann. `ResumeAttempted`, `ResumeCompleted` und
`ResumeBlocked` liefern at-least-once Laufzeit-Evidence; terminale
Workflowereignisse schreiben zuerst einen Tombstone und bereinigen danach
Checkpoint, Lease und Workspace. Ein Abbruch zwischen beiden Schritten wird
beim nächsten Start idempotent fertiggestellt. Reconcile blockiert Resume.

Jeder autoritative Übergang erhöht die DB-Epoch transaktional und aktualisiert
danach synchron `<data_dir>/samuel-state-authority.json`, bevor eine davon
abhängige Wirkung beginnt. Ein lokaler OS-Lock serialisiert konkurrierende
Witness-Schreiber; unter dem Lock wird stets die neueste DB-Epoch publiziert,
sodass ein später beendeter älterer Write die Hochwassermarke nicht
zurücksetzen kann. Fehlender/fremder Witness, Epoch-Rückstand oder
eine höhere optionale Audit-Hochwassermarke machen Reconcile in State-
Diagnose, einem eigenen fehlgeschlagenen Authority-Health-Check (damit auch
im Dashboard) und `AuthorityReconcileRequired` sichtbar und blockieren
Healing und Resume. Audit bleibt Zusatznachweis und keine Korrektheitsquelle.

Stufe 5a ergänzt einen vom Witness-Mutex getrennten Lifecycle-`flock`. Jeder
DB-Leser und -Schreiber hält ihn shared; `samuel state restore` hält ihn über
Staging-Prüfung, Sentinel, atomaren Datenbankwechsel, Witness-Synchronisierung
und Sentinel-Cleanup exklusiv. Der geprüfte Backupstand erhält eine neue
`instance_uuid`; seine Epoch startet oberhalb von Live-DB, Witness, Backup,
persistierter Restore-Hochwassermarke und konservativ gelesener Audit-Epoch.
Der Restore bleibt danach absichtlich in `reconcile_required`.

`samuel state reconcile-scan` inventarisiert Claims, Intents, Checkpoints,
Leases, Authority-Records, Workspaces und bekannte SCM-Wirkungen über die
bestehenden Ports. PRs werden zuerst über die notierte Nummer, im engen
API-/Notierungsfenster über den backendneutralen Intent-Marker geprüft.
`scan_failed` kann nur ein erfolgreicher vollständiger Rescan verlassen;
Operator-Klassifikationen verwenden `verified_effect`, `verified_absent`,
`abandoned` oder `unresolved`. Erst ein erfolgreicher Scan ohne `unresolved`
erlaubt `reconcile-complete`. Eine offene oder unterbrochene Operation kann
nur mit expliziter alter Operations-ID und Begründung superseded werden; die
neue Operation übernimmt keine alten Klassifikationen. Healing und Resume
bleiben bis zum Abschluss blockiert. Health und `state status|dump` zeigen
Operations-ID, Scanstatus und Restore-Sentinel ohne gespeicherte Payloads.

Autoritätsereignisse nach diesem Serienschnitt tragen
`authority_series=authority.v2`, `instance_uuid` und `authority_epoch`.
Ältere Auditereignisse ohne UUID bleiben bei der Hochwassermarke konservativ
wirksam; der asynchrone Audit-Sink autorisiert keinen Normalbetrieb.

Der Referenzadapter akzeptiert nur über Linux-Mountinfo als lokal klassifizierte
Dateisysteme. NFS, CIFS und unbekannte Typen blockieren vor der
DB-Initialisierung. Das Schema nutzt `PRAGMA user_version=10`, WAL,
`foreign_keys=ON`, UTC-Zeitwerte und `auto_vacuum=INCREMENTAL`; ein neuerer,
unversionierter, beschädigter oder nicht prüfbarer Stand blockiert den Start.
`samuel state status|dump --json` läuft ohne SCM-/LLM-/Workflow-Bootstrap und
gibt keine gespeicherten Payloads aus. Ein v1- bis v9-Store wird
einseitig auf v10 aktualisiert; ein neuerer Stand blockiert weiterhin
Downgrades. Der Adapter
sichert eine aktive WAL-DB
über die SQLite Backup API und prüft das Artefakt; eine Dateikopie der aktiven
DB ist kein unterstützter Backupweg. Der Witness gehört bewusst nicht zum
DB-Backup-Artefakt. Der unterstützte Restore-Abgleich aus Stufe 5a ist aktiv;
ein manuelles Ersetzen von DB/Witness/Audit bleibt unsupported. Löschende
Retention bleibt ausschließlich Stufe 5c; gebundenes Finalisierungs-Resume
ist in Stufe 4 aktiv.
Der ADR-0482-Nachtrag vom 2026-08-30 teilt die beschlossene Stufe 5 in drei
getrennte Changes: 5a erzeugt beim Restore eine neue Autoritätslinie und
reconciled sie exklusiv, 5b liefert vollständigen Retention-Katalog,
kategorieweise Policy/Dry-Run sowie Score-Replay, und 5c aktiviert Löschung
erst einzeln je Kategorie. Das ausgelieferte Zielprofil ist
`eu_operational`; `eu_ai_act_high_risk_support` ist ein rollenbezogenes Opt-in
und keine Rechts- oder Konformitätszusage.

Stufe 5b implementiert den vollständigen, maschinengeprüften Katalog. Mit dem
5c-Fundament umfasst Schema v10 mit 26 State-Tabellen einschließlich Identity-
State sowie Workspace-Registry,
Audit-JSONL, verwaltete Backups und
Quarantäne. `config/privacy.json` klassifiziert jede Spalte sowie die Wurzel
jeder strukturierten Payload, definiert Kategorie- und Profil-/Rollendigest
und lehnt unbekannte Kategorien, unbekannte Felder, zu kurze Profilfristen,
einen nicht allowlist-fähigen `enforce`-Modus sowie das pensionierte
`pii_anonymize_after_days` fail-closed ab.
`planning_clarifications` enthält die begrenzten Frage-/Antwortinputs und
Akteurbindung als `pii_bearing`, bleibt wegen aktiver und späterer
Plan-Authority ohne zeitbasierte Löschung und wird nicht in Audit- oder
Dashboardpayloads kopiert.
Ein unbekanntes reales Schemaobjekt bleibt unangetastet und erscheint als
Finding. Der Dry-Run zeigt UTC-Cutoffs, Treffer und Schutzgründe. Für
`score_derivations` bindet er zusätzlich Kategorie-/Profilpolicy, absoluten
Cutoff, Anker, die Plan-Schemaserie `retention-execution-plan.v1` und sortierte
SHA-256-Objektidentitäten in einem Plan-Digest. Der Kategorie-Digest bindet
Feld-/Payloadklassifikation und Schutzregeln; die Kandidatenmenge bindet den
aktuell ausgewerteten Schutzstatus jeder Zeile.
Die ausgelieferte globale Retention-Notabschaltung ist aktiv, bleibt außerhalb
der Policy-Digests und ist in State/Health sichtbar.

Kategorie-Autorität wird persistent als
`report_only -> enforce | suspended` geführt; fehlende oder veraltete Bindung
erscheint als `report_only_pending_review`. `IRetentionExecutionStore` bietet
keinen Tabellen-/SQL-Parameter und registriert ausschließlich die
`score_derivations`-Strategie. `activate` bindet Plan-Digest, absoluten
UTC-Cutoff und serverseitigen Aktivierungszeitpunkt und lehnt einen Cutoff ab,
der zu diesem Zeitpunkt die effektive Kalenderfrist unterschreitet. `execute`
verwendet genau diesen Grant; ein gültiger konservativer Cutoff verfällt nicht
durch späteren Vollzug. Ausführung revalidiert Tabellen- und
Payloadklassifikation, Schutzstatus und exakten Kandidatensatz in der
SQLite-Transaktion, löscht und schreibt den append-only Receipt samt
Authority-Epoch atomar. Ein bereits belegter Receipt wird vor heutigen
Stop-/Policyregeln anhand seiner gespeicherten Identität gelesen; falsche
Identitätsbehauptungen blockieren. Wiederholung liefert denselben Receipt;
Drift oder Schreibfehler blockiert und suspendiert die Kategorie.
Restore aktiviert den globalen Stop und suspendiert jede vorherige
Vollzugsautorität.
`RetentionCoordinator.status` projiziert denselben Authoritystand passiv und
payloadfrei in den Dashboard-Health-Endpunkt: Not-Aus, Pending-Review,
Kategorie-/Profil-/Evidence-Digests, Grantzeit und letzte belegte Wirkung.

Für `run_projections` ist zusätzlich `non_terminal_never` konfiguriert und im
Dry-Run technisch ausgewertet: Nur `blocked`, `complete` oder `unbound` können
bei einem späteren eigenen Kategorie-Child überhaupt Alterskandidaten sein.
`running` und jeder unbekannte Status bleiben unabhängig vom Zeitanker
geschützt. Eine Löschstrategie für diese Kategorie ist weiterhin nicht
registriert; ihr Enforce-Rollout bleibt in #668 getrennt.

Alle ausgelieferten Kategorien stehen weiterhin auf `report_only`; es gibt
keinen Scheduler und keine produktive Löschaktivierung. Die CLI-Aktionen
`approve`, `activate`, `suspend`, `pause`, `unpause` und `execute` sind
begründungspflichtige Operatoraktionen. Der synthetische Canary belegt nur die
Mechanik. Die erste reale Kategorie bleibt in #668 offen, bis tatsächlich
abgelaufene produktive Objekte unter eigener Rollout-Evidence vorliegen.

Managed Backups entstehen nur
über die SQLite Backup API unter `managed_backup_dir`; Registry und
Verzeichnis werden gegeneinander geprüft, offene Restore-Digests pinnen ein
Backup. Kopien außerhalb dieser Grenze bleiben Betreiberverantwortung. Der
Score-Replay leitet aus immutable Rohbeobachtungen idempotent mehrere
Policy-/Formelserien ab und publiziert weder `ScoreObserved` noch verändert
er Quality-EWMA.

---

## 16. CLI-Reference

`samuel.cli` baut den Bus via `bootstrap()` und dispatched einen Subcommand.
Aufgerufen wird im Betrieb ausschließlich das installierte Console-Script
`samuel`; der Modulaufruf ist aus Zielrepositorys nicht unterstützt.
Die dabei sichtbare Produktversion stammt ausschließlich aus den installierten
Paketmetadaten. Beim Build materialisiert `setuptools-scm` diesen Wert aus
strikten `v<Version>`-Produkt-Tags; Phase-Tags werden ignoriert. Ein Checkout
nach dem Tag erhält eine PEP-440-Dev-Version mit Commitkürzel, während
metadatenlose Quellen nur `0+unknown` liefern. Voll-SHA und gesamter
Arbeitsbaum-Dirty-State bleiben separate Build-Evidence.

Globale Flags vor dem Subcommand:

| Flag | Wirkung |
|------|---------|
| `--config <dir>` | Pfad zum Config-Verzeichnis. Default ist `SAMUEL_RUNTIME_CONFIG_DIR`, falls gesetzt, sonst `config`. Bei gesetzter Runtimebindung muss ein expliziter Pfad normalisiert identisch sein; Abweichung blockiert vor dem Bootstrap. |
| `--log-level DEBUG\|INFO\|WARNING\|ERROR` | Override `agent.log_level` |
| `--self` | Self-Mode aktivieren (laedt `.env.agent` overlayend, setzt `SAMUEL_SELF_MODE=1`, default-workflow `self`) |
| `--allow-non-main` | Erlaubt `--self run` auf einer anderen Branch als `main` (Default: blockiert; Schutz gegen #227-Regression) |
| `-V`, `--version` | Version drucken und beenden |

### Subcommands

| Subcommand | Aufgabe | Wichtige Flags |
|------------|---------|----------------|
| `setup` | Interaktiver Einrichtungs-Wizard: SCM-Verbindung (Live-Test + Repo-Liste) samt genau einem erwarteten Required-Check-Kontext, Verzeichnisse, PROJECT_ROOT, Sicherheit (Auto-Keys), Zeitzone/Port → schreibt `.env` (chmod 600) + `agent.json`, legt Dirs + Labels an und führt Doctor aus. Die Abschlussbox sagt ausschließlich „Konfiguration gespeichert“, weist Doctor-/Qualification-Fehler getrennt aus und gibt niemals Credentialwerte aus. Laeuft vor Bootstrap. Der ausgelieferte, sichtbar gemeldete Kontext-Default ist `CI / lint-and-test (pull_request)`. | `--non-interactive` (Werte aus Env/.env, keine Prompts) |
| `doctor` | Diagnose mit Fix-Hinweisen: normalisierte Produktversion, getrennte vollständige Build-Revision/Dirty-State, SCM-Konfig + Live-Verbindung, bei Gitea Wert und Quelle des Soll-Required-Checks sowie fail-closed exakter Abgleich mit der nativen Release-Branch-Regel, LLM-Provider, Sicherheits-Keys, Verzeichnisse, Default-Configs, PROJECT_ROOT sowie TEST-Runner-/Toolchain-Readiness aus derselben Auflösung wie Planning und Gate 11. Ein leerer Sollwert, fehlendes Leserecht oder eine Abweichung ergeben Exit 1; beobachteter SCM-Zustand wird nie zum Sollwert. Das Ergebnis wird ohne Detail-/Secretpayload instanzgebunden für die passive Qualification projiziert. | – |
| `install-service` | systemd-Unit mit echten Pfaden/User/installiertem Console-Script generieren (ersetzt die Platzhalter-`samuel.service`). | `--mode watch\|dashboard`, `--write` (nach `/etc/systemd/system/`), `--user`, `--name` |
| `health` | Aktiver technischer Check (Python, Git-Runtime, Config, State/Authority, SCM, effektive LLM-Taskrouten) mit unverändertem Exitvertrag. Sein Bootstrap startet kein Auto-Resume und übernimmt keine Run-Workspaces. Die Ausgabe trennt `technical_health`, zweckgebundene `operational_readiness` und Doctor-/Audit-`qualification`. Externe LLM-Erreichbarkeit wird nicht live behauptet und ergibt deshalb Readiness `unknown`; State/Config/Authority bleiben kritisch. | – |
| `run <issue>` | `IssueReady`-Event fuer Issue publizieren (durchlaeuft den aktiven Workflow); ein zum Aufruf korrelierter `PlanBlocked` oder `PlanReplanRejected` ergibt Exit 1, ein erfolgreicher Dispatch Exit 0; autorisiert außerdem ausdrücklich eine neue Klärungsserie nach Timeout, Rundenerschöpfung oder Source-Supersession | `--workflow <name>` (Override) |
| `replan <issue>` | Aktiven Plan und seine Freigabe nachvollziehbar widerrufen, danach einen neuen Plan mit neuer Freigaberunde erzeugen | `--reason <text>` (Pflicht), `--workflow <name>` |
| `watch` | Polling-Loop, scannt nach Issues mit Workflow-Label | `--once`, `--interval <s>` |
| `dashboard` | HTTP-Server mit Web-Dashboard und REST-API; Operator-Konfiguration ist standardmäßig eingefroren | `--host`, `--port` (Default 7777), `--configuration-mode production\|setup` (Default `production`) |
| `setup-labels` | Workflow-/Risk-/Scope-Labels auf dem SCM anlegen (idempotent, liest `config/labels.json`) | – |
| `refresh-pricing` | OpenRouter-Modell-Cache aktualisieren (350+ Modelle mit Preisen, Dump in `data/`) | – |
| `replay` | Workflow eines Issues side-effect-frei aus dem Audit-Log rekonstruieren | `--issue <n>`, `--run <correlation-id>`, `--publish` |
| `audit` | HMAC-Chain des Audit-Logs auf Manipulationen pruefen | `verify` |
| `dlq` | Fehlgeschlagene Events auflisten oder erneut publizieren | `list`, `replay <id>`, `--limit <n>` |
| `changelog` | Markdown-Delta aus git log erzeugen (`feat`/`fix`/`refactor`/...-Commits mit `(#NNN)`-Ref). Default-Start ist der höchste erreichbare kanonische Produkt-Tag; Phasenmarker zählen nur mit explizitem `--phase`. | `--since <rev>`, `--phase <n>` (mappt auf `phase-n-complete`), `--post-to-issue <n>` (Kommentar in Gitea-Issue), `--out <delta-file>` |
| `state` | SQLite-State vor dem normalen Bootstrap diagnostizieren, einen Claim aufgeben oder den unterstützten Restore/Reconcile bedienen; Ausgabe enthält Schema/Mount/Pragmas/Tabellen oder nur Zähler, niemals gespeicherte Payloads. | `status`, `dump`, `abandon-healing`, `restore`, `reconcile-status|scan|classify|complete`, `--json` |
| `identity` | Lokalen Dashboard-Identity-State ohne Provider-/Workflow-Bootstrap diagnostizieren, ersten Administrator initialisieren, den Legacy-Cutover atomar ausführen oder nach Restore lokal recovern. Passwörter kommen ausschließlich aus einer eigentümergebundenen Datei mit Modus 0600 oder strenger. | `status`, `bootstrap`, `cutover`, `recover`, `--username`, `--password-file`, `--reason`, `--client-inventory-confirmed`, `--json` |
| `retention` | Katalog ohne normalen Bootstrap prüfen, Kategorie-Autorität explizit steuern, einen exakt gebundenen allowlist-basierten Plan ausführen, ein SQLite-konsistentes Managed Backup erzeugen oder Scoreableitungen event-/EWMA-frei wiederholen. Ausgeliefert ist keine Kategorie aktiv und es existiert kein Scheduler. | `dry-run`, `approve`, `activate`, `suspend`, `pause`, `unpause`, `execute`, `backup`, `replay-scores`, `--category`, `--plan-digest`, `--cutoff-utc`, `--reason`, `--json` |
| `evidence` | Einen explizit benannten vorhandenen Gitea-Actions-Run begrenzt lesen, gegen ein `EvaluationSubject` bewerten und als unveränderliche Advisory-Observation speichern. Startet keinen Run und besitzt keine Gate-/Dispatch-/Mutationswirkung. | `assess`, `--run-id`, `--attempt`, `--subject`, `--workflow`, `--event`, `--max-age-seconds`, `--issue`, `--json` |
| `candidate` | Einen bestehenden vollständigen Git-Head dem aktiven, menschlich freigegebenen Plan zuordnen. `submit` liest nur vorhandene Evidence. `request` autorisiert oder reconciliiert den gebundenen Providerauftrag; nur `--new-request` erzeugt bewusst eine neue Requestidentität. Beide passiven Varianten erstellen keinen PR und besitzen keine Implementierungs-/Healingwirkung. Exit 0 = gebundener passiver Erfolg, 1 = terminal abgelehnt/fehlgeschlagen, 2 = Provider-Evidence ausstehend. | `submit\|request <issue>`, `--head <full-sha>`, `--new-request` nur mit `request`, `--json` |
| `resume` | Gebundene Finalisierungs-Checkpoints über den normalen Bootstrap inspizieren, gezielt/gesamt fortsetzen oder nach Operatorprüfung aufgeben und bereinigen. `attempt` und `resume` sind Aliases. | `list`, `inspect <key>`, `attempt|resume [<key>]`, `abandon <key> --reason <text>`, `cleanup <key> --reason <text>`, `--json` |
| `workspace` | Gemeinsame Worktree-Registry ohne SCM-/LLM-/Workflow-Bootstrap inspizieren, terminale Einträge bereinigen, aktive Einträge begründet quarantänisieren oder bereits geprüfte Quarantäne-Evidence explizit verwerfen. | `list`, `inspect <id>`, `prune`, `quarantine <id> --reason <text>`, `discard <id> --reason <text>`, `--json` |

### Praxis-Beispiele

```bash
# Issue #136 manuell durch den Standard-Workflow
samuel run 136

# Fachlich unzureichenden aktiven Plan explizit ersetzen
samuel replan 136 --reason "Akzeptanzkriterium für den Fehlerpfad fehlt"

# Watch-Loop alle 30 s, Timeout aus config/agent.json:agent.auto.poll_timeout
samuel watch --interval 30

# Einmaliger Scan ohne Loop (CI/Cron-Pattern)
samuel watch --once

# Self-Mode: Agent bearbeitet ein eigenes Issue
samuel --self run 136

# Self-Mode auf Branch ausserhalb main (gefaehrlich, nur fuer manuelle Runs)
samuel --self --allow-non-main run 136

# Workflow override (z.B. night-Workflow ad-hoc)
samuel run 42 --workflow night

# Dashboard auf localhost only
samuel dashboard --host 127.0.0.1 --port 8080

# Verbose Logs (CLI uebersteuert config/agent.json)
samuel --log-level DEBUG run 42

# Changelog-Delta seit letztem Produkt-Tag; danach reviewt übernehmen
samuel changelog --out CHANGELOG_DELTA.md

# Changelog seit Phase 13, zusaetzlich als Kommentar zu Issue 250
samuel changelog --phase 13 --post-to-issue 250

# Runtime-State ohne SCM-/LLM-Start prüfen
samuel state status --json
samuel state dump --json
samuel state reproject-runs --json  # idempotente Statusreduktion, keine Payloadausgabe

# Retention: ausgeliefert report-only; keine dieser Zeilen aktiviert Löschung
samuel retention dry-run --json
samuel retention approve --category observations --reason "operator review" --json
samuel retention backup --json
samuel retention replay-scores --issue 667 --json
samuel retention replay-scores --eval-config-dir config \
  --eval-config-dir /srv/samuel/policies/formula-v2 --json

# Vorhandenen Gitea-Actions-Run ausschließlich advisory bewerten
samuel evidence assess --run-id 123 --attempt 1 --subject subject.json \
  --workflow .gitea/workflows/ci.yml --event pull_request --json

# Vorhandenen Candidate ohne PR-, Implementierungs- oder Healingfreigabe prüfen
samuel candidate submit 521 --head 0123456789abcdef0123456789abcdef01234567 --json

# Unterstützter Restore (Watch/Dashboard vorher stoppen)
samuel state restore --source BACKUP.sqlite3 --json
samuel state reconcile-scan --operation-id UUID --json
samuel state reconcile-status --operation-id UUID --json
samuel state reconcile-classify --operation-id UUID --object-type TYPE \
  --object-key KEY --classification abandoned --reason "operator evidence"
samuel state reconcile-complete --operation-id UUID --json

# Gebundene Finalisierung prüfen oder gezielt fortsetzen
samuel resume list --json
samuel resume inspect CHECKPOINT_KEY --json
samuel resume attempt CHECKPOINT_KEY --json

# Worktree-Registry und Quarantäne ohne Produkt-Workflow prüfen
samuel workspace list --json
samuel workspace inspect WORKSPACE_ID --json
```

### Watch-Exitvertrag

Der synchrone Watch-Slice zählt einen Planning-Dispatch erst nach einem
korrelierten `PlanPosted` als `planned`; ein Approval-Dispatch benötigt je nach
Workflow `PRCreated`, `ReviewCompleted` (`reviewed`) oder `PRMerged`.
`ReviewBlocked`, `MergeOutcomeUnknown`, `PlanBlocked`, `WorkflowAborted` und andere terminale
Fehler und ein Dispatch ohne beobachtbaren Endzustand erhöhen stattdessen
`dispatched_failed`. Das strukturierte Scanergebnis enthält zusätzlich je
Issue `correlation_id`, Phase, Status und terminales Event in
`dispatch_outcomes`. `samuel watch --once` beendet sich bei mindestens einem
solchen Fehler oder einem fehlenden strukturierten Scanergebnis mit Exit 1.
Das ist Ergebnisreduktion für Operator/CI, keine neue Retry-, Workflow- oder
Freigabeautorität.

### Workflow-Wahl: Reihenfolge

1. `--workflow X` (explizit am CLI)
2. `--self` → Workflow `self`
3. `agent.mode` aus `config/agent.json`

Override-Mechanik: vor `bootstrap()` wird `SAMUEL_WORKFLOW_OVERRIDE` gesetzt, weil
der Bootstrap das Workflow-File zur Lade-Zeit aussucht (#260).

Der mit `--config` gewaehlte Pfad wird beim Bootstrap normalisiert und als
prozesslokaler Wert fuer `agent.config_dir` gepinnt. Damit lesen und schreiben
LLM-Factory, Dashboard, Gates, Eval, Hooks und Notifications garantiert dieselbe
aktive Konfiguration; ein relativer oder von einem anderen Host stammender Wert
in `agent.json` kann den expliziten CLI-Pfad nicht umleiten (#470).

### Audit-Sink-Drainage beim Shutdown

Beim Beenden ruft die CLI `_shutdown_audit_sinks(bus)`, das alle `AsyncAuditSink`
deterministisch flushed bevor `sys.exit` greift (#257). Ohne diesen Schritt
werden Daemon-Worker-Threads unsanft gekillt und queued Events gehen verloren.

---

### Health-, Readiness- und Qualification-Projektion (#693)

`HealthHandler` führt den aktiven technischen Check aus und schreibt dessen
bereinigte Zusammenfassung sowie die zweckgebundene Workflow-Readiness in die
vorhandenen `run_projections`. `samuel doctor` und `samuel audit verify`
schreiben unabhängig ihre Fachbefunde. Alle Datensätze tragen
`health-readiness.v1`, State-Instanz, UTC-Prüfzeit und Evidence-Digest.

Ein Snapshot ist höchstens 3600 Sekunden aktuell. Eine fremde Instanz nach
Restore oder ein älterer Datensatz ist `stale`; ein fehlender Datensatz ist
`not_checked`. Eine aktuelle erfolgreiche Wiederholungsprüfung löst einen
Fehler nur unter Bindung seines vorherigen Digests auf. Fehlender Auditkey,
fehlende Dateien oder Rotation können einen Fehler weder überschreiben noch
in einen Pass verwandeln. Der State-Authorityblock enthält keinen erfundenen
`resume_enabled`-Default; nur der Resume-Runtime-Resolver liefert diesen Wert.

`GET /api/v1/dashboard/health` und der Viewerstatus lesen den Snapshot ohne
Bus-Command, SCM- oder LLM-Zugriff. Der aktive Self-Check bleibt unter
`RUN_PROVIDER_PROBES`: Er prüft jede wirksame konfigurierte LLM-Taskroute
über den vorhandenen Connection-Tester und übergibt an Health nur feste
Task-/Provider-/Pass-Facts. Eine vollständige Probe setzt die Readiness auf
`ready`, eine fehlende oder fehlgeschlagene Route auf `blocked`. Providerantworten,
Credentials, Endpoints und Modell-IDs werden weder im Ergebnis noch in der
Projektion gespeichert. Ein späterer Health-Check ohne Probe bleibt in seiner
eigenen Antwort `unknown`, überschreibt aber keinen noch aktuellen aktiven
Probe-Befund. Die Projektion ist Darstellung und gespeicherte Diagnose, keine
Gate-, Workflow-, Merge- oder Releaseauthority.

## 17. Dashboard-Reference

Web-Frontend auf `http://<host>:<port>/`. Auto-Refresh alle 10 Sekunden.

### Tabs / Sektionen

| Sektion | Quelle / API | Inhalt |
|---------|--------------|--------|
| Status-Karten | `dashboard`-Slice | Die auth-freie HTML-Shell rendert die normalisierte Produktversion serverseitig aus Paketmetadaten; nach Anmeldung ergänzt der Status-Payload getrennte Build-Revision/Dirty-State, aktuellen Modus und SCM-Verbindung |
| Metriken-Tabelle | `MetricsMiddleware` | Pro Command/Event: Count, Errors, Avg Latency |
| Health / Readiness / Qualification | `HealthCheckCommand`, `health-readiness.v1` | Der aktive Command bewahrt `healthy`, `critical` und `checks`, ergänzt aber technische Gesundheit und zweckgebundene Workflow-Readiness. Doctor und Auditverifier schreiben ihre eigenen begrenzten Qualification-Facts. Die passive Projektion ist an State-Instanz und Prüfzeit gebunden, läuft nach 3600 Sekunden ab und unterscheidet `active`, `stale`, `resolved` und `not_checked`. Fehlende Auditdaten löschen keinen früheren Fehler. Projektionen erteilen keine Authority. |
| LLM Quality (#153/#589) | `get_quality_overview` | Heatmap Provider/Modell × Task aus der neuesten gültigen gebundenen Score-Serie; `Serien-Calls` zählt nur den attribuierten letzten Issue-Call, unattribuierte Calls und Calls anderer Legacy-/Policy-/Formelserien werden getrennt ausgewiesen |
| Activity (#230) | `get_scm_activity` | Chronologischer SCM-Ereignis-Stream (Webhook), Filter Bot/Human |
| Compliance | `get_compliance_legend` | OWASP-/AI-Act-Legende, Deployment-Risikoklasse, LLM-Code-Kennzeichnung (#270) |
| Workflow-Runs | SQLite-`run_projections` | Redigierte, rotationsunabhängige History nach Issue und gebundener `correlation_id`; gemeinsame Core-Terminalreduktion, `unbound`-Ausschluss und idempotente Reprojektion; Audit-JSONL ist nur initiale Backfill- und Compliance-Evidence (#277/#627/#675/#672) |
| System-Prompts | `samuel/core/prompts/*.md` | 7 Prompts (planner, analyst, reviewer, healer, log_analyst, docs_writer, senior_python); Schreiben nach API-Key-Anmeldung ausschließlich im expliziten Setup-Prozess |
| Schedule | `config/llm/defaults.json` | Validierte Tag-/Nacht-Routing-Einstellungen pro Task |
| Test-Connection | LLM-Adapter | Manueller Provider-Reachability-Check inkl. Balance-Abruf (OpenRouter) |

### LLM-Call-Projektion

Im LLM-Tab sind der konfigurierte Default-Provider und die gespeicherten
Taskrouten von aktuellen Calls getrennt (#891). Die bestehende Metering-Kette
liefert prozesslokale Call-Facts an die passive Dashboard-API: Task, Provider,
angefordertes Modell, Issue/Workflow-Korrelation und Startzeit. Nach einer
Antwort kommt das tatsächlich gemeldete Modell hinzu; bei Fehlern ausschließlich
die Exceptionklasse, ohne Rohmeldung, Prompt oder Response. `response_received`
belegt keine Parser-, Task-, Gate- oder Qualification-Abnahme.

Ohne aktive Calls meldet die angebundene Runtime `idle`; ohne Livequelle bleibt
der Zustand `unknown`. Der letzte Call ist flüchtig. Nach Neustart werden weder
alte Budgetreservationen noch Audit-History als aktuelle Calls übernommen.
Die Anzeige erzeugt keine Providerprobe und keine Workflowaktion. Eine
konfigurierte Evaluation-Route besitzt derzeit keinen produktiven LLM-Consumer;
die Konfiguration belegt weder Nutzung noch Modellverfügbarkeit.

### Operator-Konfigurationsmodus

`samuel dashboard` löst genau einmal beim Start den typisierten Modus aus
`--configuration-mode`, danach `SAMUEL_CONFIGURATION_MODE` und schließlich dem
sichtbaren Default `production` auf. Nur `setup` erteilt diesem Prozess die
Authority für Setup-, Risiko-/Attribution-, Featureflag-, globale und
taskbezogene LLM- sowie Promptwrites. Authentisierung und spätere Rollen sind
davon unabhängig. Produktion antwortet vor jedem solchen Write mit HTTP 409
und `configuration_frozen`; auch der direkte Handlerpfad ist gesperrt.

Settings und Setup-Status projizieren Quelle, Schreibbarkeit, gespeicherten
und beim Prozessstart wirksamen nicht geheimen Config-Digest sowie
Neustartbedarf. Erfolgreiche Writes erzeugen keine In-Memory-Ersatzpolicy und
laden `FileConfig` nicht heiß nach. `.env` bleibt die externe Secretgrenze und
wird nicht in sichtbare Digests aufgenommen. Ein Setup-Prozess wird nach den
Änderungen beendet; erst ein neuer Produktionsprozess verwendet den
gespeicherten Stand.

### PR- und Merge-Erklärung

Der native Human-Merge-Abschluss bleibt ein eigener S.A.M.U.E.L.-Nachweiskommentar.
Bereits der PR zeigt neben dem Gatebriefing den fachlichen Auftragskontext und
den gebundenen Änderungsvergleich. Ein zweiter fachlicher Mergekommentar zeigt
den Auftragskontext und einen begrenzten,
redigierten Änderungsvergleich zwischen der gebundenen Base und dem Candidate.
Beide Kommentare sind replayfest; der fachliche Vergleich erzeugt keine neue
Gate-/Reviewauthority. Bei fehlender oder abweichender Bindung wird keine
Änderungserklärung erfunden.

### Problemdiagnosen

Die Problemtabelle zeigt neben Titel und vorsichtiger Ursachenbeschreibung die
bereits redigierte konkrete Diagnose und, sofern vorhanden, Exceptionklasse.
Gruppierte Meldungen lassen sich aufklappen: bis zu 20 jüngste Vorkommnisse
bleiben mit Zeit, Issue, Korrelation, Zeile und Diagnose sichtbar (#890).
Korrelation ist keine behauptete Kausalkette; eine generische Meldung belegt
keine Root Cause. Die Darstellung liest die vorhandene Auditprojektion und
erzeugt weder neue Diagnoseereignisse noch Remediation- oder Workflowaktionen.
`PlanComplexityWarn` bleibt ein sichtbarer, nicht blockierender Umfangshinweis;
seine Anzeige behauptet keinen abgelehnten Plan oder Gate-FAIL. Reale
Gate-/Workflowfehler behalten ihre eigene Diagnose.

### REST-API

Siehe §18 (`api/v1/...`).

### Auth

`config/auth.json` wählt exakt `legacy_api_key` oder `local_identity`. Legacy
akzeptiert `Authorization: Bearer <SAMUEL_API_KEY>` und `X-API-Key`; ein
fehlender Key blockiert bereits den Serverstart. Local Identity verwendet
Argon2-Passworthashes, opaque HttpOnly-Sessions, SameSite-Strict-/CSRF-Cookies
und explizit berechtigte Automation-Bearer. Der lokale Modus fällt niemals auf
den Legacy-Key zurück. Jede Route wird vor Dispatch einer Permission
zugeordnet; Viewer, Auditor, Operator und Administrator sind unabhängige
Rollen und können kombiniert werden.

Öffentlich bleiben die HTML-Shell `/` und `/dashboard`, der secretfreie
Modusendpunkt `/api/v1/auth/mode`, das Login und der separat HMAC-validierte
Webhook. Das Dashboard-JS speichert nur im Legacy-Modus den Key im aktuellen
Tab; lokale Rohsessions liegen nie im Browser-Storage.
Die Shell rendert ausschließlich die bereits öffentliche, HTML-escaped
Produktversion aus `__build_info__`; Voll-SHA, Dirty-State und Betriebsdaten
werden erst nach authentifiziertem Statusabruf ergänzt. `Cache-Control:
no-store` verhindert, dass ein aktualisiertes Deployment noch eine alte Shell
oder deren Platzhalter aus dem Browsercache zeigt (#746).
Benutzer, Rollen, Session-/Tokenhashes und Widerrufe liegen im aktuellen
SQLite-Schema v10 und verwenden dieselbe Instanz-UUID, Authority-Epoch und
Witness-Grenze.
Restore sperrt lokale Anmeldung bis zum begründeten CLI-Recovery.

### Webhook-Endpunkt

`POST /api/v1/webhook` empfaengt Gitea- oder GitHub-Webhooks. HMAC-Signatur
wird vor dem JSON-Mapping gegen die unveränderten Request-Bytes und
`SLICE_HMAC_KEY` validiert. Gitea verwendet in `X-Gitea-Signature` exakt den
unpräfixierten kleingeschriebenen HMAC-SHA256-Hexdigest; GitHub verwendet in
`X-Hub-Signature-256` weiterhin `sha256=<digest>`. Akzeptierte Events:
`issue-opened`, `issue-closed`, `pull_request-merged` sowie native
Gitea-Labeländerungen über `issues` / `issue_label` / `label_updated`.
Der native 1.27.2-Payload ist nur ein signierter Trigger und enthält kein
Label-Delta. Planfreigaben verlangen deshalb genau ein zum
`issue.updated_at` korreliertes providerseitiges Timeline-Ereignis für ein
menschliches `status:approved`-ADD nach dem aktiven Plan. Actor, Repository,
Issue, Plan, Contract und `X-Gitea-Delivery` werden gebunden; Removal,
andere oder mehrdeutige gleichzeitige Labelereignisse, historische Approvals,
Bot-Akteure und fremde Subjects bleiben fail-closed. Die Timeline ist Evidence
innerhalb des signierten Webhook-Transports und kein Polling-Fallback.

---

## 18. API-Endpoints

| Methode | Pfad | Beschreibung | Auth |
|---------|------|--------------|------|
| GET | `/`, `/dashboard` | Dashboard-HTML mit kanonischer Produktversion, ohne Build-Revision oder Betriebsdaten | Nein (Shell, exempt) |
| GET | `/api/v1/auth/mode` | aktiven Zugriffsmodus und secretfreien Identity-Status lesen | Nein |
| POST | `/api/v1/auth/login` | lokale Session und CSRF-Cookie erzeugen | Nein; nur lokaler Modus |
| GET | `/api/v1/auth/check`, `/api/v1/auth/session` | aktive Authentisierung beziehungsweise Actorprojektion prüfen | Authentisiert |
| POST | `/api/v1/auth/logout`, `/api/v1/auth/reauth` | Session widerrufen beziehungsweise nach Passwortprüfung rotieren | Session + CSRF |
| GET/POST | `/api/v1/admin/users`, `/api/v1/admin/sessions`, `/api/v1/admin/tokens` | lokale Principals, Sessions und explizite Automation-Token verwalten | passende Admin-Permission; Mutationen zusätzlich frische Reauth + CSRF |
| GET | `/api/v1/health` | Health-Check (`HealthCheckCommand`) einschließlich `retention_emergency_stop` und `retention_future_enforcement_blocked` im Authority-Block | Key¹ |
| GET | `/api/v1/dashboard/status` | Status + Metriken einschließlich `build.product_version`, Voll-SHA, Dirty-State und Revisionsquelle | Key¹ |
| GET | `/api/v1/dashboard/metrics` | Bus-Metriken (Count, Errors, Avg Latency) | Key¹ |
| GET | `/api/metrics` | Prometheus-kompatibler Export | Bearer |
| POST | `/api/v1/issues/{id}/plan` | `PlanIssueCommand` triggern | Bearer |
| POST | `/api/v1/issues/{id}/implement` | `ImplementCommand` triggern | Bearer |
| POST | `/api/v1/scan` | `ScanIssuesCommand` triggern | Bearer |
| POST | `/api/v1/webhook` | Gitea/GitHub Webhook-Empfang | HMAC-Signatur |

Plan-, Implement- und Scan-Commands liefern `202` nur für eine synchron
erfolgreiche Annahme; eine legitime Handler-Rückgabe `None` bleibt dabei
zulässig. Hat `ErrorMiddleware` den Command bereits vor der Antwort terminal
behandelt, liefert der Adapter stattdessen ein begrenztes RFC-9457-Problem mit
`code`, `correlation_id`, `command` und optionaler Issue-Nummer: 404 für ein
fehlendes Commandziel, 409 für einen Workflowabbruch und 500 für einen
internen Fehler. Rohes Exception-/SCM-Material wird nicht Teil der Antwort.
Spätere asynchrone Fehler verändern die ursprüngliche Annahme nicht (#752).

**Auth:** exakt der in `config/auth.json` gewählte Modus. Endpunkte ohne
explizite öffentliche Ausnahme verlangen immer Authentisierung und die
zugeordnete Permission.
**Webhook-Signatur:** `X-Gitea-Signature` als unpräfixierter 64-stelliger
Lowercase-Hexdigest beziehungsweise `X-Hub-Signature-256` als
`sha256=<digest>` gegen `SLICE_HMAC_KEY`; jeweils über die unveränderten
Request-Bytes und mit Constant-Time-Vergleich.

---

## 19. Konfigurations-Dateien

| Datei | Schema (in `samuel/core/config.py`) | Zweck |
|-------|-------------------------------------|-------|
| `.env` | – | SCM-Token, LLM-Keys, `SAMUEL_API_KEY`, `SLICE_HMAC_KEY` |
| `.env.agent` | – | Self-Mode-Override (laden mit `override=True`) |
| `config/agent.json` | `AgentConfigSchema` | Modus, Polling, Datenverzeichnis, Logging, Sequence-Validator |
| `config/llm.json` | `LLMConfigSchema` | Laufzeit-Default, Provider-Modelle und geordnete Fallback-Kette |
| `config/llm/defaults.json` | – | Per-Task-Routing, Token-/Temperaturwerte, Prompts und Schedules |
| `config/llm/providers.json` | – | Provider-Katalog, Key-/URL-Metadaten (kein konkurrierender Laufzeit-Default) |
| `config/gates.json` | `GatesConfigSchema` | Required/Optional/Disabled Gates |
| `config/eval.json` | `EvalSchema` | passive Scoring-Gewichte sowie Control-Plane-Runner-Policy (`test_policy_version`, `test_cmd`, `test_timeout`) |
| `config/execution.json` | versionierter Adaptervertrag | Standardmäßig deaktivierter Gitea-Execution-Provider; Trustprofil, Workflow-/Tool-/Environment-Digests, Artifact- und Freshnessgrenzen sowie Name der separaten Integritätsschlüsselvariable; Platzhalterdigests verhindern eine Aktivierung |
| `config/extensions.json` | `samuel.extensions.ExtensionConfiguration` | Beim Start gelesene, standardmäßig deaktivierte Operatorwahl für den öffentlichen Documentation-Datenconsumer; kein Runtime-Override oder Hot Reload |
| `config/architecture.json` | – | Rollen + Expansion-Scopes für Context Builder und ContractScope Gate 7b; Bestandteil des Policy-Digests |
| `config/hooks.json` | strikt validiert | Self-Preflight-Zuordnung bekannter `IQualityCheck`-Implementierungen pro Extension; unbekannte Werte stoppen den Start |
| `config/audit.json` | `AuditConfigSchema` | Sink-Type (jsonl), Pfad, Rotation |
| `config/notifications.json` | – | Slack/Teams/Webhook |
| `config/privacy.json` | `PrivacyConfigSchema` | PII-Scrubber, DSGVO-Drittland-Transfer, Retention |
| `config/repo_patterns.json` | – | Erwartete Event-Sequenzen pro Repo-Typ |
| `config/labels.json` | – | Workflow-/Risk-/Scope-Labels (`samuel setup-labels`) |
| `config/features.json` | – | Feature-Flags |
| `config/workflows/*.json` | – | 7 Workflow-Definitionen |

In `config/eval.json` ist ausschliesslich `weights` fuer die Gewichtung der
vier Scoring-Kriterien massgeblich. Das fruehere Listenfeld `criteria` bleibt
voruebergehend lesbar, ist aber deprecated, wird nicht ausgewertet und erzeugt
bei nicht-leerer Verwendung eine Warnung. Neue oder migrierte Konfigurationen
duerfen nur `weights` verwenden.

### LLM-Konfiguration: Zustaendigkeit und Prioritaet

Die drei LLM-Dateien sind keine austauschbaren Overrides:

| Datei | Wird zur Laufzeit gelesen von | Massgebliche Inhalte |
|---|---|---|
| `config/llm.json` | `FileConfig` und LLM-Factory | globaler Default-Provider, geordnete Fallback-Kette, Provider-Modell und Provider-URL |
| `config/llm/defaults.json` | LLM-Factory direkt | globale Aufrufparameter (`max_tokens`, `temperature`, `reasoning_reserve`), Circuit-Breaker/Cache sowie statische Per-Task- und validierte Schedule-Overrides |
| `config/llm/providers.json` | Dashboard-/Setup-Metadaten und Privacy-Providerabgleich | Katalog der angebotenen Provider, Namen der Key-Variablen und Anzeige-/Verbindungsmetadaten; **keine** Laufzeit-Prioritaet fuer Provider oder Modell |

Dabei sind fünf Ebenen getrennt: Die Multi-Provider- und Taskroutingfunktion
ist Produktcode; `config/llm/defaults.json` ist die ausgelieferte
Initialkonfiguration; gemountete Dateien und ausdrücklich gesetzte
Umgebungswerte sind Betreiberkonfiguration; ein D0-Profil ist eine externe,
subjectgebundene Qualificationkonfiguration; erst die nach Schedule-, Task-
und Globalauflösung tatsächlich gewählte Route ist die effektive
Runtimekonfiguration. Eine D0-Freigabe ändert weder Produktdefault noch
allgemeinen Supportumfang (#822, #829).

Effektive Provider-Prioritaet fuer einen Task: aktives validiertes Zeitfenster
(`tasks.<task>.schedule`) vor statischem Task-Override
(`tasks.<task>.provider`) vor `SAMUEL_LLM_PROVIDER` vor
`llm.json::default.provider`. Die Env-Variable ersetzt also den globalen
Default, aber keinen ausdruecklichen Task- oder Schedule-Eintrag.

Effektive Modell-Prioritaet: Schedule-Modell vor Task-Modell vor
`llm.json::<provider>.model` vor dem Adapter-Default im Code. Ein `model` in
`providers.json` ist Katalogmetadatum und ueberschreibt die Laufzeit nicht.
Aufrufparameter werden pro Feld aus `tasks.<task>` und danach aus
`defaults.json::default` bezogen; fehlt beides, gilt der Code-Default. Die
Fallback-Reihenfolge stammt ausschliesslich aus
`llm.json::default.fallbacks`.

Die Metadatenquellen `llm.json::openrouter.models_url` und
`openrouter.benchmarks_url` haben getrennte stabile Defaults
(`https://openrouter.ai/api/v1/models` beziehungsweise `/api/v1/benchmarks`).
Sie ändern weder Completion-URL noch Provider, Modell oder Taskroute.
Factory, `refresh-pricing` und Dashboard-Refresh verwenden dieselbe vorhandene
Config. Ungültige HTTP(S)-URLs mit Credentials, Query, Fragment oder
Steuerzeichen werden vor Netzwerkzugriff abgelehnt. Der Cache bindet seine
Quellen zusätzlich zur bisherigen TTL; ein Quellenwechsel verwirft die alte
Generation. Ältere Caches ohne Quellenbindung bleiben nur mit den historischen
Defaultquellen lesbar. Fehler zeigen sichere Klassen statt Response- oder
Exceptiontext; fehlende Benchmarks bleiben ausdrücklich advisory.

Vor einem Operator-Freeze werden die fünf effektiven Routen samt Provider,
Modell, Fallback, Timeout, Outputlimit, Workflowbudget und Promptdatei
secretfrei ausgelesen und an den Config-Digest gebunden. Änderungen erfordern
einen Neustart und einen neuen Subject; Catalog-, Benchmark- oder
Connection-Test-Ergebnisse überschreiben keine Route und autorisieren keinen
stillen Laufzeitfallback.

Ein statisches oder zeitgesteuertes `timeout`-Override wird an den jeweils
ausgewählten Leaf-Adapter weitergereicht, einschließlich der nativen Claude-
und Ollama-Adapter. Ohne Override verwenden beide weiterhin 120 Sekunden.

---

## 20. Deployment

### Lokale Releasegrenze

ADR-0706 ergänzt den Entwicklungscheckout um einen lokalen
Release-Candidate-Pfad. `samuel-release stage` erzeugt aus dem
release-manifestgebundenen Wheel und dem veröffentlichten hashgebundenen
Runtime-Lock eine vollständig neue venv unter
`/opt/samuel/releases/<version>`. Der isolierte Probe-Lauf vergleicht
Distribution-Metadaten, Python-API, installiertes Console-Script, Importpfad,
Produktversion und vollständige Revision. Erst danach kann
`samuel-release activate --expected-current ...` den Symlink
`/opt/samuel/current` atomar ersetzen.

Wirksame Konfiguration/Secrets (`/etc/samuel`), State/Evidence
(`/var/lib/samuel`), Prozesslogs (`/var/log/samuel`) sowie Workspaces,
Backups und reservierte Extensions (`/srv/samuel`) sind disjunkt vom Core.
Die Initialisierung kopiert Defaults nur in eine leere Config-Wurzel; Updates
verändern diese Pfade nicht und starten weder Dienst noch State-Migration.
Unklassifizierte Overlays direkt im Core, alte Importpfade und ein nicht
erwarteter aktiver Stand blockieren. `install.sh` bleibt Entwicklungsmodus;
die reale lokale Releasequalification folgt erst mit einem veröffentlichten
D0-Upgrade in #658.

### Systemd

Unit mit echten Pfaden generieren (statt die Platzhalter-`samuel.service` von
Hand anzupassen):

```bash
samuel install-service --mode watch                          # Vorschau
sudo $(which samuel) install-service --mode watch --write    # nach /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now samuel-watch
sudo journalctl -u samuel-watch -f
```

Die generierte Unit setzt `User`, `WorkingDirectory`, `EnvironmentFile=.env` und
`ExecStart=<absoluter-Console-Pfad>/samuel <mode>`. Bei einer ADR-0706-
Installation bewahrt der immutable Launcher den aufgerufenen stabilen
`/opt/samuel/current/bin/samuel`-Pfad, nachdem er geprüft hat, dass Launcher
und Runtime demselben Releaseverzeichnis angehören. Fehlt der installierte
Console-Entry-Point, bricht der Generator ab; es gibt keinen Modul-Fallback.

Für einen dauerhaften Dienst muss `agent.data_dir` auf ein absolutes,
persistentes, lokales, für den Unit-User schreibbares Verzeichnis zeigen.
NFS/CIFS und unbekannte Mounttypen blockieren den SQLite-State fail-closed.
Neben Audit- und Idempotenzdaten gehören insbesondere
`samuel-state.sqlite3`, `samuel-state-authority.json` und checksumbenannte
Legacyarchive zum Betriebsbestand. Ein DB-Backup umfasst den Witness bewusst
nicht. Vor jeder Rücksicherung ist der Dienst zu stoppen. Der unterstützte
Restore läuft über `samuel state restore --source <backup>`, danach
`reconcile-scan`, `reconcile-status`, begründete
`reconcile-classify`-Entscheidungen und zuletzt `reconcile-complete`.
Vollständiges manuelles Ersetzen von DB, Witness und Audit ist unsupported und
kann nicht als sicher erkannt behauptet werden. Der alte
`CheckRetentionCommand` vollzieht keine automatische Retention.
`samuel retention dry-run|backup` liefert Katalog und verwaltete
Backupgrenze. Das 5c-Fundament besitzt absichtlich keinen Scheduler und wird
mit globalem Stop sowie ausschließlich `report_only` ausgeliefert. Eine
Ausführung ist nur nach separatem Kategorie-Review, exakt gebundener
Planaktivierung, begründetem Stop-Release und explizitem `execute` möglich.

`samuel-state.sqlite3` läuft im WAL-Modus. Im laufenden Dienst darf sie nicht
per `cp` gesichert werden; die implementierte Adaptergrenze verwendet die
SQLite Backup API und prüft `integrity_check`. Der unterstützte
Restore-/Reconcile-Abgleich ist in Stufe 5a aktiviert. Eine offene Operation,
ein Sentinel oder eine erkannte Abweichung führt sichtbar in Reconcile und blockiert Healing
sowie Resume. Außerhalb von Reconcile bleiben sichere Finalisierungszustände
restartfähig; ein Offline-Backup des
gesamten Data-Verzeichnisses verlangt deshalb einen vollständig gestoppten
Dienst und anschließende Integritätsprüfung.

### Docker

```bash
SAMUEL_BUILD_VERSION="$(samuel --version | awk '{print $2}')" \
SAMUEL_BUILD_REVISION="$(git rev-parse HEAD)" \
SAMUEL_BUILD_SOURCE_URL="$(git remote get-url origin)" \
docker compose up -d
docker compose logs -f samuel
```

`Dockerfile` verwendet ein digestgebundenes `python:3.10-slim` für
`linux/amd64`. Build- und Runtimeabhängigkeiten werden aus getrennten, exakt
gepinnten SHA-256-Locks installiert; das lokal gebaute Projektwheel wird ohne
erneute Auflösung übernommen. Die vom Worktree-Adapter und Planning-Snapshot
benötigte Git-Runtime wird mit exakter Paketversion aus einem unveränderlichen
Debian-Snapshot installiert. Policy, Dockerfile, Manifest, Runtime-Probe und
Health binden beziehungsweise prüfen diese Voraussetzung (#727).
`.dockerignore` und gezielte
`COPY`-Anweisungen halten `.env`, `.git`, lokale Daten, Tests und lokale
Lizenzdateien aus Kontext beziehungsweise Image. `SAMUEL_VERSION`,
`SAMUEL_REVISION` und `SAMUEL_SOURCE_URL` werden als OCI-Annotationen
übernommen; die vollständige Revision speist zusätzlich `samuel.build_info`.
Volume-Mounts: `./config` (ro), `./data:/app/data`; `.env` via `env_file`.
Der Data-Mount ist der Persistenzvertrag für gebundene Evaluation- und
Healing-Evidence sowie `samuel-state.sqlite3` und muss deshalb als lokales
Volume in die Sicherung aufgenommen werden. Aktive WAL-Dateien werden nicht
mit einer einfachen Host-Dateikopie gesichert.
`CMD` =
`dashboard`.

`tools/container_release.py check` prüft Policy-, Input-, Lock-, Dockerfile-,
Kontext- und Compose-Drift offline in CI. Der Publish-Pfad übernimmt die
Tag-/Commit-/Artefakt-Authority von `tools/release_gate.py`, baut und prüft
`linux/amd64`, pusht create-only, startet das Registry-Digest in einem frischen
Compose-Projekt und schreibt erst nach Health- und Dashboard-Smoke
Manifest-Schema 2. Registry und Login bleiben Betreiberparameter. Der
mitgelieferte Referenzpublisher prüft Giteas persönliche Owner-/Token-Scope-
Grenze; das veröffentlichte Image und der Runtime-Pull haben weiterhin
keine Gitea-Abhängigkeit im Produktpfad. `v2.0.0a2` bleibt historisch ohne
Container-Image. `v2.0.0a3` ist mit dem Registry-Digest
`sha256:6a9c53ae5ba554a5b000e140f3a0929447984f230c9e50a1e5ce9c07d06dc5f6`
und einem grünen frischen Compose-Smoke als erster Containerstand nach diesem
Vertrag belegt. Der vollständige Update-, Rollback-, Publish- und
Abbruchvertrag samt CI-/Release-Evidence für #555 steht in
[`CONTAINER_RELEASE_OPERATIONS.md`](CONTAINER_RELEASE_OPERATIONS.md).

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

**CI-Vertrag:** Der bestehende Required Check läuft erst nach vollständigen
Tests auf CPython 3.10 und 3.14. Anschließend prüft er Paketbuild/Lizenz, Ruff,
Format, Produktions- und Test-Mypy, die vollständige Testsuite,
Architekturtests und den fail-closed Dependency-Audit. Das `dev`-Extra enthält
die echte Tree-sitter-JavaScript-Grammatik, damit Dashboard-Skripte auch in den
sauberen Kompatibilitätsumgebungen geparst und nicht nur lexikalisch geprüft
werden. Produkt-Tags lösen
zusätzlich das Post-Tag-Release-Gate aus. Ab `2.0.0a5` validiert dieses neben
dem Wegfall der Legacy-Autoritätsartefakte die fünf realen #399/#577-Fälle
gegen `docs/rollout/issue-399.schema.json` und die fallsemantische
Offline-Prüfung in `tools/rollout_evidence.py`; Freitext-Evidence genügt nicht.
Der getrennte #620/#653-Nachweis liegt in
`docs/rollout/issue-620.json`, ist an die exakten Bytes von
`docs/rollout/issue-620.schema.json` gebunden und wird durch
`tools/preflight_rollout_evidence.py` fallsemantisch geprüft. Die sechs
Fremd-Repository-Fälle belegen den grünen vollständigen Preflight, 7b-/9-/13a-
Blocks ohne `VerifyAC`, `GateEvaluationUnavailable` vor Subject-Aufbau und die
weiterhin heilbare alleinige Gate-11-Niederlage. Gate-/Observation-Schema v2,
Observation-/Evidence-Digest, nicht bindende Scoreability und PR-Revision sind
Teil der gespeicherten Evidence; Freitextkommentare allein genügen auch hier
nicht.
Der externe Ausführungsvertrag ist
getrennt in [`CI_RUNNER_OPERATIONS.md`](CI_RUNNER_OPERATIONS.md) festgelegt:
repositoryspezifisches Label, digestgebundenes amd64-Job-Image und vollständige
Commit-SHAs für externe Actions. Admission-Healthcheck, Git-Low-Speed-Grenze
und endliche Joblimits trennen dabei Hostverfügbarkeit, stillstehenden
Checkout und die äußere Laufzeitgrenze; ein Netzfehler bleibt fail-closed.

### Slice-Isolation-Regel

`tests/test_architecture_v2.py` schlaegt fehl, wenn:
- Ein Slice einen anderen Slice importiert (`from samuel.slices.X` in Slice Y)
- Ein Slice direkt einen Adapter importiert (`from samuel.adapters.X`)

Wenn ein Slice einen Adapter braucht, geht das ueber Dependency-Injection im
Bootstrap (`server.py`) oder via Resolver-Funktion (z.B. `_balance_resolver` in
`server.py`).

### Repository-Wartung und Self-Mode

Der ausgelieferte `self`-Workflow beschreibt eine Produktfähigkeit. Für die
aktuelle Wartung dieses Repositorys ist sein Einsatz bis zu einer
ausdrücklichen Freigabe ausgesetzt; Änderungen laufen manuell auf einem
Issue-Branch durch Tests, Review-PR und den geschützten Mergepfad. Ein
`--chat-workflow`-CLI-Flag existiert nicht; ein anderes Profil wird bei einem
normalen Produktlauf mit `samuel run <issue> --workflow <name>` gewählt.

---

## 22. Erweiterung

### Öffentlicher externer Datenanschluss

`samuel.extensions` ist die einzige öffentliche Python-Grenze für den ersten
externen Consumer. Der Contract `documentation.static_claims` `1.0` verwendet
geschlossene JSON-Manifeste, Requests und Resultate; die zugehörigen
sprachneutralen JSON Schemas werden im Wheel mitgeliefert. Externe Prozesse
werden nicht im Core geladen und erhalten keinen Store-, Secret-, Gate- oder
Mergezugriff. Details, Eingangsgrenzen und CLI-Beispiele stehen im
[Extension-Datenvertrag](EXTENSION_CONTRACT.md).

`config/extensions.json` ist beim ausgelieferten Stand deaktiviert und
optional. Die Auswahl wird beim Prozessstart gelesen; Installation oder
Manifestanwesenheit aktiviert nichts. Ein optional fehlender Consumer lässt
Coreworkflows unverändert. Eine ausdrücklich erforderliche, aber deaktivierte,
fehlende oder inkompatible Capability blockiert die betroffene
Extensionaktion. Änderungen folgen dem D08-Setup-/Restartvertrag.

Die erste konkrete Claimfamilie `documentation.inventory.v1` bindet eine
repositoryeigene exakte Markdown-Pfadliste, Consumer-Identifier und Tooldigest
an Repository und vollständigen Head. Der unabhängige Consumer erzeugt nur
Pfad-/Größen-/Digestclaims. Der Produktverifier liest die tatsächlichen
Git-Blobs erneut, verlangt exakte Coverage und prüft Secret-/Sensitive-Data-
Signale, bevor eine nicht autoritative Metadatenprojektion publiziert werden
kann. Contractdigests verwenden lexikografisch sortiertes kanonisches JSON.

`samuel.adapters.git_publication.publish_projection` ist der schmale
Artefakteingang vor dem vorhandenen Publisher. Der bisherige Wiki-Publisher
bleibt sein kompatibler Caller; Inventory-Projektionen verwenden denselben
Marker-, Non-force-, No-op- und atomaren Receiptpfad. Ein fehlendes lokales
Receipt wird nur bei identischem Remote-Marker, Revision, Dateisatz und Digest
rekonstruiert. Es existiert kein zweiter Publisherstore.

### Neuen Slice anlegen

```
samuel/slices/<name>/
├── __init__.py
├── handler.py          # subscribed Events/Commands im Bus
└── tests/
    └── test_handler.py
```

Im Bootstrap registrieren (Step 7). Architektur-Test laeuft automatisch
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

`config/architecture.json` editieren — kein Code noetig. Context Builder und
ContractScope (Gate 7b) lesen die Datei zur Laufzeit; jede Änderung verändert
den gebundenen Policy-Digest und invalidiert ältere Evidence.

---

## 23. Deterministischer Wiki-Build

Der interne Wiki-Pilot aus ADR-0635, ADR-0643 und ADR-0649 projiziert das aktive
Dokumentinventar in zehn aufgabenorientierte Markdown-Seiten. Er ist
Repository-Tooling und kein Runtime-Slice, Plugin, Publisher oder
Freigabe-Gate.

```bash
python tools/wiki.py impact       # Review-Impact je Page/Block als JSON
python tools/wiki.py check        # Manifest, Coverage, deterministische Builds
python tools/wiki.py build        # lokale Ausgabe nach wiki/
python tools/wiki.py check-local  # lokale Ausgabe fehlt, ist stale oder verändert?
```

`impact` ist read-only und darf bereits im dirty Working Tree laufen. Der
JSON-Bericht ordnet stale oder nicht auflösbare Content-Block-Bindungen sowie
vorhandene `document_contract_impact()`-Abschnitte über die manifestierte
Primärquelle einer Page-ID zu. Er aktualisiert keinen Digest und behauptet
weder eine semantische Vollprüfung freier Prosa noch eine exakte
Git-Diff-/Byteänderungsprognose. Eine leere Liste ersetzt deshalb nicht
`check`; sie bedeutet nur, dass die vorhandenen gebundenen Review-Quellen
aktuell keinen Impact melden.

`check` und `build` verlangen einen sauberen getrackten Stand. Ungetrackte
Operatorartefakte fließen nicht ein. `check` benötigt in einem frischen
Checkout keine vorhandene ignorierte Ausgabe. `check-local` vergleicht dagegen
die materialisierten Seitenbytes und den stabilen Receipt-Inhalt mit dem
aktuell gebundenen Head. Das versionierte
`docs/capabilities/wiki-manifest.json` ordnet jedes aktive Dokument aus
`document-contract.json` exakt einer primären Page-ID zu; fehlende, zusätzliche
oder doppelte Zuordnungen blockieren. Die Zahl der Dokumente ist nicht im Tool
hardcodiert. Getrennt davon bindet jede Page-ID mindestens einen stabilen
`source_section`- oder `resolved_fact`-Content-Block. Abschnittsblöcke nennen
aktives Quelldokument, exakte Überschrift, Dokumentklasse und Digest der
ausgewählten Bytes. Fact-Blöcke verwenden ausschließlich zugelassene Resolver
aus `tools/control_matrix.py` und binden deren kanonisch serialisiertes Ergebnis.
Fehlende oder mehrdeutige Selektoren, stale Digests, Klassenabweichungen und
nicht auflösbare Links blockieren den Build.

`wiki/` ist ignorierte, lokale Buildausgabe. `install.sh` und der dokumentierte
Source-Updatepfad erzeugen sie; beliebige Git-Operationen installieren keinen
versteckten Hook. Die zehn Seiten enthalten
Persona-Wege, direkt lesbare gebundene Kerninhalte, aufgelöste Runtime-Facts,
Quellenklasse/-modus, relative Links und vertiefende Inhaltsoutlines. Relative
Links ausgewählter Quellabschnitte werden aus dem ursprünglichen
Dokumentkontext auf Repositoryziele umgeschrieben; Codeblöcke, Tabellen und
Überschriften bleiben deterministisch erhalten. Die Seiten bleiben nicht
autoritative Projektionen; Code, ausgelieferte Konfiguration, gebundene
Resolver und aktive Quelldokumente bleiben maßgeblich.

Die Wiki-Ausgabe wird niemals separat redaktionell gepflegt. Erklärende
Langform wird einmal im zuständigen aktiven Dokument geändert; maschinenlesbare
Fakten einmal in Code oder ausgelieferter Konfiguration. Danach werden lokales
und externes Wiki neu gebaut. Der Content-Block-Digest erzwingt vor der
Übernahme eine bewusste Prüfung der betroffenen Darstellung und wird nicht im
normalen Build automatisch passend geschrieben.

`build-receipt.json` bindet Repository, vollständigen Head-SHA,
Dokumentvertrags- und Quelldigest, Generatorversion, Seitenmanifest und exakte
Seitenbytes. Nur `created_at` verwendet die reale Laufzeit. Die sichtbare
Buildzeit kommt aus der Commitzeit beziehungsweise `SOURCE_DATE_EPOCH` und der
Artefaktdigest enthält weder Uhrzeit, absoluten lokalen Pfad noch
Publisherdaten. Das Receipt ist weder `EvidenceEnvelope` noch Gate-, Release-
oder Publication-Receipt.

P1 führt keinen Candidate-Code aus und benötigt weder SCM-/LLM-/Cloud-Token
noch Netzwerkzugriff. Die lokale Ausgabe ist providerneutral. Die davon
getrennte, in P3 implementierte Veröffentlichung nach Gitea Wiki, GitHub Wiki
oder mehreren Zielen verwendet den in Abschnitt 24 beschriebenen Git-Publisher
mit eigenem Publication Receipt. Der spätere Reference-Plugin-Vertrag gehört
weiterhin in #639/#636.

---

## 24. Providerneutraler Git-Wiki-Publisher

Der P3-Publisher aus #645 nimmt ausschließlich den mit `check-local` geprüften
Build unter `wiki/` als Eingang und veröffentlicht über ein konfiguriertes
Git-Remote. Er verwendet keine Gitea-/GitHub-Wiki-API. Providerunterschiede
liegen in Remote-URL, Zielbranch und dem SHA-gebundenen Quell-URL-Template.

Seit #636 kapselt `samuel.adapters.git_publication.publish_projection` den
Wirkungsteil hinter einem schmalen validierten Eingang aus Dateibytes,
Source-Head und Eingangsartefaktdigest. Der bisherige Wiki-Wrapper erzeugt
weiterhin dieselbe Projektion und übergibt sie an diesen Eingang. Der
Documentation-Inventory-Pfad übergibt nach seiner separaten Contract-, Git-
Blob-, Coverage- und Sensitive-Data-Prüfung drei begrenzte Metadatendateien.
Beide Pfade verwenden denselben Marker und Receipt; der Eingang akzeptiert
keine Vertrauensentscheidung eines Producers.

```bash
python tools/wiki_publish.py \
  --remote "$WIKI_GIT_REMOTE" \
  --branch main \
  --source-url-template "$WIKI_SOURCE_URL_TEMPLATE"
```

Git authentisiert über einen vorher eingerichteten SSH-Agenten oder Credential
Helper. Token gehören nicht in Remote-URL, CLI-Argumente, Marker, Log oder
Receipt. Ein fremdes nicht leeres Wiki blockiert, bis sein exakter Head einmalig
mit `--adopt-existing-head <full-sha>` bestätigt wird. Danach prüft der Marker
Dateisatz und publizierten Content-Digest; unbekannte oder manipulierte Dateien
blockieren. Der Publisher verwendet einen normalen Git-Push ohne Force; bewegt
sich der Remote-Head nach dem Clone konkurrierend weiter, lehnt Git den Push ab
und die Veröffentlichung blockiert. Ein identischer Folgelauf bleibt ohne
Commit und Push.

Das Manifest mappt die zehn Page-IDs auf stabile Git-Wiki-Dateien; `wiki.home`
wird `Home.md`. Der Publisher ergänzt `_Sidebar.md` und `_Footer.md` und
projiziert lokale Quelllinks über das konfigurierte Template auf den gebundenen
Head. Das lokale Standard-Receipt liegt unter
`build/wiki-publication-receipt.json`. Es bindet Eingangs-Artifact-Digest,
publizierten Content-Digest, credentialfreies Ziel, Branch und vorherigen/neuen
Remote-Commit. Es ist weder EvidenceEnvelope noch Gate- oder Release-Nachweis.

Gitea und GitHub können denselben Publishervertrag verwenden. Ein Ziel wird
nicht allein durch die Synchronisation des Hauptrepositorys aktualisiert;
jeder Wiki-Remote benötigt einen eigenen expliziten Publikationslauf und ein
eigenes Receipt.

---

*Stand 2026-08-29. Bei Pipeline-Aenderungen siehe Pflege-Regel in
`technische Beschreibungen/README.md`: zuerst Code, dann Doc — im gleichen PR.*

---

## Lizenz

Der gesamte Repository-Inhalt steht unter Apache-2.0. Die maßgebliche
Root-Datei `LICENSE` enthält den Lizenztext; `pyproject.toml` deklariert denselben Status
maschinenlesbar als SPDX-Ausdruck und nimmt die Lizenzdatei in Wheel und sdist
auf. Es gibt keine separate Entitlement-Lizenz oder Premium-Laufzeitstufe.
