from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from samuel.adapters.api.webhooks import WebhookIngressAdapter
from samuel.core.bus import Bus, IdempotencyMiddleware, IdempotencyStore
from samuel.core.events import Event
from samuel.core.ports import IVersionControl
from samuel.core.types import SCMActivity
from samuel.slices.watch.activity import SCMActivityPoller


def test_webhook_and_polling_observation_are_deduplicated(tmp_path: Path) -> None:
    bus = Bus()
    bus.add_middleware(IdempotencyMiddleware(IdempotencyStore(tmp_path / "idempotency.json")))
    received: list[Event] = []
    bus.subscribe("IssueOpened", received.append)
    WebhookIngressAdapter(bus).handle_webhook(
        "issues",
        {
            "action": "opened",
            "issue": {
                "number": 390,
                "title": "Polling",
                "created_at": "2026-08-21T12:00:00+02:00",
            },
            "sender": {"login": "alice"},
        },
    )
    scm = MagicMock(spec=IVersionControl)
    scm.list_scm_activity.return_value = [
        SCMActivity(
            event="IssueOpened",
            number=390,
            timestamp="2026-08-21T10:00:00Z",
            title="Polling",
            actor="alice",
        )
    ]
    poller = SCMActivityPoller(
        bus,
        scm,
        tmp_path / "activity.json",
        now_fn=lambda: datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc),
    )

    poller.poll()

    assert len(received) == 1
    assert received[0].payload["source"] == "webhook"
