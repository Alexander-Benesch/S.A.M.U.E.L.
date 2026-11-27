# Agent Prompts and Instructions

Historische Basis des Consumerinventars: `main@b59b1fc3def41ce73fef1cf29841a2e6ffbe8db7` (10.10.2026).
Promptkonfiguration, Laufbindung aus #878 und sichere Dateizugriffe sind
gegen den a34-Quellstand `cff727fe9b8dd8e9aea3b9e6f46fa5644faec9f4` abgeglichen. Productauthority besitzen nur versionierter Code,
ausgelieferte Config und akzeptierte Vertraege. Lokale Handoff-, Qualification-
oder Coding-Agent-Anweisungen sind Operatorhilfe und keine Runtimeauthority.

## Promptinventar

| Datei | shipped Taskbindung | Consumer-/Formatvertrag |
|---|---|---|
| `samuel/core/prompts/planner.md` | `planning` | Planlayout, kanonischer Scope und Acceptance-Contract; Parser und Precheck in Planning |
| `senior_python.md` | `implementation` | strukturierte Patchoperationen; Implementation-Parser, Scope-/Syntax-/Riskchecks |
| `reviewer.md` | `review` | genau ein gebundenes Review-JSON; `review_contract.py` validiert closed schema und Bindings |
| `healer.md` | `healing` | genau ein begrenzter gebundener Reparaturversuch; Candidate-/Contractbindung bleibt |
| `log_analyst.md` | in `config/llm/defaults.json` fuer `evaluation` konfiguriert, aber derzeit kein produktiver LLM-Consumer im `EvaluationHandler` | Library-/Routing-Konfiguration; Score- und Gate-Observation bleiben deterministisch, keine Mergeauthority |
| `analyst.md` | ungebundene Librarydatei | verfuegbar fuer explizite Operatorprofile, derzeit keine shipped Taskbindung |
| `docs_writer.md` | ungebundene Librarydatei | verfuegbar fuer explizite Operatorprofile, derzeit keine shipped Taskbindung |

Prompttexte werden hier nicht dupliziert. Quelle, Digest und effektive Auswahl
muessen aus dem exakten Config-/Productstand ermittelt werden.

## Aufloesung

`system_prompt_by_provider` kann zuerst den Dateinamen fuer den aktiven
Provider waehlen. Danach gilt die feste Reihenfolge:

1. `config/llm/prompts/model/<sanitized-model>/<name>`;
2. `config/llm/prompts/provider/<sanitized-provider>/<name>`;
3. `config/llm/prompts/<name>`;
4. Package-Default `samuel/core/prompts/<name>`.

Provider-/Modellteile werden auf ein sicheres Pfadsegment reduziert. Die
Kaskade überspringt fehlende, nicht lesbare und nicht als UTF-8 decodierbare
Dateien; der Dashboard-Quellenindikator folgt derselben lesbaren Auswahl.
Fehlende optionale Override-Dateien und -Verzeichnisse sind bei Kaskade,
Scopeansicht und Libraryliste normal und erzeugen keine Warnung. Tatsächliche Lese-, UTF-8- oder Pfadsicherheitsprobleme bleiben
Warnungen, auch wenn eine niedrigere Quelle erfolgreich geladen wird. In
Probleme/Logs werden Meldungen des Promptdateiresolvers als
„Promptkonfiguration prüfen“ erklärt. Die technischen Details und effektive
Quelle grenzen den Befund ein; das Ergebnis der LLM-Aufgabe steht im eigenen
Runstatus.
Eine explizite Scope-Abfrage liefert dagegen nur diesen Operatorlayer, ohne
Fallback auf andere Profile oder das Package. Fehlt dort eine lesbare Datei,
sind Inhalt und Quellenindikator leer bzw. `none`. Fehlt in der gesamten
Kaskade ein lesbarer Prompt, wird dies sichtbar geloggt und als leer geliefert;
der jeweilige Task-/Guardvertrag entscheidet danach fail-closed. Promptdateien werden im bestehenden Dashboard-Konfigurationsmodus als Entwurf
bearbeitet und ausdrücklich aktiviert. Der Editor gibt Eingabe und Schreibaktionen
erst nach erfolgreichem Laden der ausgewählten Ebene frei. Alte Antworten nach
Ebenen-/Ansichtswechsel oder Schließen ersetzen keine aktuelle Eingabe; Ladefehler
lassen die Bearbeitung gesperrt. Auch laufende Save-/Reset-/Referenzaktionen sperren
die Eingaben bis zur Antwort; eine Ablehnung erhält den Text, und Antworten eines
vorherigen Dialogs verändern keinen neu geöffneten Editor. Offene oder wartende Vorgänge verhindern
seinen Einstieg. Direkte alte Schreibendpunkte bleiben auf die Erstinstallation
beschränkt; gespeicherte Änderungen werden nicht heimlich hot geladen.

