# S.A.M.U.E.L. Capability-/Wirksamkeitsmatrix

> Diese Datei wird aus `docs/capabilities/control-matrix.json` erzeugt.
> Code und ausgelieferte Konfiguration bleiben die Quellen für Verhalten und
> Aktivierung; die Matrix ist die Quelle für Bewertung und öffentliche Claims.

**Auditdatum:** 2026-09-29
**Geprüfter Ausgangscommit:** `41340e75e0acc918fbc577653c3bedfec0f70aaa`
**Geprüfter Quelldigest:** `sha256:b16761df763612f1888cc2593120885a960420cdf9fe6e4d498506eb5ed7a836`
**Schema:** `1.0`

## Statusmodell

`lifecycle` beschreibt Existenz und Reife. Die effektive Wirkung wird getrennt
je realem Profil oder Pfad als `enforced`, `advisory`, `telemetry`, `disabled`
oder `not_applicable` geführt. Ein registrierter oder als `required`
konfigurierter Name ist deshalb noch kein Wirksamkeitsnachweis.

## Reale Referenzqualification

Profil-ID: `internal-d0` · Authority-Issue: #658 · Status: **partial** · Qualifizierter Release: **keiner**

Die Proofs der Einzelkontrollen sind automatisierte Code-/Integrationsnachweise. Die reale Qualification bewertet zusätzlich genau eine externe Installation und einen vollständigen Paket-/Image-zu-PR-Lauf; beide Aussagen werden nicht miteinander gleichgesetzt.

| Belegklasse | Stand |
|---|---|
| Real beobachtet | separate Paketinstallation sowie Teilpfade von Runtime-Start, CLI, Doctor und Dashboard; reale Planning-/Freigabeteilpfade und echte Blockierergebnisse; reale Candidate-Erzeugung im getrennten Demo-Repository mit gebundener menschlicher Freigabe; nachgelagerter TEST-Vertragsfehler blockierte vor PR; v2.0.0a8 aus veröffentlichtem OCI-Digest gestartet; erster Zielrepository-Lauf vor Planning wegen fehlender Git-Runtime reproduzierbar blockiert; v2.0.0a9 mit grüner Tag-CI, vier hashgeprüften Releaseassets, Git 2.47.3 und gesundem digestgebundenem Compose-Smoke veröffentlicht; D0-Nachlauf belegte #690 und #756; v2.0.0a10 mit grüner Tag-CI #763, vier erneut byteidentisch geprüften Releaseassets, Git 2.47.3, getrennter Publisherrolle und gesundem digestgebundenem Compose-Smoke veröffentlicht; D0-Golden-Plan belegte danach den widersprüchlichen Runner-Prompt; v2.0.0a11 mit grüner Tag-CI #770, vier byteidentisch geprüften Releaseassets, gesundem digestgebundenem Compose-Smoke und frischer unabhängiger Installation veröffentlicht; Runtime-/Provider-/Readinesspfade und echter diff_secret_scan-Block bestanden; Golden-Pfad wegen Approval-/Re-Plan-Drift #767 vor Candidate gestoppt; v2.0.0a15 mit grüner Tag-CI #793, vier byteidentisch geprüften Assets, Git 2.47.3 und gesundem digestgebundenem Compose-Smoke veröffentlicht; frische Installation, Runtime-, Provider-, Auth-, Audit-, Neustart- und Dashboardpfade bestanden; Demo-#57 lief nach menschlicher Freigabe über gebundenen Candidate, Required Gates, PR #59 und PR-CI #794, wurde entgegen der D0-Bedingung aber durch demo-example-bot statt einen Menschen gemergt; Demo-#58 wurde durch diff_secret_scan ohne PR oder damalige main-Änderung blockiert; PlanReplanRejected blieb terminal blockiert und bewahrte Plan, Vertrag und status:plan unverändert; v2.0.0a19 mit grüner Tag-CI #878, vier hashgebundenen Releaseassets, manifestgebundenem OCI-Digest und gesundem frischem Compose-Smoke veröffentlicht; keine D0-Installation, kein Golden- oder Blockierpfad wurde in diesem Release-Lauf ausgeführt; v2.0.0a20 und v2.0.0a22 blieben fehlgeschlagene Publishversuche mit falscher OCI-Source-Bindung; kein Release wurde daraus abgeleitet; v2.0.0a23 belegte Product-Source-OCI-Publish und Compose-Smoke; ein vollständiger Gitea-Package-Publish ist nicht belegt; v2.0.0a24 wurde mit Tag-CI #909, Gitea-Prerelease #38, vier Releaseassets und manifestgebundenem OCI-Digest veröffentlicht; der D0-Lauf blieb unvollständig und begründet weder Qualification noch Support; v2.0.0a25 wurde mit Tag-CI #928, Gitea-Prerelease #39, vier remote hashgeprüften Releaseassets, korrekter Produkt-Source, manifestgebundenem linux/amd64-OCI-Digest und grünem ersten Required Smoke veröffentlicht; Golden-D0 und Capabilityqualifications wurden nicht ausgeführt und der Publish begründet weder Qualification noch Support |
| Für Qualification fehlt | vorgeschriebener menschlicher Merge des gebundenen Golden-Path-PR; vollständiger frischer D0-Lauf gegen einen neu veröffentlichten unveränderlichen Release |
| Bekannte Findings | #690, #691, #692, #693, #694, #697, #701, #706, #711, #712, #713, #714, #727, #735, #752, #754, #756, #759, #767, #772, #776, #808, #822, #828, #829, #830, #835, #838, #843, #844, #845, #846, #847 |

## First-Release-Baseline

Profil-ID: `reference-worker-first-release` · Status: **ready** ·
Die Produktversionspolitik #487, konsistente Versionsflächen #489, Release-Gates #490 und die tagbasierte Authority #488 sind umgesetzt; die Dachabnahme #479 ist abgeschlossen. `v2.0.0a1` blieb nach roter Tag-CI unveröffentlicht; das veröffentlichte `v2.0.0a2` ist der strikte SCM-Anker. Exakte Tags, Dev-/Dirty-Stände, Phase-Tag-Ausschluss, sdist/wheel und der metadatenlose Nicht-Release-Fallback sind automatisiert geprüft.

| Kontroll-ID | Kontrolle | Bereitschaft | Blocker |
|---|---|---|---|
| `PROC-ACCEPTANCE-CONTRACT` | Freigegebener strukturierter Acceptance Contract | **ready** | — |
| `PROC-EVALUATION-SUBJECT` | Unveränderlicher Candidate-Prüfgegenstand | **ready** | — |
| `SEC-DIFF-SECRET-SCAN` | Commitgebundener Diff-Secret-Scanner | **ready** | — |
| `PRG-07B` | ContractScope | **ready** | — |
| `EXT-PATH-RISK` | Konfigurierbarer Pfad-Risikoklassifikator | **ready** | — |
| `PRG-08` | SliceGate | **ready** | — |
| `PRG-09` | PythonSyntax | **ready** | — |
| `SEC-INSTALLED-CLI-ENTRYPOINT` | Installierter Console-Entry-Point als Prozessherkunft | **ready** | — |
| `SCM-REQUIRED-HEAD-CHECK` | Gitea Required CI Check am PR-Mergepunkt | **ready** | — |
| `SCM-DIRECT-PUSH-PROTECTION` | Schutz vor normalen direkten Pushes auf main | **ready** | — |

## Input und Kontext

| ID | Präziser Ist-Name | Lifecycle | Tatsächliche Wirkung | Folgeissue |
|---|---|---|---|---|
| `INPUT-CONTEXT-SELECTION` | Keyword-, Plan- und Symbol-basierte Kontextauswahl | implemented | reference-worker: enforced | — |
| `INPUT-CONTEXT-VALIDATION` | Pre-LLM Context-Größen- und Präsenzprüfung | implemented | reference-worker: enforced | — |
| `INPUT-PII-SANITIZER` | Konfigurierbarer PII-Prompt-Sanitizer | implemented | pii_scrubbing.enabled=true: enforced; pii_scrubbing.enabled=false-or-missing: disabled | #474, #481 |
| `INPUT-PROMPT-GUARD-HEADER` | Zentrale Prompt-Guard-Header der Worker-Slices | implemented | reference-worker-llm-prompts: advisory | #474, #481, #485 |
| `INPUT-PLAN-VALIDATION` | Struktur- und Skeleton-basierte Planvalidierung | implemented | reference-worker-planning: enforced | #575, #655, #714, #735, #902 |
| `INPUT-PLAN-PRECHECK` | Plan-Pre-Check und Komplexitätssignal | implemented | reference-worker-planning: enforced; complexity-only: advisory | #575, #655, #735, #742, #902 |
| `SEC-PROMPT-INJECTION-SIGNAL` | Normalisiertes Prompt-Injection-Risikosignal | implemented | reference-worker-llm-prompts: advisory | #474, #481, #485 |
| `SCM-WEBHOOK-HMAC` | Optionale Webhook-HMAC-Verifikation | implemented | SLICE_HMAC_KEY=set: enforced; key-missing: disabled | — |
| `INPUT-BOUND-CLARIFICATION` | Revisionsgebundener Planning-Klärungsdialog | implemented | explicit-issue-gap-with-finite-wait: enforced; clear-issue: not_applicable | #575 |

## Ausführung

| ID | Präziser Ist-Name | Lifecycle | Tatsächliche Wirkung | Folgeissue |
|---|---|---|---|---|
| `EXEC-PATCH-APPLY` | Strukturierter Patch-Parser und dateitypbezogener Applier | implemented | reference-worker: enforced | #601, #606 |
| `EXEC-IMPLEMENTATION-WORKSPACE-TRANSACTION` | Atomarer Workspace des Implementation-LLM-Loops | implemented | reference-worker-implementation-loop: enforced | #482, #549, #598 |
| `SEC-IMPLEMENTATION-PATCH-TARGET-BOUNDARY` | Projektwurzel- und Git-Control-Plane-gebundene Patchziele | implemented | reference-worker-implementation-loop: enforced | #600, #603 |
| `EXEC-TOKEN-OUTPUT-BUDGET` | Provider- und taskbezogenes LLM-Ausgabebudget | implemented | active-llm-chain: enforced | #744 |
| `AUTH-WORKFLOW-TOKEN-BUDGET` | Persistente kumulative Tokenzulassung je Workflowauftrag | implemented | issue-bound active LLM chain: enforced | #549, #884 |
| `EXEC-LLM-RETRY` | Konfigurierter Retry für transiente Providerfehler | implemented | retry.enabled=true: enforced; retry.enabled=false: disabled | #698, #701, #744 |
| `EXEC-LLM-FALLBACK` | Geordneter LLM-Provider-Fallback | implemented | configured-fallback-list: enforced; no-fallback: not_applicable | — |
| `EXEC-CIRCUIT-BREAKER` | LLM-Provider Circuit Breaker | implemented | active-llm-chain: enforced | — |
| `MW-IDEMPOTENCY` | Bus-Idempotenz-Deduplizierung | implemented | bus-messages-with-key: enforced | — |
| `SEC-COMMAND-SAFETY` | Aktionsnahe destruktive Core-Git-Policy | implemented | samuel-core-git: enforced | #474, #481 |
| `PROC-CANDIDATE-ENVIRONMENT` | Sterile Candidate-Prozessumgebung | implemented | candidate-import-and-test: enforced | #613 |
| `PROC-BOUND-HEALING` | Einmaliges Healing aus gebundener Acceptance-Evidence | implemented | runtime: enforced | #399, #485, #581, #620, #629, #521 |
| `PROC-WORKTREE-LIFECYCLE` | Gemeinsamer Git-Worktree-Lifecycle für Run und Verifikation | implemented | implementation-and-gate11: enforced | #482, #603, #618, #619, #714, #727, #729, #739 |
| `PROC-BOUND-FINALIZATION-RESUME` | Gebundene Finalisierung nach Prozessneustart | implemented | bootstrap-watch-operator: enforced | #482, #618, #633, #666 |
| `SEC-INSTALLED-CLI-ENTRYPOINT` | Installierter Console-Entry-Point als Prozessherkunft | implemented | installed-console-script: enforced; generated-systemd-unit: enforced; runtime-container: enforced; python-module-from-untrusted-working-directory: disabled | #583 |

## Artefakt und Commit

| ID | Präziser Ist-Name | Lifecycle | Tatsächliche Wirkung | Folgeissue |
|---|---|---|---|---|
| `PRG-05` | DiffNotEmpty | implemented | gate-profile:default: advisory; gate-profile:self: advisory; gate-profile:audit: enforced | #515 |
| `PRG-06` | SelfConsistency | experimental | gate-profile:default: advisory; gate-profile:self: advisory; gate-profile:audit: enforced | #517 |
| `PRG-07` | ForbiddenPathGuard | implemented | gate-profile:default: enforced; gate-profile:self: enforced; gate-profile:audit: enforced | #474, #485 |
| `PRG-07B` | ContractScope | implemented | gate-profile:default: enforced; gate-profile:self: enforced; gate-profile:audit: enforced | #485, #529 |
| `PRG-08` | SliceGate | implemented | gate-profile:default: enforced; gate-profile:self: enforced; gate-profile:audit: enforced | — |
| `PRG-09` | PythonSyntax | implemented | gate-profile:default: enforced; gate-profile:self: enforced; gate-profile:audit: enforced | #518 |
| `PRG-13A` | BranchFreshness | implemented | gate-profile:default: advisory; gate-profile:self: advisory; gate-profile:audit: enforced | #468 |
| `PRG-13B` | DestructiveDiff | implemented | gate-profile:default: enforced; gate-profile:self: enforced; gate-profile:audit: enforced | — |
| `EXT-PATH-RISK` | Konfigurierbarer Pfad-Risikoklassifikator | implemented | level=block: enforced; level=warn: advisory | #474 |
| `EXT-SYMBOL-RESOLUTION` | Python-Import-Symbolauflösung | experimental | all-gate-profiles: telemetry | #520 |
| `EXT-COVERAGE-DIFF` | Coverage-Dateipräsenz-Hinweis | experimental | all-gate-profiles: telemetry | #518 |
| `SEC-DIFF-SECRET-SCAN` | Commitgebundener Diff-Secret-Scanner | implemented | all-create-pr-workflows:blocking-rules: enforced; all-create-pr-workflows:jwt-and-aws-id: advisory | #474, #481 |
| `QUAL-LOCAL-EVIDENCE` | Self-Workflow lokaler Quality-Preflight | implemented | workflow:self: enforced; other-shipped-workflows: not_applicable | #441, #518 |

## Prozess und Vertrag

| ID | Präziser Ist-Name | Lifecycle | Tatsächliche Wirkung | Folgeissue |
|---|---|---|---|---|
| `PRG-01` | BranchGuard | implemented | gate-profile:default: enforced; gate-profile:self: enforced; gate-profile:audit: enforced | #124 |
| `PRG-02` | PlanComment | implemented | gate-profile:default: enforced; gate-profile:self: enforced; gate-profile:audit: enforced | #519 |
| `PRG-11` | ACVerification | implemented | gate-profile:default: enforced; gate-profile:self: enforced; gate-profile:audit: enforced | #519, #612, #613, #620 |
| `PRG-12` | AcceptanceReadiness | implemented | gate-profile:default: advisory; gate-profile:self: advisory; gate-profile:audit: enforced | #519 |
| `PROC-ACCEPTANCE-CONTRACT` | Freigegebener strukturierter Acceptance Contract | implemented | create-pr: enforced | #519, #529, #714, #731, #754 |
| `PROC-EVALUATION-SUBJECT` | Unveränderlicher Candidate-Prüfgegenstand | implemented | all-create-pr-workflows: enforced | #515 |
| `PROC-PASSIVE-CANDIDATE-SUBMISSION` | Passive Prüfung eines bestehenden Git-Candidates | implemented | operator-candidate-submit: enforced | #521, #679 |
| `PROC-BOUND-EXECUTION-PROVIDER` | Gebundene externe Candidate-Verifikation | experimental | explicit-candidate-request: disabled; reference-worker-create-pr: disabled | #520, #521, #679 |
| `PROC-PR-HEAD-REVALIDATION` | PR-Head-Revalidierung vor Evidence und Auto-Merge | implemented | pr-created: enforced; gitea-expected-head-auto-merge: enforced | #515, #468 |
| `PROC-BOUND-REVIEW-MERGE` | Strukturierter Reviewentscheid und erwarteter-Head-Merge | experimental | structured-review-standard-autonomous: enforced; auto-merge-default: disabled; expected-head-qualification-default: disabled; gitea-native-expected-head: enforced | #468, #869 |
| `PROC-HUMAN-PLAN-APPROVAL` | Workflowabhängige menschliche Planfreigabe | implemented | standard/watch/self/chat: enforced; autonomous/night/patch-clear-issue: not_applicable; autonomous/night/patch-clarified-plan: enforced | #519, #575, #582, #695, #713, #754, #767, #895 |
| `PROC-WATCH-OUTCOME` | Fail-closed Watch-Dispatch-Ergebnis | implemented | watch-scan-and-once-exit: enforced | #696 |
| `PROC-AC-VERIFIER` | Tagbasierter ACVerificationHandler | implemented | planning-dry-run: advisory; create-pr: enforced | #399, #519, #612, #613, #620, #713, #756 |
| `PROC-AUTHORITY-PROFILE` | Gebundene Gate-Profilauflösung | implemented | standard:default-or-audit: enforced; self:self: enforced | #399, #579 |
| `STATE-AUTHORITY-PERSISTENCE` | Transaktionaler lokaler Autoritätszustand mit Restore-Witness | implemented | runtime-state: enforced | #482, #629, #633, #666 |
| `OPS-ATOMIC-LOCAL-RELEASE` | Manifestgebundene lokale Release-Aktivierung | implemented | local-wheel-release: enforced; development-editable-install: not_applicable; oci-release: not_applicable | #706, #658 |
| `SCM-REQUIRED-HEAD-CHECK` | Gitea Required CI Check am PR-Mergepunkt | implemented | audited-gitea-pr-merge: enforced; other-installations: not_applicable | #441, #518, #694 |
| `SCM-DIRECT-PUSH-PROTECTION` | Schutz vor normalen direkten Pushes auf main | implemented | audited-gitea: enforced; other-installations-before-doctor-proof: disabled | #124, #528, #694 |
| `OPS-CONFIGURATION-FREEZE` | Expliziter Operator-Konfigurationsmodus und Produktions-Freeze | experimental | dashboard-production: enforced; operator-setup-process: enforced | #691, #823 |
| `SEC-LOCAL-DASHBOARD-IDENTITY` | Lokaler Dashboard-Identity-Provider mit explizitem Cutover | experimental | shipped-legacy-migration-mode: enforced; local-identity-after-explicit-cutover: disabled | #422 |
| `OPS-HEALTH-READINESS-SEPARATION` | Passive instanzgebundene Health-, Readiness- und Qualification-Projektion | experimental | dashboard-viewer-and-passive-health: enforced; active-dashboard-self-check: enforced; real-deployment-qualification: disabled | #693 |
| `OPS-GITEA-PUBLISHER-BOUNDARY` | Dedizierter persönlicher Gitea-Publisher mit create-only Postcondition | experimental | gitea-publisher-preflight: enforced; create-only-oci-publish: enforced; interrupted-oci-release-recovery: enforced; runtime-scm-credential-fallback: disabled; real-release-host-qualification: disabled | #759 |
| `EXT-PUBLIC-DATA-CONTRACT` | Versionierter öffentlicher Extension-Datenvertrag | implemented | shipped-default-or-optional-absent: disabled; explicitly-enabled-compatible-consumer: advisory; validated-documentation-publication: advisory | #636, #639 |

## Evidenz und Telemetrie

| ID | Präziser Ist-Name | Lifecycle | Tatsächliche Wirkung | Folgeissue |
|---|---|---|---|---|
| `EVID-DEAD-LETTER-QUEUE` | Persistente Dead-Letter-Queue für Event-Subscriberfehler | implemented | event-subscriber-exception: telemetry | — |
| `EVID-SEQUENCE-TRACKER` | Event-Sequenztracking mit expliziter Validierungsfunktion | experimental | shipped-workflows-recording: telemetry; sequence-enforcement: disabled | — |
| `MW-AUDIT` | Bus-AuditMiddleware | implemented | configured-audit-sink: telemetry | #482 |
| `MW-ERROR` | Bus-Exception-zu-WorkflowAborted-Abbildung | implemented | bus-handler-exceptions: enforced | #697, #752 |
| `MW-METRICS` | Bus-Laufzeitmetriken | implemented | bus: telemetry | — |
| `PRG-03` | MetadataBlock | implemented | gate-profile:default: enforced; gate-profile:self: enforced; gate-profile:audit: enforced | #517 |
| `PROC-WEIGHTED-SCORING` | Gebundene nicht bindende Qualitätsbeobachtung | implemented | runtime: telemetry | #399, #485, #589, #620, #627 |
| `EVID-DASHBOARD-WORKFLOW-OUTCOME` | Outcome-gebundene Workflow-Stage-Darstellung | implemented | dashboard-workflow-detail: telemetry | #399, #578, #627, #675, #672, #692, #698, #711, #712, #738, #521 |
| `EVID-AUDIT-REDACTION` | Flache Audit-Payload-Secret-Redaktion | implemented | audit-middleware: enforced | #481 |
| `EVID-AUDIT-HMAC` | Optionale JSONL-HMAC-Kette | implemented | SAMUEL_AUDIT_HMAC_KEY=set: telemetry; key-missing: disabled | #482, #689 |
| `EVID-SARIF-EXPORT` | Write-only SARIF-Findings-Export | implemented | sarif-sink-enabled: telemetry | #520 |
| `EVID-SCM-CHECK-ADVISORY` | Externe SCM-Check-Advisory-Bewertung | implemented | gitea-existing-run-pull: advisory | #520, #679 |
| `EVID-CONTEXT-HMAC` | Optionale Context-Ausgabe-HMAC ohne Konsumentenprüfung | experimental | shipped-workflows: telemetry | #485 |
| `PRIV-RETENTION-REPORT` | Digestgebundener Retention-Vertrag mit deaktiviertem Vollzugsfundament | implemented | retention-stage-5b-report: advisory; retention-stage-5c-score-derivations: disabled | #482, #667, #668, #673 |
| `ADVISORY-MODEL-COST-PARETO` | Taskbezogene Überqualifiziert-Klassifikation und optionaler Pareto-Kostenhinweis | experimental | dashboard-model-quality: telemetry; dashboard-model-cost-advisory: telemetry; model-selection-and-routing: disabled; real-price-benchmark-qualification: disabled | #454, #428, #549, #575 |

