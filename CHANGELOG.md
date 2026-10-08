# Changelog

All notable changes to S.A.M.U.E.L. v2.

## [Unreleased]

## [2.0.0a28] - 2026-10-08

- #978: Official offline hash-locked Python/Pytest toolchain preparation and read-only OCI registration reuse the existing TEST runner, sterile process environment and Gate-11 evidence. Toolchain identity joins the existing policy/resume binding; missing or changed artifacts fail closed.
- #978: Doctor accepts a protected temporary branch-protection token file for the branch GET only, for Gitea and GitHub (including Enterprise). Runtime credentials remain unchanged; redirected temporary credential reads are rejected. GitHub native protection is now checked instead of omitted.

- #873: CRA advisory controls, version-bound generic mapping snapshots and a shared OWASP/AI-Act loader; GDPR descriptors and a common dashboard legend. Existing policy, privacy and attribution semantics are preserved. The full active pack/policy contract remains open.

## [2.0.0a27] - 2026-10-06

### Publication

- Official seven-asset release and immutable OCI image published and read back. Independent installation from published assets on pristine Ubuntu 24.04.5 passes setup, production health, identity, persistence and freeze checks. #970/#971 closed; workflow/LLM, Golden and D0 acceptance remain separate in #962.

### Fixed

- #970/#971: Manifest-bound OCI clean installation delivers a checked installer kit and Compose assets, derives runtime ownership from the image, preserves external operator sources, and guides setup into production.
- Fresh non-interactive setup leaves SCM fields empty. Incomplete SCM settings now follow the existing unconfigured bootstrap path so the dashboard can start before credentials are entered.
- The container health check allows a bounded 60 seconds for runtime bootstrap and connectivity checks, avoiding false unhealthy results from the former five-second timeout on slower fresh hosts.
- Installation documentation uses the selected release manifest instead of a15 as an active reference. Docker/Compose/platform and registry failures are reported before operator-path initialization.

## [2.0.0a26] - 2026-10-05

- Publish: Main-CI #1165, annotiertes Tag, Tag-CI #1166, Gitea-Prerelease
  #40, vier byteidentisch zurückgelesene manifestgebundene Assets und
  linux/amd64-OCI-Digest sind real belegt. Der erste Required Smoke war
  healthy und versions-/revisionsgebunden. Die fehlenden Altlastenabnahmen
  bleiben in #962 vertagt; kein Golden-/D0-/Supportclaim.


- Release: Alpha-Stand für die separate Erstinstallation durch den Maintainer.
  Die implementierten Altissues mit ausschließlich fehlender Restabnahme sind
  administrativ geschlossen und nach #962 übertragen. Fehlender Abnahme-PASS
  blockiert diesen Release ausdrücklich nicht; Build, CI, Paket-, Tag-,
  OCI-, Required-Smoke- und Manifestbindung bleiben Pflicht. Kein Golden-/D0-
  oder Supportclaim. Das vollständige Testkonzept entsteht erst nach der
  getrennten Installation; offene Implementation-/Designissues bleiben offen.

- Workflow: Seit a25 integriert sind dauerhafte Planauthority und native
  signierte Gitea-Approvalverarbeitung, korreliertes Replanfeedback, begrenzte
  Providerfehlerpfade sowie gebundene MANUAL-Fortsetzung und Human-Merge-
  Projektion. Healthchecks starten keine Workflowfortsetzung. Vorhandene
  Grenzen für echte menschliche Planfreigabe, Acceptance und Merge bleiben.

- Dashboard: Taskmodelllisten erhalten unbekannte gespeicherte Modelle,
  ignorieren veraltete Discoveryantworten und zeigen Fehler/Leerlisten
  konsistent. Workflowzeiten verwenden die vorhandene Setup-Zeitzone;
  Diagnose-, Callaktivitäts- und Rekonfigurationshinweise sind präzisiert.

- Implementation: SEARCH/REPLACE erhält die ursprüngliche EOF-Semantik;
  vorhandene Runner-/Prompt-/Reviewverträge wurden gezielt korrigiert.

