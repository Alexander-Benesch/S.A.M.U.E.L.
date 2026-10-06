# Container-Release-Betrieb

Stand: 6. Oktober 2026

Dieses Runbook beschreibt den in #555 eingeführten, digest- und
lockgebundenen Containerpfad. Es erweitert das allgemeine Release-Gate aus
[`VERSIONING.md`](VERSIONING.md), ersetzt es aber nicht. Der Produktcode kennt
keine Container-Registry: Registry, Repository und Anmeldung sind
Betreiberparameter von `tools/container_release.py`. Die unten genannte
Gitea-Registry ist ausschließlich die gegenwärtige Infrastruktur dieses
Repositories; derselbe Ablauf gilt analog für eine OCI-kompatible Registry.

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

Der erste vollständig nach diesem Vertrag veröffentlichte Containerstand ist
`v2.0.0a3`:

- Das annotierte Tagobjekt
  `484efff40b706fc4b2525e16398ee08c42a09aaf` zeigt auf Commit
  `41ee7506dd5a09f6eef4a3b71ad08276d0848911`.
- Gitea-Run #522 war mit Jobs #682 (Python 3.10), #683 (Python 3.14),
  #684 (vollständige Qualitätspipeline) und #685 (Post-Tag-Release-Gate)
  vollständig `success`.
- Das create-only veröffentlichte `linux/amd64`-Image ist unter der intern
  archivierten Registryreferenz mit Digest
  `sha256:6a9c53ae5ba554a5b000e140f3a0929447984f230c9e50a1e5ce9c07d06dc5f6`
  gebunden. Private Registryhost- und Ownerwerte gehören nicht in die aktive
  öffentliche Betriebsdokumentation.
  OCI- und Runtime-Version waren `2.0.0a3`; OCI-, Runtime- und
  Dashboard-Revision waren der vollständige Release-Commit. Der frische
  Compose-Start vom Registry-Digest erreichte Docker-Health `healthy`.
- Gitea-Prerelease #10 enthält `release-manifest.json` mit Schema 2 sowie
  Wheel und sdist. Erneute Downloads ergaben für das Manifest
  `03f89fdf23969458336da1e916abc2286fb5b4181ff1e0b3db06bfb682af2554`,
  für das Wheel
  `8a5d3217849cb86c272057011d99091c6e56b0dbb82e211e246f5c8e05a3c916`
  und für das sdist
  `4ccc6efb2122d145ab9b1a83a25f646cf8c8c2b20a53d98de179c400c7686f9f`.
  Die beiden Paketwerte stimmen mit dem Manifest überein.

Diese Evidence gilt genau für den genannten Tag, Commit, Digest und die
Plattform. Der lesbare Image-Tag ist keine Installationsauthority. Die interne
Gitea-Registry und ihre HTTP-Freigabe sind Betreiberkonfiguration, keine
Produktabhängigkeit.

## Nicht freigegebener Publishversuch v2.0.0a5

