# Current Product Status

[Produkt](../../README.md) · [Technischer Überblick](../TECHNICAL_OVERVIEW.md) · [Dokumentwege](../README.md)

## Gegenwärtige Einordnung — 18.11.2026

Die Produktfunktionen und ihre Grenzen sind in der
[Advanced-Referenz](../README_technical.md) und der
[Capability-/Wirksamkeitsmatrix](../CAPABILITY_MATRIX.md) beschrieben.
Implementierung, aktive Profilwirkung, Regression und reale Qualification
bleiben getrennte Aussagen. Zielbilder in ADRs ersetzen keinen Betriebsnachweis.
S.A.M.U.E.L. bleibt im Alpha-/Referenzstadium; ein Dokumentmerge erteilt keine
Produktions-, Isolations-, Support- oder regulatorische Freigabe.

Die Dokumentation verwendet drei verbindliche Verständnistiefen: Produkt,
technischer Überblick und Advanced-Details. D1–D10 aus #1003 sind auf Main
`ededfccc8bf9cff7216a74c01ab6859e38bb8a18` integriert. D11 besitzt unveränderte
Modellantworten und benötigt weiterhin echte menschliche Verständlichkeitsabnahme.
Die 26 zusätzlich vorgesehenen ursprünglichen Free-Modellantworten sind durch
Maintainerentscheidung abbestellt, nicht bestanden. Die autorisierten späteren
Qualitätsarbeiten behalten ihre eigenen Prüfungen und Integrationsgrenzen.
Aktuelle Arbeitszustände werden im nativen EPIC einschließlich Kommentaren geführt.

