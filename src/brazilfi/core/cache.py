"""Download com cache em disco para fontes que servem arquivos inteiros (CSV/ZIP)."""
from __future__ import annotations

import time
from pathlib import Path

import httpx

from brazilfi.core.exceptions import DataNotFoundError, ProviderError
from brazilfi.core.http_client import USER_AGENT

CACHE_ROOT = Path.home() / ".cache" / "brazilfi"


def cached_download(
    url: str,
    dest: Path,
    *,
    max_age_days: float | None = 1,
    headers: dict[str, str] | None = None,
    timeout: float = 120.0,
) -> Path:
    """
    Baixa `url` para `dest` se o cache não existir ou estiver velho; devolve `dest`.

    `max_age_days=None` marca o arquivo como imutável (ex.: pregão passado) —
    uma vez baixado, nunca é rebaixado. A escrita é atômica (`.part` + rename):
    um Ctrl+C no meio não deixa um cache truncado válido.

    404 vira `DataNotFoundError` (a fonte ainda não publicou aquele arquivo);
    qualquer outro 4xx/5xx vira `ProviderError`.
    """
    if dest.exists() and (
        max_age_days is None or time.time() - dest.stat().st_mtime < max_age_days * 86400
    ):
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    with httpx.stream(
        "GET",
        url,
        timeout=timeout,
        headers=headers or {"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as resp:
        if resp.status_code == 404:
            raise DataNotFoundError(f"Arquivo não publicado na fonte: {url}")
        if resp.status_code >= 400:
            raise ProviderError(f"HTTP {resp.status_code} ao baixar {url}")
        with tmp.open("wb") as f:
            for chunk in resp.iter_bytes():
                f.write(chunk)
    tmp.replace(dest)
    return dest
