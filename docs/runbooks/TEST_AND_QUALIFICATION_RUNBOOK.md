# Test and Qualification Runbook

## Aktueller Testrelease v2.0.0a29 — 09.10.2026

PR #989 und #980 sind menschlich gemergt und in a29 veröffentlicht.
Main-/Tag-CI, sieben gebundene Assets, OCI-Publisher-Smoke, frische
Draft-Installation und erneuter Asset-Readback nach Veröffentlichung sind PASS.
[Exakte Releasebindung und offene Nachweisgrenzen](../status/CURRENT_PRODUCT_STATUS.md#veröffentlichter-installationsstand-v200a29--09102026).
Nur saubere neue Alpha-Testinstallationen; kein Golden-/D0- oder Isolations-PASS.


## #989: Nacharbeit und Alpha-Nachweisgrenze — 09.10.2026

P1 bindet die Sourcewurzel über Device/Inode und geschützte Host-Eltern an
Registrierung und Recreate. Negative Tests müssen fehlende/ausgetauschte Quellen,
Rechteabweichungen und unerlaubte Git-Hook-/Filterwirkungen abweisen. Die
Git-Härtung bleibt in den bestehenden Git-/Workspacepfaden; keine Sandbox.
P2 umfasst auch den Gate-7-Fallback ohne PathRisk-Konfiguration vor lokaler und
externer Verifikation. Findings, Exceptions und nicht ausgeführte Required-
Preflights blockieren; Ergebnisse entstehen nur einmal. Ein Scanner-SKIP bleibt
SKIP und wird nicht als ausgeführter FAIL ausgegeben. P4 ergänzt Readiness-Gründe und erhält andere Blocker sowie die
Trennung zur technischen Health.

P3 prüft aktuelle Policy-/Contractbindung und Restart/Recovery anhand vorhandener
Regressionen. Neue Alpha-Qualification erfolgt durch saubere Neuinstallation des
neuesten freigegebenen Releases. Alte Alpha-Migration, Upgrade/Downgrade und
Cross-Release-Checkpointkompatibilität sind keine Mergevoraussetzungen.
Historische FAIL-Evidence bleibt erhalten. PR-Tests erlauben weder Release noch
Golden/D0; volle Sicherheitsqualification bleibt ohne nachgewiesene Isolation
BLOCKED. H3 bleibt zurückgestellt.

## #988: freigegebener Implementierungsumfang — 08.10.2026

Die Maintainerentscheidung erlaubt H1 (lokale OCI-Projektintegration) und die
F13-Korrektur innerhalb H2. Human Approval/Human Merge bleiben beim Menschen.
H3 (Remote-Architektur) ist zurückgestellt. Diese Entscheidung ist keine
maschinelle Planfreigabe, keine neue Golden-Freigabe und kein Abnahme-PASS.

Zwei Nachweisarten bleiben getrennt:

| Nachweis | Zulässige Aussage |
|---|---|
| Lokaler Funktionstest | Planning, Human Approval, Candidate, Required-Gates, PR und Recovery funktionieren im exakt geprüften Umfang. |
| Volle Sicherheitsqualifikation | Zusätzlich sind tatsächliche Isolation, vertrauenswürdige Evidence, minimale Rechte und negative Umgehungstests für den konkreten Executionpfad belegt. |

Die bestehende lokale Kandidatenausführung bleibt eine Prozessausführung mit
den Rechten ihrer Laufzeit. Umgebungsfilter und frühe statische Gates sind keine
Sandbox. Solange unbefugter Zugriff auf Authority-State, Credentials,
Evidence-Schlüssel und andere Workspaces nicht ausgeschlossen und negativ
getestet ist, bleibt **volle Sicherheitsqualifikation BLOCKED**. Vorhandene
externe CI-/Verifierinfrastruktur ist vorrangig für diesen Nachweis zu verwenden;
eine externe Ergebnisdatei allein belegt keine tatsächliche Isolation.

Vor dem nächsten gesondert freigegebenen Golden-/D0-Lauf sind fünf Nachweise nötig:

1. Veröffentlichung und Projektzugriff: Manifest-/Image-/Kitbindung, richtige
   SCM-Identität und volle Ausgangsrevision, effektive UID/GID, Mount- und
   Rechteprüfung, getrennte Source/Workspace/Statepfade. Reale Fetch-/Worktree-/
   Test-/Pushoperationen separat nachweisen; passive Readiness reicht nicht.
2. Reihenfolge: alle effektiv vorgeschriebenen statischen Preflights vor
   Candidate-IMPORT/-TEST bzw. externer Verifikation; Fehler/Exception sperren
   die Ausführung. Noch nicht ausgeführte Gates erhalten `skipped_precondition`,
   `executed=false`, `passed=null`. Bereits ausgeführte externe Gates erscheinen
   genau einmal. Gate 13a wird durch diesen Fix nicht pauschal required.
3. Regression: beide SCM-Adapter, Referenz-/Fremdworkerpfade, Scanner und
   LLM-Routen, Human Approval, Required-Gates, Evidence-Binding, Logs, Audit,
   Token-/Budgetstatistik und Recovery testen. Bestehende #986-/#987-Restpunkte
   werden durch diesen lokalen Fix nicht als abgeschlossen behauptet.
4. Ausführungsgrenze: explizit lokale Funktionsprüfung oder qualifizierten
   isolierten Executionpfad ausweisen. Fehlende Isolation bleibt sichtbarer
   Sicherheitsblocker, auch wenn der funktionale Lauf erfolgreich ist.
5. Neues Subject: Repository, Basis-/Kandidaten-SHA, Contract, Policy-Digest,
   Release-/Toolchainbindung und Attempt neu erfassen. Die Policyänderung
   unterscheidet den korrigierten Ausführungsvertrag auch bei unveränderter
   Operator-Policyversion. Keine alten FAILs löschen oder umetikettieren.

Entwicklungs-, Paket-, JS-/HTTP-, Shell- und Containerintegrationstests sind
reguläre PR-Nachweise. Sie sind keine vorgezogene Kundeninstallation oder
Golden-/D0-Abnahme. Self-Mode bleibt im nativen Sourcecheckout qualifizierbar;
ein fehlender Self-Checkout im Image wird nicht über CWD-Fallback ersetzt.

## Historischer Installationsstand v2.0.0a28 — 08.10.2026

Prerelease #42 bindet Productcommit `e17c80ef0071a302a7dfd331b18553eb5623190c`,
annotiertes Tagobjekt `7bc086ba6609962cf51c69a415f974973d12dfd7` und erfolgreiche
Main-CI #1216 / Tag-CI #1217 einschließlich Release-Gate. PR #979 wurde
menschlich gemergt. Sieben Assets wurden bytegleich zurückgelesen.
Manifest-SHA-256: `9837bcc474a14241d08e69c72fd4e48d6fc15cfdb7d9324ea9a1ffcb9b9fb86f`.
Die vollständige `container.reference` dieses Schema-2-Manifests ist die
OCI-Installationsauthority. Ihr Image-Digest lautet
`sha256:c5cb2af616c927d273ae00d3bbadc6ab1e974ec13218f6ab434f9c4cd3c06c78`;
der Registry-Endpunkt wird aus dem heruntergeladenen Manifest übernommen.

Erster Required Publisher-Smoke und unabhängige Erstinstallationen aus Draft-
sowie veröffentlichten Assets auf je einem leeren Ubuntu 24.04.5 / Docker
29.8.2 / Compose 5.6.0 sind PASS: Setup vor SCM, authentisierte Konfiguration,
Production healthy, Identität, Persistenz, Recreate, Freeze und Secret-Check.
Das offizielle heruntergeladene Kit wird verwendet, kein Runtime-Checkout.

**#978 ist PARTIAL/FAILED, nicht abgeschlossen.** Der offizielle
credentialfreie Wheeldownload, die Offlinevorbereitung und read-only
Toolchainregistrierung sind PASS. Echte erfolgreiche und fehlgeschlagene
Pytest-Tests funktionieren; fehlende/falsche Artefaktbindungen werden
fail-closed abgelehnt. Die harte 8-Sekunden-Versionprobe ist auf der
unabhängigen VM jedoch reproduzierbar zu knapp: TIMEOUT nach 8034 ms,
weitere Proben 6907 / 7125 ms. Spätere PASSs ersetzen diesen FAIL nicht.
Der aktuelle Follow-up-PR korrigiert ausschließlich die gebundene
Versionsprobe über das vorhandene `test_timeout`, maximal 60 Sekunden.
Ungebundene Modul-Presence-Proben behalten 8 Sekunden. Die Korrektur ist
noch kein veröffentlichter Stand; sie benötigt Human Merge und einen neuen
create-only Release a29 mit eigener frischer Abnahme. a28 bleibt unverändert.

Der spätere externe Report #981 belegt den separaten Branchschutz-Leser und
Doctor mit `0 FAIL` für die dort benannte a28-Umgebung; diese Teilabnahmen sind
in #978 übernommen. Sie ersetzen weder den Timeout-FAIL der unabhängigen
langsamen VM noch eine Abnahme dieses neuen Candidates. Der tatsächliche
serverseitige Widerruf bleibt NOT_PROVEN. Gemeinsam verwendete Credentials
werden dafür nicht widerrufen. Gitea-/GitHub-/Enterprise-
Regressionen ersetzen diese reale Probe nicht. Runtimebot, Runner-/Gate-/
MANUAL-/Human-Merge-Authority bleiben bestehen; #977 bleibt analyse-only.
Installation und Technical Health sind kein Golden-/D0- oder Supportclaim.
#962 bleibt offen; der jüngste vollständig D0-qualifizierte Referenzstand
ist weiterhin nicht nachgewiesen.

GitHub Main und Wiki enthalten die bereinigte aktuelle Projektion; GitHub-a28
liefert sieben eigene Public-Assets mit separatem Publiccommit und Schema 1,
geprüftem Wheel, aber kein öffentliches OCI-Image. Native OCI-Evidence wird
nicht übertragen. Bisherige a26-/a27-Tags und Assets bleiben unverändert.
a27 ist historische Installations-Evidence ohne #978-Pfad. Frische a28-
Installationen werden unterstützt; In-Place-Migration alter Daten/Receipts
und Übernahme alter Qualification auf neue Toolchains sind nicht vorgesehen.
Quelle: Release `v2.0.0a28` und Issue #978 im konfigurierten nativen Repository.
Die öffentliche GitHub-Releaseprojektion besitzt einen eigenen Manifestvertrag.


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

Stand: 04.10.2026. Eigener Development-Hauptpfad bis Merge auf `main@a0f16c02`
mit separat erhaltenem initialem Approvalfinding #948; Details unten.
Der ältere Hauptpfad-PASS @ `main@7843d4fd` bleibt historische eigene Baseline.
Getrennte frühere Baselines `main@1a87ef03` (02.10.2026), `main@eb6cce18`
und `main@41d39b0e` (03.10.2026) behalten ihre eigenen Bindungen.
Befehle stammen aus
`.gitea/workflows/ci.yml`, den ausgelieferten Tools und den bestehenden
Release-/D0-Vertraegen. Dieses Runbook schafft keine neue Authority.

## Gemeinsamer Abnahmeplan der verbliebenen Altlasten — #859

Stand: 04.10.2026. Der Maintainer hat die gemeinsame Vorbereitung in #859
beauftragt. Dieser Abschnitt ordnet bestehende Abnahmen zu; Authority bleiben
issueeigene AC, ADRs, R24, der Demo-RUNBOOK und dessen Q00–Q16-Vorlage.
Es entsteht weder ein neues Testframework noch eine Freigabe durch diesen Index.

### Bindung und Ausführungsreihenfolge

1. Fehlende deterministische Fälle mit vorhandenen Regressionen prüfen;
   notwendige Änderungen über Required CI und Human Merge integrieren.
2. Danach endgültigen Main und vollständige Main-CI binden. Das bereits
   gebaute Candidate-Artefakt darf nur bei gleicher Productbindung verwendet
   werden. Kein Tag oder Publish als Nebenwirkung der Vorbereitung.
3. Für reale Fälle den bestehenden Production-Compose-/Setup-/Preflightpfad
   verwenden. Nur invalidierte oder abgelaufene Checks erneuern; nie den
   verbrauchten Subject als frisch ausgeben. Vier produktive Taskrouten,
   keine Evaluation-LLM-Probe und kein versteckter Fallback.
4. Dashboard der tatsächlich gebundenen Instanz bereitstellen, lokalen
   Tokenzugriff ohne Secretkopie ermöglichen, READY/Exit0 vorlegen und an der
   bestehenden menschlichen START-Grenze halten.
5. Die freigegebenen Fälle auf derselben unveränderten Product-/Artefaktbindung
   ausführen. Jeder negative Fall erhält einen eigenen isolierten Subject und
   den erwarteten BLOCK; er wird nicht zum positiven Fall repariert.
6. Der vollständige Rehearsal verwendet die Q00–Q16-Vorlage. Q03 ist dort eine
   installierte Development-Candidate-Bindung, kein veröffentlichter Release.
   Q10 und Q11–Q16 bleiben die eigenen negativen und positiven Scenario-Subjects.
   Human Plan Approval, MANUAL Acceptance und Human Merge bleiben menschlich.
7. Erst nach dem vollständigen unveränderten Rehearsal und ausdrücklicher
   Releasefreigabe folgt der create-only Releasepfad. Die ausdrücklich
   releasegebundenen Fälle und Formal D0 #658 beginnen auf dem veröffentlichten
   Artefakt mit eigenen frischen Bindungen; kein Transfer alter Erfolgsflags.

Ein Fallrecord benutzt die bestehende Evidence-Vorlage und nennt mindestens
Issue/AC, Teststufe, Product/Artefakt, Profil, Subject/Attempt, öffentliche
Aktion, Sollausgang, beobachtetes Resultat, fehlende Nebenwirkung und Beleg.
Fehlende Felder bleiben NOT_EVALUATED; UNKNOWN blockiert notwendige Vorbereitung.
Ein erwarteter Negativ-BLOCK ist kein positiver Hauptpfad-PASS.

### Fälle und issueeigene Abschlussgrenzen

| Fall / bestehende Grenze | Aktion und Sollausgang | Träger und Abschlussgrenze | Menschlicher Halt |
|---|---|---|---|
| Q00–Q02 / Rollen, Base, Demo | Live-Main/Base/Seed, Runtimebot/Human, Runner/Required Context lesen; Scenario check, Demo-tests und standalone HTTP/Fach-Smoke ausführen | #900, #905, #894, #859: nur tatsächlich beobachtete Teil-AC | Keine neue Rollen-/Rechteentscheidung ableiten |
| Q03 / Candidateinstallation | Revision, Wheel/sdist und OCI-Config-/Manifestbindung des exakten Candidate bestätigen | #859; veröffentlichte #847/#823/#658-AC bleiben offen | Release/Tag/Publish separat |
| Q04 / Setup und Persistenz | Über bestehenden Setupweg nichtgeheime Einstellung speichern, Recreate, stored/effective und Production-Schreibsperren prüfen; kontrollierter Persistenzfehler nur in separater Wegwerfinstallation | #691/#823: Positiv-, Fehler-/Rollback- und ausdrücklich veröffentlichte Fälle getrennt; kein Crashatomaritätsclaim | Nur erforderliche Bedienabnahme; kein Produktionssubject umkonfigurieren |
| Q05 / Doctor | Exakten Required Context positiv und gezielt falschen prozesslokalen Sollwert negativ an derselben nativen Regel prüfen; keine Branchregel entfernen | #694: eigener temporärer Prüfer und tatsächlicher Widerruf zusätzlich Pflicht | Getrennten freigegebenen Prüferzugang identifizieren; aktiven gemeinsamen Operatorzugang nicht widerrufen |
| Q06 / Health, Restart, State | Aktive berechtigte Probe von passiven GETs trennen; vorab geplanten Restart und Statebindung lesen; TTL/Instanz/Restore/Integritätsnegative in separaten Installationen | #693: fehlende/alte Facts nicht PASS; #894: non-root/Owner/Gitadmin/Mountmatrix; #830: Restart im Lauf nicht durch Prep-Restart ersetzen | Ein Lifecycle-Drill wird vor Start festgelegt, kein reparierender Neustart |
| Q07 / Dashboard | Tatsächliche URL/Instanz, Auth-Deny, Workflowphasen, aktuelle/letzte Calls und Abschlussprojektion lesen | #830, #890: eigene negative und releasegebundene AC bleiben Pflicht; #889/#891/#944 bereits selbstständig abgenommen | Nur noch konkret benötigte neue Sichtabnahme |
| Q08 / Native SCM | Labels/Events/HMAC/Delivery, Required Context, Bot-/Humanrechte lesen; tatsächliche Humanaktion über signierte native Delivery beobachten | #905: Transport-/Setup-AC; keine künstlichen internen Events, keine Watch-Rettung | Echte Planfreigabe beim jeweiligen Subject |
| Q09 / Taskrouten | Bestehende bounded Planning/Implementation/Review/Healing-Probes samt Parser, effective readback und Freeze prüfen; Catalog/Suitability als advisory ausweisen | #822: nur das verwendete Profil/Modell; keine Qualification aller Provider oder der ungenutzten Evaluation | Kein Routenwechsel innerhalb eines Subjects |
| Q10 / Secret-Negativscenario | Kanonisches negatives Scenario nativ anlegen; ein öffentlicher `samuel run`; Humanapproval; Secret-Gate muss blockieren, ohne PR/Merge/Mainänderung oder Secretpersistenz | #859/#890: erwarteter BLOCK und Ursache/Folge/Related-Evidence; #844: durchgehende signierte Writerbindung zusätzlich | Human Plan Approval; bei anderem Ausgang terminal FAIL |
| Q11–Q16 / vollständiges positives Scenario | Kanonisches Golden-Scenario; Planning → Humanapproval → Candidate → AC/Gates → PR/Review/CI → Human Merge → Demo-Redeploy/Fach-Smoke → Audit-/Dashboardabschluss | #859: vollständige gleiche Bindung; #900/#905/#830/#890 nur ihre hier belegten AC | Plan Approval und Human Merge; kein automatischer SCM-Issueabschluss |
| #846 / Nichtplan und Replan | Eigener frischer SCM-Fall mit nichtautoritativer Blockmeldung darf keine aktive Planauthority erzeugen; echter bestehender Plan blockiert erneutes `run`, explizites Replan widerruft alte Approval | #846: reales SCM-Input-/Plan-/Audit-/Runreadback; frühere terminale Subjects nicht reparieren | Ersatzplan verlangt neue Humanfreigabe |
| #847 / CLI-Gegenfälle | Eigene installierte `samuel run`-Invocation mit echtem PlanBlocked muss nonzero liefern; positive Invocation liefert 0, fremde Korrelation beeinflusst sie nicht | Regression vorab; eigene verpflichtende releasegebundene Positiv-/Negativprozesse nach Publish | Releasegrenze; kein interner Bus als Realqualification |
| #880 / MANUAL-Matrix | Bestehende Integration prüft einzelne Kriterien, falschen Head/Contract/Actor, Stale, Replan und Replay. Mehrere gültige Receipts müssen erst gemeinsam genau eine native Fortsetzung erzeugen | Deterministische Regression zählt auf ihrer Ebene. Reale UX-/Transportfälle erhalten eigenes zulässiges Scenario mit echter fachlicher/visueller MANUAL-Notwendigkeit; kanonischen Golden-Contract nicht künstlich erweitern | Nur der Mensch akzeptiert; kein Dummy-MANUAL und keine Botreceipt |
| #948 / Approval-Veröffentlichung | Sichtbaren Plan, PlanPosted/Labels, native Timeline/Delivery und materialisierte Approval in einem fokussierten Fall vergleichen; fehlende/stale/mehrdeutige Bindung bleibt blockiert | Historische Root Cause bleibt UNKNOWN. Testfall erst mit reproduzierbarer Zustellreihenfolge und konkretem Soll ausführen; vorhandenes Label wird nicht zur Approval | Humanaktion zur benötigten Stufe; keine schnelle Approval künstlich simulieren |
| #844 / Auditnegative | Neue Wegwerfchain mit richtig gebundenem Writer prüfen; keylosen Append/fehlenden Key fail-closed prüfen; nach geplantem Restart native `audit verify` | Keine Änderung alter q1/q2-Chains; eigene releasegebundene Chainprobe bleibt Pflicht | Kein produktiven Key entfernen oder historischen Audit schreiben |
| #828 / Applydiagnose | Vorhandene Parser-/Applyregressionen und redigierte Diagnose im passenden Fall prüfen; Input-/Subjectbindung ohne Providerrawtext erhalten | Neuer Fall beweist nicht die unbekannte ursprüngliche Ursache. Nicht wiedergewinnbare historische Evidence bleibt explizite eigene Abschlussentscheidung | Keine Root Cause oder historische PASS-Evidence erfinden |

Q10 und Q11–Q16 verwenden vorhandene Scenario-Dateien, keine neue
Scenario-/Harnessplattform. Ergänzende Fälle benutzen bestehende öffentliche
CLI/API/SCM-Pfade. Ein deterministischer In-Process-Test wird nicht als reale
SCM-/Provider-/Releaseabnahme bezeichnet. Vor jedem neuen echten Subject gilt
sein eigener Preparation-/Freshness-/Freezevertrag.

### Was nicht durch diese Kampagne geschlossen wird

#422 (Identity/TLS/Session-Recovery), #468 (Review-/Expected-head-/Automerge-
Sonderfälle), #521/#679 (passiver/externer Execution-Provider), #549
(Budgetgrenzen), #575 (Clarification), #668/#482 (Retention-/Recoveryvollzug),
#636/#639 (releasegebundene externe Consumer) und #878 (Promptprofil-Sonderfälle)
benötigen ihre eigenen ausdrücklich verlangten Zusatzfälle. Gemeinsame
Infrastruktur ist nutzbar, deren Aktivierung ist kein Golden-Nebeneffekt.
#811 und #567 behalten ihre menschliche Support-/Netzentscheidung; #821 die
noch fehlenden tatsächlich benötigten Rollen-/Toolzugänge.

