"""Testes de core.cache.cached_download (download atômico com cache em disco)."""
from __future__ import annotations

import os
import time
from pathlib import Path

import httpx
import pytest
import respx

from brazilfi.core.cache import cached_download
from brazilfi.core.exceptions import DataNotFoundError, ProviderError

URL = "https://dados.exemplo.gov.br/arquivo.csv"


@respx.mock
def test_downloads_once_and_reuses_fresh_cache(tmp_path: Path) -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, content=b"a;b\n1;2\n"))
    dest = tmp_path / "sub" / "arquivo.csv"

    assert cached_download(URL, dest).read_bytes() == b"a;b\n1;2\n"
    cached_download(URL, dest)

    assert route.call_count == 1
    assert not dest.with_name("arquivo.csv.part").exists()


@respx.mock
def test_stale_cache_is_refreshed_unless_immutable(tmp_path: Path) -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, content=b"novo"))
    dest = tmp_path / "f.csv"
    dest.write_bytes(b"velho")
    two_days_ago = time.time() - 2 * 86400
    os.utime(dest, (two_days_ago, two_days_ago))

    cached_download(URL, dest, max_age_days=1)
    assert dest.read_bytes() == b"novo"
    assert route.call_count == 1

    os.utime(dest, (two_days_ago, two_days_ago))
    cached_download(URL, dest, max_age_days=None)  # imutável: nunca rebaixa
    assert route.call_count == 1


@respx.mock
def test_404_is_data_not_found_and_leaves_no_file(tmp_path: Path) -> None:
    respx.get(URL).mock(return_value=httpx.Response(404))
    dest = tmp_path / "f.csv"
    with pytest.raises(DataNotFoundError):
        cached_download(URL, dest)
    assert not dest.exists()


@respx.mock
def test_other_http_errors_are_provider_errors(tmp_path: Path) -> None:
    respx.get(URL).mock(return_value=httpx.Response(503))
    with pytest.raises(ProviderError, match="503"):
        cached_download(URL, tmp_path / "f.csv")