- Fix: Unabhängige Setup-Rollbacks werden nach dauerhaft verweigertem Write
  weiter abgeschlossen (#957). Die folgende private Stagingkorrektur gehört
  ebenfalls zu diesem Release; die ursprüngliche Evidence bleibt erhalten.

- Fix: Der explizite Setup-Dateibindmount nutzt privates Staging auch beim
  Rollback, wenn das image-eigene Elternverzeichnis nicht schreibbar ist.
  Ein kontrollierter Writefehler überdeckt dadurch nicht mehr die Rücknahme
  mit einem zweiten Staging-Permissionfehler; temporäre Dateien werden
  entfernt. Production-Freeze und die begrenzte Crashgarantie bleiben
  unverändert (#823, #691).

## [2.0.0a25] - 2026-09-21

- Release: Dieser Alpha-Stand folgt auf den veröffentlichten, aber nicht
  D0-qualifizierten Stand `v2.0.0a24`. `v2.0.0a25` ist mit grüner Tag-CI,
  vier manifestgebundenen Assets, OCI-Digest und erstem Required Smoke
  veröffentlicht. Golden-D0 und Capabilityqualifications bleiben eigene
  nachgelagerte Nachweise; dieser Eintrag behauptet weder Qualification noch
  Support.

- Fix: Agenten-, Block- und Statuskommentare ohne gültigen veröffentlichten
  Acceptance Contract erzeugen keine aktive Planauthority. Der bestehende
  Schutz für echte Pläne, Replan, Approval und Widerruf bleibt erhalten
  (#846).

- Fix: `samuel run` beendet einen eigenen terminalen `PlanBlocked`-Lauf mit
  einem Fehlerstatus und einen erfolgreichen eigenen Lauf weiterhin mit
  Status 0. Fremde Terminalereignisse werden nicht zugerechnet; das bestehende
  `PlanReplanRejected`-Verhalten bleibt erhalten (#847).

- Security: Ein keyloser JSONL-Auditwriter verweigert vor jeder Mutation den
  Append an eine bereits signierte Chain. Neue unsigned Chains bleiben
  zulässig, bestehende signed Restart-, Multiprozess-, Rotations- und
  Fallbackpfade sowie die optionale Signierung bleiben unverändert (#844).

- Diagnostics: Konkrete Applyfehler werden begrenzt und redigiert bis zur
  terminalen Evidence weitergereicht. Parser- und Appliersemantik wurden ohne
  einen belegten Produktfehler nicht geändert (#828).

- Documentation: Die aktive Release-Lineage weist a25 als jüngsten
  veröffentlichten, nicht qualifizierten Kandidaten aus. a20/a22 bleiben
  fehlgeschlagene Sourcebindungen, a23 besitzt nur belegten OCI-Publish und
  Smoke, und a15 bleibt unterstützt, ohne den wegen Bot-Merge nicht
  bestätigten vollständigen D0-PASS zu behaupten. Historische Releaseeinträge
  und unveränderliche Evidence bleiben erhalten. Bootstrap-/Stored-effective-
  Grenzen, kanonische Origins, Provider-/Taskprofile, Dashboardzugang,
  Release-Source/-Operator und lokale Secretquellen sind dokumentarisch
  angeschlossen, ohne reale Betriebswirkung zu behaupten (#808, #843, #845,
  #822, #829, #830, #835, #821, #840).

- Tests: Veraltete Release-/Qualification-, Manifest-/ImplementationPort- und
  Control-Matrix-Erwartungen sowie Event-Skip-/Coverageaussagen wurden an die
  bereits integrierten Verträge angeglichen (#575, #693, #840).

## [2.0.0a24] - 2026-09-21

- Security: Der Setup-Wizard gibt keine Dashboard-Credentialwerte mehr aus.
  Seine Abschlussinformation bestätigt nur den konfigurierten lokalen
  Authentifizierungszustand (#838).

- Release: Dieser neue Kandidat folgt auf `v2.0.0a23`; der frische Golden-D0
  bleibt erforderlich.

## [2.0.0a23] - 2026-09-20

- Release: Dieser neue create-only Kandidat folgt auf `v2.0.0a22`, dessen
  OCI-Tag nach einem fehlgeschlagenen frischen Compose-Smoke unverändert als
  nicht qualifizierte Evidence erhalten bleibt. Der Kandidat verwendet die
  extern korrigierte, auf das Produkt-SCM-Subject gebundene
  Release-Operatorumgebung (#835); eine D0-Qualification wird dadurch nicht
  behauptet.

## [2.0.0a22] - 2026-09-20

- Fix: Der Planning-Snapshot übergibt bekannte Aufrufnamen an den
  Skeleton-Pre-Check. Dadurch blockiert eine im gebundenen Snapshot bereits
  vorhandene Funktionsreferenz wie `casefold()` keinen autorisierten Plan
  mehr als vermeintlich neue Definition (#831).

- Release: Dieser Kandidat folgt auf `v2.0.0a21`; Veröffentlichung, Tag-CI
  und OCI-Publish sind noch keine D0-Qualification. Der frische Golden-D0
  bleibt erforderlich.

## [2.0.0a21] - 2026-09-20

- Release: Dieser create-only Folgecandidate ersetzt den unveränderlichen, aber
  nicht veröffentlichbaren OCI-Tag `v2.0.0a20`. Dessen Publish band vor der
  Manifest- und Prerelease-Erstellung eine falsche Source-Referenz; der Tag
  bleibt Auditspur, wird nicht überschrieben und ist nicht D0-qualifizierbar.
  a21 verwendet die aus dem Produktremote abgeleitete Source-Referenz und
  durchläuft Tag, Artefakte, OCI-Smoke und den vollständigen D0-Lauf erneut.

## [2.0.0a20] - 2026-09-20

- Release: Dieser geplante create-only Alpha-Kandidat folgt auf den technisch
  veröffentlichten, aber nicht D0-qualifizierten Stand `v2.0.0a19`. Er enthält
  den gezielten Setup-Fix aus #823. Tag, Artefakte, OCI-Publish und
  Compose-Smoke werden vor der separaten D0-Qualification nach dem
  Releasevertrag nachgewiesen; bis zum vollständigen frischen Golden- und
  Blockierpfad desselben veröffentlichten Digests besteht kein
  Qualification- oder Supportclaim.

- Fix: Der getrennte Setup-Prozess kann den dokumentierten einzelnen
  Docker-`.env`-Datei-Bind-Mount nach einem nachgewiesenen `EBUSY` oder einer
  nicht beschreibbaren imageeigenen Elterndirectory mit dem bereits privat
  gestagten Inhalt synchronisiert in-place aktualisieren. Der reguläre
  Rename-Pfad sowie die Mehrdateien-Staging- und Rollbacksemantik bleiben
  erhalten; kontrollierte Fehler im Fallback werden zurückgerollt. Der
  Fallback beansprucht ausdrücklich keine Rename-Atomizität bei Prozess- oder
  Hostabbruch während des In-Place-Writes. Production bleibt eingefroren und
  die produktive Konfiguration read-only (#823).

## [2.0.0a19] - 2026-09-20

- Release: Dieser neue create-only Alpha-Kandidat folgt auf den nicht
  veröffentlichten a18-Auditstand. Er führt den korrigierten Produktions-
  Compose-Vertrag durch einen frischen Tag-, Artefakt-, OCI- und
  Compose-Smoke-Pfad. Bis zum erneuten frischen D0-Installations-, Golden- und
  Blockiernachweis desselben Digests ist er ausdrücklich nicht qualifiziert.

- Fix: Die Produktionsroute importiert ihre Operator-Env ausschließlich über
  Compose `env_file`; sie bindet die Datei nicht mehr als `/app/.env` in den
  unprivilegierten Laufzeitcontainer ein. Der getrennte Setup-Override behält
  den expliziten schreibbaren Mount für bestätigte Konfigurationsänderungen
  (#691).

- Fix: Ein nachweisbarer Unterbruch nach create-only OCI-Push und vor
  Manifestmaterialisierung kann ausschließlich über einen neuen fail-closed
  Recoverypfad geprüft werden. Der Pfad baut, pusht, retaggt, löscht und
  veröffentlicht nichts; er bindet nur einen vorhandenen, frisch geprüften
  Digest nach erfolgreichem Compose-Smoke an das Manifest (#814).

## [2.0.0a18] - 2026-09-19

- Release: Dieser create-only Alpha-Kandidat führt den in #691 ergänzten
  operatorgestarteten Compose-Setup-Overlay aus. Konfigurationsänderungen
  erfolgen nur im ausdrücklich gestarteten Setupmodus gegen dieselbe externe
  Env-/Config-Quelle; der anschließende Produktionsdienst bindet diese Quellen
  read-only und verlangt für ihre wirksame Übernahme einen Restart. Der Stand
  ist bis zum frischen Release-, Deploymentübergangs- und D0-Nachweis
  ausdrücklich nicht qualifiziert.

- Fix: `docker-compose.setup.yml` stellt den bestehenden Dashboard-Editor mit
  schreibbaren externen Env- und Config-Mounts bereit. Der normale
  `docker-compose.yml`-Dienst erhält dieselbe Env-Datei ausschließlich
  schreibgeschützt. Installations- und Container-Releasevertrag prüfen die
  Mount- und Modusgrenze gegen Drift (#691).

## [2.0.0a17] - 2026-09-19

- Release: Dieser create-only Alpha-Kandidat folgt auf den unveröffentlichten
  Tag `v2.0.0a16` und übernimmt den aktuellen Produktstand mit dem ersten
  öffentlichen Documentation-Contract, seinem unabhängigen Advisory-Consumer
  sowie dem gebundenen Review-/Auto-Merge-Mechanismus. Tag, Artefakte und
  Container-Publish sind keine D0-Qualification. Der Stand bleibt bis zum
  frischen Installations-, Golden- und Secret-Blockiernachweis desselben
  Pakets und OCI-Digests ausdrücklich nicht qualifiziert.

- Feature: `samuel.extensions` liefert den ersten öffentlichen, versionierten
  und ausschließlich datenbasierten Extensionvertrag für
  `documentation.static_claims`. Geschlossene JSON Schemas und die read-only
  CLI `samuel-extension` binden Repository, Head, Policy, Request und
  Artefaktdigests. Der D08-geschützte Dashboard-Editor zeigt gespeicherten und
  wirksamen Zustand getrennt. `config/extensions.json` bleibt ausgeliefert
  optional und deaktiviert; Installation aktiviert nichts, und eine
  Required-Capability kann durch Deaktivierung nicht umgangen werden.
  Fremdcode wird nicht in den Core geladen, die erste Wirkung bleibt advisory. Der reale unabhängige
  Documentation-Consumer und Publishernachweis sind in #636 dokumentiert (#639).

- Feature: `documentation.inventory.v1` konkretisiert den öffentlichen
  Extensionvertrag als exakte, commitgebundene Markdowninventur mit
  Policy-, Tool-, Subject- und Artefaktdigests. `samuel-documentation`
  bereitet Requests vor, verifiziert die unabhängigen Claims erneut gegen
  Git, blockiert Secret-/Sensitive-Data-Signale und publiziert nur eine
  nicht autoritative Metadatenprojektion. Wiki und Inventory verwenden
  denselben Git-Marker-, Non-force-, No-op- und Receipt-Reconcilepfad; der
  reale Consumer bleibt ausschließlich im Apache-2.0-Demorepository (#636).

- Feature: Der nachgelagerte Review akzeptiert einen geschlossenen,
  versionierten und an Subject, Diff, Policy, Tool sowie Prompt gebundenen
  `pass|block|indeterminate`-Entscheid. Der optionale Auto-Merge läuft erst
  nach `pass`, frischer menschlicher Planfreigabe, gebundenen Required-Gates
  und erneut bestätigter PR-Revision. Gitea erhält `head_commit_id`; ein an
  Review und Subject gebundener Intent verhindert blinde Wiederholung und
  reconciliert unbekannte Ausgänge. Beide Aktivierungs-/Qualifikationsflags
  bleiben ausgeliefert aus, bis der isolierte Live-Smoke abgeschlossen ist
  (#468).

## [2.0.0a16] - 2026-09-19

- Release: Dieser Alpha-Kandidat übernimmt den auf `v2.0.0a15` folgenden
  Produktstand einschließlich des gebundenen Planning-Klärungsdialogs aus
  #575. Veröffentlichung und Tag-CI sind noch keine reale Qualification. Der
  Stand bleibt ausdrücklich nicht D0-qualifiziert, bis eine frische
  Installation mit leerem State und neuen Issues im unabhängigen
  Demo-Repository den positiven Klärungs-/Approval-/PR-Pfad sowie Timeout,
  doppelte, verspätete und editierte Antworten, Supersession und terminale
  Blockade desselben Digests belegt.

- Feature: Planning erkennt ausschließlich explizite Lücken und beweisbare
  Vertragswidersprüche deterministisch und führt sie in höchstens zwei
  persistente SCM-Klärungsrunden mit je drei Fragen und expliziter endlicher
  Operatorfrist. Frage, Antwort, Akteur, Kommentarrevision, Issue-/Base-Quelle
  und Workflow-Budgetzulassung werden gebunden und vor Approval sowie
  Implementation erneut gelesen. Timeout, Drift oder mehrdeutige Evidence
  erzeugen `PlanBlocked`/`WorkflowAborted` ohne partiellen Contract. Ein Plan
  mit Klärungsbasis benötigt auch in sonst automatischen Profilen die
  bestehende menschliche Freigabe des exakten Plans; klare Issues behalten den
  bisherigen Pfad. SQLite-Schema v10, Restore/Retention/Reconcile,
  Audit/Dashboard sowie OWASP- und AI-Act-Projektion bilden denselben Vertrag
  ab (#575).

- Feature: `samuel evidence assess` liest einen ausdrücklich benannten,
  vorhandenen Gitea-Actions-Run über eine begrenzte SCM-Check-Grenze, trennt
  Providerfacts von der S.A.M.U.E.L.-Bewertung und persistiert das Ergebnis im
  vorhandenen Observation-Store. Repository, Run/Attempt, PR-Base/-Head,
  Workflow-Blob, Statuskontext und Freshness werden geprüft; fehlende
  Runner-, Toolchain-, Signatur- oder Request-Bindung bleibt sichtbar. Das
  Ergebnis und sein in-toto-Statement-v1-Rahmen sind ausschließlich advisory
  und besitzen weder Required-, Dispatch- noch Mutationswirkung. Der bindende,
  auftragsgebundene Providerpfad bleibt #679 (#520).

- Fix: Setup, Dashboard und `samuel doctor` verwenden für Gitea genau einen
  expliziten erwarteten Required-Check-Kontext. Fehlt
  `SCM_REQUIRED_STATUS_CONTEXT`, wird der ausgelieferte Default sichtbar
  gemeldet; leere oder mehrzeilige Werte sowie jede Abweichung von der nativen
  Branch-Regel blockieren fail-closed. Provider und effektiver Kontext sind in
  Gate-Policy, Evidence-Identität und Resume-Schutz gebunden, ohne den Sollwert
  aus beobachtetem SCM-Zustand abzuleiten (#694). Die reale positive und
  negative Qualification am unabhängigen Zielrepository bleibt vor
  Issueabschluss erforderlich.

- Fix: Ein wegen `llm_response_truncated` blockierter Planning-Lauf weist im
  Issue-Kommentar jetzt auf Ausgabetokenbudget, Modell-/Prompt-Eignung und den
  bewussten neuen Planning-Lauf hin. Er klassifiziert den Fall nicht mehr
  fälschlich als unscharfen Issue-Text. TokenLimitHit, PlanBlocked, Retry- und
  Fallbacksemantik bleiben unverändert.

- Qualification: Der native Ollama-Pfad aus #701 ist in der isolierten
  D0-Umgebung positiv und negativ real belegt. Ein digestgebundenes lokales
  Modell erzeugte über den unveröffentlichten `main`-Kandidaten `7fac8e7`
  einen strukturell gültigen Plan mit realen Tokenwerten,
  `stop_reason=stop`, Plan-/Acceptance-Score 100 und 5/5 Checks. Der reale
  a15-Dashboard-Quality-Pfad kennzeichnet dasselbe 3B-Modell zugleich korrekt
  als `below_min` zur lokalen 7B-Warnschwelle; der Call besitzt keinen
  gebundenen Modellqualitätsscore oder EWMA. Bei absichtlich gestopptem
  Provider wiederholte a15 exakt
  zweimal und endete korreliert in `LLMUnavailable` und `PlanBlocked`, ohne
  `LLMCallCompleted` oder Fallback. Claude und Gemini bleiben ausschließlich
  durch providergetreue Fixtures belegt; die Evidence ist kein allgemeiner
  Verfügbarkeits- oder Performanceclaim, macht aus der informativen
  Parameterwarnung keine Blockierpolicy und ändert den a15-Release nicht.

- Fix: Statische Task- und zeitgesteuerte Routing-Overrides reichen den
  konfigurierten LLM-Timeout jetzt auch an die nativen Claude- und
  Ollama-Adapter weiter. Ohne Override bleibt deren bisheriger Standard von
  120 Sekunden bestehen (#781).

- Qualification: `v2.0.0a15` hat die interne D0-Referenzstrecke aus #658
  abgeschlossen. Die frische digestgebundene Installation bestand Runtime-,
  Provider-, Auth-, Audit-, Neustart- und Dashboardprüfungen. Demo-#57 lief
  nach menschlicher Freigabe vom gebundenen Plan über Candidate, Required
  Gates und PR-CI #794 bis PR #59, Merge und grüner Main-CI #795. Demo-#58
  wurde am gebundenen Candidate durch `diff_secret_scan` blockiert, ohne PR
  oder damalige `main`-Änderung. Der absichtlich wiederholte Planning-Aufruf
  blieb terminal `blocked`, auditierbar und unter OWASP ASI01 sichtbar,
  während Plan, Kommentar, Vertrag und `status:plan` unverändert blieben.
  Damit ist a15 für genau diese Referenzkombination der unterstützte
  Alpha-Stand; dies ist keine Beta-, Compliance- oder allgemeine
  Deploymentfreigabe. #694 bleibt eine bekannte Betreibergrenze.

## [2.0.0a15] - 2026-09-17

- Release: Dieser Alpha-Kandidat ersetzt den bereits unveränderlich
  veröffentlichten, aber nicht D0-qualifizierten Stand `v2.0.0a14`. Die
  frische a14-Referenzinstallation bestätigte die terminale `blocked`-
  Projektion, Audit-Kette, Dashboarddarstellung sowie OWASP ASI01 und AI Act
  Art. 14 für einen abgelehnten impliziten Replan. Dabei zeigte sie zugleich,
  dass die Labels-Projektion den weiterhin autoritativen Plan fälschlich von
  `status:plan` auf `status:failed` setzte. a15 führt die Korrektur aus #776
  mit neuer create-only Identität durch die vollständige Liefer- und
  D0-Strecke. Bis zum frischen Golden- und Blockiernachweis bleibt auch a15
  ausdrücklich nicht qualifiziert; #658 und #714 bleiben offen.

- Fix: `PlanReplanRejected` bleibt ein terminal blockierendes Workflow-
  Ergebnis für Run-, Stage-, Log-, Audit- und Security-Projektionen, löst aber
  keine Labels-Transition mehr aus. Der unveränderte exakte Plan bleibt damit
  unter `status:plan` für eine menschliche Prüfung oder einen ausdrücklichen
  `samuel replan ISSUE --reason TEXT` erhalten (#776).

## [2.0.0a14] - 2026-09-17

- Release: Dieser Alpha-Kandidat ersetzt den bereits unveränderlich
  veröffentlichten, aber nicht D0-qualifizierten Stand `v2.0.0a13`. Die
  frische a13-Referenzinstallation wies den Schutz gegen einen impliziten
  Replan real nach: kein neuer Plan, kein neuer SCM-Kommentar und keine
  Vertrags- oder Labelübertragung. Das Ereignis war in Audit, Dashboard,
  OWASP ASI01 und AI Act Art. 14 sichtbar, doch die Run-Projektion blieb
  fälschlich `running`. a14 führt die Korrektur aus #772 mit neuer
  create-only Identität durch die vollständige Liefer- und D0-Strecke. Bis
  zum frischen Golden- und Blockiernachweis bleibt auch a14 ausdrücklich
  nicht qualifiziert; #658 und #714 bleiben offen.

- Fix: `PlanReplanRejected` beendet den abgelehnten Lauf in der gemeinsamen
  Outcome-Authority als `blocked` und erscheint als fehlgeschlagene Plan-Stage,
  Log-Warnung und OWASP-ASI01-Security-Ereignis. Der weiterhin autoritative
  bestehende Plan und seine Labels bleiben unverändert. `PlanRevoked` bleibt
  nichtterminal, damit ein expliziter `samuel replan ISSUE --reason TEXT`
  danach im selben Lauf einen neuen, erneut freigabepflichtigen Plan erzeugen
  kann (#772).

## [2.0.0a13] - 2026-09-17

- Release: Dieser Alpha-Kandidat ersetzt den abgebrochenen create-only Stand
  `v2.0.0a12`. Dessen Tag-CI und Artefaktprüfung waren grün und das Image wurde
  einmalig gepusht; der verpflichtende erste Compose-Smoke verwendete jedoch
  ein unvollständiges Operatorprofil und erreichte deshalb den Healthstatus
  nicht innerhalb des Zeitlimits. Der unveränderte a12-Digest wurde danach mit
  dem vollständigen vorhandenen Profil erfolgreich diagnostiziert, wird nach
  dem Abbruchvertrag aber weder erneut publiziert noch als Release ausgegeben.
  a13 führt denselben #767-Produktfix mit neuer unveränderlicher Identität durch
  die vollständige Lieferkette. Auch a13 ist bis zum frischen D0-Golden- und
  Blockiernachweis nicht qualifiziert; #658 und #714 bleiben offen.

- Fix: Ein normaler `samuel run` ersetzt keinen aktiven Plan. Nur
  `samuel replan ISSUE --reason TEXT` darf den exakten Plan und seine Freigabe
  revisionsfest widerrufen; der neue Plan benötigt danach ein neues, zeitlich
  und inhaltlich gebundenes menschliches Approval. Alte, verzögerte,
  unvollständige oder boterzeugte Freigabeevidence bleibt fail-closed (#767).

## [2.0.0a12] - 2026-09-17

- Release: Dieser Alpha-Kandidat ersetzt `v2.0.0a11` für die noch offene
  D0-Gesamtqualification. a11 bestand Installation, Runtime-, Provider- und
  Blockierpfade, scheiterte aber im positiven Golden Path daran, dass ein
  erneuter Lauf einen bereits freigegebenen Plan ersetzte und die bestehende
  Freigabe auf den neuen Plan übertrug (#767). a12 enthält die Korrektur dieses
  Workflowvertrags. Veröffentlichung und Tag-CI sind noch kein Support- oder
  Gesamtclaim; #658 und #714 bleiben bis zum frischen Golden- und
  Secret-Scan-End-to-End-Nachweis für exakt den neuen Digest offen. #694 bleibt
  als entscheidungspflichtige SCM-/Doctor-Grenze unverändert.

- Fix: Ein normaler `samuel run` ersetzt keinen aktiven Plan mehr. Das neue
  explizite `samuel replan ISSUE --reason TEXT` widerruft den exakten Plan und
  seine Freigabe revisionsfest, entfernt die Workflowlabels und erzeugt erst
  nach bestätigtem Widerruf einen neuen Plan. Dessen Freigabe muss durch ein
  neues menschliches Labelereignis erfolgen, das an Plan-Kommentar, Vertrag,
  Akteur, Methode und Zeitpunkt gebunden ist. Alte, verzögerte, unvollständige
  oder boterzeugte Approval-Evidence bleibt fail-closed; unterbrochene Replans
  können ohne doppelten Widerruf fortgesetzt werden (#767).

- Release-Evidence: Annotiertes Tag `v2.0.0a12` und Gitea-Tag-CI #780 sind
  grün. Der create-only OCI-Push erzeugte einen unveränderlichen Digest, doch
  der unmittelbar folgende erste Compose-Smoke blieb mit dem unvollständigen
  Operatorprofil im Startzustand. Es wurde deshalb kein Gitea-Prerelease für
  a12 angelegt. Der Stand bleibt Abbruchevidence und wird durch a13 ersetzt.

## [2.0.0a11] - 2026-09-02

- Release: Dieser Alpha-Kandidat ersetzt `v2.0.0a10` für die noch offene
  D0-Gesamtqualification. a10 bestand frische Installation, Runtime-/Provider-
  und Runner-Negativprüfungen sowie den getrennten a9→a10-OCI-Upgrade-Drill,
  scheiterte aber im positiven Golden-Plan an einem widersprüchlichen
  `[TEST]`-Beispiel im Planning-Prompt. a11 enthält ausschließlich dessen
  Korrektur. Der anschließende D0-Lauf bestand Installation, Runtime,
  Provider-/Readinessprüfungen und den echten Secret-Scan-Block, scheiterte
  aber im Golden-Pfad an der unzulässigen Übernahme eines älteren
  Approval-Labels auf einen neu erzeugten Plan (#767). a11 ist deshalb
  veröffentlicht, aber ausdrücklich nicht D0-qualifiziert; #658 und #714
  bleiben offen. #694 bleibt als entscheidungspflichtige SCM-/Doctor-Grenze
  unverändert. #690 und #756 wurden mit der gebundenen a11-Evidence
  geschlossen.

- Release-Evidence: Annotiertes Tag `v2.0.0a11`, Gitea-Tag-CI #770,
  Prerelease #25, vier erneut byteidentisch geprüfte Assets und ein frischer
  digestgebundener OCI-/Compose-Smoke stimmen auf Commit
  `bde64862f20e2d2bea0b1cb07211ac4a671390b5` überein. Der D0-Negativfall
  Demo-#52 blockierte erwartungsgemäß in `diff_secret_scan`, ohne PR, Merge
  oder Änderung von `main`. Demo-#51 blieb vor Candidate-Erzeugung stehen;
  die unveränderlichen Releaseartefakte bleiben Audit-Evidence für den
  fehlgeschlagenen Qualification-Lauf.

- Fix: Der Planning-Prompt leitet sein `[TEST]`-Beispiel jetzt aus derselben
  bootstrapgebundenen Runner-Policy ab wie Precheck, Doctor und Gate 11.
  Unittest erhält ausschließlich gepunktete Python-Selektoren, Pytest darf
  Node-IDs verwenden und unbekannte Runner erhalten nur neutrale logische
  Selektoren. Der Rohbefehl wird nicht in den LLM-Prompt übernommen. Damit
  widerspricht der einmalige Retry seiner eigenen Runner-Abhilfe nicht mehr
  (#756; reales D0-Finding aus Demo-#50).

## [2.0.0a10] - 2026-09-02

- Release: Dieser Alpha-Kandidat bündelt ausschließlich die seit
  `v2.0.0a9` integrierten D0-Korrekturen für dynamische LLM-Readiness und
  runnergebundene TEST-Selektoren. Veröffentlichung, Tag-CI und
  Container-Smoke belegen noch keinen vollständigen Kundenbetrieb: #658,
  #690, #706, #714 und #756 bleiben bis zum frischen Installations-,
  Update-, Golden- und Blockiernachweis für exakt denselben Digest offen.
  Die entscheidungspflichtige Required-Check-Konfiguration aus #694 ist
  nicht Bestandteil dieses Stands und bleibt als bekannte
  Qualification-Grenze transparent.

- Release-Evidence: Annotiertes Tag `v2.0.0a10`, Gitea-Tag-CI #763,
  Prerelease #24, vier erneut byteidentisch geprüfte Assets und der frische
  digestgebundene OCI-/Compose-Smoke stimmen auf Commit
  `b750a64ad1321280a5a81b3ee790952b33a74dac` überein. Der Publish belegt
  Lieferkette und Runtime-Identität, noch nicht den offenen #658-D0-Lauf.

- Fix: Planning löst die eine wirksame TEST-Runner-Policy bereits vor
  `PlanPosted` auf und prüft Runnerinstallation sowie Selektorgrammar, ohne
  Tests auszuführen. Fehlender Runner, fehlende Toolchain oder eine
  Pytest-Node-ID bei einem Unittest-Runner verbrauchen höchstens den
  bestehenden einmaligen Retry und blockieren danach vor Candidate-Erzeugung.
  Doctor verwendet denselben Core-Resolver und nennt Policy, Runnerart und
  zulässige Selektorform; es gibt weder Umschreiben, Installation noch
  stillen Fallback (#756).

- Fix: Health wertet die effektive LLM-Routen-Readiness bei jedem Aufruf neu
  aus. Ein erfolgreicher OpenRouter-Katalog- und Benchmark-Refresh wird damit
  ohne Prozessneustart sichtbar; unbekannte Kataloglage bleibt unbekannt,
  bekannte Modellabwesenheit blockiert weiterhin ohne versteckten Fallback.
  Fehler der Readiness-Auswertung werden secretfrei und fail-closed gemeldet
  (#690).

## [2.0.0a9] - 2026-09-02

- Release: Dieser Alpha-Kandidat bündelt die seit `v2.0.0a8` integrierten
  D0-Korrekturen und den atomaren lokalen Releasepfad. Besonders betroffen
  sind die reproduzierbar ausgelieferte Git-Runtime und private
  Transportauthentisierung, aktuelle Remote-/Skeleton-/Scope-Bindung,
  robuste LLM-/Planning-Verträge, wahrheitsgemäße REST-/Dashboard-Evidence,
  die frühe TEST-Selektorvalidierung sowie getrennte Preserve-/Replace-
  Grenzen für Updates. Veröffentlichung und grüner Release-Smoke belegen
  noch keinen vollständigen Kundenbetrieb: #658 bleibt bis zum frischen
  Installations-, Golden- und Blockierlauf für exakt diesen Digest `partial`.

- Fix: Synchron bereits behandelte Commandfehler werden nicht mehr als
  erfolgreiche REST-Annahme (`202 null`) bestätigt. `ErrorMiddleware` gibt
  dafür einen redigierten typisierten Fehlerwert zurück; REST bildet ihn auf
  ein begrenztes RFC-9457-Problem mit derselben Korrelation ab. Ein fehlendes
  SCM-Ziel ergibt 404, ein Policyabbruch 409 und ein interner Fehler 500.
  Legitime Handler-Rückgabe `None` behält 202. Diagnostic-/Abort-Evidence,
  Audit und Metriken bleiben fail-closed und enthalten keine rohe Exception
  oder Providerpayload (#752).

- Fix: Der kanonische Acceptance-Contract validiert `[TEST]`-Selektoren nun
  vor `PlanPosted` mit derselben Grammar wie Gate 11. Zulässig bleiben ein
  sicherer logischer Testname oder ein sicherer Pytest-Node-ID mit `::`;
  bloße Dateipfade, Traversal und freie Argumente verbrauchen höchstens den
  vorhandenen einmaligen Planning-Retry und blockieren danach vor
  menschlicher Freigabe. Es gibt weder stilles Umschreiben noch einen
  Full-Suite- oder Runner-Fallback (#754).

- Feature: Der lokale Release-Candidate-Pfad installiert manifestgebundene
  Wheels zusammen mit dem veröffentlichten hashgebundenen Runtime-Lock in
  unveränderliche, versionierte Geschwister-venvs und aktiviert erst nach
  isolierter Prüfung von Console-Script, Paketmetadaten, Importpfad, Version
  und vollständiger Revision einen stabilen `current`-Symlink per atomarem
  Compare-and-swap. Config, Secrets, State/Evidence, Logs, Workspaces,
  Backups und reservierte Extensions liegen in getrennten Betreiberwurzeln;
  Updates überschreiben sie nicht und führen den Wizard nicht erneut aus.
  Self-Mode erhält keine Aktivierungsautorität. `install.sh` bleibt
  Entwicklungsmodus, OCI behält seinen Digestvertrag; die reale lokale
  Kundenqualification folgt erst mit einem veröffentlichten D0-Upgrade
  (#706, ADR-0706).

- Release: Das Release-Gate veröffentlicht ab dem nächsten Release zusätzlich
  `samuel-runtime-<version>.lock`, prüft ihn gegen die vorhandene Container-
  Lock-Policy und bindet ihn mit Wheel und sdist in dasselbe SHA-256-Manifest.
  Die Release Notes dokumentieren damit Herkunft, Zweck, Erstinstallation,
  Update-, Abbruch- und Rollbackgrenze des lokalen Pfads (#706).

- Docs: Die Installationsanleitung inventarisiert Betriebsarten, getrennte
  Accounts, minimale SCM-/Package-/Runnerrechte, Credentialablage und
  Widerruf sowie Preserve-/Replace-Grenzen für Produkt, Config, State,
  Workspaces und Evidence. Copy-paste-Pfade halten Token aus argv und
  Shell-History; aktive Beispiele enthalten keine private
  Referenzinfrastruktur mehr (#741).

- Fix: Workflow-Liste und -Detail verwenden dieselbe korrelationsgebundene
  Zustandsreduktion. Ein synchron erst nach seinen Folgeereignissen
  persistiertes `IssueReady` kann `PlanValidated`, Implementierungs-, Block-
  oder PR-Evidence nicht mehr zurückstufen; sichtbares Zustandsereignis und
  Zeitstempel stammen aus der fachlich maßgeblichen Evidence des neuesten
  Laufs. Ein neuer unvollständiger Lauf erbt keinen alten Erfolg (#738).

- Fix: Sichtbare Plan-Kommentare benennen `status:approved` als wirksamen
  Polling-/Webhook-Kanal und qualifizieren `ok`/`/approve` ausdrücklich mit
  der Voraussetzung eines eingerichteten SCM-Webhook-Ingress. Activity-
  Polling wird nicht länger implizit als Kommentarfreigabe dargestellt (#737).

- Fix: Planner-, Retry- und Operatorhinweise beschreiben die bereits
  unterstützten einfachen oder doppelten GREP-Pattern-Delimiter vollständig.
  Patterns mit doppelten Anführungszeichen werden außen einfach gequotet (und
  umgekehrt); nicht unterstützte Backslash-Escapes erhalten eine konkrete
  Korrekturanweisung. Die bestehende repositoryweite GREP-Grammatik wird
  weder gelockert noch erweitert (#713).

- Fix: Die auth-freie Dashboard-HTML-Shell rendert die kanonische,
  HTML-escaped Produktversion bereits serverseitig aus derselben
  Paketmetadaten-Authority wie CLI und Status-API. API-Anmeldung oder ein
  erfolgreicher JavaScript-Refresh sind damit keine Voraussetzung mehr für
  die sichtbare Versionsnummer. Die Shell wird außerdem mit `Cache-Control:
  no-store` ausgeliefert, damit ein Update keinen alten Platzhalter oder Stand
  aus dem Browsercache behält; Voll-SHA und Dirty-State bleiben weiterhin im
  authentifizierten Statuspfad (#746).

- Fix: Der gemeinsame OpenAI-kompatible Adapter wertet einen expliziten
  Truncation-Grund vor dem sichtbaren Content aus. Eine leere Antwort mit
  `length`, `max_tokens` oder `token_limit` erreicht dadurch mit realen
  Usage-Zählern den vorhandenen fail-closed Tokenlimitpfad; ohne diesen
  Providerbeleg bleibt leerer Content permanent malformed. Prompt,
  Raw-Payload und `reasoning_content` werden nicht exponiert, und es entsteht
  weder ein versteckter Retry noch eine automatische Budgeterhöhung (#744).

- Fix: Der Planning-Scope-Guard bewertet bei einem gültigen strukturierten
  Änderungsscope nur dessen `[FILE]`-Einträge als beabsichtigte
  Mutationspfade. Prosa-, Negativ- und `[TEST]`-Referenzen erweitern keine
  Schreibautorität; historische oder nicht auswertbare Pläne ohne FILE-Scope
  behalten die konservative Freitextprüfung (#742).

- Fix: Lokale Commit- und transaktionale `commit-tree`-Finalisierung verwenden
  ohne Host-/Repository-Git-Konfiguration eine stabile, ausdrücklich
  nicht-menschliche Referenzidentität. Vollständige
  `SAMUEL_GIT_AUTHOR_NAME`/`SAMUEL_GIT_AUTHOR_EMAIL`-Paare überschreiben sie;
  partielle Paare blockieren, statt Quellen zu mischen. Parent-/Tree-/Ref-CAS,
  Signierung und die Trennung von Attribution und Authority bleiben erhalten
  (#739).

- Fix: Der Skeleton-Pre-Check unterscheidet den Bestand des gebundenen
  Planning-Snapshots von einer geplanten Neuanlage. Nur ein dort noch nicht
  vorhandener und zugleich vom strukturierten Scope autorisierter Pfad wird
  nicht als Skeleton-Widerspruch bewertet; vorhandene, ungescopte oder ohne
  gebundenes `project_root` behauptete Dateien bleiben fail-closed (#735).

- Fix: Der einzige Planning-Korrekturaufruf verwendet dieselbe effektive
  `planning`-Provider-/Modellroute wie der Erstentwurf. Die Auditphase bleibt
  `planning_retry`, aber eine unbekannte synthetische Task-ID kann nicht mehr
  unbemerkt auf das globale Defaultmodell fallen (#733).

- Fix: Ein formal ungültiger erster Acceptance-Contract wird vor jeder
  Freigabeautorität mit der konkreten Parserdiagnose in den bereits
  vorgesehenen einzigen Planning-Retry gegeben. Der korrigierte Entwurf wird
  unabhängig von einer Score-Steigerung erneut kanonisch geparst; ein zweiter
  Contract- oder Pre-Check-Fehler blockiert ohne weiteren LLM-Aufruf und macht
  nur den letzten Entwurf ausdrücklich nicht autoritativ sichtbar (#731).

- Security: Private HTTP Git fetch/push uses one repository- and
  operation-bound `IGitTransportAuth` port across the worktree manager and
  core Git finalization. The installed `samuel-git-askpass` helper receives
  credentials only in the network child environment; tokens in argv,
  `http.extraHeader`, remote URLs and Git configuration plus interactive or
  credential-helper fallbacks are prohibited. Candidate/local Git processes
  remain credentialfree; same-user process-environment visibility is
  documented as a residual boundary (#729).

- Fix: Das veröffentlichte Referenz-Image liefert die vom Git-Worktree- und
  Planning-Snapshot-Pfad vorausgesetzte Git-Runtime aus einem unveränderlichen
  Debian-Snapshot mit exakter Paket- und Runtime-Version. Release-Contract und
  Schema-2-Manifest binden diese Systempaket-Policy; der Publish-Smoke prüft
  `git --version`. `samuel health`, Container-Health und Dashboard-Self-Check
  melden eine fehlende oder nicht ausführbare Git-Runtime vor einem Workflow
  mit konkretem Operatorhinweis (#727).

## [2.0.0a8] - 2026-09-01

- Fix: Planning löst den konfigurierten SCM-Base-Ref vor dem LLM auf einen
  vollständigen Commit auf und erzeugt Skeleton, Dateikontext, Suche und
  Pre-Checks ausschließlich in einem detached Snapshot dieses Commits.
  Repository, Ref, SHA und Issue-Digest werden systemseitig in Contract und
  Freigabe gebunden; fehlende Commits sowie Repository-, Issue- oder
  Base-Drift blockieren vor Candidate-Mutation und nochmals vor Commit-Wirkung.
  Lokale uncommittete oder nur lokal commitierte Inhalte sind kein Fallback
  (#714).

- Fix: Effektive LLM-Readiness wird pro tatsächlich gebauter Taskroute
  ausgewertet. Fehlende Credentials und in einem frischen OpenRouter-Katalog
  nachweislich fehlende Modelle machen Health verständlich rot; unbekannte oder
  veraltete Katalogdaten werden nicht als Live-Verfügbarkeit ausgegeben. Es
  entsteht weder ein versteckter Provider- noch Modellfallback (#690).

- Fix: Native und OpenAI-kompatible Providerfehler werden vor jeder
  Inhaltsauswertung in dieselbe begrenzte, secretfreie Fehlersemantik
  normalisiert. Planning erklärt ausgeschöpfte Providerfehler als
  Konfigurations-, Authentifizierungs-, Modell-, Rate-Limit-, Transport- oder
  Antwortproblem, ohne ein schwaches Modell durch Produktlogik umzudeuten
  (#415, #701).

- Fix: Dashboard und Runtime-Projektionen behalten Issue- und
  Workflow-Korrelation auch für gruppierte Probleme, LLM-Retries und
  abgefangene Command-/Busfehler. Security-Sichten unterscheiden externe
  Signaturverletzungen, interne Audit-Integritätsverletzungen und sonstige
  Supply-Chain-Ereignisse mit konsistenter Baseline-Severity, Auswirkung und
  Operatorhinweis (#692, #697, #711, #712).

- Fix: Planning fordert den kanonischen strukturierten Scope parsergenau an.
  Neu erzeugte Pläne ohne gültigen Scope oder mit nicht autorisierten Pfaden
  blockieren atomar vor `PlanPosted` mit einem ausdrücklich nicht autoritativen
  Kommentar. Die Scope-Creep-Erkennung gilt auch in unabhängigen
  Zielrepositories; explizite Issue-Pfade können nicht durch gleichnamige
  Dateien an anderen Orten erweitert werden. Historische ungebundene Contracts
  bleiben nur als fehlende Evidence lesbar (#695, #709).

- Documentation: README, Supporttabelle, Installation, Versionierung und
  Container-Runbook bilden den zum Dokumentcommit live veröffentlichten
  `v2.0.0a7`-Stand samt
  Tag-/Artefakt-/Manifest-Evidence ab. Release, OCI-Veröffentlichung und die
  weiterhin partielle #658-D0-Qualification sind getrennte Statusstufen; der
  pauschale `git pull`-Pfad wird bis zur Updateentscheidung #706 nicht mehr als
  qualifizierter Kundenupdateweg dargestellt (#722).

- Documentation: Die Archivierungsgrenze trennt aktive Vertragsdokumente,
  dauerhaft versionierte Historie und lokale Issue-/Audit-/Infrastruktur-
  Snapshots. Ersetzte lokale Arbeitsdateien werden dadurch nicht als neue
  Produkt-Authority in das Repository übernommen (#720).

- Documentation: Die bestehende Issue→PR-Referenz erklärt Planning- und
  Implementation-Kontext, Skeleton-/TOC-/Grep-Grenzen, jede Gate- und
  Acceptance-Semantik, Authority, Sichtbarkeit und Operator-Diagnose
  durchgängig. Kontrollmatrix und Wiki unterscheiden automatisierte Evidence
  nun ausdrücklich von der noch unvollständigen realen D0-Qualification
  (#715).

- Maintenance: Reproduzierbare Dashboard-Capture-Zwischenartefakte werden
  nicht mehr getrackt und standardmäßig unter dem ignorierten Buildpfad
  erzeugt. Die ungenutzte optionale `tree-sitter-python`-Abhängigkeit wurde
  entfernt; Python-Skeletons verwenden weiterhin den Standardbibliotheks-AST
  (#717).

- Fix: `GREP`-/`GREP:NOT`-Kriterien bleiben ausdrücklich repositoryweit und
  dürfen nach einem gequoteten Pattern keinen scheinbaren Pfadsuffix mehr
  tragen. Mehrdeutige neue Contracts blockieren vor `PlanPosted`; Planning,
  Contract-Parser und Verifier verwenden dieselbe Syntax. Ungequotete
  Mehrwort-Patterns werden vollständig statt nur bis zum ersten Wort geprüft
  (#713).

- Fix: Der synchrone Watch-Slice zählt Planning und Approval nur nach einem
  issue- und korrelationsgebundenen Erfolgsendzustand. Blockaden, Abbrüche und
  normale Command-Exceptions sowie Dispatches ohne beobachtbaren Endzustand
  erscheinen als `dispatched_failed` mit einzelnem `dispatch_outcomes`-Eintrag;
  gemischte Batches behalten ihre jeweiligen Ergebnisse. `samuel watch --once`
  liefert für einen solchen Lauf fail-closed Exit 1 statt eines Scheinerfolgs
  (#696).

- Bekannte Grenze: `v2.0.0a8` wurde konsistent veröffentlicht, scheiterte aber
  beim ersten echten Lauf in der unabhängigen #658-Umgebung vor dem Planning,
  weil die vom Worktree-Adapter benötigte Git-Runtime im Image fehlte (#727).
  Der Stand bleibt unveränderliche Release-Evidence, ist aber nicht D0-
  qualifiziert oder der unterstützte Installationsstand. Der reale Image-
  basierte Installations-, Update-, Positiv- und Blockiernachweis wird nach
  den auf `v2.0.0a9` gefundenen Korrekturbedarfen #690 und #756 mit dem
  veröffentlichten `v2.0.0a10`-Qualification-Kandidaten und dessen neuem
  Digest vollständig wiederholt; dessen Release-Smoke allein ist noch keine
  D0-Abnahme. Die semantische
  Verlässlichkeit modellgenerierter Akzeptanzkriterien bleibt getrennt in #575;
  #691, #693, #694 und #706 enthalten noch bewusste Designentscheidungen.

## [2.0.0a7] - 2026-08-31

- Fix: OpenAI-kompatible Adapter validieren Providerfehler, `choices`,
  Message und Content vor der Auswertung. Fehlerobjekte und HTTP-/Transport-
  ausgänge werden auf eine begrenzte, secretfreie Exception mit Status, Code
  und expliziter Retrybarkeit abgebildet; fehlende oder leere Antworten sind
  kein erfolgreicher Call. Planning beendet ausgeschöpfte Fehler korreliert mit
  `LLMUnavailable` und `PlanBlocked`, ohne Erfolgs-Metering oder versteckten
  Providerfallback (#698).

- Fix: Signierte JSONL-Audit-Appends verwenden auf lokalen POSIX-Dateisystemen
  den unter exklusivem `flock` neu gelesenen und verifizierten Dateikopf statt
  eines prozesslokalen HMAC-Caches. Dashboard, Container-Healthcheck und
  Einmal-CLI erzeugen damit eine gemeinsame Kette; fehlende Lock-Unterstützung
  sowie ungültige, unsignierte oder manipulierte Tails blockieren den Append.
  Fallback-Dateien bleiben getrennte Ketten und beschädigte Bestandslogs werden
  nicht automatisch repariert (#689).

## [2.0.0a6] - 2026-08-31

- Fix: Der Container-Release-Smoke stellt Data- und Workspace-Bind-Mounts
  getrennt und mit der im Image gebundenen Runtime-Eigentümerschaft bereit,
  übergibt `SAMUEL_WORK_DIR` explizit und bereinigt beide temporären Pfade.
  Der reguläre S.A.M.U.E.L.-Container bleibt nicht privilegiert. Damit kann
  der verpflichtende Digest-Smoke mit frischen persistenten Verzeichnissen
  starten; `v2.0.0a5` bleibt nach seinem fehlgeschlagenen Smoke eine
  unveränderte, nicht freigegebene Auditspur (#685/#687).

## [2.0.0a5] - 2026-08-31

- Fix: Eine gemeinsame Core-Reduktion klassifiziert echte Workflowausgänge
  jetzt konsistent für SQLite-Run-Projektion, Dashboard und Replay.
  `PlanBlocked`, reserviertes `LLMUnavailable`, `WorkflowBlocked`,
  `WorkflowAborted`, `PRCreationFailed` und
  `EvaluationSubjectInvalidated` bleiben terminal; `GateFailed`, `EvalFailed`
  und `TokenLimitHit` sind nur Stage-Evidence. Historische LLM-only-
  Projektionen werden ohne Heuristik `unbound`, nicht als Run angezeigt, und
  `samuel state reproject-runs --json` korrigiert Bestandsprojektionen
  idempotent. Nicht terminale Run-Projektionen sind von künftiger Retention
  ausdrücklich geschützt (#672/#668).

- Fix: `LLMCallCompleted` übernimmt in Planning, Implementation, gebundenem
  Healing und Review jetzt die bestehende Workflow-`correlation_id` aus einem
  gemeinsamen Core-Kontext. Standalone-Aufrufe bleiben ausdrücklich
  ungebunden markiert; interne Korrelationsdaten werden nicht als freie
  Providerparameter transportiert. Dadurch materialisiert die SQLite-
  Run-Projektion keinen zweiten künstlichen Run je LLM-Aufruf (#675/#672).

- Added: ADR-0482 Stufe 5c ergänzt in SQLite-Schema v6 einen fail-closed
  Retention-Execution-Port, persistente Kategorie-Autorität und append-only
  Ausführungsreceipts. Ausschließlich `score_derivations` besitzt eine feste
  Löschstrategie; Plan, Revalidierung, Delete und Receipt sind digest- und
  epochgebunden sowie transaktional. Alle ausgelieferten Kategorien bleiben
  `report_only`, der globale Not-Aus bleibt aktiv, und weder Scheduler noch
  produktive Löschaktivierung werden eingeführt (#673/#668/#482).

- Added: ADR-0482 Stufe 5b hebt den Runtime-State auf Schema v5 und liefert
  einen vollständigen, in beide Richtungen geprüften Retention-Katalog für 16
  State-Tabellen sowie Audit, Workspaces und Quarantäne. Kategorie- und
  Profil-/Rollendigest binden append-only Reviews; `eu_operational` ist der
  Betriebsdefault und `eu_ai_act_high_risk_support` ein Opt-in ohne
  Konformitätszusage. `samuel retention dry-run|approve|backup|replay-scores`
  bietet nicht löschende Evidence, SQLite-konsistente verwaltete Backups und
  idempotenten Score-Replay ohne Events oder EWMA-Updates. Die globale
  Notabschaltung bleibt aktiv und sichtbar; Löschvollzug bleibt ausschließlich
  Stufe 5c (#667/#482).

- Added: ADR-0482 Stufe 5a hebt den lokalen Runtime-State auf Schema v4 und
  implementiert einen unterstützten, exklusiv gelockten Restore als neue
  Autoritätslinie. Staging-Prüfung, persistierter Sentinel, atomarer Wechsel,
  global monotone Epoch und synchroner Witness führen zwingend in einen
  vollständigen Operator-Reconcile. Claims, Intents, Checkpoints, Leases,
  Workspaces und bekannte SCM-Wirkungen werden portgebunden klassifiziert;
  `scan_failed` verlangt Rescan und `unresolved` blockiert den Abschluss.
  Autoritätsereignisse tragen ab `authority.v2` UUID und Epoch. Löschende
  Retention bleibt getrennt in Stufe 5b/5c (#666/#482).

- Documentation: ADR-0482 entscheidet den offenen Stufe-5-Vertrag ohne
  Laufzeitaktivierung. Unterstützter Restore/Reconcile (5a), vollständiger
  kategorieweiser Retention-Katalog mit Dry-Run und Replay (5b) sowie einzeln
  evidenzgebundene Löschaktivierungen (5c) bleiben getrennte Changes.
  `eu_operational` ist das vorgesehene Betriebsprofil; einsatzbezogene Profile
  sind opt-in und keine Konformitätszusage. Quality-EWMA,
  Legacy-Importmarker und permanente Autoritäts-Tombstones erhalten keine
  zeitbasierte Löschung (#482).

- Fix: Nach dem einzigen Planning-Retry publiziert S.A.M.U.E.L. nur noch bei
  vollständig grünem `overall_pass` ein `PlanValidated`. Verbleibende
  Komplexitäts-Splits und sonstige Pre-Check-Fehler enden mit getrennten,
  in Audit, Dashboard und Issue-Kommentar sichtbaren `PlanBlocked`-Gründen;
  beide Pre-Check-Läufe transportieren dieselben Coverage-Felder (#655).
- Added: `MANIFESTO.md` fasst die producer-unabhängige Projekthese „Trust the
  change, not the producer“ zusammen und trennt belegten Alpha-Iststand,
  offene Roadmap, bewusste Nicht-Ziele und Mitwirkungsmöglichkeiten. Das
  Manifest ist als nicht normative Zielrichtung im Dokumentvertrag und in der
  Wiki-Startseite gebunden; Runtime-/Capability-Referenzen bleiben technische
  Authority (#642).
- Added: `python tools/wiki.py impact` liefert einen deterministischen,
  schreibfreien JSON-Bericht über stale oder nicht auflösbare Wiki-
  Content-Blöcke und ordnet betroffene Dokumentvertrag-Abschnitte ihrer
  bereits manifestierten primären Wiki-Seite zu. Der Bericht darf im dirty
  Working Tree laufen, aktualisiert keine Bindungen und ersetzt nicht die
  fail-closed Vollprüfung durch `check` (#661).
- Fix: Gebundenes Healing zählt nach `HealingAttemptStarted` auch bei Provider-,
  Truncation-, Budget- oder Authority-Finalisierungsfehlern genau einen
  fachlichen Versuch. Providerinterne Transport-Retries erhöhen diese Zahl
  nicht; bekannte Tokens einer erhaltenen Antwort bleiben in
  `HealingAborted` erhalten. Vor dem Versuch blockierte Pfade bleiben bei null
  Versuchen. Ein Ausfall der ausdrücklich advisory Prompt-Risk-Analyse strandet
  den bereits beanspruchten Versuch nicht mehr (#485).
- Security: Der Acceptance-Test-Runner löst Befehl, Timeout und Policy-Version
  ausschließlich aus dem beim Bootstrap gebundenen Control-Plane-Snapshot
  auf; Candidate-Konfiguration kann keinen beliebigen Runner-Befehl wählen.
  Die ausgeführten Tests enthalten weiterhin Candidate-Code und werden erst
  durch den getrennten Sandbox-Vertrag aus #619 prozessisoliert (#612).
- Security: Candidate-IMPORT-/TEST-Prozesse erhalten eine versionierte strikte
  Environment-Allowlist ohne geerbte SCM-/LLM-/Cloud-Secrets, `HOME` oder
  Agentinstallationspfade. Das reduziert Credential-Exposure, ist aber weder
  Dateisystem- noch Netzwerk- oder Ressourcen-Sandboxing (#613/#619).
- Maintenance: Der historische direkte Evaluation-Kompatibilitätspfad benennt
  seine konfigurierbare 90-Einträge-Vorgabe als `DEFAULT_HISTORY_MAX` und
  verwendet dieselbe Quelle im Handler; ausgelieferter Wert und Verhalten
  bleiben unverändert (#485 B2).
- Security: Required-Preflight-Gates 7b, 8, 9, 13a und 13b laufen jetzt vor
  jeder kandidatenkontrollierten Acceptance-Ausführung. Scheitert eines davon,
  werden Gate 11, übrige nachgelagerte Gates und External-Gates nicht
  ausgeführt und als `skipped_precondition` mit `passed=null` ausgewiesen.
  GateResult- und Observation-Schema v2, Dashboard, Reviewer-Briefing,
  passive Evaluation und Healing unterscheiden PASS, FAIL, ERROR, N/A und
  SKIP; ein Preflight-Block bleibt gebunden beobachtbar, aber `not_scoreable`
  und niemals heilbar. Sechs reale Fremd-Repository-Fälle binden diesen
  Vertrag zusätzlich an geschlossenes Rollout-Schema, Offline-Validator,
  Fixture-Issues und exakte Base-/Head-/Policy-/Evidence-Identitäten
  (#620/#653).

- Added: ADR-0482 Stufe 4 setzt ausschließlich gebundene
  Finalisierungszustände (`commit_pending`, `push_pending`, `gates_pending`,
  `pr_pending`) nach einem Prozessneustart fort. Die Übernahme erfolgt über
  Worktree-OS-Lock, abgelaufenes Lease-CAS, Contract-/Policy-/Schema- und
  Git-Prädikat sowie SCM-Postcondition. Commit, Push und PR bleiben durch
  persistierte Intents idempotent; Drift wird ohne Reset oder Force-Push
  quarantänisiert. Bootstrap und Watch prüfen offene Zustände, während
  `samuel resume list|inspect|attempt|resume|abandon|cleanup`, State, Health
  und Dashboard den Operatorpfad und Status bereitstellen (#633).

- Changed: Der fail-closed Authority-Port nutzt nun SQLite-Schema v3 für
  Healing-Claims, diagnostische nicht resumefähige Checkpoints,
  Commit-/Push-/PR-Intents und Lease-CAS. Jeder Übergang erhöht eine monotone
  Epoch und aktualisiert vor abhängigen Wirkungen einen separaten synchronen
  Witness; Rückstand, fremde Herkunft oder höhere Audit-Evidence führen
  sichtbar in Reconcile und blockieren Healing. Der frühere
  `bound_healing_attempts.json`-Bestand wird transaktional und checksumgebunden
  importiert und read-only archiviert. `samuel state abandon-healing` ist der
  einzige Operatorpfad zu `abandoned`. Der automatische Restore-Abgleich und
  löschende Retention bleiben ausdrücklich ADR-0482 Stufe 5 (#629/#633).

- Changed: Gebundene Evaluation-Beobachtungen, ihre versionierten
  Score-Ableitungen, nicht scorebare Terminalzustände, Quality-EWMA und die
  redigierte Dashboard-Run-Projektion liegen nun im lokalen SQLite-State-Store
  (Schema v2). Herkunft, Observation-Schema, Policy und Formel bilden getrennte
  Serien; Projektionsfehler bleiben nicht blockierend, aber über DLQ, Audit und
  State-Health sichtbar. Vier Legacy-JSON-Bestände werden einmalig,
  checksumgebunden importiert und danach schreibgeschützt archiviert; Healing-
  Autorität und Resume bleiben ausdrücklich späteren ADR-0482-Stufen vorbehalten
  (#627).

- Fix: Der synchrone Watch-Pfad unterstützt bis zu einem ausdrücklich
  implementierten Dispatcher nur `max_parallel=1`. Agent- und Workflowwert
  werden einzeln fail-closed geprüft, alle ausgelieferten Profile setzen `1`,
  und Test sowie Dokumentation behaupten weder In-Process-Parallelität noch
  Mehrprozesskoordination durch die prozesslokale Semaphore (#614; die in
  #573 belegte synchrone `try/finally`-Freigabe bleibt unverändert).
- Fix: Plan-Kommentar und `PlanPosted` leiten die sichtbare Approval-Semantik
  nun aus der aktiven Workflowkante ab. Autonome Profile zeigen ihre
  Policyfreigabe mit `awaiting_approval=false`; kontrollierte Profile warten
  weiterhin sichtbar und maschinenlesbar auf menschliche Freigabe (#582).
- Fix: Der ergänzende globale Dokument-Quelldigest erfasst nun auch die im
  aktiven Review-Inventar geführte manuelle Historie `CHANGELOG.md`.
  Inhaltsbasierte Regressionstests belegen zugleich, dass lokale/ungetrackte
  Dateien und generierte Referenzausgaben den Digest weiterhin nicht
  beeinflussen; der Digest bleibt ausdrücklich kein semantischer
  Claim-Nachweis (#596).
- Fix: Python-WRITE verwendet nun vor Verzeichnisanlage und sichtbarem Write
  denselben `ast.parse()`-Validator wie SEARCH/REPLACE und REPLACE LINES.
  Ungültige Text- und Structured-WRITEs lassen bestehende Datei oder Neuziel
  samt relevanten Metadaten unverändert; ein Retry sieht den letzten gültigen
  Stand. Vorsorgliche, nachweislich unveränderte Workspace-Snapshots werden
  freigegeben, damit ein terminaler Rollback die MTime nicht neu schreibt.
  Gate 9 bleibt die getrennte commitgebundene Syntaxautorität (#606).
- Fix: JSON-SEARCH/REPLACE- und REPLACE-LINES-Patches berechnen ihren
  Kandidaten nun schreibfrei und validieren ihn vor dem sichtbaren Write.
  Ungültiges JSON lässt Inhalt, Inode, Modus, Größe und MTime unverändert; ein
  Folge-Retry sieht den letzten gültigen Zustand. Gültige JSON-Patches und
  WRITE behalten ihre Semantik. Andere fachliche Applier-Fehlerpfade wurden
  mutationsfrei gegengeprüft; der Python-WRITE-Befund wurde getrennt in #606
  nachgeführt (#601).
- Security: Die Implementation-Patchziel-Grenze reserviert nun `.git` in jeder
  Pfadtiefe und ermittelt einmal pro Loop über Git selbst die effektiven
  absoluten Git-/Common-/Index-/Object-Pfade. Dadurch blockieren auch linked
  worktrees, separate Git-Dirs und wirksame `GIT_*`-Overrides vor Read,
  Snapshot und Write als inhaltsfreies `git_control_plane`; Config, HEAD,
  Hooks, Index und Objects bleiben außerhalb des Candidate-Diffs unverändert,
  während normale Dotfiles weiterhin patchbar sind (#603).
- Security: Strukturierte und textuelle Implementation-Patches werden nun vor
  dem ersten Apply einer Antwort vollständig auf normalisierte relative
  POSIX-Ziele innerhalb der kanonischen Projektwurzel geprüft. Absolute Pfade,
  Traversal und Symlink-Ausbrüche blockieren den Loop als
  `unsafe_patch_target` mit inhaltsfreien Reason-Codes und ohne externe
  Mutation; interne Unterverzeichnisse und Nicht-Python-Dateien bleiben
  zulässig (#600). Die getrennte Git-Control-Plane-Grenze folgt in #603.
- Fix: Der Implementation-LLM-Loop übernimmt Patches nur noch bei einem
  erfolgreichen Gesamtergebnis. Tokenlimit, No-Patch, No-Progress,
  Partial-Failure und Exceptions restaurieren alle im Loop berührten Dateien
  auf Inhalt, Existenz und Modus vor dem Lauf, ohne vorhandenen Operatorzustand
  per Git-Reset zu überschreiben. Restore-Fehler blockieren eindeutig als
  `workspace_rollback_failed` mit inhaltsfreier Evidence (#598).
- Fix: Nicht truncierte Implementierungsantworten ohne strukturiert oder
  textuell parsbaren Patch enden jetzt eindeutig als
  `WorkflowBlocked(reason=no_parseable_patches)` mit inhaltsfreier
  Runden-/Patchanzahl-Diagnose statt widersprüchlich als `complete` ohne
  Fehlerursache. Erfolgs-, Tokenlimit-, No-Progress-, Partial-Failure- und
  Git-Finalisierungspfade behalten ihre bisherigen Gründe (#588).
- Fix: Der Workflow-Drilldown bindet PR-, Gate- und Healing-Stufen an echte
  Outcomes: `CreatePR` allein bestätigt keinen PR, ein terminal blockierter
  Gate-Lauf bleibt fehlgeschlagen und verhindert eine grüne PR-Stufe, und eine
  nicht heilbare Klassifikation ohne Attempt wird als `not_attempted` statt als
  fehlgeschlagener Heilungsversuch gezählt. Korrelierte Läufe vermischen keine
  früheren PR-/Healing-Ergebnisse. Der Dev-/CI-Testvertrag enthält dafür die
  echte Tree-sitter-JavaScript-Grammatik (#578).
- Fix: Ein erfolgreich geheilter, commitgebundener Candidate entfernt
  `status:failed` nur noch dann, wenn `PRCreated` exakt zu Issue,
  Workflow-Korrelation und ursprünglicher Gate-Beobachtung des gestarteten
  Healing-Versuchs gehört. Terminale Re-Fails bleiben fail-closed und
  unkorrelierte PR-Ereignisse dürfen fremde Fehlerzustände nicht löschen
  (#587).
- Security: Der installierte Console-Entry-Point `samuel` ist nun die einzige
  unterstützte Betriebsgrenze. systemd-Generator, Platzhalter-Unit,
  Container-Entrypoint und Healthcheck verwenden ihn direkt; ein
  Fremd-Working-Directory-Test verhindert erneutes Import-Shadowing durch ein
  Zielrepository (#583).
- Fix: Serienbeschriftete Quality-Zeilen zählen nur noch den letzten, exakt zur
  aktiven Herkunfts-/Policy-/Formelserie attribuierten LLM-Call. Nicht
  auswertbare Calls und Calls aus anderen Serien werden separat ausgewiesen,
  statt den aktiven Denominator still zu vermischen (#589).
- Fix: Der Bootstrap löst Workflow, Gate-Profil und Healing-Route nun vor dem
  Runtime-Wiring als eine Autoritätsmatrix auf. Gebundene Standardläufe
  akzeptieren nur `default`/`audit`; Legacy und Self sind geschlossene Profile,
  die `SAMUEL_GATES_PROFILE` nicht in einen Mischzustand versetzen kann (#579).
- Fix: Automatische, commitgebundene Acceptance-Resultate liefern nun
  strukturierte Verifier-Evidence für das einmalige Evidence-Healing; eine
  reale Verifier→Gate-11→Healing-Integration verhindert synthetisch grüne
  Klassifikation (#581).
- Fix: Das Manual-LLM-Dateiprotokoll publiziert PID-Sidecar und vollständigen
  JSON-Request nun per Same-Directory-Rename atomar; Consumer können keine
  sichtbare partielle Request-Datei mehr lesen (#585).

### Changed

- **#399 Freigabeautorität vollständig an den gebundenen Gate-Lauf
  verschoben.** Der ausgelieferte Workflow führt `CodeGenerated` direkt in
  das profilierte `EvaluationSubject`; Evaluation speichert dessen terminale
  Evidence idempotent und publiziert nur noch versionierte, nicht bindende
  Qualitätsbeobachtungen. Gate 4/10, Score-Schwelle, Bestmarke und
  Self-Parity besitzen im Zielmodus keine Autorität. Healing verwendet genau
  einen kriteriumsweisen Gate-11-Evidence-Versuch am fehlgeschlagenen Head.
  Ein atomarer Legacy-Rollback bleibt nur bis `2.0.0a4`; das Folgerelease
  verlangt reale Rollout-Evidence.

### Fixed

- **#485 Gate-Fallback meldet die tatsächlich wirksamen Schema-Defaults.**
  Fehlt `gates.json`, unterscheidet die Laufzeitmeldung nun Required-,
  Optional- und Disabled-Gates, statt fälschlich alle Gates als erforderlich
  auszuweisen. Die Werte werden aus derselben Schema-Instanz protokolliert,
  die anschließend verwendet wird, und sind durch einen Regressionstest
  gegen erneute Meldungs-/Konfigurationsdrift geschützt.

### Documentation

- **#649 Wiki-Seiten als eigenständig lesbare, gebundene Projektionen.**
  Alle zehn Seiten enthalten nun deterministisch ausgewählte Kernabschnitte
  oder aufgelöste Runtime-Facts statt nur Überschriftenindizes. Stabile
  Content-Block-IDs sowie Quell-, Klassen- und Fact-Digests blockieren stale,
  mehrdeutige oder nicht auflösbare Projektionen. Code, Konfiguration und
  aktive Dokumente bleiben die einzigen gepflegten Quellen; lokales, Gitea-
  und späteres GitHub-Wiki bleiben generierte Zielartefakte.
- **#572 Laufzeitdokumentation abschnittsbezogen an ihre Quellen gebunden.**
  Der vorhandene Control-Matrix-Check klassifiziert alle aktiven Dokumente,
  erzeugt Runtime- und ADR-Referenzen aus Code und ausgelieferter
  Konfiguration und weist betroffene Quellen, Proofs und Reviewregeln per
  Impactbericht aus. Exakte AC-Tags, Gate-Profile, Schwellen,
  Workflowübergänge und Persistenzartefakte ersetzen manuell driftende
  Tabellen; lokale Pfade, Links, Anker und ADR-Supersession werden
  fail-closed geprüft.
- **#573 Semaphore-Lebensdauer an den synchronen Watch-Pfad angeglichen.**
  Die aktive Architektur beschreibt nun die reale Slot-Belegung vor dem
  Dispatch und die Freigabe im jeweiligen `try/finally`, statt nicht
  vorhandener Terminalevent-Subscriptions und `release_slot()`-Verdrahtung.
- **#485 Aktive Dokumentation gegen den ausgelieferten Stand abgeglichen.**
  Gate-, Port-, Event-, Slice- und Adapterinventar, ContractScope-Schema,
  Persistence-Pfade, Self-Mode-Arbeitsweg sowie Retention-, PII-, Transport-
  und Human-Oversight-Grenzen entsprechen wieder Code, Konfiguration und
  Tests. Neue Regressionstests schützen die maschinenprüfbaren Angaben.
- **#567 Wiederkehrende Duplicate-ARP-Evidence ergänzt.** Der Runner-Vertrag
  dokumentiert die korrekte und die konkurrierende MAC, den erneuten
  TCP/22-Ausfall sowie die unveränderte Abgrenzung von Betreiberinfrastruktur
  und registry-/SCM-neutralem Produktpfad.

## [2.0.0a3] - 2026-08-27

### Changed

- **#555 Container-Releases digest- und lockgebunden vorbereitet.** Ein
  digestgebundenes `linux/amd64`-Basisimage, getrennte hashgeprüfte Build- und
  Runtime-Locks, ein enger Build-Kontext und ein registry-neutraler
  Publish-/Smoke-Pfad binden OCI-Identität und Manifest an Produkt-Tag und
  vollständigen Commit. CI weist Input-/Lock-/Dockerfile-/Compose-Drift
  offline ab. Ein Image gilt erst nach Push, Digest-Auflösung, frischem
  Compose-Health und passendem Dashboard-Buildstatus als veröffentlicht;
  `v2.0.0a2` bleibt unverändert ohne Container-Image. Der veröffentlichte
  Stand `v2.0.0a3` erfüllt diesen Vertrag mit einem Schema-2-Manifest und dem
  unveränderlichen Registry-Digest
  `sha256:6a9c53ae5ba554a5b000e140f3a0929447984f230c9e50a1e5ce9c07d06dc5f6`.

- **#488 Produktversion aus Produkt-Tags abgeleitet.** `setuptools-scm`
  akzeptiert ausschließlich strikte `v<Version>`-Tags; Phasenmarker bleiben
  ohne Einfluss. Exakte Tags, Entwicklungs- und Dirty-Stände, sdist/wheel
  sowie der ehrliche metadatenlose Fallback `0+unknown` sind automatisiert
  gegengeprüft. `samuel.__version__` bleibt aus den installierten
  Paketmetadaten abgeleitet; ein statischer Parallelwert wurde entfernt.

## [2.0.0a2] - 2026-08-26

### Fixed

- **#490 Annotiertes Tagobjekt im Gitea-Tag-Checkout erhalten.**
  `actions/checkout` ersetzte im ephemeren Job trotz vollständigem Fetch den
  lokalen annotierten Tag-Ref durch den direkten Commit. Das Post-Tag-Gate
  stellt nun ausschließlich den gleichnamigen Remote-Tag wieder her, prüft
  dessen Objekttyp erneut und bleibt bei fehlendem oder leichtgewichtigem Tag
  fail-closed. `v2.0.0a1` bleibt als unveränderliche, vom Gate abgewiesene
  Auditspur ohne Gitea-Release bestehen. `v2.0.0a2` wurde nach vollständig
  grüner Tag-CI als erstes Gitea-Prerelease mit manifestgebundenem Wheel und
  sdist veröffentlicht.

## [2.0.0a1] - 2026-08-25

### Changed

- **#490 Ersten formalen Produkt-Release abgesichert.** Der vorhandene
  Changelog-Pfad nimmt standardmäßig nur kanonische Produkt-Tags als Grenze;
  historische Phasenmarker bleiben explizit anwählbar. Ein gemeinsames
  Pre-/Post-Tag-Gate bindet den sauberen `main`-Commit, annotierten Tag,
  Changelog, Paketmetadaten, Python-API, CLI, Dashboard sowie frische Wheel-/
  sdist-Artefakte an `v2.0.0a1` und schreibt ein SHA-256-Manifest. CI prüft
  Python 3.10 und 3.14 vor dem bestehenden Required Check. Der Docker-
  Quellbuild hat einen engen Kontext und OCI-Version/Revision, ist aber noch
  kein veröffentlichtes, bitreproduzierbares Release-Image; der dafür
  erforderliche Digest-/Lock-Vertrag ist #555 zugeordnet.
- **#489 Versionsflächen und Buildidentität vereinheitlicht.** Paketmetadaten,
  `samuel.__version__`, `samuel --version`, Dashboard-Status und
  produktbezogene Audit-Attribution verwenden denselben normalisierten
  Produktstand. Eine vollständige Commit-Revision und ein möglicher
  Dirty-State bleiben davon getrennte Build-Evidence; `samuel doctor`,
  Dashboard, Plan-Metadaten, PR-Attribution und Commit-Trailer weisen sie aus.
  Ohne Paket- oder SCM-Metadaten wird kein plausibler Release erfunden.
- **#487 Versionspolitik festgelegt.** `docs/VERSIONING.md` verbindet die
  Bedeutung von MAJOR/MINOR/PATCH mit kanonischer PEP-440-Syntax, trennt
  Produkt-, Build-, API-, Event-, Konfigurations-, Dokument-, Prompt-/Modell-
  und Fremdformatversionen und ordnet `2.0.0a0` als ungetaggte Baseline ein.
  Der erste formale Produkt-Tag ist nach den Release-Gates `v2.0.0a1`;
  `SECURITY.md` behauptet bis dahin keine veröffentlichte Supportlinie.
- **#477 Entitlements und parallele Premium-Pfade entfernt.** Ed25519-
  Lizenzprüfung, Feature-Tokens, Issuer-Werkzeuge, Premium-/Free-Anzeigen, der
  alte Bootstrap-Router und der unverdrahtete `TokenLimitHandler` sind
  ersatzlos entfernt. Task-Routing und validierte Schedules laufen über die
  vorhandene LLM-Adapterkette; Dashboard- und Prompt-Schreibwege bleiben durch
  API-Key und serverseitige Eingabevalidierung geschützt. Das aktive
  Call-Ausgabelimit bleibt erhalten; ein davon verschiedenes kumulatives
  Token-/Kostenbudget wird nicht behauptet und ist als Designvertrag #549
  erfasst. `cryptography` bleibt nur im `github`-Extra für RS256-App-Auth.
- **#476 Apache-2.0 konsistent ausgewiesen.** Der unveränderte Lizenzvolltext
  liegt als Root-`LICENSE` vor. PEP-639-/SPDX-Paketmetadaten deklarieren
  `Apache-2.0` und nehmen die Datei in Wheel und sdist auf. Der Geltungsbereich
  umfasste auch den damals noch vorhandenen Inhalt von `samuel/premium/`; die
  davon getrennte alte Laufzeitfreischaltung wurde anschließend mit #477
  entfernt.
- **#529 Contract-Scope commitgebunden durchgesetzt.** Acceptance Contract
  Schema v2 enthält einen versionierten FILE-/PATH-Scope. Required Gate 7b
  prüft die vollständige Changed-File-Liste desselben EvaluationSubject;
  optionale Erweiterungen stammen ausschließlich aus `architecture.json` und
  dessen Inhalt ist Teil des Policy-Digests. Fehlende, stale, mehrdeutige oder
  nicht kanonische Scope-Evidence blockiert. Renames werden als alter und neuer
  Pfad geprüft; die frühere Plan-/Basename-Heuristik entscheidet nicht mehr
  über den Merge-Pfad.
- **#514 MANUAL-Akzeptanzkriterien eindeutig getrennt.** `[MANUAL]` erzeugt
  jetzt `ACManualPending` mit `passed: null`/`status: manual_pending` statt
  eines automatischen Fehlschlags. Verifier, Scoring und Evaluation führen
  getrennte automatische und manuell ausstehende Zähler; Self-Parity nutzt
  die automatischen Werte. Die vorhandene Workflow-Detailansicht zeigt PASS,
  FAIL und MANUAL PENDING getrennt. Commitgebundener Contract und
  menschlicher Review-Receipt bleiben #519.

### Refactored (Compliance)
- **#373 AI-Act-`obligation` kontextabhaengig von der Deployment-Risikoklasse.**
  Das statische `obligation`-Feld pro Artikel (aus #366) kodierte die Annahme
  "SAMUEL ist immer Limited Risk" — was nur den Self-Mode beschreibt. SAMUELs
  Zweck ist aber die Ueberwachung fremder, teils hochriskanter Host-Projekte;
  dort sind Art. 12-15 Pflicht, und SAMUELs Kontrollen sind deren
  Compliance-Instrumente.
  - `ai_act.json`: `obligation` → `applies_to` (Adressatenkreis; Art. 50 →
    `all`, Art. 12-15 → `high_risk`); Artikel-Beschreibungen risikoklassen-
    neutral. Loader validiert `applies_to` fail-loud.
  - `samuel.core.ai_act`: neue `deployment_risk_class()` (env `SAMUEL_RISK_CLASS`,
    Default `limited_risk`), `obligation_for(article, risk_class)` und
    `ai_act_articles(risk_class)`. Statische `AI_ACT_ARTICLES`/`AI_ACT_OBLIGATIONS`
    entfallen (Wert ist jetzt abgeleitet, nicht gespeichert).
  - Dashboard: `get_compliance_legend()` liefert abgeleitete Obligationen +
    `ai_act_risk_class` (+ `_source`); Compliance-Tab zeigt die aktive
    Risikoklasse und faerbt die Pflicht/freiwillig-Badges entsprechend.
  - **Im Dashboard editierbar:** Dropdown im Compliance-Tab persistiert die
    Klasse nach `config/compliance.json` (POST `/api/v1/settings/risk-class`,
    `DashboardHandler.set_risk_class`). Aufloesungs-Prioritaet env
    `SAMUEL_RISK_CLASS` > persistierter Wert > Default; bei env-Fixierung ist
    der Selektor read-only.
  - `docs/AI_ACT_COMPLIANCE.md` §1/§3/§5 neu gerahmt (Self- vs. Deployment-
    Sicht, `SAMUEL_RISK_CLASS`). Self-Mode-Default unveraendert: Art. 50
    Pflicht, Art. 12-15 freiwillig.


- **#290 OWASP-Taxonomie auf 2026-offiziell umgestellt (A01..A10 → ASI01..ASI10).**
  `samuel/core/compliance/owasp.json` enthaelt jetzt die 10 ASI-Kategorien aus
  dem Dezember-2025-OWASP-Release. 89 `(cat, evt) → risk_class`-Mappings sowie
  16 Cat-Fallbacks wurden re-klassifiziert. `samuel.core.owasp` exportiert
  zwei neue Maps fuer Backward-Compat mit historischen Audit-Logs:
  - `OWASP_LEGACY_KEY_MAP` — alte Risk-Class-Keys
    (`unrestricted_agency`, `excessive_autonomy`, ...) auf ihre
    ASI-Aequivalente
  - `OWASP_LEGACY_ID_MAP` — alte IDs (`A01`..`A10`) auf
    `ASI01`..`ASI10`
  Plus neue Funktion `owasp.resolve_legacy_key()`. Dashboard
  (`get_security_overview`, `get_tamper_events`) wurde so umgebaut, dass
  alte Audit-Eintraege weiter im richtigen ASI-Bucket landen.

  **Kategorie-Mapping (alte A0X → neue ASI0X):**

  | Alt | Neu | Begruendung |
  |---|---|---|
  | A01 Unrestricted Agency | **ASI03** Identity & Privilege Abuse | Schranken-Uebergehen ist Privilege-Eskalation |
  | A02 Uncontrolled Behavior | **ASI01** Agent Goal Hijack | Workflow-Entgleisung = Goal-Drift |
  | A03 Inadequate Sandboxing | **ASI05** Unexpected Code Execution | Sandbox-Probleme sind RCE-Vehikel |
  | A04 Broken Trust Boundaries | **ASI04** Agentic Supply Chain | Modul-Grenzen-Verletzung + destruktive Merges |
  | A05 Identity & Access Abuse | **ASI03** Identity & Privilege Abuse | 1:1-Mapping |
  | A06 Unmonitored Activities | **ASI08** Cascading Failures (Default), z.T. ASI03/ASI04 (event-spezifisch) | A06 hatte kein direktes ASI-Pendant; Audit-Luecken kaskadieren bevor sie sichtbar werden |
  | A07 Unsafe Tool Integration | **ASI02** Tool Misuse | 1:1-Mapping |
  | A08 Excessive Autonomy | **ASI01** Agent Goal Hijack | Autonomie ohne Mandat = Goal-Drift |
  | A09 Inadequate Feedback Loops | **ASI08** Cascading Failures | Schwache Eval-Loops lassen Fehler kaskadieren |
  | A10 Opaque Reasoning | **ASI09** Human-Agent Trust Exploitation | Authority-Bias-Klassiker |

  Mehrere alte Kategorien (A01+A05 → ASI03, A02+A08 → ASI01) fallen auf
  dieselbe ASI-Kategorie. Das ist gewollt — die ASI-Taxonomie ist anders
  geschnitten; einzelne Events landen je nach konkretem Verhalten in
  unterschiedlichen ASI-Buckets. ASI06 (Memory & Context Poisoning) und
  ASI07 (Insecure Inter-Agent Communication) sind in SAMUEL heute noch
  nicht populated (kein produktiver Memory-Layer, Single-Agent-Setup) —
  reserviert fuer kuenftige Erweiterungen.

  Audit-Trail-Historie (JSONL-Logs ab 2026-04) bleibt voll lesbar — der
  Dashboard-Security-Tab und `get_tamper_events` loesen alte Keys/IDs
  transparent auf neue ASI-Aequivalente auf.

### Fixed (Compliance)
- **#366 EU-AI-Act-Klassifikation konsistent gemacht** — Limited-Risk-
  System darf nach VO 2024/1689 nicht gleichzeitig Art. 12/14/15/86 als
  `Pflicht erfuellt` ausweisen; diese Artikel adressieren ausschliesslich
  Hochrisiko-KI-Systeme. Bereinigung:
  - `samuel/core/compliance/ai_act.json` — neues `obligation`-Feld pro
    Artikel (`required` fuer Art. 50, `voluntary` fuer Art. 12/13/14/15)
  - `samuel/core/ai_act.py` — neue Map `AI_ACT_OBLIGATIONS`; Schema-
    Validation prueft `obligation` als required-Field
  - `samuel/slices/privacy/ai_act.py` — `RISK_CLASSIFICATION` strikt
    getrennt in `mandatory_obligations` (nur Art. 50) und
    `voluntary_practices` (analog Art. 12/14/15 als freiwillige
    High-Risk-Standards). Alte Felder `transparency_measures` und
    `human_oversight` entfernt (Begriffsverwirrung)
  - `docs/AI_ACT_COMPLIANCE.md` — komplette Umformulierung. Art. 86
    raus aus AI-Act-Kontext (gehoert zu Hochrisiko-Anhang-III oder als
    DSGVO Art. 22 in `docs/DSGVO_VVT.md`)

### Refactored
- **#357 Prompt-Konfiguration konsolidiert** — Variante-Dropdown im
  System-Prompts-Edit-Modal entfernt. Per-Provider-Zuweisung erfolgt
  ausschliesslich ueber `tasks.<task>.system_prompt_by_provider` im
  Task-Editor (#351). Modal-Save schreibt immer in `config/llm/prompts/<name>`
  (Library). Die backend-seitige Cascade auf `provider/<X>/<file>.md` und
  `model/<Y>/<file>.md` bleibt funktional als Backward-Compat fuer
  bestehende Operator-Files.

## How this file is generated

Phasen-Eintraege (Phase 0a - Phase 13) werden manuell beim Phasen-
Abschluss ergaenzt. **Issue-basierte Eintraege ab Phase 14** werden
automatisch ueber das CLI generiert (#163):

```bash
# Default: alle Eintraege seit dem höchsten erreichbaren Produkt-Tag
samuel changelog

# Seit einem bestimmten Tag oder Phasen-Marker
samuel changelog --since v2.1
samuel changelog --phase 13           # mappt auf Tag 'phase-13-complete'

# In Datei schreiben statt stdout
samuel changelog --out CHANGELOG_DELTA.md

# Zusaetzlich als Kommentar zu einem Tracking-Issue posten
samuel changelog --phase 13 --post-to-issue 250
```

Phasenmarker werden nur über das ausdrückliche `--phase` berücksichtigt. Eine
Ausgabe mit `--out` ist immer eine Delta-Datei zur menschlichen Übernahme und
darf nicht direkt den vollständigen historischen `CHANGELOG.md` ersetzen.

Der Aggregator parst conventional-commit-Subjekte (`feat`, `fix`,
`refactor`, `perf`, `docs`, `chore`, ...) zwischen Start-Revision und
HEAD, gruppiert per Issue-Ref `(#NNN)`, und uebergibt das Ergebnis an
den bestehenden ``ChangelogCommand``-Handler. Commits ohne Issue-Ref
werden uebersprungen — die Repo-Konvention verlangt
`<type>(scope)?: <title> (#<issue>)`.

## [2.0.0-alpha] - 2026-04-17

### Phase 0a: Vorarbeiten
- Pre-commit hooks und Test-Konventionen

### Phase 0b: Shared Kernel
- Event-Bus, Commands, Config, Ports, Types

### Phase 1: Audit-Trail
- JSONL-Audit-Sink mit Rotation und Correlation-IDs

### Phase 2: SCM-Port
- IVersionControl, GiteaAdapter, IAuthProvider

### Phase 3: LLM-Port
- ILLMProvider, CircuitBreaker, SanitizingAdapter

### Phase 4: Planning-Slice
- PlanIssueCommand, 3-Stufen LLM-Qualitaetskontrolle

### Phase 5: Implementation-Slice
- IPatchApplier-Registry, Resume mit WorkflowCheckpoint

### Phase 6: PR-Gates-Slice
- 14 PR-Gates, config/gates.json

### Phase 7: Evaluation-Slice
- Eval-Score-History, Baseline-Threshold

### Phase 8: Watch, Healing, Dashboard + restliche Slices
- 23 Slices komplett, Semaphore-kontrollierte Parallelitaet

### Phase 9: Aufräumen
- v1-Dateien entfernt (commands/, plugins/)
- v1→v2 Mapping-Test
- Sequence-Validator

### Phase 10: Server-Hook + Flexibilität
- Gitea pre-receive Hook
- GitHubAdapter + GitHubAppAuth
- IQualityCheck Registry (Python, TypeScript)
- Skeleton-Builder (Python, TypeScript, Go, SQL, Config)

### Phase 11: Compliance
- PromptSanitizer (PII-Scrubbing)
- TransferWarning (Drittland-Transfer DSGVO)
- AI-Attribution-Trailer (EU AI Act Art. 50)
- DSGVO VVT, AI Act Technical Documentation

### Phase 12: Hardening
- Dockerfile + docker-compose.yml
- pyproject.toml mit allen Extras
- TLS-Verify konfigurierbar
- MetricsMiddleware

### Phase 13: Vergessenes & Konzeptfehler
- E7 Code-Injection Fix (AC-Tag Sanitization)
- M3 Semaphore-Leak Fix
- OpenRouter Pricing Integration
- 6 neue Events, 4 Config-Bereiche externalisiert
