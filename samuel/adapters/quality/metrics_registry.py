"""#153: persistierte LLM-Qualitaets-Aggregation pro (provider, model, task).

Schreibt einen recency-gewichteten Gleitdurchschnitt (EWMA) nach
``data/quality_metrics.json``. EWMA statt einfachem Mittel, damit ein Modell,
das sich verbessert (oder verschlechtert), nicht ewig von alten Scores
ueberlagert wird — neuere Evals zaehlen staerker (#153-AC "Recency").
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from samuel.core.ports import IQualityMetricsRegistry

log = logging.getLogger(__name__)

# Glaettungsfaktor: 0.3 => der juengste Score traegt 30%, die Historie 70%.
# Hoeher = reaktiver auf neue Evals, niedriger = stabiler.
DEFAULT_ALPHA = 0.3


def _series(metadata: dict[str, Any] | None) -> tuple[str, str, str]:
    if metadata and metadata.get("evidence_origin") == "bound_acceptance_evidence":
        return (
            "bound_acceptance_evidence",
            str(metadata.get("scoring_policy_version", "unknown")),
            str(metadata.get("formula_version", "unknown")),
        )
    return ("unbound_worktree", "legacy", "legacy")


def _key(
    provider: str,
    model: str,
    task: str,
    series: tuple[str, str, str] = ("unbound_worktree", "legacy", "legacy"),
) -> str:
    if series == ("unbound_worktree", "legacy", "legacy"):
        return f"{provider}|{model}|{task}"
    return "|".join((provider, model, task, *series))


class FileQualityMetricsRegistry(IQualityMetricsRegistry):
    def __init__(self, data_dir: str | Path = "data", alpha: float = DEFAULT_ALPHA):
        self._path = Path(data_dir) / "quality_metrics.json"
        self._alpha = alpha

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("could not read %s: %s", self._path, exc)
            return {}

    def _write(self, data: dict[str, Any]) -> None:
        tmp = self._path.with_suffix(".tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            tmp.replace(self._path)
        except OSError as exc:
            log.warning("could not write %s: %s", self._path, exc)

    def record(
        self,
        provider: str,
        model: str,
        task: str,
        score: float,
        passed: bool | None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        from datetime import datetime, timezone

        data = self._load()
        series = _series(metadata)
        k = _key(provider, model, task, series)
        entry = data.get(k) if isinstance(data.get(k), dict) else None
        if entry is None:
            entry = {
                "provider": provider,
                "model": model,
                "task": task,
                "evidence_origin": series[0],
                "scoring_policy_version": series[1],
                "formula_version": series[2],
                "ewma_score": float(score),
                "count": 0,
                "passed": 0,
                "failed": 0,
                "observed": 0,
                "last_score": float(score),
                "last_ts": "",
            }
        else:
            prev = float(entry.get("ewma_score", score))
            entry["ewma_score"] = round(
                self._alpha * float(score) + (1 - self._alpha) * prev,
                4,
            )
        entry["count"] = int(entry.get("count", 0)) + 1
        if passed is True:
            entry["passed"] = int(entry.get("passed", 0)) + 1
        elif passed is False:
            entry["failed"] = int(entry.get("failed", 0)) + 1
        else:
            entry["observed"] = int(entry.get("observed", 0)) + 1
        entry["last_score"] = float(score)
        entry["last_ts"] = datetime.now(timezone.utc).isoformat()
        entry["provider"], entry["model"], entry["task"] = provider, model, task
        entry["evidence_origin"] = series[0]
        entry["scoring_policy_version"] = series[1]
        entry["formula_version"] = series[2]
        if metadata:
            entry["last_observation"] = dict(metadata)
        data[k] = entry
        self._write(data)

    def score_for(
        self,
        provider: str,
        model: str,
        task: str,
    ) -> float | None:
        matching = [
            entry
            for entry in self._load().values()
            if isinstance(entry, dict)
            and entry.get("provider") == provider
            and entry.get("model") == model
            and entry.get("task") == task
            and isinstance(entry.get("ewma_score"), (int, float))
        ]
        if matching:
            latest = max(matching, key=lambda item: str(item.get("last_ts", "")))
            return float(latest["ewma_score"])
        return None

    def aggregates(self) -> list[dict]:
        rows: list[dict] = []
        for entry in self._load().values():
            if not isinstance(entry, dict):
                continue
            graded = int(entry.get("passed", 0)) + int(entry.get("failed", 0))
            rows.append(
                {
                    "provider": entry.get("provider", ""),
                    "model": entry.get("model", ""),
                    "task": entry.get("task", ""),
                    "evidence_origin": entry.get("evidence_origin", "unbound_worktree"),
                    "scoring_policy_version": entry.get("scoring_policy_version", "legacy"),
                    "formula_version": entry.get("formula_version", "legacy"),
                    "ewma_score": entry.get("ewma_score"),
                    "count": int(entry.get("count", 0)),
                    "passed": int(entry.get("passed", 0)),
                    "failed": int(entry.get("failed", 0)),
                    "observed": int(entry.get("observed", 0)),
                    "success_rate_pct": (
                        round(int(entry.get("passed", 0)) / graded * 100) if graded else None
                    ),
                    "last_score": entry.get("last_score"),
                    "last_ts": entry.get("last_ts", ""),
                }
            )
        rows.sort(key=lambda r: r.get("last_ts", ""), reverse=True)
        return rows
