# S.A.M.U.E.L.

### Sicheres Autonomes Mehrschichtiges Ueberwachungs- und Entwicklungs-Logiksystem

S.A.M.U.E.L. ist ein Zero-Trust-Framework, das Entwicklerteams die
**LLM-gestuetzte Routinearbeit abnimmt**: aus einem Issue wird automatisch ein
Pull Request — ohne dass ein LLM jemals unkontrolliert auf das Repo schreibt.

Das System integriert sich in bestehende Team-Workflows auf **GitHub** und
**Gitea**. LLMs werden als austauschbare, **nicht vertrauenswuerdige Worker**
behandelt — die Schranken sind technisch, kein Prompt kann sie umgehen.

---

## Wofuer S.A.M.U.E.L. da ist

Entwicklerteams beschreiben Aufgaben in Issues. S.A.M.U.E.L. greift Issues mit
einem Workflow-Label, plant die Loesung, schreibt den Code, prueft das
Ergebnis und oeffnet einen Pull Request. Der Mensch bleibt im Review-Loop —
aber Recherche, Boilerplate, Tests und Linter-Roboterarbeit sind weg.

S.A.M.U.E.L. ist gebaut fuer Teams, die:

- LLM-Output **auditieren und zertifizieren** muessen (DSGVO, AI-Act, OWASP-Risk)
- mit **mehreren LLM-Providern** arbeiten wollen (lokal + Cloud, Cost-Saving im Nacht-Schedule)
- klare **Schranken** brauchen, was ein Agent darf — und was nicht
- den Bot **nachvollziehbar** im Repo arbeiten lassen wollen, mit jedem Schritt als Audit-Event

Was S.A.M.U.E.L. nicht ist: kein Code-Assistent in der IDE, kein interaktiver
Chatbot, kein Generic-Function-Caller. Der Fokus liegt auf der
**End-to-End-Strecke Issue → PR** im Team-Repo.

---

## Wie ein Issue durch S.A.M.U.E.L. laeuft

```
Issue (GitHub/Gitea)
  │
  ▼
┌────────────┐    ┌──────────────┐    ┌────────────┐    ┌────────────┐
│  Planning  │───▶│Implementation│───▶│ Evaluation │───▶│ PR-Gates   │
└────────────┘    └──────────────┘    └────────────┘    └────────────┘
   │                  │                    │                  │
   ▼                  ▼                    ▼                  ▼
5 Schranken      7 Schranken          4 Schranken         14 Gates
```

### 1. Planning — Issue → Plan

Ein LLM erstellt aus dem Issue einen strukturierten Plan: Aufgaben,
Akzeptanzkriterien, betroffene Dateien, Tests. Bevor der Plan akzeptiert wird,
muss er **fuenf Schranken** passieren:

- **Prompt-Guard** — fester Header in jedem LLM-Prompt; manipulierte Eingaben
  werden vor dem Aufruf abgewiesen.
- **Prompt-Injection-Detection** — 7 Muster (`ignore instructions`,
  `system prompt`, `act as …`, …) gegen den Issue-Text; Treffer blockt den
  Bus-Call.
- **Plan-Validator** — der erzeugte Plan wird gescored (Vollstaendigkeit,
  AC-Format, Datei-Pfade); Score 50–80 % triggert Retry mit kritischem
  Feedback ans LLM.
- **Plan-Pre-Check / Komplexitaets-Waechter** — zu komplexe Plaene werden als
  `PlanComplexityWarn` markiert; im `chat`-Workflow ist Plan-Approval Pflicht.
- **Plan-als-Kommentar** — der Plan wird als Issue-Kommentar gepostet, *bevor*
  Code geschrieben wird. Voll auditierbar, das Team kann eingreifen.

### 2. Implementation — Plan → Code

Aus dem Plan wird Code in einem **Multi-Round-LLM-Loop** (5 Runden) erzeugt.
**Sieben Schranken**:

- **Context-Builder** — Code-Skeleton-as-TOC + zielgerichtete File-Slices
  (HMAC-signiert) statt ganze Dateien; kein Slice darf den Scope aus
  `architecture.json` ueberschreiten.
- **Sanitizer** — strippt PII, sekundaere Prompt-Injections und Geheimnisse
  aus jedem LLM-Input.
- **Patch-Parser** — der Output wird in `[DIFF]`-Bloecke geparst; unparsbare
  Antworten provozieren Retry, nicht Apply.
- **Secret-Scanner** — der Diff wird auf API-Keys, Tokens und Private-Keys
  gescannt; Treffer blockt den Apply (fail-closed).
- **Quality-Pipeline** — Lint und Type-Check pro Datei-Extension via
  `config/hooks.json`; Failure triggert `QualityRetry`.
- **Branch-Guard** — Code landet auf einem neuen Branch, niemals auf
  `main`/`master`.
- **Self-Healing-Loop** — bei Test-/Lint-Fehler wird das LLM mit dem konkreten
  Fehler erneut aufgerufen — mit hartem Token-Budget und Versuch-Limit.

### 3. Evaluation — Code → Score

Der erzeugte Code wird gegen die Akzeptanzkriterien aus dem Plan evaluiert.
**Vier Schranken**:

- **AC-Verifier** — `[DIFF]`, `[GREP]`, `[GREP:NOT]`, `[IMPORT]`, `[TEST]`,
  `[PYTEST]` werden maschinell geprueft.
- **Auto-Detected Test-Runner** — `pyproject.toml` / `package.json` /
  `go.mod` / `Cargo.toml` / `pom.xml`; passender Runner pro AC.
- **Gewichtetes Scoring** — Plan-Konformitaet, Test-Pass, Diff-Hygiene,
  Quality-Pass; Hard-Block-Schwellwerte aus `eval.json`.
- **Eval-History** pro Issue (Score-Trend ueber mehrere Runs, im Dashboard
  sichtbar).

### 4. PR-Gates — Score → PR

Vor dem Erstellen des Pull-Requests muessen **14 Gates** passieren —
konfigurierbar in `config/gates.json` als `required` / `optional` / `disabled`.
Highlights:

- Branch-Guard, Plan-Kommentar, Eval-Score ≥ Schwellwert
- **Scope-Guard** — kein `.env`, keine Secrets, kein Out-of-Scope-Diff
- **Slice-Gate** — Architektur-Isolation respektiert (kein Cross-Slice-Import)
- **AC-Verifier** — alle Akzeptanzkriterien bestanden
- **Destructive-Diff-Check** — Loeschungen ≤ 3× Hinzufuegungen

Erst wenn alle `required` Gates gruen sind, wird der PR erstellt — mit Plan,
Eval-Markdown und Audit-Link im PR-Body. Das Team reviewt einen sauberen,
maschinell vorgeprueften PR.

### Quer-Schranken (gelten in jeder Stufe)

- **Bus-Middleware** — Idempotency → Security → PromptGuard → Audit → Error →
  Metrics. Jeder einzelne Bus-Call durchlaeuft diese Kette.
- **Audit-Trail** — JSONL mit Correlation-IDs, OWASP-LLM-Risk-Codes und
  AI-Act-Mapping. Querybar nach Issue, Run, Risk.
- **Command-Safety** — `DROP TABLE`, `rm -rf`, `git push --force` werden
  blockiert.
- **HMAC-Signierung** — Webhook-Payloads (GitHub/Gitea) und Context-Slices
  zwischen Bus und Workern.

---

## Funktions-Uebersicht

> **Premium vs. Free:** Die meisten Features sind im Free-Mode vollstaendig
> nutzbar. Wo "Premium" steht, ist das eine optionale Erweiterung — der
> Free-Mode-Fallback wird in der Box jeweils benannt, damit klar ist, was
> man auch ohne Lizenz hat.

