from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

log = logging.getLogger(__name__)

# Ed25519 public key (32 bytes hex). Operator generates with
# tools/generate_keypair.py and replaces this placeholder. Until then,
# no license verifies and the system runs in free mode.
LICENSE_PUBLIC_KEY_HEX = "f8a7ba231ccf178294c4a7767900c23ee4609309a32527af9513f3029c4240f6"

_DEFAULT_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


@dataclass(frozen=True)
class License:
    email: str
    features: frozenset[str]
    issued_at: str


def _config_dir() -> Path:
    override = os.environ.get("SAMUEL_CONFIG_DIR")
    if override:
        return Path(override)
    return _DEFAULT_CONFIG_DIR


def _canonical_payload(data: dict) -> bytes:
    """Canonical JSON bytes for signing/verifying — all fields except signature."""
    payload = {k: v for k, v in data.items() if k != "signature"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _parse_and_verify(raw: str) -> License | None:
    if not LICENSE_PUBLIC_KEY_HEX:
        log.warning(
            "License public key not configured (LICENSE_PUBLIC_KEY_HEX is empty) "
            "— running in free mode. Operator: run tools/generate_keypair.py."
        )
        return None
    try:
        data = json.loads(raw)
        sig_b64 = data["signature"]
        sig = base64.b64decode(sig_b64)
        canonical = _canonical_payload(data)
        pubkey = Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(LICENSE_PUBLIC_KEY_HEX)
        )
        pubkey.verify(sig, canonical)
    except (json.JSONDecodeError, KeyError, ValueError, InvalidSignature) as exc:
        log.warning(
            "License invalid (%s: %s) — running in free mode",
            type(exc).__name__, exc,
        )
        return None

    return License(
        email=str(data.get("email", "")),
        features=frozenset(data.get("features", [])),
        issued_at=str(data.get("issued_at", "")),
    )


def _load() -> License | None:
    # 1. Env var (CI / Secrets-Vaults take precedence)
    raw = os.environ.get("SAMUEL_LICENSE_KEY", "").strip()
    if raw:
        return _parse_and_verify(raw)
    # 2. File (Operator-Setup)
    fp = _config_dir() / "license.json"
    if fp.is_file():
        try:
            return _parse_and_verify(fp.read_text(encoding="utf-8"))
        except OSError as exc:
            log.warning("License file read failed (%s) — free mode", exc)
    return None


_LICENSE: License | None = _load()


def is_premium_active() -> bool:
    """True if a valid signed license is loaded; False otherwise (free mode)."""
    return _LICENSE is not None


def has_feature(name: str) -> bool:
    """True if the active license includes ``name``."""
    return _LICENSE is not None and name in _LICENSE.features


def license_status() -> dict:
    """Status dict for dashboard / health-check rendering."""
    if _LICENSE is None:
        return {"active": False, "reason": "no valid license"}
    return {
        "active": True,
        "email": _LICENSE.email,
        "features": sorted(_LICENSE.features),
        "issued_at": _LICENSE.issued_at,
    }


def _reload() -> None:
    """Re-evaluate the license source — used by tests after monkeypatch."""
    global _LICENSE
    _LICENSE = _load()
