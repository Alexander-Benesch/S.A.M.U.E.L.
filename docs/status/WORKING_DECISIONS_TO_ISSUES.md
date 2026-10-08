# Working Decisions to Issues

Quelle: lokales `SAMUEL_WORKING_DECISIONS_v8.md`, erhoben 2026-09-29. Das
Sammeldokument besitzt keine Product-Authority und bleibt unveraendert in der
lokalen Safety-Evidence erhalten.

| Working Decision | Ergebnis | Referenz / heutiger Befund |
|---|---|---|
| 1 Qualification-/Golden-Konzept | ISSUE | #859, #658; Runbook dieses PRs |
| 2 SCM-Subject-Isolation | ISSUE | #900; disposable Repo-Matrix |
| 3 Provider-Readiness | ISSUE | #822, #679, #921 |
| 4 externe Provider-Web-URLs | ISSUE | #922; Katalog/Benchmark in `costs.py` bestaetigt hardcoded |
| 5 Dashboard `llm failed (4/1!)` | VERIFY_LATER | #890/#891; einzelner Fund belegt keinen eigenen Bug |
| 6 `.env`-Parsing | ISSUE / OPERATOR CONTRACT | #900/#905; kanonischen Compose-/Loaderpfad verwenden |
| 7 Qualification-Hilfspfad vs. Production-Start | ISSUE | #900; Hilfspfad bleibt Diagnose, nicht Qualification |
| 8 Required-Gate-Lokalisierung | ISSUE | #890; keine Secretwerte oder Fingerprints |
| 8 Gitea-Setup im Wizard | ISSUE | #905, #921; least-privilege und Readback |
| 9 Gate-Findings operatorverstaendlich | ISSUE | #890, dupliziert semantisch Decision 8 |
| 10A Review ProviderUnavailable | CLOSED_WITH_EVIDENCE | #912 / PR #914 / Main-CI #1030 |
| 10B konkurrierendes Resume | CLOSED_WITH_EVIDENCE | #913 / PR #915 / Main-CI #1032 |
| 11 Complexity-Warn | VERIFY_LATER | bestehendes Feature #247; keine neue Bug-Evidence |
| 12 terminale Blocker / Re-Entry | ISSUE | #920 |
| 13 Full Self-Check | ISSUE | #921; nutzt #693/#694, grenzt #888/#900/#905 ab |
| 14A Runner-Autodetection | CLOSED_WITH_EVIDENCE | #754/#756 plus aktuelle Runnergrammar-Regressionen |
| 14B Label-Provisioning | ISSUE / HARNESS | #900/#905/#921; fehlende Prep war kein belegter Corebug |
| 15 Replan/Backtick-Contract | CLOSED_WITH_EVIDENCE | #902/#916 und heutige Contract-/Parserregressionen |
| 16 Implementation Output-Limit | ISSUE / PROVIDER EVIDENCE | #822/#679/#920; kein erfundener Corebug |
| 17 MANUAL-Continuation | CLOSED_WITH_EVIDENCE + REMAINDER | #910/PR #911 technisch geschlossen; Human-UX bleibt #880 |
| 18 Housekeeping | DOCS PR | dieser Branch; Human Merge und danach Wiki/Public-Sync bleiben extern |

Materialisierung veraendert keine alte Failure-Evidence und erzeugt keine
Goldenbehauptung. Neue Issues wurden nur fuer die drei bestaetigten, nicht
passend abgedeckten Scopeeinheiten #920 bis #922 angelegt.
