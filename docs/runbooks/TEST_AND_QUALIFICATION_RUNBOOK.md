# Test and Qualification Runbook

Stand: `main@41340e75`, 2026-09-29. Befehle stammen aus
`.gitea/workflows/ci.yml`, den ausgelieferten Tools und den bestehenden
Release-/D0-Vertraegen. Dieses Runbook schafft keine neue Authority.

## Gemeinsame Regeln

- Golden ist kein Debugginglauf. Ein fehlgeschlagener Subject bleibt FAIL.
- Verschiedene Runs werden nie zu einem PASS zusammengesetzt.
- Provider-/Modell-/Configwechsel ist ein neuer Input und mindestens ein neuer
  Attempt; nach Candidate-/Releasebindung ist regelmaessig ein neuer Subject
  erforderlich.
- `configured` oder `stored_effective=match` bedeutet nicht `available`.
- `PlanBlocked` und `WorkflowBlocked` werden nicht durch Handler-, Bus-, DB-
  oder Labelmanipulation umgangen.
- Human Approval, MANUAL Acceptance und Human Merge bleiben echte
  Humanhandlungen.
- Labels sind Projektion. Plan, Contract, Policy, Source und Candidate-Head
  bleiben die Authority und muessen bei Fortsetzung unveraendert gebunden sein.
- Signierte Webhookdelivery und authentifiziertes Polling sind getrennte
  Transport-Evidence, auch wenn beide dieselbe Entscheidung materialisieren.
- Prep-/Harness-, Provider-, Operator- und Productfehler werden getrennt.

## Teststufen

| Stufe | Zweck und erlaubter Claim | Voraussetzungen / Befehl | Stop, Recovery und Evidence |
|---|---|---|---|
| Format/Lint | statische Stil- und Fehlerpruefung; beweist keine Runtimewirkung | isolierte Dev-Umgebung; `ruff check .` und `ruff format --check .` | jeder Befund stoppt CI; Code/Doku korrigieren und gleiche Stufe wiederholen; Log + SHA sichern |
| Typecheck | statische Produktions- und Testtypen | `mypy samuel/ --ignore-missing-imports`; `mypy --config-file mypy-tests.ini` | Typfehler stoppt; Impact-Retest, danach volle CI |
| Architektur/Contracts | Slicegrenzen, Capability-/Dokument-/Wiki-/Containervertrag | `python3 tools/control_matrix.py check`; `python3 tools/wiki.py check`; `python tools/container_release.py check`; `pytest tests/test_architecture_v2.py -v` | Drift nie manuell uebergehen; generierte/gebundene Quelle korrigieren; Receipts und Digests sichern |
| Unit/Regression | lokale Funktion und konkrete Defekte | `pytest tests/ samuel/ -v --tb=short` | rot stoppt; gezielter Retest ist Debug-Evidence, volle Suite vor PR bleibt Pflicht |
| Integration | Komponenten- und reale In-Process-Uebergaenge | in der vollen Suite, besonders `tests/test_*integration*.py`, State, Workspace, Watch, Approval und Gate-Tests | beweist keinen externen SCM-/Providerbetrieb; JUnit/Log und Head sichern |
| Docs/Wiki/Capability | aktive Claims gegen gebundene Quellen | Contracttools oben plus relevante `tests/test_active_docs.py`, `test_document_contract.py`, `test_control_matrix.py`, `test_wiki.py` | historische Dateien nicht umschreiben; aktuelle Quelle oder Statusindex korrigieren |
| Container/Release offline | reproduzierbarer Build-/Lock-/Lizenzvertrag ohne Publish | `python tools/container_release.py check`; Build in Tempdir mit `python -m build --outdir "$DIR"`; `python tools/verify_distribution_license.py "$DIR"` | kein Registry-Push; Buildlog, Manifest-/Lockdigests sichern |
| Security/Dependencies | bekannte Dependencyvulnerabilities und Secretgrenzen | `python tools/run_pip_audit.py --attempts 3 --delay-seconds 5`; diff-/history Secret-Scan mit redigiertem Ergebnis | echte Vulnerability stoppt sofort; Transportfehler bounded retry; niemals Fundwerte protokollieren |
| Public Flow / Black Box | nur installierte CLI, REST, SCM und dokumentierte Operatorpfade | frische Installation; Befehle aus `INSTALL.md`; keine internen Handler | interner Dispatch entwertet den Claim; Request-/Responseklassen, Version und Subject sichern |
| Provider Self-Check | reale Erreichbarkeit jeder effektiv aktiven Taskroute | aktuelle Config/Secrets, bounded Connection-Test je Planning, Implementation, Review, Healing, Evaluation | Auth, unavailable, Schemafehler oder Truncation blockiert positiven E2E; keine Route im laufenden Attempt wechseln |
| Positive Development E2E | normaler Hauptpfad bis PR, CI, Human Review/Merge | frischer isolierter SCM-Subject, exakter Product-/Demo-Head, Labels, Runner, Webhook, Required Check und alle Routen bereit | erster Product-/Harness-/Providerfehler beendet Attempt; Ursache klassifizieren, Fix separat integrieren, neuer unveraenderter Komplettlauf |
| Negative Development E2E | fail-closed Verhalten an gezielten oeffentlichen Grenzen | eigener frischer Negativsubject und erwarteter Blockvertrag | kein Heilen zu PASS; gebundener Reason-Code, fehlende Nebenwirkung und Evidence sichern |
| Development Golden Rehearsal | releasefaehige, zusammenhaengende Development-Strecke | alle Vorchecks PASS; unveraenderte Kandidateninputs; #859 | jeder Fehler terminal; keine Kombination alter Runs; kompletter neuer Lauf nach Fix |
| Formal Golden/D0 | releasegebundener Positiv- und Negativnachweis | immutable Release/Publish, frische Installation, neuer Subject, D0-Vertrag #658 | keine Debugaktion; Abweichung FAIL und neue Release-/Subjectentscheidung |
| Release/Publish | create-only Artefakte, Human Merge/Tag/Publish und Readback | `VERSIONING.md`, `CONTAINER_RELEASE_OPERATIONS.md`, Release-Gates; getrennte Publisherrolle | kein Force/Overwrite; unterbrochenen Publish nur ueber dokumentierte Recovery; Tag, Assets, Digests, CI sichern |
| Post-Publish | beweist Auslieferung und Nutzbarkeit des exakten Artefakts | frische Installation vom publizierten Digest/Asset, Version/Revision/Health und D0-Readback | andere lokale Builds sind keine Ersatz-Evidence |

