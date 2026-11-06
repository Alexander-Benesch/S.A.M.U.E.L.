from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from samuel.core import git as core_git
from samuel.core.attribution import decorate_patch
from samuel.core.ports import ILLMProvider
from samuel.core.security_policy import redact_secrets
from samuel.core.types import is_truncated_stop_reason
from samuel.slices.implementation.patch_parser import (
    get_applier,
    parse_patches,
    parse_patches_structured,
    parse_slice_requests,
)
from samuel.slices.implementation.patch_targets import resolve_patch_target
from samuel.slices.implementation.workspace_transaction import (
    WorkspaceRollbackError,
    WorkspaceTransaction,
)

log = logging.getLogger(__name__)

MAX_ROUNDS = 5
MAX_EXCERPT_LINES = 200
# #152: Slice-Request-Loop — Obergrenzen gegen sequentielles Abscannen.
MAX_SLICE_ROUNDS = 3
MAX_SLICE_REQUESTS_PER_ROUND = 5
MAX_APPLY_DIAGNOSTICS = 10
MAX_APPLY_DIAGNOSTIC_DETAIL = 500


def _apply_failure_diagnostic(message: str, target: str) -> dict[str, str]:
    """Return a bounded, redacted description of one rejected patch."""

    detail = re.sub(r"\s+", " ", redact_secrets(str(message))).strip()
    detail = detail[:MAX_APPLY_DIAGNOSTIC_DETAIL] or "apply rejected without detail"
    if detail.startswith("SEARCH not found"):
        code = "search_not_found"
    elif detail.startswith("line range") and "out of bounds" in detail:
        code = "line_range_out_of_bounds"
    elif "validation failed" in detail:
        code = "validation_failed"
    elif detail.endswith("invalid JSON after patch"):
        code = "invalid_json"
    elif detail.endswith("not found"):
        code = "target_not_found"
    else:
        code = "apply_rejected"
    safe_target = re.sub(r"\s+", " ", redact_secrets(str(target))).strip()
    return {
        "code": code,
        "target": safe_target[:240],
        "detail": detail,
    }


def _apply_failure_summary(
    *,
    round_num: int,
    patch_count: int,
    applied_patch_count: int,
    failures: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "kind": "apply_failure",
        "round": round_num,
        "patch_count": patch_count,
        "applied_patch_count": applied_patch_count,
        "apply_failures": failures[:MAX_APPLY_DIAGNOSTICS],
    }


def _build_slice_prompt(base_prompt: str, served_blocks: list[str]) -> str:
    """#152: Prompt fuer die naechste Runde mit den angeforderten Code-Slices."""
    return "\n".join(
        [
            base_prompt,
            "",
            "## Angeforderter Code (SLICE-Antwort)",
            "Hier die angeforderten Zeilen. Liefere jetzt die Patches "
            "(REPLACE LINES / SEARCH/REPLACE / WRITE). Weitere SLICE-Requests nur, "
            "wenn unbedingt noetig — das Budget ist begrenzt.",
            "",
            *served_blocks,
        ]
    )


def _load_file_excerpt_for_patch(
    project_root: Path,
    patch: dict[str, Any],
    *,
    git_control_paths: tuple[Path, ...] = (),
) -> str:
    target, rejection = resolve_patch_target(
        project_root,
        patch.get("file", ""),
        git_control_paths=git_control_paths,
    )
    if target is None:
        return f"(Patchziel abgelehnt: {rejection})"
    rel = target.relative
    file_path = target.path
    if not file_path.exists() or not file_path.is_file():
        return f"(Datei {rel} existiert nicht — nutze `## WRITE: {rel}` Format)"
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"(Datei konnte nicht gelesen werden: {exc})"

    lines = content.splitlines()
    if patch.get("type") == "replace_lines" and patch.get("lines"):
        start, end = patch["lines"]
        context_start = max(1, start - 10)
        context_end = min(len(lines), end + 10)
    elif patch.get("search"):
        search_first = patch["search"].splitlines()[0] if patch["search"] else ""
        hit = None
        for i, line in enumerate(lines, start=1):
            if search_first and search_first.strip() in line:
                hit = i
                break
        if hit:
            context_start = max(1, hit - 10)
            context_end = min(len(lines), hit + 30)
        else:
            context_start = 1
            context_end = min(len(lines), MAX_EXCERPT_LINES)
    else:
        context_start = 1
        context_end = min(len(lines), MAX_EXCERPT_LINES)

    if context_end - context_start > MAX_EXCERPT_LINES:
        context_end = context_start + MAX_EXCERPT_LINES

    return "\n".join(f"{i:5d} | {lines[i - 1]}" for i in range(context_start, context_end + 1))


