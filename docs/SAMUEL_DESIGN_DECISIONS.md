# S.A.M.U.E.L. — Designentscheidungen

Stand: 30. August 2026 · Ausgangslage: Alpha-Release und bestätigte Produktgrenze #678

Der folgende Teil C ist ein historischer Audit-Snapshot gegen die unten
genannten August-Commits und **kein** aktueller Product-/Release-Status.
Aktuelle Code-, Qualification- und Issue-Restpunkte stehen in
`docs/status/CURRENT_PRODUCT_STATUS.md` und
`docs/status/ISSUE_IMPLEMENTATION_MATRIX.md`; akzeptierte dauerhafte
Entscheidungen in Teil A bleiben davon getrennt.

---

## Zweck und Geltung

Dieses Dokument entscheidet die Designfragen, von denen Positionierung und
erste funktionierende Version abhängen. Es schließt keine Issues und ersetzt
deren Akzeptanzkriterien nicht.

**Teil A (E1–E19) enthält die dauerhaften Entscheidungen.** Entscheidung,
Begründung, Konsequenzen und verworfene Alternativen gelten unabhängig vom
Codestand und ändern sich nur durch eine ausdrückliche Nachfolgeentscheidung.
Datierte Ist-Stände, konkrete Issue-Zuordnungen und Umsetzungsreihenfolgen sind
dagegen nicht dauerhaft; sie stehen in Teil C beziehungsweise Teil E.

**Teil C ist ein datierter Prüfbefund und wird superseded, nicht gelöscht.** Er
ist an einen konkreten Commit gebunden und kann nach jedem Merge überholt sein.
Nach dem nächsten Audit wird er unverändert als `AUDIT_<datum>_<commit>.md`
archiviert und mit einem Verweis `superseded_by` versehen. So bleibt der
historische Nachweis erhalten, ohne als aktueller Stand missverstanden zu
werden. Das ist die Regel aus E9, angewendet auf dieses Dokument selbst.

**Abgleichsbasis für Teil C:**

- `origin/main` auf Commit `d4c147c1e87ba9f7a8e2e99a21ac54d1ed8ef515`
- lokaler älterer Checkout auf `6ce7409c60cc85a4c2dd6fa48c5407f8ac58f198`
  mit nicht zu diesem Dokument gehörenden Arbeitsbaumänderungen
- Gitea-Issues einschließlich Kommentaren und Korrekturen, abgerufen am
  24. August 2026

**Statusabgleich nach dem Prüfbefund:** Issue-Status und Restscope wurden zuletzt
am 27. August 2026 gegen `main` auf
`507c810716e1a708795f99c9a2185561a58cf147` und den veröffentlichten
Release-Commit `41ee7506dd5a09f6eef4a3b71ad08276d0848911` abgeglichen. Das ändert die
historischen Beobachtungen aus Teil C nicht; spätere Behebungen werden dort
ausdrücklich als Statusnachtrag gekennzeichnet.

---

# Teil A — Dauerhafte Entscheidungen

## Kernaussage

S.A.M.U.E.L. ist funktional ein Agent. Der dauerhafte Produktwert liegt aber
nicht im eingebauten Worker, sondern in der kontrollierten Strecke zwischen
freigegebenem Änderungsauftrag, Candidate-Commit und Merge.

**Der Harness ist das Produkt. Der eigene Worker ist die gepflegte
Referenzimplementierung. Fremde Werkzeuge werden eingebunden, nicht
nachgebaut.**

Lackmustest für jede kommende Entscheidung:

> Bleibt der Wert bestehen, wenn man den Worker austauscht?

Bei einer reinen Coding-Agent-Funktion lautet die Antwort nein. Bei einer
Kernfunktion muss sie ja lauten — oder die Funktion ist ausdrücklich als
Komfort des Referenz-Workers klassifiziert.

---

## Entscheidungsübersicht

| | Entscheidung | Kern |
|---|---|---|
| E1 | Positionierung | Herkunftsunabhängige Prüf- und Nachweisschicht; `Zero Trust` nur als Architekturprinzip |
| E2 | Kontrollklassen | Fünf Klassen statt Zweiteilung, dazu eine Wirksamkeitsmatrix |
| E3 | Acceptance Contract und Fremd-Worker | Commitgebundener Vertrag zuerst; austauschbarer Port danach |
| E4 | Sicherheitszusage | Auf exakten Head-SHA und Merge begrenzt, nicht auf das Erstellen eines PR |
| E5 | Eigener Worker | Maintenance- und Referenzmodus |
| E6 | Premium | Entfernung, in zwei getrennten Schritten; entscheidet #476–#478 fachlich |
| E7 | Prompt Injection | Heuristik als Signal, nicht als alleinige Blockade |
| E8 | README | Ausschließlich aus nachgewiesenen Fähigkeiten ableiten |
| E9 | Claims-to-Code | Alle wesentlichen Produktbehauptungen, mit claimabhängiger Nachweistiefe |
| E10 | **Integration statt Nachbau** | Evidence-Vertrag mit passenden Standardformaten; self-hosted Standalone-Pfad |
| E11 | **Fähigkeitsabsicht erhalten** | Validierte Absicht bewahren, nicht zwingend ungenutzten Produktionscode |
| E12 | **Registry-neutraler Containerpfad** | OCI-Digest und Release-Identität gemeinsam binden; Registry bleibt Betreiberparameter |
| E13 | **Installierter CLI-Entrypoint** | Console-Script ist die Betriebsgrenze; Working Directory und `PROJECT_ROOT` sind keine Importauthority |
| E14 | **Atomarer Implementation-Loop** | Erfolg übernimmt alle Loop-Patches; jeder kontrollierte Fehlschlag restauriert den exakten Pfad-Vorzustand ohne Git-Reset |
| E15 | **Projektwurzel-gebundene Patchziele** | Alle Ziele einer LLM-Antwort werden vor dem ersten Apply kanonisch gebunden; absolute, traversierende und externe Symlink-Ziele blockieren fail-closed |
| E16 | **Versionierter Runtime-State** | Lokales SQLite für queryfähige Historie und transaktionale Autorität; getrennte Ports, Diagnose und stufenweise Migration |
| E17 | **Bedarfsgebundene Capability-Ebenen und Providergrenze** | Für austauschbare Nicht-Core-Capabilities nur benötigte Ebenen; Standards zuerst, Candidate-Ausführung außerhalb des Core und realer Referenzlauf als Release-Qualification |
| E18 | **Unveränderliche lokale Releases** | Neue manifestgebundene Geschwister-venv, atomarer `current`-Zeiger und disjunkte Betreiberpersistenz; Aktivierung bleibt Operatorautorität |
| E19 | **Health-/Readiness-Trennung** | Technische Gesundheit, zweckgebundene Betriebsbereitschaft und instanzgebundene Fach-Qualification ohne neue Authority getrennt projizieren |

E10, E11 und E17 binden die übrigen Entscheidungen; E12 ergänzt den
registry-neutralen Containervertrag, E13 die vorgelagerte Prozessherkunft und
E14 die Transaktionsgrenze, E15 die Dateisystem-Zielgrenze des
Referenz-Workers vor dem Candidate-Commit, E16 die lokale Persistenzgrenze und
E18 die lokale Release-/Updategrenze und E19 die Status-/Diagnosegrenze. E17
bindet diese Ebenen an den realen Bedarf und die Produktgrenze.

---

## E1 — Positionierung: Prüf- und Nachweisschicht

### Entscheidung

S.A.M.U.E.L. wird als **herkunftsunabhängige, policy-erzwungene Prüf- und
Nachweisschicht für KI-gestützte Codeänderungen** positioniert. Interne
Kurzbezeichnung: **Merge-Assurance-Schicht**.

`Zero Trust` bleibt Architekturprinzip und Zielbild, wird aber nicht
unqualifiziert als erreichte Produkteigenschaft verwendet. Nach NIST SP 800-207
gehören dazu neben Merge-Gates auch explizite Authentisierung und
Autorisierung, Least Privilege, Policy Enforcement Points und fortlaufende
Zustandsbewertung.

### Warum

Der Issue-zu-PR-Loop ist 2026 als Agentenfunktion breit verfügbar. Der
belastbare Unterschied ist nicht, dass ebenfalls Code erzeugt wird, sondern
dass ein freigegebener Änderungsauftrag gegen einen konkreten Commit geprüft
und die Entscheidung belegt wird.

### Was ausdrücklich verworfen wurde

Die frühere Aussage, das Feld der Kontrollschicht sei **unbesetzt**, ist
falsch und wird nicht verwendet. GitHub Rulesets, Copilot Hooks, CodeSlick und
GATE decken bereits Teile von Policy Enforcement, PR-Blocking oder
Agenten-Audit ab.

Die mögliche Differenzierung liegt in der Kombination aus:

- selbst hostbar und auch für Gitea nutzbar,
- unabhängig von Modell, Provider und Worker,
- freigegebener Änderungsvertrag,
- Bindung der Prüfung an den exakten Candidate-Commit,
- deterministische Kontrollen außerhalb des Modells,
- fail-closed Durchsetzung an der Merge-Grenze,
- exportierbare Kontroll- und Prüfnachweise,
- Einbindung vorhandener Prüfwerkzeuge statt Ersatz (E10).

### Benennung nach außen

„Merge-Assurance-Schicht" ist präzise, aber ein Kunstbegriff, nach dem niemand
sucht. Er bleibt internes Architekturwort. Der erste README-Satz braucht
zusätzlich eine Formulierung, die ein fachkundiger Fremder ohne Vorwissen
einordnet (siehe E8).

### Grenze der heutigen Zusage

Merge-Assurance ist nicht Runtime-Isolation. Ein externer Worker mit Shell,
Netzwerk und persistentem Speicher kann außerhalb des Diffs Schaden
verursachen. Für eine vollständige Zero-Trust-Zusage fehlen unter anderem ein
expliziter Worker-Identitätsvertrag, aufgabenbezogene Credentials,
Sandbox-/Egress-Regeln und Tool-Call-Policies.

#422 deckt einen Teil der Authentifizierungs- und Autorisierungsrichtung ab,
ersetzt aber kein Bedrohungsmodell für externe Worker. Das ältere Teil-Backlog
#332 ist darin einschließlich der Akteursbindung für Auditereignisse
aufgegangen.

---

## E2 — Fünf Kontrollklassen und nachgewiesene Wirksamkeit

### Entscheidung

Die Kontrollen werden nicht in Worker- und Artefakt-Level geteilt — diese
Zweiteilung war zu grob und hat die Ausführungsebene verschluckt. Es gelten
fünf Klassen:

| Klasse | Aufgabe | Beispiele |
|---|---|---|
| Input und Kontext | unvertrauenswürdige Eingaben begrenzen und markieren | Sanitizer, Context Builder, File Slicing, Prompt-Guard |
| Ausführung | Aktionen des Workers begrenzen | Tool-Policy, Sandbox, Egress, Credentials, Command Policy |
| Artefakt und Commit | den erzeugten Kandidaten deterministisch prüfen | Secret-Scan, Scope, Architektur, Lockfiles, IaC, Tests, destruktiver Diff |
| Prozess und Vertrag | Freigabe und Merge an Regeln binden | Acceptance Contract, Human Approval, Head-SHA, Branch-Schutz, Merge-Policy |
| Evidenz und Telemetrie | Entscheidungen nachvollziehbar machen | Audit, SARIF, Gate Receipts, Metriken, Injection-Signale |

Keine Klasse gilt pauschal unverändert für jeden Worker. Die Anwendbarkeit wird
pro Kontrolle und Adapter ausgewiesen:

- *Input und Kontext* kann auch für fremde Worker gelten, wenn S.A.M.U.E.L. den
  Contract oder Kontext erzeugt und den Aufruf vermittelt; bei einem
  unabhängig gestarteten Worker fehlt diese Kontrolle.
- *Ausführung* kann gelten, wenn S.A.M.U.E.L. den Worker startet, sandboxed und
  seine Tool-Calls vermittelt; bei einem fremd betriebenen Worker ist sie heute
  nicht abgedeckt.
- *Artefakt und Commit* gilt nur, wenn der vollständige Candidate-Commit
  unverändert und ohne Trunkierung geprüft wird.
- *Prozess und Vertrag* gilt nur bei nachweisbarer Freigabe-, Head-SHA- und
  Merge-Durchsetzung.
- *Evidenz und Telemetrie* kann Ergebnisse fremder Worker aufnehmen, beweist
  deren Ausführung aber nur mit vertrauenswürdiger Receipt oder Attestation.

### Capability-Matrix

Für jede Kontrolle wird geführt:

- Kontroll-ID und eindeutiger Name
- Klasse und Schutzziel
- verantwortliche Komponente und konkreter Enforcement Point
- produktiver Aufrufpfad
- benötigte und unvertrauenswürdige Eingaben
- Gültigkeit beim eigenen und bei fremden Workern
- Status `enforced`, `advisory`, `telemetry`, `implemented`, `unwired`,
  `disabled`, `experimental`, `deprecated`, `not_applicable`, `unknown` oder
  `planned`
- Required/Optional/Disabled je Workflow
- Verhalten bei Fehler oder fehlenden Daten
- Datenvollständigkeit, Trunkierung und Freshness
- erzeugte Evidence, Quelle und Vertrauensniveau
- geprüfter Base- und Head-SHA
- Policy-/Taxonomie-/Schema-Version sowie Tool-Identität, Version und Digest
- Override-, Ausnahme- und Invalidation-Verhalten
- Positiv-, Negativ- und Umgehungstests
- zuständiges Issue

Die Angabe „rund 30" darf nur als Inventar vorhandener Mechanismen verwendet
werden, solange die Matrix nicht 30 wirksame, voneinander abgegrenzte
Kontrollen nachweist. Die 13 Einträge im `GATE_REGISTRY` sind 13 registrierte
PR-Gate-Funktionen, aber nicht automatisch 13 unabhängige Security-Gates.

**Die Capability-Matrix ist als #517 eigenständig erfasst.** Sie ist ein
Arbeitsstrang, kein Kleinfund. Sie in #474 oder #485 zu pressen, erzeugt genau
die Scope-Verzerrung, die die Issue-Regel vermeiden soll. Dies ist die
ausdrückliche Ausnahme von „keine neuen Issues".

---

## E3 — Freigegebener Acceptance Contract vor `ImplementationPort`

### Entscheidung

Zuerst wird ein workerunabhängiger Acceptance Contract eingeführt und an den
exakten Candidate-Commit gebunden. Diese Grundlage ist bereits für den eigenen
Worker und damit für v1 erforderlich. Erst danach wird die
Implementation-Stufe als austauschbarer Port ausgeformt. Der Port ist eine
spätere Integrationsfähigkeit und darf die Commitbindung nicht blockieren.

Der stabile Vertrag wird nicht agentenspezifisch formuliert und setzt nicht
voraus, dass S.A.M.U.E.L. selbst den ersten Plantext geschrieben hat.

Vertrauensanker ist ein **freigegebener, unveränderlicher Acceptance
Contract** mit mindestens:

- Issue-Identität und freigegebene Akzeptanzkriterien
- Repository-Identität sowie Issue-/Kommentar-Revision als Herkunft
- Base-SHA
- erlaubte und verbotene Pfade
- relevante Regeln aus `architecture.json` und der aktiven Policy
- Risk-Klasse und erforderliche Kontrollen
- Contract-Schema sowie Policy-Version und -Digest
- festgelegte Kanonisierung, Hash-Algorithmus und kanonischer Contract-Hash
- Freigabestatus, Zeitpunkt, verantwortlicher authentisierter Akteur
- Ablauf, Widerruf und Schutz vor Wiederverwendung eines alten Vertrags

Ein Worker liefert zurück:

- Branch und exakten Candidate-Head-SHA
- Contract-Hash
- Worker-, Modell- und Versionsidentität als Telemetrie; für behauptete
  Ausführungsprovenienz verpflichtend und attestiert
- optional strukturierte Ausführungsnachweise

S.A.M.U.E.L. bewertet nie „den Branch", sondern den angegebenen Head-SHA gegen
genau diesen Contract. Jeder neue Push invalidiert die vorherige Freigabe.

### Bevorzugter Anschlussweg

Für die erste fremde Implementation ist ein SCM-natives Abgabeprotokoll
vorzuziehen:

1. S.A.M.U.E.L. veröffentlicht den freigegebenen Contract.
2. Ein beliebiger Worker erzeugt einen Branch.
3. Ein Push oder PR meldet den Candidate-Head.
4. S.A.M.U.E.L. prüft diesen Commit und veröffentlicht commitgebundene
   Ergebnisse.

Agentenspezifische Adapter bleiben dünne Übersetzer. Die frühere Option, einen
lokalen Prozess-/Containerexecutor als bevorzugte Core-Referenz auszubauen,
ist durch E17/ADR-0678 superseded. Kandidatenkontrollierte Ausführung soll in
einem externen Execution-/CI-Provider stattfinden; der vorhandene lokale Pfad
bleibt bis zum nachgewiesenen atomaren Cutover als begrenzte Legacy-
Implementierung erhalten.

### Abgrenzung und Reihenfolge

Der datierte Ist-Stand und die Issue-Zuordnung stehen in Teil C und Teil E.
Der Contract wird als v1-Grundlage umgesetzt; ein `ImplementationPort` und
fremde Adapter folgen erst nach Stabilisierung der Kernkontrollen, damit kein
vorschneller Adapter pro Agent entsteht. Der spätere Port und seine
Conformance-Suite sind in #521 erfasst.

`--self` bleibt getrennt: Self-Mode bezeichnet den Lauf gegen das eigene
Repository, nicht die Herkunft des Workers.

---

## E4 — Zusage: geprüfter Merge

### Entscheidung

> Kein Commit wird gemergt, dessen exakter Head-SHA nicht gegen den
> freigegebenen Änderungsvertrag und die aktive Policy geprüft wurde.

