# Process Deviations and Shortcuts

Diese datierte Liste beschreibt beobachtete Praxisabweichungen. Sie aendert
`OPERATING_RULES.md` nicht.

| Abweichung | Wirkung | Korrektur |
|---|---|---|
| Debugging, Impacttest und Qualification vermischt | Teilstrecken wirkten wie Golden-Evidence | Stufen im Test-/Qualification-Runbook trennen |
| Impacttests als Abschluss verstanden | unveraenderte Gesamtstrecke blieb unbelegt | nach jedem Fix volle CI und neuer kompletter Rehearsal-Lauf |
| bekannte Providerroute erneut ohne Suitability-Probe | wiederholte Implementation-Truncation | bounded reale Probe jeder effektiven Route vor Subject |
| Setupready trotz fehlender Labels | erster LLM-Pfad wirkte, Statusmaterialisierung scheiterte | Labels/Required Checks/Webhook/Runner als Preflightmatrix |
| ad-hoc `.env`-/Containerhelper | andere Secret- und Startsemantik als Production | ausgelieferten Compose-/Setupweg verwenden |
| neue Vorbedingungen erst im laufenden Attempt | viele terminale Subjects und Zeitverlust | #921 als vollstaendige Readiness; bei UNKNOWN nicht starten |
| lokale Harnesslogik als Productauthority | Diagnose konnte als Capability missverstanden werden | Authorityklasse an jeder neuen Aussage, historische Evidence separat |
| Abschluss-Sync von Issues/Doku/Wiki ausgelassen | alte offene/erledigte Claims und stale Navigation | Housekeeping-PR, Issue-Matrix und Wiki-Publish nach Merge |

Diese Abweichungen rechtfertigen weder interne State-Reparatur noch eine
Lockerung von Human-, Gate-, Security- oder Mergegrenzen.

## Datierte Befunde und tragende Regel

| Zeitpunkt / Abweichung | Warum sie entstand und beobachtete Folge | Kuenftige Sperre / Traeger |
|---|---|---|
| August/September 2026: 3x100-/3-of-3-Heuristik als scheinbare allgemeine Qualification | Run-lokales Score-/Wiederholungsmuster wanderte in eine breitere Golden-Behauptung; Teil-PASS wurde ueberbewertet | Nur der konkrete akzeptierte Subjectvertrag zaehlt; #658/#859 und `OPERATING_RULES.md` |
| September 2026: lokale Checkout- und Remote-SHA ohne erneuten Readback verwechselt | Dokument-/Testclaim bezog sich auf einen aelteren Stand als Gitea-`main` | Vor jeder Wirkung Fetch, Mergebase, Safety-Snapshot und Fast-forward; #840 |
| 28.09.: ad-hoc `.env`-Parsing und Helper-Container statt ausgeliefertem Startpfad | Secret-/Compose-Werte und Owner-/Mountverhalten wichen vom Productionpfad ab; positive Helperproben waren keine Installationsqualification | kanonischer Setup-/Compose-Pfad, keine eigene dotenv-Semantik; #900 |
| 28.09.: nativen Hook-Test als harmlosen Preflight verstanden | Gitea-Push-Event beruehrte historische Demo-Issues und erzeugte WorkflowBlocked-Evidence | isolierter Subject, nicht autorisierender Testevent und Native-Delivery-Readback; #900/#905 |
| 28./29.09.: Labels/Runner erst nach Beginn des Subjects entdeckt | fehlende Workflowlabels und falsche unittest/Pytest-Erkennung blockierten spaet | exakter Label-/Required-Check-/Runner-Preflight; #900/#921 |
| 29.09.: bekannte 8192-Token-Implementationroute erneut verwendet | zweiter positiver Versuch endete vor Candidate an derselben Outputgrenze | bounded reale Route-/Suitability-Probe vor dem Subject; #822/#679/#859 |
| 29.09.: signierten MANUAL-Receipt als Fortsetzung angenommen | Receipt wurde beobachtet, aber keine Reevaluation dispatcht; alter Run blieb FAIL | #910/PR #911 Regression; neuer kompletter Lauf #859 |
| 29.09.: Docs-Meta-PR als vollstaendige Reconciliation bezeichnet | 36 aeltere offene Issues hatten keinen aktuellen Remote-Deltaanker; Wiki und Primardokumente blieben alt | v9-Remote-Kommentare, Dokument-Readback und Wiki-Publish nach Merge; #923 |

Die Datierung bezeichnet den beobachteten Vorfall, nicht den Zeitpunkt einer
spaeteren Reparatur. Kein Eintrag erteilt eine neue Workflow- oder
Qualification-Authority.
