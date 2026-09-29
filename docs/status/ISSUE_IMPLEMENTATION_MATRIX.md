# Issue Implementation Matrix

Erhebung: 2026-09-29 auf Gitea `main@41340e75`. Die vorangegangene vollstaendige
Reconciliation der damals 41 offenen Issues ist unter
`docs/archive/housekeeping/2026-09-26/` gebunden. Der v9-Live-Readback pruefte 482 Product-Issues paginiert (46 offen, 436
geschlossen) gegen Product `main@41340e75`. Die 43 zuvor offenen Traeger
wurden remote mit einem aktuellen Reconciliation-Kommentar versehen, sofern
nicht schon der v8-Delta-Kommentar vorhanden war; #920-#922 besitzen
aktuelle Bodies und #921 wurde auf den fehlenden Aggregationsscope begrenzt. Geschlossene historische Issues werden ohne individuellen neuen
Evidenceabgleich nicht pauschal als `CLOSED_CORRECTLY` bezeichnet; die seit dem Snapshot geschlossenen Fixes #902, #906, #908, #910,
#912, #913, #916 und #918 sind durch Merge, Regressionen und gruenen Main-CI
belegt.

Statusbegriffe bedeuten exakt den Implementierungsstand, nicht Prioritaet.
Die 436 geschlossenen Issues sind einzeln in
[`CLOSED_ISSUE_CLASSIFICATION.md`](CLOSED_ISSUE_CLASSIFICATION.md)
aufgefuehrt. Dort ist fehlende individuelle aktuelle Evidence als `UNKNOWN`
oder `IMPLEMENTED_UNVERIFIED` sichtbar, nicht als stiller Abschluss-PASS.

