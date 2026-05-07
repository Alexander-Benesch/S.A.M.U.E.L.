"""#294: Tests for premium-license verification (Ed25519).

Uses a freshly generated test keypair per test — does NOT use the production
public key embedded in samuel/core/license.py. Production deployment requires
the operator to run tools/generate_keypair.py once and embed the resulting
PUBLIC_KEY_HEX into LICENSE_PUBLIC_KEY_HEX.
"""
from __future__ import annotations

import base64
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


@pytest.fixture
def test_keypair():
    """Fresh Ed25519 keypair per test."""
    private = Ed25519PrivateKey.generate()
    public_hex = private.public_key().public_bytes_raw().hex()
    return private, public_hex


def _sign(data: dict, private) -> dict:
    payload = {k: v for k, v in data.items() if k != "signature"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sig = private.sign(canonical)
    return {**payload, "signature": base64.b64encode(sig).decode("ascii")}


def _activate(monkeypatch, test_keypair, license_data):
    private, public_hex = test_keypair
    signed = _sign(license_data, private)
    monkeypatch.setenv("SAMUEL_LICENSE_KEY", json.dumps(signed))

    from samuel.core import license as _lic
    monkeypatch.setattr(_lic, "LICENSE_PUBLIC_KEY_HEX", public_hex)
    _lic._reload()
    return _lic


def test_license_valid_signature_activates_premium(monkeypatch, test_keypair):
    lic = _activate(monkeypatch, test_keypair, {
        "email": "alice@example.com",
        "features": ["llm_routing", "api_validate"],
        "issued_at": "2026-05-05T12:00:00Z",
    })
    assert lic.is_premium_active() is True
    assert lic.has_feature("llm_routing") is True
    assert lic.has_feature("api_validate") is True
    assert lic.has_feature("nonexistent") is False


def test_license_invalid_signature_falls_back_to_free(monkeypatch, test_keypair):
    private, public_hex = test_keypair
    signed = _sign({
        "email": "alice@example.com",
        "features": ["llm_routing"],
        "issued_at": "2026-05-05T12:00:00Z",
    }, private)
    # Tamper with email — signature now invalid
    signed["email"] = "mallory@example.com"
    monkeypatch.setenv("SAMUEL_LICENSE_KEY", json.dumps(signed))

    from samuel.core import license as _lic
    monkeypatch.setattr(_lic, "LICENSE_PUBLIC_KEY_HEX", public_hex)
    _lic._reload()

    assert _lic.is_premium_active() is False
    assert _lic.has_feature("llm_routing") is False


def test_license_missing_file_is_free_mode(monkeypatch, tmp_path):
    monkeypatch.delenv("SAMUEL_LICENSE_KEY", raising=False)
    monkeypatch.setenv("SAMUEL_CONFIG_DIR", str(tmp_path))  # empty
    from samuel.core import license as _lic
    _lic._reload()
    assert _lic.is_premium_active() is False
    assert _lic.license_status()["active"] is False


def test_license_env_var_takes_precedence_over_file(monkeypatch, tmp_path, test_keypair):
    private, public_hex = test_keypair
    file_lic = _sign({
        "email": "file@example.com",
        "features": ["from_file"],
        "issued_at": "2026-05-05T12:00:00Z",
    }, private)
    (tmp_path / "license.json").write_text(json.dumps(file_lic), encoding="utf-8")
    monkeypatch.setenv("SAMUEL_CONFIG_DIR", str(tmp_path))

    env_lic = _sign({
        "email": "env@example.com",
        "features": ["from_env"],
        "issued_at": "2026-05-05T12:00:00Z",
    }, private)
    monkeypatch.setenv("SAMUEL_LICENSE_KEY", json.dumps(env_lic))

    from samuel.core import license as _lic
    monkeypatch.setattr(_lic, "LICENSE_PUBLIC_KEY_HEX", public_hex)
    _lic._reload()

    assert _lic.has_feature("from_env") is True
    assert _lic.has_feature("from_file") is False


def test_has_feature_returns_false_in_free_mode(monkeypatch, tmp_path):
    monkeypatch.delenv("SAMUEL_LICENSE_KEY", raising=False)
    monkeypatch.setenv("SAMUEL_CONFIG_DIR", str(tmp_path))
    from samuel.core import license as _lic
    _lic._reload()
    assert _lic.has_feature("anything") is False


def test_license_status_dict_shape(monkeypatch, test_keypair):
    lic = _activate(monkeypatch, test_keypair, {
        "email": "bob@example.com",
        "features": ["llm_routing"],
        "issued_at": "2026-05-05T12:00:00Z",
    })
    status = lic.license_status()
    assert status["active"] is True
    assert status["email"] == "bob@example.com"
    assert status["features"] == ["llm_routing"]
    assert status["issued_at"] == "2026-05-05T12:00:00Z"


def test_license_no_public_key_configured_is_free_mode(monkeypatch, test_keypair):
    """Empty LICENSE_PUBLIC_KEY_HEX (= placeholder) -> free mode even with valid license."""
    private, _ = test_keypair
    signed = _sign({
        "email": "alice@example.com",
        "features": ["llm_routing"],
        "issued_at": "2026-05-05T12:00:00Z",
    }, private)
    monkeypatch.setenv("SAMUEL_LICENSE_KEY", json.dumps(signed))

    from samuel.core import license as _lic
    monkeypatch.setattr(_lic, "LICENSE_PUBLIC_KEY_HEX", "")  # placeholder
    _lic._reload()

    assert _lic.is_premium_active() is False


def test_license_malformed_json_is_free_mode(monkeypatch, test_keypair):
    _, public_hex = test_keypair
    monkeypatch.setenv("SAMUEL_LICENSE_KEY", "{not valid json")

    from samuel.core import license as _lic
    monkeypatch.setattr(_lic, "LICENSE_PUBLIC_KEY_HEX", public_hex)
    _lic._reload()

    assert _lic.is_premium_active() is False