## Einzelbefunde

### `INPUT-CONTEXT-SELECTION` — Keyword-, Plan- und Symbol-basierte Kontextauswahl

- **Schutzziel:** Den an den Referenz-Worker übergebenen Repository-Kontext begrenzen.
- **Tatsächliches Verhalten:** Der Context Builder wählt Skeleton-, Plan-, Keyword- und Symboltreffer mit festen Datei- und Zeilenlimits; er ist keine allgemeine Geheimnis- oder Berechtigungsgrenze.
- **Fehler/fehlende Daten:** Nicht lesbare Dateien werden teilweise übersprungen; fehlender verwertbarer Kontext wird erst vom Context Validator blockiert.
- **Prüfgegenstand:** Worker-Level vor der Candidate-Erzeugung; nicht an den späteren EvaluationSubject gebunden.
- **Evidence:** Context-Metadaten und Tests, keine attestierte Merge-Evidence.
- **Vertrauen/Vollständigkeit:** Repository-Dateien und Issue-/Plantext sind unvertrauenswürdig; Auswahl ist begrenzt, aber kein Sandbox-Ersatz.
- **Fundstellen:** `samuel/slices/implementation/context_builder.py#build_full_context`, `samuel/slices/implementation/handler.py#build_full_context`
- **Issues:** —

### `INPUT-CONTEXT-VALIDATION` — Pre-LLM Context-Größen- und Präsenzprüfung

- **Schutzziel:** Offensichtlich leeren oder übergroßen Worker-Kontext vor dem LLM-Aufruf stoppen.
- **Tatsächliches Verhalten:** Prüft Titel, Bodylänge, vorhandene Kontextteile und eine zeichenbasierte Token-Schätzung mit festen Schwellwerten.
- **Fehler/fehlende Daten:** Harte Findings brechen die Implementierungsrunde ab; Warnungen blockieren nicht.
- **Prüfgegenstand:** Worker-Level vor Candidate und EvaluationSubject.
- **Evidence:** ContextValidation und WorkflowBlocked-Ereignisse.
- **Vertrauen/Vollständigkeit:** Tokenzahl ist nur len(prompt)//4; Datenqualität und Modellkontext werden nicht providerexakt bewiesen.
- **Fundstellen:** `samuel/slices/implementation/context_validator.py#validate_context`, `samuel/slices/implementation/handler.py#validation = validate_context`
- **Issues:** —

### `INPUT-PII-SANITIZER` — Konfigurierbarer PII-Prompt-Sanitizer

- **Schutzziel:** Konfigurierte PII-Muster in User-Nachrichten vor Provideraufrufen ersetzen.
- **Tatsächliches Verhalten:** Die aktive LLM-Adapterkette ersetzt E-Mail, IP, Kreditkarte und Telefon nur bei aktivierter privacy.json-Konfiguration; System-/Assistant-Nachrichten und beliebige Secrets sind nicht umfasst.
- **Fehler/fehlende Daten:** Fehlende Konfiguration bedeutet keinen PII-Sanitizer; unbekannte Muster werden übersprungen.
- **Prüfgegenstand:** LLM-Call-bezogen, nicht Candidate- oder Commit-gebunden.
- **Evidence:** Sanitizer-Testergebnisse; Redaktionsdetails werden nicht als Gate Receipt persistiert.
- **Vertrauen/Vollständigkeit:** Regex-basiert, begrenzte Musterabdeckung, kein vollständiger Datenschutzfilter.
- **Fundstellen:** `samuel/adapters/llm/factory.py#SanitizingLLMAdapter`, `samuel/adapters/llm/sanitizer.py#_sanitize_messages`, `samuel/slices/privacy/handler.py#class PromptSanitizer`
- **Issues:** #474, #481

### `INPUT-PROMPT-GUARD-HEADER` — Zentrale Prompt-Guard-Header der Worker-Slices

- **Schutzziel:** LLM-Prompts um unveränderliche Sicherheitsanweisungen ergänzen.
- **Tatsächliches Verhalten:** Planning, Implementation, Healing und Review importieren dieselben zwei Marker aus der Core-Security-Policy; die Marker bleiben eine Prompt-Layer-Maßnahme und keine modellunabhängige Injection-Abwehr.
- **Fehler/fehlende Daten:** Ein Konsistenztest schlägt fehl, wenn einer der vier Worker-Pfade eine abweichende Markerquelle verwendet; das Modell kann die Instruktionen dennoch missachten.
- **Prüfgegenstand:** Worker-Level je Prompt, nicht Commit-gebunden.
- **Evidence:** Gemeinsamer-Objekt-/Prompt-Tests, keine unabhängige Enforcement-Evidence.
- **Vertrauen/Vollständigkeit:** Promptanweisungen liegen innerhalb der Modellvertrauensgrenze und können keine technische Policy ersetzen.
- **Fundstellen:** `samuel/core/security_policy.py#PROMPT_GUARD_MARKERS`, `samuel/slices/planning/handler.py#PROMPT_GUARD_MARKERS`, `samuel/slices/implementation/handler.py#PROMPT_GUARD_MARKERS`, `samuel/slices/healing/handler.py#PROMPT_GUARD_MARKERS`, `samuel/slices/review/handler.py#PROMPT_GUARD_MARKERS`
- **Issues:** #474, #481, #485

### `INPUT-PLAN-VALIDATION` — Struktur- und Skeleton-basierte Planvalidierung

- **Schutzziel:** Offensichtlich unvollständige oder unzulässige LLM-Pläne vor der Implementation stoppen oder erneut erzeugen.
- **Tatsächliches Verhalten:** Der konfigurierte SCM-Base-Ref wird vor dem Planning-LLM auf eine vollständige Commit-SHA aufgelöst und vom gemeinsamen Worktree-Manager als detached Remote-Snapshot materialisiert. Skeleton, relevante Dateien, Suche und Pre-Checks werden für jeden Command frisch daraus erzeugt. Struktur, AC-Anzahl/-Tags, Pfade und Skeleton-Bezug werden bewertet; eine im Snapshot noch nicht vorhandene, strukturiert gescopte Datei gilt als geplante Neuanlage statt als Skeleton-Widerspruch. Unter 0,5 wird sofort blockiert, unter 0,8 oder bei negativem Pre-Check folgt genau ein Retry mit den konkreten fehlgeschlagenen Score-Dimensionen und Validator-Warnungen. Der tatsächliche Retry wird erneut vollständig geprüft und nur bei unverändertem Source-/Scope-Contract, ohne Struktur-/Precheck-Regress und mit mindestens einer behobenen fehlgeschlagenen Dimension übernommen. Danach entsteht PlanValidated ausschließlich bei overall_pass=true. Zusätzlich bewahrt der Precheck ausdrücklich genannte vollständige TEST-Selektoren, blockiert beweisbare GREP/GREP:NOT-Teilstringwidersprüche und lehnt nicht vom Issue verlangte wörtliche Python-Signaturen als Verhaltensevidence ab.
- **Fehler/fehlende Daten:** Nicht auflösbarer oder commitloser Base-Ref, SCM-/Origin-Abweichung und fehlender Worktree blockieren vor dem LLM. Vorhandene Dateien ohne Skeleton-Bezug, ungescopte unbekannte Pfade und Neuanlagebehauptungen ohne gebundenes project_root bleiben fail-closed. Ein nach dem Retry negativer Pre-Check blockiert als complexity_split_recommended oder pre_check_failed; der isolierte Score kann diese Schranke nicht überstimmen. Heuristische Scores beweisen keine fachliche Korrektheit.
- **Prüfgegenstand:** PlanningSourceSnapshot bindet Repository, Base-Ref, vollständige Base-SHA und Issue-Digest an den Acceptance-Contract; der spätere Candidate-Head ergänzt diese Identität im EvaluationSubject.
- **Evidence:** PlanContextLoaded.source_snapshot, source-gebundener Plan-Kommentar, PlanValidated, PlanBlocked, PlanRetry und PlanRetryEvaluated.
- **Vertrauen/Vollständigkeit:** SCM-Refauflösung und Remote-Commit sind Codequelle; uncommittete oder nur lokal commitierte Inhalte sind kein Fallback. Issue, Snapshotcode und LLM-Plan bleiben Eingaben; Schwellwerte und Heuristiken sind kein Acceptance-Nachweis.
- **Fundstellen:** `samuel/slices/planning/handler.py#validate_plan`, `samuel/slices/planning/handler.py#validate_plan_against_skeleton`
- **Issues:** #575, #655, #714, #735, #902

### `INPUT-PLAN-PRECHECK` — Plan-Pre-Check und Komplexitätssignal

- **Schutzziel:** Plan/Skeleton-/AC-Widersprüche vor der Implementation erkennen und zu breite Pläne markieren.
- **Tatsächliches Verhalten:** Kombiniert Struktur, Skeleton, AC-Dry-Run, Issue-Abdeckung und Komplexität. Der Skeleton-Abgleich verlangt für eine geplante Neuanlage sowohl Abwesenheit im gebundenen project_root als auch Autorisierung durch den strukturierten Scope. Der Scope-Creep-Guard behandelt bei einem gültigen Vertrag nur dessen FILE-Einträge als Mutationspfade; Prosa-, Negativ- und TEST-Referenzen erweitern keine Schreibautorität. Ein negativer erster Lauf führt zum einzigen Retry. Dessen Prompt enthält die konkreten Precheck-Scores, Mindestschwellen und Validator-Warnungen. Der zweite Lauf prüft immer die tatsächliche Retry-Antwort; PlanRetryEvaluated bindet Initial-/Retry-Scores, Adoption und deterministischen Auswahlgrund.
- **Fehler/fehlende Daten:** Zusätzliche strukturierte FILE-Einträge ohne Issue-Verankerung blockieren bei aktivem scope_guard. Fehlt ein gültiger FILE-Scope, bleibt die konservative Freitext-Pfaderkennung aktiv. split_recommended blockiert nach dem Retry mit eigenem Grund; jeder andere negative Pre-Check blockiert als pre_check_failed. PlanValidated wird dann nicht publiziert. Ausdrücklich offene Anforderungen werden vor diesem Pfad durch den gebundenen Klärungsdialog behandelt; ein negativer erzeugter Plan bleibt terminal und wird nicht durch freie LLM-Annahmen repariert.
- **Prüfgegenstand:** Planungsphase; kein Candidate und keine commitgebundene Evidence.
- **Evidence:** PlanPreCheckCompleted, PlanRetryEvaluated und PlanComplexityWarn.
- **Vertrauen/Vollständigkeit:** Heuristische Issue-/Plan-/Skeletonanalyse mit begrenzter Pfaderkennung.
- **Fundstellen:** `samuel/slices/planning/handler.py#_run_plan_pre_check`, `samuel/slices/planning/handler.py#_select_plan_retry`, `samuel/slices/planning/handler.py#detect_scope_creep`, `samuel/core/events.py#class PlanPreCheckCompleted`, `samuel/core/events.py#class PlanRetryEvaluated`
- **Issues:** #575, #655, #735, #742, #902

### `EXEC-PATCH-APPLY` — Strukturierter Patch-Parser und dateitypbezogener Applier

- **Schutzziel:** LLM-Ausgaben in begrenzte Dateiänderungen übersetzen, vorhandene dateitypbezogene Prüfungen vor dem Write ausführen und fachlich abgelehnte Patches mutationsfrei halten.
- **Tatsächliches Verhalten:** Verarbeitet strukturierte oder textuelle REPLACE-LINES-, SEARCH/REPLACE- und WRITE-Patches. Line-Patches berechnen partielle Kandidaten schreibfrei; alle Python-Operationen einschließlich des normalisierten vollständigen WRITE validieren vor Verzeichnisanlage und sichtbarem Write per AST. JSON SEARCH/REPLACE und REPLACE-LINES validieren den vollständigen Kandidaten mit json.loads vor dem Write; JSON-WRITE validiert ebenfalls zuerst. Andere Dateitypen werden mechanisch geschrieben.
- **Fehler/fehlende Daten:** Nicht passende Suche, ungültiger Bereich oder fachlicher Python-/JSON-Fehler meldet False ohne sichtbare Mutation; der Retry liest den letzten gültigen Stand. Ein vorsorglicher Loop-Snapshot wird nur bei nachgewiesener Unverändertheit freigegeben, damit terminaler Rollback keine Metadaten neu schreibt. I/O-Fehler während eines begonnenen Writes propagieren als Exception in die Loop-Transaktion. Eine nicht truncierte Antwort ohne parsbaren Patch blockiert als no_parseable_patches.
- **Prüfgegenstand:** Worker-Arbeitsbaum vor Candidate; EvaluationSubject entsteht später.
- **Evidence:** CodeGenerated oder WorkflowBlocked mit maschinenlesbarem Grund sowie Candidate-, Metadaten-, Retry-, Handler-, Parser- und Applier-Tests.
- **Vertrauen/Vollständigkeit:** Kein Sandbox-, Egress- oder allgemeiner Tool-Call-Policy-Ersatz. Die mutationsfreie Zusage gilt für fachliche Ablehnungen vor dem Write; YAML hat keine Syntaxprüfung und Gate 9 bleibt die spätere commitgebundene Python-Syntaxautorität.
- **Fundstellen:** `samuel/slices/implementation/patch_parser.py#_candidate_content`, `samuel/slices/implementation/patch_parser.py#JSONPatchApplier`, `samuel/slices/implementation/llm_loop.py#patches = parse_patches`, `samuel/slices/implementation/handler.py#blocked_payload`
- **Issues:** #601, #606

### `EXEC-IMPLEMENTATION-WORKSPACE-TRANSACTION` — Atomarer Workspace des Implementation-LLM-Loops

- **Schutzziel:** Verhindern, dass ein insgesamt fehlgeschlagener Implementation-Loop seine zuvor angewendeten Teilpatches an einen späteren Run vererbt.
- **Tatsächliches Verhalten:** Der Referenz-Worker erfasst vor dem ersten Schreibversuch je Zielpfad Inhalt, Existenz und Dateimodus. Einen nur vorsorglich erfassten Pfad gibt er nach einer fachlichen Patchablehnung ausschließlich dann frei, wenn Existenz, Bytes und Modus nachweislich unverändert sind; dadurch schreibt ein terminaler Rollback dessen Metadaten nicht neu. Nur success=true übernimmt die übrigen Loop-Patches; Tokenlimit, No-Patch, No-Progress, Partial-Failure und Exceptions restaurieren alle weiterhin berührten Pfade ohne Git-Reset und entfernen neu erzeugte, danach leere Verzeichnisse.
- **Fehler/fehlende Daten:** Ein unvollständiger Restore wird als workspace_rollback_failed mit erhaltenem trigger_reason und inhaltsfreien Anzahlen blockiert. Ein harter Prozessabbruch kann die In-Memory-Transaktion nicht ausführen.
- **Prüfgegenstand:** Prozesslokaler Worker-Arbeitsbaum vom Zustand vor dem LLM-Loop bis zu dessen Rückgabewert; noch kein EvaluationSubject und keine restart-persistente Bindung.
- **Evidence:** Rollback-Resultat, patches_rolled_back, TokenLimitHit und WorkflowBlocked sowie Transaktions-, Unverändertheits-, Loop-, Handler- und Integrationstests.
- **Vertrauen/Vollständigkeit:** Erfasst Dateiinhalte im Arbeitsspeicher und persistiert nur inhaltsfreie Status-/Anzahl-Evidence. Patchziel-Begrenzung und mutationsfreie fachliche Patchablehnung sind eigene vorgelagerte Controls; abrupter Prozessverlust, Git-Finalisierung und kumulatives Budget sind nicht Teil dieser Kontrolle.
- **Fundstellen:** `samuel/slices/implementation/workspace_transaction.py#WorkspaceTransaction`, `samuel/slices/implementation/workspace_transaction.py#release_if_unchanged`, `samuel/slices/implementation/llm_loop.py#_finalize_result`, `samuel/slices/implementation/handler.py#on_token_limit`
- **Issues:** #482, #549, #598

### `SEC-IMPLEMENTATION-PATCH-TARGET-BOUNDARY` — Projektwurzel- und Git-Control-Plane-gebundene Patchziele

- **Schutzziel:** Verhindern, dass unvertrauenswürdige strukturierte oder textuelle LLM-Patchziele vor dem Candidate-Commit außerhalb der Projektwurzel oder in die lokale Git-Control-Plane lesen oder schreiben.
- **Tatsächliches Verhalten:** Der Referenz-Worker validiert alle Patchziele einer Modellantwort vor dem ersten Apply. Er akzeptiert nur normalisierte relative POSIX-Pfade, löst Projektwurzel und Ziel kanonisch auf und reicht den kanonischen internen Pfad an Transaktion, Applier, Resultat und Git-Staging weiter. Absolute POSIX-/Windows-/Drive-/UNC-Pfade, Backslashes, Steuerzeichen, .. und externe Symlink-Ziele werden abgelehnt. Jeder .git-Bestandteil ist reserviert; ein read-only Core-Git-Aufruf ermittelt einmal pro Loop zusätzlich die effektiven absoluten Git-/Common-/Index-/Object-Pfade für linked/separate Git-Dirs und wirksame GIT_*-Overrides.
- **Fehler/fehlende Daten:** Ein einziges unzulässiges Ziel blockiert die vollständige Antwort und den Loop als unsafe_patch_target vor dem ersten Apply. Frühere Loop-Runden werden über die Workspace-Transaktion restauriert; Resultat und WorkflowBlocked enthalten nur begrenzte Reason-Codes, Anzahlen und inhaltsfreie Rollback-Evidence.
- **Prüfgegenstand:** Kanonisch auf den lokalen project_root des Referenz-Workers gebunden, vor Candidate-Commit und EvaluationSubject.
- **Evidence:** unsafe_patch_target mit rejection_codes/rejected_patch_count, WorkflowBlocked und Resolver-, Text-/Structured-Loop-, Symlink-, Rollback-, Git-Discovery-, Git-Metadaten- und Handlertests.
- **Vertrauen/Vollständigkeit:** Der LLM-Pfad ist unvertrauenswürdig und wird nie in der Ablehnungs-Evidence reflektiert. Die Grenze ist keine Prozesssandbox und schützt nicht gegen konkurrierende lokale Dateisystemmutation. Bei fehlgeschlagener Git-Discovery bleibt die lexikalische .git-Mindestgrenze; normale Dotfiles und versionierte Hook-Quellen außerhalb effektiver Verwaltungspfade bleiben zulässig.
- **Fundstellen:** `samuel/core/git.py#git_control_plane_paths`, `samuel/slices/implementation/patch_targets.py#resolve_patch_target`, `samuel/slices/implementation/llm_loop.py#resolved_patches`, `samuel/slices/implementation/handler.py#blocked_payload`
- **Issues:** #600, #603

### `EXEC-TOKEN-OUTPUT-BUDGET` — Provider- und taskbezogenes LLM-Ausgabebudget

- **Schutzziel:** Die maximale sichtbare LLM-Ausgabe pro Call begrenzen.
- **Tatsächliches Verhalten:** TokenBudgetLLMAdapter setzt max_tokens und optional OpenRouter-Reasoning-Reserve pro physischem Call. Der OpenAI-kompatible Adapter bewahrt einen expliziten Truncation-Grund und reale Usage auch bei leerem sichtbarem Content, damit die aufrufenden Slices fail-closed unterscheiden können. Der davon getrennte kumulative Workflowvertrag wird durch AUTH-WORKFLOW-TOKEN-BUDGET durchgesetzt.
- **Fehler/fehlende Daten:** Leerer Content ohne expliziten Truncation-Grund bleibt malformed. Eine erkannte Truncation erhöht weder die Call-Grenze noch startet sie einen versteckten Retry.
- **Prüfgegenstand:** LLM-Call-bezogen, nicht Candidate-gebunden.
- **Evidence:** LLMCallCompleted-Metrik, Adaptertests und korrelierter Planning-Tokenlimit-Integrationstest.
- **Vertrauen/Vollständigkeit:** Providerzählung und Stop-Reason bleiben providerabhängig.
- **Fundstellen:** `samuel/adapters/llm/factory.py#TokenBudgetLLMAdapter`, `samuel/adapters/llm/token_budget.py#class TokenBudgetLLMAdapter`
- **Issues:** #744

### `AUTH-WORKFLOW-TOKEN-BUDGET` — Persistente kumulative Tokenzulassung je Workflowauftrag

- **Schutzziel:** Jeden Planning-, Retry- und Fallback-Providerattempt vor der Sendung aus einer dauerhaft gebundenen Tokenzulassung decken.
- **Tatsächliches Verhalten:** Planning persistiert vor dem ersten LLM-Call eine Zulassung, die Repository, Issue, akzeptierte Invocation, Source-Snapshot und Workflow-/Budgetpolicy bindet. Der exakte Planvertrag samt Plan-Kommentar-ID wird nach dem sichtbaren Plan an dieselbe Zulassung gebunden; Watch und Webhook lösen Approval nur mit diesem Planbinding aus. Jeder physische Providerattempt reserviert atomar einen konservativen UTF-8-/Framing-Eingabebound plus den providerseitig erzwungenen max_tokens-Ausgabebound. Gemeldete Usage rechnet die Reservation auf tatsächliche Tokens ab; Retry und Fallback reservieren erneut innerhalb derselben logischen Call-ID. Resume-Checkpoints tragen die Zulassungsidentität weiter. Ein budgetgeschützter CreatePR-/Review-Wiedereintritt rekonstruiert dieselbe Zulassung ausschließlich aus dem exakten Repository-, Issue-, Planvertrag- und Plan-Kommentar-Binding; eine mitgegebene fremde Zulassung blockiert vor PR und Provider.
- **Fehler/fehlende Daten:** Fehlende oder fremde Zulassung, fehlender positiver Ausgabebound und ein ausgeschöpftes Budget blockieren vor dem Provider. Timeout, verlorene Antwort, ungemeldete Usage oder Usage oberhalb des Bounds halten die vollständige Reservation. Eine fehlgeschlagene Settlement-Persistierung blockiert die Antwortweitergabe; Reserved bleibt dadurch konservativ wirksam.
- **Prüfgegenstand:** workflow-budget.v1 bindet Repository, Issue, Invocation-Digest, Source-Digest und Policy-Digest; correlation_id ist Telemetrie und keine Authority. Der später gebundene Acceptance-Contract samt Plan-Kommentar-ID identifiziert die Zulassung für Polling, Webhook, Resume und denselben Candidate wiederaufnehmende PR-/Review-Auswertung.
- **Evidence:** SQLite-Schema v9 mit workflow_budget_admissions und llm_budget_attempts; authority.v2-gebundene WorkflowBudgetAdmitted-, LLMBudgetAttemptReserved/-Settled- und LLMBudgetBlocked-Ereignisse; payloadfreie State-Zähler sowie Dashboard-/Audit-Projektion.
- **Vertrauen/Vollständigkeit:** Tokenzählung des Providers wird nur bei vollständig gemeldeten nichtnegativen Werten abgerechnet. Der vorab reservierte Eingabebound ist tokenizerunabhängig konservativ für die ausgelieferten Textadapter; max_tokens wird durch den bestehenden Call-Adapter gesetzt. Preis- und Rechnungswerte bleiben informative Meteringdaten und sind kein Geldkosten-Hardcap. Reale Timeout-/Retry-/Fallback-Qualification je unterstütztem Provider ist vor Abschluss von #549 weiterhin erforderlich.
- **Fundstellen:** `samuel/core/llm_budget.py#workflow_budget_admission`, `samuel/adapters/llm/workflow_budget.py#WorkflowTokenBudgetLLMAdapter`, `samuel/adapters/state/sqlite.py#SQLiteAuthorityStateStore`, `samuel/slices/planning/handler.py#PlanningHandler`, `samuel/slices/watch/handler.py#WatchHandler`, `samuel/slices/pr_gates/handler.py#_bind_review_budget_admission`, `config/llm/defaults.json#workflow_budget`, `docs/adr/0482-runtime-state-store.md`
- **Issues:** #549, #884

