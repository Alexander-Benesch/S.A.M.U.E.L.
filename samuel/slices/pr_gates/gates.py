from __future__ import annotations

import hashlib
from typing import Any, cast

from samuel.core.acceptance import AcceptanceContract, AcceptanceScopeEntry
from samuel.core.gate_metadata import GateStatus
from samuel.core.path_risk import DEFAULT_SECRET_PATH_PATTERNS, path_matches_pattern
from samuel.core.types import GateContext, GateResult


def gate_1_branch_guard(ctx: GateContext) -> GateResult:
    blocked = ctx.branch in ("main", "master", "")
    return GateResult(
        gate=1,
        passed=not blocked,
        reason="Branch ist main/master" if blocked else "Branch OK",
        owasp_risk="A05:2021" if blocked else None,
    )


def gate_2_plan_comment(ctx: GateContext) -> GateResult:
    has_plan = ctx.plan_comment is not None and len(ctx.plan_comment) > 20
    return GateResult(
        gate=2,
        passed=has_plan,
        reason="Plan-Kommentar vorhanden" if has_plan else "Kein Plan-Kommentar gefunden",
    )


def gate_3_metadata_block(ctx: GateContext) -> GateResult:
    has_meta = ctx.plan_comment is not None and "Agent-Metadaten" in ctx.plan_comment
    return GateResult(
        gate=3,
        passed=has_meta,
        reason="Metadaten-Block vorhanden" if has_meta else "Metadaten-Block fehlt im Plan",
    )


def gate_5_diff_not_empty(ctx: GateContext) -> GateResult:
    has_diff = bool(ctx.diff and ctx.diff.strip())
    return GateResult(
        gate=5,
        passed=has_diff,
        reason="Diff vorhanden" if has_diff else "Diff ist leer",
    )


def gate_6_self_consistency(ctx: GateContext) -> GateResult:
    if not ctx.plan_comment or not ctx.changed_files:
        return GateResult(gate=6, passed=True, reason="Keine Daten für Konsistenz-Check")
    import re

    plan_files = set(re.findall(r"[\w/]+\.(?:py|ts|js|go|sql|json|yaml|yml)\b", ctx.plan_comment))
    if not plan_files:
        return GateResult(gate=6, passed=True, reason="Keine Datei-Referenzen im Plan")
    changed_set = {f.split("/")[-1] for f in ctx.changed_files}
    plan_basenames = {f.split("/")[-1] for f in plan_files}
    missing = plan_basenames - changed_set
    if missing and len(missing) > len(plan_basenames) / 2:
        return GateResult(
            gate=6,
            passed=False,
            reason=f"Plan referenziert Dateien die nicht im Diff sind: {', '.join(sorted(missing)[:5])}",
        )
    return GateResult(
        gate=6,
        passed=True,
        reason=f"Plan-Diff Konsistenz: {len(plan_basenames - missing)}/{len(plan_basenames)} Dateien",
    )


def gate_7_scope_guard(ctx: GateContext) -> GateResult:
    """Forbidden-path fallback; this is not the approved contract scope."""
    if not ctx.changed_files:
        return GateResult(gate=7, passed=False, reason="Keine geänderten Dateien")
    if ctx.path_risk_configured:
        return GateResult(
            gate=7,
            passed=True,
            reason="Konfigurierbarer Path-Risk-Gate ist fuer Pfad-Schutz massgeblich",
        )
    violations = [
        path
        for path in ctx.changed_files
        if any(path_matches_pattern(path, pattern) for pattern in DEFAULT_SECRET_PATH_PATTERNS)
    ]
    if violations:
        return GateResult(
            gate=7,
            passed=False,
            reason=f"Scope-Verstoß: {', '.join(violations[:3])}",
            owasp_risk="A01:2021",
        )
    return GateResult(gate=7, passed=True, reason="Keine verbotenen Fallback-Pfade")


def _architecture_scope_entries(values: Any) -> tuple[AcceptanceScopeEntry, ...]:
    if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
        raise ValueError("architecture scope list is invalid")
    entries = tuple(
        AcceptanceScopeEntry(
            kind="path" if item.endswith("/") else "file",
            value=item,
        )
        for item in values
    )
    if len(entries) != len(set(entries)):
        raise ValueError("architecture scope entries must be unique")
    return entries


