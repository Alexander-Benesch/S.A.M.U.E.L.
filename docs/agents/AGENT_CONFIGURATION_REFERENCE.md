# Agent Configuration Reference

Shipped defaults aus `config/llm/defaults.json` auf `41340e75`:

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
