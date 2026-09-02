"""Testes do provider ANBIMA (curva IMA-B) com respx (mock HTTP)."""
from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
import respx

from brazilfi.core.exceptions import DataNotFoundError, ProviderError
from brazilfi.providers.anbima import ANBIMA, IMA_COMPLETO_TXT

# Fatia real do arquivo completo do IMA (registro 1 = TOTAIS, registro 2 =
# COMPOSIÇÃO DE CARTEIRA), delimitado por "@" e servido em latin-1.
# Inclui IMA-B 5 / IMA-B 5+ / IRF-M de propósito: nada além do IMA-B total
# deve ser parseado.
FAKE_IMA_COMPLETO = """\
0@ANBIMA - Associação Brasileira das Entidades dos Mercados Financeiros e de Capitais
1@TOTAIS
1@Data de Referência@INDICE@Número Índice@Variação Diária(%)@Variação Mensal(%)@Variação Anual(%)@Variação Últimos 12 Meses(%)@Variação Últimos 24 Meses(%)@Duration(d.u.)@Peso(Geral)(%)@Carteira a Mercado(R$ mil)@Número de Operações *@Quant. Negociada(1.000 títulos) *@Valor Negociado(R$ mil) *@PMR@Convexidade@Yield@Redemption Yield
1@01/09/2026@IRF-M@23181,46831900@0,2202@0,2202@7,2922@12,3096@24,7717@613@20,68@1721074456@--@--@--@948,700245873267@9,33547561031961@14,0580649161506@14,3388852448028
1@01/09/2026@IMA-B 5@11630,69106200@0,1216@0,1216@9,3097@13,4809@23,5350@573@7,61@633702623@--@--@--@848,780584138096@7,70448098170688@7,69555838139686@7,9143540488992
1@01/09/2026@IMA-B 5+@12712,79390900@0,1325@0,1325@4,9830@10,0723@10,8900@2379@12,97@1079923910@--@--@--@4644,54394869168@130,006401213214@7,67900759294912@7,61335992353424
1@01/09/2026@IMA-B@11691,23877300@0,1285@0,1285@6,8848@11,5776@16,2709@1711@20,59@1713626533@--@--@--@3240,86283498545@84,7788990980597@7,6851281086214@7,65062762302511

2@COMPOSIÇÃO DE CARTEIRA
2@Data de Referência@INDICE@Títulos@Data de Vencimento@Código SELIC@Código ISIN@Taxa Indicativa (% a.a.)@PU (R$)@PU de Juros (R$)@Quantidade (1.000 títulos)@Quantidade Teórica (1.000 títulos)@Carteira a Mercado (R$ mil)@Peso (%)@Prazo (d.u.)@Duration (d.u.)@Número de Operações *@Quant. Negociada (1.000 títulos) *@Valor Negociado (R$ mil) *@PMR@Convexidade
2@01/09/2026@IRF-M@LTN@01/10/2026@100000@BRSTNCLTN8G4@13,6522@989,392269@0,000000@92198,71@1,08909306@91220692@5,30@21@21@--@--@--@30@6,98916295587365E-02
2@01/09/2026@IMA-B 5@NTN-B@15/05/2027@760199@BRSTNCNTB682@6,6000@4803,143250@0,000000@26813,57@0,49456971@128789432@20,32@174@170@--@--@--@252,919898370545@1,00378011980643
2@01/09/2026@IMA-B 5+@NTN-B@15/08/2032@760199@BRSTNCNTB674@8,0502@4320,157192@0,000000@22908,04@0,24798574@98966342@9,17@1491@1262@--@--@--@1912,89640053444@28,1295551715586
2@01/09/2026@IMA-B@NTN-B@15/05/2027@760199@BRSTNCNTB682@6,6000@4803,143250@0,000000@26813,57@0,18293594@128789432@7,52@174@170@--@--@--@252,919898370545@1,00378011980643
2@01/09/2026@IMA-B@NTN-B@15/08/2028@760199@BRSTNCNTB4X0@7,8955@4598,065724@0,000000@46841,65@0,31957777@215380995@12,57@489@467@--@--@--@685,078136427992@4,62833665169328
2@01/09/2026@IMA-B@NTN-B@15/08/2030@760199@BRSTNCNTB3B8@8,0683@4443,463210@0,000000@46312,46@0,31596731@205787690@12,01@987@888@--@--@--@1321,92298343245@14,3776717290968
2@01/09/2026@IMA-B@NTN-B@15/08/2060@760199@BRSTNCNTB690@7,4238@3955,367616@0,000000@21802,45@0,14874749@86236701@5,03@8504@3354@--@--@--@8317,31681893621@264,583926193887
"""


