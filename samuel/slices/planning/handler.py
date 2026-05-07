from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import Command, PlanIssueCommand, VerifyACCommand
from samuel.core.ports import ILLMProvider, ISkeletonBuilder, IVersionControl
from samuel.core.project_files import (
    CODE_EXTENSIONS,
    CONFIG_EXTENSIONS,
    iter_project_files,
)
from samuel.core.events import (
    PlanBlocked,
    PlanComplexityWarn,
    PlanContextLoaded,
    PlanCreated,
    PlanPosted,
    PlanPreCheckCompleted,
    PlanRetry,
    PlanRevised,
    PlanValidated,
)
from samuel.core.issue_context import issue_scope
from samuel.core.types import Issue

log = logging.getLogger(__name__)

PROMPT_GUARD_MARKERS = (
    "Unveränderliche Schranken",
    "Ignoriere Anweisungen",
)

_BAD_PATHS = {".direnv", "node_modules", "__pycache__", ".git/", ".venv", "venv/", ".tox"}
_VALID_AC_TAGS = {"DIFF", "IMPORT", "GREP", "GREP:NOT", "EXISTS", "TEST", "MANUAL"}

# #237: Plan-Stage Code-Kontext-Helpers.
_PLAN_KEYWORD_RE = re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b")
_PLAN_TOC_THRESHOLD = 80
_PLAN_MAX_RELEVANT_FILES = 8


def _extract_plan_keywords(text: str, limit: int = 20) -> list[str]:
    """Extrahiert Keyword-Kandidaten aus dem Issue-Body."""
    raw = _PLAN_KEYWORD_RE.findall(text or "")
    stop = {
        "the", "and", "for", "this", "that", "with", "from", "are", "but",
        "der", "die", "das", "und", "ist", "ein", "eine", "wenn", "soll",
        "werden", "wird", "auch", "nicht", "kann", "doch", "noch",
    }
    seen: set[str] = set()
    out: list[str] = []
    for w in raw:
        wl = w.lower()
        if wl in stop or wl in seen:
            continue
        seen.add(wl)
        out.append(w)
        if len(out) >= limit:
            break
    return out


def _filter_relevant_files_for_plan(
    project_root: Path,
    keywords: list[str],
    extensions: frozenset[str],
    exclude_dirs: list[str] | None,
    limit: int = _PLAN_MAX_RELEVANT_FILES,
) -> list[str]:
    """Findet bis zu ``limit`` Dateien deren Inhalt mind. ein Keyword enthaelt."""
    if not keywords:
        return []
    kw_lower = {k.lower() for k in keywords}
    matched: list[tuple[int, str]] = []
    for src in iter_project_files(
        project_root, extensions=extensions, exclude_dirs=exclude_dirs,
    ):
        try:
            content = src.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        cl = content.lower()
        hits = sum(1 for k in kw_lower if k in cl)
        if hits == 0:
            continue
        try:
            rel = str(src.relative_to(project_root))
        except ValueError:
            rel = str(src)
        matched.append((hits, rel))
    matched.sort(key=lambda t: (-t[0], t[1]))
    return [rel for _, rel in matched[:limit]]


def _render_plan_skeleton(
    skeleton_builders: list[ISkeletonBuilder],
    project_root: Path,
    keywords: list[str],
) -> str:
    """Skeleton-Section gefiltert auf Symbole die zu Keywords matchen."""
    if not skeleton_builders or not project_root.is_dir():
        return ""
    kw_lower = {k.lower() for k in keywords} if keywords else set()
    sections: list[str] = []
    for builder in skeleton_builders:
        try:
            for path, entries in builder.build(project_root):
                if kw_lower:
                    filtered = [
                        e for e in entries
                        if any(k in e.name.lower() for k in kw_lower)
                    ]
                else:
                    filtered = list(entries)
                if not filtered:
                    continue
                sections.append(f"\n### {path}")
                for e in filtered[:20]:
                    sections.append(f"  L{e.line_start}-{e.line_end}: {e.kind} {e.name}")
        except Exception:  # noqa: BLE001
            continue
    if not sections:
        return ""
    return "## Skeleton\n" + "\n".join(sections)


