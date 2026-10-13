# Self-Mode Prompt-Quality — Entscheidungs-Memo

**Issue:** #259
**Stand:** 2026-05-01
**Autor:** Claude (Manual-LLM-Adapter, Self-Audit)

---

## 1. Problem-Definition

Samuel's Self-Mode generiert Implementation-Patches durch:
1. Skeleton-Builder + relevant_files + grep + module_context bauen einen LLM-Prompt
2. LLM-Adapter (DeepSeek/Claude API ODER Manual-Mode/Mensch) erzeugt SEARCH/REPLACE-Patches
3. Patch-Parser appliziert die Patches auf das Working-Tree
4. AC-Verifier verifiziert das Ergebnis

**Bei Manual-Mode-Tests bisher (Claude-Code Konversation als LLM-Adapter):** ich kann
zusätzlich via Read-Tool die Roh-Datei lesen, um meine Patches gegen exakte Whitespace-
und Indent-Verhältnisse zu verifizieren. Das ist eine **Information-Asymmetrie** zu API-
LLMs (DeepSeek/Claude/GPT), die nur den vom Samuel zusammengestellten Prompt sehen.

**Konsequenz:** Self-Mode-Erfolgsraten unter Manual-LLM sind eine Obergrenze. API-LLM-
Performance wird in der Praxis schlechter sein, mit mehr Patch-Retry-Rounds und
EvalFailed-Wiederholungen.

Diese Memo bewertet Optionen, die Lücke zu schließen.

---

## 2. Live-Auswertung der letzten 9 Self-Mode-Runs

Daten aus `data/logs/agent_2026-04-*.jsonl` und `agent_2026-05-01.jsonl`. Wo mehrere
EvalCompleted/Failed pro Issue, wurde der ERSTE genommen (echter Self-Mode-Run, keine
synthetischen Folgetests).

| Issue | Plan-Retries | Score-Verlauf | Patch-Rounds | Eval-Score | EvalCompleted | Gate-Fail | PR | Tokens IN/OUT |
|---|---|---|---|---|---|---|---|---|
| #176 | 0 | - | n/a | 1.0 | ✓ | 4 | ✓ | 20560/600 |
| #193 | 0 | - | n/a | 0.067 | ✗ | 0 | ✗ | 15200/3100 |
| #219 | 0 | - | 1 | 1.0 | ✓ | 3 | ✗ | 12211/1120 |
| #240 | 0 | - | 1 | 1.0 | ✓ | 1 | ✓ | 71100/20700 |
| #241 | 0 | - | 1 | 1.0 | ✓ | 0 | ✓ | 20700/2300 |
| #243 | 0 | - | 1 | 1.0 | ✓ | 1 | ✗ | 15700/3350 |
| #246 | 1 | 60→100 | **3** | 1.0 | ✓ | 3 | ✗ | 86000/10400 |
| #251 | 0 | - | n/a | 0.7 | ✗ | 0 | ✗ | 25700/4450 |
| #254 | 1 | 75→100 | 1 | 1.0 | ✓ | 0 | ✓ | 14200/2950 |

