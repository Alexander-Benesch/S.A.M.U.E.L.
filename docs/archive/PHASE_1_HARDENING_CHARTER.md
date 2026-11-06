# Phase 1 — Workflow-Hardening Charter

**Verbindlich für alle Issues #236 (X4), #237 (X1), #238 (X2), #239 (X3).**
**Stand:** 2026-04-30

Dieser Charter definiert die nicht-verhandelbaren Anforderungen für die Phase-1-Hardening-Welle. Jede Implementierung dieser Issues MUSS allen Punkten genügen. Self-Mode-LLM und manuelle Implementierungen sind gleichermaßen daran gebunden.

**Phase-2+-Fortsetzung:** Die operativen Lessons aus Phase 1 sind in `docs/OPERATING_RULES.md` zu einem dauerhaften Regelwerk konsolidiert. Die Charter-§§1.1–1.5 bleiben dort als Constraints weiterhin gültig.

---

## 0. Scope & Reihenfolge

| # | Titel | Reihenfolge |
|---|---|---|
| #243 | Gate 8 per-Datei-Diff-Tracking statt globaler Walk | **X-2 (1.)** PR-Gate-Validität |
| #241 | Implementation-Handler: kein vorzeitiger main-Checkout | X-1 (2.) ✅ gemergt |
| #240 | TEST-Tag-Handler sprachneutral | X0 (3.) |
| #236 | AC-Verifier Tag-Argument-Extraktion strukturiert | X4 (4.) |
| #237 | Plan-Stage Code-Kontext (Skeleton + relevant_files + grep) | X1 (5.) |
| #238 | Plan-Pre-Check härten (Skeleton-Validation + AC-Dry-Run) | X2 (6.) |
| #239 | EvalFailed-Retry-Loop (3 Runden + No-Improvement-Stop) | X3 (7.) |

**Begründung X-2 als 1.:** `samuel/slices/pr_gates/gates.py:93-120` (Gate 8 `slice_gate`) walked die GESAMTE diff einmal und schreibt jede `+from samuel.slices.X import`-Zeile JEDEM `slice_file` in `changed_files` zu — false-positive für globale Tests, die legitim aus mehreren Slices importieren. Live-Beleg: #240-Run vom 2026-04-30 — Score 1.0, EvalCompleted, Gate 8 blockt CreatePR fälschlich. Charter §1.4-Pflicht-Test (`tests/test_event_mapping_complete.py`) muss mehrere Slices importieren, was Gate 8 als Verstoß deutet. Discovery: Bug-Disziplin §1.5 nach #240-Re-Run.

