# S.A.M.U.E.L. v2 — Technische Dokumentation

[Produkt](../README.md) · [Technischer Überblick](TECHNICAL_OVERVIEW.md) · [Dokumentwege](README.md)

Diese Advanced-Referenz richtet sich an Entwickler, Operatoren und Reviewer,
die eine konkrete Funktion bis zu Konfiguration, Consumer und Fehlergrenze
nachvollziehen müssen. Die bestehenden Kataloge bleiben vollständig erhalten.

| Frage | Maßgebliche Vertiefung |
|---|---|
| Welche Komponente empfängt den Auftrag und führt ihn aus? | Architektur/Core (§1), Bus (§2), Bootstrap (§3), Events/Commands (§4), Workflow (§5), Slices (§6) und Adapter (§7). |
| Wie entstehen ein gebundener Candidate und eine Entscheidung? | [Referenz-Workflow](../technische%20Beschreibungen/README.md), LLM-Stack (§8), Gates (§9), Acceptance (§10), Review/Merge und Healinggrenzen in den Pipelinebeschreibungen. |
| Wie bediene und diagnostiziere ich den Prozess? | CLI (§16), Dashboard (§17), API (§18), Konfiguration (§19) und [Installation/Betrieb](INSTALL.md). |
| Welche Daten überleben einen Neustart, und was bedeutet ihr Status? | Persistenz (§15), [State-/Recoveryreferenz](STATE_STORE.md) und die dort getrennten Authority-, Observation- und Projektionsdaten. |
| Wo liegen Budget-, Sicherheits- und Fehlergrenzen? | LLM-Stack (§8), Routing/Budgets (§12), Security (§13), Audit (§14) sowie Abbruch-/Recoverypfade in den Pipelinebeschreibungen und der State-Referenz. |
| Welche Modellrolle liest welche Anweisung? | [Tatsächliche Prompt-/Consumerreferenz](agents/AGENT_PROMPTS_AND_INSTRUCTIONS.md); konfigurierte Route, aktiver Consumer und Coding-Agent-Anweisung bleiben getrennt. |
| Welche Erweiterung besitzt welche Rechte? | [Produktgrenze](adr/0678-product-boundary-and-integration-profile.md), Erweiterungen (§22) und [Extension Contract](EXTENSION_CONTRACT.md). |

Ergänzende Bedienungs- und Datenbeschreibungen:
[alle Dokumente und Funktionswege](README.md),
[Dashboard und sämtliche Settingsbereiche](DASHBOARD.md),
[SQLite: Zweck, Tabellen, Spalten, Constraints und Betrieb](STATE_STORE.md).

