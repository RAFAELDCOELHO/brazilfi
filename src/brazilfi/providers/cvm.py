"""Provider CVM — dados abertos: fundos, cotas, carteiras (CDA), FII, DFP/ITR."""
from __future__ import annotations

import re
import zipfile
from datetime import date
from functools import reduce
from typing import Any

import pandas as pd

from brazilfi.core.cache import CACHE_ROOT, cached_download
from brazilfi.core.exceptions import DataNotFoundError

CVM_BASE = "https://dados.cvm.gov.br/dados"
# Com a Resolução CVM 175 o cadastro de fundos migrou de cad_fi.csv (hoje só
# legado, ~20 fundos ativos) para o registro fundo/classe/subclasse. A *classe*
# é quem tem CNPJ e cota — é ela que aparece no informe diário.
REGISTRO_URL = f"{CVM_BASE}/FI/CAD/DADOS/registro_fundo_classe.zip"
INF_DIARIO_URL = f"{CVM_BASE}/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_{{yyyymm}}.zip"
CAD_CIA_URL = f"{CVM_BASE}/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv"
# DFP (anual) e ITR (trimestral) têm o mesmo layout, só muda o prefixo.
DOC_URL = f"{CVM_BASE}/CIA_ABERTA/DOC/{{doc}}/DADOS/{{doc_lower}}_cia_aberta_{{year}}.zip"

# Informe mensal de FII (um ZIP por ano com geral/complemento/ativo_passivo) e
# composição de carteira dos fundos (CDA: um ZIP por mês, 8 blocos por tipo de ativo).
FII_URL = f"{CVM_BASE}/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_{{year}}.zip"
CDA_URL = f"{CVM_BASE}/FI/DOC/CDA/DADOS/cda_fi_{{yyyymm}}.zip"
FII_SECTIONS = {"geral", "complemento", "ativo_passivo"}
CDA_BLOCKS = range(1, 9)
CDA_LOOKBACK_MONTHS = 4  # o CDA sai com 1-2 meses de atraso

CACHE_DIR = CACHE_ROOT / "cvm"
ENCODING = "latin-1"  # a CVM serve tudo em ISO-8859-1, sem declarar charset
STATEMENTS = {"BPA", "BPP", "DRE", "DRA", "DFC_MD", "DFC_MI", "DMPL", "DVA"}

