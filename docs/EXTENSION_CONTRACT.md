# Öffentlicher Extension-Datenvertrag

Stand: 19. September 2026 · Contract `documentation.static_claims` `1.0`

## Zweck und Produktgrenze

Der erste öffentliche Extensionanschluss transportiert ausschließlich gebundene
JSON-Daten für statische Dokumentationsclaims. Er lädt keinen fremden Pythoncode
in den S.A.M.U.E.L.-Prozess und stellt keinen Pluginhost, Paketmanager,
Secretbroker, Jobrunner oder Sandboxdienst bereit. Installation, Start und
Upgrade eines externen Consumers bleiben Aufgabe vorhandener Paket- und
Deploymentwerkzeuge.

Die Prozessgrenze belegt keine Isolation und kein Vertrauen. S.A.M.U.E.L. prüft
Schema, Kompatibilität und Bindung der Daten; der externe Producer erhält
dadurch keine Gate-, Approval-, Merge- oder Publishauthority. Der erste Effekt
ist fest `advisory`. Eine spätere bindende Verwendung benötigt die getrennten
Trust- und Requestnachweise der Evidence-Grenze.

## Öffentliche Artefakte

Der unterstützte Python-Namespace ist `samuel.extensions`. Sprachneutrale JSON
Schemas werden im Wheel unter `samuel/extensions/schemas/` ausgeliefert:

- `capability-manifest.v1.json`
- `request.v1.json`
- `result.v1.json`

`samuel-extension validate-manifest`, `samuel-extension status` und
`samuel-extension validate-result` stellen dieselben Prüfungen als read-only
CLI bereit. `samuel-documentation` bereitet den konkreten Inventory-Request
vor, verifiziert das Resultat und übergibt erst danach eine begrenzte
Projektion an den vorhandenen Git-Publisher. Externe Consumer müssen keine
internen Module importieren. Imports
aus `samuel.slices`, `samuel.adapters`, `samuel.core`, Handlern oder Stores sind
kein öffentlicher Vertrag.

Der Capability-Manifestvertrag ist bewusst geschlossen:

```json
{
  "schema": "samuel-extension-capability.v1",
  "capability_id": "documentation.static_claims",
  "contract_version": "1.0",
  "transport": "filesystem-json",
  "effect": "advisory",
  "claim_families": ["documentation.inventory.v1"],
  "permissions": ["repository:read"],
  "credentials": []
}
```

Request und Resultat binden Capability und Version, eine begrenzte Request-ID,
das kanonische Repository `owner/name`, den exakten 40-stelligen Git-Head,
Claimfamilie, Advisory-Effekt, Policy- beziehungsweise Requestdigest und
digestierte JSON-Artefakte. Ein Resultat gilt nur für den exakten Request. Eine
andere Request-ID, Subjectrevision, Claimfamilie oder Contractversion blockiert
die Annahme.

Alle Contractdigests verwenden kanonisches UTF-8-JSON: Objektschlüssel werden
lexikografisch sortiert, Whitespace außerhalb von Strings entfällt,
`ensure_ascii` ist aus und optionale Felder mit `null` werden vor der
Serialisierung ausgelassen. Damit kann der sprachneutrale Consumer denselben
Digest ohne Pydantic- oder Produktabhängigkeit bilden.

## Konkrete Claimfamilie `documentation.inventory.v1`

Die paketierten Schemas `documentation-policy.v1.json` und
`documentation-claims.v1.json` schließen den ersten fachlichen Payloadvertrag.
Die Policy bindet ein kanonisches Repository, den Consumer-Identifier, seinen
exakten Tooldigest und eine sortierte, duplikatfreie Liste von höchstens 128
normalisierten Markdownpfaden. Claims müssen exakt dieselbe Pfadmenge liefern
und binden je Dokument Medientyp, Bytezahl und SHA-256. Ein Dokument ist auf
1 MiB, die gesamte gebundene Menge auf 8 MiB begrenzt.

`samuel-documentation prepare` liest Policy und Consumerwerkzeug als Git-Blobs
aus dem exakten aktuellen Commit und erzeugt Request sowie kanonisches
Policyartefakt. Der externe Consumer liest dieselben Commit-Blobs und erzeugt
Claims und Resultat. `validate` prüft anschließend Request-/Resultbindung,
Policy- und Tooldigest, exakte Coverage, Checkout-Head sowie jedes Dokument
erneut gegen Git. Arbeitsbaumbytes, ungetrackte Dateien oder ein bloßer
Consumer-Erfolgsstatus ersetzen diese Prüfung nicht.

Vor einer Publikation werden die gebundenen UTF-8-Dokumentbytes mit der
vorhandenen Secret-Shape-Policy sowie begrenzten Regeln für private
Netzadressen und lokale Credentialpfade geprüft. Fehler nennen nur Regel,
Pfad und Zeile, nie den gefundenen Wert. Die veröffentlichte Seite enthält nur
Pfad-, Größen-, Digest- und commitgebundene Quelllinks. Sie erklärt sichtbar,
dass sie advisory und nicht autoritativ ist; freie Prosa wird nicht als
formale Wahrheit bestätigt.