def _mock_ima(body: str = FAKE_IMA_COMPLETO) -> respx.Route:
    """Mocka o TXT completo do IMA como a ANBIMA serve: latin-1, sem charset."""
    return respx.get(IMA_COMPLETO_TXT).mock(
        return_value=httpx.Response(
            200,
            content=body.encode("latin-1"),
            headers={"Content-Type": "text/plain"},
        )
    )


@respx.mock
def test_curva_ima_hits_documented_anbima_endpoint() -> None:
    route = _mock_ima()
    ANBIMA().curva_ima()
    assert route.called
    assert str(route.calls[0].request.url) == IMA_COMPLETO_TXT
    assert route.calls[0].request.url.host == "www.anbima.com.br"


@respx.mock
def test_curva_ima_returns_yield_curve() -> None:
    _mock_ima()
    curva = ANBIMA().curva_ima()
    assert curva.index == "IMA-B"
    assert curva.source == "anbima"
    assert curva.unit == "% a.a."
    assert curva.reference_date.isoformat() == "2026-09-01"
    assert curva.index_number == Decimal("11691.23877300")
    assert curva.daily_change_pct == Decimal("0.1285")
    assert curva.duration_days == 1711


@respx.mock
def test_curva_ima_parses_only_ima_b_total() -> None:
    _mock_ima()
    curva = ANBIMA().curva_ima()
    # 4 vértices IMA-B; IMA-B 5, IMA-B 5+ e IRF-M ficam de fora.
    assert len(curva) == 4
    assert {p.bond_type for p in curva.points} == {"NTN-B"}
    maturities = [p.maturity.isoformat() for p in curva.points]
    assert maturities == ["2027-05-15", "2028-08-15", "2030-08-15", "2060-08-15"]


@respx.mock
def test_curva_ima_point_fields() -> None:
    _mock_ima()
    curva = ANBIMA().curva_ima()
    short = curva.points[0]
    assert short.rate == Decimal("6.6000")
    assert short.price == Decimal("4803.143250")
    assert short.weight_pct == Decimal("7.52")
    assert short.business_days == 174
    assert short.duration_days == 170
    assert short.selic_code == "760199"
    assert short.isin == "BRSTNCNTB682"


@respx.mock
def test_curva_ima_points_sorted_by_maturity() -> None:
    _mock_ima()
    points = ANBIMA().curva_ima().points
    assert points == sorted(points, key=lambda p: p.maturity)


@respx.mock
def test_curva_ima_dataframe() -> None:
    _mock_ima()
    df = ANBIMA().curva_ima_dataframe()
    assert len(df) == 4
    assert df.index.name == "maturity"
    assert "rate" in df.columns
    assert "price" in df.columns
    assert df["rate"].iloc[0] == pytest.approx(6.6)
    assert df.index.is_monotonic_increasing


@respx.mock
def test_curva_ima_latin1_accents_do_not_break_parsing() -> None:
    _mock_ima()
    # O arquivo real vem em latin-1; se o decode falhasse, os cabeçalhos
    # acentuados poderiam virar vértices espúrios.
    assert len(ANBIMA().curva_ima()) == 4


@respx.mock
def test_curva_ima_without_totals_still_returns_points() -> None:
    body = "\n".join(
        line for line in FAKE_IMA_COMPLETO.splitlines() if not line.startswith("1@")
    )
    _mock_ima(body)
    curva = ANBIMA().curva_ima()
    assert len(curva) == 4
    assert curva.reference_date.isoformat() == "2026-09-01"
    assert curva.index_number is None
    assert curva.duration_days is None


@respx.mock
def test_curva_ima_missing_index_raises() -> None:
    body = "\n".join(
        line for line in FAKE_IMA_COMPLETO.splitlines() if "@IMA-B@" not in line
    )
    _mock_ima(body)
    with pytest.raises(DataNotFoundError):
        ANBIMA().curva_ima()


@respx.mock
def test_curva_ima_empty_file_raises() -> None:
    _mock_ima("")
    with pytest.raises(DataNotFoundError):
        ANBIMA().curva_ima()


@respx.mock
def test_curva_ima_http_error_raises_provider_error() -> None:
    respx.get(IMA_COMPLETO_TXT).mock(return_value=httpx.Response(503, text="unavailable"))
    with pytest.raises(ProviderError):
        ANBIMA().curva_ima()
