"""Testes do provider IBGE."""
from __future__ import annotations

import httpx
import pytest
import respx

from brazilfi.core.exceptions import DataNotFoundError
from brazilfi.providers.ibge import IBGE

BASE = "https://servicodados.ibge.gov.br/api/v3/agregados"

FAKE_PIB = [
    {
        "id": "583",
        "variavel": "PIB a preços de mercado",
        "unidade": "Milhões de reais",
        "resultados": [
            {
                "classificacoes": [],
                "series": [
                    {
                        "localidade": {"id": "1", "nome": "Brasil"},
                        "serie": {
                            "2025.I": "2800000",
                            "2025.II": "2850000",
                            "2025.III": "2900000",
                            "2025.IV": "2950000",
                        },
                    }
                ],
            }
        ],
    }
]

FAKE_IPCA = [
    {
        "id": "63",
        "variavel": "IPCA — variação mensal",
        "unidade": "%",
        "resultados": [
            {
                "classificacoes": [],
                "series": [
                    {
                        "localidade": {"id": "1", "nome": "Brasil"},
                        "serie": {
                            "202601": "0.54",
                            "202602": "0.31",
                            "202603": "0.40",
                        },
                    }
                ],
            }
        ],
    }
]


@respx.mock
def test_pib_trimestral() -> None:
    respx.get(url__regex=rf"{BASE}/1620/periodos/-4/variaveis/583.*").mock(
        return_value=httpx.Response(200, json=FAKE_PIB)
    )
    ts = IBGE().pib(last=4)
    assert ts.source == "ibge"
    assert ts.code == "1620.583"
    assert len(ts) == 4
    # Ordenação cronológica
    assert ts.points[0].date.year == 2025 and ts.points[0].date.month == 1
    assert ts.points[-1].date.month == 10


@respx.mock
def test_ipca_mensal() -> None:
    respx.get(url__regex=rf"{BASE}/7060/periodos/-3/variaveis/63.*").mock(
        return_value=httpx.Response(200, json=FAKE_IPCA)
    )
    ts = IBGE().ipca(last=3)
    assert ts.code == "7060.63"
    assert len(ts) == 3
    df = ts.to_dataframe()
    assert len(df) == 3


@respx.mock
def test_agregado_generico() -> None:
    respx.get(url__regex=rf"{BASE}/4099/periodos/-2/variaveis/4099.*").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "4099",
                    "variavel": "Taxa de desocupação",
                    "unidade": "%",
                    "resultados": [
                        {
                            "classificacoes": [],
                            "series": [
                                {
                                    "localidade": {"id": "1", "nome": "Brasil"},
                                    "serie": {"202504": "7.2", "202507": "6.9"},
                                }
                            ],
                        }
                    ],
                }
            ],
        )
    )
    ts = IBGE().agregado(4099, 4099, last=2)
    assert len(ts) == 2


@respx.mock
def test_empty_raises() -> None:
    respx.get(url__regex=rf"{BASE}/9999/periodos/-1/variaveis/1.*").mock(
        return_value=httpx.Response(200, json=[])
    )
    with pytest.raises(DataNotFoundError):
        IBGE().agregado(9999, 1, last=1)


def test_parse_period() -> None:
    assert IBGE._parse_period("2024").year == 2024
    assert IBGE._parse_period("202404").month == 4
    assert IBGE._parse_period("2024.I").month == 1
    assert IBGE._parse_period("2024.II").month == 4
    assert IBGE._parse_period("2024.III").month == 7
    assert IBGE._parse_period("2024.IV").month == 10
