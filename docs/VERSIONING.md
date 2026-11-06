# Versionsrichtlinie

Aktuelle Verfahren und Grenzen stehen in den Fachabschnitten dieser Anleitung.
Frühere Releases und Attempts sind über die erhaltenen Anker im
[historischen Originalbestand](archive/reader-history-2026-10-11/VERSIONING.md) erreichbar.
a15 ist keine aktuelle Installationsreferenz oder Supportempfehlung; spätere
Erfolge ändern seine Teilnachweise und fehlende vollständige Human-Merge-Abnahme nicht.


## Aktueller Testrelease v2.0.0a29 — 09.10.2026

PR #989 und #980 sind menschlich gemergt und in a29 veröffentlicht.
Main-/Tag-CI, sieben gebundene Assets, OCI-Publisher-Smoke, frische
Draft- und Published-Erstinstallation sowie der erneute Asset-Readback sind PASS.
[Exakte Releasebindung und offene Nachweisgrenzen](status/CURRENT_PRODUCT_STATUS.md#veröffentlichter-installationsstand-v200a29--09102026).
Nur saubere neue Alpha-Testinstallationen; kein Golden-/D0- oder Isolations-PASS.


## Historischer Installationsstand v2.0.0a28 — 08.10.2026

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](archive/reader-history-2026-10-11/VERSIONING.md#historischer-installationsstand-v200a28--08102026).

### Artefaktbindung a28

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](archive/reader-history-2026-10-11/VERSIONING.md#artefaktbindung-a28).

## Historischer Installationsnachweis v2.0.0a27 — 06.10.2026

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](archive/reader-history-2026-10-11/VERSIONING.md#historischer-installationsnachweis-v200a27--06102026).

**Weiterhin geltende Grenze:**

Diese Richtlinie definiert die Produktversion und grenzt sie von unabhängig
versionierten Verträgen ab. SCM-Anker bleiben die Build-Authority; Main-CI,
Tag, Veröffentlichung, Qualification und Support sind getrennte Aussagen.
Die unten stehenden Versions-, Release- und Create-only-Regeln gelten weiter.
Die bestehenden Verträge #488 (SCM-Versionsquelle), #489 (sichtbare Ausgaben)
und #490 (Tag-/Releasebindung) bleiben maßgeblich. `main` ist ein integrierter
Entwicklungsstand und wird nicht durch einen Tag oder eine Main-CI selbst zum Release.

## Historischer Veröffentlichungsnachweis v2.0.0a26 — 05.10.2026

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](archive/reader-history-2026-10-11/VERSIONING.md#historischer-veröffentlichungsnachweis-v200a26--05102026).

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

Veröffentlichungsübersicht, abgeglichen am 9. Oktober 2026:

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
| `v2.0.0a28` | grün (#1217) | Prerelease #42, sieben verifizierte Assets | ja | ja | nein | historische OCI-Installations-Evidence; langsame Verifierprobe TIMEOUT bleibt FAIL; kein Golden-/D0-/Isolations-PASS |
| `v2.0.0a29` | grün (#1226) | Prerelease #43, sieben verifizierte Assets | ja | ja | nein | #989/#980 veröffentlicht; unabhängige frische Draft- und Published-OCI-Erstinstallation PASS; reale Funktion und Sicherheitsqualification bleiben getrennt |

### Revisionsfester Nachweis des ersten Release-Ankers

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](archive/reader-history-2026-10-11/VERSIONING.md#revisionsfester-nachweis-des-ersten-release-ankers).

### Revisionsfester Nachweis v2.0.0a3

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](archive/reader-history-2026-10-11/VERSIONING.md#revisionsfester-nachweis-v200a3).

### Revisionsfester Nachweis v2.0.0a6 und v2.0.0a7

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](archive/reader-history-2026-10-11/VERSIONING.md#revisionsfester-nachweis-v200a6-und-v200a7).

### Revisionsfester Nachweis v2.0.0a8 und D0-Abbruch

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](archive/reader-history-2026-10-11/VERSIONING.md#revisionsfester-nachweis-v200a8-und-d0-abbruch).

### Revisionsfester Veröffentlichungsnachweis v2.0.0a9

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](archive/reader-history-2026-10-11/VERSIONING.md#revisionsfester-veröffentlichungsnachweis-v200a9).

### Revisionsfester Veröffentlichungsnachweis v2.0.0a10

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](archive/reader-history-2026-10-11/VERSIONING.md#revisionsfester-veröffentlichungsnachweis-v200a10).

### Revisionsfester Veröffentlichungs- und D0-Nachweis v2.0.0a11

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](archive/reader-history-2026-10-11/VERSIONING.md#revisionsfester-veröffentlichungs--und-d0-nachweis-v200a11).

### Revisionsfester Veröffentlichungs- und D0-Teilnachweis v2.0.0a15

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](archive/reader-history-2026-10-11/VERSIONING.md#revisionsfester-veröffentlichungs--und-d0-teilnachweis-v200a15).

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

Der Tag-Workflow führt die vollständige Python-3.12-/3.14-Kompatibilitäts- und
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
2. `SECURITY.md`: den ausdrücklich unterstützten Stand beziehungsweise das
   Fehlen einer Support-/Qualificationfreigabe benennen; höchstens ein
   Alpha-Stand wird als unterstützt geführt;
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
| Persistierte Run-/Audit-Daten | Eventformate, SQLite-Schema v10, Witness und Restore-Sentinel | ADR-0482, Audit-/Persistenzvertrag | Gebundene Beobachtung, sichere Finalisierungsgrenzen und Restore/Reconcile sind implementiert; reale Crash-/Retention-/Capabilityqualification bleibt #962. Keine LLM-Rundenrekonstruktion oder Cross-Release-Zusage |
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

Die unterstützte CPython-Spanne ist ein eigener Laufzeitvertrag. Gemäß der
verbindlichen Maintainerentscheidung zu #811 vom 13.10.2026 deklariert der
neue Quellstand `>=3.12`. Die Required CI prüft CPython **3.12.14 und 3.14.7**;
Lint, Typprüfung und Releaseprüfung laufen weiterhin auf 3.12.14. Dazwischen-
liegende Reihen sind aufgrund des Bereichsoperators installierbar, werden
aber nicht als einzeln CI-geprüft behauptet. Python 3.10 gehört nicht zur neuen
Supportmatrix. Die OCI-Referenz nutzt den per Digest gebundenen Python-3.12-
slim-Stand (aktuell geprüft: 3.12.15, Debian 13); Patchversion und
`linux/amd64`-Manifest stehen im bestehenden Container-Lockvertrag.

**Erstes betroffenes Alpha-Release: `v2.0.0a30`.** Vor der Umsetzung wurden
sämtliche operativen Gitea-Tags und Releases geprüft: zuletzt veröffentlicht
`v2.0.0a29`, kein Tag und kein Release für a30. Die Bindung gilt für den ersten
noch unveröffentlichten Alpha-Release, der die abgeschlossene Änderung
enthält. Vor Integration/Releaseplanung wird der create-only Readback erneut
geprüft; falls a30 inzwischen ohne diese Änderung veröffentlicht wurde, wird
der nächste unveröffentlichte Alpha-Stand dokumentiert. Es werden keine Tags
oder Assets dieses Entwicklungsauftrags erstellt oder geändert.

Bereits veröffentlichte Releases einschließlich a29 behalten ihre damaligen
Metadaten, Interpreter, Locks und Nachweise. Für a30 und später benötigen
lokale Wheel-/venv-/Quellinstallationen Python >=3.12; eine neue Umgebung mit
passendem Interpreter verwenden, keine bestehende venv in-place umdeuten.
Beim OCI-Weg liefert das neue Image Python; auf dem Dockerhost ist weiterhin
kein eigener Pythoninterpreter nötig. Corewechsel, selektiver Restore,
Auditkey/Kettenpaar und State-/Mount-/Authoritygrenzen bleiben die bestehenden
[Installationsverträge](INSTALL.md#corewechsel-frische-installation-und-selektiver-restore-985).
Ein Interpreterwechsel verleiht weder State-Migration noch einen Golden-/D0-
oder rückwirkenden Abnahme-PASS.

## Quellen

- [setuptools-scm: aktuelle Konfiguration](https://setuptools-scm.readthedocs.io/en/latest/config/)
- [setuptools-scm: Nutzung und Runtime-Version](https://setuptools-scm.readthedocs.io/en/latest/usage/)
- [PyPA: Single-Sourcing der Produktversion](https://packaging.python.org/en/latest/guides/single-sourcing-package-version/)
- [PyPA: Version Specifiers / PEP 440](https://packaging.python.org/en/latest/specifications/version-specifiers/)
- [Semantic Versioning 2.0.0](https://semver.org/)
- [CPython: Status of Python versions](https://devguide.python.org/versions/)
