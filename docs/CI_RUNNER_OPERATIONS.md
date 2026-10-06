> Public-Snapshot-Projektion: Runnername und privater Image-Identifier sind Beispielwerte; die internen Operatorwerte sind nicht veröffentlicht.

# CI-Runner-Betrieb

Stand: 18. September 2026 · Betriebsvertrag zu #441, #492, #551, #557 und #679

Diese Anleitung beschreibt die externe Gitea-Actions-Ausführungsumgebung für
dieses Repository. Sie ist kein Bestandteil der S.A.M.U.E.L.-Laufzeit. Ein
grüner Required Check ist nur dann belastbar, wenn Workflow-Commit,
Runner-Label, Container-Image und verwendete Actions eindeutig bestimmt sind.

Diese Repository-CI ist nicht automatisch der Execution Provider aus #679.
Der dafür implementierte Gitea-Adapter verlangt zusätzlich einen vor der
Wirkung persistierten Request, eindeutige Run-/Attemptbindung, einen
vertrauenswürdigen Workflow-Blob, kriteriumsweise Evidence, Tool- und
Environment-Digests, Freshness/Nonce sowie eine candidate-unabhängige
Integritätsprüfung. `config/execution.json` bleibt ausgeliefert deaktiviert und
unqualifiziert. Erst ein realer positiver und negativer Conformance-/D0-Lauf
mit ephemerem Job, fehlendem Host-Docker-Socket, minimalem Token,
kontrolliertem Egress, Ressourcenlimits und getrenntem Attestierungssecret
darf dieses konkrete Profil für Required-Nutzung freigeben.

## Freigegebener Vertrag

| Bestandteil | Gebundener Stand |
|---|---|
| Gitea | `1.27.2`, native systemd-Installation mit SQLite; Binary-SHA-256 `aa4e624ca6aa58a824a75562caecc2d206fcab8c70bc8fab765b456f182844fd` |
| Runner | `gitea-runner v3.3.1`, SHA-256 `71031feb288e53c4c86c06eeb75df9cc94b7ceb1b927b45644d4f9d230c80734`, systemd-Service `act_runner.service` |
| Architektur | `linux/amd64` |
| Workflow-Label | `public-runner-example` |
| Basis-Image | `gitea/runner-images@sha256:e77e2b1ebba51adb1c59d8eb185bc54e397b7e22442756aa7ea0e7b841fd2906` |
| Job-Image | `sha256:0000000000000000000000000000000000000000000000000000000000000001`; lokale Image-ID des daraus abgeleiteten Images, kein Tag |
| Checkout-Action | `actions/checkout@11d5960a326750d5838078e36cf38b85af677262` (`v4`) |
| Python-Action | `actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065` (`v5`) |
| Python-Runtimes | CPython `3.10.21`, `3.12.14` und `3.14.7`, `linux-24.04-x64`, SHA-256-Werte im Image-Bauwerkzeug |
| Python-Paketwerkzeug | `pip 26.2.1`, Python `>=3.10`, offizielles PyPI-Wheel mit SHA-256 `71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e` |
| Parallelität | `capacity: 1` |

Der Basis-Image-Digest wurde am 26. August 2026 auf dem tatsächlichen Runner
als lokales `linux/amd64`-Image nachgewiesen. Das daraus gebaute Job-Image wird
über seine lokale, inhaltsgebundene Image-ID adressiert. Ein Tag wie
`ubuntu-latest` oder `samuel/ci-python:20260827-3` ist keine Freigabeidentität.
Kommentare hinter den Action-SHAs dienen nur der
Lesbarkeit; ausführbar ist ausschließlich der volle Commit.

