# Verzeichnis der Verarbeitungstaetigkeiten (VVT)

> Gemaess Art. 30 DSGVO (VO 2016/679)

**Verantwortlicher:** Betreiber der S.A.M.U.E.L.-Instanz
**Stand:** 2026-08-29 (Runtime-State-Abgleich #627)

> Vorlage für den Betreiber, keine automatisch gültige Rechtsdokumentation.
> Aktivierung und Grenzen technischer Kontrollen stehen in der
> [Capability-/Wirksamkeitsmatrix](CAPABILITY_MATRIX.md). Zwecke,
> Rechtsgrundlagen, Empfänger, Verträge und Fristen müssen für das konkrete
> Deployment geprüft und angepasst werden.

---

## 1. Verarbeitungstaetigkeit: Issue-Analyse und Planungserstellung

| Feld | Inhalt |
|------|--------|
| Zweck | Analyse von Gitea/GitHub-Issues zur automatisierten Planerstellung |
| Rechtsgrundlage | Art. 6 (1f) — berechtigtes Interesse an Softwareentwicklungs-Automatisierung |
| Kategorien betroffener Personen | Issue-Ersteller, zugewiesene Entwickler |
| Kategorien personenbezogener Daten | Benutzername, Issue-Texte (koennen PII enthalten) |
| Empfaenger | LLM-Provider (gemaess `config/privacy.json → provider_locations`) |
| Drittland-Transfer | Abhaengig vom Provider — siehe Abschnitt 6 |
| Loeschfristen | Abhängig von der betroffenen Speicherkategorie. Das ausgelieferte Profil `eu_operational` wird durch `samuel retention dry-run` ausgewertet. Das 5c-Fundament ist vorhanden, aber alle Kategorien bleiben ausgeliefert `report_only`, der globale Stop ist aktiv und es gibt keinen Scheduler. Providerseitige Fristen bleiben ein separater Betreibervertrag |
| TOMs | Bei aktivierter Konfiguration begrenztes PII-Scrubbing von User-Nachrichten; TLS-Transport und Token-Auth deploymentabhängig |

## 2. Verarbeitungstaetigkeit: Code-Generierung via LLM

| Feld | Inhalt |
|------|--------|
| Zweck | Automatisierte Code-Generierung basierend auf Planvorgaben |
| Rechtsgrundlage | Art. 6 (1f) — berechtigtes Interesse |
| Kategorien personenbezogener Daten | Code-Kontext (kann Entwicklernamen, Kommentare enthalten) |
| Empfaenger | LLM-Provider |
| Drittland-Transfer | Abhaengig vom Provider |
| Loeschfristen | Nach Vertrag und Konfiguration des gewählten LLM-Providers; S.A.M.U.E.L. erzwingt dort keine Speicherfrist |
| TOMs | Kontextminimierung; konfigurierbares PII-Scrubbing. Die vier Worker-LLM-Pfade erzeugen bei begrenzten Prompt-Risikosignalen advisory Audit-Evidence ohne den rohen Input zu kopieren; Prompt-Header bleiben eine weiche Maßnahme und keine Injection-Garantie |

## 3. Verarbeitungstaetigkeit: Audit-Trail

| Feld | Inhalt |
|------|--------|
| Zweck | Nachvollziehbarkeit aller Agenten-Aktionen (Compliance, Debugging) |
| Rechtsgrundlage | Art. 6 (1c) — rechtliche Verpflichtung (EU AI Act Art. 12) |
| Kategorien personenbezogener Daten | Benutzernamen, Correlation-IDs, Event-Metadaten |
| Empfaenger | Nur lokal (JSONL-Datei) |
| Drittland-Transfer | Keiner (lokale Speicherung) |
| Loeschfristen | `eu_operational` konfiguriert Audit-JSONL mit `P1Y`. `samuel retention dry-run` verwendet den letzten parsebaren Event-Zeitstempel und schützt leere, beschädigte, partielle oder unlesbare Dateien. Für Audit-JSONL existiert keine Löschstrategie. `pii_anonymize_after_days` ist pensioniert und wird fail-closed abgelehnt; identifierbasierte Anonymisierung erfolgt weiterhin nur auf expliziten Aufruf |
| TOMs | Dateisystem-Berechtigungen des Deployments; Audit-HMAC nur bei gesetztem `SAMUEL_AUDIT_HMAC_KEY`; signierte lokale Mehrprozess-Appends benötigen POSIX-`flock`, beschädigte Tails werden nicht fortgeschrieben und Fallback-Dateien bleiben getrennte Ketten |

## 4. Verarbeitungstaetigkeit: Dashboard und Metriken

| Feld | Inhalt |
|------|--------|
| Zweck | Monitoring und Statusuebersicht fuer Betreiber |
| Rechtsgrundlage | Art. 6 (1f) — berechtigtes Interesse |
| Kategorien personenbezogener Daten | Aggregierte Qualitätsmetriken sowie redigierte Run-Metadaten; Actor-/Issue-Identifier können personenbezogen sein |
| Empfaenger | Dashboard-Nutzer (lokales Netzwerk) |
| Drittland-Transfer | Keiner |
| Loeschfristen | Schema v10 besitzt einen kategorieweisen Dry-Run-Vertrag und ein deaktiviert ausgeliefertes operatorgeführtes 5c-Fundament. Enforce-Grants binden Cutoff und Aktivierungszeit; vor Löschung werden Katalog, Klassifikation und Kandidaten transaktional revalidiert. Betriebsdefaults sind unter anderem `P1Y` für Rohbeobachtungen und `P90D` für Ableitungen/Run-Projektionen. Nur `score_derivations` besitzt zunächst eine Löschstrategie, ist ausgeliefert aber nicht aktiv. Quality-EWMA, Workflow-Budgetzulassungen/-Attempts, revisionsgebundene Planning-Klärungen, Legacy-Importmarker, Retention-Autorität/-Receipts und permanente Autoritäts-Tombstones bleiben ohne zeitbasierte Löschung |
| TOMs | Optionaler API-Key wird als expliziter Header statt als Cookie verwendet; Bind-Adresse, TLS und Netzwerk-Segmentierung muss der Betreiber absichern. Ein eigener CSRF-Token ist nicht implementiert |

## 5. Technische und organisatorische Massnahmen (TOMs)

| Massnahme | Beschreibung | Konfiguration |
|-----------|-------------|---------------|
| PII-Scrubbing | E-Mail, IP, Telefon, Kreditkarten werden vor LLM-Calls entfernt | `config/privacy.json → pii_scrubbing` |
| Retention-Policy | Maschinengeprüfter Katalog mit Zeitanker, ISO-Kalenderfrist, Spalten-/Payloadklassifikation, Schutzgründen und Digestbindung. Identity-Principals und Akteursfelder gelten konservativ als personenbezogen, Credential-/Session-/Tokenhashes als secret-bearing; sie sind lifecycle-gebunden und nicht für automatische zeitbasierte Löschung freigegeben. `eu_operational` ist ausgeliefert; `eu_ai_act_high_risk_support` ist rollenbezogenes Opt-in und keine Konformitätszusage. Notabschaltung, Reconcile, fehlende/stale Kategorie-Autorität und Plan-Drift blockieren. Es gibt keinen Scheduler; alle ausgelieferten Kategorien bleiben `report_only` | `config/privacy.json → retention`, `samuel retention dry-run --json`, ADR-0482, ADR-0422 |
| Drittland-Warnung | Dashboard zeigt bei `transfer_warning: true` (Default) Warnungen fuer Provider ausserhalb EU/EEA; `false` unterdrueckt nur die Warntexte, nicht Standort und `allowed`-Einstufung der API | `config/privacy.json → transfer_warning` |
| Transport-Verschluesselung | Bei HTTPS werden TLS und konfigurierbare Zertifikatsprüfung verwendet; Betreiber können auch andere URLs konfigurieren und tragen dann die Transportverantwortung | Deployment-/SCM-Konfiguration |
| Token-Authentifizierung | SCM- und LLM-Token als Umgebungsvariablen, nie im Code | `.env` |
| Candidate-Prozessminimierung | IMPORT-/TEST-Kindprozesse erben keine SCM-/LLM-/Cloud-/Signing-Credentials; ihr versioniertes Allowlist-Profil enthält nur neu gesetzte Betriebswerte. Gleiche Benutzerrechte und Host-/Prozesssicht bleiben bis zum separaten Sandbox-Vertrag eine Restrisiko-Grenze. | `samuel/core/process_environment.py`, AC-Evidence |
| Passive Candidate-Prüfung | Submission übernimmt nur Issue-Zuordnung und vollständigen Commit-SHA. Authority stammt aus bestehenden SCM-/Policyquellen; Event-/Dashboardprojektionen enthalten gebundene Identitäten und begrenzte Gründe, aber keine Candidate-Inhalte, Credentials oder frei gelieferten Authoritydaten. | `samuel candidate submit`, `Candidate*`-Events |
| Öffentlicher Extension-Datencontract | Der erste Documentation-Consumer erhält ausschließlich Repositorykennung, Head-/Policy-/Tool-/Artefaktdigests und eine exakt policygebundene statische Markdowninventur. Contractdateien enthalten keine Credentials; freie Prosa wird nicht als formale Evidence übernommen. Vor Publikation blockieren Secretformen, private Netzadressen und lokale Credentialpfade ohne Übernahme der Fundwerte in Evidence. Die Capability erzeugt keinen eigenen Runtime-State; nur das vorhandene lokale Publication-Receipt gilt nach der bestehenden Betreiber-Retention. | `config/extensions.json`, `samuel.extensions`, `samuel-documentation`, `docs/EXTENSION_CONTRACT.md` |
| Externe Candidate-Verifikation | Persistierter Request, Providerprofil, Run-/Attemptidentität, kriteriumsweise Status/Digests und begrenzte Gründe werden für Recovery, Audit und Gateentscheidung verarbeitet. Candidateprozesse erhalten weder Runtime-SCM-/LLM-/Signing-Secrets noch den Evidence-Integritätsschlüssel; Dashboard und Events enthalten diese Secrets ebenfalls nicht. | `config/execution.json`, `ProviderVerification*`-/`ProviderGateEvaluationCompleted`-Events |
| Prompt-Header | Zentral definierte, von vier Slice-Pfaden verwendete Instruktionen; keine technische Enforcement-Zusage | `samuel/core/security_policy.py` + Slice-Handler |
| Audit-Trail | Bus-Audit-Events mit Correlation-ID; keine Vollständigkeitszusage außerhalb emittierter Events | JSONL + OWASP-Klassifikation |
| Runtime-State | SQLite/WAL und Authority-Witness nur auf lokal klassifiziertem Dateisystem, Modus `0600`; Run-Projektion entfernt bekannte Secretfelder rekursiv. Das ist keine vollständige PII-Anonymisierung. Die Health-/Readiness-Projektion speichert nur Status, Instanz-/Zeit-/Digestbindung, feste Checknamen und begrenzte Zähler, keine Credentials, Providerantworten oder Auditpayloads. Planning-Klärungen speichern Frage-/Antworttext und Akteurbindung als `pii_bearing` nur im autoritativen State und sichtbaren SCM-Plan; Audit und Dashboard erhalten ausschließlich IDs, Digests, Runden und Status. Strukturierte, secret-bereinigte Reviewfindings werden sichtbar im SCM-Kommentar und Audit verarbeitet und können wie der geprüfte Code weiterhin Personenbezug enthalten. Der vollständige Review-Diff wird verarbeitet, im Auditpayload aber durch einen festen Platzhalter ersetzt; der Mergeintent speichert nur Issue-/PR-/Commit-/Subject-/Reviewbindung und keine Credentials. State-Diagnose und Restore-/Reconcile-Status geben keine Payloads aus; Legacy-JSON wird checksumgebunden und read-only archiviert. Schema v10 klassifiziert 26 State-Tabellen und JSON-Wurzeln konservativ und prüft den Katalog mechanisch. Managed Backups sind nur unter `managed_backup_dir` erfasst; externe Kopien bleiben Betreiberverantwortung. Das 5c-Fundament ist operatorgeführt und ausgeliefert deaktiviert. | `agent.data_dir`, `config/privacy.json`, ADR-0482 Stufen 3/5a/5b/5c, ADR-0693 |

## 6. Drittland-Transfer nach Provider

| Provider | Standort | Transfer | Schutzmassnahme |
|----------|----------|----------|-----------------|
| Ollama | Lokal | Keiner | — |
| LM Studio | Lokal | Keiner | — |
| DeepSeek | CN | Ja | SCCs erforderlich, Warnung im Dashboard |
| Claude (Anthropic) | US | Ja | EU-US Data Privacy Framework, DPA erforderlich |
| Gemini (Google) | US | Ja | EU-US Data Privacy Framework, DPA erforderlich |
| OpenAI | US | Ja | EU-US Data Privacy Framework, DPA erforderlich |
| OpenRouter | US-Gateway | Ja | DPA mit OpenRouter und Bewertung des jeweils nachgelagerten Modellanbieters |

Die maschinenlesbaren Schluessel in
`config/privacy.json::provider_locations` entsprechen exakt den Provider-IDs
aus `config/llm/providers.json`: `claude`, `deepseek`, `gemini`, `lmstudio`,
`ollama`, `openai`, `openrouter`. Fehlt fuer einen spaeter ergaenzten Provider
eine Standortangabe, erscheint er fail-safe als `unknown` mit Warnung im
Compliance-Tab, statt aus der Liste zu verschwinden.

**OpenRouter ist ein Gateway.** `US` bezeichnet konservativ den Standort der
Gateway-Verarbeitung und damit mindestens einen Drittland-Transfer. Der
tatsaechliche weitere Verarbeitungsort und die zusaetzlichen Empfaenger haengen
vom ausgewaehlten Modell ab. Vor produktiver Nutzung sind deshalb sowohl der
Vertrag mit OpenRouter als auch DPA/SCC/TIA des nachgelagerten Modellanbieters
zu pruefen; die pauschale Standortangabe ersetzt diese Einzelfallpruefung nicht.

## 7. DPA-Anforderungen pro Provider

Fuer jeden Cloud-Provider muss ein Data Processing Agreement (Art. 28 DSGVO) vorliegen:

- **Anthropic:** https://www.anthropic.com/policies/privacy — DPA auf Anfrage
- **Google Gemini:** Google Cloud Data Processing Addendum und eingesetzte
  Gemini-Dienstvariante pruefen
- **OpenAI:** https://openai.com/policies/data-processing-agreement
- **OpenRouter:** DPA des Gateways plus Bedingungen des durchgereichten
  Modellanbieters pruefen
- **DeepSeek:** Kein Standard-DPA verfuegbar — SCCs + TIA (Transfer Impact Assessment) erforderlich

**Hinweis:** Lokale Provider (Ollama, LM Studio) benoetigen kein DPA, da keine Daten das lokale System verlassen.
