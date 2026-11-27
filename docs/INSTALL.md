# S.A.M.U.E.L. installieren und einrichten

Diese Anleitung gilt für eine neue Testinstallation der öffentlichen Alpha **v2.0.0a43**. Für einen Linux-Server empfehlen wir das fertige Docker-Image. Wer S.A.M.U.E.L. ohne Docker ausführen oder am Quellcode arbeiten möchte, kann dieselbe Version manuell mit Python installieren. [Release und Downloads auf GitHub](https://github.com/Alexander-Benesch/S.A.M.U.E.L./releases/tag/v2.0.0a43)

<a id="91-oci-erstinstallation-auf-einem-leeren-docker-host-970"></a>

## Öffentliche Alpha auf einem Docker-Host installieren

**Empfohlen.** Du brauchst einen Linux/amd64-Host mit Docker Engine ab 26, dem Compose-Plugin ab 2.26, Internetzugang und `sudo`. Mit `docker version` und `docker compose version` kannst du die vorhandenen Versionen prüfen. Öffne auf dem Zielhost ein interaktives Terminal und führe in einem eigenen Verzeichnis diesen Befehl aus.

```bash
curl --proto '=https' -fsSL https://github.com/Alexander-Benesch/S.A.M.U.E.L./releases/download/v2.0.0a43/samuel-install.sh -o samuel-install.sh && sudo bash samuel-install.sh
```

Der Installer prüft die signierten Release-Dateien und lädt das öffentliche Image `ghcr.io/alexander-benesch/samuel:v2.0.0a43` anhand seines Digests. Dafür brauchst du weder ein GitHub-Konto noch eine Registry-Anmeldung.

### Was du im Terminal eingibst

| Anzeige | Was du eingibst und warum |
|---|---|
| `[sudo] password for …:` | Falls Linux fragt, gib dein Linux-Passwort ein, damit der Installer Docker und die Systemverzeichnisse einrichten kann. Die Eingabe bleibt unsichtbar. |
| `Anmeldename [admin]:` | Mit Enter übernimmst du `admin`. Du kannst einen eigenen Namen für die Anmeldung am Dashboard eingeben. |
| `Freier Dashboard-Hostport:` | Erscheint bei einem belegten Port. Wähle einen freien TCP-Port auf dem Dockerhost, beispielsweise `7780`. Du kannst ihn auch beim Start vorgeben, etwa mit `sudo bash samuel-install.sh --port 7780`. |
| `Neues Dashboard-Passwort:` / `Dashboard-Passwort wiederholen:` | Wähle für dein Dashboard-Konto ein Passwort mit 12 bis 1024 Zeichen und gib es zweimal verdeckt ein. Bei einem Fehler fragt der Installer erneut. |

Die Meldungen über Bootstrap, Download und Signaturprüfung verlangen keine Eingabe. Der erste Download kann mehrere Minuten dauern. Während der Wartungsprüfung kann die erste Antwort bis zu 180 Sekunden dauern. `SCM not configured` ist an dieser Stelle zu erwarten. Das Repository wird später im Dashboard eingerichtet.

Bei einer Unterbrechung denselben Installer erneut starten. Er übernimmt Kontonamen und Port aus der begonnenen Einrichtung.

Bei einem Abbruch steht der genaue Pfad zum **Installationslog** in der letzten Terminalmeldung. Öffne diese Datei auf dem Dockerhost mit `sudo less /var/log/samuel-install.XXXXXXXX.log` und ersetze den Beispielpfad durch den angezeigten Pfad. Das Log enthält die Installationsphasen, den Abbruchgrund, verfügbare technische Fehlerursachen und den Exitcode. Jeder Aufruf erhält eine eigene Datei. Passwörter, Tokens und Terminaleingaben werden nicht mitgeschrieben.

### Das Setup-Dashboard öffnen

Warte auf die Ausgabe „3. Dashboard öffnen“. Die folgenden Beispiele verwenden den Standardport. Wenn du einen anderen gewählt hast, nutze den ausgegebenen SSH-Befehl und die angezeigte Adresse. Docker veröffentlicht den Dashboard-Port auf dem Zielhost unter `127.0.0.1:7777`. Auf diesem Host öffnest du `http://127.0.0.1:7777` direkt.

**Bei einem entfernten Dockerhost** den folgenden Befehl auf deinem Arbeitsplatz ausführen. Ersetze `BENUTZER@HOST` durch denselben SSH-Zugang, mit dem du auf den Dockerhost kommst.

```bash
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:17777:127.0.0.1:7777 BENUTZER@HOST
```

Lass den Tunnel geöffnet und rufe auf dem Arbeitsplatz `http://127.0.0.1:17777` auf. SSH muss auf dem Dockerhost erreichbar sein und TCP-Portweiterleitung erlauben. Die bestehende Docker-Portbindung genügt. Ist `17777` auf deinem Arbeitsplatz belegt, wähle einen freien lokalen Port und verwende ihn auch in der Browseradresse. Melde dich mit deinem neuen Dashboard-Konto an.

## Manuell aus dem Quellcode installieren

**Ohne Docker.** Du brauchst Linux, Git, Python ab 3.12 mit `venv` und `pip` sowie Internetzugang für die Python-Pakete. Führe die Befehle als normaler Benutzer aus. Wähle ein Arbeitsverzeichnis, in dem es noch kein Unterverzeichnis `samuel` gibt.

```bash
git clone --branch v2.0.0a43 --depth 1 https://github.com/Alexander-Benesch/S.A.M.U.E.L..git samuel
cd samuel
bash ./install.sh
source .venv/bin/activate
samuel --version
```

Erwartete Ausgabe: `samuel 2.0.0a43`. Das Skript installiert S.A.M.U.E.L. in die virtuelle Umgebung dieses Checkouts und initialisiert die lokale Konfiguration.

Lege im selben Terminal den ersten Administrator an. Gib sein Passwort zweimal verdeckt ein.

```bash
samuel identity bootstrap --username admin --prompt-password
```

Bei einer frischen Installation ohne vorhandene Dashboard- oder API-Clients kannst du die lokale Anmeldung wie folgt aktivieren. Starte anschließend das Setup-Dashboard.

```bash
samuel identity cutover --client-inventory-confirmed --reason "Frische Installation ohne bestehende Clients"
samuel dashboard --configuration-mode setup --host 127.0.0.1 --port 7777
```

Öffne `http://127.0.0.1:7777` und melde dich als `admin` an. Läuft S.A.M.U.E.L. auf einem anderen Rechner, öffne auf deinem Arbeitsplatz mit `ssh -N -L 7777:127.0.0.1:7777 BENUTZER@HOST` einen Tunnel zum Server. Lass das Terminal mit dem Tunnel geöffnet, während du das Dashboard benutzt.

## Das erste Projekt einrichten

1. Lege deinen Repository-Zugang und den Zugang zum Modellanbieter bereit. Öffne die ausgegebene Adresse und melde dich mit deinem Dashboard-Konto an. Auf einem entfernten Host bleibt der Installer während der Einrichtung im ersten Terminal offen, der SSH-Tunnel läuft in einem zweiten Terminal auf deinem Arbeitsplatz.
2. Gib Server und Repository an. Für `https://gitea.example.org/team/mein-projekt` ist das Repository `team/mein-projekt`. Ein leerer Branch übernimmt den Standardbranch. Beim verwalteten Dockerweg erzeugt der Installer eine eigene Arbeitskopie unter `/srv/samuel/project`; der Container sieht sie als `/projects/codebase`. Optionale Label-Synchronisation legt fehlende Labels im gewählten Repository an und braucht dort Schreibrechte.
3. Bei einer **manuellen Projektbindung** öffne ein Terminal in der Arbeitskopie und führe `git rev-parse --show-toplevel` aus. Übernimm den vollständigen Pfad, beispielsweise `/opt/meine_codebasis`. Die native Einrichtung prüft den Checkout und bei erfolgreicher SCM-Abfrage dessen Repository. Bei Docker sind Hostquelle und eingebundener Containerpfad getrennte Angaben. `PROJECT_ROOT` bezeichnet den Pfad aus Sicht der laufenden Anwendung.
4. Wähle Modellanbieter und Modell, trage den passenden Zugang ein und klicke auf **Prüfen und starten**. Beim verwalteten Weg führt der Installer die Projektprüfung und den Betriebsstart durch. Danach kannst du den Installer schließen. Für Fernzugriff bleibt der Tunnel offen. Die Anmeldung als Admin genügt für die Statusansicht.


- **Manuell:** Speichere die Konfiguration und beende das Setup-Dashboard mit `Strg+C`. Starte im selben Checkout mit aktivierter virtueller Umgebung `samuel dashboard --configuration-mode production --host 127.0.0.1 --port 7777`.

Einzelheiten zu Projektpfaden, Berechtigungen, Branchschutz, Diensten und Fehlerdiagnose stehen in der [technischen Betriebsreferenz](INSTALL_REFERENCE.md).

<!-- oci-first-install:start -->
<details>
<summary>Was der Docker-Installer auf dem Host ausführt</summary>

Der Installer verwendet die unveränderliche Image-Referenz aus `container.reference` im signierten Manifest. Das mitgelieferte Werkzeug `samuel-container` übernimmt die Einrichtung einschließlich `samuel setup`. Compose startet mit `--no-build` aus dem geprüften Image.

</details>
<!-- oci-first-install:end -->