#873/#883/#897/#920 und der vollständige Produktrest #921 sowie die späteren
UX-Findings #951/#954 werden nicht als bereits implementierte Abnahmen
ausgegeben oder vorsorglich in den Hauptpfad eingebaut. #952s enger Taskeditorfix
ist inzwischen durch #958 integriert und nativ abgenommen (eigene Matrix,
05.10.2026); nur dessen Dokument-/Remoteabschluss bleibt offen. Er erzeugt
keinen neuen Golden-/D0-Nachweis. #888 bleibt seine
Post-Golden-Auswertung; #840 erhält nur den aktuellen Träger-/Evidenceanschluss.

### Abschluss je ursprünglichem Issue

Ein Verweis auf #859 schließt kein Issue. Nach dem Fall werden die eigenen AC
mit Code/Test/realem Receipt oder einer ausdrücklich benannten
Maintainerentscheidung abgeglichen. Ungeprüfte Restfälle bleiben sichtbar.
Ein Issue wird erst nach eigenem Exit inklusive relevantem Doku-/Main-/Wiki-
Anschluss geschlossen. Eine fehlende historische Evidence wird nicht durch
neue Runs ersetzt. #812 ist auf ausdrücklichen Maintainerauftrag administrativ
geschlossen; dessen a18-Pre-Tag-Punkt ist weiterhin nicht nachgewiesen.

