# GitHub Sync Readiness

## Aktueller Publikationsvertrag — 06.10.2026

Die GitHub-Publikation ist bereits technisch eingerichtet: Der bereinigte
Main-Snapshot `36bb183732303c97a1e81532001e41029efa7aab`, Wiki und Issue #2
wurden unabhängig zurückgelesen. Auch die bereinigte Python-Releaseprojektion
v2.0.0a26 ist veröffentlicht. Ein Token fehlt für den aktuellen Auftrag
nicht; Credentials bleiben ausschließlich in der geschützten lokalen Quelle.
Der Maintainer beauftragt jetzt den erneuten Abgleich einschließlich a27.

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

## Live-Befund

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

## Tokengebundener Ablauf nach Bereitstellung der Authority

1. Den nach dem letzten Docs-Merge aus Product-`main` vorbereiteten public-safe
   Ein-Commit-Snapshot mit `PUBLIC_SNAPSHOT.md` und README-Hinweis gegen das
   externe Receipt erneut pruefen.
2. GitHub-`main`, Wiki-Head und Issue-#2-Revision anonym unmittelbar vor
   Wirkung nochmals lesen und gegen vorbereitete Werte binden.
3. Den exakten Public-Tree und die neue Root-Commit-ID dokumentieren; einen
   Gitea/GitHub-Mergebase gibt es nach diesem Historyvertrag gerade nicht.
4. Secret-/Privacy-Scan auf dem exakten Public-Tree ausfuehren und jeden Fund
   redigiert klassifizieren; bei einem echten Fund stoppen.
5. Den tokenlos vorbereiteten Executor mit exaktem `--force-with-lease` fuer
   den neuen Public-Root-Commit, getrenntem Wiki-Publish und redigiertem
   Issue-#2-Snapshot pruefen.
6. Erst mit passender GitHub-Tokenauthority ausfuehren und Branch, Wiki und
   Issue #2 zuruecklesen.

Erwartete Auswirkung: bewusster Ein-Commit-Public-Snapshot, kein privater
Historymirror. Tags werden nicht ueberschrieben. Gitea- und GitHub-Wiki
bleiben getrennte Publikationsziele.
