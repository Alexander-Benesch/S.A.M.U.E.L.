# Issue Workstream Map

Diese Reihenfolge folgt dem fruehesten blockierenden Workflowpunkt. Sie ist
keine neue Architektur und ersetzt nicht die einzelnen Issuevertraege.

## P0 — Positive-E2E- und Authority-Blocker

Reihenfolge: #822/#679 (Route real bereit) -> #905/#845/#843 (SCM, Subject und
wirksame Config) -> #846/#847/#828 (Planning-/CLI-/Implementationgrenzen) ->
#880 (Human-MANUAL-UX) -> #468 (Review) -> #859 (zusammenhaengender Lauf) ->
#658 (releasegebundener Formal D0).

Route-, Setup- und Authority-Probes koennen parallel vorbereitet werden. Der
abschliessende #859-Lauf muss dieselbe unveraenderte Strecke verwenden; einzelne
alte PASS-Abschnitte duerfen nicht zusammengesetzt werden. #658 beginnt erst
nach einem immutable Release und darf nicht mit Development-E2E kombiniert
werden.

Abschluss: bounded Routeprobes, Setup/Doctor-Readback, kompletter neuer
Development-E2E, Human Merge, danach frische Release-/D0-Evidence.

## P1 — Recovery, Operability und Self-Check

Reihenfolge: #921 (vollstaendige Diagnosebasis) -> #920 (sicherer Re-Entry) ->
#482/#668 (State-/Retentionauthority) -> #691/#693/#694/#823/#889/#894
(Installation und reale Betriebsabnahme) -> #897.

#921 besitzt ausschliesslich die fehlende backendneutrale Full-System-
Aggregation und den kritischen Preflight. #693/ADR-0693 bleiben Authority fuer
Health-, Readiness-, Qualification- und aktive Self-Check-Semantik; #694 fuer
Required-Check-Diagnose und #905 fuer native Webhook-Delivery. Es entsteht
keine zweite Health-Architektur, automatische Reparatur oder Gitea-
Corekopplung. #920 darf Ownership-, Approval-, Candidate- und
Gatebindungen nicht abschwaechen. Retention und Workflow-Recovery bleiben
getrennte Authoritybereiche.

Abschluss: negative State-/SCM-/Runner-/Providerproben, restartfeste
Re-Entry-Matrix und reale non-root-/recreate Tests.

## P1 — Determinismus, Contract und Prompt/Parser

#892 und #878 fuehren; danach verbleibende Qualification in #575, #549 und
#521. Die TEST-Runner-/Selectorfehler sind technisch durch #754/#756/#902/#916
geschlossen und werden nur als Regression ueberwacht. Provider-Truncation ist
Route-/Qualification-Evidence und kein Parserbug.

Promptresolver/Profile und Parsergrammar duerfen parallel analysiert werden;
Promptaenderungen benoetigen eigene Product-Authority und gehoeren nicht in
Docs-/Qualification-Fixes.

## P2 — Observability, UX und Statusprojektion

Reihenfolge: #890 (kausales Modell) -> #891 (Route/current/last-call) -> #830
(reale Dashboardabnahme) -> #828/#897. #880 gehoert fuer seinen Authoritypfad
zu P0, die reine UX kann parallel hier bearbeitet werden.

Labels und Dashboardstatus bleiben Projektion. Dieser Workstream darf keine
Approval-, Merge-, Retry- oder Gateauthority aus UI-Zustand ableiten.

## P2 — Dokumentation, Release und Statusdrift

#812, #829, #636, #639, #840 und dieses Housekeeping-Paket. Wiki-Publish und
GitHub-Sync folgen erst auf Human Merge. Historische Releaseevidence bleibt
unveraendert; keine a26-Claims werden aus dem geschlossenen PR #857 uebernommen.

## P3 — Features und Post-Golden

#873, #878, #883, #888 und #922; ausserdem #811, #821 und #567 als
menschlich/infrastrukturell gebundene Entscheidungen. Diese Arbeit beginnt
nicht als Voraussetzung fuer den naechsten positiven Hauptpfad, sofern ihr
eigener Vertrag keine aktuelle Sicherheitsblockade belegt.

## Gemeinsam oder nacheinander

- #822/#679 und #900/#905 liefern den Preflight fuer #859; #921 aggregiert
  spaeter die wiederverwendbaren Readinessbefunde, erteilt selbst aber keine
  E2E-Authority.
- #846/#847 und #828 betreffen verschiedene Planning-/CLI-/Implementation-
  Fehlergrenzen; ihre automatisierten Fixes bleiben als Regression erhalten,
  waehrend #859 die reale Gesamtstrecke prueft.
- #904/#908/#910 sind integrierte Authority-/Webhook-/MANUAL-Fixes. #880
  traegt nur den verbleibenden Human-UX-/Transportvertrag; #859 darf die alten
  Failure-Subjects nicht zu PASS kombinieren.
- #857 ist ein geschlossenes historisches a26-Kandidaten-Changelog. Sein
  Development-Restpunkt ist in #859 (Kommentar #44960), der spaetere frische
  Formal-D0-Restpunkt in #658 (Kommentar #44956) sichtbar.
- #840 und #888 sind Koordinations-/Nachbewertungstraeger. #873/#883/#922
  sind nachrangige eigenstaendige Features/Vertraege, sofern keine neue
  konkrete Sicherheitsblockade entdeckt wird.

Human-/Infrastrukturentscheidungen bleiben separat: #811 (Python-Support),
#567 (Runner-Netz/L2) und #821 (lokale Credentialquellen). Keine dieser
Entscheidungen wird aus einem gruenen Unit-Test abgeleitet.
