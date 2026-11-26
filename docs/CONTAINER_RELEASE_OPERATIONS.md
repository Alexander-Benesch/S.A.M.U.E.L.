# Container-Release-Betrieb

## Release für eine neue Testinstallation

Für eine frische Docker-Installation reicht das Passwort für das Dashboard-Konto `admin`. Der Installer prüft Release und Image automatisch. Im Dashboard wählst du Repository, optional den Branch und den Modellzugang. Mit **Prüfen und starten** wird das Projekt ausgecheckt und der Betrieb gestartet. [Release auf GitHub](https://github.com/Alexander-Benesch/S.A.M.U.E.L./releases/tag/v2.0.0a42)

Für künftige öffentliche Releases vor der Freigabe den fertigen OCI-Kandidaten einschließlich aller Schichten, Image-Konfiguration und Build-Historie auf Secrets prüfen. Befunde klären und das Ergebnis an den Image-Digest binden. Nach Veröffentlichung den Digest anonym aus der Registry zurücklesen. README, Installationsanleitung, Dokumentationsentwurf und öffentliche Statusübersichten mit dem Release abgleichen.

### Prüfung der Docker-Erstinstallation

Den Release-Kandidaten auf einem frischen Dockerhost installieren. Der Dialog nennt das Konto `admin` und erklärt die Passwortregeln vor der Eingabe. Bei leerem Host legt der Installer das persönliche Konto direkt an und protokolliert die Erstinstallation. Im Dashboard ein Testrepository und den Modellzugang einrichten. Nach **Prüfen und starten** die ausgecheckte Revision sowie Anmeldung und Betriebszustand prüfen.

Einen belegten Hostport simulieren, einen anderen wählen und bestätigen, dass die angezeigte Adresse diesen Port verwendet. Der Installer akzeptiert auch `--port HOSTPORT`. Ein ungültiges oder abweichend wiederholtes Passwort muss noch im selben Terminal korrigierbar sein. Nach einer unterbrochenen Aufnahme denselben Installer erneut ausführen: Release und vorhandenen Zustand prüfen, ein bereits angelegtes Konto und sein Passwort erhalten, das Setup fortsetzen. Bei fremdem oder unklarem Zustand mit Diagnose anhalten. Im root-lesbaren Protokoll unter dem beim Start angezeigten Pfad stehen Phasen und Ergebnis. Eingaben und Zugangsdaten gehören nicht ins Protokoll.

Am Ende den Login mit dem lokalen Konto von einem zweiten Rechner über den ausgegebenen SSH-Tunnel prüfen. Der Hostport bleibt an `127.0.0.1` gebunden. Beim Veröffentlichen README, Standardanleitung, Handbuchentwurf und Wiki auf dasselbe tatsächlich freigegebene Release umstellen.

## #1090 Beta-Lifecycle-Auftrag

Die folgenden Kriterien dokumentieren den damaligen internen Auftrag #1090. Für eine neue Installation gilt die [Installationsanleitung](INSTALL.md#öffentliche-alpha-auf-einem-docker-host-installieren).

**Freigegebener Gesamtauftrag; Teilstände sind keine vollständige Lifecycle-Abnahme.**
**Aktuelle Betreiberentscheidung zur Alpha-Abnahme:** Für #1090 gilt eine frische
Installation aus dem veröffentlichten Release mit Administratoraufnahme, Dashboard,
SCM-Anbindung, aktivierter LLM-Konfiguration und explizitem Production-Start.
Ein reales Test-Issue muss mit gültiger Planfreigabe durch Implementierung, Tests,
Security-Gates, PR, CI, Review und Merge laufen. Audit und fachliches Ergebnis am
gemergten Stand prüfen. Einen unzulässigen Merge in der isolierten Umgebung
tatsächlich abweisen lassen.

Es gibt keine zu migrierenden Kundeninstallationen. Die historischen a34–a37-Tests
und ihre Grenzen bleiben dokumentiert. Für diese Stände entfällt die Pflicht zu
Migration und Rückwärtskompatibilität. Die erste zukünftige Update-Baseline wird
erst mit überprüfter Installation, gebundener Version, Commit, Manifest, Image-Digest,
konsistentem State und funktionierendem Backup-/Recoveryweg ausdrücklich benannt.
Bis dahin ist sie offen. Die erste kompatible reguläre Folgeversion muss den echten
Updateweg mit ausdrücklichem Operatoraufruf belegen. Kein Testrelease für diesen
Nachweis. Die technischen Teilstände unten beschreiben ihre jeweilige Version.

Quelle: ursprüngliches Issue #1090 und die nachfolgenden ausdrücklichen
Betreiberentscheidungen im Arbeitsdialog; Bestandsabgleich vom 13.11.2026 auf
lokalem und nativem Main `4b9b21568d93ef9e502a5b33f5bc3e438e4e0bde`.
Beim Abgleich enthielt #1090 keine Kommentare und es gab keine offenen PRs.
Die folgende Disposition erhält die historische Analyse und präzisiert den
Auftrag. Die implementierten Entwicklungsstände sind vom veröffentlichten a34
und von ihrer tatsächlichen Funktionsabnahme zu unterscheiden; commitgebundene
Nachweise stehen im [Produktstatus](status/CURRENT_PRODUCT_STATUS.md#entwicklung-des-einzelprojekt-lifecycles-1090--15112026).

**AP-2-Teilstand im Code:** Der bestehende OCI-Installer unterstützt die
optionale Administratoraufnahme mit `install --admin-username USER` vor dem
Dashboardstart. Sie verwendet `identity bootstrap --prompt-password` und den
vorhandenen expliziten Cutover nach bestätigter Client-Inventur und Begründung.
Details, unabhängige Rollen, Fehlerfälle und erforderlicher Production-Start
stehen in [INSTALL](INSTALL_REFERENCE.md#91-oci-erstinstallation-auf-einem-leeren-docker-host-970).
Die vorhandenen nichtinteraktiven Aufrufe bleiben erhalten. CLI-/Terminal- und
Orchestrierungsregressionen ersetzen weder eine reale Docker-/Browserabnahme
noch Erstvertrauen, Artefaktbeschaffung oder den gesamten AP-2-Nachweis.

**Weiterer AP-2-Teilstand:** Der vorhandene Release-CLI kann mit `fetch` ein
TUF-signiertes Eingabeartefakt und mit `fetch --release` ein Manifest samt allen
gebundenen Artefakten beziehen. `install` kann diesen Baustein über ein
betreiberseitig geliefertes Bootstrap-Profil mit dem vorhandenen OCI-Installer
verbinden. Authentisierte Erstübergabe bleibt offen; die davon getrennten Funktionsnachweise stehen im Produktstatus. [Vertrag und Nachweisgrenze](CONTAINER_RELEASE_OPERATIONS.md#tuf-artefaktbezug-im-vorhandenen-release-cli).
Der Installer gibt nach erfolgreichem Setupstart
den vollständig gebundenen Bash-Aufruf für den separaten Production-Start aus.
Der Betreiber muss dessen Pfade und Instanzoptionen nicht erneut zusammensetzen;
Ausführung und erneute Prüfungen bleiben ausdrücklich beim vorhandenen Operatorweg.

### Entscheidungshistorie und verbindliche Grenze

| Quelle / Reihenfolge | Aussage und heutige Disposition |
|---|---|
| Ursprüngliches #1090, Abschnitte 3.C, 4.3 und 7 | Mehrprojektbetrieb und Projektwechsel waren Untersuchungs-/Anforderungsbestandteile. Der Wortlaut allein bestimmte nicht eindeutig mehrere Codebasen pro Installation. |
| Agentenplanung und nachfolgende ausdrückliche Betreiberentscheidung | Eine Installation mit mehreren registrierten Codebasen, einer aktiven Runtime und Projektwechsel wurde zwischenzeitlich ausdrücklich akzeptiert. Das war eine Scopeentscheidung, keine vorhandene a34-Fähigkeit und kein Abnahme-PASS. |
| Spätere Scopekorrektur | Verbindlich bleibt eine Installation für genau eine Codebasis. Historische Mehrprojektanforderungen sind zurückgestellt, nicht implementiert oder erfolgreich abgenommen. |
| Hostausführung | Nach Prüfung des Compose-Helfers wurde für die Beta Dashboard-Konfiguration/-Updatevorbereitung mit vorhandener lokaler Operator-CLI für privilegierte Aktionen gewählt. Kein dauerhaft privilegierter Helfer, keine Docker-Authorisierungsarchitektur, keine neue systemd-Pflicht. |
| Betreiberentscheidung vom 19.11.2026 zu Erstvertrauen und Distribution | Die eigenständige interne Erstübergabe mit unabhängiger Bootstrap- und TUF-Root-Bindung entfällt als Abschlusskriterium für #1090. Ihr technischer Status bleibt NOT_VERIFIED. Für die spätere offizielle Distribution ist GitHub bestimmt. #1140 führt den konkreten HTTPS-Bezug, die initiale Vertrauensbindung und die automatische Updateprüfung. |
| Umsetzung | Kleine, getrennt geprüfte PRs je Arbeitspaket; bestehende Mechanismen erweitern und Required CI, Review sowie Human Merge erhalten. |

Dashboard und Runtime erhalten weder Docker-Socket noch allgemeine Hostrechte.
Keine Projektlisten/-wechsel, zusätzliche Worker, installationsübergreifende
Serialisierung oder neue Identityverwaltung. Mehrere unabhängige Installationen
für unterschiedliche Codebasen behalten getrennte Ports, Credentials und Daten.
Mehrere Instanzen auf derselben Codebasis gelten ohne gesonderte Konflikt- und
Governanceprüfung nicht als unterstützt. Mehrprojektverwaltung und spätere
vollständige Dashboardausführung bleiben getrennte, nicht freigegebene Vorhaben;
hierfür wird kein Folge-Issue ungefragt angelegt.

### Wiederverwendung und verbleibender Umfang

| Bereich | Vorhanden / wiederverwenden | Änderung und eigener Nachweis |
|---|---|---|
| Installation | `tools/samuel-container`, `tools/container_init.py`, manifestgebundenes OCI-Kit aus #970/#971 | Einfacher Einstieg und automatische Artefaktprüfung; vollständiger leerer Docker-Host statt vorbereiteter Smoke-Artefaktsammlung. |
| Setup und lokale Identität | Bestehende Dashboard-/Setupfunktionen, `samuel identity bootstrap/cutover`, R15a | Administratoraufnahme in den Installationsaufruf integrieren; keine manuell vorzubereitende Passwortdatei oder versteckte zusätzliche Identitybefehle. Cutover bestätigt Inventur und Begründung ausdrücklich. |
| LLM und Prompts | ConfigurationSession aus #992/#878 für `llm.json`, `llm/defaults.json`, `llm/prompts` | Bestehende UI und Aktivierung ohne Dienstneustart erhalten; keine Ausweitung auf Secrets, Budgets oder Featureflags. |
| Eine Projektbindung | `samuel/project_binding.py`, Operatoraktion `project` aus #988/#989 | Dashboard bereitet vor; Operator prüft und bestätigt Hostbindung. Pfad-, Inode-, Rechte-, Repo- und Overlayprüfungen erhalten; kein neuer Projektmanager. |
| Release und Updates | Releasegates, Manifest-/Digestprüfung, Compose, native Releasehilfe gemäß ADR-0706 | TUF mit vorhandener Implementierung integrieren, keine eigene Kryptografie. Eine OCI-Operatoraktion bündelt Updateprüfungen und Ausführung; keine zweite native Releasehilfe. |
| Backup und Recovery | SQLite-Backup, State-/Witness-, Restore-/Reconcile- und Identityverträge | Zugehörige Konfiguration und Evidence erhalten; Wiederherstellung einer qualifizierten Neuinstallation und Fehlerfälle mit realen Artefakten eigenständig prüfen. |

Die offenen Qualificationumfänge aus #978, #962, #994 und #1072 werden nicht
durch #1090 als erfüllt behandelt. #1089 war Dokumentationsabgleich, keine
neue Runtimefunktion. Die frühere Analyse mit 365 bestandenen Bestandstests
ist Regressionbaseline, keine Abnahme der hier beauftragten Funktionen.

### Benutzerweg und kleine Arbeitspakete

Die nachfolgenden Befehlsformen sind im Entwicklungsstand implementiert.
Die Paketgliederung dokumentiert ihren Umfang, keine zusätzliche Folge manueller
Vorbereitungsschritte. Der vollständige Benutzerweg und die nachgewiesenen Grenzen
stehen in [INSTALL](INSTALL_REFERENCE.md#91-oci-erstinstallation-auf-einem-leeren-docker-host-970)
und im Produktstatus; Teiltests sind weiterhin keine Gesamtqualifikation.

1. **AP 1 – Bestands-/Scopeabgleich:** Diese Disposition, vorhandene Funktionen,
   Quellen und getrennte Nachweise festhalten; keine Runtimeänderung.
2. **AP 2 – Bootstrap/Installation:** Vorhandenen Installer vereinfachen,
   Artefakte automatisch prüfen und den lokalen Identity-Bootstrap einschließlich
   ausdrücklichem Cutover in einen Installationsaufruf integrieren. Anschließend
   im gesicherten Dashboard einrichten. Der spätere explizite Operatoraufruf
   `samuel-container start` bleibt ein eigener, dokumentierter Schritt.
   Bei der leeren Initialisierung liegen die privaten Sicherheitskeys bereits
   vor dem ersten auditierenden Wartungsprozess vor. Installer, CLI-Setup und
   Dashboard verwenden dieselbe Schlüsselerzeugung und erhalten vorhandene Werte.
   Eine neue Installation darf nicht mit unsigniertem Audit beginnen und danach
   still den Schlüssel wechseln; bestehende Segmente werden nicht repariert.
3. **AP 3 – Setup und Projektbindung:** Allgemeine Änderungen im Dashboard
   bündeln. Ein `setup`-Aufruf übernimmt Zulassungsprüfung, kontrollierten
   Production-Stopp und Setup-Start; `start` prüft den Abschluss und wechselt
   zurück. Die einzelne Host-Projektbindung wird unabhängig geprüft. LLM-/
   Promptänderungen benötigen weiterhin nur die ConfigurationSession.
   **Teilstand Schreibschutz:** Allgemeine Dashboard-Setup-Schreibvorgänge
   verwenden die bestehende prozessübergreifende Konfigurationssperre über
   Prüfung und Persistierung hinweg. Das sichert konkurrierende Schreib- und
   Arbeitsstarts ab. Die reale End-to-End-Abnahme ist ein eigener
   Teil von AP 3; ihr commitgebundener Stand steht im Produktstatus.
   **Teilstand Wartungsprotokoll:** Der lokale CLI kann einen gebundenen
   Moduswechsel im vorhandenen Authority-State sperren. Prozessabbruch lässt
   die Sperre bestehen; Dashboard-Konfigurationsaktionen heben sie nicht auf.
   **Installerkopplung:** `install`/`setup`/`start` führen dieses Protokoll
   intern aus; der normale Benutzer erhält keinen weiteren CLI-Schritt.
   Zulassungsprüfung, Stopp, modegerechter Start, Image-/Readinessnachweis und
   expliziter Abschluss sind gekoppelt. Ein reservierter Name des kurzlebigen
   CLI-Containers verhindert auch nach dessen Tod parallele Hostaktionen;
   Prozessverlust kann eine ausdrückliche lokale Recoverybestätigung verlangen.
   Keine Dockerauthority im Container und kein dauerhafter Helferdienst.
   Gestoppte Projekt-/Toolchainregistrierung nutzt dieselbe Wartungssperre.
   Bestandsaufrufe prüfen die Installation zuvor mit dem vorhandenen Helper im
   ausschließlich lesenden Modus `verify-installed`: Config, State, Workspaces,
   Logs und Backups sind dafür read-only gemountet. Fehlende Verzeichnisse oder
   Receipts führen zum Abbruch, niemals zur Neuinitialisierung. Die bisherigen
   Manifest-, Ownership-, Compose- und Registrierungsprüfungen bleiben wirksam.
   **Kurzer Operator-Einstieg:** Dasselbe geprüfte Bootstrap-Paket akzeptiert
   `setup`/`start` mit dem Installationspräfix. Ein ausschließlich lesender,
   nicht vernetzter Prüflauf verwendet die geschützte Quittung, kontrolliert das
   vorhandene Cachekit und delegiert an den bisherigen vollständigen Installer.
   Port und Compose-Projekt bleiben gebunden; keine neue Orchestrierung,
   Cache-Reparatur oder implizite Freigabe. Der vollständige Operatorweg bleibt
   bei fehlendem Bootstrapcache erhalten. Diese Vereinfachung ist kein Update-
   oder Offline-Recoverynachweis.
   **Teilstand Projektvorbereitung:** Das Setupformular speichert ausschließlich
   Daten für die einzelne Erstbindung. `start` prüft diese und die gespeicherte
   SCM-Identität erneut, verlangt eine eigene ausdrückliche Operatorbestätigung
   und verwendet nach dem kontrollierten Stopp die vorhandene Registrierung.
   Kein zusätzlicher normaler `project`-/Compose-Schritt und keine Bindungsänderung
   über das Dashboard. Rolle, CSRF, Production-Freeze, Datenänderung und
   Registrierungsfehler benötigen eigene Funktionsnachweise.
   Reale vollständige Installation, Update-Baseline und Erstvertrauen sind
   getrennte Nachweise; der Produktstatus nennt jeweils Ergebnis und Grenze.
4. **AP 4 – Updatevorbereitung/-ausführung:** Dashboard zeigt Ausgangs-/Zielstand,
   Kompatibilität, Sicherungsbedarf, Blocker und genau den erforderlichen
   Operatoraufruf. `samuel-container update --target <Release-ID>` prüft alles
   unabhängig erneut, verlangt Betreiberfreigabe und bündelt Sicherung,
   zugelassene Migration, Aktivierung und Readiness. Dashboarddaten sind keine
   vertrauenswürdigen Shell-, Image-, Mount- oder Composeanweisungen. Noch nicht
   ausgeführte Hostprüfungen bleiben sichtbar offen.
   **Gekoppelter Operatorweg:** Der Aufruf übernimmt die folgenden internen
   Schritte ohne zusätzliche Normalbenutzerbefehle: lesende Statebeobachtung,
   erneuter signierter Bezug beider Kits aus der privaten Quelle, Prüfung der
   tatsächlichen Zielruntime, ausdrückliche Terminalbestätigung, bestehende
   Wartungssperren mit verwaltetem Backup, kontrollierter Stopp, Dateisicherung,
   getrennte Toolchainvorbereitung, feste Metadatenübernahme und Production-Start.
   Erst geprüfte Zielidentität und technische Readiness erlauben `COMMIT`.
   Ein gewöhnliches Update benötigt keinen vorherigen Setupwechsel und keinen
   nachgelagerten manuellen `start`; allgemeine Konfigurationsänderungen bleiben
   weiterhin an R15a und den bestehenden Setupweg gebunden.
   Der gespeicherte private Vorbereitungshash bindet Ausgang und Ziel für die
   Wartung. Selbst ein direkt aufgerufener gebundener Installer prüft TUF und
   State vor der Bestätigung erneut; Cachebytes sind keine Freigabe.
   `update --recover-update <Vorbereitungshash>` setzt ausschließlich denselben
   weiterhin offenen Vorgang fort. Prüfung auf Pending erfolgt nochmals unter
   den bestehenden Sperren; ein abgeschlossener Vorgang wird nicht neu eröffnet.
   Bei Teilwrites prüft derselbe Metadatenbaustein zunächst ohne Writes, dass
   jede Datei entweder exakt dem gesicherten alten oder dem gebundenen Zielstand
   entspricht. Fremde Änderungen werden nicht repariert. Keine automatische
   Rücksicherung, kein Workflowstart und kein abgeschwächter Restore-/Reconcileweg.
   Der Installer gibt vor Beginn auch einen vollständig gebundenen Recoveryaufruf
   aus. Vor dessen Verwendung müssen der vorherige Operatorprozess und seine
   Hostaktionen beendet sein. Auch eine abgelaufene Wartungsaufnahme kann bereits
   Pending-State und Backup hinterlassen, obwohl die Quellruntime noch läuft.
   Ihr Fehlerhinweis bleibt an `--recover-update` beziehungsweise die ausdrücklich
   gewählte Quellrestoration `--restore-update` gebunden; der allgemeine
   Moduswechsel-Parameter `--recover-maintenance` gilt nicht für Updates.
   Releasebezug/Registry müssen erreichbar bleiben;
   allgemeine Offline-Recovery wird hierdurch nicht zugesichert.
   `update --restore-update <Vorbereitungshash>` ist die gesondert bestätigte
   Rücksicherung nach begonnener Metadatenübernahme: feste Quelldateien aus dem
   geprüften Capture, danach der bestehende State-Restore im Quellimage unter
   gehaltenen Wartungssperren. Kein allgemeines Entpacken, keine Rücksetzung des
   aktuellen Witness oder der Auditdateien, kein automatischer Productionstart.
   Der vorhandene State-Restore erzwingt eine neue Authority-Linie, Reconcile,
   Retention-STOP und gegebenenfalls Identity-Recovery. Ein begonnener Restore
   sperrt die Vorwärtsaktivierung desselben Updates. Die notwendigen lokalen
   Reconcile-/Identity-/Startschritte sind im
   [Benutzerweg](INSTALL_REFERENCE.md#kontrolliertes-oci-update-und-gebundene-fortsetzung-1090)
   ausdrücklich Teil des Fehlerfalls; ihre Ausgabe ist kein Nachweis ihres
   erfolgreichen Abschlusses.
   Beim Moduswechsel hält der Operator die Aufnahme dauerhaft gesperrt.
   Nach seiner Bestätigung schreibt er `host_transition_commit_requested`,
   speichert die Entscheidung mit Vorgangskennung, Ziel, Installationsbindung
   und `commit_version` im Zustand `maintenance/pending` und protokolliert
   diesen Zwischenstand als `host_transition_commit_recorded`. Die konfigurierten
   primären JSONL-Transkripte müssen ihren Schreibvorgang synchron bestätigen.
   Erst dann speichert der Operator den Zielzustand und die Quittung
   `last_host_transition`; danach meldet der CLI den Abschluss.
   `state status --read-only --json` zeigt den offenen Vorgang oder die letzte
   Quittung. Nach einem Abbruch vor der Freigabe den bisherigen Operatorweg
   mit derselben Installation und demselben Ziel fortsetzen. Mehrere signierte
   Beobachtungen derselben Vorgangskennung und Commit-Version gehören zur
   selben Entscheidung. Für die Abnahme Quittung, Zielzustand, State/Witness,
   Auditkette und CLI-Ergebnis gemeinsam prüfen. Historische
   `host_transition_completed`-Ereignisse aus a38 können dem tatsächlichen
   Schreibversuch vorausgehen und benötigen einen unabhängigen Zustandsnachweis.
   Eine vollständig wiederhergestellte und reconciliierte Installation kann
   erneut ein reguläres Update vorbereiten. Die Vorprüfung verwendet den
   bestehenden UUID-/Epoch-Vertrag des State-Stores, einschließlich der beim
   Restore erzeugten UUID mit Bindestrichen. Die Instanzkennung wird nicht
   umgeschrieben oder normalisiert; Witness, alte Vorbereitung und neue
   Betreiberfreigabe müssen weiterhin zum tatsächlichen Zustand passen.
   Funktionsprüfungen, zukünftiges qualifiziertes Update, vollständiger Restore und Erstvertrauen
   bleiben getrennte Nachweisstufen; die Kopplung allein schließt keinen davon.
   **Teilstand State-Sicherung:** Das vorhandene interne Wartungsprotokoll kann
   mit `--backup-before-transition` das bestehende verwaltete SQLite-Backup unter
   beiden Prozesssperren erstellen, bevor der neue Wartungszustand geschrieben
   wird. Nur ein vollständig ruhender Zustand und das Ziel `production` sind
   zulässig. Backupfehler, neue Blocker und erneuter Aufruf bei bereits offener
   Wartung geben keine Hostaktion frei. Die Backupreferenz wird mit dem offenen
   Wartungszustand atomar über dessen bestehenden CAS gespeichert, vor Audit und
   Ausgabe. Ein passend gebundener Wiederanlauf ohne neue Backupanforderung erhält
   dieselbe Referenz; ein verlorener CLI-Ausgabestrom erzwingt keine erratene
   Backupauswahl. Artefaktprüfung, ausdrückliche Fortsetzung und Restorefreigabe
   bleiben getrennt. Die ergänzende interne Funktion
   `capture_update_files` im vorhandenen Installerhelfer archiviert dieses
   verwaltete Backup mit Konfiguration, Runtime-Dateien einschließlich Witness,
   Logs/Evidence, Workspaces und optional gebundener Verifier-Toolchain. Sie
   übernimmt keine Live-SQLite-/WAL-Dateien und führt keinen Restore aus.
   Dateirechte, Owner, Links, Zeitstempel und Extended Attributes werden als
   Daten erhalten; externe Symlinkziele werden nicht gelesen. Der Aufrufer muss
   zuvor Wartungssperren halten und alle Schreiber stoppen. Der gekoppelte
   Operatorweg übernimmt dies. Für kurzlebige Installer-Prüfcontainer,
   Setup-/Identity-CLI und den
   Wartungscontainer wird der geerbte Image-Healthcheck deaktiviert: Er startet
   selbst Bootstrap und Auditschreiber und könnte sonst neben der ausdrücklich
   gewählten Prüfung oder während der Sicherung zusätzliche Schreibzugriffe
   verursachen. Die jeweilige CLI-Prüfung und ihr Exitstatus bleiben verpflichtend.
   Runtime-Healthcheck, ausdrückliche Ziel-Readiness und das
   Wartungsprotokoll bleiben unverändert aktiv. Der Wartungsaufruf verwendet
   den gemeinsamen Bootstrap nur bis zur State-, Audit- und SCM-Verdrahtung.
   LLM-Adapter, Workflow-Slices und deren Startup-Healthprüfung werden dafür
   nicht gestartet. Die bestehenden lokalen und externen Blocker, beide
   Prozesssperren, Backupprüfung und ausdrückliche Bestätigung bleiben erhalten;
   die erste Antwort erhält einschließlich Compose-/Containerstart und Sicherung
   ein begrenztes Zeitfenster von 180 Sekunden. Erst die geprüfte Aufnahme erlaubt
   Hostaktionen; späte oder fehlende Antworten erteilen keine Freigabe. Die
   Folgeantwort nach dem Backup und der Abschluss behalten jeweils 60 Sekunden.
   Der normale Image-Healthcheck
   startet seinen Prüfer per `exec`, damit ein Docker-Timeout den Prüfer selbst
   beendet und kein verwaister zusätzlicher Auditschreiber weiterläuft.
   Zeitbudget und Fehlerstatus bleiben erhalten. Die reale Dateisicherungs-/Recoveryabnahme ist weiterhin separat nachzuweisen;
   weder SQLite-Backup noch Archiv-Komponententests sind ein Restore-PASS.
   **Teilstand Release-Metadaten:** `prepare_update_metadata` im vorhandenen
   Installerhelfer bereitet ausschließlich die festen Receipt-/Compose- und
   mechanischen Projekt-/Toolchainbindungen vor. Die tatsächliche Zielruntime
   muss Version, Revision, Plattform, Schema und unveränderte UID/GID bestätigen.
   Vorhandene Konfigurationsbytes werden nicht geschrieben; eine Toolchain wird
   nur mit separat geprüfter Zielkopie und identischen alten Paket-/Lockbytes
   umgebunden. Die bestehende Registrierungsfunktion erzeugt ihre neue Metadaten-
   darstellung in einem privaten temporären Layout. Quellenänderungen blockieren
   das Ergebnis. Der Rückgabewert ist keine Aktivierung oder Betreiberfreigabe;
   Wartung, Zielstart und ausdrücklicher Abschluss bleiben Aufgaben des
   gekoppelten öffentlichen Operatoraufrufs.
   **Teilstand Dateiübernahme:** `apply_update_metadata` bereitet diese Zielbytes
   unabhängig erneut vor und prüft die private Sicherungsquittung, das gesamte
   Archiv sowie die gebundenen alten Metadaten und Pflichtartefakte. Erst danach
   legt es eine dauerhafte offene Vorgangsquittung an. Der vorhandene Dateischreiber
   übernimmt die festen Dateien unter Erhalt von Ownern, Rechten und Extended
   Attributes; das Installationsreceipt folgt zuletzt. Kontrollierte Schreibfehler
   verwenden dessen bisherigen Rollback. Ein Prozessverlust kann einen Teilstand
   hinterlassen; implizite Wiederholung wird abgewiesen, die ursprüngliche Sicherung bleibt
   erhalten. Die Erfolgsquittung bestätigt nur übernommene Metadaten, keinen
   Runtime-Start oder Wartungsabschluss. Diese interne Funktion verlangt einen
   ausdrücklich freigegebenen, gestoppten und gesperrten Operatorvorgang. Die
   interne Funktion allein beweist keine durchgängige Update-/Recoveryausführung.
   **Teilstand explizite Metadatenfortsetzung:** Derselbe interne Baustein kann
   nach ausdrücklichem Recoveryauftrag ausschließlich den bereits gebundenen
   Zielstand fertigstellen. Er rekonstruiert die festen alten Metadaten in einem
   privaten temporären Layout, prüft Manifest, Zielruntime, Installer und
   Toolchain erneut und vergleicht die private offene Vorgangsquittung exakt.
   Für diese Rekonstruktion benötigen auch der reine Recovery-Vorprüfer und
   die Recovery-Toolchainprüfung neben `DAC_READ_SEARCH` gezielt `CHOWN` und
   `FOWNER`. Sie setzen Owner und Modi ausschließlich im privaten `/tmp` nach;
   aktive Konfiguration, Daten, Logs, Backups und Releasecache bleiben in diesen
   Schritten schreibgeschützt. Nur die Toolchainvorbereitung darf zusätzlich
   ihre feste Zielkopie im Toolchainverzeichnis anlegen. Kein Docker-Socket,
   kein Netzwerkzugriff und kein allgemein privilegierter Container.
   Aktive Dateien dürfen nur die gesicherten alten oder die erneut berechneten
   Zielbytes enthalten; andere Inhalte, Owner oder Attribute blockieren. Auch
   die unveränderte Operator-`.env` gehört zum Quellvergleich. Bereits korrekte
   Zieldateien werden nicht neu geschrieben, aber einschließlich Elternordnern
   erneut synchronisiert. Keine allgemeine Archive-Extraktion, State-Rücksetzung,
   neue Releasefreigabe, Runtime-Aktivierung oder Öffnung der Wartungssperre.
   Die öffentliche Recoverykopplung prüft den weiterhin anhängigen
   Wartungsvorgang und die ausdrückliche Betreiberentscheidung zusätzlich.
5. **AP 5 – Recovery und zukünftige Baseline:** Zur frisch installierten Version gehörende
   Daten, Konfiguration, Freigaben und Evidence gemeinsam sichern und wiederherstellen.
   Audit, Witness und ausdrücklichen Neustart über die lokale Operator-CLI prüfen.
   Der frühere Auftrag zur a34-Migration ist durch die spätere Scopeentscheidung zurückgestellt.
6. **Ersatz-/Gesamtabnahme:** Erst nach unabhängig bestandenem Ersatznachweis
   entbehrliche Benutzer-Wizardteile entfernen; benötigte Setupfunktionen
   erhalten. Endgültigen Benutzerweg mit allen tatsächlichen Schritten prüfen.
   Der separate interaktive CLI-Fragebogen ist durch die vorhandenen
   Dashboardfelder ersetzt. `setup --non-interactive`, gemeinsame private
   Dateischreiber, Schlüsselinitialisierung, Setup-APIs, Labelabgleich und
   Doctor bleiben erhalten. Ein alter Aufruf `setup` ohne Flag schreibt nichts
   und nennt den Dashboardweg; Skripte verwenden das bestehende ausdrückliche
   Flag. Die frühere CLI-Repoliste ist keine zusätzliche Projektverwaltung:
   das gewünschte einzelne Repository wird im Dashboard angegeben.

Jedes Paket enthält seine betroffenen Betriebs-/Entwicklungsdokumente und
passenden Tests im selben PR. Abhängige Pakete bauen auf integriertem Stand auf;
kein Sammel-PR für den gesamten Lifecycle. Fehlende öffentliche Distribution
blockiert nicht die davon unabhängige Implementierung und Funktionsprüfung.

Im normalen Betrieb und für registrierte LLM-/Promptänderungen ist kein
Setupwechsel nötig. Allgemeine Änderungen verlangen je gebündelter Sitzung
einen Eintritt und einen Rückwechsel; eine empirische Häufigkeit ist nicht
nachgewiesen. Updates führen nicht erneut durch den Konfigurationswizard.
Production-Start, Update und erfolgreiche Health erteilen weder Workflowstart
noch Wiederaufnahmefreigabe. R15a und bestehende Approval-/Evidencegrenzen
bleiben unverändert.

<a id="deklarierter-oci-updatevertrag-ap-4-noch-keine-ausführung"></a>

### Deklarierter OCI-Updatevertrag (AP 4)

Der vorhandene Manifest-Publisher ergänzt bei neu gebauten Nachfolgern von
a34 ein `update_contract`-Objekt. Bestehende veröffentlichte Manifeste bleiben
unverändert. Die Deklaration `oci-update.v1` nennt unterstützte Quellversionen
explizit, Quell-/Ziel-State-Schema 10, unveränderte
Runtime-UID/GID und `project-binding.v2`. Konfiguration, Credentials, lokale
Identität, Authority/Freigaben, Evidence, Workspaces und Projektbindung müssen
erhalten bleiben. Für diesen Schema-10-Pfad ist `migration=none`; ein anderes
Schema benötigt einen eigenen geprüften Migrationsvertrag. Ein Codewechsel
an State- oder Projektbindingschema blockiert die Manifestergänzung, bis der
Vertrag ausdrücklich angepasst wurde.

Die reine Prüfung im bestehenden Releasemodul lehnt fehlende/abgeschwächte
Verträge, unbekannte Quellversionen, Downgrades, abweichende Schemas und freie
Migrations-/Befehlsfelder ab. `declared_compatible` bedeutet ausschließlich,
dass die vorgelegten Daten diesen Vertrag erfüllen. Authentisierter
Manifestbezug, tatsächliche Host-/Konfigurationsprüfung, Backup und ausdrückliche
Operatorfreigabe bleiben separate Pflichtprüfungen. Der Rückgabewert weist
Hostchecks als `not_verified` und Qualification als `not_evaluated` aus.

Die früheren Kandidaten deklarierten `2.0.0a34` als Quelle. Nach a38
erzeugt der Publisher zunächst eine leere Liste `source_versions`.
Installation eines frischen Releases bleibt möglich. Das Dashboard und der
Operatorpfad weisen Updates auf ein solches Ziel bei der gemeinsamen
Kompatibilitätsprüfung ab. Für ein späteres Ziel ist die konkrete, geprüfte
Quellversion ausdrücklich in dessen Vertrag einzutragen.

Die Deklaration allein ist weder eine erfolgreiche reale a34-Migration noch die
Berechtigung, mit dem bisherigen Erstinstaller ein Update auszuführen. Die
implementierte Dashboard-/Operator-/Recoverykopplung führt die nachfolgend
beschriebenen Prüfungen aus; ihre tatsächlichen Nachweise bleiben commit- und
subjectgebunden im Produktstatus erhalten. Neue freigegebene Quellversionen müssen im
bestehenden Releasevertrag gezielt ergänzt und qualifiziert werden; kein
Versionsbereich oder alleiniger gleicher Schemanummernwert erteilt pauschale
Updatefreigabe. Kein neuer Publisher, Server oder Migrationsdienst.

Die gemeinsame Updatevorbereitung im vorhandenen Releasemodul verwendet die
gebundene Quelle, eine ausdrücklich gewählte kanonische Zielversion und den
bestehenden TUF-/Artefaktbezug. Ein signiertes Manifest mit einer anderen Version
wird ebenso abgewiesen wie ein fehlender oder inkompatibler Updatevertrag.
Die Rückgabe bindet Quelldokument und Zielmanifest per SHA-256 und benennt die
zu sichernden Datenklassen einschließlich SQLite-Onlinebackup, Authority-Witness,
Identität, Projekt-/Toolchainbindung und bisherigem Installer. Sie entpackt,
installiert, migriert oder startet nichts und erteilt keine Freigabe.

Der vorhandene Containerhelper kann anschließend mit `prepare_update_installer`
das Zielkit für den Operator vorbereiten. Er wiederholt zuerst die gemeinsame
Prüfung mit festem root-Owner der privaten Quelle und eigenem Cache. Erst danach
verwendet er dieselbe Archiv-/Deliveryprüfung wie der Bootstrap, statt einen
zweiten Entpacker einzuführen. Die Rückgabe nennt ausschließlich gebundene
Cachepfade; bestehende Kits werden erneut geprüft und bei Abweichung weder
überschrieben noch repariert. Das ist die interne Vorbereitung des gekoppelten Operatorwegs, kein
zusätzlicher Normalbenutzerbefehl. Es gibt
weiterhin keine Aktivierung, Sicherung, Datenmigration oder Freigabe durch diese
Funktion; tatsächliche Host-/State-/Zielruntimeprüfung bleibt erforderlich.

`prepare_installed_update` koppelt diese Vorbereitung mit dem tatsächlichen,
privaten Installationsreceipt. Beide Releasekits werden über den vorhandenen
TUF-/Artefaktpfad und denselben Entpacker geprüft. Das Quellmanifest muss exakt
zum gespeicherten Manifesthash, Image, Version und Commit passen; das Altkit
bleibt für Dateisicherung und Recovery erforderlich. Fehlende oder nicht mehr
signiert verfügbare Altartefakte blockieren diesen Vorbereitungspfad. Ein
Dashboardcache oder mitgelieferter Hash ersetzt den Nachweis nicht.

Eine vorhandene private Releasequelle bleibt maßgeblich. Ein neueres,
ausdrücklich bereitgestelltes Bootstrap-Paket darf einen neueren Verifier binden,
aber weder Root, Bezugsadressen noch Zielauflösung der Installation ändern.
Nur für tatsächliches a34 ist ein fehlender neuer Releasequellen-Eintrag zulässig:
Die Quelle wird dann aus der expliziten Paketbindung vorläufig vorbereitet und
als noch zu übernehmen ausgewiesen. Weder Installation noch Vertrauensquelle
werden dabei geschrieben. Bei anderen Versionen ist ein fehlender Eintrag ein
Recoveryfall; beschädigte oder manipulierte Einträge werden nie ersetzt.
Änderungen von Receipt oder Quelle während des Bezugs verhindern ein vollständiges
Vorbereitungsergebnis. Erstvertrauen bleibt unabhängig offen.

Die vorgelagerte Statebeobachtung verwendet `state status --read-only --json`
mit dem vorhandenen lesenden SQLite-Adapter. Der gewöhnliche Statusaufruf kann
initialisieren oder migrieren und ist dafür ungeeignet. Schemawerte dieser
internen Vorbereitung sind tatsächlich zu beobachten; sie sind keine
Dashboardanweisung oder freigegebene Migrationsvorgabe. Reconcile-/Workflowblocker,
Zielruntimeidentität, gehaltene Wartung, Sicherung und ausdrückliche Freigabe
bleiben Pflichten des äußeren Operatoraufrufs. Dieser Teilnachweis ist noch keine
öffentliche Updateausführung oder erfolgreiche a34-Gesamtmigration.

Für die unabhängige Auswahl der bestehenden Installation liest derselbe Helper
mit `read_installation_receipt` das vorhandene `.container-install.json`.
Die gemeinsame Dateilesefunktion prüft tatsächlich geöffnete reguläre Bytes,
root-Owner/-Gruppe, private Rechte, Größenlimit und Änderungen während des Lesens.
Das Receipt muss exakt dem bekannten Einzelprojektlayout unter dem ausdrücklich
gewählten Hostpräfix entsprechen. Version, Revision, Imagedigest, Manifesthash,
Port, Projektname und nicht privilegierte Runtime-UID/GID werden validiert;
zusätzliche Felder oder fremde Pfadklassen sind unzulässig. Die Rückgabe enthält
den Hash genau dieser Bytes. Sie allein bestätigt weder einen laufenden Container
noch den Manifestinhalt oder vorhandene Mounts; die bestehenden unabhängigen
Release-/Layout-/Zustandsprüfungen bleiben vor Hostaktionen erforderlich.
Der Leser schreibt, repariert und initialisiert nichts und stellt noch keinen
öffentlichen Updateaufruf bereit.

Die Dashboardanbindung zeigt diese Vorbereitung mit getrennten lokalen und
ausdrücklich abgefragten SCM-Blockern. Die passive Ansicht lädt keine Releases;
parallele Vorbereitung wird abgewiesen, geänderte Installations-/Quellenbindungen
werden sichtbar veraltet. Sie schreibt keine Konfiguration oder Freigabe.
Eine aktuelle Vorbereitung ohne bekannte Blocker zeigt den notwendigen lokalen
Operatoraufruf. Er wird im unabhängig geprüften Bootstrap-Paket mit denselben
Hostrechten und gegebenenfalls demselben `--root` ausgeführt. Die Oberfläche
führt ihn nicht aus. Der Operator muss die gemeinsame Prüfung mit
der geschützten eigenen Quelle, eigenem Cache und erneut
beobachtetem Installationszustand ausführen. Manipulierte Dashboardangaben zu
Freigabe, Hostchecks oder Erstvertrauen werden dadurch nicht übernommen. Auch
erfolgreiche Vorbereitung bedeutet nur deklarierte Kompatibilität; tatsächliche
Host-/Zielruntimeprüfungen, Backup, Betreiberfreigabe, Recovery und Erstvertrauen
bleiben gesondert nachzuweisen.

Die Deklaration grenzt mechanische Releasebindungen mit `release_rebinding`
ausdrücklich ein: Installations-Releaseidentität, Installationshash der gleichen
Projektbindung und erneut geprüfte Releaseidentität der Verifier-Toolchain.
Keine Workflowfreigabe oder fachliche Policy darf dadurch übertragen oder
umgeschrieben werden. Bestehende Freigaben/Evidence bleiben an ihren bisherigen
Subject gebunden; die neue Toolchain erhält einen neuen Gate-Policy-Digest und
benötigt neue Ausführungsnachweise. Aktive oder fortsetzbar wartende Vorgänge
bleiben durch die bestehende Wartungszulassung blockierend.

Die vorbereitenden Funktionen im bestehenden Projekt-/Toolchainmodul verändern
keine aktive Registrierung. Projektpfad, Repoidentität, initiale Revision,
Quell-Dateisystemidentität, UID/GID und alle Installationspfade bleiben gleich;
nur der Hash des geprüften neuen Installationsreceipts wird vorbereitet. Ein
inzwischen fortgeschrittener Checkout wird nicht auf den initialen SHA
zurückgesetzt. Der Operator muss den tatsächlichen Hostzustand zusätzlich prüfen.

Bei einer registrierten Python-Toolchain werden bestehende Lock-, Paket- und
Distributionsbytes sowie die bisherige Release-/Imagebindung geprüft. Nur bei
identischer Python-/Plattformidentität wird eine getrennte neue Kopie vorbereitet,
mit neuem Release-/Imagedigest gebunden und durch den unveränderten Runtime-
Validator erneut geprüft. Keine Paketauflösung, kein Download, keine Candidate-
Hooks und keine Änderung des alten Toolchainbaums. Andere Python-/Plattformstände,
Drift, Pfadüberlappung oder Teilfehler blockieren; ein Teilverzeichnis ist kein
fertiges Ergebnis. Tatsächliche Target-Runner-/Readinessprüfung, gebundene
Aktivierung, Backup und Recovery bleiben Aufgabe der anschließenden Installer-
Anbindung. Diese Funktionen sind noch kein ausführbarer Updateaufruf.

### GitHub-Einstieg für eine öffentliche Alpha vorbereiten

Der geprüfte öffentliche Schema-2-Dateisatz bindet das öffentliche Image unter
`ghcr.io/alexander-benesch/samuel@sha256:…`. Die TUF-Metadaten und Targets
werden als Dateien des versionierten GitHub-Prereleases ausgeliefert. Das
Manifest hat den Targetnamen `release-manifest.json`. Die Dateinamen im
Release müssen dem gewählten TUF-Modus für Versions- und Hashpräfixe entsprechen.

Im Release-Verzeichnis den Einstieg aus dem Manifest, dem danebenliegenden
OCI-Kit und der für dieses öffentliche Release bestimmten, signierten
TUF-Root erzeugen:

```bash
python /pfad/zum/checkout/tools/github_bootstrap.py release-manifest.json trusted-root.json samuel-install.sh
```

Der Generator bindet Installer und Helper aus dem geprüften Kit, die öffentlichen
Root-Metadaten, das Image und den HTTPS-Pfad für genau dieses Tag. Private
Signierschlüssel verbleiben beim Publisher. Vor der Freigabe eine frische
Installation und den Abbruch bei veränderten Downloads prüfen. Die öffentliche
Abnahme verwendet anschließend den README-Befehl und einen anonymen Imagepull.

### Bootstrap-Vertrauen und relevante Transportgrenzen

| Grenze / beobachteter Stand | Verbindliche Behandlung |
|---|---|
| Nativer Gitea-Bezug | Am 13.11.2026 antwortete der konfigurierte interne Endpunkt über HTTP; TLS am selben Host/Port scheiterte. Konkrete private Adresse bleibt Betreiberkonfiguration. Andere TLS-Zugänge und durchgängiges HTTPS sind nicht nachgewiesen. |
| Publisher/Registry | Vorhandene Owner-/Token-Scope-, Manifest- und Digestprüfungen erhalten. `--registry-insecure` ist eine explizite interne Transportausnahme, kein Erstvertrauensnachweis; Authentisierung allein schützt keine unverschlüsselte Übertragung. |
| Setup-/Production-Dashboard | Installer bindet den Hostport an Loopback und nennt für entfernte Hosts einen SSH-Tunnel. HTTP im internen Containerpfad und lokale Identity-/API-Prüfungen ergeben keine HTTPS-Zusage. Eine benötigte Tunnel-/Zugriffseinrichtung gehört sichtbar zum konkreten Benutzerweg. |
| SCM-/Providerzugänge | Bereits konfigurierte HTTP-/HTTPS-Ziele getrennt prüfen und in der laufbezogenen Evidence ohne Secrets erfassen. Ein funktionierender Zugang qualifiziert keinen anderen Transport. |

**Phase 1 – interne Alpha-/Beta-Qualifikation:** Ein versioniertes Bootstrap-Paket
mit gebundener initialer TUF-Root darf nur über einen ausdrücklich bestimmten,
authentisierten und unabhängig verifizierten Übergabeweg benutzt werden. Vor
seiner ersten Ausführung das gesamte Paket gegen die unabhängig authentisierte
Bindung prüfen; ein mitgelieferter Hash aus derselben ungeprüften Quelle genügt
nicht. Für diese interne Übergabe blieben Übergabeweg und Root **OFFEN / NOT_VERIFIED**. Der Nachweis
bindet Betreiberentscheidung, Paketversion/-Digest, Root-Version/-Digest und
Schlüssel-/Schwellwertkonfiguration sowie die Zielhostprüfung. Keine privaten
Schlüssel oder Zugangsdaten in Evidence. Die TUF-Root wird nicht erst aus einem
unverifizierten Bootstrap als vertrauenswürdig übernommen.

**Öffentliche Erstinstallation.** Seit dem 26.11.2026 enthält das [GitHub-Release v2.0.0a42](https://github.com/Alexander-Benesch/S.A.M.U.E.L./releases/tag/v2.0.0a42) den Installer für das öffentliche Docker-Image.

**Planungsstand vom 19.11.2026.** GitHub war die vom Betreiber am 19.11.2026
bestimmte Plattform. Das Folgevorhaben #1140 führt den konkreten HTTPS-Bezug
für Erstinstallation und Updates, den vertrauenswürdigen Bootstrap, die
initiale TUF-Root und die automatische Updateprüfung. URL, Vertrauensbindung
und Zielhostablauf benötigen eine eigene Qualifikation. Die unabhängige
interne Erstübergabe bleibt technisch NOT_VERIFIED. Der Betreiber hat sie am
selben Tag aus den Abschlusskriterien von #1090 genommen.

### TUF-Artefaktbezug im vorhandenen Release-CLI

`samuel-release fetch` verwendet `python-tuf` für Root-Rotation,
Signaturschwellwerte, Ablaufzeiten, Metadatenversionen und Target-Prüfung.
Die vorhandenen Installer-/Manifest-/Imageprüfungen bleiben anschließend
erforderlich. Ein signiertes Artefakt ist noch kein kompatibles oder zur
Aktivierung freigegebenes Release.

Für die interne technische Qualifikation sind alle Eingaben ausdrücklich
bereitzustellen: `--trust-root FILE`, `--trust-root-sha256 SHA256`,
`--metadata-url URL`, `--targets-url URL`, `--cache-dir DIR` und `--target PATH`.
Es gibt keine voreingestellte Downloadadresse oder Root. Die Root-Datei muss
außerhalb des schreibbaren Cache liegen; ihre Bytes werden vor jedem Bezug
gegen die unabhängig bereitgestellte SHA-256-Bindung geprüft. Ein Hash aus
demselben ungeprüften Paket ist kein unabhängiger Nachweis. Die tatsächliche
authentisierte Übergabe des ausgeführten Bootstrap-Codes **und** der Root bleibt
der oben beschriebene offene Erstvertrauensnachweis. Auch ein erfolgreicher
Bezug meldet deshalb `initial_handoff: not_qualified_by_this_check`.

Mit `--release` bezeichnet `--target` das Release-Manifest. Der Befehl prüft
Manifestidentität, Schema und die vollständige Artefaktliste und bezieht dann
alle Einträge über denselben TUF-Vertrag. Die Targets liegen im selben
signierten Verzeichnis wie das Manifest; die Manifestnamen sind einfache,
eindeutige Dateinamen, keine URLs oder Hostpfade. Jedes Artefakt muss sowohl
seine TUF-Bindung als auch Länge und SHA-256 im Manifest erfüllen. Der bestehende
Manifestprüfer der nativen Releasehilfe wird dafür wiederverwendet. Erst nach
vollständigem Erfolg enthält die JSON-Ausgabe Manifest- und Artefaktreceipts
sowie Version und Revision. Bei einem Fehler gibt es kein vollständiges
Ergebnis; bereits verifizierte Cachedateien bleiben erhalten. Auch dieses
Ergebnis autorisiert weder Entpacken noch Installation oder Aktivierung und
qualifiziert keine Erstübergabe. Der spätere Bootstrap kann diesen Baustein
verwenden; die technischen Flags sind keine zusätzlichen Normalbenutzerschritte.

Der Cache ist ein privates Operatorverzeichnis mit Modus `0700`, getrennt von
Runtime-State und Konfiguration. Dieselben Cachepfade bei Folgebezügen
weiterverwenden: Die gespeicherten signierten Metadaten enthalten den Stand
für die Rollbackprüfung. Einen beschädigten Cache nicht still löschen und
neu initialisieren. Eine lokale Prozesssperre verhindert parallele Bezüge;
ein abgebrochener Download ersetzt kein zuvor verifiziertes Artefakt. Die
Bibliothek prüft Ablaufzeiten gegen die Uhr des ausführenden Hosts.

HTTP und HTTPS sind ausdrücklich konfigurierbare Transportwege. TUF prüft
die signierten Inhalte; der Befehl bestätigt weder TLS noch eine vertrauliche
Übertragung. Zugangsdaten in URLs, Queryparameter, Fragmente, lokale Datei-URLs,
Traversal und Root-Symlinks werden abgewiesen. Ein privater Distributionsweg
mit zusätzlicher Transportauthentisierung ist dadurch noch nicht integriert
oder qualifiziert. Kein neuer Server oder TLS-Aufbau ist Bestandteil dieses
Teilpakets.

Die JSON-Ausgabe nennt verifizierten Targetpfad, lokalen Artefaktpfad, Länge,
SHA-256 und Root-Bindung. Artefakte werden unter ihrem unveränderten Dateinamen
in einem Hashverzeichnis abgelegt. Kein Entpacken, Docker-Aufruf, Dienstwechsel,
Runtimebootstrap, Update oder Workflowstart folgt daraus. Die bestehenden
lokalen `init`-/`stage`-/`verify`-/`activate`-Funktionen laden den TUF-Client
nicht und bleiben bei einem fehlenden Trust-Client aufrufbar. Dieser technische
Bezugsbefehl ist kein zusätzlicher manueller Schritt des geplanten normalen
Ein-Aufruf-Installationswegs; der vorhandene Installer ruft ihn intern über
das nachfolgend beschriebene Profil auf.

Das Bootstrap-Profil ist ein **Distributionsinput**, keine neue Runtime-
Konfiguration oder Freigabequelle. Es wird zusammen mit dem versionierten
Installer/Helper und der benachbarten `trusted-root.json` über den ausdrücklich
festzulegenden Übergabeweg bereitgestellt. Seine strikte JSON-Oberfläche ist:

| Feld | Bindung |
|---|---|
| `schema_version` | Ganzzahl `1` |
| `bootstrap_image` | Unveränderliche Produktimagereferenz `…@sha256:…` mit integriertem Release-/TUF-Bezug; keine neue Imageart |
| `trust_root_sha256` | Unabhängig verifizierte SHA-256-Bindung der initialen Root |
| `metadata_url`, `targets_url` | Explizite Transportendpunkte nach dem oben genannten Vertrag |
| `manifest_target` | Sicherer relativer Targetpfad des gewünschten Release-Manifests |
| `manifest_target_template` (optional) | Betreiberseitig bestimmter relativer Targetpfad mit genau einem `{version}` für spätere Versionsauswahl; keine URL, kein Shelltemplate. Ohne dieses Feld bleibt die Installation möglich, die Versionsauflösung für Updatevorbereitung ausdrücklich unkonfiguriert. |

Es gibt kein ausgeliefertes Profil mit produktiven Beispielwerten. Vor der
**ersten Ausführung** müssen Paket/Code, Imagebindung und initiale Root unabhängig
authentisiert sein; das Programm kann diese Betreiberentscheidung nicht selbst
beweisen. Das Profil darf keine Shellbefehle, Mounts oder Composeaufträge
enthalten. Der Prüflauf hat nur lesende Bootstrapinputs und einen privaten
Cachemount. Archivpfade, Links, doppelte Dateien und fehlende Pflichtdateien
werden vor dem Entpacken abgewiesen; danach prüft der vorhandene Deliveryvertrag
alle ausgelieferten Installer-/Composebytes erneut. Erst dann führt der Host
das gebundene vorhandene Installationsprogramm aus. Es gibt keinen zusätzlichen
manuellen `fetch`-, Prüfsummen- oder Entpackschritt im Benutzerweg.

Der äußere Installer-Cache bleibt privat (`0700`). Das veröffentlichte Kit
innerhalb dieser Grenze erhält ausdrücklich lesbare Verzeichnisse (`0755`)
und Dateien (`0644`), unabhängig von der privaten Operator-umask. Nur dieses Kit
wird für die Deliveryprüfung read-only eingebunden; der Prüfer bleibt beim
nicht privilegierten Imagebenutzer. Bestehende abweichende Kitrechte führen
zum Abbruch statt zu einer stillen Rechtekorrektur.

Der Bootstrap erhält das validierte Profil und die ursprünglichen öffentlichen
Root-Metadaten als inhaltsgebundenen Quelldatensatz im vorhandenen privaten
Cache. Der bestehende Initialisierungshelper legt bei der Erstinstallation
eine Operatorquelle `/etc/samuel/.release-source.json` (root, `0600`) und eine
separate Runtimeprojektion `config/release-source.json` (Runtime-Owner, `0600`)
an. Bei `--root` gelten dieselben Prefixpfade. Die Projektion ist Dateninput
für spätere Dashboardvorbereitung, keine Hostauthority. Privilegierte Aktionen
müssen die getrennte Operatorquelle unabhängig lesen und prüfen; eine veränderte
Runtimekopie darf sie nicht ersetzen. Das verlangt keinen weiteren Benutzeraufruf. Der bestehende
Quellenleser kann Eigentümer und private Dateirechte am tatsächlich geöffneten
Dateideskriptor erzwingen; die privilegierte Wiederprüfung muss dafür fest
`source_owner=(0, 0)` an die gemeinsame Updatevorbereitung übergeben. Das ist
kein Dashboardparameter. Eine falsche Ownership oder Gruppen-/Fremdrechte
stoppen vor dem Releasebezug. Änderungen während des Lesens werden ebenfalls
abgewiesen. Dieser Teilnachweis ersetzt weder den unabhängigen Abgleich mit der
Installation noch die Host-/Stateprüfung, Freigabe oder Erstvertrauensqualifikation.
Die Dashboardansicht verwendet weiterhin ihre unverbindliche Runtimeprojektion.

Eine andere bestehende Quelle wird nicht überschrieben. Bei erneuter
Initialisierungsprüfung werden vorhandene Daten einschließlich Ownership/Rechte
nur verglichen; fehlende Quelle einer bestehenden Installation wird nicht
ungefragt nachgerüstet. Nach einem I/O-Abbruch bleiben Teilstände zur ausdrücklichen
Operatorprüfung erhalten. Das ist ein Recoveryfall, kein erfolgreicher Normalweg.
Die Quelldaten gehören zusammen mit den bisherigen Installationsbindungen in die
Operator-Sicherung. Sie enthalten keine privaten Schlüssel oder Zugangsdaten.
Ein gespeicherter Root-Digest oder eine eigene Kopie qualifiziert weiterhin
keinen Erstvertrauensweg; der Datensatz hält `initial_handoff` ausdrücklich auf
`not_qualified_by_this_check`. Kein gewählter produktiver Kanal oder Trust Root
wird ausgeliefert. Die Dashboard-/Updateausführung folgt in separaten Teilpaketen.

Eine erfolgreiche Vorbereitung bedeutet weiterhin kein Erstvertrauens-PASS.
Fehlender Trust-Client, falsche Profile, defekte Signaturen, fehlende Artefakte
oder manipulierte Kits blockieren vor Identityaufnahme und Runtimestart. Der
Cache wird nach Fehlern nicht still zurückgesetzt. Installationsfehler und
Recovery des gestarteten bestehenden Installers behalten ihren eigenen Vertrag.

Referenz für die wiederverwendete Bibliothek:
[python-tuf: expliziter Bootstrap-Anker](https://theupdateframework.readthedocs.io/en/stable/INSTALLATION.html)
und [Updater-Vertrag](https://theupdateframework.readthedocs.io/en/stable/api/tuf.ngclient.updater.html).
Tests mit lokal erzeugten Testschlüsseln und einem lokalen HTTP-Repository
prüfen diesen Bezugsmechanismus, keine reale Betreiber-Root oder Distribution.

### Getrennte Abnahme und sichtbare Restpunkte

- **Funktionsnachweise:** Jeden neuen Pfad separat prüfen. Interne Zielhostabnahme
  erfasst tatsächliche Übergabe/Prüfung, Installationsaufruf einschließlich
  Administratoraufnahme, Dashboardeinrichtung und abschließenden Operator-
  Production-Start. Keine direkten DB-Eingriffe, vorbereiteten Identitäten,
  versteckten CLI-Schritte oder manuellen Reparaturen als normaler Benutzerweg.
- **Konfiguration:** LLM-/Promptsession ohne Neustart; allgemeine Production-
  Schreibversuche gesperrt; gebündelte Setupänderungen und Session-Recovery.
- **Update:** Unabhängige Wiederprüfung veralteter/manipulierter Vorbereitung,
  explizite Freigabe, Ausschluss paralleler Wartung und neuer Arbeit. Aktive Arbeit
  blockiert; wartende/fortsetzbare Zustände benötigen eigene nachgewiesene
  Releasekompatibilität. Unbekannte Upgradepfade stoppen.
- **Migration/Recovery:** Wiederherstellung und Neustart der Einzelprojektinstallation prüfen. Ein künftiges
  Update ab festgelegter Baseline eigenständig prüfen. Freigaben/Evidence erhalten und ihre
  Wirksamkeit getrennt bewerten. Download-, Speicher-, Sicherungs-, Migrations-,
  Aktivierungs- und Readinessfehler sowie Abbruch und defekten neuen Installer
  prüfen; lokaler Recoveryweg ohne Dashboard bleibt erforderlich.
- **Erstvertrauen:** Austausch von Bootstrap, Root oder beiden samt passenden
  manipulierten Hashes muss vor Ausführung erkannt werden. Fehlender Übergabe-
  oder Ankernachweis bleibt offen, auch bei bestandenen Funktionstests. Tests mit
  Testschlüsseln sind keine reale Erstvertrauensabnahme.
- **Evidence:** Release/Commit/Digests, Umgebung, Subject/Attempt, tatsächliche
  Benutzeraktionen und Ergebnis binden. Fehlende Evidence, historische FAILs und
  nicht ausgeführte Tests bleiben sichtbar. Kein pauschaler Golden-/D0-Claim.

## Historischer Testrelease v2.0.0a29 — 09.10.2026

PR #989 und #980 sind menschlich gemergt und in a29 veröffentlicht.
Main-/Tag-CI, sieben gebundene Assets, OCI-Publisher-Smoke, frische
Draft- und Published-Erstinstallation sowie der erneute Asset-Readback sind PASS.
[Exakte Releasebindung und offene Nachweisgrenzen](status/CURRENT_PRODUCT_STATUS.md#veröffentlichter-installationsstand-v200a29--09102026).
Nur saubere neue Alpha-Testinstallationen; kein Golden-/D0- oder Isolations-PASS.


## #988/#989 und #980: in a29 veröffentlichter Umfang

H1 ist zur Umsetzung freigegeben: der vorhandene lokale Referenzworkflow erhält
mit `samuel-container project` eine registrierte Sourcebereitstellung.
[Installationsablauf und Alpha-Nachweisgrenzen](INSTALL_REFERENCE.md#registrierter-lokaler-oci-projektbestand-988)
sind Teil des ausgelieferten Kits. Es gibt keinen automatischen Clone, keine
freie Compose-Erweiterung und keine zweite Workspaceverwaltung. Die vorhandene
#978-Toolchainregistrierung bleibt nutzbar; Projekt- und Toolchain-Overlay werden
nach ihrer jeweiligen Bindungsprüfung gemeinsam verwendet.

H2 trennt die korrigierte Required-Preflight-Reihenfolge von der noch offenen
Ausführungsisolation. Die Gate-Policy erhält `preflight.v4`; zusätzlich bindet
auch eine beibehaltene Operator-Policyversion den neuen Ausführungsvertrag im
Policy-Digest. Alte Subjects/Resume-Evidence werden nicht als neue Policy-PASSes
wiederverwendet. Historische FAILs bleiben erhalten. Kein State-Schemawechsel.

PR #989 wurde am 09.10.2026 menschlich gemergt; Maincommit
`5f0a1314b957997cf2e9852df71dd30166566f2d` enthält den lokalen Projektzugriff
und die vollständige statische Preflight-Reihenfolge. Der darauf aktualisierte
PR #980 ergänzt ausschließlich das Budget der gebundenen Verifier-Probe.
PR #980 ist ebenfalls menschlich gemergt; kombinierte Regression, PR-CI,
Main-/Tag-CI und Releasegates sind für a29 bestanden. Für jeden neuen Release
sind diese Nachweise erneut erforderlich. Danach
Image-Digest, Installerassets, Version und Revision unabhängig zurücklesen,
frische Installation und Projektregistrierung prüfen, erst dann einen gesondert
freigegebenen Funktions-/Golden-Lauf mit neuem Subject beginnen. Die Produktion
auf einem fremden Zielhost ist durch lokale Entwicklungstests nicht abgenommen.

Die ursprüngliche #989-Qualification belegte nur saubere neue
Alpha-Testinstallationen, keine Cross-Release-Checkpointmigration und keinen
Upgrade-/Downgradevertrag. Der spätere #1090-Updatepfad besitzt seinen eigenen
expliziten Quellversions- und Kompatibilitätsvertrag. Die neue
Sourcebindung prüft Device/Inode und geschützte Host-Eltern bei Recreate.
Historische FAIL-Evidence bleibt erhalten; aktuelle Policy-/Resumeprüfungen
werden weiterhin ausgeführt.

H3 (vollständig externe Projekt-/Executionumgebung) wird nicht implementiert.
Die vorhandenen SCM-, Worker-, Scanner-, LLM- und Verifierports bleiben erhalten.

## Historischer Installationsstand v2.0.0a28 — 08.10.2026

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](archive/reader-history-2026-10-11/CONTAINER_RELEASE_OPERATIONS.md#historischer-installationsstand-v200a28--08102026).

### Artefaktbindung a28

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](archive/reader-history-2026-10-11/CONTAINER_RELEASE_OPERATIONS.md#artefaktbindung-a28).

**Weiterhin geltende Grenze:**

Für Corewechsel, bewusst frische Betreiberpfade und selektives Übertragen von
Configwerten gilt genau die [kanonische Preserve/Replace/Reject-Matrix](INSTALL_REFERENCE.md#corewechsel-frische-installation-und-selektiver-restore-985).
Das historische a28-First-install-Kit war kein In-place-Updater. Für den
aktuellen kontrollierten OCI-Updatepfad gelten der [#1090-Vertrag](#1090-beta-lifecycle-auftrag)
und die ausdrücklich gebundene Quellversion; die Matrix für bewusst frische
Installationen ersetzt diesen Vertrag nicht. Ein neuer Auditkey darf keine
bereits geschriebene alte Kette übernehmen; ein vollständiger
Alt-`.env`-Restore darf ebenso wenig den passenden Key der neuen Kette ersetzen.
Historische Installations-/Upgradebelege behalten ihre eigene Releasebindung.

## Optionales Verifier-Artefakt (#978)

a28 führte diesen Pfad ein; seine zu knappe Readinessprobe bleibt als realer
FAIL dokumentiert. Der Budgetfix ist seit a29 veröffentlicht: gebundene
Versionsproben nutzen das effektive TEST-Budget, höchstens 60 Sekunden;
ungebundene Presence-Proben behalten acht Sekunden. a27 besitzt diesen Pfad
noch nicht. Das bestätigt keine vollständige #978-Qualification.

Der releasegebundene OCI-Installer liefert zusätzlich den geprüften
`containers/verifier-pytest.lock` innerhalb seines bestehenden Kit-Assets.
Der Samuel-Runtime-Lock, die OCI-Imagebytes und der Schema-2-Releasevertrag
werden dadurch nicht um projektspezifische Testpakete erweitert. Nach
Erstinstallation bereitet `samuel-container toolchain` diese Pakete ausdrücklich
offline in einem kurzlebigen Container aus dem manifestgewählten Image vor.
Ein eigenes Toolchainmanifest bindet Paketbytes, Lock, Distributionsversionen
und Python-/Plattform-/Releaseidentität; sein SHA-256 liegt in der bestehenden
Eval-/Gate-Policy. Der rootgeführte read-only Zusatzmount und sein
Installationsreceipt sind Teil des offiziellen Installerpfads. Vorbereitung
ersetzt keine vorhandene Toolchain und verleiht keine Qualificationauthority.
Gitea und GitHub verwenden denselben Runnerpfad. Der unabhängige Test muss
auch dieses Artefakt und den getrennten Doctor-Prüfer binden; ein früherer
Release- oder D0-Nachweis gilt dadurch nicht für die neue Kombination.
Operatoraufrufe und Grenzen: [INSTALL.md](INSTALL_REFERENCE.md#oci-pythonpytest-toolchain-und-separater-doctor-prüfer-978).

## Historischer Installationsnachweis v2.0.0a27 — 06.10.2026

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](archive/reader-history-2026-10-11/CONTAINER_RELEASE_OPERATIONS.md#historischer-installationsnachweis-v200a27--06102026).

**Weiterhin geltende Grenze:**

Dieses Runbook beschreibt den in #555 eingeführten, digest- und
lockgebundenen Containerpfad. Es erweitert das allgemeine Release-Gate aus
[`VERSIONING.md`](VERSIONING.md), ersetzt es aber nicht. Der Produktcode kennt
keine Container-Registry: Registry, Repository und Anmeldung sind
Betreiberparameter von `tools/container_release.py`. Die Gitea-Registry ist
Referenzinfrastruktur dieses Repositories. Der mitgelieferte Publisher prüft
jedoch ausdrücklich Giteas persönlichen Owner- und Token-Scope-Vertrag. Ein
anderer OCI-Provider ist durch eine andere Repository-URL allein nicht
qualifiziert; Pull-/Imageformat und Publisherqualification bleiben getrennt.

Damit erbt auch der Container-Publish ab `2.0.0a5` die #399/#580-Schranke:
Legacy-Autoritätsartefakte müssen entfernt sein und die fünf realen
Rolloutfälle müssen den schema- und digestgebundenen Offline-Vertrag erfüllen.
Der Containerpfad kann diese Produkt-Releaseprüfung nicht umgehen.

## OCI-Erstinstallation durch den Betreiber (#970)

Der neue Benutzerpfad steht in [INSTALL, Abschnitt 9.1](INSTALL_REFERENCE.md#91-oci-erstinstallation-auf-einem-leeren-docker-host-970):
unabhängig geprüftes Bootstrap-Paket → ein `samuel-container install` einschließlich
Administratoraufnahme → authentisiertes Setup-Dashboard → explizites
`samuel-container start` einschließlich bestätigter Erstprojektbindung mit Config read-only.
Bezug, Manifestprüfung und gemeinsamer nichtinteraktiver Initialisierer laufen
im vorhandenen Installer; die technische Vollform für ältere Kits bleibt separat. Der Bootstrap verwendet Defaults und UID/GID aus dem tatsächlich
gebundenen Image. Die Publisherfunktion `_smoke_compose()` ist kein Ersatz
für diesen Benutzerpfad. Historische a15-Teilnachweise empfehlen keine aktuelle
Installation; maßgeblich ist der neueste gewählte Release samt Manifest.

## Revisionsfester Veröffentlichungsnachweis v2.0.0a3

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](archive/reader-history-2026-10-11/CONTAINER_RELEASE_OPERATIONS.md#revisionsfester-veröffentlichungsnachweis-v200a3).

## Nicht freigegebener Publishversuch v2.0.0a5

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](archive/reader-history-2026-10-11/CONTAINER_RELEASE_OPERATIONS.md#nicht-freigegebener-publishversuch-v200a5).

## Früherer unterstützter Veröffentlichungsnachweis v2.0.0a7

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](archive/reader-history-2026-10-11/CONTAINER_RELEASE_OPERATIONS.md#früherer-unterstützter-veröffentlichungsnachweis-v200a7).

## Veröffentlichter, nicht D0-qualifizierter Stand v2.0.0a8

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](archive/reader-history-2026-10-11/CONTAINER_RELEASE_OPERATIONS.md#veröffentlichter-nicht-d0-qualifizierter-stand-v200a8).

## Durch D0-Findings abgelöster Qualification-Kandidat v2.0.0a9

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](archive/reader-history-2026-10-11/CONTAINER_RELEASE_OPERATIONS.md#durch-d0-findings-abgelöster-qualification-kandidat-v200a9).

## Durch den Runner-Prompt abgelöster Qualification-Kandidat v2.0.0a10

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](archive/reader-history-2026-10-11/CONTAINER_RELEASE_OPERATIONS.md#durch-den-runner-prompt-abgelöster-qualification-kandidat-v200a10).

## Veröffentlichter, im D0-Golden-Pfad gescheiterter Stand v2.0.0a11

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](archive/reader-history-2026-10-11/CONTAINER_RELEASE_OPERATIONS.md#veröffentlichter-im-d0-golden-pfad-gescheiterter-stand-v200a11).

## Abgelöster, nicht D0-qualifizierter Stand v2.0.0a19

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](archive/reader-history-2026-10-11/CONTAINER_RELEASE_OPERATIONS.md#abgelöster-nicht-d0-qualifizierter-stand-v200a19).

## Release-Lineage v2.0.0a20 bis v2.0.0a25

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](archive/reader-history-2026-10-11/CONTAINER_RELEASE_OPERATIONS.md#release-lineage-v200a20-bis-v200a25).

**Weiterhin geltende Grenze:**

Ein späterer erfolgreicher Smoke oder Release heilt keinen früheren
create-only Kandidaten. Source, Revision, Digest, erster Required-Smoke und
Gitea-Readback werden für jeden neuen Kandidaten aus der spezialisierten
Release-Operatorquelle an das kanonische Produkt-SCM gebunden; Demo-SCM- und
Runtime-Bot-Credentials sind dafür keine Ersatzquelle (#835).

## Veröffentlichter Release v2.0.0a26 — 05.10.2026

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](archive/reader-history-2026-10-11/CONTAINER_RELEASE_OPERATIONS.md#veröffentlichter-release-v200a26--05102026).

## Historischer a15-Release- und D0-Teilnachweis (keine Installationsreferenz)

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](archive/reader-history-2026-10-11/CONTAINER_RELEASE_OPERATIONS.md#historischer-a15-release--und-d0-teilnachweis-keine-installationsreferenz).

## Produktimage wechseln: heutige Betriebsgrenze

Für die #1090-Installation das Update im Dashboard vorbereiten und genau den
angezeigten Operatoraufruf `samuel-container update --target <Release-ID>`
im aufbewahrten Bootstrap-Paket bestätigen. Die CLI prüft Release, TUF,
Versionsvertrag, Zustand und Freigabe unabhängig erneut und koppelt die
vorhandenen Sicherungs-, Metadaten- und Composeaktionen. Ein manuelles Stoppen,
Ändern des Image-Digests und `compose up` ersetzt diesen Wartungsvertrag nicht.
[Normalweg, gebundene Fortsetzung und vollständige Quellrücksicherung](INSTALL_REFERENCE.md#kontrolliertes-oci-update-und-gebundene-fortsetzung-1090).

Die unterstützten Ausgangsversionen sind eine exakte Manifestliste; weder ein
neueres Versionslabel noch ähnliche Dateien erlauben einen ungeprüften Wechsel.
Der Quellrestore verlangt passende Dateien und State, Reconcile, gegebenenfalls
lokale Identity-Recovery und einen ausdrücklichen Quellstart. Witness und Audit
werden nicht still zurückgesetzt. Es gibt keinen automatischen Fallback auf einen
älteren Tag und keine allgemeine Cross-Release-/Dateisystem-Recoveryzusage.

Der frühere manuelle a9→a10-Digestwechsel bleibt ausschließlich historische
Evidence für jenes Versionspaar. `/app/data`, `/samuel-workspaces`, Betreiber-
Secrets und Konfiguration bleiben außerhalb des Images; die bestehende
Preserve-/Replace-/Reject-Grenze gilt weiter. Der Produktstatus trennt die
Entwicklungsnachweise von der eigenen Abnahme veröffentlichter Artefakte.

## Gebundener Buildvertrag

- `containers/lock-policy.json` bindet das OCI-Index-Digest des Basisimages,
  dessen `linux/amd64`-Manifest-Digest, Prüfzeitpunkt, Python-Zielplattform,
  exakte Dependency-Inputs, Generator und Upload-Cutoff. Zusätzlich bindet
  `system_packages` den unveränderlichen Debian-Snapshot, dessen Repositorys,
  die exakte Git-Paketversion und die erwartete Git-Runtime-Version.
- `requirements-container.lock` und
  `requirements-container-build.lock` pinnen Runtime- und Build-Pakete samt
  SHA-256-Hashes. Der Docker-Build installiert beide mit
  `--require-hashes`; das Projektwheel wird ohne erneute Auflösung installiert.
- Ab dem Entwicklungsstand **nach a38** verwenden beide Python-Baustufen
  `SOURCE_DATE_EPOCH=315532800`. Das Projektwheel erhält ein festes ZIP-Datum
  (01.01.1980 UTC), und pip erzeugt hashbasierte Bytecode-Header. Beim Vergleich
  zweier a38-Builds waren die Wheel-Inhalte identisch. ZIP-Zeitstempel,
  Bytecode-Header, Paketmanager-Protokolle und Dateizeitstempel unterschieden sich.
  Für die Freigabe zählt die tatsächlich getestete Image-ID. Beim Registry-Readback
  muss das per Digest adressierte Manifest genau diese ID als `config.digest`
  referenzieren. Ein weiterer Build braucht eine eigene Prüfung.
- `.dockerignore` ist eine Allowlist. Operator-`.env`, `.git`, Tests, lokale
  Arbeitsdaten und lokale Lizenzdateien gehören weder in den Kontext noch in
  das Image. Default-Konfiguration ist Teil des Images; wirksame
  Operator-Konfiguration und Daten werden beim Start gemountet.
- Das gemountete `/app/data` enthält die lokale WAL-Datenbank
  `samuel-state.sqlite3`; sie ist weder Image- noch Registrybestandteil. Ab
  Schema v10 liegen Evaluation-, Quality- und Run-History sowie Claims,
  diagnostische Checkpoints/Intents/Leases, Workflow-Budgetzulassungen und
  physische Attempt-Reservationen, Restore-Operationen,
  Reconcile-Inventar und Authority-Epoch dort. Importierte
  JSON-Altdaten werden checksumbenannt als `*.migrated-<sha256>` archiviert;
  das gilt auch für `bound_healing_attempts.json`. Der synchrone Witness
  `samuel-state-authority.json` liegt im selben Volume, aber außerhalb des
  DB-Backup-Artefakts; eine Abweichung erzwingt sichtbares Reconcile. Das Volume
  muss auf einem lokal klassifizierten Dateisystem liegen. Eine aktive WAL-DB
  wird über die SQLite Backup API gesichert, nicht per Dateikopie.
  Ein Restore wird bei gestopptem regulären Dienst in einem kontrollierten
  One-shot-Container mit demselben Data-Volume über `samuel state restore`
  eingespielt und anschließend über `reconcile-scan`, begründete
  `reconcile-classify`-Entscheidungen und `reconcile-complete` abgeschlossen.
  Bis dahin bleiben Healing und Resume fail-closed.
  Der nicht löschende Retention-Check läuft im One-shot-Container über
  `samuel retention dry-run --json`. Verwaltete Backups entstehen mit
  `samuel retention backup --json` im separat persistent zu mountenden
  `managed_backup_dir`; Kopien außerhalb dieser Grenze werden nicht erfasst.
- Das getrennt gemountete `/samuel-workspaces` enthält Run-/Verifikations-
  Worktrees und deren lokale Lifecycle-Registry. Es ist weder Image- noch
  State-Backupbestandteil. Quarantänen werden vor Container-/Volumewechsel mit
  `samuel workspace list|inspect --json` geprüft; aktive oder quarantänisierte
  Bäume dürfen nicht durch ein pauschales Volume-Cleanup verschwinden. Die
  168-Stunden-Operatorfrist löscht nichts automatisch; nur ein begründetes
  `samuel workspace discard` terminalisiert bereits geprüfte Evidence.
  Offene gebundene Finalisierungen verwenden denselben persistenten Worktree
  nach einem Containerneustart; deshalb müssen `/app/data` und
  `/samuel-workspaces` gemeinsam erhalten bleiben. `samuel resume list --json`
  zeigt pending/blocked Zustände. Reconcile, fehlender OS-Lock, lebendes Lease
  oder Git-/SCM-/Policy-Drift blockieren ohne automatisches Volume-Cleanup.
- `tools/container_release.py check` vergleicht Policy, Projektinputs,
  Lockdigests, Dockerfile, Kontext und Compose offline. Derselbe Check läuft in
  CI ohne Docker-Socket.
- Das Runtime-Image startet und prüft Health ausschließlich über den im Wheel
  installierten Console-Entry-Point `samuel`. Health prüft auch, ob die vom
  Worktree-Adapter benötigte Git-Runtime ausführbar ist. Der Offline-Check
  weist einen Rückfall auf `python -m samuel` als Herkunftsdrift zurück
  (#583/ADR-0583/#727).
- Der Publish-Pfad führt im fertig gebauten Image zusätzlich
  `git --version` aus. Manifest-Schema 2 bindet den kanonischen Hash der
  Systempaket-Policy und die erwartete Git-Runtime-Version; ein Image ohne den
  vereinbarten Stand wird nicht gepusht.

## Abhängigkeiten aktualisieren

Beim Hinzufügen einzelner notwendiger Abhängigkeiten kann der vorhandene
Generator mit `--keep-existing` kompatible Pins aus den bestehenden Lockdateien
bevorzugen. Er ersetzt damit keine Sicherheitsprüfung; unvermeidbare Änderungen
sind weiterhin vollständig zu reviewen. Ohne diese Option bleibt die bisherige
vollständige Neuauflösung erhalten. Für den TUF-Bezug wurden nur `tuf`,
`securesystemslib` und `urllib3` ergänzt. Der Audit des bisherigen Locks fand
zusätzlich [GHSA-6q48-6c7w-9gw2 in certifi](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2);
deshalb verlangt das bestehende LLM-Extra jetzt `certifi>=2026.10.19`, im Lock
auf `2026.10.23` gebunden. Der Build-Lock enthält außerdem den
[Windows-spezifischen setuptools-Befund GHSA-xmj3-9gf7-h52w](https://github.com/pypa/setuptools/security/advisories/GHSA-xmj3-9gf7-h52w).
Die Buildanforderung wird auf mindestens `84.1.0`, der Pin auf `84.2.1`
angehoben. Das ist kein Nachweis einer Ausnutzbarkeit im unterstützten
Linux-/amd64-Container und keine Erweiterung des Plattformsupports.
Alle anderen bisherigen Runtime-/Build-Pins,
Basisimage und Systempakete bleiben erhalten. Der wiederholte Lauf mit
denselben Eingaben muss identische Locks liefern.

Bei der #1090-Prüfung des tatsächlichen a35-Kandidatenimages wurde außerdem
`pip 25.0.1` aus dem Basisimage gefunden. Es war weder im Runtime- noch im
Build-Lock erfasst; ein erfolgreicher Audit der Anwendungsabhängigkeiten deckte
es deshalb nicht ab. Der vorhandene Generator bindet den Containerinstaller
jetzt in **beiden** Locks (`pip>=26.2.2,<27`); native Produktabhängigkeiten bleiben
unverändert. Die Sicherheitskorrekturen sind im
[offiziellen pip-Changelog](https://pip.pypa.io/en/stable/news/) beschrieben.
Die bestehenden hashgeprüften Docker-Buildschritte ersetzen damit das geerbte
Paket. Der vorhandene Runtime-Probelauf verlangt vor dem Push die exakte
Runtime-Lockversion von pip. Dies ist kein Nachweis, dass sämtliche gemeldeten
pip-Befunde auf dem unterstützten Python-/Linux-Stand ausnutzbar waren.

Lockänderungen erfolgen in einem normalen Review-PR. Benötigt werden exakt
`uv 0.12.6`, Python 3.12 und ein bewusst gewählter UTC-Cutoff:

```bash
python -m pip install 'uv==0.12.6'
python tools/update_container_locks.py \
  --exclude-newer 2026-08-27T14:05:00Z
python tools/container_release.py check
```

Den Sicherheitsabgleich auch gegen die tatsächlich ausgelieferten Pins führen,
nicht nur gegen die gerade installierte Entwicklungsumgebung. Mit `pip-audit`
aus dem bestehenden `ci`-Extra:

```bash
python -m pip_audit -r requirements-container.lock -r requirements-container-build.lock \
  --require-hashes --disable-pip --strict
```

Zusätzlich die tatsächlich installierten Python-Distributionen im erzeugten
Image mit `importlib.metadata` inventarisieren und die Drittanbieter-Pins mit
dem vorhandenen `pip-audit` prüfen. Das eigene S.A.M.U.E.L.-Paket wird über
Commit/Releasebindung geprüft, nicht als gleichnamiges öffentliches PyPI-Paket.
Auch aus dem Basisimage geerbte Distributionen müssen berücksichtigt werden;
ein Lock-Audit allein ist kein vollständiger Image-Nachweis. Python-/OS-Pakete
und Erstvertrauen bleiben eigene Prüfumfänge. Historische Audit-FAILs erhalten
und den wiederholten Audit an den neu gebauten Image-Digest binden.

Der Cutoff wird bei einer späteren Aktualisierung auf den tatsächlichen
Prüfzeitpunkt gesetzt, nicht still wiederverwendet. Im Diff werden mindestens
Inputs, aufgelöste Versionen, Hashes, neue transitive Pakete und bekannte
Sicherheitsbefunde geprüft. CI weist Änderungen an `pyproject.toml` zurück,
solange Policy und Locks nicht gemeinsam aktualisiert sind.

## Basisimage aktualisieren

1. Das gewünschte Tag in der Herstellerregistry auflösen und sowohl den
   OCI-Index als auch das `linux/amd64`-Manifest über die Registry-API prüfen.
2. `base_image.reference`, `base_image.platform_manifest_digest` und
   `base_image.verified_at` in `containers/lock-policy.json` aktualisieren.
   Dieselbe digestgebundene Referenz als Default von `PYTHON_IMAGE` im
   `Dockerfile` setzen.
3. `python tools/container_release.py check`, den vollständigen lokalen
   Testsatz und einen frischen `linux/amd64`-Build ausführen. Image-Inspect,
   Runtime-Identität und Compose-Smoke müssen grün sein.
4. Änderung und externe Digest-Evidence in einem Review-PR festhalten. Ein
   bewegliches Tag allein ist keine Evidence.

Ein Rollback erfolgt ausschließlich als neuer Review-PR auf das zuvor
nachgewiesene Paar aus Index- und Plattform-Digest. Bereits veröffentlichte
Produkt-Tags oder Image-Tags werden weder verschoben noch überschrieben. Ist
ein problematisches Image schon veröffentlicht, wird die nächste
Vorabversion gebaut; die alte Referenz bleibt Auditspur und wird nicht mehr
als empfohlener Stand dokumentiert.

## Git-Systempaket aktualisieren

Git ist kein frei beweglicher `apt install`-Nebeneffekt. Für eine Aktualisierung
werden Debian-Snapshot-Zeitpunkt, beide Snapshot-Repositorys, exakte
Paketversion und erwartete Ausgabeversion gemeinsam in
`containers/lock-policy.json` und den drei Dockerfile-Buildargumenten geändert.
Der Snapshot ist unveränderlich; APT prüft weiterhin die signierten
Repositorymetadaten. Review und CI führen `tools/container_release.py check`
aus, der fertige Imagekandidat muss den Runtime-Probe und den frischen
Compose-Smoke bestehen. Erst der reale D0-Lauf belegt darüber hinaus, dass Git
im Zielrepository-Pfad tatsächlich verwendbar ist.

## Kandidat bauen und veröffentlichen

Für v2.0.0a26 gilt die datierte Maintainerdisposition in
[VERSIONING](VERSIONING.md#maintainerdisposition-für-v200a26--05102026):
separate Erstinstallation, danach vollständiges Testkonzept. Die nach #962
vertagten Altlastenabnahmen sind kein Publishblocker und kein PASS.
Für den Alpha-Auftrag #1090 werden die Distributionsdateien und das
Produktimage einmal am integrierten Commit gebaut. Die Prüfprotokolle binden
Version, Commit, SHA-256 des Schema-1-Manifests und die vollständige lokale
Docker-Image-ID. Die Image-ID bezeichnet den Digest der Imagekonfiguration.
Der Registry-Manifestdigest entsteht beim Push und wird separat festgehalten.

Zunächst Wheel, sdist und die zugehörigen Releaseassets mit dem
[Pre-Tag-Gate](VERSIONING.md#ausführbarer-release-prozess) im privaten
Kandidatenverzeichnis vorbereiten. Am selben sauberen Checkout wird das
Image gebaut. `RELEASE_TAG` und `CANONICAL_SOURCE_URL` entsprechen dem
konkreten Releaseauftrag. `TESTED_DIST` enthält den vorbereiteten Dateisatz.

```bash
release_commit="$(git rev-parse HEAD)"
candidate_dir="$(mktemp -d)"
docker build --pull --no-cache --platform linux/amd64 \
  --build-arg "SAMUEL_VERSION=${RELEASE_TAG#v}" \
  --build-arg "SAMUEL_REVISION=$release_commit" \
  --build-arg "SAMUEL_SOURCE_URL=$CANONICAL_SOURCE_URL" \
  --iidfile "$candidate_dir/image.id" .
cat "$candidate_dir/image.id"
sha256sum "$TESTED_DIST/release-manifest.json"
```

Browser, Konfiguration, Persistenz, Recovery und Security am so identifizierten
Kandidaten prüfen. Die getesteten Werte zusammen mit den Nachweisen vor dem Tag
sichern. Nach annotiertem Tag und erfolgreicher Tag-CI werden beim folgenden
Aufruf `TESTED_IMAGE_ID` und `TESTED_MANIFEST_SHA256` aus diesem
Prüfnachweis übernommen. Beide haben die Form `sha256:<64 Hex-Ziffern>`.
Eine unveränderte Kopie des vorab geprüften Dateisatzes dient als
Arbeitsverzeichnis für das Schema-2-Manifest.

Der Releasehost benötigt eine lokale Compose-Umgebungsdatei mit den für den
Health-Start erforderlichen Operatorwerten. Der persönliche Package-Owner
verwendet eine eigene Credential mit `write:package` ohne weitere Schreibscopes.

Soll dieser Kandidat anschließend formal als Golden-D0 qualifiziert werden,
muss derselbe Produktcommit bereits vor Tag und Publish den in
[`VERSIONING.md`](VERSIONING.md) und
[`OPERATING_RULES.md`](OPERATING_RULES.md) R24 gebundenen vollständigen
Development-Rehearsal-Exit besitzen. Ein Teilretest oder ein aus mehreren
Attempts zusammengesetzter Status reicht dafür nicht. Der Receipt erteilt
keine Publish- oder Qualificationauthority; er ist eine zusätzliche
Startbedingung für diesen ausdrücklich vorgesehenen Releasezweck. Alle
folgenden create-only-, Smoke-, Manifest- und Readbackregeln bleiben
unverändert.

```bash
read -r -s -p 'Publisher token: ' SAMUEL_OCI_PUBLISHER_TOKEN
printf '\n'
export SAMUEL_OCI_PUBLISHER_TOKEN

python tools/container_release.py preflight \
  --tag "$RELEASE_TAG" \
  --image-repository "$REGISTRY_HOST/$REGISTRY_OWNER/samuel" \
  --publisher-api-url "$GITEA_URL" \
  --publisher-user "$REGISTRY_OWNER" \
  --release-host-id "$RELEASE_HOST_ID"

release_dist="$(mktemp -d)"
cp -a "$TESTED_DIST/." "$release_dist/"
python tools/verify_distribution_license.py "$release_dist"

python tools/container_release.py publish \
  --dist-dir "$release_dist" \
  --tested-image-id "$TESTED_IMAGE_ID" \
  --tested-manifest-sha256 "$TESTED_MANIFEST_SHA256" \
  --tag "$RELEASE_TAG" \
  --commit-ref origin/main \
  --image-repository "$REGISTRY_HOST/$REGISTRY_OWNER/samuel" \
  --source-url "$CANONICAL_SOURCE_URL" \
  --compose-env-file "$OPERATOR_ENV_FILE" \
  --publisher-api-url "$GITEA_URL" \
  --publisher-user "$REGISTRY_OWNER" \
  --release-host-id "$RELEASE_HOST_ID"

unset SAMUEL_OCI_PUBLISHER_TOKEN
```

Auf einem getrennten Docker-Host darf `--docker-command 'sudo -n docker'`
verwendet werden. Das Werkzeug liest die Publishercredential nur aus
`SAMUEL_OCI_PUBLISHER_TOKEN`, prüft über Giteas `/api/v1/token` die gebundene
Identität und Scopes und verwendet dieselbe Credential über `--password-stdin`
in einer temporären Docker-Config. Token erscheinen weder in Argumenten noch
in der JSON-Ausgabe. Für die aktuelle Infrastruktur lautet das
Repository nach dem neutralen Muster `<registry>/<owner>/samuel`; konkrete
private Host-/Ownerwerte bleiben lokale Betreiberkonfiguration. Der
qualifizierbare Publisher-Preflight unterstützt in dieser Stufe ausschließlich
Gitea mit persönlichem Owner; eine andere OCI-Registry benötigt einen eigenen
gleichwertigen Identitäts-/Scopebeleg und ist nicht durch bloßes Ändern des
Betreiberwerts freigegeben. Nutzt eine ausdrücklich interne Registry HTTP statt
TLS, müssen Docker-Daemon und Login dafür separat
konfiguriert sein; zusätzlich erhält nur deren Create-only-Preflight die
bewusste Option `--registry-insecure`. Für öffentliche Registries bleibt sie
aus.

Temporäre Docker-Metadaten und die vollständige Smoke-Konfiguration werden
auch bei unterschiedlichen Host-/Containerbenutzern entfernt. Reicht das
normale Löschen nicht aus, verwendet das Werkzeug ausschließlich ein bereits
lokales Image, ohne Netzwerk oder Pull, und bindet nur seinen eigenen privaten
Temporärordner ein. Symlinks zu anderen Pfaden werden nicht verfolgt;
allgemeine Hostrechte werden nicht erweitert. Die temporäre Login-Datei wird
auch bei einem Fehler vor dem Metadaten-Cleanup entfernt.

Scheitert das Aufräumen (etwa weil Docker oder das lokale Image nicht mehr
verfügbar ist), bleibt der Lauf fehlgeschlagen. Die ursprüngliche Ursache und
der zusätzliche Cleanuphinweis samt betroffenem Pfad erscheinen gemeinsam.
Dockerzugriff wiederherstellen und nur diesen privaten Restpfad bereinigen.
Bereits geschriebene Tags niemals überschreiben; bei unterbrochenem Publish
zuerst Registry-/Manifeststand prüfen und den unten beschriebenen
Wiederaufnahmevertrag beachten.

Pull und Publish verwenden getrennte Credentials und Zwecke: Ein privater
Runtime-Pull braucht bei Gitea nur `read:package` plus Owner-Leserecht. Der
Releasehost verwendet eine separat ausgestellte Publishercredential des
persönlichen Owners mit `write:package`. Der gleiche Owneraccount bleibt damit
eine gemeinsame Trustwurzel. Der providerseitige Scope gilt für Packages des
Accounts; Releasehost, Aufrufzeit und konkretes Image sind organisatorische
Bindungen und keine technisch erzwungene Einzelimage-Isolation. Die temporäre
Docker-Config wird nach Preflight oder Publish verworfen; der Plattformtoken
wird anschließend separat aus der Shell entfernt und bei Bedarf widerrufen.

Gitea ordnet Packages einem Benutzer oder einer Organisation zu, nicht
automatisch dem Quellrepository. Der erste unterstützte Pfad verlangt daher
den persönlichen Owner als authentifizierte Tokenidentität und `write:package`
ohne weitere Write-Scopes; ein Repository-/SCM-Token wird ausdrücklich
abgewiesen. Der Preflight weist Identität, Scope, Credentialtrennung,
Owner-Package-Read und exakte Tagabwesenheit getrennt aus. Er führt keinen
Probepush aus. Ein fehlender oder nicht lesbarer Beleg bleibt blockiert und
wird nicht aus erfolgreichem `manifest inspect` zu Schreibrecht hochgestuft.
Siehe die offiziellen Gitea-Verträge für
[Package-Zugriff](https://docs.gitea.com/usage/packages/overview/#access-restrictions)
und die
[Container-Namensform](https://docs.gitea.com/usage/packages/container/#image-naming-convention).

Der Publish-Schritt ist fail-closed und führt in dieser Reihenfolge aus:

1. Offline-Vertrag und bestehendes Post-Tag-Release-Gate prüfen.
2. Dedizierte Credential, persönliche Owneridentität, `write:package`,
   Owner-Read, Releasehost-/Imagebindung und Tagabwesenheit nachweisen.
3. Den geprüften Schema-1-Dateisatz und die vorliegende Image-ID übernehmen.
4. OCI-Labels, Runtime-Version, vollständigen Commit und ausgeschlossene
   lokale Dateien im Image prüfen.
5. Tag einmalig pushen, Registry-Manifestdigest auflösen und die zugehörige
   Imagekonfiguration mit der geprüften lokalen Image-ID vergleichen.
6. Das gepushte Digest mit einem frischen Compose-Projekt, temporärem
   Datenverzeichnis, gemounteter Konfiguration und Operator-`.env` starten;
   Docker-Health und Dashboard-Buildstatus prüfen.
7. Erst danach `release-manifest.json` auf Schema 2 erweitern und Image,
   Digest, Plattform, Basisdigests und Runtime-Lockdigest eintragen.

Ohne das Optionspaar nutzt `publish` für bestehende Abläufe seinen bisherigen
Buildpfad. Für die Abnahme eines bereits getesteten Alpha-Images werden beide
Optionen benötigt. Nach dem Push die Registryreferenz unabhängig lesen und nach
der nativen Veröffentlichung die sieben Assets erneut beziehen. Die frische
Installation und der reale Produktauftrag verwenden genau diesen Dateisatz
und das durch Schema 2 gebundene Registryimage.

Das resultierende Manifest wird mit den sechs gebundenen Assets an das Release
des unveränderten Tags angehängt. Nutzungsdokumentation nennt ausschließlich
die `image@sha256:...`-Referenz aus diesem Manifest. Der lesbare Image-Tag ist
ein Suchschlüssel, keine unveränderliche Installationsauthority.

## Abbruch und Wiederaufnahme

Bei einem State-Fehler gibt die Wartungs-CLI ab dem Entwicklungsstand nach a38
den stabilen Diagnosecode aus. Erscheint kein `SAMUEL_MAINTENANCE_COMMITTED`,
bleibt der Abschluss unbestätigt. Den lokalen Zustand und den angegebenen
Recoveryweg prüfen. Ein fehlender Marker erteilt keine Startfreigabe.

- Vor dem Push ist der lokale Kandidat wegwerfbar; Ursache in einem normalen
  PR korrigieren und alle Gates wiederholen.
- Bei unbekanntem Registry-Status oder fehlendem Nachweis der Tag-Abwesenheit
  wird nicht gepusht.
- Nach einem erfolgreichen Push, aber vor grünem Smoke, bleibt der create-only
  Tag unverändert. Ursache dokumentieren und mit der nächsten Produktversion
  korrigieren; kein Überschreiben.
- Ein reiner Transportfehler nach nachweislich erfolgreichem Push darf nur
  durch erneutes Auflösen und Prüfen desselben Digests behandelt werden.
- Meldet der Push einen Fehler und der Tag ist anschließend vorhanden, stoppt
  das Werkzeug mit unbekanntem Ausgang. Der Tag wird weder gelöscht noch
  überschrieben oder automatisch erneut gepusht; zuerst wird sein Digest unter
  demselben Releaseauftrag reconciliert. Auch bei weiterhin nicht belegtem Tag
  gibt es keinen automatischen Credentialfallback oder Retry.
- Wurde der lokale Aufruf **nach** einem nachweislich vorhandenen OCI-Tag,
  aber **vor** dem ersten Compose-Smoke und der Manifestmaterialisierung
  unterbrochen, darf ausschließlich der explizite Recoverypfad denselben
  Artefaktsatz weiter prüfen. Er führt keinen Build, Push, Retag, Löschvorgang
  oder Gitea-Release-Schritt aus:

  ```bash
  python tools/container_release.py recover \
    --dist-dir "$RECOVERY_DIST" \
    --tested-image-id "$TESTED_IMAGE_ID" \
    --tested-manifest-sha256 "$TESTED_MANIFEST_SHA256" \
    --tag "$RELEASE_TAG" \
    --commit-ref origin/main \
    --image-repository "$REGISTRY_HOST/$REGISTRY_OWNER/samuel" \
    --source-url "$CANONICAL_SOURCE_URL" \
    --compose-env-file "$OPERATOR_ENV_FILE" \
    --publisher-api-url "$GITEA_URL" \
    --publisher-user "$REGISTRY_OWNER" \
    --release-host-id "$RELEASE_HOST_ID"
  ```

  `RECOVERY_DIST` ist eine Arbeitskopie des gesicherten Schema-1-Dateisatzes.
  Beide geprüften Hashwerte stammen aus dem ursprünglichen Lauf.
  Recovery prüft erneut den annotierten Tag, Gate und unveränderten
  Schema-1-Artefaktsatz, fordert genau den bestehenden Image-Tag ab, löst
  genau einen Digest auf und prüft Labels, Runtime sowie frischen
  digestgebundenen Compose-Smoke. Erst danach entsteht das Schema-2-Manifest.
  Fehlender, mehrdeutiger, bereits gebundener oder identitätsabweichender
  Zustand blockiert ohne Mutation. Ein fehlgeschlagener Smoke ist kein
  technischer Unterbruch: Er verlangt weiterhin einen neuen Produktkandidaten.
- Temporäre Compose-Ressourcen werden auch bei Fehlern entfernt. Operator-
  Konfiguration und Arbeitsdaten verbleiben außerhalb von Repository,
  Build-Kontext und Image.

## Konfigurationsmounts und Installationsprüfung (#1072)

Production hält die allgemeine Konfiguration read-only; ausschließlich die
beiden LLM-JSON-Dateien und `llm/prompts/` sind für die bestehende exklusive
Konfigurationssitzung schreibbar. Der Erstinstaller erstellt den Promptordner
mit Runtime-Eigentümer und privaten Rechten. Setup ersetzt die Mountliste,
damit atomare JSON-Ersetzung keine geerbten Dateimounts trifft; die getrennten
Log-/Backup-Pfade sowie danach ergänzte Projekt-/Toolchain-Overlays bleiben
bestehen. Der Publisher-Smoke verwendet eine eigene Kopie der Image-Defaults
mit passender Ownership statt des Sourcecheckout-Konfigurationsordners.

Bei der frischen Installation globale und Taskkonfiguration speichern,
anschließend im Produktionsmodus alle drei Prompt-Ebenen aktivieren, Recreate,
Referenzwiederherstellung und die weiterhin gesperrten direkten Schreibwege
prüfen. Die erforderliche frische lokale Administratoranmeldung bleibt
unverändert; ein Legacy-API-Key ist keine frische Identität. Diese Prüfungen
ersetzen weder Workflow- noch unabhängige Live-Abnahme.

Den Startpfad zusätzlich vor und nach lokalem Identity-Cutover in Setup und
Production prüfen. Legacy verwendet weiterhin die authentisierten HTTP-Checks;
lokale Identitäten verwenden öffentlichen Auth-Modus, laufenden Prozessmodus,
installierte Buildidentität und den vorhandenen CLI-Health-Check als JSON.
Falsche Version, Revision oder Betriebsart brechen weiterhin unmittelbar ab.
Fehlende lokale Startvoraussetzungen und ungesunde Production dürfen keinen
Installationserfolg melden; dabei werden keine neuen API-Tokens benötigt.

## Offizielles OCI-Installationspaket (#970/#971)

Seit v2.0.0a27 materialisiert das Release-Gate zum Wheel, sdist
und Runtime-Lock zusätzlich `samuel-oci-<Version>.tar.gz` und beide Compose-Dateien.
Alle drei Assets sind im bestehenden Release-Manifest mit Größe und SHA-256
gebunden. Das Kit ist deterministisch und enthält keine Betreiberquellen.
Der Operatorpfad ist `samuel-container install` → authentisiertes Setup →
`samuel-container start`; siehe INSTALL Abschnitt 9.1. Die Imageauthority bleibt
`container.reference`. Die UID/GID-Ableitung nutzt denselben Helper wie der
Publisher-Smoke; die tatsächliche Endnutzerabnahme benutzt ausschließlich
den ausgelieferten Installer. Logs und Backups liegen am Host in getrennten
Verzeichnissen und behalten ihre bisherigen Containerpfade unter State.

Vor Veröffentlichung wird der veröffentlichbare Kit auf einem frischen
Ubuntu-/Docker-Host mit leerem Imagestore und leeren Betreiberpfaden geprüft.
Nach Veröffentlichung werden Manifest und Assets erneut heruntergeladen und
der gleiche dokumentierte Installationsweg wiederholt. Technical Health ist
keine automatische Workflow-, Golden- oder D0-Freigabe.
