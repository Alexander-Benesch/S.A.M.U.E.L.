"""Operate the bounded documentation inventory capability."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from samuel.adapters.git_publication import PublishError, publish_projection
from samuel.documentation_capability import (
    DocumentationVerification,
    build_documentation_projection,
    prepare_documentation_exchange,
    verify_documentation_exchange,
)
from samuel.extensions import ContractError, contract_digest


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _verification(args: argparse.Namespace) -> DocumentationVerification:
    return verify_documentation_exchange(
        repository_root=args.repository_root,
        exchange_root=args.exchange_root,
        request_path=args.request,
        result_path=args.result,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare", help="bind a tracked policy to the exact Git HEAD")
    prepare.add_argument("--repository-root", type=Path, required=True)
    prepare.add_argument("--repository", required=True)
    prepare.add_argument("--policy", required=True)
    prepare.add_argument("--exchange-root", type=Path, required=True)
    prepare.add_argument("--request-id", required=True)

    for name, help_text in (
        ("validate", "verify consumer claims without publishing"),
        ("publish", "verify and publish the advisory inventory projection"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--repository-root", type=Path, required=True)
        command.add_argument("--exchange-root", type=Path, required=True)
        command.add_argument("--request", type=Path, required=True)
        command.add_argument("--result", type=Path, required=True)
        if name == "publish":
            command.add_argument("--remote", required=True)
            command.add_argument("--branch", default="main")
            command.add_argument("--source-url-template", required=True)
            command.add_argument("--receipt", type=Path, required=True)
            command.add_argument("--adopt-existing-head")

    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            request, policy_path = prepare_documentation_exchange(
                repository_root=args.repository_root,
                repository=args.repository,
                policy_path=args.policy,
                exchange_root=args.exchange_root,
                request_id=args.request_id,
            )
            _print(
                {
                    "prepared": True,
                    "request_id": request.request_id,
                    "request_digest": contract_digest(request),
                    "head_sha": request.subject.head_sha,
                    "policy_path": str(policy_path),
                }
            )
            return 0

        verification = _verification(args)
        if args.command == "validate":
            _print(
                {
                    "valid": True,
                    "request_id": verification.request.request_id,
                    "repository": verification.request.subject.repository,
                    "head_sha": verification.request.subject.head_sha,
                    "document_count": len(verification.claims.documents),
                    "claims_digest": verification.result.output_artifact.digest,
                    "effect": "advisory",
                }
            )
            return 0

        projection = build_documentation_projection(
            verification,
            source_url_template=args.source_url_template,
        )
        receipt = publish_projection(
            projected=projection,
            source_head_sha=verification.request.subject.head_sha,
            input_artifact_digest=verification.result.output_artifact.digest,
            remote=args.remote,
            branch=args.branch,
            receipt_path=args.receipt,
            commit_subject=(
                f"documentation inventory for {verification.request.subject.repository}"
            ),
            adopt_existing_head=args.adopt_existing_head,
        )
        _print(receipt)
        return 0
    except (ContractError, PublishError, OSError) as exc:
        _print({"valid": False, "error": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
