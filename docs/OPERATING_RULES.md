# Operating Rules

**Aktiver Stand:** 2026-09-22, gegen Code und offene Issues abgeglichen.

Der Reconciliation-Readback vom 29.09.2026 aendert die 24 Regeln nicht.
Neuere Development-E2E-Fehler und ihre verbleibenden Tasks sind in
`docs/status/CURRENT_PRODUCT_STATUS.md`, `docs/status/ISSUE_WORKSTREAM_MAP.md`
und `docs/runbooks/TEST_AND_QUALIFICATION_RUNBOOK.md` datiert. Ein alter
positiver Teilpfad ist weiterhin keine aktuelle Golden-/D0-Authority.

Dieses Dokument bündelt dauerhafte Regeln für die aktuelle issue-getriebene
Entwicklung. Historische Phasen und externe Legacy-Checkouts sind keine
Voraussetzung für Entwicklung, Test oder Installation.

Die 24 Regeln sind verbindlich. Abweichungen werden transparent als Findings
dokumentiert und nicht stillschweigend als erledigt ausgegeben.

---

## 1. Ausführungsdisziplin

### R1 — Ausführungsweg und Zielsystem müssen eindeutig sein

Vor jedem Lauf ist festzulegen, ob S.A.M.U.E.L. am eigenen Repository
(`--self`) oder an einem konfigurierten externen `PROJECT_ROOT` arbeitet.
Manuelle Entwicklung bleibt ein zulässiger, im Issue/PR offen dokumentierter
Weg.

- **Why:** Ein implizites Ziel kann Änderungen am falschen Repository oder einen
  wirkungslosen Lauf verursachen.
- **How to apply:** Ziel und Ausführungsweg im PR-Nachweis nennen; ein fehlendes
  oder ungültiges Ziel gilt als Blocker. Ein Self-Mode-Lauf darf
  Core-Quelländerungen nur als normalen Candidate erzeugen; die laufende
  Installation, Trust Roots, der Updatepfad und die wirksame Policy bleiben
  außerhalb seiner Selbstautorisierung.

### R2 — Required-Gate-Fehler = STOP; Score ist Beobachtung

Bei einem blockierenden Required-Gate oder nicht etablierbarer gebundener
Evaluation: Ursache prüfen und transparent dokumentieren, nicht stumm neu
starten. Ein niedriger oder nicht berechenbarer `ScoreObserved`-Wert ist kein
Freigabe- oder Workflowentscheid.

- **Why:** „Vielleicht klappt's diesmal" ist keine Strategie. Ein wiederholter Run kostet Tokens und verschleiert systematische Probleme.
- **How to apply:** Beim ersten Fail Gate- und Acceptance-Evidence samt
  `EvaluationSubject` prüfen. Einen sicheren Root-Cause-Fix durchführen oder
  ein Folge-Issue anlegen; nur echte Entscheidungsblocker an den Operator
  eskalieren. `status:failed` darf nach einem Healing-Versuch nur durch ein
  bestätigtes `PRCreated` derselben Issue-, Korrelations- und
  Ursprungsbeobachtung entfernt werden; Re-Fail oder fehlende Provenienz
  bleiben fail-closed.

### R3 — Manuelle PR-Erstellung darf nicht lügen

Wenn der Self-Mode-Workflow vor `CreatePR` aussteigt und der PR über die Gitea-API gepostet wird, darf der PR-Body **nicht** behaupten, dass alles automatisch lief.

- **Why:** Audit-Trail muss korrekt sein. Falsche Self-Mode-Behauptungen verfälschen den OWASP-Logging-Pfad (`unmonitored_activities`).
- **How to apply:** PR-Body kennzeichnet manuelle Stages explizit, zum Beispiel:
  „Self-Mode bis CodeGenerated; CreatePR/Gate-Lauf manuell wegen Gate-X."

---

## 2. Patch-Qualität

### R4 — Keine Cross-Slice-Imports, auch in Tests

Tests einer Slice importieren nichts aus anderen Slices. Wenn ein Test einen anderen Handler braucht: Stub in der eigenen Slice, nicht `from samuel.slices.X.handler import …`.

- **Why:** `tests/test_architecture_v2.py:test_no_cross_slice_imports` prüft die
  Repository-Regel umfassender. Gate 8 blockiert im Candidate-Diff nur das
  konkret erfasste Muster neu hinzugefügter Python-`from`-Imports zwischen
  Slices; Details und Grenzen stehen in der Capability-Matrix.
- **How to apply:** Vor Push: `pytest tests/test_architecture_v2.py -v`. Wenn Test-Fixtures Cross-Slice-Verhalten brauchen → Stub im eigenen Slice oder `tests/` (top-level).

### R5 — Out-of-Scope-Bugs werden Folge-Issues

Bei der Implementierung entdeckte Bugs, die nicht zum aktuellen Issue gehören: separates Issue mit Verweis auf Discovery-Run.

- **Why:** Mitfixen vergrößert den Diff, macht den PR schwerer reviewbar und verschleiert den Ursprung eines Findings.
- **How to apply:** Bug mit Datei, Reproduktion und Herkunft dokumentieren und
  ein eigenes Issue anlegen. Ist das Finding unabhängig, anschließend im
  ursprünglichen Scope weiterarbeiten; nur echte Abhängigkeiten blockieren ihn.

### R6 — HTML-Tags in LLM-Patches encoden

Wenn ein LLM-Patch HTML/XML-artige Tags enthält (Test-Fixtures, JS-Snippets in `DASHBOARD_HTML`, Assertions auf Tag-Strings): `<` → `&lt;`, `>` → `&gt;`.

- **Why:** `SanitizingLLMAdapter.strip_html` zerlegt solche LLM-Patches sonst und produziert nicht anwendbare Diffs.
- **How to apply:** Im Plan-Stage explizit anweisen, im Implementation-Prompt nochmal erinnern. Alternativ Tag-Strings über `chr(60)`/`chr(62)` oder String-Concat aufbauen.

---

## 3. Compliance-Mappings

### R7 — Jedes neue Event braucht beide Mappings

Neue Event-Klasse in `samuel/core/events.py` ⇒ Eintrag in `samuel/core/owasp.py:OWASP_RISK_MAP` UND `samuel/core/ai_act.py:AI_ACT_ARTICLE_MAP`.

