"""Persistent per-issue baseline storage for anti-regression.

After every passing Eval the highest score per issue is persisted to
``<data_dir>/eval_baselines.json`` ({issue_number: float}) so that the next
Eval for the same issue must score at least that high to pass. Without
this, a subsequent eval with a lower score would still pass against the
static config baseline — silent regression.

The store is intentionally tiny and self-contained: a JSON dict, atomic
write via ``.tmp`` + rename, graceful degrade on corrupt files (treat as
empty). Keep this in the evaluation slice — no other slice should read
or write the file directly.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

_BASELINE_FILENAME = "eval_baselines.json"


def _path(data_dir: Path | str) -> Path:
    return Path(data_dir) / _BASELINE_FILENAME


def load_baselines(data_dir: Path | str) -> dict[int, float]:
    """Read the persisted baselines map. Corrupt or missing file → empty."""
    path = _path(data_dir)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Baseline store unreadable at %s: %s — treating as empty", path, exc)
        return {}
    if not isinstance(raw, dict):
        log.warning("Baseline store at %s is not a dict — ignoring", path)
        return {}
    out: dict[int, float] = {}
    for key, value in raw.items():
        try:
            out[int(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def get_baseline(data_dir: Path | str, issue_number: int, default: float = 0.0) -> float:
    """Return the persisted baseline for ``issue_number`` (``default`` if none)."""
    return load_baselines(data_dir).get(int(issue_number), default)


def promote_baseline(
    data_dir: Path | str, issue_number: int, score: float
) -> float:
    """If ``score`` exceeds the persisted baseline, raise it. Returns the
    effective (post-update) baseline for ``issue_number``."""
    baselines = load_baselines(data_dir)
    issue_key = int(issue_number)
    current = baselines.get(issue_key, 0.0)
    new_baseline = max(current, float(score))
    if new_baseline == current and issue_key in baselines:
        return current
    baselines[issue_key] = new_baseline
    _write_atomic(data_dir, baselines)
    return new_baseline


def _write_atomic(data_dir: Path | str, baselines: dict[int, float]) -> None:
    path = _path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {str(k): v for k, v in baselines.items()}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    tmp.rename(path)
