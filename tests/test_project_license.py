from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).parents[1]
APACHE_2_0_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"


def test_root_license_is_unmodified_apache_2_0_text() -> None:
    license_bytes = (ROOT / "LICENSE").read_bytes()

    assert hashlib.sha256(license_bytes).hexdigest() == APACHE_2_0_SHA256


def test_pep639_metadata_declares_and_packages_root_license() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'requires = ["setuptools>=77.0", "setuptools-scm>=10.2,<11"]' in pyproject
    assert 'license = "Apache-2.0"' in pyproject
    assert 'license-files = ["LICENSE"]' in pyproject
    assert 'license = {text = "Proprietary"}' not in pyproject


def test_active_license_docs_cover_the_entire_repository() -> None:
    for relative_path in ("README.md", "docs/README_technical.md"):
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "gesamte" in text or "gesamten" in text
        assert "Apache-2.0" in text
        assert "LICENSE" in text
        assert "maßgeblich" in text
