# S.A.M.U.E.L. Manifest

> **Trust the change, not the producer.**

Software wird von Menschen, CI-Automationen und zunehmend von KI-gestützten
Werkzeugen verändert. Die Herkunft einer Änderung allein macht sie weder
richtig noch sicher. Vertrauen sollte deshalb an den konkreten Softwarestand,
nachvollziehbare Nachweise und eine explizite Policy gebunden sein.

Dieses Manifest beschreibt die Projekthese und die angestrebte Richtung von
S.A.M.U.E.L. Es ist **keine Runtime-Spezifikation, keine Policy und kein
Compliance-Nachweis**. Für den implementierten Stand gelten der
[technische Einstieg](docs/README_technical.md), die generierte
[Runtime-Referenz](docs/RUNTIME_REFERENCE.md), die
[Capability-/Wirksamkeitsmatrix](docs/CAPABILITY_MATRIX.md) und die
[Architekturentscheidungen](docs/adr/README.md). Code, ausgelieferte
Konfiguration und ausführbare Tests bleiben die technische Wahrheit.

## Unsere These

Die entscheidende Frage lautet nicht:

> Wer hat diese Änderung geschrieben?

Sondern:

> Unter welchen belegten Bedingungen darf genau diese Änderung unter genau
> dieser Policy als vertrauenswürdig behandelt werden?

Das Zielbild trennt deshalb Producer und Freigabeautorität:

```text
Mensch / Referenz-Worker / fremder Agent / Automation
                         │
                         ▼
                  Software-Candidate
                         │
                         ▼
                unveränderlicher Subject
                         │
             ┌───────────┼───────────┐
             ▼           ▼           ▼
           Tests      Security      Doku
             │           │           │
             └──────── Evidence ─────┘
                         │
                         ▼
                  wirksame Policy
                         │
                         ▼
                  PR / Block / Review
```

Ein Producer darf Vorschläge erzeugen. Er darf nicht selbst bestimmen, ob
seine Ausgabe die erforderlichen Nachweise erfüllt. Ein Dashboard, Score oder
Auditereignis erhält ebenfalls nicht allein deshalb Autorität, weil es
existiert. Entscheidend ist, woran das Signal gebunden ist, welche Policy es
auswertet und welche Grenzen tatsächlich technisch durchgesetzt werden.

## Leitprinzipien

### 1. Der Prüfgegenstand ist unveränderlich

Eine Aussage über „den aktuellen Branch“ ist zu schwach. Prüfung und Evidence
müssen sich auf denselben identifizierten Softwarestand beziehen. Im heutigen
Referenzpfad bindet der `EvaluationSubject` Repository, vollständige Base- und
Head-SHA, Acceptance Contract und Gate-Policy.

### 2. Evidence kommt vor Vertrauen

Freigabeaussagen brauchen nachvollziehbare Ergebnisse, Fehlerzustände und
Herkunft. Fehlende oder nicht prüfbare Evidence darf nicht still als Erfolg
erscheinen. Das bedeutet nicht, dass jede Evidence vollständig oder formal
verifiziert ist: Reichweite, Vertrauensniveau und bekannte Lücken müssen
sichtbar bleiben. Bei externer Evidence gehören außerdem Issuer und dessen
Vertrauensprofil, Integritäts- und Transportnachweis, wirksame Policy,
Tool-/Ausführungsumgebung, Frischegrenze und Replay-Schutz zur Bewertung. Dass
Candidate oder Producer eine Evidence erzeugen können, autorisiert diese
Evidence nicht automatisch.

### 3. Policy liegt außerhalb des Producers

LLM-Ausgabe und Candidate-Code sind untrusted Input. Promptregeln können
Verhalten lenken, ersetzen aber keine technische Schranke. Welche Prüfung
blockiert, warnt, nur beobachtet oder deaktiviert ist, muss außerhalb des
Producers aufgelöst und überprüfbar dokumentiert werden.

Kein Producer, Agent oder Provider erhält implizite Autorität. Rechte,
Credentials, Werkzeuge sowie Netz- und Dateizugriffe werden zweckgebunden,
minimal, zeitlich beziehungsweise auf einen Run begrenzt und nachvollziehbar
delegiert. Identität allein begründet keine Freigabeautorität. S.A.M.U.E.L.
muss dafür kein eigenes IAM bauen; es muss die benötigte und tatsächlich
verwendete Autorisierung als Teil des Provider- und Evidence-Vertrags
behandeln.

