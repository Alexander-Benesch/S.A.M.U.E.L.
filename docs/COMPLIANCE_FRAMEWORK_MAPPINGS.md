# Compliance-Framework-Mappings und CRA

## Implementierter Umfang

Stand 06.10.2026, Issue #873: CRA ist als **advisory Mapping** zu vorhandenen
technischen Controls verfügbar. OWASP, AI Act, GDPR und CRA verwenden den
package-relativen Loader in `samuel/core/compliance_mapping.py`. Die bisherige
OWASP-/AI-Act-API und ihre Kategorie-/Artikel-IDs bleiben erhalten. Die
GDPR-Definition beschreibt vorhandene Privacy-Mechanismen; sie ersetzt diese
nicht. Das Dashboard zeigt die vier Definitionsversionen, Mappingversionen,
Digests und Controls über die vorhandene Compliance-Legend-API.

Das ist der Umfang der heutigen OWASP-/AI-Act-Zuordnung, **kein vollständiger
aktiver Framework-Pack-/Policy-Vertrag**. Eine Eventzuordnung ist weder eine
Prüfung der referenzierten Evidence noch ein ALLOW/REVIEW/BLOCK-Entscheid.
Keine neue Runtime-, Gate-, Authority-, Release- oder Default-Policy wird
aktiviert. Der CRA-Inhalt bewirkt keine zusätzlichen Pflichten im Workflow.
Die unveränderten Privacy-, Attribution- und Security-Invarianten gelten
weiterhin unabhängig von dieser beschreibenden Framework-Schicht.

## Definition und Verwendung

Die JSON-Dateien unter `samuel/core/compliance/` reisen als Package-Data mit.
Jede Definition besitzt Framework-ID, Framework-Version, Mapping-Version,
Primärquelle, Controls, Eventmappings und optionale Kategorie-Fallbacks. Die
Mappingidentität bindet einen kanonischen SHA-256-Digest der ganzen Definition;
auch geänderter Inhalt unter derselben Versionsnummer erhält einen anderen
Digest. Control-/Versionsänderungen brauchen keinen neuen Core-Codepfad.

Die generische Mappingfunktion kann von einem expliziten Consumer verwendet
werden:

```python
from samuel.core.compliance_mapping import COMPLIANCE_DIR, load_mapping

mapping = load_mapping(COMPLIANCE_DIR / "cra.json")
annotation = mapping.annotate(
    scope="example/release-1",
    selected_scopes=("example/release-1",),
    evidence_id="existing-observation-id",
    category="eval",
    event="test_run",
)
```

Ohne exakte Scopeauswahl entsteht keine Annotation. Ein Scopepräfix oder die
Auswahl eines anderen Frameworks aktiviert sie nicht. Der Consumer übergibt
die vorhandene Evidenceidentität; der Mapper kopiert und bewertet deren
Payload nicht. Dieselbe Evidence kann mehrere Frameworkzuordnungen erhalten.
Fehlende oder fehlerhafte ausgewählte Definitionen werden vor einer Annotation
abgelehnt. Ein ungültiges optionales Pack wird im Dashboard als ungültig
angezeigt und beschädigt keine anderen Frameworkanzeigen.

Eine historische Annotation muss zusammen mit ihrer vollständigen Mapping-
identität gespeichert werden. Die zurückgegebenen Werte und das geladene
Mapping sind immutable Snapshots; später geladene Definitionen ändern sie
nicht. Vorhandene historische OWASP-/AI-Act-Records werden nicht rückwirkend
mit CRA annotiert. Diese API führt **keinen neuen persistenten Store** ein.

## CRA-Bezug und Grenzen

