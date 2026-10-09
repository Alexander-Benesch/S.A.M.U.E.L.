# S.A.M.U.E.L. — Generierte Runtime-Referenz

> Diese Datei wird durch `python tools/control_matrix.py render` aus Code und
> ausgelieferter Konfiguration erzeugt. Nicht manuell bearbeiten. Sie beschreibt
> verfügbare und ausgelieferte Fakten; operatorseitige Overrides bestimmen den
> effektiv aktiven Zustand und müssen für den konkreten Betrieb separat nachgewiesen
> werden. Wirksamkeitsbewertungen bleiben in `docs/CAPABILITY_MATRIX.md`.

## Quellen- und Statusmodell

- **Verfügbar:** Registry, Schema oder produktiver Code stellt die Fähigkeit bereit.
- **Konfiguriert:** eine ausgelieferte Config beziehungsweise ein Workflow wählt Werte.
- **Effektiv aktiv:** ausgewähltes Profil plus operatorseitige Overrides; nicht aus dem
  Repository allein ableitbar.

Ein Code-Default wird ausdrücklich als Default und nicht als ausgelieferter oder
effektiv aktiver Wert ausgegeben.

## Runtime-Inventar

| Artefaktklasse | Verfügbar im Code |
|---|---:|
| Commands | 20 |
| Events | 104 |
| Ports | 31 |
| Slices | 31 |
| Adapter-Gruppen | 13 |
| Core-Module einschließlich Paketmodul | 44 |

## AC-Tags

Verifier-Registry und Planner-Zulassung müssen exakt dieselbe Menge enthalten:

`DIFF, EXISTS, GREP, GREP:NOT, IMPORT, MANUAL, TEST`

| Tag | Planner | Plan-Dry-Run | Gebundene Beobachtung | Direkte Kompatibilitätsfamilien |
|---|---|---|---|---|
| `[DIFF]` | zugelassen | ausgeführt | `hallucination_free` | `syntax_valid`, `hallucination_free` |
| `[EXISTS]` | zugelassen | ausgeführt | `hallucination_free` | `syntax_valid`, `hallucination_free` |
| `[GREP]` | zugelassen | deferred | `scope_compliant` | `scope_compliant` |
| `[GREP:NOT]` | zugelassen | deferred | `scope_compliant` | `scope_compliant` |
| `[IMPORT]` | zugelassen | deferred | `syntax_valid` | `syntax_valid` |
| `[MANUAL]` | zugelassen | deferred | keine | keine |
| `[TEST]` | zugelassen | deferred | `test_pass_rate` | `test_pass_rate` |

Die Plan-Komplexitätsheuristik zählt ausschließlich: `DIFF`, `EXISTS`, `GREP`, `GREP:NOT`, `IMPORT`, `TEST`.

`GREP` und `GREP:NOT` sind repositoryweite Textprüfungen über die unterstützten
Code-/Konfigurationsdateien des gebundenen Candidate-Checkouts. Sie besitzen
kein Pfadargument. Nach einem gequoteten Pattern sind nur Zeilenende oder ein
eindeutiger Beschreibungstrenner zulässig; ein scheinbarer Pfadsuffix blockiert
den neuen Contract vor `PlanPosted`. Der äußere Pattern-Delimiter darf doppelt
oder einfach sein; enthält das Pattern eine Art Anführungszeichen, wird die andere
außen verwendet. Backslash-Escapes für den äußeren Delimiter sind nicht Teil der
Grammatik. Enthält das Pattern beide Arten oder ist Verhalten dateigebunden, ist
ein fokussiertes `[TEST]`-Kriterium zu verwenden.

Ein `[TEST]`-Argument ist entweder ein sicherer logischer Testname oder ein
sicherer Pytest-Node-ID mit mindestens einem `::`-Segment. Bloße Dateipfade
sind kein portabler Selektor für die unterstützten projektspezifischen Runner
und werden bereits vor `PlanPosted` abgelehnt. Es gibt keinen stillen
Full-Suite- oder Runner-Fallback.

