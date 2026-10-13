# Current Engineering Workflow

Abgeleitet aus `OPERATING_RULES.md`, `CONTRIBUTING.md`, `VERSIONING.md`, der
Gitea-CI und den bestehenden Release-/D0-Vertraegen; aktueller Abgleich auf
`b59b1fc3def41ce73fef1cf29841a2e6ffbe8db7` (10.10.2026). Normative
Quellen gehen diesem erklaerenden Index vor.

| Stufe | Required / Authority | Evidence und unzulaessige Abkuerzung |
|---|---|---|
| Issue Intake | required; Mensch/SCM definiert Bedarf und Scope | Issue, Source-Snapshot, Risiko; keine erfundene Maschinenlesbarkeit |
| Analyse/Planung | required; Planner erzeugt Vorschlag, Parser/Core validiert | gebundener Plan/Contract/Policy/Base; kein Label als Authority |
| Planfreigabe | workflowabhaengig: standard/watch/self/chat verlangen echte Human Approval; klare autonome/night/patch-Plaene koennen nur nach ihrer expliziten Policyfreigabe fortfahren, gebundene Klaerungsbasis wartet auch dort auf den Menschen | Actor-/Source-/Contractbindung oder exakte Policy-Evidence; Label, Bot oder alte Approval nicht uebertragen |
| Implementierung | required; gebundener Worker im autorisierten Scope | Candidate-Commit und Workspace-Receipt; keine Mutation von `main` |
| lokale Pruefungen | required | Impacttests waehrend Debugging, volle CI-Suite vor Abschluss |
| Required Gates | required; Gate registry/policy | exakter Candidate, Contract und Evidence; kein Skip durch Statusprojektion |
| PR | required fuer Productaenderung | Head/Base/Issue/Marker gebunden; Dokumentationsfolgen nach [Documentation acceptance](../../CONTRIBUTING.md#documentation-acceptance) im selben PR bearbeiten oder konkret begründen; kein Direktpush |
| CI | required; Gitea Actions Required Context | exakter PR-Head; alte oder fremde gruenen Runs zaehlen nicht |
| Review | required gemaess Workflow | gebundene Reviewentscheidung; Providerfehler wird fachlich blockiert |
| Human Merge | required durch Projektvertrag | Maintainerentscheidung; keine Bot-/Adminumgehung |
| Release Candidate | optional bis Releaseauftrag, danach required | sauberer `main`, Changelog, pre-tag Gate; kein stale Kandidatenchangelog |
| Release/Publish | explizite Human-/Publisherauthority | create-only Tag/Assets/Image/Digests und Post-Publish-Readback; kein Overwrite |
| Development E2E | required fuer Hauptpfadclaims | frischer isolierter Subject, oeffentliche Pfade, kompletter Lauf |
| Golden/D0 | required fuer Golden-/D0-Claim | immutable Release, frische Installation, Positiv- und Negativsubject |
| Issueabschluss | nach belegtem Scope | Implemented/Verified/Remaining-Kommentar; Merge allein reicht nicht |
| Doku/Wiki-Sync | required bei relevantem Delta | versionierte Quellen, Contractcheck, Publishreceipt nach Merge |
| GitHub/Public-Sync | explizite Public-Freigabe | secretfreier Delta-/Historyscan und exakter Pushplan |

`run`, `replan`, bound resume und Healing besitzen verschiedene Aufgaben.
`resume` finalisiert nur persistierte technische Zustande; Healing ist begrenzt;
Replan widerruft einen autoritativen Plan; ein allgemeiner terminaler Retry ist
bis #920 kein freier Operator-Stage-Sprung.

Die frühere Warteforderung „Testkonzept erst nach getrennter Erstinstallation“
ist für den heutigen Arbeitsstatus SUPERSEDED: a29 ist veröffentlicht und
frisch installiert; #994 beauftragt und trägt die Abnahmeinventur sowie
Testentwürfe. Eigene Maintainerreview und tatsächliche Ausführung bleiben
getrennt ausstehend. Die 24 administrativen Altissueabschlüsse vom 05.10.2026
bleiben historische Entscheidungen ohne Abnahme-PASS; ihre heutigen Restclaims
stehen in #962. Normaler Entwicklungsworkflow benötigt keinen Golden-PASS.
Human START/Planfreigabe, MANUAL, Human Merge und reale Isolation werden weder
durch Testplanung noch durch CI ersetzt. Historische Releaseentscheidungen
bleiben im datierten Qualification-Runbook erhalten.

Der tatsaechliche normale Entwicklungsabschluss ist: Issue und Scope lesen,
Code/Config/Tests und erforderliche Dokumentations-/Quellenbindungsänderungen
auf einem eigenen Branch im selben PR bearbeiten, lokale Impacttests,
vollstaendige CI, PR-Review und regulären Human Merge abwarten. Danach
Issue-Body/Restpunkte sowie aktive Doku, Quellenbindungen und betroffene
Wiki-Projektionen gegen den tatsächlichen Merge-Head prüfen. Ein dort erst
erkannter Fehler benötigt eine reguläre Korrektur; dieser Integrationscheck
verschiebt bekannte Dokumentationsfolgen nicht auf einen späteren PR.
Ein Releaseauftrag fuehrt erst danach ueber create-only Tag und Publisher-
Readback zum veroeffentlichten Artifact. Der Development-E2E-/Golden-Nachweis
braucht eine unveraenderte komplette Strecke; Formal D0 beginnt separat auf
dem tatsaechlich publizierten Release. Die datierten Abkuerzungen und ihre
Folgen stehen in `PROCESS_DEVIATIONS_AND_SHORTCUTS.md`.
