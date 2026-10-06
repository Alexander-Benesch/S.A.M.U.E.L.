# Public-Snapshot-Vertrag

Dieser Stand wurde am 2026-10-06 manuell aus der privaten lokalen
S.A.M.U.E.L.-Entwicklung für GitHub als neuer Public Snapshot vorbereitet. GitHub ist derzeit weder die
operative Entwicklungs- noch die Issue-Authority und wird nicht kontinuierlich
synchronisiert.

Quelle: ursprünglicher privater a27-Releasecommit `c815eea789c14f644f25c7abacd5a8b1201f60cf`; die öffentliche Projektion ist ein neu geprüfter Ein-Commit-Root-Snapshot.

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

Dieser Snapshot ist die bereinigte Public-Projektion ausschließlich von
v2.0.0a27, Private-Sourcecommit c815eea789c14f644f25c7abacd5a8b1201f60cf.
GitHub-Tag und sieben Assets erhalten eigene Public-Commit-/Prüfsummenbindungen.
Die unveränderte private Ausgabe bleibt getrennt erhalten. Diese Public-Ausgabe
liefert Pythonpakete sowie bereinigte Installer-/Compose-Quellen unter dem
vorhandenen Schema-1-Manifestvertrag. Sie veröffentlicht kein OCI-Image oder
private Registryreference. Eine OCI-Installation allein aus diesen Assets ist
nicht belegt; dafür fehlen eine veröffentlichte Imageausgabe und deren
Schema-2-Bindung. Die private Erstinstallationsabnahme ist keine öffentliche
Qualification. Beispielwerte sind keine erreichbare Infrastruktur.
