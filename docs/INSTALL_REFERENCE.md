# S.A.M.U.E.L. — Technische Betriebsreferenz

Für eine Erstinstallation folge der [Installationsanleitung mit Docker und Python](INSTALL.md). Hier stehen die Einzelheiten für Einrichtung, Betrieb und Diagnose. Versionsgebundene Prüfberichte nennen den jeweils geprüften Stand.

## Unterbrochene Administratoraufnahme fortsetzen

Bei einer Unterbrechung während der Kontoaufnahme denselben a42-Installer erneut starten. Er prüft den vorbereiteten Zustand und übernimmt bei passender Installation den gewählten Hostport und Anmeldenamen. Das beim Start angezeigte, nur für root lesbare Protokoll unter `/var/log/samuel-install.*.log` enthält Phasen und Ergebnis.

Diese Anleitung beschreibt eine S.A.M.U.E.L.-Installation für genau eine externe
Codebasis. Für den späteren Betrieb werden ein Projektcheckout, SCM-Zugriff und ein Modellzugang benötigt.

> **Abgrenzung:** Diese Doku beschreibt das **Überwachen eines fremden Projekts**
> (Normalfall). Der **Self-Mode** (`--self`) ist etwas anderes — er dient nur
> SAMUELs Selbst-Erweiterung am eigenen Code und ist hier nicht relevant.

> **Vor Produktivbetrieb:** Die
> [Capability-/Wirksamkeitsmatrix](CAPABILITY_MATRIX.md) nennt den geprüften
> Kontrollstand. Für die separate Testinstallation gilt der neueste
> veröffentlichte Release mit seinem verifizierten Manifest und OCI-Kit.
> Releaseidentität und Installationsnachweise stehen in dessen Release Notes.
> Golden-D0 und Capabilityqualifications benötigen getrennte Abnahmen. Ein Installationstest
> ist keine vollständige Funktionsabnahme. Gate-Profil, Required CI Check und
> Schutz vor direkten Pushes werden für jede SCM-Installation separat geprüft.

## 0. Überblick

