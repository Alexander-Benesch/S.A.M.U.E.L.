---
id: ADR-0693
title: Technische Gesundheit, Betriebsbereitschaft und Qualification getrennt projizieren
status: accepted
decision_issue: 693
decision_date: 2026-09-18
decision_digest: sha256:68decffdb8614f1476b7d08326b5707f39327cb2686a3ed7cd97ee2d4c77e87c
supersedes: []
superseded_by: []
---

# Technische Gesundheit, Betriebsbereitschaft und Qualification getrennt projizieren

## Kontext

Der bisherige Health-Aufruf vermischte Prozess- und Konfigurationszustand mit
der Aussage, ein Workflow sei betriebsbereit. Ein grüner Check konnte weder
eine externe LLM-Verbindung noch Branchschutz oder Auditintegrität belegen.
Zugleich führte der lesende Dashboard-Health-Endpunkt aktive SCM-Zugriffe aus.
Nach Logrotation, Restore oder Ablauf eines Diagnosefensters durfte ein
Integritätsfehler nicht still als behoben erscheinen.

## Entscheidung

Der bestehende Health-Vertrag behält `healthy`, `critical` und `checks` bei und
ergänzt drei klar getrennte Projektionen:

- `technical_health` beschreibt den aktuellen begrenzten Prozess-, Config-,
  State-, Authority-, SCM- und LLM-Konfigurationscheck;
- `operational_readiness` beschreibt ausschließlich den Zweck
  `workflow_execution`; ohne externe LLM-Liveprobe bleibt sie `unknown`;
- `qualification` zeigt die instanzgebundenen aktuellen Ergebnisse von
  `samuel doctor` und `samuel audit verify`. Nur beide aktuellen positiven
  Fachprüfungen ergeben `passed`.

Die Projektionen verwenden den vorhandenen `run_projections`-Store. Sie sind
an die State-Instanz, Prüfzeit und einen Evidence-Digest gebunden. Nach einer
Stunde werden sie `stale`; fehlende Daten sind `not_checked`. Ein erfolgreicher
Fach-Recheck darf einen Fehler auflösen und bindet dafür dessen vorherigen
Digest. Fehlende Auditlogs oder ein fehlender Auditkey überschreiben einen
aktiven beziehungsweise nach Restore veralteten Integritätsfehler nicht.

Viewer und der Dashboard-Health-Endpunkt lesen ausschließlich die bereinigte
Projektion. Der aktive Self-Check bleibt eine operative Provideraktion und
verlangt `RUN_PROVIDER_PROBES`. Der persistente State behauptet keinen
`resume_enabled`-Wert; diese wirksame Aussage kommt allein aus dem
Resume-Runtime-Resolver. Setup meldet Konfigurationsabschluss und Doctor-
Ergebnis getrennt.

## Konsequenzen und Grenzen

Die Projektion erteilt keine Gate-, Workflow-, Merge- oder
Release-Qualification-Authority. Doctor, Auditverifier und Fachcapabilities
bleiben die Quellen ihrer jeweiligen Wirkung. Publish-/Release-Qualification
bleibt in #759 getrennt. Der Docker-Healthcheck bleibt ein enger technischer
Startupcheck.

Gespeichert werden Status, Instanzbindung, Zeit, Digest und begrenzte Zähler
oder feste Checknamen, keine Credentials, Providerantworten oder Auditpayloads.
Projectionfehler bleiben nach dem vorhandenen State-Vertrag nicht blockierend.
Die reale Betriebs-, Restore-, Integritäts- und Permission-Qualification auf
der Referenzinstallation ist vor Abschluss von #693 weiterhin erforderlich.

## Verworfene Alternativen

- ein zweiter Health-, Incident- oder Monitoringstore;
- fehlende oder abgelaufene Evidence als bestanden zu behandeln;
- aktive Providerprobes aus Viewer-GETs;
- Health als Ersatz für Doctor, Auditverifikation oder Release-Qualification;
- ein persistenter Defaultwert, der Runtime-Resume-Authority vortäuscht.
