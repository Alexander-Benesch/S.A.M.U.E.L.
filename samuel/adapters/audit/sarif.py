"""#368 Task 5: SARIF-Audit-Sink (parallel zum JSONL-Sink).

SARIF (Static Analysis Results Interchange Format, 2.1.0) ist ein Findings-
Format fuer statische-Analyse-Tools. Es bildet **Code-Findings** ab (Symbol,
Pfad, Secret, riskante Pfade) — also Events mit OWASP-Bezug.

**Einschraenkung (bewusst):** Gate-Resultate wie Eval-Score oder Plan-Konsistenz
sind keine ortsgebundenen Findings und passen nur ueber ``result.properties``
hinein. SARIF ist daher KEIN Volltranskript des Bus — das bleibt der
JSONL-Sink. Dieser Sink filtert den Event-Strom auf Findings (``owasp_risk``
gesetzt oder bekannter Finding-Event-Typ) und schreibt eine akkumulierende
SARIF-Datei; alle uebrigen Events werden ignoriert.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from pathlib import Path
from typing import Any

from samuel.core.ports import IAuditSink
from samuel.core.types import AuditQuery

log = logging.getLogger(__name__)

# Event-Typen, die ohne ``owasp_risk`` trotzdem als Finding gelten.
FINDING_EVENTS = frozenset(
    {
        "GateFailed",
        "SecurityTripwireTriggered",
        "TamperDetected",
        "UnauthorizedChange",
        "IntegrityViolation",
    }
)

_TOOL_NAME = "S.A.M.U.E.L."


def _as_record(event: Any) -> dict:
    if isinstance(event, dict):
        return event
    if dataclasses.is_dataclass(event) and not isinstance(event, type):
        return dataclasses.asdict(event)
    return {"payload": {}}


def is_finding(payload: dict) -> bool:
    """Ein Record ist ein SARIF-Finding, wenn er ein ``owasp_risk`` traegt oder
    ein bekannter Finding-Event-Typ ist."""
    if not isinstance(payload, dict):
        return False
    if payload.get("owasp_risk"):
        return True
    return payload.get("message_name") in FINDING_EVENTS


class SARIFAuditSink(IAuditSink):
    def __init__(self, path: Path | str):
        self._path = Path(path)

    def _load(self) -> dict:
        if self._path.exists():
            try:
                doc = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(doc, dict) and doc.get("runs"):
                    return doc
            except (OSError, json.JSONDecodeError) as exc:
                log.warning("SARIF reload failed (%s) — re-initialising", exc)
        return {
            "version": "2.1.0",
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "runs": [
                {
                    "tool": {"driver": {"name": _TOOL_NAME, "rules": []}},
                    "results": [],
                }
            ],
        }

    def _result_for(self, payload: dict) -> dict:
        rule_id = str(payload.get("owasp_risk") or payload.get("message_name") or "finding")
        reason = str(payload.get("reason") or payload.get("message_name") or "")
        disposition = str(payload.get("disposition") or "").lower()
        # Locations aus den im Payload referenzierten Dateien (falls vorhanden).
        files = payload.get("files")
        if isinstance(files, str):
            files = [files]
        if not isinstance(files, list):
            files = [f for f in [payload.get("file"), payload.get("path")] if f]
        locations = [
            {"physicalLocation": {"artifactLocation": {"uri": str(f)}}} for f in files if f
        ]
        props = {
            "owasp_risk": payload.get("owasp_risk"),
            "message_name": payload.get("message_name"),
            "correlation_id": payload.get("correlation_id"),
            "issue": payload.get("issue"),
            "gate": payload.get("gate"),
            "disposition": payload.get("disposition"),
        }
        result: dict[str, Any] = {
            "ruleId": rule_id,
            "level": "warning" if disposition == "advisory" else "error",
            "message": {"text": reason or rule_id},
            "properties": {k: v for k, v in props.items() if v is not None},
        }
        if locations:
            result["locations"] = locations
        return result

    def write(self, event: Any) -> None:
        record = _as_record(event)
        raw_payload = record.get("payload")
        payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}
        if not is_finding(payload):
            return
        try:
            doc = self._load()
            run = doc["runs"][0]
            run["results"].append(self._result_for(payload))
            rule_id = str(payload.get("owasp_risk") or payload.get("message_name") or "finding")
            rules = run["tool"]["driver"].setdefault("rules", [])
            if not any(r.get("id") == rule_id for r in rules):
                rules.append({"id": rule_id})
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            tmp.replace(self._path)
        except Exception:
            log.exception("SARIF write failed")

    def query(self, query: AuditQuery) -> list[Any]:
        # SARIF ist write-orientiert (Findings-Export); abfragbares Volltranskript
        # bleibt der JSONL-Sink.
        return []
