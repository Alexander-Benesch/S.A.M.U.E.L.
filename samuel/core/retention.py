"""Strict retention policy and plan contracts for ADR-0482 stages 5b/5c."""

from __future__ import annotations

import calendar
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

RetentionMode = Literal["report_only_pending_review", "report_only", "enforce"]
FieldClassification = Literal[
    "pii_free",
    "pii_bearing",
    "secret_bearing",
    "not_automatically_verifiable",
]
StorageKind = Literal[
    "sqlite_table",
    "workspace_registry",
    "audit_jsonl",
    "managed_backup",
    "quarantine_worktree",
]

_PERIOD_RE = re.compile(r"^P(?:(?P<years>\d+)Y)?(?:(?P<months>\d+)M)?(?:(?P<days>\d+)D)?$")
_FIELD_CLASSES = frozenset(
    {
        "pii_free",
        "pii_bearing",
        "secret_bearing",
        "not_automatically_verifiable",
    }
)
_MODES = frozenset({"report_only_pending_review", "report_only", "enforce"})
_STORAGE_KINDS = frozenset(
    {
        "sqlite_table",
        "workspace_registry",
        "audit_jsonl",
        "managed_backup",
        "quarantine_worktree",
    }
)
EXTERNAL_RETENTION_CATEGORIES = frozenset({"audit_logs", "workspaces", "quarantine_worktrees"})
EXECUTABLE_RETENTION_CATEGORIES = frozenset({"score_derivations"})
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_RETENTION_KEYS = frozenset(
    {
        "schema_version",
        "active_profile",
        "operator_role",
        "managed_backup_dir",
        "profiles",
        "categories",
    }
)
_PROFILE_KEYS = frozenset({"role", "minimums", "notice"})
_CATEGORY_KEYS = frozenset(
    {"storage", "source", "mode", "period", "anchor", "fields", "payload_paths", "protections"}
)


class RetentionError(ValueError):
    """Configuration- and payload-free retention failure."""

    def __init__(self, code: str, safe_message: str):
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


