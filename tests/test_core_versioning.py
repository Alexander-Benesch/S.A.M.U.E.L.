from __future__ import annotations

import pytest

from samuel.build_info import product_tag, product_tag_sort_key, product_version_from_tag


@pytest.mark.parametrize(
    ("tag", "version"),
    [
        ("v2.0.0a1", "2.0.0a1"),
        ("v2.0.0b3", "2.0.0b3"),
        ("v2.0.0rc1", "2.0.0rc1"),
        ("v2.0.0", "2.0.0"),
    ],
)
def test_product_tag_round_trip(tag: str, version: str) -> None:
    assert product_version_from_tag(tag) == version
    assert product_tag(version) == tag


@pytest.mark.parametrize(
    "tag",
    [
        "phase-13-complete",
        "2.0.0a1",
        "v2.0.0-alpha.1",
        "v2.0",
        "v02.0.0",
        "v2.0.0.dev1",
        "v2.0.0+local",
        "vnext",
    ],
)
def test_non_product_tags_are_rejected(tag: str) -> None:
    assert product_version_from_tag(tag) is None


def test_product_tag_rejects_noncanonical_version() -> None:
    with pytest.raises(ValueError, match="canonical"):
        product_tag("2.0.0-alpha.1")


def test_product_tag_sort_order_matches_selected_pep440_stages() -> None:
    tags = ["v2.0.0", "v2.0.0rc2", "v2.0.0b3", "v2.0.0a9", "v1.99.0"]

    assert sorted(tags, key=lambda tag: product_tag_sort_key(tag) or ()) == [
        "v1.99.0",
        "v2.0.0a9",
        "v2.0.0b3",
        "v2.0.0rc2",
        "v2.0.0",
    ]
