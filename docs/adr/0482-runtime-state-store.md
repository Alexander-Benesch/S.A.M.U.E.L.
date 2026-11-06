---
id: ADR-0482
title: Versionierter SQLite-State für Beobachtungen, Projektionen und Workflow-Autorität
status: accepted
decision_issue: 482
decision_date: 2026-08-29
decision_digest: sha256:99db5f82c3f57b7569b0dd866723050d4078f0b51e3ca332a0769c5ebf757d32
amendment: 2026-09-19 — Schema v10, Workflow-Tokenzulassung und gebundene Planning-Klärung
supersedes: []
superseded_by: []
---

# Versionierter SQLite-State für Beobachtungen, Projektionen und Workflow-Autorität

## Kontext

Evaluation-History, Baselines, Quality-Metrics und Healing-Claims liegen heute
in mehreren JSON-Dateien mit verschiedenen Schlüsseln und globalen Limits.
Session- und Implementation-Checkpoints sind prozesslokale Dicts. Das
Dashboard rekonstruiert Runs verlustbehaftet aus einer begrenzten, rotierenden
Audit-JSONL-Sicht. Dadurch verdrängt Aktivität eines Issues fremde Historie,
und Neustart oder Logrotation zerstören Laufzeitkontext.

Eine Datei pro Issue würde Abfragen vereinfachen, aber Retention weiterhin
durch Umschreiben einzelner Dateien vollziehen und Atomarität nur verteilen.
`max_parallel=1` ist kein SQLite-Treiber. Die tragenden Gründe sind
queryfähige issue-/run-/serienbezogene Historie, unabhängige Retention und
transaktionale Claims, Intents und Checkpoints.

SQLite entfernt zugleich die direkte Textinspektion des Runtimezustands, die
im Homelab für Diagnose wertvoll ist. Dieser Verlust braucht eine
Produktgrenze, nicht nur ein internes Debugskript.

## Entscheidung

S.A.M.U.E.L. erhält einen versionierten lokalen SQLite-State-Store unter dem
persistenten `agent.data_dir`. Audit-JSONL bleibt revisions- und
complianceorientierte Evidence, ist aber weder Runtime-Datenbank noch
vollständige Rekonstruktionsquelle.

Der Core verwendet getrennte Ports mit unterschiedlicher Fehlersemantik:

- Der **ObservationStore** hält unveränderliche gebundene Rohbeobachtungen und
  deren versionierte Ableitungen.
- Der **RunProjectionStore** hält die queryoptimierte Dashboard-Sicht. Ein
  Schreibfehler wird sichtbar und nachholbar, blockiert aber nicht den
  Freigabeworkflow.
- Der **AuthorityStateStore** hält Checkpoints, Leases, Healing-Claims,
  Operations-Intents, Reconcile-State und Authority-Epoch. Ein fehlgeschlagener
  autoritativer Write blockiert den Eintritt in den nächsten unsicheren
  Abschnitt fail-closed.

Die Ports können einen Adapter und Schema-Lifecycle teilen, behaupten aber
nicht dieselbe Kritikalität.

`samuel state status|dump --json` ist Bestandteil der ersten Ausbaustufe und
liefert eine secret- und PII-arme, maschinenlesbare Sicht auf Schema, Tabellen,
Serien, Epoch, Reconcile und Kapazität.

## Speicher- und Schemavertrag

Der Referenzadapter unterstützt SQLite/WAL nur auf einem geprüften lokalen
Dateisystem. NFS, CIFS und unbekannte Netzmounts blockieren den Start. systemd-
und Containerbetrieb müssen `agent.data_dir` als persistentes lokales Volume
verankern.

Schemaänderungen verwenden `PRAGMA user_version`; ein neuerer unbekannter
Stand blockiert einen Downgrade. Zeitwerte sind UTC. Die Vacuum-Strategie wird
vor dem ersten produktiven Schema festgelegt, damit Retention die Datei auch
physisch kontrollierbar hält.

Backups verwenden die SQLite Backup API oder `VACUUM INTO`, niemals `cp` einer
aktiven WAL-Datenbank. Migrationen aus JSON sind idempotent,
checksumgebunden und einseitig. Migrierte Quelldateien werden so markiert, dass
alte Codestände sie nicht still weiterbeschreiben.

## Beobachtungs- und Ableitungsidentität

Eine Rohbeobachtung wird identifiziert durch

