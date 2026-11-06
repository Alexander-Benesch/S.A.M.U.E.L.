---
id: ADR-0399
title: Freigabeautorität an gebundene Gates, Score als Beobachtung
status: accepted
decision_issue: 399
decision_date: 2026-08-28
decision_digest: sha256:a87dd522ec16197b62acc8e509fd52ec4b9522b879ab27d893751a64b6983513
supersedes: []
superseded_by: []
---

# Freigabeautorität an gebundene Gates, Score als Beobachtung

## Kontext

Der Evaluation-Slice vergleicht einen gewichteten Score mit einer statischen
Schwelle und einer issuebezogenen High-Water-Baseline. Gate 10 und der
Self-Workflow verwenden weitere Schwellen. Diese Werte sind nicht durchgängig
an dasselbe `EvaluationSubject`, denselben Acceptance Contract und dieselbe
Policy wie die nachfolgenden Required Gates gebunden.

Damit erhielt ein formal vorhandenes, aber semantisch unvollständig gebundenes
Signal Autorität über einen stärker gebundenen Freigabepfad. Die
Dashboard-Baseline machte diese Bindungslücke sichtbar, war aber nicht ihre
Ursache.

## Entscheidung

Freigabeentscheidungen trifft ausschließlich das aktive Required-Gate-Profil.
Die Capability-/Wirksamkeitsmatrix weist aus, welche Gates an ein
`EvaluationSubject` gebunden sind und welche strukturelle Vorbedingungen
prüfen.

Der gewichtete Score wird eine nicht bindende Qualitätsbeobachtung. Er löst
weder Freigabe, Blockierung, Workflowverzweigung noch Healing aus.

Healing bleibt erhalten und verwendet kriteriumsweise, commit-, contract- und
policygebundene `AcceptanceEvidence`. Der Evaluation-Slice wird ein passiver,
idempotenter Subscriber auf den aggregierten Gatelauf. Externe Präsentation
bleibt vom synchronen Freigabepfad getrennt und zeitlich begrenzt.

Die blockierende issuebezogene Bestmarke aus #213 wird fachlich abgelöst.
Historische Werte bleiben lesbar, besitzen nach dem Cutover aber keine
Freigabeautorität.

## Bindungsvertrag

Eine Rohbeobachtung wird über

`observation_key = EvaluationSubject + Gate-Policy + Evidence-Digest`

identifiziert. Eine abgeleitete Formelberechnung bindet sich an den
vollständigen Beobachtungsschlüssel und ergänzt

`score_key = observation_key + Scoring-Policy + Formelversion`.

Wiederholte Eventzustellung erzeugt dadurch keine Duplikate; mehrere
Formelversionen bleiben legitime, nachvollziehbare Ableitungen derselben
Evidence.

## Konsequenzen

- Es gibt genau einen Runtime-Autoritätspfad: Workflow, Gate-Profil und
  Evidence-Healing werden als gebundener Pfad verdrahtet.
- Die Profilauswahl wird vor dem Runtime-Wiring validiert: Nicht-Self-Läufe
  erlauben `default`/`audit`, Self erzwingt unabhängig vom Environment das
  eigene Profil. Inkompatible Kombinationen blockieren den Bootstrap
  fail-closed.
- Der Legacy-Modus war nur bis einschließlich `2.0.0a4` zulässig. Seine
  Workflow-, Profil- und Autoritätsschalter sind entfernt; alte explizite
  Einstellungen blockieren den Start. Ab `2.0.0a5` erzwingt das Release-Gate
  zusätzlich ihre Abwesenheit und die reale Rollout-Evidence. Fehlende Evidence
  verlängert Legacy nicht.
- Scoreberechnung und `ScoreObserved` bleiben kurz und lokal. PR-Kommentare,
  Dashboard und andere externe I/O laufen getrennt mit Timeout.
- Leere Familien sind in der Ziel-Formel `n/a`; jedes automatische Kriterium
  zählt genau einmal. Diese Semantik bleibt reine Telemetrie.
- #577 hat die reale Rollout-Evidence erbracht; #580 bindet sie strukturell und
  fallsemantisch an den Releasevertrag. Nach a4 ist nur noch der gebundene Pfad
  verdrahtet; die frühere Modusauswahl ist keine Produktkonfiguration mehr.

## Fehlerklasse

Ein formal vorhandenes oder erfolgreich geprüftes Signal darf keine
Entscheidungs- oder Nachweisautorität erhalten, solange es nicht ausdrücklich
an seinen Gegenstand, seinen fachlichen Kontext und die geltende Policy
gebunden ist. Formale Existenz ersetzt keine semantische Bindung.
