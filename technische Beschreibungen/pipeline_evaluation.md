# Pipeline: Evaluation (gebundene Qualitätsbeobachtung)

Der Evaluation-Slice trifft im ausgelieferten Runtime-Pfad keine
Freigabeentscheidung. Das Required-Gate-Profil entscheidet über den
Candidate. Evaluation abonniert anschließend genau ein terminales Gate-Event,
persistiert dessen gebundene Evidence und leitet daraus eine ausdrücklich
nicht bindende Qualitätsbeobachtung ab.

**Prüfdatum:** 2026-08-30 · **Abgeglichener Commit:**
`11d589950b2f88abf4ecf09f6947a2b72119dd38`

Die #485-Korrekturen und die Retention-/Replay-Erweiterung aus #667 wurden
gegen diese integrierte Ausgangsbasis, den Implementierungsdiff und die
geänderten Tests geprüft.

## Verantwortungsgrenze

```text
CodeGenerated
  -> CreatePRCommand
  -> vollständiger Gate-Lauf auf EvaluationSubject
       -> GateEvaluationCompleted
            +-> PR-Erstellung, wenn required Gates bestanden
            +-> EvaluationObserver -> ScoreObserved (nicht bindend)
            +-> BoundHealingCoordinator -> höchstens ein Evidence-Healing
       -> GateEvaluationUnavailable
            +-> EvaluationObserver (nicht berechenbarer Lauf)
            +-> WorkflowBlocked
```

Der Slice arbeitet im aktiven Pfad ausschließlich als Event-Subscriber. Er
importiert keinen anderen Slice. Die Kommunikation läuft
über den Bus. Einzelne `GateFailedEvent` sind weder Telemetrie- noch
Healing-Trigger: Der PR-Gate-Handler veröffentlicht nach der vollständigen
Gate-Schleife genau ein `GateEvaluationCompleted` mit sämtlichen Ergebnissen.
Ist vor oder beim Aufbau des Subjects keine vollständige Beobachtung möglich,
veröffentlicht er stattdessen genau ein `GateEvaluationUnavailable`.

## Getrennter externer Advisory-Pfad

`samuel evidence assess` ist kein weiterer Workflow- oder Gate-Subscriber. Der
Operator benennt `{provider, repository, run_id, attempt}`, ein vorhandenes
`EvaluationSubject` sowie optionale Workflow-/Event-/Freshness-Erwartungen.
Der Gitea-Adapter liest Run, Jobs, Commit-Status und Workflow-Blob-ID und gibt
nur die entscheidungsrelevante Projektion an den Core zurück. Freie Joblogs,
Workflowinhalt und unbekannte Payloadwerte werden verworfen.

Der Core hält Providerfacts (`SCMCheckObservation`) und eigene Prüfung
(`EvidenceAssessment`) getrennt. Repository, vollständige Base-/Head-SHA,
Attempt, Statuskontext, Workflow und Freshness werden verglichen; fehlende
Runner-/Toolchain-/Signatur-/Requestbindungen bleiben sichtbar. Die
Observation nutzt denselben `IObservationStore` wie die passive Evaluation,
aber die versionierte Herkunft `external_scm_advisory`. Deduplizierung meldet
einen Replay und verändert Payload, Severity oder Herkunft nicht.

Auch ein `advisory_qualified` Ergebnis trägt unveränderlich
`authority=none`. Required-, Dispatch- und Mutationswirkung sind `false`; es
gibt keine Verdrahtung zu `IExternalGate`, Healing oder CreatePR. Das
in-toto-Statement v1 ist ein portabler äußerer Rahmen für genau dieses
Assessment, keine Signatur-, SLSA- oder Trust-Behauptung. Die getrennte
auftragsgebundene Required-Nutzung und der Provider-Cutover bleiben #679.

`ScoreCommand`, `EvaluateCommand`, `Scored`, `EvalCompleted` und `EvalFailed`
bleiben als historische Typen bzw. direkt aufrufbarer Kompatibilitätscode
erhalten. Der Bootstrap registriert ihre Handler nicht, und kein ausgelieferter
Workflow referenziert sie.