Für die getrennte Testinstallation ist der private Alpha-Prerelease **v2.0.0a39** verfügbar. Die [Abnahme der veröffentlichten Artefakte](#alpha-testrelease-v200a39) nennt die konkrete Bindung und den erreichten Umfang. Die [öffentliche Projektion](../github/GITHUB_SYNC_READINESS.md) hat einen eigenen Auslieferungsstand.

Heute relevante Sicherheitsgrenzen bleiben sichtbar: lokale IMPORT-/TEST-
Ausführung ist keine allgemeine Prozesssandbox, externe Evidence besitzt nur
die dokumentierte Annahmeauthority, Score bleibt passiv und Compliance-Mappings
sind keine Konformitätsabnahme. R25 verlangt nach explizitem Replan eine neue
menschliche Freigabe. Mit #920 erzwingt der gemeinsame Wiederanlaufpfad diese
auch in autonomen Profilen; die getrennte Live-Abnahme steht noch aus. Details stehen im
[CLI-Vertrag](../README_technical.md#argumente-voraussetzungen-und-ergebnisgrenzen).
Eigenständige Operatorabnahmen wie #985 werden nicht durch Dokumentation ersetzt.

## Alpha-Testrelease v2.0.0a39

Die interne Alpha v2.0.0a39 wurde auf einem frischen Dockerhost aus den veröffentlichten privaten Releaseartefakten installiert. Die Abnahme umfasste die Administratoraufnahme, das Dashboard, die Modellkonfiguration und die Wiederherstellung derselben Version.

Die installierte Instanz hat einen realen Änderungsauftrag bearbeitet. Nach der Freigabe des Plans setzte das konfigurierte Modell eine Codeänderung um. Tests, Sicherheitsprüfung, Pull Request, CI, unabhängiges Review, geschützter Merge und signiertes Audit wurden geprüft. In einem separaten Negativtest verhinderte ein fehlgeschlagener Pflichtcheck den Merge.

Die Quellprojektion umfasst den nach der Produktabnahme integrierten Dokumentationsstand sowie die separat integrierte Korrektur der Warteansicht im Dashboard. Für die technische Prüfung des Installers kam ein Test-Vertrauensanker zum Einsatz. GitHub ist als Plattform für die spätere offizielle Distribution ausgewählt. Die technische Qualifikation des HTTPS-Kanals für Installation und Updates sowie die unabhängige Erstbestätigung des Bootstrap-Vertrauensankers stehen aus. Der Betreiber hat diese Erstübergabe aus den Abschlusskriterien der internen Alpha-Abnahme herausgenommen. Das spätere Distributionsvorhaben führt die technischen Nachweise weiter. Diese Veröffentlichung umfasst Quellcode, Wiki und die Übersicht der Produktthemen.

## Entwicklung des Einzelprojekt-Lifecycles #1090 — 15.11.2026

Die folgenden Zwischenstände dokumentieren die damaligen Anforderungen und Befunde. Für die Abschlusskriterien zur Erstübergabe und die Plattformwahl gilt die [Betreiberentscheidung vom 19.11.2026](#alpha-testrelease-v200a39).

Der [Beta-Auftrag](../CONTAINER_RELEASE_OPERATIONS.md#1090-beta-lifecycle-auftrag)
bleibt eine Installation pro Codebasis: Dashboardkonfiguration und
Updatevorbereitung, privilegierte Aktionen über den vorhandenen Operator-CLI.
Kein neuer privilegierter Helfer und kein öffentlich veröffentlichtes Folgerelease.

### Abschlussaudit und interner Releasekandidat — 16.11.2026

Der Folgeauftrag zu #1090 verlangt eine eigene Abnahme veröffentlichter
Artefakte. Ausgangspunkt des repositoryweiten Audits ist Main
`c5d38b4c2b1aeaea230435aea32d6ae4aad68320`. Der zunächst geplante interne
a35-Testkandidat hat inzwischen ein Tag und internes OCI-Image, bleibt aber
wegen des nachstehenden realen Dashboard-Gate-FAILs unveröffentlicht.
Ein Changelog, Commit oder Build ist keine Veröffentlichung. Es wird kein neuer
Golden-/D0-, Beta-Reife- oder Supportclaim abgeleitet.

### a38 und zukünftige Update-Baseline

Der interne Kandidat `v2.0.0a38` auf
`6d4e122c7dc23ada990b7165f771b5c0a8ce77f9` hat seine Vorabprüfung mit dem
lokalen Image einschließlich Dashboard, echter Reauthentisierung, Promptprofilen
und signiertem Audit bestanden. Die Veröffentlichung ist bedingt freigegeben.
Zwei lokale Builds hatten dieselben fünf Basis-Layer, dieselben 383
Wheel-Dateiinhalte und denselben Python-Bytecode. Zeitstempel, ZIP-Metadaten
und Paketmanagerdateien unterschieden sich. Am 18.11.2026 wurde der Commit mit
dem annotierten Tagobjekt `9c9ba37009e4fc256742ca7bff28e6d43edf235e` gebunden.
Die Betreiberfreigabe verlangt die Prüfung des konkreten Publisherimages vor
dem internen Push und den anschließenden Abgleich mit dem Registry-Manifest.
Im ersten Durchlauf der Tag-CI (#1614, Job 4638) beendete der Testclient die
Viewer-Anmeldung nach zwei Sekunden. Der Server erreichte die erfolgreiche
Login-Antwort und traf beim Schreiben auf die geschlossene Verbindung. Dieser
Fehlversuch bleibt eigenständig dokumentiert. Beide Varianten desselben Tests
bestanden anschließend lokal auf dem unveränderten Commit.
Unter Python 3.14.7 (Job 4639) hielt die Wartungs-CLI bereits beim Aufbau des
Installationszustands mit `StateStoreError` an. Der Zieltest für abgewiesene
Updateaufnahme wurde dadurch nicht erreicht. Der Log enthält keinen State-Code.
Beide Matrixjobs endeten mit je 5.037 bestandenen Tests, einem Fehler und fünf
übersprungenen Tests. Lint und Release-Gate wurden übersprungen. Für a38 gab es
keinen Publisher-Build, Registry-Push oder privaten Prerelease. Das Tag bleibt
erhalten. Der Betreiberauftrag vom 18.11.2026 umfasst einen Nachfolger unter
seinen eigenen Pflichtgates. Commit, geprüfte Distributionsdateien, Image und
frische Releaseabnahme werden jeweils an diesen Nachfolger gebunden.

Bei einer gezielt gehaltenen SQLite-Schreibsperre im isolierten lokalen
a38-Vorabimage blieb die Wartung auf `pending`. Obwohl der CLI-Abschlussmarker
fehlte, trug das signierte Audit für diese Vorgangskennung einen Abschluss ein.
Erst der explizite Wiederholungsaufruf mit derselben Installationsbindung war
erfolgreich. Der lokale Docker-Versuch verwendete das Vorabimage. Der genaue
Fehlercode des früheren Tag-CI-Laufs lässt sich daraus nicht ableiten.

Im isolierten Vorabtest blieben der geänderte Prompt und das aktive Modellprofil
über einen echten Neustart erhalten. Beim State-Restore waren Reconciliation,
explizite Identity-Recovery und manueller Start erforderlich. Anschließend stimmten
State- und Witness-Epoche überein, die signierte Auditkette enthielt 119 Einträge.
Die Neuinstallation aus tatsächlich veröffentlichten Artefakten und ein vollständiges
reales Test-Issue mit gültigen Freigaben, funktionierendem Ergebnis, abgewiesenem
unzulässigen Merge und Audit stehen aus. Eine zukünftige Update-Baseline ist offen.
Die datierten a34–a37-Nachweise unten sind historisch. Eine erneute Migration dieser
Alpha-Stände gehört nicht zur geltenden Abnahme.

### a37 vor dem Tagging gesperrt — 17.11.2026

Am freigegebenen Commit `bca883f4beda2a4e1805b1bbd5c859c7d0ec7d1c`
ersetzte eine verspätete echte Antwort auf die Sitzungsliste das Passwortfeld.
Die bereits eingegebene Zeichenfolge verschwand vor der Reauthentisierung.
Der zusätzliche Vorabtest sperrt den Kandidaten vor Tag und Veröffentlichung.
Die erfolgreichen Teilnachweise und die früheren a35-/a36-Fehler bleiben erhalten.

### a36-Entwurf durch Prompteditor-Gate gesperrt — 16.11.2026

Der ausdrücklich freigegebene Kandidat `v2.0.0a36` gehört zu Commit
`27a800395fc51e4fbdebf78427a67405fc2473d0`, annotiertem Tagobjekt
`b6ab6e99c2ae117d6300607e043976c56c9b1b8f` und internem OCI-Digest
`sha256:faa5bcbb2e7831469b095a56cc845cb6a281f1f16409cea965717663ea89993d`.
Manifest-SHA256: `455eebbc177a3f6a7a961587c24b6a5bfb00579ec14309fd407c5920c66eac9b`.
Main-CI #1600 und alle vier Tag-CI-Jobs #1601 bestanden; die drei Testsuiten
melden je 5016 PASS / fünf SKIP. Das separate tatsächliche OCI-Pythoninventar
umfasst 32 geprüfte Pakete ohne Skip und ohne bekannte Findings; kein voller
Security-PASS. Die sieben Assets des privaten **Entwurfs 50** wurden unabhängig
bytegenau zurückgelesen. Es gibt keinen veröffentlichten nativen a36-Release.

- Ein erster VM-Versuch scheiterte vor jeder Produktinstallation am SSH-Banner-
  Timeout der Testumgebung. Seine irreführende Wartungsfehlermeldung wurde anhand
  des erhaltenen stderr korrigiert. Das ist kein Produkt-PASS und kein Nachweis
  laufender OS-Wartung. Der alte Subject bleibt erhalten.
- Neuer Subject `draft-empty-host-vm-bbj1j39i`: leerer Dockerhost,
  Administratoraufnahme, ausdrückliche Rollenvergabe, Dashboard-SCM-/Projekt-
  konfiguration und Production-Start bestanden mit genau zwei Anwendungsaufrufen.
- ConfigurationSession bestand mit realer Änderung einer manuellen LLM-Testroute
  und eines Prompts, frischer Reauth und Apply ohne Runtime-Neustart. Eine echte
  alte Sitzung wurde mit 401 zurückgewiesen; genau ein neuer GET unter den
  rotierten Cookies erhielt 200. Die veraltete Anmeldemaske blieb geschlossen.
  Allgemeine Production-Schreibversuche blieben mit 409 gesperrt.
- **Required Prompt-Gate FAIL:** Provider-Ebene bestand; bei der Modell-Ebene
  entsprach der aktive Inhalt nicht der eingegebenen Änderung. Die Diagnose am
  unveränderten Image bestätigt: Während eines Prompt-GET sind Textfeld und
  Save bereits aktiv; eine verspätete echte Antwort überschreibt die Eingabe.
  Diagnose nur mit regulärem Enter/Cancel, ohne gespeicherte Prompts zu ändern.
  Ursprünglicher FAIL, Dateien, Screenshots und Prozessreceipts bleiben erhalten.

Zusätzliche unabhängige Prüfungen mit denselben unveränderten **Entwurfsartefakten**:

- Regulärer a34→a36-Updateweg mit einem bestätigten Aufruf, ohne Retry oder Recovery,
  bestanden. Reale historische Produkt-/SCM-Freigaben, MANUAL-Receipt, Beobachtungen,
  Dateien und Domain-State erhalten; stale Planquellen und fremde Candidates bleiben
  abgewiesen. Historische Testfreigaben waren delegiert, keine neue Human-Abnahme.
- Zielstartverlust und Unterbrechungen nach realem Stopp/Metadatenwechsel geprüft.
  Vollständige zusammengehörige Quellmetadaten-/Datei-/State-Wiederherstellung,
  Auditpräfixe, konsistente neue Authority/Witness, ausdrückliche Reconciliation
  bekannter historischer Effekte und a34-Operatorstart ohne Dashboard bestanden.
  Danach ein neuer regulärer a34→a36-Updateaufruf aus dem tatsächlich restaurierten
  Zustand unter derselben Test-Vertrauensquelle bestanden. Beide alten Operations-
  Replays bleiben gesperrt. Lokale Identity-Recovery ist in diesem Legacy-Subject
  nicht anwendbar und dadurch nicht qualifiziert.
- 16 reale Berechtigungs-/CSRF-/Zustandsfälle bestanden; gespeicherte Konfiguration
  und Runtime unverändert, Auditverifier bestanden. Anschließender allgemeiner
  Setup-Wechsel scheiterte am Testwerkzeug-Timeout. Der Host zeigte vollen Swap und
  die emulierte VM wiederholte Kernel-Soft-Lockups. Kein Setup-/Production-PASS aus
  diesem Versuch; Fehler und Subject bleiben erhalten.

[Gebundener Fortschritt und getrennte Umgebungsfehler](https://scm.example.invalid/Alexander-Benesch/S.A.M.U.E.L./issues/1090#issuecomment-51317).
Der ungetaggte a37-Kandidat korrigiert gezielt den Prompt-Leseablauf und dessen
Schreibantworten. Sieben neue Leseregressionen und die Browser-Impactprüfung gegen
das unveränderte Backend bestanden. Beim ergänzenden Review reproduzierte der
ausgelieferte JavaScript-Code auch Eingabeverlust während einer laufenden
Save-Antwort. Neun weitere Regressionen für Write/Delete/Referenz, Ablehnung und
Dialogwechsel bestanden nach der gezielten Korrektur. Dies ist Entwicklungs-Evidence. Zwei lokale Suite-FAILs bei
Verifier-Unterprozessen unter Speicherdruck bleiben als frühere Versuche erhalten;
ein positiver Wiederholungslauf darf sie nicht umwerten. Gültige aktuelle Gates
bleiben an den endgültigen Kandidaten gebunden.

Ergänzender Diagnoseversuch am 17.11.2026: Der allgemeine Setup-/Production-
Wechsel auf einer kalten Kopie des erhaltenen Fehlsubjects bestand mit zwei
Operatoraufrufen, Dashboardänderung, erhaltenen Daten/Rollen/Credentials und
Auditprüfung. Der ursprüngliche Timeout bleibt FAIL. Eine erste zusätzliche
Identity-Recovery scheiterte vor Restore an einer falschen optionalen Compose-
Datei im Testwerkzeug; die vorhandene Installer-Auswahl ist korrekt.
Ein neuer Subject zeigte danach einen **weiteren echten a36-Fehler**: Ein schon
belegter lokaler Tokenname führt zu einem HTTP-Verbindungsabbruch. Der äußere
SQLite-Kontext übersetzt den Konflikt vor seiner vorhandenen Identitybehandlung.
Noch kein Restore begonnen; Fehlerlogs erhalten, Testsitzung explizit abgemeldet.
Die gezielte Korrektur bleibt im selben a37-Kandidaten: vorhandene Konfliktbehandlung
innerhalb der Transaktion, ohne neue Fehlercodes, Permissions oder Statearchitektur.
Vier echte HTTP-Regressionsfälle und ein Transaktionsrollbackfall scheiterten zuvor;
aktuelle endgültige Gates und reale Folgereleaseabnahme bleiben gesondert erforderlich.
Die lokale Identity-Recovery ist weiterhin offen; die a34-Legacy-Restoration ersetzt sie nicht.

Diese Teilnachweise sind keine vollständige Releaseabnahme. Der gezielte Fix
verändert weder a36-Tag noch Image/Assets und darf den fehlgeschlagenen Versuch
nicht nachträglich bestehen lassen. Ein korrigierter Nachfolger braucht volle
Gates, reguläre Integration, eigene konkrete Publishfreigabe und frische Abnahme.
Native Fortschrittsreferenz: [#1090, bestätigter Prompteditor-Fehler](https://scm.example.invalid/Alexander-Benesch/S.A.M.U.E.L./issues/1090#issuecomment-51315).
Veröffentlichte Neuinstallation, a34-Upgrade und vollständige Recovery bleiben
separat ausstehend. Erstvertrauen, HTTPS, GitHub-Projektion und minimale
Runtime-Tokenrechte bleiben offen; #1090 wird nicht geschlossen.

### a35-Entwurf durch Dashboard-Gate gesperrt — 16.11.2026

Die ausdrücklich kandidatenspezifische Betreiberfreigabe betrifft ausschließlich
`v2.0.0a35`, Commit `767f763261332b63c12d591c2c75362768fdb02b`.
Annotiertes Tagobjekt: `b1f3e66479f92a6b74ec0cef7c9e69533967a6d1`.
Main-CI #1589 und alle vier Tag-CI-Jobs #1590 bestanden; die drei vollständigen
Testsuiten der Tag-CI melden je 4993 PASS / fünf SKIP. Der tatsächliche
OCI-Pythonbestand wurde separat mit 32 Drittanbieterpaketen, ohne Skip und
ohne bekannte Findings geprüft; dies ist kein vollständiger Sicherheitsnachweis.

- Internes OCI-Manifest: `sha256:084eaa02e59b6817b40a9d9998ea7416bd85f239729cd66eb1eba4a936399630`.
- Release-Manifest: `sha256:17693892a5c3342c1687e3dea82e87b88137333a93bdeddf953a578cb233a379`.
- Privater nativer Release **49 bleibt Entwurf**, sieben Originalassets wurden
  unabhängig zurückgelesen. Tag, Image und Assets werden nicht ersetzt.
- Zwei frische leere Docker-VMs bestanden Installation, Administratoraufnahme,
  Dashboardkonfiguration einer externen Codebasis und ausdrücklichen
  Production-Start mit genau zwei Anwendungsaufrufen. Dies sind schmale
  Entwurfsnachweise, keine vollständige Releaseabnahme.
- Die erste anschließende Konfigurationsprüfung wurde mit Prozessstatus 143
  unterbrochen; die Signalursache bleibt unbekannt. Der neue vollständige Lauf
  `draft-empty-host-vm-_x_azhbd` endete regulär mit **FAIL**: Nach erfolgreicher
  Reauthentisierung blockierte `auth-overlay` den Übernehmen-Button bis zum
  180-Sekunden-Testtimeout. Keine Übernahme wurde abgeschlossen.
- Eine getrennte HTTP-/Browserdiagnose bestätigt 401-Antworten alter
  Hintergrundanfragen vor und nach erfolgreicher Sitzungsrotation. Die aktuelle
  Sitzung antwortete bereits mit 200, während der Anmeldedialog sichtbar blieb.
  Der Konfigurationsentwurf blieb `editing`, Version 10. Keine Testreparatur
  oder Codeänderung wird rückwirkend zum a35-PASS erklärt.

Die gezielte Browserkorrektur benötigt eigene Regressionen, Review und CI.
Ein korrigierter unveränderlicher Release benötigt anschließend eine neue
konkrete Publishfreigabe. Die a35-Freigabe gilt nicht für einen anderen Commit.
Veröffentlichte Neuinstallations-, a34-Upgrade- und Recoveryabnahmen sowie ein
positives Dashboardupdate zwischen zwei echten kompatiblen Releases bleiben
offen. Erstvertrauen bleibt **NOT_VERIFIED**; öffentlicher HTTPS-Kanal,
GitHub-Dokumentationsprojektion und minimale Runtime-Tokenrechte bleiben
getrennt offen. #1090 bleibt offen.

| Geltende Anforderung | Implementierung / Integration auf Ausgangs-Main | Entwicklungsnachweis | Eigene Abnahme veröffentlichter Lifecycle-Artefakte |
|---|---|---|---|
| Eine Installation, eine Codebasis; getrennte unabhängige Instanzen | Vorhandene Projektbindung gezielt erweitert; kein Mehrprojektumbau | Host-/Repository-/Receiptgrenzen und reale einzelne Projektbindung geprüft | Für den Nachfolger noch nicht ausgeführt |
| Ein Installationsaufruf und initialer Administrator | Vorhandener OCI-Installer, Identity-Bootstrap und Cutover gekoppelt | Leerer Dockerhost, echte Terminalaufnahme und Browserlogin bestanden | Noch nicht ausgeführt |
| Dashboard-SCM-/Projekt-/Secret-/allgemeine Konfiguration | Vorhandene Setup-API/-Writer erhalten; Erstprojektvorbereitung, Zeitzone und Labelabgleich ergänzt | Reale Einrichtung, Rollen und Production-Freeze geprüft | Noch nicht ausgeführt |
| Expliziter Production-Start | Vorhandener Operatorstart registriert die vorbereitete Erstbindung nach Bestätigung | Genau zweiter Anwendungsaufruf nach Installation bestanden | Noch nicht ausgeführt |
| LLM-/Prompt-Konfiguration | Bestehende ConfigurationSession wiederverwendet; keine neue Authority | Entwurf, Reauth, Übernahme ohne Hostneustart sowie allgemeiner Schreibblock geprüft | Noch nicht ausgeführt |
| Allgemeine Moduswechsel | Vorhandene Compose-/CLI-Aktionen mit gebundener Wartung | Genau setup / Dashboardänderung / start bestanden | Noch nicht ausgeführt |
| Dashboard-Updatevorbereitung und ein Operatorupdate | Release-/TUF-/Stateprüfungen und bestehende Backup-/Datei-/Startbausteine gekoppelt | Normaler Updateweg ohne Retry/Recovery bestanden | Noch nicht ausgeführt; kein synthetisches Versionspaar übernehmen |
| a34-Daten, Freigaben und Evidence erhalten | Deklarierter OCI-Vertrag akzeptiert ausdrücklich a34, Schema 10; keine allgemeine Versionsfreigabe | Veröffentlichtes a34 als Quelle, produktseitige History und neuer Entwicklungs-Target geprüft | Veröffentlichtes Nachfolgerziel noch nicht vorhanden |
| Vollständiger Quellrestore ohne Dashboard | Bestehende State-/Witness-/Reconcile-/Identitypfade mit gebundener Dateirücksicherung | Tatsächlicher Zielstartverlust, Dateien/State, Audit, neue Authority und expliziter Quellstart bestanden | Noch nicht ausgeführt |
| Bisherigen Benutzer-Wizard ablösen | Interaktiver CLI-Fragebogen entfernt; unzulässiger Altaufruf beendet sich ohne Schreibwirkung | Ersatzweg und eigener Altaufruf-Negativtest im integrierten Image bestanden | Noch nicht ausgeführt |
| Dokumentation, Beispiele und Entwicklungsanweisungen konsistent | Repositoryweites Audit und gezielte Korrekturen im laufenden Candidate; kein alleiniger Wiki-Abgleich | Quellen-/Vertragsprüfung und nach Integration frischer Wiki-Readback erforderlich | Ausgelieferte Anleitung noch wortgetreu zu prüfen |
| Initiales Bootstrap-Vertrauen | Prüfmechanismen vorhanden; tatsächlicher Übergabeweg und initiale Rootbindung sind Betreiberinput | Fixturetransport ist kein Erstvertrauens-PASS | **NOT_VERIFIED**, ausdrücklich offene Betreiberentscheidung |
| Offizieller HTTPS-Vertrieb | Separater Infrastrukturbedarf, keine Infrastrukturänderung in #1090 | Keine durchgängige HTTPS-Verfügbarkeit behauptet | **NOT_SELECTED** |

**Wizard- und Bestandsabgrenzung:** `samuel setup` ohne
`--non-interactive` besitzt nur noch den kontrollierten Abbruch mit Exit 2.
`install.sh` ist ausschließlich der Entwicklungscheckout-Installer. Der
nichtinteraktive Initialisierer, private Setup-Dateischreiber, Sicherheitskey-
Initialisierung, `/api/v1/setup/status`, `/configure` und `/labels` sowie das
bestehende Dashboardformular werden weiter benötigt. Dessen interne Funktionen
`loadSetupWizard` / `saveSetupWizard` bedienen dieses eine Formular; ihr Name
belegt keinen verbliebenen separaten Wizard. Sie werden nicht wegen ihres
Namens entfernt. Der direkte manifestgebundene Installer, `project` und
`toolchain` bleiben für ihre beschriebenen Bestands-/Recovery-/Projektaufgaben
erhalten; `project` ist kein zusätzlicher Normalinstallationsschritt.

**Auditumfang:** Alle getrackten Textquellen wurden nach Installations-, Wizard-,
Lifecycle-, Transport- und Mehrprojektangaben inventarisiert. Der fachliche
Abgleich umfasst Rootdokumente, INSTALL, Dashboard, CLI/API/Deploymentreferenz,
Architektur-/Entscheidungsquellen, State-/Recovery, Agent-/LLM-Anweisungen,
Konfigurationsvorlagen, SECURITY-/Supportangaben, Installer, Release-/Smokewerkzeuge und bestehende
Wiki-Quellenbindungen. Datierte a29-Screenshots und Versionshistorien bleiben
mit ihren ursprünglichen Aussagen erhalten; sie werden nicht als Aufnahme des
neuen Release ausgegeben. `docs/archive/` bleibt historisch. Eine reine
Trefferliste oder ein grüner Digestcheck ist keine semantische Gesamtabnahme.

Belegte Korrekturen betreffen insbesondere den uneindeutigen Einstieg über
Quellcheckout, manuelle Artefaktzusammenstellung als vermeintlichen Normalweg,
den alten manuellen Imagewechsel, den fehlenden Flag am Initialisierer und die
zusätzliche Projektregistrierung im Neuinstallationsbeispiel sowie den veralteten
a34-Kandidatenstatus in SECURITY.md. Die ursprünglichen
Entwicklungsnachweise unten bleiben unverändert und werden nicht in eine
Releaseabnahme umetikettiert.

**Konkrete Releasegrenze:** Der aktuelle Manifestvertrag lässt ausschließlich
`source_versions = ["2.0.0a34"]` und ein tatsächlich neueres Ziel zu. Ein
Dashboardupdate von einem neu installierten a35 zu sich selbst ist daher kein
zulässiger Positivtest. Ein vollständig veröffentlichter Dashboard-zu-Operator-
Nachfolgetest benötigt zwei echte passende Lifecycle-Releases und einen eigens
geprüften Versionsvertrag. Die bisher synthetischen a35/a36/a37-Labels dürfen
nicht als solche Releases ausgegeben werden. Der reale a34→Nachfolger-Test und
die frische Nachfolgerinstallation bleiben unabhängig davon ausführbar.

Am 16.11.2026 wurde nach Integration des Wartungsaufnahme-Fixes #1125 auf
Main `1fa31016d533128b4a0de3b91bfa82e34b1e8c2b` der vollständige
gewöhnliche a34-Updateweg erneut bestanden: genau ein bestätigter Aufruf ohne
Retry oder Recovery, tatsächlicher Zielstart, erhaltene produktseitig erzeugte
Freigaben und Evaluation-Evidence, unveränderte fachliche Daten und Auditpräfixe.
Ein separater Fehlerlauf bestätigt den tatsächlichen Zielstartverlust und die
vollständige gebundene Rückkehr zu a34-Metadaten und State, neue Authority-Linie,
Reconciliation mit zwei quellengeprüften Klassifikationen und ausdrücklichen
Quellstart ohne Dashboard. Ursprüngliches a34: Commit
`cff727fe9b8dd8e9aea3b9e6f46fa5644faec9f4`, Image
`sha256:b34663caa2b3fc06abc43cec389c64ae20c136ac4f73e7b66336f2b537fc5bef`.
Geprüftes Zielimage: `sha256:055c171113481f39c6cf006354dd46fd47a301c8f053da93b7068553ea98fe48`.
Attempts: `final-main-a34-update-ioyq_3bi` und
`final-main-a34-source-restoration-mm307xvg`. Die vorhandenen Freigaben bleiben
an ihren ursprünglichen Candidate gebunden; veraltete Planquellen und fremde
MANUAL-Candidates werden weiterhin abgewiesen. Die historischen Testfreigaben
waren delegiert; dies ist keine unabhängige menschliche Workflowabnahme.
Der getrennte leere-Host-/Browser-/CLI-Lauf desselben Main verwendet Subject
`empty-host-vm-aidjvyvm`: Ubuntu 24.04.5, Docker 29.8.2, Compose 5.6.0,
1-GiB-VM unter QEMU/TCG; anfangs keine Images, Container, Anwendungsverzeichnisse
oder Registrycredentials. Vorhandene externe Codebasis, Test-SCM, manuelle
LLM-Routen und gepinnter SSH-Testtransport sind ausdrücklich Testvoraussetzungen.

| Tatsächlicher Benutzerweg | Ergebnis und notwendige Operatoraktionen |
|---|---|
| Installation, Administratoraufnahme, Browserkonfiguration, Production | PASS: ein Installationsaufruf mit verdeckter Passworteingabe und explizitem Cutover; Rollen/SCM/Projekt/Labels/fünf LLM-Routen im Dashboard; genau der ausgegebene zweite Aufruf `start` mit Projektfreigabe. |
| LLM-/Prompt-ConfigurationSession | PASS: Entwurf, Vorschau, Reauth und ausdrückliche Übernahme; gespeicherter/effektiver Stand identisch, Container-ID/PID unverändert, null Hostaktionen. Allgemeine Production-Schreibversuche weiterhin HTTP 409. |
| Gewöhnliches Releaseupdate | PASS: Dashboardvorbereitung ohne Neustart, separater Nein-Negativtest ohne aktive Änderung, danach genau ein bestätigter Updateaufruf ohne Retry/Fortsetzung/Restore; Zielstart, bestehende Browsersitzung, Rollen, Credentials, Konfiguration, fachlicher State und Audit geprüft. |
| Fehlziel und vollständige Quellrestoration mit lokaler Identity | PASS: tatsächlicher Zielstartverlust; bestätigter Quell-/State-Restore ohne Dashboard, neue Authority-Linie, Reconcile, lokale Identity-Recovery und ausdrücklicher Quellstart. State/Witness Epoch 32, Auditpräfix und Backupdigest erhalten; alte Sitzung 401, Administrator ohne Operatorrecht 403, Rollen anschließend bewusst neu vergeben. |
| Allgemeine Rekonfiguration | PASS: genau `setup`, Zeitzonenänderung im Dashboard und `start`; UTC danach wirksam, übrige geprüfte Konfiguration, Credentials, Rollen, Projektbindung und fachliche Tabellen erhalten. Gleiches Release, Config wieder read-only, Session idle und Auditprüfung bestanden. |
| Ablösung des interaktiven CLI-Wizards | PASS: Ersatzweg oben im integrierten Image bestanden; zusätzlicher Negativaufruf `samuel setup` liefert Exit 2 und Dashboardhinweis ohne Konfigurations- oder Runtimeänderung. Der bestehende nichtinteraktive Installerbaustein bleibt erhalten. |

Das gewöhnliche Update erreicht das gebundene Zielimage
`sha256:2a36ed6269c9516e34cefdc19c9665606263592113fd520c8c916c4923ea8374` mit angezeigter Testversion a36.
Der zusätzliche Docker-Readback um 00:25:53 UTC bestätigt `healthy`. Während des
kalten Zielimagebezugs meldete die emulierte Quell-VM zuvor `unhealthy`; diese
Beobachtung und die Registry-/Dockerdiagnose bleiben erhalten. Der Operatorlauf
selbst benötigte weder Wiederholung noch Recovery. Dies ist kein Performance-
oder allgemeiner Workflow-/Providerqualifikationsnachweis. Der relative
Updateaufruf wurde im Bootstrap-Verzeichnis ausgeführt; ein absoluter Skriptpfad
ist ebenfalls möglich. Keine zusätzlichen Composeaktionen im Normalweg.

Das tatsächliche Fehlerziel verwendet Image
`sha256:9830c1d023281e6188073cb0019a8dd5bbd6457026a5632eec39997a506820d6` (Testversion a37).
Seine Quellrestoration erreicht wieder das oben gebundene a36-Image. Die private
Passwortdatei und die zusätzlichen Reconcile-/Identity-/Startschritte sind Teil
des dokumentierten Recoveryfalls; sie werden nicht als normale Installations-
oder Updateschritte verschwiegen. Ein beliebiger Dateisystemverlust oder fehlender
Releasebezug ist damit nicht qualifiziert.

Diese Funktionsabnahme bindet die drei Testimages an denselben integrierten Main;
a35/a36/a37 sind hier synthetische Versionsidentitäten mit signierten Testmetadaten,
keine veröffentlichten Releases oder produktiven Kompatibilitätsfreigaben. Für
#1125 sind am geprüften Dateibaum 4.991 lokale Tests bestanden, fünf übersprungen;
native PR-CI #1581 und eigene Main-CI #1582 haben alle drei Pflichtjobs bestanden.
Regression, reale Referenzabnahme und unabhängige menschliche Acceptance bleiben
unterschiedliche Nachweisstufen. Ein Dokumentationsmerge übernimmt keine neue
Runtime-/Releasequalifikation auf seinen eigenen Commit.

Beim zusätzlichen ersten Wizard-Negativtest waren Fachassertionen und Receipt
vollständig, die Ausführungshülle endete jedoch mit 143. Dieser Befund bleibt
separat erhalten; die getrennte Bestätigung mit direktem Prozessaufruf endete
sauber mit 0 und bestätigte erneut den erwarteten Produkt-Exit 2. Das ist ein
zusätzlicher Qualificationaufruf, kein versteckter Schritt der Installation.

Initiales Bootstrap-Erstvertrauen bleibt `NOT_VERIFIED`: Der tatsächliche
authentisierte Übergabeweg und die unabhängige initiale Rootbindung benötigen die
ausdrückliche Betreiberfestlegung und ihren Nachweis. Der offizielle HTTPS-
Distributionskanal bleibt `NOT_SELECTED`, ein gesonderter offener Infrastruktur-
und Sicherheitsbedarf. Keine neue TLS-Infrastruktur, kein ungefragt angelegtes
Folge-Issue und keine Bootstrap-Veröffentlichung innerhalb dieses Nachweises.

Historischer Zwischenstand: Auf integriertem Main `017bde1bc3c97d572ec971ecc93277f24a6b9a9b` wurde eine
tatsächliche a34-Installation mit zuvor über Produktabläufe erzeugten Freigaben
und Evaluation-Evidence regulär aktualisiert: ein bestätigter Updateaufruf,
Zielstart, Zustandserhalt und Auditprüfung bestanden. Ein getrennter vollständiger
Fehlerfall bestätigt nach Zielstartverlust die Rückkehr zu originalen a34-Dateien
und State, neue Restore-Instanz/Epoch, Reconcile-STOP, zwei quellengeprüfte
Operator-Klassifikationen und ausdrücklichen Quellstart ohne Dashboard.
Subjects: `ordinary-main-a34-update-uv21h270` und
`a34-source-restoration-3c7f40_p`; tatsächliches Zielimage
`sha256:a87a8cb80dd9c6d87853f596dc64c1955171f28ee0db7cce6648f420a4b0fc70`.
Das Ziel verwendet signierte Testmetadaten und eine lokale Testversionskennung;
es ist kein veröffentlichter a35-Release. Historische Testfreigaben sind keine
unabhängige menschliche Acceptance. Der ursprüngliche VM-Update-Timeout und
fehlgeschlagene Harnessversuche bleiben mit eigener Bindung erhalten.

Die leere Docker-VM `empty-host-vm-hkujl3nq` belegt am damaligen Candidate
`1f75ae9e47934867caae9f8eabfb4e9f31eb3767` Installation mit Administratoraufnahme,
Dashboardeinrichtung und ausdrücklichem Production-Start sowie spätere
ConfigurationSession-Änderungen ohne Hostaktion. Ihr reguläres Update blieb FAIL;
die erfolgreiche gebundene Fortsetzung ist ein getrennter Nachweis.
Der integrierte Main `9d0416c6530a0dead42774e061615db2722d7c5f` bestätigt
in `empty-host-vm-53sf5qs3` die leere Erstinstallation, lokale Administratoraufnahme,
Dashboardkonfiguration, ausdrücklichen Production-Start und ConfigurationSession.
Auch dort blieb der gewöhnliche Updateversuch an der ersten 60-Sekunden-Antwortfrist
FAIL; die erfolgreiche gebundene Fortsetzung ersetzt diesen Nachweis nicht.
Docker-Ereignisse belegen, dass diese Frist schon Compose-/Containerstart und
Bootstrap einschließt. Die gezielte Korrektur gibt ausschließlich dieser ersten
Antwort 180 Sekunden; Sperren, Prüfungen und Folgefristen bleiben erhalten.
Der gewöhnliche Updateversuch dieses früheren Standes bleibt FAIL; der
integrierte Fix erhält die oben getrennt benannten neuen Nachweise.

Derselbe integrierte Stand wurde nach einem weiteren tatsächlichen Zielstartverlust
vollständig auf das gebundene Quellrelease zurückgeführt: ursprüngliche Dateien
und fachlicher State, neue Authority-Instanz, höhere und mit dem Witness identische
Epoch, ausdrückliche Reconciliation sowie lokale Administrator-Recovery. Alte
Sitzungen werden abgewiesen; Operatorrechte müssen nach der Administrator-Recovery
ausdrücklich im Dashboard wieder zugewiesen werden. Quellstart und Auditprüfung
sind bestanden, das Auditpräfix des Fehlziels und der Backupdigest bleiben erhalten.
Die dafür notwendige private Passwortdatei ist ein zusätzlicher dokumentierter
Recoveryeingabeschritt, kein versteckter Normalinstallationsschritt. Der bestandene
Recoverylauf ersetzt den früheren gewöhnlichen Update-FAIL nicht.

Ein getrennter Browser-/CLI-Nachweis auf diesem Stand bestätigt eine allgemeine
Konfigurationsänderung mit genau `setup` und `start`: Zeitzone UTC bleibt nach
Production wirksam; übrige Konfiguration, Credentials, Rollen, Projektbindung
und geprüfte fachliche Statezeilen bleiben erhalten. Das Config-Mount ist wieder
read-only, ConfigurationSession idle und Auditverifikation bestanden. Eine erste
SSH-Bootbeobachtung war vor Beginn des Produkttests abgelaufen; ihr eigener
Vorbereitungs-FAIL bleibt erhalten.

Diese Nachweise verwenden die synthetischen Versionen a35/a36/a37 desselben Main,
Test-SCM und Test-TUF. Das Quellimage für Recovery und Rekonfiguration ist
`sha256:55ae9bcda61f045b5108e21e998cabc61499d736dac5422141ef61f8b20e5524`,
das tatsächlich gestartete und gezielt gestoppte Fehlerziel
`sha256:18421f641b30ff9e8ff99502660181620cf4deef2a96fc43adb2fb014151aae1`.
Der damals noch fehlende kombinierte Benutzer-/Updateweg ist oben für den
integrierten Timeoutfix mit eigener Bindung nachgewiesen. Ein beliebiger Dateisystemverlust wurde damit nicht geprüft;
a34 verwendet im getrennten historischen Subject Legacy-Credentials.
Die aktuelle Entwicklung und genaue Evidence stehen in #1090, nicht als pauschaler
Golden-/D0-/Gesamt-PASS. Initialer authentisierter Bootstrap-Übergabeweg und
offizieller HTTPS-Kanal samt Erstvertrauensbindung bleiben offen.

## Veröffentlichter Testrelease v2.0.0a34 — 10.11.2026

Native Veröffentlichung #48 bindet Productcommit
`cff727fe9b8dd8e9aea3b9e6f46fa5644faec9f4` und annotiertes Tagobjekt
`9576e282e4a469422f75097bd19b3867c258764c`. Main-CI #1480 und alle vier
Tag-CI-Jobs #1481 einschließlich Release-Gate sind bestanden. Sieben Assets
wurden vor und nach Veröffentlichung unabhängig bytegleich zurückgelesen.
Manifest-SHA-256: `58e6b49c65dc58e83933bd834dcb084659431a87b19de37407997f5ce4ee3fdb`.
OCI-Digest: `sha256:b34663caa2b3fc06abc43cec389c64ae20c136ac4f73e7b66336f2b537fc5bef`.
Für die Installation ausschließlich die vollständige `container.reference`
aus diesem geprüften Schema-2-Manifest verwenden, keinen Registrypfad ableiten.

**Tatsächlich geprüft:**

- Frisch installiertes nicht editierbares Wheel: 4.305 Tests bestanden,
  fünf zugangsabhängige Skips; separat acht reale lesende SCM-Tests bestanden
  (drei Überschneidungen). Frische sdist-Installation und Abgleich aller
  238 installierten Produktdateien bestanden. CI-Kompatibilitätsprofile
  3.12.14 und 3.14.7: jeweils 4.304 Tests und sechs Skips; das dort fehlende
  optionale Cryptoextra wird im vollständigen CI-Profil geprüft.
- Offizieller Publisher, Digest-Pull und Compose-Smoke bestanden. Zwei
  getrennte offizielle Erstinstallationen mit leeren eigenen Docker-Datenspeichern
  bestanden: Entwurfsassets und anschließend veröffentlichte Assets. Dies sind
  getrennte Engines auf einem bestehenden Linux-Testhost, keine zwei frischen
  Betriebssysteminstallationen. Setup, Authentifizierung, Persistenz, Recreate,
  Productionfreeze, Runtimeidentität und Health geprüft.
- Vollständiger beobachteter OCI-Workflow: Demo-Issue #272 → PR #273 → Merge
  `6c4df29ac87941b044db306fd33e67533b2d1521`. Plan #50939, Candidate
  `0208f5d8c96da0b0766307f70e36141aeffed02d`, sechs erfüllte Acceptance-Kriterien,
  strukturierter Review #50951 ohne Findings und Required-CI #1482 bestanden.
  Öffentliche CLI, Dashboard und authentifiziertes SCM-Polling wurden verwendet;
  keine internen Handler-/State-Reparaturen. Plan-, MANUAL- und Mergeentscheidungen
  waren ausdrücklich delegierte **automatisierte Testfreigaben**.
- Geordneter Neustart bei ausstehendem MANUAL erhält Bindung/Kriterien;
  doppelte MANUAL-Freigabe erzeugt keine zusätzliche Implementierung oder PR.
  Der gemergte Demo-Stand wurde unabhängig über 48 Gitblobs geprüft, separat
  ohne Credentials installiert und mit 60 Tests, echten HTTP-JSON-Aufrufen,
  sichtbarem 404/Exitcode 22 und Chromium geprüft. SAMUEL meldete selbst
  `PRMerged`, `status:done` und Leerlauf nach drei LLM-Aufrufen.
- Auditprüfung: 382 Records mit intakter Kette. Im beobachteten Abschlusslauf
  keine gemeldeten Verluste, SQLite-Sperr- oder Diagnoseprojektionsfehler.
  Kettenintegrität ist kein allgemeiner Vollständigkeitsnachweis.

Modellrouten vor dem Workflow: Planning und übrige Tasks `deepseek-flash`,
Implementation und Review `deepseek-v4-pro`; während des Laufs unverändert.
Der positive Lauf belegt keinen ausgeführten Healing-/Quality-Aufruf und
keine allgemeine Qualifikation anderer Modelle. Die früheren 53 Simulationen
behalten ihre jeweiligen Produktstände und Ergebnisse. Nicht alle Szenarien
wurden auf a34 erneut durchgeführt; kein pauschaler T01–T45-/Golden-/D0-PASS.

**Erhaltene Fehler und Restgrenzen:** F18 bleibt ein fehlgeschlagener
Container-Regressionsversuch mit `state_locked` unter Speicherlast. Unveränderte
Gegenproben und der spätere persistente Workflow bestanden; daraus folgt keine
Verfügbarkeitsgarantie bei überlastetem State. F19/F20 korrigieren ausschließlich
Testfixtures. Ein erster Published-Installationsversuch wurde nach einem
Testtreiber-Startfehler gestoppt; erst der separate neue Versuch ist PASS.
a33 bleibt unveröffentlichter Fehlkandidat. Die Sicherheitsisolations- und
externen Providerqualifikationen, natürliche Langzeitfristen und unabhängige
Zielserverabnahme bleiben eigenständige Nachweise. #1072 enthält die datierten
Fehlversuche und Abschlussbelege; #962/#994 behalten ihre formalen Restkriterien.

Code und betroffene Fachabschnitte gehören im selben PR zusammen. Release- und
Integrationsnachweise werden nach ihrem tatsächlichen Abschluss nachgeführt;
sie dürfen nicht aus einer vorherigen Planungsnotiz abgeleitet werden. Aktuelle
Main-Dokumentation und Wiki verweisen auf die unveränderte a34-Releasebindung.
[Öffentlicher GitHub-Stand und Zugangssperre](../github/GITHUB_SYNC_READINESS.md)
bleiben separat ausgewiesen; kein öffentlicher a34-Release wird behauptet.

## Historie lesen, ohne sie als aktuellen Arbeitsauftrag zu verwenden

Der [vollständige bisherige Statusverlauf](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md)
erhält sämtliche früheren Release-, Candidate-, Fehler- und Integrationsnachweise.
Die folgenden zwei datierten Fachnachweise bleiben wegen bestehender Verweise
und Wiki-Projektionen unverändert zugänglich. Darin genannte damalige offene
Issues vor neuer Arbeit nativ lesen; sie sind kein aktueller Gesamtbacklog.
Weitere alte Anker führen direkt zur jeweiligen Archivstelle. Gültige ADRs,
aktive Betriebsregeln und historische Originale im Auditarchiv bleiben erhalten.

## Veröffentlichter Installationsstand v2.0.0a29 — 09.10.2026

Prerelease #43 bindet Productcommit `1a1c1f2eeaf324b62074a41adc9dc2474057561f` und
annotiertes Tagobjekt `332e2aab137748841d73b7523654fc06578e6894`. PR #989 und #980 sind
menschlich gemergt; Main-CI #1225 und Tag-CI #1226 einschließlich Release-Gate
sind SUCCESS. Sieben Assets wurden nach Upload und Veröffentlichung bytegleich
zurückgelesen. Manifest-SHA-256: `c62013a8a171627a0932fcf0c999aea9664c2d8533e27bb156414ddc51ed030b`.
OCI-Digest: `sha256:81c835bd358cb889f2333ed395f326c4b8cc50255cdb54659c6ce938c9095b69`.
Installationsauthority bleibt die vollständige `container.reference` im
geprüften Schema-2-Manifest, kein rekonstruierter Registry- oder Tagpfad.

Der erste Required Publisher-Smoke und zwei unabhängige Erstinstallationen
auf jeweils frischem Ubuntu 24.04.5 mit Docker 29.8.2 und Compose 5.6.0 sind
PASS: zuerst aus exakten Draft-Assets, danach aus veröffentlichten Assets.
Beide prüfen offiziellen Installer, Setup vor SCM, authentisierte Konfiguration,
Production Health, Releaseidentität, Persistenz, Recreate und Freeze. Das
Published-Installationsreceipt wurde am 09.10.2026 um 11:12:14 UTC abgeschlossen
und bindet denselben Productcommit und OCI-Digest. Kein Workflowstart oder
LLM-Aufruf; Projekt-Readiness bleibt ohne qualifizierte Projektbindung blockiert.
Keine vorhandene Installation oder Kundenquelle geändert. Alle sieben
veröffentlichten Assets sind zusätzlich bytegleich zurückgelesen. Die
Installationsreceipts sind in den Release Notes separat ausgewiesen.
Dies ist technische Installations-Evidence, kein kompletter Funktions-/D0-Lauf.

Enthalten sind registrierte lokale OCI-Projektquellen mit Recreate-Identität
und Git-Härtung, Gate-7-Fallback vor Kandidatenausführung, vollständige
Readinessaggregation sowie die gebundene Verifier-Versionprobe im vorhandenen
TEST-Budget mit maximal 60 Sekunden. Kleine Operatorbudgets bleiben verbindlich;
ungebundene Presence-Proben behalten acht Sekunden. Projektbestand, Workspaces,
Runtime und Authority-State bleiben getrennte bestehende Rollen.

Neue Alpha-Tests verwenden saubere Neuinstallationen; keine Übernahme alter
State-/Checkpoint-/Projektreceipts oder Cross-Release-Migration. Die kombinierte
PR-Suite bestand 3568 Tests; fünf Credentialfälle wurden separat nachgewiesen.
Diese Entwicklungsnachweise ersetzen keine reale a29-Funktionsabnahme.

**Offen:** vollständige lokale Prozessisolation, reale externe Sicherheits-
qualification und spätere H3-Remoteumgebung. #978/#988 bleiben für ihre eigenen
realen Abnahmen offen; #977/#986/#987 werden nicht pauschal erledigt. Die extern
berichteten a28-Teilabnahmen aus #981 bleiben auf deren damalige Umgebung
begrenzt; serverseitiger Tokenwiderruf bleibt unbelegt. Historische a28-Timeout-
FAILs bleiben erhalten. Kein Golden-/D0-PASS oder Produktionssupportclaim.
Die GitHub-Projektion ist ein eigener Auslieferungsstand; dieser native OCI-
Release behauptet keinen neuen Public-OCI- oder GitHub-a29-Publish.

## Untersuchung #951 abgeschlossen — freie Modelleingabe nach #975

Der ursprüngliche #951-Auftrag fordert ausdrücklich Ist-Stand, fachliche
Prüfung, vorhandene Checks und minimale Empfehlung vor späterer Umsetzung.
Alle acht Untersuchungsfragen sind beantwortet. #951 ist als
**INVESTIGATION_COMPLETE** geschlossen; die ursprünglichen Kriterien bleiben
erhalten. Am integrierten Code-Stand `20e3a172ef0b7398c4731be09172e310277c2f4a` bestehen die bisherigen
40 Fälle sowie 13 integrierte JavaScriptregressionen: **53 PASS, 0 SKIP** mit
bereits vorhandener Node v24.11.0 nur im Testprozess-PATH. Der erste Nachlauf
mit 40 PASS / 13 SKIP und die Korrektur des zunächst falschen PASSzählers
bleiben erhalten. Die ursprüngliche Browserbeobachtung ist historische
Evidence; keine neue Live-Providerprobe oder Save-/Route-/Configänderung.

Die verbindliche Maintainerentscheidung vom 13.10.2026 zu #975 erhält die
freie Modelleingabe in Einrichtung, Task und Schedule. Optionale Vorschläge
sind Orientierung; entfernte/unbekannte IDs, fehlende Kataloge und Refresh
ersetzen keine Eingabe. Die Umsetzung im Quellstand vereinheitlicht diese
Formulare und trennt Modellkatalog- von Benchmarkzustand. Bedienung und
UNKNOWN-Grenzen stehen im [Dashboard](../DASHBOARD.md#freie-modelleingabe-und-optionale-vorschläge).
Gatewaykatalog, native Endpoint-/Konto-Verfügbarkeit und Task-Suitability
bleiben getrennt; Setup→Persistenz→Recreate→Freeze und vorhandene
Routing-/Quality-/Fallbackregeln bleiben erhalten. Das ist kein neuer
Liveprovider-, nativer Browser-, Workflow- oder Qualification-PASS. Die
historischen 53 Untersuchungstests oben behalten ihre eigene Codebindung;
aktuelle #975-Regressionen werden im eigenen PR-/Issue-Nachweis geführt.

## Frühere Anker und Nachweise

## Dokumentationsarchitektur: integrierte Grundlagen D1–D6 — 10.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#dokumentationsarchitektur-integrierte-grundlagen-d1d6--10102026).

## HISTORICAL / AUDIT_EVIDENCE — Dokumentabgleich nach #1002

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#historical--audit_evidence--dokumentabgleich-nach-1002).

## Dokumentation integriert — Abgleich nach #1002, 10.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#dokumentation-integriert--abgleich-nach-1002-10102026).

## HISTORICAL / AUDIT_EVIDENCE — Vorbereitung vor dem Dokumentmerge

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#historical--audit_evidence--vorbereitung-vor-dem-dokumentmerge).

## Integrierter Entwicklungsstand und Dokumentnachlauf — 10.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#integrierter-entwicklungsstand-und-dokumentnachlauf--10102026).

## HISTORICAL / AUDIT_EVIDENCE — Dokumentvorbereitung vor Productmerges

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#historical--audit_evidence--dokumentvorbereitung-vor-productmerges).

## Erneuter Current-State-Abgleich — Candidateprüfung, 09.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#erneuter-current-state-abgleich--candidateprüfung-09102026).

## Autonomer Arbeitsstand auf Main 4bd335c — 09.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#autonomer-arbeitsstand-auf-main-4bd335c--09102026).

## #989 und #980 integriert und in a29 veröffentlicht — 09.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#989-und-980-integriert-und-in-a29-veröffentlicht--09102026).

## #988 — freigegebener lokaler Implementierungsumfang, 08.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#988--freigegebener-lokaler-implementierungsumfang-08102026).

## Historischer Installationsstand v2.0.0a28 — 08.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#historischer-installationsstand-v200a28--08102026).

## Entwicklungsdelta nach a27: Framework-Mappings — 06.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#entwicklungsdelta-nach-a27-framework-mappings--06102026).

## Historischer Installationsnachweis v2.0.0a27 — 06.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#historischer-installationsnachweis-v200a27--06102026).

## Productdelta nach #965 — 06.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#productdelta-nach-965--06102026).

## Veröffentlichter Release v2.0.0a26 — 05.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#veröffentlichter-release-v200a26--05102026).

## Administrativer Altlastenabschluss und Releasezweck — 05.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#administrativer-altlastenabschluss-und-releasezweck--05102026).

## Eigene releasegebundene Consumerabnahme — 05.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#eigene-releasegebundene-consumerabnahme--05102026).

## Eigener Taskeditor-Abnahmedelta — 05.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#eigener-taskeditor-abnahmedelta--05102026).

## Abnahmen und nächste gebündelte Kampagne — 04.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#abnahmen-und-nächste-gebündelte-kampagne--04102026).

## Eigene Operator-Abnahmen und verbleibende Grenzen — 04.10.2026, f514ddee

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#eigene-operator-abnahmen-und-verbleibende-grenzen--04102026-f514ddee).

## Aktueller eigener Abschluss nach #949 — 04.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#aktueller-eigener-abschluss-nach-949--04102026).

## Identitaet und Baseline

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#identitaet-und-baseline).

## Eigener aktueller Abschlussabgleich — 04.10.2026, a0f16c02

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#eigener-aktueller-abschlussabgleich--04102026-a0f16c02).

## Nachgewiesen funktionierend

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#nachgewiesen-funktionierend).

## Enger EOF-Fix und aktueller E2E-Impact

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#enger-eof-fix-und-aktueller-e2e-impact).

## Eigene Operator-Teilabnahmen — 04.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#eigene-operator-teilabnahmen--04102026).

## Teilweise oder noch nicht end-to-end belegt

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#teilweise-oder-noch-nicht-end-to-end-belegt).

## Aktuelle Blocker

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#aktuelle-blocker).

## Eigenständiger Development-E2E auf integriertem Main — 04.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#eigenständiger-development-e2e-auf-integriertem-main--04102026).

## Eigenständiger Development-E2E auf integriertem Main — 03.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#eigenständiger-development-e2e-auf-integriertem-main--03102026).

## Frühere eigene Development-E2E-Baseline auf eb6cce18 — 03.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#frühere-eigene-development-e2e-baseline-auf-eb6cce18--03102026).

## Historische positive Development-E2E-Baseline — 02.10.2026

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#historische-positive-development-e2e-baseline--02102026).

## Historischer fehlgeschlagener MANUAL-Lauf

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#historischer-fehlgeschlagener-manual-lauf).

## Qualification, Wiki und Public Sync

HISTORICAL — [unveränderter damaliger Aussagebestand](../archive/CURRENT_PRODUCT_STATUS_2026-10-11.md#qualification-wiki-und-public-sync).