`observation_key = hash(EvaluationSubject + Evidence-Digest + Observation-Schema)`.

Eine Scoreableitung verwendet

`score_key = hash(observation_key + Scoring-Policy-Version + Formelversion)`.

Der Ableitungsschlüssel bindet damit immer seine konkrete Rohbeobachtung.
Mehrere Formelversionen sind legitime Ableitungen und duplizieren keine
Evidence. Persistiert werden die Roheingaben je Kriterium, ihre Herkunft,
Anwendbarkeit/Ausführung, Ergebnisstatus und Kategoriezuordnung sowie
Familienzähler. Formeln bleiben daraus replayfähig.

`unbound_worktree` und `bound_acceptance_evidence` sind getrennte Serien und
werden nicht gemeinsam ausgewertet. Der GateResult-/Observation-Schemawechsel
aus ADR-0620 ist ein weiterer expliziter Serienschnitt.

## Autoritätszustand und externe Wirkungen

Checkpoint, Ownership und Fortsetzbarkeit sind getrennt. Ein Checkpoint bindet
Run, Issue, Workflow, `EvaluationSubject`, Workspace, Branch, Base/Head und
sichere Boundary. Ein abgelaufenes Lease erlaubt einen Übernahmeversuch, aber
kein Resume ohne OS-Lock, Zustandsprädikat und SCM-Abgleich.

Healing bleibt at-most-once. Der Claim wird vor der Wirkung geschrieben und
wechselt von `claimed` nach `attempted` oder operatorgesetzt nach `abandoned`;
er wird nicht automatisch freigegeben.

Commit, Push und PR-Erstellung erhalten persistente Saga-Intents und
überprüfbare Postconditions. `correlation_id` ist keine
Wirkungsidempotenz. Commit-Recovery verwendet Parent-/Tree-Identität aus
ADR-0618; PR-Recovery notiert primär die PR-Nummer und prüft Head, Base und
Revision. Ein Body-Marker ist nur Fallback für das Fenster vor der Notierung.

## Workflow-Tokenzulassung

Schema v9 erweitert denselben schmalen Authority-State um
`workflow_budget_admissions` und `llm_budget_attempts`. Die Zulassung wird vor
dem ersten Planning-/Klärungs-LLM-Aufruf geschrieben und bindet Repository,
Issue, akzeptierte Invocation, Source-Snapshot sowie Workflow- und
Budgetpolicy. `correlation_id` bleibt reine Laufzuordnung. Nach erfolgreichem
Planpost werden der exakte Acceptance-Contract und die konkrete
Plan-Kommentar-ID einmalig an diese Zulassung gebunden; Polling, Webhook und
Resume finden sie über beide Werte wieder.

Jeder physische Retry- oder Fallback-Attempt reserviert in einer
`BEGIN IMMEDIATE`-Transaktion vor der Sendung seinen konservativen
Eingabe-Bound und den providerseitig erzwungenen Ausgabe-Bound. Verlässlich
gemeldete Usage setzt den Attempt auf `settled` und belastet die tatsächliche
Summe. Timeout, verlorene Antwort, ungemeldete Usage oder eine Überschreitung
des reservierten Bounds setzen ihn auf `unknown` beziehungsweise lassen im
Persistenzfehlerfall `reserved` bestehen; beide Zustände halten den vollen
Bound. Eine Wiederholung oder ein Fallback benötigt eine eigene Reservation.

Das ist Tokenauthority für einen bestehenden Workflowauftrag, kein Approval,
Jobstore oder Billingservice. Preis- und Rechnungswerte bleiben getrennte
Meteringdaten. Der State-Dump und Reconcile führen nur Identitäten, Status und
Zähler, keine Prompt- oder Antwortinhalte.

## Gebundene Planning-Klärung

Schema v10 ergänzt `planning_clarifications` im selben Authority-State. Eine
Serie bindet Repository, Issue, PlanningSourceSnapshot-Digest,
Workflow-Budgetzulassung, endliche Deadline, maximal zwei Runden und die
revisionsgebundene SCM-Frage-/Antwort-Evidence. Frage- und Antworttexte können
personenbezogene Inhalte enthalten und sind deshalb als `pii_bearing`
klassifiziert. Sie werden nicht in Audit- oder Dashboardpayloads projiziert.
Solange die Serie oder der daraus entstandene Plan Authority trägt, gibt es
keine zeitbasierte Löschung. Restore und Reconcile behandeln die Tabelle wie
den übrigen autoritativen State.

