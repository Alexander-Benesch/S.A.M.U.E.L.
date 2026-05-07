from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from samuel.core.issue_context import current_issue, issue_scope


def test_no_scope_returns_none():
    assert current_issue() is None


def test_scope_sets_issue():
    with issue_scope(176):
        assert current_issue() == 176
    assert current_issue() is None


def test_nested_scopes_stack():
    with issue_scope(100):
        assert current_issue() == 100
        with issue_scope(200):
            assert current_issue() == 200
        assert current_issue() == 100
    assert current_issue() is None


def test_scope_isolated_per_thread():
    seen: dict[str, int | None] = {}

    def worker(name: str) -> None:
        seen[name] = current_issue()

    with issue_scope(42):
        with ThreadPoolExecutor(max_workers=1) as ex:
            ex.submit(worker, "child").result()
        seen["main"] = current_issue()

    assert seen["main"] == 42
    assert seen["child"] is None


def test_scope_clears_on_exception():
    try:
        with issue_scope(7):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert current_issue() is None
