# Agent Prompts and Instructions

Stand: `main@41340e75`. Productauthority besitzen nur versionierter Code,
ausgelieferte Config und akzeptierte Vertraege. Lokale Handoff-, Qualification-
oder Coding-Agent-Anweisungen sind Operatorhilfe und keine Runtimeauthority.

## Promptinventar

| Datei | shipped Taskbindung | Consumer-/Formatvertrag |
|---|---|---|
| `samuel/core/prompts/planner.md` | `planning` | Planlayout, kanonischer Scope und Acceptance-Contract; Parser und Precheck in Planning |
| `senior_python.md` | `implementation` | strukturierte Patchoperationen; Implementation-Parser, Scope-/Syntax-/Riskchecks |
| `reviewer.md` | `review` | genau ein gebundenes Review-JSON; `review_contract.py` validiert closed schema und Bindings |
| `healer.md` | `healing` | genau ein begrenzter gebundener Reparaturversuch; Candidate-/Contractbindung bleibt |
| `log_analyst.md` | in `config/llm/defaults.json` fuer `evaluation` konfiguriert, aber derzeit kein produktiver LLM-Consumer im `EvaluationHandler` | Library-/Routing-Konfiguration; Score- und Gate-Observation bleiben deterministisch, keine Mergeauthority |
| `analyst.md` | ungebundene Librarydatei | verfuegbar fuer explizite Operatorprofile, derzeit keine shipped Taskbindung |
| `docs_writer.md` | ungebundene Librarydatei | verfuegbar fuer explizite Operatorprofile, derzeit keine shipped Taskbindung |

Prompttexte werden hier nicht dupliziert. Quelle, Digest und effektive Auswahl
muessen aus dem exakten Config-/Productstand ermittelt werden.

## Aufloesung

`system_prompt_by_provider` kann zuerst den Dateinamen fuer den aktiven
Provider waehlen. Danach gilt die feste Reihenfolge:

1. `config/llm/prompts/model/<sanitized-model>/<name>`;
2. `config/llm/prompts/provider/<sanitized-provider>/<name>`;
3. `config/llm/prompts/<name>`;
4. Package-Default `samuel/core/prompts/<name>`.

Provider-/Modellteile werden auf ein sicheres Pfadsegment reduziert. Ein
fehlender Prompt wird sichtbar geloggt und als leer geliefert; der jeweilige
Task-/Guardvertrag entscheidet danach fail-closed. Dashboardwrites sind nur im
Setupmodus zulaessig; Production bleibt read-only und laedt gespeicherte
Aenderungen nicht heimlich hot.

## Dynamische Runtimeanteile

Die Handler ergaenzen Issue/Plan, gebundene Source-/Base-/Candidateidentitaet,
Repositorykontext, Runner- und Selectorgrammar, Retrydiagnosen,
Acceptance-/Reviewbindings und Scope-/Riskmarker. Diese Teile gehoeren zum
effektiven Prompt und koennen nicht allein durch den statischen Markdownprompt
bewertet werden. Planning besitzt genau den vertraglich vorgesehenen
Contractretry; Implementation besitzt begrenzte Patch-/Slice-Runden; Healing
bleibt auf einen gebundenen Versuch begrenzt. Provider-Transportretry ist davon
getrennt.

## Arbeitsanweisungen im Checkout

Im Repository existiert kein `AGENTS.md`, keine Cursor-Regel und keine
versionierte Copilot-Instructions-Datei. `CONTRIBUTING.md`,
`docs/OPERATING_RULES.md`, Security-/Release-/Qualification-Vertraege und die
CI sind die versionierte Arbeitsgrundlage. Lokale Dateien wie
`SAMUEL_WORKING_DECISIONS_v8.md`, Challengepakete und Handoffs sind
Provenienz/Operatorhilfe und werden ueber `docs/audits/INDEX.md` klassifiziert.

Keine Prompt-, Task-, Config-, Retry- oder Parsersemantik wurde durch diesen
Housekeeping-Auftrag veraendert.

## Verifizierte Autoritaets- und Retrygrenzen

Die sieben Dateien unter `samuel/core/prompts/` sind Package-Guidance. Die
fuenf ausgelieferten Task-Konfigurationen und ihre Defaults stehen in
`AGENT_CONFIGURATION_REFERENCE.md`; `analyst.md` und `docs_writer.md`
sind derzeit nicht in `config/llm/defaults.json::tasks` referenziert.
`samuel/adapters/llm/factory.py` baut fuer Task-Overrides eigene Providerketten
und aktiviert einen Schedule-Wrapper nur, wenn mindestens ein Task ein
`schedule`-Objekt besitzt. Das shipped Profil besitzt keines.

`samuel/adapters/llm/prompts.py` und die Task-/Handler-Tests pruefen
Provider-/Modell-/Generic-/Package-Aufloesung und sichere Pfadsegmente.
Planning, Implementation, Review, Healing und Evaluation fuegen ihre
jeweiligen Laufzeitdaten hinzu; der statische Package-Text alleine kann weder
Planapproval noch Candidate-, Gate-, Review- oder Mergeauthority herstellen.
Transportretry (shipped hoechstens drei Versuche) ist von fachlichem
Plan-Contract-Retry, begrenzten Implementation-Runden und einem gebundenen
Healingversuch getrennt. Erschoepfung ist ein sichtbarer Fehler, kein
Fallback-PASS. Fuer heutige Parser-/Consumer-Details bleiben der Code, die
ausgefuehrten Regressionen und `README_technical.md` die pruefbaren Quellen.
