"""Generate Ed25519 keypair for SAMUEL license signing.

Run this ONCE at deployment setup. Store PRIVATE_KEY_HEX offline (never commit
to git). Paste PUBLIC_KEY_HEX into samuel/core/license.py:LICENSE_PUBLIC_KEY_HEX
and commit the public key.
"""
from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main() -> None:
    private = Ed25519PrivateKey.generate()
    public = private.public_key()

    print("PRIVATE_KEY_HEX:", private.private_bytes_raw().hex())
    print("PUBLIC_KEY_HEX: ", public.public_bytes_raw().hex())
    print()
    print("Next steps:")
    print("  1. Save PRIVATE_KEY_HEX OFFLINE (e.g. ~/.samuel/license-private.key, 0600)")
    print("  2. Set PUBLIC_KEY_HEX in samuel/core/license.py:LICENSE_PUBLIC_KEY_HEX")
    print("  3. git commit + push (public key is fine to commit)")
    print("  4. Issue customer licenses with tools/generate_license.py")


if __name__ == "__main__":
    main()
