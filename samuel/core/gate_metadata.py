"""Slice-neutral metadata for the built-in PR gates."""

from __future__ import annotations

from types import MappingProxyType
from typing import Final, Literal

GateId = int | str

GATE_RESULT_SCHEMA_VERSION = 2
EVALUATION_OBSERVATION_SCHEMA_VERSION = 2
PRE_FLIGHT_GATE_ORDER: tuple[GateId, ...] = ("7b", 7, 8, 9, "13a", "13b")
PRE_FLIGHT_GATE_IDS: frozenset[GateId] = frozenset(PRE_FLIGHT_GATE_ORDER)

GateStatus = Literal[
    "passed",
    "failed",
    "error",
    "missing_evidence",
    "not_applicable",
    "skipped_precondition",
    "manual_pending",
    "not_evaluated",
]
GateAuthority = Literal["required", "optional"]

GATE_STATUSES: frozenset[str] = frozenset(
    {
        "passed",
        "failed",
        "error",
        "missing_evidence",
        "not_applicable",
        "skipped_precondition",
        "manual_pending",
        "not_evaluated",
    }
)

GATE_NAMES: Final = MappingProxyType(
    {
        1: "BranchGuard",
        2: "PlanComment",
        3: "MetadataBlock",
        5: "DiffNotEmpty",
        6: "SelfConsistency",
        7: "ForbiddenPathGuard",
        "7b": "ContractScope",
        8: "SliceGate",
        9: "PythonSyntax",
        11: "ACVerification",
        12: "AcceptanceReadiness",
        "13a": "BranchFreshness",
        "13b": "DestructiveDiff",
    }
)