## Autorität

- Freigaben stammen ausschließlich aus dem für den Workflow geladenen
  Required-Gate-Profil.
- `ScoreObserved` hat keine Workflowkante und löst weder PR-Erstellung,
  Abbruch noch Healing aus.
- Die alte statische Score-Schwelle, `fail_fast_on` und die issuebezogene
  High-Water-Baseline werden nur noch vom nicht verdrahteten direkten
  Kompatibilitäts-Handler ausgewertet. `self_parity_ok` ist entfernt.
- Gate 4 (`EvalPresence`) und Gate 10 (`EvalScore`) sind aus Registry,
  Metadaten und Profilen entfernt.
- Die Bindungsqualität der einzelnen Gates ist in der Capability-Matrix
  dokumentiert: 7b, 9 und 11 liefern `EvaluationSubject`-gebundene Evidence;
  weitere required Gates sind strukturelle Vorbedingungen.

## Gebundene Rohbeobachtung

`EvaluationSubject` bindet Repository, Base- und Head-SHA,
Acceptance-Contract-Hash sowie Gate-Policy-Version und -Digest. Jede
`GateEvaluationCompleted`-Payload enthält:

- das vollständige `EvaluationSubject`,
- alle Gate-Ergebnisse samt `required`/`optional`-Autorität,
- die kriteriumsweise Acceptance-Evidence aus Gate 11,
- Evidence-Provenance und den berechneten Evidence-Digest.

Observation-Schema v2 verlangt pro Gate ausdrücklich `executed`,
`passed=true|false|null` und einen validierten Status. Der Skip-/Abwesenheits-
zustand geht kanonisch in den Evidence-Digest ein. Fehlt Gate-11-Evidence wegen
eines Required-Preflight-Blocks, entsteht eine persistierte
`not_scoreable`-Beobachtung mit Grund `missing_acceptance_evidence`; sie ist
weder ein 0-%- noch ein 100-%-Score. Schema v1 bleibt nur als historische Serie
lesbar und wird nicht mit v2 aggregiert.

Der `observation_key` wird kanonisch aus Subject, Gate-Policy und
`evidence_digest` gebildet. Derselbe Schlüssel mit anderem Inhalt ist ein
Konflikt; eine echte Wiederholung wird idempotent behandelt. Abweichende
Evidence für dasselbe Subject erzeugt wegen ihres Digests eine andere
Beobachtung.

Nicht beobachtbare Läufe erhalten keinen erfundenen Ersatz-Subject.
`GateEvaluationUnavailable` wird separat und idempotent über einen
`terminal_key` gespeichert. Das verhindert, dass genau frühe Fehler aus der
Betriebsbeobachtung verschwinden.

## Ableitung und Replay

Die Rohbeobachtung und die daraus berechneten Scores haben getrennte
Identitäten:

- `observation_key = H(subject + gate policy + evidence digest)`
- `score_key = H(observation_key + scoring policy + formula version)`

Damit wird die Roh-Evidence nur einmal gespeichert, während mehrere
Formelversionen legitime, an dieselbe Beobachtung gebundene Ableitungen bilden
können. `config/eval.json` benennt dafür `policy_version` und
`formula_version`; Gewichte sind Teil des Scoring-Policy-Digests.
`samuel retention replay-scores` verwendet denselben Ableitungscode wie der
Live-Subscriber. Mehrfach angegebene `--eval-config-dir`-Verzeichnisse mit
versionierter `eval.json` erzeugen mehrere legitime Serien, ohne
`ScoreObserved` zu publizieren oder Quality-EWMA zu verändern.

Die ausgelieferte Formel `bound-evidence.v1` ordnet jedes automatische
Kriterium genau einer Kategorie zu:

| AC-Tag | Zielkategorie |
|---|---|
| `TEST` | `test_pass_rate` |
| `IMPORT` | `syntax_valid` |
| `DIFF`, `EXISTS` | `hallucination_free` |
| `GREP`, `GREP:NOT` | `scope_compliant` |
| `MANUAL` | keine automatische Score-Kategorie |

