# Entwicklungsproblem, Nutzen und offene Nachweise

[Produkt](../README.md) · [Technischer Überblick](TECHNICAL_OVERVIEW.md) · [Dokumentwege](README.md)

S.A.M.U.E.L. adressiert ein konkretes Koordinationsproblem: Auftrag, Änderung,
Prüfergebnis und Entscheidung müssen zum selben Gegenstand gehören. Der Core
bindet diese Informationen; der mitgelieferte Referenz-Worker kann zusätzlich
Änderungen erzeugen. Ob diese Kombination einem bestimmten Team genug Arbeit
oder Risiko erspart, um ihren Betriebsaufwand zu rechtfertigen, ist **offen**.
Ein implementierter Kontrollpfad belegt noch keinen wirtschaftlichen Nutzen.

Diese Untersuchung trennt lokale Produktquellen von externer Forschung.
Produktbasis ist der integrierte Stand `8d06763ff5f00e49eb6e14d845108330a945c06c`;
der fortgeschriebene Document Contract bindet die maßgeblichen Quellen.
Externe Quellen wurden am **11.10.2026** geprüft. Ihre Ergebnisse betreffen
jeweils die untersuchten Werkzeuge und Populationen, nicht S.A.M.U.E.L.

## Welches heutige Problem wird bearbeitet?

Die Beispiele sind prüfbare Anwendungsfälle, keine Behauptung neu ausgeführter
Kundenläufe. Die [Capabilitymatrix](CAPABILITY_MATRIX.md) enthält die konkreten
Kontrollquellen, Regressionen und getrennten Qualificationgrenzen.