### 4. Producer sollen austauschbar werden

Ob eine Änderung von einem Menschen, dem mitgelieferten Referenz-Worker oder
einem fremden Werkzeug stammt, soll langfristig nicht die Freigabesemantik
ändern. Die passive, workerneutrale Übergabe eines vorhandenen Git-Candidates
an denselben Approval-, Subject- und Gatepfad ist implementiert (#521,
D05/D07). Eine allgemeine aktive Fremdworkersteuerung ist keine zugesagte
Produktfähigkeit; ihr Port- und Conformance-Vertrag entsteht erst bei einem
tatsächlichen zweiten Adapterbedarf.

### 5. Fail-closed gilt nur für den benannten Scope

Eine grüne Kontrolle beweist nur das, was sie tatsächlich geprüft hat. Eine
Syntaxprüfung ist kein Testlauf, ein Secret-Basisscan keine vollständige DLP,
ein Worktree keine Prozesssandbox und ein grünes Gate keine juristische
Zertifizierung. S.A.M.U.E.L. soll Grenzen präzise benennen, statt Sicherheit
aus der Anzahl vorhandener Kontrollen abzuleiten.

### 6. Standards und Werkzeuge werden integriert, nicht nachgebaut

S.A.M.U.E.L. soll weder eine allgemeine Policy-Sprache noch CI-, Sandbox-,
Plugin-, IAM-, Supply-Chain-, Attestation-, Scanner- oder
Dokumentationsplattformen ersetzen. OPA/Rego oder CEL, in-toto/Sigstore,
SARIF, JUnit, SCM-Checks, externe Runner, Scanner und Docs-Producer werden über
schmale Ports und passende Standardformate angebunden. S.A.M.U.E.L. prüft ihre
Evidence; ihre Fachfunktion wird nicht allein deshalb Core, weil eine
Out-of-the-box-Referenz mitgeliefert wird.

Es gibt kein seriöses Universalprotokoll für alle Integrationsrollen. Das
bevorzugte Profil kombiniert OpenAPI, CloudEvents/CDEvents,
in-toto-kompatible Attestations und domänenspezifische Standardartefakte. MCP
und A2A bleiben optionale Adapter für LLM-Werkzeuge beziehungsweise fremde
Agenten und erhalten keine Freigabeautorität.

Für LLM- und Agentenbeobachtung werden OpenTelemetry und, soweit ausreichend
reif und mit der Datenschutzpolicy vereinbar, die versionierten GenAI Semantic
Conventions bevorzugt. Telemetrie bleibt Beobachtung und wird nicht allein
durch ihr Format zu Evidence oder Authority. Prompt-, Antwort- und
Toolinhalte sind sensible optionale Daten, kein standardmäßig zu exportierender
Diagnoseumfang.

### 7. Menschen und Betreiber bleiben Teil der Vertrauensgrenze

Technische Gates reduzieren Risiko, ersetzen aber nicht automatisch Review,
Branch-Schutz, Rechteverwaltung oder betriebliche Verantwortung. Welche
Workflows menschliche Planfreigabe verlangen und welche autonom laufen, ist
explizite Konfiguration. Merge- und Deploymentregeln müssen im Zielsystem
wirksam eingerichtet und nachgewiesen werden.

Eine menschliche Zustimmung ist nur für die konkrete Aktion am exakten
Subject autoritativ, wenn die zustimmende Identität authentifiziert und die
Entscheidung dauerhaft nachvollziehbar ist. Wiederholte Bestätigungsdialoge
und pauschale Freigaben ersetzen keine technische Policy.

### 8. Referenzbetrieb ist Teil des Wirksamkeitsnachweises

Unit-, Integrations- und Architekturtests bleiben notwendig, beweisen aber
nicht allein, dass eine veröffentlichte Installation den zugesagten Weg
durchläuft. Jede Release-Zusage braucht deshalb einen reproduzierbaren
Referenzlauf aus einem veröffentlichten Paket oder Image gegen ein eigenes
Demo-Repository: mindestens ein vollständiger positiver Ablauf und ein echter
erwarteter Blockierfall mit gebundener Evidence.

Gitea, der Referenz-Worker, das lokale Dashboard und weitere mitgelieferte
Komponenten dürfen diesen sofort nutzbaren Referenzbetrieb bilden. Sie werden
als Referenzimplementierungen ausgewiesen und nicht zu versteckten
Core-Abhängigkeiten erklärt.