`$DIR` wird mit `mktemp -d` erzeugt. Release-, Provider- und SCM-Befehle mit
externen Wirkungen werden nur aus den jeweils akzeptierten Runbooks ausgefuehrt.

## Impact-Retest, kompletter Lauf und neuer Subject

Ein Impact-Retest genuegt waehrend der Fehlerkorrektur, wenn er nur die
betroffene lokale Grenze bestaetigt. Vor Merge folgt trotzdem die volle CI.
Nach einem Fix in einer bereits begonnenen E2E-/Golden-Strecke folgt ein neuer
vollstaendiger Lauf. Ein neuer Subject ist zwingend, wenn der alte Subject
terminal fehlgeschlagen ist, Inputs oder Authoritybindungen gewechselt haben,
oder der Formal-D0-Vertrag Frische verlangt. Derselbe langlebige Issue darf nur
ueber den sicheren, vom Core abgeleiteten Re-Entry-Vertrag #920 erneut versucht
werden; alte Evidence bleibt erhalten.

## Failure-Klassifikation

| Klasse | Beispiel | Zulaessige naechste Aktion |
|---|---|---|
| PRODUCT_DEFECT | fehlender MANUAL-Dispatch im historischen Issue #3 | Issue/Regression/Fix/volle CI; alter Run bleibt FAIL |
| QUALIFICATION_HARNESS | Labels nicht provisioniert, falscher Startpfad | Harness/Runbook korrigieren; Productcode nicht erfinden |
| OPERATOR | nicht autorisierter Hook-/State-Eingriff | stoppen, Evidence sichern, sicheren Prepweg wiederherstellen |
| PROVIDER_QUALITY/AVAILABILITY | Outputlimit, Modell weg, inkompatible Antwort | Route vor neuem Attempt real pruefen; kein Corebug ohne Codeevidence |
| ENVIRONMENT/INFRASTRUCTURE | Mountrechte, Netzwerk, Runner | Infrastruktur beheben und Readiness neu pruefen |
| CONTRACT/POLICY | Parser-, Source-, Candidate- oder Required-Gate-Block | fail-closed; autorisierten Fix oder Replan, keine Umgehung |

## Aktuelle Development-E2E-Evidence

- Issue #1: Planning-Truncation, falsche Runner-Autodetection,
  Label-Provisioning und spaeter Contract/Selectorgrenzen. Die technischen
  Runner-/Retry-/GREP-Fixes sind heute integriert; der Run bleibt historisch.
- Issue #2: Planning und echte Human Approval bestanden; Implementation endete
  auf einer bekannten Route mit `token_limit` bei 8192, ohne Candidate.
- Issue #3: alle Routen vorgeprueft; Planning, Human Approval, Implementation,
  Candidate und automatische Gates bestanden; signierter MANUAL-Receipt wurde
  beobachtet, aber damals nicht fortgesetzt. #910 behebt den Codepfad; kein
  alter Run wurde fortgesetzt.

