# Technische Beschreibungen — S.A.M.U.E.L. v2

Dokumentation der zentralen Pipelines. Jeder Knotenpunkt mit Input/Output,
beteiligten Dateien, Sprach-Unterstützung, Voraussetzungen und Beispielen.

**Prüfdatum:** 2026-09-21 · **Abgeglichener Commit:**
`05ea89ec9b93a6838e1ddeca66f23fe69adcfab9`

Diese Seite beschreibt die ausgelieferte Produktpipeline. Installation,
Szenario und Runbook eines eigenständigen Demonstrationsprojekts gehören
nicht in dieses Repository. Die unter #658 geführte reale
Referenzqualification bewahrt für die dokumentierte a15-Referenzkombination
positive Teilnachweise; der vorgeschriebene menschliche Golden-PR-Merge wurde
nicht erfüllt. Das ist weder ein vollständiger D0-PASS noch eine allgemeine
Beta- oder Betriebsfreigabe.
Die aktuellen Merge- und MANUAL-Hinweise sind ausschließlich Projektionen
des gebundenen Subjects: Planfreigabe ist getrennt vom MANUAL-Receipt;
`PRMerged` erzeugt keinen pauschalen Issue- oder Qualification-Abschluss.


---

## Pipeline-Übersicht

Der vollständige E2E-Flow von Issue bis PR besteht aus 4 Pipelines, die über
das Bus-System verkettet sind:

```
┌─────────────────────────────────────────────────────────────┐
│  Issue (Gitea)                                              │
└────────────────────┬────────────────────────────────────────┘
                     │  IssueReady Event
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  PIPELINE 1:  PLANNING                                      │
│                                                             │
│  PlanIssueCommand → LLM(Plan-Prompt) → validate_plan        │
│                   → Contract-Parser / Pre-Check             │
│                   → höchstens ein gemeinsamer Retry         │
│                   → Post Plan → ggf. menschliche Freigabe   │
│                                                             │
│  Details: pipeline_planning.md                              │
└────────────────────┬────────────────────────────────────────┘
                     │  PlanValidated Event
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  PIPELINE 2:  IMPLEMENTATION (Context-Building)             │
│                                                             │
│  ImplementCommand                                           │
│   → K1 Issue laden                                          │
│   → K2-K11 Context bauen (Keywords, Skeleton, Grep, ...)    │
│   → K12 Prompt-Assembly                                     │
│   → K13 Validator-Gate                                      │
│   → K14 LLM-Loop (5 Runden, Retry mit echtem Code)          │
│   → K15 Patches anwenden                                    │
│   → K16 Git commit + Branch-Push                            │
│                                                             │
│  Details: pipeline_issue_to_llm.md                          │
└────────────────────┬────────────────────────────────────────┘
                     │  CodeGenerated Event
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  PIPELINE 3:  PR-GATES (einzige Freigabeautorität)          │
│                                                             │
│  CreatePRCommand                                            │
│   → G1 Repository/Base/Head/Contract/Policy binden          │
│   → G2 vollständigen Commit-Diff ermitteln                  │
│   → G4 Required-Preflight ohne Candidate-Prozess            │
│   → G4b Acceptance-Verifikation + nachgelagerte Gates       │
│   → G5 External-Gate-Plugins                                │
│   → G6 scm.create_pr()                                      │
│                                                             │
│  Details: pipeline_pr_gates.md                              │
└──────────┬───────────────────────────┬──────────────────────┘
           │ vollständige Evidence     │ Subject nicht etablierbar
           ▼                           ▼
 GateEvaluationCompleted       GateEvaluationUnavailable
           │
           ├── required bestanden → PRCreated → gebundener Review
           │                              ├── pass → optionaler Mergeentscheid
           │                              └── block/indeterminate → Blockade
           ├── Preflight blockiert → Gate 11 SKIP, kein Candidate-Prozess
           ├── Gate 11 eindeutig fehlgeschlagen → 1 Healing-Versuch
           └── Evaluation-Subscriber → ScoreObserved (nicht bindend)
```

