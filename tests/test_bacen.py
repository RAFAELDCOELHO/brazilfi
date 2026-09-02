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

FAKE_IGPM = [
    {"data": "01/01/2026", "valor": "0.62"},
    {"data": "01/02/2026", "valor": "0.85"},
    {"data": "01/03/2026", "valor": "-0.11"},
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
def test_igpm_last_n() -> None:
    route = respx.get(f"{SGS_BASE}/bcdata.sgs.189/dados/ultimos/3").mock(
        return_value=httpx.Response(200, json=FAKE_IGPM)
    )
    ts = Bacen().igpm(last=3)
    assert route.called
    assert len(ts) == 3
    assert ts.source == "bacen"
    assert ts.code == "189"
    df = ts.to_dataframe()
    assert len(df) == 3
    assert "value" in df.columns


@respx.mock
def test_igpm_date_range() -> None:
    route = respx.get(url__regex=rf"{SGS_BASE}/bcdata\.sgs\.189/dados.*").mock(
        return_value=httpx.Response(200, json=FAKE_IGPM)
    )
    ts = Bacen().igpm(start="2026-01-01", end="2026-03-01")
    assert route.called
    assert ts.code == "189"
    assert len(ts) == 3


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


# ---------- Focus (Olinda) ----------

FOCUS_ANUAL = {
    "value": [
        {
            "Indicador": "IPCA", "IndicadorDetalhe": None, "Data": "2026-08-21",
            "DataReferencia": "2026", "Media": 5.0067, "Mediana": 5.0248, "DesvioPadrao": 0.209,
            "Minimo": 4.3, "Maximo": 5.6, "numeroRespondentes": 120, "baseCalculo": 0,
        },
        {
            "Indicador": "IPCA", "IndicadorDetalhe": None, "Data": "2026-08-28",
            "DataReferencia": "2026", "Media": 4.99, "Mediana": 5.0, "DesvioPadrao": 0.2,
            "Minimo": 4.3, "Maximo": 5.6, "numeroRespondentes": 118, "baseCalculo": 0,
        },
    ]
}
FOCUS_ANY = r"https://olinda\.bcb\.gov\.br/olinda/servico/Expectativas/versao/v1/odata/.*"


@respx.mock
def test_focus_builds_odata_query_with_percent20() -> None:
    route = respx.get(url__regex=FOCUS_ANY).mock(return_value=httpx.Response(200, json=FOCUS_ANUAL))
    df = Bacen().focus("IPCA", start="2026-08-01", end="2026-08-31")

    url = str(route.calls[0].request.url)
    assert "/ExpectativasMercadoAnuais?" in url
    # O Olinda rejeita "+" como espaço: a query tem de ir com %20.
    assert "+" not in url
    assert "$filter=Indicador%20eq%20'IPCA'%20and%20Data%20ge%20'2026-08-01'" in url
    assert "Data%20le%20'2026-08-31'%20and%20baseCalculo%20eq%200" in url
    assert "$orderby=Data%20asc" in url and "$format=json" in url

    assert list(df.columns[:4]) == ["indicator", "detail", "date", "reference"]
    assert str(df["date"].iloc[-1].date()) == "2026-08-28"
    assert df["median"].iloc[-1] == 5.0
    assert df["respondents"].iloc[0] == 120


@respx.mock
def test_focus_freq_selects_dataset_and_base_none_drops_filter() -> None:
    route = respx.get(url__regex=FOCUS_ANY).mock(return_value=httpx.Response(200, json=FOCUS_ANUAL))
    Bacen().focus("Selic", freq="selic", base=None)
    url = str(route.calls[0].request.url)
    assert "/ExpectativasMercadoSelic?" in url
    assert "baseCalculo" not in url
    assert "Indicador%20eq%20'Selic'" in url


def test_focus_invalid_freq_raises() -> None:
    with pytest.raises(ValueError, match="freq"):
        Bacen().focus("IPCA", freq="semanal")


@respx.mock
def test_focus_empty_raises_data_not_found() -> None:
    respx.get(url__regex=FOCUS_ANY).mock(return_value=httpx.Response(200, json={"value": []}))
    with pytest.raises(DataNotFoundError):
        Bacen().focus("Indicador Inexistente")
