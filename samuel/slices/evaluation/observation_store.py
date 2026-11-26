"""Idempotent materialized view of bound evaluation observations.

The audit JSONL event stream remains the canonical raw source. This store is
an operational index rebuildable from gate and score observation events.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Literal

_FILENAME = "evaluation_observations.json"


class ObservationConflictError(ValueError):
    """The same identity was presented with different canonical content."""


class EvaluationObservationStore:
    def __init__(self, data_dir: str | Path) -> None:
        self._path = Path(data_dir) / _FILENAME
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        return self._path

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {
            "schema_version": 1,
            "observations": {},
            "scores": {},
            "unavailable": {},
        }

    def load(self) -> dict[str, Any]:
        with self._lock:
            if not self._path.exists():
                return self._empty()
            try:
                value = json.loads(self._path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ObservationConflictError(
                    "evaluation observation store is unreadable"
                ) from exc
            if (
                not isinstance(value, dict)
                or value.get("schema_version") != 1
                or not isinstance(value.get("observations"), dict)
                or not isinstance(value.get("scores"), dict)
                or not isinstance(value.get("unavailable"), dict)
            ):
                raise ObservationConflictError("evaluation observation store has invalid schema")
            return value

    def record_observation(self, payload: dict[str, Any]) -> Literal["created", "duplicate"]:
        with self._lock:
            return self._record_observation(payload)

    def _record_observation(self, payload: dict[str, Any]) -> Literal["created", "duplicate"]:
        key = payload.get("observation_key")
        if not isinstance(key, str) or not key:
            raise ValueError("observation payload needs observation_key")
        document = self.load()
        existing = document["observations"].get(key)
        if existing is not None:
            existing_core = dict(existing)
            payload_core = dict(payload)
            existing_ids = existing_core.pop("correlation_ids", [])
            payload_ids = payload_core.pop("correlation_ids", [])
            if existing_core != payload_core:
                raise ObservationConflictError("observation identity has conflicting content")
            merged_ids = sorted(
                {
                    str(item)
                    for item in [*existing_ids, *payload_ids]
                    if isinstance(item, str) and item
                }
            )
            if merged_ids != existing_ids:
                existing["correlation_ids"] = merged_ids
                self._write(document)
            return "duplicate"
        document["observations"][key] = payload
        self._write(document)
        return "created"

    def record_score(self, payload: dict[str, Any]) -> Literal["created", "duplicate"]:
        with self._lock:
            return self._record_score(payload)

    def _record_score(self, payload: dict[str, Any]) -> Literal["created", "duplicate"]:
        key = payload.get("score_key")
        observation_key = payload.get("observation_key")
        if not isinstance(key, str) or not key or not isinstance(observation_key, str):
            raise ValueError("score payload needs score_key and observation_key")
        document = self.load()
        if observation_key not in document["observations"]:
            raise ObservationConflictError("score derivation has no stored raw observation")
        existing = document["scores"].get(key)
        if existing is not None:
            if existing != payload:
                raise ObservationConflictError("score identity has conflicting content")
            return "duplicate"
        document["scores"][key] = payload
        self._write(document)
        return "created"

    def record_unavailable(self, payload: dict[str, Any]) -> Literal["created", "duplicate"]:
        with self._lock:
            return self._record_unavailable(payload)

    def _record_unavailable(self, payload: dict[str, Any]) -> Literal["created", "duplicate"]:
        key = payload.get("terminal_key")
        if not isinstance(key, str) or not key:
            raise ValueError("unavailable payload needs terminal_key")
        document = self.load()
        existing = document["unavailable"].get(key)
        if existing is not None:
            if existing != payload:
                raise ObservationConflictError("terminal identity has conflicting content")
            return "duplicate"
        document["unavailable"][key] = payload
        self._write(document)
        return "created"

    def _write(self, document: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self._path)