```text
PIPELINE 4: PASSIVE EVALUATION
GateEvaluationCompleted/-Unavailable
  -> gebundene Rohbeobachtung in SQLite persistieren
  -> versionierte Score-Ableitung aus Gate-11-Evidence
  -> ScoreObserved ohne Workflowkante
  -> redigierte Issue-/Run-Projektion unabhängig von Auditrotation
  -> Darstellung erst getrennt nach PRCreated
```

Ein davon getrennter Operatorpfad liest mit `samuel evidence assess` einen
vorhandenen Gitea-Actions-Run. Er projiziert nur Run-, PR-, Workflow- und
Statusfacts, bindet sie an ein vorhandenes `EvaluationSubject` und speichert
das Assessment im selben Observation-Store. Dieser Pfad ist ausschließlich
advisory, startet keinen Providerlauf und beeinflusst weder Gates noch
Dispatch oder Mutation (#520/#679).

```text
RESTART-FINALISIERUNG (pipelineübergreifend, kein fünfter Fachworkflow)
Bootstrap / Watch / Operator -> ResumePendingCommand
  -> vorhandenen Run-Worktree per OS-Lock übernehmen
  -> abgelaufenes Lease per CAS übernehmen
  -> Binding-, Git- und SCM-Prädikate prüfen
  -> commit_pending | push_pending | gates_pending | pr_pending fortsetzen
  -> Drift: ResumeBlocked + Quarantäne, kein Reset/Force-Push
```

Der Resume-Koordinator läuft ausschließlich über Commands/Events und bestehende
Ports. Er rekonstruiert weder Planning noch einen halben LLM-/Healing-Round.
Ein resumefähiger Finalisierungscheckpoint trägt jedoch die bereits
autorisierte Workflow-Budgetzulassung weiter; Resume erzeugt keine neue
Zulassung aus der Correlation-ID.
Details der Finalisierung stehen in K16 und G6; Score und Healing bleiben von
Resume-Ereignissen unabhängig.

## End-to-End-Ablauf, Authority und Sichtbarkeit

Die optionale OCI-Python/Pytest-Toolchain (#978) gehört zur bestehenden
Runner-/Gate-Policy, nicht zur Producer-Authority. Doctor, Planning und TEST
validieren dasselbe read-only Artefakt; Gate 11 konsumiert weiterhin die
gebundene Acceptance-Evidence. Ein anderer Toolchain-Digest benötigt eine
neue Policy-/Subjectbindung. Der temporäre Doctor-Prüfer liest nur nativen
Branchschutz in Gitea oder GitHub; normale Runtimecredentials, Human Approval,
MANUAL und Human Merge bleiben davon unabhängig.

Die folgende Tabelle ist der Einstieg für einen realen Lauf. „Authority“ meint
die Komponente, deren Ergebnis den Übergang tatsächlich erlaubt oder stoppt;
ein Dashboard, LLM-Score oder Prompt ist nie Freigabeautorität.

| Stufe | Eingaben und tatsächlich eingesetzte Werkzeuge | Authority und Fehlersemantik | Evidence und Sichtbarkeit |
|---|---|---|---|
| Intake | SCM-Issue, Labels, CLI/REST/Watch; `IVersionControl` und Workflow-Konfiguration | Readiness-/Workflow-Regel entscheidet, ob `IssueReady` entsteht. Fehlende SCM-Konfiguration oder nicht passendes Issue blockiert/überspringt den Dispatch. | Issue/Labels, `IssueReady`, Audit und Run-Projektion; Watch-Exitcode bildet den terminalen Ausgang ab. |
| Planning | Issue-Text plus Repository, Base-Ref und vollständige SCM-Base-SHA; relevante Dateien, Skeleton und begrenzte Keyword-Suche werden bei jedem Command frisch im detached Base-Worktree gebaut, Architektur-Constraints und TEST-Runner-Policy stammen aus der Control Plane | Vor dem ersten LLM-Call bindet eine persistente Tokenzulassung Repository, Issue, Invocation, Source und Policy. Ein deterministischer Readiness-Check erkennt nur leere/ungültige Quellen, explizite Lücken und beweisbare Widersprüche. Bei Klärungsbedarf persistiert er höchstens zwei revisionsgebundene Runden mit je drei Fragen und expliziter endlicher Operatorfrist; Timeout, doppelte/späte/editierte Antwort oder Source-Drift blockieren ohne partiellen Contract. Nur ein ausdrückliches `samuel run` autorisiert nach terminalem Zustand eine neue Serie. Jeder physische Retry/Fallback reserviert atomar vor Sendung; unbekannte Usage hält den Bound. SCM-Auflösung und Snapshot-Materialisierung sowie Contract-Parser, Struktur-/Pre-Check-/Scope-Regeln blockieren fail-closed; das LLM autorisiert weder Readiness, Quellstand noch Plan. Eine am Ausgabetokenlimit unvollständige Providerantwort blockiert vor `PlanCreated`; der Operatorhinweis verweist auf Budget und Modell-/Prompt-Eignung statt den Issue-Text pauschal als unscharf zu bewerten. Eine im Snapshot fehlende Datei gilt nur mit passendem strukturiertem Scope als geplante Neuanlage, während vorhandene und ungescopte Referenzen skeletonpflichtig bleiben. Bei gültigem Scope sind dessen FILE-Einträge Mutationsauthority; Prosa-, Negativ- und TEST-Referenzen erweitern sie nicht. TEST-Readiness löst `test_cmd` vor Projektmarker auf und prüft Toolchain sowie bekannte Selektorgrammar ohne Ausführung. Der Planprompt erhält nur die daraus abgeleitete Selektorform und nie den Runnerbefehl. Ein formaler oder Readiness-Erstfehler darf genau den mit dem Pre-Check geteilten einzigen Retry verbrauchen. Precheck-Retries erhalten die konkreten fehlgeschlagenen Dimensionen und Validator-Warnungen; die tatsächliche Retry-Antwort wird nur bei unverändertem Source-/Scope-Contract, ohne Einzelregress und nach behobener Blocking-Dimension übernommen. Ein vorhandener autoritativer Plan blockiert einen impliziten Replan; nur `replan --reason` widerruft ihn und eine vorhandene Freigabe, bevor der Grund als abgegrenztes Feedback genau den Ersatzplan erreicht. Dieses Feedback erweitert weder Scope noch Authority. Standard, Watch, Chat und Self benötigen anschließend eine gebundene menschliche Planfreigabe. Die Freigabe wird als create-only Authority-Record an Plan, Contract, SCM-Quelle und vorhandenen Source Snapshot gebunden; spätere Statuslabels projizieren nur den Workflow. Autonomous, Night und Patch bleiben nur für klare Issues automatisch; ein Plan mit Klärungsbasis wartet auch dort auf `PlanApproved`. | `WorkflowBudgetAdmitted`, `LLMBudgetAttemptReserved/-Settled/-Blocked`, `ClarificationRequested/Waiting/Accepted/Superseded`, `PlanContextLoaded.source_snapshot`, `PlanCreated`, `PlanPreCheckCompleted`, höchstens ein `PlanRetry`, `PlanRetryEvaluated`, `PlanValidated`, `PlanPosted`, `TokenLimitHit`, `PlanBlocked`, `WorkflowAborted`, `PlanReplanRejected`, `PlanRevoked`; `plan_approval.v1`; source- und Plan-Kommentar-gebundener Contract im Issue. |
| Implementation | Freigegebener/validierter Plan samt PlanningSourceSnapshot und exakter Workflow-Budgetzulassung, Run-Worktree auf derselben Base-SHA, `build_full_context`, Context-Validator, LLM-Adapter, Patch-Parser und Workspace-Transaktion | Repository-, Issue-, Plan-Kommentar-, Budget- oder Base-Drift blockiert vor LLM beziehungsweise nochmals vor Commit-Wirkung. Context-Validator, Patchziel-Policy und atomarer Loop blockieren vor Candidate; das Modell kann weder Branch noch Erfolg autorisieren. | LLM-/Token- und Budgetattempt-Metadaten, `TokenLimitHit`, `LLMBudgetBlocked`, `WorkflowBlocked` oder `CodeGenerated`; Audit, Issue-/Run-Projektion und Dashboard. |
| Subject/Preflight | Repository, vollständige Base-/Head-SHA, Contract- und Policy-Digest; SCM-Vergleich und Gates 7b/8/9/13a/13b | Subject-Aufbau ist fail-closed. Ein fehlgeschlagenes **required** Preflight-Gate stoppt Candidate-Prozesse; restliche Gates werden `skipped_precondition`. | `GateEvaluationUnavailable` bei fehlendem Subject, sonst kriteriumsweise Gate-Evidence und `GateFailedEvent`; Audit/Dashboard/Reviewer-Briefing. |
| Acceptance und Rest-Gates | Bei deaktiviertem Provider: detached Candidate-Worktree und lokaler AC-Verifier. Nach qualifiziertem atomarem Cutover: persistierter Verification Request und exakt gebundene Provider-Evidence. Dazu restliche interne und externe Gates | Nur das aktive Required-Gate-Profil entscheidet. Der Providerpfad bindet Plan/Approval, Subject, Policy, Run/Attempt, Workflow, Tool, Environment, Nonce/Freshness und Integrität; er prüft die aktuelle Authority vor Verwendung erneut. Trust-/Infrastrukturfehler sind nicht healbar und es gibt keinen automatischen lokalen Fallback. Die ausgelieferte Providerkonfiguration ist deaktiviert und unqualifiziert. Ein ausschließlich offenes MANUAL-Kriterium wartet mit gebundenem Checkpoint fail-closed; es erzeugt keinen terminalen Failure. | Lokal `ACVerified`/`ACFailed`/`ACManualPending`; providerseitig `ProviderVerificationRequested/Pending/Blocked`, danach genau ein gebundenes Gate-Ergebnis; PR-Body, Audit, Projektion und Dashboard. |
| PR/Review/Merge | Positives Gate-Ergebnis, persistierter PR-Intent, SCM-PR-Revision, vollständiger Diff und Acceptance Contract | S.A.M.U.E.L. darf den PR nur für dasselbe Subject erstellen. Bei einem budgetgeschützten Wiedereintritt nach MANUAL-Pause werden die vorhandene Admission und die ursprüngliche Planfreigabe über Repository, Issue, aktiven Planvertrag und Plan-Kommentar aus Authority-State zurückgebunden; `manual_pending` und Restart widerrufen sie nicht; ein allein aus MANUAL-Pending stammendes `status:failed` wird nicht mehr projiziert. Der ursprüngliche Approvaltransport wird anhand seiner historischen SCM-Evidence revalidiert, ohne das aktuelle `status:approved`-Label zu verlangen. Fehlende, fremde, stale oder durch Replan widerrufene Authority blockiert vor PR und Provider, ohne neue Authority oder einen neuen Budgettopf anzulegen. Der strukturierte Review bindet `pass|block|indeterminate` samt Findings an Subject, Diff, Policy, Tool und Prompt und ersetzt keine menschliche Freigabe. Auto-Merge bleibt default-off und verlangt zusätzlich frische Approval-/Required-Evidence, erneuten Headvergleich, eine deploymentbezogen qualifizierte native Expected-Head-Bedingung sowie einen vor Wirkung persistierten reviewgebundenen Mergeintent. Unbekannte Ausgänge werden ohne zweiten Effekt reconciliert. | `PRCreated`, `ReviewCompleted`, `ReviewBlocked`, `PRCreationFailed`, `EvaluationSubjectInvalidated`, `MergeOutcomeUnknown`, optional `PRMerged`; SCM, Authority-State, Audit und Dashboard. |
| Passive Evaluation | Terminale Gate-Evidence und unveränderlicher Subject | Keine Freigabeautorität. Score/Benchmark/Dashboard dürfen keinen blockierten Candidate freigeben und keinen positiven Gate-Lauf widerrufen. | SQLite-Observation, `ScoreObserved`, Audit, PR-Kommentar und Dashboard als nicht bindende Qualitätsbeobachtung. |
| Healing/Resume | Eindeutig gebundene Fehlevidence bzw. persistierter Finalisierungscheckpoint | Healing höchstens einmal und nur für genau ein heilbares Gate-11-Kriterium; Resume setzt nur Commit/Push/Gates/PR fort. Ein MANUAL-Wartecheckpoint löst kein automatisches Implement-Resume aus; `samuel watch` setzt erst nach exakt gebundenem menschlichem SCM-Receipt die Gate-Reevaluation fort. Drift, unklare Authority oder fehlende Bindung blockieren. | `HealingAttemptStarted`/`HealingAborted`, `ResumeAttempted`/`ResumeCompleted`/`ResumeBlocked`, Quarantäne und Doctor/Workspace-Diagnose. |

Die Workflow-Liste und das Detail reduzieren den sichtbaren Issue-Status aus
dem neuesten korrelierten Lauf. Wegen synchron verschachtelter Dispatches ist
die physische Audit-Schreibreihenfolge keine Kausalitätsquelle: Ein außen
nachgeschriebenes `IssueReady` überstimmt keine bereits vorhandene
`PlanValidated`-, Implementierungs-, Block- oder PR-Evidence. Das angezeigte
`last_event` samt Zeitstempel ist die fachliche Statusbegründung; unvollständige
neue Läufe bleiben `unknown`, statt einen Erfolg aus einem alten Lauf zu erben
(#738). `PlanReplanRejected` beendet nur den abgelehnten Aufruf als `blocked`
und fehlgeschlagene Plan-Stage; `PlanRevoked` bleibt nichtterminal, weil der
explizite Ersatzlauf danach weitergeht (#772).

## Belegreife der realen Referenzstrecke

Automatisierte Tests belegen Codepfade, nicht automatisch eine funktionierende
Kundeninstallation. Die [Capability-/Wirksamkeitsmatrix](../docs/CAPABILITY_MATRIX.md)
nennt je Kontrolle positive/negative Tests, Wirkung und offene Issues. Die
zusätzliche reale Referenzqualification #658 bewertet Installation und Lauf als
Gesamtsystem. Stand des hier geprüften Ausgangscommits:

| Bereich | Automatisierte Evidence | Reale interne Referenz-Evidence | Aussage |
|---|---|---|---|
| Installation, Start, CLI, Doctor, Dashboard | Paket-, CLI-, Doctor-, REST- und Dashboard-Tests vorhanden; die Korrekturen #690 und #756 sind automatisiert belegt. #694 bindet genau einen erwarteten Required-Check-Kontext an Konfiguration, Doctor und Gate-Policy; die reale Zielprüfung steht noch aus | `v2.0.0a15` ist mit grüner Tag-CI #793, vier byteidentisch geprüften Assets, Git 2.47.3 und gesundem digestgebundenem Compose-Smoke veröffentlicht. Der frische D0-Lauf bestand Setup, Demo-Tests, Runtime-/Dashboardidentität, API-Auth, reale Providerprobes, Katalogaktualisierung, Credential-/Modell-/Webhookblocks, Audit und Neustart | **Reale Teilnachweise für die a15-Referenzkombination**; kein vollständiger D0-PASS, keine Beta- oder allgemeine Betriebsfreigabe. Bis zum positiven und negativen Live-Doctor-Nachweis bleibt #694 eine bekannte Betreibergrenze. |
| Planning und menschliche Freigabe | Unit-/Integrationspfade einschließlich Remote-Snapshot, explizitem Replan-Widerruf, Plan-Kommentar-ID, menschlichem Labelereignis, Positiv-, Retry-, Drift-, Runner-Readiness- und Blockfällen vorhanden | Demo-#57 und #58 erhielten je genau einen an denselben Demo-Base gebundenen Plan. Ein absichtlicher zweiter `run` für #57 endete terminal `blocked`; Plan, Kommentar, Vertrag und `status:plan` blieben unverändert. Erst die danach menschlich gesetzten Labels autorisierten den Watch-Pfad | **Qualifiziert für a15**; ein Planersatz verlangt weiterhin expliziten Widerruf und eine neue exakte Freigabe. |
| Implementation bis Candidate | Context-, LLM-Loop-, Patch-, Worktree- und Finalisierungstests vorhanden | Demo-#57 und #58 erzeugten nach echter menschlicher Freigabe je einen commitgebundenen Candidate aus ihrem gebundenen Base. Der Golden-Candidate wurde geprüft und als PR #59 publiziert; der Negativ-Candidate blieb ohne PR | **Positiver und negativer Candidate-Pfad für a15 real belegt**. Provider-/Modellschwäche bleibt eine getrennte Betriebsgrenze. |
| Acceptance, Required Gates und PR | Umfangreiche Gate-/AC-/Subject-/Recovery-Tests sowie negative Referenzbeobachtungen vorhanden | Demo-#57 bestand die gebundenen Acceptance-Kriterien, Required Gates und PR-CI #794; PR #59 wurde anschließend durch `demo-example-bot` statt durch den vorgeschriebenen menschlichen Akteur gemergt. Demo-#58 wurde durch `diff_secret_scan` blockiert; es entstanden für diesen Negativfall kein PR und keine damalige Main-Änderung | **Positive und negative Teilpfade real belegt; vollständiger D0-PASS nicht bestätigt.** Wesentliche Änderungen der gebundenen Kombination verlangen eine neue Evaluation. |
| Evaluation, Audit und Dashboard-Projektion | Observer-, Persistenz-, Replay-, Dashboard- und Security-Tests vorhanden | a15-Setup-, Provider-, Plan-, Approval-, Candidate-, AC-, PR- und Blockadeereignisse sind real persistiert; Audit-Kette und Dashboard blieben über Neustart intakt. `PlanReplanRejected` erschien als Workflow-Warnung, OWASP ASI01 und terminal blockierter Lauf | **Für die beobachteten a15-Teilpfade belegt**; offene Merge-, Diagnosedetail- und Betreibergrenzen bleiben getrennt sichtbar. |
| Externe SCM-Check-Advisory-Evidence | Parser-, Größen-, Subject-/Workflow-/Status-, Freshness-, Widerspruchs-, Dedupe-, Restore- und Authority-Regressionen vorhanden | Gitea-Run 794 für Demo-PR 59 wurde mit exakter Base-/Head-, Attempt-, Workflow-Blob- und Statuskontextbindung real gelesen; Replay blieb identisch, ein falscher Subject-Head wurde advisory abgelehnt | **Für diesen vorhandenen Gitea-Run als Advisory-Pull qualifiziert**; keine #679-, Required-, Runner-/Toolchain- oder Transportintegritäts-Qualification. |
| Self-Mode | Automatisierte Self-/Parity-/Schutzpfade vorhanden | Kein Self-Mode-D0 gegen den S.A.M.U.E.L.-Core | **Nicht real gegen den Core qualifiziert**. Erst nach wirksamem Schutz von laufender Installation, Trust Roots, Updatepfad und Policy darf ein unabhängiges Zielprojekt als Candidate dienen. |

Ein veröffentlichter Tag darf erst als für diese Referenzstrecke qualifiziert
bezeichnet werden, wenn ein frischer Install, ein positiver Golden Path und ein
echter Blockierfall mit genau diesem Paket-/Image-Digest abgeschlossen sind.
a15 erfüllt diese Grenze wegen des Bot-Merges nicht vollständig; grüne Tests,
andere Releases und geänderte Provider-/Policy-/Toolchainkombinationen bleiben
getrennte Aussagen. `v2.0.0a26` ist mit Tag-CI #1166, Prerelease #40, vier
remote hashgeprüften Assets, korrekter OCI-Source und grünem ersten Required
Smoke der jüngste veröffentlichte Kandidat. Golden-D0 und
Capabilityqualifications wurden für a26 nicht ausgeführt. Er ist daher
**PUBLISHED — NOT QUALIFIED**; eine spätere Qualification benötigt einen
eigenen ausdrücklich freigegebenen Auftrag. Die nach #962 übertragenen eigenen
Altlastenabnahmen sind auf Maintainerentscheidung kein Blocker für diesen
Release. Die administrative Schließung von #658/#694 ist kein Abnahme-PASS;
ihre fehlenden Referenz-/Betriebsnachweise bleiben dort einzeln erhalten.
Das vollständige Testkonzept entsteht erst nach separater Erstinstallation.


## Operator: von Meldung zur Ursache

1. Im Dashboard zuerst Issue, Run/Correlation-ID, Eventname, Subject-Head und
   Zeitstempel notieren. Fehlt die Zuordnung, den Fall nicht einem Issue
   zurechnen; offene Projektionslücken stehen insbesondere in #697/#711/#712.
2. `samuel doctor` prüft Konfiguration und externe Voraussetzungen; `samuel
   health` und Dashboard-Self-Check prüfen zusätzlich Runtime-Readiness wie die
   erforderliche Git-Ausführbarkeit. Beide sind weder allein ein vollständiger
   Funktionsnachweis (#693/#727). Ein fehlender Branchschutz/Required Check ist
   eine reale Betriebsblockade, kein Dashboardfehler (#694).
3. Audit zeigt empfangene Events und Security-Signale. Ein absichtlich im Test
   erzeugtes `TamperDetected` bleibt ein echtes Security-Testereignis; es ist
   nicht automatisch ein Produkt-Issue (#692).
4. `GateEvaluationUnavailable` bedeutet: kein belastbarer Subject, daher keine
   Gateentscheidung. `GateEvaluationCompleted(blocked=true)` bedeutet:
   Subject vorhanden, mindestens eine erforderliche Schranke blockiert.
5. Erst die Detail-Evidence des betroffenen Gates/AC-Kriteriums bestimmt die
   sichere nächste Handlung. Score, grüne Self-Check-Kacheln oder wiederholte
   LLM-Versuche dürfen fehlende Authority-Evidence nicht ersetzen.

---

## Pipeline-Dokumente

| Pipeline | Datei | Knoten | Stand |
|---|---|---|---|
| 1. Planning | [pipeline_planning.md](pipeline_planning.md) | P1-P10 | geprüft 2026-08-25 |
| 2. Implementation (Context→LLM) | [pipeline_issue_to_llm.md](pipeline_issue_to_llm.md) | K1-K16 + gebundene Commit-/Push-/Gate-Finalisierung | geprüft 2026-08-29 |
| 3. PR-Gates | [pipeline_pr_gates.md](pipeline_pr_gates.md) | G0-G6, 13 Gates, commitgebundener Subject + PR-Recovery | geprüft 2026-08-29 |
| 4. Passive Evaluation | [pipeline_evaluation.md](pipeline_evaluation.md) | terminale Gate-Evidence, SQLite-Beobachtung/Run-Projektion, Retention/Replay, Darstellung und Evidence-Healing | geprüft 2026-08-30 |

---

## Übergreifende Komponenten (nicht Pipeline-spezifisch)

Diese Module werden von mehreren Pipelines genutzt:

| Komponente | Datei | Zweck |
|---|---|---|
| Event-Bus | `samuel/core/bus.py` | Pub/Sub + Command-Dispatch; Idempotency-, Audit-, Error- und Metrics-Middleware. Security liegt an Input-, Artefakt- und Aktionsgrenzen |
| WorkflowEngine | `samuel/core/workflow.py` | Liest `config/workflows/*.json`, verdrahtet Events→Commands |
| SCM-Adapter | `samuel/adapters/gitea/`, `adapters/github/` | Issue/Comment/PR/Label API |
| LLM-Adapter | `samuel/adapters/llm/` | Provider-Abstraction (DeepSeek/Claude/Ollama/LMStudio) |
| Audit-Trail | `samuel/slices/audit_trail/` | OWASP-Klassifikation + JSONL-Log |
| Architecture | `samuel/slices/architecture/` | Konfig-getriebene Scope-Regeln |
| Labels | `samuel/slices/labels/` | Workflow-Label-Transitions |

---

## Historische Gap-Referenzen

Der ursprüngliche Stand vom 17. April 2026 verwies auf #152
(Skeleton-as-TOC/Slice-Request-Loop) und #153 (gemessene LLM-Qualität). Beide
Issues sind inzwischen geschlossen und werden deshalb nicht mehr als aktuelle
Lücken geführt. Verbindliche aktuelle Prüftiefe und offene Folgeissues stehen
in der [Capability-/Wirksamkeitsmatrix](../docs/CAPABILITY_MATRIX.md); die
einzelnen Pipeline-Dokumente beschreiben nur ihren jeweiligen Ablauf.

Wiederholbare Inventare, AC-Tags, Gate-Profile, Schwellen und ausgelieferte
Workflowübergänge stehen in der aus Code und Config erzeugten
[Runtime-Referenz](../docs/RUNTIME_REFERENCE.md). Manuelle Pipelineaussagen
bleiben über den Dokumentvertrag abschnittsbezogen prüfpflichtig.

---

## Lese-Tipps nach Persona

**Neueinsteiger:** Lies in dieser Reihenfolge:
1. Diese README (Übersicht)
2. `pipeline_planning.md` (einfachste Pipeline, 2 LLM-Calls max)
3. `pipeline_issue_to_llm.md` (die komplexeste, Herzstück)
4. `pipeline_pr_gates.md` (Regeln + Gates)
5. `pipeline_evaluation.md` (nicht bindende Qualitätsbeobachtung und Evidence-Healing)

**Debugger eines schlechten LLM-Outputs:**
Starte in `pipeline_issue_to_llm.md` bei K13 (Validator) und arbeite rückwärts.

**Erweiterung um neue Sprache:**
Siehe `pipeline_issue_to_llm.md` Abschnitt "K7 Skeleton-Builders" + Registry.

**Neues Gate für PR:**
Siehe `pipeline_pr_gates.md` → Gate in `samuel/slices/pr_gates/gates.py` anlegen + in `GATE_REGISTRY` eintragen.

**Neue Architektur-Regel:**
`config/architecture.json` bearbeiten — keine Code-Änderung nötig. Siehe K5 in `pipeline_issue_to_llm.md`.

---

## Konfigurations-Dateien

Zentrale Config-Dateien die Pipeline-Verhalten steuern:

| Datei | Schema | Zweck |
|---|---|---|
| `config/agent.json` | - | Mode, exclude_dirs, Context-Limits |
| `config/architecture.json` | - | Rollen + Scopes (Pipeline 2, K5) |
| `config/features.json` | - | Feature-Flags |
| `config/labels.json` | - | Workflow-Labels (Seeded via `samuel setup-labels`) |
| `config/gates.json` | `GatesConfigSchema` | Required/Optional/Disabled Gates (Pipeline 4) |
| `config/eval.json` | `EvalSchema` | passive Scoring-Policy sowie bootstrapgebundene TEST-Runner-Policy |
| `config/llm.json` + `config/llm/*.json` | - | Provider + Routing |
| `config/workflows/*.json` | - | Workflow-Definitionen (Events↔Commands) |
| `config/hooks.json` | strikt validiert | Extension→`IQualityCheck`-Registry des lokalen Self-Preflights |
| `config/audit.json` | - | JSONL-Sink-Config |
| `config/notifications.json` | - | Notification-Sinks |
| `config/privacy.json` | - | DSGVO-Regionen, Retention |
| `config/repo_patterns.json` | - | Sequence-Validator Patterns |

---

## Pflege-Regel

Bei Pipeline-Änderungen: **Zuerst Code, dann Doc — im gleichen PR**.
Ein Pipeline-Doc ist nur dann wertvoll, wenn es aktuell ist.

Wenn die Pipeline erweitert wird (z.B. neuer Knoten K17 / P11), diese README
um die Übersicht aktualisieren und den jeweiligen Pipeline-Datei-Eintrag
ergänzen.

---

*Erstellt: 2026-04-17. Zuletzt gegen Code und aktive Dokumentation geprüft:
2026-09-01 auf Ausgangscommit
`53b859467bb28dced6e7208c020b70da4d708e75`.*
