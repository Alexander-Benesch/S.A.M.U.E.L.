"""Read-only validator for the public external data contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from samuel.extensions.contract import (
    ContractError,
    contract_digest,
    load_capability_manifest,
    load_extension_policy,
    load_extension_request,
    load_extension_result,
    resolve_capability,
    validate_result_binding,
)


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    status = commands.add_parser("status", help="resolve operator policy and compatibility")
    status.add_argument("--config", type=Path, required=True)
    status.add_argument("--manifest", type=Path)

    manifest = commands.add_parser("validate-manifest", help="validate a capability manifest")
    manifest.add_argument("path", type=Path)

    result = commands.add_parser("validate-result", help="validate an exact request/result pair")
    result.add_argument("--request", type=Path, required=True)
    result.add_argument("--result", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            policy = load_extension_policy(args.config)
            resolution = resolve_capability(policy, manifest_path=args.manifest)
            _print(resolution.model_dump(exclude_none=True))
            return 1 if resolution.blocked else 0
        if args.command == "validate-manifest":
            value = load_capability_manifest(args.path)
            _print(
                {
                    "valid": True,
                    "capability_id": value.capability_id,
                    "contract_version": value.contract_version,
                    "effect": value.effect,
                    "contract_digest": contract_digest(value),
                }
            )
            return 0
        request = load_extension_request(args.request)
        result_value = load_extension_result(args.result)
        validate_result_binding(request, result_value)
        _print(
            {
                "valid": True,
                "request_id": request.request_id,
                "effect": result_value.effect,
                "status": result_value.status,
                "result_digest": contract_digest(result_value),
            }
        )
        return 0
    except ContractError as exc:
        _print({"valid": False, "error": str(exc)})
        return 1
    except OSError as exc:
        _print({"valid": False, "error": f"contract I/O failed: {type(exc).__name__}"})
        return 1


if __name__ == "__main__":
    sys.exit(main())
