"""Testes do provider CVM (dados abertos) com respx e cache redirecionado para tmp_path."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import httpx
import pandas as pd
import pytest
import respx

from brazilfi.core.exceptions import DataNotFoundError
from brazilfi.providers import cvm as cvm_module
from brazilfi.providers.cvm import CAD_CIA_URL, CVM, CVM_BASE, REGISTRO_URL

# Cabeçalhos e linhas reduzidos dos arquivos reais (latin-1, separador ";").

REGISTRO_CLASSE = """\
ID_Registro_Fundo;ID_Registro_Classe;CNPJ_Classe;Codigo_CVM;Data_Inicio;Tipo_Classe;Denominacao_Social;Situacao;Classificacao;Classificacao_Anbima;Forma_Condominio;Exclusivo;Publico_Alvo;Patrimonio_Liquido;Data_Patrimonio_Liquido
2071;35522;60079651000140;4464;2025-03-25;Classes de Cotas de Fundos FII;VERDE A&I CEDRO PORTFOLIO RENDA FII;Em Funcionamento Normal;;;Fechado;N;Público Geral;165878600.00;2026-07-31
10;20;00017024000153;3;1994-12-20;CLASSES - FIF;FIF - CLASSE DE INVESTIMENTO RENDA FIXA;Em Funcionamento Normal;Renda Fixa;Renda Fixa Duração Baixa;Aberto;N;Público Geral;1214277.88;2026-08-31
99;98;11111111000111;9;2010-01-01;CLASSES - FIF;FUNDO VERDE ANTIGO;Cancelado;Ações;;Aberto;N;Público Geral;0.00;2015-01-01
"""
REGISTRO_FUNDO = """\
ID_Registro_Fundo;CNPJ_Fundo;Denominacao_Social;Administrador;Gestor
2071;60079651000140;VERDE A&I CEDRO FII;BTG PACTUAL SERVIÇOS FINANCEIROS S.A. DTVM;VERDE ASSET AGRO E IMOBILIÁRIO LTDA
10;00017024000153;BRADESCO FIF RF;BANCO BRADESCO S.A.;BRAM - BRADESCO ASSET MANAGEMENT S.A. DTVM
99;11111111000111;FUNDO VERDE ANTIGO;ADM X;GESTOR X
"""
# Julho ainda no layout antigo, agosto já no layout da Resolução CVM 175.
INF_202607 = """\
TP_FUNDO;CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST
FI;00.017.024/0001-53;2026-07-30;1095646.22;44.100000000000;1207786.03;0.00;0.00;1
FI;00.017.024/0001-53;2026-07-31;1096222.50;44.200000000000;1208303.34;10.00;0.00;1
FI;60.079.651/0001-40;2026-07-31;1.00;1.000000000000;1.00;0.00;0.00;5
"""
INF_202608 = """\
TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;ID_SUBCLASSE;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST
CLASSES - FIF;00.017.024/0001-53;;2026-08-03;1095646.22;44.275588000000;1207786.03;0.00;0.00;1
CLASSES - FIF;00.017.024/0001-53;;2026-08-04;1096222.50;44.294551800000;1208303.34;0.00;2842.45;1
CLASSES - FIF;60.079.651/0001-40;;2026-08-04;1.00;1.000000000000;1.00;0.00;0.00;5
"""
CAD_CIA = """\
CNPJ_CIA;DENOM_SOCIAL;DENOM_COMERC;DT_REG;SIT;CD_CVM;SETOR_ATIV;CATEG_REG;SIT_EMISSOR
33.000.167/0001-01;PETRÓLEO BRASILEIRO S.A. - PETROBRAS;PETROBRAS;1977-07-20;ATIVO;9512;Petróleo e Gás;Categoria A;FASE OPERACIONAL
33.000.167/0001-01;PETRÓLEO BRASILEIRO S.A. - PETROBRAS;PETROBRAS;1977-07-20;ATIVO;9512;Petróleo e Gás;Categoria A;FASE OPERACIONAL
11.396.633/0001-87;3A COMPANHIA SECURITIZADORA;TRIPLO A;2010-03-08;CANCELADA;21954;Securitização de Recebíveis;Categoria B;FASE PRÉ-OPERACIONAL
"""
DRE_CON_2025 = """\
CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;GRUPO_DFP;MOEDA;ESCALA_MOEDA;ORDEM_EXERC;DT_INI_EXERC;DT_FIM_EXERC;CD_CONTA;DS_CONTA;VL_CONTA;ST_CONTA_FIXA
00.000.000/0001-91;2025-12-31;1;BCO BRASIL S.A.;001023;DF Consolidado - Demonstração do Resultado;REAL;MIL;ÚLTIMO;2025-01-01;2025-12-31;3.01;Receitas de Intermediação Financeira;1.0000000000;S
00.000.000/0001-91;2025-12-31;2;BCO BRASIL S.A.;001023;DF Consolidado - Demonstração do Resultado;REAL;MIL;PENÚLTIMO;2024-01-01;2024-12-31;3.01;Receitas de Intermediação Financeira;273505274.0000000000;S
00.000.000/0001-91;2025-12-31;2;BCO BRASIL S.A.;001023;DF Consolidado - Demonstração do Resultado;REAL;MIL;ÚLTIMO;2025-01-01;2025-12-31;3.01;Receitas de Intermediação Financeira;319462104.0000000000;S
00.000.000/0001-91;2025-12-31;2;BCO BRASIL S.A.;001023;DF Consolidado - Demonstração do Resultado;REAL;MIL;ÚLTIMO;2025-01-01;2025-12-31;3.02;Despesas de Intermediação Financeira;-218451400.0000000000;S
33.000.167/0001-01;2025-12-31;1;PETRÓLEO BRASILEIRO S.A. - PETROBRAS;009512;DF Consolidado - Demonstração do Resultado;REAL;MIL;ÚLTIMO;2025-01-01;2025-12-31;3.01;Receita de Venda de Bens e/ou Serviços;500000000.0000000000;S
"""


def _zip(**members: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, body in members.items():
            zf.writestr(name.replace("__", "."), body.encode("latin-1"))
    return buf.getvalue()


def _latin1(body: str) -> httpx.Response:
    return httpx.Response(200, content=body.encode("latin-1"))


@pytest.fixture(autouse=True)
def _tmp_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cvm_module, "CACHE_DIR", tmp_path)


def _mock_registro() -> respx.Route:
    return respx.get(REGISTRO_URL).mock(
        return_value=httpx.Response(
            200,
            content=_zip(
                registro_classe__csv=REGISTRO_CLASSE,
                registro_fundo__csv=REGISTRO_FUNDO,
                registro_subclasse__csv="ID_Registro_Classe;ID_Subclasse\n",
            ),
        )
    )


def _mock_inf(yyyymm: str, body: str | None) -> respx.Route:
    url = f"{CVM_BASE}/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_{yyyymm}.zip"
    if body is None:
        return respx.get(url).mock(return_value=httpx.Response(404))
    return respx.get(url).mock(
        return_value=httpx.Response(200, content=_zip(**{f"inf_diario_fi_{yyyymm}__csv": body}))
    )


def _mock_dfp(year: int = 2025) -> respx.Route:
    return respx.get(f"{CVM_BASE}/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_{year}.zip").mock(
        return_value=httpx.Response(
            200,
            content=_zip(
                **{
                    f"dfp_cia_aberta_{year}__csv": "CNPJ_CIA;DT_REFER\n",
                    f"dfp_cia_aberta_DRE_con_{year}__csv": DRE_CON_2025,
                }
            ),
        )
    )


# ---------- fundos ----------


@respx.mock
def test_fundos_uses_cvm175_registry_and_merges_manager() -> None:
    route = _mock_registro()
    df = CVM().fundos(search="verde")

    assert route.called
    assert list(df["cnpj"]) == ["60079651000140"]  # "FUNDO VERDE ANTIGO" está cancelado
    row = df.iloc[0]
    assert row["manager"] == "VERDE ASSET AGRO E IMOBILIÁRIO LTDA"
    assert row["fund_cnpj"] == "60079651000140"
    assert row["net_assets"] == pytest.approx(165_878_600.0)
    assert row["cd_cvm"] == 4464
    assert "fund_id" not in df.columns


@respx.mock
def test_fundos_by_cnpj_accepts_punctuation_and_inactive() -> None:
    _mock_registro()
    df = CVM().fundos(cnpj="11.111.111/0001-11", active=False)
    assert df.iloc[0]["situation"] == "Cancelado"
    with pytest.raises(DataNotFoundError):
        CVM().fundos(cnpj="11.111.111/0001-11")


@respx.mock
def test_fundos_second_call_uses_cache() -> None:
    route = _mock_registro()
    CVM().fundos()
    CVM().fundos()
    assert route.call_count == 1


# ---------- cotas ----------


@respx.mock
def test_cotas_concatenates_old_and_new_layouts() -> None:
    _mock_inf("202607", INF_202607)
    _mock_inf("202608", INF_202608)
    df = CVM().cotas("00.017.024/0001-53", start="2026-07-01", end="2026-08-31")

    assert len(df) == 4
    assert df.index.is_monotonic_increasing
    assert str(df.index[0].date()) == "2026-07-30"
    assert df["quota"].iloc[-1] == pytest.approx(44.2945518)
    assert df["outflow"].iloc[-1] == pytest.approx(2842.45)
    assert set(df["cnpj"]) == {"00017024000153"}
    assert int(df["shareholders"].iloc[0]) == 1


@respx.mock
def test_cotas_skips_unpublished_month_and_filters_dates() -> None:
    _mock_inf("202608", INF_202608)
    _mock_inf("202609", None)
    df = CVM().cotas("00017024000153", start="2026-08-04", end="2026-09-30")
    assert len(df) == 1
    assert str(df.index[0].date()) == "2026-08-04"


@respx.mock
def test_cotas_unknown_fund_raises() -> None:
    _mock_inf("202608", INF_202608)
    with pytest.raises(DataNotFoundError):
        CVM().cotas("99.999.999/0001-99", start="2026-08-01", end="2026-08-31")


def test_cotas_start_after_end_raises() -> None:
    with pytest.raises(ValueError):
        CVM().cotas("00017024000153", start="2026-09-01", end="2026-08-01")


# ---------- companhias ----------


@respx.mock
def test_companhias_dedupes_and_filters_active() -> None:
    respx.get(CAD_CIA_URL).mock(return_value=_latin1(CAD_CIA))
    df = CVM().companhias(search="petrobras")
    assert len(df) == 1
    assert df.iloc[0]["cnpj"] == "33000167000101"
    assert df.iloc[0]["cd_cvm"] == 9512

    with pytest.raises(DataNotFoundError):
        CVM().companhias(search="securitizadora")
    assert len(CVM().companhias(active=False)) == 2


# ---------- dfp / itr ----------


@respx.mock
def test_dfp_keeps_latest_version_last_exercise_and_scales_to_brl() -> None:
    route = _mock_dfp()
    df = CVM().dfp(1023, 2025, statement="DRE")

    assert route.called
    assert list(df["account"]) == ["3.01", "3.02"]
    assert df.iloc[0]["value"] == pytest.approx(319_462_104_000.0)  # VERSAO 2, em reais
    assert df.iloc[0]["company"] == "BCO BRASIL S.A."
    assert str(df.iloc[0]["period_start"].date()) == "2025-01-01"
    assert bool(df.iloc[0]["fixed"]) is True


@respx.mock
def test_dfp_by_cnpj_with_comparative_exercise() -> None:
    _mock_dfp()
    df = CVM().dfp("00.000.000/0001-91", 2025, last_only=False)
    assert df["order"].value_counts().to_dict() == {"ÚLTIMO": 2, "PENÚLTIMO": 1}
    assert str(df.iloc[0]["period_end"].date()) == "2024-12-31"


@respx.mock
def test_dfp_unknown_company_and_invalid_statement() -> None:
    _mock_dfp()
    with pytest.raises(DataNotFoundError):
        CVM().dfp(424242, 2025)
    with pytest.raises(ValueError, match="statement"):
        CVM().dfp(1023, 2025, statement="XYZ")


@respx.mock
def test_itr_hits_itr_endpoint_and_member() -> None:
    route = respx.get(f"{CVM_BASE}/CIA_ABERTA/DOC/ITR/DADOS/itr_cia_aberta_2026.zip").mock(
        return_value=httpx.Response(
            200, content=_zip(itr_cia_aberta_DRE_ind_2026__csv=DRE_CON_2025)
        )
    )
    df = CVM().itr(9512, 2026, consolidated=False)
    assert route.called
    assert df.iloc[0]["value"] == pytest.approx(500_000_000_000.0)


# ---------- fii ----------

FII_COMPLEMENTO = """\
CNPJ_Fundo_Classe;Data_Referencia;Versao;Data_Informacao_Numero_Cotistas;Total_Numero_Cotistas;Patrimonio_Liquido;Valor_Patrimonial_Cotas;Percentual_Rentabilidade_Efetiva_Mes;Percentual_Dividend_Yield_Mes
00.332.266/0001-31;2026-01-01;1;2026-01-30;3600;1.00;1.00;0.001;0.001
00.332.266/0001-31;2026-01-01;2;2026-01-30;3639;259735756.51;92.2101419138767;0.005242;0.004342
00.332.266/0001-31;2026-02-01;1;2026-02-27;3620;258000000.00;92.10;0.0050;0.0043
11.111.111/0001-11;2026-01-01;1;2026-01-30;10;1000.00;10.00;0.0;0.0
"""
FII_GERAL = """\
Tipo_Fundo_Classe;CNPJ_Fundo_Classe;Data_Referencia;Versao;Nome_Fundo_Classe;Segmento_Atuacao;Mandato
Classe;00.332.266/0001-31;2026-01-01;2;VIA PARQUE SHOPPING FII RESP LTDA;Shoppings;
"""


def _mock_fii(year: int = 2026) -> respx.Route:
    return respx.get(f"{CVM_BASE}/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_{year}.zip").mock(
        return_value=httpx.Response(
            200,
            content=_zip(
                **{
                    f"inf_mensal_fii_complemento_{year}__csv": FII_COMPLEMENTO,
                    f"inf_mensal_fii_geral_{year}__csv": FII_GERAL,
                }
            ),
        )
    )


@respx.mock
def test_fii_keeps_latest_version_and_converts_numbers() -> None:
    route = _mock_fii()
    df = CVM().fii(2026, cnpj="00.332.266/0001-31")
    assert route.called
    assert len(df) == 2
    jan = df.iloc[0]
    assert str(jan["date"].date()) == "2026-01-01"
    assert jan["version"] == 2
    assert jan["patrimonio_liquido"] == pytest.approx(259_735_756.51)
    assert jan["total_numero_cotistas"] == 3639
    assert str(jan["data_informacao_numero_cotistas"].date()) == "2026-01-30"
    assert set(df["cnpj"]) == {"00332266000131"}

    assert len(CVM().fii(2026)) == 3  # todos os fundos
    geral = CVM().fii(2026, section="geral")
    assert geral.iloc[0]["segmento_atuacao"] == "Shoppings"
    with pytest.raises(ValueError, match="section"):
        CVM().fii(2026, section="xyz")
    with pytest.raises(DataNotFoundError):
        CVM().fii(2026, cnpj="99.999.999/0001-99")


# ---------- carteira (CDA) ----------

CDA_BLC_1 = """\
TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;DENOM_SOCIAL;DT_COMPTC;TP_APLIC;TP_ATIVO;EMISSOR_LIGADO;TP_NEGOC;QT_POS_FINAL;VL_MERC_POS_FINAL;VL_CUSTO_POS_FINAL;DT_CONFID_APLIC;TP_TITPUB;CD_ISIN;CD_SELIC;DT_EMISSAO;DT_VENC
CLASSES - FIF;00.017.024/0001-53;FIF RENDA FIXA;2026-07-31;Títulos Públicos;Título público federal;;Para negociação;29.000000;567153.87;;;LETRAS FINANCEIRAS DO TESOURO;BRSTNCLF1RH3;210100;2021-07-02;2027-09-01
CLASSES - FIF;99.999.999/0001-99;OUTRO FUNDO;2026-07-31;Títulos Públicos;Título público federal;;Para negociação;1.000000;1.00;;;LETRAS FINANCEIRAS DO TESOURO;BRSTNCLF1RH3;210100;2021-07-02;2027-09-01
"""
CDA_BLC_4 = """\
TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;DENOM_SOCIAL;DT_COMPTC;TP_APLIC;TP_ATIVO;EMISSOR_LIGADO;TP_NEGOC;QT_POS_FINAL;VL_MERC_POS_FINAL;VL_CUSTO_POS_FINAL;DT_CONFID_APLIC;CD_ATIVO;DS_ATIVO;CD_ISIN;DT_INI_VIGENCIA;DT_FIM_VIGENCIA
CLASSES - FIF;00.017.024/0001-53;FIF RENDA FIXA;2026-07-31;Ações;Ação ordinária;N;Para negociação;100.000000;300000.00;;;ITUB3;ITAUUNIBANCO ON      N1;BRITUBACNOR4;2009-05-20;
"""
CDA_BLC_8 = """\
TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;DENOM_SOCIAL;DT_COMPTC;TP_APLIC;TP_ATIVO;EMISSOR_LIGADO;TP_NEGOC;QT_POS_FINAL;VL_MERC_POS_FINAL;VL_CUSTO_POS_FINAL;DT_CONFID_APLIC;DS_ATIVO;PF_PJ_EMISSOR;CPF_CNPJ_EMISSOR;EMISSOR
CLASSES - FIF;00.017.024/0001-53;FIF RENDA FIXA;2026-07-31;Disponibilidades;Outros;;;0.000000;132846.13;;;Disponibilidade;;;
"""
CDA_PL = """\
TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;DENOM_SOCIAL;DT_COMPTC;VL_PATRIM_LIQ
CLASSES - FIF;00.017.024/0001-53;FIF RENDA FIXA;2026-07-31;1000000.00
"""


def _mock_cda(yyyymm: str, members: dict[str, str] | None) -> respx.Route:
    url = f"{CVM_BASE}/FI/DOC/CDA/DADOS/cda_fi_{yyyymm}.zip"
    if members is None:
        return respx.get(url).mock(return_value=httpx.Response(404))
    return respx.get(url).mock(return_value=httpx.Response(200, content=_zip(**members)))


def _cda_members(yyyymm: str) -> dict[str, str]:
    # Só 3 dos 8 blocos + PL, como num ZIP parcial: os blocos ausentes são pulados.
    return {
        f"cda_fi_BLC_1_{yyyymm}__csv": CDA_BLC_1,
        f"cda_fi_BLC_4_{yyyymm}__csv": CDA_BLC_4,
        f"cda_fi_BLC_8_{yyyymm}__csv": CDA_BLC_8,
        f"cda_fi_PL_{yyyymm}__csv": CDA_PL,
    }


@respx.mock
def test_carteira_merges_blocks_and_weights_by_net_assets() -> None:
    route = _mock_cda("202607", _cda_members("202607"))
    df = CVM().carteira("00.017.024/0001-53", month="2026-07")

    assert route.call_count == 1  # um download, vários membros
    assert list(df["asset"]) == ["LETRAS FINANCEIRAS DO TESOURO", "ITUB3", "Disponibilidade"]
    assert list(df["block"]) == [1, 4, 8]
    assert df["weight_pct"].tolist() == pytest.approx([56.715387, 30.0, 13.284613])
    lft = df.iloc[0]
    assert lft["isin"] == "BRSTNCLF1RH3"
    assert str(lft["maturity"].date()) == "2027-09-01"
    assert lft["quantity"] == 29
    assert set(df["cnpj"]) == {"00017024000153"}
    assert not any(c.startswith("_") for c in df.columns)


@respx.mock
def test_carteira_walks_back_when_fund_not_yet_filed() -> None:
    today = pd.Timestamp.today().to_period("M")
    _mock_cda(today.strftime("%Y%m"), None)  # mês corrente ainda sem ZIP
    prev = (today - 1).strftime("%Y%m")
    _mock_cda(prev, {f"cda_fi_BLC_1_{prev}__csv": CDA_BLC_1.replace("00.017.024", "00.000.000")})
    prev2 = (today - 2).strftime("%Y%m")
    _mock_cda(prev2, _cda_members(prev2))

    df = CVM().carteira("00017024000153")
    assert len(df) == 3

    with pytest.raises(DataNotFoundError):
        CVM().carteira("55.555.555/0001-55", month="2026-07")
