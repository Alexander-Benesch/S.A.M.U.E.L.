# Rehearsal Repository Cleanup

Readback: 2026-09-29. Die Product-Bot-Rolle erhielt 404; die getrennte,
berechtigte Demo-Rolle bestaetigte danach alle fuenf Repositories. 404 war
eine Sichtbarkeitsgrenze, kein Existenzbeweis. Ihre Git-Mirrors und
API-Exporte wurden im privaten USB-Backup erzeugt. Der gemeinsame
Default-Head der fuenf Repositories war
`7251f29fddeff5c089a622e1d38c24f7b336fb22`; die jeweilige
Product-/Versuchsbindung steht getrennt in den Issues und Receipts und darf
nicht allein aus dem Repositorynamen abgeleitet werden.

| Repository | Demo-Rollen-Readback | Evidence / Entscheidung |
|---|---|---|
| `samuel-r24-next-943b9eb-20260929` | 3 Branches; Issues #1 und #2 offen; kein PR | **KEEP_EVIDENCE**; offene Subjects, Transfer nicht vollstaendig belegt |
| `samuel-r24-retry-2141d360-20260928` | 3 Branches; Issues #1/#2 offen; PR #3 offen | **KEEP_EVIDENCE**; offener PR schliesst Delete aus |
| `samuel-clean-e2e-v2-2141d360-20260928` | 1 Branch; Issues #1/#2 offen; kein PR | **KEEP_EVIDENCE**; Unique-Evidence-Transfer nicht bewiesen |
| `samuel-clean-e2e-2141d360-20260928` | 1 Branch; Issue #1 offen; kein PR | **KEEP_EVIDENCE**; Unique-Evidence-Transfer nicht bewiesen |
| `samuel-r24-next-41340e7-20260929-03` | 2 Branches; Issues #1/#2/#3 offen; kein PR | **KEEP_EVIDENCE**; juengste Positiv-E2E-Fehlerevidence |

Ein API-/Git-Mirror ist nur ein Baustein des privaten Backups. Vor einer
spaeteren Loeschung muessen zusaetzlich vollstaendige Attachments/LFS,
CI-Artefakte, Webhook-/Approval-/Candidate-Receipts und Zielreferenzen
verifiziert werden. `backup_complete`, `unique_evidence_transferred`,
`no_open_pr_needed` und `not_latest_required_evidence` sind derzeit nicht
gemeinsam erfuellt. **Kein Repository wurde geloescht.** Product, Demo,
Pipeline und Wiki sind nie disposable Cleanup-Ziele.