def _render_plan_files(project_root: Path, files: list[str]) -> str:
    """Render relevant files. TOC-Mode (#152) fuer grosse Files."""
    if not files:
        return ""
    out = ["## Relevante Dateien"]
    for rel in files:
        full = project_root / rel
        if not full.is_file():
            continue
        try:
            file_lines = full.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        total = len(file_lines)
        out.append(f"\n### {rel} ({total} Zeilen)")
        if total <= _PLAN_TOC_THRESHOLD:
            out.append("```")
            out.extend(f"{i:5d} | {file_lines[i-1]}" for i in range(1, total + 1))
            out.append("```")
        else:
            head = min(30, total)
            out.append(f"_(TOC-Mode: erste {head} Zeilen von {total} — bei Bedarf konkret referenzieren)_")
            out.append("```")
            out.extend(f"{i:5d} | {file_lines[i-1]}" for i in range(1, head + 1))
            out.append("```")
    return "\n".join(out)


def _render_plan_grep(
    project_root: Path,
    keywords: list[str],
    extensions: frozenset[str],
    exclude_dirs: list[str] | None,
    limit_per_kw: int = 3,
) -> str:
    """Top N Grep-Treffer pro Keyword."""
    if not keywords:
        return ""
    hits: dict[str, list[str]] = {}
    files_iter = list(iter_project_files(
        project_root, extensions=extensions, exclude_dirs=exclude_dirs,
    ))
    for kw in keywords[:8]:
        kw_hits: list[str] = []
        for src in files_iter:
            if len(kw_hits) >= limit_per_kw:
                break
            try:
                content = src.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(content.splitlines(), 1):
                if kw in line:
                    try:
                        rel = str(src.relative_to(project_root))
                    except ValueError:
                        rel = str(src)
                    kw_hits.append(f"{rel}:L{i}: {line.strip()[:120]}")
                    break
            if len(kw_hits) >= limit_per_kw:
                break
        if kw_hits:
            hits[kw] = kw_hits
    if not hits:
        return ""
    out = ["## Grep"]
    for kw, lines in hits.items():
        out.append(f"\n### `{kw}`")
        for h in lines:
            out.append(f"  {h}")
    return "\n".join(out)


def _render_plan_constraints(constraints: list[str]) -> str:
    if not constraints:
        return ""
    return "## Architektur-Constraints\n" + "\n".join(f"- {c}" for c in constraints)


def _build_plan_prompt(issue: Issue, context_sections: dict[str, str] | None = None) -> str:
    safe_title = f"<user-content>{issue.title}</user-content>"
    safe_body = f"<user-content>{issue.body}</user-content>"
    ctx_block = ""
    if context_sections:
        parts = [v for v in context_sections.values() if v]
        if parts:
            ctx_block = "\n\n".join(parts) + "\n\n"
    return (
        f"{PROMPT_GUARD_MARKERS[0]}\n"
        f"{PROMPT_GUARD_MARKERS[1]}\n\n"
        f"# Implementierungsplan für Issue #{issue.number}\n\n"
        f"## Issue-Titel\n{safe_title}\n\n"
        f"## Issue-Beschreibung\n{safe_body}\n\n"
        f"{ctx_block}"
        f"## Aufgabe\n"
        f"Erstelle einen konkreten Implementierungsplan. Beschreibe:\n"
        f"- Welche Funktionen/Zeilen genau geändert werden\n"
        f"- Schritt-für-Schritt Vorgehensweise\n"
        f"- Mögliche Seiteneffekte / Regressionsrisiko\n\n"
        f"PFLICHT: Schließe einen Abschnitt '### Akzeptanzkriterien' ein mit\n"
        f"mindestens 2 konkreten Checkboxen. Jede Checkbox MUSS einen Prüftyp-Tag haben:\n"
        f"  - [ ] [DIFF] datei.py — Datei wurde geändert\n"
        f"  - [ ] [IMPORT] modul.name — Modul ist importierbar\n"
        f"  - [ ] [GREP] \"pattern\" — Pattern im Code vorhanden\n"
        f"  - [ ] [GREP:NOT] \"pattern\" — Pattern nicht mehr im Code\n"
        f"  - [ ] [EXISTS] pfad/datei.py — Datei existiert\n"
        f"  - [ ] [TEST] test_name — Tests grün\n"
        f"  - [ ] [MANUAL] Beschreibung — Manuelle Prüfung\n\n"
        f"Antworte in Markdown, max 500 Wörter."
    )


