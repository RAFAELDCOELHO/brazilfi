"""Cliente HTTP com retry, timeout e rate limiting básico."""
from __future__ import annotations

import asyncio
import time
from importlib.metadata import version
from typing import Any

import httpx

from brazilfi.core.exceptions import ProviderError, RateLimitError

DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 0.5
USER_AGENT = f"brazilfi/{version('brazilfi')}"

# Erros transitórios que valem nova tentativa (rede, timeout, 5xx do servidor).
_RETRYABLE = (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)


class _ServerError(ProviderError):
    """HTTP 5xx — transitório, o loop de retry tenta de novo."""


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
        self.headers = headers or {"User-Agent": USER_AGENT}

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET síncrono com retry."""
        return self._get(path, params).json()

    def get_text(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        encoding: str | None = None,
    ) -> str:
        """
        GET síncrono com retry retornando texto puro.

        Para fontes que servem CSV/TXT em vez de JSON. Use `encoding` quando o
        servidor não declara charset (muitos endpoints brasileiros são latin-1).
        """
        resp = self._get(path, params)
        if encoding:
            return resp.content.decode(encoding, errors="replace")
        return resp.text

    async def aget(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET assíncrono com retry."""
        url = self._build_url(path)
        last_exc: Exception | None = None

        async with httpx.AsyncClient(
            timeout=self.timeout, headers=self.headers, follow_redirects=True
        ) as client:
            for attempt in range(self.retries):
                try:
                    resp = await client.get(url, params=params)
                    self._check_status(resp)
                    return resp.json()
                except (*_RETRYABLE, _ServerError) as e:
                    last_exc = e
                    if attempt < self.retries - 1:
                        await asyncio.sleep(DEFAULT_BACKOFF * (2**attempt))

        raise ProviderError(f"Falha após {self.retries} tentativas: {last_exc}")

    # ---------- Internals ----------

    def _get(self, path: str, params: dict[str, Any] | None) -> httpx.Response:
        url = self._build_url(path)
        last_exc: Exception | None = None

        with httpx.Client(
            timeout=self.timeout, headers=self.headers, follow_redirects=True
        ) as client:
            for attempt in range(self.retries):
                try:
                    resp = client.get(url, params=params)
                    self._check_status(resp)
                    return resp
                except (*_RETRYABLE, _ServerError) as e:
                    last_exc = e
                    if attempt < self.retries - 1:
                        time.sleep(DEFAULT_BACKOFF * (2**attempt))

        raise ProviderError(f"Falha após {self.retries} tentativas: {last_exc}")

    def _build_url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

    @staticmethod
    def _check_status(resp: httpx.Response) -> None:
        if resp.status_code == 429:
            raise RateLimitError(f"Rate limit: {resp.text[:200]}")
        if resp.status_code >= 500:
            raise _ServerError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        if resp.status_code >= 400:
            raise ProviderError(f"HTTP {resp.status_code}: {resp.text[:200]}")
