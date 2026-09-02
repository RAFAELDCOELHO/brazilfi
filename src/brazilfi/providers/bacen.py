"""Provider do Banco Central do Brasil (SGS + expectativas Focus via Olinda)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import quote

import pandas as pd

from brazilfi.core.exceptions import DataNotFoundError
from brazilfi.core.http_client import HttpClient
from brazilfi.core.models import SeriesPoint, TimeSeries

# Códigos SGS mais usados
SGS_SERIES = {
    "selic_diaria": (11, "SELIC diária", "%"),
    "selic_meta": (432, "Meta SELIC (Copom)", "%"),
    "cdi": (12, "CDI diário", "%"),
    "ipca": (433, "IPCA mensal", "%"),
    "ipca_acum_12m": (13522, "IPCA acumulado 12 meses", "%"),
    "igpm": (189, "IGP-M mensal", "%"),
    "dolar_venda": (1, "Dólar comercial (venda)", "BRL"),
    "euro_venda": (21619, "Euro (venda)", "BRL"),
}

# Expectativas de mercado (boletim Focus), API OData do Olinda.
FOCUS_BASE = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata"
FOCUS_DATASETS = {
    "anual": "ExpectativasMercadoAnuais",
    "mensal": "ExpectativaMercadoMensais",
    "trimestral": "ExpectativasMercadoTrimestrais",
    "selic": "ExpectativasMercadoSelic",
    "inflacao_12m": "ExpectativasMercadoInflacao12Meses",
    "top5_anual": "ExpectativasMercadoTop5Anuais",
    "top5_mensal": "ExpectativasMercadoTop5Mensais",
    "top5_selic": "ExpectativasMercadoTop5Selic",
}
SAFE_CHARS = "'"  # aspas simples do OData ficam legíveis na URL
FOCUS_COLS = {
    "Indicador": "indicator",
    "IndicadorDetalhe": "detail",
    "Data": "date",
    "DataReferencia": "reference",
    "Reuniao": "meeting",
    "Suavizada": "smoothed",
    "Media": "mean",
    "Mediana": "median",
    "DesvioPadrao": "std",
    "Minimo": "min",
    "Maximo": "max",
    "numeroRespondentes": "respondents",
    "baseCalculo": "base",
}


class Bacen:
    """
    Wrapper para APIs do Banco Central (SGS — Sistema Gerenciador de Séries).

    Exemplos:
        >>> bc = Bacen()
        >>> df = bc.selic(last=30).to_dataframe()
        >>> df = bc.ipca(start="2023-01-01").to_dataframe()
        >>> df = bc.series(11, last=10).to_dataframe()  # código SGS genérico
        >>> df = bc.focus("IPCA")                         # expectativas Focus (anual)
        >>> df = bc.focus("Selic", freq="selic")          # por reunião do Copom
    """

    SGS_BASE = "https://api.bcb.gov.br/dados/serie"

    def __init__(self, timeout: float = 30.0) -> None:
        self.client = HttpClient(base_url=self.SGS_BASE, timeout=timeout)

    # ---------- Convenience methods ----------

    def selic(
        self,
        start: str | date | None = None,
        end: str | date | None = None,
        last: int | None = None,
        meta: bool = False,
    ) -> TimeSeries:
        """SELIC. Use `meta=True` para a meta Copom em vez da diária."""
        key = "selic_meta" if meta else "selic_diaria"
        return self._get_named(key, start=start, end=end, last=last)

    def cdi(
        self,
        start: str | date | None = None,
        end: str | date | None = None,
        last: int | None = None,
    ) -> TimeSeries:
        return self._get_named("cdi", start=start, end=end, last=last)

    def ipca(
        self,
        start: str | date | None = None,
        end: str | date | None = None,
        last: int | None = None,
        acum_12m: bool = False,
    ) -> TimeSeries:
        key = "ipca_acum_12m" if acum_12m else "ipca"
        return self._get_named(key, start=start, end=end, last=last)

    def igpm(
        self,
        start: str | date | None = None,
        end: str | date | None = None,
        last: int | None = None,
    ) -> TimeSeries:
        return self._get_named("igpm", start=start, end=end, last=last)

    def dolar(
        self,
        start: str | date | None = None,
        end: str | date | None = None,
        last: int | None = None,
    ) -> TimeSeries:
        return self._get_named("dolar_venda", start=start, end=end, last=last)

    def series(
        self,
        code: int,
        start: str | date | None = None,
        end: str | date | None = None,
        last: int | None = None,
        name: str | None = None,
        unit: str = "",
    ) -> TimeSeries:
        """Acesso genérico a qualquer série SGS pelo código."""
        data = self._fetch_sgs(code, start=start, end=end, last=last)
        points = self._parse_sgs(data)
        return TimeSeries(
            code=str(code),
            name=name or f"SGS {code}",
            unit=unit,
            source="bacen",
            points=points,
        )

    # ---------- Focus ----------

    def focus(
        self,
        indicador: str = "IPCA",
        freq: str = "anual",
        start: str | date | None = None,
        end: str | date | None = None,
        base: int | None = 0,
        top: int = 10000,
    ) -> pd.DataFrame:
        """
        Expectativas de mercado do boletim Focus (Olinda/OData).

        Args:
            indicador: "IPCA", "Selic", "Câmbio", "PIB Total", "IGP-M"... (como no Focus).
            freq: "anual" (default), "mensal", "trimestral", "selic" (por reunião do
                Copom), "inflacao_12m", "top5_anual", "top5_mensal", "top5_selic".
            start/end: janela da data de coleta; default últimos 90 dias.
            base: 0 = todos os respondentes dos últimos 30 dias (default), 1 = só os
                dos últimos 5 dias, None = ambos.
            top: máximo de linhas.

        Uma linha por (data de coleta, referência). `reference` é o ano, "MM/YYYY"
        ou a reunião do Copom conforme `freq`.
        """
        if freq not in FOCUS_DATASETS:
            raise ValueError(f"freq inválida. Use uma de: {sorted(FOCUS_DATASETS)}")
        today = date.today()
        start_ = self._iso(start) if start else (today - timedelta(days=90)).isoformat()
        filters = [f"Indicador eq '{indicador}'", f"Data ge '{start_}'"]
        if end:
            filters.append(f"Data le '{self._iso(end)}'")
        if base is not None:
            filters.append(f"baseCalculo eq {base}")
        # O Olinda não aceita "+" como espaço (que é como o httpx codifica params),
        # então a query vai montada à mão com %20.
        options = {
            "filter": " and ".join(filters),
            "orderby": "Data asc",
            "top": top,
            "format": "json",
        }
        query = "&".join(f"${k}={quote(str(v), safe=SAFE_CHARS)}" for k, v in options.items())
        data = self.client.get(f"{FOCUS_BASE}/{FOCUS_DATASETS[freq]}?{query}")
        rows = data.get("value", []) if isinstance(data, dict) else []
        if not rows:
            raise DataNotFoundError(f"Focus sem dados para {indicador!r} ({freq}) desde {start_}")
        df = pd.DataFrame(rows).rename(columns=FOCUS_COLS)
        df["date"] = pd.to_datetime(df["date"])
        return df.reset_index(drop=True)

    # ---------- Internals ----------

    @staticmethod
    def _iso(d: str | date) -> str:
        return d if isinstance(d, str) else d.isoformat()

    def _get_named(
        self,
        key: str,
        start: str | date | None,
        end: str | date | None,
        last: int | None,
    ) -> TimeSeries:
        code, name, unit = SGS_SERIES[key]
        data = self._fetch_sgs(code, start=start, end=end, last=last)
        points = self._parse_sgs(data)
        return TimeSeries(
            code=str(code), name=name, unit=unit, source="bacen", points=points
        )

    def _fetch_sgs(
        self,
        code: int,
        start: str | date | None,
        end: str | date | None,
        last: int | None,
    ) -> list[dict[str, Any]]:
        # Endpoint: /bcdata.sgs.{code}/dados?formato=json&dataInicial=&dataFinal=
        # Ou: /bcdata.sgs.{code}/dados/ultimos/{N}
        if last is not None:
            path = f"bcdata.sgs.{code}/dados/ultimos/{last}"
            params: dict[str, Any] = {"formato": "json"}
        else:
            path = f"bcdata.sgs.{code}/dados"
            params = {"formato": "json"}
            if start:
                params["dataInicial"] = self._fmt_date(start)
            if end:
                params["dataFinal"] = self._fmt_date(end)
            if not start and not end:
                # padrão: últimos 90 dias
                today = date.today()
                params["dataInicial"] = self._fmt_date(today - timedelta(days=90))
                params["dataFinal"] = self._fmt_date(today)

        data: list[dict[str, Any]] = self.client.get(path, params=params)
        if not data:
            raise DataNotFoundError(f"Série SGS {code} sem dados no período")
        return data

    @staticmethod
    def _parse_sgs(data: list[dict[str, Any]]) -> list[SeriesPoint]:
        points: list[SeriesPoint] = []
        for row in data:
            # Formato: {"data": "DD/MM/YYYY", "valor": "0.12"}
            dt = datetime.strptime(row["data"], "%d/%m/%Y").date()
            val = Decimal(str(row["valor"]))
            points.append(SeriesPoint(date=dt, value=val))
        return points

    @staticmethod
    def _fmt_date(d: str | date) -> str:
        if isinstance(d, str):
            # aceita "YYYY-MM-DD" e converte para "DD/MM/YYYY"
            d = datetime.strptime(d, "%Y-%m-%d").date()
        return d.strftime("%d/%m/%Y")
