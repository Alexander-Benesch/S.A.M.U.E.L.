# Current Product Status

Stand: 2026-09-29, Europe/Berlin. Die technische Product-Codepruefung ist an
`41340e75e0acc918fbc577653c3bedfec0f70aaa` gebunden; anschliessende
Housekeeping-Commits aendern nur Dokumentation. Den aktuellen `main`-SHA
liefert der Live-Readback, nicht diese zeitgebundene Statusseite. Sie ersetzt
keine Release-, Golden- oder D0-Evidence.

## Identitaet und Baseline

| Feld | Aktueller Befund | Authority |
|---|---|---|
| Gitea `main` | PR #923 ist als Docs-only-Merge integriert; exakten heutigen Head live lesen | `CURRENT_CODE_FACT` |
| lokaler Product-`main` | nach dem PR-#923-Merge gleich `origin/main`; nach weiteren Docs-Merges erneut abgleichen | `CURRENT_TEST_EVIDENCE` |
| letzter publizierter Product-Release | `v2.0.0a25`; keine a26-Releasebehauptung | `CURRENT_CODE_FACT` |
| letzter Tag / Releasebasis | `v2.0.0a25`; die spaeteren Product- und Docs-Commits sind kein Release | `CURRENT_CODE_FACT` |
| Docs-PR-CI | #1041 fuer PR #923: beide Python-Kompatibilitaetsjobs und Required-`lint-and-test` erfolgreich; Release-Job ereignisbedingt skipped | `CURRENT_TEST_EVIDENCE` |
| lokaler Baseline-Test | 3.176 Tests bestanden; Mypy, Control-/Document-Matrix, Wiki-, Container- und Dependency-Vertrag bestanden; Docs-Merge erzeugt keine neue Product-Qualification | `CURRENT_TEST_EVIDENCE` |
| Demo-/Reference-Stand | letzte Development-E2E-Evidence auf disposable Issue #3; kein PR und kein Merge | `HISTORICAL_EVIDENCE` |

## Nachgewiesen funktionierend

Der aktuelle Code besitzt getestete, gebundene Vertraege fuer Planning und
Replan, dauerhafte Human-Approval-Authority, Implementation und Candidate,
Required Gates, MANUAL-Receipt-Pruefung, oeffentliche Watch-Fortsetzung,
Review- und Provider-Fehlergrenzen, Workspaces, Resume, State, Audit,
Dashboard/API, Setup/Doctor, Release- und Wiki-Projektion. Die lokale Suite
belegt diese technischen Vertraege; sie beweist keine externe
Providerverfuegbarkeit und keinen erfolgreichen Golden-Lauf.

Seit dem letzten Statusbericht wurden insbesondere integriert:

- MANUAL pending bleibt nichtterminal und wird ueber den oeffentlichen
  Watch-Pfad erneut ausgewertet (#910/PR #911);
- native signierte Gitea-Freigaben werden gebunden verarbeitet (#904);
- Health-Probes duerfen aktive Workflows nicht fortsetzen (#906);
- konkurrierendes Resume vergiftet den aktiven Issue-Status nicht (#913);
- erschöpfte Providerfehler werden in Review sowie Implementation/Healing
  fachlich blockiert (#912 und #918);
- unmoegliches repositoryweites `GREP:NOT` wird vor Freigabe blockiert (#916).

## Teilweise oder noch nicht end-to-end belegt

Die 46 offenen Product-Issues nach dieser Reconciliation stehen in
`ISSUE_IMPLEMENTATION_MATRIX.md`. Viele liefern bereits Code und Regressionen,
benoetigen aber reale, releasegebundene oder rollengetrennte Qualification.
Besonders betroffen sind Identity/Cutover, Review, State/Retention,
Provider/Execution, Setup/Config, Health/Doctor, Documentation Publisher und
Extensions.

## Aktuelle Blocker

| Stage | Befund | Träger |
|---|---|---|
| Development E2E | Es gibt noch keinen unveraenderten zusammenhaengenden positiven Lauf bis Human Merge | #859 |
| Operational Readiness | Kein vollstaendiger backendneutraler Full Self-Check; statische Konfiguration beweist keine Verfuegbarkeit | #921, #693, #694 |
| Recovery | Kein einheitlicher sicherer Re-Entry-Vertrag ueber terminale Workflowgrenzen | #920 |
| Providerroute | reale Route-/Modellverfuegbarkeit und Output-Suitability bleiben externe Inputs | #822, #679 |
| Formal Golden/D0 | frischer releasegebundener Positiv- und Negativsubject fehlt | #658 |
| Rehearsal cleanup | fuenf disposable Repositories sind mit der Demo-Rolle sichtbar und privat gesichert; alle bleiben `KEEP_EVIDENCE` | `REHEARSAL_REPOSITORY_CLEANUP.md` |

## Letzter Positive-E2E-Stand

Disposable Issue #3 erreichte Planning PASS, echte Human Approval,
Implementation, Candidate und automatische Gates. Ein exakt an AC, Contract
und Candidate-Head gebundener signierter MANUAL-Receipt wurde angenommen,
aber der damalige Stand dispatchte keine Reevaluation. Der Defekt wurde danach
durch #910/PR #911 technisch mit Integrationsregression behoben. Der alte Lauf
bleibt FAIL-Evidence und wurde nicht fortgesetzt. Es gibt weiterhin keinen PR,
keinen Merge und keinen Development-Golden-PASS aus dieser Kette.

## Qualification, Wiki und Public Sync

- `Development E2E`: technische Fixes und Teilstrecken belegt; kompletter
  neuer Lauf fehlt.
- `Development Golden`: offen in #859.
- `Formal D0`: offen in #658 und erst nach immutable Release auf frischer
  Installation zulaessig.
- `Wiki`: nach PR #923 wurden zehn Inhaltsseiten plus Footer und Sidebar
  publiziert und ueber den Git-Wiki-Marker auf den Docs-Merge zurueckgelesen.
  Jeder weitere Docs-Merge erfordert einen neuen Build, Publish und
  Live-Readback des Marker-`source_head_sha`; ein lokaler `check` allein
  belegt keine aktuelle Live-Publikation.
- `GitHub`: Der historische Public-Snapshot liegt nach anonymem API-Readback
  unter `Alexander-Benesch/S.A.M.U.E.L.`; `main` zeigte am 29.09.2026 auf
  `f1fa875c1e05138ecda9cb2e618e4f56e8ecf32a`. Ein GitHub-Remote ist im
  Product-Checkout nicht konfiguriert. Der naechste bereinigte Ein-Commit-
  Snapshot, das getrennte Wiki und Issue #2 werden ausserhalb des Product-
  Checkouts als tokengebundenes Paket vorbereitet. Der genaue Source-/Tree-
  Stand steht im privaten Sync-Receipt; fuer die Veroeffentlichung fehlt eine
  passende GitHub-Tokenauthority. Siehe
  `docs/github/GITHUB_SYNC_READINESS.md`.
