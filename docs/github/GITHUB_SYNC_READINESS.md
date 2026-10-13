## Public-Projektion — aktueller Abgleich vom 13.10.2026

Dieser Snapshot projiziert den integrierten Source `754f8387edd89a0a69270d8465c322c0c3ffc7f2` einschließlich freier Modelleingabe, Python-3.12-Mindestversion, Audit-Schreibdiagnose, Installationsanleitung und aller vorhandenen Dokumentationsbilder. Der neue Public-Root und die zugehörige Wiki-Revision sind im externen Abschlussreceipt gebunden. Die aktuelle begrenzte Planung steht in PUBLIC_SNAPSHOT.md; Issue #2 bleibt historische Planung. Die Veröffentlichung erfolgt über den bestehenden Ein-Commit-/Lease-/Wiki-/Issue-2-Vertrag. Die darunter stehenden datierten Readbacks sind historische Nachweise ihres jeweiligen Stands; Tags und Releases werden hier nicht verändert. Siehe [PUBLIC_SNAPSHOT.md](../../PUBLIC_SNAPSHOT.md).

# GitHub Sync Readiness

## Aktueller Publikationsstand und Vertrag — 10.10.2026

Anonymer Readback der GitHub-API am 10.10.2026: Public-Main
`7a03d34f6f2b21aefb533aef08ca00835c394bcc` (parentloser Root); jüngstes veröffentlichtes Prerelease
[v2.0.0a28](https://github.com/Alexander-Benesch/S.A.M.U.E.L./releases/tag/v2.0.0a28). a27 und a26 sind ebenfalls vorhanden.
Die API `/releases/latest` liefert bei dieser Prerelease-Serie keinen Release;
maßgeblich ist die tatsächlich gelesene Releaseliste.

Der Public-Snapshot benennt den freigegebenen nativen Source
`d490fb16bb959a6a990e4ac808c45d17821374ec` mit a29-Produktsemantik;
PR #991 ist dort ausdrücklich noch nicht enthalten. Der native aktuelle Main
ist `b59b1fc3def41ce73fef1cf29841a2e6ffbe8db7`. Die öffentliche **Releaseliste**
enthält weiterhin nur a28/a27/a26, keinen veröffentlichten a29-Release.
Sourceprojektion, veröffentlichtes Paket und öffentlich verfügbares OCI sind
getrennte Nachweise; der im Snapshot beabsichtigte GHCR-Pfad ist ohne
veröffentlichtes Manifest und unabhängigen Pull kein Verfügbarkeitsbeleg.
Der separate Public-Uploadnachweis vom 09.10.2026, 14:20 UTC, hält einen
**unveröffentlichten a29-Draft** fest: Release-ID `407987322`, sieben
hochgeladene und byteverifizierte Assets, weiterhin Schema-1-Staging ohne
öffentliche Containerbindung. Das create-only Public-Tag `v2.0.0a29` existiert
bereits; der erneute anonyme Tagreadback bindet Tagobjekt
`4099df5d52964d4d1bdb0a4ca73aaf2d89d3e2b1` an den genannten Publiccommit.
Draft, Tag, veröffentlichte Releaseliste und installierbares OCI bleiben
verschiedene Claims. Der datierte GHCR-Schreibpreflight meldet 403
`permission_denied` für den vorhandenen Fine-grained PAT; die erforderliche
Packages-Publisherauthority ist ein echter externer Betreiberrest. Kein neuer
Token, Workflow oder Runner wird daraus autonom angelegt. Der erfolgreiche
Release-Assetupload widerlegt einen pauschalen GitHub-Token-/Upload-Missing-
Blocker, belegt aber keinen GHCR-Push oder anonymen Imagepull.

Dieser Dokumentabgleich publiziert weder GitHub-Main noch Wiki oder Releases.
Die Publikationsauthority ist eingerichtet; Credentials bleiben ausschließlich
in der geschützten lokalen Quelle. Jeder weitere öffentliche Abgleich bindet seinen
eigenen Source-/Public-Stand und unabhängigen Readback.

GitHub bleibt eine bereinigte, nicht autoritative Projektion mit einem
parentlosen Root-Commit. Gitea-Historie, private Evidence, Zugänge und
Infrastrukturkennungen werden nicht übernommen. Public-Artefakte besitzen
eigene Commit-/Prüfsummenbindungen; eine Public-Projektion übernimmt keinen
Installations- oder Workflow-PASS der privaten Ausgabe. Die private
OCI-Registry ist dadurch nicht öffentlich verfügbar. Tags und bestehende
Release-Dateien bleiben create-only.

Der folgende Token-Missing-Readback ist historische Evidence vom 29.09.2026
und kein heutiger Blocker. Die exakten neu veröffentlichten Heads und
Readbacks stehen im jeweiligen externen Abschlussreceipt.

Erhebung: 2026-09-29. Ergebnis: `PUBLIC_REMOTE_IDENTIFIED; PUBLISH_TOKEN_MISSING`.

## HISTORICAL — früherer Readback vom 09.10.2026

Der frühere anonyme Readback nannte Public-Main
`e41ce383be5a6c97e9cdf89d5ab1e069777295d6` und a28 als jüngstes
Prerelease. Die Headangabe ist durch den oben genannten erneuten Readback
superseded; die aktuelle Releaseliste bestätigt die a28-Paketgrenze weiterhin.
Kein damaliger Readback wird rückwirkend umgedeutet.

## Historischer Readback — 29.09.2026

| Feld | Wert |
|---|---|
| Gitea Product-Codebaseline | `41340e75e0acc918fbc577653c3bedfec0f70aaa` vor dem Docs-PR; der finale Housekeeping-Source-SHA steht im externen Public-Sync-Receipt |
| konfigurierter GitHub-Remote | keiner |
| historischer Public-Snapshot | `https://github.com/Alexander-Benesch/S.A.M.U.E.L.`; Product-Issue #635, Kommentar #40308 und `PUBLIC_SNAPSHOT.md` sind Provenienz |
| anonymer GitHub-Readback | Repository public, Defaultbranch `main`, Head `f1fa875c1e05138ecda9cb2e618e4f56e8ecf32a` am 29.09.2026 |
| exakter Git-Clone-URL | `https://github.com/Alexander-Benesch/S.A.M.U.E.L..git` (doppelter Punkt vor `git`, weil der Repositoryname mit Punkt endet) |
| GitHub-Wiki | `https://github.com/Alexander-Benesch/S.A.M.U.E.L..wiki.git`, Branch `master`, Head `003e3870f97ca32d10a6dad29f5a465ea24a216f` |
| Historymodell | bereinigter Snapshot mit genau einem Root-Commit; keine private Gitea-Historie spiegeln |
| GitHub Issue #2 | offener, nicht autoritativer Product-Issue-Snapshot; zuletzt 2026-08-30T06:01:38Z aktualisiert |
| GitHub SHA / Mergebase / ahead-behind | GitHub-Head bekannt; Gitea-History ist absichtlich nicht verwandt, daher kein Fast-forward-Delta |
| Tag-/Release-Delta | nicht Teil des neuen Ein-Commit-Root-Snapshots; keine Tag-Ueberschreibung vorgesehen |
| Dry-run | vor dem Token nur lokal pruefbar; Remote-Push-Dry-run braucht die spaetere Tokenauthority |

Es wurde kein GitHub-Push versucht. Der historische Snapshot-Vertrag verlangt
ein neues public-safe Root-Tree mit exakt einem Commit und einen Push nur mit
`--force-with-lease` gegen den zuvor gelesenen GitHub-Head. Wiki und Issue #2
werden separat aktualisiert. Ein fehlender lokaler Git-Remote ist kein
Existenzbeweis; die anonyme GitHub-API bestaetigt das Zielrepository.

## Public-Safety-Gate

Der vorbereitete Public-Stand darf nur aus dem nach allen Docs-Merges festgelegten
Gitea-`main` bestehen. Das externe Paket bindet den exakten Source-SHA,
Public-Root-Commit, Wiki-Projektion und Issue-#2-Revision. Vor dem Push sind der exakte Public-Tree und die
beabsichtigte GitHub-Head-Ersetzung zu pruefen:

- Arbeitsbaum, Public-Root-Commit und dessen einzelner Parent-freier Tree;
- `.env`, Token/API-Key/HMAC/Signingkey, Cookie/Session und Registrycredential;
- credential-bearing URLs/Headers und wiederherstellbare Fingerprints;
- private Evidencepayloads, interne absolute Pfade und private
  Infrastrukturadressen;
- Tags/Releases und grosse/ungewoehnliche Dateien.

Die ungetrackten Audit-/Falsification-Originale sind bewusst nicht Teil dieses
Docs-PRs. Der secretfreie Index in `docs/audits/INDEX.md` ersetzt sie nicht als
Evidence, verhindert aber eine versehentliche Publicaufnahme.

## Publikationsablauf — historische Vorbereitung, Authority heute eingerichtet

1. Den nach dem letzten Docs-Merge aus Product-`main` vorbereiteten public-safe
   Ein-Commit-Snapshot mit `PUBLIC_SNAPSHOT.md` und README-Hinweis gegen das
   externe Receipt erneut pruefen.
2. GitHub-`main`, Wiki-Head und Issue-#2-Revision anonym unmittelbar vor
   Wirkung nochmals lesen und gegen vorbereitete Werte binden.
3. Den exakten Public-Tree und die neue Root-Commit-ID dokumentieren; einen
   Gitea/GitHub-Mergebase gibt es nach diesem Historyvertrag gerade nicht.
4. Secret-/Privacy-Scan auf dem exakten Public-Tree ausfuehren und jeden Fund
   redigiert klassifizieren; bei einem echten Fund stoppen.
5. Den ursprünglich tokenlos vorbereiteten Executor mit exaktem `--force-with-lease` fuer
   den neuen Public-Root-Commit, getrenntem Wiki-Publish und redigiertem
   Issue-#2-Snapshot pruefen.
6. Erst mit passender GitHub-Tokenauthority ausfuehren und Branch, Wiki und
   Issue #2 zuruecklesen.

Erwartete Auswirkung: bewusster Ein-Commit-Public-Snapshot, kein privater
Historymirror. Tags werden nicht ueberschrieben. Gitea- und GitHub-Wiki
bleiben getrennte Publikationsziele.