def _entry_intersects_module(entry: AcceptanceScopeEntry, module_path: str) -> bool:
    module = AcceptanceScopeEntry(
        kind="path" if module_path.endswith("/") else "file",
        value=module_path,
    )
    return entry.matches(module.value.rstrip("/")) or module.matches(entry.value.rstrip("/"))


def gate_7b_contract_scope(ctx: GateContext) -> GateResult:
    """Enforce the approved, versioned scope for the immutable candidate.

    Explicit contract entries are authoritative.  ``architecture.json`` can
    add paths only when the contract explicitly enables expansion; its blocked
    scopes then take precedence over its allowed scopes.  The architecture
    policy therefore augments, but never duplicates, the contract language.
    """

    if ctx.subject is None:
        return GateResult(
            gate="7b",
            passed=False,
            status="not_evaluated",
            reason="Contract-Scope hat keinen EvaluationSubject",
        )
    if not isinstance(ctx.acceptance_contract, dict):
        return GateResult(
            gate="7b",
            passed=False,
            status="missing_evidence",
            reason="Acceptance Contract für Scope-Prüfung fehlt",
        )
    try:
        contract = AcceptanceContract.from_dict(ctx.acceptance_contract)
    except (TypeError, ValueError):
        return GateResult(
            gate="7b",
            passed=False,
            status="not_evaluated",
            reason="Acceptance Contract ist nicht schema-valide",
        )
    if contract.contract_hash != ctx.subject.contract_hash:
        return GateResult(
            gate="7b",
            passed=False,
            status="missing_evidence",
            reason="Contract-Scope gehört zu einem anderen Contract-Hash",
        )
    if contract.schema_version != 2 or contract.scope is None:
        return GateResult(
            gate="7b",
            passed=False,
            status="missing_evidence",
            reason="Acceptance Contract enthält keinen Scope nach Schema v1",
        )
    if not ctx.changed_files:
        return GateResult(
            gate="7b",
            passed=False,
            status="not_evaluated",
            reason="Contract-Scope kann ohne Changed-Files nicht ausgewertet werden",
        )

    try:
        changed = tuple(
            AcceptanceScopeEntry(kind="file", value=path).value for path in ctx.changed_files
        )
    except ValueError:
        return GateResult(
            gate="7b",
            passed=False,
            status="not_evaluated",
            reason="Changed-Files enthalten einen nicht kanonischen Pfad",
        )
    if len(changed) != len(set(changed)):
        return GateResult(
            gate="7b",
            passed=False,
            status="not_evaluated",
            reason="Changed-Files sind mehrdeutig",
        )

    scope = contract.scope
    expanded_allowed: tuple[AcceptanceScopeEntry, ...] = ()
    expanded_blocked: tuple[AcceptanceScopeEntry, ...] = ()
    roles: set[str] = set()
    if scope.architecture_expansion == "allowed":
        architecture = ctx.architecture_policy
        if not isinstance(architecture, dict):
            return GateResult(
                gate="7b",
                passed=False,
                status="not_evaluated",
                reason="Architecture-Expansion ist erlaubt, aber architecture.json fehlt",
            )
        modules = architecture.get("modules")
        expansion_policy = architecture.get("expansion_policy")
        if not isinstance(modules, list) or not isinstance(expansion_policy, dict):
            return GateResult(
                gate="7b",
                passed=False,
                status="not_evaluated",
                reason="architecture.json besitzt keine auswertbare Expansion-Policy",
            )
        try:
            for module in modules:
                if not isinstance(module, dict):
                    raise ValueError("architecture module is invalid")
                module_path = module.get("path")
                role = module.get("role")
                if not isinstance(module_path, str) or not isinstance(role, str) or not role:
                    raise ValueError("architecture module identity is invalid")
                if any(_entry_intersects_module(entry, module_path) for entry in scope.entries):
                    roles.add(role)
            if not roles:
                raise ValueError("contract scope does not resolve to an architecture role")
            allowed: list[AcceptanceScopeEntry] = []
            blocked: list[AcceptanceScopeEntry] = []
            for role in sorted(roles):
                policy = expansion_policy.get(role)
                if not isinstance(policy, dict):
                    raise ValueError("architecture role has no expansion policy")
                allowed.extend(_architecture_scope_entries(policy.get("allowed_scopes")))
                blocked.extend(_architecture_scope_entries(policy.get("blocked_scopes")))
            expanded_allowed = tuple(dict.fromkeys(allowed))
            expanded_blocked = tuple(dict.fromkeys(blocked))
        except (TypeError, ValueError):
            return GateResult(
                gate="7b",
                passed=False,
                status="not_evaluated",
                reason="architecture.json enthält widersprüchliche oder ungültige Scope-Regeln",
            )

    out_of_scope: list[str] = []
    for path in changed:
        if any(entry.matches(path) for entry in scope.entries):
            continue
        architecture_allows = any(entry.matches(path) for entry in expanded_allowed)
        architecture_blocks = any(entry.matches(path) for entry in expanded_blocked)
        if not architecture_allows or architecture_blocks:
            out_of_scope.append(path)

    evidence: dict[str, Any] = {
        "control_id": "PRG-07B",
        "scope_schema_version": scope.schema_version,
        "contract_hash": contract.contract_hash,
        "repository": ctx.subject.repository,
        "base_sha": ctx.subject.base_sha,
        "head_sha": ctx.subject.head_sha,
        "policy_version": ctx.subject.policy_version,
        "policy_digest": ctx.subject.policy_digest,
        "architecture_expansion": scope.architecture_expansion,
        "architecture_roles": sorted(roles),
        "changed_files": list(changed),
        "out_of_scope": out_of_scope,
        "diff_bytes": len(ctx.diff.encode("utf-8")),
        "diff_digest": f"sha256:{hashlib.sha256(ctx.diff.encode('utf-8')).hexdigest()}",
    }
    if out_of_scope:
        return GateResult(
            gate="7b",
            passed=False,
            status="failed",
            reason=(
                f"Contract-Scope verletzt: {len(out_of_scope)} Datei(en): "
                f"{', '.join(out_of_scope[:5])}"
            ),
            tool=evidence,
        )
    return GateResult(
        gate="7b",
        passed=True,
        status="passed",
        reason=f"Contract-Scope erfüllt: {len(changed)} Datei(en)",
        tool=evidence,
    )


