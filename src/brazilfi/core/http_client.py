"""Cliente HTTP com retry, timeout e rate limiting básico."""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from brazilfi.core.exceptions import ProviderError, RateLimitError

DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 0.5


class HttpClient:
    """Wrapper em cima de httpx com retry exponencial."""

    def __init__(
        self,
        base_url: str = "",
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.retries = retries
        self.headers = headers or {"User-Agent": "brazilfi/0.1.0"}

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET síncrono com retry."""
        url = self._build_url(path)
        last_exc: Exception | None = None

        with httpx.Client(timeout=self.timeout, headers=self.headers) as client:
            for attempt in range(self.retries):
                try:
                    resp = client.get(url, params=params)
                    self._check_status(resp)
                    return resp.json()
                except (httpx.TimeoutException, httpx.NetworkError) as e:
                    last_exc = e
                    if attempt < self.retries - 1:
                        import time

                        time.sleep(DEFAULT_BACKOFF * (2**attempt))

        raise ProviderError(f"Falha após {self.retries} tentativas: {last_exc}")

    async def aget(
        self, path: str, params: dict[str, Any] | None = None
    ) -> Any:
        """GET assíncrono com retry."""
        url = self._build_url(path)
        last_exc: Exception | None = None

        async with httpx.AsyncClient(
            timeout=self.timeout, headers=self.headers
        ) as client:
            for attempt in range(self.retries):
                try:
                    resp = await client.get(url, params=params)
                    self._check_status(resp)
                    return resp.json()
                except (httpx.TimeoutException, httpx.NetworkError) as e:
                    last_exc = e
                    if attempt < self.retries - 1:
                        await asyncio.sleep(DEFAULT_BACKOFF * (2**attempt))

        raise ProviderError(f"Falha após {self.retries} tentativas: {last_exc}")

    def _build_url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

    @staticmethod
    def _check_status(resp: httpx.Response) -> None:
        if resp.status_code == 429:
            raise RateLimitError(f"Rate limit: {resp.text[:200]}")
        if resp.status_code >= 400:
            raise ProviderError(
                f"HTTP {resp.status_code}: {resp.text[:200]}"
            )
