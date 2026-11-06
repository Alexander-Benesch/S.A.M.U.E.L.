# Container-Release-Betrieb

Aktuelle Verfahren und Grenzen stehen in den Fachabschnitten dieser Anleitung.
Frühere Releases und Attempts sind über die erhaltenen Anker im
[historischen Originalbestand](archive/reader-history-2026-10-11/CONTAINER_RELEASE_OPERATIONS.md) erreichbar.
a15 ist keine aktuelle Installationsreferenz oder Supportempfehlung; spätere
Erfolge ändern seine Teilnachweise und fehlende vollständige Human-Merge-Abnahme nicht.


## Aktueller Testrelease v2.0.0a29 — 09.10.2026

PR #989 und #980 sind menschlich gemergt und in a29 veröffentlicht.
Main-/Tag-CI, sieben gebundene Assets, OCI-Publisher-Smoke, frische
Draft- und Published-Erstinstallation sowie der erneute Asset-Readback sind PASS.
[Exakte Releasebindung und offene Nachweisgrenzen](status/CURRENT_PRODUCT_STATUS.md#veröffentlichter-installationsstand-v200a29--09102026).
Nur saubere neue Alpha-Testinstallationen; kein Golden-/D0- oder Isolations-PASS.


## #988/#989 und #980: in a29 veröffentlichter Umfang

H1 ist zur Umsetzung freigegeben: der vorhandene lokale Referenzworkflow erhält
mit `samuel-container project` eine registrierte Sourcebereitstellung.
[Installationsablauf und Alpha-Nachweisgrenzen](INSTALL.md#registrierter-lokaler-oci-projektbestand-988)
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

Für #989 sind nur saubere neue Alpha-Testinstallationen vorgesehen. Keine
Cross-Release-Checkpointmigration, kein Upgrade-/Downgradevertrag. Die neue
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
Configwerten gilt genau die [kanonische Preserve/Replace/Reject-Matrix](INSTALL.md#corewechsel-frische-installation-und-selektiver-restore-985).
Das veröffentlichte First-install-Kit ist kein In-place-Updater. Ein neuer
Auditkey darf keine bereits geschriebene alte Kette übernehmen; ein vollständiger
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
Operatoraufrufe und Grenzen: [INSTALL.md](INSTALL.md#oci-pythonpytest-toolchain-und-separater-doctor-prüfer-978).

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

Der neue Benutzerpfad steht in [INSTALL, Abschnitt 9.1](INSTALL.md#91-oci-erstinstallation-auf-einem-leeren-docker-host-970):
verifiziertes Manifest und OCI-Kit → ausgelieferter `samuel-container install`
mit nativem CLI-Setup und writable Override → authentisiertes Setup-Dashboard
→ explizites `samuel-container start` mit Config read-only. Der Bootstrap verwendet Defaults und UID/GID aus dem tatsächlich
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

Ein neues Manifest veröffentlicht keinen automatischen Updateauftrag. Vor
einem manuellen Digestwechsel werden reguläre Dienste gestoppt, offene
Workspaces/Resume-Zustände inspiziert und das Data-Volume über die
SQLite-Backup-API (`samuel retention backup --json`) gesichert. Das neue Image
wird ausschließlich über seine
Manifest-Digest-Referenz gestartet; Version, vollständige Revision,
Docker-Health und Dashboard-Buildstatus müssen übereinstimmen.

`/app/data`, `/samuel-workspaces`, Operator-`.env` und gemountete
Konfiguration werden weder in das Image kopiert noch beim Pull ersetzt.
ADR-0706 bindet die Preserve-/Replace-/Reject-Grenze; der reale a9→a10-Drill
belegte sie für genau diesen Digestwechsel. Daraus folgt weder eine allgemeine
Schema-/Migrationszusage noch ein vollständig qualifizierter
Copy-paste-Kundenupdateweg für beliebige Versionen. Es gibt keinen stillen
Fallback auf einen älteren Image-Tag.

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

Lockänderungen erfolgen in einem normalen Review-PR. Benötigt werden exakt
`uv 0.12.6`, Python 3.12 und ein bewusst gewählter UTC-Cutoff:

```bash
python -m pip install 'uv==0.12.6'
python tools/update_container_locks.py \
  --exclude-newer 2026-08-27T14:05:00Z
python tools/container_release.py check
```

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
Der folgende normale Publisher-/Create-only-/Smoke-/Manifestvertrag bleibt
unverändert; die bedingte Golden-D0-Zweckbindung erteilt jetzt keinen D0-Claim.


Voraussetzungen sind ein sauberer Checkout des annotierten Produkt-Tags auf
dem identischen `origin/main`-Commit, eine grüne Tag-CI, frische Wheel-/sdist-
Artefakte und eine lokale Compose-Umgebungsdatei mit den für den Health-
Start nötigen Operatorwerten. Der persönliche Package-Owner stellt für den
kontrollierten Releasehost eine eigene Credential mit `write:package`, aber
ohne weitere Write-Scopes aus. Sie wird weder aus `SCM_TOKEN` übernommen noch
als Argument übergeben:

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
python -m build --outdir "$release_dist"
python tools/verify_distribution_license.py "$release_dist"

python tools/container_release.py publish \
  --dist-dir "$release_dist" \
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
3. `linux/amd64` ohne Cache aus dem digestgebundenen Basisimage bauen.
4. OCI-Labels, Runtime-Version, vollständigen Commit und ausgeschlossene
   lokale Dateien im Image prüfen.
5. Tag einmalig pushen und das Registry-Digest auflösen.
6. Das gepushte Digest mit einem frischen Compose-Projekt, temporärem
   Datenverzeichnis, gemounteter Konfiguration und Operator-`.env` starten;
   Docker-Health und Dashboard-Buildstatus prüfen.
7. Erst danach `release-manifest.json` auf Schema 2 erweitern und Image,
   Digest, Plattform, Basisdigests und Runtime-Lockdigest eintragen.

Das resultierende Manifest wird zusammen mit Wheel und sdist an das Release
des unveränderten Tags angehängt. Nutzungsdokumentation nennt ausschließlich
die `image@sha256:...`-Referenz aus diesem Manifest. Der lesbare Image-Tag ist
ein Suchschlüssel, keine unveränderliche Installationsauthority.

## Abbruch und Wiederaufnahme

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
    --dist-dir "$RELEASE_DIST" \
    --tag "$RELEASE_TAG" \
    --commit-ref origin/main \
    --image-repository "$REGISTRY_HOST/$REGISTRY_OWNER/samuel" \
    --source-url "$CANONICAL_SOURCE_URL" \
    --compose-env-file "$OPERATOR_ENV_FILE" \
    --publisher-api-url "$GITEA_URL" \
    --publisher-user "$REGISTRY_OWNER" \
    --release-host-id "$RELEASE_HOST_ID"
  ```

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
