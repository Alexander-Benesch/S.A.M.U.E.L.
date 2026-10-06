# Active Document Reconciliation Readback

Stand 2026-09-29; Product-Codebaseline `41340e75e0acc918fbc577653c3bedfec0f70aaa`. Die 55 vor diesem v9-Delta im Contract aktiven Dokumente wurden auf Pfad, Rolle, letztes Git-Datum, Status-/Release-Schluesselwoerter und die unten benannten Quellgrenzen gelesen. `bound` bedeutet maschinengepruefter Code-/Config-/Manifestvertrag, **nicht** semantischer Vollbeweis jeder freien Prosa. `reviewed` bezeichnet die konkrete aktuelle Claimpruefung; `dated` eine als historisch erkannte Aussage. Ein fehlender Vollcheck bleibt offen ausgewiesen.

| Pfad | Rolle | Letzte Aenderung | Code/Config | Release/Issues | v9 geaendert | Befund / Grund falls unveraendert |
|---|---|---:|---|---|---|---|
| `.claude/CLAUDE.md` | operations | 2026-08-28 | partial | partial | no | no evidenced status correction in this delta; deployment evidence remains separate |
| `CHANGELOG.md` | history | 2026-09-21 | dated | reviewed | no | history retained; stale a26 candidate PR #857 not copied |
| `CONTRIBUTING.md` | operations | 2026-09-22 | reviewed | partial | no | no evidenced status correction in this delta; deployment evidence remains separate |
| `MANIFESTO.md` | target_architecture | 2026-09-21 | dated | dated | no | no evidenced status correction in this delta; deployment evidence remains separate |
| `README.md` | runtime_reference | 2026-09-29 | reviewed | reviewed | yes | a25 published/a15 support and missing D0 separated; status links |
| `SECURITY.md` | operations | 2026-09-21 | reviewed | reviewed | no | supported versions table separates a25 and a15 |
| `docs/AI_ACT_COMPLIANCE.md` | operations | 2026-09-19 | partial | partial | no | regulatory context, not a current legal certification |
| `docs/AI_ACT_TECHNICAL_DOC.md` | runtime_reference | 2026-09-19 | partial | partial | no | technical/legal context, current deployment qualification separate |
| `docs/CAPABILITY_MATRIX.md` | runtime_reference | 2026-09-29 | bound | reviewed | yes | generated; control-matrix audit needed after this commit |
| `docs/CI_RUNNER_OPERATIONS.md` | operations | 2026-09-18 | partial | partial | no | external runner details are dated; not live requalified |
| `docs/CONTAINER_RELEASE_OPERATIONS.md` | operations | 2026-09-22 | partial | reviewed | no | a25 lineage present; historical headings dated |
| `docs/DSGVO_VVT.md` | operations | 2026-09-19 | partial | partial | no | operator-specific context, not runtime proof |
| `docs/EXTENSION_CONTRACT.md` | runtime_reference | 2026-09-19 | partial | partial | no | contract exists; external consumer qualification #639 open |
| `docs/GATE_COMPLIANCE_MATRIX.md` | runtime_reference | 2026-08-28 | partial | partial | no | redirect only; source is control matrix |
| `docs/INSTALL.md` | operations | 2026-09-26 | reviewed | reviewed | yes | native webhook, labels, runner, route and Compose preflight added |
| `docs/OPERATING_RULES.md` | operations | 2026-09-26 | reviewed | partial | yes | dated rules retained; current status pointers added |
| `docs/PRODUCT_BOUNDARY_HANDOVER_PROMPT.md` | operations | 2026-09-21 | partial | partial | no | no evidenced status correction in this delta; deployment evidence remains separate |
| `docs/PROMPT_CONTRACT_AUDIT.md` | runtime_reference | 2026-09-24 | partial | partial | no | dated to 24 September and 3be2694, not current blanket claim |
| `docs/README_technical.md` | runtime_reference | 2026-09-28 | reviewed | partial | yes | #904/#906/#910/#912/#913/#916/#918 delta added |
| `docs/RUNTIME_REFERENCE.md` | runtime_reference | 2026-09-26 | bound | partial | no | generated from code/config; rerender needed |
| `docs/SAMUEL_ARCHITECTURE_V2.1.md` | target_architecture | 2026-09-26 | reviewed | dated | yes | target architecture clearly separated from runtime; old fixed matrix date removed |
| `docs/SAMUEL_DESIGN_DECISIONS.md` | adr | 2026-09-21 | reviewed | dated | yes | August Part C marked historical |
| `docs/VERSIONING.md` | operations | 2026-09-22 | reviewed | reviewed | no | a25 publication, a15 support and D0 gap distinct |
| `docs/adr/0399-score-authority.md` | adr | 2026-08-28 | dated | dated | no | accepted decision/history retained; no new runtime authority |
| `docs/adr/0422-local-dashboard-identity.md` | adr | 2026-09-18 | dated | dated | no | accepted decision/history retained; no new runtime authority |
| `docs/adr/0482-runtime-state-store.md` | adr | 2026-09-19 | dated | dated | no | accepted decision/history retained; no new runtime authority |
| `docs/adr/0583-installed-cli-entrypoint.md` | adr | 2026-08-28 | dated | dated | no | accepted decision/history retained; no new runtime authority |
| `docs/adr/0618-worktree-manager.md` | adr | 2026-09-01 | dated | dated | no | accepted decision/history retained; no new runtime authority |
| `docs/adr/0619-candidate-sandbox.md` | adr | 2026-08-30 | dated | dated | no | accepted decision/history retained; no new runtime authority |
| `docs/adr/0620-preflight-gate-state.md` | adr | 2026-08-29 | dated | dated | no | accepted decision/history retained; no new runtime authority |
| `docs/adr/0635-wiki-pilot.md` | adr | 2026-08-29 | dated | dated | no | accepted decision/history retained; no new runtime authority |
| `docs/adr/0643-repository-wiki-materialization.md` | adr | 2026-08-29 | dated | dated | no | accepted decision/history retained; no new runtime authority |
| `docs/adr/0649-wiki-content-projection.md` | adr | 2026-08-29 | dated | dated | no | accepted decision/history retained; no new runtime authority |
| `docs/adr/0678-product-boundary-and-integration-profile.md` | adr | 2026-08-30 | dated | dated | no | accepted decision/history retained; no new runtime authority |
| `docs/adr/0693-health-readiness-qualification.md` | adr | 2026-09-18 | dated | dated | no | accepted decision/history retained; no new runtime authority |
| `docs/adr/0706-atomic-release-layout.md` | adr | 2026-09-02 | dated | dated | no | accepted decision/history retained; no new runtime authority |
| `docs/adr/README.md` | adr | 2026-09-19 | bound | dated | no | accepted decision/history retained; no new runtime authority |
| `docs/agents/AGENT_CONFIGURATION_REFERENCE.md` | runtime_reference | 2026-09-29 | partial | partial | yes | source/path check; free prose needs subject-specific evidence |
| `docs/agents/AGENT_PROMPTS_AND_INSTRUCTIONS.md` | runtime_reference | 2026-09-29 | partial | partial | yes | source/path check; free prose needs subject-specific evidence |
| `docs/audits/INDEX.md` | history | 2026-09-29 | dated | reviewed | yes | private originals copied; public-safe summaries and SHA-256 indexed |
| `docs/github/GITHUB_SYNC_READINESS.md` | operations | 2026-09-29 | partial | partial | yes | historical public GitHub URL/head recovered |
| `docs/governance/CURRENT_ENGINEERING_WORKFLOW.md` | operations | 2026-09-29 | partial | partial | yes | no evidenced status correction in this delta; deployment evidence remains separate |
| `docs/governance/DRIFT_HISTORY_AND_LESSONS.md` | history | 2026-09-29 | dated | dated | yes | historical record retained; not current Product status |
| `docs/governance/PROCESS_DEVIATIONS_AND_SHORTCUTS.md` | history | 2026-09-29 | dated | dated | yes | historical record retained; not current Product status |
| `docs/runbooks/TEST_AND_QUALIFICATION_RUNBOOK.md` | operations | 2026-09-29 | partial | partial | yes | no evidenced status correction in this delta; deployment evidence remains separate |
| `docs/status/CURRENT_PRODUCT_STATUS.md` | runtime_reference | 2026-09-29 | partial | reviewed | yes | source/path check; free prose needs subject-specific evidence |
| `docs/status/ISSUE_IMPLEMENTATION_MATRIX.md` | operations | 2026-09-29 | partial | reviewed | yes | no evidenced status correction in this delta; deployment evidence remains separate |
| `docs/status/ISSUE_WORKSTREAM_MAP.md` | operations | 2026-09-29 | partial | reviewed | yes | no evidenced status correction in this delta; deployment evidence remains separate |
| `docs/status/REHEARSAL_REPOSITORY_CLEANUP.md` | operations | 2026-09-29 | partial | partial | yes | demo-role readback supersedes Product-Bot 404 |
| `docs/status/WORKING_DECISIONS_TO_ISSUES.md` | history | 2026-09-29 | dated | reviewed | yes | historical record retained; not current Product status |
| `technische Beschreibungen/README.md` | runtime_reference | 2026-09-28 | partial | partial | no | source/path check; free prose needs subject-specific evidence |
| `technische Beschreibungen/pipeline_evaluation.md` | runtime_reference | 2026-09-26 | partial | partial | no | source/path check; free prose needs subject-specific evidence |
| `technische Beschreibungen/pipeline_issue_to_llm.md` | runtime_reference | 2026-09-29 | partial | partial | no | source/path check; free prose needs subject-specific evidence |
| `technische Beschreibungen/pipeline_planning.md` | runtime_reference | 2026-09-29 | partial | partial | no | source/path check; free prose needs subject-specific evidence |
| `technische Beschreibungen/pipeline_pr_gates.md` | runtime_reference | 2026-09-28 | partial | partial | no | source/path check; free prose needs subject-specific evidence |

## Grenzen und Checks

The control-matrix `check` validates 75 controls and bound document sections; the Wiki `check` validates source digests and 10 page projections after clean commit. Full Product tests and CI are recorded separately. Neither tool proves free-form prose or real operator/Provider/D0 availability. The relevant current drift was corrected in the files marked changed; older dated ADRs, release histories and regulatory context were not rewritten.
