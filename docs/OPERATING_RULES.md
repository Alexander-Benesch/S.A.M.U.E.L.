# Operating Rules — Phase 2+

**Verbindlich ab Phase 2.** Stand: 2026-05-01.

Dieses Dokument distilliert die Lessons aus der Phase-1-Hardening-Welle (Issues #236–#239 und die X-Folge danach) zu einem dauerhaften Regelwerk. Wo der `docs/PHASE_1_HARDENING_CHARTER.md` Phase-1-spezifisch bindet, gilt dieses Dokument für alle weiteren Phasen — insbesondere Phase 2 (v1→v2-Parität).

Die 18 Regeln sind nicht-verhandelbar. Verstöße sind STOP-Conditions im Sinne von Charter §1.5 und werden als separate Issues nachgezogen, nicht stillschweigend mitgefixt.

---

## 1. Self-Mode-Disziplin

### R1 — Self-Mode ist der Default-Pfad

Manuelle Fixes nur bei (a) Self-Mode-Blocker, (b) Charter-§1-Verstoß im LLM-Output, (c) eigener Regression aus dem letzten Patch.

- **Why:** Phase 1 hat mehrfach gezeigt, dass „mal eben manuell" zu inkonsistenten PR-Bodies und unklarer Provenienz führt. Self-Mode liefert messbare Scores; manuelle Patches umgehen die Eval-Pipeline.
- **How to apply:** Jeder manuelle Commit hat einen Grund-Satz im Body (z.B. "Manuell wegen Gate-8-Block in Self-Mode-Run-1"). Ohne Grund-Satz ist der Commit zurückzuweisen.

### R2 — Score < 1.0 oder GateFailed = STOP

Bei Score-Underperformance oder Gate-Block: Operator melden, nicht stumm neu starten.

- **Why:** „Vielleicht klappt's diesmal" ist keine Strategie. Ein wiederholter Run kostet Tokens und verschleiert systematische Probleme.
- **How to apply:** Beim ersten Fail: Score-Felder lesen, Blocker benennen, Operator-Entscheidung abwarten. Erst dann Re-Run, Plan-Retry oder Issue-Split.

### R3 — Manuelle PR-Erstellung darf nicht lügen

Wenn der Self-Mode-Workflow vor `CreatePR` aussteigt und der PR über die Gitea-API gepostet wird, darf der PR-Body **nicht** behaupten, dass alles automatisch lief.

- **Why:** Audit-Trail muss korrekt sein. Falsche Self-Mode-Behauptungen verfälschen den OWASP-Logging-Pfad (`unmonitored_activities`).
- **How to apply:** PR-Body kennzeichnet manuelle Stages explizit: „Self-Mode bis EvalCompleted, CreatePR manuell wegen Gate-X."

---

## 2. Patch-Qualität

### R4 — Keine Cross-Slice-Imports, auch in Tests

Tests einer Slice importieren nichts aus anderen Slices. Wenn ein Test einen anderen Handler braucht: Stub in der eigenen Slice, nicht `from samuel.slices.X.handler import …`.

- **Why:** `tests/test_architecture_v2.py:test_no_cross_slice_imports` und Gate 8 (`samuel/slices/pr_gates/gates.py:slice_gate`) blockieren das. In Phase 1 war Gate 8 wegen #240-Tests fälschlich rot — wir wollen das gar nicht erst pushen.
- **How to apply:** Vor Push: `pytest tests/test_architecture_v2.py -v`. Wenn Test-Fixtures Cross-Slice-Verhalten brauchen → Stub im eigenen Slice oder `tests/` (top-level).

### R5 — Out-of-Scope-Bugs werden Folge-Issues

Bei der Implementierung entdeckte Bugs, die nicht zum aktuellen Issue gehören: separates Issue mit Verweis auf Discovery-Run.

- **Why:** Memory `feedback_scope_creep_discipline`, `feedback_self_mode_stop`. Mitfixen vergrößert den Diff, macht den PR schwerer reviewbar und verfälscht Self-Mode-Scores.
- **How to apply:** Sofort STOP, Bug dokumentieren (Datei:Zeile, Repro-Schritte), neues Issue anlegen mit Body-Zeile „Discovered in Self-Mode-Run #NNN von Issue #MMM". Erst dann zurück zum Original-Issue.

### R6 — HTML-Tags in LLM-Patches encoden

Wenn ein LLM-Patch HTML/XML-artige Tags enthält (Test-Fixtures, JS-Snippets in `DASHBOARD_HTML`, Assertions auf Tag-Strings): `<` → `&lt;`, `>` → `&gt;`.

- **Why:** Memory `feedback_html_in_llm_response`. `SanitizingLLMAdapter.strip_html` zerlegt sonst den Patch und produziert nicht-applybare Diffs.
- **How to apply:** Im Plan-Stage explizit anweisen, im Implementation-Prompt nochmal erinnern. Alternativ Tag-Strings über `chr(60)`/`chr(62)` oder String-Concat aufbauen.

---

## 3. Charter-§-Tandem

### R7 — Jedes neue Event braucht beide Mappings

Neue Event-Klasse in `samuel/core/events.py` ⇒ Eintrag in `samuel/core/owasp.py:OWASP_RISK_MAP` UND `samuel/core/ai_act.py:AI_ACT_ARTICLE_MAP`.

- **Why:** Charter §1.4 ist sonst nicht durchsetzbar. `tests/test_event_mapping_complete.py` (oder Äquivalent) ist die Sicherung.
- **How to apply:** Plan-Phase nennt explizit Mapping-Pflicht; Implementation berührt beide Mapping-Dateien im selben Commit. Mapping-Completeness-Test muss grün bleiben.

### R8 — Neue Categories brauchen 3 Einträge

Neue OWASP-Risk-Class oder neue AI-Act-Article-Cat ⇒ Eintrag in **beiden** Fallback-Dicts (`OWASP_RISK_CAT_FALLBACK`, `AI_ACT_FALLBACK`) UND in `test_owasp.py:expected_cats` (bzw. Äquivalent für AI-Act).

- **Why:** Fallback-Dicts sichern unmapped Events ab; `expected_cats` verhindert stilles Weglassen einer Category bei Refactor.
- **How to apply:** Vor dem Schreiben des neuen Events: 3-Stellen-Checkliste durchgehen. PR-Review prüft auf alle drei.

### R9 — Bus-Resilience-Test pro neuem Slice-Feature

Jedes neue Slice-Feature liefert mindestens einen Test mit Feature-Flag aus / Adapter null / Dependency fehlt → graceful degrade, keine Exception.

- **Why:** Charter §1.2. In Phase 1 hatten mehrere Issues ihre Resilience-Tests erst nachträglich bekommen — fehlende Tests = unentdeckte Crashes in Prod.
- **How to apply:** Test-File pro Issue hat eine Klasse `TestResilience` oder Methoden `test_*_disabled`/`test_*_missing_dependency`. Pre-Check (#238) erinnert daran.

### R10 — Sprachneutralitäts-Test pro Issue

Jedes Issue, das Tag-Handler / Datei-Iteration / Code-Analyse anfasst, hat mindestens einen Test mit Nicht-Python-Fixture (`.go`, `.ts`, `.java`, `.yaml`, `.sql`).

- **Why:** Charter §1.1. Das Framework ist sprachunabhängig — Python-only-Tests führen schleichend python-only-Annahmen ein.
- **How to apply:** Fixture-Datei in `tests/fixtures/` mit Nicht-Python-Extension. Bei reinem Doku-/Config-Issue (wie diesem hier) entfällt R10.

---

## 4. Plan-Pre-Check (Schicht A — #238)

### R11 — `overall_pass=False` ist kein Soft-Signal

Pre-Check-Warnung mit `overall_pass=False` ⇒ `blocking_failures` lesen und entscheiden: Plan-Retry oder Issue-Split.

- **Why:** Der Pre-Check ist nicht informativ, sondern blockierend. Wer durchwinkt, schiebt das Problem an Implementation/Eval, wo es teurer wird.
- **How to apply:** Pre-Check-Output ist Pflicht-Lektüre vor Implementation. `blocking_failures` triggern entweder Plan-Retry mit erweiterten Constraints oder Issue-Split.

### R12 — `split_recommended` ⇒ Issue splitten

`recommendation=split_recommended` heißt: Issue auf zwei oder mehr separate Issues aufteilen, nicht ignorieren.

- **Why:** Pflicht-Bereich-Schwelle (heuristisch 4) ist kalibriert auf reviewbare PR-Größe. Über der Schwelle ist der LLM-Output nicht mehr deterministisch.
- **How to apply:** Wenn Pre-Check splitten empfiehlt: aktuelles Issue als Epic markieren, Sub-Issues anlegen, Sub-Issues einzeln durch Self-Mode laufen lassen.

### R13 — AC-Tag-Vielfalt ist die Pflicht-Bereich-Heuristik

7 verschiedene AC-Tag-Bereiche (DIFF/EXISTS/GREP/IMPORT/TEST/USE/REQUIRE) ⇒ Issue gehört in mindestens 2 Issues.

- **Why:** Hohe Tag-Vielfalt korreliert mit thematischer Breite. Ein Issue, das alle 7 Tag-Typen braucht, ist mit hoher Wahrscheinlichkeit „Sammelsurium" und kein einzelner Schritt.
- **How to apply:** Issue-Split-Heuristik vor Plan-Stage anwenden. Bei Grenzfällen: Pre-Check entscheidet.

---

## 5. Dashboard-Verifikation

### R14 — Dashboard restart + konkrete Smoke-Test-Anleitung

Nach Dashboard-relevanter Änderung: Dashboard-Prozess neustarten, dann via Browser/curl ein konkretes Beispiel aufrufen. Smoke-Test-Anleitung nennt **Tab + Position + Aussehen** des UI-Elements.

- **Why:** Memory `feedback_dashboard_restart`, `feedback_browser_change_localization`. „X sichtbar" ist nicht falsifizierbar; der User kann das so nicht überprüfen.
- **How to apply:** Smoke-Test-Block im PR-Body nach dem Schema: „Tab Y öffnen → unter Section Z → grüner Badge mit Text 'foo'." Vorher Dashboard-Prozess (`samuel/server.py`) neu starten.

### R15 — JS-Escapes in `DASHBOARD_HTML` immer verdoppeln

JavaScript in `samuel/server.py:DASHBOARD_HTML` ist in einem Python-Triple-String. Backslash-Escapes müssen verdoppelt werden: `\n` → `\\n`, `\t` → `\\t`, `\\` → `\\\\`.

- **Why:** Memory `feedback_dashboard_js_escapes`. Einfache Escapes werden vom Python-Parser konsumiert, das `<script>` bricht stumm beim Browser-Parse.
- **How to apply:** Bei jedem Edit in `DASHBOARD_HTML`: nach Save mit `python3 -c 'from samuel.server import DASHBOARD_HTML; print(DASHBOARD_HTML[:200])'` kontrollieren, dass die JS-Escapes korrekt sind.

---

## 6. Manuelle Eingriffe

### R16 — Manueller Commit braucht Issue-Reference + Begründung

Operator-Commit ohne Self-Mode: Commit-Message enthält `(#NNN)` UND nennt warum nicht Self-Mode (z.B. „Charter-§1-Fix nach Gate-8-Block aus Self-Mode-Run-1").

- **Why:** Audit-Trail nachvollziehbar machen. Ohne Begründung wirkt jeder manuelle Commit wie eine Self-Mode-Umgehung.
- **How to apply:** Commit-Template oder Pre-Commit-Hook prüft auf `(#NNN)` und mindestens 2 Body-Zeilen (Grund + Was).

### R17 — Workspace muss clean sein vor Self-Mode-Run

`git status` clean prüfen vor jedem Self-Mode-Start. Sonst kapert der Run uncommitteten State und der Diff ist nicht mehr dem Issue zuordenbar.

- **Why:** Self-Mode operiert auf dem Worktree. Uncommitteter State landet als Teil des Issue-Diffs im PR.
- **How to apply:** Self-Mode-Start-Skript (oder Operator-Pre-Flight-Check) prüft `git status --porcelain` — bei nicht-leerem Output: STOP, Operator entscheidet (Stash, Commit, Discard).

---

## 7. Memory-Hygiene

### R18 — Lessons-Learned als Memory speichern, nicht in Code-Comments

Konkrete Erkenntnisse aus Bugs/Failures gehören in `~/.claude/projects/.../memory/feedback_*.md`, nicht in Inline-Code-Comments oder in CLAUDE.md.

- **Why:** Memory wird in jeder neuen Session geladen und ist projektübergreifend wirksam. Code-Comments sind lokal und werden beim Refactor verloren. Phase 1 hat 16 `feedback_*.md`-Einträge — die wirken in jedem neuen Run.
- **How to apply:** Nach jedem Operator-Eingriff: Memory-Eintrag prüfen/anlegen. Bei wiederkehrendem Pattern → eigene Memory-Datei mit `Why:` und `How to apply:` (siehe Memory-Section in CLAUDE.md).

---

## Querverweise

- `docs/PHASE_1_HARDENING_CHARTER.md` — Phase-1-spezifische Vorläufer-Constraints. Charter §1.1–1.5 sind in Phase-2+ weiterhin gültig; OPERATING_RULES erweitert um operative Regeln.
- `docs/PHASE_WORKFLOW.md` — 3-Stufen-Protokoll Implementation → Phase-Review → QS-Check.
- Memory-Index: `~/.claude/projects/-home-alexanderbenesch-S-A-M-U-E-L-/memory/MEMORY.md` — die `feedback_*.md`-Dateien sind die granularen Quellen vieler Regeln hier.

## Was diese Rules NICHT regeln

- Code-Style jenseits Best-Practice 2026 — Linter-Sache.
- Issue-Granularität jenseits R12/R13 — User entscheidet je Phase.
- Test-Bibliothek — pytest steht fest.
