# Prompt-Contract-Audit

> **HISTORICAL / AUDIT_EVIDENCE.** Der folgende Audit bindet den damaligen
> Consumerstand vom 24.09.2026 an `3be2694` und Campaign #859 / Attempt 18.
> Er bleibt unverändert als Provenienz erhalten und ist kein vollständiger
> Nachweis der heutigen Promptauflösung, Overridebedienung oder Qualification.
> Aktuelle Nutzung: [Prompt-/Operatoranleitung](agents/AGENT_PROMPTS_AND_INSTRUCTIONS.md)
> und [Config-/Providerreferenz](agents/AGENT_CONFIGURATION_REFERENCE.md).
> Verhalten bestimmen aktueller Code, Config und gebundene Consumercontracts.

Stand: 24. September 2026, Produkt-Commit `3be2694`, Issue #877. Der Audit
folgte dem tatsächlich ausgeführten Code bis zum Parser oder Consumer. Die
Promptdateien wurden nicht nur untereinander verglichen. Operator-Overrides
waren im geprüften Checkout und in der gebundenen Konfiguration von Campaign
#859, Attempt 18, nicht vorhanden.

## Gemeinsamer Ladepfad

`samuel/adapters/llm/prompts.py` löst einen Prompt in dieser Reihenfolge auf:
Modell-Override, Provider-Override, generischer Operator-Override,
Package-Default unter `samuel/core/prompts`. `SystemPromptInjectorAdapter`
stellt den Text als Systemnachricht voran, sofern der Aufrufer nicht bereits
eine Systemnachricht mitgibt. Die Task-Konfiguration in
`config/llm/defaults.json` bindet `planner`, `senior_python`, `reviewer`,
`healer` und `log_analyst` an die Tasks `planning`, `implementation`, `review`,
`healing` und `evaluation`. Nur die ersten vier Tasks haben einen produktiven
LLM-Consumer. `analyst.md` und `docs_writer.md` sind editierbare
Prompt-Library-Einträge ohne Task-Bindung.

Die gemeinsame Provider-Schicht wiederholt begrenzte transiente
Transportfehler gemäß `llm.retry` (Default: höchstens drei Versuche). Das ist
kein semantischer Retry für eine syntaktisch oder fachlich ungültige Antwort.

## 1. `planner.md`

- **Tatsächlich geladener Systemprompt:** Package-Default `planner.md` über
  Task `planning`; die Override-Kaskade bleibt wirksam.
- **Runtimeassembly und Kontext:** `PlanningHandler._build_plan_prompt` ergänzt
  Guard-Marker, Issue-Titel und -Body in `user-content`, Skeleton,
  relevante Dateiauszüge, GREP-Treffer, Architekturvorgaben, den kanonischen
  Scope-Block sowie die zur realen Runner-Policy passende TEST-Grammatik.
- **Parser/Consumer und Schema:** `validate_plan`,
  `parse_acceptance_scope` und `parse_acceptance_contract` verlangen die fünf
  Markdown-Abschnitte, Scope-Schema 1 und die Tags `DIFF`, `IMPORT`, `GREP`,
  `GREP:NOT`, `EXISTS`, `TEST` oder `MANUAL`. Scope-, Skeleton-,
  Semantik- und Komplexitätsprüfungen konsumieren das Ergebnis.
- **Retry/Healing:** Nach einem ungültigen Contract oder Precheck gibt es
  höchstens einen fachlichen Plan-Retry. Hinzu kommen nur die transienten
  Transport-Retries des Adapters. Planning hat keinen Healingpfad.
- **Security/Authority:** Issue-Inhalt bleibt markierter User-Content.
  Prompt-Risk-Analyse ist advisory. Parser, genehmigter Scope, menschliche
  Planfreigabe und spätere Gates sind autoritativ; der Systemprompt ist
  Defense in Depth.
