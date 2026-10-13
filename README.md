> **Public snapshot · 13.10.2026:** Bereinigte Projektion des aktuellen integrierten Entwicklungsstands. Herkunft, Public-Bindung und Releasestand: [PUBLIC_SNAPSHOT.md](PUBLIC_SNAPSHOT.md).

# S.A.M.U.E.L.

S.A.M.U.E.L. verbindet einen Softwareänderungsauftrag mit dem konkreten
Candidate, den passenden Prüfnachweisen und der dafür geltenden Policy.
Teams können dadurch nachvollziehen, **was geändert werden durfte, was
wirklich geprüft wurde und worauf eine Entscheidung beruht**. Ein
mitgelieferter Referenz-Worker kann zusätzlich den Weg vom Issue über Planung
und Codeerzeugung bis zum Pull Request übernehmen.

Der Produktkern bleibt auch dann relevant, wenn Code anderswo entsteht:
Ein passiv eingereichter Git-Candidate verwendet den bestehenden gebundenen
Approval-, Subject- und Gatepfad. Producer und ihre eigenen Bewertungen
verleihen einer Änderung keine Freigabeauthority.

[S.A.M.U.E.L. Manifest](MANIFESTO.md) — Produktthese und Richtung ·
[Technischer Überblick: Architektur begreifen](docs/TECHNICAL_OVERVIEW.md) ·
[Advanced: Funktionen und Implementierung nachvollziehen](docs/README_technical.md)

## Wofuer S.A.M.U.E.L. da ist

Ein grüner Testlauf, ein Scannerbefund und ein Review können sich auf
unterschiedliche Commits oder Voraussetzungen beziehen. Der Kern verbindet
deshalb den Änderungsauftrag und Acceptance Contract mit einem unveränderlichen
Prüfgegenstand: Repository, vollständige Base-/Head-SHA, Contract und Policy.
Prüfungen und Entscheidungen müssen zu diesem Gegenstand passen. Fehlende
oder widersprüchliche Bindungen werden an ihren definierten Grenzen sichtbar
und blockieren dort, wo der Vertrag dies verlangt.

Der Nutzen liegt in einer prüfbaren Entscheidungskette: Welche Bedingung war
maßgeblich? Welche Evidence liegt dafür vor? Welche Kontrolle hat blockiert,
nur gewarnt oder ausschließlich beobachtet? Ein LLM-Score oder Dashboardstatus
kann fehlende Authority nicht ersetzen.

## Was S.A.M.U.E.L. bereits mitbringt

Der Governance-Core hält Auftrag, Änderung und Nachweise zusammen. Der
Referenz-Worker erzeugt passende Candidates; Routing und Codekontext
unterstützen seine Arbeit. Dashboard, CLI, API und Audit machen den Ablauf
bedienbar und nachvollziehbar. Die folgende Übersicht beschreibt vorhandene
Fähigkeiten und ihren praktischen Einsatz. Welche Konfiguration sie aktiviert
und welche Wirkung im Einzelnen geprüft ist, steht in den verlinkten Referenzen
und der [Capability-/Wirksamkeitsmatrix](docs/CAPABILITY_MATRIX.md).

### Änderungen steuern und nachvollziehbar entscheiden