## Dateinamen und sichere Operatoroverrides

Ein Promptname ist ein einzelner nicht leerer `.md`-Basename. Absolute Pfade,
Separatoren, Traversal und Steuerzeichen werden von derselben Validierung in
Config, Task-/Scheduleeditor und Promptdateioperationen abgewiesen. Unterhalb
der expliziten Configwurzel werden Komponenten descriptorrelativ ohne
Symlinkfolgen geöffnet; nur reguläre UTF-8-Dateien sind Promptinput.
Schreiben verwendet exklusives privates Staging und Rename; Delete entfernt
den gewählten Operatoroverride und gibt die niedrigere Quelle frei.
Configwurzel und Paketinstallation bleiben vertrauenswürdige Operatorinputs.
Eine gemeinsame Prüfung vor Lesen, Ersetzen und Löschen verlangt außerdem
einen normalisierten Zielpfad innerhalb der Wurzel einschließlich
Verzeichnisgrenze und gibt nur den validierten Dateinamen für den
deskriptorrelativen Zugriff zurück. Sie folgt keinen Symlinks; der bestehende
No-Follow-Verzeichnisdurchlauf bleibt erforderlich. Gültige Promptnamen und
die Auflösungskaskade ändern sich dadurch nicht.
Fehlende sichere Plattformoperationen werden nicht durch einen unsicheren
Fallback ersetzt. Grenzen und API: [technische Referenz](../README_technical.md#prompt-dateigrenze).

## Dynamische Runtimeanteile

Die Handler ergaenzen Issue/Plan, gebundene Source-/Base-/Candidateidentitaet,
Repositorykontext, Runner- und Selectorgrammar, Retrydiagnosen,
Acceptance-/Reviewbindings und Scope-/Riskmarker. Diese Teile gehoeren zum
effektiven Prompt und koennen nicht allein durch den statischen Markdownprompt
bewertet werden. Planning besitzt genau den vertraglich vorgesehenen
Contractretry; Implementation besitzt begrenzte Patch-/Slice-Runden; Healing
bleibt auf einen gebundenen Versuch begrenzt. Provider-Transportretry ist davon
getrennt.

Seit #880 schärfen Paketplanner und Laufzeitanweisung die Auswahl der
Acceptance-Prüftypen: automatisch prüfbare Eigenschaften automatisch,
MANUAL mit konkreter menschlicher Entscheidung und Begründung. Der vorhandene
Retry erhält dieselbe Anleitung. Resolver, Operatoroverrides, Parser und
Freigabeauthority bleiben unverändert; die Anleitung ist kein semantischer
Blocker. [Auswahlregel und Grenzen](../README_technical.md#auswahl-automatischer-und-manueller-kriterien-880).

## Arbeitsanweisungen im Checkout

Der Coding-Agent-Einstieg steht in
[`.claude/CLAUDE.md`](../../.claude/CLAUDE.md#vor-der-ersten-mutation), mit
Verweis aus `CONTRIBUTING.md`. Diese Entwicklungsanweisungen sind von den
oben beschriebenen Product-Runtime-Rollen getrennt.

Im Repository existiert kein `AGENTS.md`, keine Cursor-Regel und keine
versionierte Copilot-Instructions-Datei. `CONTRIBUTING.md`,
`docs/OPERATING_RULES.md`, Security-/Release-/Qualification-Vertraege und die
CI sind die versionierte Arbeitsgrundlage. Lokale Dateien wie
`SAMUEL_WORKING_DECISIONS_v8.md`, Challengepakete und Handoffs sind
Provenienz/Operatorhilfe und werden ueber `docs/audits/INDEX.md` klassifiziert.

Die folgende Zuordnung erklärt die vorhandenen Zuständigkeiten; sie ersetzt
keine der verlinkten Quellen und keinen Issueauftrag.

| Quelle | Zuständigkeit und tatsächlicher Leser/Consumer |
|---|---|
| [CONTRIBUTING.md](../../CONTRIBUTING.md#documentation-acceptance) | Beitragsworkflow und Dokumentationsabnahme für Menschen und Coding-Agenten; notwendige Updates im verursachenden PR, begründeter Verzicht im bestehenden Nachweis. |
| [.claude/CLAUDE.md](../../.claude/CLAUDE.md) | Versionierter Coding-Agent-Einstieg für diesen Checkout; verweist auf Beitragsworkflow, fachliche Verträge und Prüfungen. Ob ein externes Werkzeug ihn automatisch lädt, hängt von dessen tatsächlichem Kontext ab. |
| [Operating Rules](../OPERATING_RULES.md) und angenommene [ADRs](../adr/README.md) | Normative Betriebs-/Entwicklungs- und Architekturentscheidungen im jeweiligen Geltungsbereich; der [Engineering Workflow](../governance/CURRENT_ENGINEERING_WORKFLOW.md) ist ihr erklärender Index. |
| [MANIFESTO.md](../../MANIFESTO.md) | Projekthese und Zielrichtung für Menschen und explizit beauftragte Coding-Agenten; laut eigenem Geltungsbereich keine Runtime-Spezifikation, Policy oder Compliance-Evidence. |
| [Übergabeprompt](../PRODUCT_BOUNDARY_HANDOVER_PROMPT.md) | Explizit in einen Arbeitschat zu übernehmende Operatorhilfe; Quellenlektüre und Grenzen für diesen Arbeitsauftrag, kein ausgelieferter Taskprompt. |
| [Audit-/Workbookindex](../audits/INDEX.md) | Disposition historischer und teilweise noch offener Arbeitsunterlagen. `SAMUEL_WORKING_DECISIONS_v8.md` bleibt `PARTIAL` mit Originaldigest und Restissues; die Zusammenfassung ersetzt weder Originalevidence noch aktuelle Regeln. |
| Packageprompts, Taskconfig und Handlerkontext | Tatsächliche Product-LLM-Quellen nach dem oben beschriebenen Resolver und den unten benannten Consumern; ihre wirksame Auswahl ist pro Run gesondert nachzuweisen. |

Für eine Coding-Agent-Lektüre werden die tatsächlich gelesenen Quellen und
ihr Commit/Digest im vorhandenen Issue-/PR-Nachweis festgehalten. Eine dort
genannte Datei ist keine automatische Product-LLM-Injektion: Der
Promptresolver lädt benannte Promptdateien, die Handler ergänzen ihren
Taskkontext. Ein Manifest-/Workbook-/CLAUDE-Usage-Claim benötigt den konkreten
Consumer und eine gebundene Laufzeitevidence. Fehlende Usage-Evidence bleibt
`UNKNOWN`. Für produktinterne Anpassungen gilt die unten beschriebene Laufbindung aus #878.

Die historische Quellenlektüre begründete keine Runtimeänderung. #878 ergänzt die unten beschriebene Konfiguration und Bindung; Parser und Freigaben bleiben Codeverträge.

## Verifizierte Autoritaets- und Retrygrenzen

Die sieben Dateien unter `samuel/core/prompts/` sind Package-Guidance. Die
fuenf ausgelieferten Task-Konfigurationen und ihre Defaults stehen in
`AGENT_CONFIGURATION_REFERENCE.md`; `analyst.md` und `docs_writer.md`
sind derzeit nicht in `config/llm/defaults.json::tasks` referenziert.
`samuel/adapters/llm/factory.py` baut fuer Task-Overrides eigene Providerketten
und aktiviert einen Schedule-Wrapper nur, wenn mindestens ein Task ein
`schedule`-Objekt besitzt. Das shipped Profil besitzt keines.

`samuel/adapters/llm/prompts.py` und die Task-/Handler-Tests pruefen
Provider-/Modell-/Generic-/Package-Aufloesung und sichere Pfadsegmente.
Planning, Implementation, Review und Healing fuegen ihre jeweiligen
LLM-Laufzeitdaten hinzu. Evaluation konsumiert gebundene Observations ohne
produktiven LLM-Prompt. Der statische Package-Text alleine kann weder
Planapproval noch Candidate-, Gate-, Review- oder Mergeauthority herstellen.
Transportretry (shipped hoechstens drei Versuche) ist von fachlichem
Plan-Contract-Retry, begrenzten Implementation-Runden und einem gebundenen
Healingversuch getrennt. Erschoepfung ist ein sichtbarer Fehler, kein
Fallback-PASS. Fuer heutige Parser-/Consumer-Details bleiben der Code, die
ausgefuehrten Regressionen und `README_technical.md` die pruefbaren Quellen.


## Vorhandene Operatorprofile nutzen

Im Konfigurationstab **Konfiguration bearbeiten** wählen. Der bestehende
Leerlaufguard verlangt abgeschlossene Vorgänge, auch wenn ein LLM gerade auf
eine Freigabe wartet. Im Taskeditor öffnet **Edit** den Promptentwurf; `generic`,
`provider:<name>` und `model:<id>` wählen die vorhandene Ebene. Eigene Dateinamen
bleiben über `system_prompt` und `system_prompt_by_provider` zuweisbar.
Speichern im Editor verändert zunächst nur den Entwurf. Die Vorschau zeigt alle
Task-/Zeitfenster-/Fallbackrouten mit Quelle, Prüfsumme und Klassifikation;
**Übernehmen und Betrieb fortsetzen** aktiviert den vorbereiteten Adaptergraphen.
**Verwerfen** beziehungsweise **Vorherigen Stand wiederherstellen** verwenden
die bestehende dauerhafte Konfigurationssitzung. Es entsteht kein Profildienst.

Anpassbar sind Erklärungssprache, Arbeitsstil, Qualitätshinweise und Hinweise
für Modelle oder Worker. Technische Feldnamen, Acceptance-Typen, Patch-/Review-
schema, Scope-/Pfadregeln, Gates und Freigabeauthority bleiben durch die
Consumer im Code geschützt. Die Prosa kann widersprechen; ihre Antworten
müssen trotzdem die vorhandenen Validatoren passieren. Es gibt keinen
semantischen Nachweis, dass frei formulierte Guidance geeignet ist.
Workerhinweise erzeugen keinen Execution-Adapter und qualifizieren keine
Isolationsgrenze. Sprache/Worker erhalten keine zusätzliche Resolverebene.

### Referenz, Custom und Laufbindung

`reference` bezeichnet die unveränderte ausgelieferte Task-/Promptzuordnung
mit Packagequelle. Andere Quellen, Dateizuordnungen oder Providerzuordnungen
sind `custom`. Beides ist **kein automatischer Qualitätsnachweis**;
`qualification: not_established` übernimmt keinen Goldenclaim. Technische
Validierung erlaubt die Aktivierung eigener Prompts ohne verpflichtenden
LLM-Probelauf. Verbindungstest und Modell-/Profilqualität sind verschiedene
Nachweise. Reale Rollenproben bleiben Teil der gebündelten Live-Abnahme.

Bei neuer Planung speichert der vorhandene Autoritätszustand ein Manifest der
vorbereiteten Task-, Provider-, Modell-, Zeitfenster- und Fallbackkombinationen,
Quellen, Inhaltsprüfsummen, Vertragsidentität und Bindungszeit. Bestehende
Schedules/Fallbacks dürfen innerhalb dieses Manifests wechseln. Nach Neustart
muss der geladene Graph zur gespeicherten Laufbindung passen. Abweichung oder
fehlende historische Bindung sperrt den nächsten LLM-Aufruf mit
`prompt_binding_mismatch`: bisherigen Stand wiederherstellen oder Versuch
beenden und neu planen. Ein alter Fehlversuch wird dadurch nicht repariert.

Pro physischem Aufruf erfasst der vorhandene Meteringpfad die tatsächliche
Quelle und `effective_messages_sha256` nach Promptzusammensetzung; dynamische
Handleranweisungen sind eingeschlossen. Eine bereits vom Aufrufer gelieferte
Systemnachricht behält Vorrang und wird als `caller/custom` ausgewiesen.
Erfolgreiche Antworten tragen diese Metadaten in `LLMCallCompleted`, Fehler im
bestehenden AuditEvent mit `action: llm_call_failed`. Prompttexte werden nicht
zusätzlich ins Audit kopiert. Die Review-eigene Promptprüfsumme behält ihre
bisherige Bedeutung. `samuel-prompt-contract/1` identifiziert diesen Vertrag;
Änderungen seiner Semantik benötigen eine neue Vertragsversion.

**Override entfernen** gibt die nächstniedrigere Quelle frei; das muss noch
nicht das Package sein. **Referenz für Aufgabe wiederherstellen** setzt die
Task-/Schedule-Promptzuordnung zurück und entfernt Overrides für deren
Referenzdatei. Das kann andere Tasks mit derselben Datei betreffen; die
Vorschau zeigt die Routen vor Übernahme. Laufende Vorgänge erhalten keine neue
Bindung. Frühere Nachweise bleiben ihrem ursprünglichen Stand zugeordnet.
