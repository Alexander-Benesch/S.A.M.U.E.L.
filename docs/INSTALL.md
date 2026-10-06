# S.A.M.U.E.L. — Installation & Inbetriebnahme

Diese Anleitung führt SAMUEL von Null auf einem Zielserver in Betrieb: in ein
Projekt klonen, konfigurieren, starten, ein Repo überwachen.

> **Abgrenzung:** Diese Doku beschreibt das **Überwachen eines fremden Projekts**
> (Normalfall). Der **Self-Mode** (`--self`) ist etwas anderes — er dient nur
> SAMUELs Selbst-Erweiterung am eigenen Code und ist hier nicht relevant.

> **Vor Produktivbetrieb:** Die
> [Capability-/Wirksamkeitsmatrix](CAPABILITY_MATRIX.md) nennt den geprüften
> Kontrollstand. `v2.0.0a25` ist der jüngste veröffentlichte
> Alpha-Kandidat. Golden-D0 und Capabilityqualifications wurden für diesen
> Stand nicht ausgeführt; er ist daher kein unterstützter
> Installationsstand. Der unterstützte Alpha-Stand `v2.0.0a15` ist keine
> Beta-Freigabe; `v2.0.0a1` blieb nach roter Tag-CI unveröffentlicht.
> `v2.0.0a8` wurde zwar mit konsistenten Python-/OCI-Artefakten
> veröffentlicht, ist wegen der im realen D0-Zielpfad fehlenden Git-Runtime
> jedoch ausdrücklich **kein** unterstützter Installationsstand (#727).
> `v2.0.0a15` besitzt grüne Tag-CI, Runtime-Lock, Git 2.47.3 und ein
> Schema-2-Manifest. Sein frischer #658-D0-Lauf bestand Installation,
> Runtime-/Provider-/Auth-/Auditpfade, den menschlich freigegebenen Golden Path
> bis PR und Required Check sowie einen echten `diff_secret_scan`-Block ohne
> PR. Der abschließende Golden-PR-Merge erfolgte jedoch durch den Demo-Bot
> statt durch den vorgeschriebenen menschlichen Akteur. Die Teilnachweise
> bleiben gültig, ein vollständiger D0-PASS ist damit nicht bestätigt. Der Fix
> für #694 ist auf `main` noch nicht real
> qualifiziert; bis zum positiven und negativen Doctor-Nachweis bleibt die
> bisherige SCM-/Doctor-Betreibergrenze bestehen.
> Gate-Profil,
> Required CI Check und Schutz vor direkten Pushes müssen für jede
> SCM-Installation separat eingerichtet und nachgewiesen werden.

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

---

## 0. Überblick

SAMUEL läuft als eigener Dienst und überwacht ein **SCM-Repository** (Gitea oder
GitHub). Es nimmt gelabelte Issues entgegen, plant, generiert Code via LLM,
prüft den Candidate mit gebundenen Gates, beobachtet die Qualität nicht
bindend und erstellt Pull-Requests — alles unter menschlicher Aufsicht.

Drei Bausteine, die du konfigurierst:
1. **SCM** — welches Repo, mit welchem Token/Account (→ `.env`).
2. **LLM-Provider** — welches Modell generiert (→ `.env` + `config/llm.json`).
3. **Sicherheit/Betrieb** — API-Auth, Webhook-Signatur, Port (→ `.env`).

---

## 1. Voraussetzungen

- **CPython ≥ 3.10** (`python3 --version`). Der Release-Check testet die
  Mindestreihe 3.10 und die aktuelle stabile Reihe 3.14 vollständig.
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
| Release-/Image-Publish | sauberer Releasecheckout, grüne Tag-CI, Docker und eine separat ausgestellte Package-Publishercredential des persönlichen Package-Owners auf dem kontrollierten Releasehost | Runtime-SCM-Token des Zielprojekts oder eine behauptete technische Einzelimage-Isolation |
| Externer Gitea-Actions-Runner | eigener Runner-Host, Docker, repo-/orggebundener Registrierungstoken und der Vertrag aus [CI_RUNNER_OPERATIONS.md](CI_RUNNER_OPERATIONS.md) | S.A.M.U.E.L.-Runtime oder deren `.env`; der Runner ist keine Produktkomponente |

### 1.2 Accounts, Credentials und kleinste Rechte

Accounts werden nicht zusammengelegt, nur weil dieselbe Plattform sie
bereitstellt. Insbesondere ist ein SCM-Bot weder Package-Publisher noch
menschliche Freigabeinstanz. Die Plattform bleibt Authority für Owner,
Mitgliedschaft und Token-Scope.

| Rolle/Credential | Zweck und kleinstes Recht | Ablage und Consumer | Rotation/Widerruf |
|---|---|---|---|
| Menschlicher Operator | Installation, Konfiguration und authentifizierte Freigabe im SCM; kein dauerhaftes Produktsecret. Repository-Adminrecht ist nur zum Setzen beziehungsweise Lesen des nativen Branchschutzes nötig. | menschliche SCM-Sitzung; Admincredential nie in der Runtime-`.env` | Plattformsession/PAT widerrufen; menschliche Freigaben bleiben subject- und aktionsgebundene Audit-Evidence |
| S.A.M.U.E.L.-SCM-Bot | Issue/Kommentar/Label sowie Repository/Branch/PR lesen und schreiben, eigene Identität lesen. Gitea: `write:issue`, `write:repository`, `read:user`; GitHub entsprechend Issues, Contents und Pull Requests read/write plus Metadata read. Kein Adminrecht. | `SCM_USER` + `SCM_TOKEN` in der deploymentlokalen `.env` (`0600`), nur vom S.A.M.U.E.L.-Prozess konsumiert | Dienst stoppen, neuen Token desselben Botkontos eintragen, starten und SCM-Probe ausführen, erst danach alten Token widerrufen |
| Temporärer Branchschutz-Prüfer | Admin-Endpunkt des Zielrepositorys lesen; getrennt vom normalen Bot. | nur für den gezielten `doctor`-Lauf, nicht dauerhaft in `.env`, Watch oder Dashboard | unmittelbar nach der Prüfung widerrufen; fehlendes Recht lässt Doctor den Branchschutz nicht als belegt melden |
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

### 2.1 Lokale Releaseinstallation (Wheel, noch D0-zu-qualifizieren)

Ein Release stellt vier zusammengehörige Assets bereit: Wheel, sdist,
versionierten Runtime-Lock und `release-manifest.json`. Alle werden aus
demselben Gitea-Prerelease geladen. Das Manifest bindet Wheel und Lock an Tag,
Produktversion und vollständigen Commit. Der sdist enthält die unveränderten
Defaultkonfigurationen für genau den ersten Installationslauf.

Für eine Erstinstallation als `root` beziehungsweise über `sudo`:

```bash
release_dir=/pfad/zu/den/vier/heruntergeladenen/assets
release_version='<exakte Version, z. B. 2.0.0a9>'
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
Schreibrecht auf State, Prozesslogs und Workspaces und führt den Wizard aus
der externen Konfigurationswurzel aus. Die wirksame Konfiguration sollte im
Dauerbetrieb für den Runtimeaccount lesbar, aber nicht pauschal schreibbar
sein; Dashboard-Konfigurationsänderungen benötigen dann eine bewusste
Operatorfreigabe.

```bash
sudo useradd --system --home /srv/samuel --shell /usr/sbin/nologin samuel
cd /etc/samuel
sudo /opt/samuel/current/bin/samuel setup
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
git checkout v2.0.0a15      # exakter unterstützter Alpha-Quellstand
./install.sh                 # legt .venv an, installiert, startet danach den Wizard
```
`install.sh` nutzt non-interaktives Setup, wenn `SCM_URL`/`SCM_TOKEN`/`SCM_REPO`
als Env-Variablen gesetzt sind (oder `SAMUEL_SETUP=auto`) — sonst zeigt es den
nächsten Schritt an. Nach erfolgreicher Paketinstallation materialisiert es die
providerneutrale lokale Entwicklernavigation unter `wiki/`.

**Manuell:**
```bash
git clone <repo-url> samuel
cd samuel
git checkout v2.0.0a15
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
Minimal genügt `pip install -e .` — dann fehlt aber das Dashboard.

---

## 3. Schnellweg (empfohlen)

```bash
samuel setup      # interaktiver Wizard (schreibt .env, legt Labels an)
samuel doctor     # Produkt-/Buildstand und Konfigurationsdiagnose
# LLM-Key in .env eintragen (s. §5), dann:
samuel dashboard  # Web-UI: Provider testen, Status sehen
samuel watch      # Polling-Überwachung starten
```

Die Details zu jedem Schritt folgen unten.

---

## 4. Konfiguration via Wizard — `samuel setup`

Der Wizard ist idempotent (liest bestehende `.env` als Vorbelegung) und fragt in
vier Schritten:

**Schritt 1 — SCM-Verbindung**
- *Provider* (`gitea`/`github`), *SCM URL*, *Benutzername*, *API-Token*.
- Bei Gitea ist der Benutzername für private Git-Fetches/-Pushes verpflichtend
  und muss zu dem Konto gehören, dessen Token verwendet wird. GitHub verwendet
  intern den providerspezifischen Token-Benutzer `x-access-token`.
- Es wird sofort ein **Live-Verbindungstest** gemacht (`GET /api/v1/user`); bei
  Fehler kannst du korrigieren und erneut versuchen.

**Schritt 2 — Repository**
- Listet (bei Gitea) deine verfügbaren Repos auf.
- *Repository* im Format `owner/name`.
- *Bot-User* — s. §4.1.

**Schritt 3 — Zielprojekt**
- *PROJECT_ROOT* (optional): lokaler Pfad des überwachten Projekts. Leer lassen,
  wenn SAMUEL im Projekt selbst läuft.
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
  Module werden nicht von S.A.M.U.E.L. installiert. `samuel doctor` muss den
  effektiven Runner und seine Selektorform vor dem ersten Lauf als `ok`
  melden.

  Ein Pytest-`test_cmd` mit `-k {test}` eignet sich nur für logische Namen.
  Soll der Plan Node-IDs verwenden, muss `{test}` wie im Beispiel als direktes
  positionsgebundenes Pytest-Argument stehen.

**Schritt 4 — Sicherheit & Dashboard**
- **HMAC-Key (Webhook)**, **Dashboard-API-Key**, **Audit-HMAC-Key** werden
  **automatisch generiert**, falls noch nicht in der `.env`.
- *Zeitzone* (IANA, wird vom System vorgeschlagen) → `config/agent.json`.
  Das Dashboard verwendet diesen effektiven Wert für Zeitdarstellung mit
  Offset und Zonenname; fehlende/ungültige Zone fällt auf sichtbar benanntes UTC
  zurück. Event-, Audit- und API-Zeitpunkte bleiben UTC. Ältere Zeitwerte ohne
  Offset werden unverändert als „Zeitzone unbekannt“ gezeigt.
- *Dashboard-Port* (Default 7777).

Danach schreibt der Wizard:
- `.env` (Merge, bestehende Werte/Kommentare bleiben erhalten, `chmod 600`),
- `config/agent.json` (Zeitzone),
- legt `config/`, `data/`, `data/logs/` an,
- synchronisiert die Workflow-**Labels** ins Repo,
- führt abschließend `doctor` aus und bestätigt den konfigurierten
  Dashboard-Authentifizierungsmodus, ohne Credentialwerte auszugeben.

> Im Legacy-Modus liegt der API-Key ausschließlich in der geschützten `.env`
> (`SAMUEL_API_KEY`). Der Wizard zeigt seinen Wert weder einmalig noch später
> an. Für die Weitergabe an einen berechtigten Client ist ein getrennter
> geschützter Operatorweg erforderlich (#838).

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

Der normale Dashboardprozess startet immer im Modus `production`. In diesem
Modus lehnt der Server Setup-, Settings-, Featureflag- und Promptänderungen mit
`configuration_frozen` ab, bevor ein Dateischreibzugriff oder ein
prozesslokaler Override erfolgt. API-Key oder eine spätere Administratorrolle
heben diese Grenze nicht auf. Die Hinweise in Einrichtung und Einstellungen
nennen denselben Ablauf: Produktionsdienst stoppen, dieselbe Konfiguration
im lokalen Setupmodus ändern, Setup beenden, Produktionsruntime neu erzeugen
und gespeicherten/wirksamen Stand samt Produktions-Freeze prüfen.

Für eine operatorgeführte Änderung den Produktionsdienst stoppen, dieselbe
externe Konfiguration vorübergehend schreibbar einbinden und einen getrennten
lokalen Setup-Prozess starten. Bei einer lokalen Installation genügt:

```bash
samuel dashboard --host 127.0.0.1 --configuration-mode setup
```

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

Die Setup-Override-Datei bindet die beiden Operator-Konfigurationsquellen
gezielt mit `rw` ein; Daten und Workspaces bleiben dieselben. Der anschließende
Produktionscontainer importiert die gespeicherte `SAMUEL_ENV_FILE` erneut und
bindet weiterhin nur `config` read-only ein. Dadurch gibt es weder Hot-Reload
noch einen zweiten Settingsstore.

Der Setup-Writer ersetzt Dateien regulär über einen gestagten atomaren Rename.
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
gespeicherten JSON-/Prompt-Konfiguration, den beim Prozessstart wirksamen
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
nicht. Bei `required=true` blockiert die zugehörige Extensionaktion, solange
der Consumer deaktiviert, nicht vorhanden oder nicht exakt kompatibel ist.
Contractdateien und Credentials werden getrennt provisioniert; der erste
Contract benötigt selbst keine Credentials. Siehe
[Extension-Datenvertrag](EXTENSION_CONTRACT.md).

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
in der Ausgabe. Vor dem Cutover alle Browser-, Skript- und Monitoringclients
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

Ein State-Restore widerruft alle Sessions und Automation-Token und setzt
`recovery_pending`. Nach Restore/Reconcile führt der lokale Operator aus:

```bash
samuel identity recover --username admin \
  --password-file /run/samuel-admin-password \
  --reason "operatorgeführte Wiederherstellung nach geprüftem Restore" --json
```

### 4.5 Ganz manuell (ohne Wizard)

```bash
cp .env.example .env
# Werte eintragen, dann:
samuel setup-labels   # Labels anlegen
```

---

## 5. LLM-Provider einrichten

Der Wizard sammelt **bewusst keine** LLM-Keys (kommt im Dashboard-Wizard,
geplant). Aktuell:

1. **API-Key in die `.env`** eintragen (Provider → Env-Variable):

   | Provider | Env-Variable | Hinweis |
   |---|---|---|
   | DeepSeek | `DEEPSEEK_API_KEY` | Cloud |
   | Anthropic | `ANTHROPIC_API_KEY` | braucht `[llm]`-Extra |
   | Gemini | `GEMINI_API_KEY` | Cloud |
   | OpenAI | `OPENAI_API_KEY` | braucht `[llm]`-Extra |
   | OpenRouter | `OPENROUTER_API_KEY` | Gateway, 350+ Modelle |
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
   Per-Task-Overrides liegen ausschließlich in `config/llm/defaults.json`.
   `config/llm/providers.json` ist nur der Provider-/Key-Metadatenkatalog und
   ueberschreibt weder Provider noch Modell zur Laufzeit. Die vollstaendige
   Prioritaet steht in `docs/README_technical.md` unter
   *LLM-Konfiguration: Zustaendigkeit und Prioritaet*.
   Dashboard-Änderungen werden sofort korrekt angezeigt; neue Adapterketten
   greifen nach dem transparent gemeldeten Agent-Neustart.

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
blockieren vor Wizard, erstem Auditwrite, Providerprobe oder Planning. Der
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

`doctor` endet mit `✅ N  ⚠️ N  ❌ N`. Kein `❌` belegt nur die darin
ausgeführten Operator-/Repositoryprüfungen. Es ersetzt weder eine externe
Provider-Liveprobe noch Audit- oder Release-Qualification. Die Webhook-Zeile
prüft nur, ob `SLICE_HMAC_KEY` konfiguriert ist. Sie beweist weder die
Signaturprüfung einer empfangenen Nachricht noch eine native SCM-Delivery.

`doctor` und `health` prüfen Produkt-/Buildidentität, lokale Pfade und
Dateisystem, wirksame Konfiguration, vorhandene Runtimecredentials,
SCM-Erreichbarkeit sowie — nur bei lesbarem Admin-Endpunkt — den Branchschutz.
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

`samuel setup` und der Dashboard-Wizard schreiben genau einen expliziten
Soll-Kontext. `samuel doctor` zeigt Wert und Quelle (`konfiguriert` oder
`ausgelieferter Default`), liest die Regel über die Gitea-API und verlangt
exakte Gleichheit. Ein leerer beziehungsweise mehrzeiliger Konfigurationswert,
fehlender Lesezugriff, eine fehlende Regel und jede Abweichung sind
Release-Blocker; es gibt kein Ableiten aus der beobachteten Regel, keine Liste
und keinen Wildcard-Abgleich. Das Lesen dieses Admin-Endpunkts benötigt
Repository-Admin-Recht; die normalen S.A.M.U.E.L.-Laufzeitfunktionen benötigen
weiterhin nur Write. Für die Freigabeprüfung kann der Operator den Doctor daher
gezielt mit einem kurzlebigen entsprechend berechtigten Token ausführen, ohne
diesen als dauerhafte Runtime-Berechtigung zu verwenden.

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
`samuel resume list --json`, danach `inspect`, `attempt`/`resume` oder ein
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

**Docker:**
```bash
SAMUEL_BUILD_VERSION="$(samuel --version | awk '{print $2}')" \
SAMUEL_BUILD_REVISION="$(git rev-parse HEAD)" \
SAMUEL_BUILD_SOURCE_URL="$(git remote get-url origin)" \
docker compose up -d        # importiert Env, mountet config (ro), data und workspaces getrennt
```

Compose importiert `SAMUEL_ENV_FILE` beim Containerstart. Die Produktionsroute
bindet sie nicht als `/app/.env` ein; damit kann sie mit restriktiven
Hostrechten verbleiben und wird nicht in das Image kopiert. Nur der explizite
Setup-Override bindet sie vorübergehend schreibbar ein.

`./data` ist damit Teil des Betriebsvertrags und muss als zusammenhängendes
lokales Volume gesichert und wiederhergestellt werden; ein Container-Neustart oder
Imagewechsel darf es nicht ersetzen.

`./workspaces` wird separat nach `/samuel-workspaces` gemountet. Es ist
kein Backupbestandteil: aktive Bäume sind Laufzeitressourcen, Quarantänen
kurzlebige Operator-Evidence. Vor Containerersatz `samuel workspace list
--json` ausführen; unresolved Quarantänen nicht still mit dem Volume löschen.

`.dockerignore` schließt `.env`, Git-Metadaten, lokale Daten, Tests und
Build-Artefakte aus; der Dockerfile kopiert nur Paket- und ausgelieferte
Default-Konfiguration. Das Basisimage sowie Runtime- und Buildabhängigkeiten
sind durch `containers/lock-policy.json` und die beiden
`requirements-container*.lock`-Dateien digest-/hashgebunden. Der dort
deklarierte unveränderliche Debian-Snapshot bindet außerdem die exakte
Git-Systempaket- und Runtime-Version. Die drei
Build-Werte landen als OCI-`version`/`revision`/`source`, die vollständige
Revision zusätzlich in der Runtime-Buildanzeige. `v2.0.0a2` besitzt historisch
kein Container-Image; `v2.0.0a3` war der erste nach #555 veröffentlichte
Containerstand und `v2.0.0a5` blieb nach fehlgeschlagenem Required-Smoke
unveröffentlicht. Für den aktuellen unterstützten Alpha-Stand
`v2.0.0a15` ist ausschließlich das Feld `container.reference` aus dem an
Gitea-Prerelease #29 angehängten
`release-manifest.json` die unveränderliche `linux/amd64`-Authority:

```bash
SAMUEL_IMAGE='<container.reference aus release-manifest.json>' \
docker compose pull samuel
SAMUEL_IMAGE='<dieselbe container.reference>' \
docker compose up -d --no-build samuel
```

Vor dem Start müssen Manifest-Tag `v2.0.0a15`, Manifest-Commit
`5d3c3ff6c17f2d3510b5da8a3451e088bd253fed`, Artefaktprüfsummen und
`container.reference` gemeinsam geprüft werden. Ein lesbarer Image-Tag oder
ein lokaler Cache ersetzt diese Bindung nicht.

Der danach veröffentlichte Stand `v2.0.0a8` darf trotz vorhandenem Manifest
nicht für eine unterstützte Installation gewählt werden: Der unabhängige
#658-D0-Lauf wies nach, dass sein Image vor Planning wegen fehlendem `git`
blockiert (#727). Ein korrigierter Nachfolger wird erst nach erneutem realen
Installations-, Positiv- und Negativnachweis hier als neuer Stand eingetragen.

`v2.0.0a9` beseitigte den fehlenden Git-Pfad, zeigte im realen D0-Nachlauf
aber die Findings #690 und #756. a10 scheiterte am widersprüchlichen
Runner-Prompt, a11 an #767, a13 an einer unvollständigen Run-Projektion und
a14 an einer unerwünschten Labels-Transition. Diese Stände bleiben
unveränderliche Fehlerevidence. a15 korrigiert die Replan-, Projektions- und
Labelgrenzen und bestand den frischen Installations-, Golden- und
Blockiernachweis. Sein Schema-2-Manifest bindet das OCI-Digest
`sha256:7fcb934da024a2418db681588f86fd864826c34b840124e59cbdbee398eb8167`;
Manifest, Commit und alle vier Asset-Hashes müssen gemeinsam geprüft werden.

Die aktuelle Registry ist interne Betreiberinfrastruktur und verwendet HTTP;
Docker muss sie deshalb vor Pull/Start ausdrücklich als interne Registry
zulassen. Andere Installationen setzen `SAMUEL_IMAGE` auf die entsprechende
OCI-Registry und benötigen keine Gitea-spezifische Produktänderung. Der
Betreiberablauf steht in
[`CONTAINER_RELEASE_OPERATIONS.md`](CONTAINER_RELEASE_OPERATIONS.md).

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
  nicht die Vollständigkeit des primären Logs.
- **Bind-Adresse:** Für nicht-öffentliche Hosts `DASHBOARD_HOST=127.0.0.1`
  setzen oder hinter Reverse-Proxy/Firewall betreiben.
- **`.env`** enthält Secrets → `chmod 600` (der Wizard setzt das).
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
   Planvalidierung direkt fort.
4. SAMUEL übernimmt danach Code → commitgebundene Gates → PR. Die passive
   Evaluation beobachtet anschließend die vollständige Gate-Evidence, trifft
   aber keine Freigabeentscheidung. Fortschritt im Dashboard (Tabs *Workflow*,
   *LLM Quality*, *Activity*).

---

## 12. Update / Troubleshooting / Deinstallation

### 12.1 Ehrliche Updategrenze der Alpha-Serie

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

Der Wizard wird bei einem Update **nicht** erneut ausgeführt. Neue notwendige
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
vollständige Funktionsabnahme für a15 ist im realen #658-Lauf gebunden und
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
- **Branch-Protection (Release) ❌:** Regel mit Repository-Admin-Recht prüfen
  und gemäß Abschnitt 8 auf den vom Doctor angezeigten Soll-Kontext
  korrigieren. Ohne lesbaren, exakten Nachweis gibt der Doctor keine
  Release-Freigabe; normale Laufzeitfunktionen bleiben davon getrennt mit
  Write-Recht nutzbar.
- **LLM ⚠️:** Key in `.env`, Provider in `config/llm.json`, `Test-Connection`.
- **Dashboard startet wegen Auth nicht:** im Legacy-Modus `SAMUEL_API_KEY`
  setzen; für den lokalen Modus zuerst den unten beschriebenen Bootstrap und
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