def _build_retry_prompt(
    base_prompt: str,
    round_num: int,
    failures_with_patches: list[tuple[str, dict[str, Any]]],
    project_root: Path,
    *,
    git_control_paths: tuple[Path, ...] = (),
) -> str:
    seen_files: set[str] = set()
    excerpts: list[str] = []
    fail_lines: list[str] = []
    for msg, patch in failures_with_patches:
        fail_lines.append(msg)
        target, _ = resolve_patch_target(
            project_root,
            patch.get("file", ""),
            git_control_paths=git_control_paths,
        )
        if target is not None and target.relative not in seen_files:
            rel = target.relative
            seen_files.add(rel)
            excerpt = _load_file_excerpt_for_patch(
                project_root,
                patch,
                git_control_paths=git_control_paths,
            )
            if excerpt:
                excerpts.append(f"### {rel} (aktueller Zustand)\n```\n{excerpt}\n```")

    return "\n".join(
        [
            base_prompt,
            "",
            f"## Patch-Fehler in Runde {round_num} — KORRIGIEREN",
            *(f"- {m}" for m in fail_lines),
            "",
            "## Aktueller Quellcode der betroffenen Dateien",
            "Nutze die gezeigten Zeilennummern exakt. REPLACE LINES mit genau diesen Nummern, "
            "oder SEARCH mit genau diesem Text.",
            "",
            *excerpts,
        ]
    )


def _finalize_result(result: dict[str, Any], transaction: WorkspaceTransaction) -> dict[str, Any]:
    if result.get("success"):
        transaction.commit()
        return result

    applied_before_rollback = len(result.get("patches_applied", []))
    rollback = transaction.rollback()
    result["rollback"] = rollback
    result["patches_rolled_back"] = (
        applied_before_rollback if rollback["status"] == "completed" else 0
    )
    if rollback["status"] in {"completed", "not_needed"}:
        result["patches_applied"] = []
        return result

    trigger_reason = str(result.get("reason") or "unknown")
    result["trigger_reason"] = trigger_reason
    result["reason"] = "workspace_rollback_failed"
    failures = list(result.get("failures") or [])
    if "workspace_rollback_failed" not in failures:
        failures.append("workspace_rollback_failed")
    result["failures"] = failures
    return result


def run_llm_loop(
    llm: ILLMProvider,
    prompt: str,
    project_root: Path,
    *,
    on_round: Any = None,
    on_token_limit: Any = None,
    llm_kwargs: dict[str, Any] | None = None,
    attribution: dict[str, Any] | None = None,
    slice_resolver: Any = None,
    on_prompt: Any = None,
) -> dict[str, Any]:
    transaction = WorkspaceTransaction()
    try:
        result = _run_llm_loop(
            llm,
            prompt,
            project_root,
            on_round=on_round,
            llm_kwargs=llm_kwargs,
            attribution=attribution,
            slice_resolver=slice_resolver,
            on_prompt=on_prompt,
            transaction=transaction,
        )
    except Exception as exc:
        rollback = transaction.rollback()
        if rollback["status"] == "failed":
            raise WorkspaceRollbackError(
                trigger_reason=type(exc).__name__,
                rollback=rollback,
            ) from exc
        raise
    except BaseException:
        rollback = transaction.rollback()
        if rollback["status"] == "failed":
            log.critical(
                "Workspace rollback while propagating process-control signal failed "
                "(%d failure(s))",
                rollback["failures"],
            )
        raise

    result = _finalize_result(result, transaction)
    trigger_reason = str(result.get("trigger_reason") or result.get("reason") or "")
    if trigger_reason == "token_limit" and on_token_limit:
        on_token_limit(
            int(result.get("round", 0)),
            int(result.get("input_tokens", 0)) + int(result.get("output_tokens", 0)),
            result["rollback"],
        )
    return result


