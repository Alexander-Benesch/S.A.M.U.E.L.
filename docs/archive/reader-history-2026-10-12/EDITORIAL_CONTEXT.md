# Historische Redaktionskontexte — 12.10.2026

HISTORICAL / AUDIT_EVIDENCE. Unveränderte Auszüge aus dem integrierten
Main `166852e32edf278f2feb273d73a07b22b496a2a6`. Sie erhalten frühere Release- und
Fehlerbeschreibungen; aktuelle Regeln und Funktionen stehen in den verlinkten
aktiven Fachquellen. Historische Rechtsaussagen sind damaliger Dokumenttext,
keine heutige rechtliche Einordnung. Keine historische Evidence wird überschrieben.

## Security release statuses

Quelle: `SECURITY.md`, Main `166852e32edf278f2feb273d73a07b22b496a2a6`.

| `2.0.0a28` | Historical published alpha with retained independent installation evidence and the slow-host readiness timeout finding; no support promise |
| `2.0.0a27` | Historical published alpha with independent installation evidence, without the #978 toolchain/Doctor path; no support promise |
| `2.0.0a26` | Historical published alpha; OCI clean-install findings in #970; legacy acceptance deferred to #962; no support promise |
| `2.0.0a25` | Superseded published alpha candidate; Golden-D0 and capability qualifications not run; no support promise |
| `2.0.0a24` | Superseded published alpha candidate; D0 run incomplete and no support promise |
| `2.0.0a23` | Product-source OCI publish and Compose smoke proven; complete Gitea package publish not proven; no support promise |
| `2.0.0a22` | Failed publish attempt with incorrect OCI source binding; no support promise |
| `2.0.0a20` | Failed publish attempt with incorrect OCI source binding; no support promise |
| `2.0.0a19` | Superseded published alpha candidate; D0 failed and no support promise |
| `2.0.0a17` | Superseded published alpha candidate; no support promise |
| `2.0.0a15` | Historical alpha with retained partial evidence; no complete functional/D0 pass and no current installation recommendation |
| `2.0.0a14` | Superseded qualification candidate after D0 label-projection finding #776; no support promise |
| `2.0.0a13` | Superseded qualification candidate after D0 run-projection finding #772; no support promise |
| `2.0.0a12` | Unreleased after its first required Compose smoke failed; no support promise |
| `2.0.0a11` | Published but failed D0 because approval could drift to a newly generated plan (#767); no support promise |
| `2.0.0a7` | Superseded supported alpha; no separate backport promise |
| `2.0.0a10` | Superseded qualification candidate after the contradictory runner prompt was found; no support promise |
| `2.0.0a9` | Superseded qualification candidate after D0 findings #690 and #756; no support promise |
| `2.0.0a8` | Published but failed D0 because the image lacked required Git runtime; no support promise |
| `2.0.0a6` and earlier published alphas | Superseded; no separate backport promise |
| `v2.0.0a5` | Unreleased audit tag/image after failed required Compose smoke; no support promise |
| `v2.0.0a1` | Failed release-gate audit tag; no published release or support promise |


## Planning workflow loading

Quelle: `technische Beschreibungen/pipeline_planning.md`, Main `166852e32edf278f2feb273d73a07b22b496a2a6`.

**Achtung — Loop-Bug-Fix (Phase 14.7):**
Früher wurde der Workflow doppelt geladen (bootstrap + CLI) → `PlanValidated` triggerte 2× Implement. Seit Phase 14.7: nur ein Loading-Punkt, Flag via `SAMUEL_WORKFLOW_OVERRIDE` env var.

## Implementation keyword matching

Quelle: `technische Beschreibungen/pipeline_issue_to_llm.md`, Main `166852e32edf278f2feb273d73a07b22b496a2a6`.

(`context_builder.py:448`). Ohne `\b` würde "cli" auch "click" treffen —
früher eine massive Rauschquelle bei HTML-Klassennamen.

## AI Act migration

Quelle: `docs/AI_ACT_COMPLIANCE.md`, Main `166852e32edf278f2feb273d73a07b22b496a2a6`.

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
Default `limited_risk`) abgeleitet — siehe §1.3. Der technische Self-Mode-Default bleibt
unverändert: Das Mapping zeigt Art. 50 als `required`, Art. 12–15 als
`voluntary`. Diese Labels sind keine rechtliche Konformitätsentscheidung.

## Provider output limit

Quelle: `docs/agents/AGENT_CONFIGURATION_REFERENCE.md`, Main `166852e32edf278f2feb273d73a07b22b496a2a6`.

werden; besonders die historische Implementation-Truncation bei 8192 Tokens
ist kein durch Konfiguration allein erledigter Befund (#822/#859).