CLASS_COLS = {
    "ID_Registro_Fundo": "fund_id",
    "CNPJ_Classe": "cnpj",
    "Codigo_CVM": "cd_cvm",
    "Denominacao_Social": "name",
    "Tipo_Classe": "type",
    "Classificacao": "class",
    "Classificacao_Anbima": "anbima_class",
    "Situacao": "situation",
    "Data_Inicio": "start_date",
    "Forma_Condominio": "condominium",
    "Exclusivo": "exclusive",
    "Publico_Alvo": "target_audience",
    "Patrimonio_Liquido": "net_assets",
    "Data_Patrimonio_Liquido": "net_assets_date",
}
FUND_COLS = {
    "ID_Registro_Fundo": "fund_id",
    "CNPJ_Fundo": "fund_cnpj",
    "Administrador": "admin",
    "Gestor": "manager",
}
# Informe diário: até 2024 a coluna era CNPJ_FUNDO; com a Resolução CVM 175
# virou CNPJ_FUNDO_CLASSE (+ ID_SUBCLASSE). Aceitamos os dois.
QUOTA_COLS = {
    "CNPJ_FUNDO": "cnpj",
    "CNPJ_FUNDO_CLASSE": "cnpj",
    "ID_SUBCLASSE": "subclass",
    "DT_COMPTC": "date",
    "VL_QUOTA": "quota",
    "VL_PATRIM_LIQ": "net_assets",
    "VL_TOTAL": "total_assets",
    "CAPTC_DIA": "inflow",
    "RESG_DIA": "outflow",
    "NR_COTST": "shareholders",
}
# Colunas comuns aos 8 blocos do CDA + as específicas que identificam o ativo.
CDA_COLS = {
    "CNPJ_FUNDO_CLASSE": "cnpj",
    "DENOM_SOCIAL": "fund",
    "DT_COMPTC": "date",
    "TP_APLIC": "application",
    "TP_ATIVO": "asset_type",
    "EMISSOR_LIGADO": "related_issuer",
    "TP_NEGOC": "trading",
    "QT_POS_FINAL": "quantity",
    "VL_MERC_POS_FINAL": "market_value",
    "VL_CUSTO_POS_FINAL": "cost_value",
    "DT_CONFID_APLIC": "confidential_until",
    "CD_ISIN": "isin",
    "DT_VENC": "maturity",
    "AG_RISCO": "rating_agency",
    "GRAU_RISCO": "rating",
    # candidatos a `asset` (na ordem de preferência) e a `issuer`
    "CD_ATIVO": "_cd_ativo",
    "TP_TITPUB": "_tp_titpub",
    "NM_FUNDO_CLASSE_SUBCLASSE_COTA": "_nm_fundo_cota",
    "DS_ATIVO": "_ds_ativo",
    "DS_SWAP": "_ds_swap",
    "DS_ATIVO_EXTERIOR": "_ds_ativo_exterior",
    "CD_ATIVO_BV_MERC": "_cd_ativo_bv",
    "EMISSOR": "_emissor",
    "CNPJ_FUNDO_CLASSE_COTA": "_cnpj_fundo_cota",
    "CPF_CNPJ_EMISSOR": "_cnpj_emissor",
    "CNPJ_EMISSOR": "_cnpj_emissor2",
}
CDA_ASSET_CANDIDATES = [
    "_cd_ativo", "_tp_titpub", "_nm_fundo_cota", "_ds_ativo", "_ds_swap",
    "_ds_ativo_exterior", "_cd_ativo_bv", "_emissor",
]
CDA_ISSUER_CANDIDATES = ["_emissor", "_cnpj_fundo_cota", "_cnpj_emissor", "_cnpj_emissor2"]

COMPANY_COLS = {
    "CNPJ_CIA": "cnpj",
    "DENOM_SOCIAL": "name",
    "DENOM_COMERC": "trade_name",
    "CD_CVM": "cd_cvm",
    "SETOR_ATIV": "sector",
    "CATEG_REG": "category",
    "SIT": "situation",
    "SIT_EMISSOR": "issuer_status",
}


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value))