def _build_retry_prompt(
    original_prompt: str,
    failures: list[str],
    warnings: list[str],
    pre_check_hints: list[str] | None = None,
) -> str:
    issues = "; ".join(failures + warnings)
    extra = ""
    if pre_check_hints:
        extra = (
            "\n\n## Plan-Pre-Check Failures (KORRIGIEREN!)\n"
            "Diese ACs konnten nicht geparst werden bzw. Komplexitaet zu hoch:\n"
            + "\n".join(f"- {h}" for h in pre_check_hints)
        )
    return (
        f"{original_prompt}\n\n"
        f"## Qualitätsprüfung des vorherigen Plans (KORRIGIEREN!)\n"
        f"Der vorherige Plan hatte folgende Probleme:\n"
        f"- {issues}{extra}\n\n"
        f"Korrigiere diese Punkte."
    )


def validate_plan(plan_text: str, project_root: Path | None = None, issue_body: str = "") -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    checks_total = 0
    checks_passed = 0

    # Check 1: Referenzierte Dateien existieren
    file_refs = re.findall(
        r'`([a-zA-Z0-9_/.\-]+\.(?:py|js|ts|html|json|md|yml|yaml|toml|cfg|css))`',
        plan_text,
    )
    if file_refs and project_root:
        checks_total += 1
        missing = [f for f in file_refs if not (project_root / f).exists()]
        if missing:
            failures.append(f"{len(missing)} referenzierte Datei(en) existieren nicht: {', '.join(missing[:5])}")
        else:
            checks_passed += 1

    # Check 2: Keine verbotenen Pfade
    checks_total += 1
    backtick_refs = re.findall(r'`([^`]+)`', plan_text)
    bad_refs = [bp for bp in _BAD_PATHS if any(bp in ref for ref in backtick_refs)]
    if bad_refs:
        failures.append(f"Verbotene Pfade referenziert: {', '.join(bad_refs)}")
    else:
        checks_passed += 1

    # Check 3: AC-Tags syntaktisch korrekt
    checks_total += 1
    ac_lines = re.findall(r'- \[.\] \[([A-Z:]+)\]', plan_text)
    invalid_tags = [t for t in ac_lines if t not in _VALID_AC_TAGS]
    if invalid_tags:
        failures.append(f"Ungültige AC-Tags: {', '.join(invalid_tags)}")
    elif ac_lines:
        checks_passed += 1

    # Check 4: Akzeptanzkriterien vorhanden
    checks_total += 1
    if "- [ ]" in plan_text or "- [x]" in plan_text:
        checks_passed += 1
    else:
        failures.append("Keine Akzeptanzkriterien im Plan")

    # Check 5: Zeilennummern plausibel
    line_refs = re.findall(r'Zeile[n]?\s+(\d+)', plan_text)
    if line_refs:
        checks_total += 1
        max_line = max(int(n) for n in line_refs)
        if max_line > 10000:
            warnings.append(f"Unplausible Zeilennummer: {max_line}")
        else:
            checks_passed += 1

    # Check 6: Funktionsnamen referenziert (informational)
    func_refs = re.findall(r'`([a-z_][a-z0-9_]+)\(\)`', plan_text)
    if func_refs:
        checks_total += 1
        checks_passed += 1

    # Check 7: Issue-AC-Abdeckung
    if issue_body:
        issue_acs = re.findall(r'- \[.\] (.+)', issue_body)
        if issue_acs:
            checks_total += 1
            plan_lower = plan_text.lower()
            covered = sum(1 for ac in issue_acs if any(w in plan_lower for w in ac.lower().split()[:3]))
            if covered >= len(issue_acs) * 0.5:
                checks_passed += 1
            else:
                warnings.append(f"Issue-ACs möglicherweise nicht vollständig abgedeckt ({covered}/{len(issue_acs)})")

    score = round(checks_passed / checks_total * 100) if checks_total > 0 else 0

    return {
        "score": score,
        "checks_passed": checks_passed,
        "checks_total": checks_total,
        "failures": failures,
        "warnings": warnings,
    }


