# Housekeeping and Repository Reconciliation Report

Stand: 2026-09-26, Europe/Berlin. Produktbasis: `401ffae93c1c768aca51377c7a5eab7a81033f90`. Dieser Bericht ist ein Housekeeping-Snapshot. Er erteilt keine Golden-, D0-, Release-, Provider-, Routing-, Prompt-, Credential- oder Runtime-Authority.

## 1. Repositoryzustand

### Produkt

| Gegenstand | Befund |
|---|---|
| Remote `main` | `401ffae93c1c768aca51377c7a5eab7a81033f90`; Merge von PR #896 für #895 |
| Main-CI | Actions-Run #999: `completed/success`, exakter Head |
| Lokales `main` | Zu Beginn `14d892e…`, 0 voraus/9 zurück; sicher per Fast-forward auf `401ffae…` abgeglichen; 21 untracked historische Dokumente unverändert |
| Offene PRs | Zu Beginn genau 1: #857 |
| Offene Issues | Zu Beginn 41; nach Housekeeping #876 geschlossen, #897 und #898 angelegt, damit 42 offen |
| Branches | Remote 140 einschließlich `main`: 137 erhaltene Heads gemergter PRs, #857-Head und der geschlossene/nicht gemergte #825-Head |
| Releases/Tags | 16 Releases, 29 Tags; jüngster Release `v2.0.0a25`; kein `v2.0.0a26`-Tag und kein a26-Release |
| Branch Protection | `main` geschützt, direkter Push aus, Required Context `CI / lint-and-test (pull_request)`; `required_approvals=0`, daher liegt die Human-Merge-Grenze im Projektvertrag |
| Wiki | 12 Seiten. Letzte Inhaltsprojektion bindet Produkt `3c3d30f…`, `_Sidebar` ist älter; gegenüber `401ffae…` stale |

Tags ohne Releaseobjekt (`a23`, `a22`, `a20`, `a18`, `a16`, `a12`, `a5`, `a1` und `phase-9-complete` bis `phase-13-complete`) bleiben historische Lineage-Evidence. Es gibt keine Lösch- oder Nachpublikationsempfehlung aus diesem Auftrag.

### Demo

| Gegenstand | Befund |
|---|---|
| Remote `main` | `d4b42b7aa2b1ac2d631c3571e2c3b8adffdc8662`; Merge von PR #138, D0-v1-Seed reset |
| Main-CI | Actions-Run #993: `completed/success`, exakter Head |
| Sichtbarkeit | Produkt-`SCM_TOKEN` (`example-bot`) erhält erwartungsgemäß 404 auf das private Demo-Repo; getrennte Maintenance-/Demo-/Operatorrollen lesen es erfolgreich. Das ist rollenabhängige Least-Privilege-Sichtbarkeit, kein gelöschtes Repo. |
| Offene PRs | 6: #101, #107, #109, #111, #120, #126 |
| Branches | 30 einschließlich `main`; 6 offene PR-Heads, 3 erhaltene gemergte Heads, 20 Qualification-/Rehearsal-Branches ohne PR |
| Releases/Tags/Wiki | keine Releases, keine Tags, keine Wiki-Seiten |
| Seed | `scenario.json` bindet exakt drei Seeddateien; aktueller Code ist blob-identisch zum Seed und enthält wieder den beabsichtigten aufsteigenden Leaderboard-Defekt |

Die alte lokale Kopie `/opt/samuel-pipeline-escape` endet bei `c3fe84b…` und ihr gecachtes `origin/main` bei `3d3a458…`. Vier erhaltene Attempt-35/36-Clones sind dagegen sauber und exakt auf `d4b42b7…` gebunden. Keine Demo-Kopie wurde verändert.

## 2. Offene PRs

