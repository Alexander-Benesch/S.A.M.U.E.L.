"""One-way, checksum-bound imports from pre-SQLite runtime state."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from samuel.adapters.state.sqlite import SQLiteQualityMetricsRegistry, SQLiteStateStore
from samuel.core.state import (
    EvaluationTerminalRecord,
    ObservationRecord,
    RunProjectionRecord,
    ScoreDerivationRecord,
    StateStoreError,
)

_LEGACY_FILES = (
    "evaluation_observations.json",
    "quality_metrics.json",
    "score_history.json",
    "eval_baselines.json",
)
_HEALING_CLAIMS_FILE = "bound_healing_attempts.json"


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _read_json(path: Path) -> tuple[bytes, Any]:
    try:
        raw = path.read_bytes()
        return raw, json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StateStoreError(
            "state_legacy_unreadable",
            f"Legacy runtime-state source {path.name!r} is unreadable",
        ) from exc


def _parse_time(value: Any, fallback: datetime) -> datetime:
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is not None and parsed.utcoffset() is not None:
                return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    return fallback


class LegacyStateMigrator:
    """Import known JSON stores and retire their active filenames."""

    def __init__(self, store: SQLiteStateStore) -> None:
        self._store = store

    def migrate(self) -> dict[str, Any]:
        reports: list[dict[str, Any]] = []
        for filename in _LEGACY_FILES:
            path = self._store.data_dir / filename
            if not path.exists():
                continue
            reports.append(self._migrate_path(path))
        return {
            "format": "legacy-state-import.v1",
            "sources": reports,
            "imported_sources": sum(1 for row in reports if row["status"] == "imported"),
        }

    def migrate_authority(self) -> dict[str, Any]:
        """Import the legacy at-most-once ledger as one authority transaction."""

        path = self._store.data_dir / _HEALING_CLAIMS_FILE
        if not path.exists():
            return {
                "format": "legacy-authority-import.v1",
                "sources": [],
                "imported_sources": 0,
            }
        if path.is_symlink() or not path.is_file():
            raise StateStoreError(
                "state_legacy_unsafe",
                f"Legacy runtime-state source {path.name!r} is not a regular file",
            )
        raw, document = _read_json(path)
        checksum = f"sha256:{hashlib.sha256(raw).hexdigest()}"
        archive = path.with_name(f"{path.name}.migrated-{checksum.removeprefix('sha256:')}")
        marker = self._marker(path)
        if marker is not None:
            if str(marker["checksum"]) != checksum:
                raise StateStoreError(
                    "state_legacy_changed",
                    f"Legacy runtime-state source {path.name!r} changed after import",
                )
            self._store._sync_authority_witness()
            self._archive(path, archive, raw)
            return {
                "format": "legacy-authority-import.v1",
                "sources": [
                    {"source": path.name, "checksum": checksum, "status": "already_imported"}
                ],
                "imported_sources": 0,
            }

        attempts = self._validate_healing_claims(document)
        imported_at = datetime.now(timezone.utc)
        imported_timestamp = imported_at.isoformat(timespec="microseconds")
        counts = {"claimed": 0, "attempted": 0}
        with self._store._connection() as connection, connection:
            for observation_key, raw_claim in attempts.items():
                legacy_status = str(raw_claim["status"])
                status = "claimed" if legacy_status == "claimed" else "attempted"
                outcome = None if status == "claimed" else legacy_status
                existing = connection.execute(
                    "SELECT status, outcome FROM healing_claims WHERE observation_key = ?",
                    (observation_key,),
                ).fetchone()
                if existing is not None:
                    if (str(existing["status"]), existing["outcome"]) != (status, outcome):
                        raise StateStoreError(
                            "state_legacy_conflict",
                            "Legacy healing claim conflicts with persisted authority",
                        )
                else:
                    connection.execute(
                        "INSERT INTO healing_claims VALUES (?, 0, 'legacy-import', ?, ?, NULL, ?)",
                        (observation_key, status, outcome, imported_timestamp),
                    )
                counts[status] += 1
            connection.execute(
                "INSERT INTO legacy_imports VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(path.resolve()),
                    checksum,
                    "bound-healing-attempts.v1",
                    str(archive.resolve()),
                    json.dumps(counts, separators=(",", ":"), sort_keys=True),
                    imported_timestamp,
                ),
            )
            connection.execute(
                "UPDATE authority_metadata SET authority_epoch = authority_epoch + 1, "
                "updated_at = ? WHERE singleton = 1",
                (imported_timestamp,),
            )
        self._store._sync_authority_witness()
        self._archive(path, archive, raw)
        return {
            "format": "legacy-authority-import.v1",
            "sources": [
                {
                    "source": path.name,
                    "checksum": checksum,
                    "status": "imported",
                    "counts": counts,
                }
            ],
            "imported_sources": 1,
        }

    @staticmethod
    def _validate_healing_claims(document: Any) -> dict[str, dict[str, Any]]:
        if (
            not isinstance(document, dict)
            or document.get("schema_version") != 1
            or not isinstance(document.get("attempts"), dict)
        ):
            raise StateStoreError(
                "state_legacy_invalid",
                "Legacy healing claim source has an invalid schema",
            )
        attempts: dict[str, dict[str, Any]] = {}
        for observation_key, raw_claim in document["attempts"].items():
            if (
                not isinstance(observation_key, str)
                or not observation_key
                or not isinstance(raw_claim, dict)
                or not isinstance(raw_claim.get("status"), str)
                or not raw_claim["status"]
            ):
                raise StateStoreError(
                    "state_legacy_invalid",
                    "Legacy healing claim entry has an invalid schema",
                )
            attempts[observation_key] = raw_claim
        return attempts

    def _migrate_path(self, path: Path) -> dict[str, Any]:
        if path.is_symlink() or not path.is_file():
            raise StateStoreError(
                "state_legacy_unsafe",
                f"Legacy runtime-state source {path.name!r} is not a regular file",
            )
        raw, document = _read_json(path)
        checksum = f"sha256:{hashlib.sha256(raw).hexdigest()}"
        archive = path.with_name(f"{path.name}.migrated-{checksum.removeprefix('sha256:')}")
        marker = self._marker(path)
        if marker is not None:
            if str(marker["checksum"]) != checksum:
                raise StateStoreError(
                    "state_legacy_changed",
                    f"Legacy runtime-state source {path.name!r} changed after import",
                )
            self._archive(path, archive, raw)
            return {"source": path.name, "checksum": checksum, "status": "already_imported"}

        fallback = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        if path.name == "evaluation_observations.json":
            counts = self._import_observations(document, fallback)
            format_version = "evaluation-observations.v1"
        elif path.name == "quality_metrics.json":
            counts = self._import_quality(document)
            format_version = "quality-metrics.legacy"
        elif path.name == "score_history.json":
            counts = self._import_score_history(document, fallback)
            format_version = "score-history.legacy"
        elif path.name == "eval_baselines.json":
            counts = self._import_baselines(document, fallback)
            format_version = "eval-baselines.legacy"
        else:  # pragma: no cover - fixed allowlist
            raise AssertionError(path.name)

        imported_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        try:
            with self._store._connection() as connection, connection:
                connection.execute(
                    "INSERT INTO legacy_imports VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        str(path.resolve()),
                        checksum,
                        format_version,
                        str(archive.resolve()),
                        json.dumps(counts, separators=(",", ":"), sort_keys=True),
                        imported_at,
                    ),
                )
        except StateStoreError:
            raise
        self._archive(path, archive, raw)
        return {
            "source": path.name,
            "checksum": checksum,
            "status": "imported",
            "counts": counts,
        }

    def _marker(self, path: Path) -> Any:
        with self._store._connection() as connection:
            return connection.execute(
                "SELECT * FROM legacy_imports WHERE source_path = ?",
                (str(path.resolve()),),
            ).fetchone()

    @staticmethod
    def _archive(path: Path, archive: Path, raw: bytes) -> None:
        if archive.exists():
            try:
                if archive.read_bytes() != raw:
                    raise StateStoreError(
                        "state_legacy_archive_conflict",
                        f"Legacy archive target for {path.name!r} has different content",
                    )
                path.unlink()
                return
            except OSError as exc:
                raise StateStoreError(
                    "state_legacy_archive_failed",
                    f"Legacy runtime-state source {path.name!r} could not be retired",
                ) from exc
        try:
            os.replace(path, archive)
            archive.chmod(0o400)
        except OSError as exc:
            raise StateStoreError(
                "state_legacy_archive_failed",
                f"Legacy runtime-state source {path.name!r} could not be retired",
            ) from exc

    def _import_observations(self, document: Any, fallback: datetime) -> dict[str, int]:
        if (
            not isinstance(document, dict)
            or document.get("schema_version") != 1
            or not isinstance(document.get("observations"), dict)
            or not isinstance(document.get("scores"), dict)
            or not isinstance(document.get("unavailable"), dict)
        ):
            raise StateStoreError(
                "state_legacy_invalid",
                "Legacy evaluation observation source has an invalid schema",
            )
        observations: dict[str, ObservationRecord] = {}
        for key, raw in document["observations"].items():
            if not isinstance(raw, dict) or raw.get("observation_key") != key:
                raise StateStoreError(
                    "state_legacy_invalid",
                    "Legacy evaluation observation identity is invalid",
                )
            subject = raw.get("evaluation_subject")
            if not isinstance(subject, dict):
                raise StateStoreError(
                    "state_legacy_invalid",
                    "Legacy evaluation observation has no bound subject",
                )
            record = ObservationRecord(
                observation_key=str(key),
                subject_key=_canonical_digest(subject),
                evidence_digest=str(raw.get("evidence_digest", "")),
                observation_schema=f"bound.v{int(raw.get('schema_version', 1))}",
                issue_number=int(raw.get("issue", 0) or 0),
                evidence_origin="bound_acceptance_evidence",
                payload={name: value for name, value in raw.items() if name != "correlation_ids"},
                observed_at=fallback,
            )
            self._store.observations.put_observation(record)
            observations[str(key)] = record

        for key, raw in document["scores"].items():
            if not isinstance(raw, dict) or raw.get("score_key") != key:
                raise StateStoreError(
                    "state_legacy_invalid",
                    "Legacy score derivation identity is invalid",
                )
            parent = observations.get(str(raw.get("observation_key", "")))
            if parent is None:
                raise StateStoreError(
                    "state_observation_missing",
                    "Legacy score derivation requires its bound observation",
                )
            self._store.observations.put_derivation(
                ScoreDerivationRecord(
                    score_key=str(key),
                    observation_key=parent.observation_key,
                    scoring_policy_version=str(raw.get("scoring_policy_version", "unknown")),
                    scoring_policy_digest=str(raw.get("scoring_policy_digest", "")),
                    formula_version=str(raw.get("formula_version", "unknown")),
                    score=(
                        float(raw["score"]) if isinstance(raw.get("score"), (int, float)) else None
                    ),
                    issue_number=int(raw.get("issue", parent.issue_number) or 0),
                    evidence_origin=str(raw.get("evidence_origin", parent.evidence_origin)),
                    observation_schema=parent.observation_schema,
                    payload=dict(raw),
                    derived_at=fallback,
                )
            )

        for key, raw in document["unavailable"].items():
            if not isinstance(raw, dict) or raw.get("terminal_key") != key:
                raise StateStoreError(
                    "state_legacy_invalid",
                    "Legacy unavailable evaluation identity is invalid",
                )
            self._store.observations.put_terminal(
                EvaluationTerminalRecord(
                    terminal_key=str(key),
                    issue_number=int(raw.get("issue", 0) or 0),
                    status="unavailable",
                    payload=dict(raw),
                    observed_at=fallback,
                )
            )
        return {
            "observations": len(document["observations"]),
            "score_derivations": len(document["scores"]),
            "evaluation_terminals": len(document["unavailable"]),
        }

    def _import_quality(self, document: Any) -> dict[str, int]:
        if not isinstance(document, dict):
            raise StateStoreError(
                "state_legacy_invalid",
                "Legacy quality-metrics source has an invalid schema",
            )
        registry = self._store.quality_metrics
        if not isinstance(registry, SQLiteQualityMetricsRegistry):  # pragma: no cover
            raise StateStoreError(
                "state_legacy_invalid", "SQLite quality projection is unavailable"
            )
        count = 0
        for raw in document.values():
            if not isinstance(raw, dict):
                raise StateStoreError(
                    "state_legacy_invalid",
                    "Legacy quality-metrics row has an invalid schema",
                )
            registry.import_aggregate(dict(raw))
            count += 1
        return {"quality_metrics": count}

    def _import_score_history(self, document: Any, fallback: datetime) -> dict[str, int]:
        if not isinstance(document, list):
            raise StateStoreError(
                "state_legacy_invalid",
                "Legacy score-history source has an invalid schema",
            )
        count = 0
        for index, raw in enumerate(document):
            if not isinstance(raw, dict):
                raise StateStoreError(
                    "state_legacy_invalid",
                    "Legacy score-history row has an invalid schema",
                )
            issue = int(raw.get("issue", 0) or 0)
            timestamp = _parse_time(raw.get("ts"), fallback)
            identity = _canonical_digest(
                {"source": "score_history.json", "index": index, "row": raw}
            )
            event = {
                "ts": timestamp.isoformat(),
                "payload": {
                    **raw,
                    "message_name": "EvalCompleted" if raw.get("passed") is True else "EvalFailed",
                    "correlation_id": identity,
                    "evidence_origin": "unbound_worktree",
                    "observation_schema": "legacy.v1",
                },
            }
            self._store.projections.upsert_projection(
                RunProjectionRecord(
                    projection_key=identity,
                    issue_number=issue,
                    correlation_id=identity,
                    series="workflow.legacy.v1",
                    status="legacy",
                    payload={"events": [event], "source": "score_history.json"},
                    updated_at=timestamp,
                )
            )
            count += 1
        return {"legacy_score_rows": count}

    def _import_baselines(self, document: Any, fallback: datetime) -> dict[str, int]:
        if not isinstance(document, dict):
            raise StateStoreError(
                "state_legacy_invalid",
                "Legacy baseline source has an invalid schema",
            )
        count = 0
        for raw_issue, value in document.items():
            try:
                issue, baseline = int(raw_issue), float(value)
            except (TypeError, ValueError) as exc:
                raise StateStoreError(
                    "state_legacy_invalid",
                    "Legacy baseline row has an invalid schema",
                ) from exc
            key = _canonical_digest({"source": "eval_baselines.json", "issue": issue})
            self._store.projections.upsert_projection(
                RunProjectionRecord(
                    projection_key=key,
                    issue_number=issue,
                    correlation_id="",
                    series="evaluation-baseline.legacy.v1",
                    status="historical",
                    payload={"baseline": baseline, "non_binding": True},
                    updated_at=fallback,
                )
            )
            count += 1
        return {"legacy_baselines": count}
