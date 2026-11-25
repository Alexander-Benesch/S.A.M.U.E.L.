from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from samuel.adapters.llm.manual import ManualAdapter, ManualLLMTimeout


def _write_resp(data_dir: Path, req_id: str, resp: dict) -> None:
    (data_dir / f"resp_{req_id}.json").write_text(json.dumps(resp))


def _write_resp_atomically(data_dir: Path, req_id: str, resp: dict) -> None:
    final_path = data_dir / f"resp_{req_id}.json"
    temporary_path = final_path.with_suffix(".json.tmp")
    temporary_path.write_text(json.dumps(resp), encoding="utf-8")
    os.replace(temporary_path, final_path)


class TestManualAdapter:
    def test_round_trip_returns_llm_response(self, tmp_path: Path):
        adapter = ManualAdapter(
            data_dir=tmp_path,
            poll_interval=0.01,
            timeout_seconds=2.0,
            id_generator=lambda: "fixed",
        )
        _write_resp(
            tmp_path,
            "fixed",
            {
                "text": "hello back",
                "input_tokens": 10,
                "output_tokens": 5,
                "stop_reason": "end_turn",
                "model_used": "manual",
            },
        )

        result = adapter.complete([{"role": "user", "content": "hi"}])

        assert result.text == "hello back"
        assert result.input_tokens == 10
        assert result.output_tokens == 5
        assert result.stop_reason == "end_turn"
        assert result.model_used == "manual"
        assert result.latency_ms >= 0

    def test_writes_request_file_with_payload(self, tmp_path: Path):
        captured = threading.Event()
        captured_payload: dict = {}

        def watcher() -> None:
            req_path = tmp_path / "req_fixed.json"
            for _ in range(200):
                if req_path.exists():
                    captured_payload.update(json.loads(req_path.read_text()))
                    captured.set()
                    _write_resp(
                        tmp_path,
                        "fixed",
                        {"text": "ok", "input_tokens": 1, "output_tokens": 1},
                    )
                    return
                threading.Event().wait(0.01)

        threading.Thread(target=watcher, daemon=True).start()

        adapter = ManualAdapter(
            data_dir=tmp_path,
            poll_interval=0.01,
            timeout_seconds=2.0,
            id_generator=lambda: "fixed",
        )
        adapter.complete(
            [{"role": "user", "content": "ping"}],
            system="You are a helper",
            max_tokens=100,
            temperature=0.5,
            model="some-model",
        )

        assert captured.wait(timeout=2.0)
        assert captured_payload["id"] == "fixed"
        assert captured_payload["system"] == "You are a helper"
        assert captured_payload["messages"] == [{"role": "user", "content": "ping"}]
        assert captured_payload["params"]["max_tokens"] == 100
        assert captured_payload["params"]["temperature"] == 0.5
        assert captured_payload["params"]["model"] == "some-model"

    def test_request_is_invisible_until_complete_atomic_publish(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        req_path = tmp_path / "req_atomic.json"
        real_write_text = Path.write_text
        real_replace = os.replace
        observed_temporary_payload: dict = {}
        request_write_started = threading.Event()
        allow_request_write = threading.Event()

        def blocking_write_text(path: Path, content: str, **kwargs: Any) -> int:
            if path.name.startswith(".req_atomic.json."):
                assert not req_path.exists()
                request_write_started.set()
                assert allow_request_write.wait(timeout=2.0)
            return real_write_text(path, content, **kwargs)

        def observing_replace(source: Path, destination: Path) -> None:
            if Path(destination) == req_path:
                assert not req_path.exists()
                assert (tmp_path / "req_atomic.pid").read_text(encoding="utf-8") == str(os.getpid())
                observed_temporary_payload.update(
                    json.loads(Path(source).read_text(encoding="utf-8"))
                )
            real_replace(source, destination)

        _write_resp(
            tmp_path,
            "atomic",
            {"text": "ok", "input_tokens": 1, "output_tokens": 1},
        )
        monkeypatch.setattr(Path, "write_text", blocking_write_text)
        monkeypatch.setattr("samuel.adapters.llm.manual.os.replace", observing_replace)
        adapter = ManualAdapter(
            data_dir=tmp_path,
            poll_interval=0.01,
            timeout_seconds=2.0,
            id_generator=lambda: "atomic",
        )

        with ThreadPoolExecutor(max_workers=1) as executor:
            completion = executor.submit(
                adapter.complete,
                [{"role": "user", "content": "ping"}],
            )
            assert request_write_started.wait(timeout=2.0)
            try:
                assert not req_path.exists()
                assert (tmp_path / "req_atomic.pid").exists()
            finally:
                allow_request_write.set()
            completion.result(timeout=2.0)

        assert observed_temporary_payload["id"] == "atomic"

    def test_failed_request_publish_leaves_no_final_or_temporary_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        req_path = tmp_path / "req_broken_publish.json"
        real_replace = os.replace

        def failing_replace(source: Path, destination: Path) -> None:
            if Path(destination) == req_path:
                raise OSError("simulated request publish failure")
            real_replace(source, destination)

        monkeypatch.setattr("samuel.adapters.llm.manual.os.replace", failing_replace)
        adapter = ManualAdapter(
            data_dir=tmp_path,
            poll_interval=0.01,
            timeout_seconds=2.0,
            id_generator=lambda: "broken_publish",
        )

        with pytest.raises(OSError, match="simulated request publish failure"):
            adapter.complete([{"role": "user", "content": "ping"}])

        assert not req_path.exists()
        assert not (tmp_path / "req_broken_publish.pid").exists()
        assert not list(tmp_path.glob(".*.tmp"))

    def test_cleans_up_files_on_success(self, tmp_path: Path):
        adapter = ManualAdapter(
            data_dir=tmp_path,
            poll_interval=0.01,
            timeout_seconds=2.0,
            id_generator=lambda: "cleanup",
        )
        _write_resp(tmp_path, "cleanup", {"text": "x", "input_tokens": 0, "output_tokens": 0})

        adapter.complete([{"role": "user", "content": "hi"}])

        assert not (tmp_path / "req_cleanup.json").exists()
        assert not (tmp_path / "resp_cleanup.json").exists()

    def test_timeout_raises_when_no_response(self, tmp_path: Path):
        adapter = ManualAdapter(
            data_dir=tmp_path,
            poll_interval=0.01,
            timeout_seconds=0.05,
            id_generator=lambda: "timeout",
        )

        with pytest.raises(ManualLLMTimeout):
            adapter.complete([{"role": "user", "content": "hi"}])

        assert (tmp_path / "req_timeout.json").exists()

    def test_invalid_json_response_raises(self, tmp_path: Path):
        adapter = ManualAdapter(
            data_dir=tmp_path,
            poll_interval=0.01,
            timeout_seconds=0.05,
            id_generator=lambda: "broken",
        )
        (tmp_path / "resp_broken.json").write_text("{not valid json")

        started = time.monotonic()
        with pytest.raises(ManualLLMTimeout) as exc_info:
            adapter.complete([{"role": "user", "content": "hi"}])
        elapsed = time.monotonic() - started

        message = str(exc_info.value)
        assert 0.04 <= elapsed < 1.0
        assert "resp_broken.json" in message
        assert "JSONDecodeError" in message
        assert "Expecting property name" in message
        assert (tmp_path / "req_broken.json").exists()
        assert (tmp_path / "resp_broken.json").exists()
        assert not (tmp_path / "req_broken.pid").exists()

    def test_retries_partial_response_until_atomic_payload_is_available(self, tmp_path: Path):
        partial_path = tmp_path / "resp_partial.json"
        partial_path.write_text('{"text":', encoding="utf-8")
        writer_finished = threading.Event()

        def finish_response() -> None:
            time.sleep(0.05)
            _write_resp_atomically(
                tmp_path,
                "partial",
                {"text": "complete", "input_tokens": 2, "output_tokens": 1},
            )
            writer_finished.set()

        writer = threading.Thread(target=finish_response, daemon=True)
        writer.start()
        adapter = ManualAdapter(
            data_dir=tmp_path,
            poll_interval=0.005,
            timeout_seconds=1.0,
            id_generator=lambda: "partial",
        )

        result = adapter.complete([{"role": "user", "content": "hi"}])

        writer.join(timeout=1.0)
        assert writer_finished.is_set()
        assert result.text == "complete"
        assert result.input_tokens == 2
        assert result.output_tokens == 1
        assert not (tmp_path / "req_partial.json").exists()
        assert not partial_path.exists()
        assert not (tmp_path / "resp_partial.json.tmp").exists()
        assert not (tmp_path / "req_partial.pid").exists()

    def test_non_object_response_remains_invalid_until_timeout(self, tmp_path: Path):
        adapter = ManualAdapter(
            data_dir=tmp_path,
            poll_interval=0.01,
            timeout_seconds=0.05,
            id_generator=lambda: "array",
        )
        (tmp_path / "resp_array.json").write_text('["not", "an", "object"]')

        with pytest.raises(ManualLLMTimeout, match="JSON-Objekt.*list"):
            adapter.complete([{"role": "user", "content": "hi"}])

    def test_non_positive_poll_interval_is_rejected(self, tmp_path: Path):
        with pytest.raises(ValueError, match="poll_interval must be greater than zero"):
            ManualAdapter(data_dir=tmp_path, poll_interval=0)

    def test_estimate_tokens(self, tmp_path: Path):
        adapter = ManualAdapter(data_dir=tmp_path)
        assert adapter.estimate_tokens("a" * 40) == 10

    def test_context_window_default(self, tmp_path: Path):
        adapter = ManualAdapter(data_dir=tmp_path)
        assert adapter.context_window == 200_000

    def test_context_window_configurable(self, tmp_path: Path):
        adapter = ManualAdapter(data_dir=tmp_path, context_window_size=8000)
        assert adapter.context_window == 8000


class TestOrphanCleanup:
    """#248: orphan req-Files (Self-Mode-Process gekillt während aktiv) müssen
    bei Adapter-Init aufgeräumt werden — sonst bleiben sie für Operator
    sichtbar liegen und bei Wiederanlauf wartet das System auf eine resp die
    nie kommt."""

    def test_writes_pid_sidecar_on_complete(self, tmp_path: Path):
        """Während eines aktiven complete()-Calls existiert eine req_<id>.pid-
        Datei mit der PID des Adapter-Prozesses."""
        import os

        captured: dict[str, int] = {}
        ready = threading.Event()

        def watcher() -> None:
            pid_path = tmp_path / "req_active.pid"
            for _ in range(200):
                if pid_path.exists():
                    captured["pid"] = int(pid_path.read_text())
                    _write_resp(tmp_path, "active", {"text": "ok"})
                    ready.set()
                    return
                threading.Event().wait(0.01)

        threading.Thread(target=watcher, daemon=True).start()
        adapter = ManualAdapter(
            data_dir=tmp_path,
            poll_interval=0.01,
            timeout_seconds=2.0,
            id_generator=lambda: "active",
        )
        adapter.complete([{"role": "user", "content": "hi"}])
        assert ready.wait(timeout=2.0)
        assert captured["pid"] == os.getpid()

    def test_cleanup_removes_orphan_with_dead_pid(self, tmp_path: Path):
        """Init räumt req+pid auf wenn PID nicht mehr lebt."""
        # Simuliere Orphan: req+pid mit PID die garantiert nicht existiert
        (tmp_path / "req_orphan.json").write_text('{"id": "orphan"}')
        (tmp_path / "req_orphan.pid").write_text("999999")

        ManualAdapter(data_dir=tmp_path)

        assert not (tmp_path / "req_orphan.json").exists()
        assert not (tmp_path / "req_orphan.pid").exists()

    def test_cleanup_keeps_request_with_alive_pid(self, tmp_path: Path):
        """Init lässt req+pid in Ruhe wenn PID noch lebt (eigene PID)."""
        import os

        # Use my own PID — guaranteed alive
        (tmp_path / "req_alive.json").write_text('{"id": "alive"}')
        (tmp_path / "req_alive.pid").write_text(str(os.getpid()))

        ManualAdapter(data_dir=tmp_path)

        # Files must remain — owning process is alive
        assert (tmp_path / "req_alive.json").exists()
        assert (tmp_path / "req_alive.pid").exists()

    def test_cleanup_ignores_request_without_pid_sidecar(self, tmp_path: Path) -> None:
        """Legacy req-Files ohne pid-Sidecar bleiben unangetastet —
        sie könnten vom Operator manuell platziert worden sein."""
        (tmp_path / "req_legacy.json").write_text('{"id": "legacy"}')

        ManualAdapter(data_dir=tmp_path)

        assert (tmp_path / "req_legacy.json").exists()

    def test_cleanup_handles_malformed_pid_sidecar(self, tmp_path: Path):
        """Unlesbarer/kaputter pid-Sidecar wird als Orphan behandelt."""
        (tmp_path / "req_bad.json").write_text('{"id": "bad"}')
        (tmp_path / "req_bad.pid").write_text("not-a-number")

        ManualAdapter(data_dir=tmp_path)

        assert not (tmp_path / "req_bad.json").exists()
        assert not (tmp_path / "req_bad.pid").exists()

    def test_cleanup_also_removes_orphan_resp_file(self, tmp_path: Path):
        """Wenn Orphan ein leftover resp_<id>.json hat, auch dieses entfernen."""
        (tmp_path / "req_zombie.json").write_text('{"id": "zombie"}')
        (tmp_path / "req_zombie.pid").write_text("999999")
        (tmp_path / "resp_zombie.json").write_text('{"text": "stale"}')

        ManualAdapter(data_dir=tmp_path)

        assert not (tmp_path / "req_zombie.json").exists()
        assert not (tmp_path / "req_zombie.pid").exists()
        assert not (tmp_path / "resp_zombie.json").exists()

    def test_pid_sidecar_removed_after_successful_complete(self, tmp_path: Path) -> None:
        """Nach erfolgreichem complete() ist kein pid-Sidecar mehr da."""
        adapter = ManualAdapter(
            data_dir=tmp_path,
            poll_interval=0.01,
            timeout_seconds=2.0,
            id_generator=lambda: "done",
        )
        _write_resp(tmp_path, "done", {"text": "ok"})
        adapter.complete([{"role": "user", "content": "hi"}])
        assert not (tmp_path / "req_done.pid").exists()

    def test_pid_sidecar_removed_on_timeout(self, tmp_path: Path):
        """Auch bei Timeout wird der eigene pid-Sidecar entfernt — sonst hätten
        wir einen "Orphan" obwohl der Prozess noch lebt."""
        adapter = ManualAdapter(
            data_dir=tmp_path,
            poll_interval=0.01,
            timeout_seconds=0.05,
            id_generator=lambda: "to",
        )
        with pytest.raises(ManualLLMTimeout):
            adapter.complete([{"role": "user", "content": "hi"}])
        # req bleibt zur Diagnose (existing behavior), aber pid weg
        assert (tmp_path / "req_to.json").exists()
        assert not (tmp_path / "req_to.pid").exists()

    def test_cleanup_at_init_does_not_remove_active_other_process(self, tmp_path: Path) -> None:
        """Eine Datei mit fremder PID die LEBT (z.B. zweiter Self-Mode-Run
        parallel) wird nicht angefasst."""
        import os

        (tmp_path / "req_other.json").write_text('{"id": "other"}')
        # PPID is parent — typically alive when test runs
        (tmp_path / "req_other.pid").write_text(str(os.getppid()))

        ManualAdapter(data_dir=tmp_path)

        # Belongs to another live process — keep
        assert (tmp_path / "req_other.json").exists()
        assert (tmp_path / "req_other.pid").exists()


class TestManualAdapterFactoryIntegration:
    def test_registered_in_factory(self):
        from samuel.adapters.llm.factory import create_llm_adapter

        class StubConfig:
            def get(self, key: str, default=None):
                table = {
                    "llm.default.provider": "manual",
                    "agent.config_dir": "config",
                    "llm.manual.data_dir": "data/manual_llm",
                    "llm.manual.poll_interval": 1.0,
                    "llm.manual.timeout": 3600,
                    "llm.manual.context_window": 200_000,
                }
                return table.get(key, default)

        class StubSecrets:
            def get(self, _key: str) -> str | None:
                return None

        adapter = create_llm_adapter(StubConfig(), StubSecrets())
        assert adapter is not None
