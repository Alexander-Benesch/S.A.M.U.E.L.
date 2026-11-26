# S.A.M.U.E.L. installieren und einrichten

Diese Anleitung gilt für eine neue Testinstallation der öffentlichen Alpha **v2.0.0a42**. Für einen Linux-Server empfehlen wir das fertige Docker-Image. Wer S.A.M.U.E.L. ohne Docker ausführen oder am Quellcode arbeiten möchte, kann dieselbe Version manuell mit Python installieren. [Release und Downloads auf GitHub](https://github.com/Alexander-Benesch/S.A.M.U.E.L./releases/tag/v2.0.0a42)

<a id="91-oci-erstinstallation-auf-einem-leeren-docker-host-970"></a>

## Öffentliche Alpha auf einem Docker-Host installieren

**Empfohlen.** Du brauchst einen Linux/amd64-Host mit Docker Engine ab 26, dem Compose-Plugin ab 2.26, Internetzugang und `sudo`. Mit `docker version` und `docker compose version` kannst du die vorhandenen Versionen prüfen. Öffne auf dem Zielhost ein interaktives Terminal und führe in einem eigenen Verzeichnis diesen Befehl aus.

```bash
curl --proto '=https' -fsSL https://github.com/Alexander-Benesch/S.A.M.U.E.L./releases/download/v2.0.0a42/samuel-install.sh -o samuel-install.sh && sudo bash samuel-install.sh
```

Der Installer prüft die signierten Release-Dateien und lädt das öffentliche Image `ghcr.io/alexander-benesch/samuel:v2.0.0a42` anhand seines Digests. Dafür brauchst du weder ein GitHub-Konto noch eine Registry-Anmeldung.

### Was du im Terminal eingibst

| Anzeige | Was du eingibst und warum |
|---|---|
| `[sudo] password for …:` | Falls Linux fragt, gib dein Linux-Passwort ein, damit der Installer Docker und die Systemverzeichnisse einrichten kann. Die Eingabe bleibt unsichtbar. |
| `Freier Dashboard-Hostport:` | Erscheint bei einem belegten Port. Wähle einen freien TCP-Port auf dem Dockerhost, beispielsweise `7780`. Du kannst ihn auch beim Start vorgeben, etwa mit `sudo bash samuel-install.sh --port 7780`. |
| `Neues Dashboard-Passwort:` / `Dashboard-Passwort wiederholen:` | Wähle für dein Dashboard-Konto `admin` ein Passwort mit 12 bis 1024 Zeichen und gib es zweimal verdeckt ein. Bei einem Fehler fragt der Installer erneut. |

Die Meldungen über Bootstrap, Download und Signaturprüfung verlangen keine Eingabe. Der erste Download kann mehrere Minuten dauern. Während der Wartungsprüfung kann die erste Antwort bis zu 180 Sekunden dauern. `SCM not configured` ist an dieser Stelle zu erwarten. Das Repository wird später im Dashboard eingerichtet.

Bei einer Unterbrechung während der Kontoaufnahme denselben a42-Installer erneut starten. Er prüft die begonnene Einrichtung und übernimmt Konto und Port. Erkennt er vorhandene Daten ohne passende Installationskennung, nennt er den betroffenen Pfad und hält an. Das beim Start angezeigte, nur für root lesbare Protokoll unter `/var/log/samuel-install.*.log` enthält Phasen und Ergebnis.

### Das Setup-Dashboard öffnen

Warte auf `setup runtime ready`. Die folgenden Beispiele verwenden den Standardport. Wenn du einen anderen gewählt hast, nutze den ausgegebenen SSH-Befehl und die angezeigte Adresse. Docker veröffentlicht den Dashboard-Port auf dem Zielhost unter `127.0.0.1:7777`. Auf diesem Host öffnest du `http://127.0.0.1:7777` direkt.

**Bei einem entfernten Dockerhost** den folgenden Befehl auf deinem Arbeitsplatz ausführen. Ersetze `BENUTZER@HOST` durch denselben SSH-Zugang, mit dem du auf den Dockerhost kommst.

```bash
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:17777:127.0.0.1:7777 BENUTZER@HOST
```

Lass den Tunnel geöffnet und rufe auf dem Arbeitsplatz `http://127.0.0.1:17777` auf. SSH muss auf dem Dockerhost erreichbar sein und TCP-Portweiterleitung erlauben. Die bestehende Docker-Portbindung genügt. Ist `17777` auf deinem Arbeitsplatz belegt, wähle einen freien lokalen Port und verwende ihn auch in der Browseradresse. Melde dich mit deinem neuen Dashboard-Konto an.

## Manuell aus dem Quellcode installieren

**Ohne Docker.** Du brauchst Linux, Git, Python ab 3.12 mit `venv` und `pip` sowie Internetzugang für die Python-Pakete. Führe die Befehle als normaler Benutzer aus. Wähle ein Arbeitsverzeichnis, in dem es noch kein Unterverzeichnis `samuel` gibt.

```bash
git clone --branch v2.0.0a42 --depth 1 https://github.com/Alexander-Benesch/S.A.M.U.E.L..git samuel
cd samuel
bash ./install.sh
source .venv/bin/activate
samuel --version
```

Erwartete Ausgabe: `samuel 2.0.0a42`. Das Skript installiert S.A.M.U.E.L. in die virtuelle Umgebung dieses Checkouts und initialisiert die lokale Konfiguration.

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

**Docker mit dem öffentlichen Installer.** Lass das Installer-Terminal geöffnet und melde dich als `admin` im Dashboard an.

1. Wähle Gitea oder GitHub und gib das Repository als `Eigentümer/Projekt` sowie den zugehörigen Zugang ein.
2. Lass **Branch** leer für den Standardbranch des Repositorys. Für einen anderen Entwicklungszweig trägst du dessen Namen ein.
3. Wähle den Modellanbieter und gib dessen Zugang und Modell an. **Prüfen und starten** prüft die Verbindungen und klont das Projekt. Die genaue Revision wird automatisch ermittelt. Das Projekt liegt auf dem Dockerhost unter `/srv/samuel/project`.
4. Der Installer startet den Betriebscontainer und prüft dessen Zustand. Dashboard-Adresse und Anmeldung bleiben gleich. Falls das Terminal während der Eingaben im Browser geschlossen wurde, starte denselben Installer erneut. Er prüft den eingerichteten Setup-Container, startet ihn bei Bedarf und zeigt die Adresse, sobald die Anmeldung erreichbar ist.

- **Manuell:** Speichere die Konfiguration und beende das Setup-Dashboard mit `Strg+C`. Starte im selben Checkout mit aktivierter virtueller Umgebung `samuel dashboard --configuration-mode production --host 127.0.0.1 --port 7777`.

Einzelheiten zu Projektpfaden, Berechtigungen, Branchschutz, Diensten und Fehlerdiagnose stehen in der [technischen Betriebsreferenz](INSTALL_REFERENCE.md).

<!-- oci-first-install:start -->
<details>
<summary>Was der Docker-Installer auf dem Host ausführt</summary>

Der Installer verwendet die unveränderliche Image-Referenz aus `container.reference` im signierten Manifest. Das mitgelieferte Werkzeug `samuel-container` übernimmt die Einrichtung einschließlich `samuel setup`. Compose startet mit `--no-build` aus dem geprüften Image.

</details>
<!-- oci-first-install:end -->
