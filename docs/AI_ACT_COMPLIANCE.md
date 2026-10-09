# S.A.M.U.E.L. — EU AI Act Compliance

> Bezug: EU AI Act (VO 2024/1689), in Kraft seit 01.08.2024.
> Letzte juristische Bereinigung: Issue #366 (Limited-Risk-Konsistenz).

> **Technischer Status 2026-08-27:** Dieses Dokument ist eine
> deploymentabhängige Orientierung, keine Konformitätserklärung oder
> Rechtsberatung. Ob ein genannter Mechanismus tatsächlich blockiert, warnt,
> misst oder deaktiviert ist, bestimmt die
> [Capability-/Wirksamkeitsmatrix](CAPABILITY_MATRIX.md). Die dort benannte
> First-Release-Baseline hat den technischen Status `ready`; das bezieht sich
> ausschließlich auf ihren namentlich begrenzten Kontrollsatz und ist weder
> eine Konformitäts- noch eine allgemeine Release-Reife-Erklärung.

Die gemeinsame Mapping-Schicht und der CRA-Querverweis sind in
[Compliance-Framework-Mappings](COMPLIANCE_FRAMEWORK_MAPPINGS.md) beschrieben.
Sie ändern den folgenden bestehenden Risikoklassen-/Attributionvertrag nicht.

## 1. Risikoklassifikation (Art. 6)

Die Risikoklasse haengt davon ab, **welches System** man betrachtet. SAMUEL ist
ein Framework, das in fremde Projekte eingesetzt wird, um deren LLM-Aktivitaet
zu ueberwachen. Es sind also zwei Systeme zu unterscheiden:

### 1.1 SAMUEL selbst (Self-Mode) — Limited Risk

Im Self-Mode beaufsichtigt der Agent **sich selbst**. SAMUEL ist dann ein
KI-gestuetztes Software-Entwicklungswerkzeug und faellt NICHT unter die
High-Risk-Kategorie (Annex III), da es:

- Keine biometrischen Daten verarbeitet
- Keine kritische Infrastruktur steuert
- Keine Beschaeftigungs- oder Kreditentscheidungen trifft
- Nicht in Strafverfolgung oder Migration eingesetzt wird

Einstufung: **Limited Risk**. Einzige rechtliche Pflicht: Art. 50 (Transparenz
fuer KI-generierte Inhalte, §2). Art. 12-15 adressieren nach Wortlaut der
Verordnung ausdruecklich Hochrisiko-KI-Systeme — fuer SAMUEL-im-Self-Mode sind
sie daher nicht verpflichtend (§3).

### 1.2 Das ueberwachte Host-Projekt — Risikoklasse des Hosts

Wird SAMUEL in ein fremdes Projekt eingesetzt, gilt fuer die Compliance dieses
Projekts dessen **eigene** Risikoklasse. Ist das Host-System ein
Hochrisiko-KI-System (Annex III: z.B. Kreditscoring, Medizin, Bewerber-
Screening, kritische Infrastruktur), dann sind Art. 9/12/13/14/15 fuer dieses
System **gesetzliche Pflicht** — und SAMUELs Mechanismen (Audit-Log → Art. 12,
Approval-Gates → Art. 14, Eval/Healing → Art. 15) sind dann die
technische **Unterstützungsinstrumente**. Sie erfüllen die Pflichten nicht
automatisch; der Betreiber muss Eignung, Konfiguration, Evidence und
Gesamtsystem separat bewerten.

### 1.3 Konsequenz fuer das Datenmodell

Ob ein Artikel **Pflicht** oder **freiwillig** ist, ist daher KEINE feste
Eigenschaft von SAMUEL, sondern wird zur Laufzeit abgeleitet:

```
obligation(Artikel) = required, wenn Deployment-Risikoklasse im
                       Adressatenkreis des Artikels liegt (applies_to),
                       sonst voluntary
```

- Die Deployment-Risikoklasse (`minimal_risk` | `limited_risk` | `high_risk`)
  loest sich nach Prioritaet auf: **env `SAMUEL_RISK_CLASS`** (expliziter
  Override fuer Container/CI) → **persistierter Dashboard-Wert** in
  `config/compliance.json` (`risk_classification`) → **Default `limited_risk`**
  (Self-Mode). Operatoren setzen die Klasse im **Compliance-Tab** des
  Dashboards (Dropdown unter der AI-Act-Tabelle); ist sie per env fixiert,
  zeigt das Dashboard den Selektor read-only mit Hinweis.
- Der Adressatenkreis je Artikel steht als `applies_to` in
  `samuel/core/compliance/ai_act.json` (Art. 50 → `all`, Art. 12-15 →
  `high_risk`).
- Die Ableitung liegt in `samuel.core.ai_act.obligation_for()`; der
  Compliance-Tab im Dashboard zeigt die aktive Risikoklasse und faerbt die
  Pflicht/freiwillig-Badges entsprechend.