### `EXEC-LLM-RETRY` — Konfigurierter Retry für transiente Providerfehler

- **Schutzziel:** Transiente Rate-Limit-, 5xx- und Netzwerkfehler begrenzt wiederholen.
- **Tatsächliches Verhalten:** OpenAI-kompatible sowie native Claude-, Gemini- und Ollama-Adapter validieren ihre jeweiligen offiziellen Error-/Content-Schemata und normalisieren Provider-, HTTP-, Transport-, Block- und Malformed-Antworten ohne Raw-Payload in den bestehenden Core-Vertrag ProviderUnavailable. Beim OpenAI-kompatiblen Format wird leerer Content nur mit einem expliziten Truncation-Grund als unvollständige LLMResponse weitergegeben; sonst bleibt er malformed. Gemini überträgt den API-Key im x-goog-api-key-Header statt in der URL. RetryLLMAdapter wiederholt nur explizit transiente Fehler mit exponentiellem Backoff und konfigurierter Versuchszahl. Planning publiziert nach einem terminalen typisierten Fehler korreliert LLMUnavailable und PlanBlocked.
- **Fehler/fehlende Daten:** Malformed-/nicht-transiente Fehler werden sofort, ausgeschöpfte transiente Fehler nach dem letzten Versuch als typisierter Fehler weitergegeben. Explizite Truncation nutzt den vorhandenen Tokenlimitpfad, löst keinen versteckten Retry aus und erhält im Planning-Kommentar eine eigene Abhilfe zu Ausgabetokenbudget sowie Modell-/Prompt-Eignung statt einer falschen Issue-Unschärfe. Planning blockiert; andere aufrufende Slices müssen die Exception weiterhin selbst fachlich zuordnen.
- **Prüfgegenstand:** LLM-Call-bezogen, nicht Candidate-gebunden.
- **Evidence:** Warnlogs, korreliertes LLMUnavailable/PlanBlocked sowie TokenLimitHit/PlanBlocked im Planningpfad und Adapter-/Planningtests. Reale isolierte D0-Evidence belegt Ollama positiv mit LLMCallCompleted, echten Tokenwerten, stop_reason=stop und PlanValidated sowie negativ nach zwei Retries mit LLMUnavailable/PlanBlocked, ohne LLMCallCompleted oder Fallback. Der Plan-/Acceptance-Score 100 ist kein Modellqualitätswert; der reale a15-Dashboard-Quality-Pfad kennzeichnet das 3B-Modell separat als below_min ohne gebundenen Modellqualitätsscore oder EWMA. Claude und Gemini bleiben providergetreue Fixture-Evidence; kein eigener attestierter Receipt.
- **Vertrauen/Vollständigkeit:** Fehlerklassifikation basiert auf validiertem Status, begrenztem Code und Exceptiontyp; Providermeldung und Raw-Payload werden nicht übernommen. Wiederholung garantiert keinen Erfolg.
- **Fundstellen:** `samuel/adapters/llm/provider_errors.py#call_json`, `samuel/adapters/llm/openai_compat.py#class OpenAICompatAdapter`, `samuel/adapters/llm/claude.py#class ClaudeAdapter`, `samuel/adapters/llm/gemini.py#class GeminiAdapter`, `samuel/adapters/llm/ollama.py#class OllamaAdapter`, `samuel/core/errors.py#ProviderUnavailable`, `samuel/adapters/llm/retry.py#class RetryLLMAdapter`, `samuel/adapters/llm/factory.py#RetryLLMAdapter`, `samuel/slices/planning/handler.py#_block_provider_error`
- **Issues:** #698, #701, #744

### `EXEC-LLM-FALLBACK` — Geordneter LLM-Provider-Fallback

- **Schutzziel:** Nach Providerfehlern einen explizit konfigurierten Folgeprovider versuchen.
- **Tatsächliches Verhalten:** FallbackLLMAdapter versucht Provider in Reihenfolge und publiziert beim Wechsel ProviderFallbackUsed; ein erfolgreicher Primary ruft keinen Fallback auf.
- **Fehler/fehlende Daten:** Wenn alle Provider fehlschlagen, wird der letzte Fehler weitergeworfen.
- **Prüfgegenstand:** LLM-Call-bezogen; Providerwechsel ist nicht Candidate-gebunden.
- **Evidence:** ProviderFallbackUsed und Tests.
- **Vertrauen/Vollständigkeit:** Provider können unterschiedliche Modelle, Datenschutzorte und Ausgabecharakteristika haben; gemeinsame Capability ist der Schnitt.
- **Fundstellen:** `samuel/adapters/llm/fallback.py#class FallbackLLMAdapter`, `samuel/adapters/llm/factory.py#FallbackLLMAdapter`
- **Issues:** —

### `EXEC-CIRCUIT-BREAKER` — LLM-Provider Circuit Breaker

- **Schutzziel:** Wiederholte Providerfehler zeitweise stoppen.
- **Tatsächliches Verhalten:** Die aktive LLM-Kette öffnet nach konfigurierbarer Fehlerzahl und erlaubt nach Cooldown einen Half-Open-Versuch.
- **Fehler/fehlende Daten:** Offener Circuit wirft ProviderUnavailable; Zustand ist pro Prozess und nicht persistent.
- **Prüfgegenstand:** Provider-/Prozesszustand, nicht Commit-gebunden.
- **Evidence:** ProviderCircuitOpen und Adaptertests.
- **Vertrauen/Vollständigkeit:** Resilienzmechanismus, keine Code- oder Sicherheitsprüfung.
- **Fundstellen:** `samuel/adapters/llm/factory.py#CircuitBreakerAdapter`, `samuel/adapters/llm/circuit_breaker.py#class CircuitBreakerAdapter`
- **Issues:** —

### `EVID-DEAD-LETTER-QUEUE` — Persistente Dead-Letter-Queue für Event-Subscriberfehler

- **Schutzziel:** Fehlgeschlagene Event-Subscriberaufrufe sichtbar und manuell replaybar halten.
- **Tatsächliches Verhalten:** Bus.publish isoliert Subscriberfehler und schreibt pro fehlgeschlagenem Handler einen JSONL-Eintrag; Commands werden nicht auf diesem Pfad erfasst.
- **Fehler/fehlende Daten:** DLQ-Schreibfehler werden geloggt und nicht an den Workflow propagiert; Replay ist eine manuelle CLI-Aktion.
- **Prüfgegenstand:** Nur Payload und Correlation-ID des Events; keine generelle EvaluationSubject-Bindung.
- **Evidence:** data_dir/dlq.jsonl und CLI list/replay.
- **Vertrauen/Vollständigkeit:** Lokale veränderliche Datei; Stack und Payload können sensible Inhalte tragen.
- **Fundstellen:** `samuel/core/bus.py#class DeadLetterQueue`, `samuel/core/bootstrap.py#DeadLetterQueue`
- **Issues:** —

### `EVID-SEQUENCE-TRACKER` — Event-Sequenztracking mit expliziter Validierungsfunktion

- **Schutzziel:** Eventfolgen aufzeichnen und bei expliziter Erwartung vergleichen.
- **Tatsächliches Verhalten:** Bootstrap zeichnet alle Bus-Events auf. `validate_sequence` kann warn/block/off auswerten, wird von ausgelieferten Workflows aber nicht aufgerufen.
- **Fehler/fehlende Daten:** Ohne expliziten Aufruf entsteht keine Sequenzentscheidung; im warn-Modus publiziert eine Abweichung kein Blockerevent.
- **Prüfgegenstand:** Prozesslokale Eventfolge, nicht Candidate-/Contract-gebunden.
- **Evidence:** In-Memory-Log, optionale Patterndatei und bei explizitem block-Aufruf SequenceViolation.
- **Vertrauen/Vollständigkeit:** Prozesslokal und nicht restartfest; aufgezeichnete Reihenfolge allein beweist keinen vollständigen Workflow.
- **Fundstellen:** `samuel/slices/sequence/handler.py#class SequenceHandler`, `samuel/core/bootstrap.py#record_sequence_event`
- **Issues:** —

### `MW-IDEMPOTENCY` — Bus-Idempotenz-Deduplizierung

- **Schutzziel:** Wiederholte Commands/Events mit demselben Idempotency-Key innerhalb der TTL nicht erneut ausführen.
- **Tatsächliches Verhalten:** Erste erfolgreiche Verarbeitung speichert den Key; Meldungen ohne Key werden nicht dedupliziert.
- **Fehler/fehlende Daten:** Persistenzfehler werden geloggt, die In-Memory-Wirkung bleibt pro Prozess.
- **Prüfgegenstand:** Message-Key, nicht EvaluationSubject.
- **Evidence:** Logeintrag und Storezustand.
- **Vertrauen/Vollständigkeit:** Key muss vom Aufrufer korrekt gesetzt sein.
- **Fundstellen:** `samuel/core/bus.py#class IdempotencyMiddleware`, `samuel/core/bootstrap.py#IdempotencyMiddleware`
- **Issues:** —

### `MW-AUDIT` — Bus-AuditMiddleware

- **Schutzziel:** Bus-Nachrichten, Laufzeit und Fehlertyp an konfigurierte Audit-Sinks senden.
- **Tatsächliches Verhalten:** Erfasst Bus-Commands/Events; direkte Funktionen, subprocess-Aktionen und reine Logs sind nicht automatisch vollständig enthalten.
- **Fehler/fehlende Daten:** Sinkfehler werden abgefangen; Async-Sink besitzt JSONL-Fallback, aber Vollständigkeit ist nicht attestiert.
- **Prüfgegenstand:** Subject wird nur erhalten, wenn die Message-Payload ihn trägt.
- **Evidence:** JSONL/SARIF je Sink-Konfiguration.
- **Vertrauen/Vollständigkeit:** Prozesslokale Erfassung, kein unveränderlicher externer Ledger.
- **Fundstellen:** `samuel/core/bus.py#class AuditMiddleware`, `samuel/core/bootstrap.py#AuditMiddleware`
- **Issues:** #482

### `MW-ERROR` — Bus-Exception-zu-WorkflowAborted-Abbildung

- **Schutzziel:** Unhandled Handler-Exceptions als sicheren Workflowabbruch sichtbar machen.
- **Tatsächliches Verhalten:** Fängt Exceptions innerhalb der Bus-Middlewarekette. Erwartete AgentAbort-Ausgänge werden als WorkflowAborted abgebildet; unerwartete Command-Exceptions erzeugen zusätzlich genau eine inhaltlich begrenzte DiagnosticRaised mit derselben Issue-/Workflow-Korrelation. Für Commands entsteht außerdem ein false-y, typisierter HandledCommandFailure, der sich eindeutig von einer legitimen Handler-Rückgabe None unterscheidet. Der synchrone REST-Adapter bildet nur diesen Wert auf ein redigiertes RFC-9457-Problem ab: 404 für ein fehlendes Ziel, 409 für Workflowabbruch und 500 für interne Fehler. Spätere asynchrone Ausgänge verändern eine bereits erteilte 202-Annahme nicht; außerhalb des Bus gestartete Arbeit ist nicht umfasst.
- **Fehler/fehlende Daten:** Der Fehler wird nicht als erfolgreicher Command auditiert oder gezählt. Diagnose, terminaler Abbruch, Command-Audit und synchrone Problemantwort verwenden dieselbe Korrelation und einen begrenzten Reason-Code. Sie enthalten weder Exceptiontext noch Secrets oder SCM-/Providerpayload; ein Fehler der Diagnosepublikation verdeckt weder den nachfolgenden WorkflowAborted-Versuch noch die autoritative Fehlerantwort.
- **Prüfgegenstand:** Correlation, nicht zwingend EvaluationSubject.
- **Evidence:** DiagnosticRaised, WorkflowAborted, fehlerklassifizierter Command-Audit und bei synchronem REST-Aufruf Problemantwort mit gemeinsamer Korrelation.
- **Vertrauen/Vollständigkeit:** Nur Bus-Ausführungspfad.
- **Fundstellen:** `samuel/core/bus.py#class ErrorMiddleware`, `samuel/core/bootstrap.py#ErrorMiddleware`, `samuel/adapters/api/rest.py#_command_response`
- **Issues:** #697, #752

### `MW-METRICS` — Bus-Laufzeitmetriken

- **Schutzziel:** Bus-Aufrufe und Laufzeiten beobachten.
- **Tatsächliches Verhalten:** Erzeugt Prozessmetriken und zählt auch einen durch eine innere ErrorMiddleware typisiert behandelten Commandausgang als Fehler statt als Erfolg; trifft keine Freigabeentscheidung.
- **Fehler/fehlende Daten:** Metrikausfall blockiert den Workflow nicht.
- **Prüfgegenstand:** Keine garantierte Subject-Bindung.
- **Evidence:** In-Memory/Exporter-Metriken.
- **Vertrauen/Vollständigkeit:** Telemetrie, keine Kontrollreceipt.
- **Fundstellen:** `samuel/core/bus.py#class MetricsMiddleware`, `samuel/core/bootstrap.py#MetricsMiddleware`
- **Issues:** —

### `PRG-01` — BranchGuard

- **Schutzziel:** Leere sowie wörtlich main/master benannte Candidate-Branches im CreatePR-Pfad ablehnen.
- **Tatsächliches Verhalten:** Prüft nur den übergebenen Branchnamen; verhindert weder direkten Push noch ähnlich benannte oder bereits geschützte Refs.
- **Fehler/fehlende Daten:** Required blockiert, optional erzeugt nur ein negatives Ergebnis.
- **Prüfgegenstand:** GateResult trägt Subject, die Entscheidung selbst verwendet nur branch.
- **Evidence:** GateResult 1 im GateEvaluationCompleted.
- **Vertrauen/Vollständigkeit:** Branchname aus Command ist kein SCM-Branchschutz.
- **Fundstellen:** `samuel/slices/pr_gates/gates.py#gate_1_branch_guard`
- **Issues:** #124

### `PRG-02` — PlanComment

- **Schutzziel:** Plantext mit mehr als 20 Zeichen verlangen.
- **Tatsächliches Verhalten:** Prüft nur Präsenz und Länge des zuletzt gefundenen Plan-/Metadatenkommentars.
- **Fehler/fehlende Daten:** Fehlend oder zu kurz ergibt Gate-Failure.
- **Prüfgegenstand:** Der gleiche Text wird in #515 gehasht, aber Inhalt/Freigabe werden hier nicht validiert.
- **Evidence:** GateResult 2.
- **Vertrauen/Vollständigkeit:** Issue-Kommentar ist unvertrauenswürdig und schemalos.
- **Fundstellen:** `samuel/slices/pr_gates/gates.py#gate_2_plan_comment`
- **Issues:** #519

### `PRG-03` — MetadataBlock

- **Schutzziel:** Den Marker Agent-Metadaten im Plantext verlangen.
- **Tatsächliches Verhalten:** Substring-Präsenzcheck ohne Schema, Feldvalidierung oder Provenienz.
- **Fehler/fehlende Daten:** Fehlender Marker ergibt Failure.
- **Prüfgegenstand:** Text ist Teil des Contract-Hash; Metadatenfelder selbst werden nicht geprüft.
- **Evidence:** GateResult 3.
- **Vertrauen/Vollständigkeit:** Selbstdeklarierter Kommentarinhalt.
- **Fundstellen:** `samuel/slices/pr_gates/gates.py#gate_3_metadata_block`
- **Issues:** #517

### `PRG-05` — DiffNotEmpty

- **Schutzziel:** Leeren Candidate-Diff erkennen.
- **Tatsächliches Verhalten:** Prüft den vollständigen, commitgebundenen Diff auf nicht-whitespace Inhalt.
- **Fehler/fehlende Daten:** Leerer Diff schlägt fehl.
- **Prüfgegenstand:** Vollständig an EvaluationSubject aus #515 gebunden.
- **Evidence:** GateResult 5.
- **Vertrauen/Vollständigkeit:** Diff stammt aus exaktem Base...Head-Vergleich.
- **Fundstellen:** `samuel/slices/pr_gates/gates.py#gate_5_diff_not_empty`
- **Issues:** #515

### `PRG-06` — SelfConsistency

- **Schutzziel:** Im Plan genannte Dateibasename grob mit changed_files vergleichen.
- **Tatsächliches Verhalten:** Passiert bei fehlenden Daten/Dateireferenzen und blockiert nur, wenn mehr als die Hälfte der extrahierten Basenames fehlt.
- **Fehler/fehlende Daten:** Mehrheit fehlend ergibt Failure; sonst Erfolg trotz Lücken.
- **Prüfgegenstand:** changed_files ist Subject-gebunden, Plantext über Contract-Hash.
- **Evidence:** GateResult 6.
- **Vertrauen/Vollständigkeit:** Regex-/Basename-Heuristik mit Kollisionen und unvollständiger Sprachenliste.
- **Fundstellen:** `samuel/slices/pr_gates/gates.py#gate_6_self_consistency`
- **Issues:** #517

### `PRG-07` — ForbiddenPathGuard

- **Schutzziel:** Ohne PathRisk-Konfiguration einen kleinen Satz sensibler Dateipfade blockieren.
- **Tatsächliches Verhalten:** Fallback-Pfadfilter; bei konfiguriertem PathRisk delegiert er vollständig und prüft keinen Issue-/Contract-Scope.
- **Fehler/fehlende Daten:** Leere Dateiliste oder Treffermuster schlägt fehl; delegierter Modus besteht.
- **Prüfgegenstand:** changed_files aus EvaluationSubject.
- **Evidence:** GateResult 7.
- **Vertrauen/Vollständigkeit:** Pfadnamen, kein Diff-Inhalt und kein allgemeiner Scopevertrag.
- **Fundstellen:** `samuel/slices/pr_gates/gates.py#gate_7_scope_guard`, `samuel/core/path_risk.py#DEFAULT_SECRET_PATH_PATTERNS`
- **Issues:** #474, #485

### `PRG-07B` — ContractScope

- **Schutzziel:** Jeden geänderten Candidate-Pfad gegen den freigegebenen, versionierten Contract-Scope prüfen.
- **Tatsächliches Verhalten:** Required Gate 7b prüft vollständige changed_files gegen exakte FILE-/PATH-Einträge des Acceptance Contract Schema v2. Nur ausdrücklich erlaubte Architecture-Expansion kann zusätzliche Pfade aus config/architecture.json öffnen; deren blocked_scopes gewinnen.
- **Fehler/fehlende Daten:** Out-of-Scope blockiert. Fehlender/leerer/ungültiger/mehrdeutiger oder stale Scope sowie nicht kanonische Changed-Files und eine nötige, aber fehlende, unlesbare oder rollenlos aufgelöste Architekturpolicy ergeben missing_evidence/not_evaluated.
- **Prüfgegenstand:** Repository, Base, Head, Contract-Hash und kombinierter Gate-/Architektur-Policy-Digest stammen aus demselben EvaluationSubject; Diff und Changed-Files aus dessen vollständigem Compare.
- **Evidence:** GateResult 7b und OutOfScopeDiff tragen strukturierte Scope-Evidence einschließlich Subject, Scope-Schema, vollständiger Dateiliste, Diff-Größe/-Digest und Out-of-Scope-Pfaden.
- **Vertrauen/Vollständigkeit:** Deterministische POSIX-Pfadsemantik ohne Globs oder Basename-/Freitextannahmen; Git-Renames werden mit --no-renames als alter und neuer Pfad sichtbar.
- **Fundstellen:** `samuel/core/acceptance.py#class AcceptanceScope`, `samuel/slices/pr_gates/gates.py#gate_7b_contract_scope`, `samuel/slices/pr_gates/handler.py#scope_evidence`
- **Issues:** #485, #529

### `PRG-08` — SliceGate

- **Schutzziel:** Neu hinzugefügte Python-from-Imports zwischen Slices erkennen.
- **Tatsächliches Verhalten:** Prüft vollständigen Diff, aber ausschließlich echte hinzugefügte from samuel.slices.X import-Zeilen in Slice-Dateien; andere Sprachen, import-Formen und bestehender Code sind nicht umfasst.
- **Fehler/fehlende Daten:** Erkannter Cross-Slice-from-Import schlägt fehl; nicht erfasste Formen sind außerhalb des Vertrags.
- **Prüfgegenstand:** Vollständiger Diff aus EvaluationSubject.
- **Evidence:** GateResult 8 mit Subject.
- **Vertrauen/Vollständigkeit:** Deterministische, aber bewusst schmale Text-/Dateiattribution.
- **Fundstellen:** `samuel/slices/pr_gates/gates.py#gate_8_slice_gate`
- **Issues:** —

### `PRG-09` — PythonSyntax

