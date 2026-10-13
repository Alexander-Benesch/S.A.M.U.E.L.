# Current Product Status

[Produkt](../../README.md) · [Technischer Überblick](../TECHNICAL_OVERVIEW.md) · [Dokumentwege](../README.md)

## Gegenwärtige Einordnung — 11.10.2026

Die Produktfunktionen und ihre Grenzen sind in der
[Advanced-Referenz](../README_technical.md) und der
[Capability-/Wirksamkeitsmatrix](../CAPABILITY_MATRIX.md) beschrieben.
Implementierung, aktive Profilwirkung, Regression und reale Qualification
bleiben getrennte Aussagen. Zielbilder in ADRs ersetzen keinen Betriebsnachweis.
S.A.M.U.E.L. bleibt im Alpha-/Referenzstadium; ein Dokumentmerge erteilt keine
Produktions-, Isolations-, Support- oder regulatorische Freigabe.

Die Dokumentation verwendet drei verbindliche Verständnistiefen: Produkt,
technischer Überblick und Advanced-Details. D1–D10 aus #1003 sind auf Main
`ededfccc8bf9cff7216a74c01ab6859e38bb8a18` integriert. D11 besitzt unveränderte
Modellantworten und benötigt weiterhin echte menschliche Verständlichkeitsabnahme.
Die 26 zusätzlich vorgesehenen ursprünglichen Free-Modellantworten sind durch
Maintainerentscheidung abbestellt, nicht bestanden. Die autorisierten späteren
Qualitätsarbeiten behalten ihre eigenen Prüfungen und Integrationsgrenzen.
Aktuelle Arbeitszustände werden im nativen EPIC einschließlich Kommentaren geführt.

Für Installationen gelten der jeweils bewusst ausgewählte veröffentlichte
Release und sein verifiziertes Manifest. Der unten datierte a29-Nachweis
belegt ausschließlich seine genannte Installation; er ist kein vollständiger
Funktions-/Golden-/D0-PASS. Einen späteren Release nicht aus dieser statischen
Seite ableiten. [Installation](../INSTALL.md),
[Releaseverfahren](../VERSIONING.md) und
[Test-/Qualification-Runbook](../runbooks/TEST_AND_QUALIFICATION_RUNBOOK.md)
bleiben die vorhandenen Verfahrensquellen.