### Issue-zu-PR-Pipeline
Aus einem Gitea-/GitHub-Issue wird ein bewerteter Pull Request — voll-automatisch,
mit rund 30 technischen Schranken auf dem Weg.
- **Wofuer:** Das Team spart Stunden pro Issue. Boilerplate, Tests, Lint,
  Format und PR-Beschreibung laufen ohne Hand. Der Mensch reviewt nur den
  fertigen, vorgeprueften PR — nicht einen LLM-Rohzustand.
- *Free-Mode: vollstaendig.*

### Multi-Provider-LLM
8 Provider plug-and-play: **Ollama** und **LM Studio** lokal; **OpenRouter**,
**DeepSeek**, **Claude**, **Gemini** und **OpenAI** in der Cloud; **Manual**
als deterministischer Stub fuer Tests. Alle mit Circuit-Breaker und Sanitizer.
- **Wofuer:** Kein Vendor-Lock-in. Lokale Modelle fuer sensible Daten, Cloud
  fuer harte Tasks, kostenloses Manual fuer CI-Tests. Wenn ein Provider
  ausfaellt, oeffnet der Circuit-Breaker und der Fallback uebernimmt.
- *Free-Mode: vollstaendig — alle 8 Provider, Circuit-Breaker, Sanitizer.*

### Per-Task-Routing mit Tag/Nacht-Schedule — Premium
Pro Task-Typ (`plan`, `implement`, `review`, `eval`, `heal`, `changelog`,
`health`) ein eigenes Modell. Optionaler Schedule, der tagsueber Cloud-Modelle
und nachts lokale Modelle nutzt.
- **Wofuer:** Cost-Saving ohne Qualitaetsverlust. Ein 7B-Modell macht den Plan
  lokal, fuer das Code-Review wird Claude Sonnet aufgerufen, nachts laeuft
  alles auf Ollama. Token-Kosten sinken in der Praxis um Faktor 3–5.
- **Premium-Features:** `llm_routing` (Per-Task), `llm_routing_advanced`
  (Tag/Nacht-Schedule).
- *Free-Mode: ein gemeinsamer Provider aus `config/llm.json` fuer alle Tasks.
  Voll funktionsfaehig — die Routing-Layer optimiert nur Kosten, sie ist
  keine Voraussetzung.*

### Workflow-Engine
7 vordefinierte Workflows als JSON: `standard`, `watch`, `autonomous`, `chat`
(mit Plan-Approval-Schritt), `night`, `patch`, `self`. Jeder Workflow mappt
Events auf Commands; eigene Workflows ohne Code-Aenderung anlegbar.
- **Wofuer:** Passt zu jedem Team-Setup — vom strikt-kontrollierten Chat-Mode
  (Mensch genehmigt jeden Plan, bevor Code geschrieben wird) bis zur
  Nacht-Batch-Verarbeitung mit `concurrency: 3`.
- *Free-Mode: alle 7 Workflows verfuegbar; eigene Workflows beliebig anlegbar.*

### 14 PR-Gates
Bevor ein Pull Request entsteht, muessen 14 maschinelle Pruefungen passen:
Branch-Guard, Plan-Kommentar, Eval-Score, **Scope-Guard** (kein `.env`),
**Slice-Gate** (Architektur-Isolation), AC-Verifier, Destructive-Diff-Check, …
- **Wofuer:** Keine LLM-Suende kommt im Repo an. Selbst wenn das LLM
  halluzinieren wuerde, fangen die Gates es technisch ab. Required vs. Optional
  pro Gate konfigurierbar — strenger Setup fuer Production-Repos, lockerer fuer
  Spielwiesen.
- *Free-Mode: vollstaendig — alle 14 Gates, Required/Optional/Disabled-Wahl.*