- **Schutzziel:** Vorhandene geänderte Python-Blobs aus dem exakten Candidate-Head per CPython ast.parse prüfen.
- **Tatsächliches Verhalten:** Kein Lint, Typecheck oder Test; Nicht-Python und bestätigte Löschungen sind not_applicable, unerwartet fehlende oder nicht lesbare Blobs schlagen fehl.
- **Fehler/fehlende Daten:** Syntax-, Revisions-, Encoding-, Missing- und Ressourcenfehler blockieren im Required-Profil fail-closed.
- **Prüfgegenstand:** SCM-Port liest jeden Blob aus EvaluationSubject.head_sha; Base, Head, Contract und Policy stammen aus demselben Subject.
- **Evidence:** GateResult 9 mit passed/failed/not_applicable, CPython-AST-Version und vollständigem EvaluationSubject.
- **Vertrauen/Vollständigkeit:** UTF-8-Python-Blob aus unveränderlichem Git-Objekt; max_quality_file_bytes ist policygebunden. Keine breitere Quality-Zusage.
- **Fundstellen:** `samuel/slices/pr_gates/gates.py#gate_9_python_syntax`, `samuel/core/ports.py#read_file_at_revision`
- **Issues:** #518

### `PRG-11` — ACVerification

- **Schutzziel:** Freigegebene Acceptance-Kriterien nur mit Evidence für exakt denselben Candidate, Contract und dieselbe Policy passieren lassen.
- **Tatsächliches Verhalten:** Nach bestandenem Required-Preflight fordert der CreatePR-Handler genau einmal strukturierte Evidence vom ACVerificationHandler an; Gate 11 validiert diese Evidence ohne zweite Verifier-Ausführung. Bei einem Required-Preflight-Fehler bleibt Gate 11 explizit skipped_precondition und startet keinen Candidate-Prozess. Alle erforderlichen Kriteriums-IDs müssen status=passed tragen. Checkboxzustände werden ignoriert.
- **Fehler/fehlende Daten:** Fehlende, mehrdeutige, veraltete oder fehlerhafte Evidence sowie manual_pending/not_applicable/unknown blockieren fail-closed.
- **Prüfgegenstand:** AcceptanceEvidence trägt den vollständigen EvaluationSubject und exakt denselben Contract-Hash; dessen Policy-Digest enthält die bootstrapgebundene TEST-Runner-Policy und das Candidate-Prozessumgebungsprofil.
- **Evidence:** GateResult 11 plus AcceptanceEvidence mit Contract, Approval-Receipt und kriteriumsweisen Statuswerten.
- **Vertrauen/Vollständigkeit:** Automatische Checks laufen in einem detached Worktree des Head-SHA. IMPORT/TEST erhalten eine sterile Environment-Allowlist ohne Parent-Secrets; TEST-Befehl, Timeout und Policy-Version stammen aus dem Control-Plane-Snapshot. Worktree und Environment-Härtung sind keine Prozesssandbox. Menschliche MANUAL-Quittungen müssen Kriterium, Contract und Head nennen.
- **Fundstellen:** `samuel/slices/pr_gates/gates.py#gate_11_ac_verification`, `samuel/core/acceptance.py#class AcceptanceEvidence`
- **Issues:** #519, #612, #613, #620

### `PRG-12` — AcceptanceReadiness

- **Schutzziel:** Vollständigkeit der Acceptance-Evidence als Readiness ausweisen, ohne eine zweite Verifikation zu behaupten.
- **Tatsächliches Verhalten:** Fasst kriteriumsweise Evidence-Status zusammen; nur ein nichtleerer, vollständig bestandener Ergebnissatz ist abschlussbereit.
- **Fehler/fehlende Daten:** Fehlende Evidence, leere Verträge und alle nicht bestandenen Statuswerte sind nicht abschlussbereit.
- **Prüfgegenstand:** Verwendet dieselbe AcceptanceEvidence wie Gate 11.
- **Evidence:** GateResult 12 mit Readiness-Status und Zahl offener Ergebnisse.
- **Vertrauen/Vollständigkeit:** Keine Checkbox- oder Issue-Status-Auswertung; die Verifikation bleibt ausschließlich Gate 11/ACVerificationHandler.
- **Fundstellen:** `samuel/slices/pr_gates/gates.py#gate_12_ready_to_close`
- **Issues:** #519

### `PRG-13A` — BranchFreshness

- **Schutzziel:** Abstand des gebundenen Head zur gebundenen Base messen.
- **Tatsächliches Verhalten:** git rev-list --count head..base; blockiert erst oberhalb 50 Commits und bei Nichtprüfbarkeit.
- **Fehler/fehlende Daten:** Fehlender Subject, Gitfehler oder >50 blockiert.
- **Prüfgegenstand:** Exakte Base-/Head-SHAs aus EvaluationSubject.
- **Evidence:** GateResult 13a.
- **Vertrauen/Vollständigkeit:** Lokales Git-Objektmodell; kein Rebase-/Konfliktnachweis.
- **Fundstellen:** `samuel/slices/pr_gates/gates.py#gate_13a_branch_freshness`
- **Issues:** #468

### `PRG-13B` — DestructiveDiff

- **Schutzziel:** Große Löschungsüberhänge im vollständigen Diff blockieren.
- **Tatsächliches Verhalten:** Blockiert nur bei mehr als 50 Löschzeilen und mehr als dreifachem Verhältnis zu Hinzufügungen.
- **Fehler/fehlende Daten:** Leerer oder unter Schwellwert liegender Diff besteht.
- **Prüfgegenstand:** Vollständiger Diff aus EvaluationSubject.
- **Evidence:** GateResult 13b.
- **Vertrauen/Vollständigkeit:** Zeilenmengenheuristik ohne Dateityp-/Risikokontext.
- **Fundstellen:** `samuel/slices/pr_gates/gates.py#gate_13b_destructive_diff`
- **Issues:** —

### `EXT-PATH-RISK` — Konfigurierbarer Pfad-Risikoklassifikator

- **Schutzziel:** Konfigurierte sensitive Pfade blockieren und weitere Risikopfade melden.
- **Tatsächliches Verhalten:** Klassen level=block liefern passed=false; warn-Klassen liefern passed=true mit Hinweis. Prüft Pfade, nicht Diff-Inhalt.
- **Fehler/fehlende Daten:** Fehlende/ungültige path_risk.json deaktiviert den External-Gate und Gate 7 übernimmt den Fallback.
- **Prüfgegenstand:** changed_files und GateResult sind EvaluationSubject-gebunden.
- **Evidence:** External GateResult path_risk.
- **Vertrauen/Vollständigkeit:** Konfigurationsbasierte Pfadklassifikation; keine Secret-Inhaltsanalyse.
- **Fundstellen:** `samuel/slices/path_risk/gate.py#class PathRiskGate`, `config/path_risk.json`
- **Issues:** #474

### `EXT-SYMBOL-RESOLUTION` — Python-Import-Symbolauflösung

- **Schutzziel:** Neu importierte, nicht auflösbare Python-Top-Level-Module melden.
- **Tatsächliches Verhalten:** Prüft fünf lokale/Lockfile/Stdlib-Quellen, publiziert Findings, gibt aber auch bei unresolved passed=true zurück.
- **Fehler/fehlende Daten:** Nicht auflösbar ist telemetry/advisory, kein Block.
- **Prüfgegenstand:** Diff und changed_files aus EvaluationSubject; Lockfile/Working-Tree-Quellen sind nicht vollständig commitisoliert.
- **Evidence:** UnresolvedSymbol und External GateResult.
- **Vertrauen/Vollständigkeit:** Python-fokussierte Heuristik, Lockfile-/Filesystem-Sicht teilweise veränderlich.
- **Fundstellen:** `samuel/slices/symbol_resolution/gate.py#class SymbolResolutionGate`
- **Issues:** #520

### `EXT-COVERAGE-DIFF` — Coverage-Dateipräsenz-Hinweis

- **Schutzziel:** Geänderte Python-Dateien ohne Treffer in coverage.xml melden.
- **Tatsächliches Verhalten:** Fehlende, unlesbare oder negative Coverage besteht immer mit passed=true; misst weder Diff-Coverage noch Schwellenwert.
- **Fehler/fehlende Daten:** Alle Datenfehler sind No-op/telemetry, nie blockierend.
- **Prüfgegenstand:** changed_files ist Subject-gebunden; coverage.xml besitzt keine Head-/Tool-Bindung.
- **Evidence:** Nur External GateResult-Reason.
- **Vertrauen/Vollständigkeit:** Lokale, potenziell stale Cobertura-Datei.
- **Fundstellen:** `samuel/slices/coverage_gate/gate.py#class CoverageDiffGate`
- **Issues:** #518

### `SEC-DIFF-SECRET-SCAN` — Commitgebundener Diff-Secret-Scanner

- **Schutzziel:** Hochpräzise Credentials im vollständigen Candidate-Diff blockieren und formatbasierte Risikosignale wertfrei dokumentieren.
- **Tatsächliches Verhalten:** DiffSecretGate scannt im CreatePR-Pfad ausschließlich hinzugefügte Zeilen des vollständigen, unveränderlichen Base-/Head-Diffs. Zugewiesene Secrets, Bearer-, GitHub-/sk-Präfixe und PEM-Private-Key-Marker blockieren; JWT-Form und AWS-Access-Key-ID sind advisory. Entfernte Secret-Zeilen blockieren die Bereinigung nicht.
- **Fehler/fehlende Daten:** Ein blockierender Regelfund liefert passed=false; advisory Regeln liefern passed=true plus SecretRiskDetected. Scanner-Ausnahmen blockieren vor GatesPassed und PR-Erstellung.
- **Prüfgegenstand:** GateContext.diff stammt aus EvaluationSubject.base_sha...head_sha; GateResult und GateEvaluationCompleted tragen denselben Subject einschließlich Contract- und Policy-Bindung.
- **Evidence:** Commitgebundene GateFailed-/GateEvaluationCompleted-Evidence für blockierende Regeln; SecretRiskDetected bindet advisory Regel-IDs und Diff-Zeilen an denselben Subject. Trefferwerte werden nie ausgegeben.
- **Vertrauen/Vollständigkeit:** Vollständiger Diff innerhalb des fail-closed Ressourcenlimits aus #515; gemeinsame Built-in-Regeln sind nur eine Baseline. Generische Entropie wurde wegen False Positives verworfen. #520 liest SCM-Check-Facts und ist kein spezialisierter Fremdscanner-Ingest.
- **Fundstellen:** `samuel/core/security_policy.py#SECRET_RULES`, `samuel/slices/security/gate.py#class DiffSecretGate`, `samuel/slices/security/handler.py#scan_diff_for_secrets`, `samuel/core/bootstrap.py#DiffSecretGate`
- **Issues:** #474, #481

### `SEC-PROMPT-INJECTION-SIGNAL` — Normalisiertes Prompt-Injection-Risikosignal

- **Schutzziel:** Einfache verdächtige Phrasen als Risikosignal erkennen.
- **Tatsächliches Verhalten:** Neun Phrasen-/Rollenmuster prüfen nach NFKC, Casefold, Entfernung von Formatzeichen und begrenztem ASCII-Confusable-Skeleton jeden Prompt von Planning, Implementation, Healing und Review; Treffer bleiben gemäß E7 advisory.
- **Fehler/fehlende Daten:** Ein Treffer blockiert nicht allein; ein Analyzer-Fehler wird gewarnt und stoppt den Worker-Pfad nicht. Deterministische Artefaktverstöße werden separat blockiert.
- **Prüfgegenstand:** Issue-, Input-Quellen- und Correlation-ID vor oder während Candidate-Erzeugung; kein EvaluationSubject und keine Merge-Evidence behauptet.
- **Evidence:** PromptInjectionRiskDetected mit Input-Quelle, Indikator-IDs, disposition=advisory, OWASP- und AI-Act-Zuordnung; kein roher Prompt im Event.
- **Vertrauen/Vollständigkeit:** Begrenzte Matching-Heuristik ohne vollständige UTS-39- oder Paraphrasen-Abdeckung; weder Vollständigkeitsbeweis noch harte Prompt-Injection-Grenze.
- **Fundstellen:** `samuel/core/security_policy.py#normalize_prompt_signal_text`, `samuel/slices/security/handler.py#inspect_text`, `samuel/slices/planning/handler.py#_inspect_prompt_risk`, `samuel/slices/implementation/handler.py#on_prompt`, `samuel/slices/healing/handler.py#prompt_risk_analyzer`, `samuel/slices/healing/bound.py#class BoundHealingCoordinator`, `samuel/slices/review/handler.py#prompt_risk_analyzer`, `samuel/core/events.py#class PromptInjectionRiskDetected`
- **Issues:** #474, #481, #485

### `SEC-COMMAND-SAFETY` — Aktionsnahe destruktive Core-Git-Policy

- **Schutzziel:** Force-Push und Hard-Reset über den von S.A.M.U.E.L. genutzten Git-Ausführungspfad verhindern.
- **Tatsächliches Verhalten:** samuel.core.git prüft das tokenisierte Argument-Array unmittelbar vor subprocess.run und lehnt git push --force, git push -f sowie git reset --hard ab; die Security-Diagnose delegiert an dieselbe Git-Policy.
- **Fehler/fehlende Daten:** Ein Treffer startet keinen Subprozess und liefert einen expliziten Fehler. Andere subprocess-Aufrufer und destruktive Operationen außerhalb von samuel.core.git sind nicht umfasst.
- **Prüfgegenstand:** Aktionsgebunden, nicht Candidate- oder Contract-gebunden.
- **Evidence:** Fehlerergebnis und Logeintrag; Tests beweisen, dass subprocess.run nicht aufgerufen wird.
- **Vertrauen/Vollständigkeit:** Argumentvektor statt Shell-Freitext am realen Git-Pfad; andere Subprozess- und Tool-Pfade sind ausdrücklich nicht umfasst.
- **Fundstellen:** `samuel/core/command_safety.py#validate_command_args`, `samuel/core/git.py#validate_command_args`, `samuel/slices/security/handler.py#validate_command_safety`
- **Issues:** #474, #481

### `QUAL-LOCAL-EVIDENCE` — Self-Workflow lokaler Quality-Preflight

- **Schutzziel:** Konfigurierte IQualityCheck-Adapter für geänderte Dateien ausführen.
- **Tatsächliches Verhalten:** Nur self.json ruft RunQuality auf; andere ausgelieferte Workflows überspringen ihn. config/hooks.json::quality_checks.extensions wird strikt validiert und wirksam ausgewertet; Ergebnisse unterscheiden passed, failed und not_applicable.
- **Fehler/fehlende Daten:** Im Self-Workflow blockiert QualityFailed den direkten Folgeschritt; in anderen Workflows ist die Kontrolle nicht im Pfad.
- **Prüfgegenstand:** Working-Tree-Dateien vor EvaluationSubject, keine Head-/Tool-Digest-Evidence.
- **Evidence:** QualityPassed/QualityFailed mit Statussummen, ausdrücklich ohne commitgebundenen Receipt.
- **Vertrauen/Vollständigkeit:** Lokale Checks und veränderlicher Arbeitsbaum, keine Remote-CI-Evidence.
- **Fundstellen:** `samuel/slices/quality/handler.py#class QualityHandler`, `config/workflows/self.json`, `config/hooks.json`
- **Issues:** #441, #518

### `PROC-ACCEPTANCE-CONTRACT` — Freigegebener strukturierter Acceptance Contract

- **Schutzziel:** Freigegebene Kriterien mit stabilen IDs, Scope und manueller/automatischer Semantik an den Candidate binden.
- **Tatsächliches Verhalten:** Der vorhandene Plan wird deterministisch als Contract-Schema v2 mit Revision, Scope-Schema v1, inhaltsbasierten stabilen Kriteriums-IDs, automatic/manual-Modus und Approval-Receipt strukturiert. Neue SCM-gebundene Pläne führen zusätzlich den systemerzeugten PlanningSourceSnapshot im selben Contract; Checkboxzustände sind keine Vertragsdaten. TEST akzeptiert vor PlanPosted dieselbe sichere logische Testnamen-/Pytest-Node-ID-Grammatik wie Gate 11. Ein formal ungültiger Erstentwurf besitzt keine Authority und darf genau den vorhandenen Planning-Retry mit Parserdiagnose verbrauchen; dessen Entwurf wird unabhängig von einer Score-Steigerung erneut kanonisch geparst.
- **Fehler/fehlende Daten:** Ein nach dem einzigen Retry weiterhin ungültiger Vertrag wird als letzter nicht autoritativer Entwurf sichtbar blockiert; nach verbrauchtem Contract-Retry löst auch ein Pre-Check-Fehler keinen zweiten LLM-Aufruf aus. Fehlender/leerer/doppelter Vertrag, selbstdeklarierter Planning-Snapshot, ungebundene Freigabe, ein vom Verifier nicht ausführbarer TEST-Selektor oder Abweichung zu Contract, Repository, Issue, Base, Head oder Policy blockiert vor Implementation beziehungsweise Gate 11. TEST wird weder still umgeschrieben noch auf Full-Suite oder einen anderen Runner umgeleitet.
- **Prüfgegenstand:** Contract-Hash bindet den PlanningSourceSnapshot und ist Bestandteil desselben EvaluationSubject wie Base, Head und Policy.
- **Evidence:** AcceptanceContract und AcceptanceEvidence werden in GateEvaluationCompleted, GatesPassed und PRCreated mitgeführt.
- **Vertrauen/Vollständigkeit:** Plantext bleibt unvertrauenswürdig; Parser, exakte IDs, Subject-Vergleich und Approval-Receipt entscheiden außerhalb des LLM.
- **Fundstellen:** `samuel/core/acceptance.py#class AcceptanceContract`, `samuel/core/acceptance.py#parse_test_criterion_argument`, `samuel/slices/pr_gates/handler.py#_resolve_subject`
- **Issues:** #519, #529, #714, #731, #754

### `PROC-EVALUATION-SUBJECT` — Unveränderlicher Candidate-Prüfgegenstand

- **Schutzziel:** Repository, Base, Head, Contract und Policy für alle Gate-Ergebnisse identisch binden.
- **Tatsächliches Verhalten:** EvaluationSubject ist frozen; Diff und changed_files stammen aus exakt Base...Head und Überschreitung blockiert ohne Teilbewertung.
- **Fehler/fehlende Daten:** Fehlende/ungültige Revision, Vergleichsfehler, Widerspruch oder Größenlimit ergibt not_evaluated und keinen Gate-Erfolg.
- **Prüfgegenstand:** Ist selbst die gemeinsame Subject-Identität.
- **Evidence:** GateEvaluationCompleted und jedes GateResult tragen den vollständigen Subject.
- **Vertrauen/Vollständigkeit:** Lokale Git-Objekte plus SCM-Refauflösung; serverweite Merge-Regeln bleiben separat.
- **Fundstellen:** `samuel/core/evaluation_subject.py#class EvaluationSubject`, `samuel/adapters/git_compare.py#compare_local_commits`, `samuel/slices/pr_gates/handler.py#_resolve_subject`
- **Issues:** #515

### `PROC-PASSIVE-CANDIDATE-SUBMISSION` — Passive Prüfung eines bestehenden Git-Candidates

- **Schutzziel:** Einen vorhandenen Candidate operatorgebunden prüfen, ohne dem Aufrufer Approval-, Policy-, PR-, Implementierungs- oder Healingauthority zu verleihen.
- **Tatsächliches Verhalten:** SubmitCandidate akzeptiert ausschließlich Issue-Zuordnung und vollständigen Head-SHA. Der Handler rekonstruiert aktiven Plan, Plan-Kommentar-ID, menschliche Approvalquelle, PlanningSourceSnapshot, Contract und wirksame Policy aus SCM und Control Plane, bindet Repository/Base/Head und führt die bestehenden prozessfreien Preflight-Gates aus. Eine exakte bereits persistierte bound_acceptance_evidence kann passiv abschließen; ohne sie bleibt der Lauf bis zum Provideranschluss #679 CandidateVerificationPending. Wiederholung erzeugt denselben submission_key und keinen Providerauftrag.
- **Fehler/fehlende Daten:** Fehlende Zuordnung, unvollständiger oder abweichender Head, fremdes Repository, geschlossener Gegenstand, fehlender/alter Plan oder Approval, Issue-/Base-Drift, ungültige Evidence und Required-Fehler werden begründet abgelehnt oder terminal negativ abgeschlossen. Pending ist weder Erfolg noch terminaler Fehler. Kein Pfad erzeugt PR, Implement, Healing, Claim oder Labelmutation.
- **Prüfgegenstand:** PlanningSourceSnapshot bindet Repository, Base und Issue-Digest; EvaluationSubject ergänzt vollständigen Head, Contract und wirksame Policy. Die Approvalquelle und Plan-Kommentar-ID werden zusätzlich im Submission-Ereignis geführt.
- **Evidence:** CandidateVerificationPending, CandidateEvaluationCompleted, CandidateEvaluationFailed oder CandidateSubmissionRejected mit submission_key, begrenztem Grund und mutation_authority=none; Dashboard und Run-Projektion unterscheiden pending, evaluated und blocked.
- **Vertrauen/Vollständigkeit:** SCM- und Control-Plane-Daten sind Authority. Producerinput kann keine Authorityfelder setzen; Events enthalten keine Candidate-Inhalte oder Credentials. Der erfolgreiche neue providergebundene Pfad bleibt #679.
- **Fundstellen:** `samuel/core/commands.py#class SubmitCandidateCommand`, `samuel/slices/pr_gates/handler.py#handle_candidate`, `samuel/core/workflow_outcome.py#reduce_workflow_outcome`, `samuel/cli.py#_cmd_candidate`
- **Issues:** #521, #679

### `PROC-BOUND-EXECUTION-PROVIDER` — Gebundene externe Candidate-Verifikation

