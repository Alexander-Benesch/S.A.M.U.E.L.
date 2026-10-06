---
id: ADR-0635
title: Deterministischer Wiki-Pilot auf vorhandener Dokumentations-Governance
status: accepted
decision_issue: 635
decision_date: 2026-08-29
decision_digest: sha256:6fcdc620adcc6776ee6d28b54c1e75cd72c67b97e6776d47f6a77c1a3004f5cc
supersedes: []
superseded_by: []
---

# Deterministischer Wiki-Pilot auf vorhandener Dokumentations-Governance

## Kontext

S.A.M.U.E.L. besitzt seit #572/#574 einen versionierten Dokumentvertrag,
abschnittsbezogene Quellenbindungen, deterministisch generierte
Runtime-/ADR-Referenzen sowie Drift-, Link-, Anker- und Impactprüfungen. Der
interne Bestand ist fachlich umfangreich, aber auf viele aktive Dokumente
verteilt. Für neue Entwickler, Maintainer, Operatoren und Reviewer fehlt eine
gemeinsame, aufgabenorientierte Wiki-Navigation.

Allgemeine Code-zu-Wiki-Generierung, inkrementelle Aktualisierung und einfache
Source-Provenance sind zugleich kein unbesetztes Produktfeld. OpenWiki,
Evidoc, Swimm, Stewie, Mintlify und etablierte Publisher decken Teile davon
bereits ab. S.A.M.U.E.L. soll deshalb weder seine bestehende
Dokumentations-Governance duplizieren noch einen allgemeinen AI-Wiki-Generator
als neuen Produktkern nachbauen.

## Entscheidung

Der erste Wiki-Pilot ist eine **deterministische, nicht autoritative Projektion**
des bestehenden Dokumentvertrags. Er erweitert beziehungsweise extrahiert die
vorhandenen Resolver aus `tools/control_matrix.py`; er führt keine zweite
Control-Matrix, Runtime-Referenz, Auditspur oder technische Primärquelle ein.

Der erste nutzbare Build benötigt weder LLM noch Publisher, Netzwerk,
Referenz-Worker-Workflow, #520 oder #619. Er führt keinen Candidate-Code aus
und verändert keine PR-/Release-Autorität.

### Stabile Seitenidentitäten

Der Pilot verwendet diese zehn stabilen Page-IDs und genau diese Reihenfolge:

| Page-ID | Titel | Primäre Aufgabe |
|---|---|---|
| `wiki.home` | Start und Systemüberblick | Einstieg, Produktgrenze und personaorientierte Wege |
| `wiki.architecture` | Architektur und Verantwortungsgrenzen | Zielbild, Ist-Abgrenzung, Ports, Bus und Slices einordnen |
| `wiki.pipeline` | Pipeline von Issue bis PR | reale Planungs-, Implementierungs-, Gate-, Evaluation- und Healingpfade verfolgen |
| `wiki.components` | Komponentenreferenz | Commands, Events, Slices, Ports, Adapter und APIs auffinden |
| `wiki.assurance` | Gates, Controls und Evidence | Wirkung, Profile, Evidence, Limits und offene Restpunkte prüfen |
| `wiki.configuration` | Konfiguration und effektive Prioritäten | verfügbare, ausgelieferte und effektiv aktive Werte unterscheiden |
| `wiki.operations` | Betrieb und Diagnose | Installation, Deployment, CLI, Runtime-State und Runbooks nutzen |
| `wiki.security` | Security, Evidence und Compliance-Grenzen | Schutzmechanismen, Trust Boundaries und Nicht-Zusagen verstehen |
| `wiki.decisions` | Entscheidungen und Issue-Navigation | ADRs, Supersession, Herkunft und Umsetzungsissues verfolgen |
| `wiki.document-status` | Dokumentstatus und Quellen | aktive Dokumente nach Klasse, Modus und Bindung prüfen |

Die IDs sind Maschinenvertrag; Titel und Darstellung dürfen später
weiterentwickelt werden. Eine Umbenennung oder Aufteilung einer ID benötigt
eine versionierte Manifestmigration und darf Links nicht still brechen.

### Persona-Einstiege

Die Startseite bietet mindestens diese Wege:

- **Entwickler:** `wiki.architecture` → `wiki.components` → `wiki.pipeline`;
- **Maintainer:** `wiki.decisions` → `wiki.assurance` →
  `wiki.document-status`;
- **Operator:** `wiki.operations` → `wiki.configuration` → `wiki.security`;
- **Reviewer:** `wiki.pipeline` → `wiki.assurance` → `wiki.decisions`.

