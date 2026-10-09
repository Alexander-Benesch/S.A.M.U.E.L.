"""External conformance fixture: public contract plus standard library only."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from samuel.extensions import (
    ArtifactReference,
    ExtensionResult,
    contract_digest,
    load_extension_request,
    verify_artifact_reference,
)


def main() -> int:
    request = load_extension_request(Path(sys.argv[1]))
    output_path = Path(sys.argv[2])
    verify_artifact_reference(Path(sys.argv[1]).parent, request.input_artifact)
    claims_path = output_path.with_name("claims.json")
    claims = json.dumps(
        {
            "schema": "documentation-inventory.v1",
            "claims": [],
            "effect": "advisory",
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    claims_path.write_bytes(claims)
    result = ExtensionResult(
        schema="samuel-extension-result.v1",
        capability_id=request.capability_id,
        contract_version=request.contract_version,
        request_id=request.request_id,
        request_digest=contract_digest(request),
        subject=request.subject,
        claim_family=request.claim_family,
        effect="advisory",
        status="passed",
        output_artifact=ArtifactReference(
            path="claims.json",
            digest=f"sha256:{hashlib.sha256(claims).hexdigest()}",
            size_bytes=len(claims),
            media_type="application/json",
        ),
    )
    verify_artifact_reference(claims_path.parent, result.output_artifact)
    output_path.write_text(
        result.model_dump_json(exclude_none=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