## Gemeinsame Regeln

- Jeder Abschlussclaim nennt Issue, HEAD/Candidate, Subject/Attempt (falls
  anwendbar), Test-/Evidence-Stufe, Resultat und verbleibenden Scope.
  Beispiel: `Regression PASS @ <sha>; #847 implementiert; installierte
  Positiv-/Negativabnahme offen`. Kein ungebundenes `fixed`, `ready` oder
  `qualified`.
- Ein gemeinsamer E2E-PASS ersetzt keine issueeigene Identity-Recovery-,
  Budget-, Clarification-, Retention-, Execution-Provider- oder
  Extension-/Consumer-Abnahme. Normale Issue→PR→CI-Arbeit bleibt möglich.
- Golden ist kein Debugginglauf. Ein fehlgeschlagener Subject bleibt FAIL.
- Verschiedene Runs werden nie zu einem PASS zusammengesetzt.
- Provider-/Modell-/Configwechsel ist ein neuer Input und mindestens ein neuer
  Attempt; nach Candidate-/Releasebindung ist regelmaessig ein neuer Subject
  erforderlich.
- `configured` oder `stored_effective=match` bedeutet nicht `available`.
- `PlanBlocked` und `WorkflowBlocked` werden nicht durch Handler-, Bus-, DB-
  oder Labelmanipulation umgangen.
