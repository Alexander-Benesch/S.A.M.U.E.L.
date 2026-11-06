---
id: ADR-0620
title: Statische Preflight-Gates und expliziter Nichtausführungszustand
status: accepted
decision_issue: 620
decision_date: 2026-08-29
decision_digest: sha256:a50cab03ae2982d37ba36a05b3f82ccdee001bed41214ef56b6adfa33bc6da67
supersedes: []
superseded_by: []
---

# Statische Preflight-Gates und expliziter Nichtausführungszustand

## Kontext

Der `PRGatesHandler` führt heute den automatischen AC-Verifier einmal vor der
Gate-Schleife aus. Candidate-IMPORT- und TEST-Prozesse können dadurch bereits
laufen, obwohl ein nachfolgendes commitgebundenes statisches Required Gate den
Candidate wegen Scope, Destructive Diff, Syntax oder Revision blockiert.

Die Gate-Schleife publiziert nach aufgebautem `EvaluationSubject` einmalig ein
vollständiges `GateEvaluationCompleted`. `GateResult.passed` ist jedoch ein
Bool. Ein nach einer gescheiterten Vorbedingung bewusst nicht ausgeführtes Gate
kann deshalb weder im Event noch in Dashboard und PR-Kommentar wahrheitsgemäß
von PASS oder FAIL unterschieden werden.

#612 bindet Runner und Timeout an die Control Plane und ist Voraussetzung für
die Neuordnung. Environment-Härtung (#613) und eine spätere Sandbox (#619)
ändern nicht, dass unnötige Candidate-Ausführung vermieden werden soll.

## Entscheidung

Commitgebundene statische Required Gates laufen vor jeder
kandidatenkontrollierten Ausführung. Der initiale Preflight umfasst Gate 7b,
Gate 8, Gate 9, Gate 13a und Gate 13b. Ihre Prüfung verwendet das bereits
aufgebaute `EvaluationSubject` und remote-/SCM-gebundene Base-/Head-Evidence;
eine stale lokale Ref ist keine Freshness-Autorität.

Scheitert ein Required-Preflight, wird kein Candidate-Prozess gestartet. Der
Lauf publiziert dennoch genau ein `GateEvaluationCompleted` mit den real
ausgeführten Preflight-Resultaten und expliziten Nichtausführungsresultaten für
nachgelagerte Gates. Vor erfolgreichem Subject-Aufbau bleibt
`GateEvaluationUnavailable` der einzige terminale Vertrag.

Ein einzelnes `GateFailedEvent` löst weder Evaluation noch Healing aus. Beide
konsumieren ausschließlich das einmalige aggregierte terminale Event.

## GateResult vNext

`GateResult` erhält:

- `passed: bool | null`,
- `executed: bool`,
- einen validierten Status aus mindestens `passed`, `failed`, `error`,
  `missing_evidence`, `not_applicable` und `skipped_precondition`,
- Gate-ID, Reason-Code, Required-/Optional-Wirkung und `EvaluationSubject`.

`passed=true` oder `passed=false` ist nur bei `executed=true` zulässig.
`skipped_precondition` verlangt `executed=false` und `passed=null`. Ein
übersprungenes Required Gate wird nicht zusätzlich als Fehler gezählt; die
blockierende Autorität stammt aus dem tatsächlich ausgeführten fehlgeschlagenen
Preflight-Gate.

Optional- und External-Gates erhalten im Umsetzungsplan eine ausdrückliche
Position. Kein Gate verschwindet still aus dem vollständigen terminalen Event.

## Observation- und Scorevertrag

Der neue GateResult-/Evidence-Schemawert ist Teil des Evidence-Digests und der
Beobachtungsidentität. Läufe vor und nach dem Wechsel bilden getrennte Serien,
auch wenn das fachliche `EvaluationSubject` identisch ist. Dashboard und Replay
dürfen diesen Wechsel nicht als kontinuierliche Formel-/Policyzeitreihe
darstellen.

Fehlt Gate-11-Acceptance-Evidence, weil ein Required-Preflight blockiert hat,
ist die Beobachtung `not_scoreable`. Sie wird weder als 0 Prozent noch durch
Renormierung als 100 Prozent ausgegeben. Fehlende Gate-11-Evidence und
`skipped_precondition` werden kanonisch und explizit serialisiert, statt als
implizit leeres Feld die Digestidentität zu verwischen.

## Healingvertrag

Healing bleibt nur zulässig, wenn genau ein Required Gate real ausgeführt und
fehlgeschlagen ist, dieses Gate Gate 11 ist und genau ein auswertbares
automatisches Kriterium scheitert. Ein Preflight-Fehler mit übersprungenem Gate
11 beansprucht keinen Healing-Claim, startet kein LLM und geht in die
menschliche Route.

## Konsequenzen

- Out-of-scope, destruktive, syntaktisch defekte oder stale Candidates erhalten
  keine unnötige IMPORT-/TEST-Ausführung.
- Gate-Evidence, Digestserialisierung, Evaluation, Healing, Dashboard,
  PR-Kommentar, Reviewer-Briefing und Rollout-Schema wechseln gemeinsam auf
  einen Dreizustandsvertrag.
- Gate 13a wird nicht als heutiger Bypass umgedeutet: `unknown_commit` bleibt
  fail-closed. Die Neuordnung muss zusätzlich die remotegebundene
  Vergleichsherkunft nachweisen.
- #620 hängt hart von #612 ab, aber nicht von Sandbox #619, Worktree #618 oder
  Persistenz #482.
- #482-Teilschritt 2 muss diesen Schema-/Serienschnitt bei Migration und
  Historyprojektion berücksichtigen.

## Rollout-Grenze

Die Entscheidung allein ändert keine Gate-Reihenfolge. Aktivierung verlangt
gebundene Evidence mindestens für: vollständig grünen Preflight mit
ausgeführtem Gate 11; Gate-7b-Fehler mit Gate-11-Skip; Gate-9-Fehler ohne
Candidate-Prozess; Gate-13a-`unknown_commit`; Subject-Aufbaufehler mit
`Unavailable`; und einen weiterhin heilbaren alleinigen Gate-11-Fehler. Bis
diese Fälle gemeinsam bestehen, bleibt das heutige vollständige Eventschema
der dokumentierte Ist-Stand.
