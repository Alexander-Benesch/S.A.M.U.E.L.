from __future__ import annotations

import io
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from samuel.adapters.auth.static_token import StaticTokenAuth
from samuel.adapters.gitea.api import GiteaAPI


def test_response_size_limit_blocks_before_json_parsing() -> None:
    response = MagicMock()
    response.__enter__.return_value = response
    response.read.return_value = b"{" + b"x" * 32
    api = GiteaAPI("https://gitea.example", StaticTokenAuth("secret"))

    with (
        patch("urllib.request.urlopen", return_value=response),
        pytest.raises(ValueError, match="size limit"),
    ):
        api.request("GET", "/repos/o/r/actions/runs/1", max_response_bytes=8)

    response.read.assert_called_once_with(9)


def test_request_once_does_not_retry_ambiguous_post() -> None:
    error = urllib.error.HTTPError(
        "https://gitea.example/api/v1/dispatch",
        503,
        "unavailable",
        {},
        io.BytesIO(b"temporarily unavailable"),
    )
    api = GiteaAPI("https://gitea.example", StaticTokenAuth("secret"))

    with (
        patch("urllib.request.urlopen", side_effect=error) as urlopen,
        pytest.raises(Exception, match="503"),
    ):
        api.request_once("POST", "/dispatch", {"ref": "main"})

    urlopen.assert_called_once()