- **Qualitätsheuristiken:** Minimaler Scope, belegte Symbole,
  Seiteneffektprüfung, repositoryweite GREP-Semantik und konfigurierte
  Komplexitätsschwellen. Die Runtime entscheidet über Warnung oder
  `split_recommended`.
- **Redundanzen:** Scope-Layout, AC-Tags und GREP-Grammatik stehen bewusst auch
  im Runtimeprompt, weil dieser die aktuelle maschinenlesbare Form besitzt.
- **Bestätigte Drift:** Der Systemprompt verschwieg `MANUAL`, behauptete
  Skeleton-only-Kontext, verbot belegte neue Dateien, nannte veraltete
  Kontrollpfade und duplizierte eine abweichende feste Komplexitätsschwelle.
- **Campaign-#859-Findings:** #860 (Scope-Layout) und #867
  (repositoryweites `GREP:NOT`) waren echte frühere Promptfehler und sind im
  geprüften Stand bereits behoben. Die jetzt korrigierten Restabweichungen
  erklären Attempt 18 nicht.
- **Minimale Änderung:** Eingabebeschreibung, Authority-Formulierung,
  `MANUAL` und Komplexitätshinweis an den realen Consumer angleichen. Parser
  und Runtime-Schema bleiben unverändert.

## 2. `reviewer.md`

- **Tatsächlich geladener Systemprompt:** Package-Default `reviewer.md` über
  Task `review`; die Override-Kaskade bleibt wirksam.
- **Runtimeassembly und Kontext:** `ReviewHandler._bound_prompt` sendet den
  exakten PR-Diff, Subject-Digest, Acceptance Contract, Diff-, Policy-, Tool-
  und Promptbindung. Vor der Korrektur fehlten die bereits vorhandenen
  Acceptance- und Required-Gate-Ergebnisse sowie die Transportsemantik von
  Markdown- und GREP-Anführungszeichen. Der Prompt enthält nun ausschließlich
  aus subject-gebundener Evidence berechnete Zähler wie `7/7 PASS` und
  `17/17 PASS`; unvollständige Evidence wird nicht als PASS dargestellt.
- **Parser/Consumer und Schema:** `parse_review_decision` verlangt genau ein
  geschlossenes JSON-Dokument, Schema 2, die exakten Top-Level-Felder,
  geschlossene Findings und alle Subject-, Diff-, Policy-, Tool- und
  Prompt-Digests. `pass` darf keinen Blocker enthalten; `block` benötigt
  mindestens einen Blocker.
- **Retry/Healing:** Es gibt keinen semantischen Retry und keinen Healingpfad
  für ungültige Reviewantworten. Transiente Providerfehler können innerhalb
  des einen logischen Calls vom Adapter wiederholt werden. Truncation und
  Vertragsfehler blockieren fail-closed.
- **Security/Authority:** Review läuft nach `PRCreated` auf der exakten
  PR-Revision. Merge-Autorität prüft danach erneut Planfreigabe, Required
  Gates und Expected Head. Der LLM-Entscheid ersetzt keine dieser Bindungen.
  Kontrollpfadänderungen werden nur außerhalb des genehmigten Contracts oder
  bei konkreter Schwächung blockiert.
- **Qualitätsheuristiken:** Findings müssen auf geänderte Zeilen oder einen
  konkreten Acceptance-Verstoß zeigen. Suggestions sind mit `pass`
  vereinbar; fehlender unveränderter Kontext allein ergibt nicht
  `indeterminate`.
- **Redundanzen:** Das geschlossene JSON-Schema steht im gebundenen
  Runtimeprompt; der Systemprompt verweist darauf und wiederholt nur stabile
  Entscheidungsregeln.
- **Bestätigte Drift:** #874 (altes Markdown-/`needs-discussion`-Format) ist im
  geprüften Stand behoben. Bestätigt waren weiterhin fehlende PASS-Evidence,
  fehlende GREP-Transportsemantik und die Reduktion aller Parserfehler auf
  `review_contract_invalid`.