| PR | Head → Base | Mergeability / CI / Review | Zweck und heutiger Nutzen | Klassifikation / Aktion |
|---|---|---|---|---|
| Produkt #857 | `06f72ee…` → `401ffae…` | `mergeable=false`; Run #935 grün, Release-Gate skipped; 0 Reviews; 37 Commits hinter `main` | a26-Kandidaten-Changelog nach #855. Nicht anderweitig gemergt, aber ohne #877/#881/#884/#886/#892/#895 und Attempt-36-Stand. | `RELEASE_BOUND`, `NEEDS_UPDATE`, `NEEDS_REVIEW`; nicht mergen. Später auf aktuellem `main` neu aufbauen, nur mit Releaseauftrag und Human Merge. |
| Demo #101 | `0c5e7a…` | Run #950 grün; 0 Reviews; 20 hinter `main` | alter Leaderboard-Candidate; späterer Code wurde mehrfach gemergt und Seed danach zurückgesetzt | `SUPERSEDED`, `STALE_CLOSE_CANDIDATE`; nach Maintainer-Readback schließen, nicht mergen |
| Demo #107 | `33beb25…` | Run #957 grün; 0 Reviews; 20 hinter | wie #101 | `SUPERSEDED`, `STALE_CLOSE_CANDIDATE` |
| Demo #109 | `006cef9…` | Run #958 grün; 0 Reviews; 20 hinter | wie #101 | `SUPERSEDED`, `STALE_CLOSE_CANDIDATE` |
| Demo #111 | `ebdaa44…` | Run #962 grün; 0 Reviews; 20 hinter | Attempt-18-Candidate; terminale Failed-Evidence bleibt erhalten | `SUPERSEDED`, `STALE_CLOSE_CANDIDATE` |
| Demo #120 | `320862b…` | Run #973 grün; 0 Reviews; 16 hinter | alter Candidate vor späteren Merges/Seedreset | `SUPERSEDED`, `STALE_CLOSE_CANDIDATE` |
| Demo #126 | `4ae8ebe…` | Run #978 grün; 0 Reviews; 12 hinter | alter Candidate vor PRs #129/#133/#137 und Seedreset #138 | `SUPERSEDED`, `STALE_CLOSE_CANDIDATE` |

Ein Merge der sechs Demo-PRs würde den absichtlich wiederhergestellten Qualification-Seed verändern. Sie wurden daher weder gemergt noch geschlossen.

## 3. Issue-Reconciliation

Klassifikation der 41 zu Beginn offenen Produktissues:

| Klasse | Anzahl |
|---|---:|
| A `IMPLEMENTED_AND_VERIFIED` | 1 |
| B `IMPLEMENTED_NOT_REAL_QUALIFIED` | 19 |
| C `PARTIALLY_IMPLEMENTED` | 9 |
| D `STILL_OPEN_AND_VALID` | 5 |
| E `SUPERSEDED` | 0 |
| F `DUPLICATE` | 0 |
| G `DOC_ONLY_REMAINDER` | 1 |
| H `POST_GOLDEN_WORK` | 1 |
| I `RELEASE_DEPENDENT` | 3 |
| J `FORMAL_D0_DEPENDENT` | 1 |
| K `INSUFFICIENT_EVIDENCE` | 1 |

