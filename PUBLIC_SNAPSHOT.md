# Public-Snapshot-Vertrag

Dieser Stand wurde am 2026-09-29 manuell aus der privaten lokalen
S.A.M.U.E.L.-Entwicklung für GitHub als neuer Public Snapshot vorbereitet. GitHub ist derzeit weder die
operative Entwicklungs- noch die Issue-Authority und wird nicht kontinuierlich
synchronisiert.

Quelle: privates Gitea-main `fb7c3df72fb9121d26bf7b6d49ffe33eeda518ea`; die öffentliche Projektion ist ein neu geprüfter Ein-Commit-Root-Snapshot.

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