Zusätzlich muss der Selektor zur vor dem Plan aufgelösten einzelnen
Runner-Authority passen. Planning prüft ohne Testausführung: explizites
Control-Plane-`test_cmd` vor Marker, vorhandenes Binary beziehungsweise
Python-Modul und bekannte Selektorgrammar. Unittest verlangt einen gepunkteten
Python-Namen; Pytest-Node-IDs sind nur mit einem Pytest-Runner und direkter
Positionsbindung von `{test}` zulässig. Fehlende oder inkompatible Readiness
blockiert nach dem einzigen Retry vor `PlanPosted`. Doctor verwendet dieselbe
Auflösung; keiner der beiden Pfade installiert, ersetzt oder startet einen Runner.

## Gates und ausgelieferte Profile

### Verfügbare Gates

| ID | Registry-Name |
|---|---|
| `1` | BranchGuard |
| `2` | PlanComment |
| `3` | MetadataBlock |
| `5` | DiffNotEmpty |
| `6` | SelfConsistency |
| `7` | ForbiddenPathGuard |
| `7b` | ContractScope |
| `8` | SliceGate |
| `9` | PythonSyntax |
| `11` | ACVerification |
| `12` | AcceptanceReadiness |
| `13a` | BranchFreshness |
| `13b` | DestructiveDiff |

### Konfigurierte Profile

| Profil | Policy | Required | Optional | Disabled | Parameter |
|---|---|---|---|---|---|
| `audit` | `2026-10-08.audit-preflight.v4` | `1`, `2`, `3`, `5`, `6`, `7`, `7b`, `8`, `9`, `11`, `12`, `13a`, `13b` | — | — | `max_diff_bytes=2000000`, `max_quality_file_bytes=1000000` |
| `default` | `2026-10-08.preflight.v4` | `1`, `2`, `3`, `7`, `7b`, `8`, `9`, `11`, `13b` | `5`, `6`, `12`, `13a` | — | `max_diff_bytes=2000000`, `max_quality_file_bytes=1000000` |
| `self` | `2026-10-08.self-preflight.v4` | `1`, `2`, `3`, `7`, `7b`, `8`, `9`, `11`, `13b` | `5`, `6`, `12`, `13a` | — | `max_diff_bytes=2000000`, `max_quality_file_bytes=1000000` |

Ausgeliefert wird ausschließlich der gebundene Gate-Autoritätspfad.
Ein Authority-Schalter und ein Legacy-Profil existieren nicht mehr; veraltete
Authority-Settings blockieren den Bootstrap. Nicht-Self-Läufe erlauben
`default` oder `audit`; Self erzwingt unabhängig von `SAMUEL_GATES_PROFILE`
das eigene Profil. Andere explizite Werte blockieren vor dem Bus-Wiring.
Ein Eintrag in `required` belegt allein noch keine Subject-Bindung oder Wirksamkeit;
dafür ist die Capability-/Wirksamkeitsmatrix maßgeblich.

GateResult-Schema `2`, Observation-Schema `2`. Statische Preflight-Gates: `7`, `7b`, `8`, `9`, `13a`, `13b`. Bei einem Required-Preflight-Fehler werden alle nachgelagerten internen und externen Gates als `skipped_precondition` geführt; Candidate-Verifikation wird nicht gestartet. Jedes v2-Resultat bindet außerdem einen kanonischen Reason-Code, Required-/Optional-Authority und denselben EvaluationSubject.

## Schwellen und Gewichtungen

| Wert | Herkunft | Status |
|---|---|---|
| Eval-Baseline `0.8` | `EvalSchema` | unverdrahteter Kompatibilitätscode; keine Runtime-Autorität |
| Eval-Baseline `0.8` | `config/eval.json` | passive Scoring-Konfiguration; weder Subject-Digest noch Runtime-Autorität |

Scoring-Policy `2026-08-28.v1`, Formel `bound-evidence.v1`. Ausgelieferte Gewichte: `hallucination_free=0.3`, `scope_compliant=0.2`, `syntax_valid=0.2`, `test_pass_rate=0.3`.

TEST-Runner-Policy `2026-08-29.runner.v1`: `test_cmd=None`, `test_timeout=60` Sekunden. Sie stammt aus dem Bootstrap-Control-Plane-Snapshot und ihr Runner-Teil bindet den EvaluationSubject-Policy-Digest; Candidate-Konfiguration ist keine Policyquelle.