@dataclass(frozen=True)
class CalendarPeriod:
    years: int = 0
    months: int = 0
    days: int = 0

    @classmethod
    def parse(cls, value: str) -> CalendarPeriod:
        match = _PERIOD_RE.fullmatch(value)
        if match is None:
            raise RetentionError(
                "retention_period_invalid",
                "Retention periods must use positive ISO calendar units PnY, PnM and/or PnD",
            )
        period = cls(**{name: int(raw or 0) for name, raw in match.groupdict().items()})
        if period.years == period.months == period.days == 0:
            raise RetentionError(
                "retention_period_invalid",
                "Retention periods must be greater than zero",
            )
        return period

    def subtract_from(self, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise RetentionError(
                "retention_timestamp_invalid",
                "Retention cutoff timestamps must be timezone-aware",
            )
        utc = value.astimezone(timezone.utc)
        total_months = utc.year * 12 + (utc.month - 1) - self.years * 12 - self.months
        year, zero_month = divmod(total_months, 12)
        month = zero_month + 1
        day = min(utc.day, calendar.monthrange(year, month)[1])
        try:
            shifted = utc.replace(year=year, month=month, day=day)
        except (OverflowError, ValueError) as exc:
            raise RetentionError(
                "retention_period_invalid",
                "Retention period cannot be resolved on the UTC calendar",
            ) from exc
        if self.days:
            from datetime import timedelta

            shifted -= timedelta(days=self.days)
        return shifted


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def retention_approval_key(
    category_id: str,
    category_digest: str,
    profile_role_digest: str,
) -> str:
    """Bind one approval to exactly one category policy and profile role."""

    return _digest(
        {
            "schema": "retention-approval.v1",
            "category": category_id,
            "category_digest": category_digest,
            "profile_role_digest": profile_role_digest,
        }
    )


def retention_plan_digest(
    *,
    category_id: str,
    category_digest: str,
    profile_role_digest: str,
    cutoff_utc: datetime,
    anchor: str,
    object_ids: tuple[str, ...] | list[str],
) -> str:
    """Bind one execution plan to policy, cutoff and privacy-safe identities."""

    if category_id not in EXECUTABLE_RETENTION_CATEGORIES:
        raise RetentionError(
            "retention_execution_category_not_allowlisted",
            "Retention execution category has no registered deletion strategy",
        )
    if cutoff_utc.tzinfo is None or cutoff_utc.utcoffset() is None:
        raise RetentionError(
            "retention_timestamp_invalid",
            "Retention cutoff timestamps must be timezone-aware",
        )
    normalized = tuple(sorted(object_ids))
    if len(normalized) != len(set(normalized)) or any(
        not _DIGEST_RE.fullmatch(value) for value in normalized
    ):
        raise RetentionError(
            "retention_plan_identity_invalid",
            "Retention plans require unique SHA-256 object identities",
        )
    return _digest(
        {
            "schema": "retention-execution-plan.v1",
            "category": category_id,
            "category_digest": category_digest,
            "profile_role_digest": profile_role_digest,
            "cutoff_utc": cutoff_utc.astimezone(timezone.utc).isoformat(),
            "anchor": anchor,
            "object_ids": normalized,
        }
    )


@dataclass(frozen=True)
class RetentionCategoryPolicy:
    category_id: str
    storage: StorageKind
    source: str
    mode: RetentionMode
    period: str | None
    anchor: str
    fields: dict[str, FieldClassification]
    payload_paths: dict[str, FieldClassification]
    protections: tuple[str, ...]
    profile_minimum: str | None = None

    def configured_period(self) -> CalendarPeriod | None:
        return CalendarPeriod.parse(self.period) if self.period is not None else None

    def effective_period(self, at: datetime) -> tuple[str | None, CalendarPeriod | None]:
        configured = self.configured_period()
        minimum = CalendarPeriod.parse(self.profile_minimum) if self.profile_minimum else None
        if configured is None:
            return None, None
        if minimum is None:
            return self.period, configured
        configured_cutoff = configured.subtract_from(at)
        minimum_cutoff = minimum.subtract_from(at)
        if configured_cutoff > minimum_cutoff:
            raise RetentionError(
                "retention_period_below_profile_minimum",
                f"Retention category {self.category_id!r} is below its active profile minimum",
            )
        return self.period, configured

    def policy_digest(self) -> str:
        return _digest(
            {
                "anchor": self.anchor,
                "fields": self.fields,
                "mode": self.mode,
                "payload_paths": self.payload_paths,
                "period": self.period,
                "profile_minimum": self.profile_minimum,
                "protections": self.protections,
                "source": self.source,
                "storage": self.storage,
            }
        )


@dataclass(frozen=True)
class RetentionPolicyConfig:
    schema_version: str
    active_profile: str
    operator_role: str
    managed_backup_dir: Path
    categories: dict[str, RetentionCategoryPolicy]
    profile_role_digest: str

    @classmethod
    def load(cls, path: Path, *, project_root: Path) -> RetentionPolicyConfig:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RetentionError(
                "retention_config_invalid",
                "Retention configuration could not be read",
            ) from exc
        retention = document.get("retention") if isinstance(document, dict) else None
        if not isinstance(retention, dict):
            raise RetentionError(
                "retention_config_invalid",
                "privacy.json must contain a retention object",
            )
        if "pii_anonymize_after_days" in retention:
            raise RetentionError(
                "retention_legacy_anonymize_setting",
                "pii_anonymize_after_days is retired; use field classifications",
            )
        if set(retention) - _RETENTION_KEYS:
            raise RetentionError(
                "retention_config_field_unknown",
                "Retention configuration contains an unknown field",
            )
        schema_version = str(retention.get("schema_version", ""))
        active_profile = str(retention.get("active_profile", ""))
        operator_role = str(retention.get("operator_role", ""))
        profiles = retention.get("profiles")
        raw_categories = retention.get("categories")
        if (
            schema_version != "1.0"
            or not active_profile
            or not operator_role
            or not isinstance(profiles, dict)
            or not isinstance(raw_categories, dict)
        ):
            raise RetentionError(
                "retention_config_invalid",
                "Retention schema, active profile, operator role and categories are required",
            )
        profile = profiles.get(active_profile)
        if not isinstance(profile, dict):
            raise RetentionError(
                "retention_profile_unknown",
                "Active retention profile is not defined",
            )
        for profile_id, candidate in profiles.items():
            if not isinstance(profile_id, str) or not profile_id or not isinstance(candidate, dict):
                raise RetentionError(
                    "retention_profile_invalid",
                    "Every retention profile must have a non-empty identity and object value",
                )
            if set(candidate) - _PROFILE_KEYS:
                raise RetentionError(
                    "retention_profile_field_unknown",
                    "Retention profile contains an unknown field",
                )
            candidate_role = candidate.get("role")
            candidate_minimums = candidate.get("minimums", {})
            if (
                not isinstance(candidate_role, str)
                or not candidate_role
                or not isinstance(candidate_minimums, dict)
            ):
                raise RetentionError(
                    "retention_profile_invalid",
                    "Every retention profile must define a role and minimums object",
                )
            if set(candidate_minimums) - set(raw_categories):
                raise RetentionError(
                    "retention_profile_category_unknown",
                    "Retention profile contains an unknown category",
                )
            for minimum in candidate_minimums.values():
                if not isinstance(minimum, str):
                    raise RetentionError(
                        "retention_profile_invalid",
                        "Retention profile minimums must be ISO calendar period strings",
                    )
                CalendarPeriod.parse(minimum)
        profile_role = str(profile.get("role", ""))
        if profile_role != operator_role:
            raise RetentionError(
                "retention_profile_role_mismatch",
                "Active retention profile does not match the configured operator role",
            )
        minimums = profile.get("minimums", {})
        if not isinstance(minimums, dict):
            raise RetentionError(
                "retention_profile_invalid",
                "Retention profile minimums must be an object",
            )
        unknown_minimums = sorted(set(minimums) - set(raw_categories))
        if unknown_minimums:
            raise RetentionError(
                "retention_profile_category_unknown",
                "Retention profile contains an unknown category",
            )

        categories: dict[str, RetentionCategoryPolicy] = {}
        for category_id, raw in sorted(raw_categories.items()):
            categories[str(category_id)] = _parse_category(
                str(category_id), raw, minimums.get(category_id)
            )
        now = datetime.now(timezone.utc)
        for category in categories.values():
            category.effective_period(now)

        raw_backup_value = retention.get("managed_backup_dir", "data/backups")
        if not isinstance(raw_backup_value, str) or not raw_backup_value.strip():
            raise RetentionError(
                "retention_managed_backup_dir_invalid",
                "managed_backup_dir must be a non-empty path",
            )
        backup_value = raw_backup_value.strip()
        backup_path = Path(backup_value).expanduser()
        if not backup_path.is_absolute():
            backup_path = project_root / backup_path
        backup_path = backup_path.resolve(strict=False)
        return cls(
            schema_version=schema_version,
            active_profile=active_profile,
            operator_role=operator_role,
            managed_backup_dir=backup_path,
            categories=categories,
            profile_role_digest=_digest(
                {
                    "active_profile": active_profile,
                    "minimums": minimums,
                    "operator_role": operator_role,
                }
            ),
        )


def _parse_category(
    category_id: str,
    raw: Any,
    profile_minimum: Any,
) -> RetentionCategoryPolicy:
    if not isinstance(raw, dict):
        raise RetentionError(
            "retention_category_invalid",
            f"Retention category {category_id!r} must be an object",
        )
    if not category_id:
        raise RetentionError(
            "retention_category_invalid",
            "Retention category identities must not be empty",
        )
    if set(raw) - _CATEGORY_KEYS:
        raise RetentionError(
            "retention_category_field_unknown",
            f"Retention category {category_id!r} contains an unknown field",
        )
    storage = str(raw.get("storage", ""))
    source = str(raw.get("source", ""))
    mode = str(raw.get("mode", ""))
    period_value = raw.get("period")
    period = str(period_value) if period_value is not None else None
    anchor = str(raw.get("anchor", ""))
    fields = _classifications(raw.get("fields"), category_id, "fields")
    payload_paths = _classifications(
        raw.get("payload_paths", {}), category_id, "payload_paths", allow_empty=True
    )
    protections_raw = raw.get("protections", [])
    if (
        storage not in _STORAGE_KINDS
        or not source
        or mode not in _MODES
        or not anchor
        or not isinstance(protections_raw, list)
        or any(not isinstance(value, str) or not value for value in protections_raw)
        or len(protections_raw) != len(set(protections_raw))
    ):
        raise RetentionError(
            "retention_category_invalid",
            f"Retention category {category_id!r} is incomplete or invalid",
        )
    if mode == "enforce" and category_id not in EXECUTABLE_RETENTION_CATEGORIES:
        raise RetentionError(
            "retention_execution_category_not_allowlisted",
            "Retention enforce mode requires a registered deletion strategy",
        )
    if period is not None:
        CalendarPeriod.parse(period)
    if profile_minimum is not None:
        CalendarPeriod.parse(str(profile_minimum))
    if any(name.endswith("_json") for name in fields) and "$" not in payload_paths:
        raise RetentionError(
            "retention_payload_classification_incomplete",
            f"Retention category {category_id!r} must classify its JSON payload root",
        )
    if anchor not in fields:
        raise RetentionError(
            "retention_anchor_unknown",
            f"Retention category {category_id!r} anchor is not a classified field",
        )
    return RetentionCategoryPolicy(
        category_id=category_id,
        storage=storage,  # type: ignore[arg-type]
        source=source,
        mode=mode,  # type: ignore[arg-type]
        period=period,
        anchor=anchor,
        fields=fields,
        payload_paths=payload_paths,
        protections=tuple(protections_raw),
        profile_minimum=str(profile_minimum) if profile_minimum is not None else None,
    )


def _classifications(
    value: Any,
    category_id: str,
    field_name: str,
    *,
    allow_empty: bool = False,
) -> dict[str, FieldClassification]:
    if not isinstance(value, dict) or (not value and not allow_empty):
        raise RetentionError(
            "retention_field_classification_invalid",
            f"Retention category {category_id!r} must define {field_name}",
        )
    result: dict[str, FieldClassification] = {}
    for name, classification in value.items():
        if not isinstance(name, str) or not name or classification not in _FIELD_CLASSES:
            raise RetentionError(
                "retention_field_classification_invalid",
                f"Retention category {category_id!r} contains an invalid classification",
            )
        result[name] = classification
    return result
