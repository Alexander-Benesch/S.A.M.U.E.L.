# Pipeline: PR-Gates (Code → PR erstellen)

Nach erfolgreicher Implementation etabliert die PR-Stufe zuerst einen
unveränderlichen Prüfgegenstand. Danach laufen die statischen Preflight-Gates;
erst ein grüner Required-Preflight darf kandidatenkontrollierte Acceptance-
Prüfungen starten. Ein `required`-Gate oder ein nicht belegbarer
Prüfgegenstand blockiert.

**Prüfdatum:** 2026-09-18 · **Abgeglichener Commit:**
`9dad1e172f5b517f4edd31c8a2312f0fcf65ee4d`.

Subject-Implementierung #515 · Wirksamkeitsaudit #517

Die Detailbewertung von Prüftiefe, Profilwirkung, Beweisen und Folgeissues
steht in der generierten
[Capability-/Wirksamkeitsmatrix](../docs/CAPABILITY_MATRIX.md). Die folgenden
13 Funktionen sind Registry-Einträge, nicht 13 gleichwertige
Sicherheitskontrollen.

---

## Inhalt

1. [Übersicht](#übersicht)
2. [G0 — `CreatePRCommand`-Eingang](#g0--createprcommand-eingang)
3. [G1 — Acceptance Contract und Revisionen binden](#g1--acceptance-contract-und-revisionen-binden)
4. [G2 — vollständigen Commit-Diff ermitteln](#g2--vollständigen-commit-diff-ermitteln)
5. [G3 — `GateContext` aufbauen](#g3--gatecontext-aufbauen)
6. [G4 — 13 interne Gates abarbeiten](#g4--13-interne-gates)
7. [G5 — External Gates (Plugin-Point)](#g5--external-gates)
8. [G6 — `PR` erstellen oder fail-closed beenden](#g6--pr-erstellen-oder-fail-closed-beenden)
9. [Gate-Ausführungsmodell und Status](#gate-ausführungsmodell-und-status)
10. [Gates im Detail](#gates-im-detail)
11. [Acceptance-Tags im Detail](#acceptance-tags-im-detail)
12. [External Gates im Detail](#external-gates-im-detail)
13. [Config: `config/gates.json`](#config-configgatesjson)

---

## Übersicht

```
 CreatePRCommand
       │
       ▼
 ┌──────────────┐
 │ G1 Subject   │   Repository + Base-/Head-SHA + Contract-/Policy-Hash
 │   etablieren │   Branch-Refs werden genau einmal per SCM aufgelöst
 └──────┬───────┘
        │
        ▼
 ┌──────────────┐
 │ G2 exakter   │   git diff <base-sha>...<head-sha>, vollständig
 │ Commit-Diff  │   über Limit: fail-closed, keine Trunkierung
 └──────┬───────┘
        │
        ▼
 ┌──────────────┐
 │ G3 GateCtx   │   derselbe EvaluationSubject für alle Gates
 └──────┬───────┘
        ▼
 ┌──────────────┐
 │ G4 Preflight │      7b, 8, 9, 13a, 13b; kein Candidate-Prozess
 └──────┬───────┘
        │ Required-Preflight grün?
        ├────► nein ────► übrige interne/externe Gates = SKIP
        ▼ ja
 ┌──────────────┐
 │ Verifikation │      deaktivierter Provider: lokaler VerifyAC
 │ + Rest-Gates │      qualifizierter Cutover: persistierter Request → Evidence
 └──────┬───────┘      nur "required" blockieren
        │  alle required passed?
        ├────► MANUAL offen ────► gebundener Wartezustand
        ├────► echter Fehler ───► GateFailedEvent(s)
        │
        ▼ ja
 ┌──────────────┐
 │ G5 External  │      IExternalGate-Plugins
 │    Gates     │
 └──────┬───────┘
        │ OK?
        ├────► nein ────► GateFailedEvent(s)
        │
        ▼
 GateEvaluationCompleted (genau einmal, vollständige Evidence)
        │
        ├────► required blockiert ────► Return + Evidence-Healing-Klassifikation
        ▼ alle required bestanden
 ┌──────────────┐
 │ G6 create_pr │      scm.create_pr(head, base, title, body)
 └──────┬───────┘
        │
        ├────► create_pr-Exception/ungültige Antwort
        │          └────► PRCreationFailed-Event ────► failed Return
        ▼ valide PR-Nummer + URL + exakt passender PR-Base/Head
    PRCreated-Event ────► successful Return
```

---

## G0 — `CreatePRCommand`-Eingang

**Datei:** `samuel/slices/pr_gates/handler.py`

**Woher?** Ziel-Workflow-Step in `config/workflows/standard.json`:
```json
{"on": "CodeGenerated", "send": "CreatePR"}
```

Der alte Weg `CodeGenerated → Score → Evaluate → EvalCompleted → CreatePR`
ist nicht mehr verdrahtet. Seine Typen und direkten Handler bleiben nur für
historische Lesbarkeit und gezielte Kompatibilitätstests vorhanden.

**Payload:**
```python
CreatePRCommand(
    issue_number: int,
    branch: str,           # z.B. "samuel/issue-136"
    base: str = "main",
    subject: EvaluationSubject | None = None,
    correlation_id: str,
)
```

---

## G1 — Acceptance Contract und Revisionen binden

Der neueste nicht widerrufene Plan-Kommentar (`## Plan` oder
`Agent-Metadaten`) bleibt die einzige Quelle des Acceptance Contracts. Ein
Widerruf bindet die konkrete Kommentar-ID, sodass auch ein inhaltlich
identischer Ersatzplan eine neue Freigabe benötigt. `parse_acceptance_contract()` strukturiert
ihn als Contract-Schema v2 beziehungsweise bei gebundener Klärungsbasis v3 mit Revision, Scope-Schema v1, inhaltsbasierten
stabilen Kriteriums-IDs, `automatic`/`manual` und Approval-Receipt. Bei neuen
SCM-gebundenen Plänen enthält derselbe Vertrag zusätzlich den systemerzeugten
`PlanningSourceSnapshot` aus Repository, Base-Ref, Base-SHA und Issue-Digest;
dieser ist Teil des Contract-Hashes. Der Scope
verwendet exakte `[FILE]`- und Präfix-`[PATH]`-Einträge sowie eine explizite
`Architecture-Expansion: disabled|allowed`. Zeilenenden, Unicode und Whitespace
werden kanonisiert; Checkboxzustände und der Kommentar-Wrapper sind reine
Darstellung und gehen nicht als Erfüllungszustand in den Vertrag ein. Der
letzte Wrapper-Trenner grenzt den systemeigenen Metadatenblock ab;
planinterne oder abschließende Markdown-Trenner bleiben Vertragsinhalt. Ein vom
LLM selbst deklarierter Source-Marker wird vor `PlanPosted` abgelehnt.
Contract v3 bindet zusätzlich die sichtbare Serien-/Rundenbasis samt exakten
Frage-/Antwortkommentar-IDs, Body-Digests, Akteur sowie Erstell- und
Änderungsrevisionen. Watch, Webhook und Implementation revalidieren diese
mutable SCM-Evidence; die PR-Gates erben dadurch ausschließlich einen bereits
freigegebenen, unveränderten Contract und führen keinen zweiten Dialog.

```python
EvaluationSubject(
    repository="https://scm.example/owner/repo",
    base_sha="<vollständige Commit-ID>",
    head_sha="<vollständige Commit-ID>",
    contract_hash="sha256:<...>",
    policy_version="2026-08-25.v4",
    policy_digest="sha256:<kanonische gates*.json + architecture.json>",
)
```

`IVersionControl.resolve_ref()` löst Base und Head genau einmal auf. Ein schon
im Command vorhandener Subject muss vollständig mit Repository, aktuellen
Revisionen, Contract und Policy übereinstimmen. Fehlender Adapter, Contract,
Commit oder eine Abweichung erzeugt `GateFailed(gate=evaluation_subject,
status=not_evaluated)`; es wird kein fachliches Gate ausgeführt.

## G2 — vollständigen Commit-Diff ermitteln

`IVersionControl.compare_commits(base_sha, head_sha, max_diff_bytes=...)`
liefert `RevisionComparison`. GitHub- und Gitea-Adapter vergleichen in der
konfigurierten lokalen Auscheckung exakt diese beiden Commit-IDs:

```text
git diff --name-only --no-renames --no-ext-diff <base-sha>...<head-sha>
git diff --binary --full-index --no-renames --no-ext-diff --no-textconv <base-sha>...<head-sha>
```

Dateiliste und Diff tragen dasselbe Base-/Head-Paar. Der vollständige Diff ist
Gate-Eingabe. `parameters.max_diff_bytes` ist ein Ressourcenlimit, kein
Anzeige-Limit: Bei Überschreitung folgt `subject_too_large` und der Lauf ist
`not_evaluated`. Es gibt keine stille Teilprüfung. Git-Fehler, nicht vorhandene
Commits, fehlender Checkout und nicht UTF-8-dekodierbare Daten blockieren.

**Output:** `RevisionComparison(repository, base_sha, head_sha,
changed_files, diff, diff_bytes)`

---

## G3 — `GateContext` aufbauen

**Typ:** `samuel/core/types.py`
```python
@dataclass
class GateContext:
    issue_number: int
    branch: str
    changed_files: list[str]
    diff: str
    plan_comment: str | None = None
    pr_url: str | None = None
    subject: EvaluationSubject | None = None
    acceptance_evidence: dict | None = None
    acceptance_contract: dict | None = None
    architecture_policy: dict | None = None
```

**Wird befüllt in:**
```python
ctx = GateContext(
    issue_number=N,
    branch=cmd.branch,
    changed_files=changed_files,
    diff=diff,
    plan_comment=accepted_contract,
    subject=subject,
    acceptance_evidence=None,  # erst nach grünem Required-Preflight gesetzt
    acceptance_contract=approved_contract,
    architecture_policy=bound_architecture_policy,
)
```

Alle internen, optionalen und externen Gates erhalten dieselbe Instanz. Der
Handler ergänzt denselben Subject auch in jedes `GateResult` und jedes
Gate-/PR-Evidence-Event. Nach der vollständigen Schleife veröffentlicht der
Handler genau ein `GateEvaluationCompleted` mit der vollständigen Liste der
Gate-Ergebnisse; jeder Listeneintrag
trägt nochmals den Subject, sodass auch ein blockierter Lauf positive,
negative und advisory Resultate eindeutig bindet. Scheitert der Subject-Aufbau
vor der Schleife, folgt stattdessen genau ein `GateEvaluationUnavailable`; es
wird kein Ersatz-Subject konstruiert. Einzelne `GateFailedEvent` dienen Audit
und Diagnose, sind aber weder Healing- noch Evaluation-Trigger.

GateResult-Schema v2 führt `executed`, `passed=true|false|null`,
`required|optional`-Authority, einen stabilen `reason_code` und einen
validierten Status. Nur `executed=false`, `passed=null` und
`status=skipped_precondition` beschreibt ein bewusst nicht ausgeführtes Gate.
Ein Skip ist weder PASS noch FAIL und erzeugt kein eigenes `GateFailedEvent`.

Ist ein qualifiziertes `config/execution.json` aktiviert, persistiert der
Handler nach grünem Preflight zuerst den versionierten Verification Request,
die Dispatchabsicht und einen Resume-Checkpoint. Der Gitea-Adapter führt den
Dispatch-POST genau einmal aus; ein unbekannter Ausgang wird gegen denselben
Request reconciliert und ein leerer Suchtreffer ist kein Abwesenheitsbeweis.
Gate 11 erhält erst dann kriteriumsweise AcceptanceEvidence, wenn Request,
Subject, Run/Attempt, Workflow-/Tool-/Environment-Digests, Issuer,
Nonce, profilgebundene maximale Evidence-Lebensdauer/Freshness und Integrität
passen und der aktive Plan samt Approval,
Base/Head und Policy unmittelbar vor Verwendung erneut bestätigt wurde.

`ProviderVerificationPending` ist nichtterminal und erzeugt weder PR noch
Healing. Ein Trust-/Infrastrukturfehler erzeugt
`ProviderVerificationBlocked`, aber keine `GateEvaluationCompleted`-
Mutationsauthority. Im autorisierten Referenz-Worker kann nur ein regulärer
kriteriumsweiser Gate-11-Fehler den bestehenden gebundenen Healingpfad
erreichen. Der passive `candidate request`-Verbraucher publiziert stattdessen
`ProviderGateEvaluationCompleted` mit `mutation_authority: none`. Provider-
Resume setzt bei derselben Evidence und `CreatePR` fort, nie bei `Implement`.
Das ausgelieferte Profil ist deaktiviert/unqualifiziert; der lokale VerifyAC-
Pfad bleibt bis zur real belegten atomaren Umschaltung aktiv.

---

## G4 — 13 interne Gates

**Registry:** `samuel/slices/pr_gates/gates.py` → `GATE_REGISTRY: dict[int | str, Callable]`

```python
GATE_REGISTRY = {
    1: gate_1_branch_guard,
    2: gate_2_plan_comment,
    3: gate_3_metadata_block,
    5: gate_5_diff_not_empty,
    6: gate_6_self_consistency,
    7: gate_7_scope_guard,
    "7b": gate_7b_contract_scope,
    8: gate_8_slice_gate,
    9: gate_9_python_syntax,
    11: gate_11_ac_verification,
    12: gate_12_ready_to_close,
    "13a": gate_13a_branch_freshness,
    "13b": gate_13b_destructive_diff,
}
```

**Jedes Gate:**
```python
def gate_N_name(ctx: GateContext) -> GateResult:
    # ausgeführt: passed bool; Precondition-Skip: passed None/executed False
    return GateResult(gate=N, passed=..., reason=..., owasp_risk=...)
```

**Ablauf:**
```python
all_gate_ids = set(config.required) | set(config.optional)
active = all_gate_ids - set(config.disabled)

preflight = [gate for gate in sorted(active) if gate in {"7b", 8, 9, "13a", "13b"}]
run(preflight)
if required_preflight_failed:
    append_skipped_precondition_for_all_remaining_gates()
else:
    ctx.acceptance_evidence = send_one_bound_verify_ac()
    run(all_remaining_internal_gates)
    run(all_external_gates)
```

**Sort-Regel:** Ints vor Strings → 1, 2, ..., 12, "13a", "13b".

Optionales Preflight-Evidence wird vorgezogen, blockiert aber weiterhin nicht.
Alle External-Gates bleiben nach der Candidate-Verifikation positioniert und
werden bei einem Required-Preflight-Block als `skipped_precondition` in das
terminale Event aufgenommen.

---

## G5 — External Gates

**Port:** `samuel/core/ports.py` → `IExternalGate`
```python
class IExternalGate(ABC):
    name: str

    @abstractmethod
    def run(self, context: GateContext) -> GateResult: ...
```

**Plugin-Point:** Konstruktor nimmt `external_gates: list[IExternalGate]`
entgegen. Sie werden nach den internen Gates ausgeführt. Bootstrap registriert
`DiffSecretGate` immer; Path-Risk kommt bei vorhandener Konfiguration hinzu,
Symbol-Resolution und Coverage-Diff werden ebenfalls ausgeliefert.

`DiffSecretGate` prüft ausschließlich hinzugefügte Zeilen des vollständigen,
commitgebundenen `GateContext.diff`. Hochpräzise Regeln einschließlich
PEM-Private-Key blockieren mit `gate=diff_secret_scan`; JWT-Form und
AWS-Access-Key-ID passieren advisory und erzeugen `SecretRiskDetected` mit
Regel-ID, Zeile, Correlation-ID und demselben `EvaluationSubject`, aber ohne
Trefferwert. Entfernte Secret-Zeilen dürfen passieren. Scanner und flache
Audit-Redaktion beziehen ihre Signaturen aus derselben Core-Regelquelle.

**Weitere mögliche Adapter:** CVE-Scanner, Lizenz-Checker, externe
Security-Services. Der Pull-only-Gitea-Check-Leser aus #520 ist bewusst nicht
an `IExternalGate` angeschlossen und bleibt unabhängig von diesem Required-
Gatepfad advisory. Weitere Evidence-Formate werden erst bei realem Bedarf
integriert; requestgebundene Required-Evidence bleibt #679.

**Fehler-Handling:** Eine Exception aus `ext.run()` blockiert und erzeugt
`GateFailedEvent` mit `external=True`. Nur die Fehlerklasse, nicht der potenziell
sensitive Exceptiontext, gelangt in Evidence. Auch das externe Ergebnis trägt
den gemeinsamen `EvaluationSubject`.

---

## G6 — `PR` erstellen oder fail-closed beenden

**Wenn `blocked`:**
```python
return {
    "passed": False,
    "results": results,  # alle GateResults
    "blocked_gates": [r for r in results if r.passed is False],
    "evaluation_subject": subject.as_dict(),
}
# Kein PR wird erstellt. GateEvaluationCompleted wurde mit allen Resultaten publiziert.
```

**Wenn alle required + external OK:**
```python
attribution = ai_attribution_fn() if ai_attribution_fn else None
# z.B. Produktversion plus separater Voll-SHA aus samuel.build_info

title = f"feat: Issue #{N}"
body_parts = [f"## Issue #{N}"]
if attribution:
    body_parts.append(f"\n{attribution}")

# Vor der externen Wirkung: Intent plus pr_pending-Checkpoint.
intent = authority.put_intent(
    create_pr,
    subject,
    head=cmd.branch,
    base=cmd.base,
    marker=backend_neutral_body_marker,
)
authority.put_checkpoint(boundary="pr_pending", intent_key=intent.key)

# Recovery: notierte Nummer zuerst, Marker nur im API-/Notierungsfenster.
pr = reconcile_by_persisted_number(intent) or reconcile_by_marker(
    intent.marker,
    head=cmd.branch,
    base=cmd.base,
    revision=subject.head_sha,
)
if pr is None:
    pr = scm.create_pr(
        head=cmd.branch,
        base=cmd.base or "main",
        title=title,
        body="\n".join(body_parts),
    )

pr_revision = scm.get_pr_revision(pr.number)
assert (pr_revision.base_sha, pr_revision.head_sha) == (subject.base_sha, subject.head_sha)
authority.finish_intent(applied, pr.number, pr_revision)

bus.publish(
    PRCreated(
        payload={
            "issue": N,
            "branch": cmd.branch,
            "pr_number": pr.number,
            "pr_url": pr.html_url,
            "ai_attribution": attribution,
            "evaluation_subject": subject.as_dict(),
        }
    )
)
```

`get_pr()` und `find_pr_by_marker()` sind Teil des backendneutralen
`IVersionControl`-Ports und besitzen Gitea-/GitHub-Konformität. Ein Markerfund
ist nur gültig, wenn genau ein PR mit Marker, Head und Base existiert und seine
Revision dem gebundenen Subject entspricht; ein manueller/abweichender oder
mehrdeutiger PR wird nicht adoptiert. Ein Crash nach API-Erfolg, aber vor
Notierung wird so ohne zweiten PR abgeglichen. Nach notierter Nummer ist diese
der Primärschlüssel. `PRCreated` terminalisiert den PR-Erstellungscheckpoint
über einen persistierten Tombstone; ein Crash vor physischer Cleanup wird beim
nächsten Start abgeschlossen. In einem Workflow mit Reviewschritt bleibt der
übergeordnete Auftrag danach bis zum strukturierten Review- oder Mergeausgang
offen.

Der PR-Intent wird vor `create_pr()` persistent geschrieben.
Der gespeicherte Intent enthält zusätzlich den vollständigen EvaluationSubject,
damit ein späterer nativer Human-Merge nach Cleanup des resumable Checkpoints
am ursprünglichen Candidate beobachtet werden kann. Dies ist keine neue
Mergefreigabe; der Consumer liest `merged` und den Head erneut über den SCM-Port.
Nach bestätigtem nativem Merge ergänzt derselbe Consumer einen idempotenten
Abschlusskommentar mit Auftrag, Candidate und gebundenen Kriterien. Die
Labelprojektion setzt nur für den noch aktiven passenden Plan `status:done`
und entfernt temporäre Arbeits-/Reviewlabels. Ein alter Candidate schließt
keinen neuen Plan ab. Das Issue bleibt offen; sein eigener Restumfang und
weitergehende Qualification werden dadurch nicht automatisch erfüllt.

Ausnahme,
ungültige Antwort und Revisionsabweichung enden als
`failed|mismatch|unresolved`; nur die bestätigte PR-Nummer mit exakt passender
Base-/Head-Revision wird `applied`. Der Abgleich ist in #629 diagnostisch und
dispatcht nach einem Neustart nichts. Ein Authority-/Witness-Writefehler vor
der Wirkung verhindert den API-Aufruf; ein Fehler beim Abschluss verhindert
`PRCreated`.

`GatesPassed` und `PRCreated` sind getrennte Zustände. `PRCreated` wird nur
publiziert, wenn der SCM-Adapter eine positive PR-Nummer, eine sicher
auditierbare absolute HTTP(S)-URL und exakt denselben Base-/Head-SHA bestätigt.
Userinfo, Query, Fragment,
Whitespace, Steuerzeichen, ungültiger Port oder fehlender Host/Pfad sind nicht
zulässig. Ein fehlender oder revisionsunfähiger Adapter wurde bereits in G1
als `not_evaluated` blockiert. Wirft `create_pr()` eine Exception oder ist
seine Antwort unvollständig, publiziert der Handler stattdessen `PRCreationFailed`
und liefert:

```python
{
    "passed": False,
    "gates_passed": True,
    "pr_created": False,
    "pr_error": {
        "code": "scm_create_pr_failed | invalid_scm_response",
        "type": "sichere Fehlerklasse",
        "provider": "Adapter-Klassenname oder none",
        "message": "SCM did not confirm creation of a valid pull request",
        "remediation": "Verify SCM configuration and repository connectivity before retrying",
    },
}
```

Ein bereits erstellter PR mit abweichender oder nicht mehr prüfbarer Revision
erzeugt `EvaluationSubjectInvalidated`, aber kein `PRCreated`. Der nachgelagerte
Review muss ein geschlossenes, an Subject, vollständigen Diff, Policy, Tool
und Prompt gebundenes `pass|block|indeterminate` liefern. Vor aktiviertem
Auto-Merge wird die PR-Revision erneut gelesen; eine Verschiebung blockiert
den Merge. Automatische Wirkung verlangt außerdem die default-off Flags
`auto_merge_pr` und `expected_head_merge_qualified`, eine frische menschliche
Planfreigabe und gebundene Required-Gates. Gitea erhält den erwarteten Head als
`head_commit_id`. Der vor dem Call persistierte, reviewgebundene Mergeintent
wird anhand der SCM-Postcondition reconciliert und nie blind wiederholt.
Dashboard und Replay behandeln `PRCreationFailed` als fehlgeschlagenen
Terminalstatus. Provider-Exceptiontexte und rohe Responses werden weder in
Event/Response noch ins Log übernommen, weil sie Credentials oder Header
enthalten können.

---

## Gate-Ausführungsmodell und Status

Die aktive Gate-Policy wird beim Bootstrap aus genau einem Profil geladen und
als Version/Digest in den `EvaluationSubject` aufgenommen. `required` ist
Freigabeautorität, `optional` ist advisory und `disabled` wird nicht
ausgeführt. Es gibt keinen stillen Fallback auf ein anderes Profil.

Der freigegebene Acceptance-Contract und Gate 11 verwenden dieselbe
`[TEST]`-Grammatik: einen sicheren logischen Testnamen oder einen sicheren
Pytest-Node-ID mit mindestens einem `::`-Segment. Ein bloßer Dateipfad ist
kein runnerübergreifend ausführbarer Selektor und blockiert bereits vor
`PlanPosted`; Gate 11 erfindet dafür weder einen Full-Suite- noch einen
anderen Runner-Aufruf (#754).

Vor dieser Candidate-Stufe löst Planning die eine Runner-Authority bereits
auf: explizites Control-Plane-`test_cmd` vor Marker-Autodetection. Der
gemeinsame Core-Resolver prüft Binary beziehungsweise Python-Modul und die
bekannte Selektorgrammar, führt aber noch keinen Test aus. Ein Unittest-Runner
akzeptiert nur gepunktete Python-Namen; eine Pytest-Node-ID ist ausschließlich
mit einem Pytest-Runner kompatibel. Fehlende oder inkompatible Readiness
blockiert nach dem einzigen Planning-Retry vor `PlanPosted`; Doctor nutzt
dieselbe Auflösung. Es gibt kein Umschreiben, Installieren oder Fallback
(#756).

Die optionale Python/Pytest-Toolchain (#978) erweitert dieselbe
Control-Plane-Runnerpolicy um Manifestpfad und SHA-256; sie erzeugt keinen
zweiten Verifier. Doctor/Planning validieren die registrierten Paket-/Lockbytes,
Python-/Plattform-/Releaseidentität und eine sterile Versionprobe außerhalb des
Candidates. TEST validiert diese Bindung erneut und startet den bisherigen
Prozesspfad mit isoliertem Interpreter und read-only Paketen. Der Digest
ergänzt den bestehenden Gate-Policy-Digest; alte Evidence passt bei Wechsel
nicht zum neuen Subject. Gate 11 konsumiert weiterhin die eine gebundene
Acceptance-Evidence; kein Zusatztestlauf und keine Candidate-Installation.

Die Preflight-Reihenfolge ist fest `7b → 8 → 9 → 13a → 13b`. Diese Gates
verwenden Diff, SCM-Blobs und Policy, starten aber keinen Candidate-Prozess.
Alle aktiven Preflights werden ausgewertet. Sobald danach mindestens ein
**required** Preflight fehlgeschlagen ist, werden alle übrigen internen Gates
und alle externen Gates als `executed=false`, `passed=null`,
`status=skipped_precondition` protokolliert. Ein optionaler Preflight-Fehler
allein stoppt die weitere Auswertung nicht.

| Status | Bedeutung | Freigabewirkung |
|---|---|---|
| `passed` | ausgeführt und positiv | required erfüllt; optional nur Beobachtung |
| `failed` | ausgeführt und fachlich negativ | required blockiert, optional nicht |
| `error` | Verifier/Schema/Tool konnte kein fachliches Ergebnis liefern | required blockiert; wird nie als Erfolg umgedeutet |
| `missing_evidence` | erforderliche, gebundene Evidence fehlt oder gehört zu anderem Subject | required blockiert |
| `not_applicable` | ausgeführt, aber für diesen Candidate nicht anwendbar; trägt `passed=true` | erfüllt das Gate, ohne weitergehende Prüftiefe zu behaupten |
| `manual_pending` | menschliche, subjectgebundene Evidence fehlt | required wartet fail-closed; weder Gate-Failure noch terminaler Workflowfehler |
| `not_evaluated` | Voraussetzungen für eine belastbare Prüfung fehlen | required blockiert |
| `skipped_precondition` | nicht ausgeführt, weil ein required Preflight bereits blockierte | niemals positive Evidence; ein required Eintrag bleibt Teil des blockierten Gesamtergebnisses |

Ein ausschließlich durch erforderliche MANUAL-Kriterien blockierter Candidate
behält seinen gebundenen Finalisierungscheckpoint. Weder `GateFailedEvent`
noch `WorkflowBlocked` oder `status:failed` entstehen allein aus diesem
Wartezustand. `samuel watch` liest den späteren menschlichen SCM-Kommentar
und stößt bei exakter AC-/Contract-/Head-/Actor-/Zeitbindung die Reevaluation
für dasselbe Subject an; Bootstrap-Resume startet dafür keine neue
Implementation. Ein echter zusätzlicher Gatefehler bleibt dagegen Failure.
Am MANUAL-Haltepunkt kommentiert der bestehende PR-Gate-Handler die offenen
Kriterien mit jeweils kopierbarem `/samuel accept <AC-ID> --contract <hash>
--head <sha>`. Wiederholte Prüfung desselben Subjects dupliziert den Hinweis
nicht. Planfreigabe, `ok` und `/approve` ersetzen diesen Receipt nicht.
Wenn dieser Wiedereintritt in einen
budgetgeschützten Review führt, rekonstruiert der PR-Gate-Handler die bereits
persistierte Admission ausschließlich über Repository, Issue, aktiven
Planvertrag und Plan-Kommentar. Er erzeugt keine neue Admission und blockiert
eine fehlende oder mitgegebene fremde Authority vor PR- und Providerwirkung.
Subject-, Head-, Contract- und Receipt-Prüfungen bleiben davon unberührt.

Die ursprüngliche menschliche Planfreigabe liegt getrennt davon als
create-only `plan_approval.v1` im bestehenden Authority-State. Sie bindet
Repository, Issue, Plan-Kommentar, Contract, Actor, Methode, Source-ID,
Zeitpunkt, Transport und den vorhandenen Source Snapshot. Gate 11 und der
Reviewpfad rekonstruieren denselben Record nach MANUAL-Wartezustand oder
Restart und revalidieren das historische Timeline-Ereignis beziehungsweise
den signierten Webhook-Receipt. Bei nativen Gitea-Labelwebhooks bindet der
Receipt das eindeutig mit dem signierten Trigger korrelierte Timeline-ADD und
die Delivery-ID; Timeline-Evidence ändert den Transport nicht zu Polling. Das
aktuelle `status:approved`-Label ist dabei
keine Existenzbedingung. Ein Labelwechsel auf `status:failed` widerruft keine
Authority; explizites Replan, Subject-/Contract-/Source-Supersession sowie
fehlende oder fremde Records blockieren weiterhin fail-closed. Ohne passenden
Authority-Store werden Label und Kommentar nicht als alternative Authority
verwendet. Sehen signierter Webhook und authentifiziertes Polling dieselbe
Labelentscheidung, bleibt der zuerst materialisierte Receipt kanonisch; nur
dieselbe Actor-/Zeit-/Plan-/Contractbindung ist idempotent replayfähig.

Genau ein `GateEvaluationCompleted` bündelt alle GateResult-Einträge für das
Subject. Scheitert schon der Subject-Aufbau, entsteht stattdessen
`GateEvaluationUnavailable`; erfundene Ersatz-SHAs oder Teilresults sind
unzulässig. `GateFailedEvent` ist Detaildiagnose, aber nicht allein der
terminale Gesamtvertrag.

---

## Gates im Detail

Die Beispiele zeigen die konkrete Implementierung, nicht allgemeine
Sicherheitsversprechen. Für jedes interne Gate gilt: Es ist nur dann
blockierend, wenn das aktive Profil es als `required` führt.

| ID/Name | Pipelineposition, Input und Risiko | Pass / N/A | Fail/Error/Missing | Positives / negatives Beispiel; Evidence |
|---|---|---|---|---|
| `1 BranchGuard` | nach Preflight; Zielbranch aus Command; verhindert Main→Main | Branch `samuel/issue-42` | `main`, `master` oder leer | `samuel/issue-42` → pass; `main` → fail. `GateResult`, bei required zusätzlich `GateFailedEvent`. |
| `2 PlanComment` | nach Preflight; letzter Plan-Kommentar; Traceability | Kommentar vorhanden und länger als 20 Zeichen | fehlt/zu kurz | strukturierter `## Plan` → pass; kein Plan → fail. |
| `3 MetadataBlock` | nach Preflight; Plantext; Attribution/Trace | enthält `Agent-Metadaten` | Marker fehlt | generierter Plan-Kommentar → pass; Kurzplan ohne Block → fail. |
| `5 DiffNotEmpty` | nach Preflight; vollständiger Base/Head-Diff | nicht leer | leer | Codeänderung → pass; identische Commits → fail. Default/Self optional, Audit required. |
| `6 SelfConsistency` | nach Preflight; Plan-Dateireferenzen vs. `changed_files`; grobe Drift-Heuristik | keine auswertbaren Referenzen oder mindestens die Hälfte der Plan-Basenamen im Diff | mehr als die Hälfte fehlt | 2/3 Plan-Dateien geändert → pass; 0/3 → fail. Basename-Vergleich, kein Scopebeweis. |
| `7 ForbiddenPathGuard` | nach Preflight; Changed-Files; Minimalfallback für sensible Pfade | kein Fallbacktreffer; bei aktivem `path_risk` delegiert es und passt | Fallbackmuster wie `.env`/Secrets bei fehlendem PathRisk | `src/app.py` → pass; `.env` → fail. Fachlicher Contract-Scope ist ausschließlich 7b. |
| `7b ContractScope` | **Preflight**; Contract Schema v2, Subject, Changed-Files, Architecture-Policy; verhindert Scope-Ausbruch | jeder Pfad explizit erlaubt oder zulässig expandiert | fremder Contract-Hash/fehlender Scope → `missing_evidence`; ungültige Policy/Pfade → `not_evaluated`; Out-of-Scope → `failed` | `[FILE] game/board.py` und nur diese Änderung → pass; zusätzlich `infra/prod.tf` → fail + `OutOfScopeDiff`. Tool-Evidence enthält Subject, Diffdigest und Pfade. |
| `8 SliceGate` | **Preflight**; hinzugefügte Diffzeilen in `samuel/slices/*`; verhindert konkret Cross-Slice-Python-Imports | kein erkanntes Cross-Slice-Muster | `from samuel.slices.B ...` in Slice A | Same-Slice-Import → pass; echter A→B-Import → fail. Kommentare/Strings sowie globale Tests/Adapter sind nicht erfasst. |
| `9 PythonSyntax` | **Preflight**; geänderte `.py`-Blobs am exakten Head via SCM und `ast.parse` | Syntax korrekt; keine Python-Datei oder nur bestätigte Löschungen → `not_applicable` | Syntaxfehler, unerwartet fehlender/zu großer/nicht lesbarer Blob | valide `board.py` → pass; fehlende Klammer → fail. Tool nennt CPython/Version; kein Lint/Type/Test. |
| `11 ACVerification` | nach positivem required Preflight; gebundene Acceptance-Evidence des detached Candidate | alle required Kriterien `passed`, Freigabe/Contract/Subject stimmen | jeder andere AC-Status, fehlende/mehrdeutige/veraltete Evidence oder Receipt | ein grüner TEST plus DIFF → pass; `manual_pending` → fail-closed warten; Test-Exit 1 → fail. Kriteriumsdetails siehe nächste Tabelle. |
| `12 AcceptanceReadiness` | nach Preflight; dieselbe Evidence, keine neue Ausführung | nichtleere Resultliste vollständig `passed` | leer/fehlend → `missing_evidence`; offene Status → `manual_pending` oder `missing_evidence` | alle zwei Kriterien grün → pass; ein MANUAL offen → nicht bereit. Default/Self optional, Audit required. |
| `13a BranchFreshness` | **Preflight**; `git rev-list head..base`; Drift-Risiko | höchstens 50 Commits hinter Base | >50 oder nicht prüfbar | 3 Commits hinter Base → pass; 51 → fail. Default/Self optional, Audit required. |
| `13b DestructiveDiff` | **Preflight**; Added/Deleted-Zeilen im vollständigen Diff | nicht gleichzeitig >50 Löschungen und >3× Adds | Schwelle überschritten | 20 Deletes/10 Adds → pass; 90/10 → fail. Mengenheuristik, keine fachliche Löschungsfreigabe. |

### Gate 1 — Branch-Guard
- Fail: Branch ist `main`/`master`/leer → OWASP `A05:2021`
- Grund: Verhindert PR von Main auf Main

### Gate 2 — Plan-Comment vorhanden
- Fail: Kein `ctx.plan_comment` oder <20 chars
- Grund: Ohne Plan kein Trace der LLM-Absicht

### Gate 3 — Agent-Metadaten-Block
- Fail: "Agent-Metadaten" nicht im Plan-Comment
- Grund: v1-Feature für Reproduzierbarkeit (model, tokens, correlation)

### Gate 5 — Diff nicht leer
- Fail: `ctx.diff` leer
- Grund: Leerer Diff = nichts zu mergen

### Gate 6 — Plan-Diff-Konsistenz
- Fail: >50% der im Plan referenzierten Dateien nicht im Diff
- Grund: LLM hat was anderes gemacht als im Plan stand

### Gate 7 — ForbiddenPathGuard
- Fail: Geänderte Datei enthält `.env`, `secrets`, `credentials` → OWASP `A01:2021`
- Bei verdrahtetem `PathRiskGate` delegiert Gate 7 vollständig. Dieses Gate
  bleibt ein Sicherheits-Pfadfallback und ist nicht der fachliche Scope.

### Gate 7b — ContractScope
- Prüft jeden kanonischen Pfad aus den vollständigen `changed_files` gegen die
  freigegebenen FILE-/PATH-Einträge des Acceptance Contract Schema v2.
- Ohne Scope, bei Contract-/Head-/Policy-Abweichung, leeren oder mehrdeutigen
  Pfaden entsteht `missing_evidence`/`not_evaluated`, niemals Erfolg.
- `Architecture-Expansion: allowed` kann zusätzliche Pfade nur über
  `config/architecture.json::expansion_policy` erlauben; `blocked_scopes`
  gewinnen. Fehlende/ungültige Policy oder eine rollenlose Auflösung ist
  `not_evaluated`. Bei `disabled` gelten ausschließlich die expliziten Einträge.
- GateResult und `OutOfScopeDiff` tragen Repository, Base, Head, Contract-Hash,
  Policy-Version/-Digest, Changed-Files, Diff-Größe/-Digest und die abgelehnten
  Pfade.
- Renames werden durch `git diff --no-renames` als alter und neuer Pfad geprüft.

### Gate 8 — Slice-Gate (Cross-Slice-Import)
- Fail: Neuer Import `from samuel.slices.A` in Datei von Slice `B` → OWASP `A05:2021`
- Grund: v2-Architektur-Regel

### Gate 9 — Python-Syntax
- Liest vorhandene geänderte `.py`-Blobs über den SCM-Port aus dem exakten
  `EvaluationSubject.head_sha` und prüft sie mit CPython `ast.parse`.
- Fail: Syntaxfehler, unerwartet fehlender/nicht lesbarer Blob, fehlender
  immutable Dateizugriff oder Überschreitung von `max_quality_file_bytes`.
- `not_applicable`: nur Nicht-Python-Dateien oder bestätigte Löschungen.
- Keine Behauptung von Lint, Typecheck, Test- oder Remote-CI-Evidence.

### Gate 11 — AC-Verifikation
- Der CreatePR-Handler führt den vorhandenen `ACVerificationHandler` genau
  einmal nach bestandenem Required-Preflight im detached Verifikationsprofil
  des gemeinsamen `IWorkspaceManager` für den exakten Candidate-Head aus. Bei
  Preflight-Block bleibt Gate 11 `skipped_precondition`; Run- und
  Verifikationsprofil teilen Registry, Lock-, Kapazitäts- und Prune-Vertrag;
  Gate 11 konsumiert und validiert dessen strukturierte
  Evidence; es startet keine zweite Ausführung. `DIFF` verwendet die
  unveränderliche Base-/Head-Comparison.
- TEST-Befehl, Timeout und Runner-Policy-Version stammen aus demselben beim
  Bootstrap gebundenen Control-Plane-`config/eval.json` wie der im
  `EvaluationSubject.policy_digest` enthaltene Runner-Policy-Snapshot.
  Candidate-Projektmarker wählen nur feste Templates; der Worktree ist keine
  Prozesssandbox.
- IMPORT- und TEST-Kindprozesse erhalten ausschließlich die versionierte
  Core-Allowlist `verifier-sterile.v1` mit neu erzeugtem HOME/TMP/XDG und
  festem Toolpfad. Parent-Secrets, Git-Pfad-/Askpasswerte, `PYTHONPATH` und
  Shellprofile werden nicht vererbt. Die Profilversion steht in der
  kriteriumsweisen Evidence und im Subject-Policy-Digest. Gleiche
  Benutzerrechte, Hostdateien, Prozesssicht, Netzwerk und Ressourcen bleiben
  ohne Sandboxgrenze.
- Besteht nur, wenn Freigabe, aktive Plan-Kommentar-ID, Contract-Hash und vollständiger
  `EvaluationSubject` übereinstimmen und jedes Required-Kriterium `passed` ist.
- Automatische `passed`-/`failed`-Resultate tragen Verifier-Evidence Schema 1:
  taggebundene Pfad-, Pattern-, Import- oder Testfakten. TEST-Output ist auf
  500 Zeichen begrenzt und gegen bekannte Secret-Muster redigiert.
- `failed`, `manual_pending`, `not_applicable`, `missing_evidence`, `error`
  sowie unbekannte oder mehrdeutige Resultate blockieren fail-closed.
- MANUAL benötigt einen menschlichen SCM-Kommentar, der Kriteriums-ID,
  Contract-Hash und Head-SHA exakt bindet. Checkboxen werden ignoriert.

### Gate 12 — AcceptanceReadiness
- Fasst die kriteriumsweisen Statuswerte derselben `AcceptanceEvidence` als
  Vollständigkeit zusammen; es verifiziert nicht erneut.
- Fehlende/leere Evidence und jeder nicht bestandene Status sind nicht
  abschlussbereit. Der Issue-Status und Checkboxen werden nicht ausgewertet.

### Gate 13a — Branch-Freshness
- Fail: geprüfter Head >50 Commits hinter der geprüften Base oder exakte
  Revisionen sind nicht prüfbar → OWASP `A05:2021`
- Grund: Veralteter Branch verursacht Merge-Konflikte

### Gate 13b — Destruktiver Diff
- Fail: `deleted_lines > added_lines * 3` UND `deleted_lines > 50` → OWASP `A05:2021`
- Grund: Massiv mehr Löschungen als Hinzufügungen = verdächtig

---

## Acceptance-Tags im Detail

Planning behandelt Zielzustands-Tags (`IMPORT`, `GREP`, `GREP:NOT`, `TEST`,
`MANUAL`) im Dry-Run als deferred. Für TEST ist dabei nur die oben
beschriebene Runner-/Selektor-Readiness verpflichtend; sie erzeugt noch keine
Test-Evidence. Die autoritative Ausführung findet nach
positivem Required-Preflight im detached Worktree des exakten
`subject.head_sha` statt. `DIFF` verwendet dagegen die immutable
Base-/Head-Changed-Files. Alle Contract-Kriterien sind required; ein leerer
oder partieller Contract kann Gate 11 nicht bestehen.

Bei den pfadartigen Tags `DIFF` und `EXISTS` sowie beim Modul-Tag `IMPORT`
darf der einzelne Argumenttoken als Markdown-Inline-Code geschrieben sein.
Dasselbe gilt für das vollständige Suchmuster von `GREP` und `GREP:NOT`.
Der Contract-Hash bindet weiterhin den exakten Plantext einschließlich der
Backticks; ausschließlich der Verifier entfernt genau diese eine
Darstellungshülle, bevor die unveränderte Pfad-, Traversal-, Modul- oder
Suchvalidierung läuft.

| Tag | Exakte Prüfung und Scope | Pass / Fail / fehlende Evidence | Positives / negatives Beispiel; Event/Evidence |
|---|---|---|---|
| `[DIFF] path` | kanonischer Pfad ist in den commitgebundenen `changed_files` | enthalten → pass; nicht enthalten → failed; unsicherer Pfad → error | `[DIFF] game/board.py` mit Änderung → `ACVerified`; ohne Änderung → `ACFailed`. Evidence: `path`, `changed`. |
| `[EXISTS] path` | Pfad existiert im detached Candidate | vorhanden → pass; fehlt → failed; Traversal/ungültiger Pfad → error | neue `README.md` vorhanden/fehlend. Evidence: `path`, `exists`. Es beweist keinen Dateiinhalt. |
| `[IMPORT] module.name` | frischer Python-Prozess im Candidate-Root unter `verifier-sterile.v1` importiert das Modul | Exit 0 → pass; Importfehler → failed; unzulässiger Modulname, Timeout oder Prozessfehler → error | `game.domain.board` importierbar/nicht importierbar; `os`, `sys` und weitere riskante Module sind als Kriterium gesperrt. Evidence: Modul, Exitcode, Umgebungsprofil. |
| `[GREP] pattern` | literale Teilzeichenfolge über alle iterierten Code- und Config-Dateien | erster Fund → pass; kein Fund → failed | `[GREP] "-entry.score"` findet das Pattern irgendwo im Repository. **Kein Pfadargument.** Ein scheinbarer Suffix wird vom Contract-Parser blockiert (#713). Evidence nennt den ersten `matched_file`. |
| `[GREP:NOT] pattern` | dieselbe repositoryweite Suche, Ergebnis invertiert | nirgends gefunden → pass; irgendein Fund → failed | `[GREP:NOT] 'token = "legacy"'` passt nur bei vollständiger Abwesenheit im Repository. Nicht verwenden, wenn nur eine Datei gemeint ist; dafür einen fokussierten TEST schreiben. |
| `[TEST] test-id` | Runner-Policy aus Control-Plane-`eval.json`; sonst feste Marker-Templates für pytest/Jest/Go/Cargo/Maven; Planning prüft davor Installation und Selektorkompatibilität ohne Ausführung; Timeout standardmäßig 60 s | Readinessfehler blockiert vor `PlanPosted`; bei Candidate-Ausführung: Exit 0 → pass, anderer Exitcode → failed, Timeout/OS-Fehler → error | Pytest: `tests/test_board.py::TestLeaderboard::test_highest_score_first`; Unittest: `tests.test_board.TestLeaderboard.test_highest_score_first`. `TestRunCompleted` plus AC-Event; Evidence enthält Runner, Exitcode, Dauer, redigierten 500-Zeichen-Auszug und Policy-/Umgebungsprofil. |
| `[MANUAL] Beschreibung` | authentifiziertes SCM-Receipt bindet Kriteriums-ID, Contract-Hash, Head-SHA, Actor und Source-ID | gültiges Receipt → pass; sonst `manual_pending` | „Dashboard visuell prüfen“ bleibt offen, bis genau dieser Candidate bestätigt wurde. Checkbox `[x]` allein hat keine Wirkung. `ACManualPending` oder `ACVerified`. |

Die repositoryweite GREP-Familie nutzt die interne Python-Dateiiteration, nicht
das Shellprogramm `grep`; Shell-/Toolrechte entstehen daraus nicht. Skeleton,
TOC, Context-Grep und Acceptance-GREP sind unterschiedliche Funktionen:
Skeleton/TOC bereiten LLM-Kontext vor, während AC-GREP nur einen literalen
post-implementation Fakt für Gate 11 liefert.

Der äußere Pattern-Delimiter darf doppelt, einfach oder genau eine vollständige
Markdown-Inline-Code-Hülle sein. Ein Pattern mit doppelten Anführungszeichen
wird außen einfach gequotet oder als Inline-Code geschrieben und umgekehrt;
Backslash-Escapes für den äußeren Quote-Delimiter sind nicht unterstützt. Eine
unvollständige oder von einem scheinbaren Pfadsuffix gefolgte Hülle wird
abgelehnt. Enthält ein Pattern keine eindeutig darstellbare Hülle, wird
stattdessen ein fokussiertes `[TEST]`-Kriterium verwendet.

---

## External Gates im Detail

Der Bootstrap verdrahtet vier Referenzadapter. Der Handler markiert ihre
GateResults als `authority=required`; Adapter mit warn-only Semantik liefern
bei einem Finding bewusst `passed=true`. Eine Adapterexception wird redigiert
als `status=error` behandelt und blockiert. Es gibt keinen versteckten
Fallback auf einen anderen Provider.

| Name | Aktivierung und tatsächliche Wirkung | Positives / negatives Beispiel; Grenzen |
|---|---|---|
| `diff_secret_scan` | immer verdrahtet; scannt nur hinzugefügte Zeilen des vollständigen Candidate-Diffs. Hochpräzise Regeln blockieren, JWT-/AWS-ID-Formsignale warnen mit `passed=true`. | normale Codezeile → pass; hinzugefügter PEM Private Key → fail; JWT-Form → pass plus `SecretRiskDetected`. Kein allgemeiner Scanner. |
| `path_risk` | nur wenn `config/path_risk.json` Klassen liefert. `level=block` blockiert; `level=warn` liefert pass mit Risikohinweis. Bei Aktivierung delegiert Gate 7 seinen Fallback. | `src/app.py` → pass; `.env` → fail; `.gitea/workflows/ci.yml` → warn/pass. Pfadklassifikation, keine Inhaltsprüfung. |
| `symbol_resolution` | immer verdrahteter Python-fokussierter Warnadapter; prüft neue Top-Level-Imports gegen Diff, Generatorpfade, Lockfiles, Stdlib und First-Party. | auflösbarer Import → pass; unbekannter Import → pass plus `UnresolvedSymbol`. Kein allgemeiner Sprach-/Dependency-Graph. |
| `coverage_diff` | immer verdrahtet; liest optional `coverage.xml`. Fehlt/unlesbar: pass/No-op. Unabgedeckte geänderte Python-Dateien: warn/pass. | vorhandener Treffer → pass; fehlender Treffer → warn/pass. Keine Coverage-Freigabeautorität. |

---

## Config: `config/gates.json`

```json
{
  "policy_version": "2026-08-29.preflight.v3",
  "required": [1, 2, 3, 7, "7b", 8, 9, 11, "13b"],
  "optional": [5, 6, 12, "13a"],
  "disabled": [],
  "custom": [],
  "parameters": {
    "max_diff_bytes": 2000000,
    "max_quality_file_bytes": 1000000
  }
}
```

**Semantik:**
- `required`: muss passen, sonst Block
- `optional`: wird ausgeführt, fail wird geloggt aber blockiert nicht
- `disabled`: wird gar nicht ausgeführt
- `policy_version`: menschlich versionierter Policy-Vertrag
- `parameters.max_diff_bytes`: harte Ressourcenobergrenze; Überschreitung
  blockiert vor der Gate-Ausführung
- `parameters.max_quality_file_bytes`: harte Grenze je Candidate-Datei für
  Gate 9; Überschreitung blockiert fail-closed

`config/gates.self.json` ist das eigene Self-Profil mit derselben
Autoritätsgrenze. `config/gates.audit.json` macht alle 13 registrierten Gates
required. Die früheren Gates 4/10 und `config/gates.legacy.json` sind entfernt.
Explizit ausgewählte fehlende oder ungültige Profile brechen den Start ab und
fallen nicht auf das Default-Profil zurück. Vor dem Runtime-Wiring erlaubt ein
Nicht-Self-Workflow nur `default`/`audit`; Self erzwingt unabhängig vom
Environment sein eigenes Profil. Doppelte, unbekannte oder pensionierte IDs
sowie Überschneidungen zwischen den Mengen werden fail-closed abgelehnt.

**Laden:** `samuel.core.config.load_gates_config()` — Pydantic-validiert via `GatesConfigSchema`.

---

## Durchsetzungsgrenze

Die Subject-Bindung belegt, was der lokale Gate-Lauf und der optionale
Auto-Merge geprüft haben. Ein nach dem Lauf verschobener PR-Head macht die alte
Evidence kraft ihrer abweichenden `head_sha` unanwendbar. Die davon getrennte
serverseitige Merge-Durchsetzung ist für das auditierte Gitea-Repository über
#441/#528 nachgewiesen: keine direkten/Force-Pushes oder Branch-Löschung,
exakter Required Check für den aktuellen Head und kein Admin-Override. Dieser
externe Betriebszustand muss je Installation mit `samuel doctor` erneut belegt
werden. Der Doctor vergleicht dafür genau den effektiven
`SCM_REQUIRED_STATUS_CONTEXT` mit der nativen Regel und zeigt an, ob der Wert
explizit konfiguriert ist oder aus dem ausgelieferten Default stammt. Leere
Werte, Listen, Wildcards und das Ableiten des Sollwerts aus der beobachteten
Regel sind ausgeschlossen. Provider und effektiver Kontext sind Bestandteil
des Gate-Policy-Digests; eine Änderung entzieht älterer Gate-Evidence und
Resume-Checkpoints die Anwendbarkeit. Die Review-/Mergepolicy aus #468 ist
repositoryseitig implementiert; ihr isolierter realer Expected-Head-/Race-
Nachweis bleibt vor Aktivierung und Issueabschluss erforderlich. Die
Implementierung aus #694 benötigt vor Abschluss weiterhin den realen
positiven und negativen Doctor-Nachweis am unabhängigen Zielrepository.

*Dokument erstellt: 2026-04-17. Zuletzt gegen den Code geprüft: 2026-09-19 im
Implementierungsscope von #468.*