- **Schutzziel:** Candidatekontrollierte automatische Akzeptanzprüfung über einen schmalen externen Execution Provider ausführen, ohne Request-, Subject-, Gate-, Healing- oder Recoveryauthority an Candidate oder Provider abzugeben.
- **Tatsächliches Verhalten:** Nach allen lokalen prozessfreien Required-Preflights persistiert der Coordinator einen versionierten Verification Request, Dispatch-Intent und Resume-Checkpoint vor dem einmaligen Gitea-Dispatch. Request und Evidence binden Planinstanz, Approvalquelle, Repository/Base/Head, Contract, Policy, Kriterien, Providerprofil, Nonce, Run/Attempt, Workflow-, Tool- und Environment-Digest, Issuer, Freshness und Integrität. Unbekannter POST-Ausgang wird ohne zweiten POST gegen denselben Request reconciliert. Vor Required-Verwendung werden aktiver Plan, aktuelle Approvalquelle, Subject und Policy erneut aus SCM und Control Plane gelesen. Passive Nutzung bleibt mutationsfrei; der autorisierte Referenz-Worker kann erst nach gültiger kriteriumsweiser Evidence Gate 11, bestehendes genau-ein-Fehler-Healing und PR fortsetzen. Provider-Resume setzt bei Evidence/CreatePR fort und sendet nie Implement.
- **Fehler/fehlende Daten:** Preflightfehler dispatchen nicht. Fehlende oder mehrdeutige Runzuordnung, falscher Request/Subject/Attempt, unerwarteter Workflow/Tool/Environment/Issuer, manipulierte, stale oder replayte Evidence sowie Authoritydrift blockieren fail-closed. Provider-Trust- und Infrastrukturfehler publizieren keine GateEvaluationCompleted-Mutationsauthority und sind nicht healbar. Ein bestätigter Dispatch ist kein Verifikationserfolg. Es gibt keinen blinden POST-Retry und keinen automatischen lokalen Fallback.
- **Prüfgegenstand:** VerificationRequest und ProviderEvidence tragen denselben vollständigen EvaluationSubject; Request-Key bindet zusätzlich genaue Authority, Kriterien, wirksame Policy, Profil, Nonce, Zeitpunkt und Consumerrolle. Run/Attempt bleiben von Request und Observation getrennt.
- **Evidence:** ProviderVerificationRequested/Pending/Blocked, ProviderGateEvaluationCompleted beziehungsweise der normale gebundene GateEvaluationCompleted-Pfad führen Request-Key, Profil und optional Run/Attempt; Authority-, Intent- und Checkpointrecords sichern Recovery. Dashboard und Audit projizieren begrenzte Identitäten und Gründe ohne Credentials oder Candidateinhalt.
- **Vertrauen/Vollständigkeit:** Der Gitea-Referenzadapter prüft Workflowinhalt am Run-Head, exakte Run-/Attemptbindung, ein begrenztes Einzeldatei-Artefakt und HMAC-SHA256 mit getrennt injiziertem Schlüssel. HMAC ist Referenzprofil, keine globale Signaturpflicht. Scheduling, Runner, Tokenminimierung, Egress, Ressourcen und Cache-Isolation bleiben externe Betriebs-/Qualificationverantwortung. Das ausgelieferte Platzhalterprofil ist disabled und required_qualified=false; der lokale Verifier bleibt bis zum real belegten atomaren Cutover aktiv.
- **Fundstellen:** `samuel/core/types.py#class VerificationRequest`, `samuel/core/ports.py#class IExecutionProvider`, `samuel/slices/provider_verification/coordinator.py#class ProviderVerificationCoordinator`, `samuel/adapters/gitea/execution_provider.py#class GiteaExecutionProvider`, `samuel/slices/pr_gates/handler.py#handle_provider_candidate`, `samuel/slices/resume/handler.py#_resume_provider`, `config/execution.json`
- **Issues:** #520, #521, #679

### `PROC-PR-HEAD-REVALIDATION` — PR-Head-Revalidierung vor Evidence und Auto-Merge

- **Schutzziel:** Veraltete Gate-Evidence bei verändertem PR-Head widerrufen.
- **Tatsächliches Verhalten:** Vergleicht PR Base/Head nach Erstellung und nach einem gebundenen strukturierten Review-Pass erneut unmittelbar vor dem optionalen internen Auto-Merge.
- **Fehler/fehlende Daten:** Abweichung oder nicht lesbare Revision blockiert fail-closed; Auto-Merge bleibt zusätzlich ohne explizite Deploymentqualification der nativen Expected-Head-Bedingung manuell.
- **Prüfgegenstand:** Exakter EvaluationSubject.
- **Evidence:** EvaluationSubjectInvalidated widerruft Dashboard-/Label-Erfolg.
- **Vertrauen/Vollständigkeit:** Nur S.A.M.U.E.L.-Pfad; externe Mergeaktionen werden durch SCM-Regeln kontrolliert.
- **Fundstellen:** `samuel/slices/pr_gates/handler.py#_pr_matches_subject`, `samuel/slices/review/handler.py#_auto_merge`, `samuel/adapters/gitea/adapter.py#merge_pr_expected`, `samuel/core/events.py#class EvaluationSubjectInvalidated`
- **Issues:** #515, #468

### `PROC-BOUND-REVIEW-MERGE` — Strukturierter Reviewentscheid und erwarteter-Head-Merge

- **Schutzziel:** Nur ein an Subject, Diff, Policy, Tool und Prompt gebundener Review-Pass darf einen optionalen Mergeversuch anfordern; die native SCM-Authority entscheidet die Wirkung.
- **Tatsächliches Verhalten:** Der Reviewhandler akzeptiert genau ein geschlossenes JSON-Schema mit pass, block oder indeterminate und Findings. Der Providervertrag überträgt den vollständigen lokalen EvaluationSubject nur als kanonischen SHA-256-Digest; dadurch bleiben Repositoryadressen aus der Provider-Nutzlast, während der lokale ReviewDecision weiterhin den vollständigen Subject trägt. Der Reviewhandler redigiert den tatsächlich gesendeten Prompt mit der effektiven Privacyregel, bevor er dessen bindenden Promptdigest berechnet; die nachgelagerte Adapterredaktion ist idempotent. Prosa, Transporterfolg oder Bindungsdrift ergeben keinen Pass. auto_merge_pr ist default-off und läuft erst nach dem Review; vor Wirkung werden aktiver Plan, unveränderte menschliche Approval-Evidence, Required-Gateresultate und PR-Revision erneut gelesen. Zusätzlich muss expected_head_merge_qualified für die konkrete Installation gesetzt sein. Der Gitea-Adapter sendet head_commit_id. Ein an Subject und Review-Digest gebundener merge_pr-Intent wird nach der Wirkung gegen PR-Mergedstatus und Revision reconciliert; doppelte Zustellung und Restart wiederholen den Merge nicht.
- **Fehler/fehlende Daten:** Fehlendes oder ungültiges Schema, block/indeterminate, Approval-/Gate-/Subjectdrift sowie fehlende oder nicht qualifizierte erwartete-Head-Fähigkeit blockieren beziehungsweise bleiben manuell. Ein unbekannter Mergeausgang bleibt unresolved und MergeOutcomeUnknown; spätere Reconciliation liest die reale SCM-Postcondition, ohne Raceloop oder unsicheren Fallback.
- **Prüfgegenstand:** ReviewDecision bindet den vollständigen lokalen EvaluationSubject über dessen kanonischen SHA-256-Digest sowie Diff-SHA-256, Policy-Version/-Digest, Toolvertrag und den Digest des tatsächlich privacy-redigierten Providerprompts; der Mergeintent bindet PR, erwarteten Head und Review-Digest.
- **Evidence:** ReviewCompleted, ReviewBlocked, MergeOutcomeUnknown und PRMerged tragen Korrelation, Issue, PR und begrenzte Bindungs-/Grunddaten; Dashboard und Audit verwenden dieselben Events.
- **Vertrauen/Vollständigkeit:** Reviewprovider produzieren Candidates ohne Approval- oder Mergeauthority. Repositoryadressen des EvaluationSubject werden dem Provider nur als kanonischer Digest übergeben; der vollständige Subject bleibt in lokaler Evidence. Nur die frische menschliche SCM-Freigabe und native SCM-Mergebedingung autorisieren den Effekt. Findings können SCM-/Auditdaten enthalten und folgen deren Retentionklasse; Credentials werden nicht in Intent oder Events kopiert.
- **Fundstellen:** `samuel/core/review.py#class ReviewDecision`, `samuel/slices/review/handler.py#class ReviewHandler`, `samuel/adapters/gitea/adapter.py#merge_pr_expected`, `samuel/slices/state_reconcile/handler.py#StateReconcileCoordinator`, `samuel/core/workflow_outcome.py#reduce_workflow_outcome`
- **Issues:** #468, #869

### `PROC-HUMAN-PLAN-APPROVAL` — Workflowabhängige menschliche Planfreigabe

- **Schutzziel:** Implementation in kontrollierten Workflows erst nach status:approved starten.
- **Tatsächliches Verhalten:** Der ausgewählte Acceptance-/Scope-Contract wird vor jedem SCM-Kommentar geparst. Neu erzeugte Pläne benötigen genau einen strukturierten Scope; historische scope-lose Contracts bleiben nur als fehlende Evidence darstellbar. Explizite Issue-Pfade autorisieren keine gleichnamigen Dateien in anderen Verzeichnissen. GREP/GREP:NOT bleiben repositoryweit; nach einem gequoteten Pattern ist kein scheinbarer Pfadsuffix zulässig. TEST akzeptiert nur die auch in Gate 11 ausführbaren sicheren logischen Namen oder Pytest-Node-IDs mit `::`. Nur ein gültiger Contract kann PlanPosted und danach die workflowabhängige Freigabe erreichen: standard/watch/self/chat warten auf PlanApproved. Eine gültige menschliche Freigabe wird vor dem Dispatch als create-only plan_approval.v1 im bestehenden Authority-State an Repository, Issue, Plan, Contract, Akteur, Methode, Quellen-ID, Zeitpunkt, Transport und vorhandenen Source Snapshot gebunden. Gate-, Review- und Resume-Pfade rekonstruieren diesen Record unabhängig vom aktuellen Statuslabel und revalidieren aktiven Plan, Contract, Subject, Source Revision und ursprüngliche SCM-Evidence. Gatefehler, MANUAL-Wartezustände, status:failed und Restart widerrufen ihn nicht; Statuslabels bleiben Projektion. Signierter Webhook und authentifiziertes Polling verwenden bei derselben Actor-/Zeit-/Plan-/Contractbindung idempotent den zuerst materialisierten Receipt. autonomous/night/patch verwenden für klare Issues die erfolgreiche PlanValidated-Policyfreigabe, warten bei einem Contract mit Klärungsbasis aber ebenfalls auf PlanApproved. Ein gewöhnlicher PlanIssue-Lauf lehnt einen vorhandenen aktiven Plan vor LLM- und Schreibzugriffen ab. Der explizite ReplanIssue-Pfad verlangt eine Begründung, schreibt zuerst einen an Kommentar-ID und Contract-Hash gebundenen Widerruf, entfernt status:approved und status:plan, bestätigt den SCM-Zustand und erzeugt erst dann einen neuen Plan mit neuer Freigaberunde. Native Gitea-Freigaben behandeln X-Gitea-Event=issues, X-Gitea-Event-Type=issue_label und action=label_updated als authentisierten Trigger. Weil Gitea 1.27.2 kein Label-Delta im Webhook liefert, muss genau ein providerseitiges Label-Timeline-Ereignis mit issue.updated_at korrelieren und status:approved als menschliches ADD nach dem aktiven Plan ausweisen; Actor, Repository, Issue, Plan, Contract und X-Gitea-Delivery werden gebunden. Der Authority-Transport bleibt signed_webhook.
- **Fehler/fehlende Daten:** Ein formal ungültiger, fehlender, scopefremder, durch mehrdeutige GREP-Syntax belasteter oder mit einem nicht ausführbaren TEST-Selektor versehener Contract erzeugt genau einen ausdrücklich nicht autoritativen Entwurfs-/Blockierkommentar, kein PlanPosted und über PlanBlocked den fehlgeschlagenen Labelzustand. Ein vorhandener aktiver Plan verlangt explizites Re-Planning. Fehlende Begründung, ein bereits laufender Workflow, nicht bestätigte Labelentfernung, fehlender menschlicher Akteur, Bot-Evidence, ein Freigabeereignis vor dem aktiven Plan oder fehlende/fremde/stale durable Approvalauthority blockieren fail-closed; nach einem Teilfehler wird kein Ersatzplan erzeugt. Ein Statuslabel oder Approvalkommentar allein darf ohne Authority-Store keinen Authority-Record nachträglich erzeugen; widersprüchliche kanalübergreifende Replays blockieren. In autonomen Profilen bleibt nur ein klarer Plan von menschlicher Freigabe ausgenommen; eine gebundene Klärungsbasis blockiert bis zur Freigabe des exakten Plans. label_cleared, Removal, fehlende oder mehrdeutige Timeline-Evidence, Actor- oder Zeitabweichungen, historische Approvals, malformed Delivery-IDs, unbekannte Subtypen, fremde Repository- oder Issuebindungen und korrekt signierte Nicht-Approval-Events erzeugen keine Approvalauthority; ein bereits vorhandenes status:approved im Issue-Post-State genügt nie.
- **Prüfgegenstand:** AcceptanceApproval trägt Contract-Hash, Plan-Kommentar-ID, Methode, menschlichen Akteur, Quellen-ID und Zeitpunkt. plan_approval.v1 ergänzt Repository, Issue, Transport und vorhandenen Source Snapshot; Gate 11 akzeptiert nur denselben aktiven Contract, dieselbe Planinstanz und denselben Subject.
- **Evidence:** Create-only plan_approval.v1 im Authority-State; PlanApproved/PlanValidated mit acceptance_approval; AcceptanceEvidence übernimmt exakt denselben Receipt.
- **Vertrauen/Vollständigkeit:** Signierter Webhook liefert den SCM-Akteur und materialisiert den Record erst nach HMAC-Prüfung und eindeutiger Timeline-Korrelation; die Timeline ist dabei Provider-Evidence innerhalb des signed_webhook-Transports. Polling liest das providerseitige Labelereignis separat und akzeptiert nur einen benannten menschlichen Akteur nach Veröffentlichung des aktiven Plans; spätere Revalidierung prüft dieses historische Timeline-Ereignis statt das aktuelle Statuslabel. Fehlende oder nicht attributierbare Historie wird nicht als Freigabe umgedeutet; SCM-Berechtigungen und der fail-closed Authority-State bleiben Vertrauensgrenze.
- **Fundstellen:** `samuel/core/acceptance.py#latest_active_plan`, `samuel/core/acceptance.py#resolve_plan_approval`, `samuel/slices/planning/handler.py#_handle_replan`, `samuel/slices/planning/handler.py#_post_plan_candidate`, `samuel/slices/watch/handler.py#class WatchHandler`, `samuel/adapters/api/webhooks.py#_acceptance_approval`, `samuel/adapters/api/webhooks.py#_native_gitea_approval_event`, `samuel/adapters/gitea/adapter.py#def get_label_events`, `config/workflows/standard.json`, `config/workflows/autonomous.json`
- **Issues:** #519, #575, #582, #695, #713, #754, #767, #895

### `PROC-WATCH-OUTCOME` — Fail-closed Watch-Dispatch-Ergebnis

- **Schutzziel:** Polling- und CI-Aufrufern nur tatsächlich beobachtete Workflowausgänge als erfolgreiche Planung oder Freigabe melden.
- **Tatsächliches Verhalten:** Der synchrone Watch-Slice beobachtet pro Issue und Korrelation die bereits vorhandenen PlanPosted- und terminalen Workflowevents. ErrorMiddleware bildet auch normale Command-Exceptions inhaltlich begrenzt auf ein korreliertes WorkflowAborted ab. Planning zählt nur PlanPosted ohne stärkeren Block-/Abbruchausgang; Approval zählt nur PRCreated oder PRMerged. Das Ergebnis enthält dispatched_failed und eine issuegebundene dispatch_outcomes-Liste. watch --once liefert bei mindestens einem fehlgeschlagenen Dispatch oder fehlendem strukturiertem Scanergebnis Exit 1.
- **Fehler/fehlende Daten:** PlanBlocked, WorkflowAborted und andere terminale Fehler sowie ein Dispatch ohne beobachtbaren Erfolgs- oder Fehlerausgang werden fail-closed gezählt. Ein gemischter Batch behält die einzelnen Ausgänge und kann erfolgreiche Nachbarissues nicht in Fehler umdeuten.
- **Prüfgegenstand:** Vor Candidate und EvaluationSubject; gebunden an SCM-Issue und Workflow-Korrelation des ScanIssues-Laufs.
- **Evidence:** Maschinenlesbares Watch-Ergebnis mit dispatched, planned, approved, dispatched_failed und dispatch_outcomes sowie Prozess-Exit von watch --once.
- **Vertrauen/Vollständigkeit:** Verwendet ausschließlich synchrone Core-Workflowevents; erzeugt keinen neuen State-Store, Retrypfad oder Freigabeautorität. Strukturierte Fehlerdiagnostik im Dashboard bleibt getrennt in #697.
- **Fundstellen:** `samuel/slices/watch/handler.py#_finish_dispatch`, `samuel/core/workflow_outcome.py#reduce_workflow_outcome`, `samuel/core/bus.py#_publish_command_abort`, `samuel/cli.py#_cmd_watch`
- **Issues:** #696

### `PROC-AC-VERIFIER` — Tagbasierter ACVerificationHandler

- **Schutzziel:** Automatische DIFF/EXISTS/IMPORT/GREP/TEST-Kriterien auswerten, TEST-Runner-Readiness vor Candidate-Erzeugung belegen und MANUAL als getrennte menschliche Readiness ausweisen.
- **Tatsächliches Verhalten:** Planning löst für TEST vor PlanPosted die einzelne effektive Runner-Policy auf, gibt dem Planprompt nur die daraus abgeleitete Selektorgrammar und prüft Installation sowie Selektor ohne Testausführung; der Control-Plane-Befehl gelangt nicht ins LLM. Doctor verwendet denselben Core-Resolver. Der CreatePR-Pfad führt den Handler genau einmal nach bestandenem Required-Preflight und vor Gate 11 in einem detached Worktree des Head-SHA aus; DIFF nutzt die unveränderliche Comparison. GREP/GREP:NOT prüfen ihr vollständiges Pattern repositoryweit über unterstützte Code-/Konfigurationsdateien; Parser und Verifier teilen dieselbe Argumentsemantik und akzeptieren keinen scheinbaren Pfadsuffix nach einem gequoteten Pattern. Bei einem Required-Preflight-Fehler wird der Handler nicht aufgerufen und Gate 11 bleibt skipped_precondition. Gate 11 validiert die erzeugte Evidence ohne zweite Ausführung. MANUAL wird nur mit exaktem menschlichem Receipt passed. Der alte Scoring-Vorlauf ist nicht verdrahtet.
- **Fehler/fehlende Daten:** Unbekannte Tags, mehrdeutige GREP-Syntax, fehlender TEST-Runner, fehlende Toolchain, runner-inkompatible Selektoren und Verifier-/Worktreefehler ergeben error beziehungsweise blockieren einen neuen Plan nach höchstens einem Retry vor PlanPosted; es gibt kein Umschreiben, keine Installation und keinen Runner-/Full-Suite-Fallback. Test-/Kriteriumsfehler sind failed; fehlende MANUAL-Quittung ist manual_pending. Kein unbekannter Zustand ist erfolgreich.
- **Prüfgegenstand:** CreatePR-Evidence trägt Repository, Base, Head, Contract-Hash, Policy-Version und -Digest des EvaluationSubject; der Digest umfasst die bootstrapgebundene TEST-Runner-Policy und das Candidate-Prozessumgebungsprofil.
- **Evidence:** AcceptanceEvidence mit kriteriumsweisen passed/failed/manual_pending/not_applicable/missing_evidence/error-Statuswerten; IMPORT/TEST weisen das Candidate-Prozessumgebungsprofil aus; historische Scoreevents bleiben nur lesbar.
- **Vertrauen/Vollständigkeit:** Automatische Ausführung im detached Candidate-Worktree. IMPORT/TEST erhalten keine Parent-Environmentwerte, aber weiterhin dieselben OS-Rechte ohne Host-/Netz-/Ressourcensandbox. TEST-Befehl, Timeout und Policy-Version stammen aus der Control Plane; Candidate-Marker wählen nur feste Templates. MANUAL-Receipt bindet menschlichen SCM-Kommentar an Kriterium, Contract und Head.
- **Fundstellen:** `samuel/core/test_runner.py#check_test_readiness`, `samuel/slices/ac_verification/handler.py#class ACVerificationHandler`, `samuel/slices/pr_gates/handler.py#VerifyACCommand`, `samuel/slices/setup/env_io.py#build_doctor_report`
- **Issues:** #399, #519, #612, #613, #620, #713, #756

### `PROC-CANDIDATE-ENVIRONMENT` — Sterile Candidate-Prozessumgebung

- **Schutzziel:** Candidate-IMPORT- und TEST-Prozesse ohne geerbte Agent-Credentials, Git-Pfadoverrides oder Benutzerprofile starten.
- **Tatsächliches Verhalten:** Eine Core-Funktion erzeugt je IMPORT-/TEST-Prozess ein Environment ausschließlich aus der versionierten Allowlist sowie kurzlebige HOME/TMP/XDG-Verzeichnisse. PATH besteht aus Interpreter-, festen System- und bei absoluter Control-Plane-Konfiguration Runner-Verzeichnissen; der Parent-PATH wird nicht kopiert.
- **Fehler/fehlende Daten:** Fehler beim Environment-Aufbau oder Prozessstart ergeben fail-closed error-Evidence. Payloads nennen nur Fehlerklasse und Environment-Profil, nie Environmentwerte.
- **Prüfgegenstand:** Die Profilversion steht in IMPORT-/TEST-Evidence und im EvaluationSubject.policy_digest.
- **Evidence:** AcceptanceEvidence und TestRunCompleted nennen process_environment_profile=verifier-sterile.v1; die Runtime-Referenz generiert die exakte Schlüsselallowlist aus dem Core-Modul.
- **Vertrauen/Vollständigkeit:** Keine Parent-SCM-/LLM-/Cloud-/Signing-Credentials, Git-Pfad-/Askpasswerte, PYTHONPATH oder Shellprofile. Gleiche Benutzerrechte, Hostdateien, Prozesssicht, Netzwerk und Ressourcen bleiben ausdrücklich außerhalb dieser Kontrolle.
- **Fundstellen:** `samuel/core/process_environment.py#verifier_process_environment`, `samuel/slices/ac_verification/handler.py#_check_import_at_candidate`, `samuel/slices/ac_verification/handler.py#_check_test`
- **Issues:** #613

### `PROC-AUTHORITY-PROFILE` — Gebundene Gate-Profilauflösung