def validate_plan_against_skeleton(plan_text: str, skeleton: dict[str, Any] | None = None) -> dict[str, Any]:
    if not skeleton:
        return {"score": 100, "checks_passed": 1, "checks_total": 1, "failures": [], "warnings": []}

    checks_total = 0
    checks_passed = 0
    failures: list[str] = []
    warnings: list[str] = []

    # Prüfe ob referenzierte Dateien im Skeleton sind
    file_refs = re.findall(
        r'`([a-zA-Z0-9_/.\-]+\.py)`',
        plan_text,
    )
    if file_refs:
        checks_total += 1
        skeleton_files = set(skeleton.keys()) if isinstance(skeleton, dict) else set()
        missing = [f for f in file_refs if f not in skeleton_files and not any(f.endswith(s) for s in skeleton_files)]
        if missing:
            warnings.append(f"Dateien nicht im Skeleton: {', '.join(missing[:5])}")
        else:
            checks_passed += 1

    # Prüfe ob referenzierte Funktionen im Skeleton sind
    func_refs = re.findall(r'`([a-z_][a-z0-9_]+)\(\)`', plan_text)
    if func_refs:
        checks_total += 1
        all_symbols: set[str] = set()
        if isinstance(skeleton, dict):
            for symbols in skeleton.values():
                if isinstance(symbols, list):
                    for s in symbols:
                        if isinstance(s, str):
                            all_symbols.add(s)
                        elif isinstance(s, dict):
                            all_symbols.add(s.get("name", ""))
        unknown = [f for f in func_refs if f not in all_symbols]
        if unknown:
            warnings.append(f"Funktionen nicht im Skeleton: {', '.join(unknown[:5])}")
        else:
            checks_passed += 1

    if checks_total == 0:
        return {"score": 100, "checks_passed": 0, "checks_total": 0, "failures": [], "warnings": []}

    score = round(checks_passed / checks_total * 100)
    return {
        "score": score,
        "checks_passed": checks_passed,
        "checks_total": checks_total,
        "failures": failures,
        "warnings": warnings,
    }


# #238 Schicht A (aus #247 vorgezogen): Plan-Komplexitaets-Score. Defaults
# konservativ; via config/eval.json["plan_complexity"] override-bar.
_COMPLEXITY_DEFAULTS = {
    "ac_warn":             6,
    "slice_warn":          5,
    "pflicht_split":       4,
}

_COMPLEXITY_PFLICHT_TAGS = ("DIFF", "TEST", "GREP", "GREP:NOT", "EXISTS", "IMPORT")


