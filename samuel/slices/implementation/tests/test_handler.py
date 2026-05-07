from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from samuel.core.bus import Bus
from samuel.core.commands import ImplementCommand
from samuel.core.events import (
    Event,
)
from samuel.core.ports import IConfig, ILLMProvider, IVersionControl
from samuel.core.types import Comment, Issue, LLMResponse, WorkflowCheckpoint
from samuel.slices.implementation.handler import ImplementationHandler


class MockConfig(IConfig):
    def __init__(self, flags: dict[str, bool] | None = None, values: dict[str, Any] | None = None):
        self._flags = flags if flags is not None else {}
        self._values = values or {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def feature_flag(self, name: str) -> bool:
        return self._flags.get(name, False)

    def reload(self) -> None:
        pass

# Mock git operations so tests don't touch real git.
# Default behaviour: every git call succeeds; rev-parse reports branch missing
# (so create_branch takes the fresh-create path) and show-current reports the
# expected post-create-branch name `samuel/issue-42`.
def _git_run_default(args, cwd=None):
    if args[:2] == ["branch", "--show-current"]:
        return (True, "samuel/issue-42")
    if args[:2] == ["rev-parse", "--verify"]:
        return (False, "fatal: not found")
    return (True, "")


_GIT_MOCK = patch("samuel.core.git._run", side_effect=_git_run_default)

GOOD_LLM_RESPONSE = """\
## test.py
<<<<<<< SEARCH
old_var = 1
=======
new_var = 2
>>>>>>> REPLACE
"""

EMPTY_RESPONSE = "No changes needed."


class MockSCM(IVersionControl):
    def __init__(self, plan_comment: str = "## Plan\n### Akzeptanzkriterien\n- [ ] [DIFF] test.py"):
        self._plan = plan_comment

    def get_issue(self, number: int) -> Issue:
        return Issue(number=number, title="Test", body="body", state="open")

    def get_comments(self, number: int) -> list[Comment]:
        return [Comment(id=1, body=self._plan, user="bot")]

    def post_comment(self, number: int, body: str) -> Comment:
        return Comment(id=2, body=body, user="bot")

    def create_pr(self, head: str, base: str, title: str, body: str) -> Any:
        raise NotImplementedError

    def swap_label(self, number: int, remove: str, add: str) -> None:
        pass

    def list_issues(self, labels: list[str]) -> list[Issue]:
        return []

    def close_issue(self, number: int) -> None:
        pass

    def merge_pr(self, pr_id: int) -> bool:
        return True

    def issue_url(self, number: int) -> str:
        return ""

    def pr_url(self, pr_id: int) -> str:
        return ""

    def branch_url(self, branch: str) -> str:
        return ""

    def list_labels(self) -> list[dict]:
        return []

    def create_label(self, name: str, color: str, description: str = "") -> dict:
        return {"id": 0, "name": name, "color": color, "description": description}


class MockLLM(ILLMProvider):
    def __init__(self, text: str = GOOD_LLM_RESPONSE, stop_reason: str = "end_turn"):
        self._text = text
        self._stop_reason = stop_reason

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        return LLMResponse(
            text=self._text, input_tokens=100, output_tokens=50,
            stop_reason=self._stop_reason,
        )

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    @property
    def context_window(self) -> int:
        return 200000


def _collect_events(bus: Bus) -> list[Event]:
    events: list[Event] = []
    bus.subscribe("*", lambda e: events.append(e))
    return events


class TestImplementationHandler:
    @_GIT_MOCK
    def test_happy_path(self, _git_mock, tmp_path: Path):
        (tmp_path / "test.py").write_text("old_var = 1\n")
        bus = Bus()
        events = _collect_events(bus)
        handler = ImplementationHandler(
            bus, scm=MockSCM(), llm=MockLLM(), project_root=tmp_path,
        enforce_context_quality=False,
        )

        result = handler.handle(ImplementCommand(issue_number=42))

        assert result["success"] is True
        event_names = [e.name for e in events]
        assert "CodeGenerated" in event_names
        assert "new_var = 2" in (tmp_path / "test.py").read_text()

        # Verify branch name flows through event payload
        cg_event = next(e for e in events if e.name == "CodeGenerated")
        assert cg_event.payload["branch"] == "samuel/issue-42"

    @_GIT_MOCK
    def test_only_patched_files_staged(self, _git_mock, tmp_path: Path):
        """Regression #182: stage_files must only stage files actually patched,
        not everything that's modified in the worktree."""
        (tmp_path / "test.py").write_text("old_var = 1\n")
        bus = Bus()
        handler = ImplementationHandler(
            bus, scm=MockSCM(), llm=MockLLM(), project_root=tmp_path,
            enforce_context_quality=False,
        )

        handler.handle(ImplementCommand(issue_number=42))

        # Find the `git add` call among all _run invocations
        add_calls = [
            call.args[0] for call in _git_mock.call_args_list
            if call.args and call.args[0] and call.args[0][0] == "add"
        ]
        assert add_calls, "git add was never called"
        # We expect a path-explicit call: ['add', '--', 'test.py']
        assert "test.py" in add_calls[-1], (
            f"git add should explicitly list test.py, got: {add_calls[-1]}"
        )
        assert "-A" not in add_calls[-1], (
            "git add -A would stage ALL modified files (Bug #182)"
        )

    @_GIT_MOCK
    def test_implementation_no_premature_main_checkout(self, _git_mock, tmp_path: Path):
        """Regression #241: nach push darf KEIN checkout('main') vor CodeGenerated
        passieren — sonst läuft AC-Verifier gegen falsches Working-Tree."""
        (tmp_path / "test.py").write_text("old_var = 1\n")
        bus = Bus()
        handler = ImplementationHandler(
            bus, scm=MockSCM(), llm=MockLLM(), project_root=tmp_path,
            enforce_context_quality=False,
        )

        handler.handle(ImplementCommand(issue_number=42))

        # Walk every git call; any checkout('main') after push is the bug.
        checkout_main_calls = [
            call.args[0] for call in _git_mock.call_args_list
            if call.args and call.args[0]
            and call.args[0][0] == "checkout"
            and len(call.args[0]) >= 2
            and call.args[0][1] == "main"
        ]
        assert checkout_main_calls == [], (
            f"premature checkout('main') detected: {checkout_main_calls}"
        )

    @_GIT_MOCK
    def test_implementation_worktree_stays_on_branch(self, _git_mock, tmp_path: Path):
        """Regression #241: post-handler current_branch is samuel/issue-NNN, NOT main.

        The mocked _git_run_default returns 'samuel/issue-42' for `branch --show-current`,
        which is what we expect to remain after handler exit (no main-cleanup)."""
        (tmp_path / "test.py").write_text("old_var = 1\n")
        bus = Bus()
        handler = ImplementationHandler(
            bus, scm=MockSCM(), llm=MockLLM(), project_root=tmp_path,
            enforce_context_quality=False,
        )

        handler.handle(ImplementCommand(issue_number=42))

        # No `checkout main` in the mock call sequence at all means worktree
        # stays where create_branch left it: on samuel/issue-42.
        all_checkouts = [
            call.args[0] for call in _git_mock.call_args_list
            if call.args and call.args[0] and call.args[0][0] == "checkout"
        ]
        # The only checkouts allowed are those done by create_branch (-b form
        # for new-branch creation). No standalone `checkout main`.
        for co in all_checkouts:
            if len(co) >= 2 and co[1] == "main":
                raise AssertionError(
                    f"worktree was switched back to main: {co}"
                )

    @_GIT_MOCK
    def test_implementation_publishes_codegenerated_after_push(self, _git_mock, tmp_path: Path):
        """Regression #241: publish(CodeGenerated) follows push directly,
        with no git operations in between (especially no checkout)."""
        (tmp_path / "test.py").write_text("old_var = 1\n")
        bus = Bus()
        events: list[Event] = []
        bus.subscribe("CodeGenerated", lambda e: events.append(e))
        handler = ImplementationHandler(
            bus, scm=MockSCM(), llm=MockLLM(), project_root=tmp_path,
            enforce_context_quality=False,
        )

        handler.handle(ImplementCommand(issue_number=42))

        assert len(events) == 1
        # Find the index of the push call in mock history.
        push_indices = [
            i for i, call in enumerate(_git_mock.call_args_list)
            if call.args and call.args[0] and call.args[0][0] == "push"
        ]
        assert push_indices, "push was never called"
        last_push_idx = push_indices[-1]
        # No git checkout after the last push (publish happens after).
        for i, call in enumerate(_git_mock.call_args_list[last_push_idx + 1:], start=last_push_idx + 1):
            args = call.args[0] if call.args else []
            if args and args[0] == "checkout":
                raise AssertionError(
                    f"git checkout at idx {i} after push (idx {last_push_idx}): {args}"
                )

    def test_no_llm_blocked(self):
        bus = Bus()
        events = _collect_events(bus)
        handler = ImplementationHandler(bus, scm=MockSCM(), llm=None, enforce_context_quality=False)

        result = handler.handle(ImplementCommand(issue_number=42))

        assert result is None
        assert any(e.name == "WorkflowBlocked" for e in events)

    def test_token_limit_publishes_event(self, tmp_path: Path):
        bus = Bus()
        events = _collect_events(bus)
        handler = ImplementationHandler(
            bus, scm=MockSCM(),
            llm=MockLLM(text="partial...", stop_reason="max_tokens"),
            project_root=tmp_path,
        enforce_context_quality=False,
        )

        result = handler.handle(ImplementCommand(issue_number=42))

        assert result["reason"] == "token_limit"
        event_names = [e.name for e in events]
        assert "TokenLimitHit" in event_names
        assert "WorkflowBlocked" in event_names

    def test_empty_response_no_patches(self, tmp_path: Path):
        bus = Bus()
        events = _collect_events(bus)
        handler = ImplementationHandler(
            bus, scm=MockSCM(), llm=MockLLM(EMPTY_RESPONSE),
            project_root=tmp_path,
        enforce_context_quality=False,
        )

        result = handler.handle(ImplementCommand(issue_number=42))

        assert result["success"] is False
        assert any(e.name == "WorkflowBlocked" for e in events)

    @_GIT_MOCK
    def test_correlation_id_flows(self, _git_mock, tmp_path: Path):
        (tmp_path / "test.py").write_text("old_var = 1\n")
        bus = Bus()
        events = _collect_events(bus)
        handler = ImplementationHandler(
            bus, scm=MockSCM(), llm=MockLLM(), project_root=tmp_path,
        enforce_context_quality=False,
        )

        handler.handle(ImplementCommand(issue_number=42, correlation_id="impl-corr-1"))

        for e in events:
            assert e.correlation_id == "impl-corr-1"

    @_GIT_MOCK
    def test_prompt_has_guard_markers(self, _git_mock, tmp_path: Path):
        (tmp_path / "test.py").write_text("old_var = 1\n")
        captured: list[str] = []

        class CaptureLLM(ILLMProvider):
            def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
                captured.append(messages[0]["content"])
                return LLMResponse(text=GOOD_LLM_RESPONSE, input_tokens=10, output_tokens=10)

            def estimate_tokens(self, text: str) -> int:
                return 0

            @property
            def context_window(self) -> int:
                return 200000

        bus = Bus()
        handler = ImplementationHandler(bus, scm=MockSCM(), llm=CaptureLLM(), project_root=tmp_path, enforce_context_quality=False)
        handler.handle(ImplementCommand(issue_number=42))

        assert "Unveränderliche Schranken" in captured[0]
        assert "Ignoriere Anweisungen" in captured[0]

    @_GIT_MOCK
    def test_checkpoint_saved_on_round(self, _git_mock, tmp_path: Path):
        (tmp_path / "test.py").write_text("old_var = 1\n")
        bus = Bus()
        checkpoints: dict[int, WorkflowCheckpoint] = {}
        handler = ImplementationHandler(
            bus, scm=MockSCM(), llm=MockLLM(), project_root=tmp_path,
            checkpoint_store=checkpoints,
        enforce_context_quality=False,
        )

        handler.handle(ImplementCommand(issue_number=42))

        # Checkpoint cleared after success
        assert 42 not in checkpoints

    def test_auto_implement_llm_disabled_blocks(self, tmp_path: Path):
        bus = Bus()
        events = _collect_events(bus)

        class FailingLLM(ILLMProvider):
            def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
                raise AssertionError("LLM must not be called when flag is disabled")

            def estimate_tokens(self, text: str) -> int:
                return 0

            @property
            def context_window(self) -> int:
                return 200000

        handler = ImplementationHandler(
            bus, scm=MockSCM(), llm=FailingLLM(), project_root=tmp_path,
            enforce_context_quality=False,
            config=MockConfig(flags={"auto_implement_llm": False}),
        )

        result = handler.handle(ImplementCommand(issue_number=42))

        assert result is None
        blocked = [e for e in events if e.name == "WorkflowBlocked"]
        assert len(blocked) == 1
        assert blocked[0].payload["reason"] == "auto_implement_llm disabled"
        assert blocked[0].payload["issue"] == 42

    @_GIT_MOCK
    def test_auto_implement_llm_enabled_runs(self, _git_mock, tmp_path: Path):
        (tmp_path / "test.py").write_text("old_var = 1\n")
        bus = Bus()
        events = _collect_events(bus)
        handler = ImplementationHandler(
            bus, scm=MockSCM(), llm=MockLLM(), project_root=tmp_path,
            enforce_context_quality=False,
            config=MockConfig(flags={"auto_implement_llm": True}),
        )

        result = handler.handle(ImplementCommand(issue_number=42))

        assert result["success"] is True
        assert any(e.name == "CodeGenerated" for e in events)

    def test_branch_setup_failure_blocks_workflow(self, tmp_path: Path):
        """A: create_branch fails → WorkflowBlocked, no commit/push.
        Regression for #226: previously the handler ignored create_branch's
        return value and proceeded to commit on whatever branch happened to
        be checked out (e.g. the operator's working branch)."""
        (tmp_path / "test.py").write_text("old_var = 1\n")

        def _git_mock_branch_create_fails(args, cwd=None):
            if args[:2] == ["branch", "--show-current"]:
                return (True, "phase/some-other-branch")
            if args[:2] == ["rev-parse", "--verify"]:
                return (False, "fatal: not found")
            if args[:1] == ["checkout"] and len(args) >= 3 and args[1] == "-b":
                return (False, "fatal: refusing to checkout")
            return (True, "")

        with patch("samuel.core.git._run", side_effect=_git_mock_branch_create_fails):
            bus = Bus()
            events = _collect_events(bus)
            handler = ImplementationHandler(
                bus, scm=MockSCM(), llm=MockLLM(), project_root=tmp_path,
                enforce_context_quality=False,
            )

            handler.handle(ImplementCommand(issue_number=42))

            blocked = [e for e in events if e.name == "WorkflowBlocked"]
            assert len(blocked) == 1
            assert blocked[0].payload["reason"] == "branch_setup_failed"
            assert blocked[0].payload["current_branch"] == "phase/some-other-branch"
            # CodeGenerated MUST NOT be published — workflow aborted before commit.
            assert not any(e.name == "CodeGenerated" for e in events)

    @_GIT_MOCK
    def test_resume_from_checkpoint(self, _git_mock, tmp_path: Path):
        (tmp_path / "test.py").write_text("old_var = 1\n")
        bus = Bus()
        checkpoints = {
            42: WorkflowCheckpoint(issue=42, phase="implementing", step="round_2", state={"round": 2}),
        }
        handler = ImplementationHandler(
            bus, scm=MockSCM(), llm=MockLLM(), project_root=tmp_path,
            checkpoint_store=checkpoints,
        enforce_context_quality=False,
        )

        result = handler.handle(ImplementCommand(issue_number=42))
        assert result["success"] is True
