from __future__ import annotations

import importlib
import logging
import re
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from samuel.core.acceptance import (
    ACCEPTANCE_STATUSES,
    AcceptanceContract,
    AcceptanceEvidence,
    AcceptanceResult,
    parse_acceptance_contract,
    parse_grep_criterion_argument,
    parse_test_criterion_argument,
)
from samuel.core.bus import Bus
from samuel.core.commands import Command, VerifyACCommand
from samuel.core.config import EvalSchema
from samuel.core.events import ACFailed, ACManualPending, ACVerified, TestRunCompleted
from samuel.core.ports import IWorkspaceManager
from samuel.core.process_environment import (
    VERIFIER_ENVIRONMENT_PROFILE,
    verifier_process_environment,
)
from samuel.core.project_files import (
    CODE_EXTENSIONS,
    CONFIG_EXTENSIONS,
    iter_project_files,
)
from samuel.core.security_policy import redact_secrets
from samuel.core.test_runner import (
    DEFAULT_TEST_RUNNER_POLICY as _DEFAULT_TEST_RUNNER_POLICY,
)
from samuel.core.test_runner import (
    VerifierRunnerPolicy,
)
from samuel.core.test_runner import (
    check_test_readiness as _check_test_readiness,
)
from samuel.core.test_runner import (
    resolve_test_runner as _resolve_test_runner,
)
from samuel.core.workspaces import WorkspaceError

log = logging.getLogger(__name__)

ACHandler = Callable[[str, Path | None], dict[str, Any]]

_AC_REGISTRY: dict[str, ACHandler] = {}

_SAFE_IMPORT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.]*$")
_SAFE_PATH_RE = re.compile(r"^[a-zA-Z0-9_./ -]+$")
# #417: These checks describe the desired post-implementation state.  Running
# them while a plan is merely being validated creates false ACFailed events
# for code that cannot exist yet.  DIFF/EXISTS remain useful at plan time to
# validate referenced paths; all deferred checks run normally after codegen.
_PLAN_DEFERRED_TAGS = frozenset({"IMPORT", "GREP", "GREP:NOT", "TEST", "MANUAL"})


def register_ac_handler(tag: str, handler: ACHandler) -> None:
    _AC_REGISTRY[tag] = handler


def _sanitize_path(arg: str, project_root: Path) -> Path | None:
    cleaned = arg.strip().replace("..", "")
    if not _SAFE_PATH_RE.match(cleaned):
        return None
    resolved = (project_root / cleaned).resolve()
    if not str(resolved).startswith(str(project_root.resolve())):
        return None
    return resolved


def _check_diff(arg: str, project_root: Path | None) -> dict[str, Any]:
    if not project_root:
        return {"passed": False, "reason": "no project root"}
    path = _sanitize_path(arg, project_root)
    if path is None:
        return {
            "passed": False,
            "status": "error",
            "reason": f"path rejected (traversal blocked): {arg}",
        }
    return {
        "passed": path.exists(),
        "reason": f"{'exists' if path.exists() else 'not found'}: {arg}",
    }


def _check_exists(arg: str, project_root: Path | None) -> dict[str, Any]:
    if not project_root:
        return {"passed": False, "reason": "no project root"}
    path = _sanitize_path(arg, project_root)
    if path is None:
        return {
            "passed": False,
            "status": "error",
            "reason": f"path rejected (traversal blocked): {arg}",
        }
    return {
        "passed": path.exists(),
        "reason": f"{'exists' if path.exists() else 'not found'}: {arg}",
    }


def _check_import(arg: str, project_root: Path | None) -> dict[str, Any]:
    module_name = arg.strip()
    if not _SAFE_IMPORT_RE.match(module_name):
        return {"passed": False, "reason": f"import rejected (invalid chars): {arg}"}
    if any(
        dangerous in module_name for dangerous in ("os", "sys", "subprocess", "shutil", "pathlib")
    ):
        return {"passed": False, "reason": f"import rejected (blocked module): {arg}"}
    try:
        importlib.import_module(module_name)
        return {"passed": True, "reason": f"importable: {module_name}"}
    except ImportError as exc:
        return {"passed": False, "reason": f"import failed: {exc}"}


