"""Smoke tests for event classes that have no behavioural test yet.

Event classes are dataclasses with a payload dict and a name; they are
plain DTOs published over the bus. Until each is exercised by its
producing slice (e.g., HealingFailed by the healing slice), this smoke
test ensures every class can be instantiated, serialises a payload, and
keeps the architecture-test
``test_event_types_complete`` from skipping.

Each event listed below should be removed from ``COVERED_EVENTS`` here
once a real producing-slice test references it directly.
"""
from __future__ import annotations

from samuel.core.events import (
    BranchCreated,
    BranchDeleted,
    ConfigValidationFailed,
    HealingFailed,
    HookIntegrityFailed,
    ImplementationFailed,
    IssueSkipped,
    PlanRevised,
    ProviderFallbackUsed,
    QualityRetry,
    SkeletonRebuilt,
)

COVERED_EVENTS = [
    BranchCreated,
    BranchDeleted,
    ConfigValidationFailed,
    HealingFailed,
    HookIntegrityFailed,
    ImplementationFailed,
    IssueSkipped,
    PlanRevised,
    ProviderFallbackUsed,
    QualityRetry,
    SkeletonRebuilt,
]


def test_event_classes_instantiable_with_payload():
    for cls in COVERED_EVENTS:
        evt = cls(payload={"smoke": True})
        assert evt.payload == {"smoke": True}
        assert evt.name == cls.__name__
        assert hasattr(evt, "ts")


def test_event_classes_carry_correlation_id():
    for cls in COVERED_EVENTS:
        evt = cls(payload={}, correlation_id="corr-123")
        assert evt.correlation_id == "corr-123"
