# HISTORICAL / AUDIT_EVIDENCE — a15-Referenzstand vom 21.09.2026

Dieser unveränderte Auszug stammt aus `technische Beschreibungen/README.md`
auf Main `4bd335cdb97871b03386e99226ce095baae35ba5`; dort war als
Prüfstand `05ea89ec9b93a6838e1ddeca66f23fe69adcfab9` benannt.
Archivierung im Rahmen #1001 am 09.10.2026. Der damalige Befund wird weder
als heutige Runtimebeschreibung verwendet noch rückwirkend zu PASS geändert.
Die im Auszug ergänzte a29-Releaseinformation und damalige Auftragsgrenzen
bleiben ebenfalls als Momentaufnahme erhalten. Aktueller Stand: vorhandene
Current-Status-/Capabilityquellen und Live-Issues #962/#994.

---

## Belegreife der realen Referenzstrecke

Automatisierte Tests belegen Codepfade, nicht automatisch eine funktionierende
Kundeninstallation. Die [Capability-/Wirksamkeitsmatrix](../docs/CAPABILITY_MATRIX.md)
nennt je Kontrolle positive/negative Tests, Wirkung und offene Issues. Die
zusätzliche reale Referenzqualification #658 bewertet Installation und Lauf als
Gesamtsystem. Stand des hier geprüften Ausgangscommits:

| Bereich | Automatisierte Evidence | Reale interne Referenz-Evidence | Aussage |
|---|---|---|---|
| Installation, Start, CLI, Doctor, Dashboard | Paket-, CLI-, Doctor-, REST- und Dashboard-Tests vorhanden; die Korrekturen #690 und #756 sind automatisiert belegt. #694 bindet genau einen erwarteten Required-Check-Kontext an Konfiguration, Doctor und Gate-Policy; die reale Zielprüfung steht noch aus | `v2.0.0a15` ist mit grüner Tag-CI #793, vier byteidentisch geprüften Assets, Git 2.47.3 und gesundem digestgebundenem Compose-Smoke veröffentlicht. Der frische D0-Lauf bestand Setup, Demo-Tests, Runtime-/Dashboardidentität, API-Auth, reale Providerprobes, Katalogaktualisierung, Credential-/Modell-/Webhookblocks, Audit und Neustart | **Reale Teilnachweise für die a15-Referenzkombination**; kein vollständiger D0-PASS, keine Beta- oder allgemeine Betriebsfreigabe. Bis zum positiven und negativen Live-Doctor-Nachweis bleibt #694 eine bekannte Betreibergrenze. |
| Planning und menschliche Freigabe | Unit-/Integrationspfade einschließlich Remote-Snapshot, explizitem Replan-Widerruf, Plan-Kommentar-ID, menschlichem Labelereignis, Positiv-, Retry-, Drift-, Runner-Readiness- und Blockfällen vorhanden | Demo-#57 und #58 erhielten je genau einen an denselben Demo-Base gebundenen Plan. Ein absichtlicher zweiter `run` für #57 endete terminal `blocked`; Plan, Kommentar, Vertrag und `status:plan` blieben unverändert. Erst die danach menschlich gesetzten Labels autorisierten den Watch-Pfad | **Qualifiziert für a15**; ein Planersatz verlangt weiterhin expliziten Widerruf und eine neue exakte Freigabe. |
| Implementation bis Candidate | Context-, LLM-Loop-, Patch-, Worktree- und Finalisierungstests vorhanden | Demo-#57 und #58 erzeugten nach echter menschlicher Freigabe je einen commitgebundenen Candidate aus ihrem gebundenen Base. Der Golden-Candidate wurde geprüft und als PR #59 publiziert; der Negativ-Candidate blieb ohne PR | **Positiver und negativer Candidate-Pfad für a15 real belegt**. Provider-/Modellschwäche bleibt eine getrennte Betriebsgrenze. |
| Acceptance, Required Gates und PR | Umfangreiche Gate-/AC-/Subject-/Recovery-Tests sowie negative Referenzbeobachtungen vorhanden | Demo-#57 bestand die gebundenen Acceptance-Kriterien, Required Gates und PR-CI #794; PR #59 wurde anschließend durch `demo-example-bot` statt durch den vorgeschriebenen menschlichen Akteur gemergt. Demo-#58 wurde durch `diff_secret_scan` blockiert; es entstanden für diesen Negativfall kein PR und keine damalige Main-Änderung | **Positive und negative Teilpfade real belegt; vollständiger D0-PASS nicht bestätigt.** Wesentliche Änderungen der gebundenen Kombination verlangen eine neue Evaluation. |
| Evaluation, Audit und Dashboard-Projektion | Observer-, Persistenz-, Replay-, Dashboard- und Security-Tests vorhanden | a15-Setup-, Provider-, Plan-, Approval-, Candidate-, AC-, PR- und Blockadeereignisse sind real persistiert; Audit-Kette und Dashboard blieben über Neustart intakt. `PlanReplanRejected` erschien als Workflow-Warnung, OWASP ASI01 und terminal blockierter Lauf | **Für die beobachteten a15-Teilpfade belegt**; offene Merge-, Diagnosedetail- und Betreibergrenzen bleiben getrennt sichtbar. |
| Externe SCM-Check-Advisory-Evidence | Parser-, Größen-, Subject-/Workflow-/Status-, Freshness-, Widerspruchs-, Dedupe-, Restore- und Authority-Regressionen vorhanden | Gitea-Run 794 für Demo-PR 59 wurde mit exakter Base-/Head-, Attempt-, Workflow-Blob- und Statuskontextbindung real gelesen; Replay blieb identisch, ein falscher Subject-Head wurde advisory abgelehnt | **Für diesen vorhandenen Gitea-Run als Advisory-Pull qualifiziert**; keine #679-, Required-, Runner-/Toolchain- oder Transportintegritäts-Qualification. |
| Self-Mode | Automatisierte Self-/Parity-/Schutzpfade vorhanden | Kein Self-Mode-D0 gegen den S.A.M.U.E.L.-Core | **Nicht real gegen den Core qualifiziert**. Erst nach wirksamem Schutz von laufender Installation, Trust Roots, Updatepfad und Policy darf ein unabhängiges Zielprojekt als Candidate dienen. |