Das annotierte Tag `v2.0.0a5` zeigt auf Commit
`b518e9a8cca2362dab947686bfdd00a6e1ceef6f`; Gitea-Run #664 einschließlich
Post-Tag-Release-Gate war vollständig grün. Der create-only Push erzeugte das
Image-Digest
`sha256:3bd6a012d714c46d7a81fa0403a1535419eb4ed08815368b1592421ea729fb2d`.
Der danach vorgeschriebene frische Compose-Smoke schlug jedoch fehl, weil der
Workspace-Bind-Mount nicht für den nicht privilegierten Runtime-Benutzer
vorbereitet war (#685). Daher existieren für `v2.0.0a5` weder ein
Schema-2-Release-Manifest noch ein Gitea-Release; Tag und Image bleiben
unveränderte Auditspur und sind **kein freigegebener Installationsstand**. Ein
korrigierter Publish verwendet gemäß Create-only-Regel die nächste
Vorabversion.

## Früherer unterstützter Veröffentlichungsnachweis v2.0.0a7

`v2.0.0a6` korrigierte den Workspace-Bind-Mount des a5-Smokes und wurde als
Gitea-Prerelease #20 vollständig veröffentlicht. Der darauf folgende frühere
Alpha-Stand `v2.0.0a7` verwendet denselben unveränderten Schema-2-Vertrag:

- annotiertes Tagobjekt:
  `e6912d0d4b8db6f95f8e6ec975f5b8a50ab226bf`;
- Release-Commit:
  `d4000e94edc70f68190bf30b16cff5cbbbf2d143`;
- Tag-CI: Python 3.10, Python 3.14, vollständige Qualitätspipeline und
  Post-Tag-Release-Gate jeweils `success`;
- Gitea-Prerelease #21 mit genau `release-manifest.json`, Wheel und sdist;
- Manifest-SHA-256:
  `9e4e7a61a16f76c143c96b4863a0de0896db0c924ca9e025cf6466f8dcac415d`;
- Wheel-SHA-256:
  `2235a6121063823973b713980b124b13ce3587056d16da504dd4d8e8d682f38c`;
- sdist-SHA-256:
  `017128f4627885a1db8e3c8bfc3edda336afe2066bfbf9b4d998a6f862f49758`;
- `linux/amd64`-OCI-Digest:
  `sha256:6083b5045288ce84a6162966d3126eca10bd0b71aff545deb30b038994bb1653`.

Für die Installation wird die vollständige `container.reference` direkt aus
diesem Manifest gelesen. Registryhostname und lesbarer Image-Tag sind keine
separate Produkt-Authority. Der erfolgreiche Release-Smoke belegt Build,
Identität und Health des frischen Digests; er belegt noch nicht den kompletten
#658-D0-Workflow. Die späteren a15-Release- und D0-Teilnachweise erweiterten
diese Evidence, bestätigten wegen des Bot-Merges aber keinen vollständigen
D0-PASS.

## Veröffentlichter, nicht D0-qualifizierter Stand v2.0.0a8

`v2.0.0a8` wurde create-only und in sich konsistent veröffentlicht, ist aber
wegen eines danach im realen D0-Lauf nachgewiesenen Runtimefehlers nicht der
unterstützte Installationsstand:

- annotiertes Tagobjekt
  `4cce7c8eda85a9cad214763564c1aefe4c7c9914` auf Commit
  `1b7dee9affff4358fe10de868a0a9bbddd7a2931`;
- vollständig grüner Gitea-Tag-Run #711;
- Gitea-Prerelease #22 mit Manifest-SHA-256
  `b4bbda9270552eef8ca174048c7dc3625ef169474eb76482b30d2acd18ba05af`,
  Wheel-SHA-256
  `fa6b3d4ad2b8f27683304b320b8cf20f7743efb8de2d6a9ce85d77ac0d03adaa`
  und sdist-SHA-256
  `bf067dd062fc7a9dc69f7de79964c99f72613beb4082f38fbcb49ec7f8e7d350`;
- OCI-Digest
  `sha256:d726acb8064c59a548b8f7b1aa0ccfdd1209049d98b2ce9bb333986115f07aea`.

Der vorgeschriebene Publish-Smoke prüfte Imageidentität, Dashboard und den
damaligen Health-Umfang erfolgreich. Im unabhängigen Zielrepository blockierte
der erste echte Lauf für Demo-Issue #24 jedoch bereits vor Planning mit
`workspace_git_failed`: Das Runtime-Image enthielt kein `git`, obwohl der
ausgelieferte Worktree-Adapter es benötigt (#727). Tag, Release und Digest
bleiben unveränderte Evidence; sie werden weder überschrieben noch als
qualifizierter Kundenstand empfohlen. Erst ein neuer Digest darf nach
erneutem Installations-, Positiv- und Negativnachweis den unterstützten Stand
ablösen.

## Durch D0-Findings abgelöster Qualification-Kandidat v2.0.0a9

`v2.0.0a9` wurde am 2. September 2026 nach demselben create-only Vertrag
veröffentlicht. Der anschließende #658-D0-Nachlauf belegte die dynamische
Health-Lücke #690 und den Runner-/Selektorkonflikt #756. Der unveränderte
Stand bleibt Release-Evidence, ist aber nicht der unterstützte Alpha-Stand:

- annotiertes Tagobjekt
  `766c2b41a9afe50324ff97bae2a35a1fa8612760` auf Commit
  `ffe709cfe14d69e2f8bd8233e6066eb6972ef8f3`;
- vollständig grüner Gitea-Tag-Run #753;
- Gitea-Prerelease #23 mit genau Manifest, Wheel, sdist und versioniertem
  Runtime-Lock;
- Manifest-SHA-256
  `2eca8460a7f5c0dd538ce1503c7f9fc5ffd4f4d7ce75b03f396d25d3d4a2f2fd`;
- Wheel-SHA-256
  `42e2fd4d81f18069e2c6fed9441f955f8a58c2b81e7e73e756fb1c3be30849a3`;
- sdist-SHA-256
  `375ff7ce165809e2215c80c48c8843841168a1a553c56eb5d15341045e49d0ff`;
- Runtime-Lock-SHA-256
  `918b2d20022fe86f4bf7be005177a70d646a65c8010c549f4598ff66efbbe97b`;
- `linux/amd64`-OCI-Digest
  `sha256:36792051ab54c54540d7d824812ce6e0a4443259c3c485d9e3e326fb8723793c`.

Der frische digestgebundene Compose-Smoke bestätigte Git 2.47.3,
Docker-Health `healthy`, Produktversion und vollständige Revision. Die
endgültige Installationsauthority bleibt die vollständige
`container.reference` im angehängten Manifest. Positiver Golden Path und
echter Blockierfall im unabhängigen Demo-Repository sind davon getrennte,
noch offene Evidence.

## Durch den Runner-Prompt abgelöster Qualification-Kandidat v2.0.0a10

`v2.0.0a10` wurde am 2. September 2026 create-only veröffentlicht und bündelt
gezielt die Korrekturen für #690 und #756. Der anschließende #658-D0-Nachlauf
belegte die Release- und Runtimeidentität, scheiterte aber im positiven
Golden-Plan an einem widersprüchlichen Runner-Beispiel. a10 wurde deshalb
durch a11 abgelöst und war zu keinem Zeitpunkt der unterstützte Alpha-Stand:

- annotiertes Tagobjekt
  `4dc4e472bbe4ef827b234d14b3db5b3005e3cfa3` auf Commit
  `b750a64ad1321280a5a81b3ee790952b33a74dac`;
- vollständig grüner Gitea-Tag-Run #763;
- Gitea-Prerelease #24 mit genau Manifest, Wheel, sdist und versioniertem
  Runtime-Lock;
- Manifest-SHA-256
  `d863dedae5cae03f2bfa497a5803a6b51a37ea8c5a01992c85db01291b7d8ad1`;
- Wheel-SHA-256
  `d0d9fa3280f399b974092f38ef78ed9026131862010d89ba5e3ce04ed2857ecf`;
- sdist-SHA-256
  `d0c7143df48f39b1db4ccf123fe7cc35982708639f05d4292f2854705fdd4315`;
- Runtime-Lock-SHA-256
  `918b2d20022fe86f4bf7be005177a70d646a65c8010c549f4598ff66efbbe97b`;
- `linux/amd64`-OCI-Digest
  `sha256:b68513e0f88eca3f32cf4708528126c0ebcdd9dc8f16faec79a567335318b76f`.

Der frische digestgebundene Compose-Smoke bestätigte Git 2.47.3,
Docker-Health `healthy`, Produktversion und vollständige Revision. Die
Publisherrolle war an der Registry wirksam und an der allgemeinen
Gitea-Benutzer-API bewusst nicht autorisiert. Die endgültige
Installationsauthority bleibt die vollständige `container.reference` im
angehängten Manifest. Der getrennte a9→a10-Drill belegte Erhalt und
Abgrenzung der persistenten Betreiberpfade für genau diesen Wechsel. Der
Golden-Pfad blieb wegen des Runner-Prompts ohne Candidate-Nachweis; a10 ist
daher historische Audit-Evidence und kein Supportclaim. #694 bleibt bis zur
freigegebenen Profilentscheidung eine ausdrücklich bekannte
Doctor-/SCM-Qualification-Grenze.

## Veröffentlichter, im D0-Golden-Pfad gescheiterter Stand v2.0.0a11

`v2.0.0a11` wurde am 2. September 2026 nach demselben create-only Vertrag
veröffentlicht. Er korrigiert ausschließlich den widersprüchlichen
Runner-Prompt aus a10. Die Release-Lieferkette ist konsistent, die reale
Qualification aber fehlgeschlagen:

- annotiertes Tagobjekt
  `ff0584fc2f9af7952922e15380623fd3345e27eb` auf Commit
  `bde64862f20e2d2bea0b1cb07211ac4a671390b5`;
- vollständig grüner Gitea-Tag-Run #770;
- Gitea-Prerelease #25 mit genau Manifest, Wheel, sdist und versioniertem
  Runtime-Lock;
- Manifest-SHA-256
  `b1e51c01e2432eb441ade91240ed8acd22526508694e0347dbf05950361ecb5d`;
- Wheel-SHA-256
  `b725797f0d55e92d2a98d69986e0635a2ce5110d7981a4a6323343b86d492caa`;
- sdist-SHA-256
  `b7135c1d51709629f4310a9e7d19f50f8f3bab5b3a393d40b56444b225058327`;
- Runtime-Lock-SHA-256
  `918b2d20022fe86f4bf7be005177a70d646a65c8010c549f4598ff66efbbe97b`;
- `linux/amd64`-OCI-Digest
  `sha256:baaff5ca3eb57170750d048364e96e84c7b19801715504074426ead70ba10a1b`.

Der frische D0-Lauf bestand Installation, Setup, Runtime-/Dashboardidentität,
Provider-/Readinessprüfungen, Audit/Restart und den echten Secret-Scan-Block.
Der Golden-Pfad wurde dagegen vor Candidate-Erzeugung gestoppt, weil ein
Re-Plan das ältere Approval-Label auf einen materiell anderen Plan hätte
übertragen können (#767). a11 bleibt unveränderliche Evidence und darf nicht
als qualifizierter Installationsstand gewählt werden. Der nächste D0-Lauf
beginnt nach dem Fix mit neuem Release, leerem State und neuen Demo-Issues.

## Abgelöster, nicht D0-qualifizierter Stand v2.0.0a19

`v2.0.0a19` ist ein vollständig veröffentlichter Alpha-Kandidat. Sein
Release- und Runtime-Nachweis ist vollständig, aber kein Nachweis einer
D0-Installation oder eines Golden-/Blockierpfads:

- annotiertes Tagobjekt `61429d8c7e9cdd846e17bfa2e1595d94b2f7d4d2` auf Commit `8656b8b6d0b2ff659db9f5ca178bdd22cfd65d86`;
- vollständig grüner Gitea-Tag-Run #878 (Python 3.10, Python 3.14,
  Qualitätspipeline und Post-Tag-Release-Gate);
- Gitea-Prerelease #33 mit genau `release-manifest.json`, Wheel, sdist und
  versioniertem Runtime-Lock;
- Manifest-SHA-256 `982d1fea4a150ed03a96cb1eaa1df657a5864c5c2248c70a8ff6ed7c84be385e`;
- Wheel-SHA-256 `4fc35ca83f23877144aeb1f5a8a95e23b23381cfe6428716ae1b78d65b2addb1`;
- sdist-SHA-256 `379e8f450641dc89edcdf9acb8408711b5d8d2c8925569ab533f0bf359a02be4`;
- Runtime-Lock-SHA-256 `6a55ba2a815c7228459b7ace7ab104fc6e1fd525c737860ba0682ce3453c507f`;
- `linux/amd64`-OCI-Digest `sha256:9235f428092c283d54a79552433304069af4e91620175231f0ad228968e1f089`.

Der frisch vom Digest gestartete Compose-Smoke bestätigte Imageidentität,
Git-Runtime, Docker-Health, Dashboard-Buildversion und vollständige Revision.
Er verwendet keinen D0-State und ersetzt weder eine frische unabhängige
Installation noch Golden- oder Blockiernachweise. `v2.0.0a19` ist daher
**PUBLISHED — D0 FAILED** und bleibt unveränderte historische Evidence.

## Release-Lineage v2.0.0a20 bis v2.0.0a25

Die create-only Kandidaten nach a19 behalten ihren jeweils eigenen Status:

- a20 und a22 materialisierten OCI-Digests, deren `source`-Label fälschlich
  auf das Demo- statt auf das Produkt-SCM zeigte. Beide bleiben unveränderte
  fehlgeschlagene Publish-Evidence und besitzen keinen Gitea-Release.
- a21 wurde vollständig veröffentlicht, aber nicht D0-qualifiziert.
- a23 bindet korrekte Produkt-Source, OCI-Digest und erfolgreichen
  Compose-Smoke. Ein vollständiger Gitea-Packagepublish ist heute nicht
  belegt; der Status wird deshalb nicht rückwirkend zu `published` erweitert.
- a24 bindet Tagobjekt `dae8673f9196c39d4a1108815f11bc65a2ac2a98`,
  Commit `4c18f7a4880c2780c9e11857dcc25bb06f61e0b8`, grünen Tag-Run #909,
  Gitea-Prerelease #38, vier manifestgeprüfte Assets und den
  `linux/amd64`-OCI-Digest
  `sha256:ef099bdc864b91fdc8aa88ec7a266dc120f1caf540613332ad77a356016c38dd`.
  Der anschließende D0-Lauf blieb unvollständig. a24 ist ein veröffentlichter,
  aber kein qualifizierter oder unterstützter Installationsstand.
- a25 bindet Tagobjekt `d260a42b9427f60e048ca66886dbaf55236ce536`,
  Commit `05ea89ec9b93a6838e1ddeca66f23fe69adcfab9`, grünen Tag-Run #928,
  Gitea-Prerelease #39 und vier vollständig remote zurückgelesene Assets. Das
  Schema-2-Manifest hat SHA-256
  `3e269936be80b0f4f0a7f068e1fa2ae76744eeaffda866a5e3493aa9442d9507`
  und bindet den `linux/amd64`-OCI-Digest
  `sha256:dc5b3272a2f33649600dc050c2e55f1280c7564a33219a7ec534be92fcab9ec6`.
  Der erste Required Smoke gegen genau diesen Digest war `healthy` und
  bestätigte Version, Produkt-Source und vollständige Revision. Golden-D0 und
  Capabilityqualifications wurden nicht ausgeführt; a25 ist veröffentlicht,
  aber nicht qualifiziert oder unterstützt.

Ein späterer erfolgreicher Smoke oder Release heilt keinen früheren
create-only Kandidaten. Source, Revision, Digest, erster Required-Smoke und
Gitea-Readback werden für jeden neuen Kandidaten aus der spezialisierten
Release-Operatorquelle an das kanonische Produkt-SCM gebunden; Demo-SCM- und
Runtime-Bot-Credentials sind dafür keine Ersatzquelle (#835).

## Veröffentlichter Release v2.0.0a26 — 05.10.2026

Der neue Alpha-Release ist technisch veröffentlicht: Main-CI #1165,
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

## Historischer a15-Release- und D0-Teilnachweis (keine Installationsreferenz)

`v2.0.0a15` wurde am 17. September 2026 nach dem create-only Vertrag
veröffentlicht. Die Zwischenstände a12 bis a14 bleiben unveränderliche
Abbruch- beziehungsweise Finding-Evidence; a15 lieferte folgende Release- und
Referenzteilnachweise:

- annotiertes Tagobjekt
  `76d68f03f13bda079c40d39c941537946c6b0578` auf Commit
  `5d3c3ff6c17f2d3510b5da8a3451e088bd253fed`;
- vollständig grüner Gitea-Tag-Run #793;
- Gitea-Prerelease #29 mit genau Manifest, Wheel, sdist und versioniertem
  Runtime-Lock;
- Manifest-SHA-256
  `365623eb29bc7d2db297462259671e2d19f2afe59e6cfaee617e1a70a32ebb29`;
- Wheel-SHA-256
  `8ab75b1dbcb4207728e88c4931cfa96725d7d7d08f634634d86cbc5d19ef6449`;
- sdist-SHA-256
  `687e297d41501710bafafd04a98b10c5989251c504e85bc01d4fabb7aff9e93f`;
- Runtime-Lock-SHA-256
  `918b2d20022fe86f4bf7be005177a70d646a65c8010c549f4598ff66efbbe97b`;
- `linux/amd64`-OCI-Digest
  `sha256:7fcb934da024a2418db681588f86fd864826c34b840124e59cbdbee398eb8167`.

Der frische Compose-Smoke bestätigte Git 2.47.3, Docker-Health `healthy`,
Produktversion und vollständige Revision. Eine frische Installation aus genau
diesem Digest verwendete leeren State und neue Demo-Issues. Demo-#57 lief nach
menschlicher Freigabe über Candidate, Required Gates, PR #59, PR-CI #794,
Merge und Main-CI #795. Demo-#58 wurde durch `diff_secret_scan` blockiert;
für den Negativfall entstanden kein PR und keine damalige Main-Änderung. Ein
absichtlich wiederholter Planning-Aufruf blieb terminal blockiert und in
Audit, Dashboard und OWASP ASI01 sichtbar, ohne den bestehenden Planstatus zu
verändern. PR #59 wurde jedoch durch `demo-example-bot` statt durch den
vertraglich geforderten menschlichen Akteur gemergt. Die Evidence bestätigt
daher keinen vollständigen D0-PASS. a15 bleibt aufgrund der getrennten
Supportdeklaration der aktuelle unterstützte Alpha-Stand. Die Registry bleibt
Betreiberinfrastruktur; #658 und #694 bleiben bekannte
Qualification-/Doctor-/SCM-Grenzen.

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
`uv 0.12.6`, Python 3.10 und ein bewusst gewählter UTC-Cutoff:

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

Das Release-Gate materialisiert ab dem Folgerelease zum bisherigen Wheel, sdist
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
