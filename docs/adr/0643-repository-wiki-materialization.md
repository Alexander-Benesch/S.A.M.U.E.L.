---
id: ADR-0643
title: Repository-lokale Wiki-Materialisierung und providerneutrale Publikation
status: accepted
decision_issue: 643
decision_date: 2026-08-29
decision_digest: sha256:4b303c53e7db388ccb9aed8b3129d0022cf88d0f35b4659ad0b1edc1328c15fd
supersedes: []
superseded_by: []
---

# Repository-lokale Wiki-Materialisierung und providerneutrale Publikation

## Kontext

ADR-0635 und #640 führten den deterministischen Wiki-Renderer zunächst unter
`build/wiki/` ein. Für den laufenden Eigenbetrieb soll die lokale Projektion an
einem stabilen, leicht auffindbaren Pfad im Repository verfügbar sein. Das
Repository wird außerdem künftig zwischen Gitea und GitHub synchronisiert;
lokale Erzeugung und externe Veröffentlichung dürfen deshalb keine
Providerabhängigkeit erhalten.

Ein Tracking der generierten Seiten im Hauptrepository ist mit der heutigen
Bindung nicht konsistent: Jede Seite nennt den vollständigen `head_sha`. Ein
Commit der Ausgabe erzeugt selbst einen neuen Head und macht die eingebettete
Bindung unmittelbar veraltet.

## Entscheidung

Der kanonische lokale Ausgabeort ist `<repository>/wiki/`. Das Verzeichnis
bleibt ignorierte, nicht autoritative Buildausgabe und gehört weder zum aktiven
Dokumentinventar noch zu Paket-, Runtime-State- oder Backup-Artefakten. Diese
Entscheidung ersetzt ausschließlich den Ausgabeort aus ADR-0635; dessen
Informationsarchitektur, Quellenhierarchie, Digest- und Receipt-Vertrag gelten
unverändert weiter.

Der Renderer erzeugt zuerst ein vollständiges Staging-Bundle und ersetzt eine
vorhandene Ausgabe mit einem rollbackfähigen Verzeichnistausch; ein
Schreibfehler darf keinen halb geschriebenen Stand als aktuell hinterlassen.
Der Source-Installer und der dokumentierte Source-Updatepfad materialisieren
das Wiki nach erfolgreicher Paketinstallation. Beliebige direkte
Git-Operationen außerhalb dieses Pfads lösen keinen versteckten Hook aus. Ein
expliziter lokaler Check vergleicht Seitenbytes und den stabilen Receipt-Inhalt
mit dem aktuell gebundenen Repository-Stand und meldet fehlende, veraltete oder
manuell veränderte Ausgabe fail-closed.

Der normale CI-Check setzt kein ignoriertes `wiki/` voraus. Er prüft weiterhin
Manifest, Coverage und deterministische Erzeugbarkeit aus einem frischen
Checkout. Damit bleibt die lokale Bequemlichkeit von der Repository- und
Release-Autorität getrennt.

## Publisher-Grenze

`wiki/` ist das providerneutrale Eingangsartefakt. Eine spätere
Veröffentlichung nach Gitea Wiki, GitHub Wiki oder mehreren Zielen erfolgt
ausschließlich über austauschbare Publisheradapter. Der Publisher bindet das
Eingangsartefakt über dessen `artifact_digest`. Falls der Ziel-Pfadraum eine
Projektion etwa von lokalen Quelllinks verlangt, weist das Publication Receipt
zusätzlich den Digest der exakten veröffentlichten Bytes, Ziel, Zielrevision
und externe Wirkung aus. Eine solche Projektion darf Facts und Aussagegrenzen
nicht verändern.

Renderer, lokaler Lifecycle und Build-Receipt kennen keine SCM-API,
Provider-URL, Publisher-Credentials oder Wiki-Zielrevision. Die Synchronisation
des Hauptrepositories nach GitHub veröffentlicht das ignorierte lokale
Artefakt nicht automatisch; diese externe Wirkung bleibt #635 P3.

## Konsequenzen

- Betreiber finden die aktuelle lokale Navigation stabil unter `wiki/`.
- GitHub-Synchronisation erzwingt keine Gitea-Abhängigkeit und umgekehrt.
- Das Wiki ist nach Clone erst nach dem dokumentierten Build-/Installationspfad
  vorhanden; diese Grenze wird nicht durch ein unbemerktes Git-Hook-Versprechen
  verdeckt.
- Eine spätere getrackte Docs-Site benötigt einen anderen Binding- und
  Publication-Vertrag und ist nicht Bestandteil dieser Entscheidung.
- Fehlende lokale Materialisierung blockiert nicht PR oder Release; ein
  lokaler Materialisierungscheck darf sie jedoch nicht als aktuell ausgeben.

## Rollout-Grenze

Die Umstellung ist abgeschlossen, wenn Renderer, Manifest, relative Links,
Installer, dokumentierter Updatepfad und lokaler Check gemeinsam auf `wiki/`
zeigen, der frische CI-Checkout ohne vorhandene Ausgabe besteht und ein Build
auf dem gemergten Main-Stand dort erfolgreich materialisiert wurde. Externe
Gitea-/GitHub-Publikation ist kein Abschlusskriterium dieses Issues.