Diese Zusage gilt nur für registrierte Zielbranches, deren Schutz- und
Required-Check-Profil S.A.M.U.E.L. mit ausreichender Berechtigung verifizieren
kann. Kann die Plattform die Durchsetzung oder Provenienz eines Required Checks
nicht belegen, darf der Betriebsmodus nicht als `enforced` ausgewiesen werden.

Die frühere Formulierung „kein ungeprüfter Code kommt in den PR" ist
**verworfen**. Ein PR ist der Prüfgegenstand; Remote-CI, Code-Scanning und
Review laufen typischerweise erst nach seiner Erstellung.

### Erforderliche Durchsetzung

- Prüfnachweise sind an Repository, Base-SHA, Head-SHA, Contract-Hash und
  Policy-Version gebunden.
- Jeder Push verwirft veraltete Nachweise.
- Required Checks gelten für den exakten PR-Head und stammen, soweit die
  Plattform das unterstützt, aus der erwarteten CI-App beziehungsweise dem
  erwarteten Runner-Kontext.
- Nicht prüfbare Required-Kontrollen blockieren.
- Branch-Schutz beziehungsweise Merge Queue verhindert das Umgehen.
- Manuelle Overrides sind technisch ausgeschlossen oder gesondert, begründet
  und unveränderlich auditiert.

### Konsequenz

Branch-Namen oder ein irgendwann bestandener Check reichen nicht als Nachweis.
Die Implementierung muss vor jeder Statusveröffentlichung und unmittelbar vor
einem Merge denselben Head auflösen, veraltete Evidence nach jedem Push
invalidieren und den vollständigen Prüfgegenstand ohne stille Trunkierung
verarbeiten. Der datierte Ist-Stand, der Nachweis aus #441 und die verbleibenden
Lücken stehen in Teil C; die Issue-Zuordnung steht in Teil E.

### Umsetzungsnachtrag vom 24. August 2026 (#515)

Die lokale Gate-Stufe besitzt nun die fehlende Grundeinheit
`EvaluationSubject`: kanonische Repository-URL, vollständiger Base-/Head-SHA,
kanonischer Contract-Hash sowie Policy-Version und -Digest. `CreatePRCommand`,
`GateContext`, alle internen/externen `GateResult`s und die Gate-/PR-Evidence
verwenden dasselbe unveränderliche Objekt. GitHub und Gitea lösen Branch-Refs
über den SCM-Port auf und vergleichen lokal exakt diese Commit-IDs. Der
vollständige Diff wird bis zur konfigurierten Ressourcenobergrenze geprüft;
Überschreitung und Git-/Revisionsfehler sind `not_evaluated`, nicht bestanden.

Nach der PR-Erstellung und erneut unmittelbar vor Auto-Merge wird das PR-Paar
gegen den Subject geprüft. Eine Abweichung erzeugt
`EvaluationSubjectInvalidated` und blockiert. Damit sind lokale Evidence und
Auto-Merge commitgebunden. **Noch nicht daraus ableitbar** ist eine
SCM-weite `enforced`-Zusage für spätere Pushes oder manuelle Merges:
SCM-Required-Check und Branch-Schutz sind inzwischen über #441/#528 gesondert
nachgewiesen; die Auto-Merge-/Review-Policy bleibt #468. Ein später
verschobener Head passt zwar
objektiv nicht mehr zur alten Evidence, wird ohne SCM-Ereignis/Check aber nicht
von diesem lokalen Handler aktiv beobachtet.

### Umsetzungsnachtrag vom 19. September 2026 (#468)

Der Reviewpfad validiert nun einen geschlossenen versionierten Entscheid mit
`pass`, `block` oder `indeterminate` samt Findings gegen EvaluationSubject,
vollständigen Diff-Digest, Policy, Tool und Prompt. Review-Evidence ersetzt
keine menschliche Planfreigabe. Der weiterhin default-off Auto-Merge läuft
erst nach einem strukturierten Pass sowie erneuter Prüfung von aktivem Plan,
unveränderter menschlicher Approval-Evidence, Required-Gates und PR-Revision.
Gitea erhält den erwarteten Head nativ als `head_commit_id`; eine Installation
muss diese Bedingung zusätzlich über den default-off Deploymentnachweis
`expected_head_merge_qualified` freigeben. Der Mergeintent bindet Subject und
Review-Digest und wird nach unbekanntem Ausgang nur gegen die SCM-Postcondition
reconciliert, nie blind wiederholt. Die Repositoryimplementierung ist damit
vorhanden; der isolierte reale Positiv-/Race-/Restart-Nachweis bleibt vor
Aktivierung und Abschluss von #468 offen.

### Umsetzungsnachtrag vom 29. August 2026 (#620)

Die angenommene ADR-0620 ist umgesetzt: 7b, 8, 9, 13a und 13b bilden den
statischen Preflight vor Candidate-IMPORT/-TEST. Ein Required-Preflight-Fehler
verhindert die Verifier-Ausführung und führt alle nachgelagerten internen und
externen Gates im GateResult-Schema v2 als `skipped_precondition`. Das eine
aggregierte `GateEvaluationCompleted` bleibt gebunden beobachtbar; ohne
Gate-11-Evidence ist die Ableitung `not_scoreable`, und Healing beansprucht
weder Claim noch LLM-Aufruf. Die aktiven Gate-Policy-Versionen und der
Policy-Digest binden den Schema-/Reihenfolgenwechsel; v1-Observationen bleiben
als getrennte historische Serie lesbar.

### Nicht-Zusage

> S.A.M.U.E.L. garantiert nicht, dass ein fremder Worker außerhalb des
> geprüften Commits keine Seiteneffekte erzeugt.

---

## E5 — Eigener Worker im Maintenance- und Referenzmodus

### Entscheidung

Der eigene Worker bleibt erhalten und wird zur minimalen, vollständig
getesteten Referenzimplementierung des Implementation-Vertrags. Er ist
zugleich der Grund, warum das System ohne fremde Werkzeuge lauffähig bleibt
(siehe E10, Standalone-Pflicht).

Zulässig bleiben:

- Sicherheits- und Fehlerkorrekturen
- Kompatibilität mit unterstützten Providern
- Anpassungen an den gemeinsamen Port-/Contract-Vertrag
- Conformance-, Integrations- und Regressionstests
- notwendige Verbesserungen, damit der dokumentierte Standalone-Pfad
  zuverlässig funktioniert

Nicht mehr roadmapbestimmend sind neue differenzierende
Coding-Agent-Fähigkeiten. Neue Worker-Funktionen werden nur aufgenommen, wenn
sie zum Testen oder Beweisen des Harness erforderlich sind.

**Klarstellung:** Arbeit an Gates und Evaluation ist Harness-Arbeit, auch wenn
die betroffene Komponente nahe am Worker liegt. Der Freeze betrifft
Erzeugungsfähigkeiten, nicht Prüffähigkeiten.

---

## E6 — Premium entfernen, in zwei getrennten Schritten

### Entscheidung

Premium-Stufe, Ed25519-Entitlement-Prüfung und Premium-Feature-Tokens werden
vor dem ersten öffentlichen Release entfernt. Die fachlich bestätigten
Funktionen sind ohne Lizenzdatei verfügbar; daraus folgt kein Erhalt doppelter,
toter oder unvollständiger Implementierungen (E11).

**Die Umsetzung wird in zwei Schritte getrennt, weil sie unterschiedlich
riskant ist:**

**Schritt 1 — Entitlement- und Aktivierungspfad bereinigen.** Lizenzprüfung,
Feature-Tokens, Premium-/Free-Anzeigen und die zugehörige Dokumentation
entfallen. Vor einer allgemeinen Freischaltung wird zugleich festgelegt,
welcher heutige Routingpfad kanonisch ist; der alte, nur per
`premium.*`-Konfiguration aktivierbare Bootstrap-Pfad wird deaktiviert. Dieser
Schritt entblockt den README-Umbau (E8), darf aber keine zweite aktive
Implementierung freischalten.