| Situation und betroffene Rolle | Bereits vorhandene Lösung | Zusätzlicher technischer Beitrag von S.A.M.U.E.L. | Was als Nutzen noch zu messen ist |
|---|---|---|---|
| Ein Reviewer erhält einen grünen Check, danach verändert sich der PR-Head. | SCM-Branchschutz, an Commits gebundene CI-Checks und erneutes Review. | Subjectbindung verbindet Repository, Base/Head, Acceptance Contract und Policy; passende Evidence muss dieselbe Bindung erfüllen. [Prüfpfad](README_technical.md#9-pr-gates-13). | Weniger übersehene Fehlzuordnungen oder kürzere Reviewzeit gegenüber einem gut konfigurierten bestehenden Prozess: **UNKNOWN**. |
| Ein Entwickler erfüllt Tests, während ein fachliches MANUAL-Kriterium offenbleibt. | Issuevorlage, Checkliste, Reviewfreigabe und organisatorische Abnahme. | Kriteriumsweise Verifikation trennt maschinelle Nachweise von menschlichen Receipts. [Acceptance](README_technical.md#10-akzeptanzkriterien-verifier). | Weniger vergessene Kriterien oder Nacharbeit: **UNKNOWN**; unpräzise Kriterien werden nicht automatisch fachlich richtig. |
| Ein Plattformteam übernimmt Ergebnisse eines externen Producers. | CI-Artefakte, Signaturen, Provenanceprüfung und projektspezifische Integrationsskripte. | Passive Candidate-Einreichung nutzt den gebundenen Prüfpfad; externe SCM-Facts werden nur im vorhandenen advisory Assessment bewertet. [Integrationsgrenzen](README_technical.md#externe-scm-check-evidence-advisory). | Weniger Integrations-/Pflegeaufwand: **UNKNOWN**. Kein universeller Workerhost, kein allgemeiner Scanner-Ingest, keine SLSA-Zertifizierung. |
| Security oder Audit muss eine Entscheidung später nachvollziehen. | SCM-/CI-Historie, Auditlogs und bestehende Policy-/Provenancewerkzeuge. | Evidence-, Policy- und Subjectbezug sowie Auditspur erklären, worauf ein konkretes Ergebnis beruht. [Audit](README_technical.md#14-audit-trail). | Zeit bis zur belastbaren Rekonstruktion, Vollständigkeit und Aufbewahrung im realen Betrieb: **UNKNOWN**. Ein Mapping ist keine Rechtskonformität. |
| Engineering betreibt wiederholte agentische Änderungsversuche. | Coding-Agent, CI und Review mit bestehenden Budget-/Zugriffsregeln. | Referenzpipeline mit Plan-/Patchgrenzen, begrenztem Healing und persistenter Tokenzulassung. [Pipeline](../technische%20Beschreibungen/README.md), [Budget](README_technical.md#12-routing-schedules-und-budgets). | End-to-End-Durchlaufzeit, Fehler-/Abbruchrate und Gesamtkosten: **UNKNOWN**. Tokenlimits sind keine Geldkostengarantie; Modellqualität bleibt extern. |

Die Aufgabe existiert auch bei manuell geschriebenem Code. Ein LLM ist keine
Voraussetzung dafür, Nachweise einem Candidate zuzuordnen. Gleichzeitig lösen
SCM, CI, Policy- und Provenancewerkzeuge bereits wesentliche Teilprobleme.
Der beanspruchte Beitrag ist deren **konkrete vertragliche Zusammenführung**
im vorhandenen Produktpfad. Ein Alleinstellungsmerkmal oder ein kausaler
Mehrwert gegenüber einer vergleichbar eingerichteten Toolchain ist nicht belegt.

## Zielgruppen: Aufgaben, Aufwand und Grenzen

Die folgende Zuordnung beschreibt, welche vorhandenen Informationen eine Rolle
nutzen kann. Sie belegt keine gemessene Zeitersparnis oder Risikoreduktion.
Die [Funktionsübersicht](TECHNICAL_OVERVIEW.md) erschließt die tatsächlichen Wege;
Controls und Referenzqualification bleiben in der Capabilitymatrix maßgeblich.

| Rolle und konkrete Aufgabe | Nutzbarer Produktpfad und Beispiel | Voraussetzungen, Aufwand und Grenze |
|---|---|---|
| **Entwickler:** Eine beauftragte Änderung fachlich fertigstellen. | Subject und kriteriumsweise Acceptance zeigen, auf welchen Candidate sich ein Test bezieht und welches MANUAL-Kriterium offen ist. [Acceptance](README_technical.md#10-akzeptanzkriterien-verifier). | Aussagekräftige Kriterien, passende Verifier und Review pflegen. Der Referenz-Worker ist optional; eigener Code ist über den vorhandenen passiven Pfad möglich. Ein grüner Test ersetzt kein menschliches Kriterium. |
| **DevOps:** Einen fehlgeschlagenen oder unterbrochenen Lauf untersuchen. | Dashboard, State und Audit helfen, gespeicherte Ergebnisse, Bindungen und zulässige Wiederaufnahme zu unterscheiden. [Betrieb](INSTALL.md), [State](STATE_STORE.md). | Installation, wirksame Konfiguration, Rechte, Backup und Reconciliation betreiben. Runtime-State, Workspace-Registry und Worktrees sind getrennt; kein allgemeines Fortsetzen eines halben Modellaufrufs. |
| **Plattformteams:** Ergebnisse unterschiedlicher Producer einordnen. | Passive Git-Candidates durchlaufen den vorhandenen gebundenen Prüfpfad; Gitea-Actions-Facts besitzen einen getrennten advisory Assessmentpfad. [Anschlussgrenzen](README_technical.md#externe-scm-check-evidence-advisory). | Konkrete Adapter, Trustprofile, Subject und Permissions konfigurieren. Architektur-Austauschbarkeit ist kein implementierter universeller Workerhost; vorhandener Adapter ist keine Qualification jeder Umgebung. |
| **Security/DevSecOps:** Reichweite eines Findings oder einer Kontrolle bewerten. | Die Capabilitymatrix nennt aktive beziehungsweise advisory Wirkung und Fehlersemantik; Audit/SARIF machen passende Findings untersuchbar. [Security](README_technical.md#13-security-model), [Audit](README_technical.md#14-audit-trail). | Regeln, Profile und Fachprüfer pflegen. Diff-Secret-Scan und Promptheuristiken besitzen begrenzten Scope; SARIF-Export ist kein allgemeiner Scanner-Ingest. |
| **Engineering-Leitung:** Über eine konkrete Änderung mit offenen Punkten entscheiden. | Auftrag, Evidence, erforderliche Kriterien und Reviewbezug erklären die verfügbare Freigabegrundlage. [Referenzablauf](../technische%20Beschreibungen/README.md). | Fachliche Verantwortung und echte menschliche Receipts bleiben bestehen. Score und Dashboardstatus verleihen keine Authority; Nutzen, Pflegekosten und Fehlalarme müssen gegenüber dem eigenen Prozess gemessen werden. |
| **Compliance, Audit und Risikomanagement:** Die Herkunft einer Entscheidung prüfen. | Subject-/Policybezug, Auditspur und technische Framework-Zuordnungen liefern untersuchbare Informationen. [Mappings](COMPLIANCE_FRAMEWORK_MAPPINGS.md), [Auditvertrag](README_technical.md#14-audit-trail). | Betreiber müssen konkrete Zwecke, Aufbewahrung, Zugriff und rechtliche Eignung bewerten. Mapping, Attribution, Installation und Tests sind keine regulatorische Konformitätsbescheinigung. |

Besondere Nachweisanforderungen können diese Aufgaben bündeln. Auch dann
bleibt die [Referenzqualification](CAPABILITY_MATRIX.md#reale-referenzqualification)
an ihre konkrete Kombination aus Version, Umgebung und Attempt gebunden.
Eine Branche allein begründet weder einen ausreichenden Zusatznutzen noch
die Eignung einer neuen Installation.

## Dieselbe Aufgabe mit vorhandenen Werkzeugen vergleichen

Quellenstand **11.10.2026**. Verglichen werden dokumentierte Fähigkeiten für
benannte Aufgaben, keine Gesamtprodukte oder Preise. Dies ist kein ausgeführter
Vergleichsbenchmark. Andere Werkzeuge können eigene Policies, Approvals und
Erweiterungen haben; aus dieser Auswahl folgt keine Aussage über fehlende
Funktionen außerhalb der betrachteten Aufgabe.

| Vergleichsaufgabe | Bereits dokumentierte Fähigkeit mit Primärquelle | Konkreter Bezug zu S.A.M.U.E.L. und offene Vergleichsfrage |
|---|---|---|
| **Code erzeugen, testen und zum Review bringen — Coding-Agent** | [GitHub Copilot auf GitHub](https://docs.github.com/en/copilot/concepts/copilot-surfaces/copilot-on-github) kann Aufgaben planen, Dateien ändern, Tests ausführen und PRs bearbeiten; Code-Review ist ebenfalls ein eigener Weg. Verfügbarkeit hängt von Plan und Organisationsregeln ab. | Überschneidung mit dem Referenz-Worker. Der eigene Core bindet zusätzlich Auftrag, Contract, Subject und Evidence an seinen Entscheidungsvertrag. Ob dies gegenüber der eingerichteten Agent-/SCM-Kombination hilft, muss konkret geprüft werden; keine Behauptung fehlender Governance beim Vergleichswerkzeug. |
| **Geprüften Stand und Freigaben vor dem Merge absichern — SCM/CI** | [GitHub Branchschutz](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches) bietet erforderliche Statuschecks und Reviews sowie konfigurierbare Regeln zum Verwerfen veralteter Approvals bei Diffänderungen. | Ein bereits eingerichteter Prozess löst wesentliche Teile des Problems. Zu vergleichen ist, ob die zusätzliche kriteriumsweise Contract-/Policy-/Evidencebindung eine konkrete Lücke schließt. Grün allein ist weder hier noch im eigenen Produkt ein Nachweis aller fachlichen Kriterien. |
| **Bestimmte Codeprobleme erkennen — Scanner** | [Semgrep-Regeln](https://docs.semgrep.dev/running-rules) definieren untersuchte Codemuster und erzeugen bei Treffern Findings; lokale YAML-Regeln und ausgewählte Regelsätze sind ausführbar. | Fachanalyse und Einordnung ihrer Evidence sind verschiedene Aufgaben. S.A.M.U.E.L. ersetzt keinen universellen Scanner. Sein SARIF-Pfad exportiert Findings; eine Semgrep-Nennung belegt weder einen aktiven Adapter noch allgemeinen SARIF-Ingest. |
| **Strukturierte Eingaben anhand einer Policy entscheiden — Policywerkzeug** | [Open Policy Agent](https://www.openpolicyagent.org/docs) wertet strukturierte Eingaben mit Rego und Daten aus; die Anwendung setzt die Entscheidung durch. | Das eigene Produkt hat konkrete Policy-/Gateverträge für Softwareänderungen. Ein vorhandener OPA-basierter Prozess kann passende Regeln bereits umsetzen. Keine aktive OPA-Integration oder Überlegenheit wird daraus abgeleitet. |
| **Herkunft und erwarteten Herstellungsweg prüfen — Provenance** | [in-toto](https://in-toto.io/) ordnet Lieferkettenschritte und zugehörige Nachweise; [SLSA v1.2](https://slsa.dev/spec/v1.2/verifying-artifacts) beschreibt unter anderem die Prüfung von Signatur, vertrauenswürdiger Builderidentität, Artefaktbezug und erwarteten Parametern. | Vergleichbar ist die explizite Bindung von Nachweis und Gegenstand, nicht automatisch dieselbe fachliche Acceptance. Provenance allein beweist keine Codekorrektheit. Weder ein aktiver in-toto-/SLSA-Anschluss noch ein erreichtes SLSA-Level ist hier zugesagt. |

Für die Auswahl zählt die konkrete Lücke: Wer nur Codeassistenz, einen
Fachscanner oder eine einzelne Provenanceprüfung benötigt, kann mit dem
jeweiligen vorhandenen Werkzeug auskommen. Wer bereits verlässliche Kriterien,
Headbindung, Reviewregeln und auffindbare Nachweise besitzt, sollte den
zusätzlichen State-, Integrations- und Pflegeaufwand zuerst rechtfertigen.
Ein negatives Ergebnis dieses Vergleichs ist zulässig. Fehlende empirische
Nutzen-/Aufwandsdaten bleiben **UNKNOWN**; Produktumfang und Forschung ersetzen
sie nicht.

## Welche Evidenz trägt welche Aussage?

- **Technisch belegt:** Implementierung und benannte Regressionen zeigen
  definierte Annahme-, Ablehnungs- und Fehlerpfade. Profil, Konfiguration und
  Permissions bestimmen, welche Kontrolle tatsächlich wirkt.
- **Begrenzt praktisch belegt:** Historische Installations- und
  Referenznachweise gelten ausschließlich für ihr Subject, ihren Attempt und
  ihre Umgebung. Die [Referenzqualification](CAPABILITY_MATRIX.md#reale-referenzqualification)
  und das [Qualification-Runbook](runbooks/TEST_AND_QUALIFICATION_RUNBOOK.md)
  bestimmen die Grenzen. Solche Nachweise sind kein kontrollierter Nutzenvergleich.
- **Hypothese:** Gemeinsame Bindungen könnten Reviewfehler und manuelle
  Nachweissuche reduzieren. Ohne Vergleichsdaten ist die Größe dieses Effekts
  ebenso offen wie die Möglichkeit, dass zusätzlicher Aufwand überwiegt.
- **Nicht belegt:** Allgemeine Produktivitätssteigerung, geringere Gesamtkosten,
  vollständiger Schutz gegen Prompt Injection, allgemeine Fremdworkerqualification
  oder regulatorische Konformität. Ein positiver Dokumentverständnistest würde
  keine dieser Produktwirkungen messen.

Die [Produktgrenzen-ADR](adr/0678-product-boundary-and-integration-profile.md)
trennt Core, Referenzimplementierung und tatsächlich benötigte Adapter.
Bestehende Grenzen gelten weiter: lokales IMPORT/TEST ist keine allgemeine
Prozesssandbox; externe Evidence erhält nicht durch ihre Existenz Authority.
Der passive Score ersetzt keine Freigabe. Die dokumentierte R25-Grenze im
[CLI-Vertrag](README_technical.md#argumente-voraussetzungen-und-ergebnisgrenzen)
bleibt ein tatsächlicher Vorbehalt, kein freigegebener Ausnahmeweg.

## Wann reicht ein bestehender Prozess aus?

Bei einem kleinen Repository mit klaren Verantwortlichen, passenden
Branchschutzregeln, verlässlicher CI und wenigen manuellen Abnahmen kann die
vorhandene Toolchain ausreichen. Wenn Reviewende die benötigten Informationen
bereits zuverlässig finden, ist zusätzlicher S.A.M.U.E.L.-Betrieb möglicherweise
nicht gerechtfertigt. Gleiches gilt, wenn hauptsächlich Codevervollständigung,
ein einzelner Scanner oder Build-Provenance gebraucht wird: Die jeweiligen
Fachwerkzeuge bearbeiten diese Aufgaben direkt.

Voraussetzungen und Aufwand sind konkret: Acceptance-Kriterien pflegen,
aktive Profile und Rechte prüfen, SCM-/Providerzugänge betreiben, State und
Arbeitsbereiche sichern, Updates und Fehlfälle bearbeiten sowie menschliche
Reviews leisten. [Installation](INSTALL.md), [Dashboard](DASHBOARD.md) und
[State/Recovery](STATE_STORE.md) beschreiben diese Aufgaben. Es liegen hier
keine belastbaren gemessenen Personalstunden oder Total-Cost-of-Ownership-
Werte vor. Auch ein Team mit hohen Nachweisanforderungen benötigt einen
Vergleich mit seinen vorhandenen Kontrollen, statt allein deshalb einen
positiven Zusatznutzen anzunehmen.

Für eine spätere Nutzenmessung wären vorab gleichartige Aufgaben und eine
vergleichbare Ausgangstoolchain festzulegen. Zu erheben wären Durchlauf- und
Reviewzeit, übersehene Bindungs-/Acceptancefehler, Nacharbeit, Fehlalarme,
Providerkosten sowie Einrichtungs- und Wartungsaufwand. Unterschiedliche
Aufgabenschwierigkeit und Lernphasen müssen berücksichtigt werden. Dies ist
ein Vorschlag für fehlende empirische Evidence, kein durchgeführter Versuch
und keine neue blockierende Entwicklungsprüfung.

## Forschung und technische Entwicklung

Die folgende Auswahl untersucht agentische Entwicklung, Governance,
Software-Supply-Chain-Security und Nachweisbarkeit. Studien, Benchmarks und
technische Empfehlungen haben unterschiedliche Aussagekraft; sie werden
nicht zu einem gemeinsamen Wirksamkeitswert verrechnet.

| Primärquelle und Stand | Tatsächlicher Befund bzw. Gegenstand | Methodische Grenze und Bezug zum Produkt |
|---|---|---|
| [Cui et al., drei Feldexperimente, Autorinnenverzeichnis / Management Science 2026](https://soniajaffe.com/research) | Randomisierter Zugang zu Codeassistenz in drei Unternehmen, zusammen 4.867 Entwickler; berichtet werden 26,08 % mehr erledigte Aufgaben, Standardfehler 10,3 %. | Misst einen anderen Eingriff und Output, nicht S.A.M.U.E.L., Reviewqualität oder agentische Governance. Kein übertragbares Einsparversprechen. |
| [METR, Early-2025-RCT](https://metr.org/Early_2025_AI_Experienced_OS_Devs_Study-paper.pdf) | 16 erfahrene Open-Source-Entwickler bearbeiteten 246 Aufgaben in vertrauten Projekten; zugelassene damalige AI-Werkzeuge verlängerten die Bearbeitungszeit im Mittel um 19 %. | Spezifische Population und Werkzeuge von Februar–Juni 2025. Keine allgemeine Aussage über heutige Modelle, andere Teams oder sämtliche Entwicklungstätigkeiten. |
| [METR, Methodenupdate vom 24.02.2026](https://metr.org/blog/2026-02-24-uplift-update/) | Die Folgestudie berichtet Selektionsprobleme bei Teilnehmenden und eingereichten Aufgaben sowie Messprobleme bei parallelen Agenten. METR bewertet die Daten als unzuverlässiges Signal für die aktuelle Effektgröße. | Weder die frühere Verlangsamung unverändert fortschreiben noch aus den neuen Rohschätzungen einen gesicherten heutigen Gewinn ableiten. Lokale Vergleichsmessung bleibt erforderlich. |
| [AgentDojo, Debenedetti et al., NeurIPS 2024 / Originalarbeit](https://arxiv.org/abs/2406.13352) | Benchmark für Tool-Agenten mit 97 Aufgaben und 629 Sicherheitstestfällen untersucht Prompt-Injection-Angriffe und Abwehr. Angriffe verletzen einige, nicht sämtliche untersuchten Sicherheitsbedingungen. | Kontrollierte Aufgaben und konkrete getestete Modelle; keine universelle Angriffsrate. Begründet Prüfung untrusted Toolinhalte, beweist aber keinen Schutz des S.A.M.U.E.L.-Referenz-Workers. |
| [NIST NCCoE, DevSecOps-Referenzmodell, Abschnitt 2.7; abgerufen 11.10.2026](https://pages.nist.gov/nccoe-devsecops/notational-reference-model.html#artificial-intelligence-new) | Behandelt übermäßige Agentenrechte, Kontextmanipulation und AI-Artefakte ohne Provenance/Freigabe. Die beschriebene aktuelle Demonstration arbeitet unter menschlicher Leitung; agentische Erweiterungen werden als spätere Phase benannt. | Technisches Referenzmodell, keine Vergleichsstudie und kein Gesetz. Stützt die Relevanz kontrollierter Übergänge; bestätigt keine konkrete Produktimplementation oder Wirksamkeit. |
| [NIST SSDF 1.1, SP 800-218 / Projektübersicht](https://csrc.nist.gov/Projects/ssdf) | Risikobasierte sichere Entwicklung umfasst unter anderem dokumentierte Sicherheitsanforderungen und Provenance für Releasekomponenten. Auswahl berücksichtigt Aufwand, Anwendbarkeit und vorhandene Grundlagen. | Empfehlungen sind keine vollständige Checkliste oder Produktzertifizierung. Die Zuordnung eigener Controls muss separat geprüft werden; bloße Begriffsähnlichkeit reicht nicht. |
| [SLSA v1.2, Build: Verifying artifacts](https://slsa.dev/spec/v1.2/verifying-artifacts) | Provenance muss geprüft werden: unter anderem Signatur, Artefaktdigest, vertrauenswürdige Builderidentität und erwartete Parameter. Die Vertrauensbasis ist explizit. | Herkunftsnachweis beweist keine fachliche Codekorrektheit. Vergleichbares Bindungsprinzip ist keine Behauptung einer aktiven SLSA-Integration oder eines erreichten SLSA-Levels. |

## KI-Code im Review und Betrieb: Forschung und Praxisberichte

Ergänzender Quellenabgleich **12.10.2026** für das
[README-Praxisbeispiel](../README.md#ein-beispiel). Betrachtet wird die Arbeit
nach der Codeerzeugung: fachliches Review, Integration, Fehlersuche und spätere
Verantwortung. Die vorstehenden Studien und ihre Grenzen bleiben erhalten.

| Quelle und tatsächlich geprüfter Stand | Aussage für Review und Betrieb | Aussagegrenze |
|---|---|---|
| [DORA 2024, Bericht v.2024.3](https://dora.dev/research/2024/dora-report/2024-dora-accelerate-state-of-devops-report.pdf), S.37–40; [Errata](https://dora.dev/research/2024/errata/) | Der untersuchte höhere AI-Adoptionswert hängt mit schnellerem Review und zugleich schlechteren Deliverykennzahlen zusammen. Die Autoren diskutieren größere Änderungen als mögliche Erklärung und betonen kleine Batches und robuste Tests. | Beobachtete Zusammenhänge, keine Messung zusätzlicher DevOps-Arbeitsstunden und kein experimenteller Nachweis dieser Erklärung. Belegt weder generell langsamere Reviews noch die Wirkung von S.A.M.U.E.L. |
| [DORA 2025, öffentliche Berichtszusammenfassung](https://dora.dev/research/2025/dora-report/); [Versions-/Erratastand](https://dora.dev/research/2025/errata/) | KI wird als Verstärker bestehender organisatorischer Stärken und Schwächen eingeordnet. Der gesamte Entwicklungsprozess ist für die Wirkung relevant. | Die öffentlich gelesene Zusammenfassung ist kein eigener Reviewzeitbenchmark. Keine allgemeinen Mehraufwandszahlen daraus ableiten; der vollständige2025-PDF-Report wurde für diese Ergänzung nicht ausgewertet. |
| [Stack Overflow Developer Survey 2025: AI tool frustrations](https://survey.stackoverflow.co/2025/ai#ai-tool-frustrations), [Methodik](https://survey.stackoverflow.co/2025/methodology) | Befragte nennen fast richtige KI-Ausgaben und zeitaufwendigere Fehlersuche als Frustrationen. | Selbstauskunft, Mehrfachauswahl, über eigene Kanäle rekrutierte Stichprobe. Keine objektive Zeitmessung oder repräsentative Aussage über sämtliche Entwickler/Teams. |
| [Reddit: Reviewing coworkers' AI-generated PRs](https://www.reddit.com/r/ExperiencedDevs/comments/1jfhqye/reviewing_coworkers_aigenerated_prs/), 20.03.2025 | Der Autor berichtet unnötige Änderungen, aufwendiges Review und Nacharbeit; er beschreibt auch einen nach Merge beschädigten Main. | Einzelner anonymer, nicht unabhängig verifizierter Erfahrungsbericht; keine Häufigkeitsstatistik, keine allgemeine Aussage über Coding-Agenten. |
| [Reddit: Reviewing 2000 line AI Slop Pull Request](https://www.reddit.com/r/ExperiencedDevs/comments/1osyyci/reviewing_2000_line_ai_slop_pull_request/), 09.11.2025 | Der Autor beschreibt Reviewaufwand und ein paralleles Architekturpattern; zusätzliche Wartung, Support und Fehlersuche befürchtet er für das Team. | Der KI-Ursprung ist seine Einschätzung. Späterer Betriebsaufwand ist eine Erwartung, keine beobachtete Ausfall- oder DevOps-Zeitmessung. Nicht repräsentativ. |

**Ableitung für das Beispiel:** Nacharbeiten und Zuordnungsprobleme sind
konkret berichtete Erfahrungen; ihre Größe hängt von Aufgabe, Team und Prozess
ab. Die bestehende METR-Studie ergänzt eine auf ihre Population begrenzte
experimentelle Zeitmessung. Die Befunde tragen ein Beispielszenario, in dem
mehrere Änderungen Review und Betrieb beanspruchen. Sie tragen keine allgemeine
Behauptung, dass KI immer schneller programmiert oder überall mehr
DevOps-Arbeit erzeugt.

**Konkreter Produktbeitrag:** Die vorhandene Subject-/Contract-/Policybindung,
PR-Auftrags-/Gate-/Acceptanceinformationen und Lauf-/Auditsicht ordnen
Änderungen und Nachweise im unterstützten Workflow zu. Große PRs werden dadurch
nicht automatisch sinnvoll klein, parallele Agenten nicht universell gesteuert
und das fachliche Review nicht ersetzt. Ob diese Zuordnung im Team tatsächlich
Such-, Review- oder Betriebszeit spart, bleibt durch einen passenden Vergleich
zu messen; die oben genannten Messgrößen gelten weiter.

**CRA im selben Zusammenhang:** Das vorhandene
[CRA-Mapping](COMPLIANCE_FRAMEWORK_MAPPINGS.md) bietet technische Querverweise zu
Controls und Evidence-Referenzen, zum Beispiel für sichere Entwicklung,
Schwachstellenbehandlung, Tests und Komponenteninformationen. Das Dashboard
zeigt die Definitions-/Mappingversionen. Das ist die implementierte advisory
Zuordnung; der aktive Pack-/Policy-Vollumfang und seine eigene Runtimeabnahme
bleiben im zuständigen #873-Scope. Fehlende SBOM- oder Incidentnachweise
entstehen nicht durch ein Mapping. Anwendungsbereich und rechtliche Erfüllung
sind gesondert zu beurteilen.

## Was folgt daraus für die zukünftige Relevanz?

**Belegte Entwicklung:** Es gibt empirische Untersuchungen von Codeassistenz,
Agenten-Sicherheitsbenchmarks und ausgearbeitete Vertrauens-/Provenanceverträge.
Die Quellen zeigen zugleich, dass gemessene Produktivität nicht aus einer
Modellbenchmark oder subjektivem Eindruck abgeleitet werden darf.

**Begründete Erwartung:** Wenn Teams mehr Änderungen durch unterschiedliche
Producer erzeugen lassen, können eindeutig gebundene Aufträge, Prüfungen und
Entscheidungen wichtiger werden. Diese Schlussfolgerung verbindet die oben
beschriebenen Risiken mit dem vorhandenen Produktkern. Sie setzt voraus, dass
Teams diese Übergänge tatsächlich nutzen und der Pflegeaufwand tragbar bleibt.
Ob S.A.M.U.E.L. dafür die passende Lösung ist, bleibt installations- und
vergleichsabhängig.

**Ungesicherte Prognose:** Künftige Marktanteile, eine allgemein notwendige
zusätzliche Governanceplattform, garantierte Kostensenkungen oder eine
regulatorisch vorgeschriebene Nutzung dieses Produkts sind nicht belegt und
werden nicht als Produktversprechen verwendet.

Die heute überprüfbare Relevanz liegt in vorhandenen, begrenzten technischen
Kontrollen. Praktischer Zusatznutzen und langfristige Eignung benötigen eigene
Nachweise. Ein negatives Ergebnis einer solchen Prüfung ist zulässig.

## Quellenpflege

Produktänderungen folgen der bestehenden
[Documentation acceptance](../CONTRIBUTING.md#documentation-acceptance):
Aussagen, Bindungen und betroffene Prüfungen werden im verursachenden PR
geprüft. Der Document Contract erkennt Änderungen seiner lokalen Quellen;
er überwacht keine externen Webseiten und bewertet keine wissenschaftliche
Semantik. Bei Änderungen dieser Nutzen-/Zukunftsaussagen sind verlinkte
Primärquellen, Version, Untersuchungszeitraum und Übertragungsgrenze erneut zu
prüfen und der Abrufstand fortzuschreiben. Zuständig bleiben die bestehenden
Repository-Maintainer, ohne zusätzliche Dokumentationsauthority.
