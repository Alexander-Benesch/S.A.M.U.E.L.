---
id: ADR-0706
title: Unveränderliche lokale Releases mit atomarem Aktivierungszeiger
status: accepted
decision_issue: 706
decision_date: 2026-09-02
decision_digest: sha256:fb08a88eefe27545bdf06f2743656fc879fb4d583b6e1046b92cc6492c7b143c
supersedes: []
superseded_by: []
---

# Unveränderliche lokale Releases mit atomarem Aktivierungszeiger

## Kontext

Ein Entwicklungscheckout, eine darin wiederverwendete Editable-venv und beim
Paketbau erzeugte `samuel.egg-info`-Metadaten können gleichzeitig
unterschiedliche Produktstände repräsentieren. Die vorhandenen
Versionsprüfungen erkannten diese reale Kollision fail-closed. Ein
Kundenupdate darf sie nicht erst im laufenden Dienst entdecken und darf
Konfiguration, Secrets, State, Evidence oder Workspaces nicht zusammen mit dem
Core überschreiben.

OCI besitzt mit dem unveränderlichen Image-Digest und externen Mounts bereits
eine etablierte Austauschgrenze. Für Installationen ohne Container fehlte die
entsprechende lokale Grenze.

## Entscheidung

Lokale Releaseinstallationen verwenden fünf disjunkte Pfadklassen:

- `/opt/samuel/releases/<version>` enthält genau einen unveränderlichen
  Produktstand mit eigener venv, Console-Launcher und Release-Receipt;
- `/opt/samuel/current` ist der atomar ersetzte Symlink auf genau einen zuvor
  vollständig geprüften Release;
- `/etc/samuel` enthält Operator-Konfiguration und Secrets;
- `/var/lib/samuel` und `/var/log/samuel` enthalten Runtime-State/Evidence
  beziehungsweise Prozesslogs;
- `/srv/samuel` enthält Workspaces, Backups und den reservierten, nicht
  automatisch geladenen Bereich `extensions`.

`samuel-release stage` bindet Release-Manifest, Wheel und den veröffentlichten
hashgebundenen Runtime-Lock an dieselbe Version und vollständige Revision. Es
installiert direkt am neuen, noch inaktiven Versionspfad eine
Geschwister-venv und prüft Console-Script,
Paketmetadaten, Importpfad, Version und Revision mit isolierter
Python-Auflösung. Eine venv wird wegen ihrer absoluten Interpreterpfade nicht
nachträglich verschoben. Erst ein erfolgreicher Probe-Lauf erzeugt das
Receipt und macht den Pfad aktivierbar; ein Teilstand bleibt zur
Operatorprüfung sichtbar. Ein
vorhandenes Versionsverzeichnis wird niemals verändert.

`samuel-release activate` prüft das Receipt erneut und ersetzt `current` per
atomarem Rename. Ein erwarteter bisheriger Stand ist als Compare-and-swap-
Bedingung verpflichtend. Unklassifizierte Dateien im unveränderlichen
Installationswurzelverzeichnis, fremde Symlinks und Identitätswidersprüche
blockieren. Es gibt keinen stillen Fallback.

Die erstmalige Layoutinitialisierung kopiert ausgelieferte Defaults nur in
eine leere Konfigurationswurzel und materialisiert absolute Persistenzpfade.
Ein erneuter Lauf mischt keine Defaults in Betreiberdateien. Der Setup-Wizard
konfiguriert anschließend diese externe Struktur. Updates führen den Wizard
nicht erneut aus und ändern weder Konfiguration noch wirksame Policy, Trust
Roots, Credentials, State, Logs/Evidence, Backups, Workspaces oder
Erweiterungen.

Der Releaseprozess veröffentlicht den Runtime-Lock als eigenes, durch das
Release-Manifest geprüftes Asset. Die lokale Installationshilfe löst nur
Python-Abhängigkeiten aus diesem Hash-Lock und installiert das gebundene Wheel
ohne Dependency-Auflösung. Sie startet oder stoppt keine Dienste und migriert
keinen State. Service-Stopp, State-Backup, Aktivierung, Neustart sowie Doctor,
Health und Funktionsabnahme bleiben sichtbare Operatoraktionen.

## Self-Mode und Erweiterungen

Self-Mode darf Änderungen als normalen Candidate im getrennten Workspace
erzeugen. Er erhält weder Schreibrecht auf `/opt/samuel` noch Autorität zum
Aktivieren eines Releases. Ein Candidate kann nach Review, Gates und Release
ein neues Artefakt liefern; ausschließlich der Operator darf dieses
aktivieren. `/srv/samuel/extensions` ist eine reservierte Persistenzklasse,
aber bis zu einem eigenen Capability-Vertrag kein impliziter Python-, Plugin-
oder Adapter-Suchpfad.

## OCI-Entsprechung

Beim Containerbetrieb bleibt der veröffentlichte OCI-Digest die einzige
Core-Authority. Externe Config-, State- und Workspace-Mounts werden erhalten;
ein neuer Digest ersetzt das Image vollständig. Die lokale Releasehilfe baut
keinen parallelen Container-Updater und keine Deployment-Orchestrierung.

## Konsequenzen und Grenzen

- `install.sh` bleibt der ausdrücklich nicht qualifizierte
  Entwicklungscheckout-Pfad.
- Ein laufender Prozess wechselt seinen Code nicht durch den Symlinktausch;
  der Operator startet den Dienst anschließend kontrolliert neu.
- Ein Code-Rollback ist nur mit schema- und statekompatiblen Daten oder einem
  passend gebundenen Backup zulässig. Es gibt keinen automatischen
  Datenrollback.
- Systempakete wie Git und systemd sowie Dateieigentümer bleiben
  Betriebsvoraussetzungen, nicht Aufgabe eines neuen Paketmanagers.
- Der reale Kundenclaim entsteht erst nach einem Upgrade derselben
  veröffentlichten Artefakte in der unabhängigen D0-Installation. Unit- und
  Integrationstests allein qualifizieren keinen Release.

## Verworfene Alternativen

- Überschreiben einer bestehenden venv oder eines Checkout-Baums;
- erneutes Ausführen des Setup-Wizards bei jedem Update;
- Vermischen von Core, Betreiberkonfiguration und Self-Mode-Ergebnissen in
  einem beschreibbaren Verzeichnis;
- automatisches Laden beliebiger Dateien aus `extensions`;
- ein eigener allgemeiner Updater, Paketmanager oder Service-Orchestrator;
- verdeckter Rückfall auf die alte Runtime nach einem fehlgeschlagenen
  Wechsel.
