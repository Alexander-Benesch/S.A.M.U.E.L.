from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from samuel.core.issue_context import (
    current_issue,
    current_workflow_correlation,
    issue_scope,
)


def test_no_scope_returns_none():
    assert current_issue() is None
    assert current_workflow_correlation() is None


def test_scope_sets_issue():
    with issue_scope(176, "run-176"):
        assert current_issue() == 176
        assert current_workflow_correlation() == "run-176"
    assert current_issue() is None
    assert current_workflow_correlation() is None


def test_nested_scopes_stack():
    with issue_scope(100, "run-100"):
        assert current_issue() == 100
        assert current_workflow_correlation() == "run-100"
        with issue_scope(200, "run-200"):
            assert current_issue() == 200
            assert current_workflow_correlation() == "run-200"
        assert current_issue() == 100
        assert current_workflow_correlation() == "run-100"
    assert current_issue() is None
    assert current_workflow_correlation() is None


def test_issue_only_nested_scope_does_not_inherit_foreign_run():
    with issue_scope(100, "run-100"):
        with issue_scope(200):
            assert current_issue() == 200
            assert current_workflow_correlation() is None
        assert current_workflow_correlation() == "run-100"


def test_scope_isolated_per_thread():
    seen: dict[str, tuple[int | None, str | None]] = {}

    def worker(name: str) -> None:
        seen[name] = (current_issue(), current_workflow_correlation())

    with issue_scope(42, "run-42"):
        with ThreadPoolExecutor(max_workers=1) as ex:
            ex.submit(worker, "child").result()
        seen["main"] = (current_issue(), current_workflow_correlation())

    assert seen["main"] == (42, "run-42")
    assert seen["child"] == (None, None)


def test_scope_clears_on_exception():
    try:
        with issue_scope(7, "run-7"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert current_issue() is None
    assert current_workflow_correlation() is None