def _check_import_at_candidate(arg: str, project_root: Path | None) -> dict[str, Any]:
    """Import in a fresh interpreter rooted at the immutable candidate."""

    if not project_root:
        return {"passed": False, "status": "error", "reason": "no candidate root"}
    module_name = arg.strip()
    if not _SAFE_IMPORT_RE.fullmatch(module_name) or any(
        dangerous in module_name for dangerous in ("os", "sys", "subprocess", "shutil", "pathlib")
    ):
        return {"passed": False, "status": "error", "reason": f"import rejected: {arg}"}
    try:
        with verifier_process_environment(sys.executable) as environment:
            proc = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import importlib,sys; importlib.import_module(sys.argv[1])",
                    module_name,
                ],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=30,
                shell=False,
                check=False,
                env=environment,
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "passed": False,
            "status": "error",
            "reason": f"candidate import verifier error ({type(exc).__name__})",
            "process_environment_profile": VERIFIER_ENVIRONMENT_PROFILE,
        }
    return {
        "passed": proc.returncode == 0,
        "reason": (
            f"importable at candidate: {module_name}"
            if proc.returncode == 0
            else f"import failed at candidate: {module_name}"
        ),
        "exit_code": proc.returncode,
        "process_environment_profile": VERIFIER_ENVIRONMENT_PROFILE,
    }


def _check_grep(arg: str, project_root: Path | None) -> dict[str, Any]:
    """#236: sprachneutral via iter_project_files (CODE+CONFIG-Extensions).
    Vorher rglob("*.py") — Python-only. Jetzt deckt .go/.ts/.json/.yaml etc."""
    if not project_root:
        return {"passed": False, "reason": "no project root"}
    pattern = arg.strip().strip('"').strip("'")
    extensions = CODE_EXTENSIONS | CONFIG_EXTENSIONS
    for src_file in iter_project_files(project_root, extensions=extensions):
        try:
            if pattern in src_file.read_text(encoding="utf-8", errors="replace"):
                try:
                    rel: Path | str = src_file.relative_to(project_root)
                except ValueError:
                    try:
                        rel = src_file.relative_to(project_root.resolve())
                    except ValueError:
                        rel = src_file.name
                return {
                    "passed": True,
                    "reason": f"found in {rel}",
                    "matched_file": str(rel),
                }
        except OSError:
            continue
    return {"passed": False, "reason": f"pattern not found: {pattern}"}


def _check_grep_not(arg: str, project_root: Path | None) -> dict[str, Any]:
    result = _check_grep(arg, project_root)
    return {
        "passed": not result["passed"],
        "reason": result["reason"].replace("found", "still present")
        if result["passed"]
        else f"confirmed absent: {arg.strip()}",
        "matched_file": result.get("matched_file"),
    }


def _check_manual(arg: str, project_root: Path | None) -> dict[str, Any]:
    return {
        "passed": None,
        "status": "manual_pending",
        "reason": f"manual check required: {arg}",
        "manual": True,
    }


