# Closed Product Issue Classification

Stand: 2026-09-29; Product `main@41340e75`. Diese vollständige 436er-Liste ist ein **konservativer historischer Triage-Readback**, kein erneuter individueller Code-/Test-/Real-Evidence-Abschluss für jedes Issue. `UNKNOWN` ist absichtlich offen ausgewiesen, wo die verfügbare Abschluss-Evidence nicht ausreicht. Ein geschlossenes Gitea-State allein beweist keinen aktuellen Capability-PASS. Klassifikationszaehlung: DOC_ONLY=26, IMPLEMENTED_UNVERIFIED=205, UNKNOWN=205.

| Issue | Titel | Closed at | Klassifikation | Merged PR-Anker | Aussagegrenze |
|---|---|---|---|---|---|
| #2 | Phase 0b: Shared Kernel bauen | 2026-04-15T19:22:45+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #3 | 0b.1 — samuel/core/ anlegen (10 Dateien) | 2026-04-15T19:22:45+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #4 | 0b.2 — Architecture-Tests schreiben | 2026-04-15T19:22:45+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #5 | 0b.3 — Skeleton-Abstraktion (Parallel-Track SP) | 2026-04-15T19:22:46+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #6 | Phase 1: Audit-Migration (erste Bridge) | 2026-04-15T19:43:02+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #7 | 1.1 — Audit-Bridge mit correlation_id | 2026-04-15T19:43:03+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #8 | 1.2 — Audit-Slice anlegen | 2026-04-15T19:43:03+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #9 | 1.3 — JSONL-Adapter + Upcaster anlegen | 2026-04-15T19:43:03+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #10 | 1.4 — AsyncAuditSink implementieren | 2026-04-15T19:43:06+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #11 | 1.5 — config/audit.json Schema | 2026-04-15T19:43:06+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #12 | Phase 2: SCM-Port (Gitea → IVersionControl) | 2026-04-15T21:16:12+02:00 | `IMPLEMENTED_UNVERIFIED` | #78 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #13 | 2.1 — IVersionControl vollständig definieren | 2026-04-15T21:16:34+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #14 | 2.2 — GiteaAdapter anlegen | 2026-04-15T21:16:34+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #15 | 2.3 — gitea_api.py zur Bridge machen | 2026-04-15T21:16:35+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #16 | 2.4 — IAuthProvider implementieren | 2026-04-15T21:16:38+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #17 | 2.5 — Provider-agnostische Config | 2026-04-15T21:16:41+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #18 | Phase 3: LLM-Port | 2026-04-15T21:16:13+02:00 | `IMPLEMENTED_UNVERIFIED` | #79 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #19 | 3.1 — ILLMProvider vollständig definieren | 2026-04-15T21:16:42+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #20 | 3.2 — LLMResponse Dataclass sicherstellen | 2026-04-15T21:16:43+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #21 | 3.3 — LLM-Adapter anlegen | 2026-04-15T21:16:44+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #22 | 3.4 — CircuitBreakerAdapter | 2026-04-15T21:16:44+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #23 | 3.5 — SanitizingLLMAdapter | 2026-04-15T21:16:45+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #24 | 3.6 — plugins/llm.py zur Bridge machen | 2026-04-15T21:16:46+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #25 | Phase 4: Erster Slice — Planning | 2026-04-15T20:23:50+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #26 | 4.1 — samuel/slices/planning/ anlegen | 2026-04-15T21:16:49+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #27 | 4.2 — PlanIssueCommand definieren | 2026-04-15T21:16:51+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #28 | 4.3 — 3-Stufen LLM-Qualitätskontrolle | 2026-04-15T21:16:51+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #29 | 4.4 — commands/plan.py zur Bridge machen | 2026-04-15T21:16:52+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #30 | 4.5 — Integration-Test: Vollständiger Plan-Durchlauf | 2026-04-15T21:16:52+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #31 | Phase 5: Implementation-Slice | 2026-04-15T20:33:37+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #32 | 5.1 — Implementation-Slice Struktur anlegen | 2026-04-15T21:16:53+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #33 | 5.2 — IPatchApplier-Registry | 2026-04-15T21:16:53+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #34 | 5.3 — Resume mit WorkflowCheckpoint | 2026-04-15T21:16:54+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #35 | 5.4 — Semaphore-Release-Verdrahtung | 2026-04-15T21:16:55+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #36 | 5.5 — commands/implement_llm.py zur Bridge | 2026-04-15T21:16:58+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #37 | Phase 6: PR-Gates-Slice | 2026-04-15T20:40:00+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #38 | 6.1 — PR-Gates-Slice anlegen | 2026-04-15T21:17:00+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #39 | 6.2 — PRGatesHandler mit Bus-Injection | 2026-04-15T21:17:03+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #40 | 6.3 — config/gates.json implementieren | 2026-04-15T21:17:06+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #41 | 6.4 — IExternalGate-Infrastruktur | 2026-04-15T21:17:08+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #42 | 6.5 — commands/pr.py zur Bridge | 2026-04-15T21:17:12+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #43 | Phase 7: Evaluation-Slice | 2026-04-15T21:16:17+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #44 | 7.1 — Evaluation-Slice anlegen | 2026-04-15T21:17:13+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #45 | 7.2 — config/eval.json mit Pydantic | 2026-04-15T21:17:13+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #46 | 7.3 — eval_after_restart.py zur Bridge | 2026-04-15T21:17:15+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #47 | Phase 8: Watch, Healing, Dashboard + alle übrigen Slices | 2026-04-15T21:16:18+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #48 | 8.1 — Watch-Slice | 2026-04-15T21:17:18+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #49 | 8.2 — Healing-Slice | 2026-04-15T21:17:20+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #50 | 8.3 — Dashboard-Slice | 2026-04-15T21:17:21+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #51 | 8.4 — Alle weiteren Slices (12 Stück) | 2026-04-15T21:17:22+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #52 | Phase 9: Aufräumen | 2026-04-16T23:47:55+02:00 | `IMPLEMENTED_UNVERIFIED` | #123 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #53 | Phase 10: Server-Hook + Flexibilität | 2026-04-17T00:03:19+02:00 | `IMPLEMENTED_UNVERIFIED` | #126 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #54 | Phase 0a: Vorarbeiten (Blocker VOR erstem Slice-Commit) | 2026-04-15T21:16:19+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #55 | 0a.1 — Pre-commit Hook: Test-Konvention für beide Welten | 2026-04-15T21:17:22+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #56 | 0a.2 — helpers.py: Auflösung nach Entscheidungsmatrix | 2026-04-15T21:17:23+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #57 | 0a.3 — AgentAbort: Event-Publishing hinzufügen | 2026-04-15T21:17:24+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #58 | 0a.4 — _cfg(): Config-Injection vorbereiten | 2026-04-15T21:17:26+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #59 | 0a.5 — Sequence-Validator auf warn-only verifizieren | 2026-04-15T21:17:28+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #60 | 9.1 — agent_start.py → samuel/cli.py reduzieren | 2026-04-16T23:41:17+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #61 | 9.2 — Alle v1-commands/ entfernen | 2026-04-16T23:41:23+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #62 | 9.3 — Alle v1-plugins/ entfernen | 2026-04-16T23:41:29+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #63 | 9.4 — test_every_v1_file_mapped() muss 0 unmapped melden | 2026-04-16T23:46:18+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #64 | 9.5 — repo_patterns.json neu lernen | 2026-04-16T23:46:28+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #65 | 9.6 — Sequence-Validator zurück auf Konfigurationswert | 2026-04-16T23:46:36+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #66 | 9.7 — Dokumentation aktualisieren | 2026-04-16T23:46:44+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #67 | 10.1 — Gitea pre-receive Hook | 2026-04-17T00:01:42+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #68 | 10.2 — GitHub-Support | 2026-04-17T00:01:54+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #69 | 10.3 — IQualityCheck Registry (externe Quality-Pipeline) | 2026-04-17T00:02:06+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #70 | 10.4 — Weitere Skeleton-Builder | 2026-04-17T00:02:16+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #71 | 8.5 — Workflow-JSON-Dateien anlegen (7 Stück) | 2026-04-15T21:17:29+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #72 | P1 — Premium-Module: LLM-Routing + Token-Limit | 2026-04-15T23:00:41+02:00 | `IMPLEMENTED_UNVERIFIED` | #132 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #73 | P2 — REST-API + Webhook-Ingress | 2026-04-15T23:00:42+02:00 | `IMPLEMENTED_UNVERIFIED` | #132 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #74 | P3 — Notification-Adapter (Slack, Teams, Webhook) | 2026-04-15T23:00:43+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #75 | P4 — ISecretsProvider + EnvSecrets Adapter | 2026-04-15T21:17:39+02:00 | `IMPLEMENTED_UNVERIFIED` | #132 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #91 | 11.1 — DSGVO-Umsetzung | 2026-04-17T00:21:33+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #92 | 11.2 — EU AI Act Umsetzung | 2026-04-17T00:21:39+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #93 | 12.1 — Packaging & Distribution | 2026-04-17T00:35:43+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #94 | 12.2 — Netzwerk, TLS & API-Härtung | 2026-04-17T00:35:45+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #95 | 12.3 — Testing & CI | 2026-04-17T00:35:49+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #96 | 12.4 — 2026 Best Practice & Modernisierung | 2026-04-17T00:35:52+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #97 | 13.1 — Config: LLM-Hardcoded-Werte | 2026-04-17T07:41:03+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #98 | 13.2 — Config: SCM / Workflow / Agent | 2026-04-17T07:41:05+02:00 | `IMPLEMENTED_UNVERIFIED` | #131 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #99 | 13.3 — Config: Context / Kontext | 2026-04-17T07:41:06+02:00 | `IMPLEMENTED_UNVERIFIED` | #132 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #100 | 13.4 — Config: Strukturelle Verbesserungen | 2026-04-17T07:41:10+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #101 | 13.5 — LLM-Provider & Adapter | 2026-04-17T07:41:14+02:00 | `IMPLEMENTED_UNVERIFIED` | #132 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #102 | 13.6 — LLM-Client Qualität & Konsistenz | 2026-04-17T07:41:19+02:00 | `IMPLEMENTED_UNVERIFIED` | #132 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #103 | 13.7 — Security: Injection-Lücken | 2026-04-17T07:41:24+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #104 | 13.8 — Security: Secrets & Auth | 2026-04-17T07:41:29+02:00 | `IMPLEMENTED_UNVERIFIED` | #132 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #105 | 13.9 — Security: RBAC & Zugriffskontrolle | 2026-04-17T07:41:34+02:00 | `IMPLEMENTED_UNVERIFIED` | #132 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #106 | 13.10 — Security: Integrität & Audit | 2026-04-17T07:41:38+02:00 | `IMPLEMENTED_UNVERIFIED` | #132 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #107 | 13.11 — Event-Bus: Fehlende Events & Commands | 2026-04-17T07:41:42+02:00 | `IMPLEMENTED_UNVERIFIED` | #131 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #108 | 13.12 — Event-Bus: Architektur-Inkonsistenzen | 2026-04-17T07:41:47+02:00 | `IMPLEMENTED_UNVERIFIED` | #131 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #109 | 13.13 — Event-Bus: Strukturelle Verbesserungen | 2026-04-17T07:41:51+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #110 | 13.14 — Workflow-Robustheit & Error-Recovery | 2026-04-17T07:41:56+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #111 | 13.15 — Error-Handling: Stilles Fangen | 2026-04-17T07:42:00+02:00 | `IMPLEMENTED_UNVERIFIED` | #131 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #112 | 13.16 — Error-Handling: Windows / Cross-Platform | 2026-04-17T07:42:04+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #113 | 13.17 — SCM / Gitea API & Datenfluss | 2026-04-17T07:42:09+02:00 | `IMPLEMENTED_UNVERIFIED` | #131, #132 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #114 | 13.18 — Dashboard & UI | 2026-04-17T07:42:11+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #115 | 13.19 — Logging & Observability | 2026-04-17T07:42:13+02:00 | `IMPLEMENTED_UNVERIFIED` | #131 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #116 | 13.20 — Vergessene v1: Code-Duplikate | 2026-04-17T07:42:17+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #117 | 13.21 — Vergessene v1: Slice-Zuordnung | 2026-04-17T07:42:21+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #118 | 13.22 — Vergessene v1: Fehlende Module | 2026-04-17T07:42:22+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #119 | Phase 11: Compliance (EU AI Act & DSGVO) | 2026-04-17T00:22:20+02:00 | `IMPLEMENTED_UNVERIFIED` | #127 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #120 | Phase 12: Hardening & Modernisierung | 2026-04-17T00:36:26+02:00 | `IMPLEMENTED_UNVERIFIED` | #128 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #121 | Phase 13: Vergessenes & Konzeptfehler (Gap-Analyse) | 2026-04-17T07:43:04+02:00 | `IMPLEMENTED_UNVERIFIED` | #129 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #122 | Sequence-Validator: Patterns lernen + auf block umstellen | 2026-05-05T21:35:21+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #124 | Deploy: pre-receive Hook auf Gitea-Server installieren | 2026-08-25T16:21:15+02:00 | `IMPLEMENTED_UNVERIFIED` | #545 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #125 | GitHub Webhook: Signatur-Validierung (X-Hub-Signature-256) | 2026-05-05T21:35:23+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #130 | Phase 9–13 Nachaudit: 18 fehlende Implementierungen & Artefakte | 2026-04-17T09:21:04+02:00 | `IMPLEMENTED_UNVERIFIED` | #132 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #133 | QS-Check: Verbleibende Findings nach Nachaudit Phase 9–13 | 2026-05-05T21:50:18+02:00 | `IMPLEMENTED_UNVERIFIED` | #131, #134, #235 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #136 | CLI: --version Flag hinzufügen | 2026-04-29T15:38:31+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #137 | Phase 14.1: Labels-Seeding-Script + config/labels.json | 2026-04-17T12:41:31+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #138 | Phase 14.2: Self-Mode CLI + .env.agent Override | 2026-04-17T12:44:37+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #139 | Phase 14.3+14.4: Implementation-Context-Pipeline + Patch-Retry mit echtem Code | 2026-04-17T12:54:21+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #140 | Phase 14.5: Workflow-Label-Transitions in Slices | 2026-04-17T12:57:05+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #141 | Phase 14.6: Dashboard Phase 2 — Actions, LLM-Routing, Self-Check, Tamper | 2026-04-17T13:09:17+02:00 | `IMPLEMENTED_UNVERIFIED` | #135 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #142 | Phase 14: v1 → v2 Feature-Parity (Überblick) | 2026-05-05T21:35:25+02:00 | `IMPLEMENTED_UNVERIFIED` | #235 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #152 | Context-Builder: Skeleton-as-TOC für große Files ohne Anker + Slice-Request-Loop | 2026-05-31T18:31:48+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #153 | LLM-Qualitätskontrolle: gemessene Gewichtung pro (Provider, Modell, Task) | 2026-05-30T09:18:28+02:00 | `IMPLEMENTED_UNVERIFIED` | #576 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #157 | fix(quality): QualityHandler bekommt keine Checks aus hooks.json Aus QS-Check #133, Punkt **B2**. Im Audit (2026-04-29) verifiziert: Bug existiert weiterhin.  ## Problem `samuel/core/bootstrap.py:195` instantiiert: ```python quality_handler = QualityHa… | 2026-04-29T14:52:46+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #158 | fix(privacy): DeleteUserDataCommand ist Placeholder (anonymized_count=0) Aus QS-Check #133, Punkt **B6**. DSGVO-relevant (Art. 17 — Recht auf Vergessenwerden). Im Audit (2026-04-29) verifiziert: Placeholder existiert weiterhin.  ## Problem `samuel/sli… | 2026-04-29T14:55:38+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #159 | fix(workflow): Review + Changelog im standard.json Workflow verdrahten Aus QS-Check #133, Punkt **B5**. Im Audit (2026-04-29) verifiziert.  ## Problem `ReviewCommand` und `ChangelogCommand` sind: - in `bootstrap.py:214,219` registriert - mit echtem Han… | 2026-04-29T14:58:47+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #163 | feat(changelog): ChangelogCommand braucht Trigger (CLI / Phase-End-Hook) | 2026-05-06T14:25:10+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #165 | feat(llm): Manual LLM-Adapter — File-Bridging für Setups ohne API-Key | 2026-04-29T15:19:23+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #167 | feat(self-mode): SAMUEL_LLM_PROVIDER env-Override + .env.agent gitignore | 2026-04-29T15:22:25+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #169 | fix(bootstrap): LLM-Log zeigt config-Wert statt aktiven Adapter (env-Override unsichtbar) | 2026-04-29T15:24:34+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #172 | fix(git): commit-Author über SAMUEL_GIT_AUTHOR_NAME/EMAIL env-vars (kein git config nötig) | 2026-04-29T15:57:21+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #174 | fix(dashboard): liest agent.jsonl statt rotated agent_<DATUM>.jsonl — Workflow-Tab leer | 2026-04-29T16:14:32+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #176 | test(self-mode): Trivial-Issue für Pipeline-Smoke — Help-Text in cli.py präzisieren | 2026-04-29T22:57:08+02:00 | `IMPLEMENTED_UNVERIFIED` | #220 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #177 | fix(audit): JSONLAuditSink stringified dataclass-Events statt strukturiertes JSON | 2026-04-29T16:19:03+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #179 | fix(bus): AuditMiddleware verwirft Original-Payload — issue/correlation/data nie audited | 2026-04-29T16:36:39+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #180 | feat(llm): LLMCallCompleted-Event publishen damit Kosten-Tracking funktioniert | 2026-04-29T16:50:38+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #181 | fix(workflow): CreatePR-Trigger nach EvalCompleted endet still — kein PR, kein Log, Issue offen | 2026-04-29T16:46:04+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #182 | fix(implementation): stage_files([]) staged ALLE modifizierten Files — Migration-Patches landen im Commit | 2026-04-29T16:39:51+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #187 | fix(workflow): Branch + changed_files Datenfluss von Implementation → Evaluation → CreatePR | 2026-04-29T17:01:59+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #188 | fix(planning): Plan-Kommentar bekommt Agent-Metadaten-Block (Gate 3) | 2026-04-29T17:04:49+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #191 | fix(dashboard): Metrics aus Audit-Log aggregieren statt prozess-lokal | 2026-04-29T18:22:33+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #192 | feat(llm): Per-Task Provider/Model-Routing — 'welche LLM macht was zu welcher Zeit' | 2026-04-29T22:53:36+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #193 | fix(workflow): auto_merge_pr Feature-Flag verdrahten — wirkt aktuell NIE | 2026-05-04T10:05:26+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #194 | fix(dashboard): Health-Tab zeigt nur scm/config — fehlen LLM/Workflow/Audit-Sink | 2026-05-05T21:48:24+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #197 | fix(dashboard): Tabs leer — Feld-Mismatch, /api/metrics legacy, data_dir nicht propagiert | 2026-04-29T18:54:20+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #199 | feat(dashboard): Workflow-Issue-Detail mit Audit-Trail + Pipeline-Stufen (v1-Parity) | 2026-04-29T19:16:36+02:00 | `IMPLEMENTED_UNVERIFIED` | #198 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #200 | feat(dashboard): Security-Tab — Tamper-Banner + OpenTelemetry + Schranken mit step/barrier-name | 2026-04-29T19:37:59+02:00 | `IMPLEMENTED_UNVERIFIED` | #198 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #201 | feat(dashboard): LLM-Tab — API-Key-Validation + Token-History + Quality-Scores | 2026-04-29T19:54:54+02:00 | `IMPLEMENTED_UNVERIFIED` | #198 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #202 | feat(dashboard): Status-Tab — System-Tiles + Score-History (v1-Parity) | 2026-04-29T20:18:20+02:00 | `IMPLEMENTED_UNVERIFIED` | #198 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #203 | feat(dashboard): Logs-Meta-Toggle + Stat-Tiles | 2026-04-29T21:12:18+02:00 | `IMPLEMENTED_UNVERIFIED` | #198 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #204 | feat(dashboard): Settings — LLM-Config-Anzeige + Label-Sync-Button + API-Key-Status | 2026-05-05T16:33:23+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #206 | fix(llm): MeteringLLMAdapter publisht LLMCallCompleted ohne issue-Korrelation | 2026-04-29T21:36:20+02:00 | `IMPLEMENTED_UNVERIFIED` | #205 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #208 | feat(security): TamperDetected/UnauthorizedChange/IntegrityViolation Events publizieren | 2026-05-29T20:07:16+02:00 | `IMPLEMENTED_UNVERIFIED` | #207 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #209 | feat(scm): IVersionControl.get_branch_protection() + GiteaAdapter-Implementierung | 2026-05-06T14:33:29+02:00 | `IMPLEMENTED_UNVERIFIED` | #207 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #211 | feat(llm): API-Key-Validation per Provider-Endpoint (Dashboard-Anzeige) | 2026-05-05T16:17:03+02:00 | `IMPLEMENTED_UNVERIFIED` | #210 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #213 | feat(eval): Anti-Regression — Baseline auto-promotion + persistente Score-History | 2026-04-29T20:18:59+02:00 | `IMPLEMENTED_UNVERIFIED` | #212, #576 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #219 | fix(workflow): auto_implement_llm Feature-Flag verdrahten — wirkt aktuell NIE | 2026-04-29T22:45:27+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #221 | fix(planning): PlanValidated vor post_comment publisht — Race-Condition mit PR-Gates | 2026-04-29T22:28:36+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #223 | epic(self-mode): Robustheits-Findings aus Live-Runs 2026-04-29 | 2026-04-29T23:24:47+02:00 | `IMPLEMENTED_UNVERIFIED` | #222 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #225 | feat(llm): Per-Task Provider/Model-Routing + Task-Naming-Konsolidierung | 2026-05-05T15:59:09+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #226 | fix(implementation): Git-Cleanup robust gegen existierende Branch + dirty worktree | 2026-04-29T23:09:44+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #227 | fix(cli): --self run Pre-Check fuer main-Branch | 2026-04-29T23:13:28+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #228 | fix(evaluation): kein 'default to passed' bei fehlenden criteria_scores | 2026-04-29T23:22:05+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #230 | feat(observability): SCM-Aktivitaet ins Bus einspeisen — Dashboard zeigt nur Bot-Workflow, keine Repo-Realitaet | 2026-05-31T18:21:31+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #232 | feat(evaluation): Score-Producer aus AC-Verifikation — criteria_scores aus Plan/Repo herleiten | 2026-04-29T23:31:55+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #236 | fix(ac_verification): Tag-Argument-Extraktion strukturiert (X4 von 4) | 2026-05-01T10:53:29+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #237 | feat(planning): Plan-Stage bekommt Code-Kontext (Skeleton + relevant_files + grep) (X1 von 4) | 2026-05-01T11:27:42+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #238 | feat(planning): Plan-Pre-Check härten — Skeleton-Validation + AC-Dry-Run (X2 von 4) | 2026-05-01T13:11:30+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #239 | feat(workflow): EvalFailed-Retry-Loop mit max 3 Runden + No-Improvement-Stop (X3 von 4) | 2026-05-05T21:35:26+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #240 | feat(ac_verification): TEST-Tag-Handler sprachneutral (X0 von 5) | 2026-04-30T10:18:24+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #241 | fix(implementation): Score läuft gegen Issue-Branch, nicht main (X-1 von 6) | 2026-04-30T09:48:30+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #243 | fix(pr_gates): Gate 8 per-Datei-Diff-Tracking statt globaler Walk (X-2 von 7) | 2026-04-30T10:13:15+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #246 | feat(dashboard): Frontend für test_runs + Anomaly-Trigger + AI-Act-Spalte (X0+ Folge zu #240) | 2026-04-30T11:46:20+02:00 | `IMPLEMENTED_UNVERIFIED` | #249 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #247 | feat(planning): Plan-Komplexitäts-Wächter + Scope-Creep + Out-of-Scope-Diff (v1-Parität, Phase 2) | 2026-05-29T20:58:13+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #248 | fix(self_mode): Orphan req-Files + Timeout-Fallback bei Process-Kill | 2026-05-01T09:50:45+02:00 | `IMPLEMENTED_UNVERIFIED` | #541 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #250 | fix(pr_gates): Gate 8 String-Inhalt von echten Imports unterscheiden | 2026-05-01T09:59:14+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #251 | fix(dashboard): OWASP-Klassifikation analog zu AI-Act dynamisch (Charter §1.4 Tandem-Pflicht) | 2026-04-30T12:28:01+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #252 | feat(dashboard): OWASP- + AI-Act-Legende sichtbar im Audit-Tab | 2026-05-01T10:06:37+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #253 | fix(ac_verification): TestRunCompleted-Events tragen issue-Field (Lückenschluss zu #246) | 2026-05-01T09:54:13+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #254 | fix(ac_verification): TEST-Runner nutzt sys.executable -m pytest (PATH-Robustheit) | 2026-05-01T10:26:43+02:00 | `IMPLEMENTED_UNVERIFIED` | #256 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #257 | fix(audit): Self-Mode verliert ~30-50%% der Workflow-Events bei sys.exit | 2026-05-01T09:20:29+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #258 | fix(dashboard): Stage-Mapping zeigt erfolgreiche gates/quality/review/implement als pending | 2026-05-01T09:33:04+02:00 | `IMPLEMENTED_UNVERIFIED` | #256 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #259 | analysis(self_mode): Prompt-Praezision vs Verifier-LLM vs staerkeres Implementation-Modell | 2026-05-01T09:45:58+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #260 | fix(cli): agent.mode-Override wirkt nicht — Self-Mode laedt standard.json statt self.json | 2026-05-01T09:24:47+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #269 | refactor(compliance): OWASP+AI-Act Mappings nach config/compliance/*.json externalisieren | 2026-05-05T13:36:58+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #270 | LLM generierter Code absolut kenntlich machen | 2026-05-29T21:37:51+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #271 | fix(workflow): self_parity_ok-Condition liest payload.score statt eval_score | 2026-05-01T11:01:26+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #274 | fix(quality): branch im Payload propagieren — sonst CreatePR-Gate-1-FAIL nach EvalCompleted | 2026-05-01T11:42:39+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #277 | feat(dashboard): Multi-Run-History pro Issue + Recovery-Trend (failed → passed) | 2026-05-06T14:42:28+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #280 | fix(ac_verification): _check_grep ValueError bei relativem project_root | 2026-05-01T18:16:05+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #281 | docs: OPERATING_RULES.md — Phase-2+-Regelwerk aus Phase-1-Lessons | 2026-05-01T17:58:05+02:00 | `DOC_ONLY` | — | Dokumentationsscope; historischer Abschluss |
| #283 | cleanup(ac_verification): _extract_arg/_ARG_SEPARATORS doppelt definiert | 2026-05-04T09:02:28+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #285 | fix(workflow): _cond_self_parity_ok — Hartstop wenn AC-Verifier 0 ACs liefert | 2026-05-04T08:50:27+02:00 | `IMPLEMENTED_UNVERIFIED` | #284 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #289 | test(workflow): auto_merge_pr End-to-End Live-Smoke gegen Gitea | 2026-08-30T00:53:42+02:00 | `IMPLEMENTED_UNVERIFIED` | #660 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #290 | migrate(owasp): A01..A10 (Draft 2024) -> ASI01..ASI10 (offiziell 2026) | 2026-05-29T18:38:27+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #292 | fix(compliance): Deployment-Regression — JSON-Files muessen ins Package, nicht ins Projekt-Root | 2026-05-05T13:51:00+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #294 | feat(license): Premium-Plugin-Foundation — Ed25519-signierte Lifetime-Lizenzen | 2026-05-05T14:37:00+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #297 | feat(plan-check): Schicht D — Issue-Body-Coverage-Check im Plan-Pre-Check | 2026-05-05T16:06:27+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #301 | feat(llm): v1-Parität — Per-Task base_url/timeout/system_prompt + Free-Tier-Gate | 2026-05-05T18:33:30+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #302 | feat(llm): Time-Window-Routing per Task — schedule-Block (Premium llm_routing_advanced) | 2026-05-05T18:41:29+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #303 | feat(llm): Gemini-Adapter — neuer Provider neben Claude/DeepSeek/Ollama/LMStudio/Manual | 2026-05-05T18:48:37+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #304 | feat(llm): OpenAI-direct-Adapter — Top-Level (statt nur via openai_compat) | 2026-05-05T19:00:02+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #309 | feat(dashboard): Settings — Per-Task LLM-Config schreibbar via UI (Premium llm_routing_dashboard_write) | 2026-05-05T19:16:27+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #311 | feat(llm): OpenRouter-Models-Discovery — public API + CLI + Dashboard-Endpoint mit Preisen | 2026-05-05T19:58:39+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #312 | feat(dashboard): LLM-Editor Layout-Fix + Provider-spezifische URL-Pre-Fill | 2026-05-05T20:35:20+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #313 | feat(dashboard): LLM-Editor Models-Dropdown + Preis-Anzeige (Premium) | 2026-05-05T20:37:20+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #314 | feat(dashboard): LLM-Editor Test-Connection-Button + Balance-Anzeige (Premium) | 2026-05-05T20:50:11+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #315 | feat(dashboard): System-Prompts View + Edit-Modal (Premium fuer Edit) | 2026-05-05T20:56:19+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #316 | feat(dashboard): LLM-Editor Schedule-Sektion (Time-Window-Picker, Premium llm_routing_advanced) | 2026-05-05T20:59:54+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #318 | feat(llm): OpenRouter als Gateway-Provider — unified Billing + Balance | 2026-05-05T20:44:01+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #319 | analyze(self-mode): Hang-Patterns + dedicated Health-Metrics | 2026-05-05T20:21:26+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #328 | fix(dashboard): LLM-Editor — base_url Pre-Fill + Models-Endpoint nutzt Editor-URL | 2026-05-05T21:11:44+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #332 | feat(security): RBAC / Benutzersystem (Backlog aus #133 F1) | 2026-08-30T00:31:00+02:00 | `IMPLEMENTED_UNVERIFIED` | #657 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #333 | feat(audit): Audit-Log HMAC-Chain (Backlog aus #133 F2) | 2026-05-29T20:12:55+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #334 | feat(bus): Dead-Letter-Queue fuer fehlgeschlagene Events (Backlog aus #133 F3) | 2026-05-29T20:01:29+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #335 | feat(llm): Structured Output / JSON-Schema fuer LLM-Calls (Backlog aus #133 F4) | 2026-05-29T20:45:39+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #336 | feat(observability): Event-Sourcing fuer Workflow-Replay (Backlog aus #133 F6) | 2026-05-29T20:18:08+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #337 | feat(llm): LLM Retry-Adapter mit Exponential-Backoff (Backlog aus #133 F8) | 2026-05-29T19:54:54+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #338 | feat(prompts): System-Prompts haerten + Per-Modell-Overrides + Reset-to-Default (Premium-Erweiterung) | 2026-05-06T14:59:16+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #346 | fix(audit): get_llm_routing round-trip + defaults.json system_prompt + factory wiring (Audit-Fix-2) | 2026-05-06T18:34:26+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #348 | feat(dashboard): Source-Indikator pro Task im LLM-Editor (#338 Schicht-B sichtbar machen) | 2026-05-06T18:56:33+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #350 | rfc(prompts): Prompt-Library + explizite Provider-Zuweisung + Default-Vorlage im Editor | 2026-05-06T20:14:44+02:00 | `IMPLEMENTED_UNVERIFIED` | #352 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #351 | feat(prompts): Hybrid-Library + per-Provider-Zuweisung + Default-Vorlage im Editor (#350 Option 3) | 2026-05-06T19:22:15+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #357 | refactor(prompts): Prompt-Konzept konsolidieren — eine Wahrheit, statt zwei parallele Mechanismen | 2026-05-08T11:36:12+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #359 | feat(dashboard): Click-Expand fuer OWASP/AI-Act-Codes im Audit-Trail + Schranken-Protokoll | 2026-05-06T20:27:41+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #364 | fix(prompts): delete_prompt-Endpoint mappt idempotent auf HTTP 400 statt 200 | 2026-05-08T12:03:28+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #366 | fix(compliance): AI-Act-Klassifikation konsistent — Limited Risk + freiwillige High-Risk-Standards | 2026-05-08T13:19:27+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #368 | User Feedback | 2026-06-01T09:42:42+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #371 | feat(dashboard): Compliance-Tab — Pflicht/freiwillig-Badges für AI-Act-Artikel (obligation) | 2026-05-29T18:51:30+02:00 | `IMPLEMENTED_UNVERIFIED` | #367 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #373 | refactor(compliance): AI-Act-obligation kontextabhängig von Deployment-Risikoklasse (nicht statisch) | 2026-05-29T19:23:33+02:00 | `IMPLEMENTED_UNVERIFIED` | #367 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #375 | feat(audit): Risikoklassen-Aenderung als Audit-Event publizieren (Folge aus #373) | 2026-05-29T19:50:15+02:00 | `IMPLEMENTED_UNVERIFIED` | #374 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #388 | fix: doppelte ACVerified/ACFailed-Event-Klassen + doppelte Dict-Keys (F811/F601) | 2026-05-31T18:12:05+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #390 | feat(observability): Polling-Backfill fuer SCM-Activity (Folge zu #230) | 2026-08-21T18:49:56+02:00 | `IMPLEMENTED_UNVERIFIED` | #450 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #399 | design(eval): Freigabeautorität an commitgebundene Gates binden; Score auf Telemetrie zurückstufen | 2026-08-28T18:48:52+02:00 | `IMPLEMENTED_UNVERIFIED` | #593, #590, #591, #592 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #402 | feat(installer): Fresh-Environment-Installer — CLI-Wizard + Dashboard + Deployment | 2026-08-21T20:25:15+02:00 | `IMPLEMENTED_UNVERIFIED` | #452, #465 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #413 | fix: Versions-Inkonsistenz — samuel/__init__.py (0.1.0) vs. pyproject.toml (2.0.0-alpha) | 2026-08-21T18:49:57+02:00 | `IMPLEMENTED_UNVERIFIED` | #412, #443 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #414 | ich möchte im Dashboard einen Hell mode haben | 2026-08-21T18:49:57+02:00 | `IMPLEMENTED_UNVERIFIED` | #447 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #415 | Blockierte/fehlgeschlagene Pläne hinterlassen keinen Grund im Issue | 2026-08-31T21:00:23+02:00 | `IMPLEMENTED_UNVERIFIED` | #708 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #416 | Kein Plan-Freigabe-Schritt: Plan wird verworfen, bevor der Mensch ihn sieht | 2026-08-21T20:47:32+02:00 | `IMPLEMENTED_UNVERIFIED` | #445, #469 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #417 | AC-Validierung prüft gegen noch nicht existierenden Code (pattern not found im Plan-Schritt) | 2026-08-21T18:49:57+02:00 | `IMPLEMENTED_UNVERIFIED` | #445 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #418 | run ohne --self läuft still ins Leere (kein Zielsystem, keine Warnung) | 2026-08-21T20:47:32+02:00 | `IMPLEMENTED_UNVERIFIED` | #443, #469 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #419 | Dashboard-Save für LLM-Config persistiert nicht / zeigt Default statt Task-Override | 2026-08-21T20:53:03+02:00 | `IMPLEMENTED_UNVERIFIED` | #447, #471 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #420 | SIGINT: Dashboard fährt nach Ctrl+C nicht sauber runter | 2026-08-21T19:02:52+02:00 | `IMPLEMENTED_UNVERIFIED` | #446 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #421 | Dashboard-URL zeigt 0.0.0.0 statt erreichbarer IP | 2026-08-21T18:49:58+02:00 | `IMPLEMENTED_UNVERIFIED` | #446 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #423 | Branch-Protection-403 crasht Dashboard statt Panel-Fehlerisolation (+ Doctor-Hinweis) | 2026-08-21T18:49:58+02:00 | `IMPLEMENTED_UNVERIFIED` | #446 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #424 | CLI: --self muss vor dem Subcommand stehen — intuitive Reihenfolge scheitert | 2026-08-21T18:49:58+02:00 | `IMPLEMENTED_UNVERIFIED` | #443 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #425 | Reasoning-Modelle erkennen, Token-Puffer konfigurierbar, Hinweis im Dashboard | 2026-08-21T20:13:48+02:00 | `IMPLEMENTED_UNVERIFIED` | #448, #455, #462 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #426 | Falsche/irreführende Labels bei blockiertem Lauf (help wanted / status:plan statt status:failed) | 2026-08-21T18:49:58+02:00 | `IMPLEMENTED_UNVERIFIED` | #445 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #427 | Abgebrochene LLM-Calls (stop_reason: length) im Log und Dashboard deutlich markieren | 2026-08-21T18:49:58+02:00 | `IMPLEMENTED_UNVERIFIED` | #448 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #428 | LLM-Qualitätsstrategie: Benchmark-basierte Eignungswarnung pro Task | 2026-08-21T20:13:48+02:00 | `IMPLEMENTED_UNVERIFIED` | #455, #462 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #429 | Zentrale Fehler-/Diagnose-Sichtbarkeit: Debug-Tab und Fehler-im-Flow im Dashboard | 2026-08-21T19:54:53+02:00 | `IMPLEMENTED_UNVERIFIED` | #455, #460, #540 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #431 | fix(tests): Gesamtlauf kippt test_compliance_legend_endpoint — SAMUEL_API_KEY aus .env leckt in den Prozess | 2026-08-21T18:49:58+02:00 | `IMPLEMENTED_UNVERIFIED` | #440 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #432 | fix(planning): Scope-Guard erkennt nur englisches "## Out of Scope" — deutsche Ueberschriften erzeugen falsche Anker | 2026-08-21T18:49:58+02:00 | `IMPLEMENTED_UNVERIFIED` | #440 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #433 | fix(planning): SkeletonBuilder-Portvertrag verletzt — realer Plan-Kontext bleibt leer | 2026-08-21T18:49:58+02:00 | `IMPLEMENTED_UNVERIFIED` | #440 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #434 | chore(quality): Ruff-Baseline mit 54 Findings bereinigen und als Gate etablieren | 2026-08-21T20:18:27+02:00 | `IMPLEMENTED_UNVERIFIED` | #440, #463 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #435 | chore(typing): Mypy-Baseline von 1883 Fehlern schrittweise zu einem ehrlichen Gate abbauen | 2026-08-21T20:18:27+02:00 | `IMPLEMENTED_UNVERIFIED` | #453, #463 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #436 | chore(dev): Git-Identität im LXC fehlt — lokale Commits werden root zugeschrieben | 2026-08-21T18:49:59+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #437 | test(planning): ScopeCreepDetected-Vertrag gezielt abdecken und Architektur-Skip entfernen | 2026-08-21T18:49:59+02:00 | `IMPLEMENTED_UNVERIFIED` | #440 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #438 | test(architecture): obsolete v1→v2-Migrationssicherung entfernen | 2026-08-21T18:49:59+02:00 | `IMPLEMENTED_UNVERIFIED` | #440 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #439 | Samuel --help command aufräumen | 2026-08-21T18:49:59+02:00 | `IMPLEMENTED_UNVERIFIED` | #442 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #441 | ci(actions): Jobs bleiben ohne Runner dauerhaft queued | 2026-08-23T23:12:36+02:00 | `IMPLEMENTED_UNVERIFIED` | #440, #545, #566 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #444 | fix(planning): PlanRevised überschreibt old_score vor dem Audit-Event | 2026-08-21T18:49:59+02:00 | `IMPLEMENTED_UNVERIFIED` | #445 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #451 | fix(scm): Bootstrap ignoriert SCM_PROVIDER und verdrahtet GitHub als Gitea | 2026-08-21T18:49:59+02:00 | `IMPLEMENTED_UNVERIFIED` | #452 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #454 | feat(llm): Optionaler Kosten-/Überqualifiziert-Hinweis bei Modellwahl | 2026-09-19T07:11:42+02:00 | `IMPLEMENTED_UNVERIFIED` | #798 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #457 | fix(tests): simulierte Fehler gelangen in produktiven Audit-Log | 2026-08-21T21:05:59+02:00 | `IMPLEMENTED_UNVERIFIED` | #473, #540 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #458 | fix(audit): Fan-out-Sink beim Shutdown vollständig leeren | 2026-08-21T19:44:59+02:00 | `IMPLEMENTED_UNVERIFIED` | #459 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #461 | fix(dashboard): Day/Night-Routing nicht ohne Schedule als aktiv anzeigen | 2026-08-21T20:13:48+02:00 | `IMPLEMENTED_UNVERIFIED` | #462 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #464 | docs(portability): obsolete Phasen-/Handover-Anweisungen aus aktiver Doku entfernen | 2026-08-21T20:25:15+02:00 | `DOC_ONLY` | #465 | Dokumentationsscope; historischer Abschluss |
| #466 | fix(workflows): night/patch dispatchen kein Issue und Profilvertrag driftet | 2026-08-21T20:46:20+02:00 | `IMPLEMENTED_UNVERIFIED` | #469 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #467 | fix(workflows): chat/autonomous Endstufen sind wirkungslos und Review erhaelt keinen Diff | 2026-08-21T20:46:20+02:00 | `IMPLEMENTED_UNVERIFIED` | #469 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #470 | fix(config): explizites --config muss fuer alle Runtime-Consumer autoritativ sein | 2026-08-21T20:52:43+02:00 | `IMPLEMENTED_UNVERIFIED` | #471 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #472 | fix(metrics): Self-Mode-Metriken ignorieren agent.data_dir und Tests verändern Produktivdaten | 2026-08-21T21:05:59+02:00 | `IMPLEMENTED_UNVERIFIED` | #473 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #474 | fix(security): Security-Schranken sind nicht verdrahtet — Injection-Detection, Secret-Scan und Command-Safety laufen nie | 2026-08-25T11:05:41+02:00 | `IMPLEMENTED_UNVERIFIED` | #532, #533 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #475 | fix(dashboard): get_health()-Docstring verspricht Checks, die HealthCheckHandler nicht liefert | 2026-08-23T23:36:34+02:00 | `IMPLEMENTED_UNVERIFIED` | #494 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #476 | fix(packaging): pyproject deklariert 'Proprietary' statt Apache-2.0 — und es fehlt eine LICENSE-Datei | 2026-08-25T16:51:30+02:00 | `IMPLEMENTED_UNVERIFIED` | #548, #550 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #477 | fix(premium): Bootstrap-Step 7 aktiviert Premium-Module ohne Lizenzpruefung — und es gibt zwei Routing-Implementierungen | 2026-08-25T17:48:35+02:00 | `IMPLEMENTED_UNVERIFIED` | #550, #566 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #478 | Lizenzdateien erstellen für Premium | 2026-08-25T17:49:37+02:00 | `IMPLEMENTED_UNVERIFIED` | #550 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #479 | Einheitliche Produktversionierung und reproduzierbarer Release-Prozess | 2026-08-27T16:00:47+02:00 | `IMPLEMENTED_UNVERIFIED` | #561, #562, #563, #566, #565 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #480 | fix(pr-gates): Reviewer-Briefing kuendigt in jedem PR-Body den SARIF-Export an, den es laengst gibt | 2026-08-23T23:30:46+02:00 | `IMPLEMENTED_UNVERIFIED` | #493 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #481 | feat(security): Erkennungstiefe auf den urspruenglich dokumentierten Stand bringen (JWT, AKIA, PEM, Unicode, Echo-Check) | 2026-08-25T12:19:30+02:00 | `IMPLEMENTED_UNVERIFIED` | #532, #533, #535, #543 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #483 | feat(ac): Gezielte pytest-Node-IDs statt -k-Namenssuche (urspruenglich als [PYTEST] dokumentiert) | 2026-08-23T23:31:23+02:00 | `IMPLEMENTED_UNVERIFIED` | #495 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #484 | feat(pr-gates): Gate-10-Schwelle konfigurierbar machen (aktuell hartkodiert 0.6) | 2026-08-23T23:31:40+02:00 | `IMPLEMENTED_UNVERIFIED` | #496 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #485 | analyse: Kleinfunde aus der Doku-Ueberarbeitung — Duplikate, Hartkodierungen, Scoring-Semantik, Altlasten | 2026-08-30T00:09:07+02:00 | `IMPLEMENTED_UNVERIFIED` | #656, #535, #574, #576, #512 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #486 | fix(privacy): Drittland-Transfer-Check uebergeht drei Provider — gemini/openrouter fehlen, 'anthropic' statt 'claude' | 2026-08-23T23:36:41+02:00 | `IMPLEMENTED_UNVERIFIED` | #497 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #487 | Versionspolitik und Versionsdomänen verbindlich dokumentieren | 2026-08-25T18:00:31+02:00 | `IMPLEMENTED_UNVERIFIED` | #552, #562, #563, #565 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #488 | Produktversion aus einer einzigen Quelle ableiten | 2026-08-26T23:05:20+02:00 | `IMPLEMENTED_UNVERIFIED` | #553, #562, #563, #565 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #489 | Versionsanzeige in CLI, Dashboard und Dokumentation konsistent machen | 2026-08-25T18:55:34+02:00 | `IMPLEMENTED_UNVERIFIED` | #553, #565 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #490 | Release-Tags, Changelog und CI-Release-Gates etablieren | 2026-08-26T22:33:04+02:00 | `IMPLEMENTED_UNVERIFIED` | #560, #561, #562, #563, #565 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #492 | ci(security): pip-audit gegen vorübergehende DNS-/Transportfehler robust machen | 2026-08-23T23:40:07+02:00 | `IMPLEMENTED_UNVERIFIED` | #499, #566 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #498 | fix(privacy): transfer_warning=false wird geladen, aber nicht ausgewertet | 2026-08-23T23:42:47+02:00 | `IMPLEMENTED_UNVERIFIED` | #500 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #501 | refactor(gates): Gate-Bezeichnungen aus gemeinsamer Core-Quelle liefern | 2026-08-25T16:36:10+02:00 | `IMPLEMENTED_UNVERIFIED` | #510, #547 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #502 | docs(config): Zuständigkeit der drei LLM-Konfigurationsdateien eindeutig festlegen | 2026-08-24T09:40:28+02:00 | `DOC_ONLY` | #509 | Dokumentationsscope; historischer Abschluss |
| #503 | fix(pr-gates): Gate 7 aus vollständiger Path-Risk-Konfiguration ableiten | 2026-08-24T09:37:01+02:00 | `IMPLEMENTED_UNVERIFIED` | #511 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #504 | refactor(config): ungenutztes EvalSchema.criteria kompatibel deprecaten | 2026-08-23T23:57:04+02:00 | `IMPLEMENTED_UNVERIFIED` | #512 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #505 | fix(config): wirkungsloses CONTEXT_DIR aus Beispiel und Installationsdoku entfernen | 2026-08-23T23:55:46+02:00 | `IMPLEMENTED_UNVERIFIED` | #507 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #506 | docs: historische V2.1-Gap-Analyse konsistent archivieren | 2026-08-24T09:36:49+02:00 | `DOC_ONLY` | #508 | Dokumentationsscope; historischer Abschluss |
| #513 | docs: technische Beschreibungen auf Datum und Commit statt Phase referenzieren | 2026-08-25T16:30:33+02:00 | `DOC_ONLY` | #525, #546 | Dokumentationsscope; historischer Abschluss |
| #514 | analyse(workflow): MANUAL-Akzeptanzkriterien in Self-Parity eindeutig behandeln | 2026-08-25T13:48:10+02:00 | `IMPLEMENTED_UNVERIFIED` | #537, #541, #542 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #515 | feat(core): unveränderlichen Prüfgegenstand für Gates und Evidence definieren | 2026-08-24T15:10:36+02:00 | `IMPLEMENTED_UNVERIFIED` | #527, #526, #536, #542, #543 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #516 | fix(pr-gates): PR-Erstellungsfehler dürfen keinen PRCreated-Erfolg erzeugen | 2026-08-24T14:02:08+02:00 | `IMPLEMENTED_UNVERIFIED` | #522, #523, #525, #526, #527 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #517 | Capability-/Wirksamkeitsmatrix als Release-Gate etablieren | 2026-08-25T10:19:10+02:00 | `IMPLEMENTED_UNVERIFIED` | #543, #545, #546 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #518 | Quality-Evidence und Workflow-Verdrahtung ehrlich vereinheitlichen | 2026-08-25T12:56:29+02:00 | `IMPLEMENTED_UNVERIFIED` | #536 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #519 | Gate 11/12 an commitgebundene Acceptance-Evidence binden | 2026-08-25T15:13:09+02:00 | `IMPLEMENTED_UNVERIFIED` | #534, #537, #542, #543 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #520 | Evidence-Ingest: realen Gitea-Shadow-/Advisory-Pfad über schmale Evidence-Grenze integrieren | 2026-09-18T18:24:19+02:00 | `IMPLEMENTED_UNVERIFIED` | #790 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #524 | docs(process): Dokumentationskonsistenz als Pflichtkriterium jeder Issue-Abnahme | 2026-08-24T13:59:59+02:00 | `DOC_ONLY` | #525, #522 | Dokumentationsscope; historischer Abschluss |
| #528 | security(scm): normale Direkt-Pushes auf main serverseitig blockieren | 2026-08-25T16:20:45+02:00 | `IMPLEMENTED_UNVERIFIED` | #545 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #529 | feat(scope): Contract-Scope an den EvaluationSubject binden | 2026-08-25T15:55:28+02:00 | `IMPLEMENTED_UNVERIFIED` | #542, #543, #544 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #538 | fix(llm): ManualAdapter darf partielle Response-Datei nicht vorzeitig lesen | 2026-08-25T14:36:35+02:00 | `IMPLEMENTED_UNVERIFIED` | #541 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #539 | fix(dashboard): unmaskierter Zeilenumbruch bricht gesamtes Frontend-JavaScript | 2026-08-25T14:21:58+02:00 | `IMPLEMENTED_UNVERIFIED` | #540 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #551 | ci(runner): Basisimage-Pull reproduzierbar und registry-ausfallsicher machen | 2026-08-27T15:29:54+02:00 | `IMPLEMENTED_UNVERIFIED` | #550, #565, #566 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #555 | Container-Releases digest- und lockgebunden veröffentlichen | 2026-08-27T17:44:16+02:00 | `IMPLEMENTED_UNVERIFIED` | #568, #569 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #557 | ci(network): Runner–Gitea-Fetchpfad begrenzen und belastbar nachweisen | 2026-08-27T12:33:17+02:00 | `IMPLEMENTED_UNVERIFIED` | #564 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #572 | docs(governance): Laufzeitdokumentation quellgebunden generieren und Drift fail-closed prüfen | 2026-08-28T12:40:12+02:00 | `DOC_ONLY` | #574 | Dokumentationsscope; historischer Abschluss |
| #573 | docs(architecture): Semaphore-Freigabe an synchronen Watch-Handler angleichen | 2026-08-28T12:22:40+02:00 | `DOC_ONLY` | #574 | Dokumentationsscope; historischer Abschluss |
| #577 | ops(eval): gebundene Rollout-Evidence für #399 erfassen und Legacy-Auslauf belegen | 2026-08-28T17:30:03+02:00 | `IMPLEMENTED_UNVERIFIED` | #576, #590, #591, #584, #586 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #578 | bug(dashboard): CreatePR-Dispatch und Nicht-Heilbarkeit werden als erfolgreiche/fehlgeschlagene Stages missdeutet | 2026-08-28T21:03:41+02:00 | `IMPLEMENTED_UNVERIFIED` | #597 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #579 | bug(config): SAMUEL_GATES_PROFILE kann atomaren Autoritätsmodus in einen Mischzustand versetzen | 2026-08-28T17:02:30+02:00 | `IMPLEMENTED_UNVERIFIED` | #590 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #580 | bug(release): #399-Rollout-Gate validiert nur Fallnamen und beliebige Evidence-Strings | 2026-08-28T18:02:12+02:00 | `IMPLEMENTED_UNVERIFIED` | #592 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #581 | bug(healing): automatische AC-Fehler liefern keine für Bound-Healing klassifizierbare Evidence | 2026-08-28T16:07:17+02:00 | `IMPLEMENTED_UNVERIFIED` | #584 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #582 | bug(planning): autonome Pläne behaupten menschliche Freigabewartezeit und publizieren falsches awaiting_approval | 2026-08-29T09:05:27+02:00 | `IMPLEMENTED_UNVERIFIED` | #611 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #583 | security(cli): dokumentierter python -m-Aufruf kann im Zielrepository ein fremdes samuel-Paket laden | 2026-08-28T20:01:27+02:00 | `IMPLEMENTED_UNVERIFIED` | #594 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #585 | bug(manual-llm): Request-Datei wird vor vollständigem JSON sichtbar und erzeugt Consumer-Race | 2026-08-28T15:37:24+02:00 | `IMPLEMENTED_UNVERIFIED` | #584 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #587 | bug(labels): erfolgreich geheilter PR behält gleichzeitig status:failed und status:wip | 2026-08-28T20:25:55+02:00 | `IMPLEMENTED_UNVERIFIED` | #595 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #588 | bug(implementation): Antwort ohne parsbare Patches endet als WorkflowBlocked(reason=complete) | 2026-08-28T21:24:20+02:00 | `IMPLEMENTED_UNVERIFIED` | #599 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #589 | bug(dashboard): seriengebundene Quality-Zeile zählt LLM-Calls aus anderen Score-Serien | 2026-08-28T17:23:02+02:00 | `IMPLEMENTED_UNVERIFIED` | #591 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #596 | bug(docs): globaler Quelldigest erfasst CHANGELOG.md trotz aktivem Review-Inventar nicht | 2026-08-29T08:51:13+02:00 | `IMPLEMENTED_UNVERIFIED` | #610 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #598 | bug(implementation): Token-Truncation kann angewandte Teilpatches im Working Tree zurücklassen | 2026-08-29T07:20:34+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #600 | security(implementation): LLM-Patchziele können project_root per Traversal oder absolutem Pfad verlassen | 2026-08-29T07:44:57+02:00 | `IMPLEMENTED_UNVERIFIED` | #604 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #601 | bug(implementation): abgelehnter JSON-Patch kann Datei trotzdem ungültig verändern | 2026-08-29T08:21:36+02:00 | `IMPLEMENTED_UNVERIFIED` | #607 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #603 | security(implementation): LLM-Patches können lokale Git-Control-Plane innerhalb project_root verändern | 2026-08-29T08:03:58+02:00 | `IMPLEMENTED_UNVERIFIED` | #605 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #606 | bug(implementation): Python-WRITE umgeht AST-Validierung und meldet ungültigen Code als Erfolg | 2026-08-29T08:39:32+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #609 | Funktions sammel request | 2026-08-30T00:41:28+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #612 | security(ac-verification): Test-Runner-Policy aus Control Plane statt Candidate auflösen | 2026-08-29T10:52:23+02:00 | `IMPLEMENTED_UNVERIFIED` | #615 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #613 | security(ac-verification): Candidate-Prozesse mit steriler Environment-Allowlist starten | 2026-08-29T11:21:44+02:00 | `IMPLEMENTED_UNVERIFIED` | #616 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #614 | fix(watch): wirkungslose Parallelitätskonfiguration und irreführenden Semaphore-Test korrigieren | 2026-08-29T11:42:54+02:00 | `IMPLEMENTED_UNVERIFIED` | #617 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #618 | design(workspaces): gemeinsamen Worktree-Manager für Run- und Verifikationsprofile entscheiden | 2026-08-29T16:32:57+02:00 | `IMPLEMENTED_UNVERIFIED` | #632 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #619 | design(security): Candidate-Ausführung mit echter Prozesssandbox begrenzen | 2026-08-30T21:49:55+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #620 | design(pr-gates): statische Preflight-Gates vor Candidate-Ausführung und expliziten Skip-Zustand einführen | 2026-08-29T23:46:45+02:00 | `IMPLEMENTED_UNVERIFIED` | #652, #654 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #625 | feat(state): versionierte SQLite-Grundlage und Diagnose bereitstellen | 2026-08-29T13:17:27+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #627 | feat(state): gebundene Beobachtungen und Run-Projektion nach SQLite migrieren | 2026-08-29T14:07:41+02:00 | `IMPLEMENTED_UNVERIFIED` | #626 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #629 | feat(state): Authority-State, Healing-Claims und Operationsjournal in SQLite migrieren | 2026-08-29T15:23:39+02:00 | `IMPLEMENTED_UNVERIFIED` | #630, #631 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #633 | feat(resume): gebundene Finalisierung nach Prozessneustart fortsetzen (ADR-0482 Stufe 4) | 2026-08-29T18:09:37+02:00 | `IMPLEMENTED_UNVERIFIED` | #632, #634 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #635 | epic(docs): internes quellgebundenes Entwickler-Wiki schrittweise aufbauen | 2026-09-02T00:51:44+02:00 | `IMPLEMENTED_UNVERIFIED` | #638, #641, #644, #662, #719 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #637 | docs(wiki): Quellen- und Informationsarchitektur des Piloten festlegen (#635 P0) | 2026-08-29T19:07:45+02:00 | `DOC_ONLY` | #638 | Dokumentationsscope; historischer Abschluss |
| #640 | docs(wiki): deterministischen Offline-Renderer und Build-Receipt liefern (#635 P1) | 2026-08-29T19:41:28+02:00 | `DOC_ONLY` | #638, #641 | Dokumentationsscope; historischer Abschluss |
| #642 | docs: wahrheitsgebundenes S.A.M.U.E.L.-Manifest veröffentlichen | 2026-08-30T01:48:17+02:00 | `DOC_ONLY` | #663 | Dokumentationsscope; historischer Abschluss |
| #643 | docs(wiki): lokale Projektion unter /wiki materialisieren und Publisher neutral halten | 2026-08-29T20:15:32+02:00 | `DOC_ONLY` | #644 | Dokumentationsscope; historischer Abschluss |
| #645 | docs(wiki): providerneutralen Git-Wiki-Publisher liefern und Gitea publizieren (#635 P3) | 2026-08-29T21:10:13+02:00 | `DOC_ONLY` | #646 | Dokumentationsscope; historischer Abschluss |
| #649 | docs(wiki): eigenständige quellgebundene Kerninhalte statt reiner Linkindexe liefern (#635 P2.1) | 2026-08-29T22:17:10+02:00 | `DOC_ONLY` | #651, #650 | Dokumentationsscope; historischer Abschluss |
| #653 | rollout(#620): reale Preflight-/Skip-/Healing-Evidence gegen isolierte Fixture | 2026-08-29T23:39:52+02:00 | `IMPLEMENTED_UNVERIFIED` | #654 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #655 | design(planning): Retry-Endzustand bei overall_pass=false festlegen | 2026-08-30T09:58:10+02:00 | `IMPLEMENTED_UNVERIFIED` | #664 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #659 | design(review): optionalen unabhängigen LLM-Codegegencheck begrenzen und einordnen | 2026-08-30T21:49:55+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #661 | feat(docs): Wiki-Impactbericht auf gebundene Seiten und Content-Blöcke erweitern | 2026-08-30T01:21:36+02:00 | `IMPLEMENTED_UNVERIFIED` | #662 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #666 | feat(state): Restore exklusiv über neue Autoritätslinie reconciliieren (ADR-0482 Stufe 5a) | 2026-08-30T12:41:19+02:00 | `IMPLEMENTED_UNVERIFIED` | #665, #669, #670 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #667 | feat(retention): Katalog, Dry-Run, Feldklassifikation und Replay liefern (ADR-0482 Stufe 5b) | 2026-08-30T14:26:31+02:00 | `IMPLEMENTED_UNVERIFIED` | #665, #669, #671 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #672 | bug(state): terminale PlanBlocked-Läufe bleiben als Run-Projektion running | 2026-08-30T18:34:03+02:00 | `IMPLEMENTED_UNVERIFIED` | #677, #676 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #673 | feat(retention): operatorgeführtes 5c-Ausführungsfundament deaktiviert liefern | 2026-08-30T15:36:33+02:00 | `IMPLEMENTED_UNVERIFIED` | #674 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #675 | bug(llm): LLM-Telemetrie an die Workflow-Korrelation binden | 2026-08-30T17:30:20+02:00 | `IMPLEMENTED_UNVERIFIED` | #676 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #678 | design(core): Produktgrenze, Standard-Integrationsprofil und Driftregeln verbindlich machen | 2026-08-30T22:12:27+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #681 | docs(governance): Manifest um Autoritäts-, Evidence- und Driftgrenzen präzisieren | 2026-08-30T22:45:56+02:00 | `DOC_ONLY` | — | Dokumentationsscope; historischer Abschluss |
| #683 | release: v2.0.0a5 für unabhängige D0-Installation veröffentlichen | 2026-08-31T10:07:07+02:00 | `IMPLEMENTED_UNVERIFIED` | #684, #686 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #685 | fix(container): Release-Smoke stellt keinen schreibbaren Workspace-Bind-Mount bereit | 2026-08-31T11:02:29+02:00 | `IMPLEMENTED_UNVERIFIED` | #686 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #687 | release: v2.0.0a6 nach #685 für unabhängige D0-Installation veröffentlichen | 2026-08-31T13:20:32+02:00 | `IMPLEMENTED_UNVERIFIED` | #686, #688 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #689 | bug(audit): Mehrprozesszugriffe brechen die HMAC-JSONL-Kette im Containerbetrieb | 2026-08-31T17:09:27+02:00 | `IMPLEMENTED_UNVERIFIED` | #699, #702 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #690 | bug(health): effektive LLM-Routen ohne Credentials oder verfügbare Modelle nicht grün melden | 2026-09-02T19:44:24+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #692 | ux(security): Tamper-, Integritäts- und Testereignisse nachvollziehbar unterscheiden | 2026-09-02T00:45:20+02:00 | `IMPLEMENTED_UNVERIFIED` | #724 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #695 | bug(planning): ungültigen Planvertrag vor SCM-Side-Effects atomar blockieren | 2026-08-31T20:30:34+02:00 | `IMPLEMENTED_UNVERIFIED` | #707 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #696 | bug(watch): fehlgeschlagene Commands nicht als planned und Exit 0 melden | 2026-08-31T19:19:37+02:00 | `IMPLEMENTED_UNVERIFIED` | #705 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #697 | bug(observability): abgefangene Bus-Exceptions als gebundene Diagnostik sichtbar machen | 2026-09-02T00:42:43+02:00 | `IMPLEMENTED_UNVERIFIED` | #724 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #698 | bug(llm): OpenAI-kompatible Fehlerantworten ohne choices typisiert behandeln | 2026-08-31T19:45:36+02:00 | `IMPLEMENTED_UNVERIFIED` | #700, #702 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #701 | bug(llm): native Providerantworten einheitlich fail-closed normalisieren | 2026-09-17T19:49:12+02:00 | `IMPLEMENTED_UNVERIFIED` | #700, #724, #782, #783 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #706 | investigation(update): gemischte Produktstände und Installations-Overlays verhindern | 2026-09-02T18:53:39+02:00 | `IMPLEMENTED_UNVERIFIED` | #705, #753 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #709 | bug(planning): kanonischen Scope im Planner-Prompt parsergenau vorgeben | 2026-08-31T22:05:50+02:00 | `IMPLEMENTED_UNVERIFIED` | #710 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #711 | bug(dashboard): gruppierte Probleme verlieren die aktuelle Issue-Zuordnung | 2026-09-02T00:34:44+02:00 | `IMPLEMENTED_UNVERIFIED` | #724 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #712 | bug(dashboard): LLM-Retry-Diagnosen werden als eigene Workflow-Runs gezählt | 2026-09-02T00:40:51+02:00 | `IMPLEMENTED_UNVERIFIED` | #724 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #713 | bug(ac): GREP-Pfadsuffix wird ignoriert und prüft unbeabsichtigt repositoryweit | 2026-09-01T23:00:37+02:00 | `IMPLEMENTED_UNVERIFIED` | #748 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #714 | bug(planning): Skeleton und Plan an aktuellen SCM-Base-Commit binden | 2026-09-17T16:25:29+02:00 | `IMPLEMENTED_UNVERIFIED` | #725, #728, #780 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #715 | docs(pipeline): Gates, Kontextaufbau und Featurewirkung durchgängig erklären (#635) | 2026-09-01T08:46:40+02:00 | `DOC_ONLY` | — | Dokumentationsscope; historischer Abschluss |
| #717 | chore(housekeeping): belegte Arbeitsartefakte und ungenutzte Dependency entfernen | 2026-09-01T08:11:57+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #720 | chore(docs): lokale Arbeits-Snapshots aus Produktroot archivieren | 2026-09-01T09:04:30+02:00 | `DOC_ONLY` | — | Dokumentationsscope; historischer Abschluss |
| #722 | docs(release): a7-Stand, Qualification und Updategrenze konsistent erklären | 2026-09-01T09:37:55+02:00 | `DOC_ONLY` | — | Dokumentationsscope; historischer Abschluss |
| #727 | bug(container): veröffentlichtes Image enthält erforderliche Git-Runtime nicht | 2026-09-01T14:31:09+02:00 | `IMPLEMENTED_UNVERIFIED` | #728 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #729 | bug(worktree): privaten SCM-Fetch mit enger Credential-Delegation ermöglichen | 2026-09-01T16:09:59+02:00 | `IMPLEMENTED_UNVERIFIED` | #728, #730 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #731 | Planning: formalen Acceptance-Contract vor Blockade einmal korrigieren | 2026-09-01T16:27:45+02:00 | `IMPLEMENTED_UNVERIFIED` | #732, #730 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #733 | bug(planning): Korrekturaufruf an effektive Planning-Route binden | 2026-09-01T23:20:29+02:00 | `IMPLEMENTED_UNVERIFIED` | #734 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #735 | bug(planning): gescopte neue Dateien im Skeleton-Pre-Check zulassen | 2026-09-01T19:27:58+02:00 | `IMPLEMENTED_UNVERIFIED` | #736 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #737 | bug(approval): sichtbarer ok-Hinweis behauptet nicht eingerichtete Kommentarfreigabe | 2026-09-01T23:35:19+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #738 | bug(dashboard): synchron nachgeschriebenes IssueReady stuft geplanten Run auf ready zurück | 2026-09-01T23:53:41+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #739 | bug(git): commit-tree scheitert in frischer Referenzinstallation ohne Author-Identität | 2026-09-01T20:12:39+02:00 | `IMPLEMENTED_UNVERIFIED` | #740 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #741 | docs(install): Voraussetzungen, Accounts und Credential-Rechte vollständig inventarisieren | 2026-09-02T00:26:11+02:00 | `DOC_ONLY` | #751 | Dokumentationsscope; historischer Abschluss |
| #742 | bug(planning): Scope-Guard verwechselt Änderungsdateien mit Prosa- und Testreferenzen | 2026-09-01T21:02:19+02:00 | `IMPLEMENTED_UNVERIFIED` | #743 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #744 | bug(llm): Leerer OpenAI-Content verliert Truncation- und Budgetdiagnose | 2026-09-01T21:36:34+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #746 | bug(dashboard): Produktversion verschwindet bis zum authentifizierten Status-Load | 2026-09-01T22:03:24+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #752 | bug(api): synchron abgebrochener Command wird als HTTP 202 null bestätigt | 2026-09-02T15:22:31+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #754 | bug(ac): Planning akzeptiert vom Gate abgelehnten TEST-Dateiselektor | 2026-09-02T13:49:25+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #756 | design(ac): fehlende projektspezifische TEST-Runner-Policy vor Candidate sichtbar machen | 2026-09-02T19:43:08+02:00 | `IMPLEMENTED_UNVERIFIED` | #762 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #759 | design(release): Publisher-Rollentrennung mit persönlichem Gitea-Package-Owner auflösen | 2026-09-19T10:55:26+02:00 | `IMPLEMENTED_UNVERIFIED` | #797 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #767 | bug(approval): Re-Plan darf bestehende Freigabe nicht auf neuen Vertrag übertragen | 2026-09-17T12:47:58+02:00 | `IMPLEMENTED_UNVERIFIED` | #768, #780 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #772 | fix(workflow): abgelehnten impliziten Replan als blockierten Lauf projizieren | 2026-09-17T14:19:16+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #774 | chore(release): v2.0.0a14 für korrigierte D0-Qualification vorbereiten | 2026-09-17T14:33:11+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #776 | fix(labels): PlanReplanRejected darf aktiven Planstatus nicht zerstören | 2026-09-17T15:13:25+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #778 | chore(release): v2.0.0a15 für korrigierte D0-Qualification vorbereiten | 2026-09-17T15:28:26+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #781 | bug(llm): Per-Task-Timeout an Claude- und Ollama-Adapter durchreichen | 2026-09-17T18:14:18+02:00 | `IMPLEMENTED_UNVERIFIED` | #782 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #784 | docs(llm): D0-Plan-Score klar von Modellqualität abgrenzen | 2026-09-17T21:51:27+02:00 | `DOC_ONLY` | #785 | Dokumentationsscope; historischer Abschluss |
| #786 | bug(planning): Truncation-Kommentar darf Issue nicht als unscharf klassifizieren | 2026-09-17T22:10:11+02:00 | `IMPLEMENTED_UNVERIFIED` | #788 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #787 | docs(pipeline): a15-Qualification und Task-Tokenbudget korrekt abbilden | 2026-09-17T22:10:11+02:00 | `DOC_ONLY` | #788 | Dokumentationsscope; historischer Abschluss |
| #802 | ops(d0): Qualification-Zugang nach Instanzneustart wiederherstellen | 2026-09-19T10:55:26+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #808 | docs(status): Release-/Qualificationclaims und veröffentlichte Wiki-Projektion reconciliieren | 2026-09-21T21:13:40+02:00 | `DOC_ONLY` | #852, #853, #854 | Dokumentationsscope; historischer Abschluss |
| #814 | fix(release): unterbrochenen Create-only OCI-Publish ohne zweiten Push recovern | 2026-09-20T00:27:37+02:00 | `IMPLEMENTED_UNVERIFIED` | #818 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #816 | fix(docs): Releaseledger nach a18-Tag konsistent halten | 2026-09-20T09:40:41+02:00 | `IMPLEMENTED_UNVERIFIED` | #817 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #831 | [D0 q7] Plan-Pre-Check blockiert neue Testmethoden in autorisierten Bestandsdateien | 2026-09-20T20:12:38+02:00 | `IMPLEMENTED_UNVERIFIED` | #832 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #833 | docs(release): fehlenden a22-CHANGELOG-Eintrag ergänzen | 2026-09-20T20:35:42+02:00 | `DOC_ONLY` | — | Dokumentationsscope; historischer Abschluss |
| #835 | ops(release): Container-Smoke an Produkt-SCM-Subject binden | 2026-09-21T21:13:40+02:00 | `IMPLEMENTED_UNVERIFIED` | #852, #81 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #836 | docs(release): a23 nach fehlgeschlagenem a22-Smoke vorbereiten | 2026-09-20T21:19:20+02:00 | `DOC_ONLY` | — | Dokumentationsscope; historischer Abschluss |
| #838 | security(setup): Wizard darf Dashboard-Credential nicht ausgeben | 2026-09-21T08:06:56+02:00 | `IMPLEMENTED_UNVERIFIED` | #839 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #841 | docs(release): a24 nach Setup-Secret-Fix vorbereiten | 2026-09-21T08:24:41+02:00 | `DOC_ONLY` | — | Dokumentationsscope; historischer Abschluss |
| #855 | Acceptance-Contract-Hash driftet bei planinterner abschließender Markdown-Trennlinie | 2026-09-22T09:25:29+02:00 | `IMPLEMENTED_UNVERIFIED` | #856 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #860 | bug(planning): Planner-Ausgabeformat kann kanonischen Scope in nummerierte Prosa einschließen | 2026-09-22T11:39:18+02:00 | `IMPLEMENTED_UNVERIFIED` | #861 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #862 | Rehearsal Q10: Approval-Labelübergang entwertet gültige Humanfreigabe vor Gate 11 | 2026-09-22T12:36:34+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #863 | Rehearsal Q10: Akzeptierter Inline-Code-Pfad scheitert im Acceptance-Verifier | 2026-09-22T12:36:34+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #865 | Rehearsal Q10: Markdown-Inline-Code-Wrapper wird bei GREP nicht normalisiert | 2026-09-22T13:44:43+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #867 | bug(planning): repositoryweites GREP:NOT darf absichtlich erhaltene Out-of-Scope-Fixtures nicht als AC erzeugen | 2026-09-22T16:25:46+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #869 | Reviewbinding: Privacy-Sanitizer verändert autoritativen EvaluationSubject | 2026-09-22T19:13:46+02:00 | `IMPLEMENTED_UNVERIFIED` | #870 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #871 | Verifier verliert venv-bin bei sterilem Python-Runner-PATH | 2026-09-23T18:25:54+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #874 | Review-Systemprompt an geschlossenen Reviewcontract angleichen | 2026-09-24T07:03:05+02:00 | `IMPLEMENTED_UNVERIFIED` | #875 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #876 | Review-Prompt muss verifizierte Acceptance-Semantik eindeutig binden | 2026-09-26T00:10:18+02:00 | `IMPLEMENTED_UNVERIFIED` | #879 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #877 | Prompt-Verträge gegen aktuellen Execution- und Golden-D0-Prozess prüfen | 2026-09-24T08:55:24+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #881 | Replan-Feedback fehlt im Prompt des Ersatzplans | 2026-09-24T10:37:02+02:00 | `IMPLEMENTED_UNVERIFIED` | #882 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #884 | MANUAL-Reevaluation verliert persistierte Workflow-Budget-Admission | 2026-09-24T14:15:47+02:00 | `IMPLEMENTED_UNVERIFIED` | #126 | PR gemergt; Code-/Real-Evidence nicht neu individuell geprueft |
| #886 | [Qualification] Dashboard-/Observability-E2E-Verifikation Q00–Q16 | 2026-09-25T10:18:39+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #895 | [Authority] Gate-Fail darf gebundene Planfreigabe vor MANUAL-Reevaluation nicht widerrufen | 2026-09-25T21:08:07+02:00 | `UNKNOWN` | — | kein belastbarer aktueller Abschlussanker aus State/Titel/PR-Readback |
| #898 | docs(housekeeping): reconcile repository state and stale operator documentation | 2026-09-26T08:12:20+02:00 | `DOC_ONLY` | — | Dokumentationsscope; historischer Abschluss |
| #902 | Fix planning retry feedback and contract-aware adoption | 2026-09-26T15:51:23+02:00 | `IMPLEMENTED_UNVERIFIED` | — | Main-Merge/Regression belegt; kein neuer Real-PASS |
| #906 | bug(health): Docker probe resumes active finalization | 2026-09-28T10:45:42+02:00 | `IMPLEMENTED_UNVERIFIED` | #151 | Main-Merge/Regression belegt; kein neuer Real-PASS |
| #908 | Keep API responsive during native approval webhook without duplicate dispatch | 2026-09-28T12:17:13+02:00 | `IMPLEMENTED_UNVERIFIED` | — | Main-Merge/Regression belegt; kein neuer Real-PASS |
| #910 | fix(acceptance): required MANUAL pending waits and resumes via public watch | 2026-09-28T13:44:45+02:00 | `IMPLEMENTED_UNVERIFIED` | — | Main-Merge/Regression belegt; kein neuer Real-PASS |
| #912 | Review: erschöpfter ProviderUnavailable muss ReviewBlocked statt WorkflowAborted erzeugen | 2026-09-29T08:14:46+02:00 | `IMPLEMENTED_UNVERIFIED` | — | Main-Merge/Regression belegt; kein neuer Real-PASS |
| #913 | Resume: workspace_owned bei konkurrierendem Resume darf aktiven Issue-Status nicht vergiften | 2026-09-29T08:53:28+02:00 | `IMPLEMENTED_UNVERIFIED` | — | Main-Merge/Regression belegt; kein neuer Real-PASS |
| #916 | Planning precheck accepts unsatisfiable repository-wide GREP:NOT outside authorized mutation scope | 2026-09-29T11:13:31+02:00 | `IMPLEMENTED_UNVERIFIED` | — | Main-Merge/Regression belegt; kein neuer Real-PASS |
| #918 | Implementation/Healing: ProviderUnavailable must block instead of WorkflowAborted(internal_command_error) | 2026-09-29T11:58:55+02:00 | `IMPLEMENTED_UNVERIFIED` | — | Main-Merge/Regression belegt; kein neuer Real-PASS |

