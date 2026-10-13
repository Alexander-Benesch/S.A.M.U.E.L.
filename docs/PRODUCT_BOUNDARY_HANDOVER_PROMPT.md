# Übergabeprompt: S.A.M.U.E.L. stabilisieren, integrierbar halten und real betreiben

Den folgenden Block vollständig in einen neuen Arbeitschat kopieren.

```text
Arbeite im bereitgestellten S.A.M.U.E.L.-Repository weiter; stelle dessen
tatsächlichen Checkoutpfad fest.

Prüfe zu Beginn den aktuellen lokalen `main`-, `origin/main`- und Gitea-Stand;
verlasse dich nicht auf einen im Prompt festgeschriebenen Commit. Verwende
S.A.M.U.E.L. derzeit nicht im Self-Mode zur Bearbeitung seines eigenen
Repositories.

Verbindliche Quellen und Reihenfolge vor Änderungen:

1. `CONTRIBUTING.md` und `docs/OPERATING_RULES.md` vollständig lesen.
2. `MANIFESTO.md`, ADR-0678, ADR-Index und die für den Scope relevanten ADRs
   vollständig lesen.
3. `docs/SAMUEL_DESIGN_DECISIONS.md`,
   `docs/SAMUEL_ARCHITECTURE_V2.1.md`, `docs/README_technical.md`,
   `docs/RUNTIME_REFERENCE.md`, `docs/CAPABILITY_MATRIX.md` sowie relevante
   Betriebs-/Pipeline-Dokumente abgleichen.
4. Alle offenen Gitea-Issues einschließlich Kommentare live abrufen; ein
   lokaler Export ist nur Snapshot und keine aktuelle Authority.
5. Behauptungen danach gegen Code, ausgelieferte Konfiguration, Tests und reale
   Betriebs-/SCM-Evidence prüfen. Bei Widerspruch ist Code plus reale Evidence
   die Ist-Wahrheit; Zielarchitektur und historische ADRs werden als solche
   gekennzeichnet.

Produktgrenze aus #678 / ADR-0678:

- S.A.M.U.E.L. ist Orchestrierungs-, EvaluationSubject-, Evidence-, Policy-
  und Entscheidungsschicht.
- Für austauschbare Nicht-Core-Capabilities werden Core-Vertrag,
  mitgelieferte Referenzimplementierung und externer Adapter/Provider als
  mögliche Ebenen betrachtet. Implementiere nur tatsächlich benötigte Ebenen;
  ein externer Port entsteht beim zweiten realen Provider/Anwendungsfall oder
  früher wegen einer Security-/Authority-Grenze.
- Mitgelieferte Komponenten sind erlaubt und für Out-of-the-box-Betrieb
  erwünscht, besitzen aber keine Sonderrechte und müssen austauschbar bleiben.
- Vor Eigenbau etablierte Werkzeuge und Standards prüfen. Bevorzugt werden je
  Rolle OpenAPI, CloudEvents/CDEvents, in-toto/DSSE, SARIF, JUnit,
  CycloneDX/SPDX, SCM-Checks, OIDC, OCI und OpenTelemetry. MCP/A2A sind
  optionale Adapter und niemals Freigabeautorität.
- Keine eigene allgemeine CI-, Sandbox-, Plugin-Lifecycle-, Agenten-, IAM-,
  Billing-, Scanner- oder Dokumentationsplattform bauen.
- Candidate-Code soll nach #679 außerhalb des Core in einem austauschbaren
  Execution-/CI-Provider laufen. Der heutige lokale Verifier ist bis zum
  vollständig belegten atomaren Cutover ein sichtbarer Legacy-Risikopfad; er
  wird nicht ersatzlos entfernt und nicht als Sandbox dargestellt.
- Pro Capability und Run existiert genau eine Authority. Shadowprovider dürfen
  vergleichen, aber nicht gemeinsam entscheiden oder versteckt zurückfallen.
- Kein Producer, Agent oder Provider erhält implizite Autorität. Rechte,
  Credentials, Werkzeuge sowie Netz- und Dateizugriffe minimal, zweck-, zeit-
  und rungebunden delegieren; Identität allein ist keine Freigabe.
- Fremd-Evidence neben Subject/Policy an Issuer/Vertrauensprofil, Provenance,
  Integrität, Tool-/Ausführungsumgebung, Freshness und Replay binden. Candidate
  und Producer autorisieren die eigene Evidence nicht automatisch.
- Self-Mode darf Änderungen am Core-Quellcode als normalen Candidate
  erzeugen, aber laufende Installation, Trust Roots, Updatepfad und wirksame
  Policy nicht selbst autorisiert überschreiben.
- Menschliche Zustimmung ist nur authentifiziert, auf exakten Subject und
  konkrete Aktion begrenzt sowie auditierbar autoritativ. Wiederholte
  Bestätigungsdialoge ersetzen keine technische Policy.
- Betriebliche Wirksamkeitsclaims gelten nur für die nachgewiesene Kombination
  aus Version, Policy, effektivem Modell/Provider, Prompt-/Agent-Konfiguration,
  Toolchain und Berechtigungsprofil; wesentliche Änderungen neu evaluieren.
- Über einen schmalen fachlichen Port hinaus erst beim zweiten realen Adapter
  oder Anwendungsfall generalisieren. Security-/Authority-Grenzen bleiben
  davon ausgenommen.

Verbindliche Grenzkarte für jedes neue oder wesentlich erweiterte Issue:

1. konkretes Nutzerproblem und kleinster End-to-End-Pfad;
2. bereits vorhandener Code, Betrieb und geeignete Fremdwerkzeuge;
3. Core-Semantik und nur tatsächlich benötigte Referenz-/Provider-Ebenen;
4. geprüfter Standard/Adapter und Build-versus-Integrate-Begründung;
5. genau eine Authority, Fehler- und Fallbacksemantik;
6. ausdrückliche Nicht-Ziele;
7. realer Referenznachweis.

Wenn aus einem Finding gleichzeitig Port, Schema, Store, Events, Dashboard,
Migration, Doctor und Conformance-Suite entstehen sollen, stoppe die
Umsetzung und lege die notwendige Designentscheidung transparent vor. Keine
Designentscheidung eigenmächtig treffen. Umsetzungsdetails, die aus
bestehenden Entscheidungen eindeutig folgen, dagegen selbständig und ohne
unnötige Unterbrechung abarbeiten.

Aktuelle Priorität:

1. `docs/status/CURRENT_PRODUCT_STATUS.md` und die Live-Issues lesen; diese
   Übergabe kopiert keinen tagesgebundenen Arbeitsvorrat als aktuelle Wahrheit.
2. Historische #658-Teilnachweise unverändert erhalten. Ein älterer Bot-Merge
   oder ein neuer Installationsteilnachweis ist kein vollständiger D0-PASS.
3. Bereits implementierte Teile von #520/#521/#679/#422/#636/#639 im aktuellen
   Main erkennen; ihre jeweiligen Qualifications separat prüfen. Keine neue
   Parallelimplementation aus alten Aufgabenlisten ableiten.
4. Den nächsten autonom belegbaren Rest nach Issue- und Capabilityvertrag
   bearbeiten. Human Merge, Releasebindung, externe Voraussetzungen und neue
   Design-/Authorityentscheidungen am zuständigen Issue parken.

Arbeits- und Abschlussregeln:

- Bestehende Architektur und Ports verwenden; keine Parallelwelt.
- Issues, Code, Tests, Doku und reale Evidence vor Umsetzung gegeneinander
  prüfen.
- Akzeptanzkriterien einzeln mit tatsächlicher Evidence abnehmen.
- Tests niemals überspringen oder fehlende Tests als Erfolg darstellen.
- Findings zuerst gegen bestehende Issues suchen; nur bei fehlender Abdeckung
  ein neues Issue anlegen und Ursprung/Abhängigkeit verlinken.
- Keine Interna, Secrets, Tokens, private Netzwerkdetails oder lokale
  Konfiguration in öffentliche Repositories, Wikis oder Evidence übernehmen.
- Änderungen modular, reviewbar und rückrollbar halten. Kein Rückbau einer
  nutzbaren Fähigkeit ohne funktionsgleichen, nachgewiesenen Cutover.
- Alle betroffenen aktiven Dokumente im selben Change codegenau aktualisieren;
  Archive bleiben historische Snapshots.
- Branch, Commit, PR und erforderlichen Push-/CI-Nachweis vollständig liefern.
- Ein Issue erst schließen, wenn Kriterien, Dokumentation, Referenzissues und
  Nachweise vollständig erfüllt sind.
- Nach einem abgeschlossenen Issue den nächsten abhängigen Schritt nennen;
  ohne echte Designentscheidung oder externe Blockade selbständig fortfahren.

Starte mit einem kurzen Ist-Abgleich und nenne vor jeder Änderung:

- welches Issue bearbeitet wird,
- warum es jetzt an der Reihe ist,
- welche Capability-Grenze gilt,
- welche Designfragen bereits entschieden sind,
- welche Punkte gegebenenfalls noch menschliche Entscheidung benötigen.

Implementiere nichts, das über den bestätigten Scope hinausgeht. Wenn der
Auftrag nur Audit oder Planung verlangt, ändere keine Runtime.
```

## Pflegehinweis

Der Prompt verweist absichtlich auf `main` und Live-Gitea statt auf eine feste
SHA oder eine kopierte Issue-Liste. Seine Produktgrenze ist durch ADR-0678
gebunden. Ändert eine spätere ADR diese Grenze, müssen dieser Prompt, Manifest,
Operating Rules und die betroffenen Issue-Kommentare im selben Change geprüft
werden.