- **Schutzziel:** Workflow, Gate-Profil und gebundenes Healing vor dem Runtime-Wiring als einzigen Autoritätspfad festlegen.
- **Tatsächliches Verhalten:** Standard löst leer/default auf gates.json und audit auf gates.audit.json auf; Self erzwingt gates.self.json unabhängig von SAMUEL_GATES_PROFILE. Legacy-Profil, Legacy-Workflows und der Authority-Schalter sind entfernt.
- **Fehler/fehlende Daten:** Veraltete Authority-Settings, Standard mit self/legacy/unbekanntem Profil sowie eine fehlende oder ungültige aktiv ausgewählte Profildatei beenden den Bootstrap vor Bus- und Slice-Wiring mit ValueError.
- **Prüfgegenstand:** Startup-Konfigurationsvertrag vor Candidate und EvaluationSubject; atomare Prozesskonfiguration statt Commit-Evidence.
- **Evidence:** Aufgelöster gates_profile-Wert und dieselbe vorvalidierte GatesConfigSchema-Instanz werden gemeinsam an PRGatesHandler übergeben; BoundHealingCoordinator ist der einzige verdrahtete Healing-Pfad.
- **Vertrauen/Vollständigkeit:** Environment und JSON-Konfiguration sind Operatorinput. Nur default/audit sind außerhalb von Self kompatibel; der geschlossene Self-Modus kann durch Environmentwerte nicht ersetzt werden.
- **Fundstellen:** `samuel/core/config.py#resolve_gate_profile`, `samuel/core/bootstrap.py#resolve_gate_profile`, `samuel/slices/pr_gates/handler.py#gates_config`
- **Issues:** #399, #579

### `PROC-WEIGHTED-SCORING` — Gebundene nicht bindende Qualitätsbeobachtung

- **Schutzziel:** Gebundene Gate-11-Evidence replaybar auf vier beobachtete Kategorien abbilden, ohne daraus Freigabeautorität abzuleiten.
- **Tatsächliches Verhalten:** Evaluation abonniert das vollständige terminale Gate-Event und persistiert über IObservationStore in SQLite. observation_key bindet Subject, Gate-Policy, GateResult-/Observation-Schema und Evidence-Digest; score_key bindet diese Beobachtung an Scoring-Policy und Formel. Jedes automatische AC zählt genau einmal, leere Familien sind n/a, Rohabdeckung bleibt separat. Ein Preflight-Block ohne Gate-11-Evidence ist ausdrücklich not_scoreable. Dashboard und Registry wählen die neueste gültige Herkunfts-/Observation-Schema-/Policy-/Formelserie; nur der attribuierte letzte LLM-Call zählt in deren Denominator, unattribuierte und andere Serien bleiben getrennt.
- **Fehler/fehlende Daten:** Fehlende oder ungültige Evidence wird als not_scoreable beziehungsweise GateEvaluationUnavailable gespeichert. ScoreObserved hat keine Workflowkante; Persistenz- oder Berechnungsfehler können den Gateentscheid nicht in einen Erfolg umdeuten.
- **Prüfgegenstand:** Vollständig an EvaluationSubject, Gate-Policy, Evidence-Digest sowie je Ableitung an Scoring-Policy und Formelversion gebunden.
- **Evidence:** GateEvaluationCompleted/-Unavailable, immutable SQLite-Observation/Derivation/Terminal und versioniertes ScoreObserved.
- **Vertrauen/Vollständigkeit:** Gate- und Acceptance-Evidence desselben Subjects; der abgeleitete Skalar bleibt Telemetrie und kein Merge-Signal.
- **Fundstellen:** `samuel/core/evaluation_observation.py#EvaluationObservationIdentity`, `samuel/slices/evaluation/handler.py#observe`, `samuel/slices/evaluation/bound_scoring.py#derive_bound_score`, `samuel/adapters/state/sqlite.py#SQLiteObservationStore`, `samuel/slices/dashboard/data.py#get_quality_from_log`, `config/eval.json`
- **Issues:** #399, #485, #589, #620, #627

### `PROC-BOUND-HEALING` — Einmaliges Healing aus gebundener Acceptance-Evidence

- **Schutzziel:** Einen eindeutig behebbaren einzelnen Gate-11-Fehler genau einmal am tatsächlich fehlgeschlagenen Candidate fortsetzen.
- **Tatsächliches Verhalten:** Der Coordinator klassifiziert nur das aggregierte GateEvaluationCompleted. Genau ein required, real ausgeführter Gate-11-Fehler und genau ein automatisches failed-Kriterium mit Verifier-Evidence Schema 1 dürfen einen LLM-Versuch auslösen; Kind und Pflichtfelder müssen zum AC-Tag passen. skipped_precondition beansprucht keinen Claim und startet kein LLM. Der SQLite-Authority-Port beansprucht observation_key transaktional vor dem LLM-Aufruf und beendet den Claim als attempted mit Outcome; nur das Operator-Kommando kann einen offenen Claim begründet auf abandoned setzen. attempts_used zählt ab HealingAttemptStarted den einen fachlichen Versuch unabhängig von internen Provider-Retries und bleibt davor null; bekannte Antwort-Tokens werden erhalten. Implementierung setzt an evaluation_subject.head_sha an und führt danach alle Gates erneut aus. Vor Claim und LLM-Aufruf muss zusätzlich eine exakte mutation_authority des Referenz-Worker-Laufs Plan-Kommentar, Contract, Approvalquelle, Workspace und Korrelation binden; passive Evaluation ist nie ausreichend.
- **Fehler/fehlende Daten:** Mehrere Fehler, MANUAL, missing_evidence, error, not_applicable, Wiederholungsfehler, Authority-/Witness-/Provider-/Budgetfehler, Reconcile, fehlende oder abweichende Mutationsauthority oder ein bereits beanspruchter Versuch führen in WorkflowBlocked; kein zweiter Healing-Versuch.
- **Prüfgegenstand:** Trigger, Kriterium und Branch-Fortsetzung sind an observation_key und den fehlgeschlagenen EvaluationSubject.head_sha gebunden. Die Mutationsauthority bindet zusätzlich Plan-Kommentar, Approvalquelle, Workspace und correlation_id.
- **Evidence:** AcceptanceEvidence mit taggebundenem Evidence-Kern, HealingClassified, HealingAttemptStarted/Completed/Aborted mit Authority-Epoch, fachlicher Attempt- und belegter Tokenzahl, SQLite-Claim claimed|attempted|abandoned und der vollständige Gate-Nachlauf. Ein früheres bound_healing_attempts.json wird checksumgebunden importiert und read-only archiviert. TEST-Auszüge sind auf 500 Zeichen begrenzt und vor der Verschachtelung gegen bekannte Secret-Muster redigiert.
- **Vertrauen/Vollständigkeit:** LLM-Vorschlag bleibt unvertrauenswürdig und erhält erst nach Commit und erneutem Required-Gate-Profil Wirkung.
- **Fundstellen:** `samuel/slices/ac_verification/handler.py#_automatic_evidence`, `samuel/slices/healing/bound.py#class BoundHealingCoordinator`, `samuel/slices/implementation/handler.py#prepare_branch_at_head`, `samuel/core/git.py#prepare_branch_at_head`, `samuel/slices/healing/bound.py#_mutation_authority_reason`
- **Issues:** #399, #485, #581, #620, #629, #521

### `PROC-WORKTREE-LIFECYCLE` — Gemeinsamer Git-Worktree-Lifecycle für Run und Verifikation

- **Schutzziel:** Candidate-Mutation und commitgebundene Verifikation in getrennten, gemeinsam verwalteten Git-Worktrees ausführen, ohne eine Prozesssandbox zu behaupten.
- **Tatsächliches Verhalten:** Ein IWorkspaceManager-Port und der GitWorktreeManager-Adapter führen eine transaktionale lokale Registry mit Run- und Verifikationsprofil. Planning verwendet ein kurzlebiges detached Verifikationsprofil für den gegen den Remote-Ref geprüften Base-Commit. Run-Worktrees starten auf genau diesem freigegebenen Commit und bleiben von Implementation über Healing, Commit, Push und synchronen Gate-Nachlauf gebunden; Gate 11 verwendet parallel einen detached Head-SHA-Worktree. Branch-/Workspace-flock, Gits eigene Worktree-Sperre, Kapazitätsbuchung, Quarantäne und kontrolliertes prune schützen den Lifecycle. Quarantänen tragen eine 168-Stunden-Operatorfrist ohne automatische Löschung; nur ein begründetes Discard terminalisiert geprüfte Evidence. Die Commit-Finalisierung bindet Parent und write-tree, umgeht geerbte Hooks per commit-tree und bewegt die Ref per update-ref-CAS. Author und Committer verwenden ein vollständiges Operatorpaar oder die stabile nicht-menschliche Referenzidentität; Attribution erteilt keine Authority und schreibt keine Git-Konfiguration. Ein gemeinsamer IGitTransportAuth-Port bindet alle Netzwerk-Fetches/-Pushes an das konfigurierte HTTP-Repository und delegiert das Credential ausschließlich über den installierten absoluten Askpass-Helper in das jeweilige Kindprozess-Environment; lokale Git- und Candidateprozesse bleiben credentialfrei. Das Referenz-Image installiert die dafür erforderliche Git-Runtime aus einer unveränderlichen, vertraglich gebundenen Debian-Snapshot- und Paketversion; Health und Publish-Probe prüfen ihre Ausführbarkeit.
- **Fehler/fehlende Daten:** Eine fehlende oder nicht ausführbare Git-Runtime sowie ein partielles Author-Override blockieren vor einem Commit; Werte aus unterschiedlichen Identitätsquellen werden nicht gemischt. Gefährliche GIT-Pfadoverrides, Netzwerkdateisystem, Verzeichnisüberlappung, fehlender Platz, volle Quarantäne, konkurrierende Eigentümer sowie Git-/CAS-/Signing-Fehler blockieren fail-closed. Fehlendes Credential oder Gitea-Benutzername, fremde/credentialtragende Remote-URL, SSH-Schema, nicht vertrauenswürdiger Askpass-Helper und nicht autorisierte Netzwerkoperation blockieren mit begrenztem Code; es gibt keinen interaktiven, globalen oder persistenten Credential-Fallback. Unerwartet abgebrochene Run-Worktrees bleiben bis zur Resume-Klassifikation erhalten; nur verwaiste oder abweichende Zustände werden quarantänisiert. Aktive und quarantänisierte Evidence wird weder automatisch entfernt noch von git worktree prune verworfen.
- **Prüfgegenstand:** workspace_id bindet Repository, Correlation/Run und Branch beziehungsweise Base-/Head-SHA; Planning- und Gate-Verifikationsworktrees prüfen den exakten PlanningSourceSnapshot beziehungsweise EvaluationSubject-Head. Commit-Intents binden workspace_id, Parent und Tree.
- **Evidence:** Workspace-Registry, CLI list/inspect/prune/quarantine, CodeGenerated.workspace_id, Content-Intent/Postcondition, system_packages-Policy samt Manifestbindung und Runtime-Probe sowie reale Linked-Worktree-, Mehrprozess-, Hook-, CAS-, Kapazitäts-, Git-Health-, frische Identitäts- und #603-Tests. Transporttests prüfen Remote-/Operationsbindung, Argv-/Config-Freiheit, fehlende Credentials, Helper-Vertrauen und die sterile Candidate-Umgebung.
- **Vertrauen/Vollständigkeit:** Worktrees enthalten unvertrauenswürdigen Candidatecode und möglicherweise Testausgaben. Sie isolieren Git-Ziel und Dateistand, aber nicht Benutzerrechte, Hostdateien, Prozesse, Netzwerk oder Ressourcen; dafür bleibt #619 zuständig. Der bestehende IAuthProvider hält das Transportcredential in der vertrauenswürdigen Runtime; beim Env-Provider kann es dort als SCM_TOKEN vorliegen und steht während Fetch/Push zusätzlich im Environment des vertrauenswürdigen Git-Kindprozesses. Der Adapter erzeugt keine persistente Kopie. Argv, Remote, Git-Konfiguration, Logs, lokale Git- und Candidatekinder bleiben frei; plattformabhängige Einsicht anderer Prozesse desselben Service-Accounts in Runtime- oder Kindprozessdaten wie /proc/<pid>/environ ist nicht ausgeschlossen und keine Mehrbenutzergarantie.
- **Fundstellen:** `samuel/core/ports.py#IWorkspaceManager`, `samuel/core/ports.py#IGitTransportAuth`, `samuel/core/workspaces.py#WorkspaceHandle`, `samuel/adapters/workspace/git.py#GitWorktreeManager`, `samuel/adapters/git_transport/http.py#HttpGitTransportAuth`, `samuel/adapters/git_transport/askpass.py#main`, `samuel/slices/implementation/handler.py#ImplementationHandler`, `samuel/slices/ac_verification/handler.py#ACVerificationHandler`, `samuel/core/git.py#commit_tree_transaction`, `docs/adr/0618-worktree-manager.md`
- **Issues:** #482, #603, #618, #619, #714, #727, #729, #739

### `PROC-BOUND-FINALIZATION-RESUME` — Gebundene Finalisierung nach Prozessneustart

- **Schutzziel:** Begonnene Commit-, Push-, Gate- und PR-Finalisierung nach hartem Prozessabbruch ohne doppelte externe Wirkung oder Adoption fremden Zustands fortsetzen.
- **Tatsächliches Verhalten:** ResumePending wird beim vollständig verdrahteten Bootstrap, vor jedem Watch-Zyklus oder operatorgeführt dispatcht. ResumeCoordinator klassifiziert persistierte Checkpoints und verwendet für die Wirkung den bestehenden Implement- und Gate-/PR-Commandpfad. Resumefähig sind ausschließlich commit_pending, push_pending, gates_pending und pr_pending. Die Übernahme erfolgt OS-Lock zuerst, danach abgelaufenes Lease per CAS, vollständiges Binding-/Git-Prädikat und SCM-Abgleich. Commit wird über Parent/Tree, Push über Remote-Revision und PR primär über notierte Nummer beziehungsweise im API-/Notierungsfenster über einen backendneutralen Marker identifiziert. Terminale Ereignisse schreiben vor Cleanup einen restartfesten Tombstone.
- **Fehler/fehlende Daten:** Reconcile, lebender OS-Lock oder Lease, fehlender Contract, Base-/Policy-/Schema-/Signing-Drift, Dirty-/Index-/HEAD-/Remote-Drift, mehrdeutiger oder abweichender PR sowie Store-/SCM-Unverfügbarkeit blockieren oder quarantänisieren mit begrenztem Reason-Code. Es gibt keinen Hard-Reset, Force-Push, zweiten PR und keine Rekonstruktion eines LLM-Rounds. Abandon und Cleanup verlangen getrennte begründete Operatoraktionen.
- **Prüfgegenstand:** Checkpoint und Intents binden Repository, Issue, correlation_id, Workflow, Boundary, Branch/Base, workspace_id, Contract-Hash, Gate-Policy-Version/-Digest, Gate-/Observation-Schema, Signing-Policy sowie erwarteten Parent/Tree beziehungsweise Candidate-Head.
- **Evidence:** SQLite-Checkpoints, Leases, Intents und Terminal-Tombstones; Worktree-Registry/OS-Lock; ResumeAttempted, ResumeCompleted und ResumeBlocked; Health/State/Dashboard-Status enabled, pending, blocked und last outcome; Operator-CLI list, inspect, attempt/resume, abandon und cleanup.
- **Vertrauen/Vollständigkeit:** Der Candidate-Worktree bleibt unvertrauenswürdig. Resume autorisiert nur eine bereits gebundene Finalisierung und erweitert weder die Prozesssandbox noch die LLM-/Prompt-/Token-Autorität. Unterstützter Restore-Reconcile ist über STATE-AUTHORITY-PERSISTENCE aktiv; PRIV-RETENTION-REPORT liefert zusätzlich ein deaktiviert ausgeliefertes operatorgeführtes Vollzugsfundament, ohne Resume-Autorität zu erweitern.
- **Fundstellen:** `samuel/slices/resume/handler.py#ResumeCoordinator`, `samuel/slices/implementation/handler.py#_resume_finalization`, `samuel/slices/pr_gates/handler.py#_find_intended_pr`, `samuel/core/ports.py#IAuthorityStateStore`, `samuel/core/ports.py#IWorkspaceManager`, `samuel/core/ports.py#IVersionControl`, `docs/adr/0482-runtime-state-store.md`
- **Issues:** #482, #618, #633, #666

### `STATE-AUTHORITY-PERSISTENCE` — Transaktionaler lokaler Autoritätszustand mit Restore-Witness

- **Schutzziel:** Claims, gebundene Finalisierungszustände und externe Wirkungsabsichten restartfest und fail-closed speichern.
- **Tatsächliches Verhalten:** SQLite-Schema v10 trennt Healing-Claims, diagnostische Round- und resumefähige Finalisierungs-Checkpoints, Operations-Intents, Leases, Restore-Operationen, Reconcile-Inventar, Authority-Metadaten, Managed-Backup-Registry, Retention-Kategorie-Autorität, Ausführungsbelege sowie Workflow-Budgetzulassungen und physische Attempt-Reservationen. Jeder autoritative Übergang erhöht die DB-Epoch und aktualisiert synchron einen separaten Witness, bevor eine abhängige externe Wirkung beginnen darf. Ein eigener Lifecycle-flock hält Leser und Schreiber während eines unterstützten Restore-Austauschs außerhalb; Staging-Prüfung, persistierter Sentinel, atomarer DB-Wechsel, neue instance_uuid und global monotone Epoch führen danach zwingend in einen vollständigen Operator-Reconcile. Commit, Push und PR-Erstellung schreiben den Intent vor der Wirkung und die unmittelbar beobachtete Postcondition danach. Startup, Watch und Operator dispatchen ausschließlich resume_eligible Finalisierungszustände über PROC-BOUND-FINALIZATION-RESUME.
- **Fehler/fehlende Daten:** DB-/Witness-Writefehler blockieren vor der nächsten abhängigen Wirkung. Fehlender oder fremder Witness, Epoch-Rückstand, Restore-Sentinel oder eine höhere optionale Audit-Epoch führt sichtbar in Reconcile; Reconcile blockiert Healing und Resume. Ein Restore mit offener Operation verlangt explizite Supersession. scan_failed wird nur durch einen erfolgreichen vollständigen Rescan verlassen; Abschluss verlangt null unresolved Einträge. Postcondition unbekannt oder abweichend bleibt unresolved beziehungsweise mismatch und wird nicht blind wiederholt.
- **Prüfgegenstand:** Claims binden observation_key; Checkpoints binden Repository-/Issue-/Korrelation-/Workflow-/Boundary-/Branch-/Base-/Head-/Workspace- und Policy-/Schemafelder; Intents binden Operation und erwarteten Candidatezustand. Die Wirkungsvoraussetzungen stehen getrennt in PROC-BOUND-FINALIZATION-RESUME.
- **Evidence:** SQLite-Tabellen einschließlich workflow_budget_admissions und llm_budget_attempts, Restore-Operation/Reconcile-Inventar, Authority-Epoch, samuel-state-authority.json, Restore-Sentinel, payloadfreie state status/dump-Zähler, AuthorityReconcileRequired sowie der Audit-Serienschnitt authority.v2 mit instance_uuid und Authority-Epoch in Healing-/CodeGenerated-/PRCreated-/Workflow-Budget-Ereignissen.
- **Vertrauen/Vollständigkeit:** Audit-JSONL ist nur zusätzliche Hochwassermarken-Evidence und kann Normalbetrieb nie autorisieren. State-Diagnose gibt keine gespeicherten Payloads aus; löschende Retention bleibt deaktiviert.
- **Fundstellen:** `samuel/core/ports.py#IAuthorityStateStore`, `samuel/adapters/state/sqlite.py#SQLiteAuthorityStateStore`, `samuel/adapters/state/legacy.py#migrate_authority`, `samuel/adapters/llm/workflow_budget.py#WorkflowTokenBudgetLLMAdapter`, `samuel/slices/state_reconcile/handler.py#StateReconcileCoordinator`, `samuel/slices/implementation/handler.py#_put_intent`, `samuel/slices/pr_gates/handler.py#_pr_intent_key`, `docs/adr/0482-runtime-state-store.md`
- **Issues:** #482, #629, #633, #666

### `EVID-DASHBOARD-WORKFLOW-OUTCOME` — Outcome-gebundene Workflow-Stage-Darstellung

