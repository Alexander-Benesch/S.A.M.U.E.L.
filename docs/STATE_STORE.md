# SQLite-State: Zweck, Datenmodell und Betrieb

[Produkt](../README.md) · [Technischer Überblick](TECHNICAL_OVERVIEW.md) · [Dokumentwege](README.md)

Diese Advanced-Referenz richtet sich an Entwickler und Operatoren, die
nachvollziehen müssen, welche Daten einen Lauf überleben und welche
Wiederherstellungsmaßnahmen zulässig sind. Der Referenz-Worker verwendet den
lokalen Adapter `samuel/adapters/state/sqlite.py` mit Schema **v10** und eine
separate Workspace-Registry. Die [Quellenbindung](capabilities/document-contract.json)
verknüpft diese Erklärung mit den tatsächlichen Consumern und Prüfungen.
Das SQL-Fragment wird aus der vorhandenen Schemaanlage erzeugt und gegen
einen tatsächlich angelegten Wegwerfstore geprüft. Produktive Datensätze und
Secrets werden nicht exportiert.

## Vom Auftrag zum wiederauffindbaren Ergebnis

Ein Issue soll beispielsweise eine freigegebene Änderung an einem Zielprojekt
erhalten. Der State hält die dafür erforderlichen Bindungen und Zwischenstände;
SCM, Git, Konfiguration und Audit behalten ihre eigenen Zuständigkeiten.

| Schritt | Schreib- und Lesepfad | Was daraus folgt |
|---|---|---|
| Auftrag und freigegebener Plan | Fachconsumer speichern und prüfen gebundene Records über `IAuthorityStateStore`; SCM bleibt Quelle des Issues und seiner menschlichen Entscheidungen. | Eine Issue-Nummer oder gespeicherte Freigabe allein autorisiert keinen beliebigen Candidate. Quellen-, Plan- und Subjectbindungen müssen passen. |
| Arbeit am Candidate | Der Workspace-Manager registriert den Git-Worktree in seiner eigenen Datenbank. Authority-Leases und CAS schützen die jeweiligen gebundenen Operationen. | Prozessowner, Lease, Git-Head und Humanentscheidung haben unterschiedliche Bedeutung. Eine kopierte Workspacezeile übernimmt keinen lebenden Prozesslock. |
| Externe Wirkung vorbereiten | Ein `operation_intent` hält Absicht und Bindung vor dem Effekt; Ergebnis beziehungsweise Postcondition werden später reconciliiert. | Nach einem Verbindungsabbruch kann der Effekt bereits eingetreten sein. Ein unklarer Ausgang erlaubt keinen blinden Wiederholungsversuch. |
| Wirkung beobachten | Evaluation schreibt gebundene Observations und daraus getrennte, versionierte Scoreableitungen. Audit schreibt zusätzlich Ereignisevidence in die JSONL-Kette. | Beobachtung, Score und Audit sind unterschiedliche Nachweise. Ein hoher Score erteilt weder Review- noch Mergefreigabe. |
| Ergebnis anzeigen | `RunProjectionHandler` materialisiert redigierte Runansichten über `IRunProjectionStore`; Dashboard und Diagnose lesen diese Projektionen. | Eine Anzeige kann fehlen oder veraltet sein. Rekonstruktion verbessert die Sicht, ersetzt aber keine Authorityprüfung oder fehlende Originalevidence. |
| Nach Unterbrechung prüfen | Gebundene Finalisierungs-Checkpoints, aktuelle Quellen und Workspacezustand werden zusammen bewertet. | Fortgesetzt werden nur die unterstützten technischen Grenzen; dies ist kein allgemeines Resume einzelner LLM-Runden, Prompts oder Tokens. |