**Begründung X-1 als 2.:** `samuel/slices/implementation/handler.py:295` machte `git checkout main` VOR Score → AC-Verifier prüfte gegen main statt Issue-Branch. ✅ gemergt 2026-04-30 (PR #242).

**Begründung X0 als 3.:** `[TEST]`-Tag hat heute keinen Handler in `samuel/slices/ac_verification/handler.py:92-97`. Folge: `test_pass_rate` chronisch 0.0 (Gewicht 0.3 in `config/eval.json`). Ohne X0 bleiben alle Eval-Scores um 0.3 zu niedrig — Score-Aussagekraft kompromittiert.

Nach Phase 1: **Phase-Ende-Verifikation** (siehe §3) und Live-Validation gegen #193.

---

## 1. Verbindliche Constraints

### 1.1 Sprachagnostik

Das Framework ist sprachunabhängig. Keine Implementierung in Phase 1 darf neue Python-only-Annahmen einführen.

**Konkrete Pflichten:**
- Datei-Iteration NUR über `samuel.core.project_files.iter_project_files()` mit `CODE_EXTENSIONS` (deckt 30+ Sprachen). Kein `rglob("*.py")`.
- AC-Tags müssen sprachneutral arbeiten:
  - `[DIFF]`, `[EXISTS]`: pfad-basiert, neutral OK
  - `[GREP]`, `[GREP:NOT]`: muss alle Code-Dateien greppen, nicht nur `.py`
  - `[IMPORT]`: bleibt Python-spezifisch (`importlib`), ist aber dokumentiert. Andere Sprachen → eigenes Folge-Issue für `[REQUIRE]`, `[USE]`, etc.
  - `[TEST]`: Test-Runner-Auswahl analog v1 (pytest/unittest/jest/go-test/cargo-test/maven), siehe `docs/README_technical.md` Phase v1
- Skeleton-Builder: bestehende Multi-Language-Builder (`PythonASTBuilder`, `GoRegexBuilder`, `TreeSitterTSBuilder`, `SQLBuilder`, `StructuredConfigBuilder`) bleiben erste Wahl. Neue Plan-Stage-Code in #237 darf KEINE python-spezifische Skeleton-Logik einziehen.
- Pfad-Patterns: keine hardcoded `samuel/` oder `*.py` Annahmen, sondern aus Config / Project-Root abgeleitet.

**Test-Pflicht:** mindestens ein Tag-Test pro Issue verwendet ein Nicht-Python-File (`.go` / `.ts` / `.json`) als Fixture.

### 1.2 Bus-Resilience

Wenn ein Slice oder Tool deaktiviert wird (Feature-Flag aus, fehlende Dependency, Adapter null), darf der restliche Workflow nicht brechen.

**Konkrete Pflichten:**
- Jeder neue Subscriber prüft seine Voraussetzungen vor Aktion (`if not self._llm: return`-Pattern beibehalten)
- Bei #237: wenn Skeleton-Builders leer / Skeleton-Refresh fehlschlägt → Plan-Stage läuft trotzdem (Issue-only Fallback-Prompt)
- Bei #238: wenn `validate_plan_against_skeleton` keinen Skeleton bekommt → Pre-Check skippt das Sub-Check, läuft AC-Dry-Run trotzdem
- Bei #239: wenn `healing` flag aus → EvalFailed bleibt Sackgasse (heutiges Verhalten), nichts crasht. Wenn flag an aber LLM nicht erreichbar → graceful WorkflowBlocked, keine Exception
- Neue Workflow-Steps mit `condition: ...` — Bedingung darf nicht crashen wenn Payload-Keys fehlen (`event.payload.get("score") or 0`-Pattern)
- Tests pro Issue: mindestens ein Test mit komplett deaktiviertem Feature-Flag und ein Test mit fehlender Dependency

### 1.3 Lückenlose Dashboard-Nachvollziehbarkeit

Jedes neue Event muss im Dashboard sichtbar werden — sonst gilt das Issue als unvollständig.

**Konkrete Pflichten:**
- Neue Events in `samuel/core/events.py` mit dataclass + `name: str = "..."`
- Pro Event: passender Slot in `samuel/slices/dashboard/data.py:get_workflow_issue_detail()` ODER `get_status()` ODER `get_score_history()` — KEIN Event ohne UI-Surface
- HTTP-Route in `samuel/server.py:738-820` muss das neue Feld liefern
- Anomalies-Pfad triggern bei Fehler-Events (siehe `get_status().anomalies`)
- Frontend (`DASHBOARD_HTML` in `samuel/server.py`): wenn neue Tab/Section nötig, dann strukturiert hinzufügen — **JS-Escapes verdoppeln** (`\\n` statt `\n`) wegen Python-Triple-String, siehe Memory `feedback_dashboard_js_escapes`
- Dashboard-Prozess am Ende des Issues neustarten (per `feedback_dashboard_restart`)

### 1.4 OWASP + EU AI Act Mapping (Pflicht-Tandem)

Jedes neue Event MUSS in beiden Mappings registriert werden — kein Event darf „unmapped" bleiben.

**Konkrete Pflichten:**

OWASP-Mapping in `samuel/core/owasp.py:OWASP_RISK_MAP` (per #251 nach core verschoben — symmetrisch zu `samuel/core/ai_act.py`; `samuel/slices/audit_trail/owasp.py` ist ein Shim für audit_trail-interne Importer):
- Neuer Eintrag `(category, event_name) → risk_class` für jedes neue Event
- Risk-Klassen aus dem bestehenden Vokabular (`unrestricted_agency`, `excessive_autonomy`, `inadequate_feedback_loops`, `opaque_reasoning`, `broken_trust_boundaries`, `inadequate_sandboxing`, `uncontrolled_behavior`, `unmonitored_activities`, `identity_access_abuse`, `unsafe_tool_integration`)

EU AI Act Mapping:
- `docs/AI_ACT_COMPLIANCE.md` definiert Art. 6, 12, 14, 15, 50, 86
- Neue Events brauchen Verweis auf den passenden Artikel (typische Zuordnungen):
  - `Plan*`-Events / Context-Loading → Art. 13 (Transparency)
  - `Eval*`-Events / Healing-Loop → Art. 15 (Robustness) + Art. 12 (Logging)
  - `WorkflowBlocked` / Stop-Conditions → Art. 14 (Human Oversight)
  - `AC*`-Events → Art. 13 (Transparency: nachvollziehbare Begründung)
- **Phase-1-Sub-Aufgabe:** falls Event-by-Event AI-Act-Mapping fehlt, Mapping-Modul `samuel/core/ai_act.py` analog zu `owasp.py` erweitern (Pflicht-Sub-Issue). Vor #246 lag das Mapping in `samuel/slices/privacy/ai_act_mapping.py`; verschoben nach `core` weil Slice-Isolation cross-slice-Imports verbietet (siehe `tests/test_architecture_v2.py:test_no_cross_slice_imports`).

**Verifikations-Pflicht:** ein Test (`tests/test_event_mapping_complete.py` o.ä.) prüft dass JEDES Event in `samuel/core/events.py` sowohl in `OWASP_RISK_MAP` als auch im AI-Act-Mapping einen Eintrag hat. Dieser Test muss am Ende von Phase 1 grün sein.

### 1.5 Bug-Disziplin (Stop-Conditions)

Wenn bei der Implementierung ein Bug oder Defekt entdeckt wird, der nicht direkt zum Issue gehört: **STOPPEN, melden, gemeinsam entscheiden**. Niemals stillschweigend mitfixen oder ignorieren.

**Auslöser für Stop:**
- Existierender Code crasht oder verhält sich offensichtlich falsch
- Test, der bereits grün sein sollte, ist rot
- Vorhandene Funktion ist anders als erwartet
- Fehlende Dependency, fehlende Konfiguration
- Self-Mode-Run liefert unerwartete Ergebnisse (Score-Stilllegung, Subprocess-Hänger, Token-Explosion)

**Verfahren:**
1. Sofort melden — keinen Workaround einbauen
2. Bug-Detail dokumentieren (Datei, Zeile, Reproduktions-Schritte)
3. Auf User-Entscheidung warten: in aktuellem Issue mitfixen / als separates Issue anlegen / verwerfen
4. Erst dann fortfahren

Siehe Memory: `feedback_self_mode_stop`, `feedback_scope_creep_discipline`.

---

## 2. Best Practice 2026

Allgemein gültige Code-Qualitäts-Pflichten:

- **Type Hints**: vollständig, `from __future__ import annotations`, `IConfig | None` statt `Optional[IConfig]`
- **Dataclasses**: `@dataclass` für alle neuen Events / Value Objects, `frozen=True` wo möglich
- **Strukturiertes Logging**: `log.info("...", extra={"issue": n, "tokens": t})` statt `f"... {n} ..."`
- **Idempotenz**: Handler-Re-Runs auf gleichem Input dürfen keine Side-Effekte verdoppeln
- **Keine versteckten Globals**: State im Handler-Instance halten, nicht in Modul-Variablen
- **Tests vor Implementierung** (TDD-leicht): mindestens 1 Test pro neuem Public-Behavior, vor Code-Schreiben definieren
- **Architektur-Disziplin**: Slice importiert NIE einen anderen Slice, nur `samuel.core.*` und Adapter
- **Keine `from typing import Optional/List/Dict`**: Built-ins (`list`, `dict`, `|`) für Python 3.10+
- **Async-Vorsicht**: Bus ist sync; neue Code bleibt sync; keine `async def` ohne Diskussion

---

## 3. Phase-Ende-Verifikation

Nach Implementierung aller vier Issues:

### 3.1 Legacy-Vergleich

Prüfung gegen v1-Code in `/home/alexanderbenesch/gitea-agent/`:
- `commands/plan.py` — alle Kontext-Building-Logik aus v1 in #237 berücksichtigt?
- `plugins/healing.py` — alle Retry-Verhaltensweisen aus v1 in #239 berücksichtigt?
- `plugins/ac_verification.py` — alle AC-Tag-Behandlungen aus v1 in #236 berücksichtigt?
- `plugins/llm_quality.py` — Touchpoints für Plan-Pre-Check in #238?
- `README_technical.md:600-613` — alle „Robustheit"-Punkte aus v1 abgedeckt?

### 3.2 Sprachneutralitäts-Check

- `grep -rn "rglob.*\.py\|\.py$" samuel/` — keine NEUEN python-only Annahmen
- AC-Verifier mit Fixtures aus mindestens 3 Sprachen testen
- Plan-Stage mit fixtures eines Nicht-Python-Slices testen

### 3.3 Bus-Resilience-Check

Test-Matrix:
- Alle Feature-Flags aus → Workflow läuft ohne Crash, Issue bleibt offen
- LLM-Adapter null → graceful PlanBlocked, keine Exception
- SCM-Adapter null → graceful Watch-Skip, keine Exception
- Skeleton-Builders leer → Plan/Implementation laufen mit Fallback

### 3.4 Mapping-Completeness

- Test `tests/test_event_mapping_complete.py` grün
- Dashboard zeigt alle neuen Events
- OWASP- und EU-AI-Act-Klassifikationen pro Event geloggt

### 3.5 Live-Verifikation

Self-Mode-Run gegen #193 — die Kette muss vollständig durchlaufen:
- Plan mit echtem Code-Kontext
- Plan-Pre-Check passt
- Implementation
- Eval scheitert (initial)
- Eval-Retry läuft 1-3 Runden
- Entweder EvalCompleted → CreatePR → Review, oder WorkflowBlocked mit klarer Begründung
- Dashboard zeigt alle Stages, Scores pro Runde, Anomalies

---

## 4. Stop-Conditions (Phase-1-spezifisch)

Phase 1 wird abgebrochen / unterbrochen wenn:

- Ein Issue der vier scheitert wiederholt im Self-Mode → manuelles Auseinandernehmen, dann Re-Run
- Phase-Ende-Verifikation §3 schlägt fehl → kein Phase 2 bis grün
- User-Stop jederzeit

---

## 5. Was diese Charter NICHT regelt

- Style-Fragen jenseits Best-Practice 2026 (lass Linter entscheiden)
- Wahl der Test-Bibliothek (pytest steht fest)
- Implementation-Reihenfolge innerhalb eines Issues (LLM/Implementer entscheidet)
- Kosmetik des Dashboard-UI

Diese Punkte sind nicht-blockierend für Phase-1-Abschluss.