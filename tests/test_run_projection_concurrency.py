"""Concurrent webhook events for one run must remain visible in its readback."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from time import sleep

from samuel.core.bus import Bus
from samuel.core.state import RunProjectionRecord
from samuel.slices.run_projection.handler import RunProjectionHandler


def test_concurrent_events_for_one_run_are_not_lost() -> None:
    class Store:
        def __init__(self) -> None:
            self.records: dict[str, RunProjectionRecord] = {}

        def get_projection(self, key):
            current = self.records.get(key)
            # Let other request threads observe a stale value if the handler
            # does not protect its complete read/modify/write operation.
            sleep(0.01)
            return current

        def upsert_projection(self, record):
            self.records[record.projection_key] = record

    store = Store()
    handler = RunProjectionHandler(Bus(), store)
    observed_at = datetime.now(timezone.utc)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(
            executor.map(
                lambda number: handler.record(
                    issue_number=153,
                    correlation_id="one-run",
                    event_name=f"Event{number}",
                    payload={"issue": 153, "number": number},
                    timestamp=observed_at,
                ),
                range(8),
            )
        )

    assert len(store.records) == 1
    record = next(iter(store.records.values()))
    assert {event["payload"]["message_name"] for event in record.payload["events"]} == {
        f"Event{number}" for number in range(8)
    }