Eine Installation betreut eine Codebasis. Der [GitHub-Installer](INSTALL.md#öffentliche-alpha-auf-einem-docker-host-installieren) richtet das Setup-Dashboard ein. Dort Projekt, SCM und Modell konfigurieren und anschließend den angezeigten Startbefehl am Host bestätigen.

SAMUEL läuft als eigener Dienst und überwacht ein **SCM-Repository** (Gitea oder
GitHub). Es nimmt gelabelte Issues entgegen, plant, generiert Code via LLM,
prüft den Candidate mit gebundenen Gates, beobachtet die Qualität nicht
bindend und erstellt Pull-Requests — alles unter menschlicher Aufsicht.

Drei Bausteine werden im geschützten Dashboard eingerichtet: SCM/Repository,
LLM-Provider und allgemeine Einstellungen. Die bestehenden Dateien `.env` und
`config/` bleiben die technische Speicherung, keine zusätzliche manuelle
Erstkonfiguration. Initiale Administratoraufnahme und veröffentlichter Hostport
gehören zum Installer; Rollen werden ausdrücklich im Dashboard vergeben.

---

## 1. Voraussetzungen

Für die Installation genügen die im Abschnitt zur [Docker-Erstinstallation](INSTALL.md#öffentliche-alpha-auf-einem-docker-host-installieren) genannten Hostvoraussetzungen. Für den Betrieb der eingerichteten Instanz Projektcheckout, SCM-Zugriff und Modellzugang bereithalten. Die folgenden Python- und venv-Angaben gelten für die native Entwicklungsinstallation.

- **CPython ≥ 3.12** (`python3 --version`). Der Release-Check testet die
  Mindestreihe 3.12 und die Reihe 3.14 vollständig. Die neue Mindestversion
  gilt ab **v2.0.0a30** (#811); veröffentlichte a29 und
  ältere Artefakte bleiben unverändert. Für eine lokale Neuinstallation eine
  neue venv mit Python >=3.12 anlegen. Docker liefert Python im Image und
  benötigt keinen Pythonwechsel auf dem Host. [Support- und Releasebindung](VERSIONING.md#support-und-python-kompatibilität).
- Ein **Repo** auf Gitea oder GitHub + **API-Token** mit Rechten:
  `issue R+W`, `repository R+W`, `user R`.
- **Mindestens ein LLM-Provider**: Cloud (DeepSeek, Anthropic, Gemini, OpenAI,
  OpenRouter) oder lokal (Ollama, LM Studio).
- Empfohlen: ein **dediziertes Bot-Konto** im SCM (z. B. `samuel-bot`) statt des
  eigenen Accounts — dann lässt sich Bot- von Mensch-Aktivität trennen (s. §4.1).
- `git` bei Installation aus dem Quellrepository, und für Cloud-LLMs
  ausgehende HTTPS-Verbindungen. Das unterstützte Referenz-Image liefert Git
  selbst; `samuel health` prüft die ausführbare Runtime vor dem Workflow.

### 1.1 Betriebsarten und externe Voraussetzungen

| Betriebsart | Zusätzlich erforderlich | Nicht erforderlich |
|---|---|---|
| Wheel/venv beziehungsweise `install.sh` | lokaler CPython, `venv`, Git für den Quellweg, Schreibrecht auf Installations-, State- und Workspacepfad; bei privaten Releaseartefakten ein getrenntes Leserecht auf deren Quelle | Docker, Registry-Publishrecht |
| OCI/Docker | Docker Engine mit Compose, unveränderliche `image@sha256:...`-Referenz aus dem Release-Manifest, drei getrennte lokale Mounts für Config, State und Workspaces; bei privatem Package ein Registry-Leser | Python/venv auf dem Host, Package-Publisherrecht |
| Dashboard | laufende S.A.M.U.E.L.-Installation, erreichbarer Bind-Port und genau ein konfigurierter Zugriffsmodus; im Legacy-Modus `SAMUEL_API_KEY`, im lokalen Modus initialisierter Identity-State; für Webhookaktivität zusätzlich erreichbarer Ingress und `SLICE_HMAC_KEY` | Repository-Adminrecht für den normalen Dashboardbetrieb |
| Watch/Einzellauf | Ziel-SCM-Bot, Zielrepository, mindestens eine effektive LLM-Route und schreibbarer lokaler State-/Workspacepfad | Registry- oder Release-Publisherrecht |
| TEST-Akzeptanzkriterien | genau ein vorhandener projektspezifischer Test-Runner: explizites `config/eval.json::test_cmd` mit `{test}` oder ein unterstützter Marker im Zielrepository; die Toolchain muss im sterilen Verifier-Pfad ausführbar sein | automatische Runnerinstallation, freie Shellbefehle oder ein Full-Suite-Fallback |
| Externer Execution Provider | vollständige reale D03-Qualification des konkreten Profils, unveränderliche Workflow-/Tool-/Environment-Digests, getrenntes Evidence-HMAC-Secret und minimal berechtigtes Dispatch-/Lesekonto | Aktivierung des ausgeliefert unqualifizierten Platzhalterprofils oder lokaler Fallback bei Providerfehler |
| Release-/Image-Publish | sauberer Releasecheckout, grüne Tag-CI, Docker und getrennte Package-Publishercredential auf dem kontrollierten Releasehost. Für #1090 zusätzlich die geprüften Distributionsdateien, vollständige Image-ID und der SHA-256 des Schema-1-Manifests gemäß [Publisheranleitung](CONTAINER_RELEASE_OPERATIONS.md#kandidat-bauen-und-veröffentlichen). | Runtime-SCM-Token des Zielprojekts oder eine behauptete technische Einzelimage-Isolation |
| Externer Gitea-Actions-Runner | eigener Runner-Host, Docker, repo-/orggebundener Registrierungstoken und der Vertrag aus [CI_RUNNER_OPERATIONS.md](CI_RUNNER_OPERATIONS.md) | S.A.M.U.E.L.-Runtime oder deren `.env`; der Runner ist keine Produktkomponente |

### 1.2 Accounts, Credentials und kleinste Rechte

Accounts werden nicht zusammengelegt, nur weil dieselbe Plattform sie
bereitstellt. Insbesondere ist ein SCM-Bot weder Package-Publisher noch
menschliche Freigabeinstanz. Die Plattform bleibt Authority für Owner,
Mitgliedschaft und Token-Scope.

| Rolle/Credential | Zweck und kleinstes Recht | Ablage und Consumer | Rotation/Widerruf |
|---|---|---|---|
| Menschlicher Operator | Installation, Konfiguration und authentifizierte Freigabe im SCM; kein dauerhaftes Produktsecret. Für Änderungen am nativen Branchschutz ist die entsprechende Operatorauthority nötig. Lesezugriff und benötigte Tokenrechte sind separat am konkreten Endpoint zu prüfen. | menschliche SCM-Sitzung; Admincredential nie in der Runtime-`.env` | Plattformsession/PAT widerrufen; menschliche Freigaben bleiben subject- und aktionsgebundene Audit-Evidence |
| S.A.M.U.E.L.-SCM-Bot | Issue/Kommentar/Label sowie Repository/Branch/PR lesen und schreiben, eigene Identität lesen. Gitea: `write:issue`, `write:repository`, `read:user`; GitHub entsprechend Issues, Contents und Pull Requests read/write plus Metadata read. Kein Adminrecht. | `SCM_USER` + `SCM_TOKEN` in der deploymentlokalen `.env` (`0600`), nur vom S.A.M.U.E.L.-Prozess konsumiert | Dienst stoppen, neuen Token desselben Botkontos eintragen, starten und SCM-Probe ausführen, erst danach alten Token widerrufen |
| Temporärer Branchschutz-Prüfer | Branchschutz-Endpunkt des Zielrepositorys lesen; getrennt vom normalen Bot, mit den dort tatsächlich benötigten minimalen Rechten. | nur für den gezielten `doctor`-Lauf, nicht dauerhaft in `.env`, Watch oder Dashboard | unmittelbar nach der Prüfung widerrufen; fehlendes Recht lässt Doctor den Branchschutz nicht als belegt melden |
| LLM-Providerkey | ausschließlich die konfigurierte Provider-API nutzen; mindestens ein Key für jede effektive Cloudroute. | providerspezifische `*_API_KEY`-Variable in `.env` (`0600`), Consumer ist der jeweilige Adapter | neuen Key setzen, Prozess neu starten, Health und Test-Connection prüfen, dann alten beim Provider widerrufen; kein automatischer Providerwechsel |
| Dashboard-Bearer `SAMUEL_API_KEY` | Zugriff auf `/api/*`; keine SCM- oder Mergeautorität. | `.env` (`0600`); Browser hält ihn nur im aktuellen Tab | Wert ändern und Dashboard neu starten; alte Browser-Sitzungen verlieren Zugriff |
| Lokale Dashboard-Identität | Rollen- und permissionspezifischer Zugriff; keine SCM-, Merge- oder Konfigurationsmodus-Autorität. | Argon2-Hash, Rollen, Session-/CSRF-Hashes und Widerrufe im SQLite-State; Browser erhält eine opaque HttpOnly-Sitzung | Administrator ändert Rolle/Passwort oder widerruft einzelne/alle Sitzungen; Restore verlangt lokalen Recoverypfad |
| Webhook-HMAC `SLICE_HMAC_KEY` | SCM-Webhook signieren und am Ingress verifizieren. | identischer Wert in SCM-Webhook und `.env`; Consumer ist der Webhookendpoint | geplantes Wartungsfenster, beide Seiten ändern und signierten Ping prüfen; falsche Übergangssignaturen werden als Tamper-Evidence abgewiesen |
| Audit-HMAC `SAMUEL_AUDIT_HMAC_KEY` | lokale Auditkette signieren/verifizieren. Ein keyloser Writer darf eine neue unsigned Datei führen, aber keine bereits signierte Rotationsdatei verändern. | `.env` (`0600`), Audit-Sink und `samuel audit verify` | kein transparenter Live-Schlüsselwechsel/Keyring: bestehende Kette vor Wartung verifizieren und mit ihrem alten Schlüssel prüfbar archivieren; nicht still am aktiven Log wechseln |
| Private-Registry-Leser | genau das freigegebene OCI-Package herunterladen. Gitea: `read:package` plus Leserecht beim Package-Owner. | Docker-Credential-Store des Deploymentusers, nicht S.A.M.U.E.L.-`.env` oder Compose-Datei; Consumer ist Docker | neuen Token per `--password-stdin` anmelden, Digest-Pull prüfen, alten Token widerrufen und nicht mehr benötigte Logins mit `docker logout` entfernen |
| Package-Publisher | create-only Image veröffentlichen. Gitea: separat ausgestellter PAT des persönlichen Package-Owners mit ausschließlich `write:package` als Write-Scope; derselbe Owneraccount bleibt gemeinsame Trustwurzel. Package-Scope gilt ownerweit und beweist keine Einzelimage-Isolation. | `SAMUEL_OCI_PUBLISHER_TOKEN` ausschließlich für den expliziten Releaseaufruf auf dem kontrollierten Releasehost; das Werkzeug meldet ihn in einer temporären Docker-Config an und entfernt diese anschließend. Nie Produkt-`.env`, Compose-Datei oder CLI-Argument. | neue Credential per `preflight` gegen Identität, Scope, Owner-Read und Tagabwesenheit prüfen, kontrollierten Publish nachweisen, alte Credential widerrufen; nie auf Runtimehosts verteilen |
| Gitea-Runner-Registrierung | genau einen repo-/orggebundenen Runner anmelden; kein S.A.M.U.E.L.-Credential. | interaktive Runnerregistrierung; danach service-user-lesbare `.runner` mit Modus `0600`, kein Token in argv/History | Registrierungstoken im Gitea-UI zurücksetzen; einen bestehenden Runner separat in Gitea löschen und seine `.runner` kontrolliert entfernen |

Für Gitea sind Package-Scope und Ownerbindung im offiziellen
[Package-Zugriffsvertrag](https://docs.gitea.com/usage/packages/overview/#access-restrictions)
und die Registry-Namensform unter
[Container Registry](https://docs.gitea.com/usage/packages/container/)
beschrieben. Ein `write`-Scope umfasst das jeweilige Leserecht, erteilt aber
keine Mitgliedschaft beim gewählten Owner.

### 1.3 Pfade: erhalten, ersetzen oder getrennt prüfen

ADR-0706/#706 trennt die lokale Releaseinstallation in unveränderlichen Core und
persistente Betreiberpfade. Der Pfad ist implementiert, bleibt aber bis zum
Upgrade eines veröffentlichten Releases in der unabhängigen D0-Installation
eine **noch nicht real qualifizierte Release-Candidate-Funktion**. Der
Entwicklungscheckout und `install.sh` verwenden weiterhin ihre kompakte
Repositorystruktur und sind kein Kundenupdatepfad.

| Pfad/Artefakt | Rolle | Bei frischer Installation/Wechsel |
|---|---|---|
| `/opt/samuel/releases/<version>` und OCI-Image `/app` | unveränderlicher Produktstand | vollständig aus manifestgebundenem Wheel/Runtime-Lock beziehungsweise exaktem Image-Digest ersetzen; nie eine bestehende venv oder `*.egg-info` überlagern |
| `/opt/samuel/current` | genau ein aktiver lokaler Produktstand | erst nach isolierter Prüfung per atomarem Symlink-CAS wechseln; der laufende Prozess wechselt erst beim kontrollierten Neustart |
| `/etc/samuel/.env` | Secrets und Zielbindung | `0600`, operatorverwaltet und bei Updates unverändert; nie committen oder in Buildkontext/Evidence kopieren |
| `/etc/samuel/config/` | wirksame Operator- und Policy-Konfiguration | Defaults nur bei der Erstinstallation in eine leere Wurzel kopieren; bei Updates weder überschreiben noch automatisch mergen |
| `/var/lib/samuel/` | SQLite-State, Authority-Witness, Audit, DLQ, Idempotenz und Legacyarchive | als zusammenhängenden lokalen persistenten Bestand erhalten; aktive WAL-DB nur über die SQLite-Backup-API sichern |
| `/var/log/samuel/` | Prozesslogs | erhalten und nach Betreiberpolicy rotieren; Audit-Evidence bleibt unter dem Data-Vertrag |
| `/srv/samuel/workspaces/` | aktive/verifizierende Worktrees, Locks, Registry und Quarantänen | erhalten; offene Resume-/Quarantänezustände vor Wechsel inspizieren |
| `/srv/samuel/backups/` | externe beziehungsweise exportierte Backups | getrennt erhalten; ein Code-Rollback rollt State nicht automatisch zurück |
| `/srv/samuel/extensions/` | reservierte kundenspezifische Erweiterungen | erhalten, aber ohne eigenen Capability-Vertrag niemals implizit importieren oder ausführen |
| `wiki/`, Buildcache, `dist/`, `build/`, `*.egg-info` | regenerierbare Ausgabe/Buildmetadaten | ersetzen beziehungsweise aus frischem Stand neu erzeugen; niemals als Runtime- oder Versionsauthority verwenden |
| Docker-Credential-Store und Runner-`.runner` | externe Betriebscredentials | nicht in Produkt-, Config-, State- oder Workspacebackup mischen; nach eigener Plattformprozedur schützen und widerrufen |

Die vollständigen codegebundenen State-/Workspace-Dateien stehen in
[RUNTIME_REFERENCE.md](RUNTIME_REFERENCE.md). Erstinstallation und Update
stehen in Abschnitt 2.1 und 12.1; die Entscheidung ist in
[ADR-0706](adr/0706-atomic-release-layout.md) gebunden.

---

## 2. Herunterladen & Installieren

Dieser Abschnitt beschreibt die alternative native Installation für die Entwicklung. Für den veröffentlichten Docker-Installer gilt die [Installationsanleitung](INSTALL.md#öffentliche-alpha-auf-einem-docker-host-installieren).

### 2.1 Lokale Releaseinstallation (Wheel, noch D0-zu-qualifizieren)

Für diesen Wheel-Pfad werden vier zusammengehörige Assets des ausgewählten
veröffentlichten Releases benötigt: Wheel, sdist, versionierter
Runtime-Lock und `release-manifest.json`. Alle vier werden aus
demselben Release geladen. Das Manifest bindet Wheel und Lock an Tag,
Produktversion und vollständigen Commit. Der sdist enthält die unveränderten
Defaultkonfigurationen für genau den ersten Installationslauf.

Für eine Erstinstallation als `root` beziehungsweise über `sudo`:

```bash
release_dir=/pfad/zu/den/vier/heruntergeladenen/assets
release_version='<Version aus dem geprüften Manifest>'  # muss zu allen Assets passen
bootstrap_dir="$(mktemp -d)"
python3 -m venv "$bootstrap_dir/venv"
"$bootstrap_dir/venv/bin/pip" install --no-deps \
  "$release_dir/samuel-$release_version-py3-none-any.whl"
mkdir "$bootstrap_dir/source"
tar -xzf "$release_dir/samuel-$release_version.tar.gz" \
  -C "$bootstrap_dir/source" --strip-components=1

sudo "$bootstrap_dir/venv/bin/samuel-release" init \
  --defaults "$bootstrap_dir/source/config"
sudo "$bootstrap_dir/venv/bin/samuel-release" stage \
  --manifest "$release_dir/release-manifest.json" \
  --wheel "$release_dir/samuel-$release_version-py3-none-any.whl" \
  --runtime-lock "$release_dir/samuel-runtime-$release_version.lock"
sudo "$bootstrap_dir/venv/bin/samuel-release" activate \
  --version "$release_version" --expected-current none
```

Danach legt der Operator einen dedizierten Serviceaccount an, gibt ihm nur
Schreibrecht auf State, Prozesslogs und Workspaces. Die gemeinsame
Initialisierung verwendet die externe Konfigurationswurzel; die weitere
Konfiguration erfolgt im ausdrücklich gestarteten Setup-Dashboard. Die wirksame Konfiguration sollte im
Dauerbetrieb für den Runtimeaccount lesbar, aber nicht pauschal schreibbar
sein; Dashboard-Konfigurationsänderungen benötigen dann eine bewusste
Operatorfreigabe.

```bash
sudo useradd --system --home /srv/samuel --shell /usr/sbin/nologin samuel
cd /etc/samuel
sudo /opt/samuel/current/bin/samuel setup --non-interactive
# Zugriff nach Abschnitt 4.4 einrichten, dann im Dashboard konfigurieren:
sudo /opt/samuel/current/bin/samuel dashboard --configuration-mode setup
# Nach dem Speichern Setup beenden; erst danach Production einrichten.
sudo chown -R root:samuel /etc/samuel
sudo chmod 0750 /etc/samuel /etc/samuel/config
sudo chmod 0600 /etc/samuel/.env
sudo chown -R samuel:samuel /var/lib/samuel /var/log/samuel \
  /srv/samuel/workspaces /srv/samuel/backups
sudo /opt/samuel/current/bin/samuel install-service \
  --mode dashboard --user samuel --write
```

Der erzeugte Dienst verwendet über den verifizierten Launcher den stabilen
Pfad `/opt/samuel/current/bin/samuel`; er fällt nicht auf einen bestimmten
alten Releasepfad oder `python -m samuel` zurück. `extensions/` ist nur eine
geschützte Ablageklasse und heute kein Plugin-Suchpfad. Self-Mode darf im
separaten Candidate-Workspace ein neues Release vorbereiten, aber niemals
`current`, Trust Roots oder wirksame Policy selbst aktivieren.

### 2.2 Entwicklungscheckout

Der folgende Einzeiler ist für Entwicklung und Evaluation aus dem exakten
Quellstand, nicht für atomare Kundenupdates:
```bash
git clone <repo-url> samuel && cd samuel
release_tag='<tag aus dem verifizierten neuesten Release-Manifest>'
git checkout "$release_tag"
./install.sh                 # Paket und gemeinsame Initialisierung; danach Dashboardeinrichtung
```
`install.sh` verwendet immer den bestehenden nichtinteraktiven Initialisierer.
Vorhandene Env-/`.env`-Werte bleiben seine Eingabe; fehlendes SCM wird anschließend
im Dashboard ergänzt. Es gibt keinen separaten interaktiven CLI-Fragebogen.
Die Ausgabe nennt den ausdrücklich zu startenden Setup-Dashboardprozess und
anschließenden Production-Start. Nach der Paketinstallation materialisiert es
weiterhin die lokale Entwicklernavigation unter `wiki/`.

**Manuell:**
```bash
git clone <repo-url> samuel
cd samuel
release_tag='<tag aus dem verifizierten neuesten Release-Manifest>'
git checkout "$release_tag"
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[all]"
python tools/wiki.py build
```

Beim Checkout eines veröffentlichten Produkt-Tags entspricht die installierte
Paketversion exakt dem Tag ohne führendes `v`. Ein Checkout nach dem neuesten
Produkt-Tag erhält automatisch eine PEP-440-Entwicklungsversion mit
Commitkürzel; ein veränderter getrackter Arbeitsbaum wird zusätzlich in der
lokalen Versionskomponente markiert. Die vollständige Revision und der gesamte
Git-Dirty-State, einschließlich ungetrackter Dateien, bleiben davon getrennte
Build-Evidence. Quellen ohne SCM-, sdist- oder installierte Paketmetadaten
melden `0+unknown` und gelten nicht als Release.

Die Installation erzeugt den Console-Entry-Point `samuel`. Nur dieser ist für
den Betrieb aus beliebigen Arbeits- und Zielrepositorys unterstützt.
`python -m samuel` darf nicht aus einem potenziell unvertrauenswürdigen
Zielrepository verwendet werden: Ein dortiges Top-Level-Paket `samuel` würde
vor der installierten Distribution importiert und könnte bereits beim Import
Code ausführen.

Zusätzlich installiert das Paket den internen Helper
`samuel-git-askpass`. Er ist kein Operator-CLI: S.A.M.U.E.L. verwendet ihn nur
für an das konfigurierte Repository gebundene HTTP-Fetches/-Pushes. Der Token
wird nicht in Git-Argumente, Remote-URLs oder Git-Konfiguration geschrieben.
Ein globaler Credential Helper ist kein unterstützter Ersatz für fehlende
`SCM_USER`-/`SCM_TOKEN`-Konfiguration.

**Extras** (statt `[all]` gezielt wählbar):

| Extra | Inhalt | wann |
|---|---|---|
| `dashboard` | jinja2 | Web-Dashboard |
| `llm` | anthropic, openai SDKs | Anthropic/OpenAI direkt |
| `tree-sitter` | tree-sitter-Parser | Skeleton für JS/TS/Go |
| `github` | cryptography | GitHub-App-Auth |
| `dev` / `ci` | pytest, ruff, mypy und JavaScript-Parser / pip-audit | Entwicklung |

Der CI-Security-Audit nutzt `tools/run_pip_audit.py`: Ein bestaetigter
Schwachstellenbericht bricht sofort ab. Nur technisch nicht auswertbare
Transport-/Tool-Fehler werden hoechstens dreimal mit je 5 Sekunden Abstand
versucht. Bleibt der Audit ohne eindeutigen sauberen Bericht, ist der Job rot
(fail-closed).

DeepSeek/Gemini/OpenRouter/Ollama/LM Studio brauchen **kein** Extra (HTTP-only).
Der HTTP-Dashboardserver verwendet im aktuellen Code die Python-Standardbibliothek;
`dashboard` bleibt ein deklariertes Extra mit Jinja2 und ist keine
Runtime-Voraussetzung dieses Servers. Minimale Providerinstallationen müssen
die tatsächlich verwendeten SDKs separat erfüllen.

---

## 3. Schnellweg (empfohlen)

Für neue Testinstallationen empfehlen wir das öffentliche Docker-Image **v2.0.0a42**. Den Installer aus dem GitHub-Release auf dem Docker-Host ausführen. [Installationsanleitung](INSTALL.md#öffentliche-alpha-auf-einem-docker-host-installieren)

Nur für den bereits installierten nativen Entwicklungs-/Wheelweg:

```bash
samuel setup --non-interactive  # vorhandene Werte und Schlüssel initialisieren
# Berechtigten Dashboardzugang nach Abschnitt 4.4 bereitstellen.
samuel dashboard --configuration-mode setup
# Nach dem Speichern Setup beenden, dann ausdrücklich:
samuel dashboard --configuration-mode production
```

Native Zugangsbereitstellung und Operatorprozesse sind zusätzliche Schritte
gegenüber dem integrierten OCI-Bootstrap. Kein automatischer Workflowstart.
`samuel doctor` bleibt die vorhandene separate Diagnose.

---

<a id="4-konfiguration-via-wizard--samuel-setup"></a>

## 4. Dashboardkonfiguration und Installer-Initialisierung

Der interaktive CLI-Fragebogen ist durch die vorhandene Dashboard-Ersteinrichtung
ersetzt. `samuel setup` ohne `--non-interactive` beendet sich mit Hinweis und
Exitcode 2, ohne Fragen, Netzwerkprobe oder Dateischreibzugriff. Automatisierungen
und der OCI-Installer verwenden weiterhin `samuel setup --non-interactive`.
Dieser gemeinsame Initialisierer ist keine zweite Konfigurationsoberfläche.

Im berechtigten Setup-Dashboard werden SCM-Provider (`gitea`/`github`), Server/API-URL,
Benutzer, Token, genau ein erwarteter Required Check, Repository (`owner/name`)
und Bot-Benutzer eingestellt. Die Verbindung wird beim Speichern geprüft;
fehlgeschlagene Proben bleiben sichtbar. Die frühere Gitea-Repoliste des
CLI-Fragebogens entfällt: Das einzelne gewünschte Repository wird im bestehenden
Dashboardfeld angegeben, ohne neue Projektverwaltung oder Discovery-API.
Bei Gitea muss der Benutzer zum Tokenkonto passen; GitHub verwendet für Git
weiterhin den providerspezifischen Benutzer `x-access-token`.

`PROJECT_ROOT` bezeichnet den expliziten Zielpfad. Im OCI-Betrieb wird die
bestehende Hostquelle im Dashboard vorbereitet und beim ausgegebenen
Operator-Production-Start nach eigener Bestätigung geprüft und registriert.
Der native Self-Mode bleibt ein eigener expliziter Sourcecheckout-Modus.

- Vor dem ersten Workflow die Teststrategie des Zielprojekts in
  `config/eval.json` festlegen. Die explizite Policy hat Vorrang vor
  Marker-Autodetection. Beispiel für Unittest:

  ```json
  {"test_cmd": "python -m unittest {test}", "test_timeout": 60}
  ```

  Dazu gehören `[TEST] tests.test_board` beziehungsweise
  `[TEST] tests.test_board.TestBoard.test_move`. Für Pytest ist etwa
  `{"test_cmd": "python -m pytest -q {test}"}` mit
  `[TEST] tests/test_board.py::TestBoard::test_move` zulässig. Runner und
  Module werden nicht durch den Workflow installiert. Im OCI-Betrieb bereitet
  der Operator Python/Pytest ausdrücklich mit dem offiziellen
  `samuel-container toolchain`-Pfad vor (siehe unten). `samuel doctor` muss den
  effektiven Runner und seine Selektorform vor dem ersten Lauf als `ok`
  melden.

  Ein Pytest-`test_cmd` mit `-k {test}` eignet sich nur für logische Namen.
  Soll der Plan Node-IDs verwenden, muss `{test}` wie im Beispiel als direktes
  positionsgebundenes Pytest-Argument stehen.

Zeitzone (IANA) und Dashboard-Port werden im selben Dashboard eingerichtet.
Die Zone wird in `agent.json` gespeichert und beim ausdrücklichen Folgeprozess
wirksam; Audit-/API-Zeitpunkte bleiben UTC. LLM-Provider, Keys und späteres
Routing/Promptprofil verwenden die bestehenden Dashboardmechanismen und
ConfigurationSession. Für allgemeine Konfiguration gilt weiterhin R15a.
Workflow-Labels werden über die vorhandene Schaltfläche synchronisiert.

Der nichtinteraktive Initialisierer erhält bestehende `.env`-Werte/Kommentare,
erzeugt nur fehlende Webhook-/Dashboard-/Audit-Schlüssel, schreibt privat mit
Modus 0600, erhält eine gespeicherte Zeitzone ohne explizites `TZ`, legt
notwendige Verzeichnisse an und verwendet den vorhandenen Labelabgleich und
Doctor. Ein Doctor-Fehler wird getrennt angezeigt; gespeicherte Konfiguration
ist keine Betriebs- oder Release-Abnahme. Der Erstinstaller startet anschließend
das gesicherte Setup-Dashboard, keine Workflows.

Im Legacy-Modus liegt `SAMUEL_API_KEY` ausschließlich in der geschützten `.env`;
der Initialisierer gibt ihn nicht aus. Die geschützte Übergabe an berechtigte
Clients bleibt ein Operatorweg. Der Doctor-Schlüsselcheck beweist keine Anmeldung
oder Berechtigung. Ohne erforderlichen Key verweigert der Legacy-Server den Start;
`local_identity` verwendet seine eigenen Benutzer-/Session-/Tokenregeln gemäß
`config/auth.json` und [Abschnitt 4.4](#44-lokale-dashboard-identitäten-und-cutover).

### 4.1 Bot-User — was ist das?

Der SCM-Account-**Login**, unter dem SAMUEL handelt (PRs, Kommentare, Labels).
Kein zusätzliches Secret — nur der Name des Kontos, zu dem dein `SCM_TOKEN`
gehört. Er dient der **Bot/Human-Unterscheidung** im Activity-Tab: Webhook-
Ereignisse, deren Auslöser == `SCM_BOT_USER`, gelten als `bot`, alle anderen als
`human`. **Best Practice:** dediziertes Konto (`samuel-bot`); läuft SAMUEL unter
deinem eigenen Account, fällt die Unterscheidung weg.

### 4.2 Non-interaktiv (Automatisierung / CI / Docker)

```bash
umask 077
if [ ! -e .env ]; then install -m 600 .env.example .env; fi
"${EDITOR:-vi}" .env
set -a
. ./.env
set +a
samuel setup --non-interactive
```
Werte kommen aus Env (oder bestehender `.env`); fehlende Secrets werden generiert,
keine Prompts. SCM-Verbindungsfehler werden toleriert (Setup läuft durch).
Der Ablauf legt nur bei fehlender Datei eine neue `.env` an und überschreibt
keine bestehende Konfiguration. Reale Token werden nur im Editor beziehungsweise Secret-
Provisioning gesetzt, nie als Befehlsargument oder wörtliche Shell-History.
Environment und Datei bleiben für andere Prozesse desselben Serviceaccounts
eine verbleibende Vertrauensgrenze.

### 4.3 Dashboard-Rekonfiguration und Produktions-Freeze

Kann der State für die Identitätsprüfung nicht gelesen oder aktualisiert
werden, weist das Dashboard geschützte Anfragen mit HTTP 503 und dem
State-Fehlercode ab. Die angeforderte Aktion wird nicht ausgeführt; es gibt
keinen Wechsel auf einen anderen Authentisierungsweg und keine automatische
Wiederholung einer Änderung. Nach Behebung des Fehlers die Ansicht neu laden
und den vorhandenen Konfigurationszustand prüfen, bevor eine Aktion erneut
ausgelöst wird.

Die Zeitzone kann im vorhandenen Einrichtungstab als IANA-Name gespeichert
werden. Der Setupweg erhält die übrigen Werte in `config/agent.json` und
verweigert ungültige Zonen ohne Teilspeicherung. Dafür gelten die allgemeinen
Setup-/Production-Grenzen; eine normale LLM-Konfigurationssitzung öffnet diesen
Schreibweg nicht. Der abschließende Operator-Start lädt die gespeicherte Zone.
Ein wiederholtes `setup --non-interactive` erhält diese Zone. Ein ausdrücklich
gesetztes `TZ` in `.env` beziehungsweise der Operatorumgebung hat weiterhin
Vorrang; nur ohne gespeicherte oder explizite Zone wird die Hostzone verwendet.
Eine unlesbare oder strukturell ungültige vorhandene `agent.json` stoppt Setup
vor der Speicherung.

Nach dem Speichern der SCM-Verbindung können die Workflowlabels über
**Settings → Labels auf SCM synchronisieren** ausdrücklich angelegt werden.
Die Aktion nutzt die gespeicherte Verbindung im selben Setup-Prozess; dafür
ist kein zusätzlicher CLI-Aufruf oder Setup-Neustart erforderlich. Sie benötigt
die bestehende Operatorberechtigung und ist im Production-Modus gesperrt.

Ein im Dashboard angezeigter offener Host-Moduswechsel wird ausschließlich
über den gebundenen lokalen Operatorweg abgeschlossen. Das Übernehmen oder
Verwerfen eines LLM-/Promptentwurfs beendet diese Wartung nicht. Die technische
Wartungssperre aus #1090 ist im erweiterten manifestgebundenen OCI-Installer
mit Stopp, Start und Readiness verbunden. Dafür den `setup`-/`start`-Weg aus
Abschnitt 9.1 verwenden; ältere veröffentlichte Kits behalten ihren bisherigen
Bedienweg. Dies ist keine rückwirkende a34- oder Releasequalifikation.

Nach einem gescheiterten Versuch kann der Operator diesen im Workflowdetail
mit Begründung sicher beenden. Erst dann und ohne sonstige offene Arbeit sind
LLM-Änderungen möglich; anschließend beginnt **Neu planen** einen eigenen
Versuch mit neuer Freigabe. [Wiederanlaufbedienung](DASHBOARD.md#versuch-beenden-neu-planen-oder-technisch-fortsetzen-920).


Der normale Dashboardprozess bleibt im Modus `production`. Für die laufende
LLM-Verwaltung dient der Konfigurations-Tab: **Konfiguration bearbeiten** öffnet
bei echtem Leerlauf einen exklusiven Bearbeitungsmodus. Watch, Night oder Self
müssen dafür nicht beendet werden. Ein laufendes Issue, Planfreigabe, MANUAL,
erforderliches Review oder ein ungeklärter fortsetzbarer Vorgang verhindern den
Eintritt. Eine fertig reviewte PR, die nur auf Human Merge wartet, blockiert nicht.

Aufgaben sowie Default/Fallbacks werden zunächst als gemeinsamer Entwurf
bearbeitet. Die Vorschau zeigt Provider, Modell und Prompt-Quelle einschließlich
Schedule- und Fallback-Routen. Freie Modell-IDs bleiben erlaubt. Schedules werden
im Betrieb weiterhin je Aufruf ausgewertet; nur ihre Bearbeitung erfordert den
Konfigurationsmodus. Benchmarkdaten sind Hinweise, keine Freigabesperre.
Verbindungstests sind optional, prüfen nur `provider.validate` und belegen keine
Modellantwort. Ein fehlgeschlagener Test benötigt beim Übernehmen eine bewusste
Bestätigung. Ohne Test bleibt der Stand ausdrücklich ungetestet.

**Übernehmen und Betrieb fortsetzen** validiert den vollständigen Entwurf,
sichert den vorherigen Stand, schreibt beide LLM-Dateien und aktiviert die neuen
Adapter gemeinsam. Ein Dienstneustart ist dafür nicht nötig. **Verwerfen und
Betrieb fortsetzen** stellt den vorherigen Stand wieder her. Browserverlust und
Prozessneustart heben die Sperre nicht auf. Nach einem unterbrochenen Vorgang kann
ein frisch authentisierter Administrator **Vorherigen Stand wiederherstellen**
verwenden. Solange Schreiben oder Wiederherstellen fehlschlägt, bleiben neue
Workflows gesperrt. Andere Browser dürfen eine veraltete Version nicht speichern.

Nach einem abgebrochenen Arbeitsprozess prüft **Ausführungsstatus abgleichen**
über eine Prozesssperre, ob tatsächlich keine Ausführung mehr lebt. Die Aktion
löscht keine wartenden Issues, Budgets oder ungeklärten externen Vorgänge; diese
müssen über die bestehenden Workflow-/Recoverywege abgeschlossen werden.

Die erste Auslieferung dieses Mechanismus benötigt einen regulären Neustart aller
Prozesse auf demselben neuen Code. Ein gemischter Betrieb mit alten Binärständen
ist nicht unterstützt. Alle Prozesse einer Installation müssen dieselben
Konfigurationsdateien und denselben Authority-State verwenden. Der Compose-
Produktionscontainer bindet `llm.json`, `llm/defaults.json` und `llm/prompts/`
für diese Bearbeitung schreibbar ein; die übrige Konfiguration bleibt read-only.
Lokal benötigt der Dienst Schreibrechte auf diese vorhandenen Konfigurationsdateien
und den Promptordner. `.env` bleibt außerhalb der ConfigurationSession.
Promptinhalte können innerhalb derselben Konfigurationssitzung bearbeitet,
geprüft und aktiviert werden. Benutzerdefinierte Prompts sind sichtbar
gekennzeichnet, ohne verpflichtenden LLM-Probelauf. Beim Öffnen oder Wechseln
der Promptebene bleiben Textfeld und Schreibaktionen bis zum erfolgreichen Laden
gesperrt. Verspätete Antworten einer vorherigen Ansicht oder Ebene werden verworfen.
Auch während Save, Reset oder Referenzwiederherstellung bleiben Text, Name, Ebene
und Schreibaktionen gesperrt. Ein abgewiesener Auftrag erhält die Eingabe für
eine bewusste Wiederholung; seine Antwort verändert keinen neu geöffneten Dialog.
Bei einem Ladefehler bleibt die Bearbeitung gesperrt; Ansicht oder Ebene erneut
öffnen und den geladenen Inhalt prüfen. [Laufbindung und Rückkehr zur Referenz](agents/AGENT_PROMPTS_AND_INSTRUCTIONS.md#referenz-custom-und-laufbindung).
Security-/Feature-Einstellungen und Workflowbudgets sind kein
Bestandteil dieser Bearbeitung. Das Setup bleibt der Erstinstallationsweg;
die bestehenden Setupfunktionen für andere Bereiche werden hier nicht erweitert.

Das Setupformular sperrt seine Eingaben, bis der Status Schreibberechtigung
bestätigt; in Production und bei fehlender Berechtigung bleiben sie gesperrt.
Der Server schützt den gesamten Setup-Schreibvorgang zusätzlich mit der
gemeinsamen Konfigurationssperre. Bei aktiver Arbeit, einem parallelen
Schreibvorgang oder einer nicht abgeschlossenen Konfigurationssitzung wird
Speichern mit HTTP 409 abgewiesen. Nach dem ausdrücklichen Abschluss des
blockierenden Vorgangs den Status neu laden und die Änderung erneut prüfen.
Bei einem abgewiesenen Save erhält die bestehende Fehleranzeige den Fokus und
wird in den sichtbaren Bereich gescrollt. Backenddetails wie ein leerer
`SCM_REQUIRED_STATUS_CONTEXT` bleiben sichtbar; Fehler erlauben keine
Speicherung. Der Projektabschnitt verweist auf die bestehende Testpolicy aus
§4 und den OCI-Projekt-/Toolchainweg aus §9.1. Er ist kein `test_cmd`-Editor
und installiert keine Abhängigkeiten.
Der Hinweis nennt die Voraussetzungen der bestehenden Projektregistrierung:
dedizierter sauberer Standalone-Checkout, passender Origin, voller initialer
Commit-SHA, Runtime-Schreibrechte und anschließend der Containerpfad als
`PROJECT_ROOT`. Ein produktiver Checkout wird nicht zum Agentenbestand.

Für Erstinstallation beziehungsweise die übrigen Setupfunktionen den Produktionsdienst stoppen, dieselbe
externe Konfiguration vorübergehend schreibbar einbinden und einen getrennten
lokalen Setup-Prozess starten. Bei einer lokalen Installation genügt:

```bash
samuel dashboard --host 127.0.0.1 --configuration-mode setup
```

Für die #1090-OCI-Installation den aufbewahrten Bootstrap verwenden:

```bash
sudo bash /pfad/zum/geprüften-bootstrap/tools/samuel-container setup
# Allgemeine Einstellungen im Dashboard prüfen und ausdrücklich speichern.
sudo bash /pfad/zum/geprüften-bootstrap/tools/samuel-container start
```

Bei abweichendem Installationspräfix beide Male denselben `--root` ergänzen.
Der Installer führt die Moduswechsel erst nach Zulassungsprüfung durch.
LLM-/Promptänderungen innerhalb der ConfigurationSession benötigen diese
Hostaufrufe nicht. Die folgende direkte Composeform ist ausschließlich ein
technischer Bestandsweg für Quellcheckouts und ältere Kits; sie ersetzt weder
die Wartungszulassung noch den normalen Operatorweg der #1090-Installation.

Für Compose ist `SAMUEL_ENV_FILE` die dauerhafte Quelle der Umgebungswerte.
Der Produktionscontainer importiert sie beim Start über `env_file`, ohne die
Datei im Container einzubinden. Nur der getrennte Setup-Lauf bindet dieselbe
Datei als `/app/.env` schreibbar ein, um eine bestätigte Änderung zu speichern.
Der Lauf bleibt am Host auf Loopback begrenzt:

```bash
docker compose stop samuel
SAMUEL_DASHBOARD_BIND=127.0.0.1 \
  docker compose -f docker-compose.yml -f docker-compose.setup.yml run --rm --service-ports samuel
# Im Setup-Dashboard validieren und speichern, dann den Setup-Prozess beenden.
docker compose up -d --force-recreate samuel
```

Die Setup-Override-Datei ersetzt die Produktionsmounts vollständig: `.env` und
`config` sind schreibbar, ohne einzelne JSON-Dateimounts, die atomare
Dateiersetzung verhindern. Daten, Logs, Backups und Workspaces bleiben an
dieselben Hostpfade gebunden. Registrierte Projekt-/Toolchain-Overlays werden
vom Installer anschließend ergänzt und bleiben auch im Setup erhalten.
Der anschließende Produktionscontainer importiert die gespeicherte
`SAMUEL_ENV_FILE` erneut und bindet `config` read-only ein. Schreibbar bleiben
nur `llm.json`, `llm/defaults.json` und `llm/prompts/` für den exklusiven
Dashboard-Konfigurationsmodus. Der Installer legt den Promptordner vor dem
Containerstart mit Eigentümer und privaten Rechten der Runtime an.
Setupänderungen werden nicht
in den laufenden Dashboardprozess übernommen; es gibt keinen zweiten
Settingsstore. Ein read-only Bind-Mount verhindert Containerwrites, aber keine
Änderungen durch den Host. Der Watch-Pfad lädt generische JSON-Werte pro Scan
erneut. Workflow und Bus-Wiring bleiben unverändert; eine neue LLM-Konfigurationsrevision wird vor dem nächsten Arbeitsstart vollständig geladen. `.env`-Werte
werden erst beim neuen Containerstart importiert.

Der Setup-Writer ersetzt Dateien regulär über einen gestagten atomaren Rename.
CLI und Dashboard verwenden denselben Staging-/Rollback-Writer. Temporäre
Dateien werden exklusiv mit privaten Rechten angelegt; `.env` enthält beim
Schreiben bereits Modus `0600`. Datei-Symlinks und nicht reguläre Ziele werden
abgewiesen, Rechtefehler werden als fehlgeschlagenes Setup gemeldet. Die
vorhandenen Merge-Regeln erhalten Werte und Kommentare. Das ist Dateisicherheit,
keine Verschlüsselung: Secrets bleiben im bestehenden `.env`-Vertrag Klartext.

Ein einzelner Docker-Datei-Bind-Mount nach `/app/.env` kann dieses Rename mit
`EBUSY` ablehnen; das image-eigene `/app` kann für den non-root-Prozess zudem
keinen Geschwister-Tempfile erlauben. Ausschließlich in diesem getrennten
Setup-Prozess stageiert S.A.M.U.E.L. den Inhalt dann privat und schreibt ihn
synchronisiert in dieselbe Datei; kontrolliert erkannte I/O-Fehler werden
zurückgerollt. Das private Staging gilt auch für die Rücknahme eines bereits
begonnenen Writes, wenn das image-eigene Verzeichnis keine Rollbackdatei
zulässt; temporäre Staging- und Rollbackdateien werden anschließend entfernt.
Ein vor jeder Mutation verweigerter Zugriff auf eine unveränderte Zieldatei
erfordert keinen erneuten Schreibversuch für diese Datei. Die Rücknahme der
bereits geänderten Dateien läuft weiter. Scheitert die Rücknahme einer tatsächlich
geänderten Datei dauerhaft, versucht der Writer trotzdem die übrigen Rücknahmen
und meldet `rollback incomplete` mit den betroffenen Dateinamen. Der Operator
prüft und korrigiert diese Quellen im gestoppten Setupzustand vor dem Neustart;
eine fehlgeschlagene Rücknahme wird nicht als erfolgreicher Setupabschluss gemeldet.
Dieser schmale Fallback ist nicht rename-atomar gegenüber einem
Prozess- oder Hostabbruch während des In-Place-Writes; der Operator prüft
deshalb den gespeicherten Stand vor dem Neustart. Production bleibt währenddessen
gestoppt und behält keine Schreibauthority.

Nach Validierung und Speichern den Setup-Prozess beenden, die Konfiguration
wieder read-only einbinden und den normalen Dienst ohne diesen Schalter neu
starten. Der ausgelieferte Compose-Befehl und die von `install-service`
erzeugte Dashboard-Unit erzwingen dafür zusätzlich
`--configuration-mode production`, auch wenn eine externe Environment-Datei
abweicht. Der Settings-Tab zeigt Modus und Quelle, den nicht geheimen Digest der
gespeicherten JSON-/Prompt-Konfiguration, den wirksamen
Digest und `Neustart erforderlich`. `.env`-Secrets fließen nicht in diese
sichtbaren Digests ein. Mehrere Dateien werden vor dem Ersetzen gestaged und
bei normalen I/O-Fehlern zurückgerollt; ein Prozess-/Hostabsturz zwischen zwei
Dateiersetzungen ist keine dateisystemübergreifende Transaktionsgarantie und
erfordert Prüfung der angezeigten gespeicherten Konfiguration vor dem Neustart.

Der optionale öffentliche Extension-Datenanschluss wird ebenfalls nur über die
Operator-Datei `config/extensions.json` gewählt. Der ausgelieferte Stand setzt
`documentation.static_claims` auf `enabled=false` und `required=false`.
Änderungen erfolgen während desselben Setup-/Rekonfigurationsfensters und
werden erst nach dem Neustart wirksam; der Produktionsprozess besitzt keinen
Runtime-Override. Der Settings-Tab zeigt gespeicherten und wirksamen Zustand
getrennt und aktiviert seine Eingaben nur im Setupmodus. Den read-only Zustand
zusätzlich per CLI prüfen:

```bash
samuel-extension status --config config/extensions.json
```

Der konkrete statische Documentation-Consumer verwendet danach einen
operatorgewählten Austauschpfad und ein unabhängiges Repository. Request,
Policy, Claims und Resultat enthalten keine Credentials:

```bash
samuel-documentation prepare \
  --repository-root /srv/target \
  --repository owner/name \
  --policy config/documentation-capability.json \
  --exchange-root /srv/samuel/extensions/documentation/exchange \
  --request-id docs-1

env -i PATH="$PATH" LANG=C.UTF-8 python3 /srv/target/tools/documentation_consumer.py \
  --repository-root /srv/target \
  --exchange-root /srv/samuel/extensions/documentation/exchange \
  --request /srv/samuel/extensions/documentation/exchange/request.json \
  --result /srv/samuel/extensions/documentation/exchange/result.json

samuel-documentation validate \
  --repository-root /srv/target \
  --exchange-root /srv/samuel/extensions/documentation/exchange \
  --request /srv/samuel/extensions/documentation/exchange/request.json \
  --result /srv/samuel/extensions/documentation/exchange/result.json
```

Der Consumer muss unter seinem policygebundenen Pfad aus genau dem gebundenen
Git-Head und in einem credentialfreien Prozess laufen. Ein Referenzconsumer
verweigert bekannte Credentialvariablen und nennt dabei nur deren Namen.
Publicationcredentials werden ausschließlich dem separaten
`samuel-documentation publish`-Prozess über Git-Authentisierung bereitgestellt;
sie gehören nicht in Remote-URL, Contractartefakte oder Logs.

Ein vorhandenes Package oder Capability-Manifest aktiviert den Anschluss
nicht. Bei `required=true` liefert `samuel-extension status` einen blockierenden
Status und Exitcode 1, solange der Consumer deaktiviert, nicht vorhanden oder
nicht exakt kompatibel ist. Die eigenständige `samuel-documentation`-CLI liest
diese Auswahl derzeit nicht; vor einer externen Ausführung muss der Status
ausdrücklich geprüft werden. Die Dashboard-Checkbox startet keinen Consumer
und keinen Wiki-Build. Für den normalen Installationstest bleiben **Aktiviert**
und **Erforderlich** ausgeschaltet. Contractdateien und Credentials werden
getrennt provisioniert; der erste Contract benötigt selbst keine Credentials.
Die Felder unter **Settings → Documentation Extension** erklärt die
[Dashboard-Anleitung im Extension-Datenvertrag](EXTENSION_CONTRACT.md#dashboard-documentation-extension-und-wiki).
Der unabhängige Repository-Wiki-Weg steht in [Abschnitt 12.2](#122-lokales-wiki-und-externer-publisher).

### 4.4 Lokale Dashboard-Identitäten und Cutover

Der ausgelieferte Zustand bleibt zunächst `legacy_api_key`, damit vorhandene
Clients ausdrücklich migriert werden können. Für den lokalen Referenzprovider
den Dienst stoppen, eine nur für den Serviceuser lesbare Passwortdatei
erzeugen und den ersten Administrator initialisieren:

```bash
umask 077
install -m 600 /dev/null /run/samuel-admin-password
"${EDITOR:-vi}" /run/samuel-admin-password
samuel identity bootstrap --username admin \
  --password-file /run/samuel-admin-password --json
samuel identity status --json
```

Die Passwortdatei muss regulär, Eigentum des aufrufenden OS-Benutzers und
`0600` oder strenger sein. Das Passwort erscheint weder im Argumentvektor noch
in der Ausgabe. Alternativ initialisiert der vorhandene CLI-Bootstrap den
Administrator ohne Passwortdatei über ein interaktives Terminal:

```bash
samuel identity bootstrap --username admin --prompt-password
```

Diese Option verlangt zwei übereinstimmende verdeckte Eingaben. Pipes,
abgebrochene Eingabe, fehlende sichere Terminalsteuerung und die gleichzeitige
Angabe von `--password-file` werden abgewiesen. Der bestehende Password-/Argon2-
Vertrag bleibt erhalten; die interaktive Option gilt ausschließlich für
`bootstrap`, nicht für Restore-/Identity-Recovery. Sie aktiviert den lokalen
Zugriffsmodus noch nicht.

Vor dem Cutover alle Browser-, Skript- und Monitoringclients
inventarisieren. Danach atomar auf den lokalen Modus wechseln:

```bash
samuel identity cutover --client-inventory-confirmed \
  --reason "Dashboard- und API-Clients auf lokale Identitäten migriert" --json
```

Nach dem Neustart akzeptiert der Server ausschließlich lokale Sessions und
explizit erzeugte Automation-Token. Der alte `SAMUEL_API_KEY` ist dann kein
Fallback. Viewer, Auditor, Operator und Administrator sind unabhängige Rollen;
ein Administrator sieht Status oder Diagnosen nur mit den zusätzlich
zugewiesenen Rollen. Identity-Administration erfordert eine frische
Passwortauthentisierung. Für HTTPS muss `secure_cookies` in `config/auth.json`
aktiv sein; ohne TLS darf dieser Betriebsclaim nicht als qualifiziert gelten.

Benutzer- und Automation-Tokennamen teilen denselben lokalen Namensraum.
Ein bereits belegter Name, auch mit anderer Groß-/Kleinschreibung, wird
strukturiert abgewiesen; bestehende Identitäten und Tokens bleiben unverändert.
Für einen zusätzlichen Token einen eigenen Namen wählen, keine vorhandene
Identität überschreiben. Das ist keine Prüfung minimaler SCM-Tokenrechte.

Ein State-Restore widerruft alle Sessions und Automation-Token und setzt
`recovery_pending`. Nach Restore/Reconcile führt der lokale Operator aus:

```bash
samuel identity recover --username admin \
  --password-file /run/samuel-admin-password \
  --reason "operatorgeführte Wiederherstellung nach geprüftem Restore" --json
```

Bootstrap, Cutover und Identity-Recovery schreiben über den vorhandenen
JSONL-Audit-Writer. Ein konfigurierter `SAMUEL_AUDIT_HMAC_KEY` bindet diese
lokalen Operatorereignisse an die signierte Tagesdatei; die Prozessumgebung
hat Vorrang vor der sicher gelesenen deploymentlokalen `.env`. Dafür werden
keine Provider oder Workflows gestartet. Scheitert das Audit-Schreiben, meldet
die CLI keinen Erfolg. Eine bereits erfolgte Identity-Änderung bleibt zur
Diagnose erhalten: `identity status` lesen und den Auditfehler beheben, keine
Auditdateien löschen oder nachträglich neu signieren.

### 4.5 Manuelle Betreiberkonfiguration

```bash
cp .env.example .env
# Werte eintragen, dann:
samuel setup-labels   # Labels anlegen
```

---

## 5. LLM-Provider einrichten

Die Installer-Initialisierung sammelt keine LLM-Keys. Das vorhandene Dashboard-Setup kann
Provider, Modell, Endpoint und Providerkey mit `WRITE_CONFIGURATION` im
expliziten Setupmodus prüfen und speichern (Abschnitt 4.3). Alternativ:

1. **API-Key in die `.env`** eintragen (Provider → Env-Variable):

   | Provider | Env-Variable | Hinweis |
   |---|---|---|
   | DeepSeek | `DEEPSEEK_API_KEY` | Cloud |
   | Anthropic | `ANTHROPIC_API_KEY` | braucht `[llm]`-Extra |
   | Gemini | `GEMINI_API_KEY` | Cloud |
   | OpenAI | `OPENAI_API_KEY` | braucht `[llm]`-Extra |
   | OpenRouter | `OPENROUTER_API_KEY` | Gateway; verfügbarer Katalog und Preise stammen aus dem Metadatencache |
   | Ollama | — | `config/llm.json` → `ollama.url` (Default `http://localhost:11434`) |
   | LM Studio | — | `config/llm.json` → `lmstudio.url` (`.../v1`) |

2. **Default-Provider** wählen — entweder in `config/llm.json`
   (`"default": {"provider": "deepseek", "fallbacks": ["openrouter"]}`),
   im Dashboard unter *Settings → LLM Default & Fallback* oder per Env
   `SAMUEL_LLM_PROVIDER`. Fallbacks werden geordnet erst nach einem Fehler des
   vorherigen Providers verwendet und als `ProviderFallbackUsed` auditiert.
   Ein expliziter Task- oder Schedule-Provider in
   `config/llm/defaults.json` hat Vorrang vor dieser globalen Wahl. Wer für
   ein Operator- oder Qualificationprofil einen anderen Provider verwenden
   will, muss deshalb die vom Profil produktiv benötigten Taskrouten bewusst
   setzen und die effektive Ausgabe vor dem Lauf prüfen; die globale
   Env-Variable allein genügt nicht (#829). Produktive LLM-Consumer besitzen
   derzeit `planning`, `implementation`, `review` und `healing`.
   Die konfigurierte Route `evaluation` besitzt keinen produktiven LLM-Consumer;
   eine ungenutzte Konfiguration erzeugt keine kritische Probepflicht.

3. **Modell** pro Provider in `config/llm.json` (z. B. `"deepseek": {"model": "deepseek-chat"}`).
   Im Dashboard bleiben Einrichtung, Taskmodell und Schedulemodell frei
   eingebbar. Optionale Vorschläge bestätigen keine Providerverfügbarkeit;
   unbekannte oder entfernte IDs werden allein wegen ihres Fehlens im Katalog
   nicht ersetzt oder abgelehnt. Ein fehlender/veralteter Katalog verhindert
   die Eingabe nicht. Katalog- und Benchmarkstatus stehen getrennt unter
   **LLM & Kosten**. Vorhandene Verbindungstests und Speicherrechte bleiben
   erforderlich. [Bedienung und Grenzen](DASHBOARD.md#freie-modelleingabe-und-optionale-vorschläge).
   Per-Task-Overrides liegen ausschließlich in `config/llm/defaults.json`.
   `config/llm/providers.json` ist nur der Provider-/Key-Metadatenkatalog und
   ueberschreibt weder Provider noch Modell zur Laufzeit. Die vollstaendige
   Prioritaet steht in `docs/README_technical.md` unter
   *LLM-Konfiguration: Zustaendigkeit und Prioritaet*.
   Im exklusiven Dashboard-Konfigurationsmodus bleibt eine Bearbeitung zunächst
   Entwurf. Erst „Übernehmen und Betrieb fortsetzen“ prüft, speichert und tauscht die vollständig
   vorbereitete Adapterkette ohne Dienstneustart. Solange ein Vorgang läuft
   oder fortsetzbar wartet, ist der Moduseintritt gesperrt. Direkte Änderungen
   außerhalb dieses Modus sind kein Hot-Reload; die Erstinstallation behält
   den getrennten Setup-/Produktionsstart.

   Der optionale Kostenhinweis liegt im selben Taskblock:
   `cost_advisory_enabled` schaltet ausschließlich die Anzeige, und
   `overqualification_margin_ratio` setzt die relative Marge auf die
   taskbezogene Benchmarkschwelle (ausgeliefert `0.20`). Bei Schwelle 50 wird
   damit ab 60 `überqualifiziert` angezeigt. Schreiben ist nur im expliziten
   D08-Konfigurationsmodus erlaubt. Der Hinweis ändert weder Modell noch
   Routing, Budget oder Freigabe.

4. **Verifizieren:** im Dashboard (Tab *LLM & Kosten*) zeigt der API-Key-Status
   `configured`, und **Test-Connection** prüft Erreichbarkeit (+ Guthaben bei
   OpenRouter). Lokale Modelle (Ollama) sollten ≥ 7B sein — der Quality-Tab warnt
   bei kleineren (`config.llm.min_local_model_params_b`).
   Für OpenRouter zeigt der Taskeditor `keine Daten`, `unterqualifiziert`,
   `geeignet` oder `überqualifiziert` nur aus dem passenden Benchmarkindex.
   Ein günstigerer Kandidat erscheint nur bei frischer gemeinsamer
   Preis-/Benchmarkgeneration, positiver Prompt-/Completionpreisgrundlage und
   strikter Pareto-Dominanz beider Preisachsen. Kreuzende Preise, zusätzliche
   Preisbestandteile oder ungeeignete Modelle erzeugen keinen Vorschlag. Ein
   vorhandener Cache vor Schema 3 muss zuerst mit `samuel refresh-pricing`
   erneuert werden; sein Inhalt wird nicht still als vergleichbar behandelt.

---

## 6. Verifikation

Vor einem frischen Qualification- oder Release-Lauf gilt zusätzlich der
selektive Operatorpreflight aus den
[Operating Rules](OPERATING_RULES.md#qualification-operatorpreflight-vor-der-ersten-wirkung).
Er übernimmt nur einzeln benannte Pflichtwerte aus der geschützten
Operatorquelle und meldet secretfrei Präsenz, Ziel sowie
`stored_effective=match|mismatch|not_applicable`. `missing` und `mismatch`
blockieren vor Initialisierung, erstem Auditwrite, Providerprobe oder Planning. Der
frische Projektcheckout muss die kanonische Ziel-`origin` und den erwarteten
Base-/Seed-Commit zeigen; lokale Transfer-Remotes werden vor Runtimebeginn
ersetzt. Dies ist ein Betriebsvertrag für den konkreten Subject und keine neue
Produkt-Configpriorität (#843, #845).

```bash
samuel doctor     # SCM-Konfig + Live-Verbindung, LLM-Provider, Security-Keys,
                  #   Produktversion + Voll-SHA, Branch-Protection, Verzeichnisse,
                  #   Default-Configs, PROJECT_ROOT und TEST-Runner — mit Fixes.
samuel health     # aktiver technischer Check plus getrennte Workflow-Readiness
samuel audit verify  # separate Qualification der Audit-HMAC-Kette
```

`doctor` fasst seine bisherigen Fachprüfungen mit `✅ N  ⚠️ N  ❌ N` zusammen;
danach folgt die separate informative Webhook-Diagnose. Kein `❌` belegt nur die darin
ausgeführten Operator-/Repositoryprüfungen. Es ersetzt weder eine externe
Provider-Liveprobe noch Audit- oder Release-Qualification. Die Webhook-Zeile
prüft nur, ob `SLICE_HMAC_KEY` konfiguriert ist. Sie beweist weder die
Signaturprüfung einer empfangenen Nachricht noch eine native SCM-Delivery.

`doctor` und `health` prüfen Produkt-/Buildidentität, lokale Pfade und
Dateisystem, wirksame Konfiguration, vorhandene Runtimecredentials,
SCM-Erreichbarkeit sowie — nur bei lesbarem Branchschutz-Endpunkt — dessen Regel.
Health bewertet effektive LLM-Routen ohne einen kostenpflichtigen Completion-
Aufruf. Deshalb bleibt `operational_readiness=unknown`, bis eine passende
Liveprobe vorliegt; der Dashboard-Button **Test-Connection** ist weiterhin der
getrennte Providercheck und erteilt keine Workflowauthority. Doctor- und
Auditbefunde werden im vorhandenen State instanzgebunden projiziert. Nach
einer Stunde oder einem Restore sind sie `stale`; fehlende Daten werden nie
grün. `/api/v1/dashboard/health` und der Viewerstatus lesen diese Projektion
ohne Providerzugriff. `/api/v1/dashboard/self_check` startet aktive Probes und
benötigt die Permission `RUN_PROVIDER_PROBES`.
Nicht automatisch beweisbar sind Package-Owner-Mitgliedschaft und
Publishrecht vor dem externen Registry-Preflight, zukünftige Tokenrotation,
Firewall-/TLS-Konfiguration, die Zustellung eines noch nicht gesendeten
Webhooks, Schutz des Host-Credential-Stores und menschliche Freigabeidentität.
Diese Punkte bestätigt der Betreiber auf der jeweiligen Plattform; ein grüner
Doctor erteilt keine fremde Plattformautorität.

Der Doctor führt keinen Candidate-Test aus. Er verwendet dieselbe
Runnerauflösung wie Planning und Gate 11: `test_cmd` vor Projektmarker, danach
kein Fallback. Er prüft, ob Binary beziehungsweise das mit dem aktiven Python
adressierte Modul vorhanden ist, und zeigt die passende Selektorform. Ein
konkreter Plan wird anschließend nochmals gegen diese Runnerart geprüft; ein
unvereinbarer `[TEST]`-Selektor blockiert vor `PlanPosted`.

---

## 7. Gitea-/GitHub-Webhook (empfohlen)

Damit Live-Aktivität (Issues/PRs/Kommentare) und Trigger ohne Polling ankommen:

- **Ziel-URL:** `http://<samuel-host>:<port>/api/v1/webhook`
- **Secret:** der Wert von `SLICE_HMAC_KEY` aus der `.env` (HMAC-validiert; eine
  ungültige Signatur löst ein `TamperDetected`-Audit-Event aus).
- **Events:** Issues, Issue-Comments, Pull-Requests, Push.

S.A.M.U.E.L. prüft die Signatur vor dem Event-Mapping gegen die unveränderten
HTTP-Request-Bytes. Für native Gitea-Webhooks ist
`X-Gitea-Signature` exakt der kleingeschriebene, unpräfixierte
64-stellige HMAC-SHA256-Hexdigest. Für GitHub bleibt
`X-Hub-Signature-256: sha256=<digest>` der getrennte Vertrag. Fehlende,
falsch formatierte oder inhaltlich falsche Signaturen werden abgewiesen.

Native Gitea-Labeländerungen werden über `X-Gitea-Event: issues` und
`X-Gitea-Event-Type: issue_label` ausgewertet. Eine Planfreigabe verlangt
`action: label_updated`. Da Gitea 1.27.2 im nativen Payload nur den
Issue-Post-State und kein Label-Delta liefert, dient der signierte Request als
authentisierter Trigger: S.A.M.U.E.L. liest anschließend die providerseitige
Issue-Timeline über den vorhandenen SCM-Port. Exakt ein Labelereignis muss mit
`issue.updated_at` korrelieren und `status:approved` als menschliches ADD nach
dem aktiven Plan ausweisen. Actor, Repository, Issue, Plan, Contract und
`X-Gitea-Delivery` werden gebunden. Fehlende, mehrdeutige, stale oder
widersprüchliche Timeline-Evidence bleibt fail-closed; ein bloß im Post-State
vorhandenes `status:approved` erteilt keine Authority. Der persistierte
Authority-Transport bleibt `signed_webhook`, nicht Polling.

Gitea erlaubt Webhookziele standardmäßig nur über seine
`[webhook].ALLOWED_HOST_LIST`. Liegt S.A.M.U.E.L. auf einer privaten Adresse,
muss der Gitea-Administrator genau den benötigten Zielhost beziehungsweise
das kleinste passende CIDR ergänzen und Gitea kontrolliert neu starten. Die
pauschalen Werte `private` oder `*` sind für diese Freigabe unnötig weit.
Anschließend muss eine native NON-GOLDEN-Testdelivery aus demselben
Gitea-Ausführungskontext den HTTP-Ingress erreichen.

Ohne Webhook funktioniert SAMUEL trotzdem via `samuel watch` (Polling). Der
Activity-Tab im Dashboard speist sich aus den Webhook-Events.

---

### Webhook-Diagnose ohne neue Startsperre (#905)

Unter **Settings/Konfiguration → Webhook-Diagnose** und **Einrichtung →
Webhook-Diagnose (wirksame Konfiguration)** stehen getrennte Befunde für den
Signaturschlüssel, gelesene Hook-Metadaten, Ingress-Empfang, Signaturprüfung,
Event-Verarbeitung und native Zustellung. Jede Zeile erklärt den nächsten
Prüfschritt. Das bloße Öffnen oder Aktualisieren liest nur den Prozessspeicher.

**SCM-Hook-Metadaten lesen** fragt ausdrücklich die erste Seite mit höchstens
50 Hooks des beim Prozessstart konfigurierten Repositorys ab. Es verwendet das
vorhandene Runtime-Credential, keine neu angeforderten Secrets. Angezeigt werden
Aktivierung, Payload-Typ, JSON-Format, Ziel und fehlende Ereignisse. Der
Repository-Operator ordnet das Ziel der tatsächlichen Samuel-Instanz zu; ein
passender Pfad allein beweist diese Zuordnung nicht. Bei verweigertem Read
bleibt das erforderliche Mindestrecht unbekannt; gezielt die vorhandene
SCM-Berechtigungsdiagnose prüfen, keine pauschale Botrechte-Erweiterung.
Gitea benötigt zusätzlich zur Gruppe Issues auch Labeländerungen
(`issue_label`); der lesende Check erwartet `issues`, `issue_label`,
`issue_comment`, `pull_request` und `push`. GitHub verwendet `issues`,
`issue_comment`, `pull_request` und `push`.

Ein privates/lokales IP-Ziel wird ohne DNS-Auflösung erkannt. Bei Hostnamen
bleibt die tatsächliche Netzzuordnung unbekannt. Der Hinweis nennt Giteas
`[webhook].ALLOWED_HOST_LIST`; der Operator prüft den einzelnen benötigten Host,
DNS, TLS und Firewall. Die Diagnose kontaktiert das Webhookziel nicht, ändert
keine Hook-/Serverkonfiguration und sendet keinen Testdispatch.

`samuel doctor` zeigt dieselben Diagnosegrenzen in einem eigenen informativen
Abschnitt. **`samuel doctor --webhook`** liest zusätzlich die Hook-Metadaten.
Der optionale Branchschutz-Prüfertoken wird dafür nicht verwendet. Die neuen
Webhookmeldungen ändern weder den Doctor-Exitcode und seine bisherigen
Qualification-Zähler noch Workflowstarts oder bestehende Freigabeprüfungen.

Empfangsbeobachtungen gehören ausschließlich zum laufenden Dashboardprozess;
Doctor verbindet sich nicht mit diesem Receiver. Je Stufe wird nur die letzte
Beobachtung für den konfigurierten Provider gezeigt. Verschiedene Stufen können
verschiedene Requests betreffen. Nach einer Stunde oder bei einer Zeit in der
Zukunft gilt ein Befund als `stale`; nach Neustart fehlt er wieder. Das ist
keine dauerhafte Zustellhistorie und kein neuer Evidence-Store.

**Native Zustellung bleibt in dieser Diagnose `not_proven`.** Auch ein
synthetisch signierter Request kann Signatur und Empfang bestätigen. Es gibt
keinen automatischen Import historischer Qualification-Receipts und keinen
Gesamt-READY-Status. Eine extern bereits belegte Zustellung wird dadurch nicht
widerrufen: ihr Nachweis bleibt an Installation, Zeitpunkt und Subject gebunden.
Für die reale Abnahme SCM-Zustellprotokoll und Receiver-Logs derselben Delivery
abgleichen; Signatur, Mapping und menschliche Freigabe getrennt bewerten.
Aktive Testzustellungen ausschließlich im dafür freigegebenen isolierten
Testziel ausführen. Ein Hook-Test auf einem belegten Repository kann einen
Issue-Scan auslösen. Die gemeinsame Installationsabnahme bleibt #962/#994;
die gemeinsame passive Übersicht ist in #921 umgesetzt, ohne neue Startsperre.

### Betriebsdiagnose und nächste Schritte (#921)

Im Dashboard **Konfig → Betriebsdiagnose** lesen Operator/Auditor vorhandene
Health-, Projekt-, Doctor-, Audit-, Konfigurations- und Webhookbefunde zusammen.
**Vorhandene Befunde neu laden** ist passiv; es erneuert keine Evidence.
Quelle, Zeitpunkt, Aktualität und konkrete Behebung stehen bei jeder Zeile.
Eine fehlende/alte Prüfung gilt nicht als bestanden, ein vergangener Fehler
nicht als behoben. Es gibt keine zusätzliche Startprüfung oder globale Freigabe.

Bei unbekanntem Health-/Providerstatus zuerst Konfiguration und vorhandene
Fehlermeldung prüfen; bei Bedarf `samuel health` beziehungsweise den berechtigten
aktiven Self-Check auslösen. Diese Fachprüfungen können externe Systeme kontaktieren.
`samuel doctor` liefert die konkreten Installations-/Runner-/Credentialpräsenz-
und Branchschutzbefunde; sein gespeichertes Gesamtergebnis ersetzt diese Details
nicht. `samuel audit verify` prüft die Kette getrennt vom Audit-Schreibpfad.
Alle Befehle müssen im Kontext derselben Installation ausgeführt werden.

Gespeicherte/wirksame Konfigurationsabweichungen zuerst im vorgesehenen
Wartungsablauf klären, nötigenfalls neu starten und anschließend Fachprüfungen
wiederholen. Der bestehende Konfigvergleich schließt Secret-Umgebung aus;
die Übersicht zeigt keine Schlüsselwerte oder Konfigurationsdigests.
Details und Statusgrenzen: [Dashboard-Bedienung](DASHBOARD.md#gemeinsame-betriebsdiagnose-921).
Reale Installationsabnahme bleibt #962/#994, unabhängig von automatisierten
HTTP-/Regressionsprüfungen. Bestehende Workflow-, Health-, Doctor-Exit- und
Qualification-Verträge gelten unverändert.

## 8. Verbindlich: nativer Schutz des Release-Branches

Für einen freigabefähigen Gitea-Betrieb ist die native Branch-Protection die
einzige maßgebliche Merge-Policy. Für den Default-Branch (`main`) muss der
Repository-Administrator folgende Regel setzen:

- direkte Pushes deaktiviert (`enable_push=false`), ohne User-, Team- oder
  Deploy-Key-Ausnahmen;
- Force-Push deaktiviert, ohne Allowlist;
- Statuschecks aktiviert und exakt der in
  `SCM_REQUIRED_STATUS_CONTEXT` konfigurierte Check erforderlich. Fehlt die
  Variable, wird der sichtbar gemeldete ausgelieferte Default
  `CI / lint-and-test (pull_request)` verwendet;
- Admin-Override beim Merge blockiert (`block_admin_merge_override=true`).

Damit darf niemand — auch nicht der S.A.M.U.E.L.-Bot oder ein Administrator —
direkt nach `main` pushen. Nutzer mit Merge-Recht dürfen ausschließlich einen
PR mergen, dessen aktueller Head den exakten Required Check erfolgreich
bestanden hat. Fehlende, wartende, fehlgeschlagene oder nur für einen älteren
Head vorhandene Ergebnisse blockieren den Merge. Branch-Löschung und
Force-Push werden von derselben nativen Regel abgelehnt.

`samuel setup --non-interactive` und die Dashboard-Ersteinrichtung schreiben genau einen expliziten
Soll-Kontext. `samuel doctor` zeigt Wert und Quelle (`konfiguriert` oder
`ausgelieferter Default`), liest die Regel über die Gitea-API und verlangt
exakte Gleichheit. Ein leerer beziehungsweise mehrzeiliger Konfigurationswert,
fehlender Lesezugriff, eine fehlende Regel und jede Abweichung sind
Release-Blocker; es gibt kein Ableiten aus der beobachteten Regel, keine Liste
und keinen Wildcard-Abgleich. Ein HTTP401/403 beim Lesen belegt keinen
konkreten fehlenden Scope und allein keine Fehlkonfiguration des Runtimebots.
Der Operator prüft das betroffene Credential und den Branchschutz-Endpunkt
separat und verwendet für Doctor bei Bedarf einen kurzlebigen Prüferzugang
mit den tatsächlich benötigten minimalen Rechten. Die normalen
S.A.M.U.E.L.-Laufzeitfunktionen behalten ihre getrennten Write-Rechte; es gibt
keine pauschale Empfehlung, der Runtime Adminauthority zu geben.

Der effektive Soll-Kontext wird zusammen mit dem SCM-Provider in den
Gate-Policy-Digest aufgenommen. Eine Änderung macht ältere Gate-Evidence und
Resume-Checkpoints für die neue Policy unbrauchbar. Ob der externe
Branchschutz aktuell tatsächlich denselben Kontext erzwingt, bleibt eine
separate Live-Aussage des Doctors.

Der frühere Repository-`pre-receive`-Hook und sein Setup-Pfad wurden mit #528
abgelöst: Er konnte normale Fast-Forward-Pushes nicht blockieren und wäre neben
der nativen Regel eine zweite, abweichende Policy gewesen. Client-Hooks bleiben
ergänzende Frühsignale; `--no-verify` ändert die serverseitige Regel nicht.

### 8.1 Vorhandenen Gitea-Check advisory bewerten

`samuel evidence assess` liest genau einen bereits vorhandenen Actions-Run.
Der Aufruf startet keinen Providerlauf und verändert weder SCM noch Workflow.
Er erwartet eine JSON-Datei im bestehenden `EvaluationSubject`-Format:

```json
{
  "repository": "https://gitea.example/owner/project",
  "base_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "contract_hash": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
  "policy_version": "gates.v1",
  "policy_digest": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
}
```

```bash
samuel evidence assess --run-id 123 --attempt 1 \
  --subject subject.json --event pull_request \
  --workflow .gitea/workflows/ci.yml --json
```

Der erwartete Statuskontext stammt aus `SCM_REQUIRED_STATUS_CONTEXT`, nicht aus
der Providerantwort. Exit 0 bedeutet `advisory_qualified`; Exit 1 umfasst auch
falsche SHAs, fehlenden Kontext, Stale Evidence und Parserfehler. Das Ergebnis
wird unveränderlich im vorhandenen SQLite-Observation-Store abgelegt und ist
mit Run und Original-URL nachvollziehbar. `authority=none` sowie
`required_effect=false`, `dispatch_effect=false` und `mutation_effect=false`
gelten auch nach Restore, Migration oder einer späteren Policyänderung. Die
Ausgabe ist keine Branchschutzprüfung; dafür bleibt `samuel doctor` zuständig.

---

## 9. Starten

**Interaktiv / Daemon:**
```bash
samuel dashboard            # Web-UI + REST-API (Port aus DASHBOARD_PORT oder --port)
samuel watch                # Polling-Loop für alle gelabelten Issues
samuel watch --once         # einmal scannen (CI/Cron)
samuel run 42               # einzelnes Issue #42 durch den Workflow
```

Für Cron- und CI-Aufrufe ist `samuel watch --once` fail-closed: Exit 0 setzt
voraus, dass jeder gestartete Dispatch seinen korrelierten Erfolgsendzustand
gemeldet hat. Eine Workflowblockade, ein Abbruch oder ein fehlender Endzustand
führt zu Exit 1; gemischte Batches behalten ihre Ergebnisse pro Issue.

Der issuegebundene LLM-Pfad benötigt eine persistente Workflow-
Tokenzulassung. Das bindende Limit wird in `config/llm/defaults.json` als
positiver Integer unter `workflow_budget.token_limit` konfiguriert; der
ausgelieferte Wert ist `500000`. Eine fehlende oder ungültige Zulassung, ein
fehlender `max_tokens`-Bound oder ein ausgeschöpftes Limit blockiert vor dem
Provider. Unbekannte Usage nach Timeout oder verlorener Antwort bleibt voll
reserviert und wird auch nach Neustart nicht automatisch freigegeben.
`samuel state dump --json`, Audit und Dashboard zeigen nur Zähler, Status und
gebundene Identitäten, keine Prompts oder Antworten. Preise sind weiterhin
informative Meteringwerte und kein Geldkosten-Hardcap.

Bei einem Wildcard-Bind (`0.0.0.0`) bleibt die Bind-Information im Log
erhalten; die zusätzlich ausgegebene Dashboard-URL verwendet eine erreichbare
LAN-Adresse oder fällt auf `127.0.0.1` zurück. Ein erstes `Ctrl+C` schließt den
Server und gibt den Port frei, ein zweites Signal ist der Notausstieg.

In einer extern betriebenen D0-Umgebung darf ein bereits gültiger,
zweckgebundener Dashboardcredential über Releases hinweg erhalten bleiben.
Er wird selektiv aus der geschützten Operatorquelle übernommen, nicht neu
erzeugt oder als Produktdefault gespeichert. Der Lauf meldet secretfrei URL,
Instanz, Release, Run-ID und Stage. Qualification erfordert anschließend den
gebundenen Readback der tatsächlichen Workflow-, Approval-, Candidate-, Gate-,
CI-, Merge-, Restart-, Audit-, Health-, Readiness- und
Qualificationprojektionen; Erreichbarkeit oder HTTP 200 allein genügt nicht
(#830).

**systemd** — Unit mit echten Pfaden und dem installierten Console-Script
generieren lassen:
```bash
samuel install-service --mode watch              # Vorschau (Pfade/User/Console-Script)
sudo $(which samuel) install-service --mode watch --write   # nach /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now samuel-watch
```
`--mode dashboard` für den Dashboard-Dienst, `--name`/`--user` zum Überschreiben.
Die Unit verwendet beim Entwicklungscheckout den absoluten venv-Pfad und bei
der lokalen Releaseinstallation den geprüften stabilen
`/opt/samuel/current/bin/samuel`-Pfad. Sie bricht bei fehlendem
Console-Entry-Point bereits während der Generierung ab.
(Die mitgelieferte `samuel.service` ist nur eine Platzhalter-Vorlage.)

`agent.data_dir` ist Laufzeitstate und muss bei dauerhaftem Systemd-Betrieb auf
einem absoluten, persistenten, lokalen und für den Unit-User schreibbaren Pfad
liegen. Der SQLite-Referenzadapter weist NFS, CIFS und unbekannte Mounttypen
fail-closed zurück. Vor dem Dienststart belegen
`samuel state status --json` und `samuel state dump --json` Schema,
Dateisystem, WAL-/Vacuum-Modus und eine payloadfreie Zählersicht.
Sichere insbesondere `idempotency.json`, Auditdaten,
`samuel-state-authority.json`, checksumbenannte Legacyarchive und
`samuel-state.sqlite3`. Die aktiven Evaluation-, Quality- und Run-Historien
sowie der Authority-State liegen ab Schema v5 in der DB; alte
`evaluation_observations.json`, `quality_metrics.json`, `score_history.json`
und `eval_baselines.json` werden nach checksumgebundenem Import atomar als
`*.migrated-<sha256>` archiviert. Eine laufende WAL-Datenbank darf nicht mit `cp`
gesichert werden; die produktive Adaptergrenze verwendet die SQLite Backup API
und prüft das Artefakt. Vor einer Rücksicherung den Dienst stoppen. Der
lokale `.samuel-state-authority.lock` ist nur ein Laufzeit-Lock und kein
Backup-Artefakt. Der
unterstützte Restore erfordert einen gestoppten Watch-/Dashboard-Dienst:
`samuel state restore --source <backup> --json`, anschließend
`reconcile-scan`, `reconcile-status`, erforderliche begründete
`reconcile-classify`-Entscheidungen und `reconcile-complete`. Bis zum
vollständigen Abschluss bleiben Healing und Resume blockiert. Ein zweiter
Restore verlangt bei offener Operation deren ID über
`--supersede-operation-id` und einen Grund. Vollständiges manuelles Ersetzen
von DB, Witness und Audit ist unsupported und kann die Erkennung umgehen.
DB-/Witness-/Sentinel-Abweichungen
führen jedoch bereits in Reconcile; State-CLI, Health, Dashboard und das
gemappte `AuthorityReconcileRequired`-Ereignis machen den Zustand sichtbar,
und Healing sowie Resume bleiben blockiert. Außerhalb von Reconcile prüft der
Bootstrap offene gebundene Finalisierungs-Checkpoints automatisch; Watch
wiederholt die Prüfung vor jedem Zyklus. Vor einer manuellen Entscheidung:
`samuel resume list --json` und `inspect` lesen vorhandenen aktuellen State
ohne Bootstrap, Zielcheckout oder SCM-/LLM-Credentials. `agent.json`, State und
Lifecyclelock müssen bereits vorhanden sein; Schemafehler werden nicht
migriert und Witness-/Restore-Drift nicht repariert. SQLite kann seine
WAL-Koordinationsdateien verwenden/anlegen. Die Diagnose verändert weder
persistierte Authority noch Config, Rechte, Leases oder Git-/SCM-Zustand.
Die mutierenden Aktionen benötigen weiterhin den gültigen `PROJECT_ROOT`
mit lokaler Git-Zielbindung (im Container den registrierten Projektmount,
nicht `/app`) und ihre bestehenden Authority-/Lockprüfungen. Danach bei
entsprechender Bindung `attempt`/`resume` oder ein
begründetes `abandon` und `cleanup`. Resume rekonstruiert keine LLM-Runde und
setzt keinen fremden oder schmutzigen Git-Zustand zurück.
`bound_healing_attempts.json` wird beim Bootstrap transaktional
importiert und checksumbenannt archiviert. DB, Witness und Legacyarchive
werden standardmäßig nicht gelöscht oder rotiert. Restore/Reconcile (5a),
der kategorieweise Dry-Run-Vertrag (5b) und das deaktiviert ausgelieferte
5c-Ausführungsfundament sind vorhanden. `samuel retention dry-run --json`
zeigt Katalog, Fristen,
UTC-Cutoffs, Schutzgründe und Klassifikation. `retention approve` bindet eine
Kategorieprüfung an ihre aktuellen Digests, autorisiert aber weiterhin keine
Löschung. Alle ausgelieferten Kategorien sind `report_only`, der globale Stop
ist aktiv und es gibt keinen Scheduler. `activate` und `execute` sind nur für
eine separat auf `enforce` konfigurierte, allowlist-basierte Kategorie mit
demselben `--plan-digest`, `--cutoff-utc` und einem Operatorgrund zulässig;
die Aktivierung bindet den Cutoff an ihre serverseitige Grantzeit. Zu junge
Cutoffs, fehlende migrierte Grantbindung sowie Katalog-/Klassifikationsdrift
blockieren. Ein vorhandener identitätsgeprüfter Receipt bleibt als historische
Evidence lesbar und löst keine erneute Löschung aus;
`pause`, `unpause` und `suspend` sind ebenfalls explizite Operatoraktionen.
Der Dashboard-Status zeigt dieselben begrenzten Authoritydaten passiv; er
aktiviert und vollzieht keine Kategorie.
`retention backup` erzeugt über die SQLite Backup API ein
registriertes Artefakt unter `config/privacy.json::managed_backup_dir`.
Externe Kopien außerhalb dieses Verzeichnisses bleiben vollständig
Betreiberverantwortung. Vor kürzerer Aufbewahrung von Scoreableitungen steht
`samuel retention replay-scores --json` als event- und EWMA-freier
Rekonstruktionspfad bereit.

`agent.workspace.work_dir` ist davon getrennt. Der ausgelieferte relative Wert
`../samuel-workspaces` wird neben dem Installationsroot aufgelöst und muss für
den Unit-User auf einem lokalen Dateisystem schreibbar sein. Vollständige
Checkouts und Quarantänen gehören nicht ins State-Backup. Vor Start und nach
einem harten Abbruch `samuel workspace list --json` prüfen; `prune` entfernt
nur terminale Einträge. Die ausgelieferte Operatorfrist beträgt 168 Stunden,
löscht aber keine Evidence automatisch. Nach dokumentierter Prüfung überführt
nur `workspace discard ID --reason ...` eine Quarantäne in den terminalen
Zustand. Ist die Quarantäne- oder Freiplatzgrenze erreicht,
startet kein neuer Candidate. Quarantänen zuerst inspizieren und nie durch ein
pauschales Hard-Reset oder Löschen als vermeintliche Reparatur entfernen.

### 9.1 OCI-Erstinstallation auf einem leeren Docker-Host (#970)

Die folgenden Angaben beschreiben die internen Installationskits und ihre damaligen Prüfungen. Für das öffentliche Release gilt die [Installationsanleitung](INSTALL.md#öffentliche-alpha-auf-einem-docker-host-installieren).

<!-- oci-first-install:start -->

**#1090-Teilstand:** Der neue TUF-Bezug im vorhandenen Release-CLI ist ein
technischer Baustein des nachfolgend beschriebenen internen Bootstrap-Einstiegs.
`fetch --release` bezieht ein signiertes Manifest und alle darin gebundenen
Artefakte mit unabhängiger TUF- und Manifestprüfung; er installiert nichts.
Er benötigt ausdrücklich bereitgestellte Repository- und Root-Eingaben und
belegt weder deren authentisierte Erstübergabe noch eine offizielle
Downloadadresse. [Bezugsvertrag und offene Nachweise](CONTAINER_RELEASE_OPERATIONS.md#tuf-artefaktbezug-im-vorhandenen-release-cli).
Die folgende bestehende Alpha-Anleitung bleibt bis zum eigenen Ersatznachweis
erhalten; der TUF-Unterbefehl ist kein zusätzlicher normaler Konfigurationsschritt.

Der offizielle OCI-Installer verwendet ausschließlich `container.reference`
aus dem gewählten `release-manifest.json`. Unterstützt ist Linux/amd64 mit
Docker Engine mindestens 26 und dem Compose-Plugin mindestens 2.26 (v2 oder v5).
Der reale Clean-Install-Nachweis wird auf einer frischen Ubuntu-Maschine geführt.
Der CLI-Healthcheck hat weiterhin ein begrenztes Zeitbudget von 60 Sekunden,
damit auch kalte Starts auf langsameren Hosts vollständig geprüft werden.
Sein Shellaufruf ersetzt sich mit `exec` durch den Prüfer. Bei einem
Docker-Timeout wird dadurch der Prüfer selbst beendet; es bleiben keine
weiterlaufenden Healthcheck-Kindprozesse eines beendeten Wrappers zurück.
Docker und Compose vorher nach der [offiziellen Ubuntu-Anleitung](https://docs.docker.com/engine/install/ubuntu/)
installieren. Der Bootstrap installiert oder konfiguriert Docker nicht selbst.
Eine private Registry benötigt einen bestehenden Docker-Login; Credentials
mit `docker login --password-stdin` oder dem Docker Credential Store provisionieren.
Bei einer HTTP-Registry ist deren explizite Freigabe im Docker-Daemon Betreiberaufgabe.

<a id="interner-bootstrap-einstieg-distribution-und-erstvertrauen-noch-offen"></a>

### Historischer Bootstrap für interne Installationskits

Ein **zuvor unabhängig geprüftes**, versioniertes Bootstrap-Paket kann den
vorhandenen Installer, dessen Helper, `bootstrap-profile.json` und
`trusted-root.json` enthalten. Seine tatsächliche authentisierte Übergabe und
die unabhängige Root-Bindung haben den Status NOT_VERIFIED. Die Erstübergabe
gehört seit der Betreiberentscheidung vom 19.11.2026 nicht mehr zu den
Abschlusskriterien von #1090. Die spätere GitHub-Distribution wurde in #1140 separat geprüft.
Dieser Abschnitt dokumentiert den damaligen internen Bootstrap. Keine hier erfundene URL,
kein `curl | bash` und kein Hash aus derselben ungeprüften Quelle ersetzen
[die Erstvertrauensprüfung](CONTAINER_RELEASE_OPERATIONS.md#bootstrap-vertrauen-und-relevante-transportgrenzen).

Nach qualifizierter Übergabe und mit den oben genannten Docker-/Registry-
Voraussetzungen beginnt die Installation mit genau einem Aufruf:

```bash
sudo bash /pfad/zum/geprüften-bootstrap/tools/samuel-container install
```

Der Installer findet das mitgelieferte Profil selbst. Ein ausdrückliches
`--bootstrap-profile FILE` ist für Operatorwerkzeuge möglich. Normale Anwender
stellen weder Manifest, Artefakte noch Prüfsummen zusammen. Der Aufruf prüft
Hostvoraussetzungen, bezieht alle signierten Releaseeingaben, prüft und entpackt
das gebundene Kit und übergibt an dessen bestehenden Installationsweg. Der
kurzlebige Prüflauf im unveränderlich gebundenen Produktimage besitzt keinen
Docker-Socket, keine Capabilities und nur den privaten Releasecache als
schreibbaren Hostmount; Python wird auf dem Host nicht vorausgesetzt.

Der erste Imagebezug einschließlich Entpacken kann mehrere Minuten dauern;
der Installer kündigt diesen Schritt an. Nach erfolgreicher Installation
zeigt er abschließend den kurzen Startaufruf desselben Bootstrap-Pakets.
Dieser ermittelt die bereits geprüften Releaseeingaben selbst; die längere
interne Installerform ist kein zusätzlicher normaler Bedienungsschritt.

Im selben Terminal folgen Administratorname (Vorgabe `admin`), Inventur- und
Cutoverbestätigung sowie zweimal verdeckte Passworteingabe. Danach das
Setup-Dashboard öffnen und anmelden. Administrator- und Operatorrolle bleiben
getrennt: Die allgemeine Einrichtung mit Administratorrechten speichern;
für spätere Workflowaktionen erforderliche Operatorberechtigungen über die
vorhandene Identitätsverwaltung vergeben. Die bestehende Erstaufnahme erteilt keine Workflowfreigabe.
Abschließend ist **ein weiterer ausdrücklicher Operatoraufruf für Production**
erforderlich. Dasselbe aufbewahrte, geprüfte Bootstrap-Paket kann die geschützte
Installationsquittung und das bereits vorhandene Releasekit selbst auswählen:

```bash
sudo bash /pfad/zum/geprüften-bootstrap/tools/samuel-container start
```

Für eine Installation unter einem abweichenden Präfix denselben kanonischen
`--root /absoluter/pfad` wie bei der Installation ergänzen. Port und Compose-
Projekt stammen aus der Quittung; keine neuen `--port`-/`--project`-Werte angeben.
Der vorhandene Installer prüft Image, Manifest, Artefakte, Layout und Zulassung
erneut und verlangt eine ausstehende Projektfreigabe weiterhin ausdrücklich.
Der vollständig nach `install` ausgegebene Startbefehl bleibt als expliziter
Operatorweg gültig. Das ist kein shellfreier Dashboardbetrieb.

Für eine spätere allgemeine Konfigurationssitzung genügt entsprechend `setup`
mit demselben Bootstrap-Paket und Installationspräfix; anschließend wieder
`start`. LLM-/Promptänderungen nutzen weiterhin die vorhandene ConfigurationSession
und benötigen keinen solchen Moduswechsel. Die Kurzform lädt keine neuen
Release-Metadaten, entpackt kein neues Kit und repariert keinen Cache. Fehlen
Quittung/Cache oder sind Bytes, Ownership beziehungsweise Bindungen verändert,
bricht sie vor dem Wartungsaufruf ab. Der bestehende vollständige Operatorweg
bleibt für historische Installationen ohne Bootstrapcache und für Recovery
erhalten. Der gebundene Prüfer und das installierte Image müssen über den
bestehenden Docker-/Registryweg verfügbar sein; keine neue Offlinezusage.

`--root`, `--port` und `--project` bleiben für getrennte Installationen verfügbar
und werden einschließlich aller verifizierten Dateipfade in den Startbefehl
übernommen. Der private Cache liegt unter `<root>/srv/samuel/release-cache`;
Metadaten und gebundene Installer für Folgeaufrufe erhalten. Die ursprünglichen
Releasequellen werden automatisch für spätere Vorbereitung und unabhängige
Operatorprüfung getrennt erhalten; kein zusätzlicher CLI-Schritt. Ein für die
Versionsauswahl benötigtes Targettemplate stammt aus dem Betreiberpaket, nicht
aus einer angenommenen Downloadadresse. [Quelldaten und Nachweisgrenze](CONTAINER_RELEASE_OPERATIONS.md#tuf-artefaktbezug-im-vorhandenen-release-cli).
Der äußere Cache
bleibt `0700`; im daraus read-only eingebundenen veröffentlichten Kit sind
Verzeichnisse `0755` und Dateien `0644`, damit der nicht privilegierte
Imagebenutzer die Deliveryprüfung lesen kann. Abweichende Rechte bestehender
Kits werden abgewiesen und nicht still repariert. Nach einem
Bezugsfehler startet keine Installation; bereits geprüfte Cachedateien bleiben
bestehen. Fehler bei Initialisierung oder Identityaufnahme folgen den unten
beschriebenen bestehenden Diagnose-/Recoverywegen, nicht einer automatischen
Rücksetzung. Ein späterer erneuter `install` ersetzt keine bestehende Instanz.
Bei Folgeaufrufen mit lokalem Manifest wird dessen gebundene SHA-256 vor
dem ersten Docker-Aufruf geprüft. Eine Abweichung stoppt auch dann eindeutig,
wenn der Docker-Daemon nicht erreichbar ist; Installationspfade bleiben unberührt.
Bestandsaufrufe (`setup`, `start`, `doctor`, `project`, `toolchain`) legen keine
fehlenden Installationsverzeichnisse an. Ihre interne Bestandsprüfung mountet
alle fünf Installationswurzeln ausschließlich lesend und verlangt das vorhandene
Installationsreceipt. Fehlende oder widersprüchliche Bestandsteile benötigen
Diagnose über den bestehenden Operatorweg; sie lösen keine Neuinstallation aus.

Diese Funktionsprüfung ersetzt weder die unabhängige authentisierte Übergabe
noch eine vollständige reale Docker-/Browserabnahme. Das Paket muss erst mit
konkretem Produktimage und Übergabeweg qualifiziert werden. Bis zum erfolgreichen
Ersatznachweis bleibt der veröffentlichte Alphaweg erhalten:

### Projekt im Dashboard vorbereiten und Production ausdrücklich starten

Für eine frische Docker-Installation reicht das Passwort für das Dashboard-Konto `admin`. Der Installer prüft Release und Image automatisch. Im Dashboard wählst du Repository, optional den Branch und den Modellzugang. Mit **Prüfen und starten** wird das Projekt ausgecheckt und der Betrieb gestartet. Der Installer muss während der Einrichtung geöffnet bleiben. Der Dienst erhält einen festen Projektordner. Die folgenden Schritte beschreiben den gesonderten Operatorweg für einen bereits bereitgestellten Checkout.


Im erweiterten #1090-Kit kann die einzelne Projektbindung im Setupformular
vorbereitet werden: den **bereits vorhandenen** dedizierten Hostcheckout,
seinen vollständigen initialen Commit und den gewünschten Containerpfad
angeben. Repositoryidentität kommt aus der vorhandenen SCM-Prüfung. Die
unten beschriebenen Checkout-/Rechtevoraussetzungen bleiben erforderlich;
Provisionierung des Checkouts ist kein verdeckter Installationsschritt.
Das Dashboard speichert nur Vorbereitungsdaten, ohne Hostprüfung, Mount oder
`PROJECT_ROOT`-Aktivierung. Eine bestehende Bindung wird hier nicht ersetzt.
Zum Verwerfen noch unregistrierter Angaben das Hostpfadfeld leeren und speichern.

Anschließend den nach `install` ausgegebenen **einen Production-Startaufruf**
ausführen. Er zeigt Hostpfad, Containerpfad, Repository, Revision und Digest
zur ausdrücklichen Bestätigung. Nach Zulassung der Wartung liest er Vorbereitung
und aktuelle SCM-Konfiguration unabhängig nochmals, stoppt Setup, ruft die
bestehende Projektregistrierung auf und startet Production mit deren Overlay.
Ein zusätzlicher manueller Compose-Stopp oder `project`-Aufruf gehört bei diesem
Weg nicht zum erfolgreichen Ablauf. Für geprüfte Operatorautomatisierung kann
`start --approve-project SHA256` exakt die angezeigten Vorbereitungsbytes freigeben;
der Digest ist keine Dashboardfreigabe und ersetzt keine Prüfung.

Abgelehnte oder geänderte Angaben verhindern den Start. Scheitert die eigentliche
Registrierung nach dem Stopp, bleibt Wartung offen; Quelle und Ursache prüfen
und denselben Aufruf ausdrücklich wiederholen. Keine automatische Ownership-
Änderung, kein Clone, kein Workflowstart. Der bestehende separate `project`-Weg
bleibt für ältere Kits und lokale Operatorarbeit erhalten. Funktionsprüfungen
mit Docker-/SCM-Doubles sind keine reale Docker-/Browser-Gesamtabnahme.

### Releasepaket prüfen und entpacken

**Technischer Bestands-/Recoveryweg; kein zusätzlicher Schritt des #1090-Standardwegs.**
Der oben beschriebene Bootstrap übernimmt Bezug, Hashprüfung und Entpacken.
Die folgende vollständige Operatorform bleibt für a34 und ältere Kits sowie
für ausdrücklich geprüfte lokale Recovery erhalten. Auch hier muss die
Vertrauensbindung unabhängig vorliegen; ein Hash vom selben ungeprüften
HTTP-Endpunkt genügt nicht. Normale Anwender führen diese Artefaktzusammenstellung
nicht zusätzlich zum Bootstrap aus.

Für diesen gesonderten Operatorweg aus **demselben** Release bereitstellen:
`release-manifest.json`, `samuel-oci-<Version>.tar.gz`, `docker-compose.yml`
und `docker-compose.setup.yml`. Der OCI-Kit enthält den Bootstrap, Helper,
beide Compose-Dateien und diese Anleitung. Die Releasebeschreibung nennt den
Manifest-SHA-256; das verifizierte Manifest bindet Name, Größe und SHA-256 jedes
Artefakts. Vor dem Ausführen oder Entpacken Manifestprüfsumme und Kitprüfsumme
prüfen. Dazu kann ein vorhandener JSON-Viewer verwendet werden; der Installer
selbst benötigt kein Python oder jq auf dem Host.

```bash
cd /pfad/zu/heruntergeladenen/releaseassets
manifest_sha256='<veröffentlichter SHA-256 des Release-Manifests>'
installer_archive='samuel-oci-<Version>.tar.gz'
installer_sha256='<SHA-256 dieses Archivs aus dem geprüften Manifest>'
printf '%s  %s\n' "$manifest_sha256" release-manifest.json | sha256sum --check -
printf '%s  %s\n' "$installer_sha256" "$installer_archive" | sha256sum --check -
tar -xzf "$installer_archive"
sudo bash samuel-oci/tools/samuel-container install \
  --manifest "$PWD/release-manifest.json" --manifest-sha256 "$manifest_sha256" \
  --installer-archive "$PWD/$installer_archive" --compose-dir "$PWD"
```

**Optionale Administratoraufnahme im selben Installationsaufruf (#1090, AP 2):**
Bei der ersten Einrichtung kann der Operator einen eigenen Kontonamen mit `--admin-username` festlegen. Der Installer richtet persönliche Konten ein und protokolliert die Erstinstallation. Das Passwort wird zweimal verdeckt eingegeben.

Ohne interaktives Terminal wird diese Option vor Docker-/Hostaktionen
abgewiesen. Sie gilt nur für `install`; bei `start` nicht wiederholen. Die
bisherigen Aufrufe ohne diese Option bleiben unverändert, einschließlich
des getrennten expliziten Cutovers für bestehende Clients. Ältere Kits und
Images werden durch eine neue Anleitung nicht nachträglich erweitert.
Automatische Artefaktbeschaffung übernimmt nur der oben beschriebene neue
Bootstrap-Einstieg. Der [a39-Produktnachweis](status/CURRENT_PRODUCT_STATUS.md#alpha-testrelease-v200a39)
dokumentiert die Neuinstallation mit Administratoraufnahme und den Browserlauf.
Für dieses interne a39-Paket blieb die unabhängige Erstübergabe NOT_VERIFIED.

Der Installer prüft Voraussetzungen, Manifest, Version, volle Revision,
Image-Digest und Auslieferungsbindung der Compose-Dateien sowie des gesamten
entpackten Kits vor dem Anlegen der Betreiberpfade. Defaults kommen aus genau
diesem Image; Ownership wird aus dessen tatsächlichen Runtimeverzeichnissen
abgeleitet. Kurzlebige Installeraufrufe benötigen für Initialisierung und
Prüfung geschützter Hostmetadaten gezielt root; die einzelnen Prüf- und
Übernahmeschritte begrenzen Mounts und Capabilities gemäß
[Lifecycle-Vertrag](CONTAINER_RELEASE_OPERATIONS.md#1090-beta-lifecycle-auftrag).
Die Runtime läuft als der non-root Benutzer des Images. Kurzlebige Prüf-,
Setup- und Identity-Container starten keinen zusätzlichen Image-Healthcheck;
die expliziten CLI-Prüfungen sowie der Healthcheck des regulären Dienstes
bleiben aktiv.

Standardpfade sind `/etc/samuel/config`, `/etc/samuel/.env`,
`/var/lib/samuel`, `/var/log/samuel`, `/srv/samuel/workspaces` und
`/srv/samuel/backups`. Separate Log-/Backup-Bind-Mounts verwenden im Container
weiterhin `/app/data/logs` und `/app/data/backups`; das Stateformat bleibt gleich.
Die Compose-Runtime bindet intern ausdrücklich `0.0.0.0:7777`; native
`DASHBOARD_HOST`-/`DASHBOARD_PORT`-Werte aus der Konfiguration ändern diese
Containerbindung nicht. `--port` am Installer bestimmt den Hostport.
`--root /absolute/testwurzel`, `--port` und `--project` erlauben eine getrennte
Testinstanz; **dieselben Optionen bei allen folgenden Befehlen verwenden**.

### Setup abschließen und Produktion starten

Bei einer neuen Installation erzeugt die leere Pfadinitialisierung über die
bestehende gemeinsame Setupfunktion die Sicherheitskeys und speichert sie privat
in `.env`, bevor der erste auditierende Wartungsprozess startet. Das vorhandene
`samuel setup --non-interactive` bewahrt diese Schlüssel; anschließend startet das authentisierte
Setup-Dashboard. Es aktiviert keinen Workflow und führt keine LLM-Completion aus.
Die Erfolgsmeldung `setup runtime ready` erscheint erst nach Prüfung von
Version, voller Revision, Konfigurationsmodus und technischer Health.

Dies verhindert ein zunächst unsigniertes Auditsegment mit anschließendem
Schlüsselwechsel während derselben Ersteinrichtung. Bestandsaufrufe erzeugen
keine neuen Schlüssel. Vorhandene unsignierte, beschädigte oder mit einem anderen
Schlüssel gebundene Auditdateien werden nicht umgeschrieben oder neu signiert;
sie bleiben mit ihrem damaligen Nachweis und gegebenenfalls Fallbacktranskript
zur ausdrücklichen Operatorprüfung erhalten. Ein erfolgreicher Healthcheck
ersetzt keine Auditkettenprüfung.

Öffnen: `http://127.0.0.1:7777`. Auf einem entfernten Host einen SSH-Tunnel
verwenden, beispielsweise `ssh -L 7777:127.0.0.1:7777 BENUTZER@HOST`.
Nach Installation mit `--admin-username` mit diesem lokalen Konto anmelden.
Es besitzt ausschließlich die Rolle `administrator`, einschließlich der
Konfigurations- und Identityrechte. Für Betriebsaktionen, Verbindungstests
und Diagnosen im vorhandenen Identitybereich zusätzlich `operator` ausdrücklich
zuweisen; diese Rolle enthält auch die Statusansicht. `viewer` allein erlaubt
nur Statusansichten. Die erforderliche frische Authentisierung bleibt erhalten. Der Legacy-Key
ist nach dem Cutover kein Fallback. Diese UI-Schritte gehören zur
Benutzerabnahme; Administratorstatus allein erteilt keine Operatorrechte.

Der vorhandene Legacy-Modus erwartet den `SAMUEL_API_KEY` aus der geschützten
`/etc/samuel/.env`. Den Wert ausschließlich über einen geschützten Operatorweg
für den berechtigten Browser bereitstellen; der Installer und der Initialisierer geben
keine Secretwerte aus. SCM-, Provider- und Modellkonfiguration im Setup prüfen,
validieren und speichern. Auch alle effektiven LLM-Taskrouten im Abschnitt
„LLM Task Configuration“ prüfen. Offene Taskeditoren behalten ungespeicherte
Eingaben bei automatischer Aktualisierung; Änderungen ausdrücklich speichern.
Ein anderer Standardprovider entfernt keine bestehenden Task-Overrides. Für einen manuellen Test jede Taskroute ausdrücklich
auf `manual` und eine Modell-ID setzen. Die Datei ist `0600`; Bearbeitung alternativ über
einen geschützten Editor. `/etc/samuel/compose.env` enthält nur Mountpfade,
Image-Digest, Loopbackadresse, Port und Projektname.

Nach bestätigtem Setup denselben Installer ausdrücklich mit `start` aufrufen
(dieselben Installationsoptionen, aber **ohne `--admin-username`**):

Bei Kits mit der #1090-Erweiterung gibt `install` beziehungsweise `setup` nach
erfolgreicher Startprüfung den vollständigen nächsten Bash-Aufruf aus. Nach
Abschluss und Prüfung der Dashboardeinrichtung diese Zeile kopieren und
ausdrücklich ausführen. Sie enthält die geprüften absoluten Installer-, Manifest-,
Archiv- und Composepfade, Manifestdigest, Image sowie die verwendeten Root-,
Port- und Compose-Projektoptionen. Der Arbeitsordner darf wechseln; Kit und
Artefakte müssen am angegebenen Ort erhalten bleiben. Der Aufruf übernimmt
keine Passwörter, Cutover-Begründung oder erneute Administratoraufnahme.

Die Ausführung erfolgt mit denselben Hostrechten. Bei einem Aufruf als root
über `sudo` wird das Präfix in der Ausgabe berücksichtigt. Die Ausgabe allein
startet nichts; der vorhandene `start`-Pfad prüft Release, Installation und
Readiness erneut. Nach fehlgeschlagenem Setupstart erscheint kein solcher
Folgeaufruf. Für ältere Kits bleibt die bisherige vollständige Form:

```bash
sudo bash samuel-oci/tools/samuel-container start \
  --manifest "$PWD/release-manifest.json" --manifest-sha256 "$manifest_sha256" \
  --installer-archive "$PWD/$installer_archive" --compose-dir "$PWD"
# start führt docker compose up --no-build --pull never aus und prüft die Runtime.
sudo docker compose --env-file /etc/samuel/compose.env \
  -f /etc/samuel/compose/docker-compose.yml exec -T samuel samuel --version
sudo docker compose --env-file /etc/samuel/compose.env \
  -f /etc/samuel/compose/docker-compose.yml exec -T samuel samuel health
```

Der `start`-Aufruf ist der notwendige separate Production-Schritt; die beiden
anschließenden Diagnosebefehle sind optionale Kontrollen. `start` selbst prüft
bereits Version, Revision, Betriebsmodus und Health. Es entsteht keine
automatische Workflowfreigabe.

Scheitert die optionale Administratoraufnahme, startet der Installer kein
Dashboard. Bereits initialisierte Verzeichnisse bleiben erhalten. Bei Fehlern
nach erfolgreichem Bootstrap den Administrator nicht erneut anlegen oder
zurücksetzen: am gestoppten System den bestehenden lokalen `identity status`-
und expliziten `identity cutover`-Pfad aus Abschnitt 4.4 verwenden. Erst nach
bestätigtem Cutover den bestehenden Setupweg fortsetzen. Das sind sichtbare
Fehler-/Recoverymaßnahmen, keine zusätzlichen Schritte des erfolgreichen
Installationswegs.

Das leere Setup prüft Erreichbarkeit, Releaseidentität und lokale Startvoraussetzungen
(Python, Git, Config, State und Authority). Vollständige technische Health kann
erst nach SCM-/Providerkonfiguration erreicht werden; `start` verlangt sie.

Nach dem Wechsel auf lokale Identitäten meldet sich der Betreiber mit seinem
lokalen Konto an. Die Startprüfung reaktiviert keinen Legacy-Key: Sie prüft den
öffentlichen Auth-Modus, Betriebsmodus des laufenden Dashboard-Prozesses und
installierte Buildidentität und verwendet `samuel health --json` im Container.
Der Health-Aufruf startet kein Auto-Resume. Im Setup müssen weiterhin Python,
Git, Config, State und Authority bestehen; Production verlangt vollständige
technische Health. Workflow-Readiness und Qualification bleiben getrennte Nachweise.

Setup bindet Config und `.env` schreibbar ein. Production importiert `.env`
beim Start und bindet Config read-only; Setupwrites werden mit
`configuration_frozen` abgelehnt. `start` ersetzt den Setupcontainer und prüft
die Produktion. Daten und Operatorquellen bleiben erhalten.

### Kontrolliertes OCI-Update und gebundene Fortsetzung (#1090)

Im Dashboard unter **Settings → Releaseupdate vorbereiten** die gewünschte
Release-ID prüfen. Versionen, deklarierte Kompatibilität, Sicherungsbedarf und
bekannte Blocker bleiben sichtbar. Danach aus demselben unabhängig geprüften
Bootstrap-Paket auf dem Docker-Host mit denselben Hostrechten ausführen:

```text
sudo bash tools/samuel-container update --target <Release-ID>
```

`tools/samuel-container` ist relativ zum Verzeichnis dieses Bootstrap-Pakets.
Alternativ dessen absoluten Skriptpfad verwenden; ein zusätzlicher Wechsel in
das Installations- oder Compose-Verzeichnis ist nicht erforderlich. Die
Dashboardanzeige kennt den lokalen Ablagepfad des Pakets nicht.

`<Release-ID>` durch die angezeigte kanonische Version ersetzen. Bei einer
Installation unter einem anderen Präfix denselben `--root` ergänzen. Keine
Releaseartefakte, Manifeste oder Prüfsummen manuell zusammenstellen. Der Aufruf
verlangt eine eigene ausdrückliche Terminalbestätigung; die Dashboardanzeige ist
keine Hostfreigabe. Er prüft unabhängig die private Releasequelle, TUF,
Installations-/Projektbindung, tatsächliche Runtimeidentität und State. Die
bestehende Wartungszulassung kontrolliert lokale und externe Workflowblocker.

Unter den bestehenden Sperren entstehen ein verwaltetes SQLite-Backup und nach
dem kontrollierten Stopp die zugehörige Dateisicherung. Der vorhandene Installer
übernimmt ausschließlich kompatible feste Releasemetadaten und startet Production.
Erst Zielversion, Revision, Image und technische Readiness schließen die Wartung.
Im erfolgreichen Updateweg sind keine separaten Dockerbefehle, kein vorheriges
`setup` und kein anschließendes manuelles `start` nötig. Der explizite
Production-Start nach der **Erstinstallation** bleibt unverändert erforderlich.
Normale LLM-/Promptänderungen bleiben im Dashboard; allgemeine Setupänderungen
verwenden weiterhin den ausdrücklich geregelten R15a-Moduswechsel.

Die erste Wartungsantwort darf bis zu drei Minuten dauern: Dazu gehören der
Compose-/Containerstart, Bootstrap, State-/SCM-Prüfungen und die angeforderte
Sicherung. Der Installer zeigt diese Wartephase an. Vor der bestätigten Aufnahme
wird die Runtime nicht gestoppt oder ersetzt. Das ist keine automatische Freigabe;
eine fehlende oder unerwartete Antwort bricht den Hostübergang weiterhin ab.

Bei Fehlern bleibt die Wartung offen. Vor Beginn werden Vorbereitungshash und
ein vollständiger Recoveryaufruf ausgegeben. Erst nach Prüfung, dass der vorherige
Operatorprozess und seine Hostaktionen beendet sind, diesen gebundenen Aufruf
oder aus dem geprüften Bootstrap-Paket folgende Form verwenden:

```text
sudo bash tools/samuel-container update --recover-update <Vorbereitungshash>
```

Auch bei einer Zeitüberschreitung der Wartungsaufnahme den tatsächlichen Zustand
prüfen: Die Runtime kann noch unverändert laufen, während die Wartung mit ihrem
Backup bereits offen ist. Die Fehlermeldung verweist für Updates auf den
gebundenen `--recover-update`-Aufruf, bei einer begonnenen Quellrestoration auf
`--restore-update`. `--recover-maintenance yes` ist kein Update-Recoverybefehl.

Auch dabei dasselbe Installationspräfix verwenden. Recovery verlangt erneut
Bestätigung, Release-/Stateprüfungen und die ursprüngliche offene Bindung. Sie
wählt kein neues Ziel und erstellt kein zweites State-Backup. Teilweise ersetzte
Metadaten dürfen nur dem alten oder dem exakt vorbereiteten Zielstand entsprechen;
fremde Änderungen werden abgewiesen. Alte Toolchain, Installer und Sicherung
bleiben erhalten. Ein bereits abgeschlossener Vorgang kann damit nicht erneut
geöffnet werden. Kein automatischer Rollback oder Restore; die bestehenden
lokalen State-/Identity-/Reconcilewege bleiben für weitergehende Fehler maßgeblich.
Dieser Updateweg benötigt den gebundenen Releasebezug und gegebenenfalls Registry-
Zugriff. Er ist kein pauschaler Offline-Recoverynachweis.

**Quellrelease nach fehlgeschlagenem Zielstart wiederherstellen:** Wenn die
Metadatenübernahme bereits begonnen hat, kann der Betreiber statt der
Vorwärtsfortsetzung ausdrücklich die ursprünglichen Releasemetadaten und das
zugehörige verwaltete State-Backup zurückspielen:

```text
sudo bash tools/samuel-container update --restore-update <Vorbereitungshash>
```

Dasselbe geprüfte Bootstrap-Paket und Installationspräfix verwenden. Die eigene
Restorebestätigung ersetzt keine Release-, Sicherungs- oder Stateprüfung. Der
Aufruf verlangt den ursprünglich offenen Vorgang, stoppt die Runtime unter den
bestehenden Wartungssperren und verwendet den vorhandenen `state restore`-Befehl
im gebundenen Quellimage. Er ersetzt nur die festen, beim Update veränderten
Releasemetadaten. Unbekannte Änderungen, veränderte Archive oder unpassende
Sicherungen werden abgewiesen. Auditdateien, externe Codebasis, Workspaces,
Credentials und der aktuelle Authority-Witness werden nicht aus dem Archiv
überschrieben; die beim Update geprüfte Releasequellenbindung bleibt erhalten.

**Danach bleibt Production gestoppt.** State-Restore erzeugt eine neue Instanz-
und Epoch-Bindung, setzt Reconcile und Retention-STOP und widerruft alte lokale
Sitzungen und Tokens. Lokale Identitäten benötigen gegebenenfalls den bestehenden
Recoveryweg. Die Ausgabe nennt den vollständigen lokalen State-Diagnoseaufruf
und den späteren Startaufruf des Quellreleases. Zuerst `reconcile-scan`, Befunde
prüfen und gegebenenfalls begründet klassifizieren, dann `reconcile-complete`;
keine Befunde pauschal freigeben. Erst nach abgeschlossenem Abgleich und nötiger
Identity-Recovery ausdrücklich Production starten. Die vorhandenen
[State-/Reconcilebefehle](README_technical.md#16-cli-reference) bleiben maßgeblich.
Diese zusätzlichen Schritte gehören zum Fehlerfall und sind keine Schritte
des erfolgreichen Updates. Der Restore startet keinen Workflow und erklärt
alte Freigaben nicht allein durch ihre Wiederherstellung wieder für gültig.

**OCI-Identity-Recovery ist ein zusätzlicher ausdrücklicher Fehlerfallschritt.**
Im ausgegebenen lokalen Diagnoseaufruf den vollständigen Compose-Präfix samt
Quellrelease und `restore-compose.json` erhalten. Für die Identityprüfung nur
`state status --json` durch `identity status --json` ersetzen. Bei
`recovery_pending` zuerst die oben beschriebene Reconciliation abschließen und
anschließend den bestehenden [Identity-Recoveryvertrag](#44-lokale-dashboard-identitäten-und-cutover)
anwenden:

- Eine reguläre private Passwortdatei auf dem Host bereitstellen. Sie muss Modus
  `0600` oder strenger und UID/GID der wiederhergestellten Installation besitzen
  (Felder `uid`/`gid` in deren `.container-install.json`). Das Passwort selbst gehört
  nicht in Argumentwerte, Logs oder die Releasekonfiguration.
- Im ausgegebenen Compose-Aufruf nach `run --rm --no-deps -T` und vor dem
  Servicenamen `samuel` beispielsweise
  `--volume /run/samuel-recovery-password:/run/secrets/recovery-password:ro`
  ergänzen; den Hostpfad an die tatsächlich bereitgestellte Datei anpassen.
  Als CLI-Aktion `identity recover --username admin --password-file
  /run/secrets/recovery-password --reason "geprüfter Restore und Reconcile" --json`
  verwenden. Kein allgemeiner Hostmount und kein Docker-Socket im Container.
- Mit demselben Diagnoseaufruf `identity status --json` und `state status --json`
  prüfen. Erst nach abgeschlossenem Reconcile und aktiver Identität den separat
  ausgegebenen Quellstart ausführen. Die private Recoverydatei anschließend sicher
  entfernen. Alte Sitzungen und Tokens bleiben widerrufen; der wiederhergestellte
  Administrator erhält nicht stillschweigend Operatorrechte. Erforderliche Rollen
  nach erneuter Anmeldung ausdrücklich im Dashboard zuweisen.

Diese Passwortbereitstellung, lokalen Prüfungen und Rollenvergabe gehören zur
Recovery einer lokalen Identität. Sie sind weder zusätzliche Schritte der
normalen Erstinstallation noch ein vollständig shellfreier Wiederherstellungsweg.

Nach einem Abbruch vor dem State-Restore kann derselbe Restoreaufruf erneut
geprüft werden. Nach begonnenem State-Restore dessen vorhandenen Status und
gegebenenfalls die ausdrücklich begründete Ablösung einer unterbrochenen
Restoreoperation verwenden; nicht erneut den alten Updatevorgang aktivieren.
Der private Captureordner unter `release-cache/update-captures` erhält
`restore-pending.json` und das feste `restore-compose.json` für den lokalen
Einmalaufruf ohne geerbten Healthcheck. Diese Dateien sind Recoveryartefakte,
keine Freigabe oder Abschlussquittung. Ein funktionierendes Dashboard ist für
diesen Weg nicht erforderlich. Verlust beliebiger Hostdateien, ein nicht mehr
ausführbares Installerimage oder fehlender Releasebezug sind damit nicht
pauschal als wiederherstellbar nachgewiesen.

Die Ausgabe eines Befehls, bestandene Regressionen oder lokale Fixturetests
ersetzen weder eine erfolgreiche Wiederherstellung aus der Neuinstallation noch den
Nachweis des authentisierten Bootstrap-Übergabewegs. Für die spätere Distribution
über GitHub führt #1140 die Qualifikation des HTTPS-Kanals und der initialen
Root. [Verbindlicher Umfang und Vertrauensgrenze](CONTAINER_RELEASE_OPERATIONS.md#bootstrap-vertrauen-und-relevante-transportgrenzen)

### Wiederholung, Fehler und Rekonfiguration

Ein zweites `install` verweigert eine bereits vorbereitete Installation.
`init` prüft dieselbe Bindung ohne Config, Secrets oder State zu ändern.
Im erweiterten #1090-Kit erledigt ein expliziter `setup`-Aufruf die
Zulassungsprüfung, den Production-Stopp und den Setup-Start. Kein vorheriger
manueller Dockerbefehl ist nötig. Für ein älteres veröffentlichtes Kit bleibt
der dort vorgeschriebene manuelle Stopp erforderlich; keine Installerdateien
zwischen Releases austauschen.

```bash
sudo bash samuel-oci/tools/samuel-container setup \
  --manifest "$PWD/release-manifest.json" --manifest-sha256 "$manifest_sha256" \
  --installer-archive "$PWD/$installer_archive" --compose-dir "$PWD"
# Nach Prüfung und Speichern wieder denselben start-Befehl verwenden.
```

Der Installer verifiziert weiterhin Manifest, Image, Receipt, Compose- und
Projektbindungen. Ein kurzlebiger Aufruf des vorhandenen CLI hält die
Konfigurations-/Arbeitssperren über die Hostaktionen. Er nutzt die
Production-Mounts, erhält keinen Docker-Socket und startet keine Arbeit.
Erst nach dem Stopp beginnen schreibbarer Setup und Administratoraufnahme.
Version, Revision, Betriebsmodus, Image und Readiness müssen bestehen, bevor
der Installer den Übergang ausdrücklich abschließt. Production prüft lokale
und externe Workflowblocker nochmals unmittelbar vor der Freigabe.

Der feste Dockername `<Compose-Projekt>-samuel-maintenance` bleibt für den
gesamten Operatoraufruf reserviert, auch wenn dessen CLI-Prozess vorher stirbt.
Er verhindert damit einen zweiten Hostvorgang während noch laufender
Dockeraktionen. Reguläres Ende entfernt ausschließlich den eigenen beendeten
Container anhand seiner ID; kein `rm --force`, keine dauerhafte Zusatzkomponente.
Die separaten Aktionen `project` und `toolchain` verwenden dieselbe Sperre,
verlangen weiterhin eine gestoppte Runtime und starten sie nicht. Die im
Dashboard vorbereitete Erstbindung wird beim bestätigten `start` nach dessen
kontrolliertem Stopp mit derselben Registrierung ausgeführt.

Nach normal gemeldetem Fehler denselben gebundenen `setup`- oder `start`-Aufruf
wiederholen; offene Wartung bleibt bis zum nachgewiesenen Abschluss gesperrt.
Nach unauffangbarem Prozessverlust kann der reservierte Container zurückbleiben.
Dann zunächst sicherstellen, dass der **vorherige äußere Operatorprozess und
seine Hostaktionen beendet sind**. Erst danach denselben Aufruf ausdrücklich
um `--recover-maintenance yes` ergänzen. Diese Bestätigung entfernt nur einen
beendeten Container mit passendem Image und Installationsreceipt. Auf demselben
Docker-Host prüft die CLI zusätzlich, dass die aufgezeichnete äußere Operator-PID
nicht mehr existiert. Lebende oder wiederverwendete PIDs, fehlende Prüfrechte,
fremde Bindungen und unklare Container werden abgewiesen. Sie löscht keine fachlichen
Wartezustände, Freigaben oder Evidence und umgeht keine Zulassungsprüfung.
`doctor` und die vorhandenen lokalen State-/Identity-Recoverywege bleiben auch
ohne Dashboard nutzbar. Das sind sichtbare Fehlerbehandlungen, keine weiteren
Schritte im erfolgreichen Normalweg.

Belegte fremde Pfade, abweichende Releasebindung und unvollständige
Initialisierung werden erklärend abgelehnt. Keine Config wird automatisch
überschrieben, gemergt oder migriert. Der Initialisierungsbeleg nennt nur
`stage=initialized`; ein Runtimefehler meldet keinen Installationserfolg.
Bei einem Dateisystemfehler während der Initialisierung bleiben Teilstände
zur Betreiberprüfung erhalten und blockieren eine erneute Erstinstallation.
Der Installer enthält keinen Updatepfad.

Historische Releases ohne manifestgebundenes OCI-Kit benötigen den gesondert
geprüften Reparaturinstaller und dessen eigene Bindung. Ihre bestehenden
Tags, Manifeste und Assets werden dadurch nicht geändert.
Eine gesunde Installation belegt technischen Betrieb; Workflow-/Golden-/D0-
Abnahmen sind eigenständige Nachweise.
<!-- oci-first-install:end -->

### Registrierter lokaler OCI-Projektbestand (#988)

Dieser Abschnitt beschreibt den seit **v2.0.0a29 veröffentlichten** lokalen
Projektpfad. Ausschließlich das manifestgebundene Kit und Image desselben
Releases verwenden. Keine Dateien eines alten Kits ersetzen.

Der Docker-Host benötigt einen dedizierten, bereits provisionierten, sauberen
Standalone-Git-Checkout des konfigurierten Zielrepositorys. Sein vollständiger
Ausgangscommit und sein credentialfreier HTTP(S)-Origin müssen bekannt sein.
Der Betreiber stellt Eigentümer, Gruppe und Rechte passend zur **tatsächlichen
Image-UID/GID** bereit; keine feste UID annehmen. Die UID/GID lassen sich nach
Prüfung des Manifestimages mit `docker run --rm --network none --entrypoint id
<container.reference>` feststellen. Keine Zugangsdaten in Git-URLs speichern.

Der Checkout ist die lokale Sourcebasis. Die vorhandene Workspaceverwaltung
legt getrennte Run-/Verifier-Worktrees unter `/samuel-workspaces` an. Weil Git
Refs, Fetch und Worktreeverwaltung die Git-Metadaten verändern, ist die
Sourcebasis **schreibbar** eingebunden. Deshalb ausschließlich einen dedizierten
Agentenbestand verwenden: keinen produktiven Kundencheckout, keinen Checkout
auf einem anderen LXC und keine gleichzeitig manuell bearbeitete Arbeitskopie.
Die Registrierung klont nichts und verändert weder Sourceinhalt noch Ownership.
Die Host-Elternverzeichnisse bis `/` müssen root gehören und dürfen weder
Gruppen- noch Fremdschreibrechte besitzen. Auch die Sourcewurzel und `.git`
dürfen keine Gruppen-/Fremdschreibrechte haben; ihre UID/GID entsprechen der
Runtime. Der Installer ändert diese Rechte nicht automatisch.

Das Registrierungsreceipt `project-binding.v2` bindet zusätzlich Device und
Inode der Sourcewurzel. Vor Compose-Start/Recreate prüft der Hostinstaller
Pfad, Elternrechte, Eigentümer und diese Identität erneut. Root-kontrollierte
Eltern verhindern unprivilegierten Verzeichnistausch zwischen Prüfung und
Docker-Bind; im Container wird die gemountete Device-/Inode-Identität erneut
verglichen. Ein fremder Bestand mit gleichem Origin und Besitzer genügt nicht.
Fehlende Quellen werden nicht angelegt. Privilegierte Hostadministratoren
können Mounts, Rechte und Registrierungen verändern; dieser lokale Vertrag
kontrolliert keinen kompromittierten Hostadministrator.

Die bestehende Git-Grenze deaktiviert Hooks, fsmonitor, geerbte System-/Global-
Konfiguration und automatische Wartung. Repository-Includes, ausführbare
Filter (einschließlich entsprechender LFS-Konfiguration), externe Diff-/GPG-
Programme und alternative Transporthelfer werden blockiert. Das ist kein
allgemeiner LFS-/Submodule-Vertrag. Der vorhandene gebundene HTTP(S)-Askpass
bleibt erhalten. Gleichzeitige Manipulation durch einen Prozess derselben
OS-Identität ist weiterhin Teil der offenen Ausführungsisolation.

SCM bleibt die gemeinsame Repositoryauthority; Änderungen entstehen weiterhin
auf verwalteten Branches und gehen durch vorhandene Gates und Human Merge.

Nach `install`, bei gestopptem Setup-/Produktionsdienst:

```bash
sudo docker compose --env-file /etc/samuel/compose.env \
  -f /etc/samuel/compose/docker-compose.yml stop samuel
sudo bash samuel-oci/tools/samuel-container project \
  --manifest "$PWD/release-manifest.json" --manifest-sha256 "$manifest_sha256" \
  --installer-archive "$PWD/$installer_archive" --compose-dir "$PWD" \
  --project-source /srv/samuel-projects/target \
  --project-target /projects/target \
  --project-repository https://scm.example/owner/repository \
  --project-revision '<vollständiger geprüfter Ausgangscommit>'
```

Bei abweichender Installation dieselben `--root`, `--port` und `--project`
wie bei `install` ergänzen. `--project` ist der Compose-Instanzname, nicht der
Sourcepfad. Der Installer erzeugt ein eng begrenztes registriertes Mount-Overlay,
`config/project-binding.json` und setzt das bestehende `PROJECT_ROOT` in `.env`.
Die ausgelieferten Compose-Dateien bleiben unverändert. Die Registrierung bindet
Installation, Source-/Zielpfad, Repositoryidentität, Ausgangsrevision und Runtime-
UID/GID. Weder dieses Receipt noch seine Prüfsummen attestieren eine Sandbox.

`start`, `setup` und `doctor` prüfen die Registrierung und nehmen ihr Overlay
automatisch hinzu. Zum anschließenden Diagnoseaufruf:

```bash
sudo bash samuel-oci/tools/samuel-container doctor \
  --manifest "$PWD/release-manifest.json" --manifest-sha256 "$manifest_sha256" \
  --installer-archive "$PWD/$installer_archive" --compose-dir "$PWD"
# Anschließend denselben manifestgebundenen start-Befehl verwenden.
```

Setup zeigt den registrierten `PROJECT_ROOT` schreibgeschützt. Ein Dashboardwert
allein kann keinen Hostmount erzeugen. Runtimeänderungen an `.env` erfordern
weiterhin Container-Recreate; diese Umgebungswerte werden nicht heiß neu
importiert. Generische JSON-Werte können im Watch-Scan erneut geladen werden,
während das gebaute Workflow-/Provider-Wiring Startzustand bleibt. CLI und Watch
prüfen den Projektzugriff vor aktivem Bootstrap. Der bestehende Workspaceadapter
prüft ihn zusätzlich vor der Workspaceanlage, auch für REST-/Eventpfade.
Doctor, Setupstatus und Dashboard verwenden dieselbe passive Projektprüfung.
Technische Health kann grün sein, während Projekt-Readiness `blocked` bleibt.
Passive GETs starten keine Tests, Fetches, LLM-Aufrufe oder Reparaturen.

Nicht unterstützt sind NFS/SSHFS/CIFS als Referenz-Source/Workspace,
Symlinkpfade, linked Worktrees als Sourcebasis, Git-Alternates, umgeleitete
Git-Worktrees, abweichende Push-Origins und Überlappungen mit State, Config,
Logs, Backups oder Verifier-Toolchain. Read-only-Mounts, falsche Runtime-UID/GID,
zu wenig Workspaceplatz/Inodes und fehlende Registrierungen blockieren.
Die Registrierung verlangt einen sauberen Ausgangscheckout einschließlich
unversionierter Dateien. Spätere SCM-Revisionen werden im bestehenden
EvaluationSubject/Workspaceverfahren gebunden; der Ausgangscommit wird nicht
als ewiger Branchstand festgeschrieben.

**Nachweisgrenze:** Ein bestandener passiver Check belegt beobachtbare lokale
Voraussetzungen, keinen tatsächlichen Fetch/Push, keine Lockgarantie und keine
Kandidatenausführungsisolation. Ein großer Bestand braucht zusätzlich genug
Platz und Inodes für die realen Worktrees. AST-/Graph-/Context-Limits bleiben
unverändert; kein unbegrenzter Großrepository-Supportclaim. Änderungen außerhalb
S.A.M.U.E.L. sind zu vermeiden; bestehende Revision-/Tree-/Lease-Prüfungen bleiben
wirksam, schützen aber nicht vor einem Administrator desselben Hosts.

**Alpha-Qualification der ursprünglichen Projektanbindung (#989):** Deren
historische Abnahme verwendete eine saubere Neuinstallation und ein neues
gebundenes Testsubject; sie belegte weder Checkpointmigration noch einen
In-place-Imagewechsel. Der spätere, gesonderte [Updatevertrag aus #1090](INSTALL_REFERENCE.md#kontrolliertes-oci-update-und-gebundene-fortsetzung-1090)
gilt ausschließlich für die ausdrücklich im Zielmanifest genannten
Quellversionen und Kompatibilitätsbindungen. Daraus folgt kein allgemeines
Cross-Release-Kompatibilitätsversprechen. Historische Test-/FAIL-Evidence bleibt
unverändert erhalten. Restart, Update und Recovery verwenden weiterhin die
vorhandenen Subject-, Policy-, Lease- und Quarantäneprüfungen. Abweichende Registrierungen blockieren; ein anderer
Sourcebestand benötigt eine neue ausdrückliche Registrierung in einer sauberen
Installation. LXC 221 und LXC 222 werden durch PR-Tests nicht verändert.

Der native Self-Mode bleibt beim bisherigen ausdrücklich ausgewählten
S.A.M.U.E.L.-Sourcecheckout. Das installierte Image enthält keinen vollständigen
Self-Entwicklungscheckout; `--self` ist kein Ersatz für Projektregistrierung und
qualifiziert keinen OCI-Self-Betrieb.

### OCI-Python/Pytest-Toolchain und separater Doctor-Prüfer (#978)

Dieser Pfad ist in v2.0.0a28 veröffentlicht; a27 enthält ihn noch nicht.
Die reale a28-Abnahme zeigt die oben dokumentierte zu knappe 8-Sekunden-
Readinessprobe. Der hier beschriebene Budgetfix ist in a29 veröffentlicht,
nicht in den unveränderten a28-Bytes.

Dieser optionale Pfad gilt für beide SCM-Provider, Gitea und GitHub. Die
Toolchain liegt außerhalb des Samuel-Images; sie wird offline in einem
kurzlebigen Container aus genau dem ausgewählten Release vorbereitet und
anschließend read-only unter `/opt/samuel-verifier` eingebunden. Es gibt keine
Installation aus Candidate-Anweisungen, keinen Host-venv, kein Runtime-Pip,
keinen Docker-Socket im Samuel-Container und keinen zweiten TEST-Verifier.

Im oben verifizierten Installerkit liegt
`samuel-oci/containers/verifier-pytest.lock`. Dieser Referenzlock enthält
Pytest und dessen Python-Abhängigkeiten mit exakten Versionen und
Wheel-SHA-256. Zusätzliche Projektabhängigkeiten benötigen einen vom Operator
geprüften vollständigen Lock im gleichen Format: ausschließlich `Name==Version`
und `--hash=sha256:…`, ohne URLs, Includes, Editable-Pakete oder Indexoptionen.
Wheels müssen zum Python und linux/amd64 des gewählten Images passen.
`.pth`-Dateien, Quellbuilds und zusätzliche native Systempakete sind in diesem
schmalen Python-Artefaktpfad nicht unterstützt.

Der folgende Download läuft in einem kurzlebigen Container ohne Runtime-`.env`
und ohne SCM-/LLM-Credentials. Der Installationshost benötigt weiterhin nur
Docker/Bash. Für das mitgelieferte reine Python-Referenzpaket sind alle Wheels
plattformunabhängig; auch eine getrennte Wheelhouse-Vorbereitung ist möglich.
Variablen für Release-Manifest und Installerarchiv stammen unverändert aus
dem Erstinstallationsbeispiel; ein lesbarer Imagetag ist keine Authority.

```bash
toolchain_lock="$PWD/samuel-oci/containers/verifier-pytest.lock"
mkdir -p "$PWD/verifier-wheelhouse"
image_ref=$(sudo sed -n 's/^SAMUEL_IMAGE=//p' /etc/samuel/compose.env)
# compose.env wurde beim offiziellen Install gegen das ausgewählte Manifest gebunden.
sudo docker run --rm --read-only --tmpfs /tmp:rw,nosuid,nodev \
  --user "$(id -u):$(id -g)" --entrypoint python \
  --mount "type=bind,src=$toolchain_lock,dst=/requirements.lock,readonly" \
  --mount "type=bind,src=$PWD/verifier-wheelhouse,dst=/wheelhouse" \
  "$image_ref" -m pip --isolated --disable-pip-version-check download \
  --require-hashes --only-binary=:all: \
  --dest /wheelhouse -r /requirements.lock
toolchain_lock_sha256=$(sha256sum "$toolchain_lock" | cut -d' ' -f1)

# Bestehenden Setup-/Productiondienst stoppen; .env mit normalem Bot bleibt erhalten.
sudo docker compose --env-file /etc/samuel/compose.env \
  -f /etc/samuel/compose/docker-compose.yml stop samuel
sudo bash samuel-oci/tools/samuel-container toolchain \
  --manifest "$PWD/release-manifest.json" --manifest-sha256 "$manifest_sha256" \
  --installer-archive "$PWD/$installer_archive" --compose-dir "$PWD" \
  --requirements-lock "$toolchain_lock" --lock-sha256 "$toolchain_lock_sha256" \
  --wheelhouse "$PWD/verifier-wheelhouse"

# eval.json vor Start prüfen: bestehendes test_cmd wird erhalten.
# Für Node-IDs z.B. "test_cmd": "python -m pytest -q {test}".
sudo bash samuel-oci/tools/samuel-container start \
  --manifest "$PWD/release-manifest.json" --manifest-sha256 "$manifest_sha256" \
  --installer-archive "$PWD/$installer_archive" --compose-dir "$PWD"
```

Der Installer legt ein neues, rootgeführtes Artefakt unter
`/srv/samuel/toolchains/sha256-<Lock-SHA>` an, registriert dessen Manifest-SHA
in `config/eval.json::verifier_toolchain` und schreibt einen getrennten
Installationsreceipt `.verifier-toolchain.json` samt kanonischem Compose-Mount.
Normale Runtime-`.env` und vorhandenes `test_cmd` bleiben erhalten. Die
gebundenen ursprünglichen Compose-Dateien werden nicht umgeschrieben.
Ein erneuter Aufruf ersetzt keine bestehende Toolchain; fehlgeschlagene
Vorbereitung bleibt als fehlgeschlagener Versuch erhalten. Ein anderer Release
oder eine andere Toolchain erfordert eine neue Installations-/Qualificationbindung.

Doctor und Planning prüfen Manifest, vollständige Paketbytes, Lock,
Distributionsversionen und Python-/Plattform-/Releaseidentität. Nur die
Versionprobe der gebundenen Toolchain läuft in einem leeren temporären
Verzeichnis mit steriler Umgebung; seit a29 verwendet sie dafür
das vorhandene `test_timeout`, begrenzt auf höchstens 60 Sekunden. Kleinere
Operatorbudgets gelten auch für diese Probe; ungebundene reine Modul-Presence-
Proben behalten ihr 8-Sekunden-Limit. Nach dessen Ablauf bleibt die Readiness
fail-closed. Diese Probe führt keine Candidate-Tests aus; Candidate-Tests laufen erst im bisherigen
TEST-Verifier. Der gewählte Interpreter startet isoliert mit den gebundenen
Paketen; Parent-PYTHONPATH, Runtime-Sitepackages und Secrets werden nicht als
Toolchain importiert. Gate 11 konsumiert weiterhin genau die bestehende
gebundene Acceptance-Evidence. Der Toolchain-Digest gehört zur Gate-Policy:
ein Wechsel macht alte Evidence/Resume-Bindungen für die neue Policy ungültig.
Fehlende oder veränderte Artefakte bleiben fail-closed. Ohne Toolchainbindung
bleibt die bisherige Runnerpolicy einschließlich anderer Sprachen bestehen.
Dieser optionale Anschluss versorgt TEST; IMPORT-Prüfungen und andere
Compiler-/CLI-Pfade erhalten dadurch keine zusätzlichen Pakete oder PATH-Werte.

Für den separaten Branchschutz-Lesezugang eine kurzlebige Token-Datei durch
den zuständigen Operator bereitstellen. Ihr Inhalt wird ausschließlich an den
Branchschutz-GET des konfigurierten Zielrepositorys übergeben. Repository-GET,
Watch, Dashboard, Git und Candidate-Prozesse verwenden weiter den normalen
Bot. Die Datei muss regulär, Eigentum des aufrufenden OS-Users und `0600` oder
strenger sein. Secretwerte gehören weder in Argumente noch in `.env`.

```bash
# Datei vorher geschützt befüllen; Inhalt nicht in Kommandozeile/Logs schreiben.
branch_token_file=/run/samuel-branch-protection.token
runtime_uid=$(sudo docker compose --env-file /etc/samuel/compose.env \
  -f /etc/samuel/compose/docker-compose.yml exec -T samuel id -u)
runtime_gid=$(sudo docker compose --env-file /etc/samuel/compose.env \
  -f /etc/samuel/compose/docker-compose.yml exec -T samuel id -g)
sudo chown "$runtime_uid:$runtime_gid" "$branch_token_file"
sudo chmod 600 "$branch_token_file"
sudo bash samuel-oci/tools/samuel-container doctor \
  --manifest "$PWD/release-manifest.json" --manifest-sha256 "$manifest_sha256" \
  --installer-archive "$PWD/$installer_archive" --compose-dir "$PWD" \
  --branch-protection-token-file "$branch_token_file"
# Danach im SCM widerrufen und lokale Token-Datei entfernen.
```

Der Installer verwendet automatisch die registrierte read-only Toolchain und
prüft die bestehende Installations-/Manifestbindung. Der Secretmount existiert
nur im einmaligen Diagnosecontainer; geerbte Compose-Overrides werden entfernt.
Ohne zusätzlichen Credentialparameter bleibt der normale Bot wirksam. Für eine
lokale Python-Installation gilt `samuel doctor --branch-protection-token-file FILE`.
Der gezielte
Token-Read folgt keinen HTTP-Redirects. HTTP401/403 beweisen allein kein
konkretes fehlendes Recht. Für GitHub verlangt der dokumentierte REST-Endpunkt
bei Fine-grained PATs Repository-`Administration: read`; Account-/Repositoryrolle
und Plattformplan sind zusätzlich zu prüfen. Quelle:
[GitHub Branch Protection API](https://docs.github.com/en/rest/branches/branch-protection#get-branch-protection).

GitHub wird jetzt ebenfalls fail-closed geprüft: exakt der konfigurierte
Required-Check-Kontext, `enforce_admins=true`, keine Force-Pushes/Löschungen,
mindestens eine erforderliche PR-Freigabe und keine Review-Bypass-Allowlist.
Es wird die native GitHub-Regel ausgewertet, keine Gitea-Feldliste. Eine fehlende
oder nicht auswertbare Regel ergibt FAIL. GitHub-Rulesets werden hier nicht als
Ersatz für den Branch-Protection-Endpunkt qualifiziert. Eine lesbare, abweichende
Regel wird durch den temporären Prüfer nicht automatisch korrigiert.
Ein Doctor mit `0 FAIL` belegt diese Diagnose; D0/Golden bleiben getrennte reale
Läufe auf dem neu veröffentlichten Digest mit frischem Subject.

### SCM-Zugriffsdiagnosen lesen (#897)

Doctor, Setup und Dashboard nennen die einzelne Operation und die verwendete
Credentialrolle. „Zugriff für diese Operation bestätigt“ belegt beispielsweise
den Repository- oder Label-Read, nicht sämtliche Botrechte. Fehlendes
Adminrecht allein ist kein Fehler. HTTP401/403 verlangt die gezielte
Operatorprüfung von Ziel, Endpoint und verwendetem Credential; das Mindestrecht
bleibt unbekannt. Bei Branchschutz/Webhookverwaltung den getrennten Operatorweg
verwenden, statt dem Runtime-Bot pauschal zusätzliche Rechte zu geben.

„Verbotene SCM-Verwaltungsoperation blockiert“ bedeutet, dass der vorhandene
Gitea-API-Guard vor dem Netzwerkzugriff eingegriffen hat. Den aufrufenden Pfad
prüfen und korrigieren; die Sperre und Botrechte beibehalten. Die Meldung
behauptet keine böswillige LLM-Absicht. „Nicht prüfbar“ bleibt bei fehlenden oder
mehrdeutigen Antworten sichtbar. Nach unklarem Schreibausgang zuerst die
bereits eingetretene Wirkung prüfen, bevor ein neuer Versuch erfolgt.

Diese Hinweise starten keine weiteren Proben oder Workflows. Bestehende
Doctor-/Releaseprüfungen und die separate Liveabnahme bleiben erforderlich.
Der [gemeinsame Diagnosevertrag](README_technical.md#scm-berechtigungsdiagnosen-897)
erklärt Felder, Beleggrenzen und die Trennung von bestätigtem Einzelzugriff und
ungeprüften Gesamtberechtigungen.

---

## 10. Sicherheit

- **Prozessherkunft:** Betriebsaufrufe verwenden ausschließlich das
  installierte `samuel`-Script. Working Directory und `PROJECT_ROOT` sind
  Arbeitskontext, keine Import- oder Build-Identitätsquelle. Ein manipuliertes
  `PYTHONPATH` oder eine kompromittierte Installation bleibt eine separate
  Betreiber-/Supply-Chain-Grenze.
- **Dashboard-Zugriff:** `config/auth.json` wählt genau einen Modus. Der
  ausgelieferte Migrationsmodus `legacy_api_key` verlangt
  `SAMUEL_API_KEY` und startet ohne Key fail-closed. `local_identity`
  akzeptiert keinen Legacy-Key-Fallback. Die HTML-Shell und
  `/api/v1/auth/mode` bleiben öffentlich; Betriebsdaten benötigen eine
  authentisierte Permission.
- **`SLICE_HMAC_KEY`** aktiviert die Signaturprüfung für Webhooks; fehlt der
  Schlüssel, ist diese Prüfung deaktiviert.
- **`SAMUEL_AUDIT_HMAC_KEY`** macht das Audit-Log tamper-evident (HMAC-Chain;
  `samuel audit verify`). Signierte Mehrprozess-Schreibvorgänge benötigen ein
  lokales POSIX-Dateisystem mit `flock`: jeder Prozess sperrt die aktuelle
  Rotationsdatei, verifiziert deren letzten Record und hängt erst dann an.
  Fehlende Lock-Unterstützung sowie ein unlesbarer, unsignierter oder
  manipulierter letzter Record lassen den Append fehlschlagen; eine bereits
  beschädigte Datei wird nicht automatisch repariert oder neu begonnen.
  `agent.jsonl.fallback` ist eine getrennt zu verifizierende Kette und belegt
  nicht die Vollständigkeit des primären Logs. `samuel health` und das Dashboard
  zeigen daneben die Audit-Schreibbeobachtung: `degraded` bedeutet erfolgreicher
  Ersatzpfad, `loss_detected` erfassten Ereignisverlust. Ein späterer erfolgreicher
  Write entfernt frühere Verluste nicht. Technische Health und deren Exitcode
  bleiben getrennt; ein Health-PASS bestätigt keinen funktionierenden Auditwriter.
- **Bind-Adresse:** Für nicht-öffentliche Hosts `DASHBOARD_HOST=127.0.0.1`
  setzen oder hinter Reverse-Proxy/Firewall betreiben.
- **`.env`** enthält Secrets → `chmod 600` (der Initialisierer setzt das).
- **Compliance-Modus:** `SAMUEL_RISK_CLASS` (z. B. `high_risk` für ein Hochrisiko-
  Host-System) und striktes Gate-Profil `SAMUEL_GATES_PROFILE=audit`. Dieses
  Opt-in ist außerhalb des Self-Workflows verfügbar. Der Self-Workflow erzwingt
  sein eigenes Profil unabhängig vom Environment; `legacy`, `self` und
  unbekannte explizite Werte brechen Standardläufe vor dem Runtime-Wiring ab.
  `SAMUEL_AUTHORITY_MODE` und `agent.authority_mode` sind nach Ablauf des
  `2.0.0a4`-Rollbackfensters entfernt und werden als veraltete Einstellungen
  fail-closed abgewiesen.

---

## 11. Den Agenten nutzen

1. Issue im überwachten Repo anlegen.
2. Mit `ready-for-agent` markieren. SAMUEL erstellt und prüft den Plan und
   veröffentlicht ihn im Issue mit `status:plan`.
3. Bei `standard`, `watch`, `chat` und `self` den Plan als Mensch mit dem Label
   `status:approved` freigeben. Dieser Kanal wird vom Watch-Polling und vom
   Webhook verarbeitet. Der exakte Kommentar `ok` beziehungsweise `/approve`
   funktioniert nur, wenn der signaturvalidierte SCM-Webhook-Ingress wirksam
   eingerichtet ist; Activity-Polling allein verarbeitet ihn nicht als
   Freigabe. Bot-Kommentare gelten nie als Freigabe. Die bewusst autonomen
   Workflows `autonomous`, `night` und `patch` fahren nach erfolgreicher
   Planvalidierung direkt fort, außer der Plan enthält eine gebundene
   Klärungsbasis. Diese verlangt in jedem Profil menschliche Freigabe.
4. SAMUEL übernimmt danach Code → commitgebundene Gates → PR. Die passive
   Evaluation beobachtet anschließend die vollständige Gate-Evidence, trifft
   aber keine Freigabeentscheidung. Fortschritt im Dashboard (Tabs *Workflow*,
   *LLM Quality*, *Activity*).

---

## 12. Update / Troubleshooting / Deinstallation

### 12.1 Ehrliche Updategrenze der Alpha-Serie

Ein mit `samuel-release fetch` erfolgreich verifiziertes Artefakt ändert diese
Updategrenze nicht: TUF-Signaturen belegen keine Datenkompatibilität, Betreiber-
Aktivierungsfreigabe oder erfolgreiche a34-Migration. Die vorhandenen
Manifest-/Digestprüfungen und der jeweilige Update-/Recoveryvertrag gelten weiter.

Für neue Ziele nach a38 ist die Liste zugelassener Quellen zunächst leer.
Das Manifest erlaubt damit eine Neuinstallation. Das Dashboard kann für dieses
Ziel keine ausführbare Updatevorbereitung liefern. Erst ein späterer geprüfter
Vertrag kann eine konkrete Quellversion freigeben.

Der deklarative `oci-update.v1`-Vertrag in Nachfolgemanifesten macht unterstützte
Quellversionen und Erhaltungsanforderungen explizit. Der gekoppelte
[Operatorweg](INSTALL_REFERENCE.md#kontrolliertes-oci-update-und-gebundene-fortsetzung-1090) prüft ihn
unabhängig vor Hostaktionen, Sicherung und ausdrücklich bestätigtem Update.
Die Deklaration allein ist kein realer Migrationsnachweis. Die interne
Dateisicherungsfunktion ist kein zusätzlicher Benutzerbefehl und ersetzt weder
den vorhandenen SQLite-Backup-/Restoreweg noch die konkrete Versionspaarabnahme.
[Vertragsgrenze](CONTAINER_RELEASE_OPERATIONS.md#deklarierter-oci-updatevertrag-ap-4).

Der erweiterte Dashboardteil kann ein Zielrelease ausdrücklich vorbereiten und
Version, signierte Artefaktbindung, deklarierte Kompatibilität, Blocker und
Sicherungsbedarf anzeigen. Dafür ist kein Setupwechsel erforderlich; produktive
Konfiguration bleibt geschützt. Eine aktuelle Vorbereitung ohne bekannte
Blocker zeigt den gesondert zu bestätigenden [lokalen Operatoraufruf](INSTALL_REFERENCE.md#kontrolliertes-oci-update-und-gebundene-fortsetzung-1090).
Die Kopplung an Installer, Sicherung und Readiness beweist noch keine reale
Versionspaar-/Restorequalifikation. [Bedienung und Grenzen](DASHBOARD.md#releaseupdate-vorbereiten-1090).


Für einen neuen Testlauf installierst du das neueste freigegebene Testrelease
in **neue, leere Verzeichnisse**. Eine bestehende Installation bleibt mit ihren
Daten erhalten. Neue und alte Installation haben jeweils ihre eigene Identität.

#### Corewechsel, frische Installation und selektiver Restore (#985)

**Welcher Fall passt zu dir?**

| Dein Vorhaben | Vorgehen |
|---|---|
| **B: Neu anfangen**, etwa mit einer neuen Alpha-Version | Folge dem Ablauf „Frische Installation“ unten. Übertrage nur die ausdrücklich geeigneten Einstellungen. Die bisherige Installation bleibt als gesicherter Altbestand erhalten. |
| **A: Nur das Programm ersetzen**, bestehende Daten weiterverwenden | Im #1090-OCI-Weg das [kontrollierte Update](INSTALL_REFERENCE.md#kontrolliertes-oci-update-und-gebundene-fortsetzung-1090) mit seinem exakten Versionsvertrag verwenden. Der weiter unten beschriebene atomare Corewechsel gehört zum separaten nativen Wheel-Weg. Ein früher erfolgreicher Wechsel beweist kein anderes Versionspaar. |
| **C: Alte Arbeitsstände in eine andere Version übertragen** | Eine allgemeine Migration zwischen Alpha-Releases ist nicht nachgewiesen. Stoppe an dieser Grenze. Der Erstinstaller ist kein Updatewerkzeug und verweigert bereits belegte Zielverzeichnisse. |

„Core“ bedeutet die Programmdateien. „State“ sind gespeicherte Arbeitsstände,
Freigaben und laufende Aufgaben. „Restore“ bedeutet, eine Sicherung
zurückzuspielen. Ein vollständiger Restore braucht zusammenpassende Daten und
eine eigene Prüfung; er ist kein Schritt der frischen Installation.

**Frische Installation mit Docker (Fall B), Schritt für Schritt**

Dieser Ablauf verwendet den Docker-Erstinstaller aus
[Abschnitt 9.1](#91-oci-erstinstallation-auf-einem-leeren-docker-host-970).
Wenn du ohne Docker aus lokalen Paketen installierst, folge stattdessen
[Abschnitt 2.1](#21-lokale-releaseinstallation-wheel-noch-d0-zu-qualifizieren).
Die Regeln für übertragbare Einstellungen und zusammengehörige Auditdateien
und Schlüssel gelten für beide Wege. Vermische ihre Startbefehle nicht.

1. **Altbestand sichern.** Erfasse die bisherige Version, Einstellungen,
   gespeicherten Arbeitsstände und offene Aufgaben. Sichere Auditdateien
   zusammen mit ihrem bisherigen Audit-Schlüssel geschützt. Für eine laufende
   State-Datenbank nutze das vorhandene
   [Backup-/Restore-Verfahren](README_technical.md), keine einfache
   Dateikopie; `samuel retention backup --json` erzeugt ein SQLite-konsistentes
   State-Backup. Dieses allein enthält noch nicht Audit, Schlüssel und alle
   externen Dateien. Lösche die alte Installation nicht.
2. **Neue Installation getrennt anlegen.** Verwende das unabhängig geprüfte
   Bootstrap-Paket des gewählten Releases und den einen Installationsaufruf
   aus Abschnitt 9.1 mit neuen, leeren Verzeichnissen. Der vorhandene Installer
   bezieht und prüft Manifest und Artefakte; keine manuelle Zusammenstellung.
   Bei bereits belegten Zielen abbrechen und den gewählten Pfad prüfen.
   Für historische a34-Kits gilt deren eigener dokumentierter Bestandsweg.
3. **Geeignete Einstellungen neu eintragen.** Öffne das vom Installer gestartete
   Setup-Dashboard wie in Abschnitt 9.1 beschrieben. Der Installer hat das
   gemeinsame `samuel setup --non-interactive` bereits ausgeführt; du musst es nicht auf dem
   Dockerhost nachinstallieren. Repository, Bot-Zugang und Modellanbieter kannst du
   bewusst neu konfigurieren; gültige Zugangsdaten dürfen über den geschützten
   Betreiberweg übernommen werden. Die Tabelle unten sagt, was neu erstellt
   werden muss. Kopiere keine vollständige alte `.env` oder Konfiguration.
4. **Auditdateien und Schlüssel zusammenhalten.** Die neue Installation bekommt
   eine neue Auditkette mit ihrem neuen Schlüssel. Sobald sie den ersten
   Eintrag geschrieben hat, darf die alte `.env` diesen Schlüssel nicht mehr
   ersetzen. Bewahre die alte Auditkette mit dem alten Schlüssel separat auf.
   Auditdateien protokollieren Ereignisse; ihr Schlüssel macht Veränderungen
   prüfbar. Ein Schlüssel aus einer anderen Installation passt nicht dazu.
5. **Projekt verbinden und prüfen.** Bereite die einzelne Projektbindung im
   Setup-Dashboard vor; der ausdrückliche Production-Start registriert sie nach
   unabhängiger Hostprüfung und Bestätigung. Ein zusätzlicher `project`-Aufruf
   gehört beim #1090-Bootstrap nicht zum Normalweg. Benötigt das Projekt eine
   separate Testtoolchain, bleibt deren vorhandener `toolchain`-Operatorweg
   eine ausdrücklich benannte Projektvoraussetzung; siehe
   [Projektbestand](#registrierter-lokaler-oci-projektbestand-988) und
   [Testwerkzeuge](#oci-pythonpytest-toolchain-und-separater-doctor-prüfer-978).
   Prüfe mit `doctor` die neue Konfiguration und Projektbindung über den
   Launcher- und Prüferweg aus Abschnitt 9.1.
6. **Kontrolliert starten und Ergebnis prüfen.** Wenn die neue Installation die
   bisherige ersetzen soll, stoppe den bisherigen Dienst vor der Aktivierung
   des neuen; beim Wechsel darf nur ein Core aktiv sein. Verwende den
   beschriebenen `start`-Befehl aus Abschnitt 9.1, der die
   Produktionskonfiguration neu erzeugt und die Runtime prüft. Prüfe danach
   angezeigte Version, Commit und Image-Digest gegen das gewählte Manifest
   sowie `health` und `audit verify` für **dieselbe neue Installation**.
   Verwende bei allen Dockerbefehlen dieselben Installationspfade und Optionen.


**Was darfst du übernehmen? — Preserve/Replace/Reject-Matrix für Fall B**

| Einstellung oder Daten | Was du bei der frischen Installation tust |
|---|---|
| Repository, Botkonto, erforderlicher CI-Check | Passende Werte neu im Setup eintragen und mit Doctor prüfen. Ein noch gültiger Token darf geschützt übernommen werden; die benötigten Rechte musst du trotzdem prüfen. |
| Modellanbieter, API-Schlüssel, Modellwahl und Budget | Bewusst neu konfigurieren und prüfen. Keine komplette alte `llm.json` oder `defaults.json` kopieren. |
| Dashboard-Zugang und Webhook-Schlüssel | Gewählten Zugriffsmodus neu einrichten und beide Webhook-Seiten prüfen. Keine alten Sitzungen, lokalen Identitätsdaten oder menschlichen Freigaben in die neue Stateidentität übertragen. |
| Auditdateien und Audit-Schlüssel | Neues Paar zusammenhalten. Altes Paar geschützt archivieren. Alte Dateien weder neu signieren noch automatisch reparieren. |
| Testbefehl, Zeitlimit und Testauswahl | Geeignete Werte bewusst in die neue Test-/Gate-Konfiguration eintragen und am Zielprojekt prüfen. |
| Projektregistrierung und Testwerkzeuge (Toolchain) | Für das gewählte Manifest und den exakten Digest neu registrieren. Alte Registrierungsnachweise gelten nicht für die neue Installation. |
| Gespeicherte Arbeitsstände, Checkpoints, Leases und Budget-/Retentionfreigaben | Nicht übernehmen. Ein vollständiger State-Restore folgt dem eigenen Backup-/Restore-Verfahren und braucht eine Kompatibilitätsprüfung. |
| Alte `.env`, `compose.env`, Defaults und Installerdateien | Nicht als Ganzes zurückspielen. Aus dem neuen Release erstellen und nur passende einzelne Werte setzen. Diese Dateien enthalten auch Schlüssel, Versions- und Pfadbindungen. |
| Alte Logs, Nachweise und Backups | Unverändert mit ihrer damaligen Version und ihrem passenden Schlüssel archivieren. Sie bestätigen keinen erfolgreichen neuen Lauf. |

Diese Tabelle gilt für die **frische Installation**. Bei einem nachgewiesen
kompatiblen Corewechsel (Fall A) bleiben State, Audit, passender Schlüssel und
externe Betreiberpfade dagegen zusammenhängend erhalten. Vor dem Wechsel
prüfst du Schema, Policy, offene Aufgaben, Leases und Rückwechselmöglichkeit,
sicherst den Bestand und stoppst den laufenden Dienst. Das vorhandene Verfahren
steht in [ADR-0706](adr/0706-atomic-release-layout.md) und im anschließenden
Befehlsabschnitt. Ein Rückwechsel der Programmdateien setzt gespeicherte Daten
nicht automatisch zurück. Die historischen Installations- und Wechseltests
belegen jeweils ihren eigenen Versionsstand; sie sind keine allgemeine
Migrationszusage.

**Wenn die Auditprüfung einen falschen Schlüssel meldet:** Stoppe den betroffenen
Dienst und erhalte die vorhandenen Dateien. Prüfe, welche Auditkette zu welchem
Schlüssel gehört. Tausche den Schlüssel nicht versuchsweise an einer laufenden
Kette aus. Ein korrektes altes Paar und ein korrektes neues Paar sind getrennt
prüfbar. Ein erfolgreiches `audit verify` bestätigt die Integrität der geprüften
Einträge; es beweist weder die aktuelle Schreibfähigkeit noch, dass keine
Ereignisse fehlen. Die Ersatzdatei (`agent.jsonl.fallback`) wird separat geprüft
und bestätigt keine Vollständigkeit der Hauptdatei (#986).

Die technische Prüfung dieser Anleitung ersetzt nicht die nachfolgende
menschliche Verständlichkeitsabnahme in #985. Ein erfolgreicher Installations-
oder Dokumentationscheck ist keine vollständige Funktions-/Golden-Abnahme.

Die folgende Befehlsfolge aktualisiert nur einen **Entwicklungscheckout**. Sie
ist kein qualifizierter Kundenupdatevertrag und darf nicht auf einer laufenden
Releaseinstallation als Beleg für ein atomar erfolgreiches Upgrade verwendet
werden:

```bash
git pull
source .venv/bin/activate
pip install -e ".[all]"
python tools/wiki.py build              # wiki/ an den neuen Head binden
python tools/wiki.py check-local        # Materialisierung explizit gegenprüfen
```

Ein beliebiger direkter `git pull` löst bewusst keinen versteckten Git-Hook
aus. Selbst die vollständige Folge oben beweist heute nicht, dass alte
Produktdateien, `*.egg-info`, Importpfade oder eine andere Editable-Installation
vollständig ersetzt wurden. Dieser Pfad bleibt Entwicklungsmodus.

Für eine nach Abschnitt 2.1 angelegte lokale Releaseinstallation wird ein
Update dagegen immer in eine neue Geschwister-venv gestaged. Konfiguration und
Persistenz werden weder kopiert noch gemergt. Das Staging kann bei laufendem
alten Dienst erfolgen; vor Aktivierung werden Zustand und Backup gebunden:

```bash
new_version='<neue veröffentlichte Version>'
old_version="$(readlink -f /opt/samuel/current | xargs basename)"
release_dir=/pfad/zu/den/neuen/release-assets
bootstrap_dir="$(mktemp -d)"
python3 -m venv "$bootstrap_dir/venv"
"$bootstrap_dir/venv/bin/pip" install --no-deps \
  "$release_dir/samuel-$new_version-py3-none-any.whl"

sudo "$bootstrap_dir/venv/bin/samuel-release" stage \
  --manifest "$release_dir/release-manifest.json" \
  --wheel "$release_dir/samuel-$new_version-py3-none-any.whl" \
  --runtime-lock "$release_dir/samuel-runtime-$new_version.lock"

cd /etc/samuel
sudo /opt/samuel/current/bin/samuel workspace list --json
sudo /opt/samuel/current/bin/samuel resume list --json
sudo /opt/samuel/current/bin/samuel retention backup --json
sudo systemctl stop samuel-dashboard samuel-watch
sudo "$bootstrap_dir/venv/bin/samuel-release" activate \
  --version "$new_version" --expected-current "$old_version"
sudo systemctl start samuel-dashboard samuel-watch
```

Nicht vorhandene Units werden in den beiden `systemctl`-Zeilen entsprechend
weggelassen. `stage` validiert Manifest, Wheel, Lock, Version, Revision,
Console-Script, Paketmetadaten und Importpfad, bevor der Release aktivierbar
ist. `activate` verlangt den beobachteten Altstand als CAS-Bedingung. Ein
Teilupdate, ein bereits vorhandenes Versionsverzeichnis, ein fremder
`current`-Pfad oder alte Produktdateien direkt unter `/opt/samuel` blockieren;
der alte Dienststand bleibt unangetastet. Das Tool löscht weder den alten
Release noch ein fehlgeschlagenes, receiptloses Versionsverzeichnis
automatisch; dessen Prüfung und Entfernung bleibt eine sichtbare
Operatorentscheidung.

Die Ersteinrichtung wird bei einem Update **nicht** erneut ausgeführt. Neue notwendige
Konfigurationsfelder müssen vor der Aktivierung explizit gemäß Release Notes
ergänzt werden; die Runtime fällt nicht unbemerkt auf neue Defaults zurück.
Ein Rückwechsel des Symlinks ist nur nach Prüfung der Schema-/State-
Kompatibilität zulässig. Hat der neue Stand persistenten State verändert,
benötigt ein älterer Core das vor dem Wechsel erzeugte, passend gebundene
Backup und den dokumentierten Restore-/Reconcile-Ablauf. Es gibt keinen
automatischen Datenrollback.

Beim OCI-Pfad bleibt der Manifest-Digest der atomare Core-Austauschpunkt.
Operator-Config, State und Workspaces bleiben externe Mounts; nur ein Container
ist aktiv. Die bereits reale D0-Evidence belegt diesen Mechanismus, nicht
automatisch den noch ausstehenden veröffentlichten Wheel-Upgrade-Drill.

Nach jedem Installations- oder manuellen Wechsel werden Produktversion,
vollständige Build-Revision und beim Container die gestartete Digest-Referenz
gemeinsam kontrolliert. Danach folgen mindestens:

```bash
cd /etc/samuel
/opt/samuel/current/bin/samuel --version
/opt/samuel/current/bin/samuel doctor
/opt/samuel/current/bin/samuel health
/opt/samuel/current/bin/samuel audit verify
/opt/samuel/current/bin/samuel workspace list --json
/opt/samuel/current/bin/samuel resume list --json
/opt/samuel/current/bin/samuel dlq list
```

Ein Widerspruch zwischen Version, Revision, Importpfad oder Image-Digest ist
ein Abbruchgrund; es gibt keinen stillen Fallback auf den älteren Stand. Die
historische Teilabnahme für a15 ist im realen #658-Lauf gebunden und
nicht aus dieser Diagnoseliste abzuleiten. Eine wesentliche Änderung an
Release, Policy, Provider-, Toolchain- oder Berechtigungsprofil verlangt einen
neuen Referenzlauf.

### 12.2 Lokales Wiki und externer Publisher

`wiki/` ist kein SCM-Publisher: Gitea-/GitHub-Wiki werden aus demselben
Artefakt über getrennte Publisher synchronisiert. `check-local` meldet einen
fehlenden oder gegenüber dem Checkout veralteten Build.

Das Wiki wird nicht manuell gepflegt. Technische Fakten werden in Code oder
ausgelieferter Konfiguration geändert, erklärende Inhalte im zuständigen
aktiven Dokument. Der Build übernimmt ausschließlich manifestgebundene
Abschnitte und Resolver-Facts; manuelle Änderungen unter `wiki/` oder im
externen Git-Wiki werden von `check-local` beziehungsweise dem Publisher als
Abweichung behandelt.

#### Git-Wiki veröffentlichen

Nach `build` und `check-local` kann derselbe providerneutrale Publisher ein
Gitea- oder GitHub-Wiki aktualisieren:

```bash
export WIKI_GIT_REMOTE='<credentialfreies-wiki-git-remote>'
export WIKI_SOURCE_URL_TEMPLATE='<commitgebundene-url-mit-{head_sha}-und-{path}>'
python tools/wiki_publish.py \
  --remote "$WIKI_GIT_REMOTE" \
  --branch main \
  --source-url-template "$WIKI_SOURCE_URL_TEMPLATE"
```

Die Git-Authentisierung wird vorab über SSH-Agent oder Credential Helper
eingerichtet. Zugangsdaten gehören nicht in die Remote-URL oder Argumente. Bei
der ersten Übernahme eines bereits vorhandenen Wikis ist zusätzlich
`--adopt-existing-head <full-sha>` erforderlich; ein abweichender Head
blockiert. Gitea und GitHub werden in getrennten Läufen mit getrennten Receipts
publiziert.

### 12.3 Diagnose und Deinstallation

- **SCM-Verbindung ❌:** `SCM_URL`/`SCM_TOKEN`/`SCM_REPO` prüfen (Token-Rechte!).
- **SCM Required Check (Soll) ❌:**
  `SCM_REQUIRED_STATUS_CONTEXT` auf genau einen nichtleeren, einzeiligen
  Checknamen setzen und Doctor erneut ausführen.
- **Branch-Protection (Release) ❌:** Den konkreten Regel-Read und dessen
  Credential separat prüfen; ein HTTP403 bestimmt das fehlende Mindestrecht
  nicht. Eine lesbare Regel gemäß Abschnitt 8 auf den vom Doctor angezeigten
  Soll-Kontext korrigieren. Ohne lesbaren, exakten Nachweis gibt der Doctor keine
  Release-Freigabe; normale Laufzeitfunktionen bleiben davon getrennt mit
  Write-Recht nutzbar.
- **LLM ⚠️:** Key in `.env`, Provider in `config/llm.json`, `Test-Connection`.
- **Dashboard startet wegen Auth nicht:** im Legacy-Modus `SAMUEL_API_KEY`
  setzen; für den lokalen Modus zuerst den in Abschnitt 4.4 beschriebenen Bootstrap und
  Cutover ausführen.
- **Deinstallation:** Dienste stoppen und zuerst `/etc/samuel`,
  `/var/lib/samuel`, `/var/log/samuel` sowie `/srv/samuel` inventarisieren.
  `/opt/samuel` enthält nur ersetzbaren Core, die übrigen Wurzeln aber Secrets,
  State, Evidence, Workspaces, Erweiterungen und Backups; sie werden niemals
  implizit mit dem Core entfernt.

---

## 13. Referenz: wichtige Umgebungsvariablen

| Variable | Zweck |
|---|---|
| `SCM_PROVIDER` / `SCM_URL` / `SCM_USER` / `SCM_TOKEN` / `SCM_REPO` | SCM-Verbindung + überwachtes Repo |
| `SCM_BOT_USER` | Bot-Account-Login (Bot/Human-Zuordnung) |
| `SCM_REQUIRED_STATUS_CONTEXT` | Genau ein erwarteter Required-Check-Kontext; fehlt die Variable, meldet und verwendet Doctor den ausgelieferten Default `CI / lint-and-test (pull_request)` |
| `DEEPSEEK_API_KEY` / `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` / `OPENAI_API_KEY` / `OPENROUTER_API_KEY` | LLM-Keys |
| `SAMUEL_LLM_PROVIDER` | Default-Provider override |
| `SAMUEL_API_KEY` | Dashboard-/REST-Auth (Bearer) |
| `SAMUEL_CONFIGURATION_MODE` | Dashboard-Konfigurationsauthority: `production` (Default, eingefroren) oder ausdrücklich gestartetes `setup`; CLI-Schalter hat Vorrang |
| `SLICE_HMAC_KEY` | Webhook-Signatur |
| `SAMUEL_AUDIT_HMAC_KEY` | Audit-Log-HMAC-Chain |
| `SAMUEL_EXECUTION_EVIDENCE_HMAC_KEY` | Separater Integritätsschlüssel des qualifizierten Execution-Provider-Profils; nur erforderlich, wenn `config/execution.json` ausdrücklich aktiviert und qualifiziert ist |
| `DASHBOARD_HOST` / `DASHBOARD_PORT` | Dashboard-Bind (CLI-Flag hat Vorrang) |
| `PROJECT_ROOT` | Lokaler Pfad des überwachten Projekts |
| `SAMUEL_RISK_CLASS` | EU-AI-Act-Deployment-Risikoklasse |
| `SAMUEL_GATES_PROFILE` | Gebundenes Nicht-Self-Profil (`default` oder `audit` = strikt); Legacy/Self nicht überschreibbar |
| `SAMUEL_GIT_AUTHOR_NAME` / `SAMUEL_GIT_AUTHOR_EMAIL` | Optionales vollständiges Paar für die Commit-Attribution des Agenten |

Config-Dateien liegen unter `config/` (z. B. `agent.json`, `llm.json`,
`gates.json`, `labels.json`, `workflows/`). Details: `docs/README_technical.md`.

Wenn Issues mit ausdrücklich offenen Markern über den gebundenen
Klärungsdialog bearbeitet werden sollen, muss der Operator in `agent.json`
unter `planning.clarification_wait_seconds` eine endliche Frist zwischen 1
und 2.592.000 Sekunden setzen. Ohne diesen expliziten Wert blockiert nur ein
tatsächlich klärungsbedürftiges Issue; klare Issues behalten ihren bisherigen
Workflow. Nach Timeout, zwei erfolglosen Runden oder Source-Supersession startet
nur `samuel run ISSUE` eine neue Serie.

Ohne dieses Paar verwendet die Referenzruntime stabil
`S.A.M.U.E.L. Reference Agent <samuel-reference@localhost.invalid>`. Das ist
eine ausdrücklich nicht-menschliche Git-Attribution und erteilt weder
Freigabe- noch Pushrechte. Ist nur eine der beiden Variablen gesetzt, blockiert
die Commit-Erzeugung fail-closed; Werte aus unterschiedlichen Quellen werden
nicht kombiniert. Es wird keine globale oder lokale Git-Konfiguration
geschrieben.

## Historischer Testrelease v2.0.0a29 — 09.10.2026

Dieser historische Nachweis verwendet ausschließlich das a29-Manifest und
die dazugehörigen Installerdateien. #989 (lokale Projektbindung/F13/Readiness) und #980 (Verifierbudget)
sind enthalten; unabhängige frische Draft- und Published-Erstinstallation sind
PASS. Exakte Digests und Grenzen stehen im [aktuellen Produktstatus](status/CURRENT_PRODUCT_STATUS.md#veröffentlichter-installationsstand-v200a29--09102026).
Der unten beschriebene Projekt-/Toolchainpfad ist seit a29 veröffentlicht. Keine Cross-Release-State-/Checkpointmigration; alte Instanzen unverändert
lassen. Der vollständige Funktions-/D0-Lauf und Prozessisolation bleiben separat.

## Historischer Installationsstand v2.0.0a28 — 08.10.2026

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](archive/reader-history-2026-10-11/INSTALL.md#historischer-installationsstand-v200a28--08102026).

## Historischer Veröffentlichungsnachweis v2.0.0a26 — 05.10.2026

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](archive/reader-history-2026-10-11/INSTALL.md#historischer-veröffentlichungsnachweis-v200a26--05102026).


> **Development-Preflight, Stand 29.09.2026:** Ein erfolgreicher synthetischer
> Signed-Receiver-Test ist kein Nachweis nativer SCM-Delivery. Vor einem neuen
> positiven Subject muessen die tatsaechlich konfigurierten Workflowlabels,
> Required-Check-Kontexte, Branchschutz, Runnerpolicy, Webhook-Eventtypen und
> jede effektive LLM-Taskroute mit der echten Operator-/Runtimeidentitaet
> gelesen beziehungsweise bounded geprueft werden (#900/#905/#921).
> Fremde Teamlabels bleiben erhalten. Ein frischer SQLite-State ersetzt keine
> SCM-Subject-Isolation; ad-hoc `.env`-Split und ein Helper-Container ersetzen
> nicht den ausgelieferten Setup-/Compose-Startpfad. Fehlende oder nicht
> gepruefte Native-Delivery wird als `NOT_PROVEN` behandelt, nicht als PASS.