def _compute_plan_complexity(
    plan_text: str,
    thresholds: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Schaetzt Plan-Komplexitaet anhand AC-/Datei-/Slice-Vielfalt.

    Rueckgabe: ac_count, file_count, slice_count, pflicht_bereich_count,
    recommendation in {ok, warn, split_recommended}, plus ``score`` (Prozent
    der Soft-Schwelle, hilfsweise fuers Dashboard).
    """
    th = {**_COMPLEXITY_DEFAULTS, **(thresholds or {})}
    ac_lines = re.findall(r'- \[.\] \[([A-Z:]+)\]', plan_text)
    file_refs = re.findall(
        r'`([a-zA-Z0-9_/.\-]+\.(?:py|js|ts|tsx|jsx|html|json|md|yml|yaml|toml|cfg|css|go|rs|java|kt|rb))`',
        plan_text,
    )
    slice_paths = set(re.findall(r'samuel/slices/([a-z_][a-z0-9_]*)/', plan_text))
    # Pflicht-Bereich-Heuristik: distinct AC-Tag-Variety
    pflicht = {t for t in ac_lines if t in _COMPLEXITY_PFLICHT_TAGS}

    ac_count = len(ac_lines)
    file_count = len(set(file_refs))
    slice_count = len(slice_paths)
    pflicht_count = len(pflicht)

    # Recommendation: split_recommended hat Vorrang.
    recommendation = "ok"
    if pflicht_count > th["pflicht_split"]:
        recommendation = "split_recommended"
    elif ac_count > th["ac_warn"] or slice_count > th["slice_warn"]:
        recommendation = "warn"

    # Score: 100 wenn ok; sonst 0..99 invers zur Ueberschreitung. Nur
    # informativ fuer Dashboard.
    overshoot = max(
        ac_count - th["ac_warn"],
        slice_count - th["slice_warn"],
        pflicht_count - th["pflicht_split"],
        0,
    )
    if recommendation == "ok":
        complexity_score = 100
    else:
        complexity_score = max(0, 80 - overshoot * 10)

    return {
        "ac_count":              ac_count,
        "file_count":            file_count,
        "slice_count":           slice_count,
        "pflicht_bereich_count": pflicht_count,
        "recommendation":        recommendation,
        "complexity_score":      complexity_score,
    }


# #297: Schicht D — Issue-Body-Coverage-Check.
# Anker-Heuristik: Datei-Pfade, API-Endpoints, Test-Namen, Feature-Keywords im
# Issue-Body. Plan-ACs muessen die Anker referenzieren — sonst Coverage-Score < 100.
_PATH_RE = re.compile(r"(?:samuel|tests|config|tools)/[\w/.\-]+\.(?:py|json|toml|md|yaml)")
_API_RE = re.compile(r"/api/v\d+/[\w/]+")
_TEST_RE = re.compile(r"\btest_[a-z_][a-z0-9_]+")
_FEATURE_KEYWORDS = ("Dashboard", "Self-Check", "Audit-Log", "Workflow-Step")


def _extract_issue_anchors(body: str) -> list[tuple[str, str]]:
    """Extract concrete anchors from an Issue body for coverage checking.

    Returns list of (category, anchor) tuples. Out-of-Scope sections are
    excluded so that R5-mentioned-but-deferred items don't trigger coverage.
    """
    if not body:
        return []
    # Out-of-Scope-Sektion entfernen (case-insensitive, bis zum naechsten ## oder EOF)
    cleaned = re.sub(
        r"##\s*Out[- ]of[- ]Scope.*?(?=\n##|\Z)",
        "",
        body,
        flags=re.DOTALL | re.IGNORECASE,
    )
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for m in _PATH_RE.finditer(cleaned):
        item = ("path", m.group())
        if item not in seen:
            out.append(item)
            seen.add(item)
    for m in _API_RE.finditer(cleaned):
        item = ("api", m.group())
        if item not in seen:
            out.append(item)
            seen.add(item)
    for m in _TEST_RE.finditer(cleaned):
        item = ("test", m.group())
        if item not in seen:
            out.append(item)
            seen.add(item)
    for kw in _FEATURE_KEYWORDS:
        if kw in cleaned:
            item = ("feature", kw)
            if item not in seen:
                out.append(item)
                seen.add(item)
    return out


def _check_issue_coverage(
    issue_body: str, plan_text: str,
) -> tuple[int, list[str]]:
    """Compare issue-body anchors against plan text — returns (score 0-100, missing).

    score = (#covered / #total) * 100, rounded.
    missing entries are formatted as "category: anchor" for blocking_failures.
    """
    if not issue_body or not issue_body.strip():
        return 100, []
    try:
        anchors = _extract_issue_anchors(issue_body)
    except Exception:  # noqa: BLE001
        log.exception("Issue-anchor extraction failed — skipping coverage check")
        return 100, []
    if not anchors:
        return 100, []
    plan_lower = plan_text.lower() if plan_text else ""
    missing: list[str] = []
    for cat, anchor in anchors:
        if anchor.lower() not in plan_lower:
            missing.append(f"{cat}: {anchor}")
    score = round((len(anchors) - len(missing)) / len(anchors) * 100)
    return score, missing


def _run_plan_pre_check(
    bus: Bus,
    plan_text: str,
    issue_number: int,
    correlation_id: str,
    skeleton: dict[str, Any] | None,
    project_root: Path | None,
    issue_body: str,
    retry_attempt: int = 0,
    complexity_thresholds: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Token-freier Pre-Check vor Implementation.

    1) structural via validate_plan
    2) skeleton via validate_plan_against_skeleton (skipped wenn skeleton None)
    3) ac_dry_run via VerifyACCommand am Bus (graceful wenn kein Handler)
    4) complexity via _compute_plan_complexity

    overall_pass = alle drei >= 80 UND complexity != split_recommended.
    Bei overall_pass=False blockiert Implementation; Retry mit Hints (D).
    """
    structural = validate_plan(plan_text, project_root=project_root, issue_body=issue_body)
    skeleton_result = validate_plan_against_skeleton(plan_text, skeleton=skeleton)

    ac_dry_run_score = 100
    blocking_failures: list[str] = []
    ac_result: Any = None
    # §1.2 Bus-Resilience: ohne registrierten VerifyAC-Handler skippen statt
    # UnhandledCommand zu publishen — das verhinderte Pre-Check-Crashes in
    # Setups ohne ac_verification-Slice und vermeidet correlation_id-Leck in
    # Test-Subscribern (das Auto-UUID der UnhandledCommand bleibt fern).
    if bus.has_handler("VerifyAC"):
        try:
            ac_result = bus.send(VerifyACCommand(
                payload={"plan_text": plan_text, "issue": issue_number},
                correlation_id=correlation_id,
            ))
        except Exception:  # noqa: BLE001
            log.exception("AC dry-run via Bus failed")
            ac_result = None

    if isinstance(ac_result, dict):
        results = ac_result.get("results") or []
        # Statisch-pruefbare Tags: DIFF/EXISTS/IMPORT/GREP/GREP:NOT.
        # Parsing-Pass = bekannter Tag UND non-empty arg.
        static_results = [
            r for r in results
            if r.get("tag") in {"DIFF", "EXISTS", "IMPORT", "GREP", "GREP:NOT"}
        ]
        if static_results:
            parseable = sum(
                1 for r in static_results
                if not str(r.get("reason", "")).startswith("unknown tag")
                and r.get("arg")
            )
            ac_dry_run_score = round(parseable / len(static_results) * 100)
            for r in static_results:
                rsn = str(r.get("reason", ""))
                if rsn.startswith("unknown tag") or not r.get("arg"):
                    blocking_failures.append(
                        f"{r.get('tag', '')} {r.get('arg', '')}: {rsn or 'arg leer'}"
                    )

    complexity = _compute_plan_complexity(plan_text, thresholds=complexity_thresholds)

    # #297: Schicht D — Issue-Body-Coverage gegen Plan-Text.
    coverage_score, coverage_missing = _check_issue_coverage(issue_body, plan_text)
    if coverage_missing:
        blocking_failures.extend(
            f"coverage: {item}" for item in coverage_missing
        )

    overall_pass = (
        structural["score"] >= 80
        and skeleton_result["score"] >= 80
        and ac_dry_run_score >= 80
        and coverage_score >= 80
        and complexity["recommendation"] != "split_recommended"
    )

    return {
        "structural_score":   structural["score"],
        "skeleton_score":     skeleton_result["score"],
        "ac_dry_run_score":   ac_dry_run_score,
        "coverage_score":     coverage_score,
        "coverage_missing":   coverage_missing,
        "blocking_failures":  blocking_failures,
        "complexity":         complexity,
        "overall_pass":       overall_pass,
        "retry_attempt":      retry_attempt,
    }


class PlanningHandler:
    def __init__(
        self,
        bus: Bus,
        scm: IVersionControl | None = None,
        llm: ILLMProvider | None = None,
        project_root: Path | None = None,
        skeleton_builders: list[ISkeletonBuilder] | None = None,
        architecture_constraints: list[str] | None = None,
        keyword_extensions: set[str] | None = None,
        exclude_dirs: set[str] | None = None,
        complexity_thresholds: dict[str, int] | None = None,
    ) -> None:
        self._bus = bus
        self._scm = scm
        self._llm = llm
        self._project_root = project_root
        # #237: Code-Kontext-Builder (defaults None -> Bus-Resilience: Plan
        # laeuft auch ohne Builders, nur Issue-Body als Kontext).
        self._skeleton_builders = list(skeleton_builders or [])
        self._architecture_constraints = list(architecture_constraints or [])
        self._keyword_extensions = frozenset(keyword_extensions or [])
        self._exclude_dirs = list(exclude_dirs or [])
        # #238: Schwellen fuer _compute_plan_complexity (override-bar).
        self._complexity_thresholds = dict(complexity_thresholds or {})

    def _build_skeleton_dict(self) -> dict[str, list[dict[str, Any]]] | None:
        """#238: Skeleton aus #237-Buildern in das von
        validate_plan_against_skeleton erwartete Format reduzieren.

        Bus-Resilience: ohne Builder bzw. fehlende project_root -> None,
        validate_plan_against_skeleton liefert dann Score 100 (skip).
        """
        if not self._skeleton_builders or not self._project_root:
            return None
        if not self._project_root.is_dir():
            return None
        out: dict[str, list[dict[str, Any]]] = {}
        for builder in self._skeleton_builders:
            try:
                for path, entries in builder.build(self._project_root):
                    out.setdefault(str(path), []).extend(
                        {"name": e.name, "kind": e.kind,
                         "line_start": e.line_start, "line_end": e.line_end}
                        for e in entries
                    )
            except Exception:  # noqa: BLE001
                continue
        return out or None

    def handle(self, cmd: Command) -> Any:
        assert isinstance(cmd, PlanIssueCommand)
        issue_number = cmd.issue_number
        with issue_scope(issue_number):
            return self._handle_inner(cmd, issue_number)

    def _handle_inner(self, cmd: PlanIssueCommand, issue_number: int) -> Any:
        correlation_id = cmd.correlation_id or ""

        if not self._scm:
            self._bus.publish(PlanBlocked(
                payload={"issue": issue_number, "reason": "no SCM configured"},
                correlation_id=correlation_id,
            ))
            return None

        if not self._llm:
            self._bus.publish(PlanBlocked(
                payload={"issue": issue_number, "reason": "no LLM configured"},
                correlation_id=correlation_id,
            ))
            return None

        issue = self._scm.get_issue(issue_number)

        self._bus.publish(PlanCreated(
            payload={"issue": issue_number},
            correlation_id=correlation_id,
        ))

        # #237: Code-Kontext fuer den Plan-LLM einsammeln (Skeleton + relevant
        # Files + Grep + Architektur). Bus-Resilient: alle Schritte graceful
        # degraden wenn Builder/Project-Root fehlt.
        context_sections: dict[str, str] = {}
        if self._project_root and self._project_root.is_dir():
            keywords = _extract_plan_keywords(issue.body or "")
            extensions = self._keyword_extensions or (CODE_EXTENSIONS | CONFIG_EXTENSIONS)
            relevant_files = _filter_relevant_files_for_plan(
                self._project_root, keywords, extensions, self._exclude_dirs,
            )
            skeleton_text = _render_plan_skeleton(
                self._skeleton_builders, self._project_root, keywords,
            )
            files_text = _render_plan_files(self._project_root, relevant_files)
            grep_text = _render_plan_grep(
                self._project_root, keywords, extensions, self._exclude_dirs,
            )
            constraints_text = _render_plan_constraints(self._architecture_constraints)
            context_sections = {
                "skeleton": skeleton_text,
                "plan_files": files_text,
                "grep": grep_text,
                "constraints": constraints_text,
            }
            self._bus.publish(PlanContextLoaded(
                payload={
                    "issue": issue_number,
                    "evt": "plan_context_load",
                    "skeleton_tokens": len(skeleton_text) // 4,
                    "relevant_files_count": len(relevant_files),
                    "grep_hits": grep_text.count("\n###"),
                    "total_context_tokens": sum(len(v) for v in context_sections.values()) // 4,
                },
                correlation_id=correlation_id,
            ))

        prompt = _build_plan_prompt(issue, context_sections=context_sections)
        tools_loaded = sorted({type(b).__name__ for b in self._skeleton_builders})
        llm_context_sections = sorted([k for k, v in context_sections.items() if v])
        llm_response = self._llm.complete(
            [{"role": "user", "content": prompt}],
            task="planning",
            guards=["prompt_guards", "plan_validator"],
            tools_loaded=tools_loaded,
            context_sections=llm_context_sections,
        )
        plan_text = llm_response.text

        result = validate_plan(
            plan_text,
            project_root=self._project_root,
            issue_body=issue.body,
        )

        if result["score"] < 50:
            self._bus.publish(PlanBlocked(
                payload={
                    "issue": issue_number,
                    "score": result["score"],
                    "failures": result["failures"],
                },
                correlation_id=correlation_id,
            ))
            return result

        # #238: Plan-Pre-Check (Skeleton + AC-Dry-Run + Complexity) tokenfrei.
        # Skeleton wird aus #237-Builders gerendert; bei None graceful (Score 100).
        pre_check_skeleton = self._build_skeleton_dict()
        pre_check = _run_plan_pre_check(
            self._bus, plan_text, issue_number, correlation_id,
            skeleton=pre_check_skeleton,
            project_root=self._project_root,
            issue_body=issue.body,
            retry_attempt=0,
            complexity_thresholds=self._complexity_thresholds,
        )
        self._bus.publish(PlanPreCheckCompleted(
            payload={
                "issue":              issue_number,
                "evt":                "plan_pre_check",
                "structural_score":   pre_check["structural_score"],
                "skeleton_score":     pre_check["skeleton_score"],
                "ac_dry_run_score":   pre_check["ac_dry_run_score"],
                "coverage_score":     pre_check.get("coverage_score", 100),
                "coverage_missing":   pre_check.get("coverage_missing", []),
                "blocking_failures":  pre_check["blocking_failures"],
                "retry_attempt":      0,
                "overall_pass":       pre_check["overall_pass"],
                "complexity":         pre_check["complexity"],
            },
            correlation_id=correlation_id,
        ))
        if pre_check["complexity"]["recommendation"] in ("warn", "split_recommended"):
            self._bus.publish(PlanComplexityWarn(
                payload={
                    "issue":                 issue_number,
                    "evt":                   "complexity_warn",
                    "ac_count":              pre_check["complexity"]["ac_count"],
                    "file_count":            pre_check["complexity"]["file_count"],
                    "slice_count":           pre_check["complexity"]["slice_count"],
                    "pflicht_bereich_count": pre_check["complexity"]["pflicht_bereich_count"],
                    "recommendation":        pre_check["complexity"]["recommendation"],
                },
                correlation_id=correlation_id,
            ))

        if result["score"] < 80 or not pre_check["overall_pass"]:
            self._bus.publish(PlanRetry(
                payload={
                    "issue": issue_number,
                    "score": result["score"],
                    "failures": result["failures"],
                },
                correlation_id=correlation_id,
            ))

            pre_check_hints: list[str] = list(pre_check["blocking_failures"])
            if pre_check["complexity"]["recommendation"] == "split_recommended":
                c = pre_check["complexity"]
                pre_check_hints.append(
                    f"Issue zu gross, splitten oder ACs reduzieren: "
                    f"ac={c['ac_count']} slices={c['slice_count']} pflicht={c['pflicht_bereich_count']}"
                )
            retry_prompt = _build_retry_prompt(
                prompt, result["failures"], result["warnings"],
                pre_check_hints=pre_check_hints,
            )
            retry_response = self._llm.complete(
                [{"role": "user", "content": retry_prompt}],
                task="planning_retry",
                guards=["prompt_guards", "plan_validator", "plan_retry"],
            )
            retry_text = retry_response.text
            retry_result = validate_plan(
                retry_text,
                project_root=self._project_root,
                issue_body=issue.body,
            )

            if retry_result["score"] > result["score"]:
                plan_text = retry_text
                result = retry_result
                self._bus.publish(PlanRevised(
                    payload={
                        "issue": issue_number,
                        "old_score": result["score"],
                        "new_score": retry_result["score"],
                    },
                    correlation_id=correlation_id,
                ))

            # Re-run pre-check on retry result.
            pre_check2 = _run_plan_pre_check(
                self._bus, plan_text, issue_number, correlation_id,
                skeleton=pre_check_skeleton,
                project_root=self._project_root,
                issue_body=issue.body,
                retry_attempt=1,
                complexity_thresholds=self._complexity_thresholds,
            )
            self._bus.publish(PlanPreCheckCompleted(
                payload={
                    "issue":              issue_number,
                    "evt":                "plan_pre_check",
                    "structural_score":   pre_check2["structural_score"],
                    "skeleton_score":     pre_check2["skeleton_score"],
                    "ac_dry_run_score":   pre_check2["ac_dry_run_score"],
                    "blocking_failures":  pre_check2["blocking_failures"],
                    "retry_attempt":      1,
                    "overall_pass":       pre_check2["overall_pass"],
                    "complexity":         pre_check2["complexity"],
                },
                correlation_id=correlation_id,
            ))

            if result["score"] < 50 or (
                pre_check2["complexity"]["recommendation"] == "split_recommended"
                and not pre_check2["overall_pass"]
            ):
                self._bus.publish(PlanBlocked(
                    payload={
                        "issue": issue_number,
                        "score": result["score"],
                        "failures": result["failures"],
                        "evt": "plan_pre_check_blocked",
                        "reason": (
                            "complexity_split_recommended"
                            if pre_check2["complexity"]["recommendation"] == "split_recommended"
                            else "score_too_low"
                        ),
                    },
                    correlation_id=correlation_id,
                ))
                return result

        metadata_block = _build_metadata_block(
            issue_number=issue_number,
            score=result["score"],
            checks_passed=result["checks_passed"],
            checks_total=result["checks_total"],
        )
        comment_body = (
            f"## Plan für Issue #{issue_number}\n\n"
            f"{plan_text}\n\n"
            f"---\n\n"
            f"{metadata_block}"
        )
        self._scm.post_comment(issue_number, comment_body)

        self._bus.publish(PlanPosted(
            payload={"issue": issue_number},
            correlation_id=correlation_id,
        ))

        self._bus.publish(PlanValidated(
            payload={
                "issue": issue_number,
                "score": result["score"],
                "checks_passed": result["checks_passed"],
                "checks_total": result["checks_total"],
            },
            correlation_id=correlation_id,
        ))

        return result


def _build_metadata_block(
    issue_number: int,
    score: float,
    checks_passed: int,
    checks_total: int,
) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        "## Agent-Metadaten\n"
        f"- **Issue:** #{issue_number}\n"
        f"- **Generated:** {ts}\n"
        f"- **Plan-Score:** {score:.2f}\n"
        f"- **Checks:** {checks_passed}/{checks_total}\n"
        f"- **Generated-By:** S.A.M.U.E.L.@v2"
    )