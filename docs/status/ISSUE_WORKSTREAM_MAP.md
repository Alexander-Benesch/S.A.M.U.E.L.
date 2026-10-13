# Issue Workstream Map

## Aktuelle Verwendung

Diese Seite ordnet Arbeits- und Nachweisarten ein. Den tatsächlichen Rest eines
Issues bestimmen sein nativer Body, Kommentare, integrierte Fixes und eigene
Evidence. Datierte alte Issuezahlen, Mergefolgen oder READINESS-Receipts sind
kein gegenwärtiger Auftrag und keine dauerhafte Freigabe. Die
[Coding-Agent-Anweisung](../../.claude/CLAUDE.md#vor-der-ersten-mutation),
[Operating Rules](../OPERATING_RULES.md) und das
[Test-/Qualification-Runbook](../runbooks/TEST_AND_QUALIFICATION_RUNBOOK.md)
bleiben die vorhandenen Authorities.

| Frage | Maßgebliche Quelle / Grenze |
|---|---|
| Ist eine Funktion vorhanden und wie wirkt sie? | [Advanced-Referenz](../README_technical.md), [Capabilitymatrix](../CAPABILITY_MATRIX.md), aktueller Code und ausgelieferte Konfiguration. |
| Ist die beauftragte Änderung integriert? | Tatsächlicher Main-/Merge-Readback und issueeigene Contracts; ein vorbereiteter PR reicht nicht. |
| Ist der konkrete Betrieb qualifiziert? | Eigener Subject-/Attempt-/Umgebungsnachweis nach Runbook; weder Unit-PASS noch ein administrativer Abschluss ersetzt ihn. |
| Welche Arbeit darf als Nächstes laufen? | Aktueller genehmigter Scope und reale Abhängigkeiten; normale Entwicklung wartet nicht pauschal auf Golden. |
| Was gilt für die Dokumentation? | EPIC #1003 trägt ursprüngliche und ergänzte Kriterien. D11 und spätere Qualitätsabnahme haben getrennte Testbasen; echte Humanabnahme bleibt erforderlich. |

Der [datierte frühere Zuordnungsbestand](../archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md) bleibt vollständig
zugänglich. Seine alten PASS/FAIL/UNKNOWN behalten ihre damalige Bindung.
Die nachstehenden Anker erhalten vorhandene Verweise; daraus entsteht keine
aktuelle Schließung oder neue Freigabe.

## Erhaltene Zuständigkeits- und Sicherheitsgrenzen

Die folgenden vorhandenen Grenzen bleiben wörtlich erhalten. Maßgebliche
Issueentscheidungen und Betriebsregeln vor weiterer Umsetzung aktuell lesen.

#679 betrifft den externen Execution-/Evidence-Provider, nicht LLM-Routen.
Sein ausgeliefertes Profil ist deaktiviert; nur ein Qualification-Profil,
das diese Capability verlangt, macht deren Provisionierung zur Voraussetzung.

#921 besitzt ausschliesslich die fehlende backendneutrale Full-System-
Aggregation und den kritischen Preflight. #693/ADR-0693 bleiben Authority fuer
Health-, Readiness-, Qualification- und aktive Self-Check-Semantik; #694 fuer
Required-Check-Diagnose und #905 fuer native Webhook-Delivery. Es entsteht
keine zweite Health-Architektur, automatische Reparatur oder Gitea-
Corekopplung. #920 darf Ownership-, Approval-, Candidate- und
Gatebindungen nicht abschwaechen. Retention und Workflow-Recovery bleiben
getrennte Authoritybereiche.

Promptresolver/Profile und Parsergrammar duerfen parallel analysiert werden;
Promptaenderungen benoetigen eigene Product-Authority und gehoeren nicht in
Docs-/Qualification-Fixes.

Labels und Dashboardstatus bleiben Projektion. Dieser Workstream darf keine
Approval-, Merge-, Retry- oder Gateauthority aus UI-Zustand ableiten.

Route-, Setup- und Authority-Probes koennen parallel vorbereitet werden. Der
abschliessende #859-Lauf muss dieselbe unveraenderte Strecke verwenden; einzelne
alte PASS-Abschnitte duerfen nicht zusammengesetzt werden. #658 beginnt erst
nach einem immutable Release und darf nicht mit Development-E2E kombiniert
werden.

## Historische Anker

## Anschluss nach integriertem Dokumentmerge — 10.10.2026

HISTORICAL — [damalige Zuordnung und Originalnachweise](../archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md#anschluss-nach-integriertem-dokumentmerge--10102026).

## HISTORICAL / AUDIT_EVIDENCE — Workstreamstand vor Dokumentmerge

HISTORICAL — [damalige Zuordnung und Originalnachweise](../archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md#historical--audit_evidence--workstreamstand-vor-dokumentmerge).

## Autonomer Restumfang — 10.10.2026

HISTORICAL — [damalige Zuordnung und Originalnachweise](../archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md#autonomer-restumfang--10102026).

## Aktueller Testrelease v2.0.0a29 — 09.10.2026

HISTORICAL — [damalige Zuordnung und Originalnachweise](../archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md#aktueller-testrelease-v200a29--09102026).

## Historischer Installationsstand v2.0.0a28 — 08.10.2026

HISTORICAL — [damalige Zuordnung und Originalnachweise](../archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md#historischer-installationsstand-v200a28--08102026).

## Untersuchung #951 abgeschlossen — UI-Entscheidung #975 offen

HISTORICAL — [damalige Zuordnung und Originalnachweise](../archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md#untersuchung-951-abgeschlossen--ui-entscheidung-975-offen).

## Aktueller #873-Workstream — 06.10.2026

HISTORICAL — [damalige Zuordnung und Originalnachweise](../archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md#aktueller-873-workstream--06102026).

## Historischer Installationsnachweis v2.0.0a27 — 06.10.2026

HISTORICAL — [damalige Zuordnung und Originalnachweise](../archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md#historischer-installationsnachweis-v200a27--06102026).

## Productdelta nach #965 — 06.10.2026

HISTORICAL — [damalige Zuordnung und Originalnachweise](../archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md#productdelta-nach-965--06102026).

## Veröffentlichter Release v2.0.0a26 — 05.10.2026

HISTORICAL — [damalige Zuordnung und Originalnachweise](../archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md#veröffentlichter-release-v200a26--05102026).

## Administrativer Altlastenabschluss und Releasezweck — 05.10.2026

HISTORICAL — [damalige Zuordnung und Originalnachweise](../archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md#administrativer-altlastenabschluss-und-releasezweck--05102026).

## Eigene releasegebundene Consumerabnahme — 05.10.2026

HISTORICAL — [damalige Zuordnung und Originalnachweise](../archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md#eigene-releasegebundene-consumerabnahme--05102026).

## Eigener Taskeditor-Abnahmedelta — 05.10.2026

HISTORICAL — [damalige Zuordnung und Originalnachweise](../archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md#eigener-taskeditor-abnahmedelta--05102026).

## Abnahmen und nächste gebündelte Kampagne — 04.10.2026

HISTORICAL — [damalige Zuordnung und Originalnachweise](../archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md#abnahmen-und-nächste-gebündelte-kampagne--04102026).

## Nächster eigener Abschluss — 04.10.2026, f514ddee

HISTORICAL — [damalige Zuordnung und Originalnachweise](../archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md#nächster-eigener-abschluss--04102026-f514ddee).

## Aktueller selektiver Abschlussblock — 04.10.2026, a0f16c02

HISTORICAL — [damalige Zuordnung und Originalnachweise](../archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md#aktueller-selektiver-abschlussblock--04102026-a0f16c02).

## Selektiver eigener Evidenceanschluss — 04.10.2026

HISTORICAL — [damalige Zuordnung und Originalnachweise](../archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md#selektiver-eigener-evidenceanschluss--04102026).

## P0 — Positive-E2E- und Authority-Blocker

HISTORICAL — [damalige Zuordnung und Originalnachweise](../archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md#p0--positive-e2e--und-authority-blocker).

## P1 — Recovery, Operability und Self-Check

HISTORICAL — [damalige Zuordnung und Originalnachweise](../archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md#p1--recovery-operability-und-self-check).

## P1 — Determinismus, Contract und Prompt/Parser

HISTORICAL — [damalige Zuordnung und Originalnachweise](../archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md#p1--determinismus-contract-und-promptparser).

## P2 — Observability, UX und Statusprojektion

HISTORICAL — [damalige Zuordnung und Originalnachweise](../archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md#p2--observability-ux-und-statusprojektion).

## P2 — Dokumentation, Release und Statusdrift

HISTORICAL — [damalige Zuordnung und Originalnachweise](../archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md#p2--dokumentation-release-und-statusdrift).

## P2 — Spaetere Features und Post-Golden

HISTORICAL — [damalige Zuordnung und Originalnachweise](../archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md#p2--spaetere-features-und-post-golden).

## Gemeinsam oder nacheinander

HISTORICAL — [damalige Zuordnung und Originalnachweise](../archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md#gemeinsam-oder-nacheinander).

## HISTORICAL / AUDIT_EVIDENCE — ursprüngliche PR-Vorbereitung

HISTORICAL — [damalige Zuordnung und Originalnachweise](../archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md#historical--audit_evidence--ursprüngliche-pr-vorbereitung).

## Autonomer Restumfang — 09.10.2026

HISTORICAL — [damalige Zuordnung und Originalnachweise](../archive/reader-history-2026-10-11/ISSUE_WORKSTREAM_MAP.md#autonomer-restumfang--09102026).

