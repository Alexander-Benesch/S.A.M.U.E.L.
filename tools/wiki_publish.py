#!/usr/bin/env python3
"""Publish the bound local wiki to a provider-neutral Git wiki remote."""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from samuel.adapters import git_publication  # noqa: E402
from tools import wiki  # noqa: E402

MARKER = git_publication.MARKER
LINK_RE = re.compile(r"(\[[^]]+\]\()([^)]+)(\))")

PublishError = git_publication.PublishError


def _digest(files: dict[str, bytes]) -> str:
    return git_publication.publication_digest(files)


def _safe_remote(value: str) -> str:
    return git_publication.safe_remote(value)


def project_pages(
    pages: dict[str, bytes],
    manifest: dict[str, Any],
    receipt: dict[str, Any],
    source_url_template: str,
) -> dict[str, bytes]:
    if "{head_sha}" not in source_url_template or "{path}" not in source_url_template:
        raise PublishError("source URL template requires {head_sha} and {path}")
    by_local = {str(item["path"]): str(item["publication_path"]) for item in manifest["pages"]}
    projected: dict[str, bytes] = {}
    output_dir = str(manifest["output_dir"])

    for item in manifest["pages"]:
        local_path = str(item["path"])
        content = pages[local_path].decode()

        def replace(match: re.Match[str], local_page: str = local_path) -> str:
            target = match.group(2)
            if target.startswith(("#", "http://", "https://", "mailto:")):
                return match.group(0)
            path_part, separator, anchor = target.partition("#")
            decoded = unquote(path_part)
            resolved = posixpath.normpath(
                posixpath.join(output_dir, posixpath.dirname(local_page), decoded)
            )
            local_prefix = output_dir + "/"
            if resolved.startswith(local_prefix) and resolved[len(local_prefix) :] in by_local:
                publication = by_local[resolved[len(local_prefix) :]]
                rewritten = publication.removesuffix(".md")
            else:
                repository_path = resolved
                if repository_path.startswith("../") or repository_path == "..":
                    raise PublishError(f"source link escapes repository: {target}")
                rewritten = source_url_template.format(
                    head_sha=receipt["head_sha"], path=quote(repository_path, safe="/")
                )
            if separator:
                rewritten += "#" + anchor
            return match.group(1) + rewritten + match.group(3)

        projected[str(item["publication_path"])] = LINK_RE.sub(replace, content).encode()

    sidebar = ["# S.A.M.U.E.L.", ""]
    for item in manifest["pages"]:
        sidebar.append(f"- [{item['title']}]({str(item['publication_path']).removesuffix('.md')})")
    projected["_Sidebar.md"] = ("\n".join(sidebar) + "\n").encode()
    projected["_Footer.md"] = (
        "Nicht autoritative Projektion · "
        f"Subject `{manifest['repository']}@{receipt['head_sha']}` · "
        f"Artifact `{receipt['artifact_digest']}`\n"
    ).encode()
    return projected


def _git(cwd: Path, *args: str, check: bool = True) -> str:
    return git_publication.run_git(cwd, *args, check=check)


def publish(
    *,
    remote: str,
    source_url_template: str,
    branch: str,
    receipt_path: Path,
    adopt_existing_head: str | None = None,
    author_name: str = "S.A.M.U.E.L. Wiki Publisher",
    author_email: str = "samuel-wiki@localhost",
) -> dict[str, Any]:
    remote = _safe_remote(remote)
    local_receipt = wiki.check_materialized()
    manifest = wiki._read_json(wiki.MANIFEST_PATH)
    pages = {
        str(item["path"]): (wiki.ROOT / "wiki" / str(item["path"])).read_bytes()
        for item in manifest["pages"]
    }
    projected = project_pages(pages, manifest, local_receipt, source_url_template)
    return git_publication.publish_projection(
        projected=projected,
        source_head_sha=str(local_receipt["head_sha"]),
        input_artifact_digest=str(local_receipt["artifact_digest"]),
        remote=remote,
        branch=branch,
        receipt_path=receipt_path,
        commit_subject="S.A.M.U.E.L. wiki",
        adopt_existing_head=adopt_existing_head,
        author_name=author_name,
        author_email=author_email,
        git_runner=_git,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", required=True)
    parser.add_argument("--source-url-template", required=True)
    parser.add_argument("--branch", default="main")
    parser.add_argument(
        "--receipt", type=Path, default=wiki.ROOT / "build/wiki-publication-receipt.json"
    )
    parser.add_argument("--adopt-existing-head")
    args = parser.parse_args()
    try:
        result = publish(
            remote=args.remote,
            source_url_template=args.source_url_template,
            branch=args.branch,
            receipt_path=args.receipt,
            adopt_existing_head=args.adopt_existing_head,
        )
    except (PublishError, wiki.WikiError, json.JSONDecodeError) as exc:
        print(f"wiki publication failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