| Issue | Klasse | Erfüllter Stand | Reale Restmenge / Aktion |
|---|---|---|---|
| #894 | K | non-root-/RO-Mount-Befund vorhanden | Body bricht bei `dubious ownership` ab, keine AC/Kommentare; vervollständigen, nicht schließen |
| #892 | B | PR #893, deterministische Contextreihenfolge und Regressionen, CI grün | neue Candidate-/Prestart-Qualification ausdrücklich offen |
| #891 | C | configured/effective Route und Promptquelle sichtbar | taskweise effective/current/last-call-Trennung fehlt |
| #890 | C | correlation/run/issue-Projektionen vorhanden | Root-Cause-Kette, nächste Aktion und Securityklassifikation vervollständigen |
| #889 | B | Setup/Freeze, Digests, Restart-Hinweis und Docs vorhanden | kompletter Operator-Lifecycle real abnehmen |
| #888 | H | klar als nach Golden/a26/Formal-D0 eingeordnet | Findingsmatrix erst post-Golden |
| #883 | D | Redaction vorhanden | produktweite Original-vs-redacted-Identität und Replay-Evidence fehlen |
| #880 | C | starke AC-/Contract-/Head-/Human-Bindung; #895 ergänzt dauerhafte Planapproval | MANUAL-UX, sichere einfache Aktion und Transportkonsistenz fehlen |
| #878 | C | Resolver, Overrides, Quellenprojektion und Tests vorhanden | Profile-Contract und vollständige positive/negative Profil-Smokes fehlen |
| #876 | A | alle 6 AC durch #877/PR #879, CI und realen Prompt-Audit-Readback belegt | Abschlusskommentar #44494 geschrieben und geschlossen |
| #873 | D | AI-/OWASP-/DSGVO-Basis vorhanden | CRA/2024-2847-Definition und AC fehlen |
| #859 | D | Campaign gültig und pausiert | Remote-Timeline auf Attempt 36 reconciliiert; Golden/Release bleiben offen |
| #847 | B | PlanBlocked Exit 1, Erfolg Exit 0, Tests/CI | installierte Positiv-/Negativabnahme und Statusdocs |
| #846 | B | Nichtplan erzeugt keine Authority, Tests/CI | reale SCM-/Release-Qualification |
| #845 | B | Transport-/Falschremote-Schutz und Tests | frischer kanonischer Remote/Base und neue Subjectgrenze |
| #844 | C | F04-P durch PR #850 umgesetzt | F04-O, D0-Writerbindung und reale Chainprobe |
| #843 | C | Setup-/Auth-Validierung teilweise vorhanden | Bootstrapquellen und stored/effective-Prüfung vor erster Wirkung |
| #840 | C | Phase-1-Reconciliation und a25/PR #858 | Coordination/Lineage bleibt, Child-/Qualificationträger offen |
| #830 | B | Dashboard/API/Auth/Health-Projektionen getestet | echter Run, UI/API/Restart/Q16 und Zugangsbindung |
| #829 | B | Produktdocs und Demo-PR integriert | effektive Routen/Freeze real |
| #828 | B | redigierte Apply-Ursache und CI | externer Providerlauf plus gebundener Input/Snapshot/Apply |
| #823 | I | Bindmount-Fix und Busy-/Rollbacktests | releasegebundene Setup→Recreate→Freeze-Abnahme |
| #822 | B | Routing/Self-check vorhanden; falsche Defaultänderung vollständig revertiert | aktuelle Routeprobe und Freeze, keine Defaultänderung |
| #821 | C | lokaler Index/Rechte und Teilproben | lokale Restentries/-proben; `INFRASTRUCTURE_ONLY` |
| #812 | G | a18-Changelog PR #813 und CI | historisches Pre-Tag-Receipt/Status zuordnen; keine Neuveröffentlichung |
| #811 | D | 0/4 AC | `HUMAN_DECISION_REQUIRED`: Python-Minimum, Matrix und wirksamer Release |
| #694 | B | Required-Check Code/Tests | reale positive/falsche-Context-Probe und Credential-/Docs-Abnahme |
| #693 | B | Health/Readiness/API und Tests | reale aktive/passive/restart/integrity Matrix |
| #691 | B | D08 und PR #793/#810/#815/#824 | reale Persistenz→Recreate→Freeze-Kette |
| #679 | B | Provider-/Resume-/Negativfixtures | reale Provisionierung, Trust, Cutover und Recovery |
| #668 | B | Cutoff/Grant/Receipt/Restore/Canarymechanik; default aus | echte Kategorie-/Abbruch-/Recovery-Rolloutbelege |
| #658 | J | technischer D0-Pfad vorhanden | vollständiger frischer zusammenhängender Formal-D0-Subject |
| #639 | I | Extension-Contract und Fixtures | releasegebundener externer Consumer |
| #636 | I | Documentation Inventory/Publisher und Tests | Produktrelease-/Paketdigestbindung |
| #575 | B | Clarification/Restart/Revision/Deadline Tests | reale Fragen, Actor, Timeout, Supersession, Resume |
| #567 | D | Netzfinding, 0/6 AC | `HUMAN_DECISION_REQUIRED`: L2-/Infrastrukturursache und Maßnahme |
| #549 | B | Budgetmechanik und Tests | reale Adapter-/Grenz-/Restart-/Release-Matrix |
| #521 | B | passive Submission und No-mutation/Gate-Tests | realer unabhängiger Repo-Positivfall und #679-Pfad |
| #482 | C | State/Restore/Reconcile/Resume und Retention 1–5b | Dach hängt an #668 und echten State-/Recovery-AC |
| #468 | B | Review/Intent/Expected-head/Fail-closed Tests | reale Head-Race/Unknown/Restart/optionale Aktivierung |
| #422 | B | AuthN/AuthZ/Sessions/Cutover Tests | reale TLS-/Rollen-/Session-/Cutover-/Restore-/Recovery-Matrix |

