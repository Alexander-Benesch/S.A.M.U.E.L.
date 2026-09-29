---
id: ADR-0649
title: Einquellige Content-Blöcke für eigenständig lesbare Wiki-Seiten
status: accepted
decision_issue: 649
decision_date: 2026-08-29
decision_digest: sha256:3ce19191f8617441c008072fac2c089169b3009b2140e5e63f3da1804926be6a
supersedes: []
superseded_by: []
---

# Einquellige Content-Blöcke für eigenständig lesbare Wiki-Seiten

## Kontext

ADR-0635 führte zehn stabile Wiki-Seiten als deterministische, nicht
autoritative Navigation über den aktiven Dokumentbestand ein. ADR-0643 legte
den lokalen Materialisierungs- und providerneutralen Publikationsvertrag fest.
Der reale P1-/P3-Stand war technisch gebunden und reproduzierbar, enthielt auf
den Wiki-Seiten selbst aber überwiegend Aufgabenwege, Dokumentklassen und
Überschriftenlisten. Für das grundlegende Systemverständnis musste der Leser
die Wiki-Seite verlassen und die Primärdokumente einzeln zusammensetzen.

Eine zweite frei redaktionelle Wiki-Fassung würde dieses Nutzwertproblem lösen,
aber eine neue manuelle Wahrheitsquelle und damit denselben Drift erzeugen, den
der Dokumentvertrag verhindern soll. Die bestehenden aktiven Dokumente dürfen
zugleich nicht aufgegeben werden: Sie sind weiterhin die gepflegte Quelle für
Architektur, Betrieb, Entscheidungen und ausführliche Referenz.

## Entscheidung

Das Wiki erhält einen versionierten hybriden Content-Block-Vertrag. Code und
ausgelieferte Konfiguration bleiben technische Runtime-Authority. Bestehende
aktive Dokumente bleiben die einzige redaktionell gepflegte Langform. Lokale,
Gitea- und spätere GitHub-Wikis sind ausschließlich generierte Zielartefakte
desselben Builds und werden nicht manuell gepflegt.

Zwei Blocktypen sind zulässig:

1. source_section wählt genau eine eindeutig benannte Überschriftensektion
   eines aktiven Dokuments. Der Block bindet seine stabile ID, Quellpfad,
   Dokumentklasse, exakten Heading-Selektor und Digest der ausgewählten
   Abschnittsbytes.
2. resolved_fact verwendet einen ausdrücklich zugelassenen Resolver aus
   tools/control_matrix.py. Der Block bindet stabile ID, Resolverselektor,
   Resolverherkunft, Dokumentklasse und Digest der kanonisch serialisierten
   Facts.

Jede der zehn stabilen Page-IDs besitzt mindestens einen Content-Block.
Primärquellen-Coverage und Content-Nutzung bleiben verschiedene Relationen:
Jedes aktive Dokument gehört weiter genau einer primären Wiki-Seite, kann aber
als explizit gebundener Inhaltsblock auf einer weiteren Seite verwendet werden.

## Fail-closed-Bindung

Der Build blockiert mindestens bei:

- fehlender, doppelter oder nicht zur Page-ID gehörender Block-ID;
- unbekanntem Blocktyp oder Resolver;
- fehlendem oder mehrdeutigem Überschriftenselektor;
- Quellpfad außerhalb des Repositorys oder außerhalb des aktiven
  Dokumentvertrags;
- abweichender Dokumentklasse;
- stale Abschnitts- oder Fact-Digest;
- fehlendem Linkziel oder fehlendem Markdown-Anker;
- einem Link, der den Repository-Scope verlässt.

Der Digest ist eine Reviewgrenze und wird nicht beim normalen Build
automatisch passend geschrieben. Eine Quellenänderung verlangt damit eine
bewusste Prüfung des betroffenen Wiki-Inhalts.

## Rendering

Ausgewählte Quellabschnitte werden mit normalisierten Überschriften in den
Kerninhalt der Zielseite übernommen. Tabellen, Listen und Codeblöcke bleiben
erhalten. Relative Links werden aus dem ursprünglichen Dokumentkontext auf
Repositoryziele umgeschrieben und bei der externen Publikation anschließend
auf das gebundene Source-Head projiziert. Interne Anker bleiben lokal, wenn
das Ziel im übernommenen Abschnitt vorhanden ist; andernfalls führen sie zur
gebundenen Primärquelle.

Resolved Facts werden nicht aus generierter Wiki-Prosa zurückgelesen. Der
Renderer ruft ausschließlich die bereits vorhandenen Governance-Resolver auf
und stellt deren Ergebnis als gekennzeichnete Tabelle samt Fact-Digest dar.

## Verworfene Alternativen

- Zehn neue frei gepflegte Wiki-Quelldokumente wurden wegen der zusätzlichen
  Drift- und Reviewfläche verworfen.
- Vollständiges blindes Kopieren aller aktiven Dokumente wurde wegen fehlender
  Informationsarchitektur und schlechter Lesbarkeit verworfen.
- Eine sofortige LLM-Zusammenfassung wurde verworfen, solange der portable
  Claim-, Verifier- und Evidence-Vertrag aus #520/#636 nicht verfügbar ist.
- Das Aufgeben der bestehenden Docs wurde verworfen, weil sie weiterhin
  Primärquellen, Betriebsverträge und reviewbare Langform sind.

## Konsequenzen

- Grundlegende Architektur-, Pipeline-, Komponenten-, Assurance-, Betriebs-,
  Security- und Entscheidungsinformationen stehen direkt im Wiki.
- Eine redaktionelle Änderung erfolgt weiterhin genau einmal im zuständigen
  aktiven Dokument; das Wiki wird danach neu gebaut und publiziert.
- Ändert sich ein maschinenlesbarer Fact, wird sein Block-Digest stale und
  erzwingt die Review derselben Darstellung.
- Der Renderer bleibt offline, deterministisch und ohne LLM-, Plugin-,
  EvidenceEnvelope- oder Gate-Abhängigkeit.
- Der Publishervertrag aus ADR-0643 bleibt unverändert. Ein zweiter GitHub-
  Wiki-Remote kann dasselbe gebundene Artefakt unabhängig veröffentlichen.

## Rollout-Grenze

Die Entscheidung ist umgesetzt, wenn alle zehn Seiten gebundene Kerninhalte
enthalten, die Mutations- und Linktests die Fehlerpfade belegen, ein doppelter
Build byteidentisch ist und die nach grüner PR-/Push-CI publizierte Gitea-Wiki
gegen Source-Head, Marker, Digests, Inhalt und No-op read-only geprüft wurde.