Die folgenden §2/§3 beschreiben den **Self-Mode-Default** (Limited Risk).

## 2. Pflicht: Transparenz fuer KI-generierte Inhalte (Art. 50)

**Pflicht (Limited Risk):** Output, der von einem KI-System erzeugt wurde,
muss als kuenstlich erzeugt erkennbar sein.

**Erfuellung in SAMUEL:**

| Mechanismus | Bezug |
|---|---|
| `AI-Generated-By: <model>@<version>` Git-Trailer in jedem KI-generierten Commit | Maschinenlesbar fuer Reviewer und Audit-Tools |
| `LLMCallCompleted` mit `provider`, `model`, Token-/Kostenfeldern und expliziter Workflow-Korrelationsbindung | Worker-Aufrufe sind pro Issue/Run rückverfolgbar; Standalone-Aufrufe bleiben als ungebunden erkennbar (#675) |

**Implementierung:** `samuel.slices.privacy.ai_act.ai_attribution_trailer()`

Beispiel:

```
feat: Add retry logic for API calls

AI-Generated-By: ollama/codellama@latest
```

## 3. High-Risk-Standards — im Self-Mode freiwillig, im Hochrisiko-Deployment Pflicht

> **Disclaimer.** Die folgenden Massnahmen orientieren sich an Hochrisiko-
> Standards (VO 2024/1689 Art. 12-15).
>
> - Im **Self-Mode** (Limited Risk, Default `SAMUEL_RISK_CLASS=limited_risk`)
>   sind sie NICHT verpflichtend; SAMUEL wendet sie freiwillig an, weil sie
>   gute technische Praxis sind.
> - Wird SAMUEL in ein **Hochrisiko-Host-System** eingesetzt
>   (`SAMUEL_RISK_CLASS=high_risk`), werden genau diese Massnahmen fuer das
>   Host-System zu möglichen **Unterstützungsinstrumenten**. S.A.M.U.E.L.
>   liefert technische Evidenzbausteine (Audit-Log, Oversight, Robustheit); ob
>   diese genügen, muss der Betreiber separat nachweisen.
>
> Welcher Fall gilt, zeigt der Compliance-Tab im Dashboard ueber die aktive
> Deployment-Risikoklasse an.

### 3.1 Audit-Logging — analog zu Art. 12

| Mechanismus | Beschreibung |
|---|---|
| JSONL Audit-Trail | Jedes Event besitzt eine Ereignis-Korrelation; gebundene Workflowevents einschließlich Worker-`LLMCallCompleted` teilen dieselbe Run-Korrelation. Standalone-LLM-Aufrufe behaupten keine Run-Bindung (#675) |
| Retention | `eu_operational` setzt für Audit-JSONL `P1Y`; der Dry-Run ankert am letzten parsebaren Event-`ts`. `eu_ai_act_high_risk_support` ist rollenbezogenes Opt-in. Das 5c-Fundament ist ohne Scheduler, mit aktivem Stop und ausschließlich `report_only` ausgeliefert. Eine altersbasierte Löschung ist nur für die registrierte Strategie `score_derivations` technisch vorhanden und ausgeliefert nicht aktiviert. Weder Profil noch Dry-Run sind eine Konformitätszusage |
| PII-Anonymisierung | Expliziter Nutzer-Löschlauf ersetzt einen angegebenen Identifier. `pii_anonymize_after_days` ist im aktiven Schema pensioniert und wird fail-closed abgelehnt; Stufe 5b klassifiziert stattdessen jede State-Spalte und JSON-Wurzel für einen späteren kategorieweisen Vollzug |
| OWASP-Klassifikation | Security-Events mit OWASP-Top-10-Codes (siehe `samuel.core.owasp`) |
| Security-Evidence #474/#481 | `PromptInjectionRiskDetected` dokumentiert normalisierte Heuristiktreffer der vier Worker-LLM-Pfade advisory und ohne rohen Prompt; `GateFailed`/`GateEvaluationCompleted` binden blockierende Diff-Secret-Regeln an den Candidate-Subject, `SecretRiskDetected` bindet JWT-/AWS-ID-Signale advisory und wertfrei |
| Authority-State #629/#666 | `AuthorityReconcileRequired` macht UUID-/Epoch-/Witness-/Restore-Sentinel-Abweichungen für Audit und Notification sichtbar. Ein unterstützter Restore erzeugt eine neue Autoritätslinie und blockiert Healing/Resume bis zum vollständigen Reconcile. Autoritätsereignisse tragen ab `authority.v2` UUID und Epoch. Der Auditstrom ist dabei nur Zusatznachweis; DB, Lifecycle-Lock und synchroner Witness tragen die fail-closed Korrektheit. |
| Tamper-Evidenz (#333/#689) | Optionale HMAC-Chain-of-Hashes pro Audit-Zeile (env `SAMUEL_AUDIT_HMAC_KEY`). Lokale POSIX-Prozesse serialisieren Appends mit `flock` gegen den verifizierten Dateikopf; ein beschädigter Tail wird nicht fortgeschrieben. Verifikation via `samuel audit verify`; bei Bruch wird ein `IntegrityViolation`-Event publisht (sichtbar im Security-Tab). Fallback-Dateien sind getrennte Ketten und kein Vollständigkeitsnachweis für das Hauptlog. |

### 3.2 Human Oversight — analog zu Art. 14

| Mechanismus | Beschreibung |
|---|---|
| PR-Gate-Registry | 13 registrierte Funktionen; Required/Optional je Profil, tatsächliche Prüftiefe und Lücken laut Capability-Matrix |
| Diff-Secret-Gate | Immer aktives External Gate auf hinzugefügten Zeilen des vollständigen Base-/Head-Diffs; hochpräzise Basisregeln einschließlich PEM blockieren, JWT-/AWS-ID-Formen sind advisory |
| Plan-Review | LLM-generierte Plaene koennen vom Operator abgelehnt werden |
| Strukturierter Code-Review | `pass`, `block` und `indeterminate` sind an Subject, Diff, Policy, Tool und Prompt gebunden. Review ersetzt keine menschliche Planfreigabe; Auto-Merge bleibt default-off und verlangt frische Approval-/Required-/Head-Evidence |
| Gate-Konfiguration | Einzelne Gates per `config/gates.json` als required/optional/disabled |
| Watch-Slotgrenze | Der synchrone Watch-Scan dispatcht sequenziell mit `max_parallel=1`; höhere Configwerte blockieren. Der prozesslokale Slot koordiniert keine weiteren Prozesse |
| Watch-Mode | Manuell startbar, explizite Konfiguration |
| Self-Mode-Parität | Der Self-Workflow nutzt ein eigenes, explizites Gate-Profil, aber denselben gebundenen Freigabepfad; keine ungebundene Score-Sonderregel |

### 3.3 Robustheit / Genauigkeit — analog zu Art. 15

| Mechanismus | Beschreibung |
|---|---|
| Gebundene Qualitätsbeobachtung | Vollständige Gate-/Acceptance-Evidence wird Subject-/Policy-gebunden persistiert; die versionierte Score-Ableitung ist kein Freigabesignal |
| Required-Gate-Profil | Profilierte Required Gates entscheiden fail-closed über den Candidate; die ungebundenen früheren Gates 4/10 sind aus Registry und Profilen entfernt |
| Evidence-Healing | Genau ein kriteriumsweiser Gate-11-Versuch am fehlgeschlagenen Head; danach vollständiger Gate-Nachlauf oder menschliche Route |
| Passive Candidate Submission | Rekonstruiert Plan-/Approval-/Snapshot-/Policyauthority aus SCM und Control Plane; passiver Erfolg, Fehler und Provider-Warten sind getrennt sichtbar. Der Pfad erstellt keinen PR und besitzt keine Mutations- oder Healingauthority. |
| Gebundener Execution Provider | Persistiert Request und Dispatchabsicht vor der Wirkung, bindet Run/Attempt sowie kriteriumsweise Evidence und prüft aktive Plan-/Approval-/Subject-/Policyauthority vor Required-Nutzung erneut. Ausgeliefert bleibt das Profil bis zur realen D03-Qualification deaktiviert. |

### 3.4 Operator-Transparenz — analog zu Art. 13

| Mechanismus | Beschreibung |
|---|---|
| `LLMCallCompleted`-Felder | `task`, `provider`, `model`, Token-/Kosten-/Latenz-/Stop-Reason-Felder, optionale Budget-/Reasoning-Metadaten, `issue`, `correlation_id` und `workflow_correlation_bound`; Promptinhalt wird nicht in diese Telemetrie kopiert |
| Gate-/AC-Verifikation sichtbar | Operator sieht Gate-Entscheidung, Test-Ergebnisse, OWASP-Klassifikation und kriteriumsweise, an Repository/Base/Head/Contract/Policy gebundene Acceptance-Evidence. IMPORT/TEST weisen das sterile Environment-Profil aus, ohne eine Sandbox zu behaupten. Eine getrennte Score-Beobachtung ist ausdrücklich nicht bindend. `[MANUAL]` bleibt ohne exakten menschlichen SCM-Receipt `manual_pending`; Checkboxen und LLM-Urteile gelten nicht als Nachweis. |
| Passive Candidate-Ausgänge | Dashboard und Audit unterscheiden `CandidateVerificationPending`, `CandidateEvaluationCompleted`, `CandidateEvaluationFailed` und `CandidateSubmissionRejected`. Alle tragen EvaluationSubject beziehungsweise einen begrenzten Ablehnungsgrund und ausdrücklich `mutation_authority: none`. |
| Provider-Ausgänge | Dashboard und Audit unterscheiden angefordert, wartend, trust-seitig blockiert und kriteriumsweise ausgewertet. Request-Key, Profil, Run und Attempt sind sichtbar; Schlüssel, Token, Candidate-Inhalte und rohe Providerantworten werden nicht projiziert. |
| Robustheit der Patchanwendung | Der Referenz-Worker prüft alle Patchziele einer Modellantwort vor dem ersten Write und blockiert absolute, traversierende, per Symlink externe sowie `.git`-/effektive Git-Control-Plane-Ziele mit inhaltsfreier Evidence. Dies begrenzt die vom LLM adressierbare Dateisystemwirkung, ist aber keine allgemeine Prozesssandbox. |
| Mutationsfreie fachliche Patchablehnung | JSON-Kandidaten werden schreibfrei aufgebaut und vor dem sichtbaren Write validiert; ein abgelehnter Patch verändert weder Retry-Quelle noch relevante Dateimetadaten. Während eines begonnenen OS-Writes auftretende I/O-Fehler bleiben eine getrennte Loop-Transaktionsgrenze. |
| Python-WRITE-Robustheit | Vollständige Python-Inhalte verwenden vor Verzeichnisanlage und Write denselben AST-Hook wie partielle Python-Patches. Unveränderte vorsorgliche Snapshots werden verifiziert freigegeben, damit ein terminaler Rollback keine Metadaten neu schreibt; Gate 9 prüft später den exakten Candidate-Blob commitgebunden. |

**Implementierung:** `samuel.adapters.llm.metering.MeteringLLMAdapter` und
`samuel.core.issue_context`; der getrennte Helper
`samuel.slices.privacy.ai_act.enrich_llm_event_payload()` ist keine Behauptung,
dass jedes optionale Attributionsfeld im aktiven Metering-Pfad vorhanden ist.

## 4. DSGVO-Querverweis (kein AI-Act, separate Schiene)

Wenn SAMUEL personenbezogene Daten in Issues/Commits verarbeitet, sind die
DSGVO-Pflichten unabhaengig vom AI Act zu erfuellen:

- **Art. 5 DSGVO** (Speicherbegrenzung) — der konfigurierte 30-Tage-Wert ist
  eine Betreiberpolicy, derzeit keine automatisch durchgesetzte Frist
- **Art. 22 DSGVO** (automatisierte Entscheidung im Einzelfall) — relevant
  nur wenn SAMUEL ohne menschliche Pruefung Entscheidungen trifft, die
  Personen rechtlich oder erheblich beeintraechtigen. Mehrere ausgelieferte
  Workflows erstellen nach technischer Prüfung ohne Planfreigabe einen PR;
  Human Oversight und die rechtliche Bewertung müssen deshalb im konkreten
  Deployment einschließlich Merge-Policy nachgewiesen werden.
- **VVT** — siehe `docs/DSGVO_VVT.md`

**Wichtig:** Art. 86 EU AI Act (Recht auf Erlaeuterung im Einzelfall) gilt
ausschliesslich fuer Hochrisiko-Systeme nach Anhang III. Fuer SAMUEL ist
Art. 86 NICHT einschlaegig. Frueher zitierte Stellen wurden mit #366
korrigiert.

## 5. Migrations-Notiz

Vor Issue #366 hat diese Doku Art. 12, 14, 15 und 86 als "Pflicht" /
"bereits erfuellt" etikettiert. Das war juristisch nicht haltbar — diese
Artikel adressieren ausschliesslich Hochrisiko-KI-Systeme. Die
technischen Mechanismen sind unveraendert vorhanden, ihre Etikettierung
ist jetzt korrekt: freiwillige Anwendung statt Pflichterfuellung.

Mit #366 trug jeder Artikel in `samuel/core/compliance/ai_act.json` ein
statisches Feld `obligation` (`required`/`voluntary`). Das war aber an die
Annahme "SAMUEL ist immer Limited Risk" gekoppelt und blendete den eigentlichen
Einsatzzweck aus (SAMUEL ueberwacht fremde, teils hochriskante Projekte).

Mit **#373** wurde das statische `obligation` ersetzt durch `applies_to` (den
Adressatenkreis je Artikel). Die effektive Pflicht/freiwillig-Einstufung wird
zur Laufzeit aus `applies_to` + der Deployment-Risikoklasse (`SAMUEL_RISK_CLASS`,
Default `limited_risk`) abgeleitet — siehe §1.3. Der Self-Mode-Default bleibt
unveraendert: Art. 50 Pflicht, Art. 12-15 freiwillig.