Neu aus diesem Auftrag:

| Issue | Klasse | Zweck |
|---|---|---|
| #897 | H | Post-Golden-Diagnosevertrag für `EXPECTED_LEAST_PRIVILEGE`, `OPERATOR_ACTION_REQUIRED`, `UNEXPECTED_PRIVILEGE_ESCALATION_REQUEST` |
| #898 | C / `NEEDS_REVIEW` | diese Reports und eindeutig sichere Schema-/Operator-Dokumentkorrekturen |

## 4. Audit-/Remediation-Abgleich

- #840 bleibt Coordination-/Provenienzträger; seine Childissues dürfen nicht pauschal durch Codeexistenz geschlossen werden.
- #859 bleibt der pausierte Golden-Träger. Kommentar #44498 ergänzt Attempt 36: Q00/Q01 PASS, Q02 `EACCES`, Suite und Provider nicht gestartet, kein Candidate-/Releaseeffekt, Attempt 37 nicht erzeugt.
- #877 ist mit PR #879 vollständig integriert. #876 war der verbliebene, durch dieselbe Evidence erfüllte Träger und wurde geschlossen.
- #880 bleibt trotz #895 offen: dauerhafte Planapproval ist umgesetzt, die MANUAL-UX nicht.
- #892 ist technisch integriert, aber noch nicht real candidate-/prestart-qualifiziert.
- #895 ist via PR #896 und `401ffae…` geschlossen; Restart/Replan/Stale-Gegenfälle sind getestet.
- Geschlossene Fixkette auf `main`: #860, #862, #863, #865, #867, #869, #871, #874, #877, #881, #884, #886, #895.
- Fresh-Install/Operability bleiben insbesondere in #691/#823/#843/#845/#889; Observability in #693/#830/#890/#891; Promptprofil in #878; MANUAL in #880; Evidence/Tooling in #828/#694; Runtime-/Workspace-Grenzen in #482/#668/#679/#845/#894.

## 5. Dokumentations-Coverage

Mechanischer Ausgangsstand auf `401ffae…`: 75 Controls gültig, 42 aktive Dokumente, 17 gebundene Abschnitte, Wiki-Build mit 10 Inhaltsseiten, 131 gezielte Tests grün und keine echten toten lokalen Markdownlinks.