Candidate-Prozessumgebung `verifier-sterile.v1`: ausschließlich `HOME`, `LANG`, `LC_ALL`, `NO_COLOR`, `PATH`, `PYTHONUNBUFFERED`, `PYTHONUTF8`, `TEMP`, `TMP`, `TMPDIR`, `TZ`, `XDG_CACHE_HOME`, `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_RUNTIME_DIR`, `XDG_STATE_HOME`. HOME/TMP/XDG werden je Prozess managerseitig neu erzeugt; PATH besteht aus Interpreter-, festen System- und gegebenenfalls absolut konfigurierten Runner-Verzeichnissen. Parent-Environment und Benutzerprofile werden nicht übernommen. Das ist Environment-Härtung, keine Dateisystem-, Prozess- oder Netzwerksandbox.

Unverdrahtetes Kompatibilitäts-Fail-Fast (nicht autoritativ): `syntax_valid`.

Gate 4 und Gate 10 sind aus Registry, Schema und Profilen entfernt.
Ausschließlich die Required-Gates des gewählten Profils treffen die
Freigabeentscheidung.

## Worktree-Lifecycle

Ein gemeinsamer `IWorkspaceManager` stellt zwei Profile bereit: einen
branch- und rungebundenen, mutierbaren Run-Worktree sowie einen detached
Verifikations-Worktree für den exakten Candidate-Head. Gebundenes Healing
verwendet denselben aktiven Run-Worktree reentrant; Gate 11 verwendet das
Verifikationsprofil. Der Manager erzwingt Git-Ziel-, Ownership-, Kapazitäts-
und Quarantänegrenzen, ist aber ausdrücklich keine Prozesssandbox.

Ausgeliefertes `work_dir`: `../samuel-workspaces`; konservative Buchung `128 MiB`, Mindestfreiraum `512 MiB`, Quarantänegrenzen `8` Einträge / `2048 MiB`; Operatorfrist `168 Stunden`. Der relative Pfad wird vom Installationsroot aus aufgelöst und muss auf einem lokalen Dateisystem außerhalb von Repository und `data_dir` liegen. Effektive Betreiberwerte sind separat nachzuweisen.

## Persistente Laufzeitartefakte

| Pfad | Inhalt | Herkunft |
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

Eine Dateiexistenz belegt noch keine ausreichende Retention, Neustartfestigkeit
oder Backup-/Restore-Policy. Stufe 5b liefert Report, Managed Backup und Replay;
das 5c-Fundament ist ausschließlich operatorgeführt und ausgeliefert deaktiviert.

## Retention Stufe 5b und deaktiviertes 5c-Fundament

Schema `1.0`, ausgeliefertes Profil `eu_operational`, Operatorrolle `operator`, Managed-Backup-Grenze `data/backups`. Die globale Notabschaltung ist im State gespeichert und nicht Teil eines Policy-Digests. Alle ausgelieferten Kategorien bleiben `report_only`; es gibt keinen Scheduler und keine aktive Löschkategorie.

| Profil | Rolle | Kategorie-Untergrenzen |
|---|---|---|
| `eu_ai_act_high_risk_support` | `declared_provider_or_deployer` | `audit_logs=P6M` |
| `eu_operational` | `operator` | keine |

