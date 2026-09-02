"""Testes do provider ANBIMA (curva IMA-B) com respx (mock HTTP)."""
from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pandas as pd
import pytest
import respx

from brazilfi.core.exceptions import DataNotFoundError, ProviderError
from brazilfi.providers import anbima as anbima_module
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


# ---------- Outros índices da família IMA ----------


@respx.mock
def test_curva_ima_other_indices() -> None:
    _mock_ima()
    an = ANBIMA()
    ima_b5 = an.curva_ima("ima-b 5")  # case-insensitive
    assert ima_b5.index == "IMA-B 5"
    assert len(ima_b5) == 1
    assert ima_b5.index_number == Decimal("11630.69106200")
    assert ima_b5.duration_days == 573

    irfm = an.curva_ima("IRF-M")
    assert [p.bond_type for p in irfm.points] == ["LTN"]
    assert irfm.points[0].rate == Decimal("13.6522")
    assert len(an.curva_ima_dataframe("IMA-B 5+")) == 1


def test_curva_ima_invalid_index_raises() -> None:
    with pytest.raises(ValueError, match="index"):
        ANBIMA().curva_ima("IBOV")


# ---------- Debêntures (mercado secundário) ----------

# Fatia real de db260901.txt: cabeçalho institucional, linha vazia, cabeçalho de colunas
# e papéis com DI+, IPCA+ (com NTN-B de referência), PREFIXADO, "% do DI" e um sem taxa (N/D).
FAKE_DEBENTURES = """\
ANBIMA - Associação Brasileira das Entidades dos Mercados Financeiro e de Capitais

Código@Nome@Repac./  Venc.@Índice/ Correção@Taxa de Compra@Taxa de Venda@Taxa Indicativa@Desvio Padrão@Intervalo Indicativo Minimo@Intervalo Indicativo Máximo@PU@% PU Par / % VNE@Duration@% Reune@Referência NTN-B
AALM12@AURA ALMAS MINERACAO S.A. (*)@02/10/2030@DI + 1,6%@0,8434@0,5768@0,7122@0,0544@0,6578@0,7667@1082,783718@101,8086@516,06@35@
VLIM25@VLI MULTIMODAL S/A (*)@15/04/2031@PREFIXADO 11,44%@--@--@--@--@--@--@N/D@N/D@N/D@@
PETR16@PETROBRAS S.A.@15/09/2031@IPCA + 5,5%@6,1@5,9@6,0@0,05@5,9@6,1@1234,5@99,5@1200,5@@15/08/2030
CDIX11@EMPRESA DI PERCENTUAL S.A.@01/01/2028@114,65% do DI@--@--@0,5@0,01@0,4@0,6@1000,0@100,0@300@@
"""

DEB_ANY = r"https://www\.anbima\.com\.br/informacoes/merc-sec-debentures/arqs/db\d{6}\.txt"


@pytest.fixture(autouse=True)
def _tmp_anbima_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(anbima_module, "CACHE_DIR", tmp_path)


def _mock_deb(body: str = FAKE_DEBENTURES) -> respx.Route:
    return respx.get(url__regex=DEB_ANY).mock(
        return_value=httpx.Response(200, content=body.encode("latin-1"))
    )


@respx.mock
def test_debentures_parses_daily_file() -> None:
    route = _mock_deb()
    df = ANBIMA().debentures(on="2026-09-01")

    assert route.calls[0].request.url.path.endswith("/db260901.txt")
    assert list(df["code"]) == ["AALM12", "CDIX11", "PETR16", "VLIM25"]
    assert str(df["date"].iloc[0].date()) == "2026-09-01"

    aalm = df.set_index("code").loc["AALM12"]
    assert aalm["issuer"] == "AURA ALMAS MINERACAO S.A. (*)"
    assert str(aalm["maturity"].date()) == "2030-10-02"
    assert (aalm["indexer"], aalm["coupon"]) == ("DI +", pytest.approx(1.6))
    assert aalm["bid_rate"] == pytest.approx(0.8434)
    assert aalm["indicative_rate"] == pytest.approx(0.7122)
    assert aalm["price"] == pytest.approx(1082.783718)
    assert aalm["duration"] == pytest.approx(516.06)
    assert pd.isna(aalm["ntnb_reference"])

    petr = df.set_index("code").loc["PETR16"]
    assert (petr["indexer"], petr["coupon"]) == ("IPCA +", pytest.approx(5.5))
    assert str(petr["ntnb_reference"].date()) == "2030-08-15"

    cdix = df.set_index("code").loc["CDIX11"]
    assert (cdix["indexer"], cdix["coupon"]) == ("% DI", pytest.approx(114.65))

    vlim = df.set_index("code").loc["VLIM25"]
    assert (vlim["indexer"], vlim["coupon"]) == ("PREFIXADO", pytest.approx(11.44))
    assert math.isnan(vlim["indicative_rate"]) and math.isnan(vlim["price"])


@respx.mock
def test_debentures_walks_back_to_last_published_day() -> None:
    route = respx.get(url__regex=DEB_ANY).mock(
        side_effect=[httpx.Response(404), httpx.Response(200, content=FAKE_DEBENTURES.encode("latin-1"))]
    )
    df = ANBIMA().debentures()
    assert route.call_count == 2
    assert df["date"].iloc[0].date() == date.today() - timedelta(days=1)


@respx.mock
def test_debentures_past_day_is_cached() -> None:
    route = _mock_deb()
    ANBIMA().debentures(on=date(2026, 9, 1))
    ANBIMA().debentures(on="2026-09-01")
    assert route.call_count == 1


@respx.mock
def test_debentures_empty_file_raises() -> None:
    _mock_deb("ANBIMA\n\nCódigo@Nome@Repac./  Venc.@Índice/ Correção@a@b@c@d@e@f@g@h@i@j@k\n")
    with pytest.raises(DataNotFoundError):
        ANBIMA().debentures(on="2026-09-01")