| ID | Finding | Bewertung / Aktion |
|---|---|---|
| DOC-01 | Dashboard/Doctor pauschalisieren 401/403 zu Repository-Admin | bestätigt; #897 erstellt, post-Golden |
| DOC-02 | aktive State-Doku sagt Schema v6/18, Runtime ist v10/26 | sichere Korrektur in #898 vorbereitet; historische ADR-v6-Aussagen bleiben |
| DOC-03 | README suggeriert Browserwrites in plain production dashboard | Quickstart/Prompt-Editor auf expliziten Setup-Prozess korrigiert |
| DOC-04 | README nennt falsche Tasknamen | auf `planning`, `implementation`, `review`, `evaluation`, `healing` korrigiert |
| DOC-05 | REST-Tabelle behauptet Vollständigkeit, listet nur Auswahl | Rest in #898/report dokumentiert; später Tabelle als Auswahl markieren oder generieren |
| DOC-06 | zentrale Config-Tabelle lässt `auth`, `compliance`, `path_risk`, `gates.audit`, `gates.self` aus | kleine gebündelte Doc-Restmenge, noch nicht geändert |
| DOC-07 | CLI-Doku hat 21 Commands, Help-Test lässt fünf neue Commands aus | kleine Test-Fixture-Restmenge, noch nicht geändert |
| DOC-08 | aktiver Product-Boundary-Handover-Prompt hat a15-Prioritäten | historische Inhalte upstreamen; wegen Prompt-Verbot heute nicht geändert |
| DOC-09 | Prompt-Contract-Audit ist wertvolle Momentaufnahme, aber aktive Runtime Reference | einzigartige Normanteile upstreamen, dann historisch bewahren |
| DOC-10 | Remote-Wiki und lokales ignoriertes Wiki-Build sind stale | nach Human-Merge aus aktuellem Source neu generieren/publizieren; heute kein Publish |

## 6. Feature → Docs → Tests

| Feature | User-/Operator-Doku | Authority/Contract | Repräsentative Tests | Status |
|---|---|---|---|---|
| Setup / Production Freeze | INSTALL, README, Technical §17 | Operating Rules Configuration Freeze | `test_configuration_mode`, Setup/Dashboard | implementiert; README-Korrektur vorbereitet, reale Abnahme offen |
| Configuration Mode | INSTALL §4.3, CLI-Referenz | Freeze-Control | Dashboard/API/Server-Tests | enforced |
| Provider-/Task-Routing | README, Technical §8/§19 | Routingpräzedenz | task routing/factory/provider verification | implementiert; reale Routequalification offen |
| Prompt Resolver/Profile | README, Prompt Audit | Resolver-/Freeze-Contract | prompt/factory/dashboard | Resolver implementiert; Profilqualification offen |
| Workflow Budget | README, Technical State | Budget-Authority | budget/integration | enforced; reale Providergrenzen offen |
| Planning / Replan | Operating R11/R25, Technical Planning | Plan-/Replan-Authority | planning/replan/determinism | implementiert |
| Clarification | Operating/Technical Planning | Actor-/Revision-/Timeout-Bindung | clarification tests | implementiert; real offen |
| Approval | Operating R25, Capability Matrix | create-only Approval Authority | plan approval/integration | implementiert; Golden offen |
| Acceptance Contract | Technical/Design E3 | AC-Verifier | acceptance contract/gate | implementiert |
| MANUAL Acceptance | Operating/Technical PR Gates | MANUAL-Receipt | verifier/PR-gates | technisch teilweise; UX #880 offen |
| Workspace Manager | Technical §6, ADR-0618 | Worktree-Registry/Quarantine | workspace manager/transactions | implementiert; ausdrücklich keine Sandbox |
| Review | Technical §9, Prompt Audit | Expected-head/Intent | review/contract | gebunden; real offen |
| Healing | Technical §9 | mutation authority/attempt | healing bound/loop | gebunden; real offen |
| Required Gates | Runtime Reference, Operating | Gate Registry | gate/integration | implementiert |
| PR / CI | CONTRIBUTING, CI Operations | Human Merge + Required Context | PR creation/Gitea/CI | implementiert; externe Installation prüfpflichtig |
| Audit | Technical §14, SECURITY | HMAC-/Redactioncontract | audit JSONL/async | implementiert |
| State / Resume | Technical §15, ADR-0482 | SQLite Authority | state/resume/migration | implementiert; Schema-Docfix vorbereitet |
| Replay | CLI/Technical | side-effect-free Replay | replay/score replay | implementiert |
| Retention | Runtime Reference, Privacy | category authority | retention | Fundament ausgeliefert deaktiviert |
| Dashboard | README, Technical §§17–18 | read/write mode + Auth | dashboard/server | implementiert; Privilegdiagnose #897 |
| Identity/Auth | INSTALL, ADR-0422 | local identity/cutover | identity/server auth | experimentell; reale Matrix offen |
| Extensions/Plugins | Manifest, Extension Contract | öffentlicher Contract | extension contract | optional, standardmäßig aus |
| Compliance mappings | AI Act/DSGVO/Gate Matrix | Mapping, kein Zertifizierungsclaim | compliance/SARIF | implementiert |
| Evidence | Technical/CLI | Advisory Observation | external evidence/CLI | implementiert; reale Fälle offen |
| Release | VERSIONING, Container Operations | create-only/Human | release gate/container release | implementiert; keine heutige Releasewirkung |
| Doctor / Self Check | INSTALL, Health ADR | readiness/branch rule | self check/health | implementiert; Rollen-/Scope-Text #897 |