def _slice_of_path(path: str) -> str | None:
    """Return slice-name if path is `samuel/slices//...`, else None.

    Globale Tests (`tests/...`), Adapter (`samuel/adapters/...`), Skripte
    und Konfig-Files liegen NICHT in einem Slice und duerfen aus mehreren
    Slices importieren — sie geben hier None zurueck.
    """
    parts = path.split("/")
    if len(parts) >= 3 and parts[0] == "samuel" and parts[1] == "slices":
        return parts[2]
    return None


def gate_8_slice_gate(ctx: GateContext) -> GateResult:
    """Per-Datei-Diff-Tracking (#243) + String/Comment-Heuristik (#250).

    Walked die diff Block-fuer-Block (`diff --git ... +++ b/` als
    File-Boundary) und attribuiert jede ECHTE `+from samuel.slices.X import`-
    Zeile der DATEI, in der sie tatsaechlich steht.

    Slice-File mit Cross-Slice-Import -> Verstoss.
    Globaler Test / Adapter / Skript mit Cross-Slice-Import -> erlaubt.
    Same-slice Import -> erlaubt.

    String-Inhalt + Kommentare werden NICHT als Imports gewertet (#250):
    - ``# from samuel.slices.X ...`` (Kommentar)
    - ``"from samuel.slices.X ..."`` (String-Literal in Test-Fixture)
    - ``foo("from samuel.slices.X ...")`` (irgendwas vor ``from``)
    Echter Import muss am Zeilenanfang (nach Indent) mit ``from`` beginnen.
    """
    import re

    diff = ctx.diff or ""
    if not diff:
        return GateResult(gate=8, passed=True, reason="Diff leer")

    violations: list[str] = []
    current_file: str | None = None
    file_slice: str | None = None
    # Anchored regex: ``\s*`` matcht den Indent, dann MUSS ``from`` folgen.
    # Strings/Kommentare haben ``"``, ``'`` oder ``#`` zwischen Indent und
    # ``from`` und schlagen damit am Match fehl.
    import_re = re.compile(r"\s*from samuel\.slices\.(\w+)")
    for line in diff.splitlines():
        # File-Boundary: `+++ b/` markiert die Zieldatei des aktuellen Hunks.
        if line.startswith("+++ b/"):
            current_file = line[len("+++ b/") :].strip()
            file_slice = _slice_of_path(current_file) if current_file else None
            continue
        if line.startswith("+++ ") or line.startswith("--- ") or line.startswith("diff --git"):
            continue
        # Echte Add-Zeile (nicht der `+++ b/`-Header) — pro Datei attribuieren.
        if not line.startswith("+") or line.startswith("++"):
            continue
        # Cross-Slice-Import nur in Slice-Files pruefen. Globale Tests etc. erlaubt.
        if file_slice is None:
            continue
        # Strip diff-Marker `+`, behalte Indent fuer das Anchored-Match.
        content = line[1:]
        if "import" not in content:
            continue
        m = import_re.match(content)
        if not m:
            continue
        imported_slice = m.group(1)
        if imported_slice == file_slice:
            continue
        violations.append(f"{current_file} -> {imported_slice}")

    if violations:
        return GateResult(
            gate=8,
            passed=False,
            reason=f"Cross-Slice-Import: {', '.join(sorted(set(violations))[:3])}",
            owasp_risk="A05:2021",
        )
    return GateResult(gate=8, passed=True, reason="Keine Cross-Slice-Imports")