Runner 3.3.1 enthält zusätzlich zu den Schutzmaßnahmen der 3.0-Linie die in
3.2 eingeführten endlichen Gitea-RPCs sowie Korrekturen für Secret-Masking,
Step-Logbereiche und fail-closed Matrixfehler. Die Verhaltensänderungen wurden
für diesen Betrieb geprüft: Es existiert kein Artifact-/Cache-Fork,
`privileged` bleibt `false`, kein Workflow nutzt `container.options`,
Service-Volumes, nackte `--env`-Optionen oder geheimnishaltige Joboutputs, und
genau ein systemd-Daemon verwendet die `.runner`-Datei. Die dadurch erzeugte
`.runner.lock` ist Teil des Schutzes vor konkurrierenden Daemons und wird nicht
manuell entfernt.

Quellen: [Runner 3.3.1](https://gitea.com/gitea/runner/releases/tag/v3.3.1),
[Runner 3.2.0](https://gitea.com/gitea/runner/releases/tag/v3.2.0),
[offizielle Prüfsumme](https://dl.gitea.com/gitea-runner/3.3.1/gitea-runner-3.3.1-linux-amd64.sha256).

## Account- und Credentialgrenze

Der Runner ist eine getrennte Betriebsrolle und erhält weder die
S.A.M.U.E.L.-`.env` noch SCM-/LLM-/Registrycredentials der Produktruntime. Ein
Registrierungstoken wird auf Repository- oder Organisationsebene unter
`Settings → Actions → Runners` erzeugt und nur für die interaktive einmalige
Registrierung verwendet. Die `--token`-Variante ist im Betriebsrunbook
unzulässig, weil sie das Secret in argv/Prozesslisten sichtbar machen kann.

```bash
sudo -u act_runner -H act_runner --config /etc/act_runner/config.yaml register
sudo chmod 600 /var/lib/act_runner/.runner
sudo chown act_runner:act_runner /var/lib/act_runner/.runner
```

Die Eingabe erfolgt am geschützten Prompt; das Secret wird weder exportiert
noch in die Shell-History geschrieben. Die nach der Registrierung erzeugte
`.runner` ist ausschließlich für den Serviceaccount lesbar und wird nicht in
Produkt-, Repository- oder State-Backups übernommen. Ein Reset des
Registrierungstokens verhindert neue Registrierungen, widerruft aber keinen
bereits registrierten Runner: Dafür wird der Runner zusätzlich in Gitea
gelöscht, der Dienst gestoppt und seine `.runner` kontrolliert entfernt. Das
pro Job von Gitea ausgestellte `GITEA_TOKEN` ist davon getrennt, wird durch die
Workflow-`permissions` begrenzt und nicht als langlebiger PAT gespeichert.

Quelle: [Gitea Act Runner – Registrierungstoken](https://docs.gitea.com/usage/actions/act-runner/#obtain-a-registration-token).

## Wirksame Konfiguration

Die Datei `/etc/act_runner/config.yaml` enthält mindestens:

```yaml
runner:
  capacity: 1
  shutdown_timeout: 30m
  action_shallow_clone: true
  tool_cache_mode: none
  labels:
    - "public-runner-example:docker://sha256:0000000000000000000000000000000000000000000000000000000000000001"

cache:
  enabled: true
  offline_mode: true

container:
  docker_host: "-"
  options: ""
  valid_volumes: []
  force_pull: false

health_check:
  enabled: true
  min_free_disk_space_mb: 1024
  script: /usr/local/libexec/gitea-runner-health
  interval: 30s
  timeout: 10s

metrics:
  enabled: true
  addr: 127.0.0.1:9101
  readiness_grace: 30s
```

`offline_mode` wird erst aktiviert, nachdem beide commitgebundenen Actions im
Cache unter `/var/lib/act_runner/.cache/act` liegen und ihre Remotes und
HEAD-SHAs geprüft wurden. Ein Offline-Cache mit beweglichen Major-Tags wäre
nicht kontrolliert aktualisierbar und ist deshalb unzulässig. Der eingebaute
Actions-Cache ist von `actions/cache`-Artefakten unter `cache.dir` zu
unterscheiden. Der Cache-Schlüssel berücksichtigt den angeforderten Ref: Die
Umstellung von einem Major-Tag auf einen vollständigen Commit kann daher trotz
identischem Repository einmalig einen neuen Cacheeintrag beziehen. Erst der
darauffolgende Lauf ist der Offline-Nachweis für den Commit-Pin.

Das Job-Image ist per lokaler Image-ID unveränderlich gebunden.
`force_pull: false` erlaubt ausschließlich den Start aus dem freigegebenen
lokalen Bestand. Fehlt die Image-ID, ruft Runner 3.3.1 dennoch den Docker-
Pullpfad mit dieser `sha256:`-Referenz auf; Docker lehnt sie ab, und der Job
scheitert vor dem Checkout. Es gibt weder einen Fallback auf den lokalen
Bautag, auf `ubuntu-latest` noch auf ein anderes Image. Der Bautag dient nur
der Inspektion und wird nie im Runner-Label verwendet.

`tool_cache_mode: none` bleibt ausdrücklich gesetzt: Der Runner erzeugt keinen
jobübergreifend beschreibbaren Toolcache. Die Interpreter liegen in der
unveränderlichen Schicht des abgeleiteten Job-Images. Ein Job kann zwar in
seine eigene Container-Schreibschicht schreiben, ein frisch gestarteter
Folgejob sieht diese Änderungen aber nicht. `options: ""` und
`valid_volumes: []` schließen eine operator- oder workflowseitige persistente
Toolcache-Bindung aus. `docker_host: "-"` verhindert außerdem, dass der
Runner den Host-Docker-Socket in Job- oder Service-Container einbindet; jeder
Workflow-Job prüft diese Grenze vor `setup-python`. Der Runner-Modus `shared`
bleibt unzulässig.

Die drei Workflow-Versionen sind als vollständige Patch-Versionen gebunden.
Vor `setup-python` prüft jeder Job den passenden `.complete`-Marker, die
Ausführbarkeit und die exakte `python --version`-Antwort. Fehlt ein Eintrag,
scheitert der Job vor einem Downloadversuch. `setup-python` darf deshalb keinen
Runtime-Download protokollieren; Runner 3.3.1 meldet den lokalen Fund mit
`Successfully set up CPython (<Version>)`. Anschließend erzeugt jeder Job unter
`RUNNER_TEMP` eine eigene virtuelle Umgebung; alle Projekt- und
Prüfabhängigkeiten werden dort installiert. Weil `venv` zunächst das mit dem
jeweiligen CPython-Archiv gelieferte `ensurepip` verwendet, installiert der
Workflow unmittelbar danach das SHA-256-gebundene pip-Wheel aus dem Image mit
`--no-index` in die neue Umgebung und prüft exakt Version 26.2.1. Dadurch kann
ein älteres eingebettetes pip nicht unbemerkt in den Security-Audit gelangen.
Die Image-Schicht mit dem Basisinterpreter bleibt jobübergreifend unverändert,
und der Lintjob installiert das `github`-Extra weiterhin ausdrücklich.

## Python-Job-Image bauen

Das Repository-Werkzeug `tools/build_ci_runner_image.sh` ist ausschließlich
für einen kontrollierten Wartungslauf auf dem Runner-Host bestimmt. Es
verwendet das bereits freigegebene Basis-Image ohne Pull, lädt genau die drei
in der Vertragstabelle genannten `actions/python-versions`-Archive sowie das
offizielle pip-Wheel, prüft alle veröffentlichten SHA-256-Werte, bewahrt das
Wheel für die joblokale Venv-Aktualisierung im Image auf und baut ohne
Layer-Cache ein neues lokales Image. Einen vorhandenen Bautag ersetzt es
nicht. Abschließend führt es alle
Interpreter aus und prüft mit zwei frischen Containern, dass eine Änderung in
der Container-Schreibschicht nicht in einen Folgecontainer gelangt.

Vor dem Lauf müssen Runner und Gitea belegen, dass kein Job aktiv ist. Danach:

```bash
cd /pfad/zum/geprueften/checkout
sudo tools/build_ci_runner_image.sh
```

Die ausgegebene `sha256:`-Image-ID wird mit `docker image inspect` samt
`linux/amd64`, OCI-Basis-Digest und Runtime-Smoke geprüft. Erst danach wird
`/etc/act_runner/config.yaml` gesichert, das Runner-Label auf genau diese
Image-ID gesetzt, `docker_host: "-"` aktiviert und der Dienst kontrolliert neu
gestartet. Der lokale Bautag ist kein Rollbackanker. Die vorherige
Konfiguration und das von ihr referenzierte Image bleiben bis zum erfolgreichen
PR- und Push-Nachweis sowie bis zum Ablauf der Rollbackfrist erhalten.

## Admission, Readiness und geordneter Stop

Das root-eigene, für den Runner nur ausführbare Skript
`/usr/local/libexec/gitea-runner-health` ruft den deploymentlokal
konfigurierten Gitea-Endpunkt nach dem Muster
`https://gitea.example.invalid/api/healthz` mit zwei Sekunden Verbindungs- und fünf
Sekunden Gesamtgrenze auf. Neben HTTP 2xx verlangt es `status: pass` und
erfolgreiche gemeldete Teilprüfungen. Ein Fehler, ungültiges JSON, ein Timeout
oder weniger als 1024 MiB freier Workspace-Speicher pausiert die Annahme neuer
Tasks. Laufende Jobs werden vom Healthcheck nicht beendet; während eines Jobs
wird das letzte Health-Ergebnis wiederverwendet. Der Hostcheck ist deshalb eine
Admission-Schranke, aber kein Nachweis für den Netzwerkpfad eines bereits
gestarteten Jobcontainers.

Der ungeschützte Monitoring-Listener bindet ausschließlich an
`127.0.0.1:9101`. `/healthz` belegt nur den laufenden Prozess, `/readyz` die
aktuelle Task-Admission. Vor jedem kontrollierten Runner-Stop müssen sowohl
Giteas Jobstatus als auch `gitea_runner_job_running 0` geprüft werden; eine
leere Docker-Liste allein ist kein Drain-Nachweis. Der Runner wartet höchstens
30 Minuten auf laufende Jobs, systemd mit `TimeoutStopSec=31min` bewusst etwas
länger. `shutdown_timeout: 0s` ist unzulässig, weil damit kein geordneter Drain
stattfindet und bereits der sofort abgelaufene Shutdown-Kontext eine generische
Cancellation-Warnung erzeugen kann.

## Endlicher Checkout-Pfad

Der vorhandene commitgebundene `actions/checkout` bleibt der einzige
Repository-Checkout; es gibt keinen Wrapper und keinen zweiten Clone-Pfad.
Der Workflow setzt für alle von der Action gestarteten Git-Prozesse
`GIT_HTTP_LOW_SPEED_LIMIT=1024` und `GIT_HTTP_LOW_SPEED_TIME=30`. Ein
etablierter HTTP-Transfer, der 30 Sekunden lang weniger als 1024 Byte/s
überträgt, schlägt dadurch fehl. Das begrenzt keinen Verbindungsaufbau vor dem
ersten Transfer; deshalb bilden Joblimits die äußere Schranke: 20 Minuten für
Kompatibilitäts- und Release-Jobs, 30 Minuten für `lint-and-test`. Ein Timeout
bleibt rot und darf nicht automatisiert in einen grünen Rerun umgedeutet
werden.

Die Kombination hat bewusst drei getrennte Ebenen: Host-Health vor der
Taskannahme, Git-Low-Speed für einen stillstehenden Transfer und Jobtimeout als
äußerste Grenze. Keine Ebene wird als Beweis für eine andere beschrieben.

### Abnahme des Runner–Gitea-Pfads (#557)

Der historische Hänger lässt sich nicht seriös auf eine einzelne Paket- oder
Hostursache zurückführen. Die zeitkorrelierte Evidence grenzt zwei getrennte
Fehlerflächen ein: Runner v1.0.8 verlor zeitweise den Gitea-Steuerpfad
(`UpdateLog`/`UpdateTask` mit HTTP 500 und anschließendem Reporter-Panic),
während der Checkout eines Jobcontainers unabhängig davon ohne endliche
Low-Speed-Grenze im Repository-Fetch stehen bleiben konnte. Gitea-Health,
Hostressourcen, Routing, MTU, SQLite-`quick_check`, Fremdschlüsselprüfung und
Gitea Doctor ergaben keinen belastbaren Hardware-, Datenbank- oder
Produktcodefehler. Die Betriebsmaßnahmen begrenzen deshalb beide belegten
Fehlerflächen, ohne eine nicht nachgewiesene Monokausalität zu behaupten.

Die Grenzen wurden am 27. August 2026 in Gitea-Run 505 auf demselben PR-Head
`4df54c668dd9f66fcab38143f2bf0d3eca0f84aa` aus dem tatsächlichen Docker-
Jobnetz geprüft:

- Versuch 2, Job 582: Ein ausschließlich für Docker-Bridges umgeleiteter,
  etablierter TCP-Pfad zu Gitea übertrug keine Daten. Checkout brach dreimal
  nach jeweils 30 Sekunden mit `Operation too slow` ab; mit den vorhandenen
  Retry-Abständen endete der Job nach 122 Sekunden eindeutig `failure`.
  Python-Setup, Abhängigkeitsinstallation und Projekttests wurden nicht
  ausgeführt. Host-Health und Runner-Steuerpfad blieben erreichbar.
- Versuch 3, Jobs 586, 587 und 588: Nach vollständiger Entfernung derselben
  temporären Netzregel bezogen Python 3.10, Python 3.14 und `lint-and-test`
  unverändert exakt denselben Head und endeten erfolgreich. Job 589
  (`release-gate`) wurde im PR-Kontext vertragsgemäß übersprungen.

Dieser Nachweis belegt den endlichen Stillstandspfad, nicht jede denkbare
Netzstörung. Insbesondere begrenzt die Git-Low-Speed-Einstellung keinen
Verbindungsaufbau, bei dem der Kernel selbst noch keinen etablierten Transfer
meldet; dafür bleibt das Jobtimeout die äußere fail-closed Schranke. Die
temporäre DNAT-Regel und der stille Testlistener sind nach der Abnahme entfernt
worden und gehören nicht zum Betriebszustand.

## Vorprüfung und kontrollierte Umschaltung

Vor jeder Konfigurationsänderung müssen laufende Jobs beendet sein. Danach:

1. Service-, Runner- und Docker-Zustand erfassen.
2. Konfiguration mit UTC-Zeitstempel und restriktiven Rechten sichern.
3. Basis-Image ausdrücklich per Digest beziehen und `RepoDigests`, `Os` und
   `Architecture` prüfen.
4. Einen minimalen Container-Smoke mit `--pull=never` ausführen.
5. Das neue Label zunächst zusätzlich zu den alten Labels deklarieren und den
   Runner neu starten.
6. Den Workflow auf `public-runner-example` und volle Action-SHAs umstellen. Ein
   Online-PR-Lauf wärmt die exakten Action-Cacheeinträge vor.
7. Cache-Remote und -HEAD prüfen, danach `offline_mode: true` aktivieren und
   die alten `ubuntu-*`-Labels entfernen.
8. Die exakt gebundenen Python-Runtimes mit dem Repository-Werkzeug in ein
   neues, vom Basis-Digest abgeleitetes Image einbauen, dessen Image-ID binden
   und den Fast-Fail-Pfad mit einer absichtlich fehlenden Image-ID prüfen.
9. Einen unveränderten PR-Lauf und anschließend einen Push-Lauf auf dem
   Merge-Commit vollständig grün nachweisen.

Während Schritt 5 muss die Daemonmeldung das neue Label zusätzlich zu den
explizit beibehaltenen Übergangslabels zeigen. Nach Schritt 7 müssen
`systemctl is-active act_runner.service` und die Daemonmeldung genau ein
deklariertes Label `public-runner-example` zeigen. Zusätzlich muss ein Joblog das
digestgebundene Image und `forcePull=false` nennen. Beim Vorabnachweis auf
Runner v3.0.0 wurde auch bei lokaler Cache-Wiederverwendung generisch
`Download action repository` protokolliert; die bloße Zeile ist daher kein
Netzwerkbeleg. Maßgeblich ist, dass der commitbezogene Cacheeintrag bereits
existiert und derselbe Job unter kontrolliert gesperrtem GitHub-/Registry-
Netzpfad ohne Remote-Fetch startet. Das Verhalten wird nach jedem
Runner-Update neu geprüft und nicht aus einem älteren Log übernommen.

## Negativnachweis ohne Registry

Der freigegebene lokale Bestand wird zuerst ohne jeden Pull geprüft:

```bash
runner_image="sha256:<FREIGEGEBENE-LOKALE-IMAGE-ID>"
docker image inspect "$runner_image" \
  --format 'id={{.Id}} os={{.Os}} arch={{.Architecture}} labels={{json .Config.Labels}}'
docker run --rm --pull=never "$runner_image" \
  bash -ceu 'test ! -S /var/run/docker.sock; for version in 3.10.21 3.12.14 3.14.7; do test "$("/opt/hostedtoolcache/Python/$version/x64/bin/python" --version)" = "Python $version"; done'
```

Der isolierte Ausfalltest blockiert anschließend die aufgelösten Docker-Hub-
Registry-Endpunkte und GitHub auf dem Runner, löst einen CI-Lauf aus und
entfernt die temporäre Regel auch bei einem Abbruch. Ein vollständig grüner
Job mit `force_pull: false`, der obigen Image-ID und den beiden commitgebundenen
Actions sowie `Successfully set up CPython` ohne Runtime-Download für alle
drei Python-Versionen belegt den lokalen Image-, Action- und Runtime-Pfad.
Unter derselben Registry-Sperre muss
ein zweiter Test mit einem absichtlich nicht lokal vorhandenen Digest vor den
Workflow-Schritten fehlschlagen.

Der Runtime-Negativtest bindet getrennt das unveränderte Basis-Image statt der
abgeleiteten Image-ID und startet einen echten Lauf. Die explizite
Workflow-Vorprüfung muss vor `setup-python` fehlschlagen; weder
GitHub-Download noch Projektinstallation oder Tests dürfen starten. Der
fehlende-Image-Negativtest verwendet dagegen eine syntaktisch gültige, lokal
nicht vorhandene Image-ID und muss schon vor den Workflow-Schritten scheitern.
Danach wird ausschließlich die gesicherte Konfiguration mit der freigegebenen
Image-ID wiederhergestellt. Die konkreten Befehle, Wiederherstellung und
erzeugten Job-IDs werden im Abnahme-Kommentar von #551 festgehalten;
Hosts- und Firewallregeln gehören nicht dauerhaft zur Runner-Konfiguration.

Der Registrytest beweist nicht die Erreichbarkeit des lokalen Gitea. Vor einem
Release wird deshalb aus demselben Jobnetz zusätzlich der Repository-Endpunkt
mit begrenztem Timeout geprüft. Ein Fetch-Timeout bleibt rot und wird nicht
durch unbegrenzte Wiederholungen in einen vermeintlich grünen Nachweis
umgedeutet. Ursache, Task-Admission-Healthcheck und endlicher Checkout-
Fehlerpfad des beobachteten Runner–Gitea-Hängers werden getrennt in #557
nachgewiesen; #551 behauptet diese Netzwerkursache nicht zu lösen.

## Offener Duplicate-ARP-Befund (#567)

Der Runner-Vertrag ist von der Adressvergabe des Betreibernetzes getrennt.
Im privaten Referenznetz beantworteten zwei Netzteilnehmer zeitweise dieselbe
Adresse mit unterschiedlichen MACs. Konkrete interne Adressen, Host-IDs und
MACs bleiben im privaten Betriebsnachweis zu #567 statt in der aktiven
Produktdokumentation. Solange Gerät oder Netzpfad nicht eindeutig
identifiziert und die Doppelbelegung beseitigt ist, ist die Runner-
Erreichbarkeit nicht stabil nachgewiesen.

Am 27. August 2026 wurde der Wechsel im unveränderten Betrieb erneut
beobachtet:

- Über die korrekte MAC waren zuvor SSH, genau ein `act_runner`-Prozess,
  Runner v3.3.1 samt Binary-Prüfsumme, das gebundene amd64-Job-Image und die
  wirksame Runner-/Docker-Konfiguration lesend bestätigt worden.
- Um 18:25:55 CEST zeigte der Neighbor-Eintrag erneut auf den konkurrierenden
  Teilnehmer. Zwei ICMP-Antworten benötigten 361 bzw. 489 ms;
  fünf aufeinanderfolgende TCP/22-Proben scheiterten. Es wurde weder ein
  statischer Neighbor gesetzt noch eine Firewall- oder Netzkonfiguration
  verändert.

Diese Zeitreihe belegt die wiederkehrende Doppelbelegung, aber noch nicht die
Identität oder Ursache des zweiten Teilnehmers. Abschlusskriterien,
Gerätezuordnung und die erforderlichen Mehrfachbeobachtungen stehen in #567.
Die spätere Korrektur und ihr Rollback gehören ausschließlich zur
Betreiberinfrastruktur; sie führen keine Gitea-, Registry- oder
S.A.M.U.E.L.-Produktabhängigkeit ein.

## Update und Rollback

Image-, Runner-, Action- und Python-Runtime-Updates sind getrennte
Wartungsvorgänge:

- Upstream-Version beziehungsweise Tag auflösen und den resultierenden Digest
  oder Commit notieren.
- Herkunft und Architektur prüfen; Image und Actions zunächst online beziehen.
- Smoke, vollständigen PR-Lauf und vollständigen Push-Lauf durchführen.
- Workflow, diese Tabelle und den #551-Nachweis gemeinsam aktualisieren.
- Erst danach alte Cacheeinträge oder die vorherige Image-ID entfernen.

Ein Python-Update erhält ein neu gebautes Image mit neuem Bautag und neuer
Image-ID; das vorhandene freigegebene Image wird nie in-place ergänzt.
Patch-Version, `actions/python-versions`-Release und veröffentlichter
Archiv-SHA werden gemeinsam im Workflow beziehungsweise Image-Bauwerkzeug
geändert. Nach dem Zwei-Container-Smoke folgen Basis- und fehlende-Image-
Negativtest, ein vollständiger PR-Lauf ohne GitHub-Erreichbarkeit und der
Push-Lauf. Erst danach darf das alte Image aus dem lokalen Bestand entfallen.

Die Sicherung von `/etc/act_runner/config.yaml`, die vorherige Image-ID
beziehungsweise der vorherige Basis-Digest und die vorherigen Action-SHAs
bleiben bis zum erfolgreichen Push-Nachweis erhalten.
Rollback bedeutet: Service stoppen, gesicherte Konfiguration wiederherstellen,
prüfen, dass das darin referenzierte Image lokal vorhanden ist, Service starten
und erneut einen echten Lauf ausführen. Tags oder Image-IDs werden nie
umgebogen; ein nicht mehr freigegebener Stand wird ausdrücklich dokumentiert.

Runner-Binary, Runner-Konfiguration, Health-Skript und Gitea-Migration sind
getrennte Rollback-Ebenen. Ihre vor der Umstellung erzeugten, geprüften
Sicherungen und SHA-256-Werte sind im Abnahmeprotokoll von #557 festgehalten.
Ein Rollback der Gitea-Datenbank ist nur als vollständige Offline-
Wiederherstellung von Binary, Konfiguration, systemd-Unit und Datenverzeichnis
zulässig; eine nach Migration 342 betriebene SQLite-Datei darf nicht mit der
alten Binary geöffnet werden. Nach jedem Rollback sind Health, Datenbankprüfung
und ein echter PR-Lauf erneut nachzuweisen.