## 7. Lokale Artefakte

### Untracked Auditdokumente im Produktroot

| Datei | Klassifikation | Empfehlung |
|---|---|---|
| `BACKLOG_AUDIT_INDEX.md` | `SUPERSEDED_BUT_PRESERVE` | Index durch Materialisierung überholt; historisch behalten |
| `BACKLOG_CHALLENGE_BUNDLE.md` | `KEEP_HISTORICAL` | einzigartige Challenge-/Entscheidungsprovenienz |
| `BACKLOG_STORY_MATERIALIZATION.md` | `KEEP_HISTORICAL` | Remote-Issue-Materialisierung und Readback |
| `D0_BOOTSTRAP_CONTRACT_AUDIT.md` | `KEEP_HISTORICAL` | einzigartiger Bootstrapaudit |
| `EXECUTION_CONFORMANCE_AUDIT.md` | `KEEP_HISTORICAL` | Conformance-/Lineagebefunde |
| `EXTERNAL_CHALLENGE_RECONCILIATION.md` | `KEEP_HISTORICAL` | Gegenreview-Provenienz |
| `ISSUE_COMMENT_RECONCILIATION.md` | `KEEP_HISTORICAL` | Timeline-/Kommentarreadback |
| `OPERATIONAL_CONTRACTS.md` | `CONTENT_MUST_BE_UPSTREAMED` | Übergangs-Super-Runbook; Restnormen in bestehende Contracts, dann `ARCHIVE_AFTER_RELEASE` |
| `P1_CHALLENGE_PACKAGE.md` | `KEEP_HISTORICAL` | eingefrorenes Auditpaket |
| `P2_AUDIT_PACKAGE.md` | `SUPERSEDED_BUT_PRESERVE` | explizit durch P2 Challenge ersetzt |
| `P2_CHALLENGE_PACKAGE.md` | `KEEP_HISTORICAL` | finaler P2-Reviewstand |
| `P3_CHALLENGE_PACKAGE.md` | `KEEP_HISTORICAL` | finaler P3-Reviewstand |
| `P4_CHALLENGE_PACKAGE.md` | `KEEP_HISTORICAL` | finaler P4-Reviewstand |
| `P4_CHALLENGE_RECONCILIATION.md` | `KEEP_HISTORICAL` | P4-Gegenreview |
| `P5_CHALLENGE_PACKAGE.md` | `KEEP_HISTORICAL` | finaler P5-Reviewstand |
| `P6_CHALLENGE_PACKAGE.md` | `KEEP_HISTORICAL` | finaler P6-Reviewstand |
| `P7_CHALLENGE_PACKAGE.md` | `KEEP_HISTORICAL` | finaler P7-Reviewstand |
| `P8_CHALLENGE_PACKAGE.md` | `KEEP_HISTORICAL` | finaler P8-Reviewstand |
| `POST_AUDIT_CONSOLIDATION.md` | `CONTENT_MUST_BE_UPSTREAMED` | einzigartige aktuelle Restmatrix; später historisch |
| `RELEASE_LINEAGE_DRIFT_AUDIT.md` | `KEEP_HISTORICAL` | einzigartige a15–a24-Lineage |
| `REMEDIATION_MATRIX.md` | `CONTENT_MUST_BE_UPSTREAMED` | offene R-Einheiten in kanonische Issues/Contracts, dann archivieren |