Eine betriebliche Wirksamkeitsaussage gilt nur für die nachgewiesene
Kombination aus S.A.M.U.E.L.-Version, Policy, effektiv verwendetem
Modell/Provider, Prompt-/Agent-Konfiguration, Toolchain und
Berechtigungsprofil. Wesentliche Änderungen dieser Kombination verlangen eine
erneute Evaluation. Das macht nicht jede Konfigurationsänderung zu einem
Release, verhindert aber stille Weiterverwendung eines überholten Nachweises.

### 9. Self-Mode verändert Candidates, nicht seine eigene Autorität

Der Self-Mode darf Änderungen am eigenen Repository einschließlich des
Core-Quellcodes als normalen Candidate erzeugen. Diese Änderungen durchlaufen
dieselbe PR-, Evidence- und Policy-Grenze wie fremde Änderungen. Der laufende
Prozess darf weder seine installierte Runtime noch Trust Roots, Updatepfad oder
wirksame Freigabepolicy selbst autorisiert überschreiben. Core-Updates werden
separat, atomar, nachvollziehbar und unter Betreiberautorität eingespielt.

## Benötigte Ebenen austauschbarer Nicht-Core-Capabilities

Für austauschbare Nicht-Core-Capabilities unterscheidet S.A.M.U.E.L. als
Architekturvokabular:

1. **Core-Vertrag:** Subject, Evidence, Policy, Zustände und Entscheidung.
2. **Mitgelieferte Referenzimplementierung:** unterstützter Standardbetrieb
   ohne Sonderrechte.
3. **Externer Adapter oder Provider:** austauschbare Implementierung über
   dieselbe fachliche Grenze.

Nur tatsächlich benötigte Ebenen werden implementiert. Eine Core-eigene
Semantik braucht keinen künstlichen Fremdprovider; eine gebündelte
Referenzfähigkeit braucht nicht vorsorglich eine vollständige
Providerplattform. Ein externer Port entsteht beim zweiten realen Provider
oder Anwendungsfall oder früher, wenn eine Security-/Authority-Grenze ihn
bereits verlangt.

„Austauschbar“ bedeutet nicht „nicht mitgeliefert“. Bestehende
Referenzfähigkeiten werden stabilisiert und erst nach funktionsgleichem,
evidenzgebundenem Cutover ersetzt.

## Was heute existiert

S.A.M.U.E.L. ist ein Alpha-Projekt. Der implementierte Stand ist kleiner als
das Zielbild, liefert aber bereits eine zusammenhängende Referenzstrecke:

- Ein integrierter Referenz-Worker verarbeitet Issues über Planung und
  Implementation bis zum Pull Request oder einem sichtbaren Blockzustand.
- GitHub und Gitea sind als SCM-Adapter vorhanden. Weitere Plattformen sind
  daraus nicht automatisch unterstützt.
- PR-Prüfungen arbeiten gegen einen gebundenen `EvaluationSubject`. Das aktive
  Required-Gate-Profil entscheidet; der gewichtete Evaluation-Score ist nach
  ADR-0399 ausschließlich nicht bindende Qualitätsbeobachtung.
- Acceptance Evidence unterscheidet bestandene, fehlgeschlagene, manuelle,
  nicht anwendbare, übersprungene und fehlerhafte Kriterienzustände.
- Einmaliges Healing darf nur aus passender, commitgebundener Acceptance-
  Evidence starten und muss den vollständigen Gate-Lauf erneut durchlaufen.
- Runtime-State für Beobachtungen, Claims, Finalisierungs-Resume und
  Dashboard-Projektion liegt in einem versionierten lokalen SQLite-Store.
- Audit-, Capability- und Dokumentationsansichten machen vorhandene Evidence
  und bekannte Wirksamkeitsgrenzen sichtbar. Sie ersetzen keine
  deploymentabhängige SCM- oder Compliance-Prüfung.

Die belastbare Detailaussage steht nicht in dieser Zusammenfassung, sondern in
der [Capability-/Wirksamkeitsmatrix](docs/CAPABILITY_MATRIX.md). Der
Alpha-Hinweis und die aktuell veröffentlichten Artefakte stehen im
[README](README.md).

## Wohin das Projekt geht

Die folgenden Richtungen sind offen. Ihre Issues dokumentieren den Vertrag;
dieses Manifest erklärt sie nicht vorzeitig als implementiert:

- **Realer Referenzbetrieb (#658):** Eine installierte Releasefassung muss den
  vollständigen positiven Pfad und mindestens einen echten Blockierfall
  reproduzierbar belegen, bevor weitere große Plattformausbauten als
  Produktfortschritt gelten.
- **Portable Evidence (#520/#679):** Der erste Gitea-SCM-Check-Adapter liest
  vorhandene Runs begrenzt, subjectgebunden und ausschließlich advisory.
  Requestgebundene Required-Wirkung, Dispatch und der externe
  Execution-Cutover bleiben #679; weitere Formate folgen erst realem Bedarf.
- **Workerneutraler Candidate-Vertrag (#521):** Referenz-Worker, Mensch und
  fremde Producer liefern zunächst denselben unveränderlichen Candidate;
  aktive Workersteuerung folgt erst bei realem Bedarf.
- **Externe Candidate-Ausführung (#679):** Candidate-Code soll außerhalb des
  Core in austauschbaren Execution-/CI-Providern laufen. Der heutige lokale
  Legacy-Pfad bleibt bis zum atomaren, nachgewiesenen Cutover sichtbar
  begrenzt; S.A.M.U.E.L. baut keine eigene Prozesssandbox.
- **Öffentliche Extension-Grenze (#639):** Zuerst entstehen schmale öffentliche
  Verträge, Kompatibilität, Enable/Disable und ein externes Conformance-
  Fixture. Eine vollständige Plugin-Lifecycle-Plattform ist kein Vorabziel.
- **Evidence-gebundene Dokumentation (#635/#636):** Das interne Wiki bleibt ein
  kleiner Pilot. Ein portables Add-on integriert vorhandene Producer,
  Verifier und Publisher über öffentliche Verträge, statt sie nachzubauen.

Diese Richtung kann sich nur über reviewbare Issues und ADRs ändern. Ein
Roadmap-Satz in diesem Dokument ersetzt keine Designentscheidung.

## Was wir bewusst nicht bauen

S.A.M.U.E.L. soll nicht werden:

- ein weiterer allgemeiner IDE-Codeassistent oder Chatbot,
- ein Vertrauensbonus allein für einen bestimmten Menschen, Agenten oder ein
  bestimmtes LLM,
- ein Ersatz für OPA/Rego, CEL oder unternehmensweite Policy-Plattformen,
- ein Ersatz für in-toto, Sigstore, SLSA, SBOM- oder Provenance-Werkzeuge,
- ein vollständiger Security-Scanner, DLP-Dienst oder eine Prozesssandbox
  unter neuem Namen,
- eine allgemeine CI-/Runner-, Plugin-Lifecycle-, Agenten-, IAM-, Billing- oder
  Dokumentationsplattform,
- eine automatische Compliance-, Rechts- oder Sicherheitszertifizierung,
- ein System, in dem schöne Dokumentation oder ein hoher Score eine
  commitgebundene Freigabe ersetzt.

Der Kernbeitrag soll die Verbindung sein: exakter Software-Candidate,
begrenzte und nachvollziehbare Evidence, explizite Policy und eine ehrliche
Entscheidung mit sichtbaren Grenzen.

## Mitarbeit und Diskussion

S.A.M.U.E.L. braucht nicht nur mehr Features, sondern überprüfbare Verträge.
Besonders hilfreich sind Beiträge zu:

- Threat Models und negative Conformance-Tests für Evidence, Worker, Provider
  und öffentliche Extension-Grenzen,
- backendneutralen Adaptern für SCM, Policy, Scanner und Attestations,
- reproduzierbaren installierten Referenzläufen mit Positiv- und
  Negativevidence,
- reproduzierbaren Fremd-Repository-Fixtures statt nur projektspezifischen
  Happy Paths,
- verständlicher Dokumentation, die Runtime-Iststand, Zielbild und bekannte
  Grenzen nicht vermischt,
- realen Betriebsnachweisen auf unterschiedlichen Installations- und
  SCM-Umgebungen.

Diskussionen sollen mit einem konkreten Issue beginnen: Welcher Subject wird
geprüft, welche Evidence liegt vor, welche Policy entscheidet, und was bleibt
ausdrücklich außerhalb des Scopes?

So bleibt die Leitfrage praktisch:

> **Trust the change, not the producer — and prove what “trust” means for this
> exact change.**