Daraus folgt weiterhin: kein kompletter positiver Development-E2E, kein
Development Golden, kein Formal D0 und kein daraus erzeugter PR/Merge.

## Ausfuehrungs- und Ergebnisvertrag je Ebene

Die Befehle oben sind die tatsaechlichen CI-Kommandos aus
`.gitea/workflows/ci.yml`. In einer lokalen Umgebung wird dieselbe installierte
Projekt-Pythonumgebung verwendet; ein fehlendes globales `pydantic`, Ruff oder
Mypy wird nicht durch geaenderte Productdependencies kaschiert. Der
Documentation-Contract laeuft mit `tools/control_matrix.py check`; die
Wiki-Projektion mit `tools/wiki.py check` und nach einem Build zusaetzlich
`check-local`. Ein Wiki-Publish ist ein getrennter externer Effekt und liefert
eine eigene Source-/Artifact-/Remote-Head-Receipt.

| Ebene | Input und Authority | Mutation / erwartete Evidence | PASS / FAIL / BLOCKED / NOT_EVALUATED |
|---|---|---|---|
| Ruff, Format, Mypy, Unit/Integration, Architektur | exakter Checkout-Head, Lock-/Pyproject-Stand, installierte CI-Tools | nur lokale Test-/Buildartefakte; Exitcode, Testzahl und Head | PASS nur bei Exit 0; rote Assertion/Typregel FAIL; fehlendes Tool BLOCKED; nicht gestartet NOT_EVALUATED |
| Control-/Document-/Wiki-Contract | versionierte Quellen, Manifest und aktuelle generierte Bindungen | `check` liest; ein bewusstes `render`/Wiki-`build` aendert nur generierte Dokumentartefakte | Digest- oder Coverage-Drift FAIL, nicht als „nur Doku“ ignorieren |
| Container offline, Distribution, Lizenz, Dependency-/Secret-Scan | exakter Source-Head, Build-/Lockdateien und definierte Scanrange | temporaere Buildartefakte; Paketmetadata, Asset-/Lizenz- und redigierte Scannergebnisse | echter Fund FAIL; Tool-/Netzausfall BLOCKED nach bounded Retry; kein Publishclaim |
| Providerprobe und Public Flow | effektive Taskrouten, Credentials nur im Prozess, SCM-/Operatorrolle | explizit autorisierte bounded Provider-/SCM-Probes; Requestklassen, Route, Schema, Zeiten, redigierter Fehler | konfigurierte Route allein NOT_EVALUATED; Auth-/Schema-/Truncationfehler FAIL/BLOCKED fuer den positiven Subject |
| Development E2E / Golden | frischer isolierter SCM-Subject, Product-/Demo-/Config-/Policy-/Runnerbindung, echte Humanentscheidungen | oeffentliche Workflowwirkungen, PR/CI/Human-Merge-Receipt nur im freigegebenen Subject | PASS nur als zusammenhaengender unveraenderter Lauf; erster materieller Fehler FAIL; fehlende Vorbedingung BLOCKED vor Start |
| Release und Formal D0 | Human-Merge, create-only Tag, veroeffentlichter unveraenderlicher Digest, frische Installation | Publisherwirkung und danach neuer D0-Subject; Tag-/Asset-/OCI-/Installations-/Goldenbelege | Publish-PASS ist kein D0-PASS; Bot-Merge, Subjectwechsel oder alte Teilbelege ergeben keinen Gesamt-PASS |

Bei einem **Productdefekt**: alten Subject und Fehlerevidence erhalten,
Defekt auf Product-`main` separat mit Tests/PR/CI beheben und fuer positive
E2E-/Golden-Claims einen neuen vollstaendigen Subject beginnen. Bei einem
**Provider- oder Infrastrukturfehler**: Fehlerquelle und effektive Route
festhalten, Vorbedingung ausserhalb des laufenden Subjects beheben und
Readiness neu pruefen; ein anderer Provider ist ein neuer Input. Bei einem
**Harness-/Operatorfehler**: die Preparation stoppen, Nebenwirkungen
read-backen und nie als Product-PASS oder Productdefekt umdeuten.

`retry` ist nur innerhalb des implementierten, budgetierten
Transport-/Taskvertrags zulaessig. `replan` widerruft den alten Plan und
benoetigt frische Authority; `resume` finalisiert ausschliesslich gebundene
persistierte technische Wirkungen. Ein freier terminaler Workflow-Retry ist
bis #920 nicht verfuegbar. Evidence verschiedener Heads, Releases, Provider,
Config-/Policy-Digests, Actors oder Subjects wird niemals zu einem Golden-
oder Formal-D0-PASS kombiniert. Eine lokale Regression darf die historische
Failure-Receipt nicht rueckwirkend aendern.
