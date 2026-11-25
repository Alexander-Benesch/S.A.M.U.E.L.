#!/usr/bin/env python3
"""Build the GitHub first-install entry from an approved release and its public TUF root."""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import io
import json
import re
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.container_init import read_manifest  # noqa: E402

RELEASES = "https://github.com/Alexander-Benesch/S.A.M.U.E.L./releases/download"
IMAGE = "ghcr.io/alexander-benesch/samuel"
HELPERS = ("tools/samuel-container", "tools/container_init.py")


def build_entry(manifest_path: Path, root_path: Path) -> bytes:
    # Only the publisher provides these inputs. The user gets one versioned HTTPS asset.
    manifest_data = manifest_path.read_bytes()
    document = json.loads(manifest_data)
    image = document["container"]["reference"]
    if not re.fullmatch(re.escape(IMAGE) + r"@sha256:[0-9a-f]{64}", image):
        raise ValueError("expected the official digest-bound public container image")
    manifest = read_manifest(manifest_path, hashlib.sha256(manifest_data).hexdigest(), image)
    version = manifest["version"]
    base_url = f"{RELEASES}/v{version}/"
    root = root_path.read_bytes()
    from tuf.api.metadata import Metadata, Root

    metadata = Metadata.from_bytes(root)
    if not isinstance(metadata.signed, Root) or metadata.signed.is_expired():
        raise ValueError("expected current public TUF root metadata")
    metadata.verify_delegate("root", metadata)
    profile = {
        "schema_version": 1,
        "bootstrap_image": image,
        "trust_root_sha256": hashlib.sha256(root).hexdigest(),
        "metadata_url": base_url,
        "targets_url": base_url,
        "manifest_target": "release-manifest.json",
    }
    members = {"trusted-root.json": root, "bootstrap-profile.json": json.dumps(profile).encode()}
    archive_name = f"samuel-oci-{version}.tar.gz"
    matches = [item for item in manifest["artifacts"] if item["name"] == archive_name]
    archive = (manifest_path.parent / archive_name).read_bytes()
    if len(matches) != 1 or matches[0] != {
        "name": archive_name,
        "size": len(archive),
        "sha256": hashlib.sha256(archive).hexdigest(),
    }:
        raise ValueError("installer archive differs from the release manifest")
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as kit:
        for name in HELPERS:
            selected = [item for item in kit if item.name == f"samuel-oci/{name}"]
            if len(selected) != 1 or not selected[0].isreg():
                raise ValueError(f"invalid installer archive member: {name}")
            source = kit.extractfile(selected[0])
            assert source is not None
            members[name] = source.read()

    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w") as bundle:
        for name, value in members.items():
            member = tarfile.TarInfo(name)
            member.size = len(value)
            member.mode = 0o644
            bundle.addfile(member, io.BytesIO(value))
    compressed = gzip.compress(payload.getvalue(), mtime=0)
    digest = hashlib.sha256(compressed).hexdigest()
    encoded = base64.encodebytes(compressed).decode("ascii")
    # The permanent, root-owned directory is also used by the printed production-start command.
    # Reserve it only after the complete embedded payload has been verified.
    return f"""#!/usr/bin/env bash
set -euo pipefail
umask 077
[[ $EUID == 0 && -t 0 && -t 2 ]] || {{ echo 'Use sudo bash in an interactive terminal.' >&2; exit 1; }}
stage=$(mktemp -d /opt/.samuel-bootstrap.XXXXXXXX)
trap 'rm -rf -- "$stage"' EXIT
base64 --decode >"$stage/payload" <<'SAMUEL_PAYLOAD'
{encoded}SAMUEL_PAYLOAD
printf '%s  %s\\n' '{digest}' "$stage/payload" | sha256sum --check --status || {{ echo 'Bootstrap verification failed.' >&2; exit 1; }}
mkdir "$stage/kit"
tar -xzf "$stage/payload" -C "$stage/kit" --no-same-owner
kit=/opt/samuel-bootstrap-v{version}-{digest[:16]}
if ! mv -T -- "$stage/kit" "$kit" 2>/dev/null; then
    [[ -d "$kit" && ! -L "$kit" && $(stat -c '%u:%a' "$kit") == 0:700 ]]
    diff --no-dereference -qr -- "$stage/kit" "$kit" || {{ echo 'Existing bootstrap differs.' >&2; exit 1; }}
fi
bash "$kit/tools/samuel-container" install
""".encode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("public_root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    entry = build_entry(args.manifest, args.public_root)
    with args.output.open("xb") as dest:
        dest.write(entry)


if __name__ == "__main__":
    main()
