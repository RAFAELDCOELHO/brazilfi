"""Testes do provider IPEA (Ipeadata OData) com respx e catálogo em cache temporário."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import respx

from brazilfi.core.exceptions import DataNotFoundError
from brazilfi.providers import ipea as ipea_module
from brazilfi.providers.ipea import CATALOG_URL, IPEA, IPEA_BASE

CATALOG = {
    "value": [
        {
            "SERCODIGO": "PRECOS12_IPCAG12", "SERNOME": "IPCA - geral - taxa de variação",
            "PERNOME": "Mensal", "UNINOME": "(% a.m.)", "FNTSIGLA": "IBGE/SNIPC",
            "BASNOME": "Macroeconômico", "SERSTATUS": "A",
            "SERATUALIZACAO": "2026-08-11T10:11:29.877-03:00", "SERCOMENTARIO": "...",
        },
        {
            "SERCODIGO": "PIBPMCE", "SERNOME": "PIB Estadual - preços de mercado",
            "PERNOME": "Anual", "UNINOME": "R$", "FNTSIGLA": "IBGE", "BASNOME": "Regional",
            "SERSTATUS": "A", "SERATUALIZACAO": None, "SERCOMENTARIO": "",
        },
        {
            "SERCODIGO": "VELHA_IPCA", "SERNOME": "IPCA descontinuado", "PERNOME": "Mensal",
            "UNINOME": "%", "FNTSIGLA": "IBGE", "BASNOME": "Macroeconômico", "SERSTATUS": "I",
            "SERATUALIZACAO": None, "SERCOMENTARIO": "",
        },
    ]
}
META_IPCA = {"value": [CATALOG["value"][0]]}
VALUES_IPCA = {
    "value": [
        {"SERCODIGO": "PRECOS12_IPCAG12", "VALDATA": "2026-06-01T00:00:00-03:00",
         "VALVALOR": 0.24, "NIVNOME": "", "TERCODIGO": ""},
        {"SERCODIGO": "PRECOS12_IPCAG12", "VALDATA": "2026-07-01T00:00:00-03:00",
         "VALVALOR": 0.26, "NIVNOME": "", "TERCODIGO": ""},
        {"SERCODIGO": "PRECOS12_IPCAG12", "VALDATA": "2026-08-01T00:00:00-03:00",
         "VALVALOR": None, "NIVNOME": "", "TERCODIGO": ""},
    ]
}
VALUES_PIB_UF = {
    "value": [
        {"SERCODIGO": "PIBPMCE", "VALDATA": "2020-01-01T00:00:00-03:00", "VALVALOR": 100.0,
         "NIVNOME": "Brasil", "TERCODIGO": "0"},
        {"SERCODIGO": "PIBPMCE", "VALDATA": "2020-01-01T00:00:00-03:00", "VALVALOR": 30.0,
         "NIVNOME": "Estados", "TERCODIGO": "35"},
        {"SERCODIGO": "PIBPMCE", "VALDATA": "2020-01-01T00:00:00-03:00", "VALVALOR": 10.0,
         "NIVNOME": "Estados", "TERCODIGO": "33"},
    ]
}


@pytest.fixture(autouse=True)
def _tmp_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ipea_module, "CACHE_DIR", tmp_path)


@respx.mock
def test_search_filters_catalog_locally() -> None:
    route = respx.get(CATALOG_URL).mock(
        return_value=httpx.Response(200, content=json.dumps(CATALOG).encode())
    )
    df = IPEA().search("ipca")
    assert route.called
    assert list(df["code"]) == ["PRECOS12_IPCAG12"]  # "VELHA_IPCA" está inativa
    assert df.iloc[0]["freq"] == "Mensal"
    assert str(df.iloc[0]["updated"].date()) == "2026-08-11"

    inactive = IPEA().search("ipca", active_only=False)
    assert list(inactive["code"]) == ["PRECOS12_IPCAG12", "VELHA_IPCA"]
    assert list(IPEA().search(freq="anual")["code"]) == ["PIBPMCE"]
    assert list(IPEA().search(source="snipc")["code"]) == ["PRECOS12_IPCAG12"]
    assert route.call_count == 1  # catálogo em cache
    with pytest.raises(DataNotFoundError):
        IPEA().search("selic")


@respx.mock
def test_serie_returns_timeseries_and_skips_null_values() -> None:
    respx.get(f"{IPEA_BASE}/Metadados('PRECOS12_IPCAG12')").mock(
        return_value=httpx.Response(200, json=META_IPCA)
    )
    respx.get(f"{IPEA_BASE}/ValoresSerie(SERCODIGO='PRECOS12_IPCAG12')").mock(
        return_value=httpx.Response(200, json=VALUES_IPCA)
    )
    ts = IPEA().serie("PRECOS12_IPCAG12")
    assert ts.source == "ipea"
    assert ts.name == "IPCA - geral - taxa de variação"
    assert ts.unit == "(% a.m.)"
    assert len(ts) == 2
    assert ts.points[-1].value == Decimal("0.26")
    assert str(ts.points[0].date) == "2026-06-01"


@respx.mock
def test_serie_regional_defaults_to_brasil_and_accepts_territorio() -> None:
    respx.get(f"{IPEA_BASE}/Metadados('PIBPMCE')").mock(
        return_value=httpx.Response(200, json={"value": [CATALOG["value"][1]]})
    )
    respx.get(f"{IPEA_BASE}/ValoresSerie(SERCODIGO='PIBPMCE')").mock(
        return_value=httpx.Response(200, json=VALUES_PIB_UF)
    )
    ipea = IPEA()
    assert [float(p.value) for p in ipea.serie("PIBPMCE").points] == [100.0]
    assert [float(p.value) for p in ipea.serie("PIBPMCE", territorio="35").points] == [30.0]
    df = ipea.dataframe("PIBPMCE")
    assert len(df) == 3 and set(df["territory"]) == {"0", "33", "35"}
    with pytest.raises(DataNotFoundError):
        ipea.serie("PIBPMCE", territorio="99")


@respx.mock
def test_unknown_series_raises() -> None:
    respx.get(f"{IPEA_BASE}/Metadados('NADA')").mock(
        return_value=httpx.Response(200, json={"value": []})
    )
    with pytest.raises(DataNotFoundError):
        IPEA().metadata("NADA")