**Schritt 2 — Pfadkonsolidierung (#477).** Doppelte Routing-Implementierung und
toter Token-Limit-Pfad werden nach Paritäts-, Aufruf- und Sicherheitsabgleich
zusammengeführt. Beide Schritte sind vor v1 abzuschließen. Redaktionelle
Vorarbeiten am README dürfen parallel laufen; als neuer Ist-Zustand werden sie
erst nach der technischen Konsolidierung veröffentlicht.

**Umsetzungsstand 25. August 2026:** Beide Entfernungsschritte sind mit #477
umgesetzt. Es gibt keinen Entitlement-Entscheidungspfad mehr; Schedule,
Task-Routing und Dashboard-/Prompt-Verwaltung verwenden die vorhandenen
allgemeinen Pfade. Der alte Router und der unverdrahtete TokenLimitHandler sind
entfernt. Der davon getrennte kumulative Budgetvertrag wurde mit D14/#549
entschieden und im allgemeinen Adapter-/Authority-Pfad umgesetzt; der Altpfad
bleibt entfernt.

### Begründung

- Grundlegende Sicherheitsfunktionen, Auditierbarkeit und harte Kostenlimits
  dürfen bei einem Sicherheitsprodukt nicht von einer Bezahlschranke abhängen.
- Es gibt keine externen Lizenznehmer und keine belastbare Erlösstrecke.
- Schedule, Provider-Routing, Prompt-Editor und Token-Budgets sind kein
  nachhaltiger proprietärer Differenzierer.
- Der Lizenzcode erzeugt eine zweite Berechtigungslogik neben echter
  Authentisierung und Autorisierung.
- CISA Secure by Design spricht dagegen, grundlegende Sicherheitsfunktionen
  und hochwertige Logging-Fähigkeiten kostenpflichtig abzuspalten.

### Durch diese Entscheidung aufgelöste Issue-Fragen

**#476 — Projektlizenz:** Der bestätigte Zielzustand „gesamtes Repository
Apache-2.0" gilt auch für den heutigen Inhalt von `samuel/premium/`. Kein
Premium-Ausschluss, keine Auslagerung in ein proprietäres Repository. #476
setzt Root-`LICENSE`, PEP-639-/SPDX-Metadaten und einen frischen Paketnachweis
um.

Die Root-Datei `LICENSE` ist die eine maßgebliche Stelle für den Lizenztext
und seinen Geltungsbereich. `pyproject.toml`, README und technische
Dokumentation spiegeln diese Entscheidung lediglich maschinen- bzw.
menschenlesbar; die heutige Ed25519-Laufzeitfreischaltung ist keine zweite
Softwarelizenz.

**#477 — doppelte Premium-Pfade:** Der Paritäts- und Produktionsaufruf-Abgleich
ergab keine notwendige einzigartige Funktion des alten Routers. Die parallele
Implementierung unter `samuel/premium/llm_routing/` und ihr Bootstrap-Pfad sind
entfernt; `TaskRoutingLLMAdapter` plus `ScheduledTaskRoutingAdapter` bilden den
einen aktiven Routingpfad.

Der an `bus._token_limit` gehängte, von Produktionscode ungelesene
`TokenLimitHandler` wird nicht als Premium-Modul verdrahtet. Ausgabegrenze je
Call, kumulatives Workflow-Tokenbudget und informative Preiswerte bleiben
unterschiedliche Fähigkeiten. `TokenBudgetLLMAdapter` deckt die
Aufruf-/Ausgabegrenze ab; D14/#549 ergänzt im aktiven allgemeinen Pfad die vor
Planning persistierte Tokenzulassung und die Reservation jedes physischen
Attempts. Der tote Premium-Pfad bleibt entfernt.

**#478 — Premium-Lizenzen ausstellen:** entfällt. Der Zielzustand enthält kein
Issuer-Tool, Premium-Keypair und keine Premium-Lizenzdatei. Die zuvor
vorhandenen Keypair-/Lizenzgeneratoren sind im Rahmen von #477 entfernt. #478
kann damit als durch die Architekturentscheidung überholt geschlossen werden.
Eine vorhandene `config/license.json` ersetzt nicht die fehlende
Open-Source-`LICENSE`-Datei.

### Funktionsmigration

| Bereich | Umgesetzter Zustand / Restscope |
|---|---|
| `samuel/core/license.py` | entfernt; kein Entitlement- oder Premium-Status |
| `SAMUEL_LICENSE_KEY` / `config/license.json` | werden nicht mehr gelesen oder als aktive Konfiguration dokumentiert |
| `llm_routing_advanced` | Schedule als normale, validierte Konfiguration |
| `llm_routing_dashboard_write` | ohne Premium-Check; im Single-Operator-Modus weiter durch API-Key-Zugriffskontrolle und Eingabevalidierung geschützt, echte Rollenautorisierung erst mit #422 |
| statisches Per-Task-Routing | bleibt der eine aktive Routing-Pfad |
| Call-Ausgabegrenze | bleibt im allgemeinen `TokenBudgetLLMAdapter`; getrennt von der kumulativen Workflowzulassung |
| kumulatives Workflow-Tokenbudget | D14/#549: persistente Zulassung vor Planning, atomare Reservation je physischem Retry/Fallback und volle Bindung unbekannter Usage; reale Provider-Qualification bleibt offen |
| Preis-/Rechnungswerte | ausschließlich informative Meteringdaten; kein Geldkosten-Hardcap |
| `samuel/premium/llm_routing/` | nach Paritäts- und Aufrufabgleich entfernt; keine einzigartige Funktion zu überführen |
| `samuel/premium/token_limit/` | als unverdrahteter Altpfad entfernt; D14/#549 ist im allgemeinen Pfad umgesetzt |
| Dashboard Premium-/Free-Anzeigen | entfernt; reale Capability- und Auth-Informationen bleiben sichtbar |
| Premium-Tests | durch Funktions-, Auth-, Migrations- und Workflow-Budgetregressionen ersetzt |
| `cryptography` | aus Core-Abhängigkeiten entfernt; bleibt ausschließlich im `github`-Extra für RS256-GitHub-App-Authentisierung |

Das Freischalten der Dashboard-Schreibwege entfernt **nicht** ihre
Sicherheitsgrenze. Der API-Key-Schutz bleibt bis zur Benutzer-/RBAC-Lösung aus
#422 bestehen. Serverseitige Autorisierung und Pfad-/Inhaltsvalidierung sind
unabhängig von Premium.

### Dokumentationsumfang

Premium-Tabelle und alle `Free-Mode`-Markierungen im README, Lizenz- und
Kostendeckungsargumente, Premium-Hinweise bei Schedule, System-Prompt-Editor
und Token-Budget, die frühere Premium-Setup-Datei und aktive Verweise darauf,
Architektur- und Installationsdokumentation, Dashboard-Texte,
API-Beschreibungen, Health-/Statusangaben, Beispielkonfigurationen,
Environment-Variablen, Feature-Token, Paketmetadaten sowie die Trennung
zwischen Apache-2.0-Projektlizenz und Laufzeitkonfiguration.

Historische Archivdokumente werden nicht rückwirkend umgeschrieben; sie
erhalten nur einen Hinweis, wenn sie als aktive Anleitung missverstanden
werden könnten.

### Akzeptanzkriterien

- [x] Kein produktiver Premium-/Free-Entscheidungspfad mehr vorhanden.
- [x] Fehlende oder vorhandene alte Lizenzdaten ändern keine Funktion.
- [x] Schedule, Prompt-Verwaltung und das Call-Ausgabelimit funktionieren über
      dokumentierte allgemeine Pfade; D14/#549 ergänzt dort die getrennte
      kumulative Workflow-Tokenzulassung.
- [x] Schreibende Dashboard-Funktionen bleiben authentisiert, autorisiert und
      negativ getestet.
- [x] Genau eine aktive Routing-Implementierung.
- [x] Je Vertrag genau eine aktive Token-Durchsetzung: Call-Ausgabebound und
      kumulative Workflowzulassung.
- [x] Tote Module, private Bus-Hacks, Feature-Tokens und zugehörige
      Typ-Ignores entfernt.
- [x] `pyproject.toml`, Wheel/sdist, Root-`LICENSE`, README und technische
      Dokumentation weisen konsistent Apache-2.0 aus (#476).
- [x] Nicht mehr benötigte Crypto-Abhängigkeiten und Keypair-Werkzeuge
      entfernt; weiterhin benötigte Verwendung begründet.
- [x] Tests, Ruff, Format, Mypy, Paketbuild und Installations-Smoke grün.
- [x] ADR-/Changelog-Eintrag mit Datum, Grund und ersatzlosem Entfall der
      Entitlements.

### Kostendeckung

Spenden über GitHub Sponsors oder Ko-fi ohne Feature-Kopplung. Eine spätere
kommerzielle Leistung darf Betrieb und Organisation betreffen — Hosting,
zentrale Policy-Verteilung, SSO/RBAC, Retention, Fleet Management, Support,
SLA. Grundlegende Kontrollen und exportierbare Nachweise bleiben frei.

---

## E7 — Prompt-Injection-Erkennung als Signal

### Entscheidung

Die Erkennung fester Prompt-Injection-Phrasen wird nach #474 aktiv verdrahtet,
aber nicht als alleinige blockierende Sicherheitsschranke bewertet. Sie ist
ein versioniertes Risiko- und Telemetriesignal mit messbarer False-Positive-
und False-Negative-Rate.

Die PASB-Studie (*Personalized Agent Security Bench*, arXiv 2602.08412) misst
in ihrem Benchmark Rest-Erfolgsquoten von 10,5 bis 22,0 Prozent trotz der
stärkeren getesteten Prompt-Layer-Abwehr. Das belegt keinen universellen
Prozentsatz, aber deutlich, dass ein Phrasenfilter keine harte
Sicherheitsgrenze ist.

### Konsistenzkonflikt mit #474 — Handlungsbedarf

#474 verlangt derzeit **wörtlich**, dass ein manipulierter Issue-Text den Lauf
blockiert. Der historische Issue-Body wird nicht still umgeschrieben. Ein
datierter Entscheidungskommentar verweist auf E7, markiert das ursprüngliche AC
ausdrücklich als superseded und dokumentiert den neuen Acceptance Contract
kriteriumsweise. Falls dadurch widersprüchliche Teilziele in #474 verbleiben,
wird #474 zum Dachissue und verweist auf eng geschnittene Folgeissues.

Der ersetzende Acceptance Contract verlangt:

- Die Heuristik erzeugt zunächst ein Finding und Audit-Evidence.
- Ein harter Block erfolgt bei deterministischen Policy-Verstößen: erkannter
  Canary-Abfluss, unerlaubter Tool-Call, verbotener Pfad, Secret im Diff oder
  fehlende menschliche Freigabe. Canary-Erkennung ist dabei Detektion und
  Regressionstest, kein Beweis, dass eine unerwünschte Verarbeitung präventiv
  verhindert wurde.
- Eine kombinierte Risk-Policy darf bei hohem Risiko blockieren, muss dann
  aber transparent, konfiguriert und mit gemessener Fehlerrate getestet sein.

#481 setzt Unicode-Normalisierung, zusätzliche Muster sowie gemeinsame
Marker-/Secret-Quellen um. Neue **heuristische oder formatbasierte** Signale
starten advisory; hochpräzise deterministische Secret-Regeln fallen unter den
oben bereits festgelegten Blockierfall „Secret im Diff“. Der generische
Post-Call-Echo-Check wurde verworfen, weil die verwendeten Marker keine
eindeutigen Canaries sind und Echo wie Echo-Abwesenheit keine Injection
belastbar beweisen.

Eine eingebaute generische Entropieprüfung wird ebenfalls verworfen: Ohne
regelbezogene Keywords, Secret-Gruppe und Allowlist ist sie für ein
fail-closed Gate zu unspezifisch. Dedizierte Scanner werden nicht nachgebaut;
ein normalisierter Scanner-/SARIF-Ingest ist nicht implementiert. #520 liest
stattdessen ausschließlich vorhandene SCM-Check-Facts advisory. Solche Regeln
dürfen erst nach
regelbezogenen Operator-Entscheidungen, versioniertem repräsentativem Korpus
und eigener Policy-Freigabe blockierend werden. Reine Trefferzählung durch
`get_finding_stats` ist kein False-Positive-Nachweis.

### Zielverteidigung

- Unvertrauenswürdige Issue-, Kommentar-, Repository-Regel- und Tool-Daten
  strukturell trennen und begrenzen.
- Tool-Calls außerhalb des Modells gegen eine explizite Policy prüfen.
- Tool-Rückgaben und Scannertexte als unvertrauenswürdig behandeln.
- Worker erhalten geringstmögliche Rechte, isolierte Ausführung, begrenzten
  Egress.
- Canaries prüfen Output, Tool-Argumente, Tool-Rückgaben, persistente Daten
  und Egress auf unbeabsichtigten Abfluss.
- Menschliche Freigabe bleibt für definierte Risikoklassen erforderlich.

Eine Command-Policy wird erst an einem realen Tool-/Command-Enforcement-Point
produktiv. Eine Freitextliste ohne solchen Aktionspfad wird nicht allein zum
Erhalt einer geplanten Funktion verdrahtet; die Absicht bleibt als Policy-
Anforderung erhalten.

### SARIF-Grenze

Schema-validiertes SARIF ist parsebar und begrenzbar, aber nicht automatisch
inhaltlich vertrauenswürdig. Auch valide `message`-, Pfad- oder
Regelbeschreibungen können manipulierten Text enthalten. Deshalb nur
notwendige Felder übernehmen, Größen und Längen begrenzen, freie Texte nie roh
in einen privilegierten Modellkontext geben. Das gilt gleichermaßen für
eingebundene Fremdwerkzeuge nach E10.

---

## E8 — README aus verifizierter Capability-Matrix ableiten

### Entscheidung

Die README führt mit Produktkategorie, Kontrollgrenze und überprüfbarer
Zusage. Der endgültige Umbau erfolgt erst nach dem ersten Capability-/
Claims-Audit, damit die neue Einleitung nicht dieselbe Übertreibung in neuer
Form wird.

Redaktionelle Vorbereitung für den Entfall der Premium-Kommunikation ist davon
unabhängig. Als neuer Ist-Zustand wird sie erst veröffentlicht, wenn E6 die
Entitlements und doppelten Aktivierungspfade technisch bereinigt hat.

### Formulierung für den heutigen Stand

> S.A.M.U.E.L. ist eine policy-gesteuerte Issue-to-PR-Pipeline mit
> integriertem LLM-Worker. Der dauerhafte Kern ist die Prüfung und
> nachvollziehbare Dokumentation von Codeänderungen außerhalb des Modells.
> Noch nicht vollständig verdrahtete Kontrollen sind ausdrücklich als solche
> gekennzeichnet.

### Formulierung nach Acceptance Contract und Head-SHA-Durchsetzung

> S.A.M.U.E.L. prüft KI-gestützte Codeänderungen, bevor sie gemergt werden —
> unabhängig davon, welches Werkzeug den Code geschrieben hat. Das System
> bindet einen freigegebenen Änderungsvertrag an einen konkreten
> Candidate-Commit, prüft ihn außerhalb des Modells gegen deterministische
> Regeln und erzeugt nachvollziehbare Prüfnachweise. Vorhandene Scanner und
> CI-Systeme werden eingebunden, nicht ersetzt. Der mitgelieferte Worker ist
> eine Referenzimplementierung.

Der erste Satz ist bewusst ohne Kunstbegriff formuliert (siehe E1).

### Zulässig

> Die entscheidenden Merge-Kontrollen laufen außerhalb des Modells und werden
> gegen den geprüften Commit erzwungen.

### Nicht zulässig, solange nicht vollständig nachgewiesen

- „kein Prompt kann die Schranken umgehen"
- „30 unabhängige, technisch erzwungene Schranken"
- „kein ungeprüfter Code kommt in einen PR"
- „EU-AI-Act-konform" oder „zertifiziert"
- „die Compliance-Matrix beweist Compliance"
- „niemand sonst arbeitet am Merge-Gate"

Das Ergebnis heißt **Kontroll- und Prüfnachweis mit Compliance-Mapping**. Es
unterstützt die Bewertung des Betreibers, ersetzt sie nicht.

### Redaktionelle Änderungen

- Langform mit „Autonomes" nicht als erste Botschaft.
- Vergleich mit Coding-Agenten direkt auflösen, nicht vermeiden.
- Für das kontrollierte Element `LLM-Worker` statt mehrdeutig `Agent`.
- `ready-for-agent` perspektivisch durch einen S.A.M.U.E.L.-Namensraum wie
  `samuel:ready` ersetzen.
- `--self` als Lauf gegen das eigene Repository beschreiben.
- Premium-/Free-Kommunikation gemäß E6 entfernen.

---

## E9 — Claims-to-Code-Audit als Release-Gate

### Entscheidung

Vor dem ersten formalen Release und bei jeder Änderung einer Produktzusage
wird ein Claims-to-Code-Audit durchgeführt.

**Umsetzung #517:** Die maschinenlesbare Quelle liegt in
`docs/capabilities/control-matrix.json`; `docs/CAPABILITY_MATRIX.md` wird daraus
deterministisch erzeugt. Code und ausgelieferte Konfiguration bleiben
maßgeblich für Verhalten und Aktivierung. Die Matrix ist ausschließlich die
Quelle für Auditbewertung, Evidence-/Claim-Zuordnung und das Profil
`reference-worker-first-release`. Ein CI-Driftcheck vergleicht Gate-Registry,
External-Gates, Middleware-Reihenfolge, Workflow-Commands, Gate-Profile,
Beweisanker, aktive Claim-Dokumente und den Digest aller auditierten Quellen.
Die Baseline bleibt solange `blocked`, bis jeder namentliche Zielkontrollpunkt
`ready` ist; #479 hat davon getrennt die SemVer festgelegt.

**Erweiterung #572:** Allgemeine maschinenlesbare Laufzeitfakten werden nicht
in die Wirksamkeitsmatrix hineingezwängt. Das versionierte
`docs/capabilities/document-contract.json` klassifiziert alle aktiven Dokumente
und bindet Hochrisikoabschnitte an konkrete Code-/Configquellen. Derselbe
`tools/control_matrix.py`-Check erzeugt `docs/RUNTIME_REFERENCE.md`, den
ADR-Index und ausgewählte aktive Fragmente; es entsteht keine zweite
Capability-Matrix. ADR-0635 projiziert dieses Inventar zusätzlich über ein
eigenes Navigationsmanifest in einen nicht autoritativen lokalen Wiki-Build.
Das Wiki-Manifest ordnet Quellen und Seiten, bestimmt aber weder
Laufzeitverhalten noch Audit-, Gate- oder Release-Autorität.

Ein globaler Quelldigest bleibt nur ein ergänzender Vollständigkeitsalarm: Er
belegt, dass sich irgendeine auditierte Quelle geändert hat, bindet die
Änderung aber nicht an eine konkrete Aussage. Durch routinemäßiges Aktualisieren
wird er semantisch wirkungslos. Sein Umfang sind getrackte, nicht generierte
Produkt-, Policy-, Proof- und Claim-Quellen hinter dem aktiven
Review-Inventar; dazu gehört auch die aktive manuelle Historie in
`CHANGELOG.md`. Lokale/ungetrackte Dateien und die aus diesen Quellen
generierten Referenzausgaben bleiben ausgeschlossen (#596). Für manuelle
Aussagen ist deshalb weiterhin der abschnittsbezogene Quelldigest maßgeblich;
generierte Aussagen werden durch exakten Rendervergleich an ihre Quellen
gebunden.

Beide Verträge behandeln dieselbe Fehlerklasse wie #399: Ein formal vorhandenes
Signal erhält keine Entscheidungs- oder Nachweisautorität, solange es nicht an
Gegenstand, fachlichen Kontext und geltende Policy gebunden ist.

**Geltungsbereich: alle wesentlichen Produktbehauptungen.** Dazu gehören nicht
nur Schutzkontrollen, sondern auch Lizenz, Premium-/Free-Status,
Installationswege, unterstützte Provider und Plattformen, Authentisierung,
Persistenz und Retention, Konfiguration, Versionen, APIs und
Compliance-Darstellungen. Die Nachweistiefe richtet sich nach dem Claim-Typ.

Für v1 wird nur der als `enforced` bezeichnete Kontrollsatz klein gehalten.
Acht nachgewiesene Gates sind mehr wert als dreißig behauptete; daraus folgt
aber keine Ausnahme anderer Produktbehauptungen vom Audit.

### Verbindliche Regel für Behauptungen

Eine Kontrolle darf in aktiver Produktdokumentation nur als `enforced`
bezeichnet werden, wenn sie:

- **implementiert** ist — produktiver Code existiert;
- **verdrahtet** ist — ein realer Produktionspfad ruft ihn auf;
- **entscheidungswirksam** ist — das Ergebnis beeinflusst den Ablauf;
- **fail-closed** ist, falls als Schranke bezeichnet — Fehler, fehlende Daten
  und nicht prüfbare Zustände umgehen sie nicht stillschweigend;
- **commitgebunden** nachgewiesen ist — für den geprüften Candidate-Commit;
- **positiv und negativ getestet** ist — Durchlassen und Blockieren;
- **extern nachweisbar** ist — Audit, PR-Status oder anderes Artefakt erklärt
  die Entscheidung;
- **aktuell dokumentiert** ist — Name, Umfang und Einschränkungen entsprechen
  dem Code.

Bis alle anwendbaren Punkte erfüllt sind, lautet der Status beispielsweise
`implemented`, `unwired`, `advisory`, `telemetry`, `experimental`, `unknown`
oder `planned`, aber nicht `enforced`.

Andere Claim-Typen erhalten passende Nachweise:

- Lizenz: Root-Lizenz, Paketmetadaten und gebaute Artefakte stimmen überein.
- Installation: sauberer Installations-Smoke aus dem Release-Commit.
- Provider/API: produktiver Adapter beziehungsweise Endpoint sowie Positiv- und
  Fehlerpfad.
- Persistenz/Retention: Speicherort, Neustart-, Rotations- und Löschtests.
- Version: Tag, Commit, Paket, CLI, Dashboard und Artefakte sind korreliert.
- Compliance: technische Evidence und Mapping werden von einer rechtlichen
  Konformitäts- oder Zertifizierungsbehauptung getrennt.

### Ablauf je Behauptung

1. Behauptung und Fundstelle erfassen.
2. Claim-Typ und dafür anwendbare Evidenzanforderungen bestimmen.
3. Produktiven Aufrufpfad, Artefakt oder Konfiguration nachweisen.
4. Bei Kontrollen Required/Optional/Advisory/Telemetry bestimmen.
5. Anwendbaren Negativpfad, Fehlerverhalten und Commit-/Artefaktbindung prüfen.
6. Vorhandenes Issue zuordnen.
7. Sinnvolle fehlende Funktion implementieren; andernfalls die Behauptung
   korrigieren.
8. Dokumentation erst nach Umsetzungsnachweis auf den belegten Status setzen.

#513 etabliert Datum und abgeglichenen Commit statt unklarer Phasenangaben;
der Vertrag ist für alle aktiven Dateien unter `technische Beschreibungen/`
umgesetzt und durch einen Doku-Regressionstest abgesichert.
#487 definiert die verbindliche Versionspolitik und `v2.0.0a1` als ersten
formalen Alpha-Tag. Dessen Tag-CI blieb wegen eines im ephemeren Checkout
ersetzten annotierten Tagobjekts korrekt rot; der Tag bleibt unverändert und
unveröffentlicht. #489 vereinheitlicht die sichtbaren Produkt- und Buildangaben.
Die in #490 implementierte Release-Gate-Mechanik bindet Tag, Changelog, Commit,
CI, Runtime-Flächen, Wheel/sdist und Prüfsummenmanifest fail-closed.
`v2.0.0a2` bestand die vollständige Tag-CI und wurde als Gitea-Prerelease mit
manifestgebundenen Artefakten veröffentlicht. #488 nutzt diesen echten
SCM-Anker als strikte setuptools-scm-Authority; ein statischer Parallelwert
oder plausibler Release-Fallback existiert nicht. `v2.0.0a3` erweitert die
Kette über #555 um das manifest- und digestgebundene Container-Release; dessen
konkrete Evidence steht unter E12 und im Container-Runbook. Die Dachkriterien von #479
sind gegen Kindissues, das annotierte Tagobjekt
`84c909cbdb1e712a2ff2ba89ef09ac414c6c8099`, Release-Commit
`9f656f70af6cf24fc7a4119cd3db4439bbdf2a03`, Tag-CI #496 / Jobs #538–#541,
Gitea-Prerelease #9 und die erneut heruntergeladenen Artefakte einzeln
abgenommen; die Versionierungs- und Releasekette ist damit abgeschlossen.
Die vollständigen Artefaktprüfsummen stehen in `docs/VERSIONING.md`. Die
Kleinfunde aus #485 sind umgesetzt oder mit belegtem Restscope in bestehende
beziehungsweise eigenständige Issues überführt. #655 entscheidet den dort nur
gefundenen Planning-Retry-Vertrag getrennt: Nach dem einzigen Retry darf
`PlanValidated` ausschließlich bei `overall_pass=true` entstehen; ein
verbleibender Split- oder Pre-Check-Fehler blockiert. Geschlossene Korrekturen
wie #475 und #486 werden als Nachweis referenziert, nicht neu erfunden. #731
ordnet formale Acceptance-Contract-Fehler in genau diesen bestehenden Retry
ein: Der erste Entwurf erhält keine Authority, der korrigierte Entwurf wird
unabhängig von einer Score-Steigerung erneut kanonisch geparst, und nach einem
verbrauchten Retry gibt es weder einen zweiten LLM-Aufruf noch Text-Rewriting.
#754 wendet dieselbe Regel auf `[TEST]`-Selektoren an: Der Contract akzeptiert
vor `PlanPosted` nur die Grammatik, die Gate 11 tatsächlich ausführen kann.
Bloße Dateipfade werden weder als freigabefähige Evidence dargestellt noch
still in einen Full-Suite- oder anderen Runner-Aufruf umgeschrieben.
#756 bindet diese syntaktische Grenze zusätzlich an die bereits vorhandene
projektspezifische Runner-Authority. Die am 2. September 2026 bestätigte
Minimalentscheidung ist fail-closed vor `PlanPosted`: explizites
Control-Plane-`test_cmd` hat Vorrang vor Marker-Autodetection; Planning und
Doctor prüfen Runnerinstallation und bekannte Selektorgrammar ohne Tests
auszuführen. Der Planning-Prompt erhält aus derselben bootstrapgebundenen
Policy ausschließlich Runnerart und zulässige Selektorform, nicht den
Control-Plane-Befehl; dadurch widerspricht auch der einzige Retry der
Readiness-Abhilfe nicht. Bei fehlender oder inkompatibler Readiness gibt es
nach dem einmaligen Planning-Retry keinen Candidate, kein Umschreiben, keine
Werkzeuginstallation und keinen Fallback.

---

## E10 — Integration statt Nachbau: Framework in the Middle

### Entscheidung

S.A.M.U.E.L. baut reife Prüfwerkzeuge ohne belegten Mehrwert **nicht nach**. Es
bindet sie ein und normalisiert ihre Ergebnisse zu commitgebundener,
policy-wirksamer Evidence.

Das ist die Auflösung des Positionierungsproblems auf technischer Ebene: Nicht
„noch ein Scanner", sondern die Schicht, die vorhandene Scanner, CI-Systeme
und Agenten an eine gemeinsame, durchsetzbare Merge-Entscheidung bindet.

### Regel für jede Prüffähigkeit

1. **Existiert ein etabliertes Werkzeug?** Dann wird ein Adapter gebaut, keine
   eigene Implementierung.
2. **Gibt es ein geeignetes Austauschformat?** Dann wird es als Payloadformat
   verwendet: SARIF für statische Code-Findings, JUnit für Testergebnisse,
   CycloneDX/SPDX für Komponenten- und SBOM-Daten, in-toto/SLSA-Muster für
   Attestations- und Provenienzbelege sowie SCM-native Checks, wo sie die
   maßgebliche Quelle sind. SARIF ist kein Universalformat für alle Evidence.
3. **Eigene Implementierung nur**, wenn kein Werkzeug existiert, das Werkzeug
   nicht selbst hostbar ist, oder eine Mindestfähigkeit für den
   Standalone-Betrieb gebraucht wird (siehe unten).
4. **Der zusätzliche Prüfwert liegt im Binden:** Finding an
   Contract, Base-SHA, Head-SHA, Policy-Version und Merge-Entscheidung koppeln.
   Einzelne Werkzeuge und SCM-Plattformen liefern bereits Teile dieser Bindung;
   S.A.M.U.E.L.s Ziel ist die gemeinsame Korrelation über Werkzeuge, Worker und
   unterstützte SCMs hinweg.

Alle Eingänge werden in einen internen, versionierten `EvidenceEnvelope`
normalisiert. Er enthält mindestens Repository, Base-/Head-SHA, Contract-Hash,
Policy-Digest, Tool-Identität/-Version/-Digest, Quelle, Vertrauensniveau,
Zeitpunkt, Vollständigkeit/Trunkierung, Schema und das formatabhängige Payload.

### Standalone-Pflicht

Standalone bedeutet: ohne externes SaaS, fremdes Control Plane oder
proprietären Pflichtdienst selbst hostbar und mit einem dokumentierten
Default-Profil nutzbar. Bewährte gebündelte Open-Source-Werkzeuge sind damit
vereinbar. Eigene Implementierungen sind nur **Mindestfähigkeit und Fallback**,
wenn ihr begrenzter Schutzwert nachgewiesen ist; sie werden entsprechend
beschrieben:

> Eingebaute Basisprüfung. Für vollständige Abdeckung ein spezialisiertes
> Werkzeug einbinden.

Das gilt insbesondere für die eigene Secret-Erkennung (#481) und die eigene
Qualitätsprüfung. Sie werden nicht auf das Niveau spezialisierter Werkzeuge
ausgebaut — sie werden ehrlich als Basis benannt und durch Adapter ergänzbar
gemacht.

### Bereits vorhandene Ansatzpunkte

- **Remote-CI** ist über #441 als Required Check der SCM-Plattform
  nachgewiesen. #520 ergänzt einen schmalen Pull-only-Leser für vorhandene
  Gitea-SCM-Checks. Seine normalisierte Observation und das davon getrennte
  Assessment bleiben ausdrücklich advisory und sind keine Gate-Authority.
- **`IExternalGate` und die heutigen Gates** für Coverage-Diff, Pfad-Risiko und
  Symbol-Resolution zeigen einen internen Erweiterungspunkt. Sie sind noch
  keine Adapter für vertrauensbewertete Befunde fremder Werkzeuge.
- **SARIF-Export** existiert. #520 liest SCM-native Run-/Check-Facts, keinen
  SARIF- oder universellen Scanner-Eingang.
- Das dokumentierte Arbeitsprinzip, saubere Integrationsflächen für externe
  Werkzeuge bereitzustellen statt Fähigkeiten intern nachzubauen, ist damit
  von der Absicht zur verbindlichen Entscheidung erhoben.

### Sicherheitsauflage

Eingebundene Werkzeuge sind Fremdquellen. Es gilt E7: Ergebnisse werden
strukturiert übernommen, begrenzt, nie roh in einen privilegierten
Modellkontext gegeben. Ein Adapter erhöht die Angriffsfläche und braucht
dieselbe Behandlung wie jede andere unvertrauenswürdige Eingabe.

### Umsetzungsstand und Restgrenze

#520 setzt die kleinste reale Stufe als begrenzte Gitea-Actions-/SCM-Check-
Observation mit in-toto-Statement-v1-Rahmen und festem `authority=none` um.
Sie beauftragt keinen Run, importiert keine SARIF-Findings und wird nicht in
`IExternalGate` eingespeist. Weitere Formate folgen ausschließlich realem
Bedarf. Die requestgebundene Required-Verwendung, Trusted Execution und der
atomare Provider-Cutover bleiben #679 und werden nicht in #468, #474 oder
#481 gepresst.

---

## E11 — Fähigkeitsabsicht erhalten, Produktionscode bewusst kuratieren

### Entscheidung

Eine validierte, für das Produktziel sinnvolle Fähigkeit wird als Absicht in
ADR, Capability-Matrix oder Issue erhalten. Daraus folgt nicht, dass
unverdrahteter, doppelter oder experimenteller Code im Produktionspaket liegen
bleiben muss. Erst nach Wirksamkeitsnachweis wird die Fähigkeit als aktive
Schranke beworben.

**Bewahrt wird die begründete Fähigkeitsabsicht, nicht zwingend jeder heutige
Codepfad.**

### Wann Code tatsächlich entfernt wird

Code wird entfernt oder aus Produktionsimports quarantänisiert, wenn
mindestens einer dieser Fälle belegt ist:

1. **Nachgewiesene Dublette** — eine zweite Implementierung derselben
   Fähigkeit existiert, ist aktiv, und die Parität ist geprüft (E6 Schritt 2,
   #477).
2. **Toter oder unvollständiger Pfad** — kein Produktionscode ruft ihn auf und
   er besitzt keinen bestätigten kurzfristigen Owner und Umsetzungsplan.
3. **Ersetzt durch Integration** — ein eingebundenes Fremdwerkzeug deckt die
   Fähigkeit vollständig ab **und** die Standalone-Pflicht aus E10 ist
   weiterhin erfüllt.
4. **Unvertretbare Sicherheits-/Wartungsfläche** — der Pfad erzeugt eine zweite
   Policy-Wahrheit, suggeriert nicht vorhandenen Schutz oder erhöht die
   Angriffsfläche ohne nachgewiesenen Nutzen.
5. **Ausdrückliche Nachfolgeentscheidung** in diesem Dokument.

Vor Entfernung werden Nutzerabhängigkeiten, Produktionsaufrufe, Konfiguration,
Tests und einzigartige Semantik geprüft. Die Absicht bleibt bei Bedarf in
Issue/ADR und Git-Historie nachvollziehbar. In Zweifelsfällen lautet die
Antwort: Status korrigieren, Scope entscheiden und experimentellen Code aus
dem aktiven Pfad isolieren.

### Begründung

Ein Ein-Personen-Projekt muss sowohl verlorene Arbeit als auch dauerhafte
Komplexität vermeiden. Auch `planned`-, Experimental- und Totcode verursachen
Audit-, Test-, Sicherheits- und Verständniskosten. Git-Historie und ein
begründetes Issue bewahren eine Idee günstiger als ungenutzter Produktionscode.
Konservativer Claim und bewusst kleiner aktiver Kern haben Vorrang.

---

## E12 — Container-Artefakt registry-neutral, Release-Identität gemeinsam

### Entscheidung

#555 führt keinen SCM- oder Registry-Adapter in den Produktkern ein. Das
vorhandene `tools/release_gate.py` bleibt alleinige Authority für Produkt-Tag,
Version, vollständigen Commit, Wheel und sdist. Ein getrenntes
Maintainerwerkzeug erweitert genau dieses Manifest erst nach einem
digestgebundenen OCI-Build und einem realen Smoke des gepushten Digests.

Registry-Host, Namespace, Repository, Login und Transportkonfiguration sind
Betreiberparameter. Gitea ist das aktuelle Veröffentlichungsziel dieses
Repositories, aber weder im Dockerfile noch im Produkt-Runtimepfad fest
verdrahtet. Eine andere OCI-kompatible Registry ersetzt den Parameter, nicht
eine Produktarchitektur.

### Bindungen und Grenzen

- Basisimage, Plattformmanifest, Build-/Runtime-Locks und ihre Generatorinputs
  bilden den überprüfbaren Buildvertrag. Ein beweglicher Image-Tag oder eine
  offene Dependency-Auflösung genügt nicht.
- OCI-Version und -Revision werden gegen Tag und vollständigen Release-Commit
  geprüft; die Runtime- und Dashboard-Flächen müssen dieselbe Identität
  melden.
- Das Registry-Digest ist die Installationsauthority. Der lesbare Produkt-Tag
  bleibt create-only und dient Auffindbarkeit und Auditzuordnung.
- Operator-Secrets, Operator-Konfiguration, Git-Metadaten und Arbeitsdaten
  bleiben außerhalb von Build-Kontext und Image. Compose injiziert sie erst
  beim Betrieb.
- CI prüft den Offline-Vertrag ohne Docker-Socket. Build, Push und frischer
  Compose-Smoke laufen bewusst auf einem kontrollierten Docker-Host und sind
  keine behauptete Fähigkeit des socketlosen Gitea-Jobcontainers.

Update, Rollback, Abbruch und der konkrete Infrastrukturaufruf stehen in
`docs/CONTAINER_RELEASE_OPERATIONS.md`. `v2.0.0a2` bleibt historisch ohne
Container-Artefakt. `v2.0.0a3` erfüllt die Veröffentlichungsbedingung durch
Schema-2-Manifest, Registry-Digest und tatsächlich grünen Compose-Smoke; die
unveränderlichen Identitäten und CI-/Release-IDs stehen revisionsfest im
Runbook. Diese konkrete Betreiber-Evidence ändert die registry-neutrale
Entscheidung nicht.

---

## E13 — Installierter Console-Entry-Point als Betriebsgrenze

### Entscheidung

Der von der installierten Distribution erzeugte Console-Entry-Point `samuel`
ist der einzige unterstützte Betriebsaufruf. systemd-Units, Container und
Operatoranleitungen verwenden ihn direkt. `python -m samuel` bleibt höchstens
ein Komfortpfad in einem bewusst vertrauenswürdigen Source-Checkout und ist
kein zulässiger Startweg aus einem potenziell unvertrauenswürdigen
Zielrepository.

### Begründung und Grenze

Die Python-Modulauflösung geschieht vor jedem Code des beabsichtigten Pakets.
Ein Zielrepository mit eigenem Top-Level-Paket `samuel` kann den Modulaufruf
daher übernehmen, bevor S.A.M.U.E.L. seine Herkunft prüfen könnte. Der
Console-Entry-Point startet dagegen aus dem Script-Verzeichnis der
Installation. Ein Regressionstest mit kollidierendem Fremdpaket bindet genau
diese Aussage; systemd- und Containerverträge weisen eine Rückkehr zum
Modulaufruf ab.

`PROJECT_ROOT` und Working Directory bleiben zulässiger Arbeits- und
Konfigurationskontext, besitzen aber keine Autorität über Produktcode,
Produktversion oder Build-Revision. Manipuliertes `PYTHONPATH`, ein ersetztes
Console-Script oder eine kompromittierte Installation bleiben vorgelagerte
Supply-Chain-/Betreibergrenzen und werden nicht als durch diese Entscheidung
gelöst behauptet. Die ausführliche Entscheidung steht in
[`ADR-0583`](adr/0583-installed-cli-entrypoint.md).

---

## E14 — Atomare Workspace-Transaktion des Implementation-LLM-Loops

### Entscheidung

Der LLM-Loop des eingebauten Referenz-Workers ist eine atomare,
prozesslokale Workspace-Transaktion. Vor dem ersten Schreibversuch auf einen
Pfad werden dessen Inhalt, Existenz und Dateimodus festgehalten. Nur ein
erfolgreiches Gesamtergebnis übernimmt die angewendeten Patches. Jedes
kontrollierte erfolglose Loop-Ende sowie eine im Loop ausgelöste Exception
stellt alle berührten Pfade auf diesen Vorzustand zurück und entfernt im Lauf
neu erzeugte, danach leere Verzeichnisse.

Die Wiederherstellung verwendet ausdrücklich weder `git reset`, Checkout noch
Stash. Damit bleibt ein vor dem Lauf vorhandener Operatorzustand die
Rollback-Basis und wird nicht durch irgendeinen Repository-Stand ersetzt. Ist
der Restore nicht vollständig möglich, wird der ursprüngliche Auslöser als
`trigger_reason` erhalten, die terminale Ursache lautet jedoch
`workspace_rollback_failed`; eine teilweise Wiederherstellung darf nicht als
erfolgreiches Rollback oder als ursprünglicher Token-/Patchfehler erscheinen.

### Begründung und Grenzen

Mehrere LLM-Runden arbeiten absichtlich auf dem echten Zwischenstand, damit
ein Retry bereits erfolgreiche Teilpatches sehen kann. Daraus folgt aber keine
Erlaubnis, diese Teilpatches nach einem insgesamt fehlgeschlagenen Lauf an den
nächsten Run zu vererben. Die frühere Round-Checkpoint-Struktur enthielt weder
persistierten Prompt noch vollständigen Workspacezustand und ist deshalb kein
gebundener Resume-Vertrag. Ein restart-fähiges Resume erfordert einen eigenen,
persistenten Zustandsvertrag (#482) und wird in #598 nicht behauptet.

Diese Entscheidung endet mit dem Rückgabewert des LLM-Loops. Ein abrupter
Prozess-/Hostabbruch kann die In-Memory-Transaktion nicht ausführen; deshalb
bleibt der Clean-Workspace-Preflight verbindlich. Die vorgelagerte
Patchziel-Begrenzung ist als E15 ein eigener, nun wirksamer Vertrag (#600).
Die Git-Control-Plane innerhalb der Projektwurzel schützt E15 als
vorgelagerte eigene Grenze (#603). Fachlich abgelehnte Applier-Patches werden
vor einem sichtbaren Write vollständig geprüft und bleiben mutationsfrei
(#601); I/O-Fehler während des eigentlichen Writes fallen weiter unter diese
Loop-Transaktion. Das gilt für vollständige Python-WRITEs ebenfalls; ein nur
vorsorglich erfasster, nach der Ablehnung nachweislich unveränderter Pfad wird
aus der Transaktion freigegeben und beim terminalen Rollback nicht neu
geschrieben (#606). Getrennt offen bleiben die nachgelagerte Branch-/Stage-/
Commit-/Push-Finalisierung. Das kumulative Workflow-Tokenbudget aus #549 liegt
vorgelagert im LLM-/Authority-Pfad und wird nicht durch die Loop-Transaktion
dargestellt.

### Konsequenz

`TokenLimitHit` und das terminale `WorkflowBlocked` führen nur inhaltsfreie
Rollback-Anzahlen und den Status. Nach vollständigem Restore enthält
`patches_applied` keine übernommenen Patches; die Zahl der zurückgenommenen
und zuvor als angewendet gezählten Patches bleibt separat auditierbar. Ein
späterer Run beginnt damit aus dem Zustand vor dem fehlgeschlagenen Loop,
solange kein vorgelagerter harter Prozessabbruch stattgefunden hat.

---

## E15 — Projektwurzel-gebundene Patchziele vor dem Apply

### Entscheidung

Der eingebaute Referenz-Worker behandelt jedes vom LLM gelieferte Patchziel als
unvertrauenswürdige Eingabe. Strukturierte und textuelle Patchoperationen
verwenden ausschließlich normalisierte relative POSIX-Pfade. Vor dem ersten
Apply einer Modellantwort werden alle Ziele gegen die aufgelöste
Projektwurzel kanonisiert und gemeinsam validiert. Ein absolutes POSIX-,
Windows-, Drive- oder UNC-Ziel, ein `..`-Segment, ein nicht portabler
Backslash, ein Steuerzeichen oder ein kanonisch externes Symlink-Ziel beendet
den Loop fail-closed als `unsafe_patch_target`, ohne irgendeinen Patch dieser
Antwort anzuwenden.

Ein zulässiger Symlink, dessen Ziel innerhalb der Projektwurzel bleibt, wird
auf den kanonischen Zielpfad festgelegt. Dieser kanonische relative Pfad wird
anschließend vom Applier, der Workspace-Transaktion, dem Loop-Ergebnis und dem
Git-Staging verwendet. Dadurch kann eine spätere Änderung des ursprünglich
gelieferten Alias nicht den bereits gewählten Apply-Pfad umleiten.

Unabhängig von dieser Containment-Prüfung ist jeder Pfadbestandteil `.git`
case-insensitiv reserviert. Einmal pro Loop fragt der Worker über den
bestehenden Core-Git-Ausführungspfad die effektiven absoluten Git-, Common-,
Index- und Object-Pfade ab. Damit sind Verzeichnis- und Datei-Marker,
verschachtelte Worktrees/Submodule, linked oder separate Git-Dirs und von Git
wirksam berücksichtigte `GIT_*`-Overrides auch dann geschützt, wenn der
administrative Pfad nicht `.git` heißt. Ein Ziel auf oder unter diesen Pfaden
endet ebenfalls fail-closed mit der inhaltsfreien Klasse
`git_control_plane`.

### Begründung und Grenzen

Die Verbindung `project_root / llm_path` ist keine Sicherheitsgrenze:
absolute rechte Operanden verwerfen den linken Pfad, `..` kann ihn verlassen,
und ein intern wirkender Symlink kann extern auflösen. Eine nachgelagerte
Diff- oder Gate-Prüfung ist dafür zu spät, weil die Mutation bereits vor dem
Candidate-Commit erfolgt. Die Prüfung gehört deshalb unmittelbar vor den
ersten Lese-, Snapshot- und Schreibzugriff und muss alle Patches derselben
Antwort erfassen, damit deren Reihenfolge keine Teilmutation erlaubt.

Die Grenze ist keine allgemeine Dateisystem- oder Prozess-Sandbox und schützt
nicht gegen einen gleichzeitig privilegiert mutierenden lokalen Akteur. Ein
Fehler der read-only Git-Pfadauflösung öffnet die reservierte `.git`-
Namensgrenze nicht, kann bei einem nicht standardmäßig und ohne für Git
auflösbaren Verwaltungspfad aber nur diese lexikalische Mindestgrenze liefern.
Die mutationsfreie fachliche Ablehnung eines Einzelpatches ist in #601
umgesetzt. Der vollständige Python-WRITE verwendet seit #606 denselben
AST-Hook vor Verzeichnisanlage und Write; Gate 9 bleibt davon getrennt die
commitgebundene Syntaxautorität über den exakten Candidate-Blob.

### Konsequenz

Reason-Codes, Terminaldiagnose und `WorkflowBlocked` spiegeln keinen
abgelehnten LLM-Pfad. Sie enthalten nur eine begrenzte Fehlerklasse, Anzahl und
die vorhandene inhaltsfreie Rollback-Evidence. Normale neue Unterverzeichnisse,
nicht-Python-Dateien, normale Dotfiles und kanonisch interne Ziele außerhalb
der effektiven Git-Control-Plane bleiben verfügbar. Diese Entscheidung gilt
für den eingebauten Worker; ein späterer fremder
`ImplementationPort` muss dieselbe Wirkung über seinen Conformance-Vertrag
belegen, nicht zwingend denselben Resolver wiederverwenden.

---

## E16 — Versionierter lokaler Runtime-State

### Entscheidung

Queryfähige Beobachtungs-/Run-Historie und spätere transaktionale
Resume-Autorität verwenden einen versionierten lokalen SQLite-State unter dem
bestehenden `agent.data_dir`. Audit-JSONL bleibt Compliance-Evidence und wird
nicht zur Runtime-Datenbank umgedeutet. Vier fachliche Ports trennen immutable
Beobachtungen, nachholbare nicht blockierende Run-Projektionen und
fail-closed Autoritätszustand sowie nicht löschendes Retention-Inventar;
Diagnose/Backup bilden eine fünfte
Operatorgrenze.

SQLite ist wegen Abfragen, unabhängiger Retention und transaktionaler
Claims/Intents gewählt, nicht wegen behaupteter Parallelität. Der Verlust der
direkten JSON-Inspektion wird durch `samuel state status|dump --json`
ausgeglichen. Der Referenzadapter läuft nur auf als lokal klassifizierten
Dateisystemen, verwendet ein versioniertes WAL-Schema und sichert aktive Daten
über die SQLite Backup API statt Dateikopie.

### Umsetzung und Grenze

#625 lieferte Schema v1, Ports, Health, Diagnose und Backup. #627 hob auf
Schema v2 an und migrierte gebundene Rohbeobachtungen, versionierte
Scoreableitungen, Quality-EWMA und redigierte Dashboard-Run-Projektionen
einseitig nach SQLite. Serien binden Evidence-Herkunft, Observation-Schema,
Scoring-Policy und Formel; Auditrotation verdrängt keine gespeicherten Runs.
Die alten JSON-Quellen werden erst nach checksumgebundenem Import archiviert.

#629 hebt auf Schema v3 an. Healing-Claims, Round-Diagnose, gebundene
Finalisierungs-Checkpoints, Operations-Intents und Lease-CAS liegen nun hinter dem
fail-closed Authority-Port. `bound_healing_attempts.json` wird transaktional
importiert und checksumbenannt archiviert. Instanz-UUID, monotone Epoch und ein
synchroner Witness außerhalb des DB-Backup-Artefakts erkennen Rückstand oder
fremde Herkunft und führen sichtbar in Reconcile; CLI, kritischer Authority-
Health-Check, Dashboard und ein gemapptes Ereignis zeigen ihn, während Healing
vor dem LLM-Aufruf blockiert wird.

Der Worktree-Vertrag aus ADR-0618 ist über #618 umgesetzt: ein gemeinsamer
`IWorkspaceManager` verwaltet den mutierbaren Run- und den detached
Verifikationsbaum, hält Branch-/Prozesslocks, Kapazitätsbuchung, Quarantäne und
Prune zusammen und finalisiert Commits hookfrei über Parent-/Tree-Identität
und Ref-CAS. Die Workspace-Registry speichert eine 168-Stunden-Operatorfrist;
sie löscht keine Quarantäne automatisch. Nur ein begründetes, explizites
Discard terminalisiert geprüfte Evidence für den anschließenden Prune. Das ist
Git-/Dateistand-Containment, keine Prozesssandbox.

Mit #633 setzt ein eigener Koordinator die sicheren Boundaries
`commit_pending`, `push_pending`, `gates_pending` und `pr_pending` fort. Er
übernimmt zuerst den OS-Lock des vorhandenen Run-Worktrees, dann ein
abgelaufenes Lease per CAS und prüft anschließend Repository-/Run-/Workspace-,
Contract-/Policy-/Schema-, Git- und SCM-Bindung. Commit-/Push-/PR-Intents und
Postconditions autorisieren nur identische, bereits begonnene Wirkungen;
abweichender Zustand wird quarantänisiert. Halbe LLM-Runden bleiben bewusst
nicht resumefähig. Löschende Retention und unterstützter Restore-Abgleich
werden dadurch nicht vorweggenommen. Vollständige
Entscheidung und Abhängigkeitskette stehen in
[ADR-0482](adr/0482-runtime-state-store.md).

#666 hebt auf Schema v4 an und setzt Stufe 5a um. Ein vom Witness-Mutex
getrennter Lifecycle-Lock umfasst jeden DB-Leser/-Schreiber und den gesamten
Restore. Der Adapter prüft ein Backup in einer Staging-DB, persistiert vor dem
Austausch einen Sentinel, erzeugt eine neue `instance_uuid` mit global
monotoner Epoch, wechselt die DB atomar ein und synchronisiert erst danach den
Witness. Claims, Intents, Checkpoints, Leases, Authority-Records, Workspaces
und bekannte SCM-Wirkungen werden über bestehende Ports inventarisiert.
`scan_failed` verlangt einen erfolgreichen Rescan; `reconcile-complete`
verlangt null `unresolved`. Eine Supersession ist explizit, begründet und
übernimmt keine Klassifikationen. Healing und Resume bleiben bis zum Abschluss
blockiert. Autoritätsereignisse tragen ab dem Serienschnitt
`authority.v2` zusätzlich `instance_uuid` und `authority_epoch`.

Der Nachtrag vom 2026-08-30 entscheidet Stufe 5. Stufe 5a ist mit #666 aktiv:
Unterstützter Restore erzeugt unter einem eigenen Lifecycle-Lock eine neue
Autoritätslinie und endet erst nach vollständigem Reconcile. Retention wird
über einen mechanisch vollständigen Katalog, kategorieweise Policy-Digests,
ein ausgeliefertes `eu_operational`-Profil und Dry-Run-Evidence vorbereitet;
ein Profil-/Rollenwechsel entzieht den betroffenen Freigaben ihre Gültigkeit.
Löschung wird erst danach je Kategorie separat aktiviert. Quality-EWMA,
Legacy-Importmarker sowie permanente At-most-once-/Autoritäts-Tombstones sind
von zeitbasierter Löschung ausgenommen. Katalog/Policy/Dry-Run/Replay sind in
5b getrennt vom weiterhin offenen kategorieweisen Vollzug der Stufe 5c.

#667 setzt Stufe 5b mit Schema v5 um. Der maschinengeprüfte Katalog deckt 16
State-Tabellen, Workspace-Registry, Audit-JSONL, Managed Backups und
Quarantäne in beide Richtungen ab. Kategorie- und Profil-/Rollendigest binden
append-only Operatorfreigaben; die globale Notabschaltung bleibt sichtbarer
Runtimezustand außerhalb dieser Digests. Alle ausgelieferten Kategorien sind
höchstens `report_only`, unbekannte oder unvollständig klassifizierte Objekte
blockieren einen späteren Vollzug. Managed Backups verwenden die SQLite
Backup API und eine eigene Registry. Score-Replay teilt den Ableitungscode mit
der Live-Beobachtung und bleibt event- sowie EWMA-frei. Es existiert in diesem
Schritt weder Delete-Code noch ein aktivierbarer `enforce`-Modus.

#673 setzt das deaktiviert ausgelieferte 5c-Ausführungsfundament mit Schema v6
um. Zwei zusätzliche, nicht zeitbasiert löschbare Tabellen halten aktuelle
Kategorie-Autorität und append-only Ausführungsbelege. Der neue fail-closed
Port besitzt keine generische Tabellen-/SQL-Schnittstelle; allein
`score_derivations` ist als Strategie registriert. Aktivierung und Ausführung
sind getrennte, begründungspflichtige Operatoraktionen und binden denselben
deterministischen Plan einschließlich Plan-Schemaserie, Klassifikations-/
Schutzvertrag und ausgewertetem Kandidatenstatus. Globaler Stop, Reconcile,
fehlende/stale Authority,
Plan-Drift und suspendierte Kategorien blockieren. Restore entzieht bestehender
Retention-Autorität die Wirksamkeit. Ausgeliefert bleibt jede Kategorie
`report_only`; der Canary ist kein Ersatz für reale Rollout-Evidence und #668
bleibt bis zur ersten produktiven Kategorieaktivierung offen.

#668 konkretisiert diese bestehende Authority ohne neue Produktentscheidung:
Ein Enforce-Grant bindet Cutoff und serverseitige Aktivierungszeit. Die
effektive Kalenderfrist wird gegen diese Grantzeit geprüft; alte Grants ohne
Bindung müssen neu aktiviert werden. Katalog, Feld-/Payloadklassifikation und
Kandidaten werden im Vollzug transaktional revalidiert. Bereits persistierte
Receipts sind historische Evidence und werden vor heutigen Wirkungsregeln
identitätsgeprüft gelesen.

---

## E17 — Benötigte Capability-Ebenen, Providergrenze und Referenzbetrieb

### Entscheidung

Für austauschbare Nicht-Core-Capabilities werden Core-Vertrag, mitgelieferte
Referenzimplementierung und externer Adapter/Provider als mögliche Ebenen
klassifiziert. Nur benötigte Ebenen werden implementiert; ein externer Port
entsteht beim zweiten realen Provider/Anwendungsfall oder früher wegen einer
Security-/Authority-Grenze. Die Referenzdistribution darf sofort nutzbare
Komponenten mitbringen, aber keine versteckte Sonderautorität besitzen.
Bestehende Funktionen werden stabilisiert und nur nach funktionsgleichem,
evidenzgebundenem Cutover ersetzt.

S.A.M.U.E.L. baut keine allgemeine CI-, Sandbox-, Plugin-Lifecycle-, IAM-,
Agenten- oder Dokumentationsplattform. Rollenbezogene Standards und bestehende
Werkzeuge werden über schmale Ports eingebunden. Das bevorzugte Profil umfasst
OpenAPI, CloudEvents/CDEvents, in-toto/DSSE, SARIF, JUnit, CycloneDX/SPDX,
SCM-Checks, optional MCP/A2A, OIDC, OCI und OpenTelemetry. Kein einzelnes Format
wird zum Universalvertrag erklärt.

Candidate-Code soll außerhalb des Core in einem Execution-/CI-Provider laufen.
S.A.M.U.E.L. bindet und bewertet dessen Evidence. #679 ersetzt damit den
eigenen Sandboxentwurf #619/ADR-0619; der aktuelle lokale Verifier bleibt bis
zum atomaren Cutover ehrlich als nicht sandboxed Legacy-Pfad dokumentiert.

#658 liefert ab D0 einen echten installierten Positiv- und Negativlauf als
Release-Qualification. Unit-, Integrations-, Architektur- und CI-Tests bleiben
Pflicht, sind aber kein Ersatz für diesen Betriebsnachweis.

Der Klarstellungsnachtrag #681 ergänzt: keine implizite Producer-/Provider-
Autorität, externe Evidence mit Issuer-/Provenienz-/Freshness-/Replayvertrag,
authentifizierte subject- und aktionsgebundene menschliche Zustimmung sowie
Re-Evaluation bei wesentlicher Modell-/Provider-/Prompt-/Tool-/Rechtedrift.
Self-Mode darf Core-Quelländerungen als normalen Candidate erzeugen, jedoch
nicht laufende Installation, Trust Roots, Updatepfad oder Policy selbst
autorisieren. OpenTelemetry GenAI bleibt ein reife- und privacyabhängiger
Observability-Anschluss ohne Freigabeautorität.

### Erweiterungsregel

Über einen schmalen fachlichen Port hinaus wird grundsätzlich erst beim
zweiten realen Adapter oder Anwendungsfall generalisiert. Entstünden aus einem
Finding gleichzeitig Port, Schema, Store, Events, Dashboard, Migration,
Doctor und Conformance-Suite, muss der Scope erneut als Designentscheidung
freigegeben werden. Security- und Authority-Grenzen bleiben davon unberührt.

Vollständige Entscheidung, Konsequenzen und verworfene Alternativen stehen in
[ADR-0678](adr/0678-product-boundary-and-integration-profile.md).

---

# Teil B — Issue-Regel

Neue Issues werden nur angelegt, wenn weder das Ursprungsissue noch ein
bestehendes Analyse-/Dachissue den Scope ohne widersprüchliche
Akzeptanzkriterien aufnehmen kann. #485 bleibt die Sammel- und Zuordnungsstelle
für erkannte Kleinfunde.

**Ausnahmen — eigene Issues gerechtfertigt:**

- **#517 Capability-/Wirksamkeitsmatrix** — Arbeitsstrang, kein Kleinfund.
- **#515 Commitgebundene Merge-Integrität** — Acceptance Contract,
  vollständiger Diff, Head-SHA-Auflösung, Push-Invalidation und serverseitige
  Durchsetzung.
- **#516 Falscher PR-Lifecycle bei fehlgeschlagener PR-Erstellung** —
  eigenständiger funktionaler Fehler, kein Auto-Merge-Designpunkt;
  nach kriteriumsweiser Nachprüfung über PR #522 und #523 abgeschlossen.
- **#518 Quality-Evidence und Workflow-Verdrahtung** — trennt Syntaxcheck,
  lokale Quality und Remote-CI.
- **#519 Commitgebundene Acceptance-Evidence** — verbindet Gate 11/12 mit
  Acceptance Contract und realem Verifikationsergebnis; Statusnachtrag
  25. August 2026: umgesetzt, kriteriumsweise Abnahme und CI-Nachweis stehen im
  Issue-Abschlusskommentar.
- **#520 Advisory-SCM-Check-Evidence** — kleinste Standard-Evidence-Stufe als
  realer Gitea-Pull-Adapter; weitere Adapter bedarfsgetrieben, bindende
  Nutzung bleibt #679.
- **#521 Generischer `ImplementationPort`** — beginnt mit passiver Candidate
  Submission; aktive Workersteuerung folgt erst einem realen zweiten Adapter.
- **#678/#679 Produkt-/Ausführungsgrenze** — Integration statt Plattformbau;
  ADR-0619/#619 superseded, lokaler Legacy-Verifier bleibt bis zum belegten
  Cutover sichtbar.

Issue-Bodies und ursprüngliche Akzeptanzkriterien werden für Auditierbarkeit
nicht still nachträglich umgeschrieben. Widerspricht eine bestätigte
Designentscheidung einem alten AC, dokumentiert ein datierter Kommentar den
superseding Acceptance Contract und die Begründung. Bei heterogenem Scope wird
das bestehende Issue zum Dachissue und verweist auf klar geschnittene
Folgeissues.

Jedes Issue enthält außerdem ein verbindliches Dokumentationskriterium. Vor
Abschluss werden alle betroffenen aktiven Dokumente und ihre Issue-Verweise
gegen Code, Konfiguration, Betrieb und den tatsächlichen Issue-Status geprüft.
Der Abschlusskommentar nennt Suchumfang, geänderte Fundstellen und exakten
Commit. Auch „keine Dokuänderung erforderlich“ braucht einen konkreten
Suchnachweis. Datierte Archivdateien bleiben historische Evidenz und werden
nicht still an den heutigen Stand angepasst.

---

# Teil C — Datierter Prüfbefund (wird superseded)

> **Diese Sektion ist an `d4c147c1e87ba9f7a8e2e99a21ac54d1ed8ef515` gebunden
> und veraltet mit jedem Merge.** Sie gehört mittelfristig in eine eigene
> Auditdatei. Bei einem Folgeaudit wird sie unverändert archiviert und mit
> `superseded_by` auf den neuen Befund verwiesen; sie wird nicht gelöscht.

| Behaupteter Bereich | Nachweisbarer Ist-Stand | Ziel und Referenz |
|---|---|---|
| Secret-Scanner | vier Muster vorhanden, kein produktiver Aufrufer | Diff-Scan aktiv und fail-closed verdrahten: #474; Erkennungstiefe und gemeinsame Musterquelle: #481 — mit E10-Vorbehalt: Basisfähigkeit, kein Nachbau spezialisierter Scanner |
| Prompt-Injection-Erkennung | sieben Phrasen vorhanden, kein produktiver Aufrufer | aktives Risikosignal und Canary-Tests: #474/#481; keine alleinige Phrase-Blockade, siehe E7 |
| Command-Safety | Funktion vorhanden, nicht verdrahtet; `force-push` trifft reale Git-Syntax nicht | aktionsnahe Policy statt Freitextliste: #474/#481 |
| PromptGuard-Middleware | auf einen nicht existierenden `LLMCall`-Command ausgerichtet | wirksam verdrahten oder entfernen: #474; gemeinsame Markerquelle: #481 und #485 A1 |
| Gate 1 „BranchGuard" | prüft nur, dass der übergebene Branch nicht `main`, `master` oder leer ist; kein Schutz gegen direkten Push | als Branch-Namenscheck benennen; reale Merge-/Push-Durchsetzung getrennt über E4 |
| Gate 2 „PlanComment" | prüft nur, ob ein gefundener Kommentar länger als 20 Zeichen ist | Contract-/Plan-Identität und Revision prüfen oder als Präsenzcheck benennen |
| Gate 3 „MetadataBlock" | sucht nur den String `Agent-Metadaten`; keine Schema- oder Inhaltsprüfung | versioniertes, schema-validiertes Metadata-/Contract-Format |
| Gate 4 „EvalTimestamp" | prüft nur `eval_score is not None`; kein Timestamp und keine Reihenfolge | umbenennen oder echte commitgebundene Eval-Freshness implementieren |
| Gate 5 „DiffNotEmpty" | prüft nur, ob der bereits begrenzte lokale Branch-Diff nicht leer ist; im Defaultprofil optional | vollständigen commitgebundenen Diff verwenden; Required/Advisory im v1-Profil ausdrücklich entscheiden |
| Gate 6 „SelfConsistency" | Basename-Vergleich; passiert bei fehlenden Daten und toleriert mehr als die Hälfte fehlender Referenzen | als Heuristik/advisory einstufen oder gegen strukturierten Contract prüfen |
| Gate 7 `ForbiddenPathGuard` | Secret-Pfadfallback mit `path_risk` als maßgeblicher eigener Kontrolle; kein fachlicher Contract-Scope | ehrlich getrennt von Gate 7b benannt |
| Gate 7b `ContractScope` | Contract-Schema v2 enthält einen Scope nach Schema v1; vollständige Changed-Files desselben EvaluationSubject werden deterministisch geprüft, optionale Ergänzungen stammen nur aus `architecture.json` | durch #529 / PR #543 implementiert; Merge `c3e9edb5`, Main-CI #463 grün |
| Gate 8 „SliceGate" | prüft nur neu hinzugefügte `from samuel.slices.X import`-Zeilen im auf 50.000 Zeichen begrenzten Diff | vollständigen Candidate ohne Trunkierung prüfen; Import-/Architekturabdeckung exakt dokumentieren |
| Gate 9 „Quality Pipeline" | parst vorhandene geänderte Python-Dateien per AST; Nicht-Python und fehlende Pfade passieren | #518: vollständige Quality-Evidence anbinden (bevorzugt über CI/Fremdwerkzeug, E10) oder ehrlich in Syntaxprüfung umbenennen; Remote-CI durch #441 nachgewiesen |
| Gate 10 „EvalScore" | vergleicht einen numerischen Command-Payload mit der Profil-Schwelle; Herkunft, Freshness und Head-Bindung des Scores fehlen | Score-Evidence an Contract/Head binden; Scoring-Semantik #399 entscheiden. #514 trennt MANUAL inzwischen als `manual_pending` aus automatischen Zählern, schafft aber noch keine commitgebundene Evidence. |
| Gate 11 „AC Verification" | **Historischer Befund:** prüfte im PR-Gate nur, ob Checkboxen vorkommen | **Statusnachtrag 29. August 2026:** #519 bindet die Evidence an Repository/Base/Head/Contract/Policy; Gate 11 validiert sie ohne zweite Ausführung. #620 führt zuerst die statischen Gates 7b, 8, 9, 13a und 13b aus und fordert den AC-Verifier nur nach bestandenem Required-Preflight genau einmal an; andernfalls bleibt Gate 11 explizit `skipped_precondition`. #612 bindet die TEST-Runner-Policy an den Control-Plane-Snapshot und dessen Policy-Digest. #613 entfernt das geerbte Parent-Environment aus IMPORT-/TEST-Kindprozessen und bindet das Environment-Profil an Evidence/Digest. Automatische Checks laufen im detached Candidate-Worktree; Worktree und Environment-Allowlist sind keine Prozesssandbox. MANUAL benötigt einen exakten menschlichen SCM-Receipt. Checkboxen werden ignoriert. |
| Gate 12 | **Historischer Befund:** zählte abgehakte/offene Checkboxen | **Statusnachtrag 25. August 2026:** #519 benennt die Kontrolle `AcceptanceReadiness`; sie fasst die Evidence-Vollständigkeit zusammen und behauptet keine zweite Verifikation. |
| Gate 13a Branch Freshness | nicht prüfbarer Zustand wird als bestanden zurückgegeben | als Required-Kontrolle fail-closed oder ausdrücklich advisory; Merge-Policy: #468 |
| Gate 13b „DestructiveDiff" | Mengenheuristik `>50` und `>3×`; leerer Diff besteht; arbeitet auf dem begrenzten Diff | als Heuristik benennen, vollständigen Diff verwenden und Risikopfade/Dateitypen ergänzen |
| Gate-Konfiguration | unbekannte Gate-IDs werden still übersprungen; `custom` wird dokumentiert, aber nicht in Gates übersetzt | Konfiguration validieren und fail-closed ablehnen oder echten Adaptervertrag implementieren |
| External-Gates | Coverage ohne `coverage.xml` und nicht auflösbare Symbole liefern `passed=true` als Warnung; Path-Risk blockiert nur Klassen mit `level=block`; Exceptions blockieren | tatsächliche Advisory-/Required-Semantik je Gate in der Capability-Matrix führen; fehlende Daten nicht als gemessene Abdeckung darstellen |
| Quality-Workflow | `RunQuality` läuft im ausgelieferten Self-Workflow, Standard/Autonomous gehen direkt zu Score; `hooks.json.extensions` wird nicht ausgewertet | #518: v1-Workflowvertrag festlegen, Konfiguration wirksam machen oder Doku korrigieren |
| PR-Gates / Commitbindung | prüfen mutable lokale Branch-Refs; `GateContext`, Command und SCM-Port tragen keinen Base-/Head-SHA oder Contract-Hash; Diff wird auf 50.000 Zeichen gekürzt | #515 „commitgebundene Merge-Integrität“; v1-Blocker |
| PR-Erstellung | **Historischer Befund auf `d4c147c1`:** `scm.create_pr()`-Fehler wurde geloggt, danach wurden trotzdem `PRCreated` und `passed: true` erzeugt; ein Test schrieb dieses Verhalten fest | **Statusnachtrag:** #516 ist über PR #522/#523 behoben und gegen persistierte Audit-Evidence geprüft; Merge-Commit `6629f0ce`, Push-CI #430 grün. Kein offener v1-Blocker mehr; die commitgebundene Candidate-Identität bleibt getrennt in #515. |
| Remote-CI-Evidence | #441 beweist einen Required Check auf der SCM-Plattform; #520 liest einen vorhandenen Gitea-Run begrenzt und dauerhaft advisory | Plattformschutz weiter nutzen; #679 trägt Requestbindung, Required-Wirkung und externen Execution-Cutover |
| SARIF | write-only Findings-Export; kein Ingest, keine Head-/Contract-/Policy-/Tool-Digest-Bindung | #520 ändert diese Grenze nicht: Sein in-toto-Rahmen enthält SCM-Check-Evidence, SARIF bleibt Format für statische Findings |
| Premium-Routing | **Historischer Befund:** lizenzgeprüfte aktive Adapterkette und zusätzlicher, nur per `premium.*`-Config aktivierbarer alter Bootstrap-Pfad | **Statusnachtrag:** #477 entfernt Entitlements, Alt-Router und Bootstrap-Pfad. Task- und Scheduled-Routing bilden einen allgemeinen Adapterpfad. |
| Token-Budget | aktiver Adapter begrenzte Output je Call; der historisch tote Premium-Handler zählte theoretisch kumulativ, wurde aber nirgends aufgerufen | **Statusnachtrag 19. September 2026:** Alt-Handler bleibt entfernt; D14/#549 ergänzt die persistente Zulassung vor Planning und atomare Reservation je physischem Retry/Fallback im allgemeinen Pfad. Geldkosten bleiben informativ; reale Provider-Qualification ist offen. |
| Premium-Issuer | **Historischer Befund:** #478 behauptete fehlende Issuer-Werkzeuge, obwohl zwei Generatoren vorhanden waren | **Statusnachtrag:** Generatoren und Entitlement-Pfad über #477 entfernt; #478 ist damit begründet überholt |
| Aktive Claims | README behauptet unter anderem rund 30 unabhängige/fail-closed Schranken, unkontrolliertes Schreiben unmöglich, Lint/Type in Gate 9, vollständige AC-Verifikation und konfigurierbare `custom`-Gates | E8/E9/#517: alle wesentlichen Claims aus Capability-Matrix und claimabhängiger Evidence ableiten |
| Gate-Namen | **Historischer Zwischenstand:** #501 hatte die Core-Quelle und den Dashboard-Verbrauch hergestellt, der PR-Gate-Verbrauch fehlte noch | **Statusnachtrag:** #529 ergänzte `GATE_NAMES` im PR-Gate-Report samt Verhaltenstest. Core, PR-Gates und Dashboard verwenden damit dieselbe slice-neutrale Quelle; #501 ist vollständig erfüllt. |
| Langzeit-Evidence | Run-History hängt am rotierenden Audit-Log, Checkpoints nicht restartfest | #482; Release-Blocker nur, wenn Resume/Langzeithistorie zugesagt werden |
| Direkter Push auf `main` | **Historischer Befund:** #441 nannte `enable_push: true` | **Statusnachtrag:** #528 konsolidiert den Pfad auf native Gitea-Branch-Protection (`enable_push=false`, keine Allowlist, Force/Löschung gesperrt, exakter Required Check, kein Admin-Override). Doctor behandelt fehlende, unlesbare oder abweichende Regeln als Release-Blocker. Der unvollständige Hook-/Setup-Pfad aus #124 ist abgelöst. |
| `ImplementationPort` | existiert in `samuel/core/ports.py` nicht | E3/#521: passive Candidate Submission zuerst; aktive Workersteuerung erst beim realen zweiten Adapter |

**Statusnachtrag zu #515 (24. August 2026):** Der oben an den Audit-Commit
`d4c147c1` gebundene Befund bleibt als Historie unverändert wahr. Die
Implementierung von #515 ergänzt danach `EvaluationSubject`, exakte
SCM-Revisionen, vollständigen Diff mit fail-closed Ressourcenlimit,
commitgebundene Gate-/PR-Evidence und unmittelbare PR-/Auto-Merge-Revalidierung.
Sie wurde über PR #526 mit Merge-Commit `8f0e1575` in `main` übernommen; der
Push-Lauf #434 auf genau diesem Commit war erfolgreich.
Die serverseitige Required-Check-/Branch-Schutz-Grenze bleibt ausdrücklich
offen; Details stehen in E4 und der technischen PR-Gate-Dokumentation.

**Statusnachtrag zu #474 (25. August 2026):** Der historische Befund der
Tabelle bleibt an `d4c147c1` gebunden. Im aktuellen Stand läuft die
Sieben-Phrasen-Heuristik vor dem Planning-LLM als advisory
`PromptInjectionRiskDetected`-Evidence. `DiffSecretGate` blockiert Funde der
vier Basismuster in hinzugefügten Zeilen des vollständigen,
commitgebundenen Candidate-Diffs; entfernte Secrets dürfen bereinigt werden.
Die wirkungslosen `SecurityMiddleware`-/`PromptGuardMiddleware`-Pfade wurden
entfernt. Der Core-Git-Pfad blockiert beide Force-Push-Schreibweisen direkt
vor dem Subprozess. Die Umsetzung wurde über PR #532 mit Merge-Commit
`5eeae6bc770bd57d766e5bef14fb9697e2202176` in `main` übernommen; PR-CI #441
und Push-CI #442 auf dem Merge-Commit waren erfolgreich. #474 ist damit
abgeschlossen. Die daran anschließende Erkennungstiefe und Policy-Präzisierung
ist in #481 umgesetzt.

**Umsetzungsstand #481 (25. August 2026):** Eine gemeinsame Core-Regelquelle
versorgt Diff-Scan und flache Audit-Redaktion; PEM-Private-Keys blockieren,
JWT- und AWS-Access-Key-ID-Formen erzeugen commitgebundene advisory Evidence.
Neun Phrasen-/Rollenmuster prüfen nach begrenzter Unicode-Normalisierung jeden
Prompt der vier Worker-Slices. Die gemeinsamen Prompt-Marker sind gegen Drift
getestet, `git reset --hard` wird am realen Core-Git-Ausführungspunkt
blockiert. Entropie- und Echo-Entscheidung entsprechen E7 oben; breite
Scannerabdeckung bleibt offen; #520 deckt nur den realen Gitea-SCM-Check-
Advisory-Pfad ab. Bindende Fremd-Evidence bleibt #679.

**Statusnachtrag zu #490 (26. August 2026):** `v2.0.0a1` bleibt als
unveränderlicher, vom Post-Tag-Gate abgewiesener Audit-Tag ohne Gitea-Release
bestehen. Der Korrekturstand `v2.0.0a2` zeigt auf Release-Commit
`9f656f70af6cf24fc7a4119cd3db4439bbdf2a03`. Tag-CI #496 bestand Python 3.10,
Python 3.14, die vollständige Qualitätspipeline und das Post-Tag-Release-Gate
#541. Das Gitea-Prerelease enthält genau Wheel, sdist und
`release-manifest.json`; erneuter Download bestätigte die im Manifest an Tag,
Version und Commit gebundenen SHA-256-Werte. Damit ist der Release-Anker für
#488 vorhanden; ein bitreproduzierbares Container-Release bleibt getrennt in
#555 und wurde für `v2.0.0a2` nicht behauptet.

**Statusnachtrag zu #488 (26. August 2026):** Das dynamische
`project.version` wird von `setuptools-scm` ausschließlich aus strikten
`v<Version>`-Produkt-Tags abgeleitet. `phase-*`-Marker werden ignoriert;
Dev-Stände tragen Commitbezug, ein veränderter getrackter Arbeitsbaum wird in
der lokalen Versionskomponente markiert und der vollständige Dirty-State
bleibt getrennte Build-Evidence. sdist und Wheel bewahren dieselbe aufgelöste
Version. Ohne SCM-, sdist- oder Paketmetadaten wird nur `0+unknown` erzeugt,
nie eine scheinbare Release-Version. Python-API, CLI und Dashboard lesen
weiterhin ausschließlich die installierten Paketmetadaten. Die Umsetzung
erfolgte über PR #562; Merge-Commit
`d328ce3a65714f7d2ef9cbbdfc628c64289bc823` bestand PR-CI #500 und Main-CI
#501 vollständig. Der rote Vorlauf #499 bleibt als Nachweis erhalten: Sein
einziger Befund war ein vor dem Tracking der neuen Testdatei berechneter
Capability-Digest; Folgecommit `087bdd84c9cc074ead5d719a2c3c023eeaf3f558`
band den Digest an den tatsächlich getrackten Quellumfang.

**Umgang mit diesen Befunden richtet sich nach E11:** Die aktive Dokumentation
nennt bis zur Abnahme den Ist-Status sichtbar. Sinnvolle Fähigkeiten bleiben
als Absicht erhalten; unverdrahteter, doppelter oder irreführender
Produktionscode kann nach Nutzungs- und Scope-Prüfung entfernt oder isoliert
werden.

### Bereits nachgewiesene Grundlagen

- **#441** — dedizierter Runner, erfolgreicher PR-Lauf, Required Check auf
  `main` live nachgewiesen und kriteriumsweise abgenommen.
- **#475** — Health-Dokumentation an den tatsächlichen Umfang angepasst.
- **#486** — konkreter Providerfehler der Drittland-Transferprüfung
  geschlossen; weitergehende Compliance-Zusagen bleiben zweckabhängig.

## E18 — Unveränderlicher Core und atomare lokale Releaseaktivierung

### Entscheidung

Der lokale Kundenpfad installiert keine neue Version über eine vorhandene venv
oder einen Checkout. Jeder manifestgebundene Produktstand erhält unter
`/opt/samuel/releases/<version>` seine eigene venv, einen unveränderlichen
Launcher und ein Release-Receipt. `/opt/samuel/current` wird nur nach
isolierter Prüfung von Wheel, hashgebundenem Runtime-Lock, Console-Script,
Paketmetadaten, Importpfad, Version und vollständiger Revision atomar per
Compare-and-swap umgeschaltet.

Operator-Konfiguration und Secrets unter `/etc/samuel`, Runtime-State/Evidence
unter `/var/lib/samuel`, Prozesslogs unter `/var/log/samuel` sowie Workspaces,
Backups und reservierte Extensions unter `/srv/samuel` bleiben außerhalb des
Core. Defaults werden nur bei der ersten Initialisierung einer leeren
Konfigurationswurzel kopiert. Ein Update führt den Wizard nicht erneut aus,
mischt keine Defaults und startet oder migriert keinen Dienst. OCI behält
seine bestehende, getrennte Digest-/Mount-Grenze.

### Authority und Self-Mode

Nur der Operator aktiviert oder rollt einen Release zurück. Self-Mode darf
einen normalen Candidate erzeugen, ihn durch Review und Gates führen und nach
dem Releaseprozess ein neues Artefakt bereitstellen. Er darf weder
`/opt/samuel/current` noch Trust Roots oder wirksame Policy selbst
autorisieren. Das reservierte `extensions`-Verzeichnis wird nicht implizit
importiert; ein späterer Adapter benötigt seinen eigenen Capability-Vertrag.

Ein Code-Rückwechsel ersetzt keinen persistenten State. Schema- oder
Stateinkompatibilität verlangt das vorab gebundene Backup und den bestehenden
Restore-/Reconcile-Ablauf. Unklassifizierte Produkt-Overlays,
Identitätswidersprüche und ein unerwarteter Altstand blockieren ohne stillen
Fallback. Die vollständige Entscheidung steht in
[`ADR-0706`](adr/0706-atomic-release-layout.md); ein Kundenclaim bleibt bis zum
veröffentlichten D0-Upgrade in #658 ausdrücklich ausstehend.

---

# Teil D — Marktlage und Recht

## EU AI Act, Stand 24. August 2026

Die Verordnung (EU) 2026/1744 („Digital Omnibus on AI") wurde am 24. Juli 2026
im Amtsblatt veröffentlicht und ist am 27. Juli 2026 in Kraft getreten.

- Eigenständige Hochrisiko-Systeme nach **Anhang III**: ab **2. Dezember
  2027** (statt 2. August 2026).
- In regulierte Produkte eingebettete Systeme nach **Anhang I**: ab
  **2. August 2028**.
- **Grundsatz:** Die Transparenz- und Kennzeichnungspflichten nach Art. 50
  gelten seit dem 2. August 2026. Für Systeme nach Art. 50(2), die bereits vor
  diesem Datum in Verkehr gebracht wurden, fügt die Verordnung eine
  Übergangsfrist bis **2. Dezember 2026** ein.
- Die neu eingeführten beziehungsweise geänderten Bestimmungen in
  Art. 5(1) Unterabs. 1 Buchstaben (ba) und (bb) sowie Art. 5(1a) und (1b)
  gelten ab **2. Dezember 2026**. Aktive Produktdokumentation nennt die
  konkreten Vorschriften statt verkürzend nur „zwei neue Verbote“.

Der nächste harte Termin ist also bereits verstrichen — er betrifft nur nicht
Anhang III.

**Auflagen für die Verwendung dieser Angaben:**

- Daraus folgt nicht, dass S.A.M.U.E.L. selbst ein Hochrisiko-System ist. Das
  hängt von Zweck und Einsatz ab.
- „Weniger Verkaufsdruck" ist eine Geschäftshypothese, keine rechtliche
  Feststellung.
- Sicherheits-, Lieferketten- und Beschaffungsanforderungen bestehen
  unabhängig weiter.
- Die Datumsangaben wurden am 24. August 2026 gegen den veröffentlichten
  EUR-Lex-Verordnungstext geprüft. Ob und wie einzelne Pflichten auf
  S.A.M.U.E.L. oder einen konkreten Betreiber zutreffen, bleibt eine
  zweck-/einsatzbezogene rechtliche Bewertung und wird nicht durch dieses
  technische Audit entschieden.

## Wettbewerb

Das Feld ist nicht unbesetzt. Plattformregeln, Agent-Hooks,
PR-Policy-Produkte, GRC-Suiten und Observability-Werkzeuge überschneiden sich
jeweils teilweise mit dem Zielbild. Marktkommunikation verwendet keine
absoluten Aussagen.

Vor öffentlicher Positionierung wird eine datierte Vergleichsmatrix geführt
mit mindestens:

- Herkunftsunabhängigkeit des Workers
- GitHub-/Gitea-/SCM-Portabilität
- self-hosted Betriebsfähigkeit
- Contract- und Head-SHA-Bindung
- Fail-closed-Verhalten
- Policy außerhalb des Modells
- Evidence-/Attestation-Export
- **Einbindbarkeit vorhandener Scanner und CI-Systeme (E10)**
- Lizenz und Kostenmodell

Herstellerangaben werden als solche gekennzeichnet und nicht als unabhängiger
Wirksamkeitsnachweis behandelt.

## Übernahmen aus Sicherheits- und Supply-Chain-Praxis

- **Policy über beobachtbare Aktionen:** Schaden anhand von Tool, Argumenten,
  Rückgabe und resultierendem Artefakt bewerten, nicht anhand eines
  beruhigenden Modelltexts.
- **Tool-Rückgaben sind unvertrauenswürdig:** Scanner- und
  Repository-Ausgaben strukturiert, begrenzt und nicht roh in privilegierte
  Kontexte übernehmen.
- **Canaries als Regressionstest:** Präparierte Kontextdateien wie
  `.claude.md`, `CLAUDE.md`, `.cursorrules` oder vergleichbare Worker-Dateien
  dürfen Canary-Werte weder in Output noch Tool-Argumente, Speicher oder
  Egress übertragen.
- **Provenance und Attestationsmuster:** Contract-Hash, Base-SHA,
  Candidate-SHA, Policy-Version und Gate-Ergebnisse bilden eine SLSA-/
  in-toto-inspirierte Evidence-Kette. Das ist noch keine
  SLSA-Konformitätsbehauptung.
- **Sichere Entwicklungsumgebung:** NIST SSDF und SP 800-218A stützen die
  Trennung von Entwicklungsumgebung, Schutzregeln, Provenienz und
  nachvollziehbaren Entscheidungen.

---

# Teil E — Weg zur ersten funktionierenden Version

## Scope v1

Bewusst klein: **eine ehrlich beschriebene, auf den Referenz-Worker begrenzte
Version.** Fremd-Worker-Anbindung und generisches Findings-Ingest sind
ausdrücklich **nicht** Teil von v1.

Der als `enforced` beworbene Kontrollsatz wird klein gehalten (E9). Er wird
nach der Capability-Matrix namentlich und mit Kontroll-IDs beschlossen; ohne
diese explizite Liste gibt es keine v1-Freigabe. Vorläufige Kandidaten sind:

- menschlich freigegebener, unveränderlicher Acceptance Contract;
- vollständiger Candidate-Diff zwischen festem Base- und Head-SHA;
- Secret-/Credential-Scan des vollständigen Diffs;
- Contract-Scope-/verbotene-Pfade-Prüfung;
- Architekturprüfung mit exakt dokumentierter Sprach-/Importabdeckung;
- nachgewiesene Quality-/Test-Evidence für denselben Head;
- Required Checks und Branch-Schutz am Merge-Punkt.

Alles Übrige wird mit ehrlichem Status geführt. Die Fähigkeitsabsicht kann
erhalten bleiben; ungenutzter Produktionscode unterliegt E11.

## Reihenfolge

1. **Dieses Dokument gegenprüfen und bestätigen** — insbesondere E1-Benennung,
   E3-Contract, E6-Zweiteilung, E7-Blockierlogik, E10 und E11.
2. **Bestehende Issues kommentarseitig anbinden.** #474 erhält den
   superseding Acceptance Contract aus E7; ursprüngliche Issue-Bodies bleiben
   als Auditspur erhalten. Eigene Issues nur nach Teil B.
3. **Capability-Matrix pflegen (#517)** — maschinenlesbare Quelle,
   deterministisches Markdown und CI-Driftcheck sind etabliert. Die Matrix
   bewertet Registry, External-Gates, Quality-, Security-, AC-/Eval-,
   Middleware- und SCM-Pfade und hält die namentliche First-Release-Baseline
   bis zur Erfüllung aller Zielkontrollen blockiert. Der Umsetzungsnachtrag
   #752 bindet an der bestehenden ErrorMiddleware einen redigierten,
   typisierten Commandfehler: Er trennt einen synchron bereits terminalen
   Ausgang von legitimer Handler-Rückgabe `None`, damit REST keine falsche
   `202`-Annahme ausgibt. Das ist keine neue Workflow- oder Jobauthority;
   spätere asynchrone Ausgänge bleiben Event-/Statussache.
4. **Merge-Integrität stabilisieren (#515)** — die lokale Subject-,
   Base-/Head-, Diff- und unmittelbare Revalidierungsgrundlage ist umgesetzt;
   SCM-seitige Push-/Required-Check-/Direkter-Push-Durchsetzung ist getrennt
   über #441/#528 belegt; die Auto-Merge-/Review-Policy ist in #468
   repositoryseitig umgesetzt und bleibt bis zur isolierten realen
   Qualification default-off. Der
   PR-Fehlerpfad aus #516 ist bereits über
   PR #522/#523 abgeschlossen.
5. **Kernkontrollen vervollständigen:** Security #474/#481, der ehrliche
   Quality-Vertrag #518, die getrennte MANUAL-Semantik #514 und die
   commitgebundene Acceptance-Evidence #519 sind umgesetzt; als Nächstes Gate
   13a gegen echte Wirksamkeit prüfen.
   Unter E10 wird ein geeignetes Fremdwerkzeug integriert, wenn es die bessere
   Antwort ist.
6. **Premium vollständig entfernen** — E6/#476/#477 sind umgesetzt. Der
   getrennte D14-Vertrag aus #549 verwendet den allgemeinen
   LLM-/Authority-Pfad; reale Provider-Qualification bleibt vor Issueabschluss
   erforderlich.
7. **README und aktive Dokumentation neu formulieren** aus der abgenommenen
   Matrix. Keine Zielarchitektur als Ist-Zustand.
8. **Aktive Doku an Prüfdatum und Commit binden** — #513 ist umgesetzt; alle
   wesentlichen Produktclaims weiterhin nach E9 abnehmen.
9. **Versionierungs- und Releasekette abgeschlossen:** #479 → #487 → #489 →
   #490 → #488. Richtlinie, einheitliche Flächen und die create-only Release-
   Gate-Mechanik sind umgesetzt. `v2.0.0a1` blieb nach roter Tag-CI als
   unveränderliche Auditspur ohne Gitea-Release bestehen. Der korrigierte
   Stand `v2.0.0a2`, dessen vollständige Tag-CI und das Gitea-Prerelease sind
   nachgewiesen. #488 macht diesen echten Produkt-Tag zur SCM-Authority,
   ignoriert Phasenmarker und verwendet metadatenlos ausschließlich den
   Nicht-Release-Fallback `0+unknown`. `v2.0.0a3` ergänzt nach #555 den ersten
   veröffentlichten, digest- und lockgebundenen Containerstand.
10. **#658 D0 mit belastbarer Teilevidence, aber ohne bestätigten Gesamt-PASS:**
    `v2.0.0a15` wurde aus veröffentlichtem Image und frischer Installation
    gegen das unabhängige Demo-Repository geprüft. Planning, Approval,
    Candidate, PR und Required Check sowie der getrennte `diff_secret_scan`-
    Block sind revisionsgebunden belegt. Der vorgeschriebene menschliche Merge
    wurde jedoch durch `demo-example-bot` ausgeführt; deshalb bleibt eine neue
    vollständige Evaluation der Referenzkombination erforderlich.
11. **Minimale Integrationsgrenze:** #520 ist mit realer, dauerhaft advisory
    bleibender Gitea-Actions-/SCM-Check-Evidence umgesetzt. #521 folgt
    zunächst als passive Candidate Submission. #679
    wechselt Candidate-Ausführung erst nach Shadow- und Negativevidence atomar
    auf den externen Provider.

## Fertig-Kriterien v1

- Der veröffentlichte Funktionsumfang ist ausdrücklich festgelegt.
- Jede als `enforced` beworbene Schranke ist implementiert, verdrahtet,
  entscheidungswirksam, getestet und commitgebunden.
- Der exakte PR-Head benötigt die dokumentierten Required Checks vor dem
  Merge.
- Security-, Lizenz-, Entitlement-, Versions- und Installationsaussagen stimmen
  mit Code und Artefakten überein.
- Apache-2.0 durch Root-`LICENSE`, Paketmetadaten und gebaute Artefakte
  konsistent belegt.
- Entitlements, alte Aktivierungspfade und doppelte Routing-/Token-
  Implementierungen sind entfernt; Call-Ausgabelimit, kumulative
  Workflow-Tokenzulassung und informative Preiswerte sind getrennte Verträge.
- Bekannte Einschränkungen sichtbar, nicht durch `Zero Trust`, `Compliance`
  oder eine Gate-Anzahl verdeckt.
- Dokumentierte Installationswege funktionieren aus dem exakten
  Release-Commit.
- CI, Branch-Schutz, Changelog, Version, Tag und Artefakte beziehen sich auf
  denselben Commit.
- Fehlgeschlagene PR-Erstellung, fehlende Evidence, unbekannte Required-Gates,
  Diff-Trunkierung und ein veränderter Head erzeugen keinen Erfolgsstatus.
- Positiver und negativer Golden-Path-E2E sind gegen ein geschütztes
  Test-Repository dokumentiert.
- Offene Findings sind einem Issue zugeordnet oder mit Begründung abgelehnt.

## Fertig-Kriterium für die workerunabhängige Positionierung

Ein Diff eines fremden Workers, der den Acceptance Contract erhält, als
Candidate-Commit eingereicht und gegen denselben Head-SHA vollständig geprüft
wird. **Nicht Voraussetzung für v1.**

## Fertig-Kriterium für die Integrationspositionierung

Ein Befund eines fremden Scanners wird über die Eingangsschnittstelle
übernommen, an Contract und Head-SHA gebunden und wird merge-wirksam. Ab
diesem Punkt ist belegt, dass S.A.M.U.E.L. einen Fremdbefund commitgebunden und
policy-wirksam in die Merge-Entscheidung einbindet. **Ebenfalls nicht
Voraussetzung für v1.**

---

## Bestehende Issues im Fokus

### Release-Blocker für v1

- **#468** — repositoryseitig umgesetzt, aber bis zum isolierten realen
  Expected-Head-/Race-/Restart-Nachweis default-off und außerhalb des
  Releaseversprechens.
- **#399** — die Designentscheidung ist angenommen und der Zielpfad
  implementiert: Required Gates entscheiden, Score misst nur. #577 hat alle
  realen Rolloutfälle belegt; #580 materialisiert sie in einem
  schema-, subject-, policy- und fallsemantisch gebundenen Releasevertrag.
  Offen bleibt die Entfernung des Legacy-Rollbacks vor `2.0.0a5`; vorhandene
  Evidence verlängert ihn nicht.

### Seit dem datierten Prüfbefund abgeschlossen

- **#479 Versionierungs- und Releasekette** — Die eigenen Dachkriterien wurden
  nach Abschluss von #487, #489, #490 und #488 einzeln gegen Code, Tests und
  Gitea-Evidence auf Ausgangscommit
  `3a4ce59021898ac70a474b894c4c81ee6c47f89e` geprüft. `v2.0.0a1` bleibt die
  unveröffentlichte rote Auditspur; `v2.0.0a2` bindet das annotierte Tagobjekt
  `84c909cbdb1e712a2ff2ba89ef09ac414c6c8099`, Release-Commit
  `9f656f70af6cf24fc7a4119cd3db4439bbdf2a03`, Tag-CI #496 / Jobs #538–#541,
  Gitea-Prerelease #9, Wheel, sdist und Prüfsummenmanifest. Container-
  Publishing war ausdrücklich getrennt und kein Lieferumfang dieses Releases;
  es wurde anschließend für `v2.0.0a3` über #555 abgeschlossen.

- **#555 Container-Releasevertrag** — `v2.0.0a3` bindet das annotierte
  Tagobjekt `484efff40b706fc4b2525e16398ee08c42a09aaf`, Release-Commit
  `41ee7506dd5a09f6eef4a3b71ad08276d0848911`, Tag-CI #522 / Jobs #682–#685,
  Gitea-Prerelease #10, Schema-2-Manifest und den grünen Compose-Smoke an das
  `linux/amd64`-Registry-Digest
  `sha256:6a9c53ae5ba554a5b000e140f3a0929447984f230c9e50a1e5ce9c07d06dc5f6`.
  Registry und Login bleiben Betreiberparameter; Update und Rollback sind im
  Container-Runbook dokumentiert.

- **#551 Runnervertrag** — Der externe Gitea-Runner führt den Release-Workflow
  auf dem repositoryspezifischen Label, einem lokal verifizierten
  digestgebundenen amd64-Image und commitgebundenen Actions aus. Cache-,
  Ausfall-, Update- und Rollbackpfad sind in `docs/CI_RUNNER_OPERATIONS.md`
  festgelegt. Ein echter Offline-Negativtest sowie abschließende PR- und Push-
  Läufe sind grün; #490 ist dadurch nicht mehr vom Runnervertrag blockiert.
  Der getrennte Runner–Gitea-Fetch-Fehlerpfad wurde über das abgeschlossene
  Issue **#557** endlich begrenzt; die Grenzen und die zugehörigen Negativläufe
  stehen in `docs/CI_RUNNER_OPERATIONS.md`.

- **#487 Versionspolitik** — `docs/VERSIONING.md` trennt Produkt-, Build-,
  API-, Event-, Konfigurations-, Persistenz-, Dokument-, Capability-, Prompt-/
  Modell- und Fremdformatdomänen. `2.0.0a0` ist eine ungetaggte Baseline;
  `v2.0.0a1` ist der erste formale, aber vom Tag-Gate abgewiesene Tag.
  `v2.0.0a2` ist der erste veröffentlichte Alpha-Stand und der von #488
  verwendete SCM-Anker. Zum Datum dieses Prüfbefunds war `v2.0.0a3` der
  aktuelle Alpha-Stand. Den heutigen veröffentlichten Kandidaten, den
  unterstützten D0-Referenzstand und den nicht veröffentlichten `main`
  führen ausschließlich `docs/VERSIONING.md` und `SECURITY.md` getrennt fort.

- **#489 Versionsflächen** — installierte Paketmetadaten sind der gemeinsame
  normalisierte Produktstand für Python-API, CLI, Dashboard und Attribution.
  Vollständiger Commit-SHA, Dirty-State und Herkunft bleiben getrennte
  Build-Evidence in Doctor, Status, Plan-Metadaten, PR-Text und Commit-Trailer;
  API-, Event-, Architektur-, Prompt-/Modell- und Fremdformatversionen bleiben
  unabhängige Domänen.

- **#488 Versionsauthority** — `setuptools-scm` materialisiert die
  Produktversion aus strikten `v<Version>`-Tags in Paketmetadaten. Exakter
  Tag, Dev-/Dirty-Stand, Phase-Tag-Ausschluss, sdist/wheel und
  `0+unknown`-Fallback sind getestet; es gibt keinen statischen zweiten
  Produktwert.

- **#477 Entitlements und Parallelpfade** — Ed25519-/Feature-Entscheidungen,
  Dashboard-Premiumstatus, Alt-Router, unverdrahteter TokenLimitHandler,
  Generatorwerkzeuge und private Bus-Anheftung entfernt. Routing, Schedule und
  Prompt-Verwaltung laufen über allgemeine, validierte Pfade; API-Key-Schutz
  und Negativtest bleiben. D14/#549 hat die damals separat dokumentierte
  Budgetsemantik später im allgemeinen Authority-/Adapterpfad umgesetzt.
- **#476 Projektlizenz** — vollständiger unveränderter Apache-2.0-Text in der
  Root-Datei `LICENSE`, PEP-639-/SPDX-Metadaten und Aufnahme der Lizenz in
  frische Wheel-/sdist-Artefakte nachgewiesen. README, technische Beschreibung
  grenzen den damaligen Laufzeit-Entitlementpfad von der für das gesamte
  Repository geltenden Softwarelizenz ab; #477 entfernte den Pfad anschließend.
- **#513 Doku-Prüfstand** — alle aktiven technischen Beschreibungen nennen
  Prüfdatum und vollständigen abgeglichenen Commit. Ein aktiver
  `Stand: Phase ...`-Marker wird im Doku-Test abgelehnt; historische
  Entstehungshinweise bleiben erhalten. Die fälschlich noch als offen
  bezeichneten #152/#153 sind in der Übersicht als abgeschlossene historische
  Referenzen eingeordnet.
- **#501 gemeinsame Gate-Anzeigenamen** — PR #510 führte die unveränderliche
  Core-Quelle und den Dashboard-Verbrauch ein. Der später über #529 ergänzte
  PR-Gate-Report löst seine Anzeigenamen ebenfalls aus `GATE_NAMES` auf. Gate
  10 war damals im erzeugten PR-Body sichtbar und ist nach #399 in
  Zielprofilen deaktiviert. Registry-/Metadaten-Test verlangt
  identische vollständige IDs und nicht leere Namen; Cross-Slice-Imports
  entstehen nicht.

- **#124/#528 Branch-Schutz** — native Gitea-Branch-Protection ist die einzige
  serverseitige Policy-Autorität. Auf der auditierten Instanz werden normale
  Fast-Forward-/Force-Pushes und Branch-Löschung für `main` abgelehnt;
  Push-Allowlisten sind leer, der konfigurierte exakte Required-Check-Kontext
  ist erforderlich und Admin-Merge-Override ist gesperrt. Der ausgelieferte
  Default lautet `CI / lint-and-test (pull_request)`. `samuel doctor` prüft
  denselben Vertrag fail-closed; #694 bindet den Soll-Kontext an
  Operator-Konfiguration und Gate-Policy. Der alte, für normale Direkt-Pushes
  unvollständige `pre-receive`-Pfad ist entfernt; #468 implementiert die
  getrennte, weiterhin default-off Review-/Auto-Merge-Policy.

- **#529 Contract-Scope** — Acceptance Contract Schema v2 bindet einen
  versionierten FILE-/PATH-Scope an denselben EvaluationSubject. Required Gate
  7b wertet vollständige Changed-Files und Diff-Evidence deterministisch aus;
  optionale Ergänzungen stammen nur aus der mitgedigesteten
  `architecture.json`. Gate 7/PathRisk bleiben separate Security-Kontrollen.
  PR #543, Merge `c3e9edb5`, Main-CI #463 erfolgreich.
- **#399 gebundene Freigabeautorität** — das aktive Required-Gate-Profil
  entscheidet allein. Evaluation konsumiert das vollständige terminale
  Gate-Event passiv, speichert Subject-/Policy-/Evidence-gebundene
  Rohbeobachtungen und publiziert versionierte, nicht bindende
  `ScoreObserved`-Ableitungen. Score, Bestmarke, Gate 4/10 und
  `self_parity_ok` besitzen im Zielmodus keine Workflowautorität. Healing
  verwendet höchstens einen kriteriumsweisen Gate-11-Evidence-Versuch am
  fehlgeschlagenen Candidate-Head. #213 ist damit fachlich abgelöst; der
  Legacy-Rollbackpfad endete verbindlich mit `2.0.0a4`. Für a5 sind Gate 4/10,
  Legacy-Workflow/-Profil und die Autoritätsmoduswahl aus der aktiven Runtime
  entfernt; alte explizite Einstellungen blockieren den Start.
- **#579 atomare Profilauflösung** — der Bootstrap löst den Autoritätsmodus vor
  dem Bus-/Slice-Wiring in genau ein kompatibles Gate-Profil auf. Gebundene
  Standardläufe erlauben nur `default` und `audit`; Legacy und Self erzwingen
  ihre eigenen Profile unabhängig von `SAMUEL_GATES_PROFILE`. Inkompatible
  Kombinationen sowie fehlende oder ungültige aktive Profile blockieren den
  Start, statt eine gemischte Authority zu verdrahten.
  Diese Übergangskontrolle hat den realen Rollback aus #577 ermöglicht und ist
  nach Ablauf des a4-Fensters durch die einzelne Workflow-zu-Profil-Auflösung
  ohne Legacy-Modus ersetzt.
- **#589 serienreine Quality-Attribution** — Dashboard und persistente
  Quality-Registry verwenden dieselbe Last-Call-je-Issue-Attribution. Die
  aktive Zeile und Heatmap stammen ausschließlich aus der neuesten gültigen
  Herkunfts-/Scoring-Policy-/Formelserie; unattribuierte Calls und Calls aus
  anderen Serien bleiben separat sichtbar und verändern keinen Denominator.
- **#580 gebundener Rollout-Nachweis** — das Release-Gate akzeptiert ab
  `2.0.0a5` keine Fallnamen oder Freitext-Platzhalter mehr. Schema `1.0` und
  der Offline-Validator verlangen je Fall vollständiges EvaluationSubject,
  Observation/Correlation/UTC sowie widerspruchsfreie Event-, PR-, Healing-
  und Rollbackdaten; die Evidence ist an den Digest der Schemabytes gebunden.
- **#581 automatische Healing-Evidence** — automatische Gate-11-Resultate
  tragen einen kleinen, versionierten und zum AC-Tag passenden Evidence-Kern
  aus dem immutable Candidate-Checkout. Bound Healing validiert Schema, Kind
  und Pflichtfelder statt eines beliebigen nichtleeren Dictionaries;
  Infrastruktur-/Nichtprüfbarkeitsfehler bleiben terminal. TEST-Auszüge sind
  begrenzt und gegen bekannte Secret-Muster redigiert.
- **#514 MANUAL-Semantik** — `[MANUAL]` wird als eigener Zustand
  `manual_pending` mit `passed: null` auditiert, aus automatischen Zählern und
  dem Self-Parity-Hartstopp entfernt und im bestehenden Workflow-Detail
  getrennt angezeigt. Gemischte und rein manuelle Pläne bleiben der
  bestehenden Score-Schwelle unterworfen; echte automatische Fehler bleiben
  blockierbar. #399 entfernte diese ungebundenen Zähler anschließend aus dem
  Zielworkflow; Contract-/Head-Bindung und menschlicher Review-Receipt stammen
  aus #519/Gate 11.
- **#518 Quality-Vertrag** — Gate 9 ist als `PythonSyntax` benannt und liest
  `.py`-Blobs über den SCM-Port aus dem exakten Candidate-Head. Evidence
  unterscheidet `passed`, `failed` und `not_applicable`, nennt die
  CPython-AST-Version und bleibt ausdrücklich ohne Lint-/Type-/Testclaim. Der
  getrennte `RunQuality`-Pfad ist ein strikt konfigurierter Working-Tree-
  Preflight nur für `self`, nicht commitgebundene v1-Evidence. #441 bleibt
  betrieblicher Required-Check-Nachweis; #520 ergänzt inzwischen einen
  getrennten advisory Gitea-Check-Leser. PR #536, Merge `e46ffbd9`, Push-CI
  #452 erfolgreich.
- **#474/#481 Security-Baseline** — aktive Prompt-, Diff-Secret- und
  Core-Git-Pfade sind verdrahtet; die Erkennungstiefe nutzt eine gemeinsame
  Regelquelle und trennt deterministische Blocks von wertfreien advisory
  Signalen. Die Capability-Matrix und die aktiven Sicherheits-, Architektur-,
  Compliance- und Pipeline-Dokumente bilden die Baselinegrenzen ab; #520
  ergänzt keine breitere Scannerabdeckung.
  PR #535, Merge `aba1a303`, Push-CI #449 erfolgreich.
- **#517 Capability-/Wirksamkeitsmatrix** — 75 bestehende Mechanismen sind
  gegen Code, ausgelieferte Konfiguration, Workflows, Tests und aktive Claims
  bewertet; maschinenlesbare Quelle, deterministisches Markdown,
  `reference-worker-first-release`-Profil und CI-Driftcheck wurden über PR
  #530 übernommen. Merge-Commit `5f8921fd`, Push-CI #438 auf genau diesem
  Commit erfolgreich. Nach dem separaten Live-Nachweis aus #528 sind ihre
  namentlich ausgewiesenen Zielkontrollen `ready`; andere Produkt- und
  Release-Arbeiten sowie die SemVer-Entscheidung bleiben davon getrennt.
- **#515 Merge-Integrität** — lokale commitgebundene Subject-/Evidence-Basis,
  exakter Base-/Head-Vergleich, vollständiger Diff mit fail-closed Limit sowie
  Revalidierung vor PR-Evidence und Auto-Merge über PR #526 nachgewiesen;
  Merge-Commit `8f0e1575`, Push-CI #434 erfolgreich. SCM-seitige
  Required-Check-/Branch-Schutzregeln sind getrennt in #441/#528 belegt;
  die davon getrennte Review-/Auto-Merge-Policy ist in #468
  repositoryseitig implementiert und noch nicht live qualifiziert.
- **#516 PR-Lifecycle** — fail-closed Fehlerzustand, persistierte sichere
  `PRCreationFailed`-Evidence und ausbleibende Review-/Merge-Folgeschritte über
  PR #522/#523 nachgewiesen; Merge-Commit `6629f0ce`, Push-CI #430 erfolgreich.
  Die davon getrennte Candidate-/Commitbindung ist mit #515 abgeschlossen.

### Scope- und evidenceabhängig

- **#520** — minimale CI-/SCM-Evidence als reale, pull-only und dauerhaft
  advisory bleibende Gitea-Stufe umgesetzt; kein proprietäres Mega-Schema.
  Required-/Dispatch-Wirkung bleibt #679.
- **#521** — passive Candidate Submission auf der vorhandenen #515/#519-
  Bindung; aktive Worker-Beauftragung erst bei realem Bedarf.
- **#679** — der schmale, persistierte Execution-/CI-Providervertrag,
  Gitea-Referenzadapter, Gate-11-/Healing-Anschluss und Recoverypfad sind
  implementiert. Die ausgelieferte Konfiguration bleibt bis zur realen
  D03-Conformance- und D0-Qualification deaktiviert/unqualifiziert; der lokale
  Verifier bleibt bis zu diesem atomaren Cutover aktiv. Kein eigener
  Sandboxbau und kein automatischer lokaler Fallback.
- **#482** — Stufen 1–4 sind über #625/#627/#629/#633 umgesetzt; das Dachissue
  bleibt für unterstützten Restore-Abgleich und löschende Retention (Stufe 5)
  offen.
- **#422 / ADR-0422** — lokaler Referenzprovider, unabhängige Rollen,
  Session-/CSRF-Vertrag, Automation-Token, Restore-Recovery und expliziter
  Legacy-Cutover sind umgesetzt. Der Abschluss bleibt an reale D0-Qualification
  von HTTPS, Migration, Neustart, Widerruf und Restore gebunden. OAuth, IAM,
  Pairing und externe Provider bleiben außerhalb dieses Scopes. #332 ist als
  älteres Teil-Backlog darin aufgegangen.
- **#468** — strukturierter Review-Entscheid und fail-closed Merge-Policy sind
  repositoryseitig umgesetzt; vor Aktivierung und Abschluss bleibt der
  isolierte Live-Smoke. Der ältere reine Smoke-Rest #289 ist darin
  aufgegangen.
- **#549** — D14-Vertrag und Repositoryumsetzung liegen vor; vor Abschluss
  bleibt die reale Provider-Qualification von Timeout, Retry und Fallback
  erforderlich. Ein Geldkosten-Hardcap ist nicht Teil des Claims.

### Überholt

- **#478** — kein Premium-Issuer, keine Premium-Lizenzdateien. Nach Umsetzung
  und Dokumentation von E6 begründet schließen.

### Issue-Abdeckung des Designaudits

Die eigenständigen Stränge dieses Audits sind mit Stand 25. August 2026
zugeordnet:

- Capability-/Wirksamkeitsmatrix: **#517**
- Gate 9 und Quality-Workflow/-Evidence: **#518**, umgesetzt; Merge-/CI-Nachweis
  im Abschlusskommentar
- MANUAL-Zustand und automatische Zählung: **#514**, umgesetzt; Gate 11/12,
  Contract-/Head-Bindung und reale menschliche Acceptance-Evidence: **#519**,
  umgesetzt (Abschlussnachweis im Issue)
- commitgebundene Merge-Integrität: **#515**; der getrennte korrekte
  PR-Fehlerpfad ist mit **#516** abgeschlossen
- externe Evidence: **#520** (erste reale Gitea-SCM-Check-Advisory-Stufe),
  **#679** (requestgebundene Required-Verwendung und Cutover)
- workerneutraler Candidate-Vertrag: **#521** (passive Submission zuerst)
- Produkt-/Providergrenze: **#678/#679**
- exakte Plan-/Freigabe-Bindung bei Re-Planning: **#767**; gewöhnliches
  Planning lehnt einen aktiven Plan ab, explizites Re-Planning widerruft
  Plan-Kommentar und Freigabe vor einem neuen Freigabezyklus

Künftige neue Befunde folgen weiterhin der Issue-Regel aus Teil B; diese
Zuordnung behauptet nicht, dass die Issues bereits umgesetzt oder abgenommen
sind.

---

## E19 — Getrennte technische Gesundheit, Readiness und Qualification

Der öffentliche Status bewahrt die bestehenden technischen Health-Felder und
ergänzt sie additiv um eine zweckgebundene Workflow-Readiness sowie die
instanzgebundenen Fachbefunde aus Doctor und Auditverifikation. Ohne passende
Livefacts bleibt Readiness `unknown`; fehlende oder alte Evidence ist
`not_checked` beziehungsweise `stale`. Ein Restore macht frühere positive
Historie nicht aktuell. Nur eine erneute Fachprüfung kann einen Fehler unter
Bindung seines Digests auflösen.

Viewerpfade lesen die bereinigte Projektion ohne Seiteneffekt. Aktive
Providerprobes benötigen `RUN_PROVIDER_PROBES`. Diese Darstellung erzeugt
keine Gate- oder Releaseauthority, keinen Incident-Lifecycle und keinen
zweiten Store. Der persistente State liefert keinen `resume_enabled`-Default;
die wirksame Aussage stammt aus dem Runtime-Resolver. Dauerhafter Vertrag:
ADR-0693.

## Was gegenüber der ersten Fassung gestrichen wurde

Zur Nachvollziehbarkeit — diese Aussagen der ersten Dokumentfassung sind
widerlegt und dürfen nicht zurückkehren:

| Gestrichen | Grund |
|---|---|
| „Das Feld der Kontrollschicht ist unbesetzt" | GitHub Rulesets, Copilot Hooks, CodeSlick, GATE decken Teile ab |
| „Kein ungeprüfter Code kommt in den PR" | Ein PR ist der Prüfgegenstand; CI läuft danach. Ersetzt durch Head-SHA-Bindung (E4) |
| Zweiteilung Worker-Level / Artefakt-Level als abschließendes Modell | zu grob, verschluckt die Ausführungsebene. Ersetzt durch fünf Klassen (E2) |
| Die Artefakt-Level-Liste als „das Produkt" im Ist-Zustand | Die Liste war aus dem README abgeleitet, nicht aus dem Code. Mehrere Einträge sind nicht verdrahtet (Teil C) |
| „Ein Diff von Claude Code läuft durch die registrierten Gates" als Fertig-Kriterium für v1 | zu früh angesetzt; jetzt Kriterium für die workerunabhängige Positionierung, nicht für v1 |
| PASB als „Policy-centric Agent Security Benchmark" | Korrekt: *Personalized Agent Security Bench* |
| AI-Act-Darstellung ohne Art. 50 und Art. 5 | Art. 50 grundsätzlich seit 2. August 2026 mit Übergangsregel für bestimmte Altsysteme; konkrete neue Art.-5-Bestimmungen ab 2. Dezember 2026 |

---

## Quellen

- [NIST, Zero Trust Architecture, SP 800-207](https://csrc.nist.gov/pubs/sp/800/207/final)
- [NIST Secure Software Development Framework](https://csrc.nist.gov/projects/ssdf)
- [NIST SP 800-218A, Secure Software Development Practices for Generative AI](https://csrc.nist.gov/pubs/sp/800/218/a/final)
- [OWASP Prompt Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html)
- [OWASP AI Agent Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html)
- [OWASP Secure Coding with AI Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secure_Coding_with_AI_Cheat_Sheet.html)
- PASB — *Personalized Agent Security Bench*, [arXiv 2602.08412](https://arxiv.org/abs/2602.08412)
- [Verordnung (EU) 2026/1744](https://eur-lex.europa.eu/eli/reg/2026/1744/oj?locale=de) — Datumsgrundlage am 24. August 2026 gegen den Volltext geprüft
- [GitHub Rulesets und Required Status Checks](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)
- [GitHub Copilot Hooks](https://docs.github.com/en/copilot/concepts/agents/hooks)
- [OASIS SARIF 2.1.0](https://docs.oasis-open.org/sarif/sarif/v2.1.0/os/sarif-v2.1.0-os.html)
- [SLSA Provenance v1.2](https://slsa.dev/spec/v1.2/provenance)
- [CodeSlick Security Directives](https://codeslick.dev/blog/security-directives-codeslick-yml-2026) — Herstellerangabe
- [GATE: AI coding agents](https://gate.software/ai-coding-agents/) — Herstellerangabe
- [setuptools-scm: aktuelle Konfiguration](https://setuptools-scm.readthedocs.io/en/latest/config/)
- [setuptools-scm: Nutzung und Runtime-Version](https://setuptools-scm.readthedocs.io/en/latest/usage/)
- [PyPA, Single-Sourcing der Produktversion](https://packaging.python.org/en/latest/guides/single-sourcing-package-version/)
- [PyPA, Version Specifiers / PEP 440](https://packaging.python.org/en/latest/specifications/version-specifiers/)
- [CISA Secure by Design](https://www.cisa.gov/securebydesign)