## Authority-Epoch und Reconcile

Die Datenbank besitzt eine `instance_uuid` und einen monotonen
`authority_epoch`. Eine Sidecar-Hochwassermarke außerhalb des DB-Backup-
Artefakts wird nach autoritativen Commits synchron aktualisiert, bevor eine
davon abhängige externe Wirkung beginnt. Autoritätsereignisse tragen die Epoch
zusätzlich im Auditstrom; der asynchrone, rotierbare Audit-Sink bleibt ein
Zusatznachweis und keine Korrektheitsquelle.

Ein Start mit älterer DB-Epoch als Sidecar-/Audit-Hochwassermarke,
UUID-Abweichung oder unbekannter Herkunft führt in einen sichtbaren
Reconcile-Modus. Reconcile blockiert automatisches Healing und Resume, bis
Claims, Intents, SCM und Workspace-Registry abgeglichen sind. Der unterstützte
Restorepfad ist `samuel state restore`. Das vollständige manuelle Ersetzen von
DB, Sidecar und Audit bleibt unsupported.

## Resume-Vertrag

ADR-0618 ist umgesetzt; #633 aktiviert restartfähiges Resume ausschließlich
für sichere Finalisierungsgrenzen. Die Reihenfolge lautet OS-Lock des
vorhandenen Run-Worktrees, Übernahme eines abgelaufenen Leases per CAS,
Bindungs-/Zustandsprädikat und SCM-Abgleich.

Fortsetzung verlangt denselben Repository-/Run-/Contract-/Policy-/Schema- und
Workspacegegenstand, einen sauberen erwarteten Index/Worktree und einen HEAD,
der entweder dem Checkpoint oder einem verifizierten Commit-Intent desselben
Runs entspricht. Commit-erledigt/Push-offen, Push-erledigt/Event-offen und
PR-erstellt/noch-nicht-notiert werden separat abgeglichen. Ein nicht
fortsetzbarer Run wird quarantänisiert; der Hauptcheckout wird nicht per
Auto-Hard-Reset repariert. LLM-Runden und ihr Prompt-/Tokenzustand sind nicht
resumefähig. Reconcile blockiert jede automatische Fortsetzung.

## Retention

Retention wird nicht zusammen mit der Migration erstmals löschend aktiviert.
Sie folgt vier Stufen: Schema und Dry-Run-Report, Vollzug hinter deaktiviertem
Flag, Beobachtungs-/Lösch-Evidence, bewusste Aktivierung in einem separaten
Change.

Audit-Evidence startet mit 365 Tagen, abfrageorientierte Runtime-/Dashboard-
History mit 90 Tagen. Claims, Intents, Tombstones und Worktree-Quarantäne
erhalten eigene Fristen. Lease-/Fortsetzbarkeit und spätere physische Löschung
sind getrennte Schwellen. PII-Anonymisierung setzt eine Spaltenklassifikation
voraus; ein generisches „sensiblen Zustand entfernen“ reicht nicht.

## Umsetzungskette

1. Store, Schema, Diagnose, lokales-FS-Prüfung und Backup — ohne
   Verhaltensänderung außer Shadowwrites/Health.
2. Rohbeobachtungen, Ableitungen und Run-Projektion migrieren.
3. Checkpoints, Claims, Intents, Lease/Epoch und Reconcile migrieren; Resume
   bleibt deaktiviert.
4. Resume nach ADR-0618 und vollständigen Crash-/SCM-/Lock-Drills aktivieren.
5. Backup/Restore und Retention nach Dry-Run stufenweise vollziehen.

Schritte 1 bis 3 hängen nicht von Worktrees ab. Schritt 4 hängt hart von
ADR-0618 ab. Schritt 2 muss den Serienschnitt aus ADR-0620 berücksichtigen.
Die Sandbox ADR-0619 ist unabhängig.

## Konsequenzen

- Eval-History je Issue und Serie wird nicht durch fremde Issues verdrängt.
- Dashboard-Runs überleben Auditrotation; Audit bleibt verlinkte Evidence.
- Autoritätszustand kann transaktional geschrieben und nach Restore sichtbar
  reconciled werden.
- SQLite ist ein neues kritisches lokales Betriebsartefakt mit explizitem
  Volume-, Backup-, Upgrade- und Downgradevertrag.
