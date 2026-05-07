from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse

log = logging.getLogger(__name__)

DEFAULT_DATA_DIR = "data/manual_llm"


class ManualLLMTimeout(Exception):
    pass


def _is_pid_alive(pid: int) -> bool:
    """Check if a process with given PID is still alive (POSIX).

    Returns True if signal 0 to PID succeeds (process exists). False if the
    PID is unknown or we lack permissions (treated as gone for safety).
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, OSError):
        return False


class ManualAdapter(ILLMProvider):
    """Manual LLM adapter — writes a request file and polls for a response.

    Lifecycle (#248): each request writes a sidecar ``req_<id>.pid`` file
    containing the producing process's PID. On adapter init, scan ``data_dir``
    for orphan ``req_*.json`` files whose companion PID is dead and clean
    them up. Without this, killed self-mode runs leave stale request files
    that an operator must remove by hand.
    """

    def __init__(
        self,
        data_dir: Path | str = DEFAULT_DATA_DIR,
        poll_interval: float = 1.0,
        timeout_seconds: float = 3600.0,
        id_generator: Callable[[], str] | None = None,
        context_window_size: int = 200_000,
    ) -> None:
        self._dir = Path(data_dir)
        self._poll = poll_interval
        self._timeout = timeout_seconds
        self._gen_id = id_generator or (lambda: uuid.uuid4().hex[:12])
        self._ctx_window = context_window_size
        self._pid = os.getpid()

        # Clean orphans from previous (killed) runs at adapter startup.
        self._cleanup_orphans()

    @property
    def context_window(self) -> int:
        return self._ctx_window

    def _cleanup_orphans(self) -> None:
        """Remove req+pid pairs whose owning process is no longer alive.

        Runs at adapter init. Files without a pid sidecar are left alone —
        they may belong to a legacy process or external producer.
        """
        if not self._dir.exists():
            return
        for req_path in self._dir.glob("req_*.json"):
            pid_path = req_path.with_suffix(".pid")
            if not pid_path.exists():
                continue
            try:
                pid = int(pid_path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                # Unreadable / malformed pid sidecar — treat as orphan
                pid = -1
            if not _is_pid_alive(pid):
                req_path.unlink(missing_ok=True)
                pid_path.unlink(missing_ok=True)
                # Also remove a possibly-leftover resp file (rare)
                resp_path = req_path.with_name(
                    req_path.name.replace("req_", "resp_", 1)
                )
                resp_path.unlink(missing_ok=True)
                log.warning(
                    "Manual-LLM: orphan request %s (pid=%d, dead) removed",
                    req_path.name, pid,
                )

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        self._dir.mkdir(parents=True, exist_ok=True)
        req_id = self._gen_id()
        req_path = self._dir / f"req_{req_id}.json"
        pid_path = self._dir / f"req_{req_id}.pid"
        resp_path = self._dir / f"resp_{req_id}.json"

        payload = {
            "id": req_id,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "system": kwargs.get("system", ""),
            "messages": messages,
            "params": {
                "max_tokens": kwargs.get("max_tokens"),
                "temperature": kwargs.get("temperature"),
                "model": kwargs.get("model"),
            },
        }
        req_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        pid_path.write_text(str(self._pid), encoding="utf-8")
        log.warning(
            "Manual-LLM: schreibe %s und warte auf %s (Timeout %ds, pid=%d)",
            req_path,
            resp_path,
            int(self._timeout),
            self._pid,
        )

        t0 = time.monotonic()
        try:
            while not resp_path.exists():
                if time.monotonic() - t0 > self._timeout:
                    raise ManualLLMTimeout(
                        f"Keine Antwort in {self._timeout}s — req-Datei: {req_path}"
                    )
                time.sleep(self._poll)

            try:
                data = json.loads(resp_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ManualLLMTimeout(
                    f"resp-Datei {resp_path} nicht parsbar: {exc}"
                ) from exc
        finally:
            # Clean up our pid sidecar regardless of success / timeout / parse-fail
            pid_path.unlink(missing_ok=True)

        latency = int((time.monotonic() - t0) * 1000)
        req_path.unlink(missing_ok=True)
        resp_path.unlink(missing_ok=True)

        return LLMResponse(
            text=str(data.get("text", "")),
            input_tokens=int(data.get("input_tokens", 0)),
            output_tokens=int(data.get("output_tokens", 0)),
            cached_tokens=int(data.get("cached_tokens", 0)),
            stop_reason=str(data.get("stop_reason", "end_turn")),
            model_used=str(data.get("model_used", "manual")),
            latency_ms=latency,
        )

    def validate(self) -> dict:
        """#211: Filesystem-Pingn fuer Manual-LLM (kein API)."""
        import os as _os
        try:
            if not self._dir.exists():
                return {"valid": False, "detail": "data_dir missing", "balance": None}
            if not _os.access(self._dir, _os.W_OK):
                return {"valid": False, "detail": "data_dir not writable", "balance": None}
            return {"valid": True, "detail": "fs ok", "balance": None}
        except OSError as exc:
            return {"valid": False, "detail": f"fs error: {exc}", "balance": None}

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    def list_models(self) -> list[dict]:
        """#311: Manual-LLM kennt kein Modell-Listing — leere Liste."""
        return []