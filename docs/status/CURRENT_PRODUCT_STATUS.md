# Current Product Status

## Untersuchung #951 abgeschlossen — UI-Entscheidung #975 offen

Der ursprüngliche #951-Auftrag fordert ausdrücklich Ist-Stand, fachliche
Prüfung, vorhandene Checks und minimale Empfehlung vor späterer Umsetzung.
Alle acht Untersuchungsfragen sind beantwortet. #951 ist als
**INVESTIGATION_COMPLETE** geschlossen; die ursprünglichen Kriterien bleiben
erhalten. Am integrierten Code-Stand `20e3a172ef0b7398c4731be09172e310277c2f4a` bestehen die bisherigen
40 Fälle sowie 13 integrierte JavaScriptregressionen: **53 PASS, 0 SKIP** mit
bereits vorhandener Node v24.11.0 nur im Testprozess-PATH. Der erste Nachlauf
mit 40 PASS / 13 SKIP und die Korrektur des zunächst falschen PASSzählers
bleiben erhalten. Die ursprüngliche Browserbeobachtung ist historische
Evidence; keine neue Live-Providerprobe oder Save-/Route-/Configänderung.

Die offenen UI-Lücken und die Entscheidung zwischen freier Eingabe mit
Katalogvorschlägen oder Dropdown mit manuellem Fallback liegen jetzt in #975.
Dies ist keine fertig implementierte Setupauswahl oder neue Qualification.
Gatewaykatalog, native Endpoint-/Konto-Verfügbarkeit und Task-Suitability
bleiben getrennt; manuelle IDs und Setup→Persistenz→Recreate→Freeze bleiben.
Die frühere NOT_IMPLEMENTED-Baseline von #951 ist durch diesen ausdrücklich
auf Untersuchung begrenzten Abschluss überholt.


## Entwicklungsdelta nach a27: Framework-Mappings — 06.10.2026

