"""Fail closed unless fresh wheel and sdist carry the repository license."""

from __future__ import annotations

import argparse
import tarfile
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import TypeVar

EXPECTED_EXPRESSION = "Apache-2.0"
EXPECTED_LICENSE_FILE = "LICENSE"
ROOT = Path(__file__).parents[1]
T = TypeVar("T")


def _single(paths: list[T], description: str) -> T:
    if len(paths) != 1:
        raise ValueError(f"expected exactly one {description}, found {len(paths)}")
    return paths[0]


def _verify_metadata(raw: bytes, archive_name: str) -> None:
    metadata = BytesParser().parsebytes(raw)
    if metadata["License-Expression"] != EXPECTED_EXPRESSION:
        raise ValueError(
            f"{archive_name}: License-Expression is "
            f"{metadata['License-Expression']!r}, expected {EXPECTED_EXPRESSION!r}"
        )
    license_files = metadata.get_all("License-File", [])
    if license_files != [EXPECTED_LICENSE_FILE]:
        raise ValueError(
            f"{archive_name}: License-File is {license_files!r}, "
            f"expected {[EXPECTED_LICENSE_FILE]!r}"
        )


def verify_wheel(path: Path, expected_license: bytes) -> None:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        metadata_name = _single(
            [name for name in names if name.endswith(".dist-info/METADATA")],
            "wheel METADATA entry",
        )
        license_name = _single(
            [name for name in names if name.endswith(".dist-info/licenses/LICENSE")],
            "wheel LICENSE entry",
        )
        _verify_metadata(archive.read(metadata_name), path.name)
        if archive.read(license_name) != expected_license:
            raise ValueError(f"{path.name}: packaged LICENSE differs from repository LICENSE")


def verify_sdist(path: Path, expected_license: bytes) -> None:
    with tarfile.open(path, mode="r:gz") as archive:
        members = [member for member in archive.getmembers() if member.isfile()]
        metadata_member = _single(
            [
                member
                for member in members
                if PurePosixPath(member.name).name == "PKG-INFO"
                and len(PurePosixPath(member.name).parts) == 2
            ],
            "sdist root PKG-INFO entry",
        )
        license_member = _single(
            [
                member
                for member in members
                if PurePosixPath(member.name).name == EXPECTED_LICENSE_FILE
                and len(PurePosixPath(member.name).parts) == 2
            ],
            "sdist root LICENSE entry",
        )
        metadata_file = archive.extractfile(metadata_member)
        license_file = archive.extractfile(license_member)
        if metadata_file is None or license_file is None:
            raise ValueError(f"{path.name}: required metadata could not be read")
        _verify_metadata(metadata_file.read(), path.name)
        if license_file.read() != expected_license:
            raise ValueError(f"{path.name}: packaged LICENSE differs from repository LICENSE")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist_dir", type=Path)
    args = parser.parse_args()

    expected_license = (ROOT / EXPECTED_LICENSE_FILE).read_bytes()
    wheel = _single(sorted(args.dist_dir.glob("*.whl")), "wheel")
    sdist = _single(sorted(args.dist_dir.glob("*.tar.gz")), "sdist")
    verify_wheel(wheel, expected_license)
    verify_sdist(sdist, expected_license)
    print(f"distribution licenses valid: {wheel.name}, {sdist.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