| Issue | Typ | Status | Implementiert / verifiziert | Verbleibender Scope / Abhaengigkeit |
|---|---|---|---|---|
| #422 | QUALIFICATION | IMPLEMENTED_UNVERIFIED | Identity-, Rollen-, Session- und Cutover-Tests | reale TLS-/Rollen-/Recovery-Matrix |
| #468 | QUALIFICATION | IMPLEMENTED_UNVERIFIED | Review, Intent und Expected-head technisch gebunden | reale Race-/Restart-/Aktivierungsprobe |
| #482 | FEATURE | PARTIALLY_IMPLEMENTED | State, Restore, Reconcile, Resume und Retention-Fundament | #668 und reale Recovery-Evidence |
| #521 | QUALIFICATION | IMPLEMENTED_UNVERIFIED | passive Candidate Submission und no-mutation tests | externer Repo-Positivfall, #679 |
| #549 | QUALIFICATION | IMPLEMENTED_UNVERIFIED | persistentes Budget und Regressionen | reale Provider-/Restartgrenzen |
| #567 | OPERABILITY | BLOCKED_EXTERNAL | Netzfinding dokumentiert | Infrastrukturentscheidung und L2-Ursache |
| #575 | QUALIFICATION | IMPLEMENTED_UNVERIFIED | Clarification, Revision, Timeout und Restart getestet | reale Actor-/Supersession-Strecke |
| #636 | QUALIFICATION | IMPLEMENTED_UNVERIFIED | Documentation Inventory/Publisher vorhanden | Release-/Paketdigestbindung |
| #639 | QUALIFICATION | IMPLEMENTED_UNVERIFIED | Extension-Contract und Fixtures | releasegebundener externer Consumer |
| #658 | QUALIFICATION | QUALIFICATION_ONLY | technischer D0-Pfad vorhanden | frischer zusammenhaengender Formal-D0-Subject |
| #668 | OPERABILITY | PARTIALLY_IMPLEMENTED | Retention-Authority, Dry-run, Receipt und Restore | kontrollierter Kategorien-Rollout |
| #679 | QUALIFICATION | IMPLEMENTED_UNVERIFIED | Providervertrag und Recoveryfixtures | reale Provisionierung/Cutover |
| #691 | QUALIFICATION | IMPLEMENTED_UNVERIFIED | Setup-/Persistenz-/Freeze-Code und Tests | reale Recreate-Kette |
| #693 | QUALIFICATION | IMPLEMENTED_UNVERIFIED | Health-/Readiness-Projektionen | reale aktive/passive/restart Matrix; #921 |
| #694 | QUALIFICATION | IMPLEMENTED_UNVERIFIED | Required-Check-Diagnose | reale Ziel-Context- und Rollenprobe; #921 |
| #811 | COORDINATION | BLOCKED_EXTERNAL | Entscheidungsgrundlage vorhanden | menschliche Python-Supportentscheidung |
| #812 | DOCS | DOC_ONLY | a18-Historie erhalten | Pre-Tag-Receipt abschliessend zuordnen |
| #821 | OPERABILITY | PARTIALLY_IMPLEMENTED | lokale Secret-Quellen teilweise konsolidiert | restliche Rollen-/Toolzugriffe, ohne Secretkopie |
| #822 | QUALIFICATION | IMPLEMENTED_UNVERIFIED | Routing und Self-check vorhanden | aktive Routeprobes und Freeze |
| #823 | QUALIFICATION | IMPLEMENTED_UNVERIFIED | Bind-mount-Persistenzfix und Tests | releasegebundene Setup-Abnahme |
| #828 | OPERABILITY | IMPLEMENTED_UNVERIFIED | redigierte Apply-Diagnose | realer Providerlauf und Inputbindung |
| #829 | DOCS | IMPLEMENTED_UNVERIFIED | Override-Praezedenz dokumentiert | reale effective-route-/Freeze-Evidence |
| #830 | OPERABILITY | IMPLEMENTED_UNVERIFIED | Dashboard/API/Health technisch projiziert | echte Run-/UI-/Restartbeobachtung |
| #840 | COORDINATION | PARTIALLY_IMPLEMENTED | Baseline und Child-Carrier reconciled | bleibt Provenienz-/Reihenfolgetraeger |
| #843 | OPERABILITY | PARTIALLY_IMPLEMENTED | Setup-/Auth-Validierung vorhanden | stored/effective vor erster Wirkung |
| #844 | SECURITY/AUTHORITY | PARTIALLY_IMPLEMENTED | keyloser Append auf signierte Chain blockiert | D0-Writerbindung und reale Chainprobe |
| #845 | QUALIFICATION | IMPLEMENTED_UNVERIFIED | Remote-/Transport-Schutz getestet | frischer kanonischer Subject-Readback |
| #846 | BUG | IMPLEMENTED_UNVERIFIED | Nichtplan erzeugt keine Planauthority | reale SCM-/Release-Qualification |
| #847 | BUG | IMPLEMENTED_UNVERIFIED | PlanBlocked liefert nonzero | installierte Positiv-/Negativabnahme |
| #859 | QUALIFICATION | QUALIFICATION_ONLY | mehrere reale Teilstrecken und Failure-Evidence | kompletter unveraenderter Development Golden |
| #873 | SECURITY/AUTHORITY | NOT_IMPLEMENTED | AI-Act/DSGVO/OWASP-Basis vorhanden | CRA-Scope, Austauschbarkeit und AC |
| #878 | FEATURE | PARTIALLY_IMPLEMENTED | Promptresolver und Override-Layer | Profilvertrag und reale Smokes |
| #880 | FEATURE | PARTIALLY_IMPLEMENTED | Receipt-Bindung und Continuation durch #910 technisch belegt | sichere einfache Human-UX und Transportdarstellung |
| #883 | SECURITY/AUTHORITY | NOT_IMPLEMENTED | Redaction-Basis vorhanden | Original-/Redacted-Identitaet und Replayvertrag |
| #888 | COORDINATION | QUALIFICATION_ONLY | Findingklassen gesammelt | post-Golden Gesamtbewertung |
| #889 | OPERABILITY | IMPLEMENTED_UNVERIFIED | Setup/Freeze/Digests dokumentiert und getestet | kompletter Operator-Lifecycle |
| #890 | OPERABILITY | PARTIALLY_IMPLEMENTED | Korrelation und Run-/Issue-Projektion | kausale Root-Cause-/Remediationdarstellung |
| #891 | OPERABILITY | PARTIALLY_IMPLEMENTED | configured/effective Route sichtbar | taskweise current/last-call Trennung |
| #892 | BUG | IMPLEMENTED_UNVERIFIED | deterministische Contextordnung via PR #893 | reale Candidate-/Prestart-Qualification |
| #894 | QUALIFICATION | IMPLEMENTED_UNVERIFIED | non-root-/RO-Mount-Grenzen beschrieben | reale Mount-/Owner-Matrix |
| #897 | OPERABILITY | NOT_IMPLEMENTED | Diagnosevertrag spezifiziert | least-privilege vs. action/escalation abbilden |
| #900 | QUALIFICATION | QUALIFICATION_ONLY | Prep-Incidents und Trennung dokumentiert | reproduzierbare Prep ohne Workflowwirkung |
| #905 | OPERABILITY | PARTIALLY_IMPLEMENTED | native signierte Webhooks technisch belegt | Setup/Doctor/Reachability-Vertrag |
| #920 | OPERABILITY | NOT_IMPLEMENTED | bestehende `run`, `replan`, bound resume Grundlagen | einheitlicher sicherer Re-Entry-Vertrag |
| #921 | OPERABILITY | PARTIALLY_IMPLEMENTED | #693/ADR-0693 besitzen Health-/Readiness-/Qualification- und aktiven Self-Check-Vertrag | nur fehlende backendneutrale Full-System-Aggregation und kritischer Preflight; keine zweite Health-Architektur |
| #922 | FEATURE | NOT_IMPLEMENTED | Completion-URL konfigurierbar | Katalog-/Benchmark-URLs aus Konstanten loesen |