- Human Approval, MANUAL Acceptance und Human Merge bleiben echte
  Humanhandlungen.
- Labels sind Projektion. Plan, Contract, Policy, Source und Candidate-Head
  bleiben die Authority und muessen bei Fortsetzung unveraendert gebunden sein.
- Signierte Webhookdelivery und authentifiziertes Polling sind getrennte
  Transport-Evidence, auch wenn beide dieselbe Entscheidung materialisieren.
- Prep-/Harness-, Provider-, Operator- und Productfehler werden getrennt.

## Teststufen

| Stufe | Zweck und erlaubter Claim | Voraussetzungen / Befehl | Stop, Recovery und Evidence |
|---|---|---|---|
| Format/Lint | statische Stil- und Fehlerpruefung; beweist keine Runtimewirkung | isolierte Dev-Umgebung; `ruff check .` und `ruff format --check .` | jeder Befund stoppt CI; Code/Doku korrigieren und gleiche Stufe wiederholen; Log + SHA sichern |
| Typecheck | statische Produktions- und Testtypen | `mypy samuel/ --ignore-missing-imports`; `mypy --config-file mypy-tests.ini` | Typfehler stoppt; Impact-Retest, danach volle CI |
| Architektur/Contracts | Slicegrenzen, Capability-/Dokument-/Wiki-/Containervertrag | `python3 tools/control_matrix.py check`; `python3 tools/wiki.py check`; `python tools/container_release.py check`; `pytest tests/test_architecture_v2.py -v` | Drift nie manuell uebergehen; generierte/gebundene Quelle korrigieren; Receipts und Digests sichern |
| Unit/Regression | lokale Funktion und konkrete Defekte | `pytest tests/ samuel/ -v --tb=short` | rot stoppt; gezielter Retest ist Debug-Evidence, volle Suite vor PR bleibt Pflicht |
| Integration | Komponenten- und reale In-Process-Uebergaenge | in der vollen Suite, besonders `tests/test_*integration*.py`, State, Workspace, Watch, Approval und Gate-Tests | beweist keinen externen SCM-/Providerbetrieb; JUnit/Log und Head sichern |
| Docs/Wiki/Capability | aktive Claims gegen gebundene Quellen | Contracttools oben plus relevante `tests/test_active_docs.py`, `test_document_contract.py`, `test_control_matrix.py`, `test_wiki.py` | historische Dateien nicht umschreiben; aktuelle Quelle oder Statusindex korrigieren |
| Container/Release offline | reproduzierbarer Build-/Lock-/Lizenzvertrag ohne Publish | `python tools/container_release.py check`; Build in Tempdir mit `python -m build --outdir "$DIR"`; `python tools/verify_distribution_license.py "$DIR"` | kein Registry-Push; Buildlog, Manifest-/Lockdigests sichern |
| Security/Dependencies | bekannte Dependencyvulnerabilities und Secretgrenzen | `python tools/run_pip_audit.py --attempts 3 --delay-seconds 5`; diff-/history Secret-Scan mit redigiertem Ergebnis | echte Vulnerability stoppt sofort; Transportfehler bounded retry; niemals Fundwerte protokollieren |
| Public Flow / Black Box | nur installierte CLI, REST, SCM und dokumentierte Operatorpfade | frische Installation; Befehle aus `INSTALL.md`; keine internen Handler | interner Dispatch entwertet den Claim; Request-/Responseklassen, Version und Subject sichern |
| Provider Self-Check | reale Erreichbarkeit jeder vom konkreten Profil produktiv konsumierten Taskroute | aktuelle Config/Secrets, bounded taskgerechte Probe für Planning, Implementation, Review und Healing; eine konfigurierte Evaluation-Route ohne LLM-Consumer ist keine Pflichtprobe | Auth, unavailable, Schemafehler oder Truncation einer benötigten Route blockiert positiven E2E; keine Route im laufenden Attempt wechseln |
| Positive Development E2E | normaler Hauptpfad bis PR, CI, Human Review/Merge | frischer isolierter SCM-Subject, exakter Product-/Demo-Head, Labels, Runner, Webhook, Required Check und alle Routen bereit | erster Product-/Harness-/Providerfehler beendet Attempt; Ursache klassifizieren, Fix separat integrieren, neuer unveraenderter Komplettlauf |
| Negative Development E2E | fail-closed Verhalten an gezielten oeffentlichen Grenzen | eigener frischer Negativsubject und erwarteter Blockvertrag | kein Heilen zu PASS; gebundener Reason-Code, fehlende Nebenwirkung und Evidence sichern |
| Development Golden Rehearsal | releasefaehige, zusammenhaengende Development-Strecke | alle Vorchecks PASS; unveraenderte Kandidateninputs; #859 | jeder Fehler terminal; keine Kombination alter Runs; kompletter neuer Lauf nach Fix |
| Formal Golden/D0 | releasegebundener Positiv- und Negativnachweis | immutable Release/Publish, frische Installation, neuer Subject, D0-Vertrag #658 | keine Debugaktion; Abweichung FAIL und neue Release-/Subjectentscheidung |
| Release/Publish | create-only Artefakte, Human Merge/Tag/Publish und Readback | `VERSIONING.md`, `CONTAINER_RELEASE_OPERATIONS.md`, Release-Gates; getrennte Publisherrolle | kein Force/Overwrite; unterbrochenen Publish nur ueber dokumentierte Recovery; Tag, Assets, Digests, CI sichern |
| Post-Publish | beweist Auslieferung und Nutzbarkeit des exakten Artefakts | frische Installation vom publizierten Digest/Asset, Version/Revision/Health und D0-Readback | andere lokale Builds sind keine Ersatz-Evidence |

