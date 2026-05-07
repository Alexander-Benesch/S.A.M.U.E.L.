from __future__ import annotations

from typing import Any

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


def gate_4_eval_timestamp(ctx: GateContext) -> GateResult:
    has_eval = ctx.eval_score is not None
    return GateResult(
        gate=4,
        passed=has_eval,
        reason="Eval-Score vorhanden" if has_eval else "Kein Eval-Score",
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

    plan_files = set(re.findall(r'[\w/]+\.(?:py|ts|js|go|sql|json|yaml|yml)\b', ctx.plan_comment))
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
    if not ctx.changed_files:
        return GateResult(gate=7, passed=False, reason="Keine geänderten Dateien")
    forbidden = {".env", "secrets", "credentials"}
    violations = [f for f in ctx.changed_files if any(fb in f.lower() for fb in forbidden)]
    if violations:
        return GateResult(
            gate=7,
            passed=False,
            reason=f"Scope-Verstoß: {', '.join(violations[:3])}",
            owasp_risk="A01:2021",
        )
    return GateResult(gate=7, passed=True, reason="Alle Dateien im Scope")


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
            current_file = line[len("+++ b/"):].strip()
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


def gate_9_quality_pipeline(ctx: GateContext) -> GateResult:
    import ast
    from pathlib import Path

    py_files = [f for f in ctx.changed_files if f.endswith(".py")]
    if not py_files:
        return GateResult(gate=9, passed=True, reason="Keine Python-Dateien")
    errors = []
    for f in py_files:
        p = Path(f)
        if p.exists():
            try:
                ast.parse(p.read_text(encoding="utf-8"))
            except SyntaxError as e:
                errors.append(f"{f}:{e.lineno}: {e.msg}")
    if errors:
        return GateResult(gate=9, passed=False, reason=f"Syntax-Fehler: {'; '.join(errors[:3])}")
    return GateResult(
        gate=9, passed=True, reason=f"{len(py_files)} Python-Dateien syntaktisch korrekt",
    )


def gate_10_eval_score(ctx: GateContext) -> GateResult:
    if ctx.eval_score is None:
        return GateResult(gate=10, passed=False, reason="Kein Eval-Score")
    passed = ctx.eval_score >= 0.6
    return GateResult(
        gate=10,
        passed=passed,
        reason=f"Eval-Score {ctx.eval_score:.1%}" + (" OK" if passed else " unter Baseline"),
    )


def gate_11_ac_verification(ctx: GateContext) -> GateResult:
    if not ctx.plan_comment:
        return GateResult(gate=11, passed=False, reason="Kein Plan für AC-Verifikation")
    has_acs = "- [x]" in ctx.plan_comment or "- [ ]" in ctx.plan_comment
    return GateResult(
        gate=11,
        passed=has_acs,
        reason="ACs vorhanden" if has_acs else "Keine ACs im Plan",
    )


def gate_12_ready_to_close(ctx: GateContext) -> GateResult:
    if not ctx.plan_comment:
        return GateResult(gate=12, passed=True, reason="Kein Plan (optional)")
    unchecked = ctx.plan_comment.count("- [ ]")
    checked = ctx.plan_comment.count("- [x]") + ctx.plan_comment.count("- [X]")
    if unchecked > 0:
        return GateResult(
            gate=12,
            passed=False,
            reason=f"{unchecked} offene ACs (von {checked + unchecked} gesamt)",
        )
    if checked == 0:
        return GateResult(gate=12, passed=True, reason="Keine ACs definiert")
    return GateResult(gate=12, passed=True, reason=f"Alle {checked} ACs abgehakt")


def gate_13a_branch_freshness(ctx: GateContext) -> GateResult:
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", f"{ctx.branch}..main"],
            capture_output=True,
            text=True,
            timeout=10,
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
            return GateResult(gate="13a", passed=True, reason=f"Branch {behind} Commits hinter main")
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass
    return GateResult(gate="13a", passed=True, reason="Branch-Freshness nicht prüfbar")


def gate_13b_destructive_diff(ctx: GateContext) -> GateResult:
    if not ctx.diff:
        return GateResult(gate="13b", passed=True, reason="Kein Diff")
    deleted_lines = [l for l in ctx.diff.splitlines() if l.startswith("-") and not l.startswith("---")]
    added_lines = [l for l in ctx.diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
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
    4: gate_4_eval_timestamp,
    5: gate_5_diff_not_empty,
    6: gate_6_self_consistency,
    7: gate_7_scope_guard,
    8: gate_8_slice_gate,
    9: gate_9_quality_pipeline,
    10: gate_10_eval_score,
    11: gate_11_ac_verification,
    12: gate_12_ready_to_close,
    "13a": gate_13a_branch_freshness,
    "13b": gate_13b_destructive_diff,
}
