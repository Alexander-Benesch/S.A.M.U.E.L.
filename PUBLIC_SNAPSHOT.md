# Public-Snapshot-Vertrag

Dieser Stand wurde am 2026-10-07 manuell aus der privaten lokalen
S.A.M.U.E.L.-Entwicklung für GitHub als neuer Public Snapshot vorbereitet. GitHub ist derzeit weder die
operative Entwicklungs- noch die Issue-Authority und wird nicht kontinuierlich
synchronisiert.

Quelle: privates Gitea-main `e19c8cd4dfe6ca615f4858776800292d16a75dcb`; die öffentliche Projektion ist ein neu geprüfter Ein-Commit-Root-Snapshot.

Der Snapshot enthält Produktcode, Tests, ausgelieferte Konfiguration,
Architektur-, Design- und aktive Betriebsdokumentation. Nicht veröffentlicht
werden:

- lokale `.env`-/Credential- und Runtime-Dateien;
- historische interne Handover-Dokumente;
- reale Dashboard-Aufnahmen mit Laufzeit- oder Issue-Daten;
- private SCM-, Registry-, Runner-, Netzwerk- und Personenkennungen.

Wo ein aktiver Vertrag strukturelle Deployment-Evidence benötigt, stehen im
Public Snapshot reservierte `.invalid`- oder TEST-NET-Beispielwerte anstelle
privater Endpunkte. Diese redigierten Werte sind keine öffentlich erreichbaren
Artefakte und kein Ersatz für das nicht veröffentlichte interne Auditoriginal.

Der öffentliche Snapshot ist ein lesbarer und testbarer Produktstand. Aussagen
über die aktuelle lokale Entwicklung oder einen nach dem Snapshot erfolgten
Rollout lassen sich daraus nicht ableiten.

Dieser Snapshot umfasst den integrierten Entwicklungsstand nach v2.0.0a27 einschließlich CRA/GDPR advisory Mappings. Er ist kein neuer Release und keine neue reale Abnahme. Die offenen realen Restabnahmen bleiben offen; öffentliche Beispielwerte sind keine erreichbare private Infrastruktur oder neue Evidence.

GitHub-a27-Tag und dessen sieben Assets bleiben unverändert an den ursprünglichen a27-Release gebunden. Der aktuelle Main-Snapshot enthält spätere Entwicklung einschließlich PR #973/#974/#976 einschließlich des abgeschlossenen Untersuchungsumfangs #951 und der offenen UI-Entscheidung #975; er ist kein neuer Release. Das private OCI-Image ist nicht auf GitHub verfügbar. Die Public-a27-Ausgabe besitzt eine separate Python-/Schema-1-Bindung und keinen öffentlichen Containerinstallationsnachweis.

Dokumentationsnachtrag vom 2026-10-07: lokale Quellrevision `0f9ae84fbe496028410a83c86e05cbe33eada5e3` auf Branch `docs/dashboard-documentation-help`, auf Basis des oben genannten privaten Main. Ergänzt sind die Dashboard-Felder unter Settings → Documentation Extension, die tatsächliche Grenze der eigenständigen Documentation-CLI und der unabhängige Repository-Wiki-Weg. Dieser reine Dokumentationsnachtrag ändert keinen Produktcode und erzeugt keinen neuen Release.

GitHub-a27-Tag und dessen sieben Assets bleiben unverändert an den ursprünglichen a27-Release gebunden. Der aktuelle Main-Snapshot enthält spätere Entwicklung einschließlich PR #973/#974/#976 einschließlich des abgeschlossenen Untersuchungsumfangs #951 und der offenen UI-Entscheidung #975; er ist kein neuer Release. Das private OCI-Image ist nicht auf GitHub verfügbar. Die Public-a27-Ausgabe besitzt eine separate Python-/Schema-1-Bindung und keinen öffentlichen Containerinstallationsnachweis.

Aktualisierung 2026-10-08: menschlich gemergter Main-Commit `e17c80ef0071a302a7dfd331b18553eb5623190c` (PR #979) mit OCI-Python/Pytest-Toolchain und separatem Doctor-Branchschutz-Credential für Gitea/GitHub/GitHub Enterprise. Der native a28-Release wird separat geprüft und veröffentlicht. Der Public-Snapshot hat eine eigene Git-/Paketbindung; er enthält keine private Registrycredential oder private Entwicklungshistorie. Native OCI-Evidence qualifiziert keinen Public-Container. #977 bleibt analyse-only.