def _check_test(
    arg: str,
    project_root: Path | None,
    policy: VerifierRunnerPolicy = _DEFAULT_TEST_RUNNER_POLICY,
) -> dict[str, Any]:
    policy_evidence = {
        "runner_policy_source": policy.source,
        "runner_policy_version": policy.policy_version,
    }
    if not project_root:
        return {"passed": False, "reason": "no project root", **policy_evidence}
    try:
        test_name = parse_test_criterion_argument(arg)
    except ValueError as exc:
        return {
            "passed": False,
            "status": "error",
            "reason": str(exc),
            **policy_evidence,
        }
    if "::" in test_name:
        test_path = _sanitize_path(test_name.split("::", 1)[0], project_root)
        if test_path is None:
            return {
                "passed": False,
                "status": "error",
                "reason": f"pytest node id rejected: {arg}",
                **policy_evidence,
            }
    try:
        resolved = _resolve_test_runner(project_root, test_name, policy)
    except (ValueError, OSError) as exc:
        return {
            "passed": False,
            "status": "missing_evidence",
            "reason": str(exc),
            **policy_evidence,
        }
    if resolved is None:
        return {
            "passed": False,
            "status": "missing_evidence",
            "manual": True,
            "reason": (
                "no test runner configured in control-plane eval.json "
                "and no supported project marker found"
            ),
            "runner": "none",
            **policy_evidence,
        }
    cmd, timeout, runner = resolved
    if policy.verifier_toolchain is not None:
        policy_evidence["toolchain_sha256"] = policy.verifier_toolchain.sha256

    t0 = time.monotonic()
    try:
        with verifier_process_environment(cmd[0]) as environment:
            proc = subprocess.run(
                cmd,
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
                check=False,
                env=environment,
            )
    except FileNotFoundError:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return {
            "passed": False,
            "status": "error",
            "reason": f"test runner binary not found: {cmd[0]}",
            "runner": runner,
            "duration_ms": duration_ms,
            "exit_code": None,
            "output_excerpt": "",
            "process_environment_profile": VERIFIER_ENVIRONMENT_PROFILE,
            **policy_evidence,
        }
    except subprocess.TimeoutExpired:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return {
            "passed": False,
            "status": "error",
            "reason": f"test timeout after {timeout}s: {test_name}",
            "runner": runner,
            "duration_ms": duration_ms,
            "exit_code": None,
            "output_excerpt": "",
            "process_environment_profile": VERIFIER_ENVIRONMENT_PROFILE,
            **policy_evidence,
        }
    except OSError as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return {
            "passed": False,
            "status": "error",
            "reason": f"test runner OS error ({type(exc).__name__})",
            "runner": runner,
            "duration_ms": duration_ms,
            "exit_code": None,
            "output_excerpt": "",
            "process_environment_profile": VERIFIER_ENVIRONMENT_PROFILE,
            **policy_evidence,
        }

    duration_ms = int((time.monotonic() - t0) * 1000)
    output_excerpt = redact_secrets((proc.stdout or proc.stderr or "")[-500:])
    if proc.returncode == 0:
        return {
            "passed": True,
            "reason": f"tests passed: {test_name} ({runner})",
            "runner": runner,
            "duration_ms": duration_ms,
            "exit_code": 0,
            "output_excerpt": output_excerpt,
            "process_environment_profile": VERIFIER_ENVIRONMENT_PROFILE,
            **policy_evidence,
        }
    return {
        "passed": False,
        "reason": f"tests failed: {test_name} (exit={proc.returncode})",
        "runner": runner,
        "duration_ms": duration_ms,
        "exit_code": proc.returncode,
        "output_excerpt": output_excerpt,
        "process_environment_profile": VERIFIER_ENVIRONMENT_PROFILE,
        **policy_evidence,
    }


def _automatic_evidence(tag: str, arg: str, result: dict[str, Any]) -> dict[str, Any] | None:
    """Build bounded verifier evidence for the immutable candidate result."""

    passed = result.get("passed")
    if not isinstance(passed, bool):
        return None
    common: dict[str, Any] = {"schema_version": 1, "kind": tag.lower()}
    if tag == "DIFF":
        return {**common, "path": arg, "changed": passed}
    if tag == "EXISTS":
        return {**common, "path": arg, "exists": passed}
    if tag == "IMPORT":
        return {
            **common,
            "module": arg,
            "importable": passed,
            "exit_code": result.get("exit_code"),
            "process_environment_profile": str(
                result.get("process_environment_profile", "unknown")
            ),
        }
    if tag == "GREP":
        return {
            **common,
            "pattern": arg,
            "found": passed,
            "matched_file": result.get("matched_file"),
        }
    if tag == "GREP:NOT":
        return {
            **common,
            "pattern": arg,
            "absent": passed,
            "matched_file": result.get("matched_file"),
        }
    if tag == "TEST":
        exit_code = result.get("exit_code")
        if not isinstance(exit_code, int):
            return None
        return {
            **common,
            "test_name": arg,
            "runner": str(result.get("runner", "unknown")),
            "exit_code": exit_code,
            "duration_ms": int(result.get("duration_ms", 0)),
            "output_excerpt": str(result.get("output_excerpt", ""))[:500],
            "runner_policy_source": str(result.get("runner_policy_source", "unknown")),
            "runner_policy_version": str(result.get("runner_policy_version", "unknown")),
            "process_environment_profile": str(
                result.get("process_environment_profile", "unknown")
            ),
        }
    return None


register_ac_handler("DIFF", _check_diff)
register_ac_handler("EXISTS", _check_exists)
register_ac_handler("IMPORT", _check_import)
register_ac_handler("GREP", _check_grep)
register_ac_handler("GREP:NOT", _check_grep_not)
register_ac_handler("MANUAL", _check_manual)
register_ac_handler("TEST", _check_test)


AC_PATTERN = re.compile(r"- \[.\] \[([A-Z:]+)\]\s*(.+)")