- **Campaign-#859-Findings:** Die fehlende Transportregel erklärt den im
  Read-only-Replay beobachteten falschen Blocker. Sie beweist nicht die Ursache
  der ursprünglichen ungültigen Attempt-18-Antwort, weil deren Rohtext nicht
  persistiert wurde. Die variable Replay-Ausgabe bleibt ein Route-Suitability-
  Befund. #876 ist damit als bestätigte Kontext- und Diagnoselücke
  klassifiziert, nicht als bewiesener Validatorbug.
- **Minimale Änderung:** Gebundene PASS-Zähler und Transportregel ergänzen;
  bei Parserfehlern eine feste, payloadfreie `validation_error_class`
  persistieren. Rohantworten bleiben verworfen, der Parser bleibt strikt und
  es wird kein Retry ergänzt.

## 3. `senior_python.md`

- **Tatsächlich geladener Systemprompt:** Package-Default `senior_python.md`
  über Task `implementation`; die Override-Kaskade bleibt wirksam.
- **Runtimeassembly und Kontext:** `_build_implement_prompt` sendet Issue,
  genehmigten Plan, Suchbegriffe, Plan-Dateien, Modulkontext, Skeleton,
  GREP-Treffer, relevante Dateien, Architekturvorgaben und optional den
  gebundenen Healing-Hinweis. Die Nutzernachricht definiert `REPLACE LINES`,
  `SEARCH/REPLACE`, `WRITE` und `SLICE`.
- **Parser/Consumer und Schema:** `patch_parser.py` akzeptiert die drei
  Patchformen sowie strukturierte JSON-Patches; der LLM-Loop konsumiert
  Slice-Anfragen. Target-Resolver, Scopeprüfung und Applier erzwingen
  Projektgrenzen und validieren Python-AST beziehungsweise JSON.
- **Retry/Healing:** Maximal fünf LLM-Runden, davon höchstens drei
  Slice-Runden mit bis zu fünf Slice-Anfragen je Runde. Apply-Fehler liefern
  begrenzte Codeauszüge für die nächste Runde; zwei Runden ohne Fortschritt
  beenden den Lauf. Die Workspace-Transaktion rollt atomar zurück.
- **Security/Authority:** Nur genehmigter Plan und Scope erteilen
  Mutation-Authority. Absolute Pfade, Traversal, Git-Control-Plane und Ziele
  außerhalb des Workspaces werden unabhängig vom Prompt blockiert.
- **Qualitätsheuristiken:** Kleine Patches, vorhandene Evidenz statt Raten,
  Seiteneffektprüfung und exakte SEARCH-Blöcke.
- **Redundanzen:** Der alte Systemprompt duplizierte Formate und Limits. Der
  genaue Wire-Contract gehört allein in die Runtime-Nutzernachricht.
- **Bestätigte Drift:** „ausschließlich Python“, eine nicht tatsächlich
  übergebene Datei `repo_skeleton.md`, „maximal drei“ Slice-Anfragen und ein
  sofortiges Slice-Ende widersprachen dem Mehrdatei-Parser und dem LLM-Loop.
- **Campaign-#859-Findings:** Die Implementierungsdrift erklärt keinen
  Attempt-18-Reviewfehler. #862/#863, #865 und #871 waren unabhängige echte
  Produktbugs in Authority-, Inline-Code-, GREP- und Runner-Pfaden und sind im
  geprüften Stand bereits behoben.
- **Minimale Änderung:** Systemprompt auf stabile Rolle, Scope und
  Qualitätsregeln reduzieren; aktuellen Patch-/Slice-Contract der Runtime
  überlassen und die Runtime-Grenzen eindeutig benennen.

## 4. `healer.md`

- **Tatsächlich geladener Systemprompt:** Package-Default `healer.md` über
  Task `healing`; die Override-Kaskade bleibt wirksam.