Für normale Run-/Watch-Aufträge ist `PROJECT_ROOT` explizit erforderlich.
Der seit v2.0.0a29 veröffentlichte lokale OCI-Projektpfad (#988) registriert einen
bestehenden dedizierten Hostcheckout mit `samuel-container project`; Setup,
Doctor und Dashboard prüfen dieselbe Bindung. Ein Dashboardpfad allein erzeugt
keinen Mount. [Betriebsanleitung und Rollback](INSTALL.md#registrierter-lokaler-oci-projektbestand-988).
Projekt-Readiness, technische Health und Sicherheitsqualifikation bleiben
getrennte Aussagen; lokale Tests sind kein Isolationsnachweis.


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
> [Pipeline-Übersicht](../technische%20Beschreibungen/README.md) mit den
> heutigen Workflow-/Authoritygrenzen und Evidencearten voneinander getrennt.
> Veröffentlichte Installation, Regression, Komponentenabnahme und vollständige
> Qualification sind eigene Claims; der aktuelle gebundene Nachweisstand steht
> in [CURRENT_PRODUCT_STATUS](status/CURRENT_PRODUCT_STATUS.md) und #962/#994.

> **Historischer Developmentdelta auf `main@41340e75` (29.09.2026):** Die technische
> MANUAL-Receipt-Fortsetzung ist durch #910/PR #911 mit gebundener
> Watch-Reevaluation und Regressionen integriert. Ebenso sind native signierte
> Gitea-Freigabe (#904), Health-/Resume-Konkurrenzgrenzen (#906/#913),
> Providerfehlerbehandlung (#912/#918) und unmoegliches `GREP:NOT` (#916)
> korrigiert. Die historischen Development-E2E-Subjects #1/#2/#3 bleiben
> Failure-Evidence; ein neuer zusammenhaengender positiver Lauf fehlt (#859).
> Der bestehende #693-Health-/Self-Check-Vertrag bleibt erhalten; #921 umfasst
> nur die fehlende Full-System-Aggregation und den kritischen Preflight.
> Der Absatz beschreibt ausschließlich den damaligen Stand. Heutiger Release-/
> Arbeitsstatus und vertagte Abnahmen stehen in
> [CURRENT_PRODUCT_STATUS](status/CURRENT_PRODUCT_STATUS.md) und #962.

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
- **Externe Systeme nur ueber Ports** — `samuel/core/ports.py` definiert die
  abstrakten Interfaces; aktuelle Inventare stehen in der generierten
  [Runtime-Referenz](RUNTIME_REFERENCE.md). Adapter implementieren sie und werden im Bootstrap
  injiziert.
- **Tests beim Slice** — `samuel/slices/<slice>/tests/test_*.py`. Uebergreifende
  Tests (Architektur, Integration) liegen in `tests/`.

### Verzeichnisstruktur

```
samuel/
├── core/                  Shared Kernel
│   ├── bus.py               Bus + 4 Middlewares
│   ├── bootstrap.py         12-Step Startup-Sequenz
│   ├── commands.py          Command-Typen (Inventar: Runtime-Referenz)
│   ├── events.py            Event-Typen (Inventar: Runtime-Referenz)
│   ├── workflow.py          WorkflowEngine (JSON-Mapping Event→Command)
│   ├── config.py            FileConfig + Pydantic-Schemas
│   ├── ports.py             Port-Definitionen (Inventar: Runtime-Referenz)
│   ├── state.py             State-Records + redigierte Fehler-Taxonomie
│   ├── types.py             Issue, PR, LLMResponse, GateContext, …
│   ├── errors.py            Error-Hierarchie
│   ├── http_client.py       HTTP-Abstraktion (httpx-Wrapper)
│   ├── git.py               Git-Helper (current_branch, diff, …)
│   ├── issue_context.py     Issue→Context-Extraktor
│   ├── project_files.py     Iter-Helper, CODE/CONFIG-Extension-Listen
│   ├── schedule.py          Tag/Nacht-Schedule
│   ├── ai_act.py + owasp.py Compliance-Mappings
│   ├── compliance/          OWASP-/AI-Act-/CRA-/GDPR-Mappings (Package-Data)
│   └── prompts/             7 System-Prompts (analyst, planner, …)
├── adapters/              Externe Systeme (siehe §7)
├── slices/                Domain-Slices (siehe §6)
├── server.py              HTTP-Server + Dashboard-HTML
├── cli.py                 CLI-Entry-Point
└── __main__.py            nur vertrauenswürdiger Source-Checkout; kein Betriebs-Entrypoint
```

### Gemeinsame Verträge und interne Hilfsmodule

Der Baum ist ein Überblick. Die folgenden Familien ordnen auch die weniger
sichtbaren Corefunktionen ihren bestehenden Bedien- und Fachgrenzen zu.
Private Helper und Kompatibilitätsmodule sind keine zusätzliche öffentliche API.

| Quellenfamilie unter `samuel/core/` | Verhalten und Beschreibung |
|---|---|
| `acceptance.py`, `evaluation_subject.py`, `evaluation_observation.py`, `review.py`, `external_evidence.py` | Plan-/Scope-/Approval-, Subject-, Beobachtungs-, Review- und advisory SCM-Check-Verträge; Validierung, Digests und Source-Revalidierung in §5, §9, §10 und §14. Ein formal gültiges Objekt erteilt keine eigene Authority. |
| `state.py`, `workspaces.py`, `retention.py`, `health_projection.py`, `approval_diagnostics.py`, `permission_diagnostics.py`, `webhook_diagnostics.py`, `identity.py` | Typisierte State-/Workspace-/Retention-/Identity-Verträge und bounded Diagnoseprojektion; §15–§18. Planfreigabediagnose revalidiert vorhandene Authority über `acceptance.py` und versendet gebundene, nichtautoritative Issue-Rückmeldungen; Store, Authority und passive Anzeige bleiben getrennt. SCM-Berechtigungsdiagnosen beschreiben einzelne Operationen ohne Gesamtfreigabe (§17). Webhookdiagnosen teilen begrenzte Ingressbeobachtungen und passive Darstellung zwischen Receiver, Dashboard und Doctor; keine Startsperre oder dauerhafte Zustellhistorie. |
| `llm_budget.py`, `issue_context.py`, `workflow_outcome.py`, `schedule.py` | Persistente Workflowzulassung, korrelierter Aufrufkontext, terminale CLI-Ergebnisreduktion und Zeitfenster; §5, §12, §16. Sessionzähler oder eine konfigurierte Route ersetzen keine Zulassung. |
| `config.py`, `configuration_mode.py`, `configuration_session.py`, `bootstrap.py`, `workflow.py` | Generische JSON-Quellen mit spezialisierten Vertragsvalidatoren, Dashboard-Schreibauthority und bestehendes Wiring; §3, §5 und §19. Setup ist für die Erstinstallation; der exklusive LLM-Konfigurationsmodus aktiviert einen vollständigen Adaptergraphen ohne Neustart. Watch lädt generische JSON-Werte pro Scan erneut; Workflow und Wiring bleiben Startzustand. |
| `project_binding.py`, `git_remote.py`, `git.py`, `command_safety.py`, `process_environment.py`, `test_runner.py` | Registrierte OCI-Projektidentität, kanonisches SCM-Ziel, Git-/Commitwirkung, aktionsnahe Commandpolicy und gemeinsame sterile Runner-/Toolchainprüfung; §10, §13, §16 und INSTALL. Keine Prozesssandbox. |
| `security_policy.py`, `attribution.py`, `compliance_mapping.py`, `ai_act.py`, `owasp.py`, `compliance/*.json` | Secret-/Promptsignalregeln, AI-Kennzeichnung und vier versionierte advisory Framework-Mappings; §13/§14 und [Frameworkzuordnungen](COMPLIANCE_FRAMEWORK_MAPPINGS.md). Keine juristische Konformitätszusage oder aktive Packpolicy. |
| `bus.py`, `commands.py`, `events.py`, `ports.py`, `types.py`, `errors.py` | Command-/Eventtransport, Ports, Domain-/Fehlertypen und begrenzte Diagnosen; §2, §4 und §7. Vorhandene Typen können unverdrahtete Kompatibilität sein. |
| `project_files.py`, `path_risk.py`, `lockfiles.py`, `quality_params.py` | Repositoryiteration, Pfadmuster, Lockfilepaketnamen und informative lokale Modellgrößenprüfung; Kontextpipeline, §6, §8 und §9. Heuristiken behaupten keine vollständige Sprach-, Dependency- oder Modellqualifikation. |
| `logging.py`, `http_client.py`, `replay.py` | Logging-/Diagnoseanschluss, begrenzter HTTP-Transport und vorhandener Event-Replay; §14/§16. Ein expliziter Bus-Replay kann Subscriberwirkungen auslösen und ist keine rein lesende Qualification. |
| `prompts/*.md` | Ausgelieferte Systemprompts und Library-Einträge; [Prompt-/Operatoranleitung](agents/AGENT_PROMPTS_AND_INSTRUCTIONS.md) nennt Consumer und Override-Reihenfolge. Drei Library-Einträge besitzen keinen aktiven LLM-Consumer. |

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

Subscriberfehler in `Bus.publish` erhalten pro fehlgeschlagenem Handler einen
Eintrag in der JSONL-Dead-Letter-Queue. Commands werden auf diesem Pfad nicht
erfasst. Auch ein DLQ-Schreibfehler bleibt möglich und wird geloggt; die Queue
ist keine Zusage, dass jedes Event wiederherstellbar ist. `samuel dlq list`
und `samuel dlq replay` sind ausdrücklich ausgelöste Operatoraktionen.

## 3. Bootstrap (12-Step Startup-Sequenz)

`samuel.core.bootstrap.bootstrap(config_path)` baut den Bus auf und gibt ihn zurueck.

| Step | Aktion |
|------|--------|
| 0 | `.env` laden (ohne ueberschreiben bestehender Env-Vars) |
| 1 | Generischer `FileConfig`-Loader; kritische Verbraucherwerte und spezialisierte Workflow-/Gate-/Evalverträge separat validieren; SCM-/Git-Auth-Adapter ohne Netzwerkzugriff konstruieren |
| 2 | Logging-Setup (Level, File, Rotation) |
| 3 | Bus + 4 Middlewares verdrahten |
| 4 | Audit-Sinks (JSONL via `AsyncAuditSink` mit Fallback) |
| 5 | Bereits in Step 1 konstruierte SCM-Auswahl protokollieren (Gitea oder GitHub via `SCM_PROVIDER`) |
| 6 | LLM-Adapter inkl. Task-Routing, geordneter Provider-Fallback-Kette, Circuit-Breaker und Sanitizer |
| 7 | Slice-Handler einschließlich Skeleton-, Gate- und Quality-Registry registrieren |
| 8 | Health-Check ausführen und kritische Fehler protokollieren; dieser Schritt allein bricht Bootstrap nicht ab. Vorgelagerte Vertrags-/Projektprüfungen besitzen eigene Blockiergrenzen. |
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
`samuel replan <issue> --reason <text>` und die Dashboard-Aktion **Neu planen** verwenden denselben expliziten Ersatzpfad. Er schreibt
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

Die [Planfreigabeanzeige im Workflowdetail](DASHBOARD.md#menschliche-planfreigabe-prüfen-948)
unterscheidet gültige dauerhafte Authority, sichtbares Label ohne Authority
und nicht prüfbare Evidence. Die ursprüngliche verlorene Freigabe aus #948
bleibt historisch UNKNOWN; heutige Regressionen rekonstruieren sie nicht.

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

Slices enthalten ihre Fachfunktion und Tests. Handler, Coordinator oder Gate
werden im Bootstrap über bestehende Ports/Buspfade verdrahtet; ein Verzeichnis
allein ist kein aktiver Command-Handler. Slices sind isoliert — kein Cross-Slice-Import.

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
| `provider_verification` | Requestgebundener Coordinator hinter `IProviderVerificationCoordinator`/`IProviderVerificationRecovery`; persistierter Dispatch, gleicher Request bei unbekanntem Ausgang, Evidence-Revalidierung und Recovery. Nur mit qualifiziert aktiviertem `execution.json`; shipped deaktiviert, keine allgemeine Runner- oder Sandboxplattform. |
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
| `session` | Prozesslokale Session-Token-/Zeitzähler und diagnostische Checkpoints (`resume_eligible=false`); nicht die persistente Workflow-Tokenauthority aus #549. |
| `sequence` | Event-Sequenz-Tracking + Muster-Analyse (warn/block/off) |
| `setup` | Verzeichnisse anlegen, Env-Var-Validierung, Label-Sync |
| `labels` | Workflow-Label-Transitionen; erfolgreicher Healing-PR räumt `status:failed` nur mit exakt passender Issue-/Korrelations-/Origin-Evidence auf |
| `watch` | Sequenzielles Issue-Polling mit einem prozesslokalen, per `try/finally` freigegebenen Slot |

Der historische [`Prompt-Contract-Audit`](PROMPT_CONTRACT_AUDIT.md) hält den
datierten Consumerabgleich vom 24.09.2026 fest. Aktuelle Promptauflösung,
Operator-Overrides und die Grenze der drei Library-Einträge ohne
Runtime-Consumer beschreibt die
[Prompt-/Operatoranleitung](agents/AGENT_PROMPTS_AND_INSTRUCTIONS.md).

---

### Kontext- und Sequenzbeobachtung

Der Context Builder begrenzt Skeleton-, Plan-, Keyword- und Symboltreffer;
der Context Validator prüft vorhandene Teile und geschätzte Größe. Harte
Findings blockieren, Warnungen nicht. Auswahl ist keine allgemeine
Secret- oder Berechtigungsgrenze. Der separate `ContextHandler` erzeugt nur
mit konfiguriertem Key ein `signature`-Feld; kein produktiver Folgeschritt
verifiziert diesen Context-HMAC als Sicherheitsschranke.

Der Sequence-Handler zeichnet Bus-Events auf. Erst ein expliziter Aufruf von
`validate_sequence` vergleicht die Reihenfolge; ausgelieferte Workflows rufen
ihn nicht als Freigabegate auf. Im warn-Modus entsteht kein Blockerevent.
Sein prozesslokaler Verlauf ist von persistentem Runtime-State zu unterscheiden.

### SCM-Labelstatus bei Evidence-Healing

Der produktiv verdrahtete Labels-Slice projiziert den abgeschlossenen,
gebundenen Ausführungsabschnitt aus dem Wiederanlaufjournal (#920). Er wartet
auf den synchronen Nachlauf; die Reihenfolge der einzelnen Subscriber erzeugt
keinen zusätzlichen Startstatus. Labels erteilen weder Planfreigabe noch
Wiederanlaufauthority.

| Belegter Ausgang | SCM-Projektion |
|---|---|
| Terminal `blocked` oder `aborted` | `status:failed`; Start-, aktive und irreführende Erfolgslabels entfernen. `help wanted` bezeichnet die notwendige ausdrückliche Operatorentscheidung über den beendeten Versuch. |
| Einzelner `GateFailed` innerhalb des laufenden Versuchs | Noch kein terminales Fehlerlabel; der vorhandene Healingpfad und sein Budget entscheiden den weiteren Verlauf. |
| Gebundener Healing-PR | Issue, Korrelation und `healing_origin_observation_key` müssen zum beobachteten Healing-Start passen; der aktuelle PR-Head und der dauerhafte Create-PR-Intent müssen denselben Candidate belegen. Danach `status:wip` und `needs-review`. |
| Plan wartet auf menschliche Freigabe | `status:plan`; kein pauschales `failed` oder `help wanted`. Eine bereits vorhandene menschliche Freigabe wird nicht vom Bot neu erzeugt. |
| MANUAL Acceptance wartet | `status:wip` und `in-progress`; vorhandene Freigabe bleibt erhalten. MANUAL-Receipts und die bisherigen Fortsetzungsprüfungen bleiben erforderlich. |
| PR wartet auf Review / Review abgeschlossen / Merge bestätigt | `needs-review` plus `status:wip` / nur `status:wip` / `status:done`, jeweils mit aktueller PR-/Candidatebindung. |
| Impliziter Replan abgelehnt | Gültiger Plan, Approval und Labels bleiben unverändert. |

Watch prüft vor dem Dispatch zusätzlich Journal, aktuellen Plan und aktuelle
Labels. Ein verbliebenes `ready-for-agent` nach einem Schreibfehler startet
keinen beendeten Versuch erneut. Widersprüchliche Statuslabels werden im
produktiven Pfad nicht nach einer Statusrangfolge bereinigt; der Scan meldet
`admission_blocked`. Auch eine erneut zugestellte native Planfreigabe startet
einen bereits begonnenen Implementationsabschnitt nicht nochmals.

Fremde oder unbestätigte Issue-/Repository-/Korrelations-/Plan-/Candidatebindung
führt zu keiner Labelmutation. Identische Planpublikationsduplikate ergeben
dieselbe Projektion; widersprüchliche Kommentar-IDs bleiben unbestätigt.
Außerhalb einer aktuellen Ausführung ist nur
der unabhängig am nativen PR und seinem dauerhaften Intent bestätigte Merge
projizierbar. Risiko-, Fachgebiets- und Ownershiplabels bleiben erhalten.
Ein vorhandenes `help wanted` wird konservativ erhalten: Ohne Beleg, welcher
Handlungsbedarf damit verbunden war und ob er erledigt ist, entfernt die
Automation es auch bei einer Neuplanung nicht. Der Operator kann es nach
Prüfung des zugehörigen Bedarfs entfernen.

Label- und terminale Kommentarversuche erhalten create-only Belege im
vorhandenen Authority-State; sie erteilen keine Workflowauthority. Der
SCM-Zustand wird nach dem Schreiben zurückgelesen. Ein Teilausfall oder eine
unklare Antwort bleibt `unconfirmed`, ohne automatische Schreibwiederholung.
Die Dispatchsperre hängt am Wiederanlaufjournal, nicht am Erfolg dieser
Projektion. Der terminale Kommentar nennt den Versuch, belegte Bindungen,
redigierten Grund, beobachtetes Healing und den bestehenden Dashboardweg zur
Operatorentscheidung. Normales Warten erzeugt keinen solchen Fehlerkommentar;
fehlende Ursachen bleiben `UNKNOWN`. Derselbe Core-Formatter wie in der
Problemtabelle ergänzt konkrete Prüf-/Behebungsschritte (#890). Bekannte
Gatekennungen aus dem gebundenen Lauf liefern zusätzliche Hinweise im selben
Kommentar; rohe Gate-/Providerantworten werden dafür nicht übernommen.
Korrelation wird ausdrücklich nicht als Kausalität ausgegeben. Eine echte
native Installations-/Liveabnahme erfolgt gesammelt in
#962/#994; Komponenten- und Integrationsregressionen ersetzen sie nicht.

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
| `adapters/audit/` | `IAuditSink` | `JSONLAuditSink` (Eventtranskript, mit konfiguriertem Key HMAC-Chain), `AsyncAuditSink`, `SARIFAuditSink` (nur Findings) und `FanOutAuditSink` (sequenziell aufgerufene Sinks; Fehler eines Sinks stoppen die übrigen nicht). Queueannahme ist keine Durabilityzusage. |
| `adapters/auth/` | `IAuthProvider`; lokaler Service verwendet `IIdentityStateStore` | `StaticTokenAuth` für SCM; `LocalIdentityService` für lokale Dashboardbenutzer, Sessions, CSRF, Reauthentisierung und Automation-Token. HTTP-Auswahl/Permissions liegen in `adapters/api/auth.py`. |
| `adapters/git_transport/` | `IGitTransportAuth` | repository- und operationsgebundene HTTP-Authentisierung über installierten Askpass-Helper; keine Credential-Plattform |
| `adapters/git_compare.py` | gemeinsamer SCM-Helfer für `RevisionComparison`/Blobread | Exakte lokal verfügbare Commit-IDs, bounded Git-Ausgabe/Timeout und UTF-8-Prüfung; Ressourcen-/Revisionsfehler sind nicht bestanden. Kein zweiter Compare-Resolver oder mutable Working-Tree-Evidence. |
| `adapters/git_publication.py` | gemeinsamer Git-Publikationshelper | Validierter Projektionseingang, Marker, Content-Digest und normaler Push/Readback; von Wiki und Documentation-Inventory wiederverwendet (§24). Kein Release- oder Gate-PASS. |
| `adapters/gitea/` | `IVersionControl`, `ISCMCheckEvidenceReader`, `IExecutionProvider` | Issue/Comment/PR/Label/Branch, begrenzter Pull-only-Actions-Check-Read sowie der deaktiviert ausgelieferte requestgebundene Gitea-Actions-Referenzprovider |
| `adapters/github/` | `IVersionControl` | GitHub-/Enterprise-SCM. `GitHubAppAuth` (RS256) ist vorhanden, aber kein über Bootstrap/Setup aktivierter Authentisierungsmodus; das normale SCM-Wiring verwendet statisches Token. |
| `adapters/llm/` | `ILLMProvider` | 8 Provider (siehe §8) + `FixedResponseAdapter` (deterministisch, fuer reproduzierbare E2E-Runs, #368) |
| `adapters/notifications/` | `INotificationSink` | Slack, Teams, Generic Webhook |
| `adapters/quality/` | `IQualityCheck` | Bestehende Registry mit `PythonSyntaxCheck`, `TreeSitterTypeScriptCheck`, `ScopeGuard` und `DiffSizeCheck` über `config/hooks.json`; kein Pylint-/Mypy-/Ruff-Subprozess. Fehlender optionaler tree-sitter meldet `not_applicable`. Der File-EWMA-Adapter bleibt ein Legacyformat. |
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
                    │ Sanitizer        │ — HTML/Länge, optional begrenzte PII
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
| `openrouter.py` | OpenRouter | API-Key | Gatewaymodellkatalog, Balance-Abruf; Verfügbarkeit konten-/zeitabhängig |
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

**HISTORICAL / AUDIT_EVIDENCE — #701, a15-Referenzkombination.**
Der folgende Providerbefund ist ein früherer Einzelbeleg und kein heutiger
Verfügbarkeits-, Modell- oder Qualificationstatus.
Die damalige isolierte D0-Evidence belegt Ollama in beiden Richtungen:
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
führt 7b, 7, 8, 9, 13a und 13b sowie anschließend die externen statischen Gates
vor jeder lokalen oder externen Candidate-Verifikation aus. Blockiert ein
Required-Preflight, werden nur noch nicht ausgeführte nachgelagerte Gates
vollständig als SKIP in das eine terminale Event aufgenommen. Optionales
Preflight-Evidence blockiert weiterhin nicht. Gate 7 übernimmt bei fehlendem
`path_risk.json` den statischen Pfadschutz-Fallback bereits im Preflight; es
wird in der nachgelagerten Gatephase nicht erneut ausgeführt.

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
| 6 | `gate_6_self_consistency` | Mindestens die Hälfte extrahierter Plan-Basenames ist im Diff | Optional |
| 7 | `gate_7_scope_guard` / `ForbiddenPathGuard` | Verbotene Fallback-Pfade; delegiert bei PathRisk und prüft keinen Contract-Scope | Required |
| 7b | `gate_7b_contract_scope` / `ContractScope` | Vollständige Changed-Files gegen Contract-Scope Schema 2; optionale Ergänzungen nur aus `architecture.json`, fehlende/stale Evidence blockiert | Required |
| 8 | `gate_8_slice_gate` | Neu hinzugefügte Python-`from samuel.slices.X import`-Zeilen zwischen Slices | Required |
| 9 | `gate_9_python_syntax` | CPython-AST des exakten Candidate-Blobs; Nicht-Python/Löschung = `not_applicable`, Missing/Fehler = Fail | Required |
| 11 | `gate_11_ac_verification` | Alle Required-ACs mit strukturierter Evidence für exakt Contract/Head/Policy bestanden | Required |
| 12 | `gate_12_ready_to_close` / `AcceptanceReadiness` | Vollständigkeitsstatus derselben Evidence; keine eigene Verifikation | Optional |
| 13a | `gate_13a_branch_freshness` | Head höchstens 50 Commits hinter gebundener Base; nicht prüfbar = fail | Optional |
| 13b | `gate_13b_destructive_diff` | Block nur bei >50 Löschungen und zugleich >3× Hinzufügungen | Required |

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
Vor dem Providerkontakt liest der Review den Originalvergleich über den
vorhandenen SCM-Port aus genau diesen unveränderlichen Base-/Head-Commits.
Repository, Revisionen und angelieferte Diffbytes müssen mit diesem Original
übereinstimmen. `PRCreated.diff_reference` bindet zusätzlich Originaltyp,
Subjectdigest, Diffdigest und Workflowkorrelation; eine Referenz aus einem
anderen Attempt oder ein als Evidence ausgewiesener Input wird abgewiesen.
Direkte Aufrufer ohne diese Zusatzreferenz benötigen ebenfalls einen lesbaren
gebundenen Git-Originalvergleich und exakt gleiche Bytes. Ein Dateiname oder
ein selbst deklarierter Digest ersetzt die Originalquelle nicht.

Fehlt das Original, lautet die begrenzte Diagnose `original_input_missing`;
eine ausgewiesene oder nachweisbar bereinigte Projektion erzeugt
`redacted_projection_not_allowed`, andere abweichende Bytes oder Digests
`artifact_digest_mismatch`, fremde Bindungen `wrong_subject`. Diese Fälle
erzeugen `ReviewBlocked` ohne LLM-Aufruf und behalten ausschließlich
berechnete Original-/Eingabedigests, keine Rohpayloads oder Exceptiontexte.
Ein bereits leerer angelieferter Diff bleibt `review_diff_missing`. Für den
Originalvergleich gilt dasselbe konfigurierte `max_diff_bytes`-Limit wie
für die PR-Gates; ein größeres Eingabelimit wird nicht aus einem Report übernommen.
Vorhandene bereinigte Audit-, Run-, DLQ- und Screenshotansichten bleiben
Erklärungs-/Diagnoseevidence, kein Ersatzinput für Replay oder Reconcile.
Ein tatsächlich im Git-Original enthaltenes Wort wie `REDACTED` ist kein
Ablehnungsgrund. Die bestehende Prompt-/PII-Bereinigung erfolgt weiterhin
nach der Originalprüfung; sie ist von der Nutzung eines bereinigten
Ersatzartefakts zu unterscheiden (#883).

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
Der äußere Pattern-Delimiter darf doppelt, einfach oder genau eine vollständige
Markdown-Inline-Code-Hülle sein. Damit kann ein literales Pattern auch beide
Anführungszeichenarten enthalten. Backslash-Escapes für den äußeren Delimiter
gehören nicht zur Grammatik. Ist keine eindeutige Hülle möglich oder Verhalten
dateigebunden, wird ein fokussierter `[TEST]` verwendet.

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

### Auswahl automatischer und manueller Kriterien (#880)

Der Paketprompt `planner.md` und `_build_plan_prompt()` leiten Erstplan und
vorhandenen Retry zur Auswahl geeigneter Prüftypen an: deterministisch
prüfbare Eigenschaften automatisch, Verhalten mit `[TEST]`. Fehlende Tests,
Toolchain oder Ausführungszugänge allein rechtfertigen kein `[MANUAL]`.
Nötige Tests gehören in den autorisierten Scope; fehlende Voraussetzungen
oder unklare Prüfbarkeit müssen benannt werden.

MANUAL bleibt für tatsächlich menschliche fachliche/gestalterische
Entscheidungen oder ausdrücklich verlangte Zustimmung. Jede neue
MANUAL-Kriteriumszeile soll die konkrete menschliche Beurteilung und den Grund
nennen, warum automatische Evidence nicht genügt, zum Beispiel:

```text
- [ ] [MANUAL] Fachliche Verständlichkeit der Fehlermeldung beurteilen — Begründung: Automatische Tests prüfen Inhalt und Auslösebedingung, die fachliche Zustimmung gibt der Betreiber.
```

Die automatisch prüfbare Auslösebedingung gehört in ein eigenes `[TEST]`;
erfolgreiche automatische Tests werden nicht zusätzlich manuell bestätigt.
Der Planner soll vor seiner Ausgabe Prüftypen und MANUAL-Begründungen prüfen.
Die [Prüfanleitung zur Planfreigabe](DASHBOARD.md#automatische-und-manuelle-kriterien-im-plan-prüfen-880)
beschreibt den menschlichen Kontrollschritt.

Die Begründung bleibt normaler Kriteriumstext: Änderungen verändern bereits
AC-ID und Contract-Hash. Schema, Store, Receipt-Syntax, Actor-/Head-Bindung,
Planfreigabe und Wiederaufnahme bleiben unverändert. Ältere MANUAL-Kriterien
ohne Begründung sind weiterhin formal gültig; aktive Verträge werden nur über
explizites Replanning ersetzt. Es gibt keine automatische Umklassifizierung,
neue semantische Validator-Schranke, zusätzliche LLM-Stufe oder Startsperre.
Die Anleitung garantiert keine richtige Modellentscheidung; eigene
Systemprompt-Overrides bleiben erhalten. Die gebündelte Live-/Modell- und
Transportabnahme in #962/#994 wird durch Prompt-/Regressionstests nicht ersetzt.

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
Die optionale `eval.json::verifier_toolchain`-Bindung nennt einen absoluten
Manifestpfad und dessen SHA-256. Der offizielle OCI-Installer bereitet die
Python/Pytest-Pakete aus einem geprüften Hashlock offline vor und registriert
den read-only Mount. Der Resolver prüft Paket-/Lockbytes und
Python-/Plattform-/Releaseidentität bei Doctor, Planning und TEST; die
Toolchainversionprobe läuft außerhalb des Candidates in steriler Umgebung.
Der Digest ergänzt die bestehende Gate-Policy-/Resume-Bindung; ohne diese
Option ändert sich die bisherige Runnerauflösung nicht. Gate 11 führt keine
zweite Testsuite aus. Vollständige Operatoraufrufe stehen in
[INSTALL.md](INSTALL.md#oci-pythonpytest-toolchain-und-separater-doctor-prüfer-978).

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

### Konkrete Verifier- und Attributionsbeispiele

Ein Pytest-Kriterium kann `tests/test_x.py::test_y[param]` adressieren, sofern
auch tatsächlich ein Pytest-Runner aufgelöst wurde. `[MANUAL]` bleibt ohne
passenden menschlichen Nachweis `passed: null` / `status: manual_pending`;
Checkboxen erbringen diesen Nachweis nicht. Details stehen in Abschnitt 10.

Die optionale Codeattribution verwendet Inline-Marker wie
`# llm: <modell> <datum>` und einen `Co-Authored-By`-Trailer. Die Auditspur mit
`AI-Generated-By` und `LLMCallCompleted` bleibt davon getrennt. Konfiguration
und die bestehende `high_risk`-Sperre beschreibt die
[AI-Act-Dokumentation](AI_ACT_COMPLIANCE.md). Diese Marker sind technische
Attribution, kein regulatorischer Konformitätsnachweis.

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

Routing- und Promptwrites benötigen `WRITE_CONFIGURATION` und einen expliziten
Setup-Prozess. `legacy_api_key` verwendet den vorhandenen Key; `local_identity`
verwendet die implementierten unabhängigen Rollen, Sessions/CSRF oder explizite
Automation-Permissions. Die Handler validieren Provider, Felder, Zeitfenster,
Pfade, Scopes und Inhalte zusätzlich. #422 ist implementiert und administrativ
geschlossen; seine weiteren realen Identity-Abnahmen bleiben in #962.

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
werden aus `config/audit.json` gebaut; bei mehreren verbindet `FanOutAuditSink` die
Sinks. Zusaetzlich (#368) der `SARIFAuditSink`: exportiert **nur Findings**
(Events mit `owasp_risk`) ins SARIF-2.1.0-Format (`data/logs/findings.sarif`,
Beispiel `docs/examples/findings.sarif`) — das JSONL bleibt das Volltranskript.
Findings-Volumen pro Typ/Issue: `get_finding_stats` (FP-Raten-Grundlage).

### Audit-Schreibdiagnose (#986)

`AsyncAuditSink` projiziert abgeschlossene JSONL-Schreibversuche direkt in den
vorhandenen `run_projections`-Store (`health-readiness.v1`, Kind `audit_writer`).
Die Diagnose läuft außerhalb des Eventbusses, damit der fehlerhafte Auditsink
seinen eigenen Fehler nicht rekursiv auditiert. Pro konfiguriertem JSONL-Ziel
existiert eine über den normalisierten Pfaddigest gebundene, begrenzte
Projektion. Primär- und Ersatzpfad melden ausschließlich feste Fehlercodes,
Prozess-/Stateinstanz, Zeit, Digest und Zähler; keine Pfade, Schlüssel oder
Ereignispayloads. Atomarer Compare-and-swap über den vorhandenen Port und
SQLite-Transaktionen erhält Zähler auch bei konkurrierenden Prozessen.

| Anzeige | Bedeutung |
|---|---|
| `written` | Letzter beobachteter Primärappend erfolgreich; keine Aussage über dauerhafte Verfügbarkeit, Kettenintegrität oder vollständige Historie. |
| `degraded` | Primärpfad gestört oder Queue voll, zugehöriger Ersatzappend erfolgreich. Die Ersatzkette bleibt separat zu prüfen. |
| `loss_detected` | Mindestens ein Ereignis bei beiden Schreibpfaden, normalem Queueüberlauf oder nach Sink-Shutdown verloren. Der Zähler bleibt auch nach späterem Primärerfolg erhalten. |
| `unknown` / einzelne `stale`-Quelle | Noch kein bestätigter Write, Neustart nach Erfolg, Projektion nicht verfügbar, andere Stateinstanz oder mehr als eine Stunde alte Beobachtung. Historischer Befund bleibt im Einzelwert sichtbar. |

Ein Start ersetzt keinen ungelösten Primärfehler durch Erfolg. Erst ein realer
Primärappend löst die Primärdegradation auf und bindet den vorherigen Befund;
verlorene Ereignisse werden damit nicht repariert. Ein nicht bestätigter Drain
beim Shutdown wird gesondert gezählt, ohne daraus belegten Ereignisverlust zu
erfinden. SARIF-Erfolg löst keine JSONL-Diagnose auf.

CLI `health`, passiver Dashboard-Health-/Viewerabruf und aktiver Self-Check
zeigen denselben zuständigen Storezustand. Status und Self-Check besitzen eine
eigene Audit-Schreibpfadanzeige. `healthy`, Health-Exitcodes, Required-Gates,
Workflow-Readiness und Doctor-/Audit-Qualification bleiben unverändert. GETs
schreiben keine Probeereignisse und kontaktieren keine Provider. Bei einem
Projektionsschreibfehler meldet der zuständige Prozess `unknown`; andere
Prozesse können ohne persistierbare Diagnose nur die letzte Beobachtung samt
Zeitgrenze sehen. Prozesslogging bleibt der zusätzliche Fehlerweg, kein zweiter
Diagnosespeicher. `audit verify` prüft weiter ausschließlich Kettenintegrität.

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
Contract sowie den passenden Planumfang als Kriteriencheckliste in Planreihenfolge.
Nur ein gespeicherter PASS des exakten Issues, EvaluationSubject, Contracts und
Plan-Kommentars setzt die jeweilige Checkbox. Fehlende, fremde, mehrdeutige oder
beschädigte Evidence bleibt UNKNOWN; Fehler und offene MANUAL-Kriterien werden
ungeprüft mit ihrem Status angezeigt. Der Merge selbst ist kein Kriteriennachweis.
Der ursprüngliche Plan bleibt unverändert. Issue-Schließung bleibt getrennt.
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
registriert; ihre reale Rollout-Abnahme wurde aus #668 nach #962 übertragen.

Alle ausgelieferten Kategorien stehen weiterhin auf `report_only`; es gibt
keinen Scheduler und keine produktive Löschaktivierung. Die CLI-Aktionen
`approve`, `activate`, `suspend`, `pause`, `unpause` und `execute` sind
begründungspflichtige Operatoraktionen. Der synthetische Canary belegt nur die
Mechanik. #668 ist administrativ geschlossen; seine reale erste
Kategorieabnahme bleibt in #962 offen, bis tatsächlich
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

`samuel.cli` dispatcht einen Subcommand. Diagnose-/Operatorwege wie `setup`,
`doctor`, `state`, `identity`, `retention` und `workspace` besitzen eigene
Einstiege vor dem normalen Workflow-Bootstrap; Workflowbefehle bauen den Bus.
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
| `doctor` | Diagnose mit Fix-Hinweisen: normalisierte Produktversion, getrennte vollständige Build-Revision/Dirty-State, SCM-Konfig + Live-Verbindung, bei Gitea/GitHub Wert und Quelle des Soll-Required-Checks sowie fail-closed exakter Abgleich mit der nativen Release-Branch-Regel, LLM-Provider, Sicherheits-Keys, Verzeichnisse, Default-Configs, PROJECT_ROOT sowie TEST-Runner-/Toolchain-Readiness aus derselben Auflösung wie Planning und Gate 11. Der Dashboard-Schlüsseleintrag prüft nur Präsenz, keine Anmeldung oder Permissions; ein fehlender Legacy-Key bedeutet Startverweigerung, keine ungeschützte API. Ein leerer Sollwert, fehlendes Leserecht oder eine Abweichung ergeben Exit 1; beobachteter SCM-Zustand wird nie zum Sollwert. Das Ergebnis wird ohne Detail-/Secretpayload instanzgebunden für die passive Qualification projiziert. | `--branch-protection-token-file <file>` (nur Branchschutz-GET, geschützte temporäre Datei); `--webhook` (informativer Hook-Metadaten-GET mit Runtimecredential) |
| `install-service` | systemd-Unit mit echten Pfaden/User/installiertem Console-Script generieren (ersetzt die Platzhalter-`samuel.service`). | `--mode watch\|dashboard`, `--write` (nach `/etc/systemd/system/`), `--user`, `--name` |
| `health` | Aktiver technischer Check (Python, Git-Runtime, Config, State/Authority, SCM, effektive LLM-Taskrouten) mit unverändertem Exitvertrag. Sein Bootstrap startet kein Auto-Resume und übernimmt keine Run-Workspaces. Die Ausgabe trennt `technical_health`, zweckgebundene `operational_readiness` und Doctor-/Audit-`qualification`. Externe LLM-Erreichbarkeit wird nicht live behauptet und ergibt deshalb Readiness `unknown`; State/Config/Authority bleiben kritisch. | – |
| `run <issue>` | `IssueReady`-Event fuer Issue publizieren (durchlaeuft den aktiven Workflow); ein zum Aufruf korrelierter `PlanBlocked` oder `PlanReplanRejected` ergibt Exit 1, ein erfolgreicher Dispatch Exit 0; autorisiert außerdem ausdrücklich eine neue Klärungsserie nach Timeout, Rundenerschöpfung oder Source-Supersession | `--workflow <name>` (Override) |
| `replan <issue>` | Aktiven Plan und seine Freigabe nachvollziehbar widerrufen, danach einen neuen Plan mit neuer Freigaberunde erzeugen | `--reason <text>` (Pflicht), `--workflow <name>` |
| `recovery inspect\|end\|replan\|resume <issue>` | Aktuellen Versuch prüfen, explizit beenden, neu planen oder vorhandene technische Checkpoints fortsetzen | `--version <version>` aus inspect für Mutationen; `--reason <text>` für end/replan |
| `watch` | Polling-Loop, scannt nach Issues mit Workflow-Label | `--once`, `--interval <s>` |
| `dashboard` | HTTP-Server mit Web-Dashboard und REST-API; Operator-Konfiguration ist standardmäßig eingefroren | `--host`, `--port` (Default 7777), `--configuration-mode production\|setup` (Default `production`) |
| `setup-labels` | Workflow-/Risk-/Scope-Labels auf dem SCM anlegen (idempotent, liest `config/labels.json`) | – |
| `refresh-pricing` | vorhandenen Modell-/Benchmark-/Preiscache aktualisieren; keine Liveeignungs- oder Routingfreigabe | – |
| `replay` | Audit lesen und Snapshot/Timeline ausgeben; `--publish` publiziert ausschließlich auf einen frischen No-op-Bus ohne Produkthandler. DLQ-Replay ist davon getrennt | `--issue <n>`, `--run <correlation-id>`, `--publish` |
| `audit` | HMAC-Chain des Audit-Logs auf Manipulationen pruefen | `verify` |
| `dlq` | Fehlgeschlagene Events auflisten oder erneut publizieren | `list`, `replay <id>`, `--limit <n>` |
| `changelog` | Markdown-Delta aus git log erzeugen (`feat`/`fix`/`refactor`/...-Commits mit `(#NNN)`-Ref). Default-Start ist der höchste erreichbare kanonische Produkt-Tag; Phasenmarker zählen nur mit explizitem `--phase`. | `--since <rev>`, `--phase <n>` (mappt auf `phase-n-complete`), `--post-to-issue <n>` (Kommentar in Gitea-Issue), `--out <delta-file>` |
| `state` | SQLite-State vor dem normalen Bootstrap diagnostizieren, einen Claim aufgeben oder den unterstützten Restore/Reconcile bedienen; Ausgabe enthält Schema/Mount/Pragmas/Tabellen oder nur Zähler, niemals gespeicherte Payloads. | `status`, `dump`, `abandon-healing`, `restore`, `reconcile-status\|scan\|classify\|complete`, `--json` |
| `identity` | Lokalen Dashboard-Identity-State ohne Provider-/Workflow-Bootstrap diagnostizieren, ersten Administrator initialisieren, den Legacy-Cutover atomar ausführen oder nach Restore lokal recovern. Passwörter kommen ausschließlich aus einer eigentümergebundenen Datei mit Modus 0600 oder strenger. | `status`, `bootstrap`, `cutover`, `recover`, `--username`, `--password-file`, `--reason`, `--client-inventory-confirmed`, `--json` |
| `retention` | Katalog ohne normalen Bootstrap prüfen, Kategorie-Autorität explizit steuern, einen exakt gebundenen allowlist-basierten Plan ausführen, ein SQLite-konsistentes Managed Backup erzeugen oder Scoreableitungen event-/EWMA-frei wiederholen. Ausgeliefert ist keine Kategorie aktiv und es existiert kein Scheduler. | `dry-run`, `approve`, `activate`, `suspend`, `pause`, `unpause`, `execute`, `backup`, `replay-scores`, `--category`, `--plan-digest`, `--cutoff-utc`, `--reason`, `--json` |
| `evidence` | Einen explizit benannten vorhandenen Gitea-Actions-Run begrenzt lesen, gegen ein `EvaluationSubject` bewerten und als unveränderliche Advisory-Observation speichern. Startet keinen Run und besitzt keine Gate-/Dispatch-/Mutationswirkung. | `assess`, `--run-id`, `--attempt`, `--subject`, `--workflow`, `--event`, `--max-age-seconds`, `--issue`, `--json` |
| `candidate` | Einen bestehenden vollständigen Git-Head dem aktiven, menschlich freigegebenen Plan zuordnen. `submit` liest nur vorhandene Evidence. `request` autorisiert oder reconciliiert den gebundenen Providerauftrag; nur `--new-request` erzeugt bewusst eine neue Requestidentität. Beide passiven Varianten erstellen keinen PR und besitzen keine Implementierungs-/Healingwirkung. Exit 0 = gebundener passiver Erfolg, 1 = terminal abgelehnt/fehlgeschlagen, 2 = Provider-Evidence ausstehend. | `submit\|request <issue>`, `--head <full-sha>`, `--new-request` nur mit `request`, `--json` |
| `resume` | Gebundene Finalisierungs-Checkpoints mit `list`/`inspect` ohne Bootstrap lesen; gezielt/gesamt fortsetzen oder nach Operatorprüfung aufgeben und bereinigen weiterhin über den normalen Bootstrap. `attempt` und `resume` sind Aliases. | `list`, `inspect <key>`, `attempt\|resume [<key>]`, `abandon <key> --reason <text>`, `cleanup <key> --reason <text>`, `--json` |
| `workspace` | Gemeinsame Worktree-Registry ohne SCM-/LLM-/Workflow-Bootstrap inspizieren, terminale Einträge bereinigen, aktive Einträge begründet quarantänisieren oder bereits geprüfte Quarantäne-Evidence explizit verwerfen. | `list`, `inspect <id>`, `prune`, `quarantine <id> --reason <text>`, `discard <id> --reason <text>`, `--json` |

### Argumente, Voraussetzungen und Ergebnisgrenzen

`samuel <command> --help` zeigt die Syntax des installierten Stands; `-h` und
`--help` beenden die Argumentauswertung ohne Commandausführung. Fehlender
Command, unbekannte Option, fehlendes Parser-Pflichtargument oder ungültiger
`choices`-Wert ergibt Exit 2. Ein fachlicher Fehler nach erfolgreichem Parsen
ist davon getrennt. Die CLI erbt lokale Prozess-/Dateirechte und konfigurierte
Providercredentials; Dashboardrollen sind keine zusätzliche lokale CLI-ACL.

`--config` und `--log-level` stehen vor dem Command. Nur `run` akzeptiert
zusätzlich `--self` und `--allow-non-main` auch hinter dem Command. Beispiel:
`samuel --config /etc/samuel/config dashboard --port 7777`. Ein erfolgreiches
`run` oder HTTP-Dispatch belegt keinen fertigen PR oder Human Merge.

| Command / Argumente | Default, Voraussetzung und tatsächliche Wirkung |
|---|---|
| `watch --interval <s> --once` | Parserdefault 60 Sekunden; `agent.auto.poll_interval` ersetzt ihn. Ein CLI-Wert ungleich 60 überschreibt die Config. Auch ausdrücklich `--interval 60` lässt daher den Configwert gelten. `--once` macht genau einen Scan; der [Watch-Exitvertrag](#watch-exitvertrag) unterscheidet Dispatchfehler von erfolgreich beendetem Scan. |
| `run <issue> --workflow <name>` | Ganzzahlige Issue-ID; Workflowwahl nach [Reihenfolge](#workflow-wahl-reihenfolge). Normaler Run benötigt ein erreichbares Git-Zielprojekt; `--self` wählt den Produktcheckout. `--allow-non-main` lockert nur den lokalen Self-Branchcheck, keine Plan-/Review-/Mergeauthority. |
| `replan <issue> --reason <text> --workflow <name>` | Issue und Begründung erforderlich; vorhandene Freigabe wird widerrufen und gilt nicht für den Ersatzplan. Nach R25 benötigt jeder Ersatzplan ein neues menschliches Freigabeereignis nach seiner Veröffentlichung; die unten beschriebene Durchsetzungsgrenze beachten. Workflowoverride optional. |
| `dashboard --host <host> --port <n>` | Expliziter nichtleerer Host bzw. nichtnull Port vor `DASHBOARD_HOST`/`DASHBOARD_PORT`, sonst `0.0.0.0:7777`; ungültiger Environmentport fällt auf 7777 zurück. Wildcardbindung ist keine Browserzieladresse. |
| `dashboard --configuration-mode production\|setup` | CLI vor `SAMUEL_CONFIGURATION_MODE`, sonst `production`. Ein eigener Setup-Prozess macht keinen bereits laufenden Produktionsprozess schreibbar; [Konfigurationsmodus](#operator-konfigurationsmodus) beachten. |
| `setup --non-interactive` | Ohne Flag interaktiv; mit Flag bestehende Env-/`.env`-Werte verwenden. Schreibt Konfiguration und synchronisiert Labels, ist keine reine Probe; [Setupvertrag](INSTALL.md#4-konfiguration-via-wizard--samuel-setup). |
| `doctor --branch-protection-token-file <file>` | Ohne Datei vorhandene Runtimecredentials; die optionale geschützte Datei liefert ausschließlich den Branchschutz-GET-Prüfer. Keine persistente Credentialumstellung. Exit 1 bei fehlender Voraussetzung/negativer Diagnose; ein positiver Check qualifiziert keinen Workflow. |
| `install-service --mode watch\|dashboard --user <user> --name <name> --write` | Defaultmodus `watch`, Benutzer aus aktueller Umgebung, Name `samuel-<mode>`. Ohne `--write` Unittext ausgeben; mit Flag nach `/etc/systemd/system/<name>.service` schreiben, mit erforderlichen lokalen Rechten. Kein implizites Starten/Freigeben der Unit. |
| `health`, `setup-labels`, `refresh-pricing` | Keine eigenen Optionen. Aktive technische Diagnose, SCM-Labelmutation und Cache-/Netzaktualisierung sind drei verschiedene Wirkungen; Credentials/Netz je Consumer nötig. |
| `replay --issue <n> --run <correlation-id> --publish` | Issue erforderlich, Runfilter optional. Liest Audit und gibt Snapshot/Timeline aus; ohne Events ebenfalls Exit 0. `--publish` benutzt einen **frischen Bus ohne Produkthandler**. Es führt keine gespeicherten Commits/PRs erneut aus. Der normale CLI-Bootstrap bleibt davon getrennt. |
| `audit verify` | Prüft die bestehende Auditkette mit ihrem zugehörigen HMAC-Key. Ergebnis und Evidence-Stufe nach [Auditvertrag](#14-audit-trail); keine Neusignierung oder Reparatur. |
| `dlq list --limit <n>`, `dlq replay <id>` | Listenlimit default 50; Replay benötigt eine vorhandene Entry-ID und publiziert auf den aktiven Bus. Anders als Audit-`replay --publish` kann es Subscriberwirkungen auslösen. |
| `changelog --since <rev> --phase <n> --post-to-issue <n> --out <file>` | Explizites `--phase` hat Vorrang vor `--since`; andernfalls höchster erreichbarer Produkt-Tag. Ohne `--out` Ausgabe auf stdout; Issueoption schreibt zusätzlich einen SCM-Kommentar. Keine Produktrelease- oder Tagfreigabe. |
| `candidate submit\|request <issue> --head <full-sha> --new-request --json` | Issue und vollständiger Head erforderlich, aktiver genehmigter Plan muss passen. `--new-request` nur mit `request`; es erzeugt ausdrücklich eine neue Requestidentität statt vorhandene Evidence erneut zuzuordnen. Exit 0 passiver Erfolg, 1 Ablehnung/Fehler, 2 Verifikation ausstehend. |
| `evidence assess --run-id <n> --subject <file>` | Beide Optionen erforderlich; Subjectdatei enthält `EvaluationSubject`. `--attempt` default 1, `--max-age-seconds` 86400, `--issue` 0 (keine zusätzliche Issuezuordnung); `--workflow` und `--event` sind optionale erwartete Providerwerte, `--json` wählt Ausgabe. Liest einen bestehenden Run und persistiert advisory Observation; kein neuer Actions-Run und kein Gate-PASS. |

**Replan und neue menschliche Freigabe.** Der produktive CLI-Replan delegiert
an denselben geprüften Wiederanlauf wie das Dashboard. Die explizite Aktion
widerruft den bisherigen Plan, erzeugt eine neue Versuchskorrelation und bindet
den Ersatzplan an einen eigenen Branch. `WorkflowRecovery` erzwingt für diesen
Plan eine neue dauerhafte menschliche Approval; `PlanValidated` ist hier keine
Freigabe. Der Planner zeigt `human_pending` auch bei autonomen Profilen. Deren
Workflowengine nimmt die tatsächliche neue `PlanApproved`-Entscheidung über
denselben bestehenden Implementierungsconsumer an. Vor dem ersten neuen
Implementierungsaufruf wird die persistierte Approval erneut gegen die
SCM-Quelle geprüft. Der frühere Komponentenbefund einer policyfreigegebenen
Ersatzplanung ist für diesen produktiven Pfad durch #920 behoben; daraus folgt
kein Live-/Golden-Nachweis.

Die folgenden Aktionsgruppen akzeptieren `--json` für strukturierte Ausgabe.
Bei `state`, `workspace`, `resume` und `retention` stehen Aktion und `ok` im
Envelope; Fehler enthalten `error.code`/`error.message`. Ein Exit 0 kann eine
erfolgreiche Diagnose mit offenem Reconcilebedarf bedeuten. Deshalb Fachstatus
lesen, nicht nur den Prozesscode. Ein blockierter Resumeversuch ergibt Exit 1.

| Aktionsgruppe | Aktionsbezogene Pflichtwerte und Grenzen |
|---|---|
| `state status`, `state dump`, `state reproject-runs` | Status/Schema/Zähler lesen beziehungsweise Runprojektionen rekonstruieren. Normaler Storezugang kann initialisieren/migrieren; kein Read-only-Versprechen. `dump` exportiert keine Rohpayloads. |
| `state abandon-healing` | `--observation-key` und nichtleeres `--reason` erforderlich; beendet den gebundenen Claim als `abandoned`. |
| `state restore` | `--source <backup>` erforderlich. `--supersede-operation-id` und `--reason` gehören zur ausdrücklich begründeten Ablösung einer Restoreoperation; bestehende Schema-/Digest-/Epoch-/Auditguards gelten. |
| `state reconcile-status\|reconcile-scan\|reconcile-complete` | `--operation-id` oder vorhandene aktive Restoreoperation nötig. Scan liest die tatsächlichen SCM-/Workspacequellen und benötigt deren Zugang; Complete hebt ungeklärte Einträge nicht still auf. |
| `state reconcile-classify` | Zusätzlich `--object-type`, `--object-key`, `--classification verified_effect\|verified_absent\|abandoned` und `--reason` erforderlich; Klassifikation nach gebundener Quellenprüfung, keine synthetische Humanentscheidung. |
| `identity status\|bootstrap\|cutover\|recover` | Status diagnostiziert. Bootstrap benötigt `--username`/`--password-file`; Cutover ausdrücklich `--client-inventory-confirmed` und `--reason`; Recovery folgt dem vorhandenen lokalen Recoveryvertrag mit Benutzer/Passwortdatei und Begründung. Passwortdatei eigentümergebunden, 0600 oder strenger. Details: [Identity/Cutover](INSTALL.md#44-lokale-dashboard-identitäten-und-cutover). |
| `retention dry-run`, `retention backup` | Inventur/Plan beziehungsweise konsistentes Managed Backup. Ausgelieferte Retention ist `report_only` mit globalem STOP; kein Scheduler. Backup umfasst nicht alle externen Stores und Git-Artefakte. |
| `retention approve\|suspend` | `--category` und fachlich erforderliche `--reason`; Kategorieautorität prüfen/ändern, noch kein Lösch-PASS. |
| `retention activate\|execute` | `--category`, exakter `--plan-digest`, `--cutoff-utc` als ISO-8601 mit Zeitzone und erforderliche Begründung. Plan/Policy/Grant müssen passen; Aktivierung und tatsächliches Execute bleiben getrennt. |
| `retention pause\|unpause` | Globalen STOP mit `--reason` steuern; Unpause erteilt keine neue Kategorie-/Objektfreigabe. |
| `retention replay-scores` | Optional `--issue <n>` filtert Observations; wiederholbares `--eval-config-dir <dir>` wählt Verzeichnisse mit `eval.json`, ohne Angabe gilt `--config`. Schreibt Ableitungen ohne erneute Events/EWMA-Wirkung, keine neue Bewertungsauthority. |
| `workspace list`, `workspace inspect <id>`, `workspace prune` | Registry diagnostizieren beziehungsweise terminale Einträge nach Managervertrag bereinigen. `inspect` verlangt vorhandene ID; `prune` ist eine Mutation. |
| `workspace quarantine\|discard <id> --reason <text>` | ID und Begründung erforderlich. Quarantäne erhält Evidence; Discard verwirft ausdrücklich geprüfte Quarantäne nach vorhandenem Managervertrag. |
| `resume list`, `resume inspect <key>` | Ohne Runtime-/Providerbootstrap vorhandene Bindungen lesen. `inspect` benötigt Key; fehlender/inkompatibler Store bleibt Fehler statt Ersatzanlage. |
| `resume attempt\|resume [<key>]` | Mit Key gezielt, ohne Key passende ausstehende Checkpoints prüfen; mutierender Bootstrapweg mit bestehenden Eligibility-/Authorityguards. |
| `resume abandon\|cleanup <key> --reason <text>` | Key und nichtleere Begründung erforderlich; Aufgeben und Bereinigung sind unterschiedliche Zustandsänderungen. Kein allgemeines LLM-Round-Resume. |

Beispiele und Betriebsgrenzen folgen unten sowie in der
[State-/Recoveryreferenz](STATE_STORE.md) und beim
[Workspacebetrieb](#gemeinsamer-worktree-manager-618). Leere optionale
Stringdefaults sind keine Freigabe; fehlende aktionsspezifische Werte werden
teilweise erst vom Fachhandler abgewiesen.

Die vorhandene Abschnittsbindung `technical-cli-reference` umfasst Parser,
Handler, installierte Entry Points und CLI-Regressionen. Bei neuen Commands,
Optionen oder geänderter Wirkung ist nach
[Documentation acceptance](../CONTRIBUTING.md#documentation-acceptance) auch
diese Erklärung im selben PR zu prüfen. Der Commit-Impact meldet neue
ungebundene Quellen und statische Argumenthinweise; dynamische Syntax,
Prioritäten, Rechte und Wirkungen bleiben source-aware Reviewaufgaben.


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

`resume list` und `inspect` lesen vorhandene `agent.json`-/State-/Workspace-
Bindungen ohne Runtime-Bootstrap. Sie benötigen keinen `PROJECT_ROOT`, keinen
lokalen Zielcheckout und keine SCM-/LLM-Credentials. Die vorhandene Datenbank
muss das aktuelle Schema haben; fehlender, beschädigter oder veralteter State
wird als maschinenlesbarer Fehler ausgegeben, weder angelegt noch migriert.
Witness-/Restore-Drift wird als Reconcilebedarf sichtbar, ohne Authority zu
reparieren. SQLite kann dabei seine WAL-Koordinationsdateien verwenden/anlegen;
Datenbankinhalte, Witness, Leases, Rechte und Config werden nicht geändert.
`inspect` zeigt Registryinformationen, keine erneute Git-/SCM-Qualification.
`attempt`/`resume`/`abandon`/`cleanup` behalten Zielbindung, normalen Bootstrap
und die jeweiligen Authority-/Lock-/Begründungsprüfungen. Diagnoseerfolg ist
keine Freigabe für diese Wirkungen und kein allgemeiner Readiness-PASS.


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

### Weitere installierte Entry Points

`pyproject.toml:[project.scripts]` liefert neben `samuel` vier Programme:

| Programm | Zweck und vorhandene Bedienreferenz |
|---|---|
| `samuel-release` | Lokales atomisches Release installieren, prüfen, Status lesen oder zum vorherigen unterstützten Release zurückschalten; [Installation und Update](INSTALL.md) sowie [ADR-0706](adr/0706-atomic-release-layout.md) |
| `samuel-extension` | Öffentliche Extension-Manifeste, Requests und Results validieren; [Extension-Datenvertrag](EXTENSION_CONTRACT.md) |
| `samuel-documentation` | Separater statischer Documentation-Consumer und Publisher; [Extension-Datenvertrag](EXTENSION_CONTRACT.md#dashboard-documentation-extension-und-wiki). Liest die Dashboardcheckboxen nicht und startet keinen Workflow. |
| `samuel-git-askpass` | Interner kurzlebiger Git-Transporthelper; Credentials ausschließlich über den bestehenden Askpass-Kanal, keine Operator-CLI oder zusätzliche Secretpersistenz |

Checkout-Werkzeuge unter `tools/` sind keine installierten Entry Points.
Releasebundles stellen zusätzlich `samuel-container` für den bestehenden
Compose-/Releasepfad bereit; Bedienung und Grenzen stehen in
[Container-Release-Operations](CONTAINER_RELEASE_OPERATIONS.md).

### Audit-Sink-Drainage beim Shutdown

Beim Beenden ruft die CLI `_shutdown_audit_sinks(bus)` zum Drain
der `AsyncAuditSink`-Queues auf (#257). Der Worker-Join hat fünf Sekunden
Timeout; das vorgelagerte Queue-Sentinel-Put besitzt kein Gesamtzeitbudget.
Timeout, Writerfehler und Fallback
bleiben mögliche Fehlergrenzen: Annahme in der Queue ist kein Beleg für einen
dauerhaften Write. Der aktuelle Health-/Auditverify-Befund beweist keine
fehlerfreie Writerzustellung; der zusätzliche Diagnosevertrag bleibt #986.

---

### Health-, Readiness- und Qualification-Projektion (#693)

Der passive Projektcheck ergänzt vorhandene operative Blockiergründe; er
überschreibt keine anderen Gründe. Eine erfolgreiche Projektbeobachtung macht
ungeprüfte oder veraltete Readiness nicht automatisch ready. Technische Health,
Workflowbereitschaft und Sicherheitsqualification bleiben getrennt.


`HealthHandler` führt den aktiven technischen Check aus und schreibt dessen
bereinigte Zusammenfassung sowie die zweckgebundene Workflow-Readiness in die
vorhandenen `run_projections`. `samuel doctor` und `samuel audit verify`
schreiben unabhängig ihre Fachbefunde. Alle Datensätze tragen
`health-readiness.v1`, State-Instanz, UTC-Prüfzeit und Evidence-Digest.
Doctor kann für den nativen Branchschutz-GET einen separaten temporären
Token-Dateipfad erhalten (`--branch-protection-token-file`), für Gitea und
GitHub einschließlich Enterprise. Die normale SCM-Probe behält den Runtimebot.
Die gespeicherte Qualification enthält weiterhin ausschließlich Checkzahlen
und Namen fehlgeschlagener Checks, keinen Tokenwert/-digest oder Dateipfad.
Ein erfolgreicher Toolchain-/Branchschutz-Check ist kein Workflow- oder D0-PASS.

Schlägt der aktive SCM-Issue-Read fehl, zeigt `checks.scm.error` nur die
Fehlerklasse und einen gültigen numerischen HTTP-Status. Freie externe
Fehlertexte, Requestpfade und Antwortkörper werden nicht in Health-Antwort,
CLI, Self-Check, Logs oder Startup-Ereignisse übernommen: Sie können private
Werte enthalten. HTTP 403 belegt dabei kein bestimmtes erforderliches
Adminrecht und keine Ursache des Fehlers. `healthy`, `critical`, bestehende
Health-Exitcodes und die Readinessentscheidung bleiben unverändert.
Bereits vorhandene historische Logs oder Ereignisse werden nicht umgeschrieben.

Ein Snapshot ist höchstens 3600 Sekunden aktuell. Eine fremde Instanz nach
Restore oder ein älterer Datensatz ist `stale`; ein fehlender Datensatz ist
`not_checked`. Eine aktuelle erfolgreiche Wiederholungsprüfung löst einen
Fehler nur unter Bindung seines vorherigen Digests auf. Fehlender Auditkey,
fehlende Dateien oder Rotation können einen Fehler weder überschreiben noch
in einen Pass verwandeln. Der State-Authorityblock enthält keinen erfundenen
`resume_enabled`-Default; nur der Resume-Runtime-Resolver liefert diesen Wert.

`GET /api/v1/dashboard/health` und der Viewerstatus lesen den Snapshot ohne
Bus-Command, SCM- oder LLM-Zugriff. Die gemeinsame passive Projektprüfung
ergänzt aktuelle lokale Voraussetzungen; eine fehlende oder abweichende
OCI-Bindung blockiert Readiness auch bei einem früheren grünen Snapshot.
Sie verändert weder State noch Source und behauptet keine Ausführungsisolation. Der aktive Self-Check bleibt unter
`RUN_PROVIDER_PROBES`: Er prüft jede wirksame konfigurierte LLM-Taskroute
über den vorhandenen Connection-Tester und übergibt an Health nur feste
Task-/Provider-/Pass-Facts. Eine vollständige Probe setzt die Readiness auf
`ready`, eine fehlende oder fehlgeschlagene Route auf `blocked`. Providerantworten,
Credentials, Endpoints und Modell-IDs werden weder im Ergebnis noch in der
Projektion gespeichert. Ein späterer Health-Check ohne Probe bleibt in seiner
eigenen Antwort `unknown`, überschreibt aber keinen noch aktuellen aktiven
Probe-Befund. Die Projektion ist Darstellung und gespeicherte Diagnose, keine
Gate-, Workflow-, Merge- oder Releaseauthority.

`samuel setup` übernimmt vorhandene `.env`-Werte und Kommentare über den
bestehenden Setup-Writer, den auch das Dashboard nutzt. Neue temporäre Dateien
sind vor dem ersten Secret-Byte privat; `.env` wird mit `0600` gespeichert.
Datei-Symlinks, nicht reguläre Ziele und Rechtefehler werden abgewiesen; die CLI
meldet bei fehlgeschlagener Persistenz Exit 1 und keinen erfolgreichen Save.
Der explizite OCI-Dateimount-Fallback behält Staging und kontrollierten Rollback.
Er ersetzt keine Rename-Atomizität bei einem Prozess-/Hostabsturz und keine
Verschlüsselung des bestehenden Klartext-Secretvertrags.

### Expliziter Wiederanlauf nach einem beendeten Versuch (#920)

Für ältere Issues ohne Wiederanlaufjournal darf der Operator ebenfalls eine
begründete vollständige Neuplanung anfordern. Ein vorhandenes Fehlerlabel
sperrt nur den automatischen Einstieg; es erteilt keine Freigabe. Eine
unbekannte alte Versuchskorrelation wird nicht nachträglich erfunden.

`WorkflowRecovery` liegt vor Workflow-Dispatch und vor Idempotenzverbrauch.
Ein synchroner Issueablauf erhält einen create-only Ausführungsbeleg und einen
Abschlussbeleg im bestehenden Authority-Store. Der vorhandene
`reduce_workflow_outcome` bewertet seine korrelierten Fakten; ein heilbarer
Stagefehler allein beendet keinen Versuch. Bei einem Prozessabbruch ohne
Abschlussbeleg bleibt der Ausgang unbekannt und automatische Wiederaufnahme
gesperrt. Ein bestätigter terminaler Fehler wird niemals zum erfolgreichen
Versuch umgeschrieben. `PlanReplanRejected` entwertet den bestehenden Plan nicht.

Der explizite Operatorweg wird gegen Konfiguration und laufende Dispatches
serialisiert. Vor Widerruf/SCM-Schreiben entsteht ein dauerhafter
Beendigungsbeleg; unvollständige Beendigung bleibt gesperrt. Erst bestätigter
Widerruf, sichere Checkpointaufgabe, Labelreadback und der Abschlussbeleg geben
den Konfigurationsblocker frei. Ein neuer Versuch ist eine neue Korrelation
mit eigenem Branch und neuer Freigabe; Verbrauch und alte Evidence bleiben
unverändert. Ein Versionsdigest bindet die Bedienaktion an gelesene Pläne,
Issueinhalt, Journal, Checkpoints und Blocker. Alte korrelierte Zustellungen
können einen ausdrücklich beendeten Versuch nicht reaktivieren.

`samuel recovery inspect 42` liefert JSON einschließlich `version`. Mit dieser
Version sind `samuel recovery end 42 --version VERSION --reason "Plan ungeeignet"`
und `samuel recovery replan 42 --version VERSION --reason "Ursache behoben"`
zulässig, sofern die tatsächlichen Guards erfüllt sind. `samuel replan 42
--reason "Plan ungeeignet"` liest den Zustand unmittelbar vor derselben Aktion.
`recovery resume 42 --version VERSION` verwendet ausschließlich die angebotenen
technischen Checkpoints. Der Recovery-CLI-Bootstrap führt keinen automatischen
Resume aus; `inspect` ist dennoch kein offline Storeleser: er benutzt die
normale Runtime und SCM. Der separate passive `resume list|inspect` bleibt
unverändert.

Die technische Resumeprüfung bleibt zuständig für Quellen-/Policy-/Contract-
und Gitbindung sowie unbestätigte Commit-/Push-/PR-Effekte. Fehlende oder stale
Bindungen erlauben keinen Stage-Sprung. Normale Freigabe-/MANUAL-Wartezustände
und laufendes budgetiertes Healing behalten ihre bestehenden Fortsetzungswege.
Die vollständige allgemeine Label-/Diagnosematrix von #956/#890 bleibt eigener
Umfang; der neue terminale Aufnahmeguard hängt nicht vom Erfolg eines
Labelwrites ab.

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
| System-Prompts | `samuel/core/prompts/*.md` | 7 Prompts (planner, analyst, reviewer, healer, log_analyst, docs_writer, senior_python); Schreiben mit `WRITE_CONFIGURATION` ausschließlich im expliziten Setup-Prozess |
| Schedule | `config/llm/defaults.json` | Validierte Tag-/Nacht-Routing-Einstellungen pro Task |
| Settings → Documentation Extension | `config/extensions.json`, `/api/v1/settings/extensions/documentation` | Operatorwahl und gespeicherter/wirksamer Status des externen statischen Dokumentations-Consumers; Felder und separater Wiki-Weg im [Extension-Datenvertrag](EXTENSION_CONTRACT.md#dashboard-documentation-extension-und-wiki) |
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

Der Status- und Settings-Default ist ein **globaler Prozessdefault**, kein
aktuell verwendeter Taskprovider (#983). Die vorhandene Factory-Zusammenfassung
liefert Default, Quelle und Fallbacks der erzeugten Adapter; ohne diese Facts
bleibt nur Prozesskonfiguration ohne Adapter-Nachweis. Die Statuskachel ist
kein grüner Call-/Probe-PASS. Task- und Schedule-Overrides können andere
Provider wählen; tatsächliche Nutzung bleibt ausschließlich in den genannten
Current-/Last-Call-Facts sichtbar.

Settings trennt den gespeicherten Default und die gespeicherte Fallback-Kette
von den prozesswirksamen Werten. Nach Setup-Save kann dort beispielsweise
DeepSeek gespeichert sein, während der laufende Prozess Gemini verwendet;
die bestehende ConfigurationAuthority zeigt dann Neustartbedarf. Erst ein
neu erzeugter Prozess übernimmt die Werte. Ein weiterhin gesetzter
Environmentoverride bleibt vorrangig für den globalen Default. Keypräsenz,
Providerkatalog und konfigurierte Route beweisen weder aktive Nutzung noch
eine erfolgreiche Verbindungsprobe; mehrere Keys erzeugen keine Fallbackliste.
Die Anzeige verändert weder Routing noch Produktions-Freeze.


### Prompt-Dateigrenze

System-Prompts verwenden einzelne `.md`-Dateinamen, keine absoluten Pfade oder
Unterverzeichnisse. Die bestehende Kaskade bleibt Modell → Provider → generischer
Operator-Override → Package-Default. Der konfigurierte Config-Pfad ist die
vertrauenswürdige Wurzel; darunter werden Verzeichnis- und Datei-Symlinks nicht
zum Lesen oder Auflisten verfolgt. Ungültige oder unlesbare Kandidaten fallen in
der Runtime durch die Kaskade; eine ausdrücklich gewählte Scoped-Ansicht bleibt
leer und wechselt nicht zu einem anderen Profil. Speichern ersetzt einen
Override über eine exklusive temporäre Datei, Löschen entfernt einen finalen
Datei-Link selbst. Verlinkte Scope-Verzeichnisse führen zu einem Fehler. Die
unterstützte Laufzeit benötigt deskriptorrelative No-Follow-Dateioperationen;
bei fehlender OS-Unterstützung werden diese Zugriffe verweigert. Dies erteilt
keine Freigabe für externe Promptverzeichnisse oder einen neuen Profilvertrag.

### Operator-Konfigurationsmodus

`samuel dashboard` startet weiterhin mit `production` (CLI vor Environment vor
Default). Die bestehende `ConfigurationAuthority` hält die allgemeinen
Setup-Schreibrechte gesperrt. Ihr ausdrücklich registrierter LLM-Bereich besitzt
einen eigenen exklusiven Lebenszyklus: `idle → editing → applying → idle`;
Fehler bleiben `failed`, Recovery verwendet `restoring`. Der Modus ist kein
zeitlich ablaufendes Setuprecht und schaltet keine weiteren Einstellungsbereiche
frei. Der [Bedienablauf](INSTALL.md#43-dashboard-rekonfiguration-und-produktions-freeze)
benötigt für normale LLM-Änderungen keine Konsole und keinen Dienstneustart.

`ConfigurationSession` nutzt ein versioniertes Dokument im bestehenden
Authority-State (`configuration_admission.v1`). CAS serialisiert Arbeitsstarts,
Owner-/Browserversion und Moduseintritt. Ein nicht ablaufender Eintrag hält
synchron laufende Ausführungen fest; wartende Issuezustände bleiben über deren
Rückkehr hinaus erhalten. Workflow-Einstiege des Bus, Watch und Webhook-Ingress
sind davor gesperrt. Webhooks erhalten HTTP 503 mit `retryable: true`, ohne ihre
Zustellung als erledigt zu deduplizieren. CLI-Einzelstarts melden BUSY; Watch
wartet auf den nächsten Zyklus. Fortsetzbare Checkpoints, ungeklärte Intents,
LLM-Budgetversuche, Healing und SCM-Wartezustände verhindern den Moduseintritt.
Fertige Reviews benötigen für den Konfigurationswechsel keinen Human Merge.

Das Dokument enthält Entwurf, vorherige Dateiinhalte, Versions- und
Revisionsnummer sowie optionale Testnachweise. Vor dem ersten Write steht der
Wiederherstellungsstand dauerhaft fest. Beide kanonischen LLM-Dateien werden
synchronisiert geschrieben und zurückgelesen; ein Abbruch wird ausdrücklich
wiederhergestellt und niemals durch Timeout freigegeben. OS-Prozesssperren
verhindern konkurrierendes Apply/Recover und erlauben den expliziten Abgleich
verwaister Ausführungseinträge. Sie löschen keine fachlichen Wartezustände.
Ein stabiler `LLMRuntime`-Verweis schaltet den vollständigen Adaptergraphen für
Planning, Implementation, Review, Healing und Health um. Andere Prozesse laden
die neue Revision vor ihrer nächsten Ausführung. Bestehende Workflowbudgets,
Reservierungen und Verbrauchshistorie werden nicht neu angelegt oder gelöscht.

Nur `llm` ist registriert. Der schmale Bereichsvertrag besteht aus Snapshot,
Validierung/Vorschau, Vorbereitung, Persistierung und Aktivierung; weitere
Bereiche können denselben Lebenszyklus später ausdrücklich verwenden. Es gibt
keine automatische Pluginregistrierung. Promptauswahl ist enthalten,
Promptdateiinhalte und Secrets bleiben außerhalb des Editors. `evaluation`
bleibt ein konfigurierbarer Task ohne aktiven LLM-Verbraucher.

`configuration:write`, vorhandene CSRF-Prüfung und bei lokalen Identitäten
frische Reauthentisierung schützen Modusaktionen. Verbindungstests verlangen
zusätzlich die separate Probe-Permission. Status/Entwurf liegen im bestehenden
Settings-Read mit `configuration:read`. Audit enthält Actor, Aktion, Change-ID,
Bereich, Version und Probe-Ergebnis/-Umfang, jedoch keine Prompttexte oder Zugangsdaten. `.env` bleibt
die externe Secretgrenze; die erste Installation verwendet weiter `setup`.

Das Setupformular sperrt alle Eingaben vor einer bestätigten Schreibfreigabe
und während des Speicherns. Fehlende Berechtigung oder Produktions-Freeze
halten die Sperre aufrecht. Abgewiesene Saves fokussieren die vorhandene
Fehleranzeige mit den Backenddetails und scrollen sie ins Sichtfeld. Die
Projektsektion verlinkt die vorhandene Testpolicy und OCI-Toolchain aus der
Installationsanleitung; sie bietet keinen zusätzlichen Policyeditor oder
Runnerresolver. Doctor-Runnerprüfung und Candidate-Test bleiben getrennte
Nachweise.

Diese Schreib-/Neustartgrenze beschreibt den Dashboardprozess. Sie ist keine
projektweite Zusage eines unveränderlichen `IConfig`: Der Watch-Handler ruft
am Anfang jedes Scans `FileConfig.reload()` auf. Handler, die danach generische
JSON-Werte oder Featureflags erneut abfragen, sehen die geladenen Werte.
Workflowprofil und Bus-Wiring werden dabei nicht neu aufgebaut; LLM-Adapter wechseln nur über die freigegebene Konfigurationsrevision; `.env` wird dadurch nicht neu importiert. Extern geänderte
Dateien und die Setup-API sind deshalb unterschiedliche Wirkungspfade.

### Documentation Extension und Wiki

Unter **Settings → Documentation Extension** speichert der Operator die
Auswahl für `documentation.static_claims`. **Aktiviert** prüft das angegebene
Capability-Manifest, **Erforderlich** lässt eine fehlende, deaktivierte oder
inkompatible Capability bei der Statusprüfung blockieren. **Manifestpfad**
bezeichnet eine für den Prozess erreichbare `capability.json`.
**Gespeichert** und **Wirksam** unterscheiden Dateistand und Startzustand;
Änderungen benötigen den Setupmodus und einen Produktionsneustart.

Die Checkbox startet keinen Consumer und keinen Wiki-Build. Die separat
aufgerufene `samuel-documentation`-CLI liest diese Operatorwahl derzeit nicht.
Für den Installationstest bleiben beide Checkboxen im Default ausgeschaltet.
Feldbeschreibung, Vorbereitung und Grenzen:
[Dashboard-Anleitung im Extension-Datenvertrag](EXTENSION_CONTRACT.md#dashboard-documentation-extension-und-wiki).
Das lokale Repository-Wiki wird unabhängig davon gebaut
([Abschnitt 23](#23-deterministischer-wiki-build)); externe Wikis werden separat
publiziert ([Abschnitt 24](#24-providerneutraler-git-wiki-publisher)).

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

Jede Meldung nennt einen konkreten Prüf- oder Behebungsschritt und den zulässigen
Folgeschritt. `diff_secret_scan` verweist auf Finding-Typ und Fundstelle sowie
Secret-Referenzen statt Klartextzugangsdaten. `bound_healing:gate_11_not_failed`
erklärt die nicht erfüllte Healing-Voraussetzung; es ist kein weiterer
Gatefehler. Ein unbekannter Workflow-Stopp verweist auf Ereignis, Zeitpunkt,
Issue/Korrelation und die zugehörigen Logs, ohne eine Ursache zu erfinden.
Nach einem gescheiterten Versuch gilt der bestehende Dashboardweg: offene
Vorgänge klären, Versuch ausdrücklich beenden, Ursache beheben, neu planen und
menschlich freigeben. Hinweise starten keine Aktionen.

Pro Vorkommnis können bis zu zehn weitere Warn-/Fehlermeldungen aus dem
vorhandenen Auditfenster aufgeklappt werden. Sie stimmen in Issue (auch ohne
Issue) und nichtleerer Korrelation überein; explizit widersprüchliche
Repository-/Head-/Base-/Vertragsbindungen werden ausgeschlossen. Fehlende
Bindungen werden nicht ergänzt: Dies ist ein Ausschnitt derselben Korrelation,
keine vollständige Runhistorie oder Kausalkette. Zeit, Ereignis, Gate und
vorhandene Fundstellen helfen beim Nachlesen im Logs-Tab. Andere Ereignis- oder
Gatearten bleiben auch bei gleicher Fingerprint-Kennung getrennte Probleme.
Die Hinweise werden beim Lesen aus dem aktuellen Formatter erzeugt; alte
Auditereignisse, FAILs und gespeicherte Hinweise bleiben unverändert.

### SCM-Berechtigungsdiagnosen (#897)

`samuel/core/permission_diagnostics.py` vereinheitlicht vorhandene SCM-Ergebnisse
für API-Logs, Dashboard, Doctor und Setup. Das additive Feld
`permission_diagnostic` verwendet `schema=scm-permission.v1` und enthält
`actor`, `operation`, `outcome`, `state`, `http_status`, `method`, `endpoint`,
`scope`, `required_permission`, `overall_permissions`, `action_actor` sowie
begrenzte Erklärung und nächste Schritte. `actor` benennt den konfigurierten
Credentialzweck (`runtime_bot` oder `operator`), keine durch eine zusätzliche
IAM-Abfrage bestätigte Identität. `endpoint` ist eine bekannte relative
Routenschablone, sonst `unknown`; IDs, Repositorynamen, Querywerte, Secrets und
Providerantworttexte werden nicht übernommen. Der konfigurierte SCM-Endpunkt
und das Zielrepository bleiben der betriebliche Kontext.

| `state` | Beleg und nächste Aktion |
|---|---|
| `ACCESS_CONFIRMED` | Genau die benannte Operation war erfolgreich. Weitere Fähigkeiten getrennt prüfen; keine Rechteausweitung ableiten. |
| `OPERATOR_ACTION_REQUIRED` | HTTP 401/403 hat den konkreten Zugriff abgewiesen. Operator prüft Endpoint und das unter `actor` genannte Credential; ein Operatorproblem wird nicht dem Bot zugeschrieben. |
| `UNEXPECTED_PRIVILEGE_ESCALATION_REQUEST` | Der vorhandene Gitea-API-Guard hat eine verbotene Mutation vor Netzwerkzugriff blockiert. Aufrufenden Pfad korrigieren, Sperre beibehalten und erforderliche Verwaltungsarbeit getrennt erledigen. Keine Absichtsbehauptung über ein LLM. |
| `UNKNOWN` | Fehlender Zugriffsnachweis, 404, Transportfehler oder unbrauchbare Probeantwort. Ziel/Verbindung prüfen; bei unklarem Schreibresultat zuerst die tatsächliche Wirkung feststellen. |

Dies ist der operationenbezogene Vertrag zur Least-Privilege-Einordnung:
`ACCESS_CONFIRMED` ersetzt **keinen** pauschalen
`EXPECTED_LEAST_PRIVILEGE`-Gesamtbefund. Alle Ergebnisse behalten
`scope=operation`, `overall_permissions=not_checked` und
`required_permission=unknown`. Ein Repository-GET, Label-GET oder lesbarer
Branchschutz beweist weder alle Bot-Schreibrechte noch minimale wirksame Scopes.
Nicht-Admin zu sein ist für sich kein Fehler. `action_actor=operator` bezeichnet
den zuständigen Prüfer, nicht die Forderung nach einem neuen Operatorsecret.

Erfolgreiche API-Aufrufe erzeugen normale INFO-Logs. Fehler und vorhandene
Guards nutzen die bestehende WARNING/CRITICAL-Brücke zu `DiagnosticRaised`;
Probleme und Logs zeigen sie mit vorhandener Issue-/Korrelation, falls der
Aufruf gebunden war. Das ist historische Beobachtung, kein neuer Healthstore.
Die Problemdarstellung rekonstruiert Hinweise aus begrenzten Feldern; alte
unstrukturierte Meldungen werden nicht nachträglich als Eskalation klassifiziert.
Die Security-Kachel liest weiterhin nur Branchschutz. Doctor prüft weiterhin
Repository und Branchschutz, Dashboard-Setup weiterhin Labels und CLI-Setup
den Identitätsendpoint. #905 ergänzt ausschließlich einen ausdrücklich ausgelösten
Hook-Metadaten-GET; keine Schreib- oder Zustellprobe.

Vorhandene Exit-/Release-/Workflowentscheidungen, Retries, Credentials und
API-Sperren bleiben maßgeblich. Insbesondere bleibt der historische
Verbindungsstatus für `/user`-403 erhalten, während die additive Diagnose den
verweigerten Zugriff ausdrücklich ausweist. HTTP404 am Branchschutz ist kein
Rechtenachweis; Doctor bleibt ohne passende Regel FAIL. GitHub erhält keine
neu erfundene lokale Gitea-Sperre. Webhookprovisionierung wird nicht als neue
Setupfunktion eingeführt; der bestehende bzw. externe Operatorweg bleibt
getrennt. #905 verwendet diese Diagnosen für seinen optionalen Hook-Read; #921 darf daraus kein
pauschales READY ableiten. Reale Rollen-/Endpoint-/Scopeabnahme erfolgt in der
zusammengefassten Installation (#962/#994).

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

### Gemeinsame passive Betriebsdiagnose (#921)

`GET /api/v1/dashboard/diagnostics` verlangt `READ_DIAGNOSTICS` und liefert
`schema=samuel-system-diagnostics.v1`, `informational_only=true`, `passive=true`,
`checks`, `note`, `coverage` sowie das unveränderte `webhook-diagnostic.v1`-Objekt
unter `webhook`. Es existiert bewusst kein globaler `status`/SYSTEM_READY und
kein neuer Preworkflow-Consumer. Die Maintainerentscheidung zu #921 ersetzt den
früheren zusätzlichen Preflight-/Gesamtfreigabeumfang durch gemeinsame Diagnose.

`checks[]` enthält feste `code`/`name`, `status` (`passed`, `failed`, `unknown`,
`degraded`), `source`, `expected` (enge Aussagegrenze), `fix`, `freshness`
(`current`, `stale`, `unknown`), `checked_at`, optionalen vorhandenen
`evidence_digest` und `previous_failure`. Nicht vorhandene Zeit/Digestwerte sind
`null`. Nur korrekt formatierte Evidence-Digests aus bestehenden bereinigten
Fachprojektionen werden übernommen; keine neuen Credentialfingerprints oder
Konfigurationsdigests. Rohfehler, Providerantworten und lokale Pfade werden nicht
in die Übersicht kopiert. Bei fehlender/alter Evidence ist das Ergebnis unbekannt;
ein letzter Fehler bleibt kenntlich, ohne als aktueller Befund ausgegeben zu werden.

Die vorhandene Dashboard-Datenschicht komponiert `health_projection.snapshot`,
den aktuellen Projektresolver und `ConfigurationAuthority.status`; Serverwiring
ergänzt `build_webhook_report` ohne Metadatenread. Keine neue Persistenz, Migration,
Events, Probe, automatische Reparatur oder zweite Fachprüfung. Health-/Doctor-/
Audit-/Startauthority bleiben unverändert. Persistierte Healthfakten sind an
State-Instanz und eine Stunde gebunden, nicht an jede Configänderung; aktuelle
Konfigdrift wird daneben sichtbar. Das Auditwriter-Ergebnis bleibt von der
Auditintegrität getrennt. Native Zustellung erhält durch Zusammenfassung keinen PASS.

Detailnachweise für TEST-Runner, einzelne LLM-Routen/Metadaten, Credentialpräsenz,
Workspace-Ownership oder SCM-Mappings werden aus gröberen gespeicherten Ergebnissen
nicht rekonstruiert. Dafür bleiben vorhandene Fachansichten/Doctor/Self-Check
zuständig. `GET …/self_check` und `POST …/webhook/read` behalten ihre explizite
`RUN_PROVIDER_PROBES`-Grenze; `samuel health`, `samuel doctor`, `samuel audit verify`
behalten Befehle und Exitcodes. Die neue Übersicht hat keinen CLI-Aggregatbefehl.
Bedienung: [Konfig → Betriebsdiagnose](DASHBOARD.md#gemeinsame-betriebsdiagnose-921).
Die gebundene reale Installationsabnahme bleibt #962/#994.

### Passive Webhook-Diagnose (#905)

`samuel/core/webhook_diagnostics.py` beschreibt ausschließlich Beobachtungen.
Der bestehende Ingress hält je Stufe Empfang/Signatur/Mapping die letzte
begrenzte Beobachtung im Prozessspeicher. Es werden keine Payloads, Secrets,
Delivery-IDs oder neuen Audit-/Workflowereignisse dafür gespeichert. Der
konfigurierte Provider wird beim Anzeigen abgeglichen. Zeit und Ein-Stunden-
Fenster begrenzen die Aussage; Stufen sind keine behauptete gemeinsame Delivery.
Neustart verwirft diesen flüchtigen Stand. Der bestehende Raw-Body-HMAC-,
Event-Mapping-, Konfigurationssitzungs- und Human-Authoritypfad bleibt erhalten.

Dashboard-GET liest nur diesen Stand und den letzten bereinigten Hook-Read.
Der explizite POST verwendet `samuel/webhook_probe.py` und die vorhandenen
SCM-Clients für `GET /repos/{owner}/{repo}/hooks`, erste Seite bis 50 Einträge.
Die beim Serverstart gebundene Konfiguration bestimmt Provider, Repository und
Credential; Requestdaten können sie nicht überschreiben. Redirects werden vor
Weitergabe des Tokens abgewiesen. Der API-Guard für Schreiboperationen bleibt
unverändert. Hook-Secrets, Authorizationheader, URL-Userinfo, Query/Fragment und
abweichende URL-Pfade werden nicht zurückgegeben. Ziele werden weder kontaktiert
noch per DNS aufgelöst. Das Ergebnis verwendet die operationenbezogene
Berechtigungsdiagnose aus #897.

`webhook-diagnostic.v1` liefert `checks`, bereinigte `hooks`, Lesestand,
Freshness und `informational_only=true`. `received`/`pass`/`handled` bestätigen
nur die jeweilige Stufe, `ignored` keine erfolgreiche Verarbeitung. Native
Zustellung bleibt `not_proven`: diese schmale Diagnose korreliert keine
providerseitige Zustellhistorie und importiert keine Qualification-Receipts.
Sie erzeugt weder eine Startsperre noch Gesamtreadiness. Doctor zeigt dieselben
Grenzen separat und liest mit `--webhook` optional Metadaten, ohne den eigenen
Exitcode oder die bestehende Qualificationprojektion zu verändern. Der
Branchschutz-Prüfertoken bleibt ausschließlich an den Branch-GET gebunden.
Bedienung, Eventauswahl und Abhilfe: [Installation](INSTALL.md#webhook-diagnose-ohne-neue-startsperre-905).

### Planfreigabe-Diagnose (#948)

Bei `plan_approval_source_revision_mismatch` prüft der Diagnosehinweis die
Plan-/Issue-/Basisrevision. Nach einem Merge kann die neue Basis von der alten
Freigabebindung abweichen: historischen Abschluss lesen, keine alte Authority
übertragen und für neue Arbeit den öffentlichen Plan-/Replanpfad verwenden.
Ein nicht erreichbarer Source-Read bleibt davon getrennt. Resolverentscheidung,
Grundcode und `unknown` bleiben bei dieser Textkorrektur erhalten.

Bei ignorierten nativen Labelzustellungen eines gebundenen Repositorys mit
sichtbarem `status:approved` ergänzt die Antwort gegebenenfalls
`approval_diagnostic`: `status=delivery_not_materialized`, fester
`reason_code`, verständliche `message`, `next_action` und
`diagnostic_persisted` sowie `issue_feedback` (`posted`, `already_posted`,
`unknown`, `unavailable`, `not_applicable`). Der Persistenzwert bestätigt ausschließlich die Diagnoseablage,
keine Planfreigabe. Originale HTTP-Status-/Action-/Reason-Semantik bleibt erhalten.
Nur erfolgreich signierte und subjectgebundene Zustellungen können eine
Diagnose schreiben. Bots, fremde Subjects und während der Bindungsprüfung
wechselnde Pläne schreiben keine aktuelle Plan-Diagnose. Nicht jede native
Labeländerung ist eine Approvalhandlung.

`approval_diagnostics.py` nutzt dafür den vorhandenen `IRunProjectionStore`
mit Serie `plan-approval-diagnostic.v1`: je Repository/Issue/Plan-Kommentar/
Contract die zuletzt gespeicherte Erklärung als fester Code und
Beobachtungszeit sowie begrenzte Kommentarzustellclaims, ohne Payloadtexte,
Akteure, Header oder Secrets. Eine alte
Zustellung vor Veröffentlichung des gelesenen Plans wird diesem nicht
zugeordnet. Die Diagnose hat keinen Workflow-/Label-/Authorityeffekt und
erzeugt keinen zusätzlichen Workflow-Run. Schreib-/Lesefehler bleiben begrenzt im
Prozesslogging sichtbar; fehlende Diagnose wird nicht zu einem Freigabe-PASS.
Eine zweite Instanz kann nur die tatsächlich persistierte letzte Beobachtung
lesen. Gleichzeitige Diagnoseschreiber liefern keinen vollständigen
Deliveryverlauf; dafür bleibt die bestehende Webhookdiagnose zuständig.

Logs ergänzt pro Plan einen kompakten Hinweis aus derselben Projektion,
ohne den vollständigen Statuskartentext zu duplizieren. Replays erneuern die
Beobachtungszeit nicht. Eine nachgewiesene Freigabe löst den früheren Hinweis
als `resolved` auf. Sortierung normalisiert Audit-/Projektionszeitformate;
Anzeige und Levelzähler verwenden dieselben höchstens 200 Einträge.
Bei der Auswahl haben ungelöste Approvalhinweise Vorrang vor der normalen
Audit-/Erledigthistorie; innerhalb beider Gruppen zählen die neuesten echten
Zeitpunkte. Die ausgewählten Zeilen werden anschließend gemeinsam zeitlich
sortiert. Auch mehr als 200 aktive Hinweise vergrößern die Antwort nicht;
in diesem Fall sind nur die neuesten 200 enthalten. Reads und wiederholte
Zustellungen frischen keinen Hinweiszeitpunkt auf. Nach `resolved` entfällt
der Vorrang. Die serverseitige Auswahl gilt ebenso für die Datenbasis der
clientseitigen Kategorie-/Level-/Textfilter.

Aktuelle menschliche native Labelzustellungen können über den bestehenden
`IVersionControl.post_comment` eine nichtautoritative Rückmeldung im Issue
erzeugen. Sie bindet den exakten Plan/Contract und erklärt Ablehnung oder
Annahme samt nächster Aktion. Eine bestehende gültige Authority hat Vorrang
vor einer später ignorierten Zustellung. Ein versteckter Produktmarker und
ein atomarer Claim per `IRunProjectionStore.compare_and_swap_projection`
begrenzen Rückmeldungen auf einen Kommentar je Plan/Contract/Grund, auch über
konkurrierende Runtimeinstanzen. Die Claims bleiben in derselben
Diagnoseserie; es entstehen keine Authorityrecords oder neue Tabellen.
POST-Exceptions werden konservativ als `feedback_unknown` geführt; ein
nachträglich gelesener Produktmarker bestätigt einen schon erfolgten Write.
Ohne Marker wird nicht blind erneut gepostet. Fehlende CAS-Unterstützung,
Store-/SCM-Fehler oder nicht mehr zuordenbare Pläne ändern weder den
ursprünglichen Webhookausgang noch Labels/Freigaben. Der bestehende
Prozessdiagnoseweg meldet Zustellfehler; der Logs-Hinweis enthält den
zugehörigen Rückmeldestatus. Polling oder Kommentarapproval erhalten dadurch
keinen neuen Authority- oder Notificationpfad.

---

## 18. API-Endpoints

`GET /api/v1/issues/{id}/recovery` liest Versuch, Phase, Grund,
Wiedereinstiegsgrenze, Blocker, erlaubte Aktionen und eine Zustandsversion.
`POST /api/v1/issues/{id}/recovery` erwartet `action` (`end`, `replan`, `resume`),
`version` und für Beenden/Neuplanung eine nichtleere `reason` (maximal 1000 Zeichen).
Ein unlesbarer Zustand, eine veraltete Version oder nicht erlaubte Aktion liefert
409; fehlende Permission/CSRF/frische Anmeldung 403. Niemals frei wählbare
Stage, Forceoption oder Gateüberspringen. GET liest SCM und Authority-State,
startet aber keine Providerprobe oder Workflowaktion.


Die LLM-Verwaltung verwendet `POST /api/v1/settings/configuration` mit den
Aktionen `enter`, `stage`, `check`, `apply`, `cancel`, `recover`, `reconcile`
(`configuration:write`). Ab `stage` ist die aktuelle `version` erforderlich;
`enter`/`reconcile` sind atomare Zustandsaktionen. Stage trägt `task` und `config`
oder nur `config` für Default/Fallbacks. `apply` akzeptiert
`override_failed_probe: true` als ausdrückliche Bestätigung. Der getrennte
`POST /api/v1/settings/configuration/probe` (`provider:probe`) prüft `task` und
`version` aus dem gespeicherten Entwurf. Konflikte liefern HTTP 409; fehlende
frische Reauthentisierung HTTP 403. Der Settings-Read enthält `configuration.session`.


Die Berechtigungen sind die vorhandenen Core-Permissions aus
`samuel/core/identity.py`; die Zuordnung stammt aus
`samuel/adapters/api/auth.py:permission_for_request`. Der HTTP-Dispatch liegt
in `samuel/server.py:SAMUELRequestHandler` und `adapters/api/rest.py:RestAPI`.
`{id}` bezeichnet die Issue-, Principal-, Session- oder Token-ID der Route,
`{name}` einen validierten Promptnamen. Queryparameter sind nur bei den unten
angegebenen Routen unterstützt.

| Methode | Pfad | Beschreibung | Permission / Zugang |
|---|---|---|---|
| GET | `/api/v1/issues/{id}/recovery` | Versuch und zulässiges weiteres Vorgehen lesen | `READ_DIAGNOSTICS` |
| POST | `/api/v1/issues/{id}/recovery` | Versuch beenden, ausdrücklich neu planen oder technische Finalisierung anfordern | `RUN_OPERATIONS`; lokale Session mit CSRF und frischer Reauth |
| GET | `/`, `/dashboard` | Öffentliche HTML-Shell mit Produktversion | Öffentlich |
| GET | `/api/v1/auth/mode` | Zugriffsmodus und secretfreier Identity-Status | Öffentlich |
| POST | `/api/v1/auth/login` | Lokale Anmeldung; Body `username`, `password` | Öffentlich; nur `local_identity` |
| GET | `/api/v1/auth/check`, `/api/v1/auth/session` | Authentisierung / Actorprojektion | Authentisiert |
| POST | `/api/v1/auth/logout`, `/api/v1/auth/reauth` | Abmelden / Session nach Passwortprüfung rotieren | Authentisiert; lokale Sessionwrites mit CSRF |
| GET | `/api/v1/admin/users` | Principals und unabhängige Rollen lesen | `MANAGE_IDENTITIES` |
| POST | `/api/v1/admin/users` | Benutzer anlegen (`username`, `password`, `roles`) | `MANAGE_IDENTITIES`; frische Reauth |
| POST | `/api/v1/admin/users/{id}` | Rollen, Passwort oder `disabled` ändern | `MANAGE_IDENTITIES`; frische Reauth |
| GET | `/api/v1/admin/sessions` | Sessions lesen; optional `?principal_id=…` | `MANAGE_SESSIONS` |
| DELETE | `/api/v1/admin/sessions/{id}` | Einzelne Session widerrufen | `MANAGE_SESSIONS`; frische Reauth |
| POST | `/api/v1/admin/sessions/revoke-all` | Alle Sessions widerrufen; `confirmation: REVOKE ALL SESSIONS` erforderlich | `MANAGE_SESSIONS`; frische Reauth |
| GET | `/api/v1/admin/tokens` | Tokenmetadaten lesen, ohne Rohwerte | `MANAGE_IDENTITIES` |
| POST | `/api/v1/admin/tokens` | Automation-Token mit `name`, expliziten `permissions` und `lifetime_seconds` erzeugen; Rohwert nur in dieser Antwort | `MANAGE_IDENTITIES`; frische Reauth |
| DELETE | `/api/v1/admin/tokens/{id}` | Automation-Token widerrufen | `MANAGE_IDENTITIES`; frische Reauth |
| GET | `/api/v1/setup/status` | Setup-/Configzustand lesen | `READ_CONFIGURATION` |
| POST | `/api/v1/setup/configure` | Setupwerte validieren und speichern; JSON, höchstens 65.536 Bytes | `WRITE_CONFIGURATION`; Setupmodus |
| POST | `/api/v1/setup/labels` | Konfigurierte Labels im SCM synchronisieren | `RUN_OPERATIONS`; Setupmodus |
| GET | `/api/v1/dashboard/status` | Status, Build und passive Healthprojektion; lokale Actoren erhalten die begrenzte Viewersicht | `VIEW_STATUS` |
| GET | `/api/v1/dashboard/metrics` | Buszählungen, Fehler und Latenzen | `READ_DIAGNOSTICS` |
| GET | `/api/metrics` | Busmetriken als JSON, kein Prometheus-Textformat | `READ_DIAGNOSTICS` |
| GET | `/api/v1/dashboard/diagnostics` | Gemeinsame passive Betriebsdiagnose, keine Gesamtfreigabe | `READ_DIAGNOSTICS` |
| GET | `/api/v1/dashboard/health` | Passive Health-/Readiness-/Qualification-Projektion | `READ_DIAGNOSTICS` |
| GET | `/api/v1/dashboard/webhook` | Passive Webhookdiagnose aus dem Prozessspeicher | `READ_DIAGNOSTICS` |
| POST | `/api/v1/dashboard/webhook/read` | Expliziter SCM-Hook-Metadaten-GET; keine Zustellung/Mutation | `RUN_PROVIDER_PROBES` |
| GET | `/api/v1/dashboard/problems` | Redigierte Problemdiagnosen und gruppierte Vorkommnisse | `READ_DIAGNOSTICS` |
| GET | `/api/v1/dashboard/workflow`, `/api/v1/dashboard/workflow/{id}` | Workflowübersicht / issuebezogene Details | `READ_DIAGNOSTICS` |
| GET | `/api/v1/dashboard/llm` | Konfiguration und aktuelle Callprojektion | `READ_DIAGNOSTICS` |
| GET | `/api/v1/dashboard/llm/pricing-info` | Metadaten des Preis-/Modellcaches | `READ_DIAGNOSTICS` |
| GET | `/api/v1/dashboard/logs` | Begrenzte Audit-/Logprojektion | `READ_AUDIT` |
| GET | `/api/v1/dashboard/security` | Security-/Integrity-Ereignisse | `READ_AUDIT` |
| GET | `/api/v1/dashboard/compliance/legend` | OWASP-/Framework-Legende und konfigurierte Risikoklasse | `READ_AUDIT` |
| GET | `/api/v1/dashboard/dlq` | Dead-Letter-Queue lesen; Replay separat über CLI | `READ_AUDIT` |
| GET | `/api/v1/dashboard/quality` | Gebundene, nicht bindende Qualitätsserien | `READ_AUDIT` |
| GET | `/api/v1/dashboard/activity` | SCM-Aktivitätsprojektion | `READ_AUDIT` |
| GET | `/api/v1/dashboard/transfer_warnings` | Konfigurierte Providerstandorte und Transferwarnungen | `READ_AUDIT` |
| GET | `/api/v1/dashboard/settings` | Gespeicherte und prozesswirksame Settings lesen | `READ_CONFIGURATION` |
| GET | `/api/v1/dashboard/llm/schedule` | Taskbezogenes Tag-/Nachtrouting lesen | `READ_CONFIGURATION` |
| GET | `/api/v1/dashboard/llm/prompts`, `/api/v1/dashboard/llm/prompts/{name}` | Promptinventur / Inhalt; optional `?scope=…` | `READ_CONFIGURATION` |
| POST | `/api/v1/dashboard/llm/prompts/{name}` | Promptoverride speichern (`content`, optional `scope`) | `WRITE_CONFIGURATION`; Setupmodus |
| DELETE | `/api/v1/dashboard/llm/prompts/{name}` | Override entfernen, idempotent; optional `?scope=…` | `WRITE_CONFIGURATION`; Setupmodus |
| GET | `/api/v1/dashboard/llm/models` | Modellkatalog; `provider` erforderlich, optional `task`, `base_url`, `threshold` (0–100), `margin` (0–1), `cost_advisory` (`true`/`false`) | `RUN_PROVIDER_PROBES`; lokale Provider können Netzwerkzugriff auslösen |
| POST | `/api/v1/dashboard/llm/models/refresh` | OpenRouter-Metadatencache aktualisieren | `RUN_OPERATIONS` |
| POST | `/api/v1/dashboard/llm/test-connection` | Temporäre Providerprobe aus `provider` und `config` | `RUN_PROVIDER_PROBES` |
| GET | `/api/v1/dashboard/self_check` | Aktive Probe aller wirksamen Taskrouten | `RUN_PROVIDER_PROBES` |
| GET | `/api/v1/dashboard/self-mode/health` | Self-Mode-Betriebsdiagnose | `RUN_OPERATIONS` |
| GET | `/api/v1/health` | Aktiver `HealthCheckCommand`; kein passiver Statusabruf | `RUN_OPERATIONS` |
| POST | `/api/v1/settings/flag` | Featureflag speichern (`name`, `enabled`) | `WRITE_CONFIGURATION`; Setupmodus |
| POST | `/api/v1/settings/risk-class` | Deployment-Risikoklasse speichern (`risk_class`) | `WRITE_CONFIGURATION`; Setupmodus |
| POST | `/api/v1/settings/attribution` | Attribution speichern (`enabled`, optional `verbosity`); High-Risk-Sperre bleibt bestehen | `WRITE_CONFIGURATION`; Setupmodus |
| POST | `/api/v1/settings/extensions/documentation` | Documentation-Operatorwahl speichern | `WRITE_CONFIGURATION`; Setupmodus |
| POST | `/api/v1/settings/configuration` | Exklusiven LLM-Modus betreten, Entwurf ändern/prüfen/übernehmen oder wiederherstellen | `WRITE_CONFIGURATION`; frische lokale Reauth |
| POST | `/api/v1/settings/configuration/probe` | Gespeicherten Taskentwurf prüfen, Status/Zeit/Version binden | `RUN_PROVIDER_PROBES`; Mode-Owner, frische lokale Reauth |
| POST | `/api/v1/settings/llm/global` | Globale LLM-Konfiguration speichern | `WRITE_CONFIGURATION`; Setupmodus |
| POST | `/api/v1/settings/llm/task` | Taskkonfiguration speichern (`task`, `config`) | `WRITE_CONFIGURATION`; Setupmodus |
| POST | `/api/v1/issues/{id}/plan`, `/api/v1/issues/{id}/implement` | Planning / Implementation anfordern | `RUN_OPERATIONS` |
| POST | `/api/v1/scan` | Issue-Scan anfordern | `RUN_OPERATIONS` |
| POST | `/api/v1/webhook` | SCM-Ereignis entgegennehmen | Separate HMAC-Validierung |

Adminrouten benötigen `local_identity`; mutierende lokale Sessionrequests
zusätzlich CSRF. Im Legacy-Modus erteilt ein gültiger API-Key alle bestehenden
Permissions, aber keine lokale Benutzerverwaltung. Automation-Bearer erhalten
nur ihre expliziten Permissions. Administrator erbt weder Viewer- noch
Operatorrechte. Produktionsprozesse blockieren allgemeine Setupwrites vor der Mutation mit `409 configuration_frozen`; der registrierte LLM-Konfigurationsmodus verwendet den eigenen versionierten Aktionspfad. Authentisierte HEAD-Anfragen führen
keine GET-Aktion aus und liefern keinen fachlichen Statusnachweis.

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

### HTTP-Antworten richtig lesen

Die Tabelle oben benennt Route und Permission. Hier folgen die dazugehörigen
Eingaben, Ergebnisse und Grenzen. Der HTTP-Server liefert das fachliche
JSON-Objekt direkt. Das interne `RestAPI`-Envelope `{status, data}` ist **kein**
zusätzlicher `data`-Wrapper auf der Leitung: bei vorhandenem `data` sendet
`SAMUELRequestHandler` dessen Inhalt. Fehler ohne `data` können hingegen das
interne `status`/`error`-Objekt enthalten. Clients müssen daher den HTTP-Status
und die routebezogenen Felder auswerten.

JSON-Schreibrequests verwenden ein Objekt. Der allgemeine Bodyreader behandelt
ungültiges JSON und Nichtobjekte wie `{}`; daraus folgt keine einheitliche
Schemafehlermeldung für alle Routen. Nur Setup erzwingt zusätzlich Medientyp
und die oben genannte Größenbegrenzung. Es gibt keine hier zugesicherte
universelle Pagination, Feldfilterung oder dynamische OpenAPI-Spezifikation.

| Ergebnis | Bedeutung und nächster Schritt |
|---|---|
| `200` / `201` | Route ausgeführt beziehungsweise Identityobjekt angelegt. Fachfelder wie `valid`, `healthy`, `updated`, `configured`, `restart_required` und `unknown` weiterhin lesen. Eine fehlgeschlagene Providerprobe kann HTTP 200 mit negativem Fachresultat liefern. |
| `202` | Plan-/Implement-/Scan-Command synchron angenommen; keine Zusage zu späterem Workflow-, Test-, Review- oder Mergeerfolg. |
| `400` | Fehlende/ungültige routebezogene Eingabe, unbekannter Task/Provider, ungültiger Promptname oder Fachvalidierung. Fehlerobjekt kann `error`, `errors` oder `code` enthalten. |
| `401` / `403` | Authentisierung fehlt/fehlgeschlagen beziehungsweise Permission, CSRF oder frische Reauth fehlt. Zusätzlichen `code` beachten; ein erneuter Schreibversuch ersetzt keine Freigabe. |
| `404` | Fehlende Route, unbekanntes Commandziel, fehlende Issueansicht oder nicht aufgelöster generischer Prompt; kein Beleg, dass die zugehörige Arbeit nie existiert hat. |
| `409` | `configuration_frozen`, Identityzustand/Konflikt, gesperrte Attribution oder abgewiesener Workflow. Fachursache beheben, keine automatische Wiederholung als Umgehung. |
| `413` / `415` | Setupbody zu groß beziehungsweise nicht `application/json`. |
| `429` | Lokales Loginlimit erreicht. |
| `500` / `502` / `503` | Terminal behandelter interner Commandfehler, fehlgeschlagener Modellcache-Refresh beziehungsweise fehlender Setup-/Dashboardhandler. Ein HTTP-Fehler ist keine neue Qualificationevidence. |

### Auth- und Identityfelder

`actor` enthält `principal_id`, `username`, `kind`, unabhängige `roles`, die
effektiven `permissions` und die verwendete `authentication`. Die IDs dienen
der konkreten Objektadressierung. Keine dieser Antworten enthält
Passwort-/Session-/Tokenhashes aus dem Store.

| Route unter `/api/v1/` | Request / Response |
|---|---|
| `auth/mode` | Keine Eingabe; `access_mode`, `secure_cookies`, `transport`, `identity_status`, `legacy_fallback` beschreiben den tatsächlichen Zugangsmodus. |
| `auth/check`, `auth/session` | Keine Eingabe; `authenticated`/`auth_required` beziehungsweise `{actor: …}`. Eine erfolgreiche Authprüfung sagt nichts über eine andere Route mit höherer Permission aus. |
| `auth/login`, `auth/reauth`, `auth/logout` | Login: `username`/`password`; Reauth: `password`; Logout kein Fachbody. Login/Reauth liefern `authenticated` und `actor` sowie Session-/CSRF-Cookies, Logout `authenticated: false` und gelöschte Cookies. CSRF-Header für mutierende Sessionrequests: `X-CSRF-Token` passend zum `samuel_csrf`-Cookie. |
| `admin/users` / `admin/users/{id}` | Anlage: `username`, `password`, Liste `roles`; Update: optionale `roles`, boolesches `disabled`, `password`. GET liefert `{users: […]}`, Anlage/Update das Principalobjekt: ID, Username, `kind`, `disabled`, Rollen und `created_at`/`updated_at`. Letzter Administrator und doppelte Namen unterliegen dem Identityvertrag. |
| `admin/sessions` / `admin/sessions/{id}` | Optionaler GET-Filter `principal_id`; Antwort `{sessions: […]}` mit Session-/Principal-ID, `created_at`, `authenticated_at`, `last_seen_at`, `expires_at`, optional `revoked_at`/`revoked_by`. DELETE liefert `revoked` für die bezeichnete Session. |
| `admin/sessions/revoke-all` | Body muss `confirmation: "REVOKE ALL SESSIONS"` enthalten; Antwort `revoked` als Anzahl und geleerte eigene Sessioncookies. |
| `admin/tokens` / `admin/tokens/{id}` | Anlage: `name`, explizite Permissionliste und positive `lifetime_seconds`. Antwort bei Anlage: einmaliger Rohwert `token`, Token-/Principal-ID, Username, Permissions und Ablaufzeit. GET `{tokens: […]}` enthält nur Metadaten einschließlich Erstellungs-/Widerrufszeit; DELETE liefert `revoked`. Rohwert geschützt übernehmen, nicht in Evidence/Logs aufnehmen. |

### Konfiguration, Prompts und aktive Proben

Bei Settingswrites bedeutet `updated: true` eine gespeicherte Änderung.
`configuration` beschreibt Modus, Quelle, Schreibbarkeit, gespeicherten und
beim Start erfassten Digest sowie Neustartbedarf; Details unter
[Operator-Konfigurationsmodus](#operator-konfigurationsmodus). `.env`-Secrets
sind vom Digest ausgenommen. Dateispeicherung erzeugt keine neue Factory und
ändert keine bereits gestartete Taskroute.

| Route unter `/api/v1/` | Eingaben, Ergebnisfelder und Grenzen |
|---|---|
| `setup/status`, `setup/configure` | Status liefert `first_run`, `scm_configured`, `api_key_configured`, `llm_configured`, secretfreie `values`, `configuration` und `project`. Configure akzeptiert `scm_provider`, `scm_url`, `scm_user`, `scm_token`, `scm_repo`, `scm_bot_user`, `scm_required_status_context`, `project_root`, `dashboard_port`, `dashboard_api_key`, `llm_provider`, `llm_model`, `llm_base_url`, `llm_api_key`, `allow_unverified`. Fehlende Werte werden nach dem [Setupvertrag](INSTALL.md#4-konfiguration-via-wizard--samuel-setup) aus bestehenden Quellen aufgelöst; ein ausdrücklich leerer Required-Check bleibt Fehler. Ergebnis: `configured`, `restart_required`, `probes`, `configuration`; ein erstmals erzeugter Dashboardkey kann einmalig als `api_key` zurückkommen, bestehende Keys werden nicht ausgelesen. `allow_unverified` erlaubt Speicherung trotz negativer Verbindungsprobe, keinen Probe-PASS. |
| `setup/labels` | Kein Fachbody; synchronisiert vorhandene Labels tatsächlich im SCM. Ergebnis des Setuphandlers mit `synced`/Fehlern lesen. Keine Issue-/Planfreigabe. |
| `settings/flag` | `name` und `enabled` erforderlich; für `enabled` JSON-Boolean senden. Der bestehende Adapter konvertiert via `bool`, garantiert also keine strikte Typzurückweisung für andere JSON-Werte. Ergebnis nennt Aktualisierung/Flagwert beziehungsweise Fehler; keine universelle Hot-Reload-Garantie. |
| `settings/risk-class` | `risk_class` als unterstützter Wert; `updated` und Ergebnis lesen. Gespeicherte Deploymentklassifikation, keine Rechtsabnahme; Environmentvorrang bleibt bestehen. |
| `settings/attribution` | `enabled`, optional `verbosity`; Boolkonvertierung wie beim Flag. `locked` oder `configuration_frozen` führt zu 409. Feldbedeutung und vorhandene Sperre: [Dashboard](DASHBOARD.md#alle-dashboardbereiche). |
| `settings/extensions/documentation` | `enabled`, `required`, `manifest_path`; unbekannte Felder abgewiesen. Antwort `updated`, `restart_required`, `extension`, `configuration`. Keine Consumer-/Wiki-Ausführung; [Extensiongrenze](EXTENSION_CONTRACT.md#dashboard-documentation-extension-und-wiki). |
| `settings/llm/global` | `provider`, optionale Liste `fallbacks`; unbekannte Felder abgewiesen, Duplikate/Default aus Fallbacks entfernt. Antwort nennt gespeicherte Auswahl, `restart_required`, `environment_override` und `configuration`. |
| `settings/llm/task` | `task` und `config`-Objekt. Zulässige Felder: `provider`, `model`, `base_url`, `timeout`, `system_prompt`, `system_prompt_by_provider`, `max_tokens`, `reasoning_reserve`, `temperature`, `cost_advisory_enabled`, `overqualification_margin_ratio`, `schedule`. Leere Werte entfernen Overrides. Schedule: `active`, `from`/`to` in HH:MM, Provider/Modell und unterstützte Promptoverrides. Feldgrenzen: [Taskeditor](DASHBOARD.md#llm-task-configuration), [Routing](#12-routing-schedules-und-budgets). Ergebnis nennt `updated`, `task`, gespeichertes `cfg`, `warnings`, `configuration` und `restart_required`; `evaluation` ist konfigurierbar, besitzt aber keinen aktiven Product-LLM-Consumer. |
| `dashboard/llm/prompts` / `…/{name}` | Liste `{prompts, scope}`; Einzelread `{name, content, source}` plus explizitem Scope. Ohne Scope aufgelöste Kaskade, mit Scope nur genau dieser Override, dessen Inhalt leer sein darf. POST `content`, optional `scope`, liefert `saved`; DELETE verwendet Scopequery und liefert `deleted`, bei fehlendem Override idempotentes 200. Pfad-/Dateigrenzen und Quellenmetadaten: [Promptvertrag](agents/AGENT_PROMPTS_AND_INSTRUCTIONS.md). |
| `dashboard/llm/models` | Queryfelder siehe Routentabelle; Defaults `threshold=50`, `margin=0.2`, `cost_advisory=true`. Antwort `{provider, models, cache}`; bei Task zusätzliche `reasoning_info`, `suitability`, `cost_advisory`. Lokale Modellauflösung kann Netz-I/O auslösen und bei Fehler leer bleiben; leere Liste oder Katalogeintrag beweist keine Kontoverfügbarkeit. |
| `dashboard/llm/models/refresh`, `…/pricing-info` | Refresh ohne Fachbody schreibt Cache und liefert sein Ergebnis, bei Fehler 502; Pricing-Info liest Cachemetadaten. Keine Modellinstallation oder Änderung des Taskroutings. |
| `dashboard/llm/test-connection` | `provider` und temporäres `config` mit Editorparametern; Response enthält Probevalidität/Details. HTTP 200 beweist keinen erfolgreichen Call: `valid` auswerten. Speichert Taskwerte nicht. |
| `dashboard/self_check`, `dashboard/self-mode/health`, `health` | Self-Check führt aktive Taskproben aus und liefert Einzelchecks plus Health-/Readiness-/Qualificationdarstellung. Self-Mode liefert `total`, `success_rate`, `no_progress_rate`, `avg_rounds`, `avg_duration_s`, `recent_runs`; ohne Daten bleiben Raten `null`. `health` dispatcht den technischen Healthcommand. Keine dieser Antworten ersetzt eine reale Workflow-/D0-Abnahme. |

### Lesende Projektionen und Workflowcommands

Die `dashboard/*`-Leserouten liefern begrenzte Ansichten aus
`DashboardHandler` und `dashboard/data.py`. Folgende Feldgruppen erklären den
fachlichen Inhalt; dynamische Stage-, Provider- und Ereignisdetails bleiben
an ihre vorhandenen Records gebunden. Die [Dashboardreferenz](DASHBOARD.md)
erklärt Anzeige, Auswahl und Grenzen je Bereich.

`dashboard/workflow/{id}` ergänzt `plan_approval` mit `status`, `reason_code`,
`message`, `next_action`, `label_is_authority=false` und bei aktivem Plan dessen
`plan_comment_id`/`contract_hash`. Statuswerte sind `accepted`,
`not_materialized`, `not_recorded`, `no_active_plan` oder `unknown`.
`accepted` entsteht ausschließlich nach erfolgreichem vorhandenem
`resolve_plan_approval`, unabhängig von späteren Labelprojektionen.
Eine zugeordnete frühere ignorierte Zustellung kann unter `last_delivery`
mit Beobachtungszeit und festem Grund stehen; sie ist keine Authorityquelle.
Nicht prüfbare gespeicherte Authority meldet den vorhandenen Resolvercode.
Diese GET-Revalidierung liest SCM-/Authority-Evidence, startet aber weder
Providerproben noch Workflows und verändert keine Labels oder Authority.

| Route unter `/api/v1/dashboard/` | Response und Bedeutung |
|---|---|
| `status` | Lokale Actoren: `service`, `available`, `product_version`, `access`, `technical_health`, `operational_readiness`, `qualification`. Legacyansicht zusätzlich Build-/Modus-/SCM-/Metrik-/Tile-/Score-/Anomaly-/Resumeinformationen und Configstatus. Das Vorhandensein eines Adapters ist kein erfolgreicher Providerzugriff. |
| `metrics` (auch `/api/metrics`) | `counts`, `errors`, `total_ms` nach Commandname aus vorhandenen Metrikquellen; JSON, keine Prometheusexposition. |
| `diagnostics` | Passive gemeinsame Betriebsdiagnose mit vorhandenen Einzelbefunden, Quellen, Aktualität und Abhilfe; `READ_DIAGNOSTICS`, keine Gesamtfreigabe. [Schema und Grenzen](#gemeinsame-passive-betriebsdiagnose-921). |
| `health` | `healthy`, `checks`, `retention`, `technical_health`, `operational_readiness`, `qualification`, `passive`; aktuelle gespeicherte Projektion, keine aktive Providerprobe. Stale/Unknown nach [Healthvertrag](#health--readiness--und-qualification-projektion-693) erhalten. |
| `logs`, `problems`, `dlq` | Logs: `entries`, `level_counts`; Probleme: `problems`, Schwere-/Historienzähler in `counts`; DLQ: `entries`, `count`. Begrenzte/redigierte Ansichten, kein vollständiger Rohlog- oder DBexport und keine Fehlerbehebung durch GET. |
| `security`, `compliance/legend`, `transfer_warnings` | Securityoverview einschließlich `tamper_events`, `otel_calls`, `branch_protection`; `total_events`, `classified_pct` und das bestehende Feld `active_risks` beschreiben OWASP-Zuordnungen im gelesenen Auditfenster (höchstens 500 Ereignisse). `active_risks` zählt Kategorien mit Ereignissen, auch bei normalen Abläufen, keine bestätigten Angriffe. Framework-/Risikoklassenlegende; `{transfer_warnings: […]}` mit konfigurierten Standorten/Warnungen. SCM-403 bleibt abgewiesener Read, kein Nachweis eines bestimmten fehlenden Adminrechts. `branch_protection.permission_diagnostic` ordnet Rolle, Operation und nächsten Schritt gemäß [SCM-Diagnosevertrag](#scm-berechtigungsdiagnosen-897) zu. |
| `workflow`, `workflow/{id}` | Übersicht `{issues, branches, recovered_count}`. Detail: Issue-/Branch-/Statusdaten, `events`, `stages`, `score`, `llm` und gebundene Gate-/AC-/PR-/Outcomeinformationen; 400 bei ungültiger ID, 404 ohne verfügbare Ansicht. `not_attempted`, `manual_pending`, gemergt und Issue geschlossen fachlich unterscheiden. |
| `llm`, `llm/schedule` | Usage/Kosten, `routing`, `routing_schedule`, `history`, `quality`, `api_keys`, `model_cache`, Prozessprovider/-quelle/-status, `configuration`, `activity`. Schedule separat taskbezogen. Keypräsenz und Katalog sind keine erfolgreiche Probe; Current-/Last-Callprojektion ist flüchtig. |
| `quality`, `activity` | Gebundene Quality-/Benchmarkserien beziehungsweise `{activity: […]}` aus SCM-Ereignissen. Origins/Formeln/Policies getrennt vergleichen; kein automatischer Modellwechsel oder Approval durch einen angezeigten Actor. |
| `settings` | `flags`, `configuration`, `extensions`, `llm_global_config`, `llm_config`, `model_cache`, `api_keys`. `llm_global_config.provider`/`fallbacks` sind gespeichert; `effective_provider`, `effective_fallbacks`, `provider_source`, `effective_status`, `restart_required` erklären den gestarteten Prozess. |

`POST /api/v1/issues/{id}/plan`, `…/implement` und `/api/v1/scan` benötigen
keinen zusätzlichen Fachbody; Issue-ID und vorhandene Verträge bestimmen den
Command. Ihre Erfolgsdaten sind das Handlerresultat, gegebenenfalls `null`.
Die oben beschriebenen RFC-9457-Fehler werden als JSON mit `type`, `title`,
`status`, `detail`, `code`, `correlation_id`, `command` und gegebenenfalls
`issue` geliefert; spätere asynchrone Ereignisse über die gebundene Ansicht
prüfen. Der Webhook verwendet unveränderte SCM-JSON-Bytes, Event-/Deliveryheader
und die separate HMAC-Prüfung aus [Webhook-Endpunkt](#webhook-endpunkt).

Beispiel für einen vorhandenen Flagwrite im ausdrücklich autorisierten Setup:

```http
POST /api/v1/settings/flag
Content-Type: application/json

{"name":"<vorhandener-flagname>","enabled":false}
```

Die modusspezifische Authentisierung kommt hinzu; lokale Sessions brauchen
CSRF. Fehlender Name/Enabledwert ergibt 400, eingefrorene Produktion 409,
fehlender Dashboardhandler 503, erfolgreicher Fachwrite 200 mit seinem
Ergebnisobjekt. Ein frei erfundener Flagname ist keine neue Capability.

### Neue Routen und Felder zuordnen

Der bestehende HTTP-Dispatch-/Permissiontest prüft erkennbare Routen und
exakte Rechte. Die Abschnittsbindung umfasst auch die Handler der Payloads.
Neue Request-/Responsefelder, dynamische Routen und geänderte Bedeutung bei
gleicher URL müssen im verursachenden PR source-aware geprüft werden; der
Commit-Impact und ein grüner Routentest beweisen keine vollständige semantische
Felderkennung. [Documentation acceptance](../CONTRIBUTING.md#documentation-acceptance)
verbindet dafür Dokument, Quellenbindung, Prüfungen und begründeten Verzicht.


---

## 19. Konfigurations-Dateien

| Datei | Schema (in `samuel/core/config.py`) | Zweck |
|-------|-------------------------------------|-------|
| `.env` | – | SCM-Token, LLM-Keys, `SAMUEL_API_KEY`, `SLICE_HMAC_KEY` |
| `.env.agent` | – | Self-Mode-Override (laden mit `override=True`) |
| `config/agent.json` | `AgentConfigSchema` | Modus, Polling, Datenverzeichnis, Logging, Context, Planning-Klärungsfrist, Workspace-/Quarantäne-/Signing-/Resumeparameter und Sequence-Validator |
| `config/llm.json` | `LLMConfigSchema` | Laufzeit-Default, Provider-Modelle und geordnete Fallback-Kette |
| `config/llm/defaults.json` | – | Per-Task-Routing, Token-/Temperaturwerte, Prompts und Schedules |
| `config/llm/providers.json` | – | Provider-Katalog, Key-/URL-Metadaten (kein konkurrierender Laufzeit-Default) |
| `config/auth.json` | `AuthRuntimeConfig` in `adapters/api/auth.py` | Genau ein Legacy-/Local-Identity-Zugriffsmodus; sichere Cookies, absolute/idle Sessionfrist, Reauthfrist und Loginlimit |
| `config/compliance.json` | Operatorpersistenz, Consumer `core/ai_act.py` | Gespeicherte Deployment-Risikoklasse; `SAMUEL_RISK_CLASS` hat Vorrang, keine Rechtsqualification |
| `config/path_risk.json` | Adaptervalidierung | Pfadklassen und block/warn; fehlt es, greift bestehender Gate-7-Fallback |
| `config/code_generators.json` | Adaptermetadaten | Erlaubte generierte Importquellen für warn-only Symbolauflösung |
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
Production-Compose bindet Config read-only, Data, separate Log-/Backupziele und
`/samuel-workspaces`; die persistente `.env` wird per `env_file` eingelesen.
Nur der explizite Setup-Override mountet `.env` und Config schreibbar.
Optionale Projekt-/Toolchain-Overlays stammen aus dem bestehenden OCI-Installer;
Source und Workspace sind getrennt. Vollständige Aufrufe: [INSTALL](INSTALL.md#91-oci-erstinstallation-auf-einem-leeren-docker-host-970).
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

Die UI verwendet absolute `/api/...`-Pfade und Cookies mit `Path=/`; das
Beispiel stellt sie daher an der Root eines eigenen Hosts bereit. Ein
Subpathbetrieb ist durch dieses Beispiel nicht belegt. TLS und die
Local-Identity-Cookiekonfiguration gemäß [INSTALL](INSTALL.md) einrichten.

```nginx
location / {
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
Tests auf CPython 3.12 und 3.14. Anschließend prüft er Paketbuild/Lizenz, Ruff,
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
fehlende oder inkompatible Capability liefert einen blockierenden
Auflösungsstatus. Die eigenständige `samuel-documentation`-CLI liest diese
Auswahl nicht; ein externer Ausführungspfad muss den Status ausdrücklich vor
der Aktion prüfen. Änderungen folgen dem D08-Setup-/Restartvertrag.

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
mit eigenem Publication Receipt. Der getrennte öffentliche Extension-/Inventoryvertrag aus #639/#636 ist
implementiert (Abschnitt 22). Seine CLI-/Consumer-/Publisherabnahmen sind
eigenständige Nachweise und keine semantische Vollprüfung freier Prosa.

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

Inlinebilder können zusätzlich `--image-url-template` verwenden. Beide Templates
binden `{head_sha}` und `{path}`; das Bildtemplate muss direkt Bildbytes liefern,
z. B. `https://scm.example/org/repo/raw/commit/{head_sha}/{path}` bei Gitea.
Es gilt nur für relative Markdown-Inlinebilder (etwa PNG oder SVG),
nicht für normale Dateilinks, externe Bild-URLs oder Wiki-Navigation. Ohne
Bildtemplate bleibt das bisherige Quelltemplate wirksam; ein Dateiansichtslink
beweist keine funktionierende Inlineanzeige. Der Publisher kopiert keine
Bilddateien und verwaltet keine zweite Assetablage. Der bestehende Contentdigest
bindet die projizierten Bildlinks; identischer Inhalt bleibt ein No-op.
Vor Veröffentlichung Bildaussage, Bereinigung und Sourcebindings prüfen,
ausschließlich integrierten Main verwenden und die tatsächlich ausgelieferte
Bilddarstellung sowie Remote-Quellbindung nachweisen. Raw-URL, API-Zugänglichkeit
oder erfolgreicher Build allein beweisen keine Browseranzeige.

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

## 25. Repositorywerkzeuge und zusätzliche Projektdateien

Diese Werkzeuge gehören zum bestehenden Entwicklungs-, Release-, Operator-
oder Dokumentationsweg. Ihr Vorhandensein ist kein Nachweis einer ausgeführten
Abnahme. Produkt-Entry-Points stehen in §16; private Evidence, lokale
Operatorquellen und Buildausgaben werden nicht als ausgelieferte Funktionen
oder aktuelle Dokumentation ausgegeben.

| Datei unter `tools/` | Zweck, Wirkung und bestehende Anleitung |
|---|---|
| `control_matrix.py` | `check`, `impact`, `render`: bestehende Capability-/Dokumentverträge und generierte Referenzen. `impact` liest Abschnittsdrift; `impact --base <SHA> --head <SHA>` zeigt alle geänderten getrackten Pfade beider Commits einschließlich ungebundener Quellen und begrenzter Strukturhinweise. Fachliche Wirkungen bleiben zu prüfen; Ablauf und PR-Nachweis stehen in [CONTRIBUTING](../CONTRIBUTING.md#documentation-acceptance). `render` schreibt abgeleitete Dokumente. Kein Quellendigest oder advisory Report beweist semantische Vollständigkeit. |
| `wiki.py` | Lokales `impact`, `check`, `build`, `check-local`; §23. Keine externe Veröffentlichung. |
| `wiki_publish.py` | Expliziter Git-Wiki-Publish über den bestehenden `git_publication`-Adapter; §24. Nur aus geprüftem gemergtem Main veröffentlichen. |
| `release_gate.py` | Produktversion, Tag-/Sourcebindung, Changelog, Wheel/sdist, Locks und Installerassets im Release-Manifest prüfen/materialisieren; [VERSIONING](VERSIONING.md). Kein impliziter Tag oder Gitea-Upload. |
| `container_release.py` | Offlinevertrag sowie getrennte Publisher-Preflight-, Publish- und Recoveryaktionen; [Containerbetrieb](CONTAINER_RELEASE_OPERATIONS.md). Publish besitzt Registrywirkung; Recovery baut/pusht nicht erneut. |
| `container_init.py` | Manifest-/Asset-/Imageprüfung und erstmalige Initialisierung leerer Operatorpfade; vom offiziellen OCI-Installer verwendet. Keine Übernahme alter Authoritydaten. |
| `samuel-container` | Im OCI-Kit gelieferter Shell-Operatorpfad für Install/Start/Stop/Setup, Toolchain und registriertes Projekt; [INSTALL §9.1](INSTALL.md#91-oci-erstinstallation-auf-einem-leeren-docker-host-970). Kein laufender allgemeiner Updater. |
| `container_install_smoke.py` | Bestehende reale Fresh-Install-Prüfung auf einem frischen Dockerhost über den gelieferten Installer; geschützte zweckgebundene Setupquelle, Receipt. Kein SCM-/LLM-/Goldenlauf. |
| `local_release.py` | Checkout-Kompatibilitätswrapper für das installierte `samuel-release`; [lokaler Releaseweg](INSTALL.md). Die Implementierung bleibt `samuel.local_release`. |
| `rollout_evidence.py`, `preflight_rollout_evidence.py` | Offlineprüfung vorhandener geschlossener Rolloutreceipts und Fallsemantik; [Score-ADR](adr/0399-score-authority.md) und [Preflight-ADR](adr/0620-preflight-gate-state.md). Starten keinen realen Workflow und erfinden keinen PASS. |
| `update_container_locks.py` | Exakter uv-/Python-/Cutoff-Vertrag zum bewussten Regenerieren der Containerlocks; [Containerbetrieb](CONTAINER_RELEASE_OPERATIONS.md#abhängigkeiten-aktualisieren). Netzwerkauflösung und geänderte Locks verlangen Review. |
| `verify_distribution_license.py` | Apache-2.0-/Metadatenprüfung der gebauten Wheel-/sdist-Dateien; Required CI und [Test-/Qualification-Runbook](runbooks/TEST_AND_QUALIFICATION_RUNBOOK.md). |
| `run_pip_audit.py` | Bounded Transportretry der bestehenden Dependencyprüfung; ein echter Vulnerabilitybefund bleibt Fehler. Kein Qualification- oder Release-PASS durch einen Retry. |
| `build_ci_runner_image.sh` | Bestehender gebundener lokaler Runnerimage-Build; [CI-Runnerbetrieb](CI_RUNNER_OPERATIONS.md). Separater kontrollierter Infrastrukturzugriff, keine Registrypublikation oder Runtimebot-Authority. |
| `screenshot_dashboard.py`, `walkthrough_dashboard.py` | Historische Playwright-/Chromium-Demohilfen: Tab-Screenshots bzw. Tourvideo. Keine aktuelle Login-/Rolequalification; die Tour verwendet einen festen alten Issue-Drilldown. Ausgaben vor Veröffentlichung auf Instanz, Stand und sensible Inhalte prüfen. |
| `build_demo_gif.py` | Pillow-Slideshow vorhandener Screenshots; Bildexport, keine Funktionsabnahme. Historische Bilder bleiben als solche gekennzeichnet. |
| `build_readme_doc.py` | Markdown-/Playwright-Hilfe für HTML/PDF-Export mit optionalen Bild-/Videobytes; kein eigener Current-State-Resolver. Der Export ist nur so aktuell wie sein gebundener Eingangsstand. |

`install.sh` bleibt der Entwicklungscheckout-Installer. `Dockerfile`, Compose,
`containers/*`, Containerlocks und `pyproject.toml` bestimmen Paket-/Image-/
Operatorinputs; `.gitea/workflows/*` bestimmen Required CI und Referenzpublisher.
Ausgelieferte JSON-Konfiguration ist in §19 beschrieben. Tests/Fixtures prüfen
ihre jeweilige Grenze, nicht beliebige reale Provider oder Humanhandlungen.
`docs/demo/*` ist historische Bildevidence; Archive, Audits, Changelog und
datierte Statusabschnitte behalten ihre eigenen Revisionen. Nicht getrackte
lokale Evidence und ignorierte `.env`-/Runtime-/venv-/Cache-/Buildverzeichnisse
liegen außerhalb des ausgelieferten Quell- und Dokumentvertrags.

Weitere Wurzeldateien haben begrenzte Aufgaben: `.env.example` ist eine
Platzhaltervorlage für die externen Operatorquellen; `.envrc` aktiviert die
Entwicklungs-venv und lädt eine lokale `.env` über direnv. `.gitignore` und
`.dockerignore` steuern Tracking beziehungsweise Build-Kontext, ersetzen aber
keine Secretprüfung oder Authoritygrenze. `MANIFEST.in` nimmt Installer- und
Operatorassets in das Sourcepaket auf; `samuel/py.typed` kennzeichnet die
Typinformationen. `.github/FUNDING.yml` enthält ausschließlich Fundingziele.
`docs/examples/findings.sarif` ist ein Formatbeispiel, kein aktueller Scan- oder
Qualificationnachweis. Schema-/Rolloutdateien unter `docs/` werden von den
bestehenden Contracts und Offlineprüfern konsumiert; eine Schema-Prüfung
ersetzt keinen neuen realen Lauf.

---

*Technischer Quellenabgleich: 2026-10-10, Main `b59b1fc3def41ce73fef1cf29841a2e6ffbe8db7`.
Ungemergte Fixes und ihre Candidate-Evidence sind im aktuellen Statusindex
separat ausgewiesen. Pflege-Regel: Code und betroffene Doku im gleichen PR.*

---

## Lizenz

Der gesamte Repository-Inhalt steht unter Apache-2.0. Die maßgebliche
Root-Datei `LICENSE` enthält den Lizenztext; `pyproject.toml` deklariert denselben Status
maschinenlesbar als SPDX-Ausdruck und nimmt die Lizenzdatei in Wheel und sdist
auf. Es gibt keine separate Entitlement-Lizenz oder Premium-Laufzeitstufe.
