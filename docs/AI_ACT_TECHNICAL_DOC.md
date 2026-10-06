# S.A.M.U.E.L. — Technische Dokumentation (EU AI Act)

> Gemaess Art. 11, Annex IV EU AI Act (VO 2024/1689)

**Stand:** 2026-08-27 (technischer Kontrollabgleich #517, Doku-Abgleich #485)

> Dieses Dokument unterstützt die technische Dokumentation eines konkreten
> Deployments; es ist weder eine Konformitätserklärung noch Rechtsberatung.
> Wirksamkeitsstatus und bekannte Lücken sind in der
> [Capability-/Wirksamkeitsmatrix](CAPABILITY_MATRIX.md) verbindlich
> ausgewiesen. Betreiber müssen Risikoklasse, Aktivierung und externe
> SCM-Kontrollen für ihre Installation selbst belegen.

---

## 1. Allgemeine Beschreibung (Annex IV Nr. 1)

**Name:** S.A.M.U.E.L. — Sicheres Autonomes Mehrschichtiges Ueberwachungs- und Entwicklungs-Logiksystem

**Zweck:** Automatisierte, kontrollierte Software-Entwicklung unter menschlicher Aufsicht. Das System nimmt Issues entgegen, generiert Plaene und Code via LLM, bewertet Ergebnisse und erstellt Pull Requests.

**Risikoklasse:** Limited Risk (Art. 50 — Transparenzpflichten)

**Nicht-Verwendung fuer:** Biometrie, kritische Infrastruktur, Beschaeftigungsentscheidungen, Strafverfolgung.

## 2. Architektur (Annex IV Nr. 2)

### 2.1 Systemarchitektur

Event-Driven Monolith mit Vertical Slices:

```
CLI / Webhook → Bootstrap → Bus (4 Middlewares) → WorkflowEngine
                                    ↓
                    ┌───────────────┤───────────────┐
                    ↓               ↓               ↓
              Planning-Slice  Implementation  Evaluation
                    ↓               ↓               ↓
              LLM-Provider    Patch-Parser    Score-Pipeline
                    ↓               ↓               ↓
              PR-Gates ←────────────┘───────────────┘
                    ↓
              Pull Request (mit AI-Attribution)
```

### 2.2 Kernkomponenten

| Komponente | Funktion | Dateien |
|-----------|----------|---------|
| Shared Kernel | Bus, Events, Commands, Config, Ports, State-, Retention-, Health-Projektions-, Workflow-Outcome-, Workspace-, LLM-Budget-, Review- und TEST-Runner-Verträge, Candidate-Prozessumgebung | `samuel/core/` (41 Python-Module einschließlich Paketmodul) |
| Feature Slices | Vertikale Funktionseinheiten | `samuel/slices/` (31 Slices) |
| Adapters | Externe Systeme (LLM, SCM, Audit, lokaler State, Git-Worktrees und gebundene Git-Transport-Authentisierung) | `samuel/adapters/` (13 Adapter-Gruppen) |
| Quality-Mechanismen | Gate 9: CPython-AST auf dem exakten Candidate-Head mit Toolversion; separater Working-Tree-Preflight nur im ausgelieferten `self`-Workflow | `samuel/slices/pr_gates/`, `samuel/adapters/quality/` |
| Skeleton-Builder | Fünf Builder für 11 Dateiendungen | `samuel/adapters/skeleton/` |

### 2.3 Middleware-Kette

Jeder Command/Event durchlaeuft 4 Middlewares:

1. **IdempotencyMiddleware** — Deduplizierung
2. **AuditMiddleware** — Protokollierung mit Correlation-ID
3. **ErrorMiddleware** — Exception-Handling
4. **MetricsMiddleware** — Latenz und Fehler-Zaehler

Security-Entscheidungen sind prüfgegenstandsnah verdrahtet: advisory
Prompt-Risikosignale an allen vier Worker-LLM-Pfaden, regelbezogen
blockierender/advisory Secret-Scan auf dem commitgebundenen Candidate-Diff und
Force-Push-/Reset-hard-Policy vor dem Core-Git-Subprozess.

## 3. Datenfluesse (Annex IV Nr. 3)

### 3.1 Issue → Plan

```
Gitea/GitHub Issue → IVersionControl → PlanIssueCommand
  → Prompt-Injection-Phrasensignal (advisory, auditiert)
  → PromptSanitizer (PII-Scrubbing)
  → Slice-lokale Prompt-Header (advisory)
  → ILLMProvider.complete()
  → PlanValidated / PlanBlocked
  → AuditEvent (mit prompt_hash, model_version)
```

### 3.2 Plan → Code

```
ImplementCommand → Context-Loading (Skeleton + Slices)
  → LLM-Loop (max 5 Runden)
  → PatchParser → PatchTargetResolver → PatchApplier
  → Commit + normaler Branch-Push
  → PRGatesHandler → aktives Required-Gate-Profil
  → GateEvaluationCompleted
      ├─→ passive, nicht bindende Evaluation/ScoreObserved
      └─→ kriteriumsweise Evidence-Healing-Klassifikation
  → PR (mit AI-Generated-By Trailer)
```

Die alten Typen und direkten Handler für `ScoreCommand → EvaluateCommand`
bleiben zum Lesen historischer Daten und für gezielte Kompatibilitätstests
vorhanden, sind aber weder im Bootstrap registriert noch in einem
ausgelieferten Workflow verdrahtet.

### 3.3 Daten an externe Systeme

| Empfaenger | Daten | Schutzmassnahme |
|-----------|-------|-----------------|
| LLM-Provider | Issue-Text (bei aktivierter Konfiguration begrenzt PII-bereinigt), Code-Kontext | PII-Scrubbing; Transport gemäß Betreiber-URL |
| SCM (Gitea/GitHub) | Commits, PR-Bodies, Kommentare | Token-Auth; TLS und Zertifikatsprüfung bei HTTPS |
| Dashboard | Rollenabhängige Status-, Audit-, Diagnose-, Operations- und Administrationsdaten; Viewer erhält nur passive, bereinigte Health-/Readiness-/Qualification-Projektionen | Genau ein Zugriffsmodus: Legacy-Key zur Migration oder lokaler Argon2-/Session-Provider; aktive Providerprobes benötigen `RUN_PROVIDER_PROBES`. Lokale Cookies sind HttpOnly/SameSite Strict und schreibende Requests CSRF-gebunden. Bind-Adresse, TLS und Netzsegmentierung bleiben Betreiberpflicht |
| Externer Documentation-Consumer | Geschlossene, digestgebundene Manifest-/Request-/Result-JSONs sowie exakte Markdownpfade und Metadaten; keine Credentials | Exakte Contractversion, Repository-/Head-/Policy-/Tool-/Coverage-/Artefaktbindung, erneute Git-Blob- und Secret-/Sensitive-Data-Prüfung und fester Advisory-Effekt; Producer erhält keine Publishercredentials und keine automatische Trust- oder Required-Aufwertung |

## 4. Risikomanagement (Annex IV Nr. 4)

### 4.1 Identifizierte Risiken

| Risiko | Mitigation |
|--------|-----------|
| LLM generiert unsicheren Code | Commitgebundene Gate-Auswertung; Prüftiefe und offene Blocker laut Capability-Matrix |
| PII in LLM-Prompts | Konfigurierbarer PII-Sanitizer (`pii_scrubbing.enabled=true`); begrenzte Regex-Abdeckung |
| Halluzinierte Funktionen | Hallucination-Guard via Skeleton-Abgleich |
| Unkontrollierte Aenderungen | Commitgebundene Gates; native Gitea-Branch-Protection sperrt auf der auditierten Instanz direkte/Force-Pushes und Branch-Löschung und erzwingt den exakten Head-Check; andere Installationen müssen dies per Doctor nachweisen |
| Externe, Git-administrative oder fachlich abgelehnte Dateisystemmutation | Vollständige Patchziel-Vorabprüfung; JSON- und sämtliche Python-Kandidaten einschließlich WRITE werden vor dem sichtbaren Write validiert. Ungültige Ziele/Inhalte blockieren ohne abgelehnten Zwischenstand (#600, #601, #603, #606) |
| Prompt-Injection | Neun normalisierte Phrasen-/Rollenmuster an Planning, Implementation, Healing und Review (advisory, auditiert); Header bleiben weich |

### 4.2 Restrisiken

| Risiko | Bewertung | Begruendung |
|--------|-----------|------------|
| LLM-Bias in Code-Stil | Niedrig | Code wird durch Gates + Eval geprueft |
| Begrenzte Secret-Erkennung | Mittel | Commitgebundener Diff-Scan blockiert hochpräzise Basisregeln einschließlich PEM; JWT/AWS-ID sind advisory. #520 liest ausschließlich SCM-Check-Facts; ein SARIF-/Fremdscanner-Ingest ist nicht implementiert |
| Provider-Ausfall | Mittel | Circuit-Breaker + expliziter Provider-Fallback; OpenAI-kompatible Fehler-/Malformed-Antworten werden begrenzt klassifiziert und Planning endet nach der Retrygrenze mit korreliertem `LLMUnavailable`/`PlanBlocked` |
| Lokale parallele Dateisystemmanipulation | Mittel | Patchziel- und Git-Control-Plane-Grenze binden den vom LLM gelieferten Pfad; Candidate-IMPORT/TEST erben keine Parent-Umgebung. Diese Kontrollen ersetzen keine Prozesssandbox gegen Hostdatei-, Prozess-, Netzwerk- oder Ressourcenwirkungen desselben OS-Benutzers |

## 5. Monitoring und Logging (Annex IV Nr. 5)

- **Audit-Trail:** JSONL mit Correlation-IDs, OWASP-Klassifikation
- **Runtime-Beobachtung:** SQLite-Schema v10 hält subjectgebundene Evaluation-
  Evidence, versionierte nicht bindende Ableitungen, redigierte Run-
  Projektionen sowie Claims, gebundene Checkpoints/Intents, Leases und die
  persistente Workflow-Tokenzulassung mit physischen Attempt-Reservationen.
  Epoch/Witness-/Sentinel-Abweichung wird als Reconcile sichtbar und blockiert
  Healing und Resume. Der unterstützte Restore erzeugt eine neue
  Autoritätslinie und verlangt einen vollständigen Operator-Reconcile über
  Claims, Intents, Checkpoints, Leases, Workspaces und bekannte SCM-Wirkungen.
  Außerhalb davon setzt der Resume-Koordinator ausschließlich
  sichere Finalisierungsgrenzen nach vollständiger Workspace-, Policy-, Git-
  und SCM-Prüfung fort; LLM-Runden bleiben nicht resumefähig. Auditrotation löscht diese Betriebssicht nicht;
  SQLite ersetzt den revisionsorientierten Audit-Trail nicht.
- **Planning-Klärung:** Explizite Lücken führen in höchstens zwei
  revisionsgebundene SCM-Runden mit endlicher Operatorfrist. Ein LLM erteilt
  keine Vollständigkeits- oder Freigabeauthority; die sichtbare Basis wird erst
  durch die bestehende menschliche Approval des exakten Plans verbindlich.
  Audit und Dashboard erhalten keine Frage-/Antworttexte.
- **Identity-Audit:** Loginfehler, Rate-Limit, Sessionrotation/-widerruf,
  Benutzer-/Rollenänderungen, Automation-Token, Bootstrap, Cutover und Recovery
  verwenden den vorhandenen Auditpfad mit Actor-ID und ohne Roh-Credentials.
- **Metriken:** Commands/Events pro Typ, Fehlerrate, Latenz
- **Dashboard:** Echtzeit-Status auf Port 7777; Workflow-Details unterscheiden
  automatische AC-PASS/FAIL-Zustände von `MANUAL PENDING`
- **Retention:** `eu_operational` ist der aktive Betriebsdefault; das
  rollenbezogene `eu_ai_act_high_risk_support` bleibt Opt-in. Schema v10 prüft
  26 State-Tabellen plus Audit, Workspaces und Quarantäne gegen explizite
  Zeitanker, Kalenderfristen, Feld-/Payloadklassifikation und Schutzgründe.
  Der Dry-Run und Score-Replay sind aktiv. Das operatorgeführte
  `score_derivations`-Ausführungsfundament ist vorhanden, aber alle
  ausgelieferten Kategorien bleiben `report_only`, die globale
  Notabschaltung ist aktiv und es gibt keinen Scheduler. Enforce-Grants binden
  Cutoff und Aktivierungszeit; der Vollzug revalidiert Katalog,
  Klassifikation und Kandidaten transaktional. Das ist keine
  AI-Act-Konformitätsaussage. Zehnjährige technische Unterlagen liegen
  außerhalb der Runtime-State-Retention.
- **Health-Check:** `samuel health` fuer System-Selbstdiagnose
  einschließlich SQLite-Schema und nicht blockierender Projection-Diagnose

## 6. Aenderungsprotokoll

| Datum | Aenderung |
|-------|-----------|
| 2026-08-30 | ADR-0482 Stufe 5c: Schema v6, persistente Kategorie-Autorität, plan-/epochgebundene Receipts und ausschließlich operatorgeführte `score_derivations`-Strategie deaktiviert ausgeliefert (#673); reale Aktivierung bleibt #668 |
| 2026-08-30 | ADR-0482 Stufe 5b: Schema v5, vollständiger Retention-Katalog, Dry-Run, Managed Backups und nebenwirkungsfreier Score-Replay umgesetzt (#667); Löschvollzug bleibt Stufe 5c |
| 2026-08-30 | ADR-0482 Stufe 5a: exklusiver Restore, neue Autoritätslinie, Schema v4 und vollständiger Reconcile umgesetzt (#666); Retention bleibt in 5b/5c offen |
| 2026-08-30 | ADR-0482-Stufe-5-Zielvertrag für exklusive Restore-Autoritätslinie, kategorieweise Retention und getrennten Vollzug dokumentiert; noch nicht implementiert |
| 2026-08-29 | Gebundenes Restart-Resume sicherer Finalisierungsgrenzen, Operatorstatus und fail-closed Drift-/Reconcile-Grenze abgeglichen (#633) |
| 2026-08-29 | Authority-State, Claim-Migration, Saga-Intents und Epoch/Witness/Reconcile gegen SQLite-Schema v3 abgeglichen; Resume bleibt deaktiviert (#629) |
| 2026-08-29 | Gebundene Evaluation-/Run-Projektion und Seriengrenzen gegen SQLite-Schema v2 abgeglichen (#627) |
| 2026-08-27 | Komponentenbestand gegen Code abgeglichen (#485) |
| 2026-04-17 | Erstversion — Phase 11 (Compliance) |