Eine leere Kategorie ist `applicable=false` und hat den Score `null`; sie
erhält nicht mehr automatisch 100 %. Der Gesamtwert wird nur über Kategorien
mit ausgewerteten `passed`/`failed`-Ergebnissen renormiert. `missing_evidence`,
`error` und `not_applicable` werden nicht als Erfolg umgedeutet, sondern
senken die separat ausgewiesene Rohabdeckung. Unbekannte automatische Tags
machen die Beobachtung `not_scoreable`.

Diese Formel ist Telemetrie. Auch ein Score von 100 % ist kein Freigabesignal.

## Persistenz und Darstellung

Audit-JSONL bleibt Compliance-Evidence, ist aber nicht mehr die Runtime-
Datenbank. Der Evaluation-Subscriber schreibt über `IObservationStore` in das
lokale SQLite-Schema v10: immutable Rohbeobachtungen, davon getrennte
Formelableitungen und `GateEvaluationUnavailable` als eigenen nicht scorebaren
Terminalzustand. `observation_key` und `score_key` bleiben die fachlichen
Idempotenzgrenzen; Wiederholungsläufe dürfen andere Zeit-/Korrelationswerte
besitzen, ohne die gebundene Evidence zu duplizieren.

Der passive `run_projection`-Subscriber materialisiert redigierte Issue-/Run-
Ereignisse in `IRunProjectionStore`. Das Dashboard liest diese Projektion und
verliert bestehende Runs deshalb nicht bei Auditrotation. Ein Schreibfehler
wird in DLQ/Auditdiagnose und `state.status.projections` sichtbar, blockiert
aber weder Gate-Auswertung noch PR-Erstellung. Ein initialer Audit-Backfill ist
idempotent; davor und über `samuel state reproject-runs --json` werden bereits
gespeicherte Ereignisfolgen ohne Payloadausgabe neu klassifiziert. Danach ist
Audit keine Rekonstruktionsvoraussetzung.

Die Authority für den Projektionsstatus liegt in
`samuel/core/workflow_outcome.py`, nicht in einer Dashboard- oder
Semaphore-Liste. `PlanBlocked`, das derzeit nur als reservierter Vertragsfall
vorhandene `LLMUnavailable`, `WorkflowBlocked`, `WorkflowAborted`,
`PRCreationFailed` und `EvaluationSubjectInvalidated` sind echte
Fehlerausgänge; `PRCreated`/`PRMerged` sind Erfolgsausgänge. Ein bestätigter PR
darf frühere heilbare/blockierende Evidence überholen, während
`EvaluationSubjectInvalidated` den Subject-Erfolg widerruft. `GateFailed`,
`EvalFailed`, `TokenLimitHit` und `HealingAborted` bleiben Stage-Evidence und
terminieren einen Run nicht allein. Die Reduktion wird nach sortierter
Ereignisfolge vollständig neu berechnet und ist damit gegen Wiederholung und
Out-of-order-Zustellung stabil.