## Operatorwahl und D08

`config/extensions.json` ist die einzige ausgelieferte Auswahlquelle. Der
Default lautet:

```json
{
  "schema_version": "1.0",
  "capabilities": {
    "documentation.static_claims": {
      "enabled": false,
      "required": false,
      "contract_version": "1.0",
      "manifest_path": null
    }
  }
}
```

Die Datei wird beim Start des verwendenden Prozesses beziehungsweise Werkzeugs
gelesen. Es gibt keinen Runtime-Override und kein Hot Reload. Der Operator
ändert sie über den bestehenden Dashboard-Settings-Editor im expliziten
Setup-/Rekonfigurationsbetrieb aus D08 und startet den Produktionsprozess
anschließend mit read-only Konfiguration neu. Das Dashboard zeigt gespeicherten
und beim Prozessstart wirksamen Extensionzustand getrennt. Direkte API-Aufrufe
werden im Produktionsmodus vor dem Dateizugriff mit
`configuration_frozen` abgewiesen.

Ein optionaler deaktivierter, fehlender oder inkompatibler Consumer verändert
keinen Coreworkflow. Eine ausdrücklich erforderliche Capability blockiert die
betroffene Extensionaktion, wenn sie deaktiviert, nicht vorhanden oder
inkompatibel ist. `required=true` lässt sich daher nicht durch
`enabled=false` umgehen. Die Installation eines Packages oder Manifests
aktiviert die Capability nicht.

## Eingangs- und Datengrenzen

- Contractdateien müssen reguläre UTF-8-JSON-Dateien bis 1 MiB sein. Symlinks,
  doppelte Schlüssel, unbekannte Felder und Typumwandlung werden abgewiesen.
- Artefaktpfade sind normalisierte relative POSIX-Pfade ohne Traversal. Ein
  referenziertes Artefakt ist auf 8 MiB begrenzt und mit kanonischem SHA-256,
  Byteanzahl und Medientyp gebunden.
- Die erste Capability fordert nur `repository:read` und transportiert keine
  Credentials. Repository- und spätere Publisherzugänge bleiben außerhalb der
  JSON-Artefakte und werden nach Wirkung getrennt bereitgestellt.
- Freie Prosa erhält keine formale Wahrheitszusage. Die konkrete
  `documentation.inventory.v1`-Payload, Coveragebindung und Publikation liegen
  im Folgescope #636.
- Version, Installation, Migration, Restore oder ein anderes Trustprofil
  werten historische Advisoryresultate nicht zu Required Evidence auf.

Fehlerausgaben nennen Contractzustand und Feldgrenze, enthalten aber keine
Payloadinhalte, Tokens oder Credentials. Der Vertrag erzeugt keinen eigenen
Runtime-State und benötigt daher keine zusätzliche Backup-, Restore- oder
Retentionklasse.

## Kompatibilität, Veröffentlichung und Lizenz

Kompatibilität ist in dieser Stufe exakt `documentation.static_claims` `1.0`.
Wildcards, automatische Downgrades und Versionsfallbacks sind nicht
unterstützt. Änderungen an geschlossenen Feldern oder Semantik benötigen eine
neue Contractversion. Die bestehende Version bleibt solange lesbar, wie sie
als unterstützt dokumentiert ist.

Der Contract, die JSON Schemas und das Conformance-Fixture sind Bestandteil des
S.A.M.U.E.L.-Repositories und stehen unter dessen Apache-2.0-Lizenz. Diese
Lizenzierung überträgt keine Lizenz auf externe Consumer oder deren Inhalte.
Vor Veröffentlichung eines externen Referenzconsumers wird dessen eigene
Lizenz ausdrücklich geprüft und dokumentiert.

## Qualificationgrenze

Die Repositorytests prüfen Schema, Versionsbindung, Required-/Optionalzustände,
Pfade, Größen, Digests, Replay und einen separaten Fixtureprozess, der nur
`samuel.extensions` nutzt. Sie sind keine reale externe Qualification. Dafür
muss der in #636 implementierte Consumer im unabhängigen Pipeline-Escape-
Repository mit minimalem Daten-/Credentialzugriff
ausgeführt werden. Erstpublikation, identischer No-op, verlorenes lokales
Receipt, frischer Prozess, Remote-Drift und falscher Marker/Digest sind dort
positiv beziehungsweise negativ zu belegen. Der Consumer erhält keine
Publishercredentials; der Referenzconsumer läuft mit leergeräumtem Environment
und verweigert bekannte Credentialvariablen, ohne deren Werte auszugeben.
Seine Apache-2.0-Lizenz ist im Zielrepository
ausdrücklich dokumentiert.

Der Produktpublisher verwendet für Wiki und Inventory denselben
`publish_projection`-Effekt: normaler Git-Push ohne Force, Remote-Marker,
vollständige Revision und Contentdigest, atomar geschriebenes lokales Receipt
und ein No-op bei identischem Remotezustand. Geht nur das lokale Receipt
verloren, wird es nach erfolgreichem Remotevergleich neu geschrieben; Drift
oder ein falscher Marker blockiert. Das ist kein zweiter Publisherstore.