def _run_llm_loop(
    llm: ILLMProvider,
    prompt: str,
    project_root: Path,
    *,
    on_round: Any = None,
    llm_kwargs: dict[str, Any] | None = None,
    attribution: dict[str, Any] | None = None,
    slice_resolver: Any = None,
    on_prompt: Any = None,
    transaction: WorkspaceTransaction,
) -> dict[str, Any]:
    # #152: ``slice_resolver(rel, start, end) -> str|None`` (vom Handler gebaut)
    # loest ``SLICE: rel:start-end``-Anforderungen auf. None -> Loop unveraendert.
    # #270: ``attribution`` (vom Handler gebaut, gated auf das Feature-Flag
    # ``llm_attribution``) traegt ``{enabled, verbosity, version, issue, date}``.
    # Ist es aktiv, wird jeder Patch vor dem Apply mit einem Inline-Marker
    # dekoriert; schlaegt der markierte Apply fehl (z.B. .py-AST-Validierung),
    # faellt die Schleife auf den unmarkierten Patch zurueck — die
    # Kennzeichnung darf nie einen sonst gueltigen Patch verwerfen.
    attr = attribution if (attribution and attribution.get("enabled")) else None
    all_patches_applied: list[dict] = []
    last_round_failures: list[str] = []
    last_round_apply_diagnostics: list[dict[str, str]] = []
    terminal_reason: str | None = None
    terminal_diagnostic: dict[str, Any] | None = None
    total_input_tokens = 0
    total_output_tokens = 0
    current_prompt = prompt
    base_kwargs = dict(llm_kwargs or {})
    git_control_paths = core_git.git_control_plane_paths(project_root)

    # #319: Round-Statistik fuer Self-Mode-Health-Metriken (samuel.adapters.llm.metering
    # publisht LLMCallCompleted, aber pro-round patches_applied/failed war bisher nicht
    # aggregiert. Hier sammeln, im Result returnen, handler schreibt jsonl).
    rounds_stats: list[dict[str, int]] = []
    consecutive_zero_progress = 0
    last_model = ""
    # #152: Slice-Loop-Status (Anti-sequential-scan).
    slice_rounds_used = 0
    served_slices: set[tuple[str, int, int]] = set()

    round_num = 0
    for round_num in range(1, MAX_ROUNDS + 1):
        if on_prompt:
            on_prompt(round_num, current_prompt)
        response = llm.complete(
            [{"role": "user", "content": current_prompt}],
            **base_kwargs,
        )
        total_input_tokens += response.input_tokens
        total_output_tokens += response.output_tokens
        last_model = response.model_used or last_model

        if is_truncated_stop_reason(response.stop_reason):
            return {
                "success": False,
                "reason": "token_limit",
                "round": round_num,
                "patches_applied": all_patches_applied,
                "failures": last_round_failures,
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "rounds_stats": rounds_stats,
                "model": last_model,
            }

        # #335: Strukturierten Output bevorzugen, wenn der Provider JSON
        # geliefert hat (response.structured); bei leerem/unbrauchbarem JSON
        # graceful auf den Freitext-Parser zurueckfallen.
        patches = parse_patches_structured(response.structured) if response.structured else []
        if not patches:
            patches = parse_patches(response.text)
        if not patches:
            # #152: Bevor wir aufgeben — fordert der LLM gezielt Code an
            # (SLICE: rel:start-end)? Dann aufloesen und naechste Runde damit
            # anreichern (max. MAX_SLICE_ROUNDS, dedupliziert gegen Re-Scan).
            if slice_resolver is not None and slice_rounds_used < MAX_SLICE_ROUNDS:
                reqs = parse_slice_requests(response.text)
                fresh = [r for r in reqs if r not in served_slices][:MAX_SLICE_REQUESTS_PER_ROUND]
                served_blocks: list[str] = []
                for rel, start, end in fresh:
                    served_slices.add((rel, start, end))
                    try:
                        block = slice_resolver(rel, start, end)
                    except Exception:
                        log.exception("slice_resolver failed for %s:%d-%d", rel, start, end)
                        block = None
                    if block:
                        served_blocks.append(block)
                if served_blocks:
                    slice_rounds_used += 1
                    rounds_stats.append(
                        {
                            "round": round_num,
                            "patches_total": 0,
                            "applied": 0,
                            "failed": 0,
                            "slices_served": len(served_blocks),
                        }
                    )
                    current_prompt = _build_slice_prompt(prompt, served_blocks)
                    log.info(
                        "Runde %d: %d SLICE-Request(s) bedient, Retry",
                        round_num,
                        len(served_blocks),
                    )
                    continue
            log.info("Runde %d: LLM lieferte keine parsbaren Patches", round_num)
            rounds_stats.append(
                {
                    "round": round_num,
                    "patches_total": 0,
                    "applied": 0,
                    "failed": 0,
                }
            )
            terminal_reason = "no_parseable_patches"
            terminal_diagnostic = {
                "round": round_num,
                "patch_count": 0,
                "applied_patch_count": len(all_patches_applied),
            }
            last_round_failures = [terminal_reason]
            break

        resolved_patches: list[tuple[dict[str, Any], Path]] = []
        rejection_codes: list[str] = []
        for patch in patches:
            target, rejection = resolve_patch_target(
                project_root,
                patch.get("file", ""),
                git_control_paths=git_control_paths,
            )
            if target is None:
                rejection_codes.append(rejection or "resolution_error")
                continue
            normalized_patch = dict(patch)
            normalized_patch["file"] = target.relative
            resolved_patches.append((normalized_patch, target.path))

        if rejection_codes:
            unique_codes = sorted(set(rejection_codes))
            rounds_stats.append(
                {
                    "round": round_num,
                    "patches_total": len(patches),
                    "applied": 0,
                    "failed": len(rejection_codes),
                }
            )
            if on_round:
                on_round(round_num, len(patches), len(rejection_codes))
            terminal_reason = "unsafe_patch_target"
            terminal_diagnostic = {
                "round": round_num,
                "patch_count": len(patches),
                "rejected_patch_count": len(rejection_codes),
                "rejection_codes": unique_codes,
            }
            last_round_failures = [f"patch_target_rejected:{code}" for code in unique_codes]
            break

        round_failures_with_patches: list[tuple[str, dict[str, Any]]] = []
        round_failures: list[str] = []
        round_apply_diagnostics: list[dict[str, str]] = []
        round_applied_count = 0
        for patch, file_path in resolved_patches:
            rel = patch["file"]
            applier = get_applier(file_path)
            transaction.capture(file_path)

            candidate = patch
            if attr and response.model_used:
                candidate = decorate_patch(
                    patch,
                    model=response.model_used,
                    date=attr.get("date", ""),
                    verbosity=attr.get("verbosity", "minimal"),
                    version=attr.get("version", ""),
                    issue=attr.get("issue"),
                )
            results = applier.apply(file_path, [candidate])
            ok = bool(results and results[0][0])
            if not ok and candidate is not patch:
                # Marker hat den sonst gueltigen Patch gebrochen -> unmarkiert.
                candidate = patch
                results = applier.apply(file_path, [patch])
                ok = bool(results and results[0][0])
            if ok:
                all_patches_applied.append(candidate)
                round_applied_count += 1
            else:
                transaction.release_if_unchanged(file_path)
                msg = results[0][1] if results else f"unknown error for {rel}"
                round_failures.append(msg)
                round_failures_with_patches.append((msg, patch))
                round_apply_diagnostics.append(_apply_failure_diagnostic(msg, rel))

        last_round_failures = round_failures
        last_round_apply_diagnostics = round_apply_diagnostics
        rounds_stats.append(
            {
                "round": round_num,
                "patches_total": len(patches),
                "applied": round_applied_count,
                "failed": len(round_failures),
            }
        )

        if on_round:
            on_round(round_num, len(patches), len(round_failures))

        if not round_failures:
            break

        # #319: Hard-Stop wenn 2 consecutive rounds 0 patches applied — Operator
        # hatte bislang manuell "killen" muessen ("manuell schneller"-Pattern,
        # 3/17 Operator-Killed in der Session-Statistik). System uebernimmt das jetzt.
        if round_applied_count == 0:
            consecutive_zero_progress += 1
        else:
            consecutive_zero_progress = 0

        if consecutive_zero_progress >= 2 and round_num >= 2:
            log.error(
                "Self-Mode aborted: %d consecutive rounds with 0 patches applied "
                "(rounds %d-%d). Plan vermutlich zu komplex oder Patches matchen "
                "nicht — Operator-Eingriff empfohlen.",
                consecutive_zero_progress,
                round_num - 1,
                round_num,
            )
            diagnostic = _apply_failure_summary(
                round_num=round_num,
                patch_count=len(patches),
                applied_patch_count=round_applied_count,
                failures=last_round_apply_diagnostics,
            )
            return {
                "success": False,
                "reason": "no_progress",
                "round": round_num,
                "patches_applied": all_patches_applied,
                "failures": [item["detail"] for item in last_round_apply_diagnostics],
                "diagnostic": diagnostic,
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "rounds_stats": rounds_stats,
                "model": last_model,
            }

        current_prompt = _build_retry_prompt(
            prompt,
            round_num,
            round_failures_with_patches,
            project_root,
            git_control_paths=git_control_paths,
        )
        log.info(
            "Runde %d fehlgeschlagen (%d Patches), Retry mit echtem Code",
            round_num,
            len(round_failures),
        )

    result: dict[str, Any] = {
        "success": len(last_round_failures) == 0 and len(all_patches_applied) > 0,
        "reason": terminal_reason or ("complete" if not last_round_failures else "partial_failure"),
        "round": min(round_num, MAX_ROUNDS) if round_num else 0,
        "patches_applied": all_patches_applied,
        "failures": last_round_failures,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "rounds_stats": rounds_stats,
        "model": last_model,
    }
    if terminal_diagnostic is None and last_round_apply_diagnostics:
        terminal_diagnostic = _apply_failure_summary(
            round_num=min(round_num, MAX_ROUNDS) if round_num else 0,
            patch_count=rounds_stats[-1]["patches_total"] if rounds_stats else 0,
            applied_patch_count=rounds_stats[-1]["applied"] if rounds_stats else 0,
            failures=last_round_apply_diagnostics,
        )
        result["failures"] = [item["detail"] for item in last_round_apply_diagnostics]
    if terminal_diagnostic is not None:
        result["diagnostic"] = terminal_diagnostic
    return result
