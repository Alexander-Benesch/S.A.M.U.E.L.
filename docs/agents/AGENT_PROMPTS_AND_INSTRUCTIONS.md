# Agent Prompts and Instructions

Code-/Consumerabgleich: `main@97ea2754` (05.10.2026). Productauthority besitzen nur versionierter Code,
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

Provider-/Modellteile werden auf ein sicheres Pfadsegment reduziert. Die
Kaskade überspringt fehlende, nicht lesbare und nicht als UTF-8 decodierbare
Dateien; der Dashboard-Quellenindikator folgt derselben lesbaren Auswahl.
Eine explizite Scope-Abfrage liefert dagegen nur diesen Operatorlayer, ohne
Fallback auf andere Profile oder das Package. Fehlt dort eine lesbare Datei,
sind Inhalt und Quellenindikator leer bzw. `none`. Fehlt in der gesamten
Kaskade ein lesbarer Prompt, wird dies sichtbar geloggt und als leer geliefert;
der jeweilige Task-/Guardvertrag entscheidet danach fail-closed. Dashboardwrites sind nur im
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

Der Coding-Agent-Einstieg steht in
[`.claude/CLAUDE.md`](../../.claude/CLAUDE.md#vor-der-ersten-mutation), mit
Verweis aus `CONTRIBUTING.md`. Diese Entwicklungsanweisungen sind von den
oben beschriebenen Product-Runtime-Rollen getrennt.

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
Planning, Implementation, Review und Healing fuegen ihre jeweiligen
LLM-Laufzeitdaten hinzu. Evaluation konsumiert gebundene Observations ohne
produktiven LLM-Prompt. Der statische Package-Text alleine kann weder
Planapproval noch Candidate-, Gate-, Review- oder Mergeauthority herstellen.
Transportretry (shipped hoechstens drei Versuche) ist von fachlichem
Plan-Contract-Retry, begrenzten Implementation-Runden und einem gebundenen
Healingversuch getrennt. Erschoepfung ist ein sichtbarer Fehler, kein
Fallback-PASS. Fuer heutige Parser-/Consumer-Details bleiben der Code, die
ausgefuehrten Regressionen und `README_technical.md` die pruefbaren Quellen.


## Vorhandene Operatorprofile nutzen

Eine abweichende Guidance wird als UTF-8-Datei im oben beschriebenen
vorhandenen Modell-, Provider- oder Genericlayer abgelegt. Der Task verweist
mit `system_prompt` beziehungsweise `system_prompt_by_provider` auf den
Dateinamen; die Quellenanzeige folgt demselben Resolver. Das bestehende
Dashboard-Librarymodal bearbeitet den Genericlayer. Ein Providerwechsel kann
somit auch die effektive Promptquelle ändern und muss vor dem neuen Subject
zusammen mit Route/Configdigest geprüft werden.

Guidance darf Sprache oder Arbeitsbeschreibung schärfen, ersetzt aber nicht
die vom Handler gebundene Plan-/Selector-/Patch-/Reviewgrammar. Ein freier
Operatortext kann keinen Scope erweitern, Gate umgehen oder eine Humanfreigabe
herstellen. Ein neues versioniertes Workerprofil mit eigener Qualification-
oder Freezeauthority ist durch diese Dateikaskade nicht implementiert; der
verbleibende Designscope bleibt #878.

Zum Rückwechsel wird nur vor einem neuen Subject der betreffende Operatorlayer
entfernt oder dessen Taskbindung im Setup korrigiert. Danach effektive Quelle,
Neustart und neue Config-/Probenbindung prüfen. Der alte fehlgeschlagene
Subject wird nicht durch Promptänderung repariert und behält seine Evidence.