`$DIR` wird mit `mktemp -d` erzeugt. Release-, Provider- und SCM-Befehle mit
externen Wirkungen werden nur aus den jeweils akzeptierten Runbooks ausgefuehrt.

## Impact-Retest, kompletter Lauf und neuer Subject

Ein Impact-Retest genuegt waehrend der Fehlerkorrektur, wenn er nur die
betroffene lokale Grenze bestaetigt. Vor Merge folgt trotzdem die volle CI.
Eine materiell pfadverändernde integrierte Änderung an Planning, Approval,
Implementation, MANUAL, Gates, PR, CI, Review, Merge oder Evidence verlangt
einen neuen passenden Development-E2E-Nachweis. Reine Doku, isolierte
Darstellung und nichtpfadrelevante Diagnose brauchen keine automatische
Voll-E2E-Wiederholung. Ein terminal fehlgeschlagener Subject wird nach einem
Fix weiterhin nicht repariert oder zu einem PASS fortgeschrieben. Ein neuer Subject ist zwingend, wenn der alte Subject
terminal fehlgeschlagen ist, Inputs oder Authoritybindungen gewechselt haben,
oder der Formal-D0-Vertrag Frische verlangt. Derselbe langlebige Issue darf nur
ueber den sicheren, vom Core abgeleiteten Re-Entry-Vertrag #920 erneut versucht
werden; alte Evidence bleibt erhalten.

