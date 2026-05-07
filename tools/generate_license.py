"""Generate a signed Ed25519 license file for a SAMUEL customer.

Usage:
    python tools/generate_license.py \\
        --email customer@example.com \\
        --features llm_routing,api_validate \\
        --private-key ~/.samuel/license-private.key \\
        --out customer_license.json

The customer places the resulting JSON file at /license.json
or sets the env var SAMUEL_LICENSE_KEY to the JSON content.
"""
from __future__ import annotations

import argparse
import base64
import json
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _load_private_key(arg: str) -> Ed25519PrivateKey:
    """Accept either a path to a key file or the raw 64-char hex string."""
    p = Path(arg)
    if p.is_file():
        hex_str = p.read_text(encoding="utf-8").strip()
    else:
        hex_str = arg.strip()
    if len(hex_str) != 64:
        raise SystemExit(
            f"Invalid private key (expected 32-byte hex = 64 chars, got {len(hex_str)})"
        )
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(hex_str))


def _canonical_payload(data: dict) -> bytes:
    payload = {k: v for k, v in data.items() if k != "signature"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="Customer email (binds the license)")
    parser.add_argument("--features", required=True, help="Comma-separated feature list")
    parser.add_argument(
        "--private-key", required=True,
        help="Path to private-key file or raw 64-char hex",
    )
    parser.add_argument("--out", default="-", help="Output path (default: stdout)")

    args = parser.parse_args()

    private = _load_private_key(args.private_key)
    features = sorted({f.strip() for f in args.features.split(",") if f.strip()})

    data = {
        "email": args.email,
        "features": features,
        "issued_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    canonical = _canonical_payload(data)
    sig = private.sign(canonical)
    data["signature"] = base64.b64encode(sig).decode("ascii")

    out_text = json.dumps(data, indent=2, sort_keys=True)

    if args.out == "-":
        print(out_text)
    else:
        Path(args.out).write_text(out_text + "\n", encoding="utf-8")
        print(f"License written to {args.out}", flush=True)


if __name__ == "__main__":
    main()