Die 21 Dateien umfassen 1,280,235 Bytes. Keine ist derzeit `SAFE_DELETE_AFTER_REVIEW`; drei exakte Duplikate existieren zusätzlich in `/tmp/postaudit840-structural`, während neuere Konsolidierungsfassungen im Root einzigartig bleiben.

### Ignorierte und externe lokale Gruppen

| Gruppe | Umfang | Klassifikation / Aktion |
|---|---:|---|
| `.env`, lokale Settings | 2 Dateien | aktive lokale Konfiguration; `HISTORICAL_EVIDENCE_KEEP_LOCAL`, niemals committen |
| `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `__pycache__`, `samuel.egg-info` | regenerierbar | `TEMPORARY_SAFE_TO_DELETE`, heute nicht gelöscht |
| `.venv` | 245.6 MB / 11,379 Dateien | regenerierbare Entwicklungsumgebung; nicht Evidence |
| `build/` | 3.9 MB / 373 | Code/Wiki generiert; Receipts `HISTORICAL_EVIDENCE_KEEP_LOCAL`, übriges regenerierbar |
| `data/` | 1.76 MB / 24 | SQLite, Auditlogs und Metrics `HISTORICAL_EVIDENCE_KEEP_LOCAL`; Modellcache separat regenerierbar |
| `dist/` | 8.0 MB / 4 | alte a8/a9 Buildartefakte: `SHOULD_BE_ARCHIVED`, nicht als heutiger Release verwenden |
| `wiki/` | 0.25 MB / 11 | stale, regenerierbares nicht-authoritatives Buildoutput |
| `/var/lib/samuel-example/.local/share/samuel-rehearsal` | 59 Gruppen / 2.46 GB | Golden-/Qualification-Evidence `HISTORICAL_EVIDENCE_KEEP_LOCAL`; keine Bulk-Löschung |
| `/tmp/samuel-*` | 273 Gruppen / 1.84 GB | gemischte Logs, Builds, Worktrees, Readbacks; `UNKNOWN` als Gesamtgruppe. Leere/duplizierte Buildfiles erst nach Provenienzreview löschbar |
| registrierte Produktworktrees | 69 zu Beginn, davon 68 sauber | viele gemergte/detached historische Worktrees; `SHOULD_BE_ARCHIVED`/später kontrolliert prunen, heute nicht gelöscht |

Attempt 36 ist als zusammenhängende historische Evidence erhalten. Der terminale Receipt hat Digest `sha256:c5b77b74e30ffd98b6c163555c205e5bd00b497b2992044ef885bc223eec9b34` und bestätigt ausdrücklich keinen Provider-, Candidate- oder Releaseeffekt.

## 8. Gitea-/Lokal-Drift

- Produkt-`main` ist jetzt lokal und remote identisch auf `401ffae…`; nur die 21 untracked Evidence-Dokumente bleiben.
- Zu Beginn existierten 225 lokale Branches. Vier Commitgraphen lagen nicht in `origin/main`: der releasegebundene #857-Branch, `fix/814-container-release-recovery`, der inhaltlich netto leere revertierte `fix/822-default-routes`-Branch und `local/docs-audit-pre-sync-20260825`. Die beiden rein lokalen Branches bleiben bis Provenienzreview erhalten.
- 137 Remote-Heads gemergter Produkt-PRs sind stale Aufräumkandidaten, aber keine automatische Löschmenge.
- Die alte Demo-Arbeitskopie ist nicht kanonisch. SHA-identische saubere erhaltene Clones belegen `d4b42b7…`.
- Remote-Wiki und lokales Wiki-Build sind beide hinter Produkt-main; sie sind untereinander nicht als aktuelle Projektion gleichwertig.
- Releases und Tags sind konsistent existent; acht historische Versionstags haben absichtlich/ungeklärt kein Releaseobjekt. Keine Reparatur ohne Releaseauthority.

## 9. Sichere bereits erledigte Korrekturen

1. Lokales Produkt-`main` fast-forward auf Remote ohne Veränderung der 21 Evidence-Dateien.
2. #876 nach vollständigem AC-/Code-/CI-/Real-Evidence-Abgleich mit Kommentar #44494 geschlossen.
3. #859 mit Attempt-36-Status und terminalem Receipt-Digest kommentiert (#44498); keine Goldenwirkung.
4. #897 als gebündeltes Post-Golden-Operability-/Securitydiagnose-Issue angelegt.
5. #898 als einziger Träger für Reports und sichere Dokumentkorrekturen angelegt.
6. Auf Branch `docs/898-housekeeping-reconciliation`: aktive State-Schema-Texte v6/18 → v10/26, README-Tasknamen und expliziter Setup-Modus korrigiert. Historische ADR-/Auditclaims bleiben unverändert.
7. Keine Datei, Branch, Evidence, Tag, Release, Route, Credential oder Runtime wurde gelöscht oder umgebunden.

## 10. Offene PRs nach Housekeeping

- #857 bleibt `RELEASE_BOUND + NEEDS_UPDATE + NEEDS_REVIEW` und darf in diesem Auftrag nicht gemergt werden.
- PR #899 für Issue #898 bleibt nach grüner CI an der Human-Merge-Grenze.
- Die sechs Demo-PRs bleiben `SUPERSEDED/STALE_CLOSE_CANDIDATE`; Schließen erst nach Maintainer-Readback, kein Merge.

## 11. Human Decisions

| Gegenstand | Entscheidung |
|---|---|
| #811 | unterstützte Python-Mindestversion, Matrix und wirksamer Release |
| #567 | bestätigte Netz-/L2-Ursache und Infrastrukturmaßnahme |
| #857 | spätere a26-Neubasis, Releaseumfang und Human Merge |
| Demo-PRs #101/#107/#109/#111/#120/#126 | historische PR-Evidence nach Readback schließen |
| Phase-A/Phase-B-Vertrag | exakte Q-Stufen- und Authoritygrenze eines neuen Preparation-Receipts |
| PR #899 / Issue #898 | Human Review/Merge; danach kanonische Wiki-Projektion aktualisieren |

## 12. Golden Preparation vs Golden Subject Run

Die Trennung ist bereits teilweise angelegt: Operating Rules R24 trennt Development Rehearsal vom formalen D0, der Operatorpreflight bindet Credentials, Origin, Seed, frischen State, fünf Routen, Dashboard und Releasequelle, und VERSIONING beschreibt Rehearsal → Release → frischen D0-Subject.

Die dokumentierte Lücke liegt vor dem Subject Run: Es gibt keinen eigenen unveränderlichen, ausdrücklich nicht qualifizierenden Phase-A-Abschlussreceipt und keinen eindeutigen Contractpunkt, an dem Issue/Q00 und damit Phase B beginnt. Die Q00–Q16-Tabelle liegt zudem im Demo-Repository.

Empfehlung für später: einen Phase-A-Readiness-Receipt für Installation, Config, Provider-/LLM-Routing, Credentials, Webhooks, Workspaces, Dateirechte, Runtime UID/GID, Doctor, Dashboard, bounded Routingqualification, Runtime Binding und Production Freeze definieren. Phase B darf erst nach dessen PASS den Issue-/Q10-/Approval-/Candidate-/MANUAL-/Gate-/PR-/Human-Merge-/Deploy-/Auditpfad starten. Die Zuordnung einzelner Q-Stufen und Authoritygrenzen ist `HUMAN_DECISION_REQUIRED`. Heute wurde daran nichts geändert.

`Golden/Release untouched = true`: Attempt 37 wurde nicht erzeugt, Attempt 36 nicht repariert oder fortgesetzt, kein Freeze neu erzeugt, kein Release/Tag angelegt, kein Provider/Route/Prompt/Harness/Runtime-Binding geändert.