def _diff_marks_deleted(diff: str, path: str) -> bool:
    lines = diff.splitlines()
    old_marker = f"--- a/{path}"
    return any(
        line == old_marker and index + 1 < len(lines) and lines[index + 1] == "+++ /dev/null"
        for index, line in enumerate(lines)
    )


def gate_9_python_syntax(ctx: GateContext) -> GateResult:
    import ast
    import platform

    from samuel.core.errors import SCMRevisionError

    tool = {"name": "cpython.ast", "version": platform.python_version()}

    py_files = [f for f in ctx.changed_files if f.endswith(".py")]
    if not py_files:
        return GateResult(
            gate=9,
            passed=True,
            status="not_applicable",
            reason="Keine geänderten Python-Dateien im Candidate",
            tool=tool,
        )
    if ctx.subject is None or ctx.read_candidate_file is None:
        return GateResult(
            gate=9,
            passed=False,
            status="failed",
            reason="Commitgebundener Candidate-Dateizugriff fehlt",
            tool=tool,
        )
    errors: list[str] = []
    checked: list[str] = []
    deleted: list[str] = []
    for f in py_files:
        try:
            content = ctx.read_candidate_file(f)
        except SCMRevisionError as exc:
            errors.append(f"{f}: {exc.code}")
            continue
        if content is None:
            if _diff_marks_deleted(ctx.diff, f):
                deleted.append(f)
            else:
                errors.append(f"{f}: unexpected_missing_file")
            continue
        try:
            ast.parse(content, filename=f)
            checked.append(f)
        except (SyntaxError, ValueError) as exc:
            line = getattr(exc, "lineno", None)
            location = f":{line}" if line is not None else ""
            errors.append(f"{f}{location}: {exc}")
    if errors:
        return GateResult(
            gate=9,
            passed=False,
            status="failed",
            reason=f"Python-Syntaxprüfung fehlgeschlagen: {'; '.join(errors[:3])}",
            tool=tool,
        )
    if not checked:
        return GateResult(
            gate=9,
            passed=True,
            status="not_applicable",
            reason=f"{len(deleted)} geänderte Python-Datei(en) am Candidate-Head gelöscht",
            tool=tool,
        )
    deletion_note = f", {len(deleted)} Löschung(en) nicht anwendbar" if deleted else ""
    return GateResult(
        gate=9,
        passed=True,
        status="passed",
        reason=f"{len(checked)} Candidate-Python-Datei(en) syntaktisch korrekt{deletion_note}",
        tool=tool,
    )