def _extract_arg(tag: str, rest_raw: str) -> str:
    """#236: Tag-spezifische Argument-Extraktion.

    Vorher griff handle() einfach ``match.group(2).strip()`` — das saugt den
    ganzen Rest der Zeile inklusive Em-Dash-Beschreibung ein und _sanitize_path
    lehnt das wegen Em-Dash ab.

    Regeln pro Tag:
    - DIFF/EXISTS/IMPORT: erstes Whitespace-getrenntes Token
    - GREP/GREP:NOT: quoted string or Markdown inline code — wrapper stripped
    - TEST: bis zum ersten Trenner ( — , – , : , -- ) oder Zeilenende
    - MANUAL: ganze Restzeile (Beschreibung ist hier inhaltlich der Punkt)
    """
    rest = rest_raw.strip()
    if tag in ("DIFF", "EXISTS", "IMPORT"):
        token = rest.split()[0] if rest else ""
        # The planner may render one path/module token as Markdown inline
        # code.  The contract hash remains bound to the exact plan text; only
        # the verifier argument is normalized before the existing strict path
        # or import validation runs (#863).
        if len(token) >= 2 and token.startswith("`") and token.endswith("`"):
            token = token[1:-1]
        return token
    if tag in ("GREP", "GREP:NOT"):
        return parse_grep_criterion_argument(rest)
    if tag == "TEST":
        return parse_test_criterion_argument(rest)
    if tag == "MANUAL":
        return rest
    return rest


