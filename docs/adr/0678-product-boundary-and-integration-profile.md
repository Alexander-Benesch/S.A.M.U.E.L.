---
id: ADR-0678
title: Produktgrenze, Standard-Integrationsprofil und Referenzbetrieb
status: accepted
decision_issue: 678
decision_date: 2026-08-30
decision_digest: sha256:ad35bdc2df3e1ad8cce509fbee2d6d86b588c524f62d1be31a2d79e6f982dff5
supersedes: ["ADR-0619"]
superseded_by: []
---

# Produktgrenze, Standard-Integrationsprofil und Referenzbetrieb

## Kontext

S.A.M.U.E.L. enthält bereits einen Referenz-Worker, SCM-Adapter, Gates,
Dashboard, lokalen State, Dokumentation und Gitea-Betriebsartefakte. Diese
Out-of-the-box-Fähigkeiten sind nützlich. Gleichzeitig wuchsen mehrere offene
Issues von einem realen Finding unmittelbar zu vollständigen eigenen
Subsystemen: Sandbox-, Plugin-, Review-, IAM- oder Dokumentationsplattform.

Die Architektur verlangte bereits Ports und „Integration statt Nachbau“, ließ
aber offen, wie mitgelieferter Standardbetrieb, Fremdprovider und
Generalisierung voneinander getrennt werden. Insbesondere widersprach der
geplante eigene Sandbox-Port aus ADR-0619 dem erklärten Nicht-Ziel, keine
Prozesssandbox unter S.A.M.U.E.L.-Namen neu zu bauen. Zugleich fehlte ein realer
installierter Referenzlauf als regelmäßiger Wirksamkeitsnachweis.

## Entscheidung

### Produktkern

S.A.M.U.E.L. besitzt und verantwortet:

- den freigegebenen Änderungsauftrag und Acceptance Contract,
- den unveränderlichen `EvaluationSubject`,
- die Bindung, Validierung und begrenzte Projektion von Evidence,
- die wirksame Policy und ihre Fehlersemantik,
- die nachvollziehbare Entscheidung `PR`, `Block` oder `Review`.

Fachwerkzeuge für Codeerzeugung, CI-Ausführung, Scanning, Dokumenterzeugung,
Identity, Publishing oder Observability werden nicht allein deshalb Core, weil
S.A.M.U.E.L. eine sofort nutzbare Referenz dafür mitliefert.

### Dreiebenenmodell

Die folgende ursprüngliche Klassifikation wird durch den
Klarstellungsnachtrag #681 am Dokumentende auf austauschbare
Nicht-Core-Capabilities und tatsächlich benötigte Ebenen begrenzt.

Jede Capability wird als **Core-Vertrag**, **mitgelieferte
Referenzimplementierung** und **externer Adapter/Provider** klassifiziert.

Die Referenzimplementierung ermöglicht einen unterstützten Standalone-Betrieb,
verwendet aber dieselbe fachliche Grenze wie externe Provider und erhält keine
Sonderautorität. „Austauschbar“ bedeutet nicht „nicht mitgeliefert“ und nicht
„bestehende Funktion entfernen“.

### Integrationsprofil

Es gibt kein einzelnes Universalprotokoll für alle Rollen. S.A.M.U.E.L.
verwendet einen kleinen eigenen Capability-Vertrag und etablierte
rollenbezogene Standards:

- OpenAPI/HTTP/JSON für synchrone APIs,
- CloudEvents und soweit passend CDEvents für Ereignisse,
- in-toto Statements sowie optional DSSE/Sigstore für Attestations,
- SARIF, ein festgelegtes JUnit-Profil, CycloneDX/SPDX und SCM-native Checks
  für domänenspezifische Evidence,
- MCP optional für LLM-Werkzeuge und Kontext,
- A2A erst bei einem realen autonomen Fremd-Worker,
- OIDC/OAuth für externe Identität,
- OCI beziehungsweise vorhandene Sprach-/Systempakete für Distribution,
- OpenTelemetry für externe Observability.

Der gemeinsame S.A.M.U.E.L.-Vertrag enthält nur Capability-ID/-Version,
Input-/Outputvertrag, Evidenceformate, benötigte Rechte, Transport und
Health/Readiness. Submit/Status/Result/Cancel gelten nur für aktive
Jobprovider. Passive Evidence-, Scanner- oder Publisheradapter werden nicht in
einen künstlichen gemeinsamen Lifecycle gezwungen.

### Candidate-Ausführung

S.A.M.U.E.L. baut keine eigene allgemeine Prozesssandbox, Containerplattform
oder CI-Engine. Kandidatenkontrollierte Ausführung soll außerhalb des Core in
einem austauschbaren Execution-/CI-Provider stattfinden. S.A.M.U.E.L. nimmt
von dort ausschließlich gebundene Evidence an und prüft Repository,
Base-/Head-SHA, Contract, Policy, Workflow, Tool/Image, Provider, Freshness und
Replay.

#679 entscheidet und implementiert diesen Übergang mit #520/#521. Der heutige
lokale IMPORT-/TEST-Pfad bleibt bis zum vollständig belegten atomaren Cutover
als begrenzter Legacy-Pfad bestehen. Er ist keine Sandbox und erhält keine
neue Zielautorität. ADR-0619 ist damit superseded.

### Referenzinstallation

#658 wird dreistufig geführt:

1. D0: sofortiger interner Golden Path aus veröffentlichtem Paket/Image gegen
   ein eigenes Demo-Repository, einschließlich echtem Blockierfall;
2. D1: reproduzierbares Setup, Reset und Release-Acceptance;
3. D2: öffentliche bereinigte Demo erst nach Auth-/HTTPS-/Secret-
   Betriebsabsicherung.