def gate_11_ac_verification(ctx: GateContext) -> GateResult:
    evidence = ctx.acceptance_evidence
    if not isinstance(evidence, dict):
        return GateResult(
            gate=11,
            passed=False,
            status="missing_evidence",
            reason="Keine strukturierte Acceptance-Evidence für den Candidate",
        )
    if evidence.get("schema_version") != 1:
        return GateResult(
            gate=11,
            passed=False,
            status="error",
            reason="Acceptance-Evidence-Schema ungültig",
        )
    if ctx.subject is None or evidence.get("evaluation_subject") != ctx.subject.as_dict():
        return GateResult(
            gate=11,
            passed=False,
            status="missing_evidence",
            reason="Acceptance-Evidence gehört zu einem anderen Prüfgegenstand",
        )
    contract = evidence.get("contract")
    results = evidence.get("results")
    if (
        not isinstance(contract, dict)
        or contract.get("schema_version") != 2
        or not isinstance(results, list)
    ):
        return GateResult(
            gate=11, passed=False, status="error", reason="Acceptance-Evidence ungültig"
        )
    if contract.get("contract_hash") != ctx.subject.contract_hash:
        return GateResult(
            gate=11,
            passed=False,
            status="missing_evidence",
            reason="Acceptance-Evidence hat einen veralteten Contract-Hash",
        )
    approval = contract.get("approval")
    if (
        not isinstance(approval, dict)
        or approval.get("state") != "approved"
        or approval.get("contract_hash") != ctx.subject.contract_hash
        or not all(approval.get(field) for field in ("actor", "method", "source_id"))
    ):
        return GateResult(
            gate=11,
            passed=False,
            status="missing_evidence",
            reason="Acceptance Contract ist nicht nachvollziehbar freigegeben",
        )
    criteria = contract.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        return GateResult(
            gate=11,
            passed=False,
            status="missing_evidence",
            reason="Acceptance Contract enthält keine Kriterien",
        )
    criterion_by_id = {
        item.get("criterion_id"): item
        for item in criteria
        if isinstance(item, dict) and isinstance(item.get("criterion_id"), str)
    }
    if len(criterion_by_id) != len(criteria):
        return GateResult(
            gate=11,
            passed=False,
            status="error",
            reason="Acceptance-Kriterien mehrdeutig",
        )
    required_ids = {
        criterion_id for criterion_id, item in criterion_by_id.items() if item.get("required", True)
    }
    result_by_id = {
        item.get("criterion_id"): item
        for item in results
        if isinstance(item, dict) and isinstance(item.get("criterion_id"), str)
    }
    if len(result_by_id) != len(results) or set(result_by_id) - set(criterion_by_id):
        return GateResult(
            gate=11, passed=False, status="error", reason="Acceptance-Evidence mehrdeutig"
        )
    missing = required_ids - set(result_by_id)
    if missing:
        return GateResult(
            gate=11,
            passed=False,
            status="missing_evidence",
            reason=f"Evidence für {len(missing)} erforderliche Kriterien fehlt",
        )
    valid_statuses = {
        "passed",
        "failed",
        "manual_pending",
        "not_applicable",
        "missing_evidence",
        "error",
    }
    if any(item.get("status") not in valid_statuses for item in result_by_id.values()):
        return GateResult(
            gate=11,
            passed=False,
            status="error",
            reason="Acceptance-Evidence enthält unbekannten Status",
        )
    for criterion_id in required_ids:
        criterion = criterion_by_id[criterion_id]
        result = result_by_id[criterion_id]
        if criterion.get("mode") != "manual" or result.get("status") != "passed":
            continue
        result_evidence = result.get("evidence")
        receipt = (
            result_evidence.get("human_receipt") if isinstance(result_evidence, dict) else None
        )
        if not isinstance(receipt, dict) or not (
            receipt.get("criterion_id") == criterion_id
            and receipt.get("contract_hash") == ctx.subject.contract_hash
            and receipt.get("head_sha") == ctx.subject.head_sha
            and receipt.get("actor")
            and receipt.get("source_id")
        ):
            return GateResult(
                gate=11,
                passed=False,
                status="missing_evidence",
                reason=f"MANUAL-Receipt für {criterion_id} fehlt oder ist veraltet",
            )
    failed = [
        result_by_id[criterion_id]
        for criterion_id in required_ids
        if result_by_id[criterion_id].get("status") != "passed"
    ]
    if failed:
        statuses = sorted({str(item.get("status") or "missing_evidence") for item in failed})
        status = statuses[0] if len(statuses) == 1 else "failed"
        if status not in {
            "failed",
            "manual_pending",
            "not_applicable",
            "missing_evidence",
            "error",
        }:
            status = "error"
        return GateResult(
            gate=11,
            passed=False,
            status=cast(GateStatus, status),
            reason=f"{len(failed)} erforderliche Kriterien nicht erfüllt ({', '.join(statuses)})",
        )
    return GateResult(
        gate=11,
        passed=True,
        status="passed",
        reason=f"Alle {len(required_ids)} Kriterien am Candidate nachgewiesen",
    )