- Fehlende Evidence aktiviert keine neue Autoritätsgrenze; löschende Retention
  bleibt bis Stufe 5 deaktiviert.
- Der Umbau erfolgt in getrennt abnehmbaren PRs; das Dachissue schließt erst
  nach allen Teilschritten und ihren PR-/Push-Nachweisen.

## Implementierungsstand

- Stufe 1: #625 abgeschlossen (Grundschema, Diagnose, lokale FS-Grenze,
  Backup-API).
- Stufe 2: #627 abgeschlossen (Observations, Ableitungen, Quality-/Run-
  Projektion und nichtautoritative Legacy-Migration).
- Stufe 3: #629 implementiert Schema v3 mit Claims, diagnostischen
  Checkpoints/Intents/Leases, UUID/Epoch/Witness und sichtbarem Reconcile.
  Ein lokaler OS-Lock serialisiert Witness-Updates verschiedener Prozesse und
  publiziert darunter stets die aktuellste DB-Epoch.
  Round-Checkpoints tragen weiterhin `resume_eligible=false`.
- Stufe 4: #633 nutzt den in #618 umgesetzten ADR-0618-Worktree-Vertrag.
  `commit_pending`, `push_pending`, `gates_pending` und `pr_pending` sind
  restartfähig; OS-Lock, Lease-CAS, vollständige Binding-/Git-Prädikate und
  SCM-Postconditions verhindern doppelte Wirkungen. Bootstrap und Watch
  triggern die Prüfung, Operatoren verwenden `samuel resume`; Health, State
  und Dashboard zeigen pending, blocked und last outcome.
- Stufe 5a: #666 implementiert Schema v4, exklusiven Restore-Lifecycle,
  neue Autoritätslinien, vollständiges Reconcile und den Audit-Serienschnitt
  `authority.v2`.
- Stufe 5b: #667 implementiert Schema v5, vollständigen Retention-Katalog,
  Dry-Run, Managed Backups und Score-Replay ohne Löschwirkung.
- Stufe 5c (kategorieweiser Löschvollzug) bleibt offen; #482 bleibt deshalb
  das offene Dachissue.

## Nachtrag 2026-08-30 — Stufe 5: Restore-Autorität und Retention

### Geltungsgrenze

Dieser Nachtrag entscheidet den noch offenen Zielvertrag der Stufe 5. Der
Entscheidungschange selbst aktivierte weder Restore noch automatische
Löschung; den aktuellen Umsetzungsstand nennt die Liste darüber. Die Umsetzung bleibt in
drei getrennt abnehmbaren Teilschritten 5a, 5b und 5c aufgeteilt. Jeder
Teilschritt braucht eigene Tests, Dokumentationsänderungen sowie PR-, Push-
und Rollout-Evidence. Insbesondere gibt es keinen gemeinsamen
Restore-/Retention-Big-Bang.

### Stufe 5a — exklusiver Restore und neue Autoritätslinie

Ein unterstützter Restore hält für seine vollständige Lebensdauer einen
eigenen exklusiven Lifecycle-Lock. Dieser Lock ist vom kurz gehaltenen
Witness-Mutex getrennt. Leser autoritativen Zustands und konkurrierende
Schreiber dürfen während des Austauschs keinen teilweise ersetzten Zustand
beobachten. Die verbindliche Reihenfolge lautet:

1. Lifecycle-Lock erwerben und einen Restore-Sentinel mit Operations-ID,
   Quelle und Vorzustand schreiben,
2. Backup vollständig in eine Staging-Datenbank einlesen und dort Schema,
   Integrität, Digest und Herkunft prüfen,
3. in einer Transaktion eine neue `instance_uuid`, `restored_from_uuid`,
   Backup-Digest, Operations-ID, `pre_restore_epoch_highwater` und
   `reconcile_required` setzen,
4. die geprüfte Datenbank atomar einwechseln,
5. Witness unter seinem eigenen Mutex auf mindestens die neue DB-Epoch
   fortschreiben und erst danach den Sentinel entfernen.

`authority_epoch` bleibt über alle `instance_uuid`-Linien global monoton und
wird durch Restore nicht zurückgesetzt. Die vollständige
Reconcile-Abschlussformel lautet:

```text
new_epoch = max(
  current_db_epoch,
  pre_restore_epoch_highwater,
  witness_epoch,
  conservatively_applicable_audit_epoch
) + 1
```