Diese Wege sind zusätzliche Navigation. Sie verändern keine Quellenautorität.

## Quellen- und Autoritätshierarchie

Für technische Laufzeitaussagen gilt:

1. getrackter Produktcode und ausgelieferte Konfiguration,
2. daran gebundene Resolver und maschinenlesbare Facts,
3. deterministisch generierte Referenzen,
4. explizit quellgebundene, manuell geprüfte Einordnung,
5. gekennzeichnete Zielarchitektur oder zeitgebundene Historie.

Eine niedrigere Stufe darf eine höhere weder überschreiben noch still
aufwerten. `docs/capabilities/control-matrix.json` bleibt Quelle für
Auditbewertung und Claim-Zuordnung, nicht für das tatsächliche
Laufzeitverhalten.

Wiki-Seiten, `docs/RUNTIME_REFERENCE.md`, `docs/CAPABILITY_MATRIX.md` und der
ADR-Index sind abgeleitete Artefakte. Sie dürfen nicht als technische
Primärquelle in ihre eigenen Resolver zurückfließen. Freie Prosa wird nicht
pauschal als formal verifiziert bezeichnet.

## Coverage-Baseline des ersten Builds

Die 31 am Ausgangsstand aktiven Dokumente und das durch diese Entscheidung
hinzukommende ADR erhalten je eine primäre Wiki-Seite. Weitere Querwege sind
zulässig; die Primärzuordnung verhindert, dass ein Dokument zwischen mehreren
Übersichten verschwindet.

| Primäre Page-ID | Aktive Dokumente am Entscheidungsstand |
|---|---|
| `wiki.home` | `README.md`; `CONTRIBUTING.md` |
| `wiki.architecture` | `docs/SAMUEL_ARCHITECTURE_V2.1.md` |
| `wiki.pipeline` | `technische Beschreibungen/README.md`; `technische Beschreibungen/pipeline_evaluation.md`; `technische Beschreibungen/pipeline_issue_to_llm.md`; `technische Beschreibungen/pipeline_planning.md`; `technische Beschreibungen/pipeline_pr_gates.md` |
| `wiki.components` | `docs/README_technical.md` |
| `wiki.assurance` | `docs/CAPABILITY_MATRIX.md`; `docs/GATE_COMPLIANCE_MATRIX.md` |
| `wiki.configuration` | `docs/RUNTIME_REFERENCE.md` |
| `wiki.operations` | `.claude/CLAUDE.md`; `docs/CI_RUNNER_OPERATIONS.md`; `docs/CONTAINER_RELEASE_OPERATIONS.md`; `docs/INSTALL.md`; `docs/OPERATING_RULES.md`; `docs/VERSIONING.md` |
| `wiki.security` | `SECURITY.md`; `docs/AI_ACT_COMPLIANCE.md`; `docs/AI_ACT_TECHNICAL_DOC.md`; `docs/DSGVO_VVT.md` |
| `wiki.decisions` | `docs/SAMUEL_DESIGN_DECISIONS.md`; `docs/adr/0399-score-authority.md`; `docs/adr/0482-runtime-state-store.md`; `docs/adr/0583-installed-cli-entrypoint.md`; `docs/adr/0618-worktree-manager.md`; `docs/adr/0619-candidate-sandbox.md`; `docs/adr/0620-preflight-gate-state.md`; `docs/adr/0635-wiki-pilot.md`; `docs/adr/README.md` |
| `wiki.document-status` | `CHANGELOG.md` |

Damit umfasst die Entscheidungsbaseline 32 aktive Dokumente. P1 darf die Zahl
nicht hardcodieren: Ein versioniertes Wiki-Manifest muss das jeweils aktuelle
Dokumentinventar exakt abdecken. Ein neues aktives Dokument ohne primäre
Page-ID lässt den Wiki-Check fail-closed scheitern; Archive bleiben
zeitgebundene Historie außerhalb des aktiven Inventars.

## Build- und Receipt-Vertrag

P1 erzeugt den lokalen Build unter `build/wiki/`. Dieser Pfad wird ignoriert,
nicht paketiert, nicht in State-Backups aufgenommen und nicht als aktives
Dokument inventarisiert. Quelländerungen erfolgen weiterhin ausschließlich in
getrackten Code-, Config-, Vertrags- und Dokumentdateien.

Jeder Build erzeugt ein maschinenlesbares Receipt mit mindestens:

```text
repository
head_sha
document_contract_digest
source_digest
generator_version
artifact_digest
page_manifest
findings
created_at
```

