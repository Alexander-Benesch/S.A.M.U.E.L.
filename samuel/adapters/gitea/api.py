from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

from samuel.core.ports import IAuthProvider

log = logging.getLogger(__name__)

_TRANSIENT_HTTP_CODES = (502, 503, 504)
_MAX_RETRIES = 2
_MAX_RESPONSE_BYTES = 2_000_000

_BLOCKED_PATH_PATTERNS = (
    "/branch_protections",
    "/git/refs",
    "/hooks",
)


class GiteaAPIError(Exception):
    def __init__(self, status: int, method: str, path: str, body: str = ""):
        self.status = status
        self.method = method
        self.path = path
        self.body = body
        super().__init__(f"Gitea API {method} {path} → {status}: {body[:200]}")


class GiteaAPI:
    def __init__(self, base_url: str, auth: IAuthProvider, *, timeout: float = 60.0):
        self._base_url = base_url.rstrip("/")
        self._auth = auth
        self._timeout = max(0.1, float(timeout))

    def request(
        self,
        method: str,
        path: str,
        data: dict | None = None,
        *,
        max_response_bytes: int = _MAX_RESPONSE_BYTES,
    ) -> dict | list | None:
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")
        if method != "GET":
            for pattern in _BLOCKED_PATH_PATTERNS:
                if pattern in path:
                    log.critical("API-Guard: %s %s BLOCKED", method, path)
                    raise PermissionError(f"API-Guard: {method} {path} is blocked.")

        url = f"{self._base_url}/api/v1{path}"
        payload = json.dumps(data).encode() if data else None
        headers = {
            "Authorization": f"token {self._auth.get_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        log.debug("%s %s", method, path)
        for attempt in range(_MAX_RETRIES + 1):
            req = urllib.request.Request(url, data=payload, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    body = resp.read(max_response_bytes + 1)
                    if len(body) > max_response_bytes:
                        raise ValueError("Gitea API response exceeds configured size limit")
                    return json.loads(body) if body else None
            except urllib.error.HTTPError as e:
                if e.code in _TRANSIENT_HTTP_CODES and attempt < _MAX_RETRIES:
                    time.sleep(2**attempt)
                    continue
                err_body = (
                    e.read(min(max_response_bytes, 200) + 1).decode(errors="replace")[:200]
                    if hasattr(e, "read")
                    else ""
                )
                raise GiteaAPIError(e.code, method, path, err_body) from e
            except (urllib.error.URLError, TimeoutError):
                if attempt < _MAX_RETRIES:
                    time.sleep(2**attempt)
                    continue
                raise
        raise RuntimeError("Gitea retry loop exhausted")

    def request_once(
        self,
        method: str,
        path: str,
        data: dict | None = None,
        *,
        max_response_bytes: int = _MAX_RESPONSE_BYTES,
    ) -> dict | list | None:
        """Send exactly one request.

        Active provider dispatch uses this entrypoint because a timeout after
        the server accepted a POST must be reconciled, never blindly retried.
        """

        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")
        if method != "GET":
            for pattern in _BLOCKED_PATH_PATTERNS:
                if pattern in path:
                    log.critical("API-Guard: %s %s BLOCKED", method, path)
                    raise PermissionError(f"API-Guard: {method} {path} is blocked.")
        body = self.request_bytes_once(
            method,
            path,
            data=data,
            max_response_bytes=max_response_bytes,
            accept="application/json",
        )
        return json.loads(body) if body else None

    def request_bytes_once(
        self,
        method: str,
        path: str,
        data: dict | None = None,
        *,
        max_response_bytes: int = _MAX_RESPONSE_BYTES,
        accept: str = "application/octet-stream",
    ) -> bytes:
        """Read one bounded response without retrying the operation."""

        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")
        if method != "GET":
            for pattern in _BLOCKED_PATH_PATTERNS:
                if pattern in path:
                    log.critical("API-Guard: %s %s BLOCKED", method, path)
                    raise PermissionError(f"API-Guard: {method} {path} is blocked.")
        url = f"{self._base_url}/api/v1{path}"
        payload = json.dumps(data).encode() if data else None
        headers = {
            "Authorization": f"token {self._auth.get_token()}",
            "Content-Type": "application/json",
            "Accept": accept,
        }
        log.debug("%s %s", method, path)
        req = urllib.request.Request(url, data=payload, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body: bytes = resp.read(max_response_bytes + 1)
                if len(body) > max_response_bytes:
                    raise ValueError("Gitea API response exceeds configured size limit")
                return body
        except urllib.error.HTTPError as exc:
            err_body = (
                exc.read(min(max_response_bytes, 200) + 1).decode(errors="replace")[:200]
                if hasattr(exc, "read")
                else ""
            )
            raise GiteaAPIError(exc.code, method, path, err_body) from exc
