"""Provider IBGE — API SIDRA v3 (séries agregadas)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from brazilfi.core.exceptions import DataNotFoundError
from brazilfi.core.http_client import HttpClient
from brazilfi.core.models import SeriesPoint, TimeSeries

# Agregados SIDRA mais usados
AGREGADOS = {
    "pib_trimestral": {
        "agregado": 1620,
        "variavel": 583,
        "classificacao": "11255[90707]",
        "name": "PIB a preços de mercado (valores correntes)",
        "unit": "milhões de BRL",
    },
    "pib_volume": {
        "agregado": 1620,
        "variavel": 584,
        "classificacao": "11255[90707]",
        "name": "PIB — variação de volume",
        "unit": "índice",
    },
    "desemprego": {
        "agregado": 4099,
        "variavel": 4099,
        "name": "Taxa de desocupação (PNAD Contínua)",
        "unit": "%",
    },
    "rendimento_medio": {
        "agregado": 4099,
        "variavel": 5933,
        "name": "Rendimento médio real (PNAD Contínua)",
        "unit": "BRL",
    },
    "ipca_mensal": {
        "agregado": 7060,
        "variavel": 63,
        "name": "IPCA — variação mensal",
        "unit": "%",
    },
    "ipca_indice": {
        "agregado": 7060,
        "variavel": 2266,
        "name": "IPCA — número-índice",
        "unit": "índice (dez/1993=100)",
    },
    "populacao_estimada": {
        "agregado": 6579,
        "variavel": 9324,
        "name": "População residente estimada",
        "unit": "habitantes",
    },
}


class IBGE:
    """
    Wrapper para API SIDRA v3 do IBGE.

    Exemplos:
        >>> ibge = IBGE()
        >>> pib = ibge.pib(last=8)                  # últimos 8 trimestres
        >>> ipca = ibge.ipca(last=12)               # últimos 12 meses
        >>> des = ibge.desemprego(last=4)           # últimas 4 medições PNAD
        >>> df = ibge.agregado(1620, 583, last=4)   # acesso genérico
    """

    BASE = "https://servicodados.ibge.gov.br/api/v3/agregados"

    def __init__(self, timeout: float = 30.0) -> None:
        self.client = HttpClient(base_url=self.BASE, timeout=timeout)

    # ---------- Convenience ----------

    def pib(self, last: int = 8, volume: bool = False) -> TimeSeries:
        """PIB trimestral. `volume=True` retorna variação de volume."""
        key = "pib_volume" if volume else "pib_trimestral"
        return self._get_named(key, last=last)

    def desemprego(self, last: int = 4) -> TimeSeries:
        """Taxa de desocupação (PNAD Contínua, trimestral móvel)."""
        return self._get_named("desemprego", last=last)

    def ipca(self, last: int = 12, indice: bool = False) -> TimeSeries:
        """IPCA mensal. `indice=True` retorna número-índice em vez da variação."""
        key = "ipca_indice" if indice else "ipca_mensal"
        return self._get_named(key, last=last)

    def populacao(self, last: int = 5) -> TimeSeries:
        """População residente estimada (anual)."""
        return self._get_named("populacao_estimada", last=last)

    def agregado(
        self,
        agregado: int,
        variavel: int,
        last: int | None = None,
        periodos: str | None = None,
        localidade: str = "N1[all]",
        classificacao: str | None = None,
        name: str | None = None,
        unit: str = "",
    ) -> TimeSeries:
        """
        Acesso genérico a qualquer agregado SIDRA.

        Args:
            agregado: código do agregado (ex: 1620 = PIB trimestral)
            variavel: código da variável
            last: últimos N períodos (usa `-N` no endpoint)
            periodos: alternativa a `last` — formato "202401-202412" ou "202401"
            localidade: padrão N1[all] (Brasil inteiro)
            name/unit: opcional, sobrescreve metadados
        """
        if last is None and periodos is None:
            last = 12
        periodo_str = f"-{last}" if last is not None else periodos

        path = f"/{agregado}/periodos/{periodo_str}/variaveis/{variavel}"
        params: dict[str, str] = {"localidades": localidade}
        if classificacao:
            params["classificacao"] = classificacao
        data = self.client.get(path, params=params)

        if not data:
            raise DataNotFoundError(
                f"SIDRA agregado={agregado} var={variavel} sem dados"
            )

        variavel_info = data[0]
        points = self._parse_sidra(variavel_info)

        return TimeSeries(
            code=f"{agregado}.{variavel}",
            name=name or variavel_info.get("variavel", f"SIDRA {agregado}"),
            unit=unit or variavel_info.get("unidade", ""),
            source="ibge",
            points=points,
        )

    # ---------- Internals ----------

    def _get_named(self, key: str, last: int) -> TimeSeries:
        cfg = AGREGADOS[key]
        classificacao = cfg.get("classificacao")
        return self.agregado(
            agregado=int(cfg["agregado"]),
            variavel=int(cfg["variavel"]),
            last=last,
            classificacao=str(classificacao) if classificacao else None,
            name=str(cfg["name"]),
            unit=str(cfg["unit"]),
        )

    @staticmethod
    def _parse_sidra(variavel_block: dict[str, Any]) -> list[SeriesPoint]:
        """Extrai pontos de um bloco SIDRA (estrutura aninhada horrível)."""
        points: list[SeriesPoint] = []
        resultados = variavel_block.get("resultados", [])
        for r in resultados:
            for serie_item in r.get("series", []):
                serie = serie_item.get("serie", {})
                for periodo, valor in serie.items():
                    if valor in (None, "...", "..", "-", "X", "x", ""):
                        continue
                    try:
                        dt = IBGE._parse_period(periodo)
                        val = Decimal(str(valor).replace(",", "."))
                        points.append(SeriesPoint(date=dt, value=val))
                    except (ValueError, TypeError, InvalidOperation):
                        continue
        # Ordena cronologicamente
        points.sort(key=lambda p: p.date)
        return points

    @staticmethod
    def _parse_period(p: str) -> date:
        """
        Converte períodos SIDRA para date:
          "2024"        → 2024-01-01
          "202404"      → 2024-04-01
          "2024.I"      → 2024-01-01 (trimestre)
          "2024.II"     → 2024-04-01
          "2024.III"    → 2024-07-01
          "2024.IV"     → 2024-10-01
        """
        if "." in p:
            year_str, tri = p.split(".")
            tri_map = {"I": 1, "II": 4, "III": 7, "IV": 10}
            month = tri_map.get(tri, 1)
            return date(int(year_str), month, 1)
        if len(p) == 6:
            return date(int(p[:4]), int(p[4:6]), 1)
        if len(p) == 4:
            return date(int(p), 1, 1)
        raise ValueError(f"Período SIDRA não reconhecido: {p}")