Heute relevante Sicherheitsgrenzen bleiben sichtbar: lokale IMPORT-/TEST-
Ausführung ist keine allgemeine Prozesssandbox, externe Evidence besitzt nur
die dokumentierte Annahmeauthority, Score bleibt passiv und Compliance-Mappings
sind keine Konformitätsabnahme. R25 verlangt nach explizitem Replan eine neue
menschliche Freigabe; die begrenzte dokumentierte Durchsetzungslücke und ihr
UNKNOWN-Livebypass stehen im
[CLI-Vertrag](../README_technical.md#argumente-voraussetzungen-und-ergebnisgrenzen).
Eigenständige Operatorabnahmen wie #985 werden nicht durch Dokumentation ersetzt.

## Historie lesen, ohne sie als aktuellen Arbeitsauftrag zu verwenden

Der [vollständige bisherige Statusverlauf](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md)
erhält sämtliche früheren Release-, Candidate-, Fehler- und Integrationsnachweise.
Die folgenden zwei datierten Fachnachweise bleiben wegen bestehender Verweise
und Wiki-Projektionen unverändert zugänglich. Darin genannte damalige offene
Issues vor neuer Arbeit nativ lesen; sie sind kein aktueller Gesamtbacklog.
Weitere alte Anker führen direkt zur jeweiligen Archivstelle. Gültige ADRs,
aktive Betriebsregeln und historische Originale im Auditarchiv bleiben erhalten.

## Veröffentlichter Installationsstand v2.0.0a29 — 09.10.2026

Prerelease #43 bindet Productcommit `1a1c1f2eeaf324b62074a41adc9dc2474057561f` und
annotiertes Tagobjekt `332e2aab137748841d73b7523654fc06578e6894`. PR #989 und #980 sind
menschlich gemergt; Main-CI #1225 und Tag-CI #1226 einschließlich Release-Gate
sind SUCCESS. Sieben Assets wurden nach Upload und Veröffentlichung bytegleich
zurückgelesen. Manifest-SHA-256: `c62013a8a171627a0932fcf0c999aea9664c2d8533e27bb156414ddc51ed030b`.
OCI-Digest: `sha256:81c835bd358cb889f2333ed395f326c4b8cc50255cdb54659c6ce938c9095b69`.
Installationsauthority bleibt die vollständige `container.reference` im
geprüften Schema-2-Manifest, kein rekonstruierter Registry- oder Tagpfad.

Der erste Required Publisher-Smoke und zwei unabhängige Erstinstallationen
auf jeweils frischem Ubuntu 24.04.5 mit Docker 29.8.2 und Compose 5.6.0 sind
PASS: zuerst aus exakten Draft-Assets, danach aus veröffentlichten Assets.
Beide prüfen offiziellen Installer, Setup vor SCM, authentisierte Konfiguration,
Production Health, Releaseidentität, Persistenz, Recreate und Freeze. Das
Published-Installationsreceipt wurde am 09.10.2026 um 11:12:14 UTC abgeschlossen
und bindet denselben Productcommit und OCI-Digest. Kein Workflowstart oder
LLM-Aufruf; Projekt-Readiness bleibt ohne qualifizierte Projektbindung blockiert.
Keine vorhandene Installation oder Kundenquelle geändert. Alle sieben
veröffentlichten Assets sind zusätzlich bytegleich zurückgelesen. Die
Installationsreceipts sind in den Release Notes separat ausgewiesen.
Dies ist technische Installations-Evidence, kein kompletter Funktions-/D0-Lauf.

Enthalten sind registrierte lokale OCI-Projektquellen mit Recreate-Identität
und Git-Härtung, Gate-7-Fallback vor Kandidatenausführung, vollständige
Readinessaggregation sowie die gebundene Verifier-Versionprobe im vorhandenen
TEST-Budget mit maximal 60 Sekunden. Kleine Operatorbudgets bleiben verbindlich;
ungebundene Presence-Proben behalten acht Sekunden. Projektbestand, Workspaces,
Runtime und Authority-State bleiben getrennte bestehende Rollen.

Neue Alpha-Tests verwenden saubere Neuinstallationen; keine Übernahme alter
State-/Checkpoint-/Projektreceipts oder Cross-Release-Migration. Die kombinierte
PR-Suite bestand 3568 Tests; fünf Credentialfälle wurden separat nachgewiesen.
Diese Entwicklungsnachweise ersetzen keine reale a29-Funktionsabnahme.

**Offen:** vollständige lokale Prozessisolation, reale externe Sicherheits-
qualification und spätere H3-Remoteumgebung. #978/#988 bleiben für ihre eigenen
realen Abnahmen offen; #977/#986/#987 werden nicht pauschal erledigt. Die extern
berichteten a28-Teilabnahmen aus #981 bleiben auf deren damalige Umgebung
begrenzt; serverseitiger Tokenwiderruf bleibt unbelegt. Historische a28-Timeout-
FAILs bleiben erhalten. Kein Golden-/D0-PASS oder Produktionssupportclaim.
Die GitHub-Projektion ist ein eigener Auslieferungsstand; dieser native OCI-
Release behauptet keinen neuen Public-OCI- oder GitHub-a29-Publish.

## Untersuchung #951 abgeschlossen — freie Modelleingabe nach #975

Der ursprüngliche #951-Auftrag fordert ausdrücklich Ist-Stand, fachliche
Prüfung, vorhandene Checks und minimale Empfehlung vor späterer Umsetzung.
Alle acht Untersuchungsfragen sind beantwortet. #951 ist als
**INVESTIGATION_COMPLETE** geschlossen; die ursprünglichen Kriterien bleiben
erhalten. Am integrierten Code-Stand `20e3a172ef0b7398c4731be09172e310277c2f4a` bestehen die bisherigen
40 Fälle sowie 13 integrierte JavaScriptregressionen: **53 PASS, 0 SKIP** mit
bereits vorhandener Node v24.11.0 nur im Testprozess-PATH. Der erste Nachlauf
mit 40 PASS / 13 SKIP und die Korrektur des zunächst falschen PASSzählers
bleiben erhalten. Die ursprüngliche Browserbeobachtung ist historische
Evidence; keine neue Live-Providerprobe oder Save-/Route-/Configänderung.

Die verbindliche Maintainerentscheidung vom 13.10.2026 zu #975 erhält die
freie Modelleingabe in Einrichtung, Task und Schedule. Optionale Vorschläge
sind Orientierung; entfernte/unbekannte IDs, fehlende Kataloge und Refresh
ersetzen keine Eingabe. Die Umsetzung im Quellstand vereinheitlicht diese
Formulare und trennt Modellkatalog- von Benchmarkzustand. Bedienung und
UNKNOWN-Grenzen stehen im [Dashboard](../DASHBOARD.md#freie-modelleingabe-und-optionale-vorschläge).
Gatewaykatalog, native Endpoint-/Konto-Verfügbarkeit und Task-Suitability
bleiben getrennt; Setup→Persistenz→Recreate→Freeze und vorhandene
Routing-/Quality-/Fallbackregeln bleiben erhalten. Das ist kein neuer
Liveprovider-, nativer Browser-, Workflow- oder Qualification-PASS. Die
historischen 53 Untersuchungstests oben behalten ihre eigene Codebindung;
aktuelle #975-Regressionen werden im eigenen PR-/Issue-Nachweis geführt.

## Frühere Anker und Nachweise

## Dokumentationsarchitektur: integrierte Grundlagen D1–D6 — 10.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#dokumentationsarchitektur-integrierte-grundlagen-d1d6--10102026).

## HISTORICAL / AUDIT_EVIDENCE — Dokumentabgleich nach #1002

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#historical--audit_evidence--dokumentabgleich-nach-1002).

## Dokumentation integriert — Abgleich nach #1002, 10.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#dokumentation-integriert--abgleich-nach-1002-10102026).

## HISTORICAL / AUDIT_EVIDENCE — Vorbereitung vor dem Dokumentmerge

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#historical--audit_evidence--vorbereitung-vor-dem-dokumentmerge).

## Integrierter Entwicklungsstand und Dokumentnachlauf — 10.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#integrierter-entwicklungsstand-und-dokumentnachlauf--10102026).

## HISTORICAL / AUDIT_EVIDENCE — Dokumentvorbereitung vor Productmerges

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#historical--audit_evidence--dokumentvorbereitung-vor-productmerges).

## Erneuter Current-State-Abgleich — Candidateprüfung, 09.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#erneuter-current-state-abgleich--candidateprüfung-09102026).

## Autonomer Arbeitsstand auf Main 4bd335c — 09.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#autonomer-arbeitsstand-auf-main-4bd335c--09102026).

## #989 und #980 integriert und in a29 veröffentlicht — 09.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#989-und-980-integriert-und-in-a29-veröffentlicht--09102026).

## #988 — freigegebener lokaler Implementierungsumfang, 08.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#988--freigegebener-lokaler-implementierungsumfang-08102026).

## Historischer Installationsstand v2.0.0a28 — 08.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#historischer-installationsstand-v200a28--08102026).

## Entwicklungsdelta nach a27: Framework-Mappings — 06.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#entwicklungsdelta-nach-a27-framework-mappings--06102026).

## Historischer Installationsnachweis v2.0.0a27 — 06.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#historischer-installationsnachweis-v200a27--06102026).

## Productdelta nach #965 — 06.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#productdelta-nach-965--06102026).

## Veröffentlichter Release v2.0.0a26 — 05.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#veröffentlichter-release-v200a26--05102026).

## Administrativer Altlastenabschluss und Releasezweck — 05.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#administrativer-altlastenabschluss-und-releasezweck--05102026).

## Eigene releasegebundene Consumerabnahme — 05.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#eigene-releasegebundene-consumerabnahme--05102026).

## Eigener Taskeditor-Abnahmedelta — 05.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#eigener-taskeditor-abnahmedelta--05102026).

## Abnahmen und nächste gebündelte Kampagne — 04.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#abnahmen-und-nächste-gebündelte-kampagne--04102026).

## Eigene Operator-Abnahmen und verbleibende Grenzen — 04.10.2026, f514ddee

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#eigene-operator-abnahmen-und-verbleibende-grenzen--04102026-f514ddee).

## Aktueller eigener Abschluss nach #949 — 04.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#aktueller-eigener-abschluss-nach-949--04102026).

## Identitaet und Baseline

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#identitaet-und-baseline).

## Eigener aktueller Abschlussabgleich — 04.10.2026, a0f16c02

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#eigener-aktueller-abschlussabgleich--04102026-a0f16c02).

## Nachgewiesen funktionierend

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#nachgewiesen-funktionierend).

## Enger EOF-Fix und aktueller E2E-Impact

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#enger-eof-fix-und-aktueller-e2e-impact).

## Eigene Operator-Teilabnahmen — 04.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#eigene-operator-teilabnahmen--04102026).

## Teilweise oder noch nicht end-to-end belegt

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#teilweise-oder-noch-nicht-end-to-end-belegt).

## Aktuelle Blocker

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#aktuelle-blocker).

## Eigenständiger Development-E2E auf integriertem Main — 04.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#eigenständiger-development-e2e-auf-integriertem-main--04102026).

## Eigenständiger Development-E2E auf integriertem Main — 03.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#eigenständiger-development-e2e-auf-integriertem-main--03102026).

## Frühere eigene Development-E2E-Baseline auf eb6cce18 — 03.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#frühere-eigene-development-e2e-baseline-auf-eb6cce18--03102026).

## Historische positive Development-E2E-Baseline — 02.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#historische-positive-development-e2e-baseline--02102026).

## Historischer fehlgeschlagener MANUAL-Lauf

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#historischer-fehlgeschlagener-manual-lauf).

## Qualification, Wiki und Public Sync

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#qualification-wiki-und-public-sync).