Die vollständigen fachlichen Records und Tabellen folgen unter
[Tabellen und Funktion](STATE_STORE.md#tabellen-und-funktion), die getrennten Gitdaten unter
[Workspace-Registry](STATE_STORE.md#zweite-datenbank-workspace-registry). Auditdarstellung und
Durabilitygrenzen stehen in der [Auditreferenz](README_technical.md#14-audit-trail).

## Neustart, Fehler und Recovery zuerst einordnen

Ein Prozessneustart verwendet bestehenden persistenten State. Ein Restore
ersetzt dagegen einen Datenstand und benötigt die eigene Instanz-/Epoch- und
Quellenreconciliation. Eine frische Releaseinstallation beginnt nochmals mit
anderen Übernahmegrenzen. Diese drei Vorgänge sind nicht austauschbar.

| Beobachtung / Aufgabe | Passender vorhandener Weg | Grenze |
|---|---|---|
| Nach einem Prozessabbruch bekannte Checkpoints ansehen | `samuel --config <config-dir> resume list --json`, danach `resume inspect <key> --json` | Passiver Diagnosepfad ohne Workflow-/Providerbootstrap; fehlende oder inkompatible State-/Lockdateien bleiben Fehler. |
| Statepfad, Schema und Zähler diagnostizieren | `samuel --config <config-dir> state status --json` beziehungsweise `state dump --json` | Kein Rohpayloadexport. Dieser normale Storezugang kann initialisieren/migrieren und besitzt nicht den Read-only-Vertrag von `resume list/inspect`. |
| Anzeige rekonstruieren | `state reproject-runs` schreibt vorhandene Runprojektionen neu; Audit-`replay --issue <n>` rekonstruiert eine ausgegebene Timeline. | Beide erteilen keine neue Freigabe. `replay --publish` verwendet einen frischen No-op-Bus; das davon getrennte `dlq replay` publiziert dagegen auf den aktiven Bus und kann Subscriberwirkungen auslösen. |
| Checkpoint fortsetzen, aufgeben oder bereinigen | `resume attempt`, `resume abandon`, `resume cleanup` gemäß [CLI-Vertrag](README_technical.md#16-cli-reference) | Mutierende Aktionen mit Bootstrap und bestehenden Guards; Diagnoseerfolg ist keine Dispatchfreigabe. |
| Konsistentes SQLite-Backup erstellen | `samuel --config <config-dir> retention backup --json` | Managed Backup des Runtime-State; Workspace-Registry, Git-Artefakte und Audit-Key/Kette separat berücksichtigen. |
| Datenstand zurückspielen | `state restore`, anschließend die gebundene `reconcile-*`-Folge | Restore-Sentinel und Reconcile-STOP verhindern eine stille Wiederverwendung alter Authority. Unresolved bleibt offen; Identity-Recovery kann gesondert erforderlich sein. |
| Epoch-/Witnessabweichung oder falscher Auditkey | Betroffene Quellen und ursprüngliche Bindung sichern und prüfen | Keine manuelle Epochsenkung, isolierte Witnessreparatur oder Neusignierung alter Auditbytes, um einen PASS herzustellen. |
| Release wechseln oder bewusst frisch installieren | [Kanonischer INSTALL-Vertrag](INSTALL.md#121-ehrliche-updategrenze-der-alpha-serie) | Selektive Konfigurationsübernahme ist kein vollständiger Alt-State-Restore oder qualifizierter Cross-Release-Upgrade. |

Details zu Fehlergrenzen und Aufbewahrung stehen unter
[Konsistenz und Diagnose](STATE_STORE.md#konsistenz-diagnose-und-öffentliche-ausgabe) und
[Migration, Backup und Restore](STATE_STORE.md#migration-backup-restore-und-aufbewahrung).
Retention unterscheidet Inventur, gebundene Freigabe und tatsächliche Löschung;
der ausgelieferte globale STOP und `report_only` bleiben maßgeblich.

## Zweck und Speichergrenzen

| Aufgabe | Inhalt | Verwendung / Grenze |
|---|---|---|
| Authority-State | Gebundene Records, Leases, Intents, Checkpoints, Budgetzulassungen/-versuche und Identity | Bestehende Fachcontracts entscheiden zulässige Wirkungen; bloße Existenz eines Records erteilt keine Freigabe |
| Beobachtung/Ableitung | Evaluation-/SCM-/Qualitätsbeobachtungen, terminale Resultate, versionierte Scoreableitungen | Evidence und advisory Bewertung; keine neue Review-/Healing-/Required-Gateauthority aus einem Score |
| Projektion | Rotationsunabhängige Runhistory und Health-/Readiness-/Qualificationdarstellung | Begrenzte Dashboard-/Diagnosesicht; stale/rebuild möglich, keine Authorityquelle |

Ports: `samuel/core/ports.py`; Records: `samuel/core/state.py` und
`samuel/core/identity.py`. Der Adapter stellt diese Ports über denselben Store
bereit. JSONL bleibt ergänzende Audit-Evidence. Operatorpolicy steht weiterhin
in `config/*.json`, SCM-Issues/PRs beim SCM, Projektcode im registrierten
Projekt/Worktree und Providersecrets in der externen Secretquelle. Es gibt
keinen universellen SQLite-Cache für rohe LLM-Prompts/-Antworten.

## Standort und Dateien

`config/agent.json::data_dir` bestimmt das Verzeichnis, Default `data/`.
Relative Pfade werden neben dem ausgewählten Configverzeichnis aufgelöst,
nicht beliebig aus dem Aufrufverzeichnis.

| Datei | Aufgabe |
|---|---|
| `samuel-state.sqlite3` | Hauptdatenbank, `PRAGMA user_version=10`, 26 Tabellen |
| `samuel-state.sqlite3-wal`, `samuel-state.sqlite3-shm` | SQLite-WAL/Koordination, soweit angelegt; keine separaten Fachstores |
| `samuel-state-authority.json` | Externer Instanz-/Epoch-Witness gegen stillen Rollback/inkonsistenten Restore |
| `.samuel-state-authority.lock` | Prozessübergreifende Witnesskoordination |
| `.samuel-state-lifecycle.lock` | Lifecycle-/Backup-/Restorekoordination |
| `samuel-state-restore.json` | Sentinel für unterbrochenen bzw. unreconciliierten Restore |

Die tatsächliche Linux-Mountklassifikation stammt aus `/proc/self/mountinfo`.
Nur die vorhandene lokale Allowlist wird akzeptiert; NFS/CIFS/SSHFS/Unbekannt
werden abgelehnt. Frische Datenverzeichnisse erhalten 0700, DB-/Witness-/Locks
die privaten Modi des jeweiligen Pfads. Unsichere/symlinkgebundene Pfade
werden nicht still sichere Authority. WAL und Foreign-Key-Prüfung gehören
zum Connection-/Schemavertrag. Lokaler Speicher ist keine Verschlüsselung,
Sandbox oder externe Trust Root.

## Tabellen und Funktion

Die Tabelle erklärt Inhalt und Consumer. Das generierte DDL darunter enthält
sämtliche Spalten/Typen, Primary-/Unique-/Foreign Keys, CHECKs und explizite
Indizes. `payload_json` ist ein versionierter Fachrecord, keine beliebige
Rohdatenablage; seine Felder bestimmen die referenzierten Fachtypen.

| Tabelle | Inhalt | Funktion / Consumer |
|---|---|---|
| `schema_migrations` | Version und Anwendungszeit | Technische Schemahistorie, kein Release-/Qualification-PASS |
| `authority_metadata` | Singleton: Instanz, Epoch, Reconcilegrund, Restoreoperation/-Highwater, Retention-STOP | Storeweite Wirkungssperren; alte Authority nach Restore/Witnessabweichung nicht still erneut zulassen |
| `authority_records` | Recordkey/-kind, Fachpayload und Zeit | `IAuthorityStateStore`; Plan-/Approval-/Requestbindungen durch Fachconsumer prüfen |
| `authority_leases` | Resource, Owner, Ablauf und Version | Ownership/Lease-CAS für vorhandene Workspace-/Resume-/Wirkungspfade; keine allgemeine Jobqueue |
| `workflow_checkpoints` | Issue/Korrelation/Workflow/Boundary, Repo/Branch/Base/Head/Workspace, Subject, Eligibility, Payload | Technische Finalisierung/Providerfortsetzung; kein LLM-Round-/Prompt-/Tokenresume oder allgemeiner terminaler Wiedereinstieg |
| `operation_intents` | Operation/Status/Subject, Payload/Postcondition | Vor Effekt persistierte Absicht und spätere Quellenreconciliation; unsicheren Ausgang nicht blind erneut dispatchen |
| `workflow_budget_admissions` | Repo/Issue, Invocation-/Source-/Policy-Digests, Korrelation, Tokenlimit/Planbindung | Persistente Workflowzulassung, nicht durch Sessionzähler ersetzbar |
| `llm_budget_attempts` | Admission/logischer Call, Provider/Modell/Task, obere Grenzen, Reservation, Usage/Ausgang | Reserve/settle/unknown mit CAS/CHECKs; verlorene Usage ist nicht null Kosten |
| `planning_clarifications` | Gebundene Serie/Status, höchstens zwei Runden, Deadline/Runde-JSON/Version | Planningrückfragen, Timeout und Supersession, keine zusätzliche Approvalauthority |
| `healing_claims` | Claim je Observation, Issue/Korrelation, claimed/attempted/abandoned, Outcome/Reason | Gebundene Healingzulassung/Idempotenz; nicht jede Störung ist heilbar |
| `observations` | Subject-/Evidence-Digests, Schema, Issue/Origin, Payload/Zeit | Gebundene Beobachtungsbasis für Evaluation/advisory SCM-Evidence |
| `score_derivations` | Observation, Scoringpolicy/-Digest/Formel, Score/Payload/Zeit | Versionierte vergleichbare Serien; Origin/Policy/Formel nicht vermischen, keine Freigabe |
| `evaluation_terminals` | Terminalkey, Issue, Status, Payload/Zeit | Terminale Evaluation-/Outcomehistorie; fehlende Evidence nicht nachträglich PASS |
| `run_projections` | Key, Issue/Korrelation, Serie/Status, redigierter Payload/Zeit | Dashboard-Runhistory und Fachprojektionen wie `health-readiness.v1`, keine Rohlog-/Authorityquelle |
| `quality_metrics` | Provider/Modell/Task, Origin/Schema/Policy/Formel, aggregierter Payload | Quality-/Benchmarkprojektion mit getrennten Legacy-/Current-Serien und Callattribution |
| `legacy_imports` | Pfad/Checksum/Format/Archiv, Recordzahlen/Zeit | Idempotenter Import alter passiver Daten, keine gültige Humanauthority aus JSONL |
| `managed_backups` | ID/Pfad/Digest/Instanz/Epoch/Zeit | Registrierte SQLite-Backups; nicht jeder Dateicopy ist ein qualifiziertes Backup |
| `restore_operations` | Operation/Status, Source-Digest, Instanzlinie/Epoch-Highwater, Supersession, Scanstatus/-fehler/Zeit | Kontrollierter Restore, anschließende Quellenprüfung; pending sperrt Wirkung |
| `reconcile_entries` | Operation + Objekttyp/-key, Classification/Reason/Evidence | verified_effect/verified_absent/abandoned/unresolved gemäß Fach-/Operatorcontract, keine simulierte Humanentscheidung |
| `retention_category_states` | Kategorie-/Profil-/Rollendigests, report_only/enforce/suspended, Version/Evidence/Grantcutoff/Grund | Einzelne gebundene Retentionfreigabe/CAS; globaler STOP bleibt vorrangig |
| `retention_executions` | Plan/Kategorie/Policy/Cutoff/Objekte, Candidate-/Deletezahl/Epoch/Grund | Tatsächliche completed-Ausführung; Prognose/Dry-run ist kein Löschungsnachweis |
| `identity_metadata` | Singleton uninitialized/active/recovery_pending, Grund/Aktivierungszeit | Lokale Identity-/Recoverygrenze; Restore gibt alte Sitzungen nicht frei |
| `identity_principals` | ID/eindeutiger Username, user/automation, Argon2-Hash, Disabled-/Credentialversion/Zeit | Lokale Principals; kein Klartextpasswort oder allgemeiner externer IAM-Store |
| `identity_principal_roles` | Principal → unabhängige Rolle | Mehrere Rollen möglich, Administrator erbt keine Operator-/Viewerrolle |
| `identity_sessions` | Session-/CSRF-Hashes, Principal/Instanz/Credentialversion, Auth-/Seen-/Ablauf-/Widerrufszeiten | Opaque Browsersessions; keine wieder auslesbare Rohsession, aktuelle Instanzbindung |
| `identity_tokens` | Tokenhash, Principal, explizite Permissions, Ablauf/Widerruf | Automation-Bearer ohne Humanauthority, Rohwert nur bei Anlage |

### Gemeinsame Spalten und Formate

`*_key` ist fachliche Idempotenz-/Bindungsidentität, nicht überall eine laufende
Nummer. `issue_number`/`correlation_id` ordnen Issue/Run zu; Korrelation beweist
keine Kausalität. `subject_key`, `evidence_digest`, `policy_digest` und andere
Digests binden Fachquellen; sie sind keine Providersecrets/Freigaben.

JSON wird kanonisch geschrieben: sortierte Schlüssel, kompakte Separatoren,
kein NaN/Infinity. `evaluation_subject_json` bindet Candidate/Contract/Policy;
`permissions_json` enthält Permissions, `rounds_json` Klärungsrunden,
`object_ids_json` ausgeführte Retentionobjekte, `evidence_json` begründete
Reconcile-Evidence und `record_counts_json` Legacyzahlen. Der genaue
`payload_json`-Contract stammt vom zugehörigen Record-/Observation-/Projectiontyp.
Zeitpunkte sind timezone-aware UTC/ISO-8601-Text. `version` dient jeweiliger
CAS-/Schemaoperation, Epoch/Instanz sind zusätzliche storeweite Bindungen.
Booleanfelder verwenden 0/1-CHECKs; NULL/UNKNOWN ist kein PASS. SQL-Constraints
und fachliche Recordvalidierung sind eigenständige Schranken.

## Exakte SQL-Struktur

Frischer v10-Store, alle 26 Tabellen und expliziten Indizes. Der vorhandene
Dokumentgenerator liest ausschließlich das SQL-Literal der Schemaanlage;
es werden weder Runtimebootstrap noch Live-State verwendet.

<!-- docs-contract:sqlite-schema:start -->
### `authority_leases` (table)

```sql
CREATE TABLE authority_leases (
                resource_key TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                version INTEGER NOT NULL CHECK(version >= 1),
                updated_at TEXT NOT NULL
            );
```

### `authority_metadata` (table)

```sql
CREATE TABLE authority_metadata (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                instance_uuid TEXT NOT NULL,
                authority_epoch INTEGER NOT NULL CHECK(authority_epoch >= 0),
                reconcile_required INTEGER NOT NULL CHECK(reconcile_required IN (0, 1)),
                reconcile_reason TEXT,
                active_restore_operation TEXT,
                pre_restore_epoch_highwater INTEGER NOT NULL DEFAULT 0
                    CHECK(pre_restore_epoch_highwater >= 0),
                restored_from_uuid TEXT,
                retention_emergency_stop INTEGER NOT NULL DEFAULT 1
                    CHECK(retention_emergency_stop IN (0, 1)),
                updated_at TEXT NOT NULL
            );
```

### `authority_records` (table)

```sql
CREATE TABLE authority_records (
                record_key TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
```

### `evaluation_terminals` (table)

```sql
CREATE TABLE evaluation_terminals (
                terminal_key TEXT PRIMARY KEY,
                issue_number INTEGER NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                observed_at TEXT NOT NULL
            );
```

### `healing_claims` (table)

```sql
CREATE TABLE healing_claims (
                observation_key TEXT PRIMARY KEY,
                issue_number INTEGER NOT NULL,
                correlation_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('claimed', 'attempted', 'abandoned')),
                outcome TEXT,
                reason TEXT,
                updated_at TEXT NOT NULL
            );
```

### `identity_metadata` (table)

```sql
CREATE TABLE identity_metadata (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                status TEXT NOT NULL CHECK(
                    status IN ('uninitialized', 'active', 'recovery_pending')
                ),
                recovery_reason TEXT,
                activated_at TEXT,
                updated_at TEXT NOT NULL
            );
```

### `identity_principal_roles` (table)

```sql
CREATE TABLE identity_principal_roles (
                principal_id TEXT NOT NULL REFERENCES identity_principals(principal_id)
                    ON DELETE CASCADE,
                role TEXT NOT NULL CHECK(
                    role IN ('viewer', 'auditor', 'operator', 'administrator')
                ),
                PRIMARY KEY(principal_id, role)
            );
```

### `identity_principals` (table)

```sql
CREATE TABLE identity_principals (
                principal_id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                kind TEXT NOT NULL CHECK(kind IN ('user', 'automation')),
                password_hash TEXT,
                disabled INTEGER NOT NULL CHECK(disabled IN (0, 1)),
                credential_version INTEGER NOT NULL CHECK(credential_version >= 1),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK(
                    (kind = 'user' AND password_hash IS NOT NULL)
                    OR (kind = 'automation' AND password_hash IS NULL)
                )
            );
```

### `identity_sessions` (table)

```sql
CREATE TABLE identity_sessions (
                session_id TEXT NOT NULL UNIQUE,
                session_hash TEXT PRIMARY KEY,
                principal_id TEXT NOT NULL REFERENCES identity_principals(principal_id)
                    ON DELETE CASCADE,
                instance_uuid TEXT NOT NULL,
                csrf_hash TEXT NOT NULL,
                credential_version INTEGER NOT NULL CHECK(credential_version >= 1),
                created_at TEXT NOT NULL,
                authenticated_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                revoked_by TEXT
            );
```

### `identity_tokens` (table)

```sql
CREATE TABLE identity_tokens (
                token_id TEXT PRIMARY KEY,
                token_hash TEXT NOT NULL UNIQUE,
                principal_id TEXT NOT NULL REFERENCES identity_principals(principal_id)
                    ON DELETE CASCADE,
                permissions_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                revoked_by TEXT
            );
```

### `legacy_imports` (table)

```sql
CREATE TABLE legacy_imports (
                source_path TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                format_version TEXT NOT NULL,
                archive_path TEXT NOT NULL,
                record_counts_json TEXT NOT NULL,
                imported_at TEXT NOT NULL
            );
```

### `llm_budget_attempts` (table)

```sql
CREATE TABLE llm_budget_attempts (
                attempt_key TEXT PRIMARY KEY,
                admission_key TEXT NOT NULL
                    REFERENCES workflow_budget_admissions(admission_key),
                logical_call_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                task TEXT NOT NULL,
                input_upper_bound INTEGER NOT NULL CHECK(input_upper_bound > 0),
                output_upper_bound INTEGER NOT NULL CHECK(output_upper_bound > 0),
                reserved_tokens INTEGER NOT NULL CHECK(
                    reserved_tokens = input_upper_bound + output_upper_bound
                ),
                status TEXT NOT NULL CHECK(status IN ('reserved', 'settled', 'unknown')),
                actual_input_tokens INTEGER CHECK(actual_input_tokens >= 0),
                actual_output_tokens INTEGER CHECK(actual_output_tokens >= 0),
                outcome_code TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK(
                    (status = 'settled' AND actual_input_tokens IS NOT NULL
                        AND actual_output_tokens IS NOT NULL)
                    OR (status IN ('reserved', 'unknown') AND actual_input_tokens IS NULL
                        AND actual_output_tokens IS NULL)
                ),
                CHECK(
                    (status = 'reserved' AND outcome_code = '')
                    OR (status IN ('settled', 'unknown') AND outcome_code != '')
                )
            );
```

### `managed_backups` (table)

```sql
CREATE TABLE managed_backups (
                backup_id TEXT PRIMARY KEY,
                path TEXT NOT NULL UNIQUE,
                digest TEXT NOT NULL,
                instance_uuid TEXT NOT NULL,
                authority_epoch INTEGER NOT NULL CHECK(authority_epoch >= 0),
                created_at TEXT NOT NULL
            );
```

### `observations` (table)

```sql
CREATE TABLE observations (
                observation_key TEXT PRIMARY KEY,
                subject_key TEXT NOT NULL,
                evidence_digest TEXT NOT NULL,
                observation_schema TEXT NOT NULL,
                issue_number INTEGER NOT NULL,
                evidence_origin TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                observed_at TEXT NOT NULL
            );
```

### `operation_intents` (table)

```sql
CREATE TABLE operation_intents (
                intent_key TEXT PRIMARY KEY,
                operation TEXT NOT NULL,
                status TEXT NOT NULL CHECK(
                    status IN ('pending', 'applied', 'failed', 'mismatch', 'unresolved')
                ),
                issue_number INTEGER NOT NULL,
                correlation_id TEXT NOT NULL,
                subject_key TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                postcondition_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
```

### `planning_clarifications` (table)

```sql
CREATE TABLE planning_clarifications (
                series_key TEXT PRIMARY KEY,
                repository TEXT NOT NULL,
                issue_number INTEGER NOT NULL CHECK(issue_number > 0),
                source_digest TEXT NOT NULL,
                admission_key TEXT NOT NULL REFERENCES workflow_budget_admissions(admission_key),
                correlation_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN (
                    'waiting', 'answered', 'planned', 'superseded', 'timed_out', 'exhausted'
                )),
                round_number INTEGER NOT NULL CHECK(round_number BETWEEN 1 AND 2),
                deadline_at TEXT NOT NULL,
                rounds_json TEXT NOT NULL,
                version INTEGER NOT NULL CHECK(version >= 1),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
```

### `quality_metrics` (table)

```sql
CREATE TABLE quality_metrics (
                metric_key TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                task TEXT NOT NULL,
                evidence_origin TEXT NOT NULL,
                observation_schema TEXT NOT NULL,
                scoring_policy_version TEXT NOT NULL,
                formula_version TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
```

### `reconcile_entries` (table)

```sql
CREATE TABLE reconcile_entries (
                operation_id TEXT NOT NULL REFERENCES restore_operations(operation_id),
                object_type TEXT NOT NULL,
                object_key TEXT NOT NULL,
                classification TEXT NOT NULL CHECK(
                    classification IN (
                        'verified_effect', 'verified_absent', 'abandoned', 'unresolved'
                    )
                ),
                reason TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(operation_id, object_type, object_key)
            );
```

### `restore_operations` (table)

```sql
CREATE TABLE restore_operations (
                operation_id TEXT PRIMARY KEY,
                status TEXT NOT NULL CHECK(
                    status IN ('reconcile_required', 'completed', 'superseded')
                ),
                source_digest TEXT NOT NULL,
                restored_from_uuid TEXT NOT NULL,
                instance_uuid TEXT NOT NULL,
                pre_restore_epoch_highwater INTEGER NOT NULL
                    CHECK(pre_restore_epoch_highwater >= 0),
                supersedes_operation_id TEXT,
                reason TEXT,
                scan_status TEXT NOT NULL CHECK(
                    scan_status IN ('pending', 'completed', 'scan_failed')
                ),
                scan_error_code TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT
            );
```

### `retention_category_states` (table)

```sql
CREATE TABLE retention_category_states (
                category_id TEXT PRIMARY KEY,
                category_digest TEXT NOT NULL,
                profile_role_digest TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('report_only', 'enforce', 'suspended')),
                version INTEGER NOT NULL CHECK(version >= 1),
                evidence_digest TEXT,
                grant_cutoff_utc TEXT,
                activated_at TEXT,
                reason TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
```

### `retention_executions` (table)

```sql
CREATE TABLE retention_executions (
                execution_id TEXT PRIMARY KEY,
                category_id TEXT NOT NULL,
                plan_digest TEXT NOT NULL UNIQUE,
                category_digest TEXT NOT NULL,
                profile_role_digest TEXT NOT NULL,
                cutoff_utc TEXT NOT NULL,
                anchor TEXT NOT NULL,
                object_ids_json TEXT NOT NULL,
                candidate_count INTEGER NOT NULL CHECK(candidate_count >= 0),
                deleted_count INTEGER NOT NULL CHECK(deleted_count >= 0),
                status TEXT NOT NULL CHECK(status = 'completed'),
                reason TEXT NOT NULL,
                authority_epoch INTEGER NOT NULL CHECK(authority_epoch >= 1),
                executed_at TEXT NOT NULL
            );
```

### `run_projections` (table)

```sql
CREATE TABLE run_projections (
                projection_key TEXT PRIMARY KEY,
                issue_number INTEGER NOT NULL,
                correlation_id TEXT NOT NULL,
                series TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
```

### `schema_migrations` (table)

```sql
CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
```

### `score_derivations` (table)

```sql
CREATE TABLE score_derivations (
                score_key TEXT PRIMARY KEY,
                observation_key TEXT NOT NULL REFERENCES observations(observation_key),
                scoring_policy_version TEXT NOT NULL,
                scoring_policy_digest TEXT NOT NULL,
                formula_version TEXT NOT NULL,
                issue_number INTEGER NOT NULL,
                evidence_origin TEXT NOT NULL,
                observation_schema TEXT NOT NULL,
                score REAL,
                payload_json TEXT NOT NULL,
                derived_at TEXT NOT NULL
            );
```

### `workflow_budget_admissions` (table)

```sql
CREATE TABLE workflow_budget_admissions (
                admission_key TEXT PRIMARY KEY,
                repository TEXT NOT NULL,
                issue_number INTEGER NOT NULL CHECK(issue_number > 0),
                invocation_digest TEXT NOT NULL,
                source_digest TEXT NOT NULL,
                policy_digest TEXT NOT NULL,
                correlation_id TEXT NOT NULL,
                token_limit INTEGER NOT NULL CHECK(token_limit > 0),
                plan_contract_hash TEXT NOT NULL DEFAULT '',
                plan_comment_id INTEGER NOT NULL DEFAULT 0 CHECK(plan_comment_id >= 0),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
```

### `workflow_checkpoints` (table)

```sql
CREATE TABLE workflow_checkpoints (
                checkpoint_key TEXT PRIMARY KEY,
                issue_number INTEGER NOT NULL,
                correlation_id TEXT NOT NULL,
                workflow TEXT NOT NULL,
                boundary TEXT NOT NULL,
                repository TEXT NOT NULL,
                branch TEXT NOT NULL,
                base_ref TEXT NOT NULL,
                head_sha TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                evaluation_subject_json TEXT NOT NULL,
                resume_eligible INTEGER NOT NULL CHECK(resume_eligible IN (0, 1)),
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
```

### `evaluation_terminals_issue` (index)

```sql
CREATE INDEX evaluation_terminals_issue
            ON evaluation_terminals(issue_number, observed_at);
```

### `identity_sessions_principal` (index)

```sql
CREATE INDEX identity_sessions_principal
            ON identity_sessions(principal_id, expires_at);
```

### `identity_tokens_principal` (index)

```sql
CREATE INDEX identity_tokens_principal
            ON identity_tokens(principal_id, expires_at);
```

### `llm_budget_attempts_admission` (index)

```sql
CREATE INDEX llm_budget_attempts_admission
            ON llm_budget_attempts(admission_key, created_at, attempt_key);
```

### `observations_issue_series` (index)

```sql
CREATE INDEX observations_issue_series
            ON observations(issue_number, evidence_origin, observation_schema, observed_at);
```

### `planning_clarifications_issue` (index)

```sql
CREATE INDEX planning_clarifications_issue
            ON planning_clarifications(repository, issue_number, updated_at, series_key);
```

### `quality_metrics_series` (index)

```sql
CREATE INDEX quality_metrics_series
            ON quality_metrics(
                provider,
                model,
                task,
                evidence_origin,
                observation_schema,
                scoring_policy_version,
                formula_version,
                updated_at
            );
```

### `run_projections_issue_series` (index)

```sql
CREATE INDEX run_projections_issue_series
            ON run_projections(issue_number, series, updated_at);
```

### `score_derivations_issue_series` (index)

```sql
CREATE INDEX score_derivations_issue_series
            ON score_derivations(
                issue_number,
                evidence_origin,
                observation_schema,
                scoring_policy_version,
                formula_version,
                derived_at
            );
```

### `workflow_budget_plan_binding` (index)

```sql
CREATE UNIQUE INDEX workflow_budget_plan_binding
            ON workflow_budget_admissions(
                repository, issue_number, plan_contract_hash, plan_comment_id
            )
            WHERE plan_contract_hash != '';
```

**Quellenbindung:**
- `samuel/adapters/state/sqlite.py::SQLiteStateStore._create_schema`
- Vertrag: `docs/capabilities/document-contract.json::sqlite-schema`
<!-- docs-contract:sqlite-schema:end -->


## Zweite Datenbank: Workspace-Registry

Der vorhandene `GitWorktreeManager` führt unabhängig vom Runtime-State
`<work_dir>/workspaces.sqlite3`. `agent.workspace.work_dir` bestimmt den Ort;
relative Pfade werden neben dem Configverzeichnis aufgelöst. Workdir und
Datadir dürfen weder identisch noch ineinander verschachtelt sein. Diese
Registry besitzt keine gemeinsame Schema-/Epochlinie mit dem v10-State.

| Tabelle | Inhalt | Funktion / Consumer |
|---|---|---|
| `workspaces` | IDs, Profil, Repository-/Worktreepfad, Branch/Base/Head, Zustand, reservierter Speicher, Prozessowner, Zeiten und Quarantänegrund | Run-/Verifikations-Worktrees, Prozessownership und Quarantäne im bestehenden `IWorkspaceManager`; kein Plan-/Review-/Qualification-PASS |

`workspace_id` ist der Primary Key, `path` eindeutig. `profile` erlaubt `run`
oder `verification`; `status` ist `creating`, `active`, `terminal` oder
`quarantined`. `owner_pid` benennt einen Prozess, keinen Humanactor;
`reserved_bytes` ist eine Reservierung, kein gemessener Verbrauch.
`repository_root`, `path`, `branch`, `base_ref` und `head_sha` binden das
verwaltete Git-Artefakt. `created_at`/`updated_at`, `quarantine_until` und
`reason` erklären Lifecycle bzw. Aufbewahrung. Leere optionale Texte sind
keine bestätigte Freigabe. Eine vorhandene alte Tabelle erhält die fehlende
`quarantine_until`-Spalte; daraus folgt keine allgemeine Release-Migration.

SQLite verwendet WAL und zehn Sekunden Busy-Timeout. `.manager.lock` und
ressourcenbezogene Dateien unter `locks/` koordinieren POSIX-`flock`; die
Tabelle allein ersetzt keinen lebenden Lock oder eine fachliche Lease.
`trees/` enthält Git-Worktrees. Read-only-Registrydiagnose legt keinen Store
an. Workspacequarantäne und Cleanup gehören dem Manager, nicht der
State-Retention. Konfiguration, Grenzen und Diagnose:
[Workspacebetrieb](README_technical.md#gemeinsamer-worktree-manager-618).

**Backupgrenze:** `samuel retention backup` sichert diese separate Registry und
die Worktrees nicht mit. Ein State-Restore muss bekannte Workspacewirkungen
über den bestehenden Reconcilecontract klären; das Kopieren der Registry
erteilt keine erneute Dispatch-/Ownership-/Approvalauthority. Es gibt keinen
hier nachgewiesenen atomaren Gesamtbackup aller Stores und Git-Artefakte.

### Exakte Workspace-Struktur

<!-- docs-contract:workspace-schema:start -->
### `workspaces` (table)

```sql
CREATE TABLE workspaces (
                    workspace_id TEXT PRIMARY KEY,
                    profile TEXT NOT NULL CHECK(profile IN ('run', 'verification')),
                    repository_root TEXT NOT NULL,
                    path TEXT NOT NULL UNIQUE,
                    branch TEXT NOT NULL,
                    head_sha TEXT NOT NULL,
                    base_ref TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN
                        ('creating', 'active', 'terminal', 'quarantined')),
                    reserved_bytes INTEGER NOT NULL,
                    owner_pid INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    quarantine_until TEXT NOT NULL DEFAULT '',
                    reason TEXT NOT NULL DEFAULT ''
                );
```

**Quellenbindung:**
- `samuel/adapters/workspace/git.py::GitWorktreeManager._initialize_registry`
- Vertrag: `docs/capabilities/document-contract.json::workspace-schema`
<!-- docs-contract:workspace-schema:end -->

## Konsistenz, Diagnose und öffentliche Ausgabe

Bootstrap injiziert spezialisierte Ports desselben Stores. Fachwrites bleiben
bei ihrem Contract; Lease-, Checkpoint-, Intent- und Budgetänderungen verwenden
die vorhandenen Transaktions-/CAS-Grenzen. JSONL ersetzt keinen DB-Commit,
Audit-Queueannahme keinen durable Write. Das Dashboard liest begrenzte Views
und verwaltet Identity über permissiongeschützte Routen; es hat keinen SQLEditor.
DB-Payloads und Passwort-/Session-/Tokenhashes gehören nicht in öffentliche
Issue-/Wiki-/Dashboardexporte.

Diagnose über `samuel state status|dump`; `dump` ist kein ungefilterter SQLEXport.
`samuel resume list|inspect` ist seit #998 ein passiver Diagnosepfad ohne
Runtimebootstrap, `PROJECT_ROOT`, SCM-/LLM-Adapter oder Workflowstart. Er liest
vorhandene `agent.json`-, State- und Workspacebindings. Derselbe SQLite-Store
öffnet `mode=ro` mit `query_only`; vorhandener Lifecyclelock wird lesend
verwendet. Fehlende State-/Lockdateien oder falsches Schema werden als Fehler
gemeldet, kein Ersatzstore angelegt oder migriert. Witness-/Restoreabweichungen
werden für die Diagnose als Reconcilebedarf berechnet, ohne Witness oder DB
zu reparieren. Eventuelle SQLite-WAL-/SHM-Lesehilfsdateien sind keine Fachwrite-
oder Runtimebootstrapwirkung. `attempt|resume`, `abandon` und `cleanup` bleiben
mutierende Aktionen mit normalem Bootstrap und ihren vorhandenen Guards.

## Migration, Backup, Restore und Aufbewahrung

Vorhandene Migrationen v1→v2 bis v9→v10 behalten Daten. Unbekannte/futurische
oder widersprüchliche Versionen werden abgewiesen, nicht still neu angelegt.
Das ist keine allgemeine Cross-Release-Upgradezusage: aktuelle Alphaabnahmen
nutzen saubere Neuinstallation ohne alte Release-Authority/Checkpoints.

Backup verwendet die SQLite-Backup-API unter der Lifecyclegrenze. Ein laufender
WAL-Store wird nicht durch Kopieren nur der Hauptdatei gesichert. Restore prüft
Quelle/Digest/Schema/Pfade, erzeugt neue Instanz-/Epochlinie, setzt Sentinel und
Reconcile-STOP. Erst Quellenprüfung erlaubt Wirkung; Identity kann
`recovery_pending` bleiben. Witness/DB nicht einzeln reparieren oder Epoch senken.
Die Auditkette benötigt separat ihren ursprünglichen HMAC-Key; korrekte DB
ersetzt keine falsche Audit-Keybindung. Details:
[INSTALL](INSTALL.md), [ADR-0482](adr/0482-runtime-state-store.md) und
[Persistenzreferenz](README_technical.md#15-persistenz).

Retention besitzt Report, Grant/Activate, Suspend, globalen STOP, Plan und
ausdrücklich beauftragtes Execute. Defaults: report_only und STOP, kein
Löschscheduler. Grants binden Kategorie/Profil/Rollen/Evidence und Cutoff;
zukünftige Objekte erhalten keine pauschale alte Löschfreigabe.

Installierte a29-Komponentenbelege prüfen begrenzte Backup-/Restore-/Status-
und Negativfälle. Vollständige Crash-/Konkurrenz-/Retention-/Reconcile-/Human-/
D0-Matrix bleibt #962. Neue Audit-/Health-/STOPsemantik aus #986 wird nicht
durch diese Beschreibung erfunden.

## Fachquellen

`samuel/adapters/state/sqlite.py`, `legacy.py`, `samuel/core/state.py`,
`ports.py`, `identity.py`, `retention.py`, `health_projection.py`,
`samuel/slices/run_projection/handler.py`, `samuel/slices/resume/handler.py`,
`samuel/adapters/identity/local.py`, `config/agent.json`, `config/privacy.json`.