- **Schutzziel:** Im Operator-Dashboard nur Outcomes anzeigen, die durch passende Gate-, Attempt- oder SCM-Evidence belegt sind.
- **Tatsächliches Verhalten:** CreatePR bleibt ohne PRCreated pending; ein terminal blockiertes Gate-Outcome markiert Gates failed und den nicht erreichten PR-Pfad blocked. HealingClassified ohne HealingAttemptStarted oder korrespondierende Attempt-Evidence bleibt not_attempted mit Attempt-Zähler 0. Planning, Implementation, gebundenes Healing und Review legen Issue und Workflow-Korrelation in einen gemeinsamen Core-Kontext; MeteringLLMAdapter übernimmt sie auf LLMCallCompleted und kennzeichnet die Bindung. Der Runtime-Logging-Bridge übernimmt dieselbe Korrelation auf DiagnosticRaised, sodass Retry-/Warn-Diagnosen innerhalb des vorhandenen Laufs bleiben. Planning publiziert einen ausgeschöpften typisierten Providerfehler als korreliertes LLMUnavailable und PlanBlocked. Eine gemeinsame Core-Reduktion klassifiziert die vollständig sortierte Ereignisfolge für Run-Projektion, Dashboard und Replay: PlanBlocked, LLMUnavailable, WorkflowBlocked, WorkflowAborted, PRCreationFailed und EvaluationSubjectInvalidated sind terminale Fehlerausgänge; PRCreated ist nur ohne nachgelagerten Reviewauftrag ein Erfolgsausgang; ReviewCompleted beendet den Reviewauftrag als reviewed, PRMerged als merged. ReviewBlocked und MergeOutcomeUnknown sind terminale Blockaden. GateFailed, EvalFailed, TokenLimitHit und HealingAborted bleiben Stage-Evidence. Die Problemprojektion bewahrt die Issue-Zuordnung jeder gruppierten Instanz und behauptet bei mehreren Issues keine einzelne Gruppen-Issue. Sicherheits-, Log-, Problem- und Statusansicht verwenden dieselbe Event-Baseline-Severity; Security-Details trennen externe Signaturfehler, interne Integritätsverletzungen und sonstige Supply-Chain-Ereignisse. Die redigierte SQLite-Projektion bleibt unabhängig von Auditrotation. Passive Candidate-Läufe werden als nichtterminal pending, terminal evaluated oder terminal blocked reduziert; die Gates-Stufe zeigt denselben Zustand ohne PR- oder Labelclaim.
- **Fehler/fehlende Daten:** Fehlende Outcome-Evidence wird nicht als Erfolg oder ausgeführter Fehlversuch hochgestuft. LLM-Aufrufe ohne gebundenen Workflow-Kontext erhalten eine unabhängige Event-ID und workflow_correlation_bound=false; Issue oder Zeitnähe werden nicht als Ersatzbindung verwendet. Ausschließlich historische beziehungsweise ausdrücklich ungebundene LLM-Telemetrie wird status=unbound und aus Runzahl/Trend ausgeschlossen. Bootstrap und Operator-CLI reklassifizieren vorhandene Projektionen idempotent; Projection-Write-Fehler blockieren den Workflow nicht und werden über DLQ/Auditdiagnose/State-Health sichtbar.
- **Prüfgegenstand:** Gate- und PR-Aussagen stammen aus GateEvaluationCompleted beziehungsweise PRCreated/PRCreationFailed/EvaluationSubjectInvalidated. Worker-LLM-Telemetrie übernimmt Issue und correlation_id aus dem synchronen Core-Workflow-Kontext; die Stage- und Call-Zuordnung ist damit an denselben Workflow-Lauf gebunden, nicht an einen Providerparameter oder eine Heuristik.
- **Evidence:** Workflow-Liste und -Detail mit gemeinsam reduziertem Status, kausalem last_event samt Eventzeit sowie done/failed/pending/blocked/not_attempted, outcomegebundenen Zählern und zugehörigem Auditgrund.
- **Vertrauen/Vollständigkeit:** Die lokale SQLite-Projektion ist Darstellungsquelle; Audit-JSONL bleibt Compliance-Evidence und initiale Backfillquelle. Die UI erzeugt keine eigene Freigabe-Evidence und ersetzt weder Gate- noch SCM-Nachweise.
- **Fundstellen:** `samuel/core/issue_context.py#issue_scope`, `samuel/core/workflow_outcome.py#reduce_workflow_outcome`, `samuel/adapters/llm/metering.py#MeteringLLMAdapter`, `samuel/slices/run_projection/handler.py#RunProjectionHandler`, `samuel/slices/dashboard/data.py#load_runtime_events`, `samuel/slices/dashboard/data.py#_derive_workflow_issue_state`, `samuel/slices/dashboard/data.py#_derive_gates_stage`, `samuel/slices/dashboard/data.py#_derive_healing_stage`, `samuel/slices/dashboard/data.py#_derive_pr_stage`, `samuel/server.py#loadWorkflowDetail`, `samuel/core/workflow_outcome.py#CandidateEvaluationCompleted`
- **Issues:** #399, #578, #627, #675, #672, #692, #698, #711, #712, #738, #521

### `EVID-AUDIT-REDACTION` — Flache Audit-Payload-Secret-Redaktion

- **Schutzziel:** Einige Tokenmuster vor Audit-Sink-Ausgabe schwärzen.
- **Tatsächliches Verhalten:** Verwendet dieselbe zentrale Regelquelle wie der Diff-Scanner und ersetzt deren Signaturen nur in top-level Stringwerten; verschachtelte Objekte und unbekannte Secretformate bleiben unberührt.
- **Fehler/fehlende Daten:** Unbekannte oder verschachtelte Secrets können in Evidence gelangen.
- **Prüfgegenstand:** Unabhängig vom Subject.
- **Evidence:** Redigierte JSONL/SARIF-Payload.
- **Vertrauen/Vollständigkeit:** Best-effort Regex, kein DLP-Gate.
- **Fundstellen:** `samuel/core/bus.py#_scrub_payload`, `samuel/core/security_policy.py#redact_secrets`, `samuel/core/security_policy.py#SECRET_RULES`
- **Issues:** #481

### `EVID-AUDIT-HMAC` — Optionale JSONL-HMAC-Kette

- **Schutzziel:** Nachträgliche Änderungen an aufeinanderfolgenden JSONL-Records erkennbar machen.
- **Tatsächliches Verhalten:** Nur bei gesetztem SAMUEL_AUDIT_HMAC_KEY; lokale POSIX-Prozesse sperren die aktuelle Rotationsdatei exklusiv, verifizieren ihren letzten Record und berechnen den nächsten HMAC gegen diesen einen Dateikopf. Das schützt lokale Records, nicht die Vollständigkeit oder den Host gegen Schlüsselkompromittierung.
- **Fehler/fehlende Daten:** Ohne Key normales unverkettetes JSONL. Bei fehlender POSIX-flock-Unterstützung, ungültigem, unsigniertem oder manipuliertem Tail sowie Schreibfehlern wird der signierte Append verweigert. Die Fallback-Datei ist eine separate Kette; Verifikation bleibt ein separater Aufruf.
- **Prüfgegenstand:** Records können Subject tragen, Kette selbst ist logbezogen.
- **Evidence:** prev_hash/hmac-Felder und verify_chain.
- **Vertrauen/Vollständigkeit:** Gemeinsamer lokaler Schlüssel und POSIX-Dateilock auf einem lokalen Dateisystem; keine externe Attestation und kein Vollständigkeitsbeleg über Haupt- und Fallback-Datei hinweg.
- **Fundstellen:** `samuel/adapters/audit/jsonl.py#_write_chained`, `samuel/adapters/audit/jsonl.py#verify_chain`, `samuel/core/bootstrap.py#SAMUEL_AUDIT_HMAC_KEY`
- **Issues:** #482, #689

### `EVID-SARIF-EXPORT` — Write-only SARIF-Findings-Export

- **Schutzziel:** Events mit OWASP-Finding als SARIF 2.1.0 ausgeben.
- **Tatsächliches Verhalten:** Exportiert Findings; kein Ingest, keine Tool-Attestation und keine allgemeine Subject-Bindung.
- **Fehler/fehlende Daten:** Nicht als Finding klassifizierte Events erscheinen nicht in SARIF; JSONL bleibt separater Sink.
- **Prüfgegenstand:** Nur wenn das Quellereignis Subjectdaten enthält.
- **Evidence:** SARIF-Datei.
- **Vertrauen/Vollständigkeit:** Lokaler Export, kein signierter Scannerreport.
- **Fundstellen:** `samuel/adapters/audit/sarif.py#class SARIFAuditSink`, `config/audit.json`
- **Issues:** #520

### `EVID-SCM-CHECK-ADVISORY` — Externe SCM-Check-Advisory-Bewertung

- **Schutzziel:** Einen vorhandenen Providerlauf begrenzt lesen, an einen EvaluationSubject binden und ohne Freigabewirkung bewerten.
- **Tatsächliches Verhalten:** samuel evidence assess liest einen expliziten Gitea-Actions-Run, projiziert nur benötigte Run-, PR-, Workflow-, Job- und Commit-Status-Facts und trennt diese vom versionierten Assessment. Ergebnis, in-toto-Statement-v1-Rahmen und immutable Observation tragen dauerhaft role=advisory und authority=none.
- **Fehler/fehlende Daten:** Ungültige Identität, falsche Base-/Head-SHA, Attempt-, Workflow- oder Statusabweichung, Widerspruch, Stale Evidence, Parserfehler und Größenüberschreitung führen zu Exit 1. Fehlende nicht autorisierende Facts bleiben als Findings sichtbar; kein Fehlerpfad dispatcht oder mutiert.
- **Prüfgegenstand:** Vollständiger EvaluationSubject wird gegen Providerinstanz/Repository, PR-Base/-Head, Run/Attempt, Workflow und operatorseitigen Statuskontext geprüft; Verification-Request-Bindung bleibt explizit unbelegt.
- **Evidence:** Versioniertes SCMCheckAssessment mit Provider-Evidence-Digest, Findings, Original-Run-Referenz und in-toto-Statement-v1-Rahmen im vorhandenen SQLite-Observation-Store.
- **Vertrauen/Vollständigkeit:** HTTP-Antworten und Subject sind größenbegrenzt; Joblogs, Workflowinhalt und unbekannte freie Payloadwerte werden verworfen. Gitea-Status, TLS, Runnerlabel oder Normalisierung erteilen keine Authority; signierte Umgebung, Toolchain und Requestbindung bleiben #679.
- **Fundstellen:** `samuel/core/external_evidence.py`, `samuel/core/ports.py#class ISCMCheckEvidenceReader`, `samuel/adapters/gitea/adapter.py#def read_check_evidence`, `samuel/cli.py#def _cmd_evidence`
- **Issues:** #520, #679

### `SCM-WEBHOOK-HMAC` — Optionale Webhook-HMAC-Verifikation

- **Schutzziel:** Webhook-Payloads bei konfiguriertem Secret authentisieren.
- **Tatsächliches Verhalten:** Bei gesetztem SLICE_HMAC_KEY wird sha256-HMAC vor dem Event-Mapping gegen die unveränderten HTTP-Request-Bytes geprüft. Native Gitea-Requests akzeptieren in X-Gitea-Signature ausschließlich einen unpräfixierten kleingeschriebenen 64-stelligen Hexdigest; GitHub-Requests akzeptieren in X-Hub-Signature-256 ausschließlich sha256=<digest>. Der Provider wird aus den konkreten Headern gebunden, Formate werden nicht permissiv vermischt und der Digestvergleich ist constant-time. Ohne Secret werden nicht autorisierende Webhooks akzeptiert; menschliche Planfreigaben über Webhook verlangen zusätzlich einen verifizierten HMAC-Transport und den durable Authority-State.
- **Fehler/fehlende Daten:** Fehlende Raw-Body-Evidence, fehlende oder malformed Signatur, unbekanntes Providerformat und falscher Digest ergeben 401 und TamperDetected; ein fehlender Schlüssel deaktiviert die allgemeine Webhookprüfung, blockiert aber jeden Webhook-Planapproval vor PlanApproved.
- **Prüfgegenstand:** Webhookereignis vor Candidate, nicht EvaluationSubject.
- **Evidence:** Begrenzte Logs für Request-Eingang, Provider/Eventtyp, Signaturergebnis und Mappingausgang sowie TamperDetected und HTTP-Status; keine Signatur, kein Secret und keine vollständige Payload werden persistiert.
- **Vertrauen/Vollständigkeit:** Shared Secret; Proxy/Transport und SCM-Berechtigungen bleiben separat.
- **Fundstellen:** `samuel/adapters/api/webhooks.py#_verify_signature`, `samuel/server.py#do_POST`, `samuel/server.py#SLICE_HMAC_KEY`
- **Issues:** —

### `EVID-CONTEXT-HMAC` — Optionale Context-Ausgabe-HMAC ohne Konsumentenprüfung

- **Schutzziel:** BuildContext-Ausgabe optional signieren.
- **Tatsächliches Verhalten:** ContextHandler erzeugt bei vorhandenem Key ein signature-Feld; kein produktiver Folgeschritt verifiziert es als Schranke.
- **Fehler/fehlende Daten:** Ohne Key keine Signatur; manipulierte Signatur wird im aktiven Workflow nicht geprüft.
- **Prüfgegenstand:** Pre-Candidate-Context, nicht EvaluationSubject.
- **Evidence:** signature-Feld im Handlerresultat.
- **Vertrauen/Vollständigkeit:** Producer-only Integritätssignal ohne Consumer-Enforcement.
- **Fundstellen:** `samuel/slices/context/handler.py#signature`
- **Issues:** #485

### `SEC-INSTALLED-CLI-ENTRYPOINT` — Installierter Console-Entry-Point als Prozessherkunft

- **Schutzziel:** Verhindern, dass ein unvertrauenswürdiges Working Directory die ausgeführte S.A.M.U.E.L.-Distribution durch ein gleichnamiges Python-Paket ersetzt.
- **Tatsächliches Verhalten:** Unterstützte Operator-, systemd- und Containerpfade starten das installierte Console-Script `samuel`; systemd löst seinen absoluten Pfad auf und blockiert ohne Script, der Containervertrag weist Modul-Entrypoints zurück.
- **Fehler/fehlende Daten:** Ein fehlender Console-Entry-Point blockiert die Service-Generierung. `python -m samuel` aus einem fremden Repository ist ausdrücklich kein unterstützter Betriebsweg, weil fremder Code vor einer eigenen Prüfung importiert werden kann.
- **Prüfgegenstand:** Bindet die Prozessherkunft an die installierte Distribution vor CLI/Bootstrap; Working Directory und PROJECT_ROOT bleiben Arbeitskontext ohne Importauthority.
- **Evidence:** Fremd-Working-Directory-Regressionstest, systemd-Unit-Vertrag und offline geprüfter Container-Entrypoint.
- **Vertrauen/Vollständigkeit:** Schützt gegen CWD-Shadowing im unterstützten Pfad; explizites PYTHONPATH, ersetztes Script und kompromittierte Installation bleiben vorgelagerte Betreiber-/Supply-Chain-Grenzen.
- **Fundstellen:** `pyproject.toml#samuel = "samuel.cli:main"`, `samuel/cli.py#_resolve_console_entrypoint`, `Dockerfile#ENTRYPOINT ["samuel"]`, `docs/adr/0583-installed-cli-entrypoint.md`
- **Issues:** #583

### `OPS-ATOMIC-LOCAL-RELEASE` — Manifestgebundene lokale Release-Aktivierung

- **Schutzziel:** Einen lokalen Produktstand vollständig ersetzen, ohne Operator-Konfiguration, State, Evidence, Workspaces oder Erweiterungen zu überschreiben.
- **Tatsächliches Verhalten:** Der Installer legt aus manifestgebundenem Wheel und hashgebundenem Runtime-Lock eine neue versionierte Geschwister-venv an, prüft Console-Script, Paketmetadaten, Importpfad, Version und vollständige Revision isoliert und schaltet erst danach einen stabilen current-Symlink per Compare-and-swap atomar um. Konfiguration, State, Logs und Service-Daten liegen außerhalb des Core.
- **Fehler/fehlende Daten:** Digest-, Versions-, Revisions- oder Importwiderspruch, ein bestehendes Versionsverzeichnis, ein unerwarteter current-Stand sowie unklassifizierte Produkt-Overlays blockieren. Der bisher aktive Release bleibt unverändert; es gibt keinen stillen Fallback und keinen automatischen State-Rollback.
- **Prüfgegenstand:** Bindet den aktivierbaren lokalen Core an genau ein Release-Manifest, eine Produktversion, eine vollständige Quellrevision, ein Wheel und einen Runtime-Lock; Persistenzpfade sind keine Produktidentitätsquelle.
- **Evidence:** Release-Receipt, isolierter Runtime-Probe-Lauf, atomarer current-Symlink und reale D0-Upgrade-Evidence nach Veröffentlichung.
- **Vertrauen/Vollständigkeit:** Nur der Operator darf den Aktivierungszeiger ändern. Self-Mode und Zielrepository erhalten keinen Schreibzugriff auf den installierten Core; extensions ist kein impliziter Importpfad.
- **Fundstellen:** `samuel/local_release.py#stage_release`, `samuel/local_release.py#activate_release`, `tools/release_gate.py#materialize_runtime_lock`, `docs/adr/0706-atomic-release-layout.md`
- **Issues:** #706, #658

### `SCM-REQUIRED-HEAD-CHECK` — Gitea Required CI Check am PR-Mergepunkt

- **Schutzziel:** Merge in main ohne erfolgreichen, exakt konfigurierten Required-Check-Status für den aktuellen PR-Head verhindern.
- **Tatsächliches Verhalten:** SCM_REQUIRED_STATUS_CONTEXT definiert genau einen Soll-Kontext; bei fehlender Variable gilt der sichtbar gemeldete ausgelieferte Default. Setup und Dashboard persistieren den Wert, Doctor vergleicht ihn exakt mit der nativen Gitea-Regel. Die reale positive und negative Qualification aus #694 steht noch aus.
- **Fehler/fehlende Daten:** Leere oder mehrzeilige Sollwerte, fehlender Lesezugriff, fehlende Regeln und jede Kontextabweichung blockieren fail-closed. Fehlende, wartende, fehlgeschlagene oder nur für einen anderen Head vorhandene Statuswerte blockieren den PR-Merge.
- **Prüfgegenstand:** Provider und effektiver Soll-Kontext sind Bestandteil des Gate-Policy-Digests und damit der Evidence- und Resume-Bindung; der externe SCM-Status bleibt an den aktuellen PR-Head gebunden.
- **Evidence:** Deterministische Config-, Setup-, Doctor-, Policy-Digest- und Resume-Drifttests; bestehender Live-Regel- und Statusnachweis aus #441. Der neue Live-Nachweis für #694 bleibt Abschlussbedingung.
- **Vertrauen/Vollständigkeit:** Der Sollwert stammt nur aus Operator-Konfiguration oder sichtbar gemeldetem Default, nie aus beobachtetem SCM-Zustand. Branchschutz bleibt zeitabhängige externe Gitea-Konfiguration und erfordert kurzlebigen Admin-Lesezugriff zur Qualification.
- **Fundstellen:** `samuel/core/config.py#resolve_scm_required_status_context`, `samuel/slices/setup/env_io.py#build_doctor_report`, `samuel/core/evaluation_subject.py#gate_policy_binding`, `docs/INSTALL.md#Verbindlich: nativer Schutz des Release-Branches`
- **Issues:** #441, #518, #694

### `SCM-DIRECT-PUSH-PROTECTION` — Schutz vor normalen direkten Pushes auf main

- **Schutzziel:** Jede Änderung an main durch den geschützten Mergepfad zwingen.
- **Tatsächliches Verhalten:** Auf der auditierten Gitea-Instanz ist die native main-Regel mit enable_push=false, leeren Push-/Force-Allowlists, deaktiviertem Force-Push, exaktem konfiguriertem Required Check und gesperrtem Admin-Merge-Override aktiv. Normale Fast-Forward-/Force-Pushes und Branch-Löschung wurden live abgelehnt.
- **Fehler/fehlende Daten:** Doctor meldet einen ungültigen Soll-Kontext, fehlenden Lesezugriff, eine fehlende Regel und jede Abweichung vom effektiven SCM_REQUIRED_STATUS_CONTEXT eindeutig als Release-Blocker; andere Installationen sind bis zu diesem Betriebsnachweis nicht freigegeben.
- **Prüfgegenstand:** Direkte Ref-Updates auf main sind unabhängig vom Absender gesperrt; PR-Merges verwenden den Gitea-Status des aktuellen Head-SHA. Provider und erwarteter Kontext sind in den Gate-Policy-Digest gebunden.
- **Evidence:** Deterministische Policy-, Sollwert- und Doctor-Tests sowie positive/negative Live-Nachweise in #528; die installationsspezifische Live-Qualification des neuen Sollwertpfads bleibt in #694 offen.
- **Vertrauen/Vollständigkeit:** Externe veränderliche Gitea-Konfiguration; Admin-Lesezugriff ist nur für die Betriebsprüfung erforderlich und Zugangsdaten gehören nicht in Evidence.
- **Fundstellen:** `samuel/slices/setup/env_io.py#gitea_release_policy_deviations`, `samuel/core/config.py#resolve_scm_required_status_context`, `docs/INSTALL.md#Verbindlich: nativer Schutz des Release-Branches`
- **Issues:** #124, #528, #694

### `PRIV-RETENTION-REPORT` — Digestgebundener Retention-Vertrag mit deaktiviertem Vollzugsfundament

- **Schutzziel:** Gespeicherte Kategorien, Zeitanker, Feldklassifikation und Schutzgründe vollständig sichtbar machen und einen einzelnen Löschplan ausschließlich nach expliziter, gebundener Operatorfreigabe ausführen.
- **Tatsächliches Verhalten:** Schema v10 stellt über IRetentionStateStore 26 State-Tabellen einschließlich der konservativ klassifizierten Identity- und Workflow-Budgettabellen bereit; der Privacy-Slice ergänzt Workspace-Registry, Audit-JSONL und Quarantäne zu 29 Kategorien. IRetentionExecutionStore besitzt keinen generischen Tabellen-/SQL-Zugriff und registriert ausschließlich score_derivations als Löschstrategie. Kategorie-Zustände, gebundene Cutoff-/Aktivierungszeiten und append-only Ausführungsbelege sind persistent. Dry-Run erzeugt einen Digest über Kategorie-/Profilpolicy einschließlich Klassifikations-/Schutzvertrag, Plan-Schemaserie, absoluten UTC-Cutoff, Anker und sortierte SHA-256-Objektidentitäten des ausgewerteten Kandidatenstatus. Aktivierung prüft die effektive Kalenderfrist an der serverseitigen Grantzeit; Ausführung revalidiert Katalog, Klassifikation und Kandidaten transaktional. Historische Receipts werden identitätsgeprüft ohne neue Wirkung gelesen. Dashboard-Health projiziert Not-Aus, Pending-Review, Digests, Grantzeit und letzte Wirkung passiv und payloadfrei. Aktivierung und Ausführung sind ausschließlich operatorgeführt; es gibt keinen Scheduler. Alle ausgelieferten Kategorien bleiben report_only und die globale Notabschaltung bleibt aktiv.
- **Fehler/fehlende Daten:** Unbekannte Config-/Schemaobjekte, unvollständige Klassifikation, nicht allowlist-fähiges enforce, zu junge Cutoffs, fehlende oder alte ungebundene Grantdaten, veraltete Review-/Planbindung, Kandidatendrift, Reconcile, Notabschaltung und suspendierte Kategorien blockieren fail-closed. Ein Löschfehler rollt Kandidaten und Receipt gemeinsam zurück und suspendiert die Kategorie; Restore setzt den Stop und suspendiert bestehende Vollzugsautorität. Ein identischer abgeschlossener Plan liefert auch nach Stop oder Policywechsel idempotent denselben integritätsgeprüften Receipt.
- **Prüfgegenstand:** Kategorie-Autorität bindet Kategorie-ID, Kategorie-Digest, Profil-/Rollendigest und bei enforce Plan-Digest, absoluten Grant-Cutoff und serverseitige Aktivierungszeit. Der Plan bindet die Schemaserie retention-execution-plan.v1, absoluten UTC-Cutoff, Anker, den klassifizierten Schutzvertrag und privacy-sichere score_key-Identitäten des aktuell ungeschützten Kandidatensatzes. Der Ausführungsbeleg bindet diese Werte zusätzlich an Authority-Epoch und Ausführungszeit; Restore entzieht der gebackupten Autorität die Wirksamkeit.
- **Evidence:** samuel retention dry-run|approve|activate|suspend|pause|unpause|execute --json, Schema-/Restore-Migrationstests, Canary-, Restart-, Repeat-, Plan-Drift- und Transaktionsabbruchtests, append-only Authority-/Execution-Records sowie State-/Health-/Dashboard-Sicht auf Stop, Pending-Review, Digests, Grantzeit und letzte Ausführung.
- **Vertrauen/Vollständigkeit:** Feldklassifikation ist konservative Betriebsmetadaten und keine automatische Anonymitäts- oder Rechtsbewertung. eu_operational ist ein Betriebsdefault; eu_ai_act_high_risk_support ist Opt-in und keine Konformitätszusage. Externe Backupkopien liegen außerhalb der technischen Zusage.
- **Fundstellen:** `samuel/core/ports.py#IRetentionStateStore`, `samuel/core/ports.py#IRetentionExecutionStore`, `samuel/core/retention.py#RetentionPolicyConfig`, `samuel/slices/privacy/retention.py#RetentionCoordinator`, `samuel/slices/evaluation/replay.py#ScoreReplay`, `config/privacy.json`, `docs/adr/0482-runtime-state-store.md`, `docs/adr/0422-local-dashboard-identity.md`
- **Issues:** #482, #667, #668, #673