**Summen:**
- 9 Self-Mode-Runs total (alle mit Manual-LLM = Claude-Konversation)
- 7/9 EvalCompleted (78%)
- 5/9 PR direkt erstellt aus Self-Mode (56%)
- 2 Plan-Retries (#246, #254)
- 1 Run mit 3 Patch-Rounds (#246)

---

## 3. Failure-Patterns mit Diagnose

### Pattern A: Plan-Validator Score < 80 → PlanRetry

**Vorkommen:** 2/9 Runs (#246: 60→100, #254: 75→100)

**Ursachen:**
- **#246:** `Keine Akzeptanzkriterien im Plan` — meine erste Plan-Version hatte ACs am Ende, der Validator suchte aber `- [ ]` literal und fand sie nicht in der gewünschten Form. Retry mit AC-Block am Anfang → Score 100.
- **#254:** `Verbotene Pfade referenziert: venv/, .venv` — der Validator sucht in Backtick-Refs nach BAD_PATHS. Mein Plan hatte `\`.venv/bin/python\`` in Backticks. Retry ohne Backtick-Path → Score 100.

**Beobachtung:** Plan-Validator funktioniert wie gewollt. Retry-Loop fängt Fehler ab.
Token-Kosten: ~+50% pro Retry-Round.

### Pattern B: Patch-Round-Retry (SEARCH not found)

**Vorkommen:** 1/9 Runs (#246, 3 Rounds)

**Ursachen (alle in #246):**
1. **HTML-Strip-Bypass:** `SanitizingLLMAdapter.strip_html` zerstörte HTML-Patches. Round 1: 3 server.py-Patches scheiterten mit "SEARCH not found" weil `<h3>`-Tags weg waren. Round 2: Encoding-Workaround mit `&lt;`/`&gt;` → erfolgreich.
2. **Whitespace-Drift:** Selbst nach HTML-Encoding gab es Indentation-Mismatches zwischen Prompt-Excerpt (mit `nnn |`-Präfix) und der Roh-Datei.

**Mitigation in Praxis:** ich (Manual-LLM) habe Read-Tool verwendet um Roh-Datei zu sehen.
**Ein API-LLM hätte das nicht.**

Token-Kosten: ~3x für 3 Rounds (~86k Tokens für #246 vs ~25k für vergleichbares #251).

### Pattern C: EvalFailed durch Tooling-Bug

**Vorkommen:** 2/9 Runs (#193 Score 0.067, #251 Score 0.7)

**Ursachen:**
- **#193:** alte Implementation, baseline 0.5 — wahrscheinlich nicht-Self-Mode.
- **#251:** AC-Verifier konnte Tests nicht ausführen (`[Errno 2] No such file or directory: 'pytest'`). Das war der `sys.executable`-PATH-Bug, gefixt in #254.

**Diagnose:** keine LLM-/Prompt-Frage, sondern Tooling. Behoben.

### Pattern D: Gate-Failures bei erfolgreichem Eval

**Vorkommen:** 4/9 Runs (#176, #219, #243, #246)

**Diagnose:**
- #176, #219, #243: Gate 8 false-positive vor #243-Fix (cross-slice tracking ungenau)
- #246: Gate 8 String-Fixture-Bypass (Pflaster, getrackt #250)

**Konsequenz:** PR wurde nicht direkt erstellt, manuelle Reparatur nötig.

### Pattern E: Implementation-Lücke trotz Score 1.0

**Vorkommen:** 1/9 entdeckt im Audit (#246, #251 nachträglich)

**Diagnose:** Plan deckte nicht alle Anforderungen ab → Self-Mode lieferte was im Plan stand, aber nicht was der Issue-Body forderte. Beispiel:
- #246: `get_security_overview` wurde nicht im Plan referenziert → fehlte in Implementation. Erst durch User-Beobachtung im Dashboard ("1% OWASP") aufgefallen.
- #251: ähnlich — OWASP-Symmetrie nur teilweise umgesetzt, weil Plan-Excerpt der Funktionen unvollständig war.

**Konsequenz:** Score 1.0 ≠ vollständige Implementation. AC-Verifier prüft nur was die ACs vorgeben, nicht ob die ACs ausreichend sind.

---

## 4. Lösungs-Varianten

### Variante A — Prompt-Verifier-LLM (Second-Opinion-LLM vor Implementation)

Vor dem Implementation-LLM-Call läuft ein billiger Verifier-LLM über den generierten
Prompt + Plan. Verifiziert:

- Stimmen die Zeilennummern im Excerpt mit den vorhandenen Symbolen überein?
- Sind alle in der Plan-AC referenzierten Funktionen im Skeleton enthalten?
- Hat der Excerpt genug Kontext (vorhergehende/nachfolgende Zeilen) um SEARCH eindeutig zu machen?
- Werden bekannte Sanitizer-Stolperfallen (HTML, Sonderzeichen) im Prompt erwähnt?
- Sind die Plan-ACs ausreichend für den Issue-Scope (gegen Pattern E)?

**Pro:**
- Strukturelle Erkennung von Prompt-Mangel und AC-Lücken vor dem teuren Implementation-Call
- Kann über Issues hinweg lernen ("Files mit DASHBOARD_HTML brauchen Encoding-Hinweis")
- Quality-Gate vor LLM-Latenz/Cost
- Adressiert Pattern A (besseres Plan-Feedback) und teilweise Pattern E (AC-Lücken-Erkennung)

**Con:**
- ~20-40% Token-Overhead pro Issue
- Verifier-LLM kann selber halluzinieren ("Excerpt ist ok" obwohl falsch)
- Latenz-Erhöhung (sequenzieller Call)
- Architektur-Änderung (neuer Slice oder Middleware)

### Variante B — Stärkerer Implementation-LLM

Statt Verifier-Layer: Claude Opus statt Claude Sonnet/Haiku, GPT-4 statt GPT-3.5.

**Pro:**
- Keine Architektur-Änderung
- Single-Call, niedrige Latenz
- Capable-Model kann auch komplexere Implementation generieren
- Markt-Trend (Modelle werden besser, Kosten sinken)

**Con:**
- ~3-5x höhere Per-Token-Kosten direkt im Implementation-Call
- Löst die Prompt-Qualität selbst NICHT (nur kompensiert)
- Bei wirklich kaputten Excerpts (z.B. fehlende Zeilen) hilft auch GPT-4 nicht
- Vendor-Lock-In-Risiko

### Variante C — Reactive Retry mit Prompt-Refinement

Aktueller Retry-Mechanismus erweitert: bei `SEARCH not found` schickt Samuel einen 2.
Prompt mit größeren Code-Excerpts. Nach 2-3 Rounds eskaliert auf stärkere LLM ODER
manuellen Eingriff.

**Pro:**
- Kein Upfront-Cost
- Nur für schwierige Issues teurer
- Bestehender llm_loop kann erweitert werden
- Adressiert Pattern B direkt

**Con:**
- Reaktiv statt präventiv
- 3 Rounds Retry = 3x Token-Cost im Worst-Case (live in #246 gemessen)
- Verzögert Eval

### Variante D — Strukturell besseren Context-Builder

Skeleton/relevant_files-Builder werden so erweitert, dass sie **vollständige Funktions-
Bodies** liefern statt Excerpte. Mehr Kontext, weniger Halluzinations-Spielraum.

**Pro:**
- Keine LLM-Calls dazu
- Deterministisch, nicht-probabilistisch
- Adressiert Wurzel statt Symptom
- Adressiert Pattern B + E direkt

**Con:**
- Sprengt Token-Budget bei großen Files (`samuel/server.py` hat 800+ Zeilen,
  `DASHBOARD_HTML` allein ~700)
- Gilt nicht für Cross-File-Pattern wie Sanitizer-Stolperfallen
- Mehr Kontext != bessere Patches (zu viel Rauschen)

### Variante E — Tool-Use im Implementation-LLM (Cursor/Aider-Modus)

LLM darf mid-conversation Tools rufen: `read_file`, `grep`, `list_symbols`. Wenn er
unsicher ist, holt er sich die Information statt zu raten.

**Pro:**
- Closeste Annäherung an mein (manual-LLM) Verhalten
- LLM holt nur Info die er BRAUCHT, nicht alles up-front
- Skaliert auf große Codebasen
- Adressiert ALLE Patterns (A-E)

**Con:**
- Massive Architektur-Änderung (Patch-Loop wird Tool-Loop)
- Verliert Determinismus (jeder Run sieht anders aus)
- Loop-Detection notwendig (LLM könnte unendlich Files lesen)
- Provider-Support unterschiedlich (Anthropic stark, andere schwächer)

---

## 5. Token-Cost-Modell

Annahmen:
- Issue-Komplexität wie #246 (mittlere Größe, mehrere Files)
- Prompt-Größe: ~30k Token (basierend auf live-gemessenen 86k bei 3 Rounds = ~28k pro Round)
- Response: ~5k Token (Plan + Implementation aggregated)

Pricing-Stand 2026 (DeepSeek-Reasoner als Baseline, indikative API-Preise):

| Modell | Input/1M | Output/1M | Pro Issue (35k tok ≈ 30k+5k) |
|---|---|---|---|
| DeepSeek-Reasoner | $0.55 | $2.19 | ~$0.03 |
| Claude Sonnet 4.6 | $3.00 | $15.00 | ~$0.16 |
| Claude Opus 4.7 | $15.00 | $75.00 | ~$0.83 |
| GPT-4 Turbo | $10.00 | $30.00 | ~$0.45 |

Verglichen pro Variante (estimate):

| Variante | Tokens pro Issue | Erfolgs-Rate (Schätzung) | Effective Cost (Sonnet-Baseline) |
|---|---|---|---|
| **Status quo** (Sonnet, 1-3 Rounds) | 35-100k | 60-70% | 1.5x |
| **A** (Verifier-Sonnet + Sonnet) | 50k | 80-85% | 1.7x |
| **B** (Opus single-call) | 35k | 75-85% | **5.2x** |
| **C** (Retry mit größerem Prompt) | 35-150k | 80-90% | 1.5-3.5x |
| **D** (mehr Kontext upfront) | 60k | 70-80% | 1.7x |
| **E** (Tool-Loop, Anthropic) | 20-80k | 90-95% | 1.5-3x |

**Kombinierbar:** A+D (60k + Verifier auf größerem Prompt = 80k), oder B+C (Opus mit Retry).

---

## 6. Empfehlung

**Stufenmodell für SAMUEL Phase 2:**

### Stufe 1 — Sofortmaßnahme (Phase 2 Start)
**Variante D + Plan-Validator-Stärkung** — kein neues LLM-System, deterministisch:

- Skeleton-Builder erweitern: bei Klassen die in der Plan-AC erwähnt werden, FULL function bodies (statt nur Signatur).
- relevant_files: bei Files die in `[DIFF]`-ACs auftauchen, vollen Datei-Inhalt unter Token-Budget.
- Plan-Validator: erweitern um "Hat der Plan ACs für jede in den Issue-Body erwähnte Datei?" (gegen Pattern E).

Token-Kosten: ~+30%. Erfolgs-Rate-Lift: ~+15-20% erwartbar.

### Stufe 2 — Reactive (parallel)
**Variante C** — bestehende llm_loop-Round-Retry-Mechanik verbessern:

- Bei `SEARCH not found`: Prompt-Refresh mit ±20 Zeilen mehr Kontext um die fehlgeschlagene Stelle.
- Bei 3+ Rounds ohne Progress: WorkflowBlocked statt Endlos-Retry.

### Stufe 3 — A/B-Testing (Phase 2 Mitte)
**Variante A vs B testen** in Staging-Umgebung:

- 10 Issues mit Variante A (Verifier-LLM)
- 10 Issues mit Variante B (Opus)
- Vergleich: Effective Cost pro erfolgreich geschlossenem Issue
- Entscheiden welcher mehr ROI bringt für SAMUEL-Use-Case

### Stufe 4 — Langfristig
**Variante E (Tool-Use)** — sobald:

- Provider-API stabil (Anthropic Tool-Use ist live, OpenAI Function-Calling auch)
- Self-Mode-Workflow Tool-Loop tolerieren kann (Loop-Detection, Cost-Cap)
- Stufe 1-3 Daten zeigen wo der ROI am höchsten ist

---

## 7. Risiken

### R1: Manual-LLM-Performance ist falsche Baseline
**Live-belegt durch dieses Memo** — meine 7/9 Erfolg ist nicht repräsentativ für API-LLMs.
A/B-Test in Stufe 3 muss mit echtem API-LLM laufen.

### R2: Verifier-LLM-Halluzination
Variante A: der Verifier-LLM kann selber falsch-positive abgeben ("Excerpt ist ok"
obwohl er ist es nicht). Mitigation: Verifier-Output ist deterministisch verifiziert
(z.B. Zeilen-Match gegen Skeleton).

### R3: Tool-Loop-Cost-Explosion
Variante E: LLM könnte ineffizient `read_file` für jede Datei rufen. Mitigation:
Cost-Cap pro Issue + Loop-Detection (gleiches File 2x lesen → Warning).

### R4: Determinismus-Verlust
Variante E: bei nicht-deterministischer Tool-Reihenfolge sind Test-Vergleiche schwer.
Mitigation: Tool-Calls + Responses ins Audit-Log.

---

## 8. Akzeptanzkriterien (für #259-Closure)

- [x] [EXISTS] docs/SELF_MODE_PROMPT_QUALITY_MEMO.md
- [x] [GREP] "Variante A" / "Variante B" / "Variante D"
- [x] Live-Auswertung der letzten 9 Self-Mode-Runs
- [x] Token-Cost-Modell mit Provider-Pricing
- [x] Empfehlung mit Stufenmodell

---

## 9. Folge-Issues (zu erstellen wenn dieses Memo akzeptiert)

- **A1 (Stufe 1)**: Skeleton-Builder erweitern: full function bodies bei Plan-AC-Match
- **A2 (Stufe 1)**: Plan-Validator: AC-Coverage-Check gegen Issue-Body
- **A3 (Stufe 2)**: llm_loop: Prompt-Refresh bei SEARCH-Failure mit erweitertem Kontext
- **A4 (Stufe 3)**: A/B-Test-Framework für Variante A vs B
- **A5 (Stufe 4, Phase 3)**: Tool-Use-LLM-Adapter (Variante E)

Erst nach User-Akzeptanz dieses Memos.