def gate_12_ready_to_close(ctx: GateContext) -> GateResult:
    evidence = ctx.acceptance_evidence
    if not isinstance(evidence, dict) or not isinstance(evidence.get("results"), list):
        return GateResult(
            gate=12,
            passed=False,
            status="missing_evidence",
            reason="Readiness unbekannt: strukturierte Evidence fehlt",
        )
    results = evidence["results"]
    unresolved = [
        item for item in results if not isinstance(item, dict) or item.get("status") != "passed"
    ]
    if unresolved:
        statuses = sorted(
            {
                str(item.get("status") or "missing_evidence") if isinstance(item, dict) else "error"
                for item in unresolved
            }
        )
        return GateResult(
            gate=12,
            passed=False,
            status="manual_pending" if statuses == ["manual_pending"] else "missing_evidence",
            reason=f"Nicht abschlussbereit: {len(unresolved)} offene Evidence-Status ({', '.join(statuses)})",
        )
    return GateResult(
        gate=12,
        passed=bool(results),
        status="passed" if results else "missing_evidence",
        reason=f"Abschlussbereit: {len(results)} Kriterien vollständig"
        if results
        else "Keine Kriterien",
    )


def gate_13a_branch_freshness(ctx: GateContext) -> GateResult:
    import subprocess

    if ctx.subject is None:
        return GateResult(
            gate="13a",
            passed=False,
            reason="Branch-Freshness ohne unveränderlichen Prüfgegenstand nicht prüfbar",
            owasp_risk="A05:2021",
        )
    try:
        result = subprocess.run(
            [
                "git",
                "rev-list",
                "--count",
                f"{ctx.subject.head_sha}..{ctx.subject.base_sha}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=ctx.project_root,
        )
        if result.returncode == 0:
            behind = int(result.stdout.strip() or "0")
            if behind > 50:
                return GateResult(
                    gate="13a",
                    passed=False,
                    reason=f"Branch {behind} Commits hinter main — rebase nötig",
                    owasp_risk="A05:2021",
                )
            return GateResult(
                gate="13a", passed=True, reason=f"Branch {behind} Commits hinter main"
            )
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass
    return GateResult(
        gate="13a",
        passed=False,
        reason="Branch-Freshness für den Prüfgegenstand nicht prüfbar",
        owasp_risk="A05:2021",
    )


def gate_13b_destructive_diff(ctx: GateContext) -> GateResult:
    if not ctx.diff:
        return GateResult(gate="13b", passed=True, reason="Kein Diff")
    deleted_lines = [
        l for l in ctx.diff.splitlines() if l.startswith("-") and not l.startswith("---")
    ]
    added_lines = [
        l for l in ctx.diff.splitlines() if l.startswith("+") and not l.startswith("+++")
    ]
    if len(deleted_lines) > len(added_lines) * 3 and len(deleted_lines) > 50:
        return GateResult(
            gate="13b",
            passed=False,
            reason=f"Destruktiver Diff: {len(deleted_lines)} Löschungen vs {len(added_lines)} Hinzufügungen",
            owasp_risk="A05:2021",
        )
    return GateResult(gate="13b", passed=True, reason="Diff nicht destruktiv")


GATE_REGISTRY: dict[int | str, Any] = {
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