### `OPS-CONFIGURATION-FREEZE` — Expliziter Operator-Konfigurationsmodus und Produktions-Freeze

- **Schutzziel:** Dashboard-Konfiguration nur in einem ausdrücklich gestarteten Operator-Setup-Prozess ändern und den normalen Produktionsdienst vor Datei- und In-Memory-Konfigurationswrites schützen.
- **Tatsächliches Verhalten:** Der Dashboardprozess löst beim Start genau einen typisierten Modus aus CLI, Environment oder dem sichtbaren Default production auf. Production blockiert Setup-, SCM-Label-, Risiko-/Attribution-, Featureflag-, globale und taskbezogene LLM- sowie Promptwrites vor Datei-, SCM- oder In-Memory-Wirkung. Setup verwendet die bestehenden Validatoren und Persistenzpfade; erfolgreiche Writes markieren Restartbedarf, laden FileConfig nicht heiß nach und setzen keine prozesslokalen Policy-Overrides. Setup-Status und Settings zeigen Quelle, Schreibbarkeit sowie gespeicherten und beim Prozessstart wirksamen secretfreien Config-Digest getrennt. Der dokumentierte einzelne Docker-`.env`-Datei-Bind-Mount verwendet nach einem `EBUSY` oder einer nicht schreibbaren Image-Elterndirectory ausschließlich im Setup-Prozess den gestagten, synchronisierten In-Place-Fallback.
- **Fehler/fehlende Daten:** Fehlender oder unbekannter Modus startet nicht mit Schreibauthority; production liefert configuration_frozen und HTTP 409. Normale Mehrdatei-I/O-Fehler werden im vorhandenen Setup-Pfad zurückgerollt. Der Datei-Bind-Mount-Fallback erhält Staging und Rollback für kontrollierte I/O-Fehler, behauptet aber keine Rename-Atomizität bei Prozess- oder Hostabbruch während des In-Place-Writes. Eine erkannte Teilpersistenz wird als configuration_partial_persistence mit Restartbedarf sichtbar; Prozess- oder Hostabsturz zwischen unabhängigen Dateiersetzungen wird nicht als atomar behauptet.
- **Prüfgegenstand:** Die Authority ist an den gestarteten Prozessmodus gebunden und entsteht weder aus API-Key, Login, Rolle noch Dateisystemfehler. Gespeicherter und beim Start wirksamer Stand werden durch getrennte Digests projiziert; Environment-Secrets sind davon ausgeschlossen.
- **Evidence:** Direkte Handler- und HTTP-Regressionsprüfungen für production/setup, Promptreset, Featureflag, Rename-, Datei-Bind-Mount-`EBUSY`-, nicht schreibbare Image-Elterndirectory-, In-Place-Fehler-/Rollback-, Setup-Persistenz, Restartprojektion, fehlenden Hot-Reload und Teilpersistenz. Reale Deploymentqualification mit schreibbarem Setup-Vorlauf, anschließend read-only Produktionsmount und Restart bleibt Abschlussbedingung von #691 und #823.
- **Vertrauen/Vollständigkeit:** Operator-Konfiguration und .env-Secrets bleiben externe Betreiberauthority. Sichtbare Digests umfassen nur JSON- und Promptdateien und enthalten keine Secretwerte oder .env-Digests. Die Begrenzung ist kein Benutzer-/Rollenmodell; #422 ergänzt Rechte, hebt den Produktions-Freeze aber nicht auf.
- **Fundstellen:** `samuel/core/configuration_mode.py#ConfigurationAuthority`, `samuel/slices/setup/handler.py#def configure_dashboard`, `samuel/slices/dashboard/handler.py#def configuration_mutation_blocked`, `samuel/server.py#create_server`, `docs/INSTALL.md#Dashboard-Rekonfiguration und Produktions-Freeze`
- **Issues:** #691, #823

### `SEC-LOCAL-DASHBOARD-IDENTITY` — Lokaler Dashboard-Identity-Provider mit explizitem Cutover

- **Schutzziel:** Lokale Menschen und Automation mit minimalen, expliziten Dashboard-Rechten authentisieren und jede Legacy-Migration fail-closed abschließen.
- **Tatsächliches Verhalten:** config/auth.json wählt genau legacy_api_key oder local_identity. Legacy startet ohne SAMUEL_API_KEY nicht. Local Identity verwendet Argon2, unabhängige kombinierbare Rollen, routegebundene Permissions, opaque instanzgebundene Sessions, absolute/Idle-Limits, CSRF, frische Reauthentisierung, selektiven/global bestätigten Widerruf und explizit berechtigte Automation-Token. Bootstrap, Cutover und Recovery sind schmale lokale CLI-Pfade.
- **Fehler/fehlende Daten:** Unbekannte oder unvollständige Auth-Konfiguration blockiert den Start. Local Identity fällt nie auf den Legacy-Key zurück. Falsche/zu häufige Logins, fehlende Permission, CSRF-Fehler, stale Reauthentisierung, letzter-Administrator-Verlust und unbestätigter Cutover blockieren. Restore widerruft Sessions/Token und setzt recovery_pending bis zum lokalen Recovery.
- **Prüfgegenstand:** Principals, Rollen, Credential-Version, Session-/Tokenhashes, Instanz-UUID und Widerrufe liegen im vorhandenen SQLite-State. Sichere Mutationen schreiten über dieselbe Authority-Epoch und denselben Witness fort. Der Browser erhält keine Rohsession im Storage; Automation erhält nur die explizite Token-Permissionmenge.
- **Evidence:** Argon2-, Rollen-, Session-Neustart/Idle-, CSRF-, Rate-Limit-, Restore-/Recovery-, Legacy-No-Fallback-, HTTP-Permission-, Automation-Token- und CLI-Cutovertests. Reale D0-Qualification mit HTTPS, Migration, Neustart, Widerruf und Restore bleibt vor Abschluss von #422 erforderlich.
- **Vertrauen/Vollständigkeit:** Benutzernamen und Actor-IDs sind personenbezogen; Hashes bleiben secret-bearing. Auditmetadaten enthalten Actor und sachlichen Grund, aber keine Passwörter, Rohsessions, CSRF-Werte oder Roh-Token. Der Provider ist eine lokale Referenzimplementierung und keine IAM-/OAuth-/PKI-/Pairing-Plattform.
- **Fundstellen:** `samuel/core/identity.py`, `samuel/adapters/auth/local.py#LocalIdentityService`, `samuel/adapters/api/auth.py#DashboardAuth`, `samuel/adapters/state/identity.py#SQLiteIdentityStateStore`, `samuel/server.py#create_server`, `config/auth.json`, `docs/adr/0422-local-dashboard-identity.md`
- **Issues:** #422

### `OPS-HEALTH-READINESS-SEPARATION` — Passive instanzgebundene Health-, Readiness- und Qualification-Projektion

- **Schutzziel:** Technische Gesundheit, zweckgebundene Betriebsbereitschaft und fachlich gebundene Qualification ohne neue Authority sichtbar trennen.
- **Tatsächliches Verhalten:** HealthCheckCommand bewahrt healthy, critical und checks und schreibt zusätzlich technische Gesundheit sowie Workflow-Readiness in run_projections. Doctor und audit verify schreiben eigene instanz- und zeitgebundene, digestierte Fachbefunde. Dashboard-Health und Viewerstatus lesen nur diese bereinigte Projektion; der aktive Self-Check bleibt permission-gebunden.
- **Fehler/fehlende Daten:** Fehlende Evidence ist not_checked, fremde Restore-Instanz oder ein Alter über 3600 Sekunden ist stale. Fehlender Auditkey oder fehlende/rotierte Logs überschreiben keinen früheren Integritätsfehler. Nur ein erfolgreicher aktueller Fach-Recheck löst ihn unter Bindung des vorherigen Digests auf. Projectionfehler bleiben sichtbar und nicht blockierend.
- **Prüfgegenstand:** Jeder Datensatz bindet Projektionsart, Ergebnis, State-Instanz, UTC-Prüfzeit, begrenzte Zusammenfassung und Evidence-Digest. Die Projektion erteilt keine Gate-, Workflow-, Resume-, Merge- oder Releaseauthority.
- **Evidence:** Restart-/Restore-/TTL-/Missing-Data-/Resolutiontests, Audit- und Doctor-CLI-Tests, aktive Health-Handler-Tests sowie HTTP-Tests ohne passiven SCM-Zugriff. Reale Betriebs-, Restore-, Integritäts- und Permission-Qualification auf D0 bleibt vor Abschluss von #693 erforderlich.
- **Vertrauen/Vollständigkeit:** Gespeichert werden feste Checknamen und begrenzte Zähler, keine Credentials, Providerantworten oder Auditpayloads. Viewer sehen nur Statussummen. Aktive Providerprobes benötigen RUN_PROVIDER_PROBES.
- **Fundstellen:** `samuel/core/health_projection.py`, `samuel/slices/health/handler.py#HealthHandler`, `samuel/slices/dashboard/handler.py#DashboardHandler`, `samuel/cli.py#_cmd_doctor`, `samuel/cli.py#_cmd_audit`, `docs/adr/0693-health-readiness-qualification.md`
- **Issues:** #693

### `OPS-GITEA-PUBLISHER-BOUNDARY` — Dedizierter persönlicher Gitea-Publisher mit create-only Postcondition

- **Schutzziel:** Einen OCI-Release mit einer vom Runtime-SCM getrennten, providerbelegten Publishercredential des persönlichen Package-Owners create-only veröffentlichen.
- **Tatsächliches Verhalten:** Der Preflight liest ausschließlich SAMUEL_OCI_PUBLISHER_TOKEN, weist über Giteas aktuelle Tokenmetadaten Identität und write:package ohne weitere Write-Scopes nach, prüft persönlichen Owner-Read und Tagabwesenheit und meldet dieselbe Credential temporär am Docker-Client an. Publish bindet Releasehost und Image, führt keinen Probepush oder Credentialfallback aus und verifiziert nach dem einmaligen Push das Digest. Der explizite Recoverypfad fordert nur einen bereits vorhandenen Tag ab, prüft genau einen Digest, Identität, Runtime und frischen Smoke und materialisiert erst dann das Manifest; er enthält keine Publishmutation.
- **Fehler/fehlende Daten:** Fehlende, mit SCM_TOKEN identische, breiter beschreibbare oder nicht dem persönlichen Owner zugehörige Credentials blockieren. Unbelegtes Read oder Tagabwesenheit blockiert. Ein fehlgeschlagener Push wird genau einmal read-only nachgeprüft; ein vorhandener oder weiterhin unklarer Tag wird weder gelöscht, überschrieben noch automatisch erneut gepusht. Recovery blockiert bei fehlendem, mehrdeutigem, bereits gebundenem oder identitätsabweichendem Zustand ohne Mutation.
- **Prüfgegenstand:** Bindet Provideridentität, accountweiten Package-Scope, persönlichen Owner, kontrollierte Releasehost-ID, konkretes Image-Repository und exakten create-only Tag. Der Provider-Scope ist ausdrücklich keine technische Einzelimage-Isolation.
- **Evidence:** Strukturierte Preflight-Ausgabe mit getrennten Identity-, Credential-Separation-, Scope-, Owner-Read-, Writequalification- und Tagabsenzbefunden sowie Publish-Postcondition. Reale Credential-/Host-/Publishqualification bleibt für #759 offen.
- **Vertrauen/Vollständigkeit:** Der persönliche Owneraccount bleibt gemeinsame Trustwurzel. Die Credential erreicht weder Produkt-.env noch CLI-Argument, JSON-Ausgabe, Buildkontext oder Runtimehost; eine temporäre Docker-Config wird nach dem Lauf verworfen.
- **Fundstellen:** `tools/container_release.py#publisher_preflight`, `tools/container_release.py#publish`, `tools/container_release.py#recover`, `docs/CONTAINER_RELEASE_OPERATIONS.md#Kandidat bauen und veröffentlichen`, `docs/VERSIONING.md#Lieferumfang und Containervertrag`
- **Issues:** #759

### `ADVISORY-MODEL-COST-PARETO` — Taskbezogene Überqualifiziert-Klassifikation und optionaler Pareto-Kostenhinweis

- **Schutzziel:** Eine belegbar über der expliziten Taskschwelle liegende Modellwahl informativ kennzeichnen und nur bei workloadneutral eindeutig niedrigeren vergleichbaren Preisen eine geeignete Alternative nennen.
- **Tatsächliches Verhalten:** Jeder Task konfiguriert cost_advisory_enabled und overqualification_margin_ratio im bestehenden Dashboard-Taskblock; ausgeliefert sind true und 0,20. get_model_suitability verwendet ausschließlich Taskindex, Schwelle und relative Marge. Ein Hinweis entsteht nur aus derselben frischen Cache-/Benchmarkgeneration, gleicher Schwelle, geeigneter Alternative, positiven Prompt-/Completionpreisen ohne Zusatzkomponenten und strikter Pareto-Dominanz. Mehrere Kandidaten werden reproduzierbar nach kanonischer Modell-ID präsentiert.
- **Fehler/fehlende Daten:** no_data, below_threshold, deaktivierter Hinweis, alte oder inkompatible Cachegeneration, abweichende Benchmarkquelle, Null-/fehlende Preise, zusätzliche Preiskomponenten und kreuzende Preisachsen liefern keinen Alternativvorschlag. Auswahl und Routing bleiben unverändert.
- **Prüfgegenstand:** Bindet Task, taskbezogenen Benchmarkindex, explizite Schwelle, relative Marge, Cachegeneration, Benchmarkquelle, ausgewähltes Modell sowie beide Preispaare. Die Modell-ID-Sortierung ist nur Präsentations-Tie-Break und keine Preisaggregation.
- **Evidence:** Unit-/API-/Dashboard-/Configtests für geeignet, unterqualifiziert, überqualifiziert, no_data, Pareto, Kreuzpreise, Zusatzkosten, Schema-/Freshnessdrift, Disable und Konfigurationsvalidierung. Reale aktuelle OpenRouter-Preis-/Benchmarkqualification bleibt für #454 offen.
- **Vertrauen/Vollständigkeit:** Der Hinweis besitzt keine Routing-, Budget-, Gate- oder Freigabeauthority und speichert keinen neuen State. OpenRouter-Cachewerte bleiben externe zeitgebundene Metadaten; alte Daten werden nicht als Empfehlung verwendet.
- **Fundstellen:** `samuel/adapters/llm/costs.py#get_model_suitability`, `samuel/adapters/llm/costs.py#get_model_cost_advisory`, `samuel/server.py#/api/v1/dashboard/llm/models`, `config/llm/defaults.json::tasks`, `docs/README_technical.md`
- **Issues:** #454, #428, #549, #575

### `INPUT-BOUND-CLARIFICATION` — Revisionsgebundener Planning-Klärungsdialog

- **Schutzziel:** Ausdrücklich offene oder widersprüchliche Issue-Anforderungen vor dem Planner begrenzt klären, ohne eine zweite Freigabeauthority einzuführen.
- **Tatsächliches Verhalten:** Ein deterministischer Readiness-Check erkennt nur leere/ungültige Quellen, explizite offene Marker und beweisbare GREP/GREP:NOT-Widersprüche. Bei Klärungsbedarf persistiert SQLite-Schema v10 höchstens zwei Serienrunden mit je drei Fragen, expliziter endlicher Operatorfrist, Source-Snapshot- und #549-Budgetbindung. Antwort-ID, Body-Digest, Akteur und Kommentarrevision werden vor Planning, Approval und Implementation erneut gelesen. Die sichtbare Basis wird Acceptance Contract v3. Automatische Profile wechseln nur für diesen Contract auf die bestehende menschliche Planapproval; klare Issues behalten PlanValidated -> Implement.
- **Fehler/fehlende Daten:** Fehlende Frist, Timeout, zwei erfolglose Runden, doppelte/späte/editierte Antwort, fehlender Kommentar oder Source-Drift erzeugen PlanBlocked/WorkflowAborted ohne partiellen Contract. Nach terminalem Zustand oder Supersession autorisiert nur ein explizites samuel run eine neue Serie; Watch setzt nicht selbst fort.
- **Prüfgegenstand:** Repository, Issue, PlanningSourceSnapshot-Digest, Workflow-Budgetzulassung, Serien-/Rundennummer, Frage- und Antwortkommentarrevision sowie der daraus erzeugte exakte Plan-Contract.
- **Evidence:** ClarificationRequested/Waiting/Accepted/Superseded, payloadfreie State-Zähler, sichtbare Klärungsbasis im Plan und bestehender menschlicher AcceptanceApproval-Receipt.
- **Vertrauen/Vollständigkeit:** Antworten sind Inputs, keine Authority. Frage-/Antworttext und Akteur können PII enthalten und liegen im autoritativen State sowie SCM-Plan; Audit und Dashboard projizieren nur IDs, Digests, Status und Zähler.
- **Fundstellen:** `samuel/core/acceptance.py#assess_issue_readiness`, `samuel/slices/planning/clarification.py#class ClarificationCoordinator`, `samuel/adapters/state/sqlite.py#class SQLiteAuthorityStateStore`, `samuel/core/workflow.py#plan_approval_required`
- **Issues:** #575

### `EXT-PUBLIC-DATA-CONTRACT` — Versionierter öffentlicher Extension-Datenvertrag

- **Schutzziel:** Den ersten externen Documentation-Consumer über eine schmale gebundene Datengrenze anbinden, ohne fremden Code oder implizite Authority in den Core zu laden.
- **Tatsächliches Verhalten:** samuel.extensions validiert geschlossene Capability-, Request-, Result-, Documentation-Policy- und Claim-JSONs für documentation.static_claims 1.0 / documentation.inventory.v1. Der unabhängige Consumer inventarisiert die exakt policygebundenen Markdown-Git-Blobs. Der Produktverifier prüft Repository, exakten Head, Policy, Consumer-Tool, vollständige Coverage, Artefakte und Sensitive-Data-Signale erneut. samuel-documentation übergibt danach nur eine nicht autoritative Metadatenprojektion an denselben Git-Marker-, Non-force-, No-op- und Receiptpfad wie der interne Wiki-Pilot. config/extensions.json bleibt optional, deaktiviert und D08-geschützt.
- **Fehler/fehlende Daten:** Duplicate Keys, unbekannte Felder, Typumwandlung, Symlinks, Traversal, übergroße Dateien, inkompatible Versionen, Subject-/Policy-/Tool-/Coverage-/Artefaktdrift sowie Secret- oder Sensitive-Data-Signale werden vor Publikation abgewiesen. Remote-Drift, falscher Marker oder Contentdigest und konkurrierender Fortschritt blockieren ohne Force-Push. Optional absent bleibt ohne Corewirkung; Required absent, disabled oder incompatible blockiert die betroffene Extensionaktion fail-closed.
- **Prüfgegenstand:** Capability-ID und Contractversion, kanonisches Repository owner/name, vollständiger Git-Head, Claimfamilie, Policy- und Consumer-Tooldigest, exakte sortierte Markdown-Coverage, Request-ID/-Digest sowie Pfad, Byteanzahl, Medientyp und SHA-256 jedes Contract- und Dokumentartefakts.
- **Evidence:** Paketierte JSON Schemas, samuel-extension und samuel-documentation, D08-geschützter Dashboard-/REST-Pfad; unabhängiger credentialfreier Apache-2.0-Consumer558beeaef. Eigene reale öffentliche D20-Policymatrix und D21-Gitea-Wiki-Publish/No-op/Receipt-Reconcile/Drift-/Marker-/Credentialnegativmatrix am veröffentlichten v2.0.0a25-OCI-Digestdc5b3272 PASS05.10.2026, #636/#639. Datierte enge advisory Qualification; kein Golden-/D0-/Sandboxclaim.
- **Vertrauen/Vollständigkeit:** Consumerartefakte enthalten keine Credentials und verleihen keine Gate-, Approval-, Merge- oder Publishauthority. Der Producer erhält keine Publishercredentials. Nur Metadaten und commitgebundene Quelllinks werden projiziert; freie Prosa erhält keine Wahrheitszusage. Es entsteht kein neuer Runtime- oder Publisherstore; out-of-process ist kein Sandbox- oder Trustnachweis.
- **Fundstellen:** `samuel/extensions/contract.py#validate_result_binding`, `samuel/extensions/documentation.py#class DocumentationClaims`, `samuel/documentation_capability.py#verify_documentation_exchange`, `samuel/documentation_capability.py#build_documentation_projection`, `samuel/adapters/git_publication.py#publish_projection`, `samuel/documentation_cli.py#main`, `samuel/slices/dashboard/handler.py#set_extension_configuration`, `config/extensions.json`, `docs/EXTENSION_CONTRACT.md`
- **Issues:** #636, #639

## Betriebsgrenze

Der auf diesem Repository nachgewiesene native Gitea-Mergepfad ist externe,
veränderliche Betriebskonfiguration und deshalb kein portabler Code-Nachweis.
Andere Installationen müssen dieselbe Regel konfigurieren und mit `samuel doctor`
vor einer Freigabe sowie nach SCM-/Berechtigungsänderungen erneut nachweisen.