## Failure-Klassifikation

| Klasse | Beispiel | Zulaessige naechste Aktion |
|---|---|---|
| PRODUCT_DEFECT | fehlender MANUAL-Dispatch im historischen Issue #3 | Issue/Regression/Fix/volle CI; alter Run bleibt FAIL |
| QUALIFICATION_HARNESS | Labels nicht provisioniert, falscher Startpfad | Harness/Runbook korrigieren; Productcode nicht erfinden |
| OPERATOR | nicht autorisierter Hook-/State-Eingriff | stoppen, Evidence sichern, sicheren Prepweg wiederherstellen |
| PROVIDER_QUALITY/AVAILABILITY | Outputlimit, Modell weg, inkompatible Antwort | Route vor neuem Attempt real pruefen; kein Corebug ohne Codeevidence |
| ENVIRONMENT/INFRASTRUCTURE | Mountrechte, Netzwerk, Runner | Infrastruktur beheben und Readiness neu pruefen |
| CONTRACT/POLICY | Parser-, Source-, Candidate- oder Required-Gate-Block | fail-closed; autorisierten Fix oder Replan, keine Umgehung |

## Historische Development-E2E-Fehlversuche

- Issue #1: Planning-Truncation, falsche Runner-Autodetection,
  Label-Provisioning und spaeter Contract/Selectorgrenzen. Die technischen
  Runner-/Retry-/GREP-Fixes sind heute integriert; der Run bleibt historisch.
- Issue #2: Planning und echte Human Approval bestanden; Implementation endete
  auf einer bekannten Route mit `token_limit` bei 8192, ohne Candidate.
- Issue #3: alle Routen vorgeprueft; Planning, Human Approval, Implementation,
  Candidate und automatische Gates bestanden; signierter MANUAL-Receipt wurde
  beobachtet, aber damals nicht fortgesetzt. #910 behebt den Codepfad; kein
  alter Run wurde fortgesetzt.

Diese drei historischen Subjects liefern keinen vollständigen positiven
Development-E2E-Nachweis und keinen Development-Golden-/Formal-D0-PASS.
Die späteren, getrennt gebundenen Hauptpfad-PASS-Baselines stehen unten;
sie ändern weder diese FAILs noch deren fehlende Evidence.