| Kategorie | Speicher/Quelle | Modus | Zeitraum | Anker |
|---|---|---|---|---|
| `audit_logs` | `audit_jsonl` / `configured_jsonl_sinks` | `report_only` | `P1Y` | `last_parseable_event_ts` |
| `authority_leases` | `sqlite_table` / `authority_leases` | `report_only` | `None` | `expires_at` |
| `authority_metadata` | `sqlite_table` / `authority_metadata` | `report_only` | `None` | `updated_at` |
| `authority_records` | `sqlite_table` / `authority_records` | `report_only` | `None` | `updated_at` |
| `evaluation_terminals` | `sqlite_table` / `evaluation_terminals` | `report_only` | `P90D` | `observed_at` |
| `healing_claims` | `sqlite_table` / `healing_claims` | `report_only` | `P1Y` | `updated_at` |
| `identity_metadata` | `sqlite_table` / `identity_metadata` | `report_only` | `None` | `updated_at` |
| `identity_principal_roles` | `sqlite_table` / `identity_principal_roles` | `report_only` | `None` | `principal_id` |
| `identity_principals` | `sqlite_table` / `identity_principals` | `report_only` | `None` | `updated_at` |
| `identity_sessions` | `sqlite_table` / `identity_sessions` | `report_only` | `None` | `expires_at` |
| `identity_tokens` | `sqlite_table` / `identity_tokens` | `report_only` | `None` | `expires_at` |
| `legacy_imports` | `sqlite_table` / `legacy_imports` | `report_only` | `None` | `imported_at` |
| `llm_budget_attempts` | `sqlite_table` / `llm_budget_attempts` | `report_only` | `None` | `updated_at` |
| `managed_backups` | `managed_backup` / `managed_backups` | `report_only` | `P30D` | `created_at` |
| `observations` | `sqlite_table` / `observations` | `report_only` | `P1Y` | `observed_at` |
| `operation_intents` | `sqlite_table` / `operation_intents` | `report_only` | `P1Y` | `updated_at` |
| `planning_clarifications` | `sqlite_table` / `planning_clarifications` | `report_only` | `None` | `updated_at` |
| `quality_metrics` | `sqlite_table` / `quality_metrics` | `report_only` | `None` | `updated_at` |
| `quarantine_worktrees` | `quarantine_worktree` / `workspaces` | `report_only` | `P7D` | `updated_at` |
| `reconcile_entries` | `sqlite_table` / `reconcile_entries` | `report_only` | `P1Y` | `updated_at` |
| `restore_operations` | `sqlite_table` / `restore_operations` | `report_only` | `P1Y` | `completed_at` |
| `retention_category_states` | `sqlite_table` / `retention_category_states` | `report_only` | `None` | `updated_at` |
| `retention_executions` | `sqlite_table` / `retention_executions` | `report_only` | `None` | `executed_at` |
| `run_projections` | `sqlite_table` / `run_projections` | `report_only` | `P90D` | `updated_at` |
| `schema_migrations` | `sqlite_table` / `schema_migrations` | `report_only` | `None` | `applied_at` |
| `score_derivations` | `sqlite_table` / `score_derivations` | `report_only` | `P90D` | `derived_at` |
| `workflow_budget_admissions` | `sqlite_table` / `workflow_budget_admissions` | `report_only` | `None` | `updated_at` |
| `workflow_checkpoints` | `sqlite_table` / `workflow_checkpoints` | `report_only` | `P90D` | `updated_at` |
| `workspaces` | `workspace_registry` / `workspaces` | `report_only` | `None` | `updated_at` |

`samuel retention dry-run --json` berechnet absolute UTC-Cutoffs und
Schutzgründe ohne Mutation. Für die einzige registrierte Strategie
`score_derivations` bindet der Report zusätzlich Cutoff, Anker, die
Plan-Schemaserie `retention-execution-plan.v1`, den klassifizierten
Schutzvertrag und privacy-sichere Objektidentitäten des aktuell
ungeschützten Kandidatensatzes in einem Plan-Digest. `approve` bindet eine
Kategorie an ihre aktuellen Kategorie- und Profil-/Rollendigests. `activate`
bindet außerdem den zulässigen absoluten Cutoff an den serverseitigen
Aktivierungszeitpunkt. `execute` revalidiert diese Grantbindung sowie Katalog,
Klassifikation und Kandidaten unmittelbar in der Löschtransaktion. Ein
historischer Receipt kann identitätsgeprüft ohne neue Wirkung auch nach Stop-
oder Policyänderungen gelesen werden. `execute`, `suspend`, `pause` und
`unpause` sind explizite Operatoraktionen; kein Hintergrundpfad ruft Vollzug
auf. `backup` verwendet die
SQLite Backup API innerhalb der verwalteten Grenze. `replay-scores`
publiziert keine Events und aktualisiert keine Quality-EWMA. Diese
Betriebsdefaults sind keine universellen Rechtsfristen oder
Konformitätszusage; externe Backupkopien bleiben Betreiberverantwortung.

## Workflowübergänge