Der #873-Kandidat ergänzt CRA/GDPR als versionierte advisory Mappings,
gemeinsamen Loader, explizite Scope-/Evidence-Referenzen und vier Framework-
Legenden im Dashboard. Bestehende OWASP-/AI-Act-Zuordnungen bleiben kompatibel.
Die [Architekturprüfung A–D](../COMPLIANCE_FRAMEWORK_MAPPINGS.md#architekturprüfung-ad)
legt verbleibende feste Kopplungen und verpflichtende Privacy-/Securitygrenzen
offen. Das ist PARTIALLY_IMPLEMENTED; der aktive Pack-/Policy-/Auditvertrag
und seine reale Consumerabnahme bleiben in #873 offen. Der Kandidat wird erst
nach PR-Merge zum Main-Stand; a27 enthält diese spätere Entwicklung nicht.

## Veröffentlichter Installationsstand v2.0.0a27 — 06.10.2026

Der offizielle Release bindet Productcommit
`c815eea789c14f644f25c7abacd5a8b1201f60cf` und annotiertes Tagobjekt
`ae750dcb254316b2ef5640d868e85288ad3b4bab`. PR #972, Main-CI #1102 und
Tag-CI #1103 sind erfolgreich. Die sieben zurückgelesenen Release-Dateien
umfassen Wheel, Sourcepaket, Runtime-Lock, OCI-Kit, beide Compose-Dateien und
Manifest. Manifest-SHA-256:
`429024d68722b775b25c90636a2a50427a2b1a432d891af4ec4462335afa6df7`.
Die unveränderliche `container.reference` im Manifest bindet OCI-Digest
`sha256:bdcebe2ea517e4cea9c7730f490e042918ac8ce96d616b6b160740b8226a954c`.

Die unabhängige Erstinstallation aus den **veröffentlichten** Release-Dateien
auf frischem Ubuntu 24.04.5, Docker 29.8.2 und Compose 5.6.0 ist PASS:
leere Operatorpfade, Setup vor SCM-Konfiguration, authentisierte Einrichtung,
Productionstart, Docker `healthy`, CLI-/API-/Imageidentität, Persistenz,
Recreate und Konfigurationsfreeze. Die Produktidentität stammt aus dem Image;
kein Runtime-Checkout wird als Installationsinput vorausgesetzt. Private
Registryzugänge gelten nur im Docker-Kontext des ausführenden Operators.

#970/#971 sind mit eigenen Nachweisen geschlossen. Der vollständige Bericht
und die veröffentlichten Installationsreceipts sind an den Issues angehängt.
Diese technische Installation ist **keine** Workflow-/LLM-, Golden- oder
Formal-D0-Abnahme: Operational Readiness blieb `blocked`; #962 bleibt offen.
Historische FAIL-/UNKNOWN-/Teilnachweise bleiben erhalten. a15 ist keine
aktuelle Installations- oder Supportreferenz. Für neue Installationen gilt
weiterhin der ausgewählte neueste veröffentlichte Release mit verifiziertem
Manifest gemäß [INSTALL](../INSTALL.md#91-oci-erstinstallation-auf-einem-leeren-docker-host-970).

## Productdelta nach #965 — 06.10.2026

PR #965 ist menschlich gemergt: Product-Main
`78830860e3861be35d6bc41d946ba60d829c296e`, vollständige Main-CI #1174 PASS.
Das Wiki wurde ausschließlich aus diesem Main gebaut und unabhängig remote
zurückgelesen: `32d8012d4f8a21c87b13329fd79c4579fff884ff`.

#954 ist anhand seiner sechs eigenen Implementierungs-, Projektions-,
Regressions- und Dokumentationskriterien geschlossen. Der vorhandene
candidategebundene Abschluss zeigt dieselben Contractkriterien in Planreihenfolge;
nur eigene immutable PASS-Beobachtungen mit aktueller Issue-, Subject-,
Contract- und Plan-Kommentarbindung setzen Checkboxen. Fehlende, fremde,
stale oder beschädigte Evidence bleibt UNKNOWN; FAILED und offene MANUAL
bleiben sichtbar. Der Originalplan bleibt unverändert. Dieser enge Scope
fordert keine zusätzliche reale Abnahme; daraus folgt kein neuer E2E-/Golden-/D0-PASS.

#956 bleibt PARTIALLY_IMPLEMENTED: Der konkrete äußere IssueReady-Startlabeldefekt
ist in beiden Subscriberreihenfolgen geschützt. Die allgemeine
failed/aborted-/Watch-/Re-Entry-Regel und ein optionales Prüflabel bleiben
Maintainerentscheidungen. Native eigene Abnahmen und historische FAILs
werden durch den Teilfix nicht ersetzt.

Der native Readback dieses Deltas zählt 18 offene Product-Issues nach dem
eigenen Abschluss von #954. Ungemergte Folge-PRs sind kein Main-Stand.
Die folgenden datierten Release-/Kampagnenabschnitte behalten ihre damaligen
Commits, Issuezahlen und Evidence; ihre #954-Backlogreferenzen sind historische
Stände vor diesem Delta. v2.0.0a26 und die 24 nach #962 übertragenen realen
Restabnahmen bleiben unverändert. Das vollständige Testkonzept folgt erst
nach der vorgesehenen getrennten Maintainerinstallation.

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
keine neue Abnahmeruntime oder Workflowfreigabe. Die bestehende a15-
Supportdeklaration und historische FAIL-/UNKNOWN-/Teil-Evidence bleiben erhalten.

## Administrativer Altlastenabschluss und Releasezweck — 05.10.2026

Der Maintainer hat die bereits implementierten, ausschließlich wegen eigener
Restabnahmen offenen Issues geschlossen. Übertragen sind #422, #468, #482, #521, #549, #575, #636, #639, #658, #668, #679, #691, #693, #694, #822, #823, #830, #844, #846, #847, #859, #894, #900, #952. Ihre genaue Restschuld und die unverändert
ungeprüften Kriterien stehen im
Abnahmeträger #962.
**Administrativ geschlossen bedeutet kein Abnahme-PASS.** Historische FAILs,
UNKNOWN-Ursachen und datierte Teilnachweise bleiben mit ihrer eigenen Bindung
erhalten. Ältere datierte Aussagen, dass diese Issues wegen Abnahmen offen
bleiben oder ihre Kampagne fortzusetzen ist, sind für den heutigen Issue-
und Arbeitsstatus durch diese ausdrückliche Maintainerentscheidung ersetzt.
PR #960 ist menschlich gemergt; Produkt-Main vor diesem Releasedelta ist
`2d3729e05dfdd2cf7b2b9ef997c0ae7181a3f806`, vollständige Main-CI #1162 PASS.

**Fehlender Abnahme-PASS ist kein Blocker für den beauftragten v2.0.0a26.**
Dieser Alpha-Release dient zunächst der Installation von Anfang an in einer
getrennten Umgebung durch den Maintainer. Erst danach wird ein vollständiges
Testkonzept von Normaldurchlauf bis Providerausfall erstellt. Jetzt entstehen
weder dieses Konzept noch neue Abnahmeläufe, START-Labels oder Qualification-
Subjects. Der normale Source-/Human-Merge-/CI-/Paket-/Tag-/OCI-/Smoke-/Manifest-
und Remote-Readbackvertrag bleibt gültig. Keine Golden-/D0-, Betriebs-,
Retentionaktivierungs- oder Supportfreigabe durch administrativen Abschluss.

Nicht begonnene Issues und verbleibende Implementation oder Design bleiben
unverändert offen. Dazu zählen die echten Findings #880/#956 und ihr
Findingträger #961. Dessen bisherige Altlastenübersicht ist datierte Evidence;
die jetzt übertragenen offenen Abnahmen werden ausschließlich in #962 geführt.

## Eigene releasegebundene Consumerabnahme — 05.10.2026

#636/#639 sind am tatsächlich veröffentlichten immutable OCI-Artefakt
`192.0.2.206:3001/alexmistrator/samuel@sha256:dc5b3272a2f33649600dc050c2e55f1280c7564a33219a7ec534be92fcab9ec6`
von v2.0.0a25 / Product `05ea89ec9b93a6838e1ddeca66f23fe69adcfab9`
real abgenommen. Unabhängiger Pipeline-Escape-Consumer aus Commit
`558beeaefa4d9599592c8043a3eaefe89ac8e19e`, vorhandene policygebundene
Tool-/Claims-/Sourcebindung, credentialfreier Standardbibliotheksprozess.
Die installierten öffentlichen CLIs belegen Prepare/Validate, Subject-/Schema-
Negativfälle und Enable/Disable/Optional/Required/Absent/Incompatible/Available.
Die reale Gitea-Wiki-Qualification belegt Erstpublish, identischen No-op,
Receiptverlust mit archiviertem Original und frischem Publisherprozess sowie
isolierte Fremddatei-/Marker-Negativrefs mit unverändertem Head nach Ablehnung.
Positiver Qualifikationsref `qualification-636-a25-20261005-01`:
`db93228a9e6424a11620802ecfd9c70b4e565b18`. Produktiver Wiki-Main blieb
`b1c34c495e4f992a56a05a6a228a76daef0980ff`. Alle Ergebnisse sind advisory;
keine Sandbox-/Lifecycleplattform, Required-Workflowauthority oder D0-Freigabe.

Der eigene D20/D21-Realrest ist damit erfüllt; #636/#639 besitzen nur noch
den Dokument-/Main-/Wiki-/Issueabschluss nach Human Merge dieses Deltas.
Sie sind ausdrücklich vom vollständigen Development Golden #859 und Formal
D0 #658 unabhängig. Der a25-Nachweis wird nicht als neu veröffentlichter
58ddcf0a-Release ausgegeben. Aktuelle Findings und die konkrete Restschuld
aller übrigen Altlasten sind in #961 belegt; kein stellvertretender Child-PASS.
Der natürliche #575-Timeout auf der getrennten 58ddcf0a-Installation endete
mit clarification_timeout/Exit1/status:failed; der positive menschliche
Klärungsdialog und #880s Multi-MANUAL-Abnahme bleiben separat offen.

## Eigener Taskeditor-Abnahmedelta — 05.10.2026

#952s vorhandener Taskeditor ist durch #958 korrigiert und menschlich integriert.
Der native Nachtest des gemeinsam integrierten Main
`0ced5203a9955ab0bf332d2864cb168f1cd05b8a` besteht für Planning,
Implementation, Review und Healing: echter gefüllter Katalog, funktionierende
Schedule-Gegenprobe, ignorierte verspätete Antworten und sichtbare
Leerlisten-/Netzfehler sowie unbekannte alte Auswahl. Gespeicherte Config und
Routen blieben unverändert; Evaluation wurde nicht aufgerufen. Evidence und
historischer FAIL bleiben getrennt in #952, Kommentar45842.

Main-CI1155 bleibt historischer FAIL. #959 korrigiert ausschließlich die
kontrolliert reproduzierte Lease-Testschwäche; die genaue Ursache des damaligen
CI-Zeitverlaufs bleibt UNKNOWN. Menschlicher Merge/Main
`58ddcf0adca8a447897f398314592304135f390c`, vollständige Main-CI1157 PASS und
Wiki-Remote `b1c34c495e4f992a56a05a6a228a76daef0980ff` sind belegt. Zwischen
0ced5203 und 58ddcf0a änderten sich nur der Resumetest und generierte
Capability-Digests; der native UI-Nachweis behält ausdrücklich seine
0ced5203-Artefaktbindung und wird nicht als neues installiertes Image ausgegeben.

#952 besitzt damit nur noch den eigenen Dokument-/Main-/Wiki-/Issueabschluss
nach menschlichem Merge dieses Deltas. #951 und #954 bleiben separat; keine
neue UI-/Routingimplementation, kein voller Golden-/D0- oder fremder
Issueabschluss. Die folgenden älteren datierten Untersuchungsstände bleiben
Historie und sind für #952s oben belegte Teile superseded.

## Abnahmen und nächste gebündelte Kampagne — 04.10.2026

Live-Readback: integrierter Main `190836962cd6997145126ff011b6aa9b79dcb26c`,
vollständige Main-CI #1141 PASS. Wiki aus demselben Main publiziert und
unabhängig remote verifiziert: `cd34ffe6cc9433985714a39243198d144485aa68`.
Der eigene Subject `19083696-20261004-01` im isolierten Repository
`example-owner/samuel-r24-19083696-20261004-01`, Issue #1 / PR #2, lief nach
zeitgültigem 19/19 READY/Exit0 bis echten Human Merge und nativen Abschluss.
Candidate `757159acc5c9863109a54e40b14af0bdaa68f106`, Human Merge
`7b54d760be47b9d401871d2df28e2975647187d1`, Candidate-CI #1143 und Merge-CI #1144
PASS, 6/6 automatische AC, 13/13 Required Gates, Review pass ohne Findings,
217 HMAC-verifizierte Auditrecords. Kein Agent-Watch/Resume, Subjectfix,
Inputwechsel oder Cross-run-PASS. Keine MANUAL-Kriterien, kein neuer
MANUAL-/Healing-/Evaluation-/vollständiger Golden-/Formal-D0-PASS. Receipt:
`/var/lib/samuel-example/.local/share/samuel-preparation-19083696-20261004/development-e2e-19083696-20261004-01/terminal-result.json`.

#889 und #891 sind nach eigener technischer/menschlicher Abnahme und #953s
Main-/Wikianschluss geschlossen. #944s verbleibende Workflowzeit-Sichtprüfung
ist ausdrücklich menschlich abgenommen; Issue geschlossen. #812 ist gemäß
Maintainer geschlossen, weil der historische a18-Pre-Tag-Receipt nicht mehr
beschaffbar ist: dieser AC ist nicht nachgewiesen, nicht abgehakt und kein PASS.
Zukünftige Releaseanforderungen bleiben unverändert. 42 offene Product-Issues
im Readback; zusätzliche spätere Findings #951/#952/#954 bleiben separat.

Die gemeinsame Vorbereitung wird im bestehenden #859 und im
[Test-/Qualification-Runbook](../runbooks/TEST_AND_QUALIFICATION_RUNBOOK.md#gemeinsamer-abnahmeplan-der-verbliebenen-altlasten--859)
geführt. Erst deterministische Restfälle/Required CI/Human Merge, dann finalen
Main binden und nur invalidierte Vorbereitung erneuern. Danach echte
Negativ-/Sonderfälle und vollständige Q00–Q16-Strecke; veröffentlichte AC und
Formal D0 erst auf immutable Release. Noch kein neuer Subject oder aktuelles
READY. Die folgenden älteren Abschnitte sind datierte Evidence und keine
erneuten Aufträge für bereits abgeschlossene Teile.

## Eigene Operator-Abnahmen und verbleibende Grenzen — 04.10.2026, f514ddee

Integrierter Product-Main `f514ddee9db59b77d07c2bca18f1e765fb6d2cf4`,
vollständige Main-CI #1139 PASS. #950 ist human gemergt; Wiki exakt dieses
Main gebaut, regulär publiziert und unabhängig remote verifiziert:
`6c86a4fc1ac652280b8a532b38a8e827c7a78c08`. Dieser Head besitzt keinen neuen
vollständigen Development-E2E-Nachweis; der abgeschlossene a0f16c02-Subject
bleibt separat gebundene historische Hauptpfad-Evidence.

- #889: technische und menschliche Operator-Bedienabnahme erbracht. Der
  Maintainer bestätigt Production-/Ersteinrichtungshinweis und erkennbare
  gespeicherte/wirksame Zustände beziehungsweise Neustartbedarf. Eigene
  Setupinstanz auf f514ddee über den bestehenden Production-Compose-/Setupweg
  gestartet; nach der Abnahme die gespeicherten Teständerungen ausschließlich
  über bestehende Settings-APIs auf das Referenzprofil zurückgestellt und
  Production neu erzeugt. Alle Configdateien semantisch wie die Referenz;
  `production`, `writable=false`, `restart_required=false` und gleiche
  gespeicherte/wirksame Digests real zurückgelesen. Historische E2E-Instanz
  unverändert. Eigener Receipt `889-post-human-production-readback.json` unter
  `/var/lib/samuel-example/.local/share/samuel-display-acceptance-f514ddee-20261004/`.
  Rest nur dieser Dokument-/Main-/Wiki-/Issueabschluss; kein weiterer
  menschlicher Bedien- oder Produktbauauftrag.
- #891: der Maintainer hat die reale Anzeige eines laufenden LLM-Consumers und
  den anschließenden Wechsel zu idle ausdrücklich beobachtet (Issuekommentar
  #45545). Der bislang offene visuelle Zeitabschnitt ist damit menschlich
  bestätigt. Die früheren konkreten Current-/Last-/Route-Readbacks und
  Regressionen bleiben an ihre eigenen Heads/Runtime gebunden. Die neue
  menschliche Meldung enthält keine exakte Call-/Subject-/Runtimebindung;
  diese bleibt UNKNOWN und erzeugt keinen neuen Head-/Qualification-PASS.
  Kein zusätzlicher Call/Subject und kein Wiederbau der vorhandenen Projektion
  für diesen eigenen Bedienumfang. Dokument-/Statusabschluss verbleibt;
  spätere Echtzeitoptimierungen bleiben separat.
- #944: Main-/Wikianschluss und allgemeine Dashboard-/Zeitzonen-Sichtabnahme
  erbracht. Nur tatsächlich befüllte Workflowzeitfelder bleiben beim nächsten
  ohnehin geplanten regulären Subject zu beobachten. Dafür kein Extra-Subject
  oder künstlicher Evaluation-Consumer.
- #694: eigene positive/falscher-Sollwert/positive Doctor-Matrix vorhanden.
  Der vorhandene dauerhafte Operatorzugang ist weiterhin als aktiv benötigt
  verzeichnet und darf nicht für eine Widerrufsabnahme entzogen werden.
  INSTALL §1.2 verlangt einen getrennten temporären Branchschutz-Prüfer und
  tatsächlichen Widerruf; Prozessende ist kein Ersatz. Dessen autorisierter
  Lifecycle bleibt eine eigene Operatorgrenze, keine neue Token-/IAM-Plattform
  und kein globaler Entwicklungsblocker.
- #812: integrierter a18-Changelog und PR-/Main-CI sind vorhanden. In den
  bekannten verbliebenen historischen lokalen Belegorten und dem vorhandenen
  CI-Artefaktreadback ist kein eigener Pre-Tag-Receipt belegt. Status
  DOC_ONLY/NEEDS_EVIDENCE; heutige Tests oder Tag-CI ersetzen ihn nicht.
- #951/#952: neue konkrete Maintainerfindings zur Einrichtung-Modellauswahl/
  Katalog-Freshness und zur nicht folgenden Taskeditor-Modellliste trotz
  funktionierender Schedule-Auswahl. Spätere Untersuchung ausdrücklich vor
  Umsetzung; kein Rest der #889-Abnahme, keine aktuelle Root-Cause-Behauptung.

45 offene Product-Issues vor Integration/issueeigenem Abschluss dieses Deltas.
Keine neue Preparation READY oder E2E-/Golden-/D0-Authority. Der nächste
menschliche Haltepunkt ist Human Merge dieses engen Dokumentdeltas; danach
Main-CI/Wiki zurücklesen und nur tatsächlich invalidierte Vorbereitungsschritte
für den finalen Candidate erneuern. `E2E_PATH_IMPACT=NO` für diesen Delta.
Ältere datierte Offen-/Warteformulierungen unten sind für die hier ausdrücklich
abgenommenen Teilumfänge superseded; historische Receipts bleiben unverändert.

## Aktueller eigener Abschluss nach #949 — 04.10.2026

#949 ist human integriert auf `45a8cf54ad306c39083ee886a0345fdf41dffa67`; vollständige
Main-CI #1136 PASS. Wiki desselben Main regulär gebaut/publiziert und unabhängig
source-/inhaltsgebunden remote verifiziert: `3ee8f5fea88c9c81f3d57a23817a1e2064797489`.
#843 und #845 sind nach ihren eigenen ursprünglichen Ops-AC geschlossen;
43 offene Product-Issues. Die folgenden älteren Rest-/Kandidatenformulierungen
sind für diese beiden eigenen Abschlüsse superseded, ihre datierten Belege bleiben
unverändert. Receipt: `949-own-843-845-closures.json` unter
`/var/lib/samuel-example/.local/share/samuel-issue-closure-a0f16c02-20261004/`.

#944 besitzt in PR #950 eine enge Darstellungskorrektur für die bereits
gespeicherte `agent.timezone`; Human Merge/Main-/Wikianschluss und allgemeine
Sichtabnahme sind auf f514ddee erfolgt. Nur befüllte Workflowzeitfelder bleiben
beim nächsten regulären Subject zu prüfen. Kein Runtimeeingriff, neuer E2E-/Release-/Formal-D0-/Sammelclaim.


Stand: 2026-10-04, Europe/Berlin. Selektiver Abschlussabgleich an
`a0f16c022bacbe5d9d6978e37fe8a2288cdd3e1d` nach Human Merges #947/#946.
Eigener neuer Development-Hauptpfad mit MANUAL bis Human Merge belegt;
initiales Approvalfinding #948 und SCM-Abschlussumfang #890 bleiben erhalten.
Ältere Subjects auf 7843d4fd/41d39b0e/1a87ef03/eb6cce18 bleiben separat.
Aktuellen Main immer live lesen; keine neue Authority durch Statusdokumentation.

## Identitaet und Baseline

| Feld | Aktueller Befund | Authority |
|---|---|---|
| Gitea `main` | #950 human integriert: `f514ddee9db59b77d07c2bca18f1e765fb6d2cf4`; heutigen Head live lesen | `CURRENT_CODE_FACT` |
| lokaler Product-`main` | sauberer tracked Checkout f514ddee; untracked Reviewentwurf unverändert | `CURRENT_TEST_EVIDENCE` |
| letzter publizierter Product-Release | `v2.0.0a25`; keine a26-Releasebehauptung | `CURRENT_CODE_FACT` |
| letzter Tag / Releasebasis | `v2.0.0a25`; die spaeteren Product- und Docs-Commits sind kein Release | `CURRENT_CODE_FACT` |
| Integrations-CI | vollständige Main-CI #1139 PASS auf f514ddee; ältere CI bleibt an ihren Heads gebunden | `CURRENT_TEST_EVIDENCE` |
| lokaler Baseline-Test | historisch 3.176 PASS @ 41340e75 (29.09.2026); neue PR-Suites getrennt ausweisen, kein heutiger Main-Testclaim aus der alten Zahl | `CURRENT_TEST_EVIDENCE` |
| Demo-/Reference-Stand | unveränderter positiver Development-E2E auf isoliertem Issue #1, PR #2 bis echten Human Merge; ältere Attempts bleiben FAIL | `HISTORICAL_EVIDENCE` |

## Eigener aktueller Abschlussabgleich — 04.10.2026, a0f16c02

Product `a0f16c022bacbe5d9d6978e37fe8a2288cdd3e1d`, Main-CI #1130 PASS;
Qualification-Base `1a4e28e310a840dac6d3a870d7193522ee17fc5e`, Operator-Demo
`558beeaefa4d9599592c8043a3eaefe89ac8e19e`, Repository
`example-owner/samuel-r24-2039a92d-20261004-01`, Subject/Attempt
`a0f16c02-20261004-01`, Issue #1 / PR #2. Candidate
`c14e811b96c562722f2726119fac3e21769a930d`, Human Merge durch example-owner
`e4c3efba45c8f5067fa5960e223543581d629909`; Candidate-CI #1131 und Merge-CI #1132
PASS am jeweiligen exakten Head. Vor Start 19/19 READY / CLI Exit 0;
Acceptance 7/7 einschließlich echter MANUAL-Acceptance #45457, Required Gates
PASS, Review pass ohne Findings, nativer `PRMerged` und Dashboard `merged`.
Die vollständige Receipt liegt unter
`/var/lib/samuel-example/.local/share/samuel-preparation-a0f16c02-20261004/development-e2e-a0f16c02-20261004-01/terminal-result.json`.

Der Hauptpfad lief nach erneuter echter menschlicher Planfreigabe bis Merge.
Die erste nicht materialisierte Labelapproval und widersprechende
Maintainerbeobachtung bleiben in #948 erhalten, Root Cause UNKNOWN; kein
störungsfreier Erst-Approval-Claim. Kein Agent-Watch/Resume/Subjectfix,
Route-/Prompt-/Configwechsel oder Cross-run-Evidence. Das SCM-Issue bleibt
`open` bei `status:done`; technische und fachliche Abschlusskommentare
#45470/#45472 sind vorhanden. Der verbleibende SCM-Abschluss-/Bedienumfang
steht in #890 Kommentar #45474; ein offenes Issue ist kein verlorener Merge.
Kein Formal-D0-/vollständiger Golden-/Healing-/Evaluation-LLM- oder
Sammelabschluss. Startreceipts bleiben datierte Evidence, kein zukünftiges READY.

Human Merge #946 ist abgeschlossen; der alte Dokument-/Start-Warteauftrag
ist superseded. Main-Wiki a0f16c02 wurde gebaut, regulär publiziert und
unabhängig source-/inhaltsgebunden remote verifiziert: Wiki-Head
`7b57ae67a9217af4001e988f5558841611ee98c4`, zehn Inhaltsseiten plus Footer/Sidebar.
Die drei eigenen #946-Receipts für Main-CI/Checkout, Wiki-Publikation und
Wiki-Remote-Readback liegen im oben genannten Preparation-Root.
Diese Dokumentänderung benötigt nach Human Merge ihren eigenen neuen Publish.

Selektive Restzuordnung, keine erneute Gesamtreconciliation:

- #880: fertiger MANUAL-Copy-Befehl #45455 und native Human-Receiptfortsetzung
  real teilabgenommen; Stale/Replan/Race/Multi-Criterion und unnötige MANUAL offen.
- #900/#905/#859: aktuelle Preparation und native Human-/Merge-Strecke
  zugeordnet; eigene Varianten-/Setup-/Negativ-/Golden-/Release-AC bleiben offen.
- #889: technischer ops-2039-Lifecycle, menschliche Bedienabnahme und eigener
  Production-Rückzustand auf f514ddee belegt; nur enger Dokument-/Issueabschluss.
- #843: ursprüngliche Pflichtwert-/Bootstrap-AC durch eigene gebundene positive
  Prestartprüfung und getrennte eigene q1/q2-Diagnosefälle belegt. Keine neue
  releasegebundene Gesamtprüfung aus dem Issue-Namen hinzufügen. Nur der enge
  aktive Dokument-/Issue-/Remoteabschluss verhindert den eigenen Abschluss.
- #845: ursprüngliche kanonische Origin/Base/Freshness vor Planning und
  tatsächlicher Productpfad im selben Subject belegt; finaler eigener
  Dokument-/Issue-/Remoteabschluss offen, kein Formal-D0-Gesamtzwang.
- #694: eigene Live-Doctor-Matrix PASS. Prozessbindung ist beendet, aber
  `persistent_operator_token_revoked=false`; das ist kein Beleg für den in
  #42522/#42755 verlangten Widerruf. Diesen konkreten Lifecyclepunkt über den
  vorhandenen autorisierten Pfad erfüllen oder ausdrücklich menschlich klären;
  keinen gemeinsamen dauerhaften Operatorzugang eigenständig widerrufen.
- #894: eigene positive/negative non-root-Matrix anerkannt, weiterer eigener
  Runtime-/Subject-/Restart-/Artefaktumfang offen. #691/#823 behalten ausdrücklich
  verlangte veröffentlichte D08-/D0- und übrige Fehler-/Recovery-AC.

45 offene Product-Issues im aktuellen Intake; #843/#845 sind Kandidaten für
issueeigenen Abschluss nach engem Dokumentmerge und Main-/Remote-Readback.
Keine pauschale Schließung oder neue Implementation vorhandener Mechanismen.
`E2E_PATH_IMPACT=NO` für diesen Evidence-/Dokumentdelta.

## Nachgewiesen funktionierend

Der aktuelle Code besitzt getestete, gebundene Vertraege fuer Planning und
Replan, dauerhafte Human-Approval-Authority, Implementation und Candidate,
Required Gates, MANUAL-Receipt-Pruefung, oeffentliche Watch-Fortsetzung,
native Kommentar-Fortsetzung und Human-Merge-Projektion (#926),
Review- und Provider-Fehlergrenzen, Workspaces, Resume, State, Audit,
Dashboard/API, Setup/Doctor, Release- und Wiki-Projektion. Die lokale Suite
belegt diese technischen Vertraege; sie beweist keine externe
Providerverfuegbarkeit und keinen erfolgreichen Golden-Lauf.

Seit dem letzten Statusbericht wurden insbesondere integriert:

- MANUAL pending bleibt nichtterminal und wird ueber den oeffentlichen
  Watch-Pfad erneut ausgewertet (#910/PR #911);
- native signierte Gitea-Freigaben werden gebunden verarbeitet (#904);
- Health-Probes duerfen aktive Workflows nicht fortsetzen (#906);
- konkurrierendes Resume vergiftet den aktiven Issue-Status nicht (#913);
- erschöpfte Providerfehler werden in Review sowie Implementation/Healing
  fachlich blockiert (#912 und #918);
- unmoegliches repositoryweites `GREP:NOT` wird vor Freigabe blockiert (#916);
- gebundene MANUAL-Copy-Anleitung, korrelierte Aktivitätsdarstellung, ehrliches
  Quality-not_attempted sowie idempotenter Auftrags-/AC-Abschluss und
  Labelcleanup nur für den aktuellen Plan sind in #927 integriert.
  Human-, Gate-, Parser- und Routingauthority bleiben unverändert;
- konfigurierbare Katalog-/Benchmarkquellen aus der vorhandenen FileConfig
  und quellengebundener Cache sind über #928 integriert. Defaults und
  Completionroute bleiben unverändert; Benchmarks bleiben advisory.
- Read-only-SCM-Testfixtures verwenden nach Test-PR #930 den kanonischen
  ENV-Parser und ein vorhandenes Issue im ausdrücklich konfigurierten Repo.
  Historische Issue12/Phase2-Annahmen entfallen; kein Provisioning, keine
  Product-/Runtime-/Workflowänderung.

Die nachfolgenden engen Deltas sind ebenfalls human integriert:

- #940: Doctor benennt Schlüsselpräsenz, keine Signatur-/Native-Deliveryprüfung;
  keylose Ingress-Observation `not_checked`. Fünf direkte Main-Regressionen PASS @ `d820047c`,
  keine Änderung an Approval-/Webhook-Mappingauthority; #905 bleibt teilweise.
- #941: lesbare Promptkaskade und exakte Scope-/Quellenanzeige; 24 direkte
  Main-Regressionen PASS @ `5f0515c5`. Keine ausgelieferten Prompts, Routen oder Parser
  geändert; eigene Profil-/Smokereste #878 bleiben offen.
- #942: vollständiger vorhandener Reconfiguration-Ablauf in den beiden
  Read-only-Hinweisen. Zwei direkte Main-UI-Fälle und der gesamte Inline-
  JavaScript-Parsercheck PASS @ `cd409660`; keine Backend-/Auth-/Setupauthorityänderung.
  Die eigene technische Operator-Lifecycle-Teilabnahme ist inzwischen am
  lokalen Candidate 2039a92d PASS; visuelle Bedienabnahme und Abschluss
  bleiben offen (Details unten).

## Enger EOF-Fix und aktueller E2E-Impact

#938 ist human als Main `cc829391b05535e6bf07f8b6534c49ea68948ddd` integriert.
Der bestehende SEARCH/REPLACE-Kandidat erhält den ursprünglichen EOF-Abschluss;
Dateien ohne Abschluss bekommen keinen erzwungenen Newline. WRITE,
REPLACE-LINES, Validierung, Rollback, Retry und Authority bleiben unverändert.
Eigene 19 EOF-Fälle direkt auf Main PASS; 295 kombinierte Impact-/Dokumenttests
und vollständige PR-CI #1102 PASS auf `6c82c41f`, Main-CI #1103 PASS auf cc829391.
Technische Beschreibung und ihr Quellen-/Wikianschluss sind integriert und
vom selben Main remote geprüft. #937 ist anhand seines engen Bugscopes belegt;
der eigene Status-/Gitea-Abschluss ist nach #939 auf Main 2b9d613c belegt,
kein fremder AC-PASS.

E2E-relevante Merges seit der historischen Baseline 41d39b0e:

| PR | Merge | E2E_PATH_IMPACT | Grenze / Regression |
|---|---|---|---|
| #936 | `67add000ae35a7954d4800aeb25a071b1898c27b` | NO | historische Evidence-/Statusdokumentation; 68 Dokument-/Wiki-Tests |
| #938 | `cc829391b05535e6bf07f8b6534c49ea68948ddd` | YES | implementation/candidate content; 19 EOF-Fälle plus vorhandene Applier-/Consumer-/Loop-/Rollbackregressionen |
| #939 | `2b9d613cfce9ea961e1c4e39a5afe1498f9dfbf3` | NO | eigener EOF-Status-/Dokumentabschluss |
| #940 | `d820047c7d07619e446bca4ed72fa8b8d9e3f9d3` | YES | Doctor-/Webhookdiagnostik und Evidence; fünf Regressionen |
| #941 | `5f0515c5d4113696f1e1e745e3267b663e945e98` | YES | Promptlookup-Fehlerbehandlung und Scope-/Quellenanzeige; 24 Regressionen |
| #942 | `cd4096608493114b4d032d5d3c34fc1ecb25286e` | NO | isolierter Reconfiguration-Hinweis; zwei UI-Fälle und Inline-Script-Parser |
| #943 | `7843d4fd9a79b4db9a9ed78e37269f59a27fc1d7` | NO | konfigurierte vs. produktive LLM-Tasks und historische Evidence; bestehender Dokumenttest, keine neue Consumer-/Routing-/Workflowauthority |

Nach #943 wurde der eigene Development-E2E auf final integriertem Main
7843d4fd mit neuen zeitgültigen Preparation-Nachweisen bis Human Merge und
nativem Abschluss PASS ausgeführt (Details unten). Die genannten Deltas sind
in diesem unveränderten Positivpfad enthalten; daraus entstehen keine eigenen
Negativ-/Profil-/Recovery- oder Release-/D0-Abnahmen. Der verbrauchte Subject
und sein Start-Receipt sind kein zukünftiges READY. Frühere Subjects/Receipts
werden weder verlängert noch kombiniert.

## Eigene Operator-Teilabnahmen — 04.10.2026

Product `2039a92d8bc759cfeab2e549a814e857f19e1feb`, vollständige Main-CI #1122
PASS; sauber gebauter **lokaler Development-Candidate**, kein veröffentlichtes
Release. Qualification-Base `1a4e28e310a840dac6d3a870d7193522ee17fc5e`,
Operator-Demo `558beeaefa4d9599592c8043a3eaefe89ac8e19e`, isolierte
Operator-Prüfung `ops-2039a92d-20261004-01`. Kein Qualification-Subject,
`samuel run`, Approval oder Human Merge wurde für diese Prüfungen erzeugt.

- #889: Production Save HTTP409 vor Mutation; derselbe externe Config-/Env-
  Bestand im ausgelieferten lokalen Setup-Compose; echte Taskprovider-/Modell-/
  Limit-/Timeout- und Providerinformationsänderung gespeichert. Stored/effective
  Digests und `restart_required` bleiben getrennt. Neue Productionruntime
  übernimmt den gespeicherten Stand. Rückkehr zum Referenzprofil über denselben
  Setupweg und erneuter Production-Freeze PASS. Visuelle Bedienabnahme bleibt
  beim Maintainer; kein Hotreload oder Adminbypass.
- #691/#823: Diese eigene reale D08-Teilprüfung belegt tatsächliche
  Bindmount-Persistenz und Recreate. Kontrollierte Fehler-/Rollbackfälle und der
  geforderte veröffentlichte D08-Subject sind damit nicht abgenommen.
- #894: Dasselbe Candidate-Image, UID/GID999. Read-only Base-Arbeitsbaum mit
  schreibbarem Gitadmin und getrenntem Workspace positiv; Base-Head/-Inhalt
  unverändert und Base-Schreibversuch abgelehnt. Falscher Owner liefert
  `dubious ownership`/Gitexit128; read-only Gitadmin blockiert den bestehenden
  WorkspaceManager ebenfalls mit `workspace_git_failed`. Kein `safe.directory=*`,
  kein Privilege-Bypass. Isolierte echte Git-/Mountdiagnose, keine Behauptung
  eines neuen vollständigen E2E oder releasegebundener Restart-Qualification.
- #843: Bestehender Demo-Validator `_binding_status` prüft die geschützte Quelle,
  den gespeicherten Bestand und tatsächliche Diagnoseprozess-Environmentwerte.
  Baseline PASS; q1 fehlend und q2 abweichend jeweils erwartungsgemäß BLOCKED.
  Die Parent-Productionruntime wurde nicht umkonfiguriert; keine Secretwerte,
  Fingerprints, Fragmente oder Providerantworten persistiert.
- #694: Drei echte Doctor-Prozesse auf derselben nativen Regel: exakter
  konfigurierter Required Context Exit0/13 ok, absichtlich falscher prozesslokaler
  Sollwert Exit1/1 fail, danach exakter Sollwert erneut Exit0. Die getrennte
  Operatorbindung endet mit jedem Prozess; Branchregel und Runtimebot bleiben
  unverändert. Der bestehende dauerhafte Operatorzugang wurde nicht widerrufen.

173 bestehende Configuration-/Workspace-/Setup-/Dashboardtests PASS auf Source
2039a92d. Sie sind Regressionsevidence, kein Ersatz für die oben getrennt
benannten realen Prüfungen. Unveränderte Evidence liegt unter
`/var/lib/samuel-example/.local/share/samuel-operator-acceptance-2039a92d-20261004/`:
`889-lifecycle-result.json`, `894-matrix-result.json`,
`843-bootstrap-negatives-result.json`, `694-required-context-matrix-result.json`.
Die Operator-Prüfinstanz wurde anschließend gestoppt; State und Evidence bleiben
unverändert erhalten. Historische E2E-PASS-/FAIL-Subjects bleiben separat.

Für #900/#905 wurde anschließend eine getrennte frische Preparation auf demselben
integrierten Product2039a92d gebunden: Repo
`example-owner/samuel-r24-2039a92d-20261004-01`, geplante Attemptbindung
`2039a92d-20261004-01`. Vier produktive DeepSeek-Taskproben, native signierte
Delivery samt erneuter Prozessbindung nach Restart, SCM-/Runnerreadbacks,
Health/Audit/Freshness/Freeze PASS. Eigener Preflight am 04.10.2026 um
09:34:18 UTC: 19/19 READY, CLI Exit0; früheste Ablaufgrenze 10:31:26 UTC.
Receipt: `/var/lib/samuel-example/.local/share/samuel-preparation-2039a92d-20261004/preflight/preparation-receipt.json`.
Dies ist datierte Startvorbereitung, keine unbegrenzte heutige Readiness und
kein neuer Workflow-PASS. Kein Subject oder `samuel run`; Dashboardprüfung und
START bleiben menschlich. Ein später integrierter Product-Head invalidiert
auch diese Candidatebindung. #905 behält seinen Setup-/Doctor-Bedienrest und
eigene Release-/Golden-AC; Doctor-Präsenz wird nicht zu Delivery-Authority.

Nach dieser positiven Save-/Recreate-Teilprüfung wurde der offene kontrollierte
Rollbackfall separat auf dem installierten Main2039-Image geprüft: UID999,
geheimnisfreie File-Bindmount-Fixture unter nicht schreibbarem `/app`,
post-write EIO. Forward verwendet privates Staging, Rollback versucht dagegen
eine Datei unter `/app` und scheitert mit PermissionError13; der ursprüngliche
Inhalt bleibt verändert. Dies ist ein belegter **PRODUCT_DEFECT** in #823/#691,
kein neuer Environmentbefund der unberührten READY-Runtime und keine Diagnose
des früheren unbekannten Review-FAILs.

PR #947 / Head `fcab1ebfbdaa924fedabe2e038d13537bee1a47d` verwendet das bestehende
private Staging auch beim Rollback des explizit erlaubten Bindmount-Ziels.
Zwei EACCES-/EPERM-Regressionen reproduzieren den Defekt vor dem Fix. Die eigene
installierte Fix-Candidate-Gegenprobe stellt den Inhalt wieder her und erhält
den ursprünglichen OSError/EIO5; private Stagingdateien werden entfernt.
Receipts `823-real-installed-rollback-reproduction.json` und
`823-real-installed-fixed-rollback-result.json` bleiben getrennte Diagnosefälle,
keine releasegebundene D08-Qualification. Der Fix wurde am 04.10.2026 human
als PR #947 integriert: Main/Merge
`b6e9eeae80c5073fa272ac4964ee2eafacb1c501`; Required PR-CI #1126 PASS am
exakten Fix-Head. Die Main-CI und der aktive Status-/Wikianschluss sind eigene
nachfolgende Nachweise, kein aus dem PR-PASS erfundener Main-PASS.
#823/#691 sind nun wieder **IMPLEMENTED_UNVERIFIED**: der belegte Coderest ist
integriert, ihre eigenen übrigen Fehler-/Release-/Abschluss-AC bleiben offen.
Der alte Main2039-Fehlerfall bleibt FAIL, die installierte Fix-Gegenprobe ihr
eigener datierter PASS. Keine reale Konfiguration, historische Evidence oder
Subjectauthority wurde für diese Fixturediagnose verändert. Die ungestartete
2039-Preparation ist durch den neuen Product-Head invalidiert; sie darf nicht
als READY für den späteren integrierten Candidate verwendet werden.

Die betroffenen Issues bleiben offen für ihre genannten Rest-AC. Dieser
Dokumentdelta benötigt Human Merge und anschließend seinen eigenen
Main-/CI-/Wiki-Remoteanschluss. `E2E_PATH_IMPACT=NO`: kein Produkt-, Config-,
Prompt-, Parser-, State-, Gate- oder Workflowcode wird geändert; kein neues READY,
Golden- oder Formal-D0 wird durch diese Statuszuordnung erteilt.

## Teilweise oder noch nicht end-to-end belegt

Der ursprüngliche 46-Issue-Snapshot und selektive neue Deltas stehen in
`ISSUE_IMPLEMENTATION_MATRIX.md`. #829 (Route-/Freeze-/Dokumentumfang) und #892 (Determinismus mit eigener
Candidate-/Prestart-Zuordnung) sind geschlossen; Live-Readback am 02.10.2026:
44 offen. #922 ist am 03.10.2026 nach eigener Code-/Test-/Main-/Wiki-Abnahme
geschlossen; damaliger selektiver Live-Readback: 43 offene Product-Issues.
Live-Readback nach dem neu belegten EOF-Defekt #937, vor dessen Abschluss:
44 offen. #937 ist danach anhand seines eigenen EOF-Scopes geschlossen;
der selektive Live-Readback auf cd409660 zählte 43 offene Product-Issues.
Am 04.10.2026 nach dem neuen ungeprüften Zeitdarstellungsfinding #944:
44 offene Product-Issues; keine Schließung aus dem allgemeinen E2E-PASS.
Viele liefern bereits Code und Regressionen,
benoetigen aber reale, releasegebundene oder rollengetrennte Qualification.
Besonders betroffen sind Identity/Cutover, Review, State/Retention,
Provider/Execution, Setup/Config, Health/Doctor, Documentation Publisher und
Extensions.

## Aktuelle Blocker

| Stage | Befund | Träger |
|---|---|---|
| Development E2E | Hauptpfad bis Human Merge positiv belegt; kein aktueller Hauptpfadblocker. Weitergehende Development-Golden-AC bleiben getrennt offen | #859 |
| Operational Readiness | Kein vollstaendiger backendneutraler Full Self-Check; statische Konfiguration beweist keine Verfuegbarkeit | #921, #693, #694 |
| Recovery | Kein einheitlicher sicherer Re-Entry-Vertrag ueber terminale Workflowgrenzen | #920 |
| LLM-Providerroute | reale Route-/Modellverfuegbarkeit und Output-Suitability bleiben externe Inputs | #822 |
| Externer Execution-Provider | Provisionierung/Trust/Cutover nur fuer Profile mit dieser Capability erforderlich; shipped deaktiviert | #679 |
| Formal Golden/D0 | frischer releasegebundener Positiv- und Negativsubject fehlt | #658 |
| Rehearsal cleanup | fuenf disposable Repositories sind mit der Demo-Rolle sichtbar und privat gesichert; alle bleiben `KEEP_EVIDENCE` | `REHEARSAL_REPOSITORY_CLEANUP.md` |

## Eigenständiger Development-E2E auf integriertem Main — 04.10.2026

Product `7843d4fd9a79b4db9a9ed78e37269f59a27fc1d7`, Qualification-Base
`1a4e28e310a840dac6d3a870d7193522ee17fc5e`, Operator-Demo
`558beeaefa4d9599592c8043a3eaefe89ac8e19e`, Repository
`example-owner/samuel-r24-7843d4fd-20261004-01`, Subject/Attempt
`7843d4fd-20261004-01`, Issue #1 / [PR #2](https://scm.example.invalid/example-owner/samuel-r24-7843d4fd-20261004-01/pulls/2).

Vor Start zeitgültige Preparation **19/19 PASS, READY, CLI Exit 0** und
unveränderte Bindung. Danach ein öffentlicher initialer Einstieg und nur
read-only Beobachtung: Planning → echte Human Plan Approval über signierten
Webhook → Implementation → sechs automatische AC → 13 Required Gates →
PR → CI → strukturierter Review → echter Human Merge → nativer Abschluss:
**Development-Hauptpfad PASS**. Kein agentenseitiger Watch-Scan, Reparatur,
Route-/Prompt-/Configwechsel oder Cross-run-PASS.

Candidate `785672757169d96dbbc0cc560b356dd4abf2f9fb`, Human Merge
`99ede5f195e2a6e61e128da2c9737ae857aeada5` durch example-owner. Candidate-CI #1119 und
Merge-CI #1120 PASS auf den jeweiligen exakten Heads; Review `pass`, keine
Findings. Dashboard `merged`/`PRMerged`, aktuelles Acceptance 6/6 PASS,
Labelbereinigung auf `status:done`, Entwicklungsabschluss #45377 und separater
fachlicher Änderungskommentar #45379 mit tatsächlichem Diff real gelesen.
Das Issue bleibt laut bestehendem Vertrag offen; Merge schließt es nicht
automatisch. Quality und Healing `not_attempted`; Audit-HMAC über
178 Records in einer Datei verifiziert.

Eigene Teilzuordnung: #859 positiver Development-Hauptpfad; #900 vorhandene
Preparation und verbrauchter isolierter Subject; #822 vier produktive
DeepSeek/deepseek-v4-pro-Taskproben vor Freeze und unverändertes Profil;
#830/#890 native Run-/Acceptance-/Merge-/Abschlussprojektion und fachliche
Erklärung. Ihre eigenen übrigen AC bleiben offen. Keine MANUAL-Kriterien,
direkte In-flight-LLM-Beobachtung, Healing-Ausführung, Evaluation-LLM-
Verfügbarkeit, vollständiger Development Golden oder Formal D0 belegt.

Nach Abschluss: eigene Runtime gegen sieben weitere sichtbare samuel-service
Compose-Instanzen read-only geprüft; keine gemeinsamen Repositories, Ports
oder State-/Workspace-Mounts mit dieser Runtime. Keine Instanz verändert;
keine globale Garantie über uninspektierte Hostprozesse. Vor-Subject-
Operator-/Harnessdiagnosen bleiben getrennt; der alte Reviewprobe-FAIL bleibt
UNKNOWN und bekommt aus diesem PASS keine rückwirkende Root Cause.

Terminal-Receipt:
`/var/lib/samuel-example/.local/share/samuel-preparation-7843d4fd-20261004/development-e2e-7843d4fd-20261004-01/terminal-result.json`.
Preparation-Receipt:
`/var/lib/samuel-example/.local/share/samuel-preparation-7843d4fd-20261004/preflight/preparation-receipt.json`.
Beide bleiben an diesen abgeschlossenen Attempt gebunden, kein heutiger neuer
Startauftrag und kein READY für einen anderen Candidate. Das neue Finding
#944 betrifft spätere Zeitdarstellungsanalyse; keine Ursache oder Änderung
wird aus dem UTC-Beispiel abgeleitet.

## Eigenständiger Development-E2E auf integriertem Main — 03.10.2026

Product `41d39b0e4f5a28ca06960a349812aee6e3eed16f` (PRs #927–#935),
Qualification-Base `1a4e28e310a840dac6d3a870d7193522ee17fc5e`,
Operator-Demo `558beeaefa4d9599592c8043a3eaefe89ac8e19e`,
Subject/Attempt `41d39b0e-20261003-01`, Repository
`example-owner/samuel-r24-41d39b0e-20261003-01`, Issue #1.

Vor Start zeitgültige Preparation **19/19 PASS, READY, CLI Exit 0**;
anschließend genau ein öffentlicher Einstieg. Planning → echte menschliche
Planfreigabe → Implementation → acht automatische AC → Required Gates → PR →
CI → strukturierter Review → Human Merge → nativer Abschluss: **PASS**.
Keine Agent-Watch-Auslösung, Reparatur, Route-/Prompt-/Configänderung oder
Cross-run-PASS-Evidence. Der inzwischen verbrauchte Subject und abgelaufene
Start-Receipt sind historische Evidence, kein zukünftiges READY.

Candidate `ed73d315496c3eb02c325131019e730cf7b37459`,
[Subject-PR #2](https://scm.example.invalid/example-owner/samuel-r24-41d39b0e-20261003-01/pulls/2),
Human Merge `e5fa956fe1fe4dc7637a6e6d5f00db4c899bd49f` durch example-owner;
Candidate-CI #1097 und Merge-CI #1098 PASS auf ihren eigenen Heads.
Review `pass` mit einer nicht blockierenden `missing_newline_eof`-Suggestion;
der historische Candidate bleibt unverändert. Dashboard `merged`/`PRMerged`,
aktuelle acht AC PASS, `status:done`, technischer Abschlusskommentar #45274 und
separater fachlicher Mergekommentar #45276 sind real gelesen. Audit-HMAC:
381 Records in einer Datei verifiziert.

Damit sind die engen #890-Fixes #933 (advisory Komplexitätshinweis ohne falschen
Workflow-FAIL) und #934 (tatsächlicher Issue-/Diffkontext in PR und separatem
Mergekommentar) auf dieser Runtime real teilabgenommen. Weiterer kausaler
Failure-/Remediationumfang bleibt offen. Keine MANUAL-Kriterien in diesem
Subject; die ältere MANUAL-Baseline bleibt separat. Keine direkte In-flight-
LLM-Beobachtung, Healing-Ausführung, Evaluation-LLM-Verfügbarkeit, Formal-D0-,
Golden- oder pauschale issueeigene Abnahme wird daraus abgeleitet.

Terminal-Receipt:
`/var/lib/samuel-example/.local/share/samuel-preparation-41d39b0e-20261003/development-e2e-41d39b0e-20261003-01/terminal-result.json`.

## Frühere eigene Development-E2E-Baseline auf eb6cce18 — 03.10.2026

Product `eb6cce188ee9c4f7cb35a28036586385815a2d51`, Qualification-Base
`1a4e28e310a840dac6d3a870d7193522ee17fc5e`, Operator-Demo
`558beeaefa4d9599592c8043a3eaefe89ac8e19e`, Subject/Attempt
`eb6cce18-20261003-01`, Repository
`example-owner/samuel-r24-eb6cce18-20261003-01`, Issue #1.
Vor Start 19/19 zeitgültige Preparation-PASS und CLI Exit 0.

Planning → Human Plan Approval → Implementation → sieben automatische AC
→ Required Gates → PR → CI → gebundener Review → Human Merge → nativer
Abschluss verlief unverändert erfolgreich. Keine Agent-Watch-Auslösung,
Reparatur, Route-/Prompt-/Configänderung oder Cross-run-Evidence.
Candidate `f15b7c4973e7a6074fde38e8ef377e3d92ff1da1`,
[Subject-PR #2](https://scm.example.invalid/example-owner/samuel-r24-eb6cce18-20261003-01/pulls/2),
Human Merge `9d35329aa6377bc99499eac53659e28afd9ce838`, Candidate-CI #1083 und
Merge-CI #1084 PASS. Dashboard `merged`/`PRMerged`, Label `status:done` und
gebundener Abschlusskommentar #45211 wurden nativ beobachtet; Auditkette mit
164 Records verifiziert. Der abgeschlossene Subject ist nicht frisch für
weitere Qualification.

Terminal-Receipt:
`/var/lib/samuel-example/.local/share/samuel-preparation-eb6cce18-20261003/development-e2e-eb6cce18-20261003-01/terminal-result.json`.
Der Plan enthielt **keine MANUAL-Kriterien**. Deshalb belegt dieser PASS keine
MANUAL-Fortsetzung auf eb6cce18; die ältere MANUAL-Baseline bleibt separat.
Kein Golden-/Formal-D0-/Healing-/Evaluation- oder Fremdissue-PASS.

Die integrierten Projektionen #931/#932 wurden teilweise real gelesen:
konkrete Diagnose/Vorkommnisse, letzte produktive Review-Callfacts und idle.
Eine direkte In-flight-Beobachtung bleibt #891-Rest. Zwei nicht blockierende
#890-Findings sind danach getrennt integriert und regressionsgesichert:
#933 erklärt den advisory `PlanComplexityWarn`-Hinweis; #934 ergänzt den
PR um Issuekontext und gebundene tatsächliche Änderung sowie nach Human Merge
einen zweiten fachlichen Kommentar neben den technischen S.A.M.U.E.L.-Nachweisen.
Der damalige Main 021c65f8 hatte noch keine eigene Runtime-/E2E-Abnahme;
die nachfolgende eigene Teilabnahme auf 41d39b0e steht oben.
Ein advisory Komplexitätshinweis
beweist weder einen abgelehnten Plan noch einen erfolglosen Workflow.
Nicht integrierte Fix-PRs sind keine neue Candidate-Qualification.

## Historische positive Development-E2E-Baseline — 02.10.2026

Product `1a87ef036b6481b8486322e7ff36dacf80a3129f`, Qualification-Base
`1a4e28e310a840dac6d3a870d7193522ee17fc5e`, Operator-Demo-Main
`558beeaefa4d9599592c8043a3eaefe89ac8e19e`, Subject/Attempt
`1a87ef03-20261002-01`. Repository:
`example-owner/samuel-r24-1a87ef03-20261002-01`, Issue #1.

Planning → menschliche Planfreigabe → Implementation → menschliche MANUAL
Acceptance → Required Gates → PR → CI → strukturierter Review → menschlicher
Merge verlief zusammenhängend ohne Watch-Scan, Reparatur, Route-/Prompt-/
Configwechsel oder Cross-run-Evidence. Candidate
`8d4ccbd525bbe936bc728e149c390040926c01f7`, [Subject-PR #2](https://scm.example.invalid/example-owner/samuel-r24-1a87ef03-20261002-01/pulls/2),
Human-Merge `6b01b8fe2a8b8e88cd4150abb48f0cab15856379`, PR-CI #1061 und
Merge-CI #1062 jeweils erfolgreich am eigenen Head.

Der vor Start zeitgültige Preparation-Receipt war 19/19 PASS/Exit 0.
Sein späterer Ablauf macht ihn nicht zu aktuellem READY; er bleibt historische
Start-Evidence. Terminal-Evidence liegt unter
`/var/lib/samuel-example/.local/share/samuel-preparation-1a87ef03-20261002/development-e2e-1a87ef03-20261002-01/terminal-result.json`.

Diese Baseline ist kein Development-Golden-/Formal-D0-PASS und schließt keine
fremden Issue-AC. Weitere UX-/Diagnose-AC sind #880/#890/#891. Die
prozesslokale Current-/Last-LLM-Projektion aus #891 ist regressionsgesichert;
die reale Teilabnahme auf eb6cce18 steht oben; die direkte In-flight-Beobachtung bleibt offen.
Sie erzeugt weder Providerprobes noch Quality- oder Workflowauthority.
Die engen Darstellungs-/Copy-/Abschlussdeltas aus PR #927 sind auf `8cd3532`
integriert; sie gehören nicht rückwirkend zur alten E2E-Evidence. Der doppelte `unittest.main()` im Candidate
ist ein nicht blockierender Reviewbefund, keine neue Gatepolicy.

## Historischer fehlgeschlagener MANUAL-Lauf

Disposable Issue #3 erreichte Planning PASS, echte Human Approval,
Implementation, Candidate und automatische Gates. Ein exakt an AC, Contract
und Candidate-Head gebundener signierter MANUAL-Receipt wurde angenommen,
aber der damalige Stand dispatchte keine Reevaluation. Der Defekt wurde danach
durch #910/PR #911 technisch mit Integrationsregression behoben. Der alte Lauf
bleibt FAIL-Evidence und wurde nicht fortgesetzt. Aus dieser historischen Kette gibt es keinen PR, Merge oder
Development-Golden-PASS. Der spätere positive Subject ist davon getrennt.

## Qualification, Wiki und Public Sync

- `Development E2E`: oben gebundener Hauptpfad bis Human Merge PASS; materielle
  künftige Pfadänderungen benötigen eine neue eigene Abnahme.
- `Development Golden`: offen in #859.
- `Formal D0`: offen in #658 und erst nach immutable Release auf frischer
  Installation zulaessig.
- `Wiki`: am 03.10.2026 von Product `main@cc829391` regulär publiziert,
  zehn Inhaltsseiten plus Footer/Sidebar. Remote-Head
  `ed9fb88e7291b1213f42cde5f27ed48694105558`; Marker und Inhaltsdigest readback-verifiziert.
  Dieser Publishnachweis gilt für `cc829391`; die Integration dieser
  Statuskorrektur verlangt ihren eigenen nachfolgenden Main-Publish.
  Jeder weitere Docs-Merge erfordert einen neuen Build, Publish und
  Live-Readback des Marker-`source_head_sha`; ein lokaler `check` allein
  belegt keine aktuelle Live-Publikation.
- `GitHub`: Der historische Public-Snapshot liegt nach anonymem API-Readback
  unter `Alexander-Benesch/S.A.M.U.E.L.`; `main` zeigte am 29.09.2026 auf
  `f1fa875c1e05138ecda9cb2e618e4f56e8ecf32a`. Ein GitHub-Remote ist im
  Product-Checkout nicht konfiguriert. Der naechste bereinigte Ein-Commit-
  Snapshot, das getrennte Wiki und Issue #2 werden ausserhalb des Product-
  Checkouts als tokengebundenes Paket vorbereitet. Der genaue Source-/Tree-
  Stand steht im privaten Sync-Receipt; fuer die Veroeffentlichung fehlt eine
  passende GitHub-Tokenauthority. Siehe
  `docs/github/GITHUB_SYNC_READINESS.md`.