### Akzeptanzkriterien-Verifier
Sechs Tag-Typen im Issue-Body: `[DIFF]`, `[GREP]`, `[GREP:NOT]`, `[IMPORT]`,
`[TEST]`, `[PYTEST]`. Der passende Test-Runner wird auto-detektiert (pytest,
jest, `go test`, `cargo test`, `mvn`).
- **Wofuer:** Das LLM kann nicht "fertig" behaupten ohne es maschinell zu
  beweisen. AC-Failure stoppt den PR oder triggert Self-Healing — kein
  Pseudo-Erfolg, der erst im Code-Review auffliegt.
- *Free-Mode: vollstaendig.*

### Self-Healing-Loop
Schlagen Tests oder Linter fehl, wird das LLM mit dem konkreten Fehler erneut
aufgerufen. Hartes Token-Budget und Versuch-Limit verhindern Endlosschleifen.
- **Wofuer:** Niemand muss bei einem trivialen Type-Error oder Lint-Warning
  einspringen. Der Agent korrigiert seine eigenen Fehler — bis das Budget
  greift, dann bricht er ab und meldet.
- *Free-Mode: vollstaendig (Versuch-Limit per Config). Optionales hartes
  Token-Cap ist Premium — siehe Token-Limit weiter unten.*

### Self-Mode — Selbst-Anpassung an die Umgebung
Eine Variante der Pipeline gegen das **eigene Repository** statt das Team-Repo:
laedt `.env.agent` overlayend, default-Workflow ist `self`, zusaetzlicher
Branch-Schutz (`--self run` darf nur auf `main` starten). Dieselben Schranken
wie auf einem Team-Repo, dieselbe Audit-Trail-Disziplin.
- **Wofuer:** S.A.M.U.E.L. passt sich an die Umgebung des Operators an, ohne
  dass jemand manuell coden muss. Issue erstellen, Workflow-Label setzen,
  der Agent baut die Aenderung ein und stellt einen PR bereit. Konkrete
  Anwendungsfaelle:
  - **Erweiterungen bauen** — neue LLM-Provider-Adapter (z.B. interner
    Konzern-Provider), neuer SCM-Adapter (z.B. GitLab), neuer
    Notification-Sink (Mattermost, Discord, internes Ticket-System).
  - **An die Systemlandschaft anpassen** — Audit-Format an existierende
    Log-Aggregatoren (Splunk, ELK) angleichen, Webhook-Signaturen an interne
    Standards anpassen, Reverse-Proxy-Setup-Snippets generieren.
  - **System-Anpassungen** — eigene Quality-Checks und PR-Gates fuer
    Team-Standards hinzufuegen, Workflow-Definitionen an interne Prozesse
    anpassen, neue Akzeptanzkriterien-Tags definieren.
  - **Routine-Wartung am Framework** — Doku-Updates, Refactorings,
    Bugfixes, Test-Erweiterungen — alles ohne dass das Engineering-Team
    Hand anlegen muss.
- *Free-Mode: vollstaendig.*

### Web-Dashboard
Eigenes Web-Frontend auf Port 7777 — kein zusaetzliches Monitoring-Tool noetig.

| Sektion | Inhalt |
|---------|--------|
| Status-Karten | Aktueller Modus, SCM-Verbindung, Premium-Lizenz-Status |
| Bus-Metriken | Pro Command/Event: Count, Errors, Avg-Latency |
| Health-Aggregation | Python, Config, SCM, LLM-Reachability, Disk, Audit-Sink |
| Workflow-Runs | History pro Issue mit Plan/Code/Eval-Status |
| System-Prompts-Browser | Alle 7 Prompts (planner, analyst, reviewer, healer, log_analyst, docs_writer, senior_python) einsehbar |
| LLM-Settings-Panel | Provider und Modell pro Task konfigurieren |
| Schedule-Section | Tag/Nacht-Routing einstellen |
| Test-Connection | Manueller Provider-Reachability-Check inkl. Balance-Abruf bei OpenRouter |
| Manueller Issue-Trigger | Plan oder Implement direkt aus dem Dashboard anstossen |

