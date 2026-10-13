# Dokumentation: Funktionswege und vollständiger Bestand

Diese Liste umfasst alle projektspezifischen Markdown-Dokumente einschließlich
Projektroot, Agentenanweisungen, Promptbibliothek und historischem Archiv.
Die Einordnung trennt aktuelle Referenzen, Entwicklungsanweisungen und
historische Nachweise. Eine Bestandsliste beweist allein keine vollständige
semantische Funktionsabdeckung oder reale Qualification. Wiki-Veröffentlichung
und Remote-Readback bleiben an den jeweiligen integrierten Main gebunden.
Der [historische Dokumentabgleich](archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#dokumentation-integriert--abgleich-nach-1002-10102026)
erhält die früheren Commit-/Integrationsnachweise.

## Drei Ebenen für unterschiedliche Fragen

| Frage | Einstieg | Aufgabe |
|---|---|---|
| Welches Produkt ist das und wem hilft es? | [Root-README](../README.md), [Manifest](../MANIFESTO.md) | Problem, Mehrwert, Stakeholder und belegte Grenzen verstehen; Manifest als Produktthese lesen. |
| Wie greifen seine Teile ineinander? | [Technischer Überblick](TECHNICAL_OVERVIEW.md) | Core, Referenz-Worker, externe Anschlüsse, Verantwortung und operativen Ablauf begreifen. |
| Wie funktioniert eine konkrete Oberfläche? | [Advanced-Referenz](README_technical.md) und folgende Fachwege | Parameter, Quellen, Wirkung, Rechte, Fehler, Recovery und Nachweise nachvollziehen. |

[Entwicklungsproblem, Nutzen und offene Nachweise](PRODUCT_VALUE_AND_EVIDENCE.md)
prüft konkrete Anwendungsfälle, Alternativen, Aufwand und Forschungsgrenzen.

### Wege nach Aufgabe

- **Engineering:** Überblick → [Referenzpipeline](../technische%20Beschreibungen/README.md)
  → [CLI/API und Komponenten](README_technical.md) → [Beitragsworkflow](../CONTRIBUTING.md).
- **DevOps, Plattform und Infrastruktur:** [INSTALL](INSTALL.md) →
  [Dashboard/Settings](DASHBOARD.md) → [State/Recovery](STATE_STORE.md) →
  [Containerbetrieb](CONTAINER_RELEASE_OPERATIONS.md).
- **Security und DevSecOps:** [Securitygrenzen](../SECURITY.md) →
  [Capabilitywirkung](CAPABILITY_MATRIX.md) → [technische Quellen](README_technical.md#13-security-model).
- **Compliance, Audit und Risiko:** [Capability-/Evidenzgrenzen](CAPABILITY_MATRIX.md)
  → [Framework-Mappings](COMPLIANCE_FRAMEWORK_MAPPINGS.md) →
  [Auditnachweise](audits/INDEX.md). Zuordnungen sind keine Konformitätsabnahme.
- **Engineering-Leitung und technische Produktverantwortliche:** Root-README →
  [Produktstatus](status/CURRENT_PRODUCT_STATUS.md) → [Entscheidungen](adr/README.md).
- **Unternehmen mit besonderen Nachweisanforderungen:** Überblick →
  [Test-/Qualification-Runbook](runbooks/TEST_AND_QUALIFICATION_RUNBOOK.md) →
  [Releasebindung](VERSIONING.md) und installationsbezogene Evidence.

### Begriffe und Geltung

Acceptance Contract, Subject, Evidence, Policy und Authority erklärt der
[Überblick](TECHNICAL_OVERVIEW.md#was-gebunden-bedeutet). Die
[Capability-Matrix](CAPABILITY_MATRIX.md#statusmodell) erklärt ihre
Wirksamkeitsbegriffe. Code und ausgelieferte Konfiguration bestimmen das
Verhalten; Regeln und angenommene ADRs behalten ihren bestehenden
Geltungsbereich. Leserreihenfolge, Wiki und ein erfolgreicher Linkcheck
verleihen keiner Quelle zusätzliche Authority.

Der nachfolgende Vollbestand bleibt erhalten: aktuelle Beschreibungen,
Entwicklungsanweisungen, Product-LLM-Eingaben, historische Nachweise und
zusätzliche Dokumentquellen/Bilder. Neue dokumentationsrelevante Änderungen
folgen der [Documentation acceptance](../CONTRIBUTING.md#documentation-acceptance)
im selben PR; eine neue Leserstruktur ersetzt keine fachliche Quellenprüfung.

## Funktionen finden

[Technischer Überblick: Gesamtarchitektur verstehen](TECHNICAL_OVERVIEW.md)
verbindet den Produkteinstieg mit den folgenden Advanced-Funktionswegen.

| Thema | Beschreibung und bestehender Vertrag |
|---|---|
| Installation, Setup, Upgradegrenzen | [Installation](INSTALL.md), [Containerbetrieb](CONTAINER_RELEASE_OPERATIONS.md) |
| Dashboard: alle Ansichten, Settings, Felder und Wirkungen | [Dashboard](DASHBOARD.md) |
| SQLite: Runtime-State und Workspace-Registry, Tabellen/Spalten/Constraints und getrennte Backupgrenzen | [State Store](STATE_STORE.md) |
| CLI, HTTP-API, Rechte, Core/Slices/Adapter und Repositorytools | [Technische Referenz](README_technical.md) |
| Provider, Routing, Modelle, Prompts, Konfiguration | [Technische Referenz](README_technical.md), [Agentenkonfiguration](agents/AGENT_CONFIGURATION_REFERENCE.md), [Prompts](agents/AGENT_PROMPTS_AND_INSTRUCTIONS.md) |
| Issue → Planning → Implementation → PR/Gates → Evaluation | [Pipelineübersicht](../technische%20Beschreibungen/README.md) |
| Doctor, Health, Readiness, Qualification und Tests | [Test-/Qualification-Runbook](runbooks/TEST_AND_QUALIFICATION_RUNBOOK.md), [Technische Referenz](README_technical.md) |
| Audit, Identity, Security, State, Retention | [Security](../SECURITY.md), [State Store](STATE_STORE.md), [Technische Referenz](README_technical.md) |
| Releases, CI-Runner, Wiki und öffentliche Synchronisation | [Versionierung](VERSIONING.md), [CI-Runner](CI_RUNNER_OPERATIONS.md), [GitHub-Abgleich](github/GITHUB_SYNC_READINESS.md) |
| Capability-/Issue-/Statusgrenzen und offene Entscheidungen | [Produktstatus](status/CURRENT_PRODUCT_STATUS.md), [Issue-Matrix](status/ISSUE_IMPLEMENTATION_MATRIX.md), [ADRs](adr/README.md) |
| Engineering-/Operatorauthority | [Operating Rules](OPERATING_RULES.md), [Engineering Workflow](governance/CURRENT_ENGINEERING_WORKFLOW.md) |

## Alle Dokumentdateien

`history` und `HISTORICAL / AUDIT_EVIDENCE` sind historische Quellen, keine
aktuelle Runtime-Authority. `target_architecture` beschreibt Ziele, keine
Existenzgarantie; angenommene ADRs bleiben verbindlich. Promptbibliotheksdateien
sind Laufzeiteingaben und keine Bedienungsanleitung.

| Datei | Einordnung |
|---|---|
| [.claude/CLAUDE.md](../.claude/CLAUDE.md) | operations |
| [CHANGELOG.md](../CHANGELOG.md) | history |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | operations |
| [MANIFESTO.md](../MANIFESTO.md) | target_architecture |
| [PUBLIC_SNAPSHOT.md](../PUBLIC_SNAPSHOT.md) | Public-Projektion / Provenienz, keine operative Authority |
| [README.md](../README.md) | runtime_reference |
| [SECURITY.md](../SECURITY.md) | operations |
| [docs/AI_ACT_COMPLIANCE.md](AI_ACT_COMPLIANCE.md) | operations |
| [docs/AI_ACT_TECHNICAL_DOC.md](AI_ACT_TECHNICAL_DOC.md) | runtime_reference |
| [docs/CAPABILITY_MATRIX.md](CAPABILITY_MATRIX.md) | runtime_reference |
| [docs/CI_RUNNER_OPERATIONS.md](CI_RUNNER_OPERATIONS.md) | operations |
| [docs/COMPLIANCE_FRAMEWORK_MAPPINGS.md](COMPLIANCE_FRAMEWORK_MAPPINGS.md) | operations |
| [docs/CONTAINER_RELEASE_OPERATIONS.md](CONTAINER_RELEASE_OPERATIONS.md) | operations |
| [docs/DASHBOARD.md](DASHBOARD.md) | runtime_reference |
| [docs/DSGVO_VVT.md](DSGVO_VVT.md) | operations |
| [docs/EXTENSION_CONTRACT.md](EXTENSION_CONTRACT.md) | runtime_reference |
| [docs/GATE_COMPLIANCE_MATRIX.md](GATE_COMPLIANCE_MATRIX.md) | runtime_reference |
| [docs/INSTALL.md](INSTALL.md) | operations |
| [docs/OPERATING_RULES.md](OPERATING_RULES.md) | operations |
| [docs/PRODUCT_BOUNDARY_HANDOVER_PROMPT.md](PRODUCT_BOUNDARY_HANDOVER_PROMPT.md) | operations |
| [docs/PRODUCT_VALUE_AND_EVIDENCE.md](PRODUCT_VALUE_AND_EVIDENCE.md) | runtime_reference |
| [docs/PROMPT_CONTRACT_AUDIT.md](PROMPT_CONTRACT_AUDIT.md) | history |
| [docs/README.md](README.md) | runtime_reference |
| [docs/README_technical.md](README_technical.md) | runtime_reference |
| [docs/RUNTIME_REFERENCE.md](RUNTIME_REFERENCE.md) | runtime_reference |
| [docs/SAMUEL_ARCHITECTURE_V2.1.md](SAMUEL_ARCHITECTURE_V2.1.md) | target_architecture |
| [docs/SAMUEL_DESIGN_DECISIONS.md](SAMUEL_DESIGN_DECISIONS.md) | adr |
| [docs/STATE_STORE.md](STATE_STORE.md) | runtime_reference |
| [docs/TECHNICAL_OVERVIEW.md](TECHNICAL_OVERVIEW.md) | runtime_reference |
| [docs/VERSIONING.md](VERSIONING.md) | operations |
| [docs/adr/0399-score-authority.md](adr/0399-score-authority.md) | adr |
| [docs/adr/0422-local-dashboard-identity.md](adr/0422-local-dashboard-identity.md) | adr |
| [docs/adr/0482-runtime-state-store.md](adr/0482-runtime-state-store.md) | adr |
| [docs/adr/0583-installed-cli-entrypoint.md](adr/0583-installed-cli-entrypoint.md) | adr |
| [docs/adr/0618-worktree-manager.md](adr/0618-worktree-manager.md) | adr |
| [docs/adr/0619-candidate-sandbox.md](adr/0619-candidate-sandbox.md) | adr |
| [docs/adr/0620-preflight-gate-state.md](adr/0620-preflight-gate-state.md) | adr |
| [docs/adr/0635-wiki-pilot.md](adr/0635-wiki-pilot.md) | adr |
| [docs/adr/0643-repository-wiki-materialization.md](adr/0643-repository-wiki-materialization.md) | adr |
| [docs/adr/0649-wiki-content-projection.md](adr/0649-wiki-content-projection.md) | adr |
| [docs/adr/0678-product-boundary-and-integration-profile.md](adr/0678-product-boundary-and-integration-profile.md) | adr |
| [docs/adr/0693-health-readiness-qualification.md](adr/0693-health-readiness-qualification.md) | adr |
| [docs/adr/0706-atomic-release-layout.md](adr/0706-atomic-release-layout.md) | adr |
| [docs/adr/README.md](adr/README.md) | adr |
| [docs/agents/AGENT_CONFIGURATION_REFERENCE.md](agents/AGENT_CONFIGURATION_REFERENCE.md) | runtime_reference |
| [docs/agents/AGENT_PROMPTS_AND_INSTRUCTIONS.md](agents/AGENT_PROMPTS_AND_INSTRUCTIONS.md) | runtime_reference |
| [docs/archive/2026-10-09/ACTIVE_DOCUMENT_RECONCILIATION.md](archive/2026-10-09/ACTIVE_DOCUMENT_RECONCILIATION.md) | HISTORICAL / AUDIT_EVIDENCE |
| [docs/archive/2026-10-09/CLOSED_ISSUE_CLASSIFICATION.md](archive/2026-10-09/CLOSED_ISSUE_CLASSIFICATION.md) | HISTORICAL / AUDIT_EVIDENCE |
| [docs/archive/2026-10-09/REHEARSAL_REPOSITORY_CLEANUP.md](archive/2026-10-09/REHEARSAL_REPOSITORY_CLEANUP.md) | HISTORICAL / AUDIT_EVIDENCE |
| [docs/archive/2026-10-09/WORKING_DECISIONS_TO_ISSUES.md](archive/2026-10-09/WORKING_DECISIONS_TO_ISSUES.md) | HISTORICAL / AUDIT_EVIDENCE |
| [docs/archive/A15_REFERENCE_EVIDENCE_2026-09-21.md](archive/A15_REFERENCE_EVIDENCE_2026-09-21.md) | HISTORICAL / AUDIT_EVIDENCE |
| [docs/archive/HANDOVER_2026-05-05.md](archive/HANDOVER_2026-05-05.md) | HISTORICAL / AUDIT_EVIDENCE |
| [docs/archive/HANDOVER_2026-05-06.md](archive/HANDOVER_2026-05-06.md) | HISTORICAL / AUDIT_EVIDENCE |
| [docs/archive/HANDOVER_2026-05-29.md](archive/HANDOVER_2026-05-29.md) | HISTORICAL / AUDIT_EVIDENCE |
| [docs/archive/PHASE_1_HARDENING_CHARTER.md](archive/PHASE_1_HARDENING_CHARTER.md) | HISTORICAL / AUDIT_EVIDENCE |
| [docs/archive/reader-history-2026-10-12/EDITORIAL_CONTEXT.md](archive/reader-history-2026-10-12/EDITORIAL_CONTEXT.md) | HISTORICAL / AUDIT_EVIDENCE |
| [docs/archive/CURRENT_PRODUCT_STATUS_2026-10-11.md](archive/CURRENT_PRODUCT_STATUS_2026-10-11.md) | HISTORICAL / AUDIT_EVIDENCE |
| [docs/archive/reader-history-2026-10-11/INSTALL.md](archive/reader-history-2026-10-11/INSTALL.md) | HISTORICAL / AUDIT_EVIDENCE |
| [docs/archive/reader-history-2026-10-11/VERSIONING.md](archive/reader-history-2026-10-11/VERSIONING.md) | HISTORICAL / AUDIT_EVIDENCE |
| [docs/archive/reader-history-2026-10-11/CONTAINER_RELEASE_OPERATIONS.md](archive/reader-history-2026-10-11/CONTAINER_RELEASE_OPERATIONS.md) | HISTORICAL / AUDIT_EVIDENCE |
| [docs/archive/reader-history-2026-10-11/TEST_AND_QUALIFICATION_RUNBOOK.md](archive/reader-history-2026-10-11/TEST_AND_QUALIFICATION_RUNBOOK.md) | HISTORICAL / AUDIT_EVIDENCE |
| [docs/archive/reader-history-2026-10-11/ISSUE_IMPLEMENTATION_MATRIX.md](archive/reader-history-2026-10-11/ISSUE_IMPLEMENTATION_MATRIX.md) | HISTORICAL / AUDIT_EVIDENCE |
| [docs/archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md](archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md) | HISTORICAL / AUDIT_EVIDENCE |
| [docs/archive/reader-history-2026-10-11/SAMUEL_ARCHITECTURE_V2.1.md](archive/reader-history-2026-10-11/SAMUEL_ARCHITECTURE_V2.1.md) | HISTORICAL / AUDIT_EVIDENCE |
| [docs/archive/README.md](archive/README.md) | HISTORICAL / AUDIT_EVIDENCE |
| [docs/archive/SAMUEL_V2_UMSETZUNGSPLAN.md](archive/SAMUEL_V2_UMSETZUNGSPLAN.md) | HISTORICAL / AUDIT_EVIDENCE |
| [docs/archive/SELF_MODE_PROMPT_QUALITY_MEMO.md](archive/SELF_MODE_PROMPT_QUALITY_MEMO.md) | HISTORICAL / AUDIT_EVIDENCE |
| [docs/archive/V2.1_GAP_ANALYSE_THEMATISCH.md](archive/V2.1_GAP_ANALYSE_THEMATISCH.md) | HISTORICAL / AUDIT_EVIDENCE |
| [docs/archive/V2_GAP_ANALYSE_KOMPLETT.md](archive/V2_GAP_ANALYSE_KOMPLETT.md) | HISTORICAL / AUDIT_EVIDENCE |
| [docs/archive/housekeeping/2026-09-26/HOUSEKEEPING_ACTION_MATRIX.md](archive/housekeeping/2026-09-26/HOUSEKEEPING_ACTION_MATRIX.md) | HISTORICAL / AUDIT_EVIDENCE |
| [docs/archive/housekeeping/2026-09-26/HOUSEKEEPING_EXECUTIVE_SUMMARY.md](archive/housekeeping/2026-09-26/HOUSEKEEPING_EXECUTIVE_SUMMARY.md) | HISTORICAL / AUDIT_EVIDENCE |
| [docs/archive/housekeeping/2026-09-26/HOUSEKEEPING_RECONCILIATION_REPORT.md](archive/housekeeping/2026-09-26/HOUSEKEEPING_RECONCILIATION_REPORT.md) | HISTORICAL / AUDIT_EVIDENCE |
| [docs/archive/phases/PHASE_0b.md](archive/phases/PHASE_0b.md) | HISTORICAL / AUDIT_EVIDENCE |
| [docs/audits/INDEX.md](audits/INDEX.md) | history |
| [docs/audits/completed/BACKLOG_STORY_MATERIALIZATION.md](audits/completed/BACKLOG_STORY_MATERIALIZATION.md) | history |
| [docs/audits/completed/EXTERNAL_CHALLENGE_RECONCILIATION.md](audits/completed/EXTERNAL_CHALLENGE_RECONCILIATION.md) | history |
| [docs/audits/completed/ISSUE_COMMENT_RECONCILIATION.md](audits/completed/ISSUE_COMMENT_RECONCILIATION.md) | history |
| [docs/audits/completed/P4_CHALLENGE_RECONCILIATION.md](audits/completed/P4_CHALLENGE_RECONCILIATION.md) | history |
| [docs/audits/completed/SAMUEL_AUDIT_ERRATA_2026-09-27.json.md](audits/completed/SAMUEL_AUDIT_ERRATA_2026-09-27.json.md) | history |
| [docs/audits/completed/SAMUEL_AUDIT_INTEGRITY_RECONCILIATION_2026-09-27.md](audits/completed/SAMUEL_AUDIT_INTEGRITY_RECONCILIATION_2026-09-27.md) | history |
| [docs/audits/completed/SAMUEL_AUDIT_SOURCE_INDEX_2026-09-26.json.md](audits/completed/SAMUEL_AUDIT_SOURCE_INDEX_2026-09-26.json.md) | history |
| [docs/audits/completed/SAMUEL_TARGETED_FALSIFICATION_CHALLENGE_2026-09-28.md](audits/completed/SAMUEL_TARGETED_FALSIFICATION_CHALLENGE_2026-09-28.md) | history |
| [docs/audits/completed/SAMUEL_TARGETED_FALSIFICATION_RESULTS_2026-09-28.json.md](audits/completed/SAMUEL_TARGETED_FALSIFICATION_RESULTS_2026-09-28.json.md) | history |
| [docs/audits/historical/BACKLOG_AUDIT_INDEX.md](audits/historical/BACKLOG_AUDIT_INDEX.md) | history |
| [docs/audits/historical/BACKLOG_CHALLENGE_BUNDLE.md](audits/historical/BACKLOG_CHALLENGE_BUNDLE.md) | history |
| [docs/audits/historical/P1_CHALLENGE_PACKAGE.md](audits/historical/P1_CHALLENGE_PACKAGE.md) | history |
| [docs/audits/historical/P2_AUDIT_PACKAGE.md](audits/historical/P2_AUDIT_PACKAGE.md) | history |
| [docs/audits/historical/P2_CHALLENGE_PACKAGE.md](audits/historical/P2_CHALLENGE_PACKAGE.md) | history |
| [docs/audits/historical/P3_CHALLENGE_PACKAGE.md](audits/historical/P3_CHALLENGE_PACKAGE.md) | history |
| [docs/audits/historical/P4_CHALLENGE_PACKAGE.md](audits/historical/P4_CHALLENGE_PACKAGE.md) | history |
| [docs/audits/historical/P5_CHALLENGE_PACKAGE.md](audits/historical/P5_CHALLENGE_PACKAGE.md) | history |
| [docs/audits/historical/P6_CHALLENGE_PACKAGE.md](audits/historical/P6_CHALLENGE_PACKAGE.md) | history |
| [docs/audits/historical/P7_CHALLENGE_PACKAGE.md](audits/historical/P7_CHALLENGE_PACKAGE.md) | history |
| [docs/audits/historical/P8_CHALLENGE_PACKAGE.md](audits/historical/P8_CHALLENGE_PACKAGE.md) | history |
| [docs/audits/historical/RELEASE_LINEAGE_DRIFT_AUDIT.md](audits/historical/RELEASE_LINEAGE_DRIFT_AUDIT.md) | history |
| [docs/audits/historical/checkpoint.json.md](audits/historical/checkpoint.json.md) | history |
| [docs/audits/historical/verification-ledger.jsonl.md](audits/historical/verification-ledger.jsonl.md) | history |
| [docs/audits/partial/D0_BOOTSTRAP_CONTRACT_AUDIT.md](audits/partial/D0_BOOTSTRAP_CONTRACT_AUDIT.md) | history |
| [docs/audits/partial/EXECUTION_CONFORMANCE_AUDIT.md](audits/partial/EXECUTION_CONFORMANCE_AUDIT.md) | history |
| [docs/audits/partial/OPERATIONAL_CONTRACTS.md](audits/partial/OPERATIONAL_CONTRACTS.md) | history |
| [docs/audits/partial/POST_AUDIT_CONSOLIDATION.md](audits/partial/POST_AUDIT_CONSOLIDATION.md) | history |
| [docs/audits/partial/REMEDIATION_MATRIX.md](audits/partial/REMEDIATION_MATRIX.md) | history |
| [docs/audits/partial/SAMUEL_FULL_AUTHORITY_HISTORY_DRIFT_AUDIT_2026-09-26.md](audits/partial/SAMUEL_FULL_AUTHORITY_HISTORY_DRIFT_AUDIT_2026-09-26.md) | history |
| [docs/audits/partial/SAMUEL_GOLDEN_PREPARATION_ISSUE_LEDGER.json.md](audits/partial/SAMUEL_GOLDEN_PREPARATION_ISSUE_LEDGER.json.md) | history |
| [docs/audits/partial/SAMUEL_GOLDEN_PREPARATION_RECONCILIATION.md](audits/partial/SAMUEL_GOLDEN_PREPARATION_RECONCILIATION.md) | history |
| [docs/audits/partial/SAMUEL_WORKING_DECISIONS_v8.md](audits/partial/SAMUEL_WORKING_DECISIONS_v8.md) | history |
| [docs/github/GITHUB_SYNC_READINESS.md](github/GITHUB_SYNC_READINESS.md) | operations |
| [docs/governance/CURRENT_ENGINEERING_WORKFLOW.md](governance/CURRENT_ENGINEERING_WORKFLOW.md) | operations |
| [docs/governance/DRIFT_HISTORY_AND_LESSONS.md](governance/DRIFT_HISTORY_AND_LESSONS.md) | history |
| [docs/governance/PROCESS_DEVIATIONS_AND_SHORTCUTS.md](governance/PROCESS_DEVIATIONS_AND_SHORTCUTS.md) | history |
| [docs/runbooks/TEST_AND_QUALIFICATION_RUNBOOK.md](runbooks/TEST_AND_QUALIFICATION_RUNBOOK.md) | operations |
| [docs/status/CURRENT_PRODUCT_STATUS.md](status/CURRENT_PRODUCT_STATUS.md) | runtime_reference |
| [docs/status/ISSUE_IMPLEMENTATION_MATRIX.md](status/ISSUE_IMPLEMENTATION_MATRIX.md) | operations |
| [docs/status/ISSUE_WORKSTREAM_MAP.md](status/ISSUE_WORKSTREAM_MAP.md) | operations |
| [samuel/core/prompts/analyst.md](../samuel/core/prompts/analyst.md) | Laufzeit-Promptbibliothek |
| [samuel/core/prompts/docs_writer.md](../samuel/core/prompts/docs_writer.md) | Laufzeit-Promptbibliothek |
| [samuel/core/prompts/healer.md](../samuel/core/prompts/healer.md) | Laufzeit-Promptbibliothek |
| [samuel/core/prompts/log_analyst.md](../samuel/core/prompts/log_analyst.md) | Laufzeit-Promptbibliothek |
| [samuel/core/prompts/planner.md](../samuel/core/prompts/planner.md) | Laufzeit-Promptbibliothek |
| [samuel/core/prompts/reviewer.md](../samuel/core/prompts/reviewer.md) | Laufzeit-Promptbibliothek |
| [samuel/core/prompts/senior_python.md](../samuel/core/prompts/senior_python.md) | Laufzeit-Promptbibliothek |
| [technische Beschreibungen/README.md](../technische%20Beschreibungen/README.md) | runtime_reference |
| [technische Beschreibungen/pipeline_evaluation.md](../technische%20Beschreibungen/pipeline_evaluation.md) | runtime_reference |
| [technische Beschreibungen/pipeline_issue_to_llm.md](../technische%20Beschreibungen/pipeline_issue_to_llm.md) | runtime_reference |
| [technische Beschreibungen/pipeline_planning.md](../technische%20Beschreibungen/pipeline_planning.md) | runtime_reference |
| [technische Beschreibungen/pipeline_pr_gates.md](../technische%20Beschreibungen/pipeline_pr_gates.md) | runtime_reference |

## Weitere Dokumentquellen und Abbildungen

Maschinenlesbare Verträge, Nachweisbeispiele und historische Bilder gehören
ebenfalls zum Dokumentbestand. Sie ersetzen keine Funktionsbeschreibung.

| Datei | Aufgabe / Status |
|---|---|
| [docs/capabilities/control-matrix.json](capabilities/control-matrix.json) | Bestehender maschinenlesbarer Dokument-/Capability-/Wikivertrag |
| [docs/capabilities/document-contract.json](capabilities/document-contract.json) | Bestehender maschinenlesbarer Dokument-/Capability-/Wikivertrag |
| [docs/capabilities/wiki-manifest.json](capabilities/wiki-manifest.json) | Bestehender maschinenlesbarer Dokument-/Capability-/Wikivertrag |
| [Bereitgestellte reale Dashboardaufnahmen](DASHBOARD.md#reale-aufnahmen-aus-dem-bereitgestellten-bildbestand) | Datierter a29-Bildbestand: Status, Block, Settings und Diagnose; fehlende Zustände ausdrücklich benannt. |
| [Reale historische SCM-Aufnahmen](../technische%20Beschreibungen/README.md#reale-scm-aufnahmen-des-änderungsablaufs) | Zusammengehöriger Issue-#2-/PR-#15-Fall; echte Ausschnitte und geprüfte Überlappungen, kein aktueller Golden-PASS. |
| [docs/images/issue-to-human-merge.svg](images/issue-to-human-merge.svg) | Fachdiagramm: Auftrag, Prüfbindungen und menschlicher Merge; Erklärung, kein Laufnachweis. |
| [docs/images/dashboard-settings-2026-10-10.png](images/dashboard-settings-2026-10-10.png) | Reale datierte Dashboardaufnahme vom10.10.2026; synthetischer Installationstest, kein aktueller Lauf-/Qualificationnachweis. |
| [docs/images/dashboard-status-2026-10-10.png](images/dashboard-status-2026-10-10.png) | Reale datierte Dashboardaufnahme vom10.10.2026; synthetischer Installationstest, kein aktueller Lauf-/Qualificationnachweis. |
| [docs/demo/dashboard-tour.gif](demo/dashboard-tour.gif) | HISTORICAL: Bild/GIF, kein aktueller UI-Nachweis |
| [docs/demo/llm-routing-night.png](demo/llm-routing-night.png) | HISTORICAL: Bild/GIF, kein aktueller UI-Nachweis |
| [docs/demo/settings-llm-config.png](demo/settings-llm-config.png) | HISTORICAL: Bild/GIF, kein aktueller UI-Nachweis |
| [docs/demo/workflow-drilldown.png](demo/workflow-drilldown.png) | HISTORICAL: Bild/GIF, kein aktueller UI-Nachweis |
| [docs/examples/findings.sarif](examples/findings.sarif) | Gebundenes Schema bzw. Beispiel-/Rolloutnachweis; kein allgemeiner Qualification-PASS |
| [docs/rollout/issue-399.json](rollout/issue-399.json) | Gebundenes Schema bzw. Beispiel-/Rolloutnachweis; kein allgemeiner Qualification-PASS |
| [docs/rollout/issue-399.schema.json](rollout/issue-399.schema.json) | Gebundenes Schema bzw. Beispiel-/Rolloutnachweis; kein allgemeiner Qualification-PASS |
| [docs/rollout/issue-620.json](rollout/issue-620.json) | Gebundenes Schema bzw. Beispiel-/Rolloutnachweis; kein allgemeiner Qualification-PASS |
| [docs/rollout/issue-620.schema.json](rollout/issue-620.schema.json) | Gebundenes Schema bzw. Beispiel-/Rolloutnachweis; kein allgemeiner Qualification-PASS |

### Aufbereitete Produktaufnahmen

Die folgenden PNGs sind verlustfreie Ausschnitte der bereitgestellten realen
Aufnahmen. Herkunft, Maskierung, Überlappungen und fehlende Zustände stehen in
[Dashboard](DASHBOARD.md#reale-aufnahmen-aus-dem-bereitgestellten-bildbestand) und
[Pipeline](../technische%20Beschreibungen/README.md#reale-scm-aufnahmen-des-änderungsablaufs).

| Datei | Aussage / Grenze |
|---|---|
| [docs/images/product-captures/audit-log-details-a29.png](images/product-captures/audit-log-details-a29.png) | HealthCheck-Log mit aufgeklappten korrelierten Metadaten; begrenzter UI-Ausschnitt. |
| [docs/images/product-captures/compliance-ai-act-ui-a29.png](images/product-captures/compliance-ai-act-ui-a29.png) | Datierter AI-Act-UI-Text und Risikowahl; keine rechtliche Abnahme. |
| [docs/images/product-captures/compliance-attribution-a29.png](images/product-captures/compliance-attribution-a29.png) | Externe LLM-Kennzeichnung und Ausführlichkeit; keine Savewirkung belegt. |
| [docs/images/product-captures/compliance-framework-mappings-a29.png](images/product-captures/compliance-framework-mappings-a29.png) | Vier advisory Framework-Mappings. |
| [docs/images/product-captures/compliance-owasp-legend-a29.png](images/product-captures/compliance-owasp-legend-a29.png) | OWASP-Kategorienlegende; beschreibende Zuordnung. |
| [docs/images/product-captures/dashboard-status-a29.png](images/product-captures/dashboard-status-a29.png) | Statusübersicht; a29, SCM verbunden, Health/LLM OK, kein Score. |
| [docs/images/product-captures/gitea-acceptance-results.png](images/product-captures/gitea-acceptance-results.png) | Sechs gebundene DIFF/TEST/GREP-Kriterien PASSED; kein MANUAL-Kriterium. |
| [docs/images/product-captures/gitea-bound-review.png](images/product-captures/gitea-bound-review.png) | Strukturierter Review pass für Candidate 6a68dd; Acceptance 6/6 PASS. |
| [docs/images/product-captures/gitea-development-completion.png](images/product-captures/gitea-development-completion.png) | Entwicklungsabschluss nach bestätigtem Merge; Issueabschluss/Golden bleiben getrennt. |
| [docs/images/product-captures/gitea-evidence-binding.png](images/product-captures/gitea-evidence-binding.png) | Gateprofil, Korrelation, Repo, Base/Head, Contract und Policy; Serveradresse und privater Owner maskiert. |
| [docs/images/product-captures/gitea-gate-results.png](images/product-captures/gitea-gate-results.png) | Pixelgleich zusammengesetzte Gate-/Extensionergebnisse; PASS ersetzt keine fehlende Coverage. |
| [docs/images/product-captures/gitea-human-merge-header.png](images/product-captures/gitea-human-merge-header.png) | PR #15 durch menschlichen Maintainer zusammengeführt; privater Handle maskiert; drei geänderte Dateien. |
| [docs/images/product-captures/gitea-issue-request.png](images/product-captures/gitea-issue-request.png) | Bestenlistenauftrag für Issue #2; Titel, Erwartung und begrenzter Scope; privater Handle maskiert. |
| [docs/images/product-captures/gitea-passive-score.png](images/product-captures/gitea-passive-score.png) | Nicht bindende Qualitätsbeobachtung 100%; sichtbarer Tabellenanfang, kein Mergesignal. |
| [docs/images/product-captures/gitea-plan-contract.png](images/product-captures/gitea-plan-contract.png) | Plan, Scope und sechs maschinelle Kriterien; wartet laut Text auf Humanapproval. |
| [docs/images/product-captures/gitea-pr-request-and-diff.png](images/product-captures/gitea-pr-request-and-diff.png) | PR-Auftrag und redigierter Diffausschnitt; unterer Diffteil ist abgeschnitten. |
| [docs/images/product-captures/health-checks-a29.png](images/product-captures/health-checks-a29.png) | Technische Einzelchecks OK; keine Golden-Qualification. |
| [docs/images/product-captures/llm-empty-metering-a29.png](images/product-captures/llm-empty-metering-a29.png) | Leere Token-/Calltabellen; doppelte Quality-Matrix weggelassen. |
| [docs/images/product-captures/llm-model-cache-a29.png](images/product-captures/llm-model-cache-a29.png) | Modell-/Benchmarkcache; Aktualität ist keine Kontoverfügbarkeit. |
| [docs/images/product-captures/llm-quality-unattributed-a29.png](images/product-captures/llm-quality-unattributed-a29.png) | Unattribuierter historischer Planningcall ohne gebundenen Score. |
| [docs/images/product-captures/llm-runtime-idle-a29.png](images/product-captures/llm-runtime-idle-a29.png) | LLM-Runtime idle, null Calls/Tokens/Kosten; konfigurierte Auswahl ist kein Call. |
| [docs/images/product-captures/llm-task-routes-a29.png](images/product-captures/llm-task-routes-a29.png) | Konfigurierte Taskrouten und Benchmarkhinweise; kein Schedule konfiguriert. |
| [docs/images/product-captures/problems-empty-a29.png](images/product-captures/problems-empty-a29.png) | Keine passenden aktiven Probleme; Filter-/Zeitfenstergrenze bleibt sichtbar. |
| [docs/images/product-captures/provider-key-presence-a29.png](images/product-captures/provider-key-presence-a29.png) | Providercredential-Präsenz und URL-only; keine Schlüsselwerte. |
| [docs/images/product-captures/provider-transfer-warnings-a29.png](images/product-captures/provider-transfer-warnings-a29.png) | Transferwarnungen; Kontoguthaben aus dem oberen Bildteil ausgeschlossen. |
| [docs/images/product-captures/retention-report-only-a29.png](images/product-captures/retention-report-only-a29.png) | Not-Aus aktiv, Pending Review 29 und report_only_pending_review; keine Löschung. |
| [docs/images/product-captures/runtime-empty-observations-a29.png](images/product-captures/runtime-empty-observations-a29.png) | Leere Score- und Anomalietabellen. |
| [docs/images/product-captures/runtime-event-counts-a29.png](images/product-captures/runtime-event-counts-a29.png) | HealthCheck-/ResumePending-Zähler; keine nachgewiesene Resumeausführung. |
| [docs/images/product-captures/scm-activity-empty-a29.png](images/product-captures/scm-activity-empty-a29.png) | Leere SCM-Activity; keine native Zustellung nachgewiesen. |
| [docs/images/product-captures/security-branch-read-denied-a29.png](images/product-captures/security-branch-read-denied-a29.png) | Branchschutz-Read eingeschränkt; OWASP-Kategoriezähler sind keine bestätigten Angriffe. |
| [docs/images/product-captures/security-empty-events-a29.png](images/product-captures/security-empty-events-a29.png) | Leere Schranken-, OTel- und Integritätsereignistabellen. |
| [docs/images/product-captures/self-check-details-a29.png](images/product-captures/self-check-details-a29.png) | Pixelgleich zusammengesetzte Self-Check-Tabelle mit LLM-Detailfortsetzung. |
| [docs/images/product-captures/self-check-summary-a29.png](images/product-captures/self-check-summary-a29.png) | Technische Gesundheit OK, Readiness ready, Qualification not_checked. |
| [docs/images/product-captures/settings-default-fallback-a29.png](images/product-captures/settings-default-fallback-a29.png) | Default/Fallback-Editor; sichtbarer Button beweist keine Schreibfreigabe. |
| [docs/images/product-captures/settings-dlq-empty-a29.png](images/product-captures/settings-dlq-empty-a29.png) | Leere Dead-Letter-Queue; Replay ist kein rein lesender Refresh. |
| [docs/images/product-captures/settings-documentation-extension-a29.png](images/product-captures/settings-documentation-extension-a29.png) | Documentation Extension disabled; Auswahl publiziert kein Wiki. |
| [docs/images/product-captures/settings-feature-flags-a29.png](images/product-captures/settings-feature-flags-a29.png) | Featureflags; Auto-Merge und Expected-Head-Qualification ausgeschaltet. |
| [docs/images/product-captures/settings-label-sync-a29.png](images/product-captures/settings-label-sync-a29.png) | Labelsynchronisierung als reale SCM-Aktion; nicht ausgeführt. |
| [docs/images/product-captures/settings-legacy-identity-a29.png](images/product-captures/settings-legacy-identity-a29.png) | Legacy-API-Key-Modus; kein local-identity-Cutover nachgewiesen. |
| [docs/images/product-captures/settings-production-freeze-a29.png](images/product-captures/settings-production-freeze-a29.png) | Operator-Konfiguration production mit gleichem gespeicherten/wirksamen Digest. |
| [docs/images/product-captures/settings-task-prompts-a29.png](images/product-captures/settings-task-prompts-a29.png) | Task-/Promptzuordnung mit Paketscope; evaluation ist kein produktiver LLM-Consumer. |
| [docs/images/product-captures/setup-llm-fields-a29.png](images/product-captures/setup-llm-fields-a29.png) | Provider-/Modell-/URL-Eingabe; API-Key ist nur Platzhalter. |
| [docs/images/product-captures/setup-project-fields-a29.png](images/product-captures/setup-project-fields-a29.png) | SCM-/Projektfelder; interne Serveradresse und private Repositoryzuordnung geschwärzt. |
| [docs/images/product-captures/setup-readonly-project-summary-a29.png](images/product-captures/setup-readonly-project-summary-a29.png) | Vorhandene Konfiguration, Production-Freeze und passiver Projektzugriff. |
| [docs/images/product-captures/setup-save-fields-a29.png](images/product-captures/setup-save-fields-a29.png) | Speicherbereich und expliziter unbestätigter Save; keine Speicherung ausgeführt. |
| [docs/images/product-captures/workflow-blocked-audit-a29.png](images/product-captures/workflow-blocked-audit-a29.png) | Auditfortsetzung: DiagnosticRaised, Budgetsettlement, Kontext und IssueReady. |
| [docs/images/product-captures/workflow-blocked-evidence-a29.png](images/product-captures/workflow-blocked-evidence-a29.png) | Historischer Planningcall, keine Tests/Acceptance; Run endet blocked am 09.10.2026. |
| [docs/images/product-captures/workflow-plan-blocked-a29.png](images/product-captures/workflow-plan-blocked-a29.png) | Issue #1 blocked; Plan/LLM failed, nachgelagerte Stages pending, keine Gates. |

## Lokale Root-Unterlagen und historische Nachweise

Die 41 zuvor unversionierten Abschlussberichte, Analyse-/Entscheidungsentwürfe
und privaten Nachweisarchive wurden getrennt vom Produktrepository archiviert.
Sie sind nicht Wikiquellen. Der lokale Archivindex enthält ursprünglichen Pfad,
Archivpfad und SHA-256 je Datei; die Dateien wurden weder gelöscht noch in
aktuelle PASS-Nachweise umgedeutet. Dies folgt der bestehenden
[Archivgrenze](archive/README.md). Private Archive und Zugangsdaten werden nicht
in die öffentliche Dokumentation übernommen.

Vier historische Statussnapshots vom September liegen jetzt unter
`docs/archive/2026-10-09/`; ihre alten Claims bleiben historische Evidence.
Sie sind aus dem aktiven Dokumentvertrag und der aktuellen Wikiprojektion
entfernt. Aktuelle Restumfänge stehen in den Live-Issues und Statusdokumenten.
