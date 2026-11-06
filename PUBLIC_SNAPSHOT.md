# Public snapshot — 2026-11-06

Bereinigte, nicht autoritative Projektion des integrierten Entwicklungsstands
`9a4e84a1d1d674864c3ff089542ee187ef0b1834`. Code, Dokumentation und das daraus
erzeugte öffentliche Wiki gehören zu diesem Source-Stand. Die öffentliche
Git-Historie besteht nach dem bestehenden Vertrag aus einem parentlosen Root-Commit.
Private Entwicklungshistorie, Evidencepayloads und Zugänge sind nicht enthalten.

Neu integriert sind der geschützte Konfigurationsmodus im Dashboard (#992),
der explizite Wiederanlauf ab Neuplanung mit neuer menschlicher Freigabe (#920),
gebundene Abschlusslabels und ein deduplizierter terminaler SCM-Kommentar (#956)
sowie konkrete Diagnose-, Prüf- und Behebungshinweise (#890). Verwandte Meldungen
bleiben als Korrelationskontext erkennbar; eine unbekannte Ursache wird nicht
behauptet. Die früheren Approval-, Modell-, Prompt- und SCM-Diagnosekorrekturen
bleiben enthalten. Doku und Wiki-Quellen wurden in denselben PRs aktualisiert.
#897 ergänzt die gemeinsame operationenbezogene Berechtigungsdiagnose in SCM-Logs,
Dashboard, Doctor und Setup: bestätigter Einzelzugriff, gezielte Operatorprüfung,
belegte bestehende API-Sperre und unbekanntes Ergebnis erhalten konkrete nächste
Schritte. Einzelzugriff ist kein Gesamt-READY; Botrechte und Workflowentscheidungen
bleiben unverändert. Die unabhängige Wiki-Projektion bindet Quellen und Bilder
an den Public-Commit.

#905 ergänzt die passive Webhook-Diagnose in Dashboard und Doctor mit gezielten
Behebungshinweisen. Konfiguration, Empfang, Signatur und Verarbeitung bleiben
getrennt; der ausdrückliche Hook-Metadaten-Read verwendet vorhandene Credentials.
Keine neue Startsperre, kein Testdispatch und kein automatischer nativer
Zustellnachweis: die externe Zustellabnahme bleibt separat.

#921 bündelt vorhandene Health-, Doctor-, Audit-, Projekt-, Konfigurations- und
Webhookbefunde als gemeinsame passive Betriebsdiagnose mit Aktualität und
konkretem nächsten Schritt. Fehlende oder veraltete Nachweise werden nicht
als bestanden ausgegeben. Bestehende Startprüfungen bleiben maßgeblich;
keine zusätzliche Startsperre, automatische Probe oder globale Freigabe.

#880 präzisiert die Planungsanweisungen: automatische Kriterien bevorzugen;
MANUAL benennt die konkrete menschliche Entscheidung und begründet, warum
automatische Evidence nicht genügt. Der vorhandene Retry erhält dieselbe
Anleitung. Bestehende Verträge bleiben gültig; keine neue semantische
Startsperre oder automatische Umklassifizierung. Die Anleitung garantiert
keine fehlerfreie Modellentscheidung.

Gemeinsame Installation und native Liveabnahme der neuen Funktionen erfolgen
separat (#962/#994). Automatisierte Entwicklungsprüfungen sind kein Golden-/D0-
oder Live-PASS. Bestehende datierte Bilder und historische FAILs bleiben erhalten.
Die aktive CRA-Erweiterung (#873) ist weiter zurückgestellt; beschreibende
Zuordnungen sind keine Zertifizierung. Dieser Snapshot erzeugt keinen neuen
Release. Tags, Releases, Drafts und Assets behalten ihre bisherigen Bindungen;
private OCI-Verfügbarkeit ist kein Nachweis einer öffentlichen Installation.

Produktcode, Paket-/Containerverträge und Bilddateien entsprechen dem integrierten
Source. Bereinigungen betreffen Beispielwerte und private Betriebs-/Archivangaben.
Bereits veröffentlichte bereinigte Archivfassungen bleiben historische Projektionen.
Quellen- und Wiki-Bindungen werden für diese Public-Projektion erneut geprüft.
GitHub Issue #2 bleibt historische, nicht autoritative Planung; aktuelle offene
Themen stehen im folgenden Überblick.

## Aktuelle offene Planung — 06.11.2026

17 offene Produktthemen als nicht autoritativer Titelüberblick. Referenznummern stammen aus dem operativen Tracker; private Bodies, Kommentare und Evidence werden nicht übernommen. Das interne Zugangsthema bleibt ausgenommen.

| Native Referenz | Offenes Thema |
|---:|---|
| `#840` | coordination(remediation): finale #840-Baseline, Issue-Reconciliation und verbleibende Arbeitsträger |
| `#873` | CRA ergänzen und Austauschbarkeit der Compliance-/Security-Frameworks prüfen |
| `#878` | Sichere anpassbare Prompt-Profile für Modelle, Provider, Worker und Umgebungen |
| `#888` | [Post-Golden Investigation] Fresh Install, Operability, Qualification-Harness, Observability und Providergrenzen sauber trennen |
| `#961` | [Altlasten-Restabnahme] Gebundene Findings und vollständige offene Restschuld05.10.2026 |
| `#962` | [Abnahme – vertagt] Vollständige Funktionssuite nach separater Releaseinstallation |
| `#977` | security(investigation): 11 GitHub-CodeQL-High-Findings zu Promptpfaden, Secrets und URL-Prüfung untersuchen |
| `#978` | # D0-Qualification auf OCI-Installation blockiert: Verifier-Toolchain fehlt und temporärer Branchschutz-Prüfer ist nicht nutzbar |
| `#988` | Architektur-Blocker im realen OCI-Funktionslauf: PROJECT_ROOT / Zielprojekt-Betriebsmodell ungeklärt |
| `#993` | S.A.M.U.E.L. v2.0.0a29 — Abnahmebericht bis `PlanBlocked` |
| `#994` | # Vollständige Abnahmeinventur erstellen und offene Tests auf Tamagotchi-Referenzlauf herunterbrechen |
| `#1003` | EPIC – S.A.M.U.E.L. Documentation Architecture 2026: Vollständigkeit, Wahrheit, Struktur, Agentenregeln und dauerhafte Codebindung |
| `#1015` | [#1003/D11] Menschliches und modellübergreifendes Produktverständnis abschließend abnehmen |
| `#1032` | [#1003/Q6] Realen Issue-to-Merge-Ablauf mit Screenshots und SVGs nachvollziehbar machen |
| `#1033` | [#1003/Q7] Erweiterten integrierten Dokumentationsstand real verständlich abnehmen |
| `#1046` | EPIC – S.A.M.U.E.L. Product Completion & Feature Cross-Check: Offene Issues systematisch abschließen und Golden-Readiness herstellen |
| `#1048` | docs: Fehlende reale Ablauf- und Zustandsaufnahmen gesammelt nachliefern |