- **Wofuer:** Operator sehen in Echtzeit was passiert. Auto-Refresh alle 10 s.
  Kein Grafana, Prometheus oder Kibana noetig — alles ist eingebaut.
- *Free-Mode: alle Views, manueller Issue-Trigger, Test-Connection,
  System-Prompts read-only.*
- **Premium-Erweiterungen:** Edit-Modus fuer LLM-Settings
  (`llm_routing_dashboard_write`), Schedule-Section
  (`llm_routing_advanced`), System-Prompts-Editor (`system_prompts_edit`).
  Im Free-Mode sind diese Sektionen sichtbar, aber read-only — der Operator
  editiert dann direkt die Config-Dateien.

### REST-API
Saemtliche Dashboard-Funktionen sind auch ueber REST verfuegbar:

| Endpoint | Aktion |
|----------|--------|
| `GET /api/v1/dashboard/status` | Status + Metriken |
| `GET /api/v1/health` | Health-Check (Bearer) |
| `GET /api/metrics` | Prometheus-kompatibler Export (Bearer) |
| `POST /api/v1/issues/{id}/plan` | Plan-Generierung anstossen (Bearer) |
| `POST /api/v1/issues/{id}/implement` | Implementation anstossen (Bearer) |
| `POST /api/v1/scan` | Polling-Scan triggern (Bearer) |
| `POST /api/v1/webhook` | Gitea/GitHub-Webhook empfangen (HMAC-validiert) |

- **Wofuer:** Push-Integration via Webhook (kein Polling noetig); Prometheus-
  Endpunkt fuer existierendes Monitoring; CI-Trigger via REST; ChatOps-
  Integration ueber Bearer-Token.
- *Free-Mode: vollstaendig.*

### Audit-Trail mit OWASP- und AI-Act-Mapping
JSONL-Logging mit Correlation-IDs, **OWASP-LLM-Top-10-Risk-Codes** (LLM-01..10)
und **EU-AI-Act-Artikel-Mapping**. Asynchron mit Worker-Thread und
Fallback-Sink, damit kein Audit-Event verloren geht.
- **Wofuer:** Compliance und Forensik. Bei einem Pre-Audit oder einer
  Sicherheits-Untersuchung laesst sich jeder LLM-Call rekonstruieren — wer hat
  wann mit welchem Modell auf welche Regel reagiert. Querbar nach Issue, Run,
  Risk-Code.
- *Free-Mode: vollstaendig.*

### PII-Scrubbing und DSGVO-Tools
Drittland-Transfer-Check, **VVT-Generator** (Verzeichnis von
Verarbeitungstaetigkeiten), konfigurierbare Retention pro Datenart.
- **Wofuer:** Rechtssichere LLM-Nutzung in der EU. Sensible Daten werden vor
  dem Cloud-Call geschwaerzt; das VVT ist auf Knopfdruck erzeugbar; bei einer
  DSGVO-Anfrage liegt die Doku bereit.
- *Free-Mode: vollstaendig.*

### Token-Limit — Premium
Hartes Token-Budget pro Workflow-Run. Bei Ueberschreitung wird `TokenLimitHit`
publiziert und der Workflow sauber abgebrochen, bevor weitere Cloud-Kosten
entstehen.
- **Wofuer:** Schutz vor Cost-Spikes — etwa wenn ein Issue durch
  Self-Healing-Loops eine ungeplante Token-Menge verbraucht oder ein
  hallucinierender Plan grosse Kontext-Fenster anfordert.
- **Premium-Feature:** `token_limit`.
- *Free-Mode: kein hartes Cap, dafuer Per-Run-Token-Reporting im Audit-Trail
  (Operator kann nachtraeglich auswerten).*

### Premium-Slot — Zusammenfassung
Premium ist optional und durch Ed25519-Lizenz freigeschaltet. Verfuegbare
Features (siehe Markierungen oben):