Ein veröffentlichter Tag darf erst als für diese Referenzstrecke qualifiziert
bezeichnet werden, wenn ein frischer Install, ein positiver Golden Path und ein
echter Blockierfall mit genau diesem Paket-/Image-Digest abgeschlossen sind.
a15 erfüllt diese Grenze wegen des Bot-Merges nicht vollständig; grüne Tests,
andere Releases und geänderte Provider-/Policy-/Toolchainkombinationen bleiben
getrennte Aussagen. `v2.0.0a29` ist mit Tag-CI #1226, Prerelease #43, sieben
remote hashgeprüften Assets, korrekter OCI-Source und grünem ersten Required
Smoke der jüngste veröffentlichte Kandidat (Quellenabgleich 09.10.2026).
Frische unabhängige OCI-Erstinstallationen aus Draft- und veröffentlichten
Assets sind PASS. Golden-D0 und vollständige Sicherheitsqualification wurden
für a29 nicht ausgeführt. Er ist daher **PUBLISHED — INSTALLATION VERIFIED,
NOT GOLDEN/D0 QUALIFIED**; eine spätere Qualification benötigt einen
eigenen ausdrücklich freigegebenen Auftrag. Die nach #962 übertragenen eigenen
Altlastenabnahmen sind auf Maintainerentscheidung kein Blocker für diesen
Release. Die administrative Schließung von #658/#694 ist kein Abnahme-PASS;
ihre fehlenden Referenz-/Betriebsnachweise bleiben dort einzeln erhalten.
Das vollständige Testkonzept entsteht erst nach separater Erstinstallation.



## HISTORICAL / AUDIT_EVIDENCE — ursprünglicher Security-Abschnitt

Unveränderter Abschnitt aus `SECURITY.md` auf Main `4bd335cdb97871b03386e99226ce095baae35ba5`.
Die damalige Support-/Mergeaussage ist keine heutige Installationsauthority.

- `v2.0.0a15` publishes the currently supported verified `linux/amd64`
  container artifact. Its Schema-2 manifest binds digest, platform, locks and
  runtime identity. The fresh #658 D0 run additionally completed a
  human-approved Golden Path through required CI, plus a real
  `diff_secret_scan` block without a pull request or contemporaneous main
  drift. This qualification is scoped to the recorded release, policy,
  provider, toolchain and permission profile. It is not a multi-platform,
  signed, transparency-log-backed, compliance-certified or general deployment
  claim. The final PR merge was performed by the demo bot instead of the
  required human actor, so this evidence does not confirm the full D0 pass.
  Registry trust and the branch-protection admin-read boundary #694
  remain operator responsibilities.