class CVM:
    """
    Dados abertos da CVM. Tudo público, sem token.

    Exemplos:
        >>> cvm = CVM()
        >>> cvm.fundos(search="verde")                       # cadastro de fundos
        >>> cvm.cotas("00.017.024/0001-53")                  # cota diária, últimos 3 meses
        >>> cvm.carteira("00.017.024/0001-53")               # composição da carteira (CDA)
        >>> cvm.fii(2026, cnpj="00.332.266/0001-31")         # informe mensal de FII
        >>> cvm.companhias(search="petrobras")               # cadastro de cias abertas
        >>> cvm.dfp(1023, 2025, statement="DRE")             # DRE consolidada do BB
        >>> cvm.itr("33.000.167/0001-01", 2026, "BPA")       # balanço trimestral
    """

    # ---------- Fundos ----------

    def fundos(
        self,
        search: str | None = None,
        cnpj: str | None = None,
        active: bool = True,
    ) -> pd.DataFrame:
        """
        Cadastro de classes de fundos (registro CVM 175, ~7 MB zipado, cache de 1 dia).

        Uma linha por classe (o CNPJ que tem cota); `fund_cnpj`, `admin` e
        `manager` vêm do fundo-mãe. CNPJs saem só com dígitos.

        Args:
            search: filtro case-insensitive na razão social.
            cnpj: filtra uma classe (com ou sem pontuação).
            active: só classes "Em Funcionamento Normal".
        """
        classes = self._csv(REGISTRO_URL, "registro_fundo_classe.zip", CLASS_COLS,
                            member="registro_classe.csv")
        funds = self._csv(REGISTRO_URL, "registro_fundo_classe.zip", FUND_COLS,
                          member="registro_fundo.csv")
        df = classes.merge(funds, on="fund_id", how="left").drop(columns="fund_id")
        if active:
            df = df[df["situation"] == "Em Funcionamento Normal"]
        if search:
            df = df[df["name"].str.contains(search, case=False, na=False, regex=False)]
        if cnpj:
            df = df[df["cnpj"].map(_digits) == _digits(cnpj)]
        if df.empty:
            raise DataNotFoundError(f"Nenhum fundo para search={search!r} cnpj={cnpj!r}")
        df["net_assets"] = pd.to_numeric(df["net_assets"], errors="coerce")
        df["cd_cvm"] = pd.to_numeric(df["cd_cvm"], errors="coerce").astype("Int64")
        for col in ("start_date", "net_assets_date"):
            df[col] = pd.to_datetime(df[col], errors="coerce")
        return df.reset_index(drop=True)

    def cotas(
        self,
        cnpj: str,
        start: str | date | None = None,
        end: str | date | None = None,
    ) -> pd.DataFrame:
        """
        Cota diária, PL, captação, resgate e cotistas de um fundo (informe diário).

        Um arquivo por mês (~10 MB zipado). Sem `start`, cobre os últimos 3 meses.
        Só há arquivos mensais a partir de 2021-01.
        """
        end_ts = pd.Timestamp(end) if end else pd.Timestamp(date.today())
        if start:
            start_ts = pd.Timestamp(start)
        else:
            start_ts = (end_ts - pd.DateOffset(months=2)).replace(day=1)
        if start_ts > end_ts:
            raise ValueError("start deve ser <= end")
        digits = _digits(cnpj)
        recent = pd.Timestamp(date.today()).to_period("M") - 1

        frames: list[pd.DataFrame] = []
        for period in pd.period_range(start_ts, end_ts, freq="M"):
            yyyymm = period.strftime("%Y%m")
            try:
                df = self._csv(
                    INF_DIARIO_URL.format(yyyymm=yyyymm),
                    f"inf_diario_fi_{yyyymm}.zip",
                    QUOTA_COLS,
                    max_age_days=1 if period >= recent else None,
                )
            except DataNotFoundError:
                continue  # mês ainda não publicado (ou anterior a 2021)
            frames.append(df[df["cnpj"].map(_digits) == digits])

        if not frames or all(f.empty for f in frames):
            raise DataNotFoundError(
                f"Sem informe diário para {cnpj} entre {start_ts:%Y-%m} e {end_ts:%Y-%m}"
            )
        df = pd.concat(frames)
        df["cnpj"] = df["cnpj"].map(_digits)
        df["date"] = pd.to_datetime(df["date"])
        df = df[(df["date"] >= start_ts) & (df["date"] <= end_ts)]
        for col in ("quota", "net_assets", "total_assets", "inflow", "outflow", "shareholders"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.set_index("date").sort_index()

    def carteira(self, cnpj: str, month: str | date | None = None) -> pd.DataFrame:
        """
        Composição da carteira de um fundo (CDA), uma linha por ativo.

        Junta os 8 blocos do CDA (títulos públicos, cotas de fundos, swaps, ações e
        derivativos, renda fixa privada, depósitos, exterior, demais) numa tabela só,
        com `asset`/`issuer` normalizados e `weight_pct` sobre o PL do mês. Posições
        confidenciais só aparecem depois de `confidential_until`.

        Args:
            cnpj: CNPJ da classe do fundo.
            month: mês de referência ("2026-07", date ou "YYYYMM"). Sem `month`, o
                mais recente publicado (o CDA sai com 1-2 meses de atraso).

        Cada ZIP mensal tem ~16 MB (180 MB abertos) e fica em cache local.
        """
        if month is not None:
            return self._carteira_on(cnpj, pd.Period(month, freq="M"))
        period = pd.Timestamp(date.today()).to_period("M")
        # Recua também quando o mês existe mas o fundo ainda não entregou o CDA
        # (o ZIP do mês corrente começa com poucos fundos e cresce ao longo do mês).
        for _ in range(CDA_LOOKBACK_MONTHS):
            try:
                return self._carteira_on(cnpj, period)
            except DataNotFoundError:
                period -= 1
        raise DataNotFoundError(
            f"Nenhum CDA com {cnpj} nos últimos {CDA_LOOKBACK_MONTHS} meses"
        )

    def _carteira_on(self, cnpj: str, period: pd.Period) -> pd.DataFrame:
        yyyymm = period.strftime("%Y%m")
        recent = pd.Timestamp(date.today()).to_period("M") - 3
        digits = _digits(cnpj)
        frames: list[pd.DataFrame] = []
        for block in CDA_BLOCKS:
            try:
                df = self._csv(
                    CDA_URL.format(yyyymm=yyyymm),
                    f"cda_fi_{yyyymm}.zip",
                    CDA_COLS,
                    member=f"cda_fi_BLC_{block}_{yyyymm}.csv",
                    max_age_days=1 if period >= recent else None,
                )
            except DataNotFoundError:
                continue  # bloco sem nenhum ativo no mês (ZIP parcial) não vem no arquivo
            df = df[df["cnpj"].map(_digits) == digits].copy()
            if df.empty:
                continue
            df["block"] = block
            frames.append(df)
        if not frames:
            raise DataNotFoundError(f"CDA {yyyymm}: nenhuma posição para {cnpj}")

        df = pd.concat(frames, ignore_index=True)
        df["asset"] = self._coalesce(df, CDA_ASSET_CANDIDATES)
        df["issuer"] = self._coalesce(df, CDA_ISSUER_CANDIDATES)
        for col in ("asset", "issuer"):
            df[col] = df[col].astype(object).where(df[col].notna(), None)  # NaN → None
        df = df.drop(columns=[c for c in df.columns if c.startswith("_")])
        df["cnpj"] = df["cnpj"].map(_digits)
        for col in ("date", "maturity", "confidential_until"):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
        for col in ("quantity", "market_value", "cost_value"):
            df[col] = pd.to_numeric(df[col], errors="coerce")

        net_assets = float("nan")
        try:
            pl = self._csv(
                CDA_URL.format(yyyymm=yyyymm),
                f"cda_fi_{yyyymm}.zip",
                {"CNPJ_FUNDO_CLASSE": "cnpj", "VL_PATRIM_LIQ": "net_assets"},
                member=f"cda_fi_PL_{yyyymm}.csv",
                max_age_days=1 if period >= recent else None,
            )
            pl = pl[pl["cnpj"].map(_digits) == digits]
            if len(pl):
                net_assets = float(pl["net_assets"].iloc[0])
        except DataNotFoundError:
            pass
        df["weight_pct"] = df["market_value"] / net_assets * 100

        front = ["cnpj", "fund", "date", "block", "application", "asset_type", "asset", "issuer"]
        rest = [c for c in df.columns if c not in front]
        return (
            df[front + rest]
            .sort_values("market_value", ascending=False)
            .reset_index(drop=True)
        )

    @staticmethod
    def _coalesce(df: pd.DataFrame, candidates: list[str]) -> pd.Series:
        """Primeiro valor não-vazio entre as colunas candidatas presentes."""
        present = [df[c] for c in candidates if c in df.columns]
        if not present:
            return pd.Series([None] * len(df), index=df.index, dtype=object)
        return reduce(lambda a, b: a.where(a.notna() & (a != ""), b), present)

    # ---------- FII ----------

    def fii(
        self,
        year: int,
        cnpj: str | None = None,
        section: str = "complemento",
    ) -> pd.DataFrame:
        """
        Informe mensal de FII (um ZIP por ano).

        Args:
            year: ano de referência.
            cnpj: filtra um fundo; sem `cnpj`, todos os FIIs do ano.
            section: "complemento" (PL, cota patrimonial, cotistas, rentabilidade,
                dividend yield — default), "ativo_passivo" (composição do balanço)
                ou "geral" (cadastro, mandato, segmento, administrador).

        Só a última versão de cada informe é mantida. Colunas ficam com o nome da
        CVM em minúsculas (`patrimonio_liquido`, `percentual_dividend_yield_mes`...).
        """
        if section not in FII_SECTIONS:
            raise ValueError(f"section inválida. Use uma de: {sorted(FII_SECTIONS)}")
        df = self._csv(
            FII_URL.format(year=year),
            f"inf_mensal_fii_{year}.zip",
            member=f"inf_mensal_fii_{section}_{year}.csv",
            max_age_days=1 if year >= date.today().year - 1 else None,
        )
        df = df.rename(
            columns={"CNPJ_Fundo_Classe": "cnpj", "Data_Referencia": "date", "Versao": "version"}
        ).rename(columns=str.lower)
        df["cnpj"] = df["cnpj"].map(_digits)
        if cnpj:
            df = df[df["cnpj"] == _digits(cnpj)]
        if df.empty:
            raise DataNotFoundError(f"Informe de FII {year}: nada para cnpj={cnpj!r}")
        df["version"] = df["version"].astype(int)
        df = df[df["version"] == df.groupby(["cnpj", "date"])["version"].transform("max")]
        df["date"] = pd.to_datetime(df["date"])
        if section != "geral":
            for col in df.columns:
                if col.startswith("data_"):
                    df[col] = pd.to_datetime(df[col], errors="coerce")
                elif col not in ("cnpj", "date", "version"):
                    df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.sort_values(["cnpj", "date"]).reset_index(drop=True)

    # ---------- Companhias abertas ----------

    def companhias(self, search: str | None = None, active: bool = True) -> pd.DataFrame:
        """Cadastro de companhias abertas (`cad_cia_aberta.csv`, cache de 1 dia)."""
        df = self._csv(CAD_CIA_URL, "cad_cia_aberta.csv", COMPANY_COLS)
        # O cadastro repete a companhia (um registro por endereço/categoria histórica).
        df = df.drop_duplicates("cnpj")
        df["cnpj"] = df["cnpj"].map(_digits)
        if active:
            df = df[df["situation"] == "ATIVO"]
        if search:
            mask = df["name"].str.contains(search, case=False, na=False, regex=False) | df[
                "trade_name"
            ].str.contains(search, case=False, na=False, regex=False)
            df = df[mask]
        if df.empty:
            raise DataNotFoundError(f"Nenhuma companhia para search={search!r}")
        df["cd_cvm"] = df["cd_cvm"].astype(int)
        return df.reset_index(drop=True)

    def dfp(
        self,
        company: str | int,
        year: int,
        statement: str = "DRE",
        consolidated: bool = True,
        last_only: bool = True,
    ) -> pd.DataFrame:
        """
        Demonstração financeira anual (DFP) de uma companhia.

        Args:
            company: CNPJ (str, com ou sem pontuação) ou código CVM (int).
            year: exercício de referência (arquivo `dfp_cia_aberta_{year}.zip`).
            statement: BPA, BPP, DRE, DRA, DFC_MD, DFC_MI, DMPL ou DVA.
            consolidated: consolidado (True) ou individual (False).
            last_only: só o exercício corrente ("ÚLTIMO"); False traz também o
                comparativo ("PENÚLTIMO").

        `value` já vem em reais (a CVM publica em milhares; `ESCALA_MOEDA` é aplicada).
        Se a companhia reapresentou a demonstração, só a versão mais recente é mantida.
        """
        return self._statement("DFP", company, year, statement, consolidated, last_only)

    def itr(
        self,
        company: str | int,
        year: int,
        statement: str = "DRE",
        consolidated: bool = True,
        last_only: bool = True,
    ) -> pd.DataFrame:
        """
        Informações trimestrais (ITR) de uma companhia — mesmo layout de `dfp()`.

        A DRE trimestral traz o trimestre isolado e o acumulado no ano na mesma
        tabela; distinga pelas colunas `period_start`/`period_end`.
        """
        return self._statement("ITR", company, year, statement, consolidated, last_only)

    # ---------- Internals ----------

    def _csv(
        self,
        url: str,
        filename: str,
        columns: dict[str, str] | None = None,
        member: str | None = None,
        max_age_days: float | None = 1,
    ) -> pd.DataFrame:
        """
        Baixa (com cache) um CSV da CVM — solto, ZIP de um CSV, ou `member` de um ZIP
        com vários — e devolve as colunas mapeadas em `columns` (todas, se None).
        """
        path = cached_download(url, CACHE_DIR / filename, max_age_days=max_age_days)
        kwargs: dict[str, Any] = {"sep": ";", "encoding": ENCODING, "dtype": str}
        if columns:
            kwargs["usecols"] = lambda c: c in columns
        df: pd.DataFrame
        if member is None:
            df = pd.read_csv(path, **kwargs)
        else:
            with zipfile.ZipFile(path) as zf:
                if member not in zf.namelist():
                    raise DataNotFoundError(f"{filename} não contém {member}")
                with zf.open(member) as fh:
                    df = pd.read_csv(fh, **kwargs)
        if columns:
            df = df.rename(columns=columns)
        return df

    def _statement(
        self,
        doc: str,
        company: str | int,
        year: int,
        statement: str,
        consolidated: bool,
        last_only: bool,
    ) -> pd.DataFrame:
        statement = statement.upper()
        if statement not in STATEMENTS:
            raise ValueError(f"statement inválido. Use um de: {sorted(STATEMENTS)}")
        doc_lower = doc.lower()
        scope = "con" if consolidated else "ind"
        raw = self._csv(
            DOC_URL.format(doc=doc, doc_lower=doc_lower, year=year),
            f"{doc_lower}_cia_aberta_{year}.zip",
            member=f"{doc_lower}_cia_aberta_{statement}_{scope}_{year}.csv",
            # DFP/ITR recentes ainda recebem reapresentações; anos antigos são estáveis.
            max_age_days=1 if year >= date.today().year - 1 else None,
        )

        if isinstance(company, int):
            mask = raw["CD_CVM"].astype(int) == company
        else:
            mask = raw["CNPJ_CIA"].map(_digits) == _digits(company)
        df = raw[mask]
        if df.empty:
            raise DataNotFoundError(f"{doc} {statement} {year}: nada para company={company!r}")

        # Reapresentações: fica só a maior VERSAO de cada data de referência.
        version = df["VERSAO"].astype(int)
        df = df[version == version.groupby(df["DT_REFER"]).transform("max")]
        if last_only:
            df = df[df["ORDEM_EXERC"] == "ÚLTIMO"]

        scale = df["ESCALA_MOEDA"].map({"MIL": 1000, "UNIDADE": 1}).fillna(1)
        out = pd.DataFrame(
            {
                "cnpj": df["CNPJ_CIA"],
                "company": df["DENOM_CIA"],
                "cd_cvm": df["CD_CVM"].astype(int),
                "reference_date": pd.to_datetime(df["DT_REFER"]),
                "period_start": (
                    pd.to_datetime(df["DT_INI_EXERC"]) if "DT_INI_EXERC" in df.columns else pd.NaT
                ),
                "period_end": pd.to_datetime(df["DT_FIM_EXERC"]),
                "order": df["ORDEM_EXERC"],
                "account": df["CD_CONTA"],
                "description": df["DS_CONTA"],
                "value": pd.to_numeric(df["VL_CONTA"]) * scale,
                "fixed": df["ST_CONTA_FIXA"] == "S",
            }
        )
        return out.sort_values(["period_end", "account"]).reset_index(drop=True)
