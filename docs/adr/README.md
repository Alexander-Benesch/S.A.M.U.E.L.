# Architecture Decision Records

> Diese Datei wird durch `python tools/control_matrix.py render` aus den
> versionierten ADR-Dateien erzeugt. Akzeptierte Entscheidungen werden nicht
> still umgeschrieben, sondern durch einen neuen ADR abgelöst.

| ADR | Entscheidung | Status | Issue | Datum |
|---|---|---|---:|---|
| [`ADR-0399`](0399-score-authority.md) | Freigabeautorität an gebundene Gates, Score als Beobachtung | `accepted` | #399 | 2026-08-28 |
| [`ADR-0422`](0422-local-dashboard-identity.md) | Lokaler Dashboard-Identity-Provider und expliziter Legacy-Cutover | `accepted` | #422 | 2026-09-18 |
| [`ADR-0482`](0482-runtime-state-store.md) | Versionierter SQLite-State für Beobachtungen, Projektionen und Workflow-Autorität | `accepted` | #482 | 2026-08-29 |
| [`ADR-0583`](0583-installed-cli-entrypoint.md) | Installierter Console-Entry-Point als einzige Betriebsgrenze | `accepted` | #583 | 2026-08-28 |
| [`ADR-0618`](0618-worktree-manager.md) | Gemeinsamer Worktree-Manager mit Run- und Verifikationsprofil | `accepted` | #618 | 2026-08-29 |
| [`ADR-0619`](0619-candidate-sandbox.md) | Fail-closed Sandboxvertrag für kandidatenkontrollierte Ausführung | `superseded` | #619 | 2026-08-29 |
| [`ADR-0620`](0620-preflight-gate-state.md) | Statische Preflight-Gates und expliziter Nichtausführungszustand | `accepted` | #620 | 2026-08-29 |
| [`ADR-0635`](0635-wiki-pilot.md) | Deterministischer Wiki-Pilot auf vorhandener Dokumentations-Governance | `accepted` | #635 | 2026-08-29 |
| [`ADR-0643`](0643-repository-wiki-materialization.md) | Repository-lokale Wiki-Materialisierung und providerneutrale Publikation | `accepted` | #643 | 2026-08-29 |
| [`ADR-0649`](0649-wiki-content-projection.md) | Einquellige Content-Blöcke für eigenständig lesbare Wiki-Seiten | `accepted` | #649 | 2026-08-29 |
| [`ADR-0678`](0678-product-boundary-and-integration-profile.md) | Produktgrenze, Standard-Integrationsprofil und Referenzbetrieb | `accepted` | #678 | 2026-08-30 |
| [`ADR-0693`](0693-health-readiness-qualification.md) | Technische Gesundheit, Betriebsbereitschaft und Qualification getrennt projizieren | `accepted` | #693 | 2026-09-18 |
| [`ADR-0706`](0706-atomic-release-layout.md) | Unveränderliche lokale Releases mit atomarem Aktivierungszeiger | `accepted` | #706 | 2026-09-02 |

## Quellenbindung

- `glob:docs/adr/[0-9]*.md`
- Vertrag: `docs/capabilities/document-contract.json::adr-index`