| Workflow | Gebundener Gate-Autoritätspfad |
|---|---|
| `autonomous` | `IssueReady → PlanIssue`<br>`PlanValidated → Implement` (`plan_without_clarification`)<br>`PlanApproved → Implement` (`plan_with_clarification`)<br>`CodeGenerated → CreatePR`<br>`HealingSuggested → Implement`<br>`PRCreated → Review` |
| `chat` | `IssueReady → PlanIssue`<br>`PlanApproved → Implement`<br>`CodeGenerated → CreatePR`<br>`HealingSuggested → Implement` |
| `night` | `IssueReady → PlanIssue`<br>`PlanValidated → Implement` (`plan_without_clarification`)<br>`PlanApproved → Implement` (`plan_with_clarification`)<br>`CodeGenerated → CreatePR`<br>`HealingSuggested → Implement` |
| `patch` | `IssueReady → PlanIssue`<br>`PlanValidated → Implement` (`plan_without_clarification`)<br>`PlanApproved → Implement` (`plan_with_clarification`)<br>`CodeGenerated → CreatePR`<br>`HealingSuggested → Implement` |
| `self` | `IssueReady → PlanIssue`<br>`PlanApproved → Implement`<br>`CodeGenerated → CreatePR`<br>`HealingSuggested → Implement` |
| `standard` | `IssueReady → PlanIssue`<br>`PlanApproved → Implement`<br>`CodeGenerated → CreatePR`<br>`HealingSuggested → Implement`<br>`PRCreated → Review` |
| `watch` | `IssueReady → PlanIssue`<br>`PlanApproved → Implement`<br>`CodeGenerated → CreatePR`<br>`HealingSuggested → Implement` |

## Watch-Concurrency

Busmodus: **synchronous**. Acquire: `WatchHandler._try_acquire`. Release: `WatchHandler._release`.

Der Slot wird in zwei synchronen Dispatchpfaden per `try/finally` freigegeben. Es
existiert keine Terminalevent-Subscription für diese Freigabe. Die ausführliche
Architekturbeschreibung in §5.4 wird aus demselben geprüften Vertrag erzeugt.
Der Scan dispatcht **sequenziell**, die Koordination ist
**prozesslokal**, und alle ausgelieferten Profile erlauben
ausschließlich `max_parallel=1`. Höhere Werte
blockieren den Start; mehrere Prozesse werden nicht koordiniert.

## Quellenbindung

- `samuel/core/commands.py`
- `samuel/core/events.py`
- `samuel/core/ports.py`
- `samuel/core/workspaces.py`
- `samuel/core/config.py::EvalSchema`
- `samuel/core/config.py::GatesConfigSchema`
- `samuel/core/config.py::resolve_gate_profile`
- `samuel/core/config.py::resolve_watch_parallelism`
- `glob:samuel/slices/*/__init__.py`
- `glob:samuel/adapters/*/__init__.py`
- `samuel/slices/ac_verification/handler.py`
- `samuel/core/acceptance.py::parse_grep_criterion_argument`
- `samuel/core/acceptance.py::parse_test_criterion_argument`
- `samuel/core/process_environment.py`
- `samuel/core/test_runner.py`
- `samuel/slices/planning/handler.py::_VALID_AC_TAGS`
- `samuel/slices/planning/handler.py::_COMPLEXITY_PFLICHT_TAGS`
- `samuel/slices/scoring/handler.py::_TAG_FAMILIES`
- `samuel/slices/scoring/handler.py::_HALLUCINATION_TAGS`
- `samuel/slices/evaluation/bound_scoring.py`
- `samuel/slices/pr_gates/gates.py`
- `samuel/core/gate_metadata.py`
- `samuel/slices/pr_gates/handler.py`
- `glob:config/gates*.json`
- `glob:config/workflows/*.json`
- `config/eval.json`
- `config/agent.json`
- `config/audit.json`
- `config/privacy.json`
- `samuel/core/retention.py`
- `samuel/core/bootstrap.py::bootstrap`
- `samuel/slices/resume/handler.py`
- `samuel/adapters/state/sqlite.py`
- `samuel/adapters/state/legacy.py`
- `samuel/adapters/workspace/git.py`
- `samuel/core/git.py::commit_tree_transaction`
- `samuel/slices/evaluation/handler.py::EvaluationHandler.observe`
- `samuel/slices/run_projection/handler.py`
- `samuel/slices/healing/bound.py`
- `samuel/slices/quality_metrics/handler.py`
- `samuel/slices/dashboard/data.py`
- `samuel/slices/watch/handler.py::WatchHandler._poll_scm_activity`
- Vertrag: `docs/capabilities/document-contract.json::runtime-reference`