Keine Checkbox wurde allein wegen eines gemergten PRs als erledigt gewertet.
`IMPLEMENTED_UNVERIFIED` bleibt offen, bis die im Issue geforderte reale oder
releasegebundene Evidence vorliegt.

## Remote-Reconciliation-Readback

Stand 2026-09-29: Die folgenden Gitea-Kommentar-IDs sind die aktuellen
Housekeeping-Deltaanker; die drei neuen Issues besitzen aktuelle Bodies.
Ein Kommentar aendert keine historischen Checkboxen und ist keine neue
Qualification. Issue #921 erhielt zusaetzlich einen aktualisierten Body.

| Issue | Gitea-Reconciliation |
|---|---|
| #422 | Kommentar #44860 |
| #468 | Kommentar #44863 |
| #482 | Kommentar #44866 |
| #521 | Kommentar #44869 |
| #549 | Kommentar #44873 |
| #567 | Kommentar #44876 |
| #575 | Kommentar #44878 |
| #636 | Kommentar #44881 |
| #639 | Kommentar #44884 |
| #658 | Kommentar #44956 |
| #668 | Kommentar #44889 |
| #679 | Kommentar #44893 |
| #691 | Kommentar #44896 |
| #693 | Kommentar #44902 |
| #694 | Kommentar #44907 |
| #811 | Kommentar #44911 |
| #812 | Kommentar #44913 |
| #821 | Kommentar #44916 |
| #822 | Kommentar #44918 |
| #823 | Kommentar #44920 |
| #828 | Kommentar #44923 |
| #829 | Kommentar #44925 |
| #830 | Kommentar #44927 |
| #840 | Kommentar #44852 |
| #843 | Kommentar #44929 |
| #844 | Kommentar #44931 |
| #845 | Kommentar #44933 |
| #846 | Kommentar #44935 |
| #847 | Kommentar #44937 |
| #859 | Kommentar #44960 |
| #873 | Kommentar #44939 |
| #878 | Kommentar #44941 |
| #880 | Kommentar #44830 |
| #883 | Kommentar #44943 |
| #888 | Kommentar #44837 |
| #889 | Kommentar #44945 |
| #890 | Kommentar #44844 |
| #891 | Kommentar #44947 |
| #892 | Kommentar #44949 |
| #894 | Kommentar #44952 |
| #897 | Kommentar #44954 |
| #900 | Kommentar #44846 |
| #905 | Kommentar #44849 |
| #920 | aktueller neuer Body |
| #921 | Kommentar #44959 |
| #922 | aktueller neuer Body |
