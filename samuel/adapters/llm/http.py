from __future__ import annotations

import json
import urllib.error
import urllib.request

_MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MB


def http_post(url: str, payload: dict, headers: dict, timeout: int = 60) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read(_MAX_RESPONSE_BYTES)
        return json.loads(body)



def http_get(
    url: str, headers: dict | None = None, timeout: int = 10,
) -> tuple[int, dict | None]:
    """GET request — returns (status_code, json_body or None on parse-fail)."""
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(_MAX_RESPONSE_BYTES)
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, None
    except urllib.error.HTTPError as e:
        return e.code, None


def http_head(
    url: str, headers: dict | None = None, timeout: int = 10,
) -> int:
    """HEAD request — returns status code (raises on non-HTTP errors like timeout)."""
    req = urllib.request.Request(url, headers=headers or {}, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code