## Ausfuehrungs- und Ergebnisvertrag je Ebene

Die Befehle oben sind die tatsaechlichen CI-Kommandos aus
`.gitea/workflows/ci.yml`. In einer lokalen Umgebung wird dieselbe installierte
Projekt-Pythonumgebung verwendet; ein fehlendes globales `pydantic`, Ruff oder
Mypy wird nicht durch geaenderte Productdependencies kaschiert. Der
Documentation-Contract laeuft mit `tools/control_matrix.py check`; die
Wiki-Projektion mit `tools/wiki.py check` und nach einem Build zusaetzlich
`check-local`. Ein Wiki-Publish ist ein getrennter externer Effekt und liefert
eine eigene Source-/Artifact-/Remote-Head-Receipt.

| Ebene | Input und Authority | Mutation / erwartete Evidence | PASS / FAIL / BLOCKED / NOT_EVALUATED |
|---|---|---|---|
| Ruff, Format, Mypy, Unit/Integration, Architektur | exakter Checkout-Head, Lock-/Pyproject-Stand, installierte CI-Tools | nur lokale Test-/Buildartefakte; Exitcode, Testzahl und Head | PASS nur bei Exit 0; rote Assertion/Typregel FAIL; fehlendes Tool BLOCKED; nicht gestartet NOT_EVALUATED |
| Control-/Document-/Wiki-Contract | versionierte Quellen, Manifest und aktuelle generierte Bindungen | `check` liest; ein bewusstes `render`/Wiki-`build` aendert nur generierte Dokumentartefakte | Digest- oder Coverage-Drift FAIL, nicht als „nur Doku“ ignorieren |
| Container offline, Distribution, Lizenz, Dependency-/Secret-Scan | exakter Source-Head, Build-/Lockdateien und definierte Scanrange | temporaere Buildartefakte; Paketmetadata, Asset-/Lizenz- und redigierte Scannergebnisse | echter Fund FAIL; Tool-/Netzausfall BLOCKED nach bounded Retry; kein Publishclaim |
| Providerprobe und Public Flow | effektive Taskrouten, Credentials nur im Prozess, SCM-/Operatorrolle | explizit autorisierte bounded Provider-/SCM-Probes; Requestklassen, Route, Schema, Zeiten, redigierter Fehler | konfigurierte Route allein NOT_EVALUATED; Auth-/Schema-/Truncationfehler FAIL/BLOCKED fuer den positiven Subject |
| Development E2E / Golden | frischer isolierter SCM-Subject, Product-/Demo-/Config-/Policy-/Runnerbindung, echte Humanentscheidungen | oeffentliche Workflowwirkungen, PR/CI/Human-Merge-Receipt nur im freigegebenen Subject | PASS nur als zusammenhaengender unveraenderter Lauf; erster materieller Fehler FAIL; fehlende Vorbedingung BLOCKED vor Start |
| Release und Formal D0 | Human-Merge, create-only Tag, veroeffentlichter unveraenderlicher Digest, frische Installation | Publisherwirkung und danach neuer D0-Subject; Tag-/Asset-/OCI-/Installations-/Goldenbelege | Publish-PASS ist kein D0-PASS; Bot-Merge, Subjectwechsel oder alte Teilbelege ergeben keinen Gesamt-PASS |

Bei einem **Productdefekt**: alten Subject und Fehlerevidence erhalten,
Defekt auf Product-`main` separat mit Tests/PR/CI beheben und fuer positive
E2E-/Golden-Claims einen neuen vollstaendigen Subject beginnen. Bei einem
**Provider- oder Infrastrukturfehler**: Fehlerquelle und effektive Route
festhalten, Vorbedingung ausserhalb des laufenden Subjects beheben und
Readiness neu pruefen; ein anderer Provider ist ein neuer Input. Bei einem
**Harness-/Operatorfehler**: die Preparation stoppen, Nebenwirkungen
read-backen und nie als Product-PASS oder Productdefekt umdeuten.

`retry` ist nur innerhalb des implementierten, budgetierten
Transport-/Taskvertrags zulaessig. `replan` widerruft den alten Plan und
benoetigt frische Authority; `resume` finalisiert ausschliesslich gebundene
persistierte technische Wirkungen. Ein freier terminaler Workflow-Retry ist
bis #920 nicht verfuegbar. Evidence verschiedener Heads, Releases, Provider,
Config-/Policy-Digests, Actors oder Subjects wird niemals zu einem Golden-
oder Formal-D0-PASS kombiniert. Eine lokale Regression darf die historische
Failure-Receipt nicht rueckwirkend aendern.

## Bestätigte Development-Regressionsbaseline — 02.10.2026

Product `1a87ef036b6481b8486322e7ff36dacf80a3129f`, Qualification-Base
`1a4e28e310a840dac6d3a870d7193522ee17fc5e`, Subject/Attempt
`1a87ef03-20261002-01`, isoliertes Repository
`example-owner/samuel-r24-1a87ef03-20261002-01`, Issue #1 / PR #2 bis Human
Merge `6b01b8fe2a8b8e88cd4150abb48f0cab15856379`: Development-Hauptpfad PASS.
Kein Watch-Scan, keine Reparatur oder Inputänderung innerhalb dieses Subjects.
Erforderliche menschliche Plan-/MANUAL-/Mergehandlungen blieben menschlich.
Vor Start 19/19 zeitgültige Preparation-PASS; diese historische Evidence ist
kein aktueller erneuerter Receipt. Weitergehende Golden-/D0-/Issue-AC bleiben
eigenständig. Details und historische FAIL-Abgrenzung: CURRENT_PRODUCT_STATUS.


## Eigenständige Development-Regressionsbaseline — 03.10.2026