## Selektive eigene Abschlüsse — 02.10.2026

Diese Ergänzung ändert keine historische Snapshotklassifikation. Eigene
Acceptance und aktuelle native Issue-Readbacks sind an Product
`1a87ef036b6481b8486322e7ff36dacf80a3129f` gebunden.

| Issue | Klassifikation | Eigene Evidence | Grenze |
|---|---|---|---|
| #829 | `DONE` | bestehende Präzedenz/Doku, eigene vier reale Taskproben und Freeze vor Subject 1a87ef03-20261002-01; Main-Wiki publiziert und remote verifiziert | keine allgemeine Provider-/Release-/D0-Qualification |
| #892 | `DONE` | integrierter Sortierfix #893; drei Determinismusregressionen PASS am exakten Main; eigene neue Candidate-/Prestart-Bindung und zeitgültiger Start-Receipt zugeordnet | keine deterministische LLM-Ausgabe, kein aktuelles READY aus abgelaufener Evidence und kein Golden-/D0-PASS |

## Selektiver eigener Abschluss — 03.10.2026

Product/Main `2671ae6fb158469cbe79ea982a4c99e1d1728a00`, Human Merge #928;
Main-CI #1071 PASS. Die historische Snapshotklassifikation bleibt erhalten.

| Issue | Klassifikation | Eigene Evidence | Grenze |
|---|---|---|---|
| #922 | `DONE` | bestehende LLM/FileConfig um getrennte Katalog-/Benchmarkquellen ergänzt; 173 eigene gezielte Tests am PR-Head, PR-CI #1068 und Merge-Main-CI #1071 PASS; Main-Wiki publiziert und marker-/inhaltsgebunden remote verifiziert | keine reale Mirror-Verfügbarkeit, Task-Suitability oder E2E-/Golden-/D0-Qualification |