Der Auditstrom erhält mit `instance_uuid` und `authority_epoch` einen
versionierten Serienschnitt. Ältere Ereignisse ohne `instance_uuid` werden
für die Hochwassermarke konservativ berücksichtigt und nicht als
linienfremd verworfen. Der asynchrone Audit-Sink bleibt Zusatznachweis und
keine Korrektheitsquelle.

Eine offene Restore-Operation wird nicht durch einen gewöhnlichen zweiten
Restore ersetzt. Eine ausdrücklich operatorbestätigte Supersession nennt die
alte Operations-ID und einen Grund, verkettet die bisherige Hochwassermarke,
erzeugt eine neue Autoritätslinie und startet eine vollständige neue
Klassifikation. Sie übernimmt keine Klassifikation der superseded Operation
und ist kein Ausweg aus `scan_failed`.

Reconcile klassifiziert jeden relevanten Claim, Intent, Checkpoint, Workspace
und jede bereits eingetretene SCM-Wirkung als `verified_effect`,
`verified_absent`, `abandoned` oder `unresolved`. `scan_failed` kann
ausschließlich durch einen erfolgreichen erneuten Scan verlassen werden.
Automatisches Resume, Healing und löschende Retention bleiben bis zum
vollständigen Abschluss blockiert. `restore_operations` ist während eines
offenen Reconcile nicht altersbedingt löschbar, weil die Zeile die
Hochwassermarke trägt. Erst nach Abschluss ist sie Retention-Evidence.

**Umsetzungsnachweis #666:** Der SQLite-Adapter verwendet Schema v4 mit
`restore_operations` und `reconcile_entries`. Der separate Lifecycle-`flock`
deckt Status/Dump, Backup, fachliche Stores und den vollständigen Restore ab.
Der Operatorpfad lautet `state restore`, `reconcile-scan`,
`reconcile-status`, begründete `reconcile-classify`-Entscheidungen und
`reconcile-complete`. Bekannte SCM-Wirkungen werden ausschließlich über den
`IVersionControl`-Port geprüft; die PR-Recovery verwendet Nummer und den
bestehenden backendneutralen Intent-Marker. Ein Sentinel, ein fehlgeschlagener
Scan oder ein unresolved Eintrag hält den Zustand fail-closed. Löschende
Retention bleibt außerhalb dieses Changes.

### Stufe 5b — vollständiger Retention-Vertrag und Dry-Run

Das ausgelieferte Standardprofil ist `eu_operational`. Einsatzbezogene
Profile, insbesondere ein AI-Act-High-Risk-Profil, sind ausdrücklich opt-in,
rollenbezogen und keine Konformitätszusage. Die zehnjährige Aufbewahrung
technischer Unterlagen nach dem dafür maßgeblichen Einsatzkontext liegt
außerhalb des Runtime-State-Retention-Vertrags; versionierte ADRs, System-
und Konformitätsdokumente werden nicht als State-Store-Zeilen modelliert.

Jede Retention-Kategorie besitzt einen eigenen Modus und einen eigenen
Policy-Digest über Frist, Zeitanker, Feld-/PII-Klassifikation und die für
diese Kategorie wirksame Profiluntergrenze. Ein separater Profil-/Rollendigest
invalidiert die Freigaben aller vom Wechsel betroffenen Kategorien. Die
globale Notabschaltung ist dagegen reiner Laufzeitzustand, erscheint in
`state status` und Health und ist nicht Teil eines Policy-Digests.

Eine konfigurierte Frist unter der aktiven Profiluntergrenze blockiert das
Laden fail-closed. Die Laufzeit verwendet zusätzlich den konservativeren
Cutoff. Profil-, Rollen- oder relevante Policy-Wechsel setzen betroffene
Kategorien auf `report_only_pending_review`; jede Kategorie wird einzeln
gegen ihren aktuellen Digest freigegeben. Ein Profilwechsel darf dadurch
keine zuvor maskierte kurze Frist schlagartig vollziehen.

Zeitanker sind kategorienbezogen. Für tabellarische Terminalzustände ist der
dokumentierte Terminalzeitpunkt maßgeblich. Bei Audit-JSONL gilt der letzte
erfolgreich geparste Event-Zeitstempel der Datei, nicht Dateiname, Rotation
oder `mtime`. Leere, beschädigte oder nicht vollständig lesbare Dateien
werden nicht gelöscht und erzeugen ein sichtbares Finding. Der Dry-Run weist
je Kategorie Profil, konfigurierten und wirksamen Zeitraum, absoluten Cutoff,
Anker, Treffermenge, Schutzgründe und Policy-Digest aus.

