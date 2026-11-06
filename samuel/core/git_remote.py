"""Shared, credential-free HTTP Git repository identity boundary."""

from __future__ import annotations

from urllib.parse import SplitResult, urlsplit

from samuel.core.errors import GitTransportAuthError


def parse_http_url(value: str, *, code: str) -> SplitResult:
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise GitTransportAuthError(code, "Git remote contains invalid characters")
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise GitTransportAuthError(code, "Git remote has an invalid network endpoint") from exc
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path
        or port is not None
        and not 1 <= port <= 65535
    ):
        raise GitTransportAuthError(code, "Git remote is outside the supported HTTP boundary")
    return parsed


def endpoint(parsed: SplitResult) -> tuple[str, str, int]:
    scheme = parsed.scheme.lower()
    default_port = 443 if scheme == "https" else 80
    return scheme, str(parsed.hostname).lower(), parsed.port or default_port


def canonical_repository_url(value: str) -> str:
    try:
        parsed = parse_http_url(value.rstrip("/"), code="project_origin_invalid")
    except GitTransportAuthError as exc:
        raise ValueError("Repository origin is outside the supported HTTP boundary") from exc
    scheme, host, port = endpoint(parsed)
    path = parsed.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    if not path or any(part in {".", "..", ""} for part in path[1:].split("/")):
        raise ValueError("Repository path is invalid")
    host = f"[{host}]" if ":" in host else host
    default_port = 443 if scheme == "https" else 80
    authority = host if port == default_port else f"{host}:{port}"
    return f"{scheme}://{authority}{path}"
