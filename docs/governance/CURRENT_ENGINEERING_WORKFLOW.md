# Current Engineering Workflow

Abgeleitet aus `OPERATING_RULES.md`, `CONTRIBUTING.md`, `VERSIONING.md`, der
Gitea-CI und den aktuellen Release-/D0-Vertraegen auf `41340e75`. Normative
Quellen gehen diesem erklaerenden Index vor.

| Stufe | Required / Authority | Evidence und unzulaessige Abkuerzung |
|---|---|---|
| Issue Intake | required; Mensch/SCM definiert Bedarf und Scope | Issue, Source-Snapshot, Risiko; keine erfundene Maschinenlesbarkeit |
| Analyse/Planung | required; Planner erzeugt Vorschlag, Parser/Core validiert | gebundener Plan/Contract/Policy/Base; kein Label als Authority |
| Planfreigabe | workflowabhaengig: standard/watch/self/chat verlangen echte Human Approval; klare autonome/night/patch-Plaene koennen nur nach ihrer expliziten Policyfreigabe fortfahren, gebundene Klaerungsbasis wartet auch dort auf den Menschen | Actor-/Source-/Contractbindung oder exakte Policy-Evidence; Label, Bot oder alte Approval nicht uebertragen |
| Implementierung | required; gebundener Worker im autorisierten Scope | Candidate-Commit und Workspace-Receipt; keine Mutation von `main` |
| lokale Pruefungen | required | Impacttests waehrend Debugging, volle CI-Suite vor Abschluss |
| Required Gates | required; Gate registry/policy | exakter Candidate, Contract und Evidence; kein Skip durch Statusprojektion |
| PR | required fuer Productaenderung | Head/Base/Issue/Marker gebunden; kein Direktpush |
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

Der tatsaechliche normale Entwicklungsabschluss ist: Issue und Scope lesen,
Code/Config/Tests auf einem eigenen Branch bearbeiten, lokale Impacttests,
vollstaendige CI, PR-Review und regulären Human Merge abwarten, danach
Issue-Body/Restpunkte und aktive Doku gegen den Merge-Head korrigieren.
Ein Releaseauftrag fuehrt erst danach ueber create-only Tag und Publisher-
Readback zum veroeffentlichten Artifact. Der Development-E2E-/Golden-Nachweis
braucht eine unveraenderte komplette Strecke; Formal D0 beginnt separat auf
dem tatsaechlich publizierten Release. Die datierten Abkuerzungen und ihre
Folgen stehen in `PROCESS_DEVIATIONS_AND_SHORTCUTS.md`.
