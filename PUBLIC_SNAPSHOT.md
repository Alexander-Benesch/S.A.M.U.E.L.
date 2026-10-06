# Public-Snapshot-Vertrag

Dieser Stand wurde am 2026-10-06 manuell aus der privaten lokalen
S.A.M.U.E.L.-Entwicklung für GitHub als neuer Public Snapshot vorbereitet. GitHub ist derzeit weder die
operative Entwicklungs- noch die Issue-Authority und wird nicht kontinuierlich
synchronisiert.

Quelle: ursprünglicher privater a26-Releasecommit `177243063052c03e14b7491b94750e6baa4d60cd`; die öffentliche Projektion ist ein neu geprüfter Ein-Commit-Root-Snapshot.

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

Dieser Snapshot ist die ausdrücklich bereinigte GitHub-Projektion ausschließlich des ursprünglichen Releases v2.0.0a26. Er enthält keine späteren Main-Änderungen und keine neue reale Abnahme. Die offenen realen Restabnahmen bleiben offen; öffentliche Beispielwerte sind keine erreichbare private Infrastruktur oder neue Evidence.

GitHub-Tag und vier Pythonassets erhalten eigene Public-Commit-/Prüfsummenbindungen. Das unveränderte private Originalrelease bleibt getrennt erhalten. Die Public-Ausgabe verwendet den vorhandenen Schema-1-Pythonmanifestvertrag. Sie veröffentlicht kein OCI-Image und keine private Registryreference; Containerinstallation ist aus diesen GitHub-Assets nicht belegt.
