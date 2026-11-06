from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_legacy_entitlement_runtime_and_issuer_are_absent() -> None:
    """#477: Removed entitlement paths must not silently return."""
    removed_files = (
        "samuel/core/license.py",
        "tools/generate_keypair.py",
        "tools/generate_license.py",
        "docs/PREMIUM_SETUP.md",
    )

    assert all(not (ROOT / relative_path).exists() for relative_path in removed_files)
    assert not list((ROOT / "samuel/premium").rglob("*.py"))


def test_production_code_has_no_entitlement_decision_path() -> None:
    """#477: General features must not depend on stale license inputs."""
    forbidden = (
        "SAMUEL_LICENSE_KEY",
        "samuel.core.license",
        "samuel.premium",
        "has_feature(",
        "is_premium_active(",
        "license_status(",
        "TokenLimitHandler",
        "bus._token_limit",
    )
    production = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "samuel").rglob("*.py"))
        if "/tests/" not in path.as_posix()
    )

    for marker in forbidden:
        assert marker not in production


def test_cryptography_is_only_a_github_extra_dependency() -> None:
    """#477: Ed25519 removal must not break RS256 GitHub App auth."""
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    dependencies, optional = pyproject.split("[project.optional-dependencies]", 1)

    assert "cryptography" not in dependencies
    assert 'github = [\n    "cryptography>=43",\n]' in optional
