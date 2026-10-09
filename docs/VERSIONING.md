# Versionsrichtlinie

## Aktueller Testrelease v2.0.0a29 — 09.10.2026

PR #989 und #980 sind menschlich gemergt und in a29 veröffentlicht.
Main-/Tag-CI, sieben gebundene Assets, OCI-Publisher-Smoke, frische
Draft-Installation und erneuter Asset-Readback nach Veröffentlichung sind PASS.
[Exakte Releasebindung und offene Nachweisgrenzen](status/CURRENT_PRODUCT_STATUS.md#veröffentlichter-installationsstand-v200a29--09102026).
Nur saubere neue Alpha-Testinstallationen; kein Golden-/D0- oder Isolations-PASS.


## Historischer Installationsstand v2.0.0a28 — 08.10.2026

Prerelease #42 bindet Productcommit `e17c80ef0071a302a7dfd331b18553eb5623190c`,
annotiertes Tagobjekt `7bc086ba6609962cf51c69a415f974973d12dfd7` und erfolgreiche
Main-CI #1216 / Tag-CI #1217 einschließlich Release-Gate. PR #979 wurde
menschlich gemergt. Sieben Assets wurden bytegleich zurückgelesen.
Manifest-SHA-256: `9837bcc474a14241d08e69c72fd4e48d6fc15cfdb7d9324ea9a1ffcb9b9fb86f`.
Die vollständige `container.reference` dieses Schema-2-Manifests ist die
OCI-Installationsauthority. Ihr Image-Digest lautet
`sha256:c5cb2af616c927d273ae00d3bbadc6ab1e974ec13218f6ab434f9c4cd3c06c78`;
der Registry-Endpunkt wird aus dem heruntergeladenen Manifest übernommen.

Erster Required Publisher-Smoke und unabhängige Erstinstallationen aus Draft-
sowie veröffentlichten Assets auf je einem leeren Ubuntu 24.04.5 / Docker
29.8.2 / Compose 5.6.0 sind PASS: Setup vor SCM, authentisierte Konfiguration,
Production healthy, Identität, Persistenz, Recreate, Freeze und Secret-Check.
Das offizielle heruntergeladene Kit wird verwendet, kein Runtime-Checkout.

**#978 ist PARTIAL/FAILED, nicht abgeschlossen.** Der offizielle
credentialfreie Wheeldownload, die Offlinevorbereitung und read-only
Toolchainregistrierung sind PASS. Echte erfolgreiche und fehlgeschlagene
Pytest-Tests funktionieren; fehlende/falsche Artefaktbindungen werden
fail-closed abgelehnt. Die harte 8-Sekunden-Versionprobe ist auf der
unabhängigen VM jedoch reproduzierbar zu knapp: TIMEOUT nach 8034 ms,
weitere Proben 6907 / 7125 ms. Spätere PASSs ersetzen diesen FAIL nicht.
Der aktuelle Follow-up-PR korrigiert ausschließlich die gebundene
Versionsprobe über das vorhandene `test_timeout`, maximal 60 Sekunden.
Ungebundene Modul-Presence-Proben behalten 8 Sekunden. Die Korrektur ist
noch kein veröffentlichter Stand; sie benötigt Human Merge und einen neuen
create-only Release a29 mit eigener frischer Abnahme. a28 bleibt unverändert.

Der spätere externe Report #981 belegt den separaten Branchschutz-Leser und
Doctor mit `0 FAIL` für die dort benannte a28-Umgebung; diese Teilabnahmen sind
in #978 übernommen. Sie ersetzen weder den Timeout-FAIL der unabhängigen
langsamen VM noch eine Abnahme dieses neuen Candidates. Der tatsächliche
serverseitige Widerruf bleibt NOT_PROVEN. Gemeinsam verwendete Credentials
werden dafür nicht widerrufen. Gitea-/GitHub-/Enterprise-
Regressionen ersetzen diese reale Probe nicht. Runtimebot, Runner-/Gate-/
MANUAL-/Human-Merge-Authority bleiben bestehen; #977 bleibt analyse-only.
Installation und Technical Health sind kein Golden-/D0- oder Supportclaim.
#962 bleibt offen; der jüngste vollständig D0-qualifizierte Referenzstand
ist weiterhin nicht nachgewiesen.

GitHub Main und Wiki enthalten die bereinigte aktuelle Projektion; GitHub-a28
liefert sieben eigene Public-Assets mit separatem Publiccommit und Schema 1,
geprüftem Wheel, aber kein öffentliches OCI-Image. Native OCI-Evidence wird
nicht übertragen. Bisherige a26-/a27-Tags und Assets bleiben unverändert.
a27 ist historische Installations-Evidence ohne #978-Pfad. Frische a28-
Installationen werden unterstützt; In-Place-Migration alter Daten/Receipts
und Übernahme alter Qualification auf neue Toolchains sind nicht vorgesehen.
Quelle: Release `v2.0.0a28` und Issue #978 im konfigurierten nativen Repository.
Die öffentliche GitHub-Releaseprojektion besitzt einen eigenen Manifestvertrag.

### Artefaktbindung a28

| Asset | SHA-256 | Bytes |
|---|---|---:|
| `docker-compose.setup.yml` | `77d18cb882ac67a828d0f90b81b35fc836154c8a7353bbcbc312e9f25874b6d8` | 512 |
| `docker-compose.yml` | `e75686401b7b625b8268c56a0e86ddf2b639cc3c2528a77db0d7360993cb1327` | 1065 |
| `samuel-2.0.0a28-py3-none-any.whl` | `46c2439a754583abfdf590be78f687f0708f949ca3294c81abccdcb53c7c194b` | 997013 |
| `samuel-2.0.0a28.tar.gz` | `8451b7714420029e826d04dc4e1948430d300aaf42828aae025e0c8bd106f1a1` | 3843695 |
| `samuel-oci-2.0.0a28.tar.gz` | `348990417a4b1154208844c3235d6889908e3e5ad8f4b41ba8340ebcee29ada5` | 58237 |
| `samuel-runtime-2.0.0a28.lock` | `6a55ba2a815c7228459b7ace7ab104fc6e1fd525c737860ba0682ce3453c507f` | 51570 |


## Historischer Installationsnachweis v2.0.0a27 — 06.10.2026

Der offizielle Release bindet Productcommit
`c815eea789c14f644f25c7abacd5a8b1201f60cf` und annotiertes Tagobjekt
`ae750dcb254316b2ef5640d868e85288ad3b4bab`. PR #972, Main-CI #1102 und
Tag-CI #1103 sind erfolgreich. Die sieben zurückgelesenen Release-Dateien
umfassen Wheel, Sourcepaket, Runtime-Lock, OCI-Kit, beide Compose-Dateien und
Manifest. Manifest-SHA-256:
`429024d68722b775b25c90636a2a50427a2b1a432d891af4ec4462335afa6df7`.
Die unveränderliche `container.reference` im Manifest bindet OCI-Digest
`sha256:bdcebe2ea517e4cea9c7730f490e042918ac8ce96d616b6b160740b8226a954c`.

Die unabhängige Erstinstallation aus den **veröffentlichten** Release-Dateien
auf frischem Ubuntu 24.04.5, Docker 29.8.2 und Compose 5.6.0 ist PASS:
leere Operatorpfade, Setup vor SCM-Konfiguration, authentisierte Einrichtung,
Productionstart, Docker `healthy`, CLI-/API-/Imageidentität, Persistenz,
Recreate und Konfigurationsfreeze. Die Produktidentität stammt aus dem Image;
kein Runtime-Checkout wird als Installationsinput vorausgesetzt. Private
Registryzugänge gelten nur im Docker-Kontext des ausführenden Operators.

#970/#971 sind mit eigenen Nachweisen geschlossen. Der vollständige Bericht
und die veröffentlichten Installationsreceipts sind an den Issues angehängt.
Diese technische Installation ist **keine** Workflow-/LLM-, Golden- oder
Formal-D0-Abnahme: Operational Readiness blieb `blocked`; #962 bleibt offen.
Historische FAIL-/UNKNOWN-/Teilnachweise bleiben erhalten. a15 ist keine
aktuelle Installations- oder Supportreferenz. Für neue Installationen gilt
weiterhin der ausgewählte neueste veröffentlichte Release mit verifiziertem
Manifest gemäß [INSTALL](INSTALL.md#91-oci-erstinstallation-auf-einem-leeren-docker-host-970).

Stand: 6. Oktober 2026

Diese Richtlinie definiert die Produktversion von S.A.M.U.E.L. und grenzt sie
von den unabhängig versionierten Verträgen des Systems ab. Änderungen an der
Versionsquelle, den sichtbaren Ausgaben und dem Release-Gate erfolgen getrennt.
#489 vereinheitlichte die sichtbaren Ausgaben der Paketmetadaten.
#490 bindet einen veröffentlichten Produkt-Tag an den geprüften
Release-Commit. `v2.0.0a1` blieb nach roter Tag-CI als unveränderliche
Auditspur ohne Release bestehen. `v2.0.0a2` bestand die vollständige Tag-CI
und wurde mit manifestgebundenem Wheel und sdist als erstes Gitea-Prerelease
veröffentlicht. `v2.0.0a3` ergänzt den ersten nach #555 digest- und
lockgebunden veröffentlichten Containerstand. `v2.0.0a6` korrigiert den
Container-Smoke. `v2.0.0a7` war der erste unterstützte Alpha-Stand mit
manifestgebundenem Python- und OCI-Lieferumfang. `v2.0.0a8` wurde ebenfalls
konsistent veröffentlicht, scheiterte danach jedoch im realen D0-Zielpfad an
der im Image fehlenden Git-Runtime (#727) und ist daher nicht qualifiziert.
`v2.0.0a9` belegte im realen D0-Lauf die Findings #690 und #756 und wurde
daher nicht als unterstützt eingestuft. a10 scheiterte anschließend am
widersprüchlichen Runner-Prompt. `v2.0.0a11` bestand Installation und den
Secret-Scan-Block, scheiterte aber im Golden-Pfad an #767. a12 blieb nach
fehlgeschlagenem erstem Compose-Smoke ohne Prerelease; a13 und a14 machten
weitere reale Projektions- und Labelbefunde sichtbar. `v2.0.0a15` korrigiert
diese Grenzen; die damalige Supportdeklaration ist seit #970 keine
aktuelle Installationsreferenz mehr. Sein
frischer Install, die menschliche Planfreigabe, Required Checks und der echte
`diff_secret_scan`-Block sind belegt; der vollständige D0-PASS ist nicht
bestätigt, weil der Golden-PR entgegen der menschlichen Mergepflicht durch den
Demo-Bot gemergt wurde. `v2.0.0a16` besitzt zwar einen grünen create-only Tag und Tag-CI,
erreichte aber ohne gebundene Publishercredential weder OCI-Publish noch
Gitea-Prerelease. Tag und CI bleiben unveränderliche Auditspur; `a17` ist der
nächste eigenständige Releasekandidat und erst nach seiner eigenen realen
Qualification beurteilbar. `v2.0.0a17` ist inzwischen als Gitea-Prerelease
veröffentlicht, bleibt aber bis zu seiner eigenen gebundenen D0-Evidence ein
nicht qualifizierter Alpha-Kandidat. `v2.0.0a18` trägt den Compose-Setup-
Vertrag aus #691, erreichte nach seinem create-only OCI-Push jedoch keinen
grünen verpflichtenden Compose-Smoke und deshalb weder Gitea-Prerelease noch
Release-Manifest. Tag und Image bleiben unveränderliche Auditspur. Der neue
Kandidat `v2.0.0a19` ist dagegen vollständig veröffentlicht: Tag-CI, vier
manifestgebundene Assets, OCI-Digest und frischer Compose-Smoke sind belegt.
Er bleibt bis zu einem eigenständigen D0-Run gegen genau diesen Digest ein
nicht qualifizierter Alpha-Kandidat ohne Supportclaim. a20 und a22 bleiben
fehlgeschlagene Publishversuche mit einer auf das Demo- statt Produkt-SCM
gebundenen OCI-Source. a23 besitzt die korrekte Produkt-Source sowie belegten
OCI-Publish und Compose-Smoke, aber keinen heute belegten vollständigen
Gitea-Packagepublish. `v2.0.0a24` ist mit Tag-CI #909, Prerelease #38, vier
manifestgebundenen Assets und korrekter Produkt-Source der jüngste
veröffentlichte Kandidat seiner Lineage; sein D0-Lauf blieb unvollständig und
er ist nicht qualifiziert oder unterstützt. `v2.0.0a25` ist mit Tag-CI #928,
Prerelease #39, vier manifestgebundenen Assets, korrekter Produkt-Source und
grünem ersten Required Smoke der damalige veröffentlichte Alpha-Kandidat.
Golden-D0 und Capabilityqualifications wurden für a25 nicht ausgeführt; der
Publish begründet weder Qualification noch Support. `main` ist ein
integrierter Entwicklungsstand und wird nicht durch einen Tag oder eine
Main-CI selbst zum Release.
#488 nutzt diese echten
SCM-Anker als einzige Build-Authority der Produktversion, ohne einen
plausiblen Release-Fallback zu erfinden. Die reale #658-D0-Qualification bleibt
davon getrennt; a15 bewahrt Teilnachweise, erfüllt aber nicht den vollständigen
Human-Merge-Vertrag. Ein neuer Stand benötigt seine eigene vollständige,
subjectgebundene Qualification.

## Historischer Veröffentlichungsnachweis v2.0.0a26 — 05.10.2026

Dieser damalige Alpha-Release wurde technisch veröffentlicht: Main-CI #1165,
annotiertes Tagobjekt `09afc4781d32b19aae45c2b47fe1e3933d7d2fdc`, Produktcommit
`177243063052c03e14b7491b94750e6baa4d60cd`, vollständig grüne Tag-CI #1166,
Gitea-Prerelease #40 mit vier vollständig byteidentisch zurückgelesenen
Assets und Schema-2-Manifest. Manifest-SHA-256:
`0477005495ba29fe21fa517ec9fda3ce1daa1bb8553dcc55347e2348a6dd3c46`; linux/amd64-OCI-Digest:
`sha256:76c2efac689c6b0c098981dd531a5fa2988725339785381807e36eb6f53ce471`. Der erste frische Required Compose-Smoke
war healthy; Runtime, Git 2.47.3 und Dashboard bestätigen Version und Revision.
Die Installationsauthority ist die vollständige `container.reference` im
angehängten Manifest, keine separat rekonstruierte Registryreferenz.

Der Release dient der getrennten Erstinstallation durch den Maintainer.
Fehlende Altlastenabnahmen sind ausdrücklich keine Releaseblocker und bleiben
in #962 vertagt. Die 24 administrativen Issueabschlüsse sind kein PASS;
19 übrige Altissues bleiben unverändert. Das vollständige Testkonzept
entsteht erst nach dieser Installation. Kein Golden-/D0-/Supportclaim für a26,
keine neue Abnahmeruntime oder Workflowfreigabe. Die historischen FAIL-/UNKNOWN-/Teilnachweise bleiben erhalten. a15 ist
keine aktuelle Installationsreferenz oder Supportempfehlung (#970).

## Produktversion

S.A.M.U.E.L. verwendet die Bedeutung von `MAJOR.MINOR.PATCH` nach Semantic
Versioning und die kanonische Python-Schreibweise nach PEP 440:

| Stufe | Beispiel | Bedeutung |
|---|---|---|
| Alpha | `2.0.0a7` | Funktionsumfang und öffentliche Verträge können sich noch ändern; bekannte Release-Lücken sind zulässig und werden sichtbar geführt. |
| Beta | `2.0.0b1` | Der Funktionsumfang der 2.0-Linie steht; beworbene Kernpfade und unterstützte Installationswege sind nachgewiesen. |
| Release Candidate | `2.0.0rc1` | Keine bekannten Release-Blocker; Änderungen beschränken sich auf Validierung und Korrekturen. |
| Final | `2.0.0` | Die dokumentierten öffentlichen Verträge und die veröffentlichte Supportpolitik gelten verbindlich. |

PEP-440-Vorabkennungen enthalten keinen SemVer-Bindestrich. S.A.M.U.E.L.
behauptet daher nicht, dass `2.0.0a3` syntaktisch eine vollständige
SemVer-2.0.0-Version ist. SemVer bestimmt die Bedeutung der drei
Release-Komponenten; PEP 440 bestimmt die veröffentlichte Python-Version und
ihre Reihenfolge `aN < bN < rcN < final`.

### Änderungsregeln

- **MAJOR** steigt bei einer inkompatiblen Änderung eines veröffentlichten
  öffentlichen Vertrags.
- **MINOR** steigt bei rückwärtskompatiblen Funktionen oder Erweiterungen
  eines öffentlichen Vertrags. Eine angekündigte Deprecation wird spätestens
  hier dokumentiert.
- **PATCH** steigt bei rückwärtskompatiblen Fehler-, Sicherheits- und
  Dokumentationskorrekturen ohne neuen verpflichtenden Vertrag.
- Während einer Vorabserie wird für jeden veröffentlichten Stand die laufende
  Kennung erhöht. Ein Tag wird niemals verschoben oder durch einen neu
  gebauten Inhalt ersetzt.

Als öffentliche Verträge gelten die dokumentierte CLI einschließlich
Exitcodes, REST-Pfade und Payloads innerhalb ihrer API-Version, ausgelieferte
Konfigurations- und Workflow-Schemata, ausdrücklich dokumentierte
Plugin-/Port-Erweiterungspunkte sowie zugesagte persistierte Formate. Interne
Slices, private Attribute und nicht dokumentierte Hilfsfunktionen sind keine
öffentliche API. Eine eigene Schema-Version kann eine Migration innerhalb
einer Domäne ermöglichen; sie hebt eine dadurch verursachte inkompatible
Änderung der veröffentlichten Produktzusage nicht automatisch auf.

## Heutiger Stand und Produkt-Tags

`2.0.0-alpha` normalisierte in der früheren Paketkonfiguration zu `2.0.0a0`.
Dieser Wert und die historische Changelog-Überschrift vom 17. April 2026 sind
eine **ungetaggte Entwicklungsbaseline**, kein nachträglich behaupteter
Release. Die vorhandenen `phase-*-complete`-Tags sind historische
Projektmarker und ebenfalls keine Produkt-Releases.

Der erste formale Produkt-Tag **`v2.0.0a1`** wurde auf dem exakt geprüften
Commit annotiert und create-only angelegt. Die Tag-CI wies ihn korrekt ab,
weil `actions/checkout` den lokalen annotierten Ref im ephemeren Job durch den
direkten Commit ersetzt hatte. Der Remote-Tag wurde weder gelöscht noch
verschoben und besitzt kein Gitea-Release. Der korrigierte Stand
**`v2.0.0a2`** bestand die vollständige Tag-CI und wurde als Gitea-Prerelease
mit geprüftem Wheel, sdist und SHA-256-Manifest veröffentlicht. Er ist der
erste veröffentlichte SCM-Versionsanker, den #488 als Authority nutzt. Die
nachfolgende Vorabversion **`v2.0.0a3`** bindet zusätzlich das veröffentlichte
Container-Image an Tag, vollständigen Commit, Basis- und Lockdigests sowie den
frischen Compose-Smoke. Sie war zum damaligen Releasezeitpunkt der aktuelle
veröffentlichte Stand. Die
Wahl von Alpha ist
bewusst: Ein Tag macht einen Build reproduzierbar, erklärt aber den noch nicht
vollständig abgenommenen Funktionsumfang nicht voreilig zur Beta. Der Wechsel
zu `2.0.0b1` ist ein späteres Reife-Gate, kein bloßes Umbenennen.

Produkt-Tags haben ausschließlich die Form `v<kanonische-PEP-440-Version>`,
beispielsweise `v2.0.0a7`. Das führende `v` gehört zum Git-Tag, nicht zur
normalisierten Paket- oder Runtime-Version. Produkt-Tags sind annotiert und
unveränderlich; Tagging und Veröffentlichung bleiben eine bewusste
Maintainer-Aktion. Das Release-Werkzeug besitzt keinen Pfad zum Verschieben,
Überschreiben oder Löschen eines vorhandenen Tags.

`v2.0.0a5` bestand die Tag-CI, erreichte aber kein freigegebenes Release: Der
create-only OCI-Push gelang, der anschließende verpflichtende Compose-Smoke
schlug am nicht vorbereiteten Workspace-Bind-Mount fehl (#685). Es gibt daher
weder ein Gitea-Release noch ein Schema-2-Manifest für diesen Stand. Tag und
Image werden nicht verschoben oder überschrieben; die Korrektur erhält die
nächste Vorabkennung.

`v2.0.0a6` ist der korrigierte, vollständig veröffentlichte Folgestand.
`v2.0.0a7` enthält die danach für D0 benötigten Audit- und LLM-Fehlerkorrekturen
und war der damalige veröffentlichte sowie unterstützte Alpha-Stand. Beide
besitzen grüne Tag-CI, Gitea-Prerelease, Wheel, sdist, Schema-2-Manifest und
ein nach frischem Compose-Smoke digestgebundenes `linux/amd64`-Image.

## Release ist kein einzelner Boolean

Die folgenden Stufen haben getrennte Authority. Eine spätere Stufe darf eine
fehlende frühere Evidence nicht ersetzen:

| Stufe | Authority und Mindestnachweis | Aussage |
|---|---|---|
| Integrierter Stand | gemergter Commit auf geschütztem `main` und grüne Main-CI | entwickelbarer Quellstand, noch kein Release |
| Release-Tag | annotierter create-only Produkt-Tag auf genau diesem Commit und grüne Tag-CI | unveränderliche Auditspur; bei späterem Fehler nicht automatisch veröffentlicht |
| Python-Release | nicht als Entwurf geführtes Gitea-Prerelease mit Manifest, genau einem Wheel, sdist und versionierten Runtime-Lock; Version, Commit, Größe und SHA-256 stimmen überein | installierbare Python-Artefakte und geschlossene lokale Runtime-Abhängigkeiten dieses Tags |
| Container-Release | Schema-2-Manifest bindet Image- und Plattformdigest, Locks, OCI-/Runtime-Identität und grünen frischen Compose-Smoke | installierbares Image über `container.reference`, nicht über den lesbaren Tag |
| Reale Qualification | #658 bindet denselben veröffentlichten Digest an frischen Install, vollständigen positiven Golden Path und echten Blockierfall | belastbarer Referenzbetriebsnachweis für genau diese Version/Policy/Provider-/Toolchain-Kombination |

Aktueller Stand vom 5. Oktober 2026:

| Tag | Tag-CI | Gitea-Release | Python | OCI | #658 D0 | Einordnung |
|---|---|---|---|---|---|---|
| `v2.0.0a1` | fehlgeschlagen | nein | nein | nein | nein | unveränderliche rote Auditspur |
| `v2.0.0a2` | grün | Prerelease #9 | ja | nein | nein | erster veröffentlichter Python-Stand, abgelöst |
| `v2.0.0a3` | grün | Prerelease #10 | ja | ja | nein | erster Schema-2-Containerstand, abgelöst |
| `v2.0.0a5` | grün | nein | nein | Push ohne grünen Required-Smoke | nein | nicht freigegebene Auditspur |
| `v2.0.0a6` | grün | Prerelease #20 | ja | ja | Teilpfad | korrigierter D0-Zwischenstand, abgelöst |
| `v2.0.0a7` | grün | Prerelease #21 | ja | ja | **partial** | früherer unterstützter Alpha-Stand; durch a15 abgelöst |
| `v2.0.0a8` | grün | Prerelease #22 | ja | ja | **failed** | konsistent veröffentlicht, aber wegen fehlendem Git im realen D0-Zielpfad nicht qualifiziert (#727) |
| `v2.0.0a9` | grün | Prerelease #23 | ja | ja | **failed** | durch reale D0-Findings #690 und #756 abgelöster Qualification-Kandidat; kein Supportclaim |
| `v2.0.0a10` | grün | Prerelease #24 | ja | ja | **failed** | Runner-Prompt widersprach der wirksamen Unittest-Policy; durch a11 abgelöst |
| `v2.0.0a11` | grün | Prerelease #25 | ja | ja | **failed** | Installation und Secret-Block belegt; Golden-Pfad wegen Approval-/Re-Plan-Drift #767 nicht qualifiziert |
| `v2.0.0a12` | grün | nein | nein | Push ohne grünen ersten Required-Smoke | **failed** | unveränderliche Abbruchevidence; durch a13 ersetzt |
| `v2.0.0a13` | grün | Prerelease #27 | ja | ja | **failed** | Replan-Block real belegt; Run-Projektion blieb fälschlich `running` (#772) |
| `v2.0.0a14` | grün | Prerelease #28 | ja | ja | **failed** | terminale Projektion belegt; Labels-Projektion zerstörte `status:plan` (#776) |
| `v2.0.0a15` | grün | Prerelease #29 | ja | ja | **partial** | historische Alpha-/Supportdeklaration; keine aktuelle Installationsreferenz; technische Teilnachweise gültig, vollständiger D0-PASS wegen Bot-Merge statt vorgeschriebenem Human-Merge nicht bestätigt |
| `v2.0.0a16` | grün | nein | nein | nein | nein | grüner create-only Tag auf `9eca86e…`; ohne gebundene Publishercredential nicht veröffentlicht und nicht qualifiziert |
| `v2.0.0a17` | grün | Prerelease #31 | ja | ja | nein | abgelöster veröffentlichter Alpha-Kandidat; keine eigene gebundene D0-Evidence und kein Supportclaim |
| `v2.0.0a18` | grün | nein | nein | Push ohne grünen verpflichtenden Compose-Smoke | nein | unveränderliche Auditspur; #815 korrigiert den Befund auf `main` |
| `v2.0.0a19` | grün | Prerelease #33 | ja | ja | **failed** | veröffentlicht; anschließender D0-Lauf fehlgeschlagen, kein Supportclaim |
| `v2.0.0a20` | grün | nein | nein | ja | **failed** | OCI-Version/Revision korrekt, Source-Label auf falsches Demo-SCM gebunden; unveränderliche Fehlerevidence |
| `v2.0.0a21` | grün | Prerelease #35 | ja | ja | nein | veröffentlicht, aber nicht D0-qualifiziert und ohne Supportclaim |
| `v2.0.0a22` | grün | nein | nein | ja | **failed** | falsche Demo-Sourcebindung und fehlgeschlagener Smoke; unveränderliche Fehlerevidence |
| `v2.0.0a23` | grün | nicht belegt | nicht vollständig belegt | ja | nein | korrekte Produkt-Source, OCI-Publish und Compose-Smoke belegt; vollständiger Gitea-Packagepublish nicht belegt |
| `v2.0.0a24` | grün | Prerelease #38 | ja | ja | **incomplete** | abgelöster veröffentlichter Alpha-Kandidat; D0-Lauf unvollständig, nicht qualifiziert und ohne Supportclaim |
| `v2.0.0a25` | grün | Prerelease #39 | ja | ja | nein | früherer veröffentlichter Alpha-Kandidat; Golden-D0 und Capabilityqualifications nicht ausgeführt, nicht qualifiziert und ohne Supportclaim |
| `v2.0.0a26` | grün | Prerelease #40 | ja | ja | nein | historischer veröffentlichter Alpha-Kandidat; OCI-Erstinstallationsfindings #970; Altlastenabnahmen nach #962 vertagt, kein Golden-/D0-/Supportclaim |
| `v2.0.0a27` | grün | veröffentlicht, sieben verifizierte Assets | ja | ja | nein | OCI-Erstinstallation aus veröffentlichten Assets PASS; #970/#971 geschlossen; Workflow-/Golden-/D0-Rest nach #962 getrennt |

### Revisionsfester Nachweis des ersten Release-Ankers

Die Dachabnahme #479 wurde am 27. August 2026 gegen den integrierten
Ausgangsstand `3a4ce59021898ac70a474b894c4c81ee6c47f89e` und erneut direkt gegen
Git und Gitea geprüft. Die unveränderlichen Anker sind:

- Das annotierte Tagobjekt `v2.0.0a2` hat die Objekt-ID
  `84c909cbdb1e712a2ff2ba89ef09ac414c6c8099` und zeigt auf den Release-Commit
  `9f656f70af6cf24fc7a4119cd3db4439bbdf2a03`.
- Gitea-Run #496 lief auf exakt diesem Commit erfolgreich. Die Jobs #538
  (Python 3.10), #539 (Python 3.14), #540 (vollständige Qualitätspipeline) und
  #541 (Post-Tag-Release-Gate) sind jeweils `success`.
- Gitea-Prerelease #9 ist nicht im Entwurfszustand und enthält genau
  `release-manifest.json`, `samuel-2.0.0a2-py3-none-any.whl` und
  `samuel-2.0.0a2.tar.gz`. Ein erneuter Download ergab für Wheel
  `4bf59e5d23b45ff7d42337c5f9db87726997aa4dd0d096f6baf9ba8f74a3305d`
  und für sdist
  `d97226f33d411c09f11d38c9736580739a12d88e1ae1143f052e34bbf0439db7`;
  beide Werte stimmen mit dem Manifest überein. Beide Paketmetadaten melden
  `Version: 2.0.0a2` und `License-Expression: Apache-2.0`.
- Die Kindissues #487, #489, #490 und #488 sind geschlossen und hatten bei der
  Dachabnahme keine offenen Checkboxen. Ihre zusammengeführte Umsetzung ist
  über PR #552 / Merge `b99b5c829a06c3cc4e95fa57312b5e5b56c7e568`,
  PR #553 / Merge `cc37188bdce52c34fb74704e2571bb7d73e97218`,
  PR #560 / Merge `9f656f70af6cf24fc7a4119cd3db4439bbdf2a03` und
  PR #562 / Merge `d328ce3a65714f7d2ef9cbbdfc628c64289bc823` belegt.

Dieser Nachweis bezieht sich ausschließlich auf Produktversionierung, Wheel,
sdist und deren Release-Gate. Er behauptet kein veröffentlichtes
Container-Image; dessen Digest-, Lock- und Smoke-Vertrag bleibt vollständig
im für `v2.0.0a2` zu diesem Zeitpunkt offenen Issue #555. Die erst nach einem
Dokumentcommit entstehenden PR-,
Merge- und `main`-CI-IDs werden im datierten Gitea-Audittrail von #479
und dem zugehörigen PR festgehalten, nicht vorweggenommen.

### Revisionsfester Nachweis v2.0.0a3

- Das annotierte Tagobjekt `484efff40b706fc4b2525e16398ee08c42a09aaf`
  zeigt auf Release-Commit
  `41ee7506dd5a09f6eef4a3b71ad08276d0848911`.
- Gitea-Run #522 und seine Jobs #682–#685 waren vollständig `success`;
  eingeschlossen waren Python 3.10, Python 3.14, die Qualitätspipeline und das
  Post-Tag-Release-Gate.
- Gitea-Prerelease #10 enthält das Schema-2-Manifest, Wheel und sdist. Die
  erneut heruntergeladenen SHA-256-Werte sind im
  [Container-Runbook](CONTAINER_RELEASE_OPERATIONS.md#revisionsfester-veröffentlichungsnachweis-v200a3)
  festgehalten.
- Das Manifest bindet `v2.0.0a3`, denselben vollständigen Commit und
  `linux/amd64` an die intern archivierte Registryreferenz mit Digest
  `sha256:6a9c53ae5ba554a5b000e140f3a0929447984f230c9e50a1e5ce9c07d06dc5f6`;
  private Registryhost-/Ownerwerte sind Betreiberkonfiguration.
  Ein frischer Compose-Start genau dieses Registry-Digests war `healthy`; der
  Dashboard-Buildstatus meldete dieselbe Produktversion und Revision.

Der Nachweis erweitert die Releasekette, ändert aber weder die historische
Liefergrenze von `v2.0.0a2` noch die create-only Regel für Tags und Images.

### Revisionsfester Nachweis v2.0.0a6 und v2.0.0a7

Der Live-Abgleich vom 1. September 2026 bestätigt die beiden späteren
Schema-2-Releases:

- `v2.0.0a6`: annotiertes Tagobjekt
  `3643f5e414cb1911303e5bea68316e7a46172ffb`, Commit
  `a66fe427ba6531e883ffa0810a3b2991dd6facbb`, vollständig grüne Tag-CI,
  Gitea-Prerelease #20 und Manifest-SHA-256
  `1faaad5d71f681df36a4265d5b06688283b28627cd6d8a247678632af8e3c694`.
  Das Manifest bindet Wheel
  `0f00989e58a31a4211a857cf889899e0c0c3d65ad0fc4dd7ec5c575b9d2e8506`,
  sdist
  `d3618d722d62d0c879370164f6437c42e294cb7a66f67a7075bcf49aa440f2ae`
  und OCI-Digest
  `sha256:6423102eca698d230acfc593ced724b44a19dae0c4e68cabad4094992439b838`.
- `v2.0.0a7`: annotiertes Tagobjekt
  `e6912d0d4b8db6f95f8e6ec975f5b8a50ab226bf`, Commit
  `d4000e94edc70f68190bf30b16cff5cbbbf2d143`, vollständig grüne Tag-CI,
  Gitea-Prerelease #21 und Manifest-SHA-256
  `9e4e7a61a16f76c143c96b4863a0de0896db0c924ca9e025cf6466f8dcac415d`.
  Das Manifest bindet Wheel
  `2235a6121063823973b713980b124b13ce3587056d16da504dd4d8e8d682f38c`,
  sdist
  `017128f4627885a1db8e3c8bfc3edda336afe2066bfbf9b4d998a6f862f49758`
  und OCI-Digest
  `sha256:6083b5045288ce84a6162966d3126eca10bd0b71aff545deb30b038994bb1653`.

Diese Nachweise autorisieren nur die jeweils genannten Releaseartefakte.
Prerelease #21 weist selbst darauf hin, dass die D0-Qualification bis zum
erneuten Lauf im unabhängigen Demo-Repository offen bleibt. Der
Capability-Matrix-Status `partial` wird deshalb nicht aus dem Releaseerfolg
hochgestuft.

### Revisionsfester Nachweis v2.0.0a8 und D0-Abbruch

`v2.0.0a8` besitzt das annotierte Tagobjekt
`4cce7c8eda85a9cad214763564c1aefe4c7c9914` auf Commit
`1b7dee9affff4358fe10de868a0a9bbddd7a2931`, den vollständig grünen
Gitea-Tag-Run #711 und Gitea-Prerelease #22. Das erneut heruntergeladene
Manifest hat SHA-256
`b4bbda9270552eef8ca174048c7dc3625ef169474eb76482b30d2acd18ba05af`;
es bindet das OCI-Digest
`sha256:d726acb8064c59a548b8f7b1aa0ccfdd1209049d98b2ce9bb333986115f07aea`.

Diese Veröffentlichung ist kein positiver D0-Nachweis. Der anschließende
frische Lauf im unabhängigen Zielrepository blockierte vor Planning mit
`workspace_git_failed`, weil das Runtime-Image die vom ausgelieferten
Worktree-Adapter vorausgesetzte Git-Runtime nicht enthielt (#727). Der
create-only Stand bleibt als überprüfbare Auditspur erhalten, darf aber weder
überschrieben noch als unterstützte Installation empfohlen werden. Die
Korrektur und der vollständige D0-Nachlauf benötigen eine neue Vorabversion
und einen neuen Digest.

### Revisionsfester Veröffentlichungsnachweis v2.0.0a9

`v2.0.0a9` besitzt das annotierte Tagobjekt
`766c2b41a9afe50324ff97bae2a35a1fa8612760` auf Commit
`ffe709cfe14d69e2f8bd8233e6066eb6972ef8f3`. Gitea-Tag-Run #753 bestand
Python 3.10, Python 3.14, die vollständige Qualitätspipeline und das
Post-Tag-Release-Gate. Gitea-Prerelease #23 enthält genau vier erneut
heruntergeladene und hashgeprüfte Assets:

- Manifest: `2eca8460a7f5c0dd538ce1503c7f9fc5ffd4f4d7ce75b03f396d25d3d4a2f2fd`;
- Wheel: `42e2fd4d81f18069e2c6fed9441f955f8a58c2b81e7e73e756fb1c3be30849a3`;
- sdist: `375ff7ce165809e2215c80c48c8843841168a1a553c56eb5d15341045e49d0ff`;
- Runtime-Lock: `918b2d20022fe86f4bf7be005177a70d646a65c8010c549f4598ff66efbbe97b`.

Das Schema-2-Manifest bindet das `linux/amd64`-OCI-Digest
`sha256:36792051ab54c54540d7d824812ce6e0a4443259c3c485d9e3e326fb8723793c`.
Der create-only Publish prüfte Git 2.47.3 im Image; ein frischer Start direkt
vom Registry-Digest erreichte Docker-Health `healthy`, und das Dashboard
meldete Version und vollständigen Commit korrekt. Das belegt die
Release-Lieferkette, noch nicht den unabhängigen D0-Workflow. Bis dessen
Installations-, Golden- und Blockiernachweise vorliegen, bleibt #658 `partial`
und `v2.0.0a7` der unterstützte Alpha-Stand.

### Revisionsfester Veröffentlichungsnachweis v2.0.0a10

`v2.0.0a10` besitzt das annotierte Tagobjekt
`4dc4e472bbe4ef827b234d14b3db5b3005e3cfa3` auf Commit
`b750a64ad1321280a5a81b3ee790952b33a74dac`. Gitea-Tag-Run #763 bestand
Python 3.10, Python 3.14, die vollständige Qualitätspipeline und das
Post-Tag-Release-Gate. Gitea-Prerelease #24 enthält genau vier erneut
heruntergeladene und byteidentisch geprüfte Assets:

- Manifest: `d863dedae5cae03f2bfa497a5803a6b51a37ea8c5a01992c85db01291b7d8ad1`;
- Wheel: `d0d9fa3280f399b974092f38ef78ed9026131862010d89ba5e3ce04ed2857ecf`;
- sdist: `d0c7143df48f39b1db4ccf123fe7cc35982708639f05d4292f2854705fdd4315`;
- Runtime-Lock: `918b2d20022fe86f4bf7be005177a70d646a65c8010c549f4598ff66efbbe97b`.

Das Schema-2-Manifest bindet das `linux/amd64`-OCI-Digest
`sha256:b68513e0f88eca3f32cf4708528126c0ebcdd9dc8f16faec79a567335318b76f`.
Der create-only Publish prüfte Git 2.47.3 im Image; ein frischer Start direkt
vom Registry-Digest erreichte Docker-Health `healthy`, und das Dashboard
meldete Version und vollständigen Commit korrekt. Die Publisherrolle konnte
die Registry bedienen, erhielt an der allgemeinen Gitea-Benutzer-API aber
erwartungsgemäß `403`; der lokale Registry-Login wurde nach dem Publish
entfernt. Das belegt die Release-Lieferkette und die enge Rolle, noch nicht
den unabhängigen D0-Workflow. Bis dessen Installations-, Update-, Golden- und
Blockiernachweise vorliegen, bleibt #658 `partial`, #694 eine bekannte
Qualification-Grenze und `v2.0.0a7` der unterstützte Alpha-Stand.

### Revisionsfester Veröffentlichungs- und D0-Nachweis v2.0.0a11

`v2.0.0a11` besitzt das annotierte Tagobjekt
`ff0584fc2f9af7952922e15380623fd3345e27eb` auf Commit
`bde64862f20e2d2bea0b1cb07211ac4a671390b5`. Gitea-Tag-Run #770 bestand
Python 3.10, Python 3.14, die vollständige Qualitätspipeline und das
Post-Tag-Release-Gate. Gitea-Prerelease #25 enthält genau vier erneut
heruntergeladene und byteidentisch geprüfte Assets:

- Manifest: `b1e51c01e2432eb441ade91240ed8acd22526508694e0347dbf05950361ecb5d`;
- Wheel: `b725797f0d55e92d2a98d69986e0635a2ce5110d7981a4a6323343b86d492caa`;
- sdist: `b7135c1d51709629f4310a9e7d19f50f8f3bab5b3a393d40b56444b225058327`;
- Runtime-Lock: `918b2d20022fe86f4bf7be005177a70d646a65c8010c549f4598ff66efbbe97b`.

Das Schema-2-Manifest bindet das `linux/amd64`-OCI-Digest
`sha256:baaff5ca3eb57170750d048364e96e84c7b19801715504074426ead70ba10a1b`.
Der create-only Publish und Compose-Smoke bestätigten Git 2.47.3,
Docker-Health `healthy` sowie die exakte Version/Revision in Runtime und
Dashboard. Die frische D0-Installation bestätigte zusätzlich Setup, Demo-
Tests, API-Auth, reale Providerprobes, Modell-/Benchmarkcache,
Credential-/Modell-Negativproben, Webhooksignaturblock, Audit und Neustart.
Demo-#52 erzeugte auf dem gebundenen Base genau einen Candidate und wurde
danach erwartungsgemäß durch `diff_secret_scan` ohne PR, Merge oder
`main`-Änderung blockiert.

Der Golden-Pfad Demo-#51 scheiterte vor Candidate-Erzeugung: Ein erneuter
Einzelaufruf erzeugte trotz vorhandenem Approval einen materiell anderen Plan,
während das ältere Approval-Label wirksam blieb. Der Lauf wurde vor dem
Watch-/Implementation-Dispatch gestoppt und als Produktfinding #767 erfasst.
Damit ist a11 eine vollständige Release- und D0-Fehlerevidence, aber kein
qualifizierter oder unterstützter Stand. Nach #767 benötigt #658 einen neuen
create-only Release, frischen State und neue Demo-Issues.

### Revisionsfester Veröffentlichungs- und D0-Teilnachweis v2.0.0a15

`v2.0.0a15` besitzt das annotierte Tagobjekt
`76d68f03f13bda079c40d39c941537946c6b0578` auf Commit
`5d3c3ff6c17f2d3510b5da8a3451e088bd253fed`. Gitea-Tag-Run #793 bestand
Python 3.10, Python 3.14, die vollständige Qualitätspipeline und das
Post-Tag-Release-Gate. Gitea-Prerelease #29 enthält genau vier erneut
heruntergeladene und byteidentisch geprüfte Assets:

- Manifest: `365623eb29bc7d2db297462259671e2d19f2afe59e6cfaee617e1a70a32ebb29`;
- Wheel: `8ab75b1dbcb4207728e88c4931cfa96725d7d7d08f634634d86cbc5d19ef6449`;
- sdist: `687e297d41501710bafafd04a98b10c5989251c504e85bc01d4fabb7aff9e93f`;
- Runtime-Lock: `918b2d20022fe86f4bf7be005177a70d646a65c8010c549f4598ff66efbbe97b`.

Das Schema-2-Manifest bindet das `linux/amd64`-OCI-Digest
`sha256:7fcb934da024a2418db681588f86fd864826c34b840124e59cbdbee398eb8167`.
Der create-only Publish und frische Compose-Smoke bestätigten Git 2.47.3,
Docker-Health `healthy`, Produktversion und vollständige Revision. Die frische
D0-Installation verwendete leeren State und einen neuen Checkout des
unabhängigen Demo-Repositorys. CLI, Dashboard/API-Authentisierung, reale
DeepSeek- und OpenRouter-Completions, Modellkatalog, fehlendes Credential,
ungültiges Modell, ungültige Webhooksignatur, Audit-Kette und Neustart wurden
real geprüft.

Demo-#57 und #58 erhielten je genau einen an denselben Base-Commit gebundenen
Plan. Ein absichtlich wiederholter `samuel run 57` wurde terminal als
`PlanReplanRejected` blockiert und in Workflow, Warn-Log, Dashboard sowie
OWASP ASI01 sichtbar, ohne Plan-Kommentar, Contract oder `status:plan` zu
verändern. Nach menschlicher Freigabe erzeugte der Watch-Pfad für #57 den
Candidate `edb4320bec73e2618fa207474dc96396592f8402`; PR #59 bestand PR-CI
#794, wurde als `9c7f2bfadc7e766d5d0e513e5dc994c6e4a7b145` gemergt und bestand Main-CI
#795. Der getrennte Candidate für #58 wurde durch `diff_secret_scan` blockiert;
es entstand kein PR und `main` blieb bis zum späteren Golden-Merge
unverändert. Der Merge von PR #59 erfolgte jedoch durch `demo-example-bot`
statt durch den nach dem damaligen Contract geforderten menschlichen Akteur.
Damit bleiben die genannten Teilnachweise gültig, bestätigen aber keinen
vollständigen D0-PASS. Die damalige a15-Supportdeklaration ist als aktuelle Installationsreferenz
zurückgenommen (#970); die Teilnachweise bleiben historisch. #658 und #694 bleiben bekannte
Betriebsgrenzen; die Evidence ist keine Beta-, Compliance-, Mehrplattform-
oder allgemeine Deploymentfreigabe.

## Autoritative Versionsableitung

`pyproject.toml` enthält keinen statischen Produktversionswert. Das dynamische
Projektfeld `version` wird ausschließlich durch `setuptools-scm` befüllt. Dessen
strikter `v`-Präfix und die kanonische Produktregex ignorieren
`phase-*-complete` und alle anderen Tags. Damit gilt:

- auf einem Produkt-Tag ist die Paketversion exakt die normalisierte Version
  hinter dem `v`;
- nach einem Produkt-Tag erzeugt `guess-next-dev` eine PEP-440-Dev-Version;
  `node-and-date` ergänzt das Git-Kürzel und markiert einen veränderten
  getrackten Arbeitsbaum;
- sdist-Metadaten tragen die aufgelöste Version in den anschließenden
  Wheel-Build; installierte Pakete lesen denselben Wert über
  `importlib.metadata` für Python-API, CLI und Dashboard;
- fehlt sowohl eine verwendbare SCM-/sdist- als auch installierte
  Paketmetadatenquelle, lautet der ausdrücklich nicht veröffentlichte Fallback
  `0+unknown` statt einer plausiblen Release-Version.

Die vollständige Commit-Revision und der gesamte Dirty-State des geladenen
Repositorys, einschließlich ungetrackter Dateien, bleiben separate
Build-Evidence in `samuel.build_info`. Das kurze Git-Kürzel der Dev-Version
ersetzt diese Evidence nicht.

## Ausführbarer Release-Prozess

`tools/release_gate.py` ist dieselbe fail-closed Prüfung vor und nach dem
Tagging. Sie verlangt einen sauberen Checkout, `HEAD == origin/main`, die
dynamische setuptools-scm-Konfiguration, einen datierten Changelog-Eintrag
sowie genau ein frisches Wheel und sdist mit derselben eingebetteten Version.
Zusätzlich materialisiert es den policygebundenen Runtime-Lock unter einem
versionsgebundenen Assetnamen und nimmt ihn in dasselbe Manifest auf.
Vor dem Tag ist die explizite Pretend-Version ausschließlich ein wegwerfbarer
Kandidaten-Build und muss exakt dem beabsichtigten Tag entsprechen. Nach dem
Tag ist dieser Override verboten; dann müssen zusätzlich Paket, Python-API,
CLI und Dashboard der vom Tag abgeleiteten Version entsprechen. Das erzeugte
`release-manifest.json` bindet deren SHA-256-Prüfsummen an Produktversion, Tag
und vollständigen Commit-SHA.

### Maintainerdisposition für v2.0.0a26 — 05.10.2026

Für diesen beauftragten Alpha-Release sind die eigenen noch fehlenden
Altlastenabnahmen nach
#962
vertagt und ausdrücklich keine Releaseblocker. Sein jetziger Zweck ist eine
separate Erstinstallation, danach die Erstellung eines vollständigen
Testkonzepts. Er ist jetzt kein als Golden-D0 freizugebender Release und
benötigt für die Veröffentlichung keinen vorherigen Acceptance-/Rehearsal-PASS.
Die administrativ geschlossenen Originalissues behaupten keinen Test-PASS;
der spätere eigene Golden-/D0- oder Supportclaim benötigt weiterhin seine
vollständige exakte Evidence. Tag, grüne CI, Artefakte, OCI-Bindung, erster
Required Smoke, Manifest und Remote-Readback werden unverändert ausgeführt.
Das ist eine datierte Maintainerentscheidung zu diesem Releasezweck, keine
Änderung der ausführbaren Gates, Testanforderungen oder Produktauthority.

### Pre-Release-Golden-Rehearsal für geplante D0-Kandidaten

Ist ein Release ausdrücklich als nächster Golden-D0-Kandidat vorgesehen, gilt
vor dem hier beschriebenen Pre-Tag-Gate zusätzlich R24 aus
[`OPERATING_RULES.md`](OPERATING_RULES.md). Der finale Produktcommit muss mit
seinem daraus erzeugten Candidate-Artefakt sowie unveränderter Demo-, Config-,
Route-, Policy- und Promptbindung einmal die vollständige vorgesehene
Q00–Q16-Strecke als Development-Rehearsal bestanden haben. Der zugehörige
Campaign-Receipt bindet Commit und Candidate-Digest und dokumentiert alle
früheren Attempts unverändert.

Ein normal behobenes Rehearsal-Finding läuft über Issue, Regression, PR, CI
und menschlichen Merge zu einem neuen Candidatecommit. Die betroffenen
Grenzen werden impact-basiert erneut geprüft; erst der finale Candidate
durchläuft noch einmal die vollständige Strecke ohne Produktcodeänderung.
Vor diesem Exit entstehen weder Tag noch OCI-Push, Manifest oder Gitea-Release.
`tools/release_gate.py` prüft weiterhin ausschließlich seinen bestehenden
Source-, Versions-, Changelog-, Build- und Artefaktvertrag; sein grünes
Ergebnis ersetzt den separaten Rehearsal-Receipt nicht.

Der Rehearsal-Exit erlaubt nur den Start des unveränderten normalen
create-only Releasepfads. Tag, Tag-CI, Artefakte, OCI-Bindung, erster Required
Smoke, Manifest und vollständiger Remote-Readback bleiben unverändert Pflicht.
Nach dem Publish beginnt die formale Qualification mit einem neuen frischen
Subject und zusammenhängendem Q00–Q16. Development-Evidence wird nicht als
formaler Golden-PASS übernommen; ein Produktbug im formalen Lauf bleibt
terminal `FAIL` und erfordert Fix, neuen Release und neuen Subject.

### Abgelaufener Autoritäts-Rollback aus #399

`legacy_score_authority`, `legacy_steps` und `config/gates.legacy.json` waren
nur bis einschließlich Produktversion `2.0.0a4` als gemeinsamer atomarer
Rollbackpfad zulässig und sind aus der Runtime entfernt. Alte explizite
Autoritätseinstellungen werden beim Start abgelehnt. Ab `2.0.0a5` weist
`tools/release_gate.py` solche Artefakte weiterhin zurück und verlangt zusätzlich
`docs/rollout/issue-399.json` nach dem geschlossenen Schema
`docs/rollout/issue-399.schema.json`, Version `1.0`. Die Evidence bindet sich
über den SHA-256-Digest an die exakten Schemabytes. Jeder der fünf Fälle trägt
Repository, vollständige Base-/Head-SHA, Contract-Hash, Gate-Policy-Version
und -Digest, Observation-Key, Correlation-ID, UTC-Zeitstempel sowie
strukturierte Run-/PR- oder Terminaldaten.

`tools/rollout_evidence.py` validiert diesen Vertrag offline und fail-closed.
Zusätzlich zu Typen und Pflichtfeldern prüft es fallbezogen insbesondere:

- Erfolg benötigt ein unblocked `GateEvaluationCompleted`, `GatesPassed` und
  einen PR mit exakt demselben Base-/Head-Paar;
- ein Required-Block benötigt `blocked=true`, terminale Route, keinen
  Healing-Auftrag und keinen PR;
- Healing bindet Ausgangs- und neuen Subject, den neuen Head als
  Fast-Forward-Nachfolger, genau einen Versuch, erneuten vollständigen
  Gate-Lauf und den PR an den geheilten Head;
- ein terminaler Re-Fail erlaubt weder zweiten Versuch noch PR;
- der Rollback-Drill erzwingt die geschlossene Reihenfolge
  Bound → Legacy → Bound, passende Profile/Policies/Healing-Routen und
  byteidentische gebundene Stores ohne Datenmigration.

### Preflight-Rollout aus #620

Der nachgelagerte reale #620/#653-Nachweis ist unabhängig vom abgelaufenen
Legacy-Fenster dauerhaft unter `docs/rollout/issue-620.json` verankert. Das
geschlossene Schema `docs/rollout/issue-620.schema.json`, Version `1.0`, wird
über seinen SHA-256-Digest an die Evidence gebunden;
`tools/preflight_rollout_evidence.py` rekonstruiert zusätzlich
`observation_key`, `evidence_digest` und `score_key` aus der exakten Subject-,
Gate-, Acceptance- und Formel-Evidence.

Die sechs Pflichtfälle verwenden ein isoliertes Fremd-Repository und keinen
Self-Mode. Sie belegen alle grünen Required-Preflights mit genau einem
Gate-11-Dispatch, 7b-/9-/13a-Fail-Closed mit explizitem Gate-11-Skip und ohne
Verifier-Dispatch, den alleinigen `GateEvaluationUnavailable`-Pfad vor
Subject-Aufbau sowie eine einzelne ausführbare Gate-11-Niederlage, die der
gebundene Klassifikator als `healable` erkennt. Jeder Fall bindet sein
Fixture-Issue und den revisionssicheren Evidence-Kommentar; nur der grüne Fall
darf einen PR tragen, dessen Base-/Head-Paar exakt dem Subject entspricht.

Die reale Evidence aus #577 ist in beiden Dateien revisionsgebunden
materialisiert; #577 und #580 sind geschlossen. Der a5-Releasevertrag prüft
nun sowohl die Abwesenheit der pensionierten Runtime-Artefakte als auch die
gebundene Evidence. Fehlende oder ungültige Evidence verlängert den
Legacy-Modus nicht.

Vorbereitung nach einem grünen Merge und grüner `main`-CI:

```bash
git fetch origin main --tags
git switch main
git merge --ff-only origin/main
test -z "$(git status --porcelain)"

release_dist="$(mktemp -d)"
release_tag="${RELEASE_TAG:?RELEASE_TAG auf die nächste freigegebene Vorabkennung setzen}"
release_version="${release_tag#v}"
export SETUPTOOLS_SCM_PRETEND_VERSION_FOR_SAMUEL="$release_version"
python -m build --outdir "$release_dist"
python tools/verify_distribution_license.py "$release_dist"
python tools/release_gate.py \
  --mode pre-tag \
  --tag "$release_tag" \
  --commit-ref origin/main \
  --dist-dir "$release_dist"
unset SETUPTOOLS_SCM_PRETEND_VERSION_FOR_SAMUEL
```

**Abbruchpunkt:** Bis hier wurde kein veröffentlichter Zustand erzeugt. Bei
einem Fehler wird nicht getaggt; Release-Commit, Changelog oder Gate werden in
einem normalen PR korrigiert und vollständig erneut geprüft.

Erst danach wird der annotierte Create-only-Tag gesetzt und ohne Force
übertragen:

```bash
git tag -a "$release_tag" -m "S.A.M.U.E.L. $release_version"
git push origin "refs/tags/$release_tag"
```

Der Tag-Workflow führt die vollständige Python-3.10-/3.14-Kompatibilitäts- und
Qualitätspipeline erneut aus, baut Wheel/sdist aus dem Tag und wiederholt das
Gate im Modus `post-tag`. Weil `actions/checkout` bei einem Gitea-Tag-Ereignis
den lokalen Tag-Ref durch den direkten Commit ersetzen kann, holt das Gate
zuvor gezielt nur den gleichnamigen Remote-Tag zurück und verlangt erneut den
Objekttyp `tag`. Ein fehlender, leichtgewichtiger oder auf einen anderen
Commit zeigender Remote-Tag bleibt rot. Erst wenn dieser Workflow grün ist,
wird in Gitea ein Prerelease für **genau diesen vorhandenen Tag** angelegt;
Wheel, sdist, der versionierte `samuel-runtime-<version>.lock` und
`release-manifest.json` werden als Assets angehängt. Der Runtime-Lock wird
direkt aus dem gegen `containers/lock-policy.json` geprüften Releasecheckout
materialisiert und im selben Manifest wie Wheel und sdist an SHA-256, Größe,
Version, Tag und vollständigen Commit gebunden. Er ist die geschlossene
Dependency-Grundlage des lokalen ADR-0706-Installationspfads; das Wheel wird
dort anschließend mit `--no-deps` installiert. Falls keine automatische
Publikation eingerichtet ist, ist die Gitea-Weboberfläche der dokumentierte
manuelle Fallback: vorhandenen Tag auswählen, als Prerelease markieren, die
vier geprüften Dateien hochladen und den Changelog-Abschnitt übernehmen.

Ab dem Release mit #970/#971 gehören zusätzlich `samuel-oci-<version>.tar.gz`,
`docker-compose.yml` und `docker-compose.setup.yml` zum manifestgebundenen
OCI-Lieferumfang. Das deterministische Kit enthält den offiziellen Bootstrap
und die releasegebundene Installationsanleitung. Der OCI-Erstinstallationsweg
wird auf einer frischen Ubuntu-/Docker-Umgebung mit genau diesen Assets
geprüft und nach Veröffentlichung durch erneuten Download wiederholt.

#### Mindestinhalt der Releasebeschreibung

Die Gitea-Releasebeschreibung ist keine bloße Kopie einer Versionsnummer. Sie
enthält für jeden neuen Stand mindestens:

1. Produktversion, annotiertes Tag, vollständigen Commit und Status
   `Prerelease`/unterstützt/nicht qualifiziert;
2. die vier Python-Assets mit Zweck sowie, bei OCI, Image-Referenz und
   Manifest-Digest;
3. nutzerwirksame Features und Fixes seit dem vorherigen Release;
4. bekannte Fehler, bewusst ungetestete Pfade und den aktuellen #658-
   Qualificationstatus – ein technischer Publish wird nicht als vollständiger
   Funktionstest ausgegeben;
5. Voraussetzungen und exakte Erstinstallations-/Updatebefehle, einschließlich
   notwendiger Config- oder State-Migrationen;
6. Preserve-/Replace-/Reject-Grenzen, Abbruchsignale und den zulässigen
   Rückweg. Ein Core-Rollback wird nie als automatischer State-Rollback
   beschrieben;
7. die maßgeblichen CI-, Manifest-, Package-/Image- und realen D0-Nachweise
   ohne Tokens, interne Pfade oder private Infrastrukturdetails.

Fehlt für einen Punkt reale Evidence, nennt die Releasebeschreibung ihn
ausdrücklich als offen. Der Changelog bleibt die langfristige Änderungshistorie;
die Releasebeschreibung ergänzt den konkret installierbaren Stand und seine
Betriebsgrenzen.

### Dokumentations- und Qualification-Abschluss

Ein technisch veröffentlichtes Prerelease ist erst vollständig dokumentiert,
wenn ein normaler Review-PR danach den live belegten Stand abgleicht. Dieser
Post-Publish-Change aktualisiert mindestens:

1. `README.md` und `docs/INSTALL.md`: jüngster veröffentlichter Tag,
   jüngster qualifizierter Referenzstand, Installationsbeispiel und
   Container-Manifest-Authority;
2. `SECURITY.md`: genau ein aktuell unterstützter Alpha-Stand;
3. dieses Dokument und `docs/CONTAINER_RELEASE_OPERATIONS.md`: Tagobjekt,
   Commit, Tag-CI, Release-ID, Manifest-/Artefakt-/OCI-Digests und historische
   Fehlversuche;
4. `CHANGELOG.md`: Inhalt und bekannte Grenzen des Releases;
5. Capability-Matrix und #658: `partial` bleibt bestehen, bis der reale
   Installations-, Positiv- und Blockiernachweis **desselben** Digests vorliegt;
   erst dann darf genau diese Referenzkombination `qualified` werden.

Vor dem Tag darf eine geplante Version als Kandidat beschrieben werden, aber
nicht als bereits veröffentlicht oder qualifiziert. Nach dem Tag darf ein
roter oder nur teilweise publizierter Stand nicht zum „aktuellen Release“
umgedeutet werden. Live-Gitea und das Manifest werden für den Post-Publish-PR
erneut gelesen; ein älterer lokaler Issue-Export genügt nicht.

Der öffentliche Extension-Contract und seine konkreten Payloadschemas werden
getrennt vom Produkt nummeriert. `documentation.static_claims` `1.0` sowie
`documentation.inventory.v1` bleiben nur bei kompatibler Semantik unter
derselben Kennung. Ein Feld-, Digest-, Coverage- oder Authoritybruch benötigt
eine neue Contract- beziehungsweise Claimfamilienversion und eine neue
Conformance-Qualification; ein Produktupdate wertet historische Advisoryclaims
nicht auf.

Die reale Qualification eines unabhängigen Consumers bindet mindestens einen
create-only Produktrelease mit Paketdigest, den exakten Consumercommit,
Policy-/Tooldigest, Request/Result und den Zielcommit des vorhandenen
Git-Publishers. Ein Test aus einem beweglichen Checkout oder nur grüne
Repositorytests reichen nicht. Scheitert ein veröffentlichter Kandidat, werden
Tag, Assets und vorhandene Remote-Publikation weder verschoben noch
überschrieben; eine Korrektur erhält einen neuen create-only Produktstand und
einen frischen gebundenen Qualificationlauf.

Der hierfür freigegebene Runner-, Image-, Label- und Action-Vertrag sowie
Update, Cache, Negativnachweis und Rollback stehen in
[`CI_RUNNER_OPERATIONS.md`](CI_RUNNER_OPERATIONS.md). Ein Lauf auf einem
beweglichen Runner-Image oder mit beweglichen Action-Refs erfüllt den
Release-Nachweis nicht.

Nach dem Tagging gibt es keinen Rollback durch Tag-Löschung oder -Verschiebung.
Scheitert die Tag-CI oder Veröffentlichung, bleibt der Tag als unveränderliche
Auditspur ohne freigegebenes Gitea-Release bestehen. Eine Code-/
Metadatenkorrektur erhält die nächste Vorabkennung (nach `v2.0.0a7`
beispielsweise `v2.0.0a8`). Ein rein technischer Uploadfehler darf für
denselben Tag nur mit den unveränderten, manifestgeprüften Artefakten erneut
versucht werden.

### Lieferumfang und Containervertrag

Historische Releases bis einschließlich `v2.0.0a8` veröffentlichten Wheel und
sdist als prüfbare Python-Artefakte; ihr vollständiger lokaler Betriebsweg blieb
der exakte Checkout. Ab dem ersten Release mit ADR-0706-Assets bilden Wheel,
sdist, versionierter Runtime-Lock und Manifest zusätzlich den lokalen
Releasevertrag. Der sdist liefert die Defaults nur für die Erstinitialisierung,
der Runtime-Lock die hashgebundenen Dependencies und das Wheel den
unveränderlichen Core. `install.sh`/Editable-Installation bleibt unabhängig
davon Entwicklungsmodus. Docker Compose verwendet weiterhin den
digestgebundenen OCI-Vertrag.

Für `v2.0.0a2` wurde ausdrücklich **kein** Container-Image veröffentlicht;
diese historische Liefergrenze bleibt unverändert. #555 ergänzt für
`v2.0.0a3` einen fail-closed Containervertrag:

- Das Basisimage ist über OCI-Index-Digest und separates
  `linux/amd64`-Manifest-Digest gebunden.
- Runtime- und Buildabhängigkeiten liegen als exakte, SHA-256-gebundene Locks
  vor; CI vergleicht sie mit den deklarierten Projektinputs.
- Produktversion, vollständiger Release-Commit, OCI-Labels, Registry-Digest
  und das Release-Manifest müssen dieselbe Identität tragen.
- Erst ein frischer Compose-Start des gepushten Digests mit grünem
  Docker-Health und passendem Dashboard-Buildstatus erlaubt Manifest-Schema 2.
- `.env`, Git-Metadaten, Tests, lokale Lizenzdateien und Arbeitsdaten bleiben
  außerhalb von Build-Kontext und Image. Operator-Konfiguration wird
  gemountet.

`tools/release_gate.py` bleibt die Authority für Tag, Commit, Version, Wheel,
sdist und den daraus veröffentlichten Runtime-Lock. `tools/container_release.py` erweitert dessen Manifest erst nach
Imageprüfung und Smoke; es führt keine zweite Produktversionsquelle ein. Das
Registry-Repository ist ein Betreiberparameter; Image und Runtime-Pull tragen
keine Gitea-Abhängigkeit des Produkts. Der mitgelieferte Referenzpublisher
prüft dagegen bewusst den Gitea-Owner-/Tokenvertrag. Update, Rollback,
Abbruchpfade und der gegenwärtige
Infrastrukturaufruf stehen in
[`CONTAINER_RELEASE_OPERATIONS.md`](CONTAINER_RELEASE_OPERATIONS.md).
Der Gitea-Referenzpublisher bindet eine separat ausgestellte
`write:package`-Credential des persönlichen Package-Owners an den expliziten
Releaseaufruf. Identität/Scope, Owner-Read, Tagabwesenheit und Push-
Postcondition werden getrennt ausgewiesen; ein Package-Scope wird nicht als
technische Einzelimage-Isolation dargestellt. Das Runtime-SCM-Token ist kein
Fallback, und ein unklarer Pushausgang darf keinen Retry, Tag-Delete oder
Overwrite auslösen.
`v2.0.0a3` bleibt der erste konkret nachgewiesene Container-Tag nach diesem
Vertrag. `v2.0.0a7` war ein späterer veröffentlichter Stand mit demselben
Schema-2-Vertrag; seine reale D0-Qualification blieb `partial`.

## Unabhängige Versionsdomänen

| Domäne | Heutige Kennung / Quelle | Verantwortlicher Vertrag | Änderungsregel |
|---|---|---|---|
| Produkt | dynamisches `[project].version`; strikter `v<Version>`-Produkt-Tag über `setuptools-scm`, in installierten Paketmetadaten materialisiert | Release-Maintainer, #479/#488 | genau eine wirksame Authority; Phase-Tags sind ausgeschlossen, metadatenloser Nicht-Release-Fallback ist `0+unknown` |
| Build-Identität | vollständiger Commit-SHA, bei lokalen Entwicklungsständen optional Dirty-State | `samuel.build_info`, Build-/Release-Prozess | bleibt getrennt von der Produktversion und bindet Artefakte an den Quellstand; keine volatile Buildzeit als Identität |
| REST-API | Pfadpräfix `/api/v1` | API-Handler und dokumentierte Payloads | inkompatible Änderung benötigt eine neue API-Hauptversion oder eine Migration; kein Produkt-Gleichlauf |
| Event-Schema | `event_version` je Event plus Upcaster | Core-Eventvertrag/Audit-Adapter | Schemaänderung erhöht die Eventversion; lesbare Altstände werden migriert oder ausdrücklich nicht unterstützt |
| Acceptance-/Evidence-/Policy-Schema | jeweiliges `schema_version`, Policy-Version und Digest | Acceptance-, Gate- und Evidence-Vertrag | Änderungen folgen dem jeweiligen Parser-/Migrationsvertrag und bleiben commitgebunden |
| Konfiguration und Workflows | ausgelieferte JSON-Struktur; nicht überall eigene Schema-ID | jeweilige Config-/Workflow-Validierung | kompatible Ergänzungen oder dokumentierte Migration; bis zu einer eigenen Schema-ID ist die Produktversion der äußere Kompatibilitätsvertrag |
| Persistierte Run-/Audit-Daten | Event- und Dateiformate | Audit-/Persistenzvertrag | nur soweit aktiv zugesagt; Neustart-/Retention-Vertrag bleibt bis #482 eingeschränkt |
| Architektur und Dokumente | z. B. „Architektur V2.1“, Dokumentstand | Dokumentverantwortliche | beschreibt die Revision des Dokuments/Modells, nicht den Produkt-Release |
| Capability-Matrix | `schema_version` der Matrix | Claims-to-Code-Audit | Parser-/Schemaänderung unabhängig von der Produktversion; geprüfter Commit und Quelldigest bleiben Pflicht |
| Prompt und Modell | Prompt-Hash/-Version, Provider-Modell-ID | LLM-/Audit-Konfiguration | als Laufzeit-Evidence pro Call; kein Produktversionsersatz |
| Fremdformate/-APIs | z. B. SARIF `2.1.0`, GitHub-API-Version | jeweilige externe Spezifikation | folgt dem Fremdvertrag und wird niemals wegen eines Produkt-Releases umnummeriert |

Keine dieser Kennungen wird pauschal an die Produktversion gekoppelt.
Insbesondere sind „Architektur V2.1“, `/api/v1`, `event_version=1`, SARIF
`2.1.0` und ein Modellname keine widersprüchlichen Produktstände.

## Sichtbarkeit und Build-Identität

#489 leitet Paketmetadaten, `samuel.__version__`, `samuel --version`,
Dashboard und produktbezogene Audit-Attribution aus demselben normalisierten
Produktstand ab; #488 speist diese Paketmetadaten aus dem strikten Produkt-Tag
beziehungsweise dem daraus abgeleiteten Dev-Stand. `samuel doctor` und der
Dashboard-Status führen die vollständige Commit-Revision als separates Feld.
Die auth-freie Dashboard-Shell rendert die HTML-escaped Produktversion bereits
serverseitig aus derselben Paketmetadatenquelle; ihre Sichtbarkeit hängt damit
nicht vom API-Key-Dialog oder JavaScript-Statusabruf ab. Voll-SHA, Dirty-State
und Betriebsdaten bleiben auf dem authentifizierten Statuspfad. Quell-Checkouts
ermitteln die Revision am Repository, das das geladene Paket enthält;
paketierte Deployments können den beim Build verifizierten Voll-SHA über
`SAMUEL_BUILD_REVISION` und einen Dirty-State über `SAMUEL_BUILD_DIRTY`
übergeben. Ungültige oder fehlende Revisionen bleiben ausdrücklich nicht
verfügbar. API-, Event-, Dokument-, Prompt-, Modell- und
Fremdformatversionen bleiben unverändert in ihrer eigenen Domäne.

Aktive Dokumentation darf einen Reifegrad nennen, aber keinen unabhängigen
zweiten „aktuellen Versionswert“ einführen. Historische Changelog-Einträge
bleiben unverändert und werden als Baseline oder Release eindeutig bezeichnet.

## Support und Python-Kompatibilität

Unterstützt sind nur Produktlinien, die `SECURITY.md` ausdrücklich als
veröffentlicht und unterstützt aufführt. Für Vorabversionen wird höchstens der
neueste ausdrücklich gelistete Stand unterstützt; `main` erhält Entwicklungs-
und Sicherheitskorrekturen, aber keine eigene Backport-Zusage. Eine neue
Veröffentlichung aktualisiert `SECURITY.md` bewusst.

Die unterstützte CPython-Spanne ist ein eigener Laufzeitvertrag. Der Quellstand
deklariert `>=3.10`; der Required Check hängt von vollständigen Tests auf der
Mindestversion 3.10 und der am 25. August 2026 aktuellen stabilen Reihe 3.14
ab. Die übrigen dazwischenliegenden CPython-Reihen sind aufgrund des
Bereichsoperators installierbar, werden aber nicht einzeln als CI-geprüfte
Matrix behauptet. Python 3.10 erreicht nach dem offiziellen CPython-Zeitplan
im Oktober 2026 das Supportende; eine spätere Veröffentlichung muss die
Mindestversion vorher mindestens auf 3.11 anheben und die aktive Installations-
und Contributor-Dokumentation im selben Change anpassen.

## Quellen

- [setuptools-scm: aktuelle Konfiguration](https://setuptools-scm.readthedocs.io/en/latest/config/)
- [setuptools-scm: Nutzung und Runtime-Version](https://setuptools-scm.readthedocs.io/en/latest/usage/)
- [PyPA: Single-Sourcing der Produktversion](https://packaging.python.org/en/latest/guides/single-sourcing-package-version/)
- [PyPA: Version Specifiers / PEP 440](https://packaging.python.org/en/latest/specifications/version-specifiers/)
- [Semantic Versioning 2.0.0](https://semver.org/)
- [CPython: Status of Python versions](https://devguide.python.org/versions/)
