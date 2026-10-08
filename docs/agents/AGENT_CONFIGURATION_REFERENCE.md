# Agent Configuration Reference

Code-/Configabgleich: `main@97ea2754` (05.10.2026). Diese Referenz beschreibt
die vorhandenen Mechanismen; Liveverfügbarkeit und reale Abnahmen bleiben
eigene Evidence. Shipped defaults aus `config/llm/defaults.json`:

| Task | Provider / Modell | Prompt | max_tokens | timeout | temperature |
|---|---|---|---:|---:|---:|
| planning | OpenRouter / `nvidia/nemotron-3-super-120b-a12b:free` | `planner.md` | 4096 | 60 s | 0.3 |
| implementation | OpenRouter / `z-ai/glm-5.2:free` | `senior_python.md` | 8192 | 60 s | 0.1 |
| review | OpenRouter / `openai/gpt-oss-20b:free` | `reviewer.md` | 4096 | 60 s | 0.2 |
| healing | OpenRouter / `z-ai/glm-5.2:free` | `healer.md` | 4096 | 60 s | 0.2 |
| evaluation | OpenRouter / `nvidia/nemotron-nano-9b-v2:free` | `log_analyst.md` | 2048 | 60 s | Providerdefault |

Die `evaluation`-Zeile ist eine ausgelieferte Routingkonfiguration, **kein
Beleg fuer einen produktiven LLM-Aufruf**: `EvaluationHandler` konsumiert
gebundene Gate-/Provider-Observations und berechnet den Score ohne LLM-Port.
Aktuelle positive Providerproben fuer die tatsaechlich genutzten Aufgaben
bleiben dennoch subjectgebundene Operator-Evidence.

Alle Tasks aktivieren im shipped Profil den Kosten-/Overqualification-Hinweis
mit Margin 0,2. Das ist advisory. Runtime-/Operatoroverrides koennen die
effektive Route aendern; deshalb beweist diese Tabelle keine aktuelle externe
Verfuegbarkeit. Die effektive Route, Promptquelle, Timeout- und Outputgrenze
muessen pro Run aus der aktiven Config und ihrem Digest gelesen werden.

Fallbacks werden nicht als stiller Erfolgsweg interpretiert. Ein
Provider-/Modellwechsel aendert den Input. Day-/Night- oder Schedulelogik darf
nur wirken, wenn sie in der aktuellen Config aufgeloest und fuer den Run
gebunden ist; sie erteilt keine Approval-, Gate-, Release- oder Mergeauthority.

## Heutige weitere Defaults und wirksame Grenze

`config/llm/defaults.json` setzt global `reasoning_reserve=0`,
`response_size_limit_bytes=10485760`, einen 24-Stunden-Pricing-Cache,
Transportretry mit hoechstens drei Versuchen und einen Circuit Breaker nach
drei Fehlern mit 120 Sekunden Cooldown. Keiner der fuenf ausgelieferten
Task-Eintraege setzt einen eigenen `reasoning_reserve` oder `schedule`.
Damit ist ein Tages-/Nachtwechsel im shipped Profil **nicht aktiv**; der
Factory-Code kann ihn nur fuer eine tatsaechlich konfigurierte Task-Schedule
aufbauen. `config/llm.json` enthaelt `default.provider=deepseek` und
`default.fallbacks=[]`; die expliziten Task-Provider in der Tabelle oben
uebersteuern den Defaultprovider fuer diese fuenf Aufgaben. Ein leerer
Fallbackkatalog erlaubt keinen heimlichen Ersatz fuer eine unbrauchbare Route.

