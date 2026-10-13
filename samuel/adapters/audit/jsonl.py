from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

from samuel.adapters.audit.upcasters import upcast
from samuel.core.ports import IAuditSink
from samuel.core.types import AuditQuery

log = logging.getLogger(__name__)

try:
    import fcntl
except ImportError:  # pragma: no cover - signed multi-process audit requires POSIX locks
    fcntl = None  # type: ignore[assignment]

# #333: Felder, die NICHT in die HMAC-Berechnung eingehen (sie sind das
# Ergebnis der Berechnung selbst).
_CHAIN_FIELDS = ("prev_hash", "hmac")


class AuditWriteError(RuntimeError):
    """An audit record could not be appended without breaking chain integrity."""


def _canonical(record: dict) -> str:
    """Stabile Serialisierung des Record-Inhalts (ohne Chain-Felder) fuer den
    HMAC. ``sort_keys`` macht die Reihenfolge deterministisch; ``default=str``
    spiegelt exakt die Schreib-Serialisierung."""
    content = {k: v for k, v in record.items() if k not in _CHAIN_FIELDS}
    return json.dumps(content, sort_keys=True, default=str)


def compute_hmac(key: str, prev_hash: str, record: dict) -> str:
    """HMAC-SHA256 ueber ``prev_hash + canonical(record)`` — verkettet jede
    Zeile mit der vorherigen (Chain-of-Hashes)."""
    msg = (prev_hash + _canonical(record)).encode("utf-8")
    return hmac.new(key.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def verify_chain(path: Path | str, key: str) -> dict[str, Any]:
    """#333: Verifiziert die HMAC-Chain einer einzelnen JSONL-Datei (per-File-
    Chain — kompatibel mit taeglicher Rotation).

    Returns ``{ok, file, records, error, line}``. Bei der ersten Diskrepanz
    bricht die Pruefung mit ``ok=False`` und Begruendung ab.
    """
    path = Path(path)
    result: dict[str, Any] = {"ok": True, "file": str(path), "records": 0, "error": "", "line": 0}
    if not path.exists():
        result["ok"] = False
        result["error"] = "file not found"
        return result
    prev = ""
    try:
        with path.open("rb") as handle:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            lines = handle.read().decode("utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        result["ok"] = False
        result["error"] = f"unreadable: {exc}"
        return result
    for i, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            result.update(ok=False, error="invalid json", line=i)
            return result
        result["records"] += 1
        stored_hmac = record.get("hmac")
        stored_prev = record.get("prev_hash", "")
        if stored_hmac is None:
            result.update(ok=False, error="missing hmac (unsigned record)", line=i)
            return result
        if stored_prev != prev:
            result.update(ok=False, error="broken chain (prev_hash mismatch)", line=i)
            return result
        expected = compute_hmac(key, stored_prev, record)
        if not hmac.compare_digest(expected, stored_hmac):
            result.update(ok=False, error="hmac mismatch (tampered record)", line=i)
            return result
        prev = stored_hmac
    return result


class JSONLAuditSink(IAuditSink):
    def __init__(self, path: Path | str, rotation: str = "daily", hmac_key: str = ""):
        self._base_path = Path(path)
        self._rotation = rotation
        # #333: Tamper-evidente Audit-Logs. Ohne Key bleibt das Verhalten
        # unveraendert (keine Chain-Felder) — backward-compatible.
        self._hmac_key = hmac_key

    def _current_path(self) -> Path:
        if self._rotation == "daily":
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            stem = self._base_path.stem
            suffix = self._base_path.suffix or ".jsonl"
            return self._base_path.parent / f"{stem}_{date_str}{suffix}"
        return self._base_path

    def write(self, event: Any) -> None:
        path = self._current_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(event, dict):
            record = dict(event)
        elif dataclasses.is_dataclass(event) and not isinstance(event, type):
            record = dataclasses.asdict(event)
        else:
            record = {"data": str(event)}
        record.setdefault("ts", datetime.now(timezone.utc).isoformat())
        if self._hmac_key:
            self._write_chained(path, record)
            return
        self._write_unsigned(path, record)

    def _write_unsigned(self, path: Path, record: dict) -> None:
        """Append only when this rotation file has no signed chain.

        A keyless writer shares the signed writer's file lock on POSIX. This
        makes the first append decisive: either the file remains unsigned, or
        a signed first record prevents every later keyless mutation.
        """
        try:
            with path.open("a+b") as handle:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                if self._has_signed_chain(handle):
                    raise AuditWriteError("unsigned audit append refused: existing chain is signed")
                handle.seek(0, os.SEEK_END)
                handle.write((json.dumps(record, default=str) + "\n").encode("utf-8"))
                handle.flush()
        except AuditWriteError:
            raise
        except (OSError, UnicodeError, TypeError, ValueError) as exc:
            raise AuditWriteError("unsigned audit append failed") from exc

    @staticmethod
    def _has_signed_chain(handle: BinaryIO) -> bool:
        handle.seek(0)
        for line in handle:
            if not line.strip():
                continue
            try:
                record = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return False
            return (
                isinstance(record, dict)
                and isinstance(record.get("hmac"), str)
                and bool(record["hmac"])
                and isinstance(record.get("prev_hash"), str)
            )
        return False

    def _write_chained(self, path: Path, record: dict) -> None:
        """Serialize one signed append against the authoritative on-disk head.

        ``flock`` is taken on the actual rotation file.  Every process therefore
        observes the latest flushed record before computing its own digest; a
        process-local cached head can never become an independent authority.
        """
        if fcntl is None:
            raise AuditWriteError("signed audit append requires POSIX flock support")
        try:
            with path.open("a+b") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                prev = self._read_chain_head(handle)
                digest = compute_hmac(self._hmac_key, prev, record)
                chained = {**record, "prev_hash": prev, "hmac": digest}
                handle.seek(0, os.SEEK_END)
                handle.write((json.dumps(chained, default=str) + "\n").encode("utf-8"))
                # The next lock holder must observe the complete new head.
                handle.flush()
        except AuditWriteError:
            raise
        except (OSError, UnicodeError, TypeError, ValueError) as exc:
            raise AuditWriteError("signed audit append failed") from exc

    def _read_chain_head(self, handle: BinaryIO) -> str:
        line = self._read_last_nonempty_line(handle)
        if line is None:
            return ""
        try:
            record = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AuditWriteError("signed audit tail is not valid JSON") from exc
        if not isinstance(record, dict):
            raise AuditWriteError("signed audit tail is not a JSON object")
        stored_hmac = record.get("hmac")
        stored_prev = record.get("prev_hash", "")
        if not isinstance(stored_hmac, str) or not stored_hmac:
            raise AuditWriteError("signed audit tail has no HMAC")
        if not isinstance(stored_prev, str):
            raise AuditWriteError("signed audit tail has an invalid previous hash")
        expected = compute_hmac(self._hmac_key, stored_prev, record)
        if not hmac.compare_digest(expected, stored_hmac):
            raise AuditWriteError("signed audit tail HMAC does not verify")
        return stored_hmac

    @staticmethod
    def _read_last_nonempty_line(handle: BinaryIO, chunk_size: int = 4096) -> bytes | None:
        """Read only the final non-empty line from a locked binary file."""
        handle.seek(0, os.SEEK_END)
        position = handle.tell()
        data = b""
        while position > 0:
            size = min(chunk_size, position)
            position -= size
            handle.seek(position)
            data = handle.read(size) + data
            stripped = data.rstrip()
            newline = max(stripped.rfind(b"\n"), stripped.rfind(b"\r"))
            if newline >= 0:
                return stripped[newline + 1 :]
        stripped = data.rstrip()
        return stripped or None

    def query(self, query: AuditQuery) -> list[Any]:
        results: list[dict] = []
        for path in sorted(
            self._base_path.parent.glob(
                f"{self._base_path.stem}*{self._base_path.suffix or '.jsonl'}"
            )
        ):
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    record = upcast(json.loads(line))
                    if self._matches(record, query):
                        results.append(record)
                        if len(results) >= query.limit:
                            return results
            except (json.JSONDecodeError, OSError):
                log.warning("Failed to read %s", path)
        return results

    def _matches(self, record: dict, query: AuditQuery) -> bool:
        if query.issue is not None:
            rec_issue = record.get("payload", {}).get("issue") or record.get("issue")
            if rec_issue != query.issue:
                return False
        if query.correlation_id is not None:
            if record.get("correlation_id") != query.correlation_id:
                return False
        if query.owasp_risk is not None:
            rec_owasp = record.get("owasp_risk") or record.get("payload", {}).get("owasp_risk")
            if rec_owasp != query.owasp_risk:
                return False
        if query.event_name is not None:
            rec_name = record.get("event_name") or record.get("name")
            if rec_name != query.event_name:
                return False
        if query.since is not None:
            ts = record.get("ts", "")
            if ts and ts < query.since.isoformat():
                return False
        if query.until is not None:
            ts = record.get("ts", "")
            if ts and ts > query.until.isoformat():
                return False
        return True
