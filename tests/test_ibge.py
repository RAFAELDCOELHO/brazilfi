"""Testes do provider IBGE."""
from __future__ import annotations

from datetime import date

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
                                    "serie": {"202501": "7.2", "202502": "6.9"},
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


FAKE_IPCA_SP = [
    {
        "id": "63",
        "variavel": "IPCA — variação mensal",
        "unidade": "%",
        "resultados": [
            {
                "classificacoes": [],
                "series": [
                    {
                        "localidade": {"id": "3550308", "nome": "São Paulo - SP"},
                        "serie": {"202601": "0.61", "202602": "0.28"},
                    }
                ],
            }
        ],
    }
]


@respx.mock
def test_ipca_municipio() -> None:
    route = respx.get(url__regex=rf"{BASE}/7060/periodos/-2/variaveis/63.*").mock(
        return_value=httpx.Response(200, json=FAKE_IPCA_SP)
    )
    ts = IBGE().ipca(last=2, localidade="N6[3550308]")
    assert ts.code == "7060.63"
    assert len(ts) == 2
    assert route.calls.last.request.url.params["localidades"] == "N6[3550308]"


@respx.mock
def test_desemprego_uf() -> None:
    route = respx.get(url__regex=rf"{BASE}/4099/periodos/-2/variaveis/4099.*").mock(
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
                                    "localidade": {"id": "35", "nome": "São Paulo"},
                                    "serie": {"202501": "6.8", "202502": "6.5"},
                                }
                            ],
                        }
                    ],
                }
            ],
        )
    )
    ts = IBGE().desemprego(last=2, localidade="N3[35]")
    assert len(ts) == 2
    assert route.calls.last.request.url.params["localidades"] == "N3[35]"


@respx.mock
def test_populacao_municipio() -> None:
    route = respx.get(url__regex=rf"{BASE}/6579/periodos/-1/variaveis/9324.*").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "9324",
                    "variavel": "População residente estimada",
                    "unidade": "Pessoas",
                    "resultados": [
                        {
                            "classificacoes": [],
                            "series": [
                                {
                                    "localidade": {
                                        "id": "3550308",
                                        "nome": "São Paulo - SP",
                                    },
                                    "serie": {"2024": "11895893"},
                                }
                            ],
                        }
                    ],
                }
            ],
        )
    )
    ts = IBGE().populacao(last=1, localidade="N6[3550308]")
    assert len(ts) == 1
    assert route.calls.last.request.url.params["localidades"] == "N6[3550308]"


@respx.mock
def test_localidade_default_permanece_brasil() -> None:
    route = respx.get(url__regex=rf"{BASE}/7060/periodos/-3/variaveis/63.*").mock(
        return_value=httpx.Response(200, json=FAKE_IPCA)
    )
    IBGE().ipca(last=3)
    assert route.calls.last.request.url.params["localidades"] == "N1[all]"


def test_ipca_uf_rejeitada() -> None:
    """IPCA é apurado por município/RM — o SIDRA não serve o agregado 7060 em N3."""
    with pytest.raises(ValueError, match="N3"):
        IBGE().ipca(last=3, localidade="N3[35]")


def test_pib_so_brasil() -> None:
    """1620 é servido só em N1: pib() não expõe localidade e agregado() a rejeita."""
    with pytest.raises(TypeError):
        IBGE().pib(last=4, localidade="N3[35]")  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="N1"):
        IBGE().agregado(1620, 583, last=4, localidade="N6[3550308]")


def test_agregado_desconhecido_nao_valida_nivel() -> None:
    """Agregado fora da tabela de metadados passa direto — quem decide é o SIDRA."""
    with respx.mock:
        respx.get(url__regex=rf"{BASE}/9999/periodos/-1/variaveis/1.*").mock(
            return_value=httpx.Response(200, json=[])
        )
        with pytest.raises(DataNotFoundError):
            IBGE().agregado(9999, 1, last=1, localidade="N6[3550308]")


# ---------- Periodicidade trimestral ----------


def test_parse_period_trimestral() -> None:
    # SIDRA codifica trimestre como YYYYQQ, indistinguível de um mês sem contexto
    assert IBGE._parse_period("202601", trimestral=True) == date(2026, 1, 1)
    assert IBGE._parse_period("202602", trimestral=True) == date(2026, 4, 1)
    assert IBGE._parse_period("202604", trimestral=True) == date(2026, 10, 1)
    assert IBGE._parse_period("202604") == date(2026, 4, 1)  # mensal
    with pytest.raises(ValueError):
        IBGE._parse_period("202605", trimestral=True)


@respx.mock
def test_pib_periodos_sao_trimestres() -> None:
    respx.get(url__regex=rf"{BASE}/1620/periodos/-2/variaveis/583.*").mock(
        return_value=httpx.Response(
            200,
            json=[{
                "id": "583",
                "variavel": "Série encadeada do índice de volume trimestral",
                "unidade": "Número-índice",
                "resultados": [{"series": [{"serie": {"202601": "194.53", "202602": "199.05"}}]}],
            }],
        )
    )
    ts = IBGE().pib(last=2)
    assert [p.date for p in ts.points] == [date(2026, 1, 1), date(2026, 4, 1)]


@respx.mock
def test_ipca_acum_12m_usa_variavel_2265() -> None:
    route = respx.get(url__regex=rf"{BASE}/7060/periodos/-1/variaveis/2265.*").mock(
        return_value=httpx.Response(
            200,
            json=[{
                "id": "2265",
                "variavel": "IPCA - Variação acumulada em 12 meses",
                "unidade": "%",
                "resultados": [{"series": [{"serie": {"202607": "4.44"}}]}],
            }],
        )
    )
    ts = IBGE().ipca(last=1, acum_12m=True)
    assert route.called
    assert ts.points[0].date == date(2026, 7, 1)
    assert float(ts.points[0].value) == 4.44
