from __future__ import annotations

from samuel.core.bus import Bus
from samuel.core.commands import ScanIssuesCommand
from samuel.core.events import PlanPosted
from samuel.core.types import Issue, Label
from samuel.slices.watch.handler import WatchHandler, _issue_risk


def _issue(number: int, *labels: str) -> Issue:
    return Issue(
        number=number,
        title=f"Issue {number}",
        body="",
        state="open",
        labels=[Label(id=index, name=name) for index, name in enumerate(labels, 1)],
    )


class _SCM:
    def __init__(self, issues: list[Issue]) -> None:
        self._issues = issues

    def list_issues(self, labels: list[str]) -> list[Issue]:
        if labels == ["ready-for-agent"]:
            return self._issues
        requested = set(labels)
        return [
            issue
            for issue in self._issues
            if requested.intersection(label.name for label in issue.labels)
        ]

    def swap_label(self, number: int, remove: str, add: str) -> None:
        raise AssertionError("No inconsistent status labels expected")

    @property
    def capabilities(self) -> set[str]:
        return {"issues"}


def _scan(issues: list[Issue], *, max_risk: int) -> tuple[dict, list[dict]]:
    bus = Bus()
    published: list[dict] = []

    def plan(event) -> None:
        published.append(event.payload)
        bus.publish(
            PlanPosted(
                payload={"issue": event.payload["issue"]},
                correlation_id=event.correlation_id,
            )
        )

    bus.subscribe("IssueReady", plan)
    handler = WatchHandler(
        bus,
        scm=_SCM(issues),  # type: ignore[arg-type]
        max_risk=max_risk,
        workflow_name="test-profile",
    )

    result = handler.handle(ScanIssuesCommand(payload={}))

    return result, published


def test_watch_dispatches_only_issues_within_workflow_risk_limit() -> None:
    result, published = _scan(
        [
            _issue(1, "risk:low"),
            _issue(2, "risk:medium"),
            _issue(3, "risk:high"),
            _issue(4, "risk:critical"),
        ],
        max_risk=2,
    )

    assert [payload["issue"] for payload in published] == [1, 2]
    assert published[0] == {
        "issue": 1,
        "title": "Issue 1",
        "risk": 1,
        "risk_source": "risk:low",
        "workflow": "test-profile",
    }
    assert result["planned"] == 2
    assert result["risk_filtered"] == 2
    assert result["max_risk"] == 2
    assert result["workflow"] == "test-profile"


def test_watch_treats_unlabelled_issue_as_high_risk() -> None:
    restricted_result, restricted = _scan([_issue(7)], max_risk=2)
    standard_result, standard = _scan([_issue(7)], max_risk=3)

    assert restricted == []
    assert restricted_result["risk_filtered"] == 1
    assert standard[0]["risk"] == 3
    assert standard[0]["risk_source"] == "unlabeled_default_high"
    assert standard_result["risk_filtered"] == 0


def test_issue_risk_uses_most_conservative_label() -> None:
    assert _issue_risk(_issue(9, "risk:low", "risk:critical")) == (4, "risk:critical")


def test_watch_without_scm_reports_active_workflow_contract() -> None:
    handler = WatchHandler(Bus(), max_risk=1, workflow_name="night")

    result = handler.handle(ScanIssuesCommand(payload={}))

    assert result["risk_filtered"] == 0
    assert result["max_risk"] == 1
    assert result["workflow"] == "night"