| Feature-Flag | Was es freischaltet |
|--------------|--------------------|
| `llm_routing` | Per-Task-Provider-Wahl (TaskRoutingLLMAdapter) |
| `llm_routing_advanced` | Tag/Nacht-Schedule (ScheduledTaskRoutingAdapter) |
| `llm_routing_dashboard_write` | LLM-Settings im Dashboard editieren |
| `system_prompts_edit` | System-Prompts-Editor im Dashboard |
| `token_limit` | Hartes Token-Budget pro Run |

- **Wofuer:** Teams mit hohem Automatisierungs-Volumen koennen LLM-Kosten
  weiter optimieren und mehr Konfiguration ueber das Dashboard verwalten.
- **Wichtig:** **Alle Kern-Features bleiben im Free-Mode ohne Einschraenkung
  verfuegbar.** Premium deckt ausschliesslich die Entwicklungs- und
  Wartungskosten der Software (Apache-2.0-Open-Source).

---

## Schnellstart

Voraussetzungen: Python ≥ 3.10, ein Repo auf GitHub oder Gitea mit API-Token,
mindestens ein LLM-Provider (lokal oder Cloud).

```bash
git clone <repo-url>
cd S.A.M.U.E.L
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"

cp .env.example .env        # SCM_TOKEN + mind. einen LLM-Provider eintragen
python -m samuel health     # Sanity-Check
python -m samuel setup-labels    # Workflow-Labels auf GitHub/Gitea anlegen
python -m samuel run 42     # Issue #42 durch den Workflow schicken
python -m samuel watch      # Polling-Loop fuer alle gelabelten Issues
```

Das Team labelt ein Issue mit dem Workflow-Label (z.B. `agent:plan`), und
S.A.M.U.E.L. uebernimmt — entweder als Daemon (`watch`) oder als Service
(systemd/Docker, siehe `docs/README_technical.md` §20).

## CLI in Kurzform

```bash
samuel health                       # Health-Check (Python, Config, SCM, LLM)
samuel run <issue>                  # Einzelnes Issue durch den Workflow
samuel watch [--once] [--interval]  # Polling-Loop
samuel dashboard [--port 7777]      # Web-Dashboard + REST
samuel setup-labels                 # Workflow-Labels auf SCM anlegen
samuel refresh-pricing              # OpenRouter-Modell-Cache (350+ Modelle)
samuel changelog [--since|--phase]  # Changelog aus git log seit Tag/Phase
samuel --self <cmd>                 # Self-Mode (Agent bearbeitet eigenes Repo)
```

Alle Subcommands inkl. Flags und Praxis-Beispielen: siehe
`docs/README_technical.md` → §16 *CLI-Reference*.

---

## Weitere Dokumentation

- **`docs/README_technical.md`** — Architektur, Bus, Slices, Adapter, Premium,
  CLI-Reference, Dashboard-Reference, API-Endpoints, Deployment, Erweiterung.
- **`technische Beschreibungen/`** — 4 Pipeline-Tiefenbeschreibungen
  (Planning, Implementation, Evaluation, PR-Gates).
- **`docs/SAMUEL_ARCHITECTURE_V2.1.md`** — Zielarchitektur (18 Kapitel).
- **`docs/AI_ACT_COMPLIANCE.md`** + **`docs/DSGVO_VVT.md`** — Compliance-Doku.
- **`CONTRIBUTING.md`** — Slice-Regeln, Entwicklungs-Workflow.
- **`SECURITY.md`** — Schwachstellen-Meldewege.

## Lizenz

S.A.M.U.E.L. ist Open-Source unter der **Apache License 2.0** — frei nutzbar,
modifizierbar und in eigene (auch kommerzielle) Projekte integrierbar.

Die optionalen **Premium-Plug-ins** (`llm_routing`, `token_limit`) sind
kostenpflichtig und finanzieren die Weiterentwicklung. Der Free-Mode laeuft
mit allen Kern-Features ohne Einschraenkung — Premium ist ausschliesslich
dafuer da, die Entwicklungs- und Wartungskosten zu decken.