Primärquelle: [Verordnung (EU) 2024/2847](https://eur-lex.europa.eu/eli/reg/2024/2847/oj).
Der technische Querverweis umfasst Risikoanalyse, sichere Entwicklung,
Schwachstellenbehandlung, Tests, Komponenten-/SBOM-Evidence, Updates,
technische Dokumentation und Meldungen. Die konkreten Referenzen stehen in
`cra.json`. Nicht vorhandene SBOM-, Incident- oder Prozessnachweise werden
nicht aus einem Test- oder Mergeevent erfunden. Externe Werkzeuge und
Betreiber liefern diese Nachweise. Anwendungsbereich, Meldungserfüllung,
Konformitätsbewertung und rechtliche Compliance sind keine Mappergebnisse.

## Architekturprüfung A–D

| Bereich / Quellpfad | Klasse | Befund und Behandlung |
|---|---|---|
| Package-JSON und Event-/Kategorie-Mappings (`core/compliance/`) | A | Deklarative Daten, austauschbare Controls und Versionen; generische normalisierte Mapping-API. |
| Separate Dateileser in `core/owasp.py`, `core/ai_act.py` | B → verbessert | Gemeinsamer Loader; Legacy-Fassaden erhalten ihre bestehenden öffentlichen Maps, Descriptions und Risk-Class-Funktionen. |
| Auditbridge und `audit_trail/handler.py`, `core/types.py`, Auditquery/-Persistenz | B | Historische `owasp_risk`-Felder bleiben kompatibel. Noch keine generische persistierte Pack-/Policy-/Scopebindung; neue API-Annotationen allein ersetzen sie nicht. |
| `adapters/audit/sarif.py`, `async_sink.py`, `upcasters.py` | B | OWASP-Finding-/Prioritäts- und Legacyprojektionen bleiben frameworkbezogen. Keine neue CRA-Findingklassifikation, Schemaänderung oder Umdeutung alter Logs. |
| Dashboard-Legend und Compliance-Tab | B → verbessert | Gemeinsame Mappingidentitäten und Tabellen; bestehende OWASP-/AI-Act-Felder und Risk-Class-UI bleiben kompatibel. Andere Audit-/Securityansichten behalten Legacyspalten. |
| Gate-/Webhook-/Budgetdiagnosen (`pr_gates/gates.py`, `api/webhooks.py`, `llm/workflow_budget.py`) | B | Direkte OWASP-Codes sind Diagnosemetadaten. Keine CRA-Verzweigung oder neue Entscheidungsregel; weitere Entkopplung wäre eine eigenständige kompatible Projektionsänderung. |
| AI-Act-Risikoklasse und `core/attribution.py` | D | Ausdrücklich bestehender Attributionvertrag #270/#373/#374; ein deaktiviertes Mapping darf verpflichtende Audit-/Human-/Attributiongrenzen nicht abschalten. Rechtliche Aussage des Gesamtdeployments bleibt separat. |
| Privacy-Sanitizer, Transfer-/Retentionregeln | D | Bestehende Datenschutz-/Security-Invarianten; kein austauschbares Framework darf sie implizit entfernen. Retention bleibt zweck-/rollen-/configgebunden. |
| Policy/Authority, Execution Conformance, Release Lineage | A für den neuen Inhalt | CRA registriert keine Subscriber/Gates und importiert diese Entscheider nicht; vorhandene generische Evidence-/Subject-/Release-Primitiven werden nur referenziert. |
| Eventcoverage und Legacy-ID-/Key-Tests | D/B | Bisherige Coverage ist weiter erforderlich; neue normalisierte API erhält zusätzlich Shape-, Versions-, Scope- und Fehlertests. Keine stillschweigende Migration der Legacy-Taxonomie. |

Keine notwendige Security-Invariante wird zur optischen Vereinfachung entfernt.
Der Scan umfasst Core, API, Audit/Persistenz, Reports, Dashboard, Gates und
Tests; der gemeinsame Loader allein beweist keine vollständige Entkopplung.
Die verbleibenden B-Kopplungen und die aktive Packgrenze sind sichtbar.

## Nachweise und offener Vollscope von #873

Die gezielten Regressionen in `tests/test_compliance_mapping.py` prüfen alle
bestehenden exakten OWASP-/AI-Act-Mappings und Fallbacks, Version-/Inhaltswechsel,
historische Identitäten, gemeinsame Evidence, exakte Scopeauswahl und fehlende
Auswahl sowie ungültige Definitionen und isolierte Dashboardfehler (einschließlich
ungültiger UTF-8-Dateien und nicht kodierbarer Unicodewerte). Bestehende
Eventcoverage-, Audit-, Privacy-, Policy-, Gate-, Dashboard- und Volltests
bleiben erforderlich. Kein neuer rechtlicher oder realer Workflow-PASS.

Für den ursprünglichen vollständigen #873-Scope fehlen weiterhin der
beschlossene aktive Pack-/Policy-Vertrag und dessen eigene Runtimeabnahme:
welche bestehenden Policies einen Packscope konsumieren, welche Evidence
Pflicht ist und wie Pack-/Policy-/Scopeversionen im vorhandenen Authority-/
Auditmodell persisted werden. ALLOW/REVIEW/BLOCK, historische Reports,
Installationen ohne Packkonfiguration und aktive Fehlermappings benötigen
anschließend ihre vollständige Consumerregression. #873 bleibt daher mit
seinem Vollscope offen; diese advisory Umsetzung ist kein stiller Vollabschluss.