| Fähigkeit | Was sie ermöglicht und wozu sie dient | Technische Vertiefung |
|---|---|---|
| **Acceptance Contracts, Policy und Candidatebindung** | Erlaubten Umfang und Erfolgskriterien vor der Änderung festhalten; anschließend Repository, Base/Head, Contract und Policy zusammen prüfen. So kann das Team den vollständigen Diff seinem Auftrag zuordnen. | [Contracts und Acceptance](docs/README_technical.md#10-akzeptanzkriterien-verifier) |
| **Evidence und Gates** | Kriteriumsbezogene Nachweise prüfen und Required-, advisory- und Beobachtungswirkung unterscheiden. Statische Preflights stehen vor der kandidatenkontrollierten Acceptance-Ausführung. | [Gates und Evidence](technische%20Beschreibungen/pipeline_pr_gates.md) |
| **Menschliche Freigaben und MANUAL-Acceptance** | Erforderliche Planfreigaben und manuelle Kriterien an ihren konkreten Gegenstand binden. PR und Review zeigen, welche Nachweise eine menschliche Entscheidung tragen und was noch offen ist. | [Freigabe- und Prüfablauf](technische%20Beschreibungen/README.md) |
| **Workflowsteuerung** | Konfigurierte Ereignisse, Bedingungen und Arbeitsschritte verknüpfen Planning, Implementation, Prüfung und Review. Workflowprofile steuern, wann der nächste Schritt stattfinden darf. Dieser Ablaufgraph ist die vorhandene Workflow-Engine. | [Workflow-Engine und Profile](docs/README_technical.md#5-workflow-engine) |
| **Vorhandene SCM-Prüfergebnisse einordnen** | Gitea-Actions-Facts eines konkreten Runs lesend beurteilen und ihrem Prüfgegenstand zuordnen. Dieses advisory Assessment ergänzt die Nachweissicht; es startet keinen Job und erteilt keine Required- oder Mutationsauthority. | [Externe SCM-Check-Evidence](docs/README_technical.md#externe-scm-check-evidence-advisory) |
| **Integrierter Referenz-Worker** | Ein Issue in einen Plan, Änderungen im eigenen Run-Worktree und einen PR übersetzen. Planning, Implementation, Healing und Review verwenden ihre jeweiligen LLM-Aufgaben und Formatverträge. | [Issue → Plan → Code → PR](technische%20Beschreibungen/README.md) |
| **Planprüfung und Klärung** | Explizit offene Anforderungen und beweisbare Widersprüche erkennen; bei Bedarf begrenzt Rückfragen stellen und Antworten revisionsgebunden in die Planbasis aufnehmen. | [Planning](technische%20Beschreibungen/pipeline_planning.md) |
| **Healing und Patchverarbeitung** | Für unterstützte Fehler einen begrenzten Reparaturversuch durchführen; strukturierte Änderungen auf Scope, Ziel und Syntax prüfen und fehlgeschlagene Patchschritte zurückrollen. | [Implementation und Patchpfad](technische%20Beschreibungen/pipeline_issue_to_llm.md), [Evidence-Healing](technische%20Beschreibungen/pipeline_pr_gates.md) |
| **Checkpoints, Replan und Recovery** | Laufzustand und Bindungen sichern, einen Auftrag neu planen und unterstützte Finalisierung nach erneuter Bindungsprüfung fortsetzen. Das hilft, Fehler und Neustarts gezielt zu bearbeiten. | [State und Wiederaufnahme](docs/STATE_STORE.md), [Replan-Vertrag](docs/OPERATING_RULES.md#r25--re-planning-widerruft-plan-und-freigabe-explizit) |
| **SCM und externe Candidates** | Gitea-/GitHub-Adapter für Issues, Kommentare, Branches, PRs und SCM-Ereignisse nutzen. Separat erzeugte Git-Candidates können über den vorhandenen passiven Anschluss denselben gebundenen Prüfpfad nutzen. | [Adapter und Ports](docs/README_technical.md#7-adapter-katalog), [Produktgrenze](docs/adr/0678-product-boundary-and-integration-profile.md) |
| **Watch, Idempotenz und Fehlerbehandlung** | Geeignete SCM-Aufträge beobachten, wiederholte Ereignisse behandeln und fehlgeschlagene Nachrichten über die Dead-Letter-Queue untersuchen. Notifications melden vorhandene Workflowereignisse. | [Slice-Katalog](docs/README_technical.md#6-slice-katalog-31-slices), [Watch-Betriebsgrenze](docs/OPERATING_RULES.md#watch-betriebsgrenze--genau-ein-synchroner-in-process-slot) |

### Modelle, Prompts und Ressourcen passend einsetzen

| Fähigkeit | Was sie ermöglicht und wozu sie dient | Technische Vertiefung |
|---|---|---|
| **Mehrere LLM-Provider** | Adapter für Anthropic/Claude, DeepSeek, Gemini, OpenAI und OpenRouter sowie lokale Ollama-/LM-Studio-Endpunkte nutzen. Eine dateibasierte manuelle Request-/Response-Brücke ist ebenfalls vorhanden. | [Provider einrichten](docs/agents/AGENT_CONFIGURATION_REFERENCE.md#provider-einrichten-und-gezielt-wechseln) |
| **Per-Task-Routing und Fallbacks** | Provider, Modell, Timeout und Ausgabegrenze je Aufgabe konfigurieren. Explizite Fallbacks, begrenzte Retries und Circuit Breaker behandeln definierte Providerfehler. | [Effektive Route und Priorität](docs/agents/AGENT_CONFIGURATION_REFERENCE.md#configquelle-und-tatsächlich-gewählte-route) |
| **Tag-/Nacht-Routing** | Mit konfigurierten Task-Zeitfenstern, auch über Mitternacht, eine andere Provider-/Modellroute wählen. Die Zeitfenster folgen der lokalen Runtimezeit; im ausgelieferten Profil sind keine Schedules aktiv. | [Schedules](docs/agents/AGENT_CONFIGURATION_REFERENCE.md#configquelle-und-tatsächlich-gewählte-route) |
| **Rollenbezogene, editierbare Prompts** | Planning, Implementation, Review und Healing mit eigenen Systemprompts führen. Im Setup lassen sich allgemeine, provider- und modellspezifische Overrides pflegen; der Quellenindikator zeigt die tatsächlich aufgelöste Datei. | [Promptauflösung und Consumer](docs/agents/AGENT_PROMPTS_AND_INSTRUCTIONS.md), [Dashboardeditor](docs/DASHBOARD.md#schedule-und-systemprompt) |
| **Token- und Workflowbudgets** | Sichtbare Ausgabe je Call und kumulative Tokenzulassung eines Workflows getrennt begrenzen. Reservierungen berücksichtigen auch Retries und Fallbacks; Metering macht Verbrauch und Preisprojektionen sichtbar. | [Budgets](docs/README_technical.md#12-routing-schedules-und-budgets) |
| **Qualitätsmetriken und passive Evaluation** | Gebundene Gate-/Providerbeobachtungen als Score-Serie nach Task, Provider und Modell untersuchen. Evaluation berechnet diese Werte ohne zusätzlichen produktiven LLM-Aufruf; Benchmark- und Kostenhinweise helfen bei der Modellkonfiguration. | [Qualitätsbeobachtung](technische%20Beschreibungen/pipeline_evaluation.md), [Modellinformationen](docs/agents/AGENT_CONFIGURATION_REFERENCE.md) |

### Codekontext und Änderungen gezielt bearbeiten

| Fähigkeit | Was sie ermöglicht und wozu sie dient | Technische Vertiefung |
|---|---|---|
| **AST-Analyse und Code-Skeletons** | Python per AST in Klassen, Funktionen, Variablen und lokale Aufrufbezüge zerlegen. JavaScript/TypeScript nutzt den optionalen tree-sitter-Parser; Go, SQL und strukturierte Konfiguration haben begrenzte Regex-/Struktur-Builder. Signaturen und Zeilenbereiche orientieren den Worker im Projekt. | [Skeleton-Builder und Sprachumfang](technische%20Beschreibungen/pipeline_issue_to_llm.md#k7--skeleton-builders) |
| **Kontextaufbau, Suche und Dateiauswahl** | Issue-/Planpfade, Symbolreferenzen, Keyword-Grep und Architekturrollen kombinieren, um relevante Dateien und Ausschnitte bereitzustellen. Große Dateien liefern begrenzte Trefferregionen oder ein Signaturverzeichnis; gezielte SLICE-Anfragen laden Zeilen nach. | [Kontextwerkzeuge und Grenzen](technische%20Beschreibungen/pipeline_issue_to_llm.md#kontextlebenszyklus-und-werkzeuggrenzen) |
| **Scope- und Syntaxprüfung** | Änderungen gegen erlaubte und gesperrte Pfade, Contractscope und unterstützte Syntax prüfen. Python-AST und vorhandene Quality-Checks helfen, ungültige Änderungen früh zu erkennen. | [Quality-Adapter](docs/README_technical.md#7-adapter-katalog), [PR-Gates](docs/README_technical.md#9-pr-gates-13) |

Die Symbolsuche erweitert Kontext heuristisch; sie ist kein allgemeiner
semantischer Code-Abhängigkeitsgraph. Die Python-Aufrufbezüge gehören zum
Skeleton, nicht zu einer vollständigen projektweiten Callgraphanalyse. Ein
CSV-Import, CSV-Export oder eigener CSV-Auswertungspfad ist im aktuellen
Produktbestand nicht implementiert; vorhandene Daten- und Exportwege verwenden
unter anderem JSON, JSONL, SARIF und Markdown.

### Security, Privacy und Audit unterstützen

| Fähigkeit | Was sie ermöglicht und wozu sie dient | Technische Vertiefung |
|---|---|---|
| **Security-Gates und Scanneranschlüsse** | Unter anderem hinzugefügte Diffzeilen auf Secrets prüfen, Pfadrisiken behandeln und konfigurierte externe Gate-/Scanner-Ergebnisse unter ihrem Evidencevertrag einbeziehen. Die konkrete Gate-/Profilwirkung ist einsehbar. | [Security-Model](docs/README_technical.md#13-security-model), [Gates](docs/README_technical.md#9-pr-gates-13) |
| **Audit-Trail und Integritätsprüfung** | Ereignisse samt Korrelation und fachlicher Zuordnung in JSONL protokollieren; optional eine HMAC-Kette verwenden und mit `samuel audit verify` prüfen. Candidate-/SHA-/Contractbindungen machen die Herkunft einer Entscheidung untersuchbar. | [Audit](docs/README_technical.md#14-audit-trail) |
| **SARIF-Export und OWASP-Mappings** | Auditfindings als SARIF für weitere Analyse bereitstellen und passende Ereignisse mit versionierten OWASP-Risikozuordnungen erläutern. Das verbindet technische Befunde mit ihrer dokumentierten Risikoeinordnung. | [SARIF](docs/README_technical.md#14-audit-trail), [Framework-Mappings](docs/COMPLIANCE_FRAMEWORK_MAPPINGS.md) |
| **DSGVO-/Privacyhilfen** | Konfigurierbares PII-Scrubbing vor LLM-Übermittlung, explizite Anonymisierung und Retentionplanung einsetzen. Die ausgelieferte Retention arbeitet report-only; begrenzte Erkennung und Betreiberpflichten sind dokumentiert. | [Privacy und Verarbeitung](docs/DSGVO_VVT.md) |
| **AI-Act-bezogene Attribution** | Modellbeteiligung über Attribution, Git-Trailer, LLM-Telemetrie und Artikel-/Risikoklassenprojektionen sichtbar machen. Damit lassen sich technische Beiträge und Nachweise zuordnen. | [Attribution und rechtliche Einordnung](docs/AI_ACT_COMPLIANCE.md) |
| **CRA-Querverweise** | Vorhandene technische Kontrollen und Evidence-Referenzen zu Risikoanalyse, sicherer Entwicklung, Schwachstellenbehandlung, Tests und Komponenteninformationen einordnen. Die Complianceansicht zeigt die versionierten Mappingdefinitionen; ihr Nutzen liegt in der nachvollziehbaren technischen Zuordnung. | [CRA-Mapping und tatsächlicher Umfang](docs/COMPLIANCE_FRAMEWORK_MAPPINGS.md) |

### Bedienen, betreiben und erweitern

| Fähigkeit | Was sie ermöglicht und wozu sie dient | Technische Vertiefung |
|---|---|---|
| **Dashboard** | Status, Activity, Workflow/Stages, Gates/Acceptance, Probleme, Logs, Security und Compliance verfolgen. LLM-/Kosten- und Qualityansichten zeigen Routen, Calls, Verbrauch und Score-Serien; Self-Check bietet eine aktive Diagnose. | [Ansichten und reale datierte Aufnahmen](docs/DASHBOARD.md) |
| **Setup und Settings** | SCM-/Projekt-/LLM-Konfiguration, Tasks, Schedules, Prompts, Flags, Labels, DLQ und vorhandene Identityoptionen bedienen. Setup schreibt mit passender Permission; Production zeigt gespeicherte und effektive Konfiguration im eingefrorenen Modus. | [Settings](docs/DASHBOARD.md#settings-vollständig-erklärt), [Installation und Konfiguration](docs/INSTALL.md) |
| **REST-API und CLI** | Aufträge, Planfreigaben und Diagnose über definierte Bedienwege ausführen; Status, Konfiguration und Evidence über permissiongebundene HTTP-Routen abfragen. `samuel doctor`, Health und Auditprüfung erschließen den Betrieb. | [CLI](docs/README_technical.md#16-cli-reference), [API](docs/README_technical.md#18-api-endpoints) |
| **Persistenz und Betriebsdiagnose** | Authorityrecords, Intents, Checkpoints und Beobachtungen in SQLite bewahren; Workspace-Registry, Health-/Readinessprojektion und Restore-/Reconcilepfade unterstützen Neustart und Fehlersuche. | [State Store](docs/STATE_STORE.md), [Installations-/Restorevertrag](docs/INSTALL.md) |
| **Dokumentation und Wiki** | Drei Verständnistiefen, vollständigen Dokumentindex, generierte Runtime-Referenz und quellgebundene Abschnitte nutzen. Bestehende Prüfwerkzeuge erkennen Struktur-/Quelldrift; der Wiki-Build projiziert gepflegte Dokumente und veröffentlicht ausschließlich integrierten Main. | [Dokumentindex](docs/README.md), [Docs-as-Code/Wiki](docs/README_technical.md#23-deterministischer-wiki-build) |
| **Erweiterungen** | Bestehende Ports/Registries für Provider, Gates und Skeleton-Builder verwenden. Der öffentliche Extension-Datenvertrag nimmt exakt gebundene statische Dokumentinventare an; die optionale Documentation Extension ist ausgeliefert deaktiviert. | [Erweiterungspunkte](docs/README_technical.md#22-erweiterung), [Extension Contract](docs/EXTENSION_CONTRACT.md) |
| **Self-Mode** | Im dafür eingerichteten Sourcecheckout Änderungen an S.A.M.U.E.L. selbst als reguläre Candidates bearbeiten und diagnostizieren. Auch hier gelten Auftrag, Prüfungen und Freigaben. | [Self-Mode](docs/README_technical.md#11-self-mode) |

## Für wen das hilfreich ist

| Zielgruppe | Konkrete Aufgaben mit S.A.M.U.E.L. |
|---|---|
| Softwareentwicklung und Engineering | Einen Auftrag planen und bearbeiten; Candidate, Scope und Acceptance gemeinsam prüfen und Fehler einem konkreten Schritt zuordnen. |
| DevOps und Infrastruktur | Installation und wirksame Konfiguration betreiben; Läufe, Diagnose, Checkpoints und unterstützte Wiederaufnahme nachvollziehen. |
| Plattformteams | Vorhandene Producer- und Evidencepfade an einen gemeinsamen Prüfgegenstand anschließen und ihre Rechte und Profile sichtbar machen. |
| Security und DevSecOps | Kontrollwirkung, Scannerbefunde und Risiken demselben Candidate und derselben Policy zuordnen. |
| Compliance, Audit und Risikomanagement | Herkunft von Entscheidungen, Attribution und Nachweisen untersuchen sowie technische Privacyhilfen einsetzen. |
| Engineering-Leitung und technische Produktverantwortliche | Offene Kriterien, Prüfergebnisse und die Grundlage einer menschlichen Mergeentscheidung finden. |
| Unternehmen mit besonderen Nachweisanforderungen | Version, Policy, Konfiguration und Evidence einer benannten Referenzkombination zuordnen. |

Diese Aufgaben gibt es auch außerhalb regulierter Branchen. Der zusätzliche
Aufwand für Verträge, Betrieb und Nachweise muss zum Anwendungsfall passen.
[Anwendungsfälle, Alternativen und offene Nutzenbelege](docs/PRODUCT_VALUE_AND_EVIDENCE.md)
erklären Voraussetzungen, Stakeholderaufwand und Fälle, in denen eine bestehende
SCM-/CI-/Reviewtoolchain ausreicht. Vergleichbare praktische Wirksamkeits- und
Aufwandsmessungen bleiben dort ausdrücklich als offene Nachweise erkennbar.

## Ein Beispiel

### KI schreibt Code. Wer behält die Änderung bis zum Merge im Blick?

Coding-Agenten wie Claude Code, Codex oder aider können Änderungen entwerfen,
Tests ergänzen und Code für einen Pull Request vorbereiten. Das Team übernimmt
anschließend die Verantwortung: Was wurde verändert? Passt es zum Auftrag?
Welche Prüfungen tragen die Entscheidung, und was muss ein Mensch beurteilen?

Diese Arbeit ist in der Praxis sichtbar: In der
[Stack-Overflow-Entwicklerbefragung 2025](https://survey.stackoverflow.co/2025/ai#ai-tool-frustrations)
schildern Befragte zusätzliche Fehlersuche an fast richtigen KI-Lösungen.
[DORA 2025](https://dora.dev/research/2025/dora-report/) betrachtet den gesamten
Entwicklungsprozess und beschreibt KI als Verstärker vorhandener Stärken und
Schwächen. Die [Quellenauswertung mit Forschung und konkreten Praxisberichten](docs/PRODUCT_VALUE_AND_EVIDENCE.md#ki-code-im-review-und-betrieb-forschung-und-praxisberichte)
unterscheidet Befragung, beobachtete Zusammenhänge und einzelne Erfahrungen.

### Ein Arbeitstag mit mehreren Änderungen

Stellen wir uns ein Team vor, das eine Webanwendung mit REST-API, Datenbank und
angebundenen Diensten betreibt. Vier Issues stehen an:

- Eine neue API-Funktion für den Datenexport.
- Ein Fehler in der Berechtigungsprüfung.
- Eine Änderung am Datenbankschema.
- Ein dringender Bugfix an einer bestehenden Schnittstelle.

Menschen und unterschiedliche Coding-Agenten bearbeiten diese Aufträge und
bereiten Pull Requests vor. Währenddessen müssen dieselben Reviewer und
DevOps-Teams die Ergebnisse verstehen, prüfen und integrieren. Im folgenden
Beispiel begleitet S.A.M.U.E.L. den Exportauftrag; die parallelen Änderungen
kommen aus dem übrigen Teamprozess.

**Im Review geht es um den Auftrag und den ganzen Diff.** Für den Export soll
etwa gelten: Nur berechtigte Nutzer erhalten die vorgesehenen Daten, vorhandene
API-Antworten bleiben kompatibel und die vereinbarten Tests prüfen diese Fälle.
Auch bei grüner CI muss der Reviewer beurteilen, ob der Code diese Anforderungen
umsetzt und ob zusätzliche Dateien oder Abhängigkeiten zum Auftrag gehören.

**Parallele Änderungen verändern die Prüfgrundlage.** Während der Export-PR
geprüft wird, landet die Berechtigungskorrektur im gemeinsamen Branch. Oder ein
Agent verändert nach einem fehlgeschlagenen Test seinen eigenen PR noch einmal.
Das Team muss prüfen, welche Tests und Freigaben zum neuen Stand passen. SCM,
Branchschutz, Merge Queues und erneute CI-Läufe liefern dafür bereits wichtige
Bausteine.

**DevOps und Security brauchen den Zusammenhang.** CI, Tests und Scanner
liefern unterschiedliche Ergebnisse. Für den Exportauftrag muss erkennbar sein,
welcher Check verpflichtend war, welcher nur einen Hinweis lieferte und auf
welchen Code sich der Befund bezieht. Bei einem unterbrochenen Lauf hilft die
Zuordnung, den betroffenen Arbeitsschritt und seine Fehler zu finden.

**Später zählt die Entstehung der Entscheidung.** Bei einem Fehler oder einem
Audit möchte das Team wissen: Wer hat den Export beauftragt? Welcher Diff wurde
geprüft? Welche Modell- und Werkzeuginformationen wurden erfasst? Welche
Kriterien waren erfüllt, welche Freigaben lagen vor? Diese Informationen sollen
während der Arbeit zusammenpassen und anschließend auffindbar bleiben.

### Wie S.A.M.U.E.L. das Team dabei unterstützt

**Der Auftrag gibt die Richtung vor.** Das Issue enthält den gewünschten Export,
seinen erlaubten Umfang und überprüfbare Akzeptanzkriterien. Der integrierte
Referenz-Worker kann daraus einen Plan, Änderungen und Tests erstellen und den
Pull Request vorbereiten. Das aktive Workflowprofil bestimmt die erforderlichen
Freigaben. Ein eingerichteter Watchpfad kann ein mit `ready-for-agent` markiertes
Issue aufnehmen; Projektbindung, Konfiguration und Readiness gehören zum Einstieg.

**Die Prüfungen gehören zu einer bestimmten Änderung.** S.A.M.U.E.L. bindet den
Candidate – den konkreten Änderungsvorschlag – an Repository, Ausgangs- und
Änderungscommit, Acceptance Contract und Policy. Der Contract hält Auftrag und
Kriterien fest; die Policy bestimmt die Wirkung der Prüfungen. Statische
Preflights stehen vor der Ausführung kandidatenkontrollierter Acceptance-Tests.
Required-Fehler blockieren an ihrer vorgesehenen Grenze, advisory Ergebnisse
liefern Hinweise. So kann das Team unterscheiden, was tatsächlich geprüft wurde
und welche Bedeutung das Ergebnis für diesen Candidate hat.

**Bestehende Werkzeuge arbeiten weiter mit.** Git, CI/CD und Scanner behalten
ihre Aufgaben. Unterstützte Prüfergebnisse werden über ihre vorhandenen
Evidenceverträge einbezogen. Alternativ lässt sich ein extern erzeugter
Git-Candidate über den passiven Anschluss bewerten, wenn Auftrags-, Freigabe-
und Quellenbindungen passen. Dieser passive Prüfweg bleibt von der aktiven
PR-Erstellung des Referenz-Workers getrennt.

**Der Reviewer erhält eine zusammenhängende Entscheidungsgrundlage.** Der PR
verbindet den Auftrag mit dem Diff, den Akzeptanzkriterien, Gate-Ergebnissen und
den zugehörigen Commit-/Contract-/Policyinformationen. Offene MANUAL-Kriterien
benötigen ihre passenden menschlichen Nachweise. Passive Qualitätsbeobachtungen
lassen sich getrennt im Dashboard und ihren Score-Serien untersuchen. Der
Reviewer kann damit gezielt entscheiden, welche fachlichen Fragen noch offen
sind, statt Prüfergebnisse ohne Zusammenhang zusammensuchen zu müssen.

**Neue Änderungen bekommen eine passende Neubewertung.** Wenn der Agent den
Export-Diff verändert oder relevante Grundlagen wechseln, prüft der bestehende
Vertrag die Gültigkeit der zugeordneten Nachweise und Freigaben erneut. Ein
früherer grüner Lauf wird nicht ungeprüft auf einen anderen Head übertragen.
Der Mensch prüft die Änderung und entscheidet im beschriebenen Reviewweg über
den Merge. Der optionale Produkt-Auto-Merge ist standardmäßig ausgeschaltet und
hat eigene Voraussetzungen.

**Die Laufspur entsteht während der Entwicklung.** Gebundene Prüfresultate,
Entscheidungen und Auditereignisse lassen sich zum jeweiligen Auftrag und
Änderungsstand zurückverfolgen. DevOps findet Laufzustände, Konfiguration und
Fehler; Security die Befunde und ihre Kontrollwirkung; Engineering-Leitung den
Prüf- und Freigabestand. Compliance und Audit können die vorhandenen zugeordneten
Nachweise untersuchen. Diese Funktionen sind auch für ein gewöhnliches
Webentwicklungsteam nützlich.

### Vom Einstieg zur späteren Nachvollziehbarkeit

Für das Beispiel führt der praktische Weg durch sechs Schritte. Jeder Einstieg
verweist auf die vorhandene Fachanleitung für genau diese Aufgabe:

| Schritt | Was du konkret tust | Einstieg |
|---|---|---|
| **1. Einrichten** | Release installieren, Projekt/SCM/Modelle konfigurieren und Diagnose prüfen. | [Installation und Setup](docs/INSTALL.md) |
| **2. Auftrag vorbereiten** | Issue, erlaubte Änderungen und prüfbare Kriterien festhalten; Plan und nötige Freigabe verstehen. | [Referenzstrecke: Auftrag und Plan](technische%20Beschreibungen/README.md#end-to-end-ablauf-authority-und-sichtbarkeit) |
| **3. Bearbeitung starten** | Das vorbereitete Issue über `samuel run` oder den eingerichteten Watchpfad bearbeiten lassen. | [CLI: Workflow starten](docs/README_technical.md#16-cli-reference) |
| **4. Verlauf und Fehler ansehen** | Lauf, Stages, Gates und offene Kriterien im Dashboard verfolgen; Fehler dem Arbeitsschritt zuordnen. | [Dashboard: Wege nach Aufgabe](docs/DASHBOARD.md#aufgabenweg-und-wirksame-konfiguration) |
| **5. PR prüfen und mergen** | Diff, Pflichtprüfungen, offene MANUAL-Kriterien und Review zusammen beurteilen; menschlich entscheiden. | [Acceptance und Gates](technische%20Beschreibungen/pipeline_pr_gates.md) |
| **6. Später nachvollziehen** | Zugeordnete Prüfresultate und Auditspur lesen; die vorhandene Auditkette mit `samuel audit verify` prüfen. | [Audit-Trail](docs/README_technical.md#14-audit-trail) |

Bei einem expliziten Replan verlangt R25 eine neue menschliche Freigabe. Die
[Replan-Referenz](docs/README_technical.md#argumente-voraussetzungen-und-ergebnisgrenzen)
beschreibt die bekannte begrenzte Durchsetzungslücke. Die vollständige
[Referenzstrecke](technische%20Beschreibungen/README.md) erklärt außerdem
begrenztes Healing und unterstützte Wiederaufnahme.

### Softwareänderungen im Zusammenhang verstehen

Der Governance-Core verbindet Auftrag, Änderung, Prüfungen und Entscheidungen.
Der Referenz-Worker bietet einen ausführbaren Weg innerhalb dieser Architektur;
der Core kann auch einen passend gebundenen externen Candidate bewerten. Das
Team erhält damit eine gemeinsame Grundlage für Entwicklung, Review, Betrieb
und spätere Nachvollziehbarkeit.

*Trust the change, not the producer.*

<a id="was-vorhanden-ist-und-wo-die-grenzen-liegen"></a>
## Heutige Einsatzgrenzen

S.A.M.U.E.L. ist im veröffentlichten Alpha-/Referenzstadium. Für neue
Testinstallationen gilt der neueste veröffentlichte Alpha-Release mit seinem verifizierten Manifest. [Produktstatus](docs/status/CURRENT_PRODUCT_STATUS.md),
[Capability-/Wirksamkeitsmatrix](docs/CAPABILITY_MATRIX.md) und
[Versionspolitik](docs/VERSIONING.md) unterscheiden Implementierung, aktive
Konfiguration, Tests und die Reichweite realer Abnahmen. Eine erfolgreiche Installation oder grüne CI ist kein vollständiger
Golden-/D0- oder Einsatznachweis.
Wheel- und OCI-Nachweise gelten für ihre jeweilige Installation: ein OCI-Nachweis qualifiziert
keine Wheelinstallation;
`container.reference` im Manifest bindet das unveränderliche Image.

Für den heutigen Einsatz sind besonders diese Grenzen relevant:

- **Freigabe:** Score, Dashboardanzeige und Producerurteil erteilen keine
  Freigabe. MANUAL-Kriterien benötigen echte menschliche Receipts; in diesem
  Projekt bleibt der Merge menschlich. Die relevante R25-Replan-Lücke steht
  im Beispiel und in der technischen Referenz.
- **Ausführung und Integration:** Lokale Candidateausführung ist keine
  allgemeine Prozesssandbox. Passive Candidate-/SCM-Evidenceanschlüsse
  steuern keinen universellen aktiven Fremdworker. Externe Ausführung benötigt
  ihre eigene qualifizierte Bindung.
- **Betrieb:** Modellzugang, SCM-Rechte und effektive Konfiguration sind
  installationsbezogen. Tokenbudgets sind keine Geldkostengarantie;
  Checkpoints erlauben kein beliebiges Resume eines halben LLM-Aufrufs.
- **Security und Compliance:** Begrenzte Scanner-/PII-Erkennung, SARIF-Export,
  OWASP-/AI-Act-Mappings und Attribution unterstützen Prüfung und Betrieb;
  sie ersetzen keine vollständige Sicherheits- oder Rechtsabnahme. SARIF ist
  Export, kein allgemeiner Scanner-Ingest.
- **Erweiterungen und Dokumentation:** Ports und Datenverträge sind konkrete
  Anschlusswege, kein allgemeiner Pluginhost. Dokument- und Bildbindungen
  erkennen Quelldrift; fachliche Wirkung und Verständlichkeit brauchen Review.

Die verlinkten Fachreferenzen halten Einzelgrenzen und historische Evidence
vollständig erreichbar. `v2.0.0a15` bleibt historische Teilevidence ohne
vollständigen Funktions- oder D0-PASS; die
[damaligen Nachweise](docs/status/CURRENT_PRODUCT_STATUS.md) bleiben erhalten. Zielbilder bleiben im
[Produktgrenzen-ADR](docs/adr/0678-product-boundary-and-integration-profile.md)
als Zielbilder erkennbar.

## Zusammenspiel mit anderen Werkzeugen

Die folgenden Einordnungen beschreiben Aufgaben, keine allgemeine
Rangfolge. Funktionen können sich überschneiden. Ein Werkzeug kann eigene
Policies und Freigaben besitzen; seine Nennung bedeutet noch keinen aktiven
S.A.M.U.E.L.-Adapter.

| Werkzeugart | Typischer dokumentierter Schwerpunkt | Einordnung zu S.A.M.U.E.L. |
|---|---|---|
| [aider](https://aider.chat/docs/index.html) | Terminalgestützte Zusammenarbeit am Code, einschließlich [Lint-/Testintegration](https://aider.chat/docs/usage/lint-test.html). | Kann eine Änderung erzeugen und prüfen; die zusätzliche Frage ist, wie Auftrag, Candidate und Evidence im Teamprozess zusammengebunden werden. |
| [Claude Code](https://code.claude.com/docs/en/overview) | Agentische Codearbeit mit Datei-, Befehls- und Git-/PR-Werkzeugen sowie eigenen Integrationsmöglichkeiten. | Überlappung mit Workeraufgaben; keine Behauptung fehlender eigener Steuerung oder eines universellen aktiven Anschlusses. |
| [Codex](https://developers.openai.com/api/docs/guides/code-generation) | Schreiben, Review und Debugging von Code; der [Harness](https://developers.openai.com/blog/codex-as-a-platform) besitzt auch Werkzeug-, Zustands-, Sandbox- und Approvalmechanismen. | Coding-Agent und mögliche vorhandene Prozessbausteine; S.A.M.U.E.L. muss seinen zusätzlichen Nutzen am konkreten gebundenen Änderungsprozess zeigen. |
| [LangGraph](https://docs.langchain.com/oss/python/langgraph/overview) | Agentenorchestrierung mit dauerhafter Ausführung, Persistenz und menschlichen Eingriffen. | Allgemeine Orchestrierung; S.A.M.U.E.L. implementiert einen konkreten Änderungs-, Evidence- und Entscheidungsvertrag. |
| [CI/CD, etwa GitHub Actions](https://docs.github.com/en/actions/get-started/understand-github-actions) | Build-, Test- und Deploymentabläufe mit konfigurierbaren Regeln. | Ausführungs-/Integrationsinfrastruktur; ein Ergebnis muss für den jeweiligen S.A.M.U.E.L.-Claim passend gebunden sein. |
| [Scanner, etwa CodeQL](https://docs.github.com/en/code-security/concepts/code-scanning/code-scanning) | Security-/Fehleranalyse und Befunde, auch über SARIF. | Fachliche Evidence; ihre Annahme, Reichweite und Wirkung folgen dem konkreten Vertrag. |
| [Policywerkzeuge, etwa OPA](https://www.openpolicyagent.org/docs) | Strukturierte Eingaben mit Rego auswerten; die Anwendung setzt die Entscheidung durch. | Eigene Gate-/Policyverträge erfüllen einen konkreten Zweck; eine vorhandene Policyintegration kann bereits ausreichen. Keine aktive OPA-Anbindung zugesagt. |
| [Provenance, etwa in-toto](https://in-toto.io/) und [SLSA v1.2](https://slsa.dev/spec/v1.2/verifying-artifacts) | Herkunft, Schritte und erwartete Herstellungsbedingungen überprüfen. | Vergleichbare Nachweisbindungen ersetzen keine fachliche Acceptance; kein aktiver Anschluss oder erreichtes SLSA-Level aus dieser Nennung. |

Der [Vergleich konkreter Aufgaben](docs/PRODUCT_VALUE_AND_EVIDENCE.md)
bezieht bestehende Branchschutz-/Reviewregeln und Fälle ohne ausreichenden
Zusatznutzen ein. Er ist kein ausgeführter Vergleichsbenchmark.

Primärquellenstand: 11.10.2026. Keine Preis-,
Benchmark-, Integrations- oder Sicherheitsüberlegenheit wird daraus abgeleitet.

## Einstieg und Vertiefung

- **Installieren und betreiben:** [INSTALL](docs/INSTALL.md), einschließlich
  offiziellem OCI-Weg, Projektbindung, Konfiguration und Restoregrenzen.
- **Architektur verstehen:** [Technischer Überblick](docs/TECHNICAL_OVERVIEW.md).
- **Eine Funktion nachvollziehen:** [Advanced-Referenz](docs/README_technical.md),
  [Dashboard](docs/DASHBOARD.md), [State/Recovery](docs/STATE_STORE.md) und
  [vollständiger Dokumentbestand](docs/README.md).
- **Beitragen:** [CONTRIBUTING](CONTRIBUTING.md). Dokumentationsrelevante
  Änderungen pflegen Aussagen, Quellenbindungen und Prüfungen im selben PR;
  auch neue Funktionen ohne bisheriges Binding und geänderte fachliche
  Wirkungen werden geprüft. Automatische Strukturhinweise ersetzen diesen
  Review nicht.

Für einen Entwicklungs-/Evaluationscheckout beginnt die Installation so:

```bash
git clone <repo-url> samuel && cd samuel
release_tag='<tag aus dem verifizierten neuesten Release-Manifest>'
git checkout "$release_tag"
./install.sh
```

Der manifestgebundene Wheel-/OCI-Betriebsweg und seine Voraussetzungen stehen
in [INSTALL](docs/INSTALL.md); dieser Checkout ist kein neuer Qualificationnachweis.

Der Name S.A.M.U.E.L. ist zugleich eine persönliche Hommage des
Projektgründers an seinen Sohn Samuel und ein technisches Wortspiel, das dem
Projekt von Anfang an seinen Namen gegeben hat.

Die Langform des Namens lautet „Sicheres Autonomes Mehrschichtiges
Ueberwachungs- und Entwicklungs-Logiksystem“. Autonomie bezeichnet den
optionalen Workerablauf und ist keine Sicherheits- oder Compliancegarantie.

## Frühere Detailabschnitte finden

Die bisherigen Direktlinks bleiben gültig und führen zu den vollständigen
Fachbeschreibungen. Produktzweck und aktueller Nachweisstatus stehen oben.

| Bisheriger Einstieg | Maßgebliche Detailbeschreibung |
|---|---|
| <a id="wie-ein-issue-durch-samuel-laeuft"></a>Wie ein Issue durch S.A.M.U.E.L. laeuft | [Referenzablauf und getrennte Authorities](technische%20Beschreibungen/README.md) |
| <a id="1-planning--issue--plan"></a>1. Planning — Issue → Plan | [Planning P1–P10](technische%20Beschreibungen/pipeline_planning.md) |
| <a id="2-implementation--plan--code"></a>2. Implementation — Plan → Code | [Kontext und Implementation K1–K16](technische%20Beschreibungen/pipeline_issue_to_llm.md) |
| <a id="3-pr-gates--candidate--freigabeentscheidung"></a>3. PR-Gates — Candidate → Freigabeentscheidung | [Subject, Preflight und Acceptance](technische%20Beschreibungen/pipeline_pr_gates.md) |
| <a id="4-evaluation--gebundene-qualitätsbeobachtung"></a>4. Evaluation — gebundene Qualitätsbeobachtung | [Passive, nicht bindende Qualitätsbeobachtung](technische%20Beschreibungen/pipeline_evaluation.md) |
| <a id="querschnittsmechanismen"></a>Querschnittsmechanismen | [Security, Audit und Resilienz](docs/README_technical.md#13-security-model) |
| <a id="funktions-uebersicht"></a>Funktions-Uebersicht | [Vollständige Funktionswege](docs/README.md) |
| <a id="issue-zu-pr-pipeline"></a>Issue-zu-PR-Pipeline | [Referenz-Worker](technische%20Beschreibungen/README.md) |
| <a id="multi-provider-llm"></a>Multi-Provider-LLM | [Provider, Fallback und effektive Konfiguration](docs/agents/AGENT_CONFIGURATION_REFERENCE.md) |
| <a id="per-task-routing-mit-tagnacht-schedule"></a>Per-Task-Routing mit Tag/Nacht-Schedule | [Taskrouting und deaktivierter Standard-Schedule](docs/agents/AGENT_CONFIGURATION_REFERENCE.md) |
| <a id="workflow-engine"></a>Workflow-Engine | [Workflows und Freigabegrenzen](docs/README_technical.md#5-workflow-engine) |
| <a id="pr-gate-registry"></a>PR-Gate-Registry | [Gatewirkung und bekannte Grenzen](docs/CAPABILITY_MATRIX.md) |
| <a id="llm-code-kennzeichnung-eu-ai-act-art-50"></a>LLM-Code-Kennzeichnung (EU-AI-Act Art. 50) | [Technische Attribution und Rechtsgrenzen](docs/AI_ACT_COMPLIANCE.md) |
| <a id="llm-qualitaetsmetriken"></a>LLM-Qualitaetsmetriken | [Messreihen und Aussagegrenzen](technische%20Beschreibungen/pipeline_evaluation.md) |
| <a id="akzeptanzkriterien-verifier"></a>Akzeptanzkriterien-Verifier | [Kriterien und gebundene Evidence](docs/README_technical.md#10-akzeptanzkriterien-verifier) |
| <a id="evidence-healing"></a>Evidence-Healing | [Begrenzter Korrekturversuch](technische%20Beschreibungen/pipeline_pr_gates.md) |
| <a id="self-mode--selbst-anpassung-an-die-umgebung"></a>Self-Mode — Selbst-Anpassung an die Umgebung | [Self-Mode und reguläre Freigaben](docs/README_technical.md#11-self-mode) |
| <a id="web-dashboard"></a>Web-Dashboard | [Dashboard, Settings und Betriebsmodus](docs/DASHBOARD.md) |
| <a id="historische-dashboardbilder"></a>Historische Dashboardbilder | [Historische Bilder und Provenienz](docs/DASHBOARD.md#historische-dashboardbilder) |
| <a id="rest-api"></a>REST-API | [Routen, Rechte und Antwortsemantik](docs/README_technical.md#18-api-endpoints) |
| <a id="audit-trail-mit-owasp--und-ai-act-mapping"></a>Audit-Trail mit OWASP- und AI-Act-Mapping | [Audit, HMAC, SARIF und advisory Mappings](docs/README_technical.md#14-audit-trail) |
| <a id="pii-scrubbing-und-dsgvo-unterstützung"></a>PII-Scrubbing und DSGVO-Unterstützung | [Technische Privacyhilfen und Betreibervertrag](docs/DSGVO_VVT.md) |
| <a id="token-budgetpfade"></a>Token-Budgetpfade | [Call- und Workflowbudget, keine Geldkostengarantie](docs/README_technical.md#12-routing-schedules-und-budgets) |
| <a id="system-prompt-konfiguration"></a>System-Prompt-Konfiguration | [Tatsächliche Consumer und wirksame Promptauflösung](docs/agents/AGENT_PROMPTS_AND_INSTRUCTIONS.md) |
| <a id="schnellstart"></a>Schnellstart | [Installation und Einstieg](docs/INSTALL.md) |
| <a id="cli-in-kurzform"></a>CLI in Kurzform | [Vollständige CLI](docs/README_technical.md#16-cli-reference) |
| <a id="weitere-dokumentation"></a>Weitere Dokumentation | [Vollständiger Bestand und Geltung](docs/README.md) |

## Lizenz

Der gesamte Inhalt dieses Repositorys steht unter der **Apache License 2.0**. Der
vollständige, maßgebliche Lizenztext liegt in [`LICENSE`](LICENSE); die
Paketmetadaten spiegeln ihn als SPDX-Ausdruck `Apache-2.0`.

Es gibt keine separate Entitlement-Lizenz oder Premium-Laufzeitstufe.
Die gültige [Entscheidung und ihre Umsetzung](docs/SAMUEL_DESIGN_DECISIONS.md#e6--premium-entfernen-in-zwei-getrennten-schritten)
bleiben nachvollziehbar dokumentiert.