class ACVerificationHandler:
    def __init__(
        self,
        bus: Bus,
        project_root: Path | None = None,
        eval_config: EvalSchema | None = None,
        workspace_manager: IWorkspaceManager | None = None,
    ) -> None:
        self._bus = bus
        self._root = project_root
        self._test_runner_policy = VerifierRunnerPolicy.from_eval_config(
            eval_config or EvalSchema()
        )
        self._workspace_manager = workspace_manager

    @contextmanager
    def _candidate_root(
        self,
        head_sha: str,
        correlation_id: str = "",
    ) -> Iterator[tuple[Path | None, str]]:
        """Yield an isolated checkout of exactly ``head_sha`` or an error.

        Automatic checks may execute imports and test runners.  A detached
        worktree prevents an uncommitted or moved local branch from becoming
        acceptance evidence for a different candidate.
        """

        if self._root is None:
            yield None, "no project root"
            return
        if self._workspace_manager is not None:
            workspace_id = f"verification:{correlation_id or head_sha}:{head_sha}"
            try:
                handle = self._workspace_manager.acquire_verification(
                    repository_root=self._root,
                    workspace_id=workspace_id,
                    head_sha=head_sha,
                )
            except WorkspaceError as exc:
                yield None, exc.code
                return
            try:
                yield handle.path, ""
            finally:
                self._workspace_manager.release(handle.workspace_id)
            return
        with TemporaryDirectory(prefix="samuel-ac-") as temp_parent:
            worktree = Path(temp_parent) / "candidate"
            added = False
            try:
                proc = subprocess.run(
                    ["git", "worktree", "add", "--detach", str(worktree), head_sha],
                    cwd=str(self._root),
                    capture_output=True,
                    text=True,
                    timeout=60,
                    shell=False,
                    check=False,
                )
                if proc.returncode != 0:
                    yield None, "candidate worktree could not be created"
                    return
                added = True
                observed = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=str(worktree),
                    capture_output=True,
                    text=True,
                    timeout=10,
                    shell=False,
                    check=False,
                )
                if observed.returncode != 0 or observed.stdout.strip() != head_sha:
                    yield None, "candidate worktree does not match evidence head"
                    return
                yield worktree, ""
            except (OSError, subprocess.TimeoutExpired):
                yield None, "candidate worktree setup error"
            finally:
                if added:
                    subprocess.run(
                        ["git", "worktree", "remove", "--force", str(worktree)],
                        cwd=str(self._root),
                        capture_output=True,
                        text=True,
                        timeout=30,
                        shell=False,
                        check=False,
                    )

    @staticmethod
    def _manual_result(
        criterion_id: str,
        tag: str,
        arg: str,
        receipt: Any,
        contract_hash: str,
        head_sha: str,
    ) -> dict[str, Any]:
        if not isinstance(receipt, dict):
            return {
                "criterion_id": criterion_id,
                "tag": tag,
                "arg": arg,
                "passed": None,
                "status": "manual_pending",
                "manual": True,
                "reason": f"manual check required: {arg}",
            }
        valid = (
            receipt.get("criterion_id") == criterion_id
            and receipt.get("contract_hash") == contract_hash
            and receipt.get("head_sha") == head_sha
            and bool(receipt.get("actor"))
            and bool(receipt.get("source_id"))
        )
        if not valid:
            return {
                "criterion_id": criterion_id,
                "tag": tag,
                "arg": arg,
                "passed": None,
                "status": "manual_pending",
                "manual": True,
                "reason": "manual receipt is missing or belongs to another subject",
            }
        return {
            "criterion_id": criterion_id,
            "tag": tag,
            "arg": arg,
            "passed": True,
            "status": "passed",
            "manual": True,
            "reason": f"human-approved by {receipt['actor']}",
            "evidence": {"human_receipt": dict(receipt)},
        }

    def _handle_bound(self, cmd: VerifyACCommand, plan_text: str) -> dict[str, Any]:
        assert cmd.subject is not None
        subject = cmd.subject
        try:
            parsed = parse_acceptance_contract(plan_text)
        except ValueError as exc:
            return {
                "verified": False,
                "status": "error",
                "reason": str(exc),
                "results": [],
            }

        supplied_contract = cmd.payload.get("acceptance_contract")
        try:
            contract = (
                AcceptanceContract.from_dict(supplied_contract)
                if isinstance(supplied_contract, dict)
                else parsed
            )
        except ValueError as exc:
            return {"verified": False, "status": "error", "reason": str(exc), "results": []}
        if (
            contract.contract_hash != parsed.contract_hash
            or contract.contract_hash != subject.contract_hash
            or contract.criteria != parsed.criteria
        ):
            return {
                "verified": False,
                "status": "missing_evidence",
                "reason": "acceptance contract does not match evaluation subject",
                "results": [],
            }

        changed_files = {
            str(path) for path in cmd.payload.get("changed_files", []) if isinstance(path, str)
        }
        manual_receipts = cmd.payload.get("manual_receipts", {})
        if not isinstance(manual_receipts, dict):
            manual_receipts = {}
        raw_results: list[dict[str, Any]] = []
        with self._candidate_root(
            subject.head_sha,
            cmd.correlation_id or "",
        ) as (candidate_root, setup_error):
            for criterion in contract.criteria:
                arg = _extract_arg(criterion.tag, criterion.text)
                if criterion.mode == "manual":
                    raw_results.append(
                        self._manual_result(
                            criterion.criterion_id,
                            criterion.tag,
                            arg,
                            manual_receipts.get(criterion.criterion_id),
                            contract.contract_hash,
                            subject.head_sha,
                        )
                    )
                    continue
                if setup_error:
                    raw_results.append(
                        {
                            "criterion_id": criterion.criterion_id,
                            "tag": criterion.tag,
                            "arg": arg,
                            "passed": False,
                            "status": "error",
                            "reason": setup_error,
                        }
                    )
                    continue
                assert candidate_root is not None
                if criterion.tag == "DIFF":
                    path = _sanitize_path(arg, candidate_root)
                    if path is None:
                        result = {
                            "passed": False,
                            "status": "error",
                            "reason": f"path rejected (traversal blocked): {arg}",
                        }
                    else:
                        passed = arg in changed_files
                        result = {
                            "passed": passed,
                            "reason": (
                                f"changed in immutable comparison: {arg}"
                                if passed
                                else f"not changed in immutable comparison: {arg}"
                            ),
                        }
                elif criterion.tag == "IMPORT":
                    result = _check_import_at_candidate(arg, candidate_root)
                elif criterion.tag == "TEST":
                    result = _check_test(arg, candidate_root, self._test_runner_policy)
                else:
                    handler = _AC_REGISTRY.get(criterion.tag)
                    if handler is None:
                        result = {
                            "passed": False,
                            "status": "error",
                            "reason": f"unknown tag: {criterion.tag}",
                        }
                    else:
                        try:
                            result = handler(arg, candidate_root)
                        except Exception as exc:  # noqa: BLE001
                            log.error(
                                "Acceptance criterion %s verifier failed (%s)",
                                criterion.criterion_id,
                                type(exc).__name__,
                            )
                            result = {
                                "passed": False,
                                "status": "error",
                                "reason": f"verifier error ({type(exc).__name__})",
                            }
                status = str(
                    result.get("status") or ("passed" if result.get("passed") else "failed")
                )
                if status not in ACCEPTANCE_STATUSES:
                    result = {
                        **result,
                        "passed": False,
                        "reason": f"unknown verifier status: {status}",
                    }
                    status = "error"
                automatic_evidence = (
                    _automatic_evidence(criterion.tag, arg, result)
                    if status in {"passed", "failed"}
                    else None
                )
                raw_results.append(
                    {
                        **result,
                        "criterion_id": criterion.criterion_id,
                        "tag": criterion.tag,
                        "arg": arg,
                        "status": status,
                        **(
                            {"evidence": automatic_evidence}
                            if automatic_evidence is not None
                            else {}
                        ),
                    }
                )

        for result in raw_results:
            event_payload = {
                "issue": cmd.payload.get("issue"),
                "criterion_id": result["criterion_id"],
                "tag": result["tag"],
                "arg": result["arg"],
                "passed": result.get("passed"),
                "status": result["status"],
                "reason": str(result.get("reason", "")),
                "evaluation_subject": subject.as_dict(),
            }
            if result["tag"] == "TEST":
                self._bus.publish(
                    TestRunCompleted(
                        payload={
                            **event_payload,
                            "test_name": result["arg"],
                            "runner": result.get("runner", "unknown"),
                            "exit_code": result.get("exit_code"),
                            "duration_ms": result.get("duration_ms"),
                            "output_excerpt": result.get("output_excerpt", ""),
                            "process_environment_profile": result.get(
                                "process_environment_profile", "unknown"
                            ),
                        },
                        correlation_id=cmd.correlation_id or "",
                    )
                )
            if result["status"] == "manual_pending":
                event_payload["evt"] = "ac_manual_pending"
                self._bus.publish(
                    ACManualPending(
                        payload=event_payload,
                        correlation_id=cmd.correlation_id or "",
                    )
                )
            elif result["status"] == "passed":
                event_payload["evt"] = "ac_verified"
                self._bus.publish(
                    ACVerified(payload=event_payload, correlation_id=cmd.correlation_id or "")
                )
            else:
                event_payload["evt"] = "ac_failed"
                self._bus.publish(
                    ACFailed(payload=event_payload, correlation_id=cmd.correlation_id or "")
                )

        evidence_results = tuple(
            AcceptanceResult(
                criterion_id=str(result["criterion_id"]),
                status=str(result["status"]),  # type: ignore[arg-type]
                reason=str(result.get("reason", "")),
                tag=str(result["tag"]),
                evidence=result.get("evidence")
                if isinstance(result.get("evidence"), dict)
                else None,
            )
            for result in raw_results
        )
        acceptance_evidence = AcceptanceEvidence(
            schema_version=1,
            subject=subject,
            contract=contract,
            results=evidence_results,
        )
        verified = bool(evidence_results) and all(
            result.status == "passed" for result in evidence_results
        )
        return {
            "verified": verified,
            "status": "passed" if verified else "failed",
            "total": len(raw_results),
            "passed": sum(1 for result in raw_results if result.get("status") == "passed"),
            "manual_pending": sum(
                1 for result in raw_results if result.get("status") == "manual_pending"
            ),
            "results": raw_results,
            "acceptance_evidence": acceptance_evidence.as_dict(),
        }

    def handle(self, cmd: Command) -> Any:
        assert isinstance(cmd, VerifyACCommand)

        plan_text = cmd.payload.get("plan_text", "")
        if not plan_text:
            return {"verified": False, "reason": "no plan text", "results": []}

        if cmd.subject is not None:
            return self._handle_bound(cmd, plan_text)

        issue_number = cmd.payload.get("issue")
        phase = str(cmd.payload.get("phase") or "post_implementation")
        correlation_id = cmd.correlation_id or ""
        results: list[dict[str, Any]] = []
        for match in AC_PATTERN.finditer(plan_text):
            tag = match.group(1)
            # #236: tag-spezifische Argument-Extraktion (ohne Em-Dash-Suffix)
            arg = _extract_arg(tag, match.group(2))
            handler = _AC_REGISTRY.get(tag)
            if handler:
                if phase == "planning" and tag == "TEST":
                    readiness = _check_test_readiness(
                        arg,
                        self._root,
                        self._test_runner_policy,
                    )
                    results.append(
                        {
                            **readiness,
                            "tag": tag,
                            "arg": arg,
                            "passed": None,
                            "runner_ready": bool(readiness.get("passed")),
                            "readiness_status": readiness.get("status", "error"),
                            "deferred": True,
                        }
                    )
                    continue
                if phase == "planning" and tag in _PLAN_DEFERRED_TAGS:
                    results.append(
                        {
                            "tag": tag,
                            "arg": arg,
                            "passed": None,
                            "deferred": True,
                            "reason": "deferred until post-implementation verification",
                        }
                    )
                    continue
                result = (
                    _check_test(arg, self._root, self._test_runner_policy)
                    if tag == "TEST"
                    else handler(arg, self._root)
                )
                if phase == "planning" and not result.get("passed"):
                    results.append(
                        {
                            "tag": tag,
                            "arg": arg,
                            "passed": None,
                            "deferred": True,
                            "reason": (
                                f"not satisfied at plan time; deferred: {result.get('reason', '')}"
                            ),
                        }
                    )
                    continue
                result["tag"] = tag
                result["arg"] = arg
                results.append(result)
                if tag == "TEST":
                    self._bus.publish(
                        TestRunCompleted(
                            payload={
                                "issue": issue_number,
                                "test_name": arg,
                                "runner": result.get("runner", "unknown"),
                                "passed": bool(result.get("passed", False)),
                                "exit_code": result.get("exit_code"),
                                "duration_ms": result.get("duration_ms"),
                                "output_excerpt": result.get("output_excerpt", ""),
                                "process_environment_profile": result.get(
                                    "process_environment_profile", "unknown"
                                ),
                            },
                            correlation_id=correlation_id,
                        )
                    )
                # Automatic pass/fail and human readiness are distinct facts.
                # In particular, MANUAL is never emitted as an automatic
                # failure and a checkbox cannot turn it into a pass (#514).
                status = str(
                    result.get("status") or ("passed" if result.get("passed") else "failed")
                )
                ac_payload = {
                    "issue": issue_number,
                    "tag": tag,
                    "arg": arg,
                    "passed": result.get("passed"),
                    "status": status,
                    "reason": str(result.get("reason", "")),
                    "evt": (
                        "ac_manual_pending"
                        if status == "manual_pending"
                        else "ac_verified"
                        if result.get("passed")
                        else "ac_failed"
                    ),
                }
                if status == "manual_pending":
                    self._bus.publish(
                        ACManualPending(
                            payload=ac_payload,
                            correlation_id=correlation_id,
                        )
                    )
                elif result.get("passed"):
                    self._bus.publish(
                        ACVerified(
                            payload=ac_payload,
                            correlation_id=correlation_id,
                        )
                    )
                else:
                    self._bus.publish(
                        ACFailed(
                            payload=ac_payload,
                            correlation_id=correlation_id,
                        )
                    )
            else:
                results.append(
                    {"tag": tag, "arg": arg, "passed": False, "reason": f"unknown tag: {tag}"}
                )

        passed_count = sum(1 for r in results if r.get("passed"))
        manual_count = sum(1 for r in results if r.get("manual"))
        deferred_count = sum(1 for r in results if r.get("deferred"))
        runner_readiness_failed = sum(1 for r in results if r.get("runner_ready") is False)
        manual_pending = sum(1 for r in results if r.get("status") == "manual_pending")
        auto_total = len(results) - manual_pending - deferred_count
        auto_passed = sum(
            1
            for r in results
            if r.get("passed") and r.get("status") != "manual_pending" and not r.get("deferred")
        )
        auto_failed = auto_total - auto_passed

        return {
            # A planning-only result with valid, deferred target-state checks
            # is structurally accepted.  It is not reported as an AC failure;
            # actual fulfilment is decided by the post-implementation run.
            "verified": (
                runner_readiness_failed == 0
                and auto_passed == auto_total
                and (auto_total > 0 or deferred_count > 0)
            ),
            "total": len(results),
            "passed": passed_count,
            "manual": manual_count,
            "automatic_total": auto_total,
            "automatic_passed": auto_passed,
            "automatic_failed": auto_failed,
            "manual_pending": manual_pending,
            "deferred": deferred_count,
            "runner_readiness_failed": runner_readiness_failed,
            "results": results,
        }
