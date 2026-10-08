# CLAUDE.md — S.A.M.U.E.L.

## Projektkontext

Dieses Repository enthält den aktuellen S.A.M.U.E.L.-Code. Der Code, die
ausgelieferten Konfigurationen und die ausführbaren Tests sind die technische
Wahrheit. Historische Planungs- und Handover-Dokumente sind keine
Runtime-Spezifikation.

S.A.M.U.E.L. wird in dieser Arbeitsumgebung entwickelt, muss aber auf einem
beliebigen Zielsystem installierbar bleiben. Keine Implementierung darf von
einem bestimmten Checkout-Pfad, Hostnamen, privaten Server oder separaten
Legacy-Repository abhängen. Zugangsdaten werden ausschließlich über die
konfigurierte Umgebung bzw. den Setup-Prozess bezogen und nie in Dokumenten,
Commits oder Remote-URLs hinterlegt.

## Aktive Referenzen

1. `README.md` und `docs/INSTALL.md` — Installation und Einstieg
2. `CONTRIBUTING.md` — Beitragsworkflow und Qualitätsgates
3. `docs/SAMUEL_ARCHITECTURE_V2.1.md` — Architekturreferenz
4. `docs/README_technical.md` — technische Bedienung
5. `docs/OPERATING_RULES.md` — Betriebsregeln
6. `docs/RUNTIME_REFERENCE.md` und `docs/CAPABILITY_MATRIX.md` — generierter
   Laufzeitstand und nachgewiesene Kontrollwirksamkeit

Dokumente unter `docs/archive/` sind ausschließlich historische Nachweise.

## Arbeitsablauf

Die Entwicklung ist issue-getrieben. Vor einer Änderung werden Issue-Body,
Kommentare, aktueller Code und vorhandene Tests vollständig geprüft. Bestehende
Ports, Slices und Hilfsfunktionen werden erweitert, bevor neue parallele
Infrastruktur entsteht.

### Vor der ersten Mutation

1. Checkout (Repository, Branch, HEAD, Arbeitsbaum) und zugänglichen Live-Main
   feststellen; lokale Trackingrefs nicht als Live-Readback ausgeben.
2. Vollständigen Issue-Body, aktuelle relevante Kommentare sowie vorhandene
   PRs, Fixes und Merge-Commits lesen. Originalanforderung, spätere
   Scopepräzisierung, integrierte Implementation und reale Abnahme unterscheiden.
3. Maßgebliche Rules, Contracts und ADRs bestimmen; aktuellen Code und
   vorhandene Tests lesen. Bereits erfüllte Teilumfänge und verbleibenden Scope
   ausdrücklich benennen. Ein historischer Codingauftrag wird nicht erneut
   umgesetzt, wenn sein Ergebnis bereits integriert ist.
4. Wirkungspfad und relevante bekannte Failureklasse prüfen; erforderliche
   Teststufe vor der Implementation festlegen. Bestehende Mechanismen und
   Regressionen zuerst verwenden.

Nicht zugängliche externe Fakten bleiben `UNKNOWN`; fehlende Evidence ist kein
bestätigter Ist-Stand. Details stehen im
[Engineering Workflow](../docs/governance/CURRENT_ENGINEERING_WORKFLOW.md),
[Test-/Qualification-Runbook](../docs/runbooks/TEST_AND_QUALIFICATION_RUNBOOK.md),
den [Operating Rules](../docs/OPERATING_RULES.md) und der
[Drift History](../docs/governance/DRIFT_HISTORY_AND_LESSONS.md).

### Umsetzung und Eskalation

1. Eigenen Branch von aktuellem `main` anlegen.
2. Root Cause und vollständigen Wirkungspfad prüfen.
3. Code und passende Verhaltens-/Regressionstests gemeinsam ändern.
4. Folgefindings zuerst bestehenden Issues zuordnen. Nur ohne passenden Träger
   ein neues Issue begründet vorschlagen; keine Duplikate erzeugen.
5. Akzeptanzkriterien erst abhaken, wenn sie auf dem integrierten Stand wahr
   und belegt sind.
6. PR mit konkretem Umfang, Tests, Abgrenzungen und bekannten Restpunkten
   reviewen und integrieren.

Vorhandene, nicht zum Issue gehörende Worktree-Änderungen werden weder
überschrieben noch ungefragt in Commits aufgenommen.

Routineanalyse, bekannte Fixes, Test-/CI-/Runner-/Preflightfehler und belegte
Issue-Reconciliation werden innerhalb des bestehenden Scopes selbstständig
bearbeitet. Den Maintainer nur für neue Produktentscheidungen, Scopeausweitung,
Authorityänderungen, echte Contractkonflikte, Architekturentscheidungen mit
mehreren legitimen Varianten, neue Capability-/Plattformgrenzen oder nicht
geregelte Securityentscheidungen einbeziehen. Human Approval und Human Merge
bleiben beim Menschen.

Normale Issue→Implementation→Tests→CI→PR→Review→Human-Merge-Arbeit wartet nicht
pauschal auf Golden. Qualification-Vorbedingungen gelten für den jeweiligen
Qualification-/E2E-/Golden-Lauf, nicht als zusätzliches allgemeines PR-Gate.

## Verbindliche Gates

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy samuel/ --ignore-missing-imports
.venv/bin/mypy --config-file mypy-tests.ini
.venv/bin/pytest -q
```

Bei Dashboard-JavaScript muss zusätzlich der ausgelieferte Script-Block mit
einem JavaScript-Parser geprüft und die betroffene HTTP-/API-Ansicht konkret
getestet werden. Ein laufender Altprozess lädt neue Python-Änderungen erst nach
einem Neustart.

## Architekturregeln

- Python-Produktcode liegt unter `samuel/`.
- Kein Slice importiert einen anderen Slice.
- Slices importieren nur den Shared Kernel (`samuel.core.*`).
- Externe Systeme werden über Ports aus `samuel.core.ports` angebunden.
- Adapter werden im Wiring-Layer injiziert, nicht direkt aus Slices importiert.
- Slice-Tests liegen beim Slice; übergreifende Verträge liegen unter `tests/`.
- Neue Events benötigen die vollständigen OWASP-/AI-Act-Zuordnungen und Tests.

## Transparenz

Ein Issue bleibt offen, solange ein verpflichtendes Kriterium, eine notwendige
Bedienoberfläche oder ein nachgewiesener Folgefehler offen ist. Optionale
Ausbaustufen werden ausdrücklich als offen bezeichnet und bei Bedarf in einem
eigenen Issue weitergeführt. Testzahlen, manuelle Prüfungen und externe
Einschränkungen werden exakt dokumentiert; fehlende Nachweise werden nicht
erfunden.

Jeder Abschluss nennt Issue, HEAD/Candidate, Subject/Attempt (falls relevant),
Test-/Evidence-Stufe, Resultat und verbleibenden Scope. `IMPLEMENTED_UNVERIFIED`
bedeutet keine fehlende Implementation; `QUALIFICATION_ONLY` ist kein neuer
Codingauftrag. Ein gemeinsamer E2E-PASS schließt keine ungeprüften
issueeigenen Sonderfälle. Historische FAILs und Teilnachweise bleiben erhalten.
