"""Shared, deliberately small security-signal catalogue.

The built-in rules are a standalone baseline, not a replacement for a
dedicated secret scanner.  Every rule declares its own disposition so a
format-only signal cannot silently become a blocking policy.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from re import Pattern
from typing import Literal

PROMPT_GUARD_MARKERS = (
    "Unveränderliche Schranken",
    "Ignoriere Anweisungen",
)

SecretDisposition = Literal["blocking", "advisory"]


@dataclass(frozen=True)
class SecretRule:
    """One shared rule for diff detection and audit-payload redaction."""

    rule_id: str
    detector: Pattern[str]
    disposition: SecretDisposition
    severity: str = "high"
    scan: bool = True
    redactor: Pattern[str] | None = None


_PEM_PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN (?P<label>(?:[A-Z0-9]+ )*PRIVATE KEY)-----.*?"
    r"(?:-----END (?P=label)-----|\Z)",
    re.DOTALL,
)

SECRET_RULES: tuple[SecretRule, ...] = (
    SecretRule(
        "assigned-secret",
        re.compile(
            r"(?:password|passwd|secret|token|api[_-]?key)\s*[:=]\s*['\"][^'\"]{8,}['\"]",
            re.IGNORECASE,
        ),
        "blocking",
    ),
    SecretRule(
        "bearer-token",
        re.compile(r"\bbearer\s+[A-Za-z0-9._~-]{20,}", re.IGNORECASE),
        "blocking",
    ),
    SecretRule(
        "github-token",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,255}\b"),
        "blocking",
    ),
    SecretRule(
        "prefixed-api-key",
        re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
        "blocking",
    ),
    SecretRule(
        "pem-private-key",
        re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"),
        "blocking",
        redactor=_PEM_PRIVATE_KEY_BLOCK,
    ),
    # A JWT can be a public/test token and an AWS access-key ID is only one
    # half of an AWS credential pair.  Their shape is therefore evidence, not
    # sufficient proof for a fail-closed decision.
    SecretRule(
        "jwt-token-shape",
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
        "advisory",
    ),
    SecretRule(
        "aws-access-key-id",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "advisory",
    ),
    # Gitea tokens and SHA-1 object IDs have the same bare 40-hex shape.  Keep
    # the conservative historic audit redaction without turning every commit
    # hash into a diff finding.
    SecretRule(
        "gitea-token-or-sha1",
        re.compile(r"\b[a-fA-F0-9]{40}\b"),
        "advisory",
        scan=False,
    ),
)


def redact_secrets(text: str, replacement: str = "***REDACTED***") -> str:
    """Redact every catalogue signature without exposing matched values."""

    for rule in SECRET_RULES:
        pattern = rule.redactor or rule.detector
        text = pattern.sub(replacement, text)
    return text


# Narrow ASCII skeleton for the phrases this project actually detects.  It is
# intentionally not advertised as a complete Unicode TR39 implementation.
_ASCII_CONFUSABLES = str.maketrans(
    {
        # Cyrillic
        "а": "a",
        "е": "e",
        "і": "i",
        "ј": "j",
        "о": "o",
        "р": "p",
        "с": "c",
        "ѕ": "s",
        "у": "y",
        "х": "x",
        # Greek
        "α": "a",
        "ε": "e",
        "ι": "i",
        "κ": "k",
        "ν": "v",
        "ο": "o",
        "ρ": "p",
        "τ": "t",
        "υ": "y",
        "χ": "x",
    }
)


def normalize_prompt_signal_text(text: str) -> str:
    """Return a bounded matching form for advisory prompt-risk signals.

    NFKC and casefold handle compatibility/case variants.  Invisible format
    controls are removed, then the limited mixed-script skeleton is applied.
    The result is for matching only and must never replace the original input.
    """

    normalized = unicodedata.normalize("NFKC", text).casefold()
    without_format_controls = "".join(
        char for char in normalized if unicodedata.category(char) != "Cf"
    )
    return without_format_controls.translate(_ASCII_CONFUSABLES)