Die benannten Free-Modelle sind Konfigurationswerte, keine
Verfuegbarkeitszusage. Vor einem neuen E2E-Subject muss jede effektive Route
mit passender Authentisierung, Outputgrenze und realem Modell-Smoke geprueft
werden; besonders die historische Implementation-Truncation bei 8192 Tokens
ist kein durch Konfiguration allein erledigter Befund (#822/#859).


## Provider einrichten und gezielt wechseln

| Provider-ID | Adapter / Anschluss | Secretvariable |
|---|---|---|
| `claude` | native Anthropic-API | `ANTHROPIC_API_KEY` |
| `deepseek` | native DeepSeek-API | `DEEPSEEK_API_KEY` |
| `gemini` | native Gemini-API | `GEMINI_API_KEY` |
| `openai` | native OpenAI-API | `OPENAI_API_KEY` |
| `openrouter` | Gateway; Modell-ID einschließlich `vendor/` | `OPENROUTER_API_KEY` |
| `ollama` | lokaler Ollama-Endpunkt | kein Cloudkey |
| `lmstudio` | lokaler OpenAI-kompatibler LM-Studio-Endpunkt | kein Cloudkey |
| `manual` | vorhandene dateibasierte Request-/Response-Brücke | kein Cloudkey |

Die Tabelle nennt implementierte Adapter, keine pauschale Qualification aller
Provider oder beliebiger Modelle. `manual` ist auch keine Human Plan Approval
oder MANUAL-Kriterienabnahme; diese Workflowentscheidungen bleiben getrennt.

Keys gehören ausschließlich in die vorhandene deploymentlokale Secretquelle,
wie in [INSTALL](../INSTALL.md#12-accounts-credentials-und-kleinste-rechte)
beschrieben. Der Factory-Consumer liest sie über den Secrets-Port. Weder
`providers.json` noch Task-Konfiguration, Prompts, Screenshots, Logs oder
Receipts enthalten Keys. Lokale Container-Endpunkte müssen aus dem Container
erreichbar sein; `localhost` bezeichnet dessen eigenen Netzwerkraum.

Einrichtungsfolge für einen noch nicht gestarteten Subject:

1. Im vorhandenen Setup-Wizard den Provider mit seinem passenden Key und
   gegebenenfalls der lokalen URL konfigurieren; Verbindung separat prüfen.
2. In den LLM-Einstellungen den globalen Default und jede tatsächlich
   benötigte Taskroute überprüfen. Ein Providerwechsel im Default ersetzt
   keine ausdrücklich gesetzten Taskprovider.
3. Für eine Task im bestehenden Taskeditor Provider, native Modell-ID,
   Timeout, Outputgrenze und Prompt auswählen. Die Modellliste ist
   Metadatenhilfe: eine manuelle/gespeicherte unbekannte Modell-ID bleibt
   sichtbar. Sie beweist weder Verfügbarkeit noch Eignung beim nativen Vendor.
4. Änderungen nur im expliziten Setupmodus speichern. Ein bereits vorhandener
   Produktionsprozess lädt sie nicht heimlich hot. Nach kontrolliertem
   Neustart gespeicherte und effektive Configbindung sowie die tatsächlich
   konsumierten Routen vergleichen; erforderliche eigene Proben/Freshness und
   Freeze vor dem nächsten Subject durchführen.

Für den vorhandenen Dashboard-Setupmodus lautet die CLI-Form beispielsweise
`samuel --config /etc/samuel/config dashboard --configuration-mode setup`.
Pfad, Authentisierung und Compose-/Installationsmechanismus stammen aus dem
bestehenden [Installationsvertrag](../INSTALL.md); keine zweite Runtime als
Konfigurationsshortcut starten. Production ist der Default und read-only.
Ein Subject erhält während seiner Ausführung keinen Provider-, Prompt- oder
Configwechsel zur Reparatur.

## Configquelle und tatsächlich gewählte Route

Die vollständige Dateizuständigkeit steht in der bestehenden
[technischen Referenz](../README_technical.md#llm-konfiguration-zustaendigkeit-und-prioritaet):
`llm.json` liefert Default/Fallback und Providerparameter,
`llm/defaults.json` liefert Task-/Aufruf-/Scheduleparameter,
`llm/providers.json` liefert Setup-/Anzeigemetadaten. Der Providerkatalog ist
keine zweite Routingauthority.

Providerpriorität: aktives gültiges Task-Zeitfenster → expliziter Taskprovider
→ globales `SAMUEL_LLM_PROVIDER` → `llm.json::default.provider`.
Modellpriorität: Schedule-Modell → Task-Modell → Provider-Modell in `llm.json`
→ Adapterdefault. Das ist pro Feld und vorhandenem Override zu lesen; ein
Eintrag in `providers.json` ersetzt keine dieser Laufzeitwerte.

Ein optionales `tasks.<task>.schedule` in `llm/defaults.json` verwendet
`active`, `from`, `to`, `provider` und `model`, zum Beispiel ein ausdrücklich
gewähltes Fenster `22:00`–`06:00`. Das Fenster folgt der lokalen Zeit des
Runtimeprozesses, unterstützt Mitternachtsübergang und wirkt außerhalb des
Fensters nicht. Ein ungültiges/inaktives Fenster aktiviert keine Nachtroute.
Task-/Scheduleänderungen sind keine Approval- oder Gateauthority; die shipped
Konfiguration oben enthält keinen Schedule und keine Kostenersparniszusage.

Die geordnete Fallbackliste steht ausschließlich in
`llm.json::default.fallbacks`. Nur explizit konfigurierte Adapter werden nach
einem Fehler versucht; ein erfolgreicher Primäraufruf erzeugt keinen zweiten
Call. Ein erschöpftes Workflowbudget wird nicht per Fallback umgangen. Die
bestehende Metering-/Auditprojektion meldet den tatsächlich verwendeten
Provider und Fallback. Eine konfigurierte Primärroute ist daher von der
wirklich konsumierten Route zu unterscheiden. Health, Benchmark oder ein
Connection-Test schalten keine Ersatzroute frei.

## Timeout, Output und Reasoning

`timeout`, `max_tokens`, `temperature` und `reasoning_reserve` werden aus dem
wirksamen Task-/Schedule-/Defaultprofil gelesen. `max_tokens` ist die
konfigurierte Grenze für sichtbaren Inhalt, keine Zusage vollständiger
Antworten. Das separate kumulative `workflow_budget.token_limit` begrenzt
Workflowadmission; unbekannte Usage bleibt konservativ gebunden.

Ein positiver `reasoning_reserve` wird als zusätzlicher expliziter
Reasoningbudgetanteil nur bei einem erkannten Reasoningmodell über den
OpenRouter-Vertrag weitergegeben. Andere Provider erhalten dadurch keine
vorgetäuschte Reasoningreservierung. Die effektiven Content-/Gesamtlimits und
die Quelle der Erkennung sind von einem bloßen Modellnamen zu unterscheiden.
Eine abgeschnittene oder parserungültige Antwort bleibt ein Fehler, auch wenn
HTTP erfolgreich war. Transportretry, Planning-Contractretry und Healing
haben unterschiedliche Grenzen; Details stehen in der
[Promptreference](AGENT_PROMPTS_AND_INSTRUCTIONS.md).

## Benchmark, Katalog und Anzeige verstehen

Die bestehenden Metadatenquellen sind
`llm.json::openrouter.models_url` und `openrouter.benchmarks_url`.
Standardmäßig liest der Refresh `/api/v1/models` und `/api/v1/benchmarks` von
OpenRouter. Der Benchmarkrequest verwendet den dafür vorgesehenen
OpenRouter-Key; eine fehlende Berechtigung oder fehlerhafte Benchmarkantwort
macht einen erfolgreichen Modell-/Preisrefresh nicht zum Benchmark-PASS.
Diese URLs beeinflussen weder Completion-Endpunkt noch Routing.

`coding_index`, `intelligence_index` und `agentic_index` sind die von der
Quelle gelieferten Modellkennzahlen. S.A.M.U.E.L. berechnet daraus keinen
lokalen Funktionstest und erfindet keine Prozentnormierung. Implementation
und Healing vergleichen `coding_index`; Planning und Review vergleichen
`intelligence_index`. Die konfigurierte Evaluation-Zuordnung ist weiterhin
kein produktiver Evaluation-LLM-Consumer.

`llm/defaults.json::benchmark_thresholds` setzt die taskbezogene Schwelle
(shipped jeweils 50). Die Anzeige bedeutet:

| Status | Bedeutung im bestehenden Vergleich |
|---|---|
| `no_data` | kein passender Kennwert in den verfügbaren Metadaten; kein behauptetes FAIL oder PASS |
| `below_threshold` | Kennwert liegt unter der konfigurierten Taskschwelle |
| `suitable` | Kennwert erfüllt diese Schwelle; keine Workflowfreigabe |
| `overqualified` | Kennwert erreicht zusätzlich den relativen Advisory-Abstand |

Bei Schwelle 50 und Margin 0,2 beginnt der Advisory-Abstand bei 60. Das ist
keine empirisch belegte Überqualifikation für den konkreten Auftrag.
`cost_advisory_enabled` steuert nur den bestehenden Preishinweis. Dieser
vergleicht Modelle anhand gleicher Taskschwelle und vergleichbarer Prompt-/
Completionpreise; er wechselt keine Route und ersetzt keine Qualitätsprüfung.
Benchmark, Preis, Score und Advisory besitzen **keine Approval-, Gate-,
Qualification-, Release- oder Mergeauthority**.

Der gemeinsame Cache liegt standardmäßig unter `data/openrouter_models.json`,
bindet Quell-URLs/Generation und verwendet `pricing_cache_hours` (shipped 24).
Das Dashboard zeigt Alter, Fehler und Refreshbedarf. Fehlende Benchmarkdaten
bleiben `no_data`; Parameterzahl und Namensheuristik ersetzen keinen fehlenden
Benchmark. Vorhandene Kennwerte aus einem veralteten Cache können weiterhin
einen Advisory-Vergleich liefern. Cachealter und Refreshbedarf müssen deshalb
mitgelesen werden: Dieser Vergleich ist kein aktueller Eignungsnachweis.
Die separate OpenRouter-Verfügbarkeitsanzeige bleibt bei fehlendem oder
veraltetem Cache `unknown`; nur ein frischer Katalog liefert `available` oder
`missing` für die exakte Modell-ID. Cloudlisten können Gatewaymetadaten
verwenden und sind damit kein Beweis für eine native Vendor-Modellliste.
Ollama/LM Studio verwenden ihren bestehenden lokalen Discoverypfad. Ein leerer
Katalog löscht keine konfigurierte Modell-ID und ist allein kein Beleg, dass
ein tatsächlich erfolgreicher Modellcall nicht verfügbar war.

Der vorhandene Operatorpfad für Metadatenrefresh heißt
`samuel --config /etc/samuel/config refresh-pricing`; alternativ der bestehende
Dashboard-Button „Modell- und Benchmarkdaten aktualisieren“. Refresh ist ein
expliziter externer Metadatenzugriff, keine neue Providerqualifikation.

## Passive Diagnose, aktive Probe und Workflowevidence

`samuel doctor` prüft seine dokumentierten Installation-/SCM-/Configgrenzen.
`samuel health` und passive Dashboard-Health-GETs starten keine Completion.
`Test-Connection` beziehungsweise der aktive Dashboard-Self-Check sind
getrennte Providerproben und benötigen die entsprechende Permission
`RUN_PROVIDER_PROBES`. Ein erfolgreicher Transporttest ist kein Beleg, dass
ein ganzer Plan/Patch/Review-/Healingvertrag erfüllt wurde.

Vor Workflowbeginn werden die vier wirklich konsumierten LLM-Taskrouten
`planning`, `implementation`, `review`, `healing` mit ihrer eigenen effektiven
Bindung geprüft. Die vorhandene konfigurierte `evaluation`-Zeile kann in
Statusflächen auftauchen, wird vom produktiven `EvaluationHandler` aber nicht
als LLM-Task aufgerufen. Native Provider-/Contractsmokes, Configfreeze und
Qualification behalten ihren vorhandenen Operatorvertrag und ihre Freshness.
Eine Probe verlängert keine alte Evidence und bewirkt weder Planapproval noch
Workflowstart. Die noch ausstehenden realen Abnahmen bleiben in #962.