Product `eb6cce188ee9c4f7cb35a28036586385815a2d51`, Qualification-Base
`1a4e28e310a840dac6d3a870d7193522ee17fc5e`, Subject/Attempt
`eb6cce18-20261003-01`, Repository `example-owner/samuel-r24-eb6cce18-20261003-01`,
Issue #1 / PR #2, Candidate `f15b7c4973e7a6074fde38e8ef377e3d92ff1da1`,
Human Merge `9d35329aa6377bc99499eac53659e28afd9ce838`: eigener Hauptpfad PASS.
Vor Start 19/19 zeitgültige Preparation-PASS/Exit 0; unveränderter Lauf ohne
Agent-Watch-Scan oder Reparatur. Required Gates, Candidate-CI #1083, Review,
Human Merge/Merge-CI #1084 und nativer Abschluss sind gebunden belegt.

Sieben automatische AC, keine MANUAL-Kriterien: daraus entsteht keine neue
MANUAL-Continuation-Evidence. Der ältere MANUAL-PASS bleibt auf 1a87ef03.
Kein Golden-/D0-/Healing-/Evaluation- oder Fremdissue-PASS. Details und
Terminal-Receipt: CURRENT_PRODUCT_STATUS. Der verbrauchte SCM-Subject darf
nicht als frische Preparation für den nächsten Lauf gelten.

## Eigenständige Development-Regressionsbaseline auf Main 41d39b0e — 03.10.2026

Product `41d39b0e4f5a28ca06960a349812aee6e3eed16f`, Qualification-Base
`1a4e28e310a840dac6d3a870d7193522ee17fc5e`, Subject/Attempt
`41d39b0e-20261003-01`, Repository `example-owner/samuel-r24-41d39b0e-20261003-01`,
Issue #1 / PR #2, Candidate `ed73d315496c3eb02c325131019e730cf7b37459`,
Human Merge `e5fa956fe1fe4dc7637a6e6d5f00db4c899bd49f`: eigener Hauptpfad PASS.
Vor Start 19/19 zeitgültige Preparation-PASS / CLI Exit 0; danach unveränderter
Lauf ohne Agent-Watch-Scan, Reparatur oder Inputwechsel. Acht automatische AC,
Required Gates, Candidate-CI #1097, Review `pass`, Human Merge/Merge-CI #1098
und nativer Abschluss einschließlich zweitem fachlichem Kommentar belegt.

Keine MANUAL-Kriterien; keine neue MANUAL-Continuation-Evidence. Die
nicht blockierende EOF-Newline-Suggestion ändert weder Reviewentscheidung noch
historischen Candidate. Ältere Subjects bleiben getrennt; keine Golden-/D0-/
Healing-/Evaluation- oder fremde AC-Abnahme. Receipt und Einzelbindungen:
CURRENT_PRODUCT_STATUS. Der verbrauchte Subject/Start-Receipt ist kein neues READY.


## Eigenständige Development-Regressionsbaseline auf Main 7843d4fd — 04.10.2026

Product `7843d4fd9a79b4db9a9ed78e37269f59a27fc1d7`, Qualification-Base
`1a4e28e310a840dac6d3a870d7193522ee17fc5e`, Repository
`example-owner/samuel-r24-7843d4fd-20261004-01`, Subject/Attempt
`7843d4fd-20261004-01`, Issue #1 / PR #2. Vor Start zeitgültiger
19/19 READY-Receipt und vorgesehener CLI Exit 0. Ein öffentlicher Einstieg,
danach nur Beobachtung: Planning → Human Plan Approval → Implementation →
sechs automatische AC → 13 Required Gates → PR → CI → Review → Human Merge →
nativer Abschluss PASS. Candidate `785672757169d96dbbc0cc560b356dd4abf2f9fb`,
Human Merge `99ede5f195e2a6e61e128da2c9737ae857aeada5` durch example-owner;
Candidate-CI #1119 und Merge-CI #1120 PASS, Review pass ohne Findings.

Kein agentenseitiger Watch-Scan, Reparatur oder Inputwechsel. Keine MANUAL-
Kriterien, direkte In-flight-Abnahme, Healing-Ausführung, Evaluation-LLM-
Verfügbarkeit, vollständiger Development-Golden-/Formal-D0- oder fremder
Issue-PASS. Der abgeschlossene Subject wird nicht weiterverwendet;
Preparation-Evidence bleibt zeitgebunden. Native Abschluss-/Labelprojektion
und separate fachliche Erklärung sind belegt; Details/Terminal-Receipt:
CURRENT_PRODUCT_STATUS. Dies ergänzt vorhandene Evidence, keine neue Regel.

## Eigener Development-Abschluss — 04.10.2026, a0f16c02

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

Die generierte MANUAL-Anleitung #45455 enthielt den exakten AC-/Contract-/Head-
Befehl und trennte Planfreigabe von Acceptance. Der Mensch bestätigte den
Candidate mit #45457; anschließend native Reevaluation, Gates/PR/Review/CI
und Human Merge ohne Agent-Watch oder Reparatur. Dies belegt den positiven
Ein-Kriterium-Pfad, keine eigene Stale-/Race-/Replan-/Multi-Criterion-Matrix.

`merged`, `status:done` und SCM-`closed` bleiben verschiedene beobachtete Fakten.
Der aktuelle Abschlusskommentar schließt das SCM-Issue ausdrücklich nicht
automatisch. Eine spätere Schließungsänderung benötigt den vorhandenen eigenen
Scope-/Authoritycontract und gezielte Regression, keinen rückwirkenden Eingriff
in diesen abgeschlossenen Subject. Die initiale Approvalablehnung wird auch
durch die spätere menschliche Freigabe nicht gelöscht oder zu PASS umgedeutet.