- **Why:** `tests/test_event_mapping_complete.py` (oder Äquivalent) sichert die vollständige Zuordnung.
- **How to apply:** Plan-Phase nennt explizit Mapping-Pflicht; Implementation berührt beide Mapping-Dateien im selben Commit. Mapping-Completeness-Test muss grün bleiben.

### R8 — Neue Categories brauchen 3 Einträge

Neue OWASP-Risk-Class oder neue AI-Act-Article-Cat ⇒ Eintrag in **beiden** Fallback-Dicts (`OWASP_RISK_CAT_FALLBACK`, `AI_ACT_FALLBACK`) UND in `test_owasp.py:expected_cats` (bzw. Äquivalent für AI-Act).

- **Why:** Fallback-Dicts sichern unmapped Events ab; `expected_cats` verhindert stilles Weglassen einer Category bei Refactor.
- **How to apply:** Vor dem Schreiben des neuen Events: 3-Stellen-Checkliste durchgehen. PR-Review prüft auf alle drei.

### R9 — Bus-Resilience-Test pro neuem Slice-Feature

Jedes neue Slice-Feature liefert mindestens einen Test mit Feature-Flag aus / Adapter null / Dependency fehlt → graceful degrade, keine Exception.

- **Why:** Fehlende Resilience-Tests lassen erwartbare Ausfälle erst im Betrieb sichtbar werden.
- **How to apply:** Test-File pro Issue hat eine Klasse `TestResilience` oder Methoden `test_*_disabled`/`test_*_missing_dependency`. Pre-Check (#238) erinnert daran.

### R10 — Sprachneutralitäts-Test pro Issue

Jedes Issue, das Tag-Handler / Datei-Iteration / Code-Analyse anfasst, hat mindestens einen Test mit Nicht-Python-Fixture (`.go`, `.ts`, `.java`, `.yaml`, `.sql`).

- **Why:** Charter §1.1. Das Framework ist sprachunabhängig — Python-only-Tests führen schleichend python-only-Annahmen ein.
- **How to apply:** Fixture-Datei in `tests/fixtures/` mit Nicht-Python-Extension. Bei reinem Doku-/Config-Issue (wie diesem hier) entfällt R10.

---

## 4. Plan-Pre-Check (Schicht A — #238)

### R11 — `overall_pass=False` ist kein Soft-Signal

Pre-Check mit `overall_pass=False` löst genau einen Plan-Retry aus. Bleibt der
zweite Pre-Check negativ, publiziert die Runtime `PlanBlocked`: bei
`split_recommended` mit eigenem Split-Grund, andernfalls als
`pre_check_failed`. `PlanValidated` ist in diesem Zustand ausgeschlossen.

- **Why:** Der Pre-Check ist nicht informativ, sondern blockierend. Wer durchwinkt, schiebt das Problem an Implementation/Eval, wo es teurer wird.
- **How to apply:** Beide `PlanPreCheckCompleted`-Ereignisse nach
  `retry_attempt` unterscheiden; der Eintrag mit `retry_attempt=1` bewertet
  immer die tatsächliche Provider-Retry-Antwort. `PlanRetryEvaluated` nennt
  beide Score-Sätze, `retry_adopted` und den deterministischen Auswahlgrund.
  Nach dem terminalen Block die konkrete Score-Dimension und
  `blocking_failures` korrigieren oder das Issue splitten;
  ein ausdrücklich offener Issue-Vertrag geht stattdessen in den gebundenen
  Klärungsdialog aus R11a.

### R11a — Klärung ist ein begrenzter, revisionsgebundener Planning-Zustand

Der deterministische Readiness-Check reagiert ausschließlich auf leere oder
ungültige Quellen, ausdrücklich offene Marker und beweisbare
GREP/GREP:NOT-Widersprüche. Er attestiert keine semantische Vollständigkeit.
Bei Klärungsbedarf muss `agent.planning.clarification_wait_seconds` vom
Operator auf eine endliche Frist zwischen 1 und 2.592.000 Sekunden gesetzt
sein. Pro Runde werden höchstens drei Fragen gestellt, nach zwei Runden wird
terminal blockiert.

Antworten verwenden den im Fragekommentar angegebenen Kopf
`S.A.M.U.E.L.-Klärung: <series>/R<n>` und nummerierte Antworten. Frage,
Antwortkommentar, Akteur, Kommentarrevision, Issue-/Base-Quelle und
Budgetzulassung werden persistiert gebunden. Editierte, doppelte, verspätete
oder nach Source-Supersession eintreffende Antworten erteilen keine Authority.
Nach Supersession, Timeout oder ausgeschöpften Runden darf nur ein explizites
`samuel run ISSUE` eine neue Serie beginnen; Watch allein setzt sie nicht fort.

Die angenommene Basis steht sichtbar im Plan. Erst die bestehende menschliche
Freigabe dieses exakten Plans macht sie verbindlich. Das gilt auch in
`autonomous`, `night` und `patch`; ohne Klärungsbasis bleibt deren bisherige
`PlanValidated`-Route aktiv. Dashboard- und Auditereignisse enthalten nur
IDs, Digests, Status und Zähler, keine Antworttexte.

Der Skeleton-Score beschreibt den Bestand des gebundenen Planning-Snapshots.
Eine dort noch nicht vorhandene Datei ist nur dann eine zulässige geplante
Neuanlage, wenn der strukturierte `[FILE]`-/`[PATH]`-Scope ihren kanonischen
Repository-Pfad autorisiert. Ohne gebundenes `project_root`, bei ungültigem
Scope oder für eine vorhandene Datei bleibt der Skeleton-Abgleich fail-closed;
Issue-Text und LLM-Behauptung sind kein Ersatz.

### R12 — `split_recommended` ⇒ Issue splitten

`recommendation=split_recommended` heißt: Issue auf zwei oder mehr separate Issues aufteilen, nicht ignorieren.

- **Why:** Pflicht-Bereich-Schwelle (heuristisch 4) ist kalibriert auf reviewbare PR-Größe. Über der Schwelle ist der LLM-Output nicht mehr deterministisch.
- **How to apply:** Wenn Pre-Check splitten empfiehlt: aktuelles Issue als Epic markieren, Sub-Issues anlegen, Sub-Issues einzeln durch Self-Mode laufen lassen.

### TEST-Runner-Policy betreiben

`test_policy_version`, `test_cmd` und `test_timeout` werden ausschließlich aus
dem beim Bootstrap geladenen Control-Plane-`config/eval.json` übernommen.
Nach einer Änderung muss die Runtime neu gestartet werden; laufende Instanzen
behalten ihren Snapshot. Candidate-`config/eval.json` ist keine Policyquelle.
Der resultierende Runner-Policy-Teil wird im `EvaluationSubject.policy_digest`
gebunden. Diese Kontrolle verhindert Policy-Override, ersetzt aber keine
Prozesssandbox; Candidate-Testcode wird weiterhin ausgeführt.

Vor `PlanPosted` muss Planning die einzelne effektive Runner-Policy auflösen
und jeden `[TEST]`-Selektor gegen deren bekannte Grammar prüfen. Diese
Readiness-Prüfung darf keinen Test starten. Fehlender Runner, fehlende
Toolchain oder ein inkompatibler Selektor blockieren nach dem einzigen
Planning-Retry; sie werden weder umgeschrieben noch durch einen anderen Runner
oder einen Full-Suite-Lauf ersetzt. `samuel doctor` verwendet denselben
Core-Resolver für die betriebliche Vorabdiagnose.

IMPORT- und TEST-Prozesse laufen zusätzlich mit der aus dem Code generierten
Allowlist `verifier-sterile.v1`. HOME, TMP und XDG werden je Prozess neu
erzeugt und danach entfernt. Relative Runner müssen im Interpreterpfad oder
einem festen Systempfad liegen; andere operatorinstallierte Runner sind in
`test_cmd` absolut anzugeben. Parent-`PATH`, Benutzerprofile und Credentials
werden nicht übernommen; user-home-gebundene Toolchains sind in diesem Profil
nicht unterstützt und müssen system- beziehungsweise installationsseitig
bereitgestellt werden. Im Gate-Nachweis müssen IMPORT-/TEST-Evidence und
Subject-Digest dieselbe Environment-Profilversion tragen. Diese Prüfung
belegt keine Sperre für Hostdateien, `/proc`, Netzwerk oder Ressourcen.

- **Why:** Operator-Policy und Candidate-Inhalt dürfen nicht dieselbe
  Autoritätsquelle sein.
- **How to apply:** Runner-Policy nur im Installations-`config_dir` ändern,
  `test_policy_version` mitändern, Runtime neu starten und Subject-Digest sowie
  TEST-Evidence (`runner_policy_source=control_plane`) im Gate-Lauf prüfen.

### R13 — AC-Tag-Vielfalt ist die Pflicht-Bereich-Heuristik

<!-- docs-contract:plan-complexity:start -->
Die Heuristik zählt genau sechs automatisch prüfbare Tag-Bereiche: `DIFF`, `EXISTS`, `GREP`, `GREP:NOT`, `IMPORT`, `TEST`. `MANUAL` ist Readiness und zählt nicht als automatischer Bereich.

Bei mehr als `4` verschiedenen gezählten Bereichen lautet die Runtime-Empfehlung `split_recommended`. Mit den ausgelieferten Code-Defaults lösen damit fünf oder sechs Bereiche die Empfehlung aus. Operatorseitige `eval.json::plan_complexity`-Werte können den Schwellenwert überschreiben und müssen für den konkreten Lauf separat nachgewiesen werden.

**Quellenbindung:**
- `samuel/slices/planning/handler.py::_COMPLEXITY_DEFAULTS`
- `samuel/slices/planning/handler.py::_COMPLEXITY_PFLICHT_TAGS`
- `config/eval.json`
- Vertrag: `docs/capabilities/document-contract.json::operating-plan-complexity`
<!-- docs-contract:plan-complexity:end -->

- **Why:** Hohe Tag-Vielfalt korreliert mit thematischer Breite. Die
  Runtime-Heuristik bleibt ein Split-Signal und kein fachlicher Beweis.
- **How to apply:** Issue-Split-Heuristik vor Plan-Stage anwenden. Bei Grenzfällen: Pre-Check entscheidet.

---

## 5. Dashboard-Verifikation

### R14 — Dashboard restart + konkrete Smoke-Test-Anleitung

Nach Dashboard-relevanter Änderung: Dashboard-Prozess neustarten, dann via Browser/curl ein konkretes Beispiel aufrufen. Smoke-Test-Anleitung nennt **Tab + Position + Aussehen** des UI-Elements.

- **Why:** „X sichtbar" ist ohne Ort und konkreten Zustand nicht falsifizierbar.
- **How to apply:** Smoke-Test-Block im PR-Body nach dem Schema: „Tab Y öffnen → unter Section Z → grüner Badge mit Text 'foo'." Vorher Dashboard-Prozess (`samuel/server.py`) neu starten.

### R15 — JS-Escapes in `DASHBOARD_HTML` immer verdoppeln

JavaScript in `samuel/server.py:DASHBOARD_HTML` ist in einem Python-Triple-String. Backslash-Escapes müssen verdoppelt werden: `\n` → `\\n`, `\t` → `\\t`, `\\` → `\\\\`.

- **Why:** Einfache Escapes werden vom Python-Parser konsumiert, das `<script>` bricht stumm beim Browser-Parse.
- **How to apply:** Bei jedem Edit in `DASHBOARD_HTML` den vollständigen
  Browser-Output mit
  `pytest tests/test_server_dashboard.py -k DashboardJavaScript` prüfen. Der
  Regressionstest untersucht alle ausgelieferten Inline-Scripts und lehnt
  literale Zeilenumbrüche in normalen JavaScript-Strings ab; ein Spotcheck
  der ersten Zeichen des HTML reicht nicht aus.

### R15a — Dashboard-Konfiguration nur im expliziten Setup-Prozess

Der normale Dashboardprozess läuft mit eingefrorener Operator-Konfiguration.
API-Authentisierung oder Administratorstatus erteilen keine Schreibauthority.
Für Setup-, Settings-, Featureflag- oder Promptänderungen startet der Operator
einen getrennten Prozess mit `--configuration-mode setup`, beendet ihn nach
dem Speichern und startet den Produktionsdienst mit read-only eingebundener
Konfiguration neu. Gespeicherter und wirksamer Stand sowie Neustartbedarf
bleiben getrennt sichtbar; In-Memory-Fallback und Hot-Reload sind unzulässig.
Bei einem einzelnen Docker-`.env`-Datei-Bind-Mount darf der Setup-Prozess nach
einem `EBUSY` oder einer nicht schreibbaren Image-Elterndirectory nur den
privat gestagten Inhalt synchronisiert in genau diese Datei schreiben und muss
kontrollierte I/O-Fehler zurückrollen. Das ist keine Rename-Atomizität bei
Prozess- oder Hostabbruch; vor dem Production-Neustart bleibt die gespeicherte
Konfiguration zu prüfen.

- **Why:** Ein Dateisystemfehler auf einem read-only Mount ist keine
  Authority-Grenze, und ein prozesslokaler Override kann gebundene Policy ohne
  persistierten Betreiberauftrag verändern.
- **How to apply:** Jede neue Konfigurationsmutation verwendet dieselbe
  `ConfigurationAuthority`, blockiert in `production` vor Wirkung und erhält
  einen positiven Setup- sowie negativen Produktionsregressionstest.

Lokale Dashboard-Identitäten werden ausschließlich über den schmalen
CLI-Bootstrap-/Recoverypfad initialisiert. Der Cutover verlangt einen aktiven
Administrator, bestätigte Client-Inventur und Begründung. Danach ist ein
Legacy-Key-Fallback unzulässig. Rollen bleiben nicht-hierarchisch, jede Route
benötigt eine explizite Permission, und Identity-Mutationen verlangen eine
frische Reauthentisierung. Restore widerruft Sessions und Automation-Token und
bleibt bis zum lokalen Recovery fail-closed.

---

## 6. Manuelle Eingriffe

### R16 — Jeder Commit braucht Issue-Bezug und nachvollziehbaren Umfang

Die Commit-/PR-Dokumentation nennt das zugehörige Issue und beschreibt den
tatsächlichen Umfang. Manuelle und automatisierte Stufen dürfen nicht
miteinander verwechselt werden.

- **Why:** Nur so bleiben Audit-Trail und spätere Ursachenanalyse verlässlich.
- **How to apply:** PR-Body nennt Issue, Umsetzung, Tests, Abgrenzung und
  manuelle Schritte; keine automatische Herkunft behaupten, wenn sie nicht
  stattgefunden hat.

### R17 — Separaten Worktree-Lifecycle vor jedem Run prüfen

Der produktive Implementation-Pfad arbeitet seit #618 nicht mehr im
Hauptcheckout. Vor Kontextaufbau und K14 muss ein Run-Worktree unter dem
konfigurierten `agent.workspace.work_dir` erfolgreich gebucht und an Branch,
Base, Repository und Run gebunden sein. Ein schmutziger Hauptcheckout wird
weder kopiert noch committed; er ist dennoch kein zulässiger Speicherort für
Run-Artefakte.

- **Why:** Harte Abbrüche sollen einen abgegrenzten, inspizierbaren Baum
  hinterlassen und nicht den nächsten Lauf oder Operatoränderungen
  kontaminieren.
- **How to apply:** Vor Dienststart `samuel workspace list --json` prüfen.
  Quarantänen bewusst inspizieren; bei voller Anzahl-/Kapazitätsgrenze startet
  kein neuer Lauf. `samuel workspace prune` entfernt ausschließlich terminale
  Einträge und nie aktive oder quarantänisierte Evidence. Die ausgelieferte
  168-Stunden-Frist ist eine Operatorfrist, keine automatische Löschung; nur
  `workspace discard ID --reason ...` terminalisiert geprüfte Quarantänen.

Der Implementation-LLM-Loop restauriert bei kontrollierten Fehlschlägen und
Exceptions weiterhin die von ihm berührten Pfade auf ihren Vorzustand (#598).
Bei einem harten Prozessabbruch bleibt der vollständige Run-Worktree erhalten.
Der gebundene Resume-Koordinator darf ausschließlich sichere
Finalisierungsgrenzen übernehmen und prüft dafür OS-Lock, abgelaufenes Lease,
Contract-/Policy-/Schema-Bindung, Git-Zustand und SCM-Postconditions. Ein
nicht eindeutig fortsetzbarer Baum wird begründet quarantänisiert; halbe
LLM-Runden werden nicht rekonstruiert. Operatoren prüfen `samuel resume list`
und verwenden `inspect`, `attempt`/`resume`, `abandon` und erst danach
`cleanup`. Die Patchziel-Grenze
blockiert zwar absolute Pfade, Traversal und Symlink-Ausbrüche vor dem ersten
Write (#600) und schützt `.git` sowie die von Git effektiv aufgelösten lokalen
Verwaltungspfade (#603). Sie ist dennoch keine Prozesssandbox und schützt
nicht gegen parallel privilegiert mutierende lokale Akteure; der
Referenz-Worker bleibt daher kein Ersatz für eine betrieblich isolierte
Ausführungsumgebung.

Netzwerk-Git darf SCM-Credentials ausschließlich über den gemeinsamen
`IGitTransportAuth`-Port und den installierten `GIT_ASKPASS`-Helper erhalten.
`http.extraHeader` mit Token, Credentials in Remote-URLs, persistente
Credential-Helper/-Konfiguration und interaktive Fallbacks sind verboten.
Vor dem Dienststart müssen `origin`, `SCM_URL`, `SCM_REPO` und bei Gitea
`SCM_USER` dasselbe Ziel und Bot-Konto beschreiben. Fehlende oder abweichende
Bindung wird behoben, nicht durch einen globalen Git-Login umgangen. Die
Single-Service-Account-Grenze schützt nicht vor demselben Benutzer mit Zugriff
auf plattformabhängige Prozess-Environments.

### Watch-Betriebsgrenze — genau ein synchroner In-Process-Slot

Der ausgelieferte Watch-Pfad unterstützt ausschließlich
`agent.max_parallel=1` und `workflow.max_parallel=1`. Beide Quellen werden
beim Start einzeln fail-closed validiert; ein vermeintlich begrenzendes
Minimum darf einen höheren Wert nicht verbergen. Ein Scan dispatcht seine
Issues sequenziell, und die Semaphore ist ausschließlich prozesslokal.
Mehrere S.A.M.U.E.L.-Prozesse werden dadurch weder serialisiert noch gegen
einen gemeinsamen Workspace isoliert. Parallelität darf erst zusammen mit
einer expliziten Dispatcher-Capability, Workspace-/Prozessisolation, Schema-,
Test- und Dokumentationsänderung aktiviert werden.

Fachlich abgelehnte Patches müssen vor einem sichtbaren Write enden. Der
JSON-Applier berechnet und validiert deshalb den Kandidaten schreibfrei; ein
Retry darf nie den vom Applier selbst abgelehnten Zwischenstand sehen (#601).
I/O-Fehler während eines begonnenen Writes bleiben Aufgabe der
prozesslokalen Loop-Transaktion, nicht dieser Einzelpatch-Zusage.
Das gilt auch für vollständige Python-WRITEs: AST-Prüfung vor `mkdir`/Write;
ein vorsorglicher Transaktionssnapshot darf nach nachgewiesener
Unverändertheit freigegeben werden, damit Rollback keine Metadaten umschreibt
(#606).

**Aktuelle Repository-Einschränkung:** S.A.M.U.E.L. wird bis zu einer
ausdrücklichen Freigabe nicht im Self-Mode zur Bearbeitung seines eigenen
Repositorys eingesetzt. Manuelle, issue-gebundene Branch-/PR-Arbeit bleibt
zulässig und folgt unverändert allen Regeln dieses Dokuments.

---

## 7. Finding-Hygiene

### R18 — Folgefindings im Repository-Issue dokumentieren

Konkrete Erkenntnisse aus Bugs und Fehlschlägen gehören in ein nachvollziehbares
Repository-Issue und bei dauerhaftem Produktverhalten in Tests bzw. aktive
Dokumentation. Sie dürfen nicht nur in einer workstation-lokalen Memory-Datei
leben.

- **Why:** Issues, Tests und versionierte Doku sind für alle Umgebungen und
  spätere Reviews verfügbar.
- **How to apply:** Finding mit Herkunft, Auswirkung und Akzeptanzkriterien
  anlegen; bei direkter Relevanz das Ursprungs-Issue verknüpfen.

### R19 — Dokumentation und Issue-Verweise sind Teil der Abnahme

Ein Issue ist erst abgeschlossen, wenn alle vom Change betroffenen aktiven
Dokumente gegen Code, Konfiguration und Betriebsverhalten geprüft sind. Das
gilt auch für Referenzen auf das Issue und seine Abhängigkeiten: Status,
erledigter Umfang und offener Restscope müssen zutreffen.

- **Why:** Ein korrekter Codepfad mit veralteter Architektur-, Betriebs- oder
  Issue-Dokumentation erzeugt weiterhin falsche Produkt- und
  Sicherheitszusagen.
- **How to apply:** Jedes Issue erhält ein Doku-Akzeptanzkriterium. Der
  Abschlusskommentar listet Suchumfang, geänderte Dokumente und exakten Commit.
  Falls keine Änderung nötig ist, nennt er die geprüften Fundstellen und die
  konkrete Begründung. Zeitgebundene Dateien unter `archive/` bleiben
  historische Evidenz und werden nicht still umgeschrieben. Der verbindliche
  `python tools/control_matrix.py check` prüft zusätzlich generierte
  Runtime-Fakten, Dokumentklassifikation, Abschnittsbindungen, ADR-Index und
  lokale Dokumentverweise.

### R20 — Preflight-SKIP ist kein bestandenes Gate

Required-Gates 7b, 8, 9, 13a und 13b laufen vor Candidate-IMPORT/-TEST. Bei
einem Required-Preflight-Fehler wird kein Candidate-Prozess gestartet; jedes
nachgelagerte interne und externe Gate erscheint im terminalen Event als
`executed=false`, `passed=null`, `status=skipped_precondition`.

- **Why:** Ein bewusst nicht ausgeführtes Gate ist weder positive noch
  negative Prüfevidence. Eine boolesche Ersatzdarstellung würde Freigabe,
  Telemetrie und Healing verfälschen.
- **How to apply:** Operatoren lesen den tatsächlich fehlgeschlagenen
  Preflight als Blockiergrund. SKIP wird nicht als zusätzlicher Fehler gezählt,
  ein Lauf ohne Gate-11-Evidence bleibt `not_scoreable`, und Healing ist nur
  bei einem real ausgeführten alleinigen Gate-11-Fehler zulässig.

---

## 8. Produktgrenze und Integrationsdisziplin

### R21 — Jede neue Capability braucht eine Grenzkarte

Vor Planung oder Umsetzung werden Nutzerproblem, kleinster End-to-End-Pfad,
vorhandener Code/Betrieb, fachliche Authority, benötigte Rechte, Nicht-Ziele
und realer Nachweis benannt. Für austauschbare Nicht-Core-Capabilities werden
die tatsächlich benötigten Ebenen aus Core-Vertrag, mitgelieferter Referenz
und externem Provider ausgewiesen; nicht benötigte Ebenen werden begründet als
`nicht erforderlich` markiert und nicht vorsorglich gebaut.

- **Why:** Ein echtes Finding darf nicht automatisch zu einem vollständigen
  neuen Subsystem anwachsen.
- **How to apply:** Fehlt einer dieser Punkte, bleibt das Issue Design-/Audit-
  Scope und erhält kein `ready-for-agent`. Bestehende Funktionen werden nicht
  entfernt, bevor ein funktionsgleicher Ersatz mit Positiv-/Negativevidence
  und atomarem Cutover belegt ist. Kein Producer oder Provider erhält
  implizite Autorität; Rechte und Credentials sind minimal, zweck-, zeit- und
  rungebunden zu delegieren.

### R22 — Standards und vorhandene Werkzeuge zuerst

Vor einem eigenen Transport, Artefaktformat oder Fachwerkzeug werden passende
Standards und vorhandene Provider geprüft. Das bevorzugte Profil umfasst je
nach Rolle OpenAPI, CloudEvents/CDEvents, in-toto/DSSE, SARIF, JUnit,
CycloneDX/SPDX, SCM-Checks, OIDC, OCI und OpenTelemetry; MCP/A2A sind optionale
Adapter und keine Authority.

- **Why:** S.A.M.U.E.L.s Kernwert ist Subject-/Evidence-/Policy-Bindung, nicht
  der Nachbau von CI, Sandboxes, Scannern, IAM oder Dokumentationssystemen.
- **How to apply:** Das Issue dokumentiert die Build-versus-Adapter-Prüfung.
  Ein eigener Minimalprovider ist nur für belegten Standalone-Nutzen zulässig
  und verwendet dieselbe fachliche Grenze wie ein Fremdprovider.
  OpenTelemetry-GenAI-Konventionen werden nur versioniert sowie reife- und
  privacybewusst verwendet; sensible Prompt-/Toolinhalte bleiben opt-in und
  Telemetrie wird nicht als Freigabeevidence umgedeutet.

### R23 — Generalisierung braucht zweiten realen Bedarf und eine Authority

Ein schmaler fachlicher Port darf für den ersten End-to-End-Fall entstehen.
Discovery-, Lifecycle-, Registry-, State-, Dashboard-, Doctor- und
Conformance-Plattformen folgen erst einem zweiten realen Adapter oder
Anwendungsfall. Security- und Authority-Grenzen sind davon ausgenommen.

- **Why:** Vorweggenommene Universalität vervielfacht Zustände und
  Fehlerflächen, bevor Austauschbarkeit praktisch belegt ist.
- **How to apply:** Pro Capability und Run genau eine Authority benennen.
  Shadowprovider dürfen vergleichen, aber nicht gemeinsam entscheiden. Soll
  ein Finding zugleich Port, Schema, Store, Events, Dashboard, Migration,
  Doctor und Conformance-Suite erzeugen, ist eine neue Designfreigabe nötig.

### R24 — Golden-Rehearsal und releasegebundene Qualification trennen

Unit-, Integrations-, Architektur- und CI-Tests bleiben Pflicht. Vor einem
Produktrelease, der ausdrücklich als nächster Golden-D0-Kandidat vorgesehen
ist, durchläuft der exakt gebundene Development-Candidate zusätzlich ein
reales Golden-Rehearsal. Dieses Rehearsal ist eine Entwicklungs- und
Integrationsprüfung. Es erzeugt weder einen `published`-, `qualified`- noch
`supported`-Claim. Der formale #658-D0-Vertrag bleibt unverändert: Erst ein
vollständig remote veröffentlichter immutable Release darf mit einem neuen
frischen Qualification-Subject zusammenhängend Q00–Q16 durchlaufen.

- **Why:** Mock- und Quellcodetests zeigen nicht, dass Installation,
  Credentials, Runner, Dashboard, Gates, SCM und Operatorpfad gemeinsam
  funktionieren. Das Rehearsal soll Produkt- und Integrationsfehler vor dem
  immutable Release sichtbar machen, ohne Teilversuche zu einem formalen
  Golden-PASS zusammenzusetzen oder dessen strengere Releasebindung zu
  lockern.
- **Candidatebindung:** Jeder Rehearsal-Attempt bindet den vollständigen
  Produktcommit, das daraus erzeugte Candidate-Artefakt samt Digest,
  Demo-Base und Seed sowie Config, Provider-/Taskroutes, Policy, Prompts und
  Limits. Editable Installationen, lokale Sourcepatches und ungebundene
  Mischstände sind unzulässig. Ändert sich einer dieser Inputs, beginnt ein
  neuer entsprechend gebundener Attempt; frühere Evidence bleibt erhalten und
  wird nicht als PASS des neuen Produktcommits ausgegeben.
- **Findings:** Ein Produkt- oder Contractbug erhält ein normales
  Produktissue, eine möglichst realitätsnahe Regression, PR, CI und
  menschlichen Merge. Danach entsteht ein neuer Candidatecommit; ein einzelnes
  Finding erzwingt noch keinen Produktrelease. Demo-, Operator- oder
  Configfehler werden an ihrer kanonischen Quelle behoben und mit einem neuen
  Attempt beziehungsweise der betroffenen Strecke geprüft, solange keine
  Produktbytes betroffen sind. Bei Secret-Ausgabe, nicht mehr
  vertrauenswürdiger Auditkette, falscher Human-/Bot-Authority oder unklarer
  Writer-/Subjectgrenze wird der Attempt hart beendet. Seine Evidence wird nie
  zu PASS repariert; ein frischer Attempt ist Pflicht. Credentials werden nur
  bei tatsächlicher Exposition oder Kompromittierung rotiert. Eine neue
  fachliche Architektur- oder Contractfrage stoppt bis zur
  Maintainerentscheidung.
- **Impact-Retest:** Nach einem normalen Fix werden die berührten Grenzen aus
  Diff, Contract und ursprünglichem Finding bestimmt. Parser-/Hashänderungen
  wiederholen die betroffene Planning-/Acceptance-Strecke,
  SCM-Authorityänderungen die SCM-/Approvalstrecken, Auditwriteränderungen
  einen frischen Attempt mit neuer Chain und globale Config-/Routingänderungen
  die entsprechenden frühen Bindungen. Reine Dokumentänderungen ohne
  Runtimewirkung erzwingen keine künstliche Runtime-Wiederholung. Solche
  Teilnachweise sind ausschließlich Development-Rehearsal-Evidence und nie ein
  zusammengesetzter Golden-PASS.
- **Campaign und Evidence:** Pro vollständigem Rehearsal-Zyklus dient genau
  ein geeignetes bestehendes Campaign-/Sammelissue oder genau ein neu
  angelegtes Issue als fortlaufender Index. Jeder unverändert erhaltene
  Attempt nennt Attempt-ID, Produktcommit, Candidate-Digest, Demo-Base/Seed,
  erreichte Q-Stufe, Finding und Klassifikation, Produkt-/Demo-Issue, PR,
  Fixcommit, invalidierte beziehungsweise erneut zu prüfende Q-Grenzen und
  Fortsetzung. Der Abschluss nennt den finalen vollständigen Rehearsal-PASS.
  Die Q00–Q16-Tabelle aus
  `samuel-pipeline-escape::qualification/EVIDENCE_TEMPLATE.md`
  darf dafür nur als ausdrücklich `Development Golden Rehearsal` markierte
  Kopie verwendet werden; Releasefelder werden durch die gebundene
  Candidateidentität ergänzt und die Kopie erteilt keine
  Qualificationauthority.
- **Öffentlicher Operator-Einstieg:** Das Scenario-Issue wird extern und nativ
  aus dem kanonischen Scenario erzeugt. Der initiale Workflowstart erfolgt
  danach genau einmal mit `samuel run <issue>`. Der dafür benannte menschliche
  Betreiber erteilt die Planfreigabe als echte Humanaktion über
  `status:approved`; ausschließlich
  der signierte Webhook liefert dafür die Golden-Authority-Evidence. Spätere
  SCM-/CI-Wirkung stammt aus nativen SCM-/CI-Ereignissen und signierten
  Webhooks. `samuel watch --once` ist Polling-, Backfill- oder
  Beobachtungspfad und ersetzt den initialen Operator-Dispatch nicht.
  `samuel resume` ist ausschließlich für einen ausdrücklich resumable,
  nichtterminalen Checkpoint zulässig.
- **Rehearsal-Exit:** Bevor der normale Releasepfad für den Golden-D0-Kandidaten
  beginnt, muss der finale Candidatecommit einmal ohne Produktcodeänderung die
  gesamte vorgesehene Q00–Q16-Strecke durchlaufen. Produktcommit,
  Candidate-Artefakt, Demo-Base und Config-/Route-/Policy-/Promptbindung
  bleiben dabei identisch. Dieser Ausgang darf `Development-Rehearsal-PASS`
  heißen, aber nicht `published`, `Golden-qualified` oder `supported`.
  Erst dieser Receipt gibt genau den gebundenen Commit für den normalen
  create-only Releasepfad frei.
- **Formaler Golden-D0:** Auf den Rehearsal-Exit folgen regulärer immutable
  Release, vollständiger Remote-Publish und Readback, ein neuer frischer
  Qualification-Subject und ein zusammenhängender Q00–Q16-Lauf ohne
  Produktänderung. Ein Produktbug in diesem formalen Lauf bleibt terminal
  `FAIL` und verlangt Fix, neuen Release und neuen Subject.
- **How to apply:** Rehearsal und späterer Release-Nachweis binden jeweils ihre
  tatsächlichen Artefakte, Repository, Base/Head,
  Contract-/Policy-/Workflow-Digests, Run-IDs, Ausgang, Dauer, Kosten und
  Grenzen sowie effektiv verwendetes Modell/Provider,
  Prompt-/Agent-Konfiguration, Toolchain und Berechtigungsprofil.
  Gitea-/Homelab-Anteile werden als Referenzinfrastruktur, nicht als allgemeine
  Produktfähigkeit ausgewiesen.

### R25 — Re-Planning widerruft Plan und Freigabe explizit

Ein autoritativer Plan bleibt bis zu seinem expliziten Widerruf gültig.
`samuel run` darf ihn weder ersetzen noch eine bestehende Freigabe auf einen
anderen Plan übertragen. Ein fachlich unzureichender Plan wird ausschließlich
mit `samuel replan <issue> --reason <text>` ersetzt.

Eine menschliche Planfreigabe wird beim autorisierten SCM-Ereignis als eigener,
an Repository, Issue, Plan-Kommentar, Contract, Akteur, Transport, Quellen-ID,
Zeitpunkt und vorhandenen Source-Snapshot gebundener Authority-Record
materialisiert. Statuslabels bleiben danach Projektion und Workflow-Signal.
`GateFailed`, `manual_pending`, `status:failed` oder ein Restart widerrufen
diesen Record nicht. Gate-, Review- und Resume-Pfade rekonstruieren ihn aus dem
Authority-State und revalidieren die ursprüngliche SCM-Quelle ohne das aktuelle
Vorhandensein von `status:approved` zu verlangen. Fehlender, fremder oder stale
State blockiert; SCM-Kommentare oder Labels bilden bei fehlendem Authority-Store
keinen Ersatzpfad. Beobachten signierter Webhook und authentifiziertes Polling
dieselbe Labelentscheidung desselben Akteurs zum selben Zeitpunkt, verwenden
beide idempotent den zuerst create-only materialisierten Record. Nur die
bestehende explizite Replan-/Supersession-Grenze macht die Freigabe ungültig.

- **Why:** Eine Freigabe gilt für den sichtbar geprüften Planvertrag. Selbst
  gleicher Plantext in einem neuen SCM-Kommentar ist eine neue
  Freigabeinstanz.
- **How to apply:** Der Replan-Pfad schreibt zuerst einen unveränderlichen,
  an Kommentar-ID und Contract-Hash gebundenen Widerruf, entfernt
  `status:approved` und `status:plan` und liest den SCM-Zustand zurück. Erst
  nach bestätigtem Widerruf darf ein Ersatzplan entstehen. Der angegebene
  Grund erreicht genau diesen Ersatzplan als abgegrenztes Replan-Feedback;
  er erweitert weder Scope noch Authority. Der Ersatzplan benötigt
  ein neues, einem Menschen zugeordnetes Freigabeereignis nach seiner
  Veröffentlichung. Ein abgelehnter impliziter Replan beendet nur den
  abgelehnten Run als `blocked`; der bestehende Plan und seine Labels bleiben
  dabei unverändert. Fehlende, ältere oder Bot-Evidence blockiert; ein
  Teilausfall erzeugt keinen Ersatzplan.

---

### Health-, Readiness- und Qualification-Anzeigen auswerten

`healthy=true` belegt nur den im Payload genannten technischen Checkumfang.
`operational_readiness=unknown` ist bei nicht ausgeführter Provider-Liveprobe
der erwartete ehrliche Zustand. Doctor und `audit verify` bleiben die
Fachquellen ihrer Qualification; `stale` und `not_checked` sind kein Pass.
Viewer-/Dashboard-Health ist passiv. Aktive Self-Checks dürfen nur mit
`RUN_PROVIDER_PROBES` ausgelöst werden. Ein Restore macht vorherige positive
Projektionen veraltet; ein früherer Auditfehler bleibt sichtbar, bis eine
echte erfolgreiche Kettenprüfung ihn digestgebunden auflöst.

Ein Container bindet den effektiven Konfigurationspfad einmal über
`SAMUEL_RUNTIME_CONFIG_DIR`. Hauptprozess, Einmal-CLI und Docker-Healthcheck
verwenden diese Bindung. Ein zusätzliches `--config` muss auf denselben
normalisierten Pfad zeigen und wird bei Abweichung vor dem Bootstrap
abgewiesen. Dadurch darf ein Healthcheck weder still auf die Defaultconfig
zurückfallen noch State unter einem anderen Datenpfad anlegen. Eine
Production-Freeze-Evidence verlangt zusätzlich einen laufenden Container,
Docker-Health `healthy`, `FailingStreak == 0`, einen erfolgreichen letzten
Healthcheck, authentifiziertes Dashboard-Health, verweigerten
unauthentifizierten Zugriff, verifizierte Auditkette und identische effektive
Config-/State-Bindungen.

### Qualification-Operatorpreflight vor der ersten Wirkung

Ein frischer Qualification-Subject übernimmt Credentials und Zielbindungen
nur selektiv aus einer autorisierten, geschützten Operatorquelle außerhalb des
Repositories. Für jeden Pflichtwert werden Zweck, Empfänger, Zielidentität und
reine Präsenz festgelegt. Weder eine vollständige alte `.env` noch eine
komplette Operator-Shellumgebung wird als Overlay geladen. Ein fehlender,
leerer oder für das falsche Ziel bestimmter Pflichtwert blockiert vor Wizard,
Auditwriter, Providerprobe oder Workflowstart (#821, #843).

Der Preflight meldet ausschließlich `present`/`missing`, Ziel und
`stored_effective=match|mismatch|not_applicable`; Wert, abgeleiteter
Secretdigest und Dateinhalt bleiben unsichtbar. Nach dem selektiven Schreiben
wird der Wert aus genau der später verwendeten Runtimeumgebung erneut gelesen
und auf Gleichheit geprüft. `stored=present` bei `effective=missing` oder
`mismatch` ist ein Blocker. Der Check definiert keine allgemeine
Configpriorität und keinen Produkt-Secretloader.

Vor dem ersten Planning bindet der neue Checkout `origin` an die kanonische
URL des Qualification-Zielrepositories und bestätigt erwarteten Base-/Seed-
Commit. Ein lokaler Seed-Transferpfad ist keine Runtime-Remoteauthority.
Config, State, Authority, Runs, Sessions, Candidates, Contracts, Approvals und
Dashboardprojektionen beginnen für den neuen Subject frisch; ausdrücklich
zulässige externe Infrastruktur und zweckgebundene Keys bleiben davon
getrennt (#845).

Für die fünf effektiven LLM-Tasks `planning`, `implementation`, `review`,
`healing` und `evaluation` werden Provider, Modell, Fallback, Timeout,
Outputlimit, Workflowbudget und Promptbindung vor dem Lauf ausgelesen. Ein
globales `SAMUEL_LLM_PROVIDER` ersetzt keinen expliziten Task- oder
Schedule-Eintrag. Das externe D0-Profil setzt deshalb jede beabsichtigte Route
über die vorhandene Operator-Konfiguration, bindet deren Digest und friert sie
bis zum Neustart ein. Catalog-/Suitability-Fakten und begrenzte reale Probes
qualifizieren nur dieses Profil; sie ändern keine ausgelieferten Defaults
(#822, #829).

Ein vorhandener gültiger D0-Dashboardcredential wird nicht still ersetzt. Der
Start meldet URL, Instanz, Release und Authmodus, niemals den Credentialwert.
Ein HTTP-200-Smoke genügt nicht: Der gebundene Goldenlauf muss seine aktuellen
Workflow-, Approval-, Candidate-, Gate-, CI-, Merge-, Restart-, Audit-,
Health-, Readiness- und Qualificationzustände im selben frischen Subject
zeigen. Alte Projektionen erteilen keine aktuelle Qualificationauthority
(#830).

Der Release-Operator liest `source`, Revision und Publisheridentität aus der
spezialisierten, auf das Produkt-SCM gebundenen Quelle. Demo-SCM,
Runtime-Bot-Konfiguration und lokale Transfer-Remotes sind keine
Releasequelle. Vor jeder Publishwirkung und im Readback müssen Produkt-Source,
Version, Revision und Digest übereinstimmen; der erste Required-Smoke gehört
zum selben create-only Kandidaten. Ein fehlgeschlagener Kandidat wird weder
überschrieben noch durch spätere Evidence geheilt (#835).

## 9. Verbindlicher Gitea-Mergepfad

Für `main` ist die native Gitea-Branch-Protection die einzige serverseitige
Policy-Autorität: kein direkter oder Force-Push, keine Löschung, keine
Push-Allowlist, exakt der effektive `SCM_REQUIRED_STATUS_CONTEXT` für den
aktuellen PR-Head und kein Admin-Merge-Override. Ohne explizite Konfiguration
gilt der sichtbar gemeldete ausgelieferte Default
`CI / lint-and-test (pull_request)`. Normale Nutzer, `example-bot` und
Administratoren dürfen daher nicht direkt pushen. Merge-berechtigte
Identitäten dürfen nur über einen regelkonformen PR mergen.

Das optionale `auto_merge_pr` ist standardmäßig aus. Seine Aktivierung
verkürzt keine Freigabekette: Erst ein geschlossenes strukturiertes
Reviewresultat `pass` darf die Mergepolicy prüfen. Danach müssen der aktive
Plan, die unveränderte menschliche Approval-Evidence, alle gebundenen Required
Gates und die aktuelle PR-Revision noch passen. Der Gitea-Pfad sendet den
erwarteten Head zusätzlich nativ als `head_commit_id`; automatische Wirkung
verlangt außerdem den separat gesetzten Deploymentnachweis
`expected_head_merge_qualified`. Fehlt Fähigkeit oder Nachweis, bleibt der
Review manuell/advisory. Ein an Subject und Review-Digest gebundener Mergeintent
mit unbekannter Postcondition wird gegen den realen PR-Zustand reconciliert
und niemals blind wiederholt. Reviewprovider und Dashboard besitzen keine
Approval- oder Mergeauthority.

Vor einer Freigabe und nach jeder SCM-/Berechtigungsänderung ist `samuel doctor`
mit Leserecht auf die Branch-Regel auszuführen. Ein `❌ Branch-Protection
(Release)` oder ein ungültiger Soll-Kontext ist ein Release-Blocker, auch wenn
SCM-Verbindung und lokale Tests grün sind. Die vollständige Einrichtung und
die Trennung von Runtime- und Prüfrechten stehen in `docs/INSTALL.md`.

## Querverweise

- `CONTRIBUTING.md` — Beitragsworkflow und aktuelle Qualitätsgates.
- `docs/SAMUEL_DESIGN_DECISIONS.md` — bestätigte Entscheidungen, datierter
  Prüfbefund und aktueller Issue-Restscope.
- `docs/CAPABILITY_MATRIX.md` — generierte Ist-Bewertung der Kontrollen,
  Profile, Beweise und Release-Blocker.
- `docs/RUNTIME_REFERENCE.md` — generierte verfügbare und ausgeliefert
  konfigurierte Laufzeitfakten.
- `docs/adr/README.md` — Index der dauerhaften Designentscheidungen.
- `docs/SAMUEL_ARCHITECTURE_V2.1.md` — Architektur und Slice-Grenzen.
- `docs/INSTALL.md` — portable Installation auf Zielsystemen.
- `docs/PRODUCT_BOUNDARY_HANDOVER_PROMPT.md` — vollständiger Starttext für
  einen neuen Arbeitschat mit derselben Produkt- und Qualitätsgrenze.

## Was diese Rules NICHT regeln

- Code-Style jenseits Best-Practice 2026 — Linter-Sache.
- Issue-Granularität jenseits R12/R13 — wird anhand des konkreten Scopes entschieden.
- Test-Bibliothek — pytest steht fest.
