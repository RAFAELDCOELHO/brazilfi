"""Testes do provider CVM (dados abertos) com respx e cache redirecionado para tmp_path."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import httpx
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