Der Katalog ist in beide Richtungen vollständig: unbekannte Kategorien in
der Konfiguration werden abgelehnt; ein im Schema oder in der Registry
vorhandenes Objekt ohne Katalogeintrag wird nicht gelöscht und erzeugt Health-
und Report-Warnungen. CI vergleicht den Katalog mechanisch mit dem realen
Schema und den extern verwalteten Artefaktklassen.

`pii_anonymize_after_days` ist kein wirksamer Vollzugsvertrag und wird in 5b
aus dem aktiven Schema entfernt beziehungsweise bei alter Konfiguration mit
einer eindeutigen Migrationsdiagnose abgelehnt. Eine spätere Anonymisierung
ist nur über explizite, feldbezogene Regeln zulässig. Vor Stufe 5c müssen alle
strukturierten Spalten und JSON-Payloadfelder als PII-frei, PII-tragend,
Secret-tragend oder nicht automatisch prüfbar klassifiziert sein.

Rohbeobachtung und Ableitung behalten getrennte Fristen. Scoreableitungen und
Run-Projektionen dürfen erst kürzer als Rohbeobachtungen gehalten werden,
wenn ein operatorgeeigneter Replay-Pfad existiert. Replay bindet die
Rohbeobachtung an Policy- und Formelversion, ist idempotent und publiziert
weder `ScoreObserved` noch aktualisiert es Quality-EWMA. Quality-EWMA wird
nicht zeitbasiert gelöscht; ein späterer Reset braucht eine eigene sichtbare
Semantik, Serie, Begründung und Evidence.

Technisch verwaltete Backups liegen in einem eigenen
`managed_backup_dir`. Nur dort kann S.A.M.U.E.L. eine Löschzusage technisch
durchsetzen. Ein Backup, auf das eine offene Restore-Operation verweist,
bleibt gepinnt. Externe Kopien liegen außerhalb dieser Zusage und werden in
der Datenschutz- und Betriebsdokumentation als Betreiberverantwortung
benannt.

### Mechanisch belegter Bestandskatalog

Der folgende Katalog wurde am 2026-08-30 zunächst gegen Runtime-Schema v3 und
die Workspace-Registry geprüft und nach #666 gegen das tatsächlich erzeugte
Schema v4 ergänzt. Er ist Ausgangspunkt, nicht Ersatz für die in 5b zu
liefernde maschinelle Vollständigkeitsprüfung.