- **Runtimeassembly und Kontext:** Der produktive
  `BoundHealingCoordinator` sendet genau ein fehlgeschlagenes automatisches
  Acceptance-Kriterium mit ID, Tag, Grund und strukturierter Evidence.
- **Parser/Consumer und Schema:** Die LLM-Antwort wird nicht als Patch geparst
  oder direkt angewendet. Sie wird als einmaliger `healing_hint` an den
  Implementation-Consumer weitergereicht; erst dieser erzeugt und validiert
  Patches. Der ältere `HealingHandler` ist nicht im Bootstrap registriert.
- **Retry/Healing:** Genau ein gebundener fachlicher Healing-Claim und ein
  logischer LLM-Aufruf pro Observation. Es gibt keinen inhaltlichen
  Healing-Retry; nur transiente Adapter-Retries können innerhalb des Calls
  auftreten.
- **Security/Authority:** Healing ist nur bei exakt einem erforderlichen
  Gate-11-Fehler, genau einem automatisch behebbaren Kriterium, vollständiger
  Evidence und exakter Mutation-Authority zulässig. Der Healer selbst mutiert
  nichts.
- **Qualitätsheuristiken:** Ursache aus Evidence ableiten, genau eine minimale
  Korrekturrichtung, bei Mehrdeutigkeit `Unklar`.
- **Redundanzen:** Patch- und Slice-Protokolle im System- und Runtimeprompt
  waren redundant, weil der Consumer nur Freitext an Implementation übergibt.
- **Bestätigte Drift:** Der Prompt verlangte einen `SEARCH/REPLACE`-Patch,
  Befehle und ein `Auto-sicher`-Schema, obwohl nichts davon geparst oder direkt
  ausgeführt wird.
- **Campaign-#859-Findings:** Diese Drift erklärt Attempt 18 nicht, weil dort
  Required Gates bestanden und kein Healingpfad aktiv war. Frühere
  Healing-Ausgänge bleiben an ihre jeweiligen Gate-Findings gebunden.
- **Minimale Änderung:** System- und gebundenen Runtimeprompt auf eine
  evidence-basierte Korrekturrichtung für den Implementierungsagenten
  reduzieren.

## 5. `analyst.md`

- **Tatsächlich geladener Systemprompt:** Keiner. Die Datei ist im Dashboard
  editierbar, aber keinem Task in `defaults.json` zugeordnet.
- **Runtimeassembly und Kontext:** Nicht vorhanden.
- **Parser/Consumer und Schema:** Nicht vorhanden.
- **Retry/Healing:** Nicht vorhanden.
- **Security/Authority:** Die Textregeln wären nur Defense in Depth; ohne
  Consumer entfalten sie keine Produktwirkung.
- **Qualitätsheuristiken:** Strukturierte Issue-Einschätzung, Risiko, Aufwand
  und offene Fragen; derzeit dormant.
- **Redundanzen:** Inhaltlich Überschneidungen mit Planning, aber keine
  Runtime-Redundanz.
- **Bestätigte Drift:** Keine Prompt-zu-Consumer-Drift, weil kein Consumer
  existiert. Die Architektur-Dokumentation ordnete die Datei fälschlich
  Planning zu.
- **Campaign-#859-Findings:** Keine.
- **Minimale Änderung:** Prompt unverändert lassen; Dokumentation auf
  „Prompt-Library, kein Runtime-Consumer“ korrigieren.

## 6. `docs_writer.md`

- **Tatsächlich geladener Systemprompt:** Keiner. Die Datei ist im Dashboard
  editierbar, aber keinem Task zugeordnet.
- **Runtimeassembly und Kontext:** Nicht vorhanden.
- **Parser/Consumer und Schema:** Nicht vorhanden; insbesondere konsumiert
  Implementation diese SEARCH/REPLACE-Ausgabe nicht unter einer
  `docs_writer`-Rolle.
