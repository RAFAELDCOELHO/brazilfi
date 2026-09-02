"""Testes do HttpClient (retry, redirects, status)."""
from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
import respx

from brazilfi.core.exceptions import ProviderError, RateLimitError
from brazilfi.core.http_client import HttpClient


@respx.mock
def test_retries_on_5xx_then_succeeds() -> None:
    route = respx.get("https://x.test/a").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json={"ok": 1})]
    )
    with patch("brazilfi.core.http_client.time.sleep"):
        assert HttpClient(base_url="https://x.test").get("a") == {"ok": 1}
    assert route.call_count == 2


@respx.mock
def test_gives_up_after_retries() -> None:
    route = respx.get("https://x.test/a").mock(return_value=httpx.Response(500))
    with patch("brazilfi.core.http_client.time.sleep"), pytest.raises(ProviderError):
        HttpClient(base_url="https://x.test", retries=2).get("a")
    assert route.call_count == 2


@respx.mock
def test_4xx_is_not_retried() -> None:
    route = respx.get("https://x.test/a").mock(return_value=httpx.Response(404))
    with pytest.raises(ProviderError):
        HttpClient(base_url="https://x.test").get("a")
    assert route.call_count == 1


@respx.mock
def test_429_raises_rate_limit() -> None:
    respx.get("https://x.test/a").mock(return_value=httpx.Response(429))
    with pytest.raises(RateLimitError):
        HttpClient(base_url="https://x.test").get("a")


@respx.mock
def test_follows_redirect() -> None:
    respx.get("https://x.test/old").mock(
        return_value=httpx.Response(302, headers={"location": "https://x.test/new"})
    )
    respx.get("https://x.test/new").mock(return_value=httpx.Response(200, text="csv"))
    assert HttpClient().get_text("https://x.test/old") == "csv"


@respx.mock
async def test_aget_retries_on_5xx() -> None:
    route = respx.get("https://x.test/a").mock(
        side_effect=[httpx.Response(502), httpx.Response(200, json=[1])]
    )
    assert await HttpClient(base_url="https://x.test").aget("a") == [1]
    assert route.call_count == 2
