# Housekeeping Action Matrix

Stand: 2026-09-26. `CI` bezeichnet die zum gebundenen Head gelesene CI; `n/a` bedeutet, dass in diesem Housekeeping keine neue Codewirkung geprüft wurde.

| ID | TYPE | CURRENT_STATE | EVIDENCE | ACTION | ACTION_TAKEN | PR | CI | NEXT_BOUNDARY |
|---|---|---|---|---|---|---|---|---|
| REPO-PRODUCT | repository | main `401ffae…` | Run #999 | local sync | fast-forward erledigt | – | success | keine |
| REPO-DEMO | repository | main `d4b42b7…` | Run #993, PR #138 | erhalten | read-only verifiziert | – | success | getrennte Demo-/Operatorrolle |
| PR-857 | product PR | release-bound, conflict, 37 behind | Head `06f72ee…`, Run #935 | update on current main later | unverändert | #857 | old head success | Releaseauftrag + Human Merge |
| DPR-101 | demo PR | superseded | spätere #129/#133/#137, Seedreset #138 | close after readback | unverändert | #101 | success | Maintainer close |
| DPR-107 | demo PR | superseded | wie DPR-101 | close after readback | unverändert | #107 | success | Maintainer close |
| DPR-109 | demo PR | superseded | wie DPR-101 | close after readback | unverändert | #109 | success | Maintainer close |
| DPR-111 | demo PR | superseded failed evidence | Attempt 18, späterer Seedreset | preserve then close | unverändert | #111 | success | Maintainer close |
| DPR-120 | demo PR | superseded | spätere Merges/Seedreset | close after readback | unverändert | #120 | success | Maintainer close |
| DPR-126 | demo PR | superseded | spätere Merges/Seedreset | close after readback | unverändert | #126 | success | Maintainer close |
| ISS-894 | issue/K | Body unvollständig | abrupt nach ownership finding, 0 AC | vervollständigen | dokumentiert | – | n/a | Evidence/AC |
| ISS-892 | issue/B | technisch implementiert | PR #893/CI | real requalifizieren | offen gelassen | #893 | success | Candidate/prestart |
| ISS-891 | issue/C | Dashboardteil vorhanden | handler/UI/tests | taskweise Projektion ergänzen | dokumentiert | – | n/a | normaler Change |
| ISS-890 | issue/C | Runprojektion teilweise | correlation/run/issue | Root Cause/next action ergänzen | dokumentiert | – | n/a | normaler Change |
| ISS-889 | issue/B | Setup/Freeze implementiert | Code/Tests/Docs | Operator-Lifecycle real | offen gelassen | – | n/a | Real Acceptance |
| ISS-888 | issue/H | bewusst post-Golden | Bodyabhängigkeiten | später bearbeiten | offen gelassen | – | n/a | Golden+a26+D0 |
| ISS-883 | issue/D | gültige Redaction-Lücke | aktuelle Codeprüfung | Inputidentität/Replay | offen gelassen | – | n/a | Implementation |
| ISS-880 | issue/C | Authority stark, UX offen | #895/PR #896 getrennt | MANUAL-UX abschließen | offen gelassen | – | n/a | Implementation/Real UX |
| ISS-878 | issue/C | Resolver vorhanden | #877 erfüllt | Profilcontract/Smokes | offen gelassen | – | n/a | Qualification |
| ISS-876 | issue/A | alle AC erfüllt | PR #879, CI, Audit | schließen | Kommentar #44494, geschlossen | #879 | success | erledigt |
| ISS-873 | issue/D | CRA-AC offen | keine aktuelle Definition | bearbeiten | offen gelassen | – | n/a | Design/Implementation |
| ISS-859 | issue/D | Golden pausiert | Attempt-36-Receipt | Status reconciliieren | Kommentar #44498 | – | n/a | nächste gezielte Golden-Session |
| ISS-847 | issue/B | CLI-Fix integriert | PR #849 | reale installierte Abnahme | offen gelassen | #849 | success | Real Acceptance |
| ISS-846 | issue/B | Authority-Fix integriert | PR #848 | reale SCM-Abnahme | offen gelassen | #848 | success | Real Acceptance |
| ISS-845 | issue/B | Transportgrenzen vorhanden | Tests | frischer Origin/Base | offen gelassen | – | n/a | Golden Preparation |
| ISS-844 | issue/C | F04-P fertig | PR #850 | F04-O/Chainprobe | offen gelassen | #850 | success | D0 writer/real probe |
| ISS-843 | issue/C | Validierung teilweise | Setup/Auth | Bootstrapquellen schließen | offen gelassen | – | n/a | Golden Preparation |
| ISS-840 | issue/C | Coordination aktiv | a25/PR #858 + Childissues | als Provenienzträger halten | offen gelassen | – | n/a | Child exits |
| ISS-830 | issue/B | Dashboard integriert | API/Auth/Health tests | echter Run/Q16 | offen gelassen | – | n/a | Golden Subject |
| ISS-829 | issue/B | Docs integriert | PR #852/Demo #81 | Routes/Freeze real | offen gelassen | #852 | success | Golden Preparation |
| ISS-828 | issue/B | Diagnose integriert | PR #851 | externer Applyfall | offen gelassen | #851 | success | Real provider |
| ISS-823 | issue/I | Bindmount-Fix integriert | PR #824 + tests | releasegebundene Kette | offen gelassen | – | n/a | Release/Qualification |
| ISS-822 | issue/B | Routing da, Defaultchange revertiert | geschlossener PR #825 | Routeprobe/Freeze | offen gelassen | #825 | n/a | Golden Preparation |
| ISS-821 | issue/C | lokale Teilinfrastruktur | Index/Proben | Restentries/-proben | offen gelassen | – | n/a | Operator infra |
| ISS-812 | issue/G | a18-Changelog fertig | PR #813 | Receipt/Status zuordnen | offen gelassen | #813 | success | Docs evidence |
| ISS-811 | issue/D | 0/4 AC | Body/Code/Docs | Entscheidung | markiert | – | n/a | HUMAN_DECISION_REQUIRED |
| ISS-694 | issue/B | Checkcode integriert | PR #789 | echte Contextproben | offen gelassen | #789 | success | Operator qualification |
| ISS-693 | issue/B | Health integriert | PR #795/#807 | reale Matrix | offen gelassen | – | success | Real qualification |
| ISS-691 | issue/B | D08 integriert | PR #793/#810/#815/#824 | Persistenzkette real | offen gelassen | – | success | Release qualification |
| ISS-679 | issue/B | Providerpfad integriert | PR #792/Demo #72 | provision/cutover/recovery | offen gelassen | – | success | Real qualification |
| ISS-668 | issue/B | Retentionfundament aus | Code/tests | echter Rollout | offen gelassen | – | n/a | Operator authority |
| ISS-658 | issue/J | technischer D0-Pfad | Runbooks/Teilbelege | neuer Formal D0 | offen gelassen | – | n/a | FORMAL_D0_DEPENDENT |
| ISS-639 | issue/I | Extensioncontract integriert | PR #804 | externer Consumer releasegebunden | offen gelassen | #804 | success | Release dependent |
| ISS-636 | issue/I | Doc-Publisher integriert | PR #805 | Paketdigestbindung | offen gelassen | #805 | success | Release dependent |
| ISS-575 | issue/B | Clarification integriert | PR #800 | reale Dialogmatrix | offen gelassen | #800 | success | Real qualification |
| ISS-567 | issue/D | Netzursache offen | 0/6 AC | Entscheidung | markiert | – | n/a | HUMAN_DECISION_REQUIRED |
| ISS-549 | issue/B | Budget integriert | PR #799 | reale Adaptermatrix | offen gelassen | #799 | success | Real qualification |
| ISS-521 | issue/B | passive Submission integriert | PR #791 | realer Fremdrepo-Fall | offen gelassen | #791 | success | #679/Real qualification |
| ISS-482 | issue/C | State 1–5b vorhanden | State/retention tests | #668 + Recovery-AC | offen gelassen | – | n/a | staged completion |
| ISS-468 | issue/B | Reviewpfad integriert | PR #803 | reale Race/Restartfälle | offen gelassen | #803 | success | Real qualification |
| ISS-422 | issue/B | Identity integriert | PR #794 | reale TLS/Rollenmatrix | offen gelassen | #794 | success | Real qualification |
| ISS-897 | issue/H | neu, post-Golden | bestätigte 401/403/Admin-Fehldiagnose | drei Zustände umsetzen | Issue erstellt | – | n/a | Post-Golden |
| ISS-898 | issue/C | neu, Docs/Reports | dieser Audit | Review/Merge | Issue + Branch erstellt | #899 | pending | Human Merge |
| DOC-STATE | docs | v6/18 stale, Runtime v10/26 | sqlite `SCHEMA_VERSION=10` | korrigieren/regenerieren | vorbereitet | #899 | pending | Human Merge |
| DOC-CONFIG-MODE | docs | Quickstart widersprüchlich | production default/freeze tests | Setup explizit nennen | vorbereitet | #899 | pending | Human Merge |
| DOC-TASKS | docs | falsche Tasknamen | shipped defaults | Namen korrigieren | vorbereitet | #899 | pending | Human Merge |
| DOC-REST | docs | API-Tabelle unvollständig | server routes | Auswahl markieren/generieren | dokumentiert | – | n/a | späterer Docchange |
| DOC-CONFIG-TABLE | docs | fünf Dateien fehlen | config tree | Tabelle ergänzen | dokumentiert | – | n/a | späterer Docchange |
| DOC-CLI-TEST | test/docs | fünf Commands ungeprüft | CLI vs help test | Fixture ergänzen | dokumentiert | – | n/a | späterer Testchange |
| DOC-HANDOVER | prompt/docs | a15-Prioritäten stale | active document contract | upstreamen/historisieren | unverändert | – | n/a | Promptänderung gesperrt |
| DOC-PROMPT-AUDIT | audit/docs | Snapshot aktiv geführt | Commit 3be/Attempt 18 | Norm upstreamen, historisch halten | unverändert | – | n/a | Docs governance |
| WIKI-PRODUCT | wiki | Source `3c3d30f…`, main `401ffae…` | Wiki commit `c14a196…` | nach Merge regenerieren/publizieren | unverändert | – | n/a | Human Merge + publish authority |
| LOCAL-AUDITS | local artifacts | 21 untracked, 1.28 MB | Hash-/Inhaltsinventar | erhalten, später archivieren | klassifiziert | – | n/a | Provenienzreview |
| LOCAL-WORKTREES | local artifacts | 69 initial, 68 sauber | Git worktree/branch readback | kontrolliert prunen nach Review | nichts gelöscht | – | n/a | Maintainer cleanup |
| LOCAL-REHEARSALS | local evidence | 59 Gruppen, 2.46 GB | Attempt-/Qualificationroots | bewahren/archivieren | nichts gelöscht | – | n/a | Evidence retention decision |
| LOCAL-TMP | local artifacts | 273 Gruppen, 1.84 GB | gemischte Logs/Builds/Clones | gruppenweise Provenienz prüfen | nichts gelöscht | – | n/a | Maintainer cleanup |
| LOCAL-CACHES | local artifacts | regenerierbare Caches/egg-info | ignored status | optional löschen | nichts gelöscht | – | n/a | safe cleanup later |
| LOCAL-DATA | local evidence | SQLite/Audit/metrics | ignored data inventory | bewahren | nichts gelöscht | – | n/a | retention policy |
| GOLDEN-SPLIT | analysis | implizit/teilweise dokumentiert | Operating R24/preflight, VERSIONING | Phase-A-Receipt entscheiden | Finding dokumentiert | – | n/a | HUMAN_DECISION_REQUIRED |

Golden/Release action: **none**. Attempt 37: **not created**. Release/tag: **none**.
