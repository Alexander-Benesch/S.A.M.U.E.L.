# Test and Qualification Runbook

Aktuelle Verfahren und Grenzen stehen in den Fachabschnitten dieser Anleitung.
Frühere Releases und Attempts sind über die erhaltenen Anker im
[historischen Originalbestand](../archive/reader-history-2026-10-11/TEST_AND_QUALIFICATION_RUNBOOK.md) erreichbar.
a15 ist keine aktuelle Installationsreferenz oder Supportempfehlung; spätere
Erfolge ändern seine Teilnachweise und fehlende vollständige Human-Merge-Abnahme nicht.


## Aktueller Testrelease v2.0.0a29 — 09.10.2026

PR #989 und #980 sind menschlich gemergt und in a29 veröffentlicht.
Main-/Tag-CI, sieben gebundene Assets, OCI-Publisher-Smoke, frische
Draft- und Published-Erstinstallation sowie der erneute Asset-Readback sind PASS.
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

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](../archive/reader-history-2026-10-11/TEST_AND_QUALIFICATION_RUNBOOK.md#historischer-installationsstand-v200a28--08102026).

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

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](../archive/reader-history-2026-10-11/TEST_AND_QUALIFICATION_RUNBOOK.md#veröffentlichter-release-v200a26--05102026).

## Administrativer Altlastenabschluss und Releasezweck — 05.10.2026

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](../archive/reader-history-2026-10-11/TEST_AND_QUALIFICATION_RUNBOOK.md#administrativer-altlastenabschluss-und-releasezweck--05102026).

**Weiterhin geltende Grenze:**

Administrativ geschlossen bedeutet kein Abnahme-PASS. Historische FAILs,
UNKNOWN und Teilnachweise behalten ihre eigene Bindung; neue Qualification
braucht ihre eigenen erfüllten Kriterien.

## Eigene releasegebundene Consumerabnahme — 05.10.2026

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](../archive/reader-history-2026-10-11/TEST_AND_QUALIFICATION_RUNBOOK.md#eigene-releasegebundene-consumerabnahme--05102026).

**Weiterhin geltende Grenze:**

Befehle stammen aus `.gitea/workflows/ci.yml`, den ausgelieferten Tools und
den bestehenden Release-/D0-Verträgen. Dieses Runbook schafft keine neue Authority.

## Gemeinsamer Abnahmeplan der verbliebenen Altlasten — #859

**HISTORICAL / AUDIT_EVIDENCE:** Diese datierte Kampagnenplanung bleibt mit
ihren damaligen Trägern und offenen Punkten erhalten. Sie ist keine aktuelle
Liste offener Issues. Insbesondere sind #636/#639/#952 mit ihren eigenen
engen Nachweisen abgeschlossen; #954s Abschluss ist oben gebunden. #567 ist
nach dem Operatorbericht vom 05.10.2026 geschlossen. Die tatsächlichen
heutigen Restabnahmen werden in #962 und den aktuellen Statusabschnitten
geführt. Ein späterer Abschluss ändert keinen früheren FAIL/UNKNOWN und
qualifiziert keinen fremden Subject.

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
Anschluss geschlossen. Fehlende historische Evidence wird nicht rückwirkend
als PASS ausgegeben. Ein heutiger Rest darf nur dann als `SUPERSEDED`
eingeordnet werden, wenn ein aktueller Nachweis denselben fachlichen Claim
oder einen nachweislich stärkeren aktuellen Contract abdeckt; alte Evidence,
Ersetzungsgrund und aktuelle Bindung bleiben sichtbar. #812 ist auf
ausdrücklichen Maintainerauftrag administrativ
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

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](../archive/reader-history-2026-10-11/TEST_AND_QUALIFICATION_RUNBOOK.md#historische-development-e2e-fehlversuche).

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

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](../archive/reader-history-2026-10-11/TEST_AND_QUALIFICATION_RUNBOOK.md#bestätigte-development-regressionsbaseline--02102026).

## Eigenständige Development-Regressionsbaseline — 03.10.2026

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](../archive/reader-history-2026-10-11/TEST_AND_QUALIFICATION_RUNBOOK.md#eigenständige-development-regressionsbaseline--03102026).

## Eigenständige Development-Regressionsbaseline auf Main 41d39b0e — 03.10.2026

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](../archive/reader-history-2026-10-11/TEST_AND_QUALIFICATION_RUNBOOK.md#eigenständige-development-regressionsbaseline-auf-main-41d39b0e--03102026).

## Eigenständige Development-Regressionsbaseline auf Main 7843d4fd — 04.10.2026

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](../archive/reader-history-2026-10-11/TEST_AND_QUALIFICATION_RUNBOOK.md#eigenständige-development-regressionsbaseline-auf-main-7843d4fd--04102026).

## Eigener Development-Abschluss — 04.10.2026, a0f16c02

HISTORICAL — [damaliger Nachweis mit unveränderten Grenzen](../archive/reader-history-2026-10-11/TEST_AND_QUALIFICATION_RUNBOOK.md#eigener-development-abschluss--04102026-a0f16c02).

**Weiterhin geltende Grenze:**

`merged`, `status:done` und SCM-`closed` bleiben verschiedene beobachtete Fakten.
Der aktuelle Abschlusskommentar schließt das SCM-Issue ausdrücklich nicht
automatisch. Eine spätere Schließungsänderung benötigt den vorhandenen eigenen
Scope-/Authoritycontract und gezielte Regression, keinen rückwirkenden Eingriff
in diesen abgeschlossenen Subject. Die initiale Approvalablehnung wird auch
durch die spätere menschliche Freigabe nicht gelöscht oder zu PASS umgedeutet.

