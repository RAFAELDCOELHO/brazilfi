"""Testes do provider Bacen com respx (mock HTTP)."""
from __future__ import annotations

import httpx
import pytest
import respx

from brazilfi.core.exceptions import DataNotFoundError
from brazilfi.providers.bacen import Bacen

SGS_BASE = "https://api.bcb.gov.br/dados/serie"

FAKE_SELIC = [
    {"data": "01/04/2026", "valor": "0.04268"},
    {"data": "02/04/2026", "valor": "0.04268"},
    {"data": "03/04/2026", "valor": "0.04268"},
]


@respx.mock
def test_selic_last_n() -> None:
    route = respx.get(f"{SGS_BASE}/bcdata.sgs.11/dados/ultimos/3").mock(
        return_value=httpx.Response(200, json=FAKE_SELIC)
    )
    ts = Bacen().selic(last=3)
    assert route.called
    assert len(ts) == 3
    assert ts.source == "bacen"
    assert ts.code == "11"
    df = ts.to_dataframe()
    assert len(df) == 3
    assert "value" in df.columns


@respx.mock
def test_selic_meta() -> None:
    route = respx.get(f"{SGS_BASE}/bcdata.sgs.432/dados/ultimos/1").mock(
        return_value=httpx.Response(200, json=[{"data": "01/04/2026", "valor": "11.25"}])
    )
    ts = Bacen().selic(last=1, meta=True)
    assert route.called
    assert ts.code == "432"


@respx.mock
def test_ipca_acumulado_12m() -> None:
    route = respx.get(f"{SGS_BASE}/bcdata.sgs.13522/dados/ultimos/6").mock(
        return_value=httpx.Response(200, json=[{"data": "01/03/2026", "valor": "4.23"}] * 6)
    )
    ts = Bacen().ipca(last=6, acum_12m=True)
    assert route.called
    assert ts.code == "13522"


@respx.mock
def test_series_empty_raises() -> None:
    respx.get(f"{SGS_BASE}/bcdata.sgs.99999/dados/ultimos/1").mock(
        return_value=httpx.Response(200, json=[])
    )
    with pytest.raises(DataNotFoundError):
        Bacen().series(code=99999, last=1)


@respx.mock
def test_custom_date_range() -> None:
    respx.get(url__regex=rf"{SGS_BASE}/bcdata\.sgs\.1/dados.*").mock(
        return_value=httpx.Response(200, json=FAKE_SELIC)
    )
    ts = Bacen().dolar(start="2026-01-01", end="2026-04-01")
    assert len(ts) == 3