D0 ergänzt Tests als Release-Qualification. Deploymentlokale Gitea-/Runner-
Eigenschaften werden ausdrücklich als Referenzadapter beziehungsweise
Infrastrukturvoraussetzung bezeichnet.

## Driftregeln

Vor jeder neuen oder wesentlich erweiterten Capability müssen Problem,
vorhandener Stand, Dreiebenenzuordnung, geprüfte Standards/Fremdwerkzeuge,
genau eine Authority, Nicht-Ziele und realer Referenznachweis dokumentiert
werden.

Generalisierung über den schmalen fachlichen Port hinaus erfolgt erst bei einem
zweiten realen Adapter oder Anwendungsfall. Erzeugt ein Finding gleichzeitig
Port, Schema, Store, Events, Dashboard, Migration, Doctor und Conformance-
Suite, ist eine neue Designfreigabe erforderlich. Security- und
Authority-Grenzen bleiben von der Second-adapter-Regel unberührt.

Konfigurationswerte ohne nachgewiesene Wirkung, gemischte Providerautorität und
Dokumentclaims ohne Code-/Betriebsnachweis sind Driftfindings.

## Konsequenzen

- #520 wird als minimale Standard-Evidence-Grenze an einem echten
  Gitea-Actions-/SCM-Check-Adapter vorgezogen.
- #521 beginnt mit passiver Candidate Submission; aktive Workersteuerung folgt
  erst einem realen Bedarf.
- #619 wird durch #679 ersetzt; das Securityfinding bleibt bis zum Cutover
  sichtbar.
- #639 beginnt mit öffentlicher API, Kompatibilität, Enable/Disable und externer
  Conformance-Fixture, nicht mit einer vollständigen Lifecycle-Plattform.
- #422 liefert lokalen sicheren Auth/RBAC-Standardbetrieb und eine spätere
  externe Identity-Grenze, aber kein allgemeines IAM.
- #468 bleibt Review-/Merge-Authority; Review-Produzenten sind Provider.
- #635 bleibt kleiner Wiki-Pilot; #636 integriert vorhandene Producer,
  Verifier und Publisher, statt sie nachzubauen.
- Bereits implementierte Funktionen werden nicht aufgrund dieser
  Zielentscheidung entfernt. Jeder Wechsel benötigt funktionsgleichen
  Ersatz, gebundene Positiv-/Negativevidence und einen atomaren Cutover.

## Verworfene Alternativen

- eine universelle Plugin-, CI-, Sandbox-, Agenten- oder IAM-Plattform als
  Voraussetzung jeder Integration;
- ein proprietäres Universalformat anstelle von Standardformatadaptern;
- Gitea, den Referenz-Worker oder lokale Provider als Core-Semantik zu
  deklarieren;
- vorhandene lokale Funktion vor einem bewiesenen Ersatz zu entfernen;
- Zielarchitektur ausschließlich aus Unit-/Mocktests als funktionsfähig zu
  erklären.

## Klarstellungsnachtrag vom 30. August 2026 (#681)

Der ursprüngliche Entscheidungstext bleibt als angenommene Historie erhalten.
Die folgenden Präzisierungen begrenzen seine Reichweite, ohne eine
Runtimeänderung oder einen neuen Plattformauftrag zu begründen:

- Das Dreiebenenmodell ist ein Architekturvokabular für austauschbare
  Nicht-Core-Capabilities, keine Pflicht, für jede Fähigkeit sofort drei
  Implementierungen zu bauen. Implementiert werden nur benötigte Ebenen. Ein
  externer Port entsteht bei einem realen zweiten Provider/Anwendungsfall oder
  früher wegen einer Security-/Authority-Grenze.
- Producer, Agenten und Provider erhalten keine implizite Autorität. Rechte,
  Credentials, Werkzeuge sowie Netz- und Dateizugriffe sind minimal,
  zweckgebunden, zeitlich beziehungsweise rungebunden und nachvollziehbar zu
  delegieren. Diese Anforderung macht S.A.M.U.E.L. nicht zum IAM-Provider.
- Self-Mode darf Änderungen am eigenen Core-Quellcode als normalen Candidate
  vorschlagen. Er darf die laufende Installation, Trust Roots, den Updatepfad
  oder die wirksame Freigabepolicy nicht selbst autorisiert überschreiben;
  Core-Updates bleiben operatorgebunden und durchlaufen den normalen
  PR-/Evidence-/Policy-Pfad.
- Subject-Bindung ist notwendig, aber für externe Evidence nicht hinreichend.
  Issuer/Vertrauensprofil, Provenance und Integrität, Policy, Tool- und
  Ausführungsumgebung, Freshness sowie Replay-Schutz gehören zum
  Annahmevertrag. Candidate und Producer autorisieren ihre eigene Evidence
  nicht allein durch deren Erzeugung.
- Betriebliche Wirksamkeitsclaims binden die nachgewiesene Kombination aus
  S.A.M.U.E.L.-Version, Policy, effektivem Modell/Provider,
  Prompt-/Agent-Konfiguration, Toolchain und Berechtigungsprofil. Wesentliche
  Änderungen erzwingen eine neue Evaluation, nicht automatisch einen neuen
  Produktrelease.
- Menschliche Zustimmung ist nur authentifiziert, aktions- und
  subjectgebunden sowie auditierbar autoritativ. Bestätigungswiederholung ist
  kein Ersatz für technische Policy.
- OpenTelemetry und die versionierten GenAI Semantic Conventions sind ein
  bevorzugter, reife- und privacyabhängiger Observability-Anschluss. Sie
  verleihen Telemetrie keine Freigabeautorität; sensible Inhalte bleiben
  opt-in.