Der `artifact_digest` wird aus kanonisch sortierten Page-IDs, Zielpfaden und
Seitenbytes gebildet. Wall-Clock-Zeit, lokaler absoluter Pfad und volatile
Publisherdaten gehören nicht in diesen Digest. Sichtbare Buildzeit verwendet
die gebundene Commitzeit beziehungsweise `SOURCE_DATE_EPOCH`; die tatsächliche
Laufzeit steht ausschließlich im Receipt.

Das Receipt ist lokale Build-Provenienz. Es ist ausdrücklich **kein**
`EvidenceEnvelope`, keine Gate-Evidence, keine Freigabeentscheidung und kein
Publication Receipt. Ein Publisher benötigt später ein getrenntes Receipt,
das Ziel, Zielrevision und externe Wirkung an den `artifact_digest` bindet.

## Rendering-Regeln

- P1 erzeugt Navigation und gebundene Projektionen; es kopiert nicht blind
  sämtliche Langform in ein zweites redaktionelles System.
- Jede Seite kennzeichnet Runtime Reference, Operations, ADR/Zielentscheidung,
  Target Architecture und History sichtbar.
- Generierte Laufzeitfacts nennen ihre konkreten Code-/Configquellen oder den
  gebundenen Quellenmanifestverweis.
- Links, Pfade, Anker und vorhandene Symbolreferenzen werden geprüft. Fehlende
  Ziele werden Findings, nicht still gültige Navigation.
- `qualified`, `advisory`, `telemetry`, bekannte Grenzen und offene Issues
  dürfen beim Rendern nicht verschwinden oder aufgewertet werden.
- Der lokale Build bleibt ohne LLM und externen Publisher vollständig
  nutzbar.

## Build-versus-Adapter-Regel

Der native P1-Renderer bleibt klein und liefert die deterministische
Referenz-/Navigationsfähigkeit für S.A.M.U.E.L. Vor jeder breiteren
Textgeneration oder Verifierimplementierung werden vorhandene Werkzeuge erneut
gegen Lizenz, Version/Digest, Datenfluss, Self-Hosting, Reproduzierbarkeit,
Sicherheitsgrenzen und den benötigten Portvertrag geprüft.

OpenWiki ist ein möglicher untrusted Producer, Evidoc ein möglicher
Verifieradapter; MkDocs, Backstage, Mintlify und Git Wiki sind mögliche
Publisherziele. Die Nennung aktiviert keine Abhängigkeit und verleiht keinem
Werkzeug Autorität. Volatile Marktangaben werden vor einer Adapterentscheidung
neu verifiziert.

## Security- und Betriebsgrenze

P0 und P1 führen keinen Candidate-Code aus, lesen keine Operator-Secrets,
benötigen keine SCM-/LLM-/Cloud-Tokens und führen keine externe
Netzwerkwirkung aus. #619 bleibt Voraussetzung für spätere
kandidatenkontrollierte Ausführung. #520 bleibt Voraussetzung für portablen
Evidence-Ingest und ein generisches Evidence-Gate.

Das Wiki darf fehlende fachliche Klärung, schwache Acceptance Contracts oder
manuelle Annahmen nicht durch überzeugende Darstellung verdecken. #575 bleibt
der getrennte Readiness-/Clarification-Vertrag.

## Konsequenzen

- P1 ist eine mechanisch begrenzte Renderer-/Manifestaufgabe und keine offene
  Produkt- oder Subject-Designentscheidung.
- Das Wiki liefert früh praktischen Nutzen, ohne auf die späteren Add-on-
  Verträge zu warten.
- Vollständigkeit wird gegen das aktive Dokumentinventar gemessen, nicht gegen
  die Menge zufällig extrahierter Facts.
- Eine spätere Publication, typisierte Claimverifikation, LLM-Produktion oder
  Gate-Autorität benötigt jeweils ein eigenes Child-Issue und reale Evidence.
- Das portable Add-on #636 übernimmt nur nachweislich neutrale Verträge; die
  S.A.M.U.E.L.-Informationsarchitektur bleibt ein interner Adapter.

## Rollout-Grenze

Diese Entscheidung erzeugt noch kein Wiki-Artefakt und ändert keine
Produktlaufzeit. P1 muss den Build zweimal für denselben getrackten Stand
ausführen und identische Seitenbytes sowie identischen `artifact_digest`
belegen. Erst ein späteres Publisher-Issue darf externe Wirkung erzeugen. Eine
Required-Gate-Semantik ist frühestens nach #520, typisierten Claims und
gebundener Rollout-Evidence zulässig.