Eine Projektion, die ausschließlich historische oder ausdrücklich mit
`workflow_correlation_bound=false` markierte `LLMCallCompleted`-Telemetrie
enthält, erhält `status=unbound`. Sie bleibt als redigierter Betriebsbestand
sichtbar, wird aber von Dashboard-Runzahl und Trend ausgeschlossen. Worker-
`LLMCallCompleted`-Events übernehmen die bestehende Run-Korrelation aus dem
Core-Kontext. Standalone-Calls tragen `workflow_correlation_bound=false` und
werden nicht allein aufgrund von Issue oder Zeitnähe einem Run zugeschlagen
(#675/#672).

Beim ersten Bootstrap werden `evaluation_observations.json`,
`quality_metrics.json`, `score_history.json` und `eval_baselines.json`
checksumgebunden importiert und erst nach erfolgreichem DB-Marker atomar als
`<name>.migrated-<sha256>` archiviert. Ungebundene Werte bleiben Legacy-
Serien. Eine wieder auftauchende abweichende Quelle blockiert den Import statt
zwei Wahrheiten zusammenzuführen. Der Healing-Einmaligkeitsnachweis liegt ab
#629 im transaktionalen Authority-Port derselben DB. Ein vorhandenes
`bound_healing_attempts.json` wird checksumgebunden importiert und danach als
`*.migrated-<sha256>` read-only archiviert. Reconcile oder ein fehlgeschlagener
Authority-/Witness-Write blockiert vor dem LLM-Aufruf.

`agent.data_dir` muss im Systemd- und Docker-Betrieb auf persistentem Storage
liegen. `samuel retention backup` sichert die aktive WAL-DB über die
SQLite-Backup-API in das konfigurierte `managed_backup_dir` und registriert
Digest, Autoritätslinie und -Epoch. Der unterstützte Restore erzeugt eine neue
Autoritätslinie und bleibt bis zum vollständigen Operator-Reconcile
fail-closed; eine Dateikopie ist kein unterstützter Restoreweg.

Schema v10 führt einen vollständigen Retention-Katalog für 26 State-Tabellen
und die externen Klassen Audit, Workspaces und Quarantäne.
`samuel retention dry-run` meldet Kalender-Cutoffs, Treffer, Schutzgründe und
Spalten-/Payloadklassifikation. Der getrennte `IRetentionExecutionStore`
besitzt keine generische Tabellen-/SQL-Schnittstelle und registriert nur
`score_derivations`; Plan, Ausführung und Receipt sind digest-/epochgebunden.
Alle ausgelieferten Kategorien bleiben `report_only`, die globale
Notabschaltung ist aktiv und kein Scheduler ruft den Vollzug auf. Externe
Backupkopien außerhalb `managed_backup_dir` bleiben Betreiberverantwortung.
Für `run_projections` meldet der Dry-Run jeden Zustand außerhalb
`blocked|complete|unbound` als `non_terminal_never`; eine spätere
Kategorieaktivierung darf solche Datensätze nicht als Alterskandidaten
übernehmen (#672/#668).

Die Darstellung wird vom Gate-Aufruf getrennt:

1. Der Evaluation-Subscriber berechnet kurz, persistiert und publiziert
   `ScoreObserved` ohne externes I/O.
2. Ein eigener Presentation-Subscriber verbindet `ScoreObserved` nach
   `PRCreated` mit dem PR und schreibt den Kommentar in einem begrenzten
   Hintergrundpfad mit SCM-Request-Timeout.
3. Fehler oder Überlastung der Darstellung verändern die Gate-Entscheidung
   nicht; die Beobachtung bleibt im Audit-/Materialisierungsbestand.

PR-Kommentar und Dashboard verwenden die Überschrift „Nicht bindende
Qualitätsbeobachtung“ und enthalten keine PASS-/FAIL-, Baseline- oder
Merge-Sprache. `quality_metrics` konsumiert im Zielmodus ausschließlich
vollständig gekennzeichnete `ScoreObserved`-Events. Persistierte SQLite-EWMA-
Reihen sind zusätzlich nach Evidence-Herkunft, Observation-Schema,
Scoring-Policy und Formelversion
getrennt; eine gebundene Reihe wird nie mit historischen
`unbound_worktree`-Werten fortgeschrieben. Sobald gebundene Beobachtungen im
SQLite-Bestand vorhanden sind, wertet das Dashboard keine Legacy-Evals in
derselben Ansicht aus. Enthält der Bestand mehrere gebundene Observation-,
Policy- oder Formelversionen, zeigt und aggregiert die Qualitätsansicht
ausschließlich die Serie der neuesten gültigen gebundenen Beobachtung; ältere
Serien bleiben in SQLite und Audit erhalten, werden aber nicht in denselben Mittelwert
eingerechnet. Auch der Call-Denominator folgt dieser Serie: Nur der letzte,
derselben Beobachtung attribuierte LLM-Call zählt als `Serien-Call`. Frühere
oder nicht evaluierbare Calls erscheinen als unattribuiert; nachweislich einer
anderen Legacy-/Policy-/Formelserie zugeordnete Calls besitzen einen getrennten
Zähler. Keiner dieser beiden Zähler fließt in Score, EWMA oder Heatmap ein.

## Laufzeit- und Budgetwirkung

Im Zielmodus erreicht jeder `CodeGenerated`-Candidate den vollständigen
Gate-Lauf; ein niedriger Legacy-Score kann ihn nicht mehr vorzeitig stoppen.
Das erhöht bewusst die Anzahl vollständiger Gate-Auswertungen. Zugleich wird
die frühere separate AC-Ausführung für Scoring nicht mehr benötigt: Score und
Healing verwenden die ohnehin von Gate 11 erzeugte Evidence. Ein Healing-Fall
verursacht genau einen zweiten vollständigen Gate-Lauf auf dem neuen Head.

Gate-Laufzeit und lokale Testprozesse werden nicht vom LLM-Tokenbudget des
Session-Slices abgezogen. Der synchrone Watch-Scan besitzt genau einen
prozesslokalen Workflow-Slot (`max_parallel=1`) und dispatcht Issues
sequenziell; er koordiniert keine weiteren Prozesse. `[TEST]`-Ausführungen
besitzen den `test_timeout` aus
dem beim Bootstrap gebundenen Control-Plane-`config/eval.json`. Candidate-
Konfiguration kann diesen Wert nicht überschreiben. Ein kumulatives
Laufzeit-/Kostenbudget für Gate-Läufe wird derzeit nicht behauptet.

## Evidence-basiertes Healing

Healing wird ebenfalls genau einmal aus `GateEvaluationCompleted`
klassifiziert. Ein aktiver Versuch ist nur zulässig, wenn:

- genau ein required Gate gescheitert ist,
- dieses Gate Gate 11 ist,
- genau ein automatisches Kriterium mit auswertbarer Evidence `failed` ist;
  auswertbar verlangt Schema 1, zum AC-Tag passendes `kind` und dessen
  Pflichtfelder,
- kein `manual_pending`, `missing_evidence`, `error` oder `not_applicable`
  vorliegt, und
- die Beobachtung noch keinen Versuch beansprucht hat.

Der Korrekturbranch wird am fehlgeschlagenen `head_sha` vorbereitet. Ein
frischer Branch von `origin/main` wäre ein Integritätsbruch und ist im
Zielpfad ausgeschlossen. Nach dem Vorschlag folgt genau eine Implementierung
und anschließend der vollständige Gate-Lauf gegen den neuen Head. Ein zweites
Scheitern oder ein nicht heilbarer Fall endet in `WorkflowBlocked` und der
menschlichen Route. Wegen `max_parallel=1` belegt dieser Nachlauf denselben
Workflow-Slot; das ist beabsichtigt und kein Hänger.

Die fachliche Attempt-Grenze ist `HealingAttemptStarted`. Danach meldet ein
terminales `HealingAborted` auch bei Provider-, Truncation-, Budget- oder
Authority-Finalisierungsfehler `attempts_used=1`; Adapter-interne
Transport-Retries zählen nicht zusätzlich. Bekannte Tokens einer erhaltenen
Antwort werden ausgewiesen, bei einem Providerfehler ohne Usage-Evidence wird
kein Tokenwert erfunden. Vor der Attempt-Grenze blockierte Pfade bleiben bei
null Versuchen.

Healing und Restart-Resume besitzen getrennte Autorität. Healing darf den
gebundenen Candidate genau einmal verändern und verwendet denselben
Run-Worktree; Resume rekonstruiert keinen Healing-/LLM-Round, sondern kann
danach nur dessen bereits persistierte Commit-/Push-/Gate-/PR-Finalisierung
fortsetzen. Reconcile blockiert beide Pfade.
`ResumeAttempted`, `ResumeCompleted` und `ResumeBlocked` sind keine Score- oder
Healing-Trigger.

Der gebundene AC-Verifier erzeugt den Evidence-Kern selbst im detached
Candidate-Checkout: Pfad-/Fund-/Importfakten für DIFF, EXISTS, IMPORT und die
GREP-Familie sowie Runner, Exit-Code, Laufzeit und einen begrenzten,
secret-redigierten Auszug für TEST. Die TEST-Evidence nennt außerdem Ursprung
und Version der bootstrapgebundenen Runner-Policy sowie das versionierte
Candidate-Prozessumgebungsprofil. Dasselbe Profil steht in IMPORT-Evidence;
es belegt die Environment-Allowlist, keine Prozesssandbox. `missing_evidence`
und `error` werden nicht durch ein beliebiges Dictionary heilbar gemacht.

## Abgelaufenes Legacy-Fenster und Rollout-Nachweis

Der atomare Legacy-Rollbackpfad war nur bis einschließlich `2.0.0a4`
zulässig. `agent.authority_mode`, `legacy_steps` und
`config/gates.legacy.json` sind aus der Runtime entfernt;
`SAMUEL_AUTHORITY_MODE` oder ein alter Konfigurationsschlüssel blockieren den
Start ausdrücklich. Es gibt damit keine zweite Autoritätsverdrahtung mehr.

Die Profilauflösung erfolgt weiterhin vor Bus- und Slice-Wiring. Außerhalb von
Self sind nur `default` oder das strengere Environment-Opt-in `audit`
kompatibel; Self erzwingt `config/gates.self.json`. Inkompatible Werte sowie
fehlende oder ungültige aktive Profildateien blockieren fail-closed.

Ab `2.0.0a5` blockiert das Release-Gate pensionierte Legacy-Artefakte. Außerdem muss
`docs/rollout/issue-399.json` nach dem versions- und digestgebundenen Schema
`docs/rollout/issue-399.schema.json` echte Nachweise für erfolgreichen Lauf,
blockierten Lauf, heilbaren Lauf, erneut gescheiterten Lauf und einen
Rollback-Drill enthalten. `tools/rollout_evidence.py` prüft Subject-,
Policy-, Observation-, Correlation-, Zeit-, Head-, Event-, PR- und
Rollbacksemantik offline. Die reale Evidence aus #577 ist materialisiert und
über #580 an Schema und Releasevertrag gebunden. Abwesenheit der pensionierten
Artefakte und gültige Evidence sind getrennte a5-Schranken.

## Verbindliche Quellen

- `samuel/slices/pr_gates/handler.py`: Gate-Schleife und terminale Events
- `samuel/core/evaluation_observation.py`: Identitäten und Digests
- `samuel/core/external_evidence.py`: Advisory-Projektion und Assessment
- `samuel/slices/evaluation/handler.py`: passiver Observer und direkter,
  unverdrahteter Kompatibilitäts-Handler
- `samuel/slices/evaluation/bound_scoring.py`: Telemetrieformel
- `samuel/core/ports.py`: Observation-/Run-Projection-Verträge
- `samuel/adapters/gitea/adapter.py`: erster realer SCM-Check-Leseadapter
- `samuel/adapters/state/sqlite.py`: aktive Materialisierung und Serienqueries
- `samuel/adapters/state/legacy.py`: einseitiger checksumgebundener Import
- `samuel/slices/run_projection/handler.py`: passive Run-Projektion
- `samuel/slices/evaluation/presentation.py`: entkoppelte Darstellung
- `samuel/slices/healing/bound.py`: Klassifikation und Einmalversuch
- `config/agent.json`, `config/eval.json`, die drei aktiven
  `config/gates*.json` und `config/workflows/*.json`: ausgelieferte Workflows
  und Policies

Maschinenlesbare Fakten wie Profile, Events, Commands, AC-Tags und
Persistenzartefakte werden zusätzlich über die generierte Runtime-Referenz
geführt. Semantische Prosa bleibt reviewpflichtig; siehe Governance-Issue
#572.