| Schema-/Artefaktklasse | Retention-Ziel | Schutzbedingung |
|---|---|---|
| `observations` | Rohbeobachtung zunächst `P1Y` | vollständige Payload-Klassifikation vor Vollzug |
| `score_derivations` | zunächst `P90D` | nur nach verfügbarem, getesteten Replay |
| `evaluation_terminals` | zunächst `P90D` | Terminalanker und Serienbindung |
| `run_projections` | zunächst `P90D` | nur `blocked`, `complete` oder `unbound`; nicht terminale/unklare Zustände bleiben durch `non_terminal_never` geschützt; Rohbeobachtung bleibt länger (#672) |
| `quality_metrics` | keine zeitbasierte Löschung | EWMA ist nicht exakt aus Restdaten rekonstruierbar |
| `healing_claims` | aktive Claims nie; abgeschlossene zunächst `P1Y` | permanenter minimaler At-most-once-Tombstone bleibt |
| `workflow_checkpoints` | aktive/Reconcile-relevante nie; terminale zunächst `P90D` | keine Löschung bei offener Autorität |
| `operation_intents` | aktive/Reconcile-relevante nie; terminale zunächst `P1Y` | externe Postcondition muss geklärt sein |
| `workflow_budget_admissions` (Schema v9) | keine zeitbasierte Löschung | Workflowauthority und Planbinding bleiben erhalten |
| `llm_budget_attempts` (Schema v9) | keine zeitbasierte Löschung | unbekannte oder reservierte Usage darf nicht freigegeben werden |
| `planning_clarifications` (Schema v10) | keine zeitbasierte Löschung | aktive Serie und gebundene Plan-/Approval-Evidence müssen Restart, Restore und Reconcile überleben |
| `authority_records` | keine zeitbasierte Löschung | enthält derzeit Autoritäts-/Resume-Tombstones |
| `legacy_imports` | keine zeitbasierte Löschung | checksumgebundene Einseitigkeit der Migration |
| `authority_metadata` | keine zeitbasierte Löschung | UUID, Epoch und Reconcile-Autorität |
| `schema_migrations` | keine zeitbasierte Löschung | Schemaherkunft |
| `authority_leases` | Lifecycle-Bereinigung, keine pauschale Zeitfrist | Lease-Ablauf ist nicht Evidence-Retention |
| `restore_operations` (5a) | offen nie; abgeschlossen eigene Evidence-Frist | trägt bis Reconcile-Abschluss die Hochwassermarke |
| `reconcile_entries` (5a) | solange Operation offen nie; danach eigene Evidence-Frist | Klassifikation und Begründung bleiben an Restore-Operation gebunden |
| Audit-JSONL | zunächst `P1Y` | letzter parsebarer Event-Zeitstempel; unlesbar bleibt |
| verwaltete Backups | zunächst `P30D` | offene Restore-Referenz pinnt; nur `managed_backup_dir` |
| Workspace-Registry `workspaces` | statusbezogene Lifecycle-Regeln | aktive/quarantänisierte Einträge nicht still löschen |
| quarantänisierte Worktrees | zunächst `P7D` report-only | bestehende Count-/Kapazitätsgrenzen und Operator-`discard` |

Die Zahlen sind ausgelieferte Betriebsdefaults, keine universelle Rechtsfrist.
Ein optionales Profil darf für ausdrücklich benannte Kategorien eine höhere
Untergrenze setzen. Es verändert nicht still die Bedeutung anderer
Kategorien.

**Umsetzungsnachweis #667:** Schema v5 ergänzt die append-only
`managed_backups`-Registry und die standardmäßig aktive, in State/Health
sichtbare Retention-Notabschaltung. `IRetentionStateStore` liefert den
realen Tabellen-/Spaltenkatalog und ausschließlich nicht löschende Snapshots.
`config/privacy.json` enthält 19 Kategorien für 16 State-Tabellen und die drei
externen Klassen Audit, Workspaces und Quarantäne; das ausgelieferte Profil
ist `eu_operational`, das rollenbezogene
`eu_ai_act_high_risk_support` bleibt Opt-in und ohne Konformitätszusage.
Kategorie- und Profil-/Rollendigest binden append-only Freigaben im
bestehenden Authority-Store. `samuel retention dry-run` meldet Cutoffs,
Treffer, Schutzgründe, Klassifikation und Katalogdrift, ohne Daten zu
mutieren. `backup` verwendet die SQLite Backup API im verwalteten Verzeichnis;
`replay-scores` teilt den Ableitungscode mit der Live-Beobachtung, akzeptiert
wiederholbare Verzeichnisse mit versionierter `eval.json` und erzeugt weder
Events noch EWMA-Updates. Der Modus `enforce` wird in Stufe 5b beim
Laden abgelehnt; es gibt keinen Delete-Port.

**Umsetzungsnachweis #673:** Schema v6 ergänzt die permanenten Tabellen
`retention_category_states` und `retention_executions` sowie den getrennten
fail-closed `IRetentionExecutionStore`. Dieser Port akzeptiert weder
Tabellennamen noch SQL und registriert zunächst ausschließlich
`score_derivations`. Kategorie-Autorität bindet Kategorie-/Profil-/Rollendigest
und bei `enforce` zusätzlich einen Plan-Digest über absoluten UTC-Cutoff,
Anker, die Plan-Schemaserie `retention-execution-plan.v1` und sortierte
SHA-256-Objektidentitäten. Der Kategorie-Digest bindet dabei Feld-/Payload-
Klassifikation und Schutzregeln; die Kandidatenmenge bindet deren ausgewerteten
Zeilenstatus. Revalidierung, Löschung,
append-only Receipt und Authority-Epoch sind eine Transaktion; Wiederholung
ist idempotent. Drift oder Schreibfehler blockiert und suspendiert die
Kategorie. Restore setzt den globalen Stop und suspendiert vorhandene
Vollzugsautorität.

Das ist ein deaktiviert ausgeliefertes Fundament, keine produktive
Aktivierung: alle Kategorien in `config/privacy.json` bleiben `report_only`,
die globale Notabschaltung ist aktiv und kein Scheduler ruft den Vollzug auf.
Ein synthetischer Canary belegt nur Mechanik. Die erste reale Aktivierung in
#668 verlangt weiterhin tatsächlich abgelaufene produktive Evidence und einen
eigenen Rolloutnachweis.

**Korrektur #668:** Schema v8 ergänzt den Enforce-Zustand um den absoluten
Grant-Cutoff und den serverseitigen Aktivierungszeitpunkt. Aktivierung prüft
den Cutoff gegen die an diesem Zeitpunkt wirksame Kalenderfrist; Vollzug
verwendet dieselbe Grantzeit und akzeptiert keine migrierte Enforce-Zeile ohne
diese Bindung. Dadurch wird ein zuvor zu junger Cutoff nicht allein durch
Warten gültig, während ein bereits konservativ gebundener Plan nicht allein
durch Zeitablauf verfällt. Der SQLite-Vollzug gleicht den aktuellen
Tabellenkatalog und die vollständige Payloadklassifikation innerhalb derselben
Transaktion mit dem typisierten Kategorievertrag ab. Ein vorhandener,
integritätsgeprüfter Receipt wird anhand seiner gespeicherten Identität vor
heutigen Stop-, Modus- und Klassifikationsregeln zurückgegeben und erzeugt
keine neue Löschwirkung. Alle ausgelieferten Kategorien bleiben
`report_only`; der reale Rollout eines abgelaufenen Betriebsobjekts bleibt
separate Abschluss-Evidence von #668.
Eine neue passive Statusprojektion zeigt diese Grenzen im Dashboard mit
Not-Aus, Pending-Review, Digests, Grantzeit und letzter Wirkung, ohne
Retention-Payloads oder neue Operatorauthority offenzulegen.

**Umsetzungsnachweis #549:** Schema v9 persistiert die vor Planning gebundene
Workflow-Tokenzulassung und jede physische Attempt-Reservation. Admission,
Reservation und Settlement erhöhen die bestehende Authority-Epoch und tragen
`authority.v2`-Bindings in Audit und Dashboard. Restart-/Restore-Reconcile
bewahrt Zulassungen und volle unbekannte Reservationen. Die beiden Tabellen
sind vollständig klassifiziert und standardmäßig `report_only` ohne
Zeitlöschung. Reale Provider-Qualification für Timeout, Retry und Fallback
bleibt eine getrennte Abschlussbedingung des Issues.

### Stufe 5c — kategorieweiser Vollzug

Löschender Vollzug wird ausschließlich kategorieweise aktiviert. Jede
Aktivierung bindet aktuellen Kategorie- und Profil-/Rollendigest, einen
erfolgreichen Dry-Run, Feldklassifikation, Backup/Restore-Grenzen,
Beobachtungs- und Lösch-Evidence sowie einen getesteten Abbruchpfad. Ein
Fehler in einer Kategorie blockiert deren Löschung, nicht die Beweisspur.

Offene Autoritätsobjekte, gepinnte Backups, `scan_failed`, unbekannte
Katalogobjekte und nicht vollständig klassifizierte Payloads sind niemals
altersbedingt löschbar. Quarantäne ist nicht die erste automatisch
aktivierte Kategorie. Quality-EWMA, Legacy-Importmarker und permanente
At-most-once-/Autoritäts-Tombstones bleiben außerhalb zeitbasierter Löschung.

### Abhängigkeiten und Ablösung

- **5a** liefert Restore, Autoritätslinie und Reconcile; es hängt nicht von
  löschender Retention ab.
- **5b** hängt von 5a für die Definition Reconcile-relevanter und gepinnter
  Objekte ab. Es liefert Katalog, Policy, Dry-Run, Klassifikation, verwaltete
  Backups und Replay, aber keinen Löschvollzug.
- **5c** hängt vollständig von 5b ab und aktiviert Kategorien in getrennten
  Changes mit eigener Evidence. Es darf 5b nicht zusammen mit der ersten
  Löschaktivierung ausrollen.

Dieser Nachtrag präzisiert und ersetzt ausschließlich den offenen
Stufe-5-Entscheidungsraum des ursprünglichen ADR. Die Entscheidungen und
Implementierungsnachweise der Stufen 1 bis 4 bleiben unverändert.
