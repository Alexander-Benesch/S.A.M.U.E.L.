"""DTO smoke tests for the explicitly listed event classes.

Event classes are dataclasses with a payload dict and a name; they are
plain DTOs published over the bus. These checks show that the listed classes
can be instantiated and carry their common fields. They do not claim complete
producer or event-catalogue coverage.

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
