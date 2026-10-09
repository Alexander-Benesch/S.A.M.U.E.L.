# Public-Snapshot-Vertrag

Bereinigte, nicht autoritative Projektion vom 09.10.2026 aus dem freigegebenen
nativen Main `d490fb16bb959a6a990e4ac808c45d17821374ec`. Der native a29-Productrelease bindet
`1a1c1f2eeaf324b62074a41adc9dc2474057561f`; dieser Main ergänzt dessen freigegebene
Release-/Installationsdokumentation. Unveränderte Produktsemantik wird separat
gegen den nativen a29-Quellstand geprüft. PR #991 ist noch ungemergt und wird
hier nicht vorweggenommen.

GitHub bleibt ein geprüfter Ein-Commit-Root-Snapshot. Private Entwicklungshistorie,
ungetrackte Auditoriginale, Credentials, Operatorstate, Screenshots, interne
SCM-/Registry-/Runner-/Netzwerk-/Personenkennungen werden nicht veröffentlicht.
Vorherige veröffentlichte, bereinigte historische Vertragsfixtures bleiben erhalten.
Beispiele verwenden reservierte `.invalid`-/TEST-NET-Werte und stellen keine
reale Infrastruktur oder neue Abnahmeevidence dar. Gitea bleibt Entwicklungs-
und Issueauthority; es gibt keinen kontinuierlichen Historymirror.

Enthalten sind #989 (registrierter lokaler OCI-Projektzugriff, Git-Härtung,
Gate-7-Fallback im statischen Preflight und Readinessaggregation), #980
(gebundene Verifierprobe im effektiven TEST-Budget) und die bestehende
providerneutrale SCM-/Worker-/Scanner-/LLM-/Verifierarchitektur. Kein H3-Remote-
Betrieb und keine eigene Sandbox. #873 liefert weiterhin advisory CRA/GDPR-
Mappings; der volle aktive Pack-/Policy-/Auditvertrag bleibt offen.

Die öffentliche a29-Ausgabe erhält eigene Source-, Tag-, Paket- und OCI-Digests.
Sie wird aus dem bereinigten Public-Tree und unveränderten hashgebundenen
Runtime-/Buildlocks erzeugt. Das Manifest des tatsächlich veröffentlichten
GitHub-Releases ist die Installationsauthority; private Registryreferenzen und
native Image-/Installationsreceipts werden nicht als Public-PASS übernommen.
Der beabsichtigte OCI-Zielpfad ist `ghcr.io/alexander-benesch/samuel`; erst ein
veröffentlichtes Schema-2-Manifest und erfolgreicher unabhängiger Pull belegen
seine öffentliche Verfügbarkeit. Vorherige a26/a27/a28-Tags und Releaseassets
bleiben create-only und unverändert.

Lokale Build-/Test-/Installationsnachweise bleiben technische Einzelbelege,
kein Golden-/D0-, Produktionssupport- oder vollständiger Isolationsnachweis.
Historische FAILs bleiben FAIL. Für neue Alpha-Qualification sind saubere
Neuinstallationen ohne alte State-/Checkpoint-/Projektreceipts vorgesehen.
