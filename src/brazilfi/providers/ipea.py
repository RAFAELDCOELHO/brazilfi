"""Provider IPEA — Ipeadata (séries macro, regionais e sociais) via OData."""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any

import pandas as pd

from brazilfi.core.cache import CACHE_ROOT, cached_download
from brazilfi.core.exceptions import DataNotFoundError
from brazilfi.core.http_client import HttpClient
from brazilfi.core.models import SeriesPoint, TimeSeries

# A API OData4 do Ipeadata ignora/rejeita $filter e $orderby: quem filtra é o cliente.
IPEA_BASE = "http://www.ipeadata.gov.br/api/odata4"
CATALOG_URL = f"{IPEA_BASE}/Metadados"
CACHE_DIR = CACHE_ROOT / "ipea"

CATALOG_COLS = {
    "SERCODIGO": "code",
    "SERNOME": "name",
    "PERNOME": "freq",
    "UNINOME": "unit",
    "FNTSIGLA": "source",
    "BASNOME": "base",
    "SERSTATUS": "status",
    "SERATUALIZACAO": "updated",
}


class IPEA:
    """
    Ipeadata (IPEA): ~3.600 séries macro, regionais e sociais.

    Exemplos:
        >>> ipea = IPEA()
        >>> ipea.search("ipca")                          # catálogo, filtrado localmente
        >>> ipea.serie("PRECOS12_IPCAG12").to_dataframe()  # IPCA mensal desde 1980
        >>> ipea.metadata("PRECOS12_IPCAG12")["SERNOME"]
    """

    def __init__(self, timeout: float = 60.0) -> None:
        self.client = HttpClient(base_url=IPEA_BASE, timeout=timeout)

    def search(
        self,
        term: str | None = None,
        freq: str | None = None,
        source: str | None = None,
        active_only: bool = True,
    ) -> pd.DataFrame:
        """
        Busca no catálogo (`Metadados`, ~7 MB, cache de 1 dia).

        Args:
            term: filtro case-insensitive no nome ou no código da série.
            freq: "Mensal", "Trimestral", "Anual", "Diária"...
            source: sigla da fonte (ex: "IBGE", "BCB"), casamento parcial.
            active_only: só séries com status "A" (ativas).
        """
        path = cached_download(CATALOG_URL, CACHE_DIR / "metadados.json")
        rows: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))["value"]
        df = pd.DataFrame(rows)[list(CATALOG_COLS)].rename(columns=CATALOG_COLS)
        if active_only:
            df = df[df["status"] == "A"]
        if term:
            mask = df["name"].str.contains(term, case=False, na=False, regex=False) | df[
                "code"
            ].str.contains(term, case=False, na=False, regex=False)
            df = df[mask]
        if freq:
            df = df[df["freq"].str.lower() == freq.lower()]
        if source:
            df = df[df["source"].str.contains(source, case=False, na=False, regex=False)]
        if df.empty:
            raise DataNotFoundError(f"Nenhuma série para term={term!r} freq={freq!r}")
        df["updated"] = pd.to_datetime(df["updated"], errors="coerce", utc=True)
        return df.reset_index(drop=True)

    def metadata(self, code: str) -> dict[str, Any]:
        """Metadados de uma série (nome, fonte, periodicidade, unidade, comentário)."""
        data = self.client.get(f"Metadados('{code}')")
        value = data.get("value", []) if isinstance(data, dict) else []
        if not value:
            raise DataNotFoundError(f"Série IPEA {code!r} não existe")
        meta: dict[str, Any] = value[0]
        return meta

    def serie(self, code: str, territorio: str | None = None) -> TimeSeries:
        """
        Série completa como `TimeSeries`.

        Séries regionais têm um ponto por território e data; sem `territorio`
        fica o agregado nacional (TERCODIGO vazio ou "0" = Brasil) ou, se não
        houver, todos os territórios.
        """
        meta = self.metadata(code)
        df = self.dataframe(code)
        if territorio is not None:
            df = df[df["territory"] == territorio]
        else:
            national = next((t for t in ("", "0") if (df["territory"] == t).any()), None)
            if national is not None:
                df = df[df["territory"] == national]
        if df.empty:
            raise DataNotFoundError(f"Série IPEA {code!r} sem valores para {territorio!r}")
        points = [
            SeriesPoint(date=d, value=Decimal(str(v)))
            for d, v in zip(df["date"], df["value"], strict=True)
        ]
        return TimeSeries(
            code=code,
            name=str(meta.get("SERNOME") or code),
            unit=str(meta.get("UNINOME") or ""),
            source="ipea",
            points=points,
        )

    def dataframe(self, code: str) -> pd.DataFrame:
        """Valores crus da série, com `level`/`territory` para séries regionais."""
        data = self.client.get(f"ValoresSerie(SERCODIGO='{code}')")
        rows = data.get("value", []) if isinstance(data, dict) else []
        records = [
            {
                "date": datetime.fromisoformat(r["VALDATA"]).date(),
                "value": float(r["VALVALOR"]),
                "level": r.get("NIVNOME") or "",
                "territory": r.get("TERCODIGO") or "",
            }
            for r in rows
            if r.get("VALVALOR") is not None
        ]
        if not records:
            raise DataNotFoundError(f"Série IPEA {code!r} sem valores")
        return pd.DataFrame(records).sort_values(["territory", "date"]).reset_index(drop=True)
