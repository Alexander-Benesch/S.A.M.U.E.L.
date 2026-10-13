# Public snapshot — 2026-10-13

Bereinigte, nicht autoritative Projektion des integrierten Entwicklungsstands
`754f8387edd89a0a69270d8465c322c0c3ffc7f2` nach den abgeschlossenen PRs #1050, #1051,
#1053, #1054 und #1052. Dieser Public-Snapshot enthält genau einen parentlosen
Root-Commit; private Entwicklungshistorie, Evidencepayloads und Zugänge bleiben
im operativen Repository. Der letzte PR wurde nach ausdrücklicher Maintainerfreigabe
und abgeschlossenen grünen Required Runs integriert.

Der vollständige aktuelle Produktcode und die bestehende Dokumentationsstruktur
sind enthalten: freie Modelleingabe mit optionalen Katalogvorschlägen (#975),
Python-Mindestversion 3.12 mit CI-Testpunkten 3.12/3.14 ab dem ersten noch nicht
veröffentlichten Alpha v2.0.0a30 (#811), sichtbare Audit-Schreibdiagnose bei
unveränderten Health-Exitcodes (#986), Originalquellenbindung für Review/Replay
(#883) und die vereinfachte Installationsanleitung (#985). Die 48 echten,
bereits verlustfrei zugeschnittenen und datenschutzbereinigten Bildausschnitte
bleiben mit ihren Aufnahme-/Statusgrenzen in den bestehenden Kapiteln erhalten.
Die unabhängige öffentliche Wiki-Projektion verlinkt diesen Public-Commit und
seine unveränderten Bilddateien.

Die menschliche Verständlichkeitsabnahme der Installationsanleitung (#985),
fehlende echte Bildzustände (#1048) und die umfangreiche aktive CRA-Erweiterung
(#873, ausdrücklich zurückgestellt) sind weiterhin getrennte offene Umfänge.
Beschreibende CRA-Zuordnungen ergeben keine Zertifizierung oder Compliance-Zusage.
Die Einordnung von S.A.M.U.E.L. selbst bleibt von einer späteren CRA-Prüffunktion
getrennt. Dieser Snapshot erzeugt keine Release-, Provider-, Workflow-, Golden-
oder menschliche Qualification. Bestehende veröffentlichte Releases, Drafts,
Tags und Assets bleiben unverändert; private OCI-Verfügbarkeit wird nicht als
öffentliche Verfügbarkeit ausgegeben.

Produktcode, Paket-/Containerverträge und Bilddateien entsprechen dem integrierten
Source. Bereits veröffentlichte bereinigte Archivfassungen bleiben historische
Projektionen. Ergänzte aktuelle Archivziele und erforderliche Beispielwerte
werden separat bereinigt und geprüft. Quellen-/Wiki-Bindungen und Tests erhalten
eigene Public-Nachweise. Aktuelle Planung wird hier als begrenzter Snapshot
geführt; der frühere GitHub-Issue-#2-Stand bleibt historische, nicht autoritative
Planung und ist kein aktueller Abschlussnachweis.

## Aktuelle offene Planung — 13.10.2026

27 offene native Produktthemen als nicht autoritativer Titelüberblick. Referenznummern stammen aus dem operativen Tracker; dies legt keine neuen GitHub-Issues an und überträgt keine privaten Bodies, Kommentare, Akteure oder Evidence. Das interne Zugangsthema bleibt ausgenommen. #811, #975, #986, #883 und #1031 sind dort abgeschlossen.

| Native Referenz | Offenes Thema |
|---:|---|
| `#840` | coordination(remediation): finale #840-Baseline, Issue-Reconciliation und verbleibende Arbeitsträger |
| `#873` | CRA ergänzen und Austauschbarkeit der Compliance-/Security-Frameworks prüfen |
| `#878` | Sichere anpassbare Prompt-Profile für Modelle, Provider, Worker und Umgebungen |
| `#880` | [UX/Authority] MANUAL-Acceptance sicher und benutzerfreundlich binden |
| `#888` | [Post-Golden Investigation] Fresh Install, Operability, Qualification-Harness, Observability und Providergrenzen sauber trennen |
| `#890` | [Observability] Fehlerdiagnosen kausal, korreliert und handlungsfähig darstellen |
| `#897` | ops(diagnostics): least-privilege, operator action and escalation requests distinguish |
| `#905` | [Setup/Operability] Native SCM-Webhook-Erreichbarkeit als Setup-, Doctor- und Doku-Vertrag absichern Problem |
| `#920` | operability(recovery): terminale Blocker auf sicheren Issue-Re-Entry abbilden |
| `#921` | operability(self-check): vollständige backendneutrale Operational Readiness bündeln |
| `#948` | [Approval/UX] Sichtbaren Plan, native Freigabe und verbleibendes status:approved bei abgelehnter Approval untersuchen |
| `#956` | [Workflow/Labels] Fehler und Abbruch sicher aus automatischer Aufnahme nehmen; Labelgrenzen und Entwickleraktionen festlegen |
| `#961` | [Altlasten-Restabnahme] Gebundene Findings und vollständige offene Restschuld05.10.2026 |
| `#962` | [Abnahme – vertagt] Vollständige Funktionssuite nach separater Releaseinstallation |
| `#977` | security(investigation): 11 GitHub-CodeQL-High-Findings zu Promptpfaden, Secrets und URL-Prüfung untersuchen |
| `#978` | # D0-Qualification auf OCI-Installation blockiert: Verifier-Toolchain fehlt und temporärer Branchschutz-Prüfer ist nicht nutzbar |
| `#985` | docs(oci): Releasewechsel und selektiven Fresh-Install-Restore einschließlich Auditkey eindeutig abgrenzen (#981) |
| `#988` | Architektur-Blocker im realen OCI-Funktionslauf: PROJECT_ROOT / Zielprojekt-Betriebsmodell ungeklärt |
| `#992` | UX/OPS-033 — Laufzeitrelevante LLM-Einstellungen erfordern vollständigen Setup-/Production-Wechsel |
| `#993` | S.A.M.U.E.L. v2.0.0a29 — Abnahmebericht bis `PlanBlocked` |
| `#994` | # Vollständige Abnahmeinventur erstellen und offene Tests auf Tamagotchi-Referenzlauf herunterbrechen |
| `#1003` | EPIC – S.A.M.U.E.L. Documentation Architecture 2026: Vollständigkeit, Wahrheit, Struktur, Agentenregeln und dauerhafte Codebindung |
| `#1015` | [#1003/D11] Menschliches und modellübergreifendes Produktverständnis abschließend abnehmen |
| `#1032` | [#1003/Q6] Realen Issue-to-Merge-Ablauf mit Screenshots und SVGs nachvollziehbar machen |
| `#1033` | [#1003/Q7] Erweiterten integrierten Dokumentationsstand real verständlich abnehmen |
| `#1046` | EPIC – S.A.M.U.E.L. Product Completion & Feature Cross-Check: Offene Issues systematisch abschließen und Golden-Readiness herstellen |
| `#1048` | docs: Fehlende reale Ablauf- und Zustandsaufnahmen gesammelt nachliefern |