- **Retry/Healing:** Nicht vorhanden.
- **Security/Authority:** Keine Produktwirkung ohne Consumer.
- **Qualitätsheuristiken:** Dokumentationsscope, belegtes Verhalten und
  knappe Kommentare; derzeit dormant.
- **Redundanzen:** Das enthaltene Patch-/Slice-Protokoll ähnelt dem
  Implementation-Protokoll, ist aber nicht verdrahtet.
- **Bestätigte Drift:** Keine aktive Prompt-zu-Consumer-Drift. Die
  Architektur-Dokumentation ordnete die Datei fälschlich Implementation zu.
- **Campaign-#859-Findings:** Keine.
- **Minimale Änderung:** Prompt unverändert lassen; Dokumentation korrigieren.

## 7. `log_analyst.md`

- **Tatsächlich geladener Systemprompt:** Die Factory lädt den Package-Default
  beim Aufbau der konfigurierten Route `evaluation`. Kein produktiver Workflow
  ruft diese Route anschließend auf.
- **Runtimeassembly und Kontext:** Nicht vorhanden. `EvaluationHandler`
  verarbeitet gebundene Gate-Observations deterministisch und besitzt keinen
  LLM-Port; Watch ruft den Prompt ebenfalls nicht auf.
- **Parser/Consumer und Schema:** Kein LLM-Consumer und kein Ausgabeschema.
  Evaluation validiert stattdessen `EvaluationObservationIdentity` und
  berechnet Scores aus strukturierter Evidence.
- **Retry/Healing:** Kein Promptaufruf, daher kein Prompt-Retry oder Healing.
- **Security/Authority:** Die deterministische Evaluation bleibt von dieser
  Promptdatei unabhängig.
- **Qualitätsheuristiken:** Logmuster und Empfehlungen im Text sind dormant.
- **Redundanzen:** Die konfigurierte Route ist ungenutzt; sie darf nicht als
  Watch-Integration dokumentiert werden.
- **Bestätigte Drift:** Keine aktive Prompt-zu-Consumer-Drift. Die
  Architektur-Dokumentation behauptete fälschlich eine Watch-Zuordnung.
- **Campaign-#859-Findings:** Keine.
- **Minimale Änderung:** Prompt und Konfiguration unverändert lassen;
  Dokumentation nennt die fehlende Runtime-Nutzung ausdrücklich.

## Prozess- und Finding-Klassifikation

Die Produktauthority ist konsistent:

```text
CodeGenerated → CreatePR → PRCreated → Review
```

`config/workflows/standard.json`, `README_technical.md`,
`RUNTIME_REFERENCE.md` und Capability `PROC-BOUND-REVIEW-MERGE` stimmen
überein. Die abweichende Q12/Q13-Formulierung ist eine externe
Qualification-/Runbook-Dokumentationslücke und wird von Demo-Issue #112
getragen. Der Produktworkflow wird dafür nicht geändert.

Attempt 18 bleibt terminal `FAIL`. Seine ursprüngliche ungültige
Reviewantwort ist nicht vorhanden; daher sind weder eine konkrete
Parserfehlerursache noch ein Validatorbug beweisbar. Die neue feste
Fehlerklasse schließt die Diagnoselücke für künftige Runs, ohne Rohantworten zu
persistieren. Die variablen Replay-Ergebnisse bleiben ein separater
Route-Suitability-Befund. #876 bleibt als Finding-Träger für die bestätigten
Kontext- und Diagnoselücken bestehen; es wird durch diesen Audit weder
geschlossen noch pauschal zum Validatorbug erklärt.

Campaign #859 bleibt pausiert, bis diese Änderungen den normalen CI- und
menschlichen Mergepfad durchlaufen haben und die externe Q12/Q13-Dokumentation
unter #112 eindeutig korrigiert ist. Dieser Audit startet keinen neuen
Rehearsal-Attempt, erstellt kein a26-Release und verändert PR #857 nicht.
