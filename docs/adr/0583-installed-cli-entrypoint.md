---
id: ADR-0583
title: Installierter Console-Entry-Point als einzige Betriebsgrenze
status: accepted
decision_issue: 583
decision_date: 2026-08-28
decision_digest: sha256:47ccd03aa93b5129435874d38f702977856e08410dea3909bef33e13d6b3216f
supersedes: []
superseded_by: []
---

# Installierter Console-Entry-Point als einzige Betriebsgrenze

## Kontext

Python setzt bei `python -m samuel` das aktuelle Arbeitsverzeichnis an eine
importwirksame Stelle. Enthält ein potenziell unvertrauenswürdiges
Zielrepository ein eigenes Top-Level-Paket `samuel`, wird dieses vor der
installierten Distribution gefunden. Fremdcode läuft damit bereits bei der
Modulauflösung und folglich vor jeder Herkunftsprüfung, die der echte
S.A.M.U.E.L.-Prozess ausführen könnte.

Der reale Rollout aus #577 hat genau diesen Herkunftswechsel belegt. Der über
`pyproject.toml [project.scripts]` installierte Console-Entry-Point verwendet
dagegen das Script-Verzeichnis der Installation als Startpunkt und lud im
gleichen Zielrepository die installierte S.A.M.U.E.L.-Distribution.

## Entscheidung

Der installierte Console-Entry-Point `samuel` ist der einzige unterstützte
Betriebsaufruf. Interaktive Aufrufe, systemd-Units, Container-Entrypoint und
Container-Healthcheck verwenden ihn direkt. Ein Service-Generator muss den
ausführbaren absoluten Script-Pfad auflösen und blockiert, wenn er nicht
existiert; er fällt niemals auf `python -m samuel` zurück.

`python -m samuel` ist kein unterstützter Aufruf aus Zielrepositorys. Das
vorhandene `samuel.__main__` bleibt ausschließlich ein Komfortpfad für einen
bewusst vertrauenswürdigen Source-Checkout. Weil ein kollidierendes Fremdpaket
vor diesem Modul ausgewählt wird, kann dieser Pfad technisch keine eigene
fail-closed Herkunftskontrolle garantieren und wird nicht als Betriebsgrenze
dokumentiert.

## Bindungsvertrag

- Die Distribution stellt `samuel = samuel.cli:main` als Console-Script bereit.
- Der unterstützte Aufruf aus einem beliebigen Working Directory importiert
  kein gleichnamiges Paket aus diesem Verzeichnis.
- Produktversion und Build-Revision stammen weiterhin aus der tatsächlich
  geladenen Distribution beziehungsweise ihrer expliziten Build-Evidence;
  `PROJECT_ROOT` und Working Directory sind keine Import- oder
  Identitätsauthority.
- Docker- und systemd-Verträge prüfen den Console-Entry-Point ausdrücklich.
  Eine Rückkehr zu `python -m samuel` ist Contract-Drift und schlägt in Tests
  beziehungsweise im Container-Release-Check fehl.

## Grenzen

Ein ausdrücklich manipuliertes `PYTHONPATH`, eine kompromittierte
Python-Installation oder ein ersetztes Console-Script liegen vor dem
S.A.M.U.E.L.-Prozess und werden durch diese Entscheidung nicht als
Sandboxing- oder Supply-Chain-Schutz ausgegeben. Wheel-, Image-, Dateirechte-
und Betreiberkontrollen bleiben dafür eigene Schichten.

## Konsequenzen

- Aktive Bedien- und Betriebsdokumentation verwendet ausschließlich `samuel`.
- Der systemd-Generator und die Platzhalter-Unit verwenden den absoluten
  installierten Script-Pfad.
- Das Runtime-Image startet und prüft Health über das installierte Script.
- Ein Regressionstest führt das Console-Script aus einem fremden Verzeichnis
  mit kollidierendem `samuel`-Paket aus und weist dessen Nichtimport nach.
- Der historische Modulpfad wird nicht entfernt, besitzt aber keine
  Betriebszusage.
