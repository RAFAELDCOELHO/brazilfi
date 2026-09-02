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

# Níveis territoriais servidos por cada agregado, conforme
# GET /agregados/<agregado>/metadados → nivelTerritorial.Administrativo
NIVEIS_TERRITORIAIS: dict[int, tuple[str, ...]] = {
    # Contas Nacionais Trimestrais: só Brasil
    1620: ("N1",),
    # PNAD Contínua: Brasil, grandes regiões, UF, município, RM e RIDE
    4099: ("N1", "N2", "N3", "N6", "N7", "N14"),
    # IPCA: Brasil, municípios e regiões metropolitanas da amostra — não há UF
    7060: ("N1", "N6", "N7"),
    # Estimativas da população: Brasil, grandes regiões, UF e município
    6579: ("N1", "N2", "N3", "N6"),
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
        """
        PIB trimestral. `volume=True` retorna variação de volume.

        Sem `localidade`: o SIDRA só serve o agregado 1620 em N1 (Brasil).
        """
        key = "pib_volume" if volume else "pib_trimestral"
        return self._get_named(key, last=last)

    def desemprego(self, last: int = 4, localidade: str = "N1[all]") -> TimeSeries:
        """
        Taxa de desocupação (PNAD Contínua, trimestral móvel).

        `localidade` aceita N1, N2, N3 (UF), N6 (município), N7 e N14.
        Ex: `desemprego(localidade="N3[35]")` → São Paulo (UF).
        """
        return self._get_named("desemprego", last=last, localidade=localidade)

    def ipca(
        self, last: int = 12, indice: bool = False, localidade: str = "N1[all]"
    ) -> TimeSeries:
        """
        IPCA mensal. `indice=True` retorna número-índice em vez da variação.

        `localidade` aceita N1, N6 (município) e N7 (região metropolitana) — o
        IPCA é apurado por amostra de municípios/RMs, então **não existe nível
        de UF (N3)**. Ex: `ipca(localidade="N6[3550308]")` → São Paulo-SP.
        """
        key = "ipca_indice" if indice else "ipca_mensal"
        return self._get_named(key, last=last, localidade=localidade)

    def populacao(self, last: int = 5, localidade: str = "N1[all]") -> TimeSeries:
        """
        População residente estimada (anual).

        `localidade` aceita N1, N2, N3 (UF) e N6 (município).
        Ex: `populacao(localidade="N6[3550308]")` → São Paulo-SP.
        """
        return self._get_named("populacao_estimada", last=last, localidade=localidade)

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

        Raises:
            ValueError: se o agregado não for servido no nível territorial pedido
        """
        self._check_nivel(agregado, localidade)
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

    def _get_named(
        self, key: str, last: int, localidade: str = "N1[all]"
    ) -> TimeSeries:
        cfg = AGREGADOS[key]
        classificacao = cfg.get("classificacao")
        return self.agregado(
            agregado=int(cfg["agregado"]),  # type: ignore[call-overload]
            variavel=int(cfg["variavel"]),  # type: ignore[call-overload]
            last=last,
            localidade=localidade,
            classificacao=str(classificacao) if classificacao else None,
            name=str(cfg["name"]),
            unit=str(cfg["unit"]),
        )

    @staticmethod
    def _check_nivel(agregado: int, localidade: str) -> None:
        """Rejeita níveis territoriais que o SIDRA não serve para o agregado."""
        niveis = NIVEIS_TERRITORIAIS.get(agregado)
        if niveis is None:  # agregado fora da tabela: deixa o SIDRA decidir
            return
        nivel = localidade.split("[")[0].strip().upper()
        if nivel not in niveis:
            raise ValueError(
                f"SIDRA não serve o agregado {agregado} no nível {nivel}. "
                f"Níveis disponíveis: {', '.join(niveis)}"
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
