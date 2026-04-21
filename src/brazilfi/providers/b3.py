"""Provider B3 via BrAPI.dev (cotações, histórico, listagem de tickers)."""
from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pandas as pd

from brazilfi.core.exceptions import DataNotFoundError, ProviderError
from brazilfi.core.http_client import HttpClient
from brazilfi.core.models import Quote

BRAPI_BASE = "https://brapi.dev/api"

# Tickers acessíveis sem token (tier gratuito de teste)
FREE_TIER_TICKERS = {"PETR4", "VALE3", "ITUB4", "MGLU3"}

# Ranges e intervalos válidos no BrAPI
VALID_RANGES = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}
VALID_INTERVALS = {"1m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"}


class B3:
    """
    Wrapper para dados da B3 via BrAPI.dev.

    Autenticação:
        - Sem token: apenas 4 tickers (PETR4, VALE3, ITUB4, MGLU3).
        - Com token (grátis): todos tickers, histórico completo, fundamentalistas.
        - Obter token gratuito em https://brapi.dev/register
        - Passar via parâmetro ou env var BRAZILFI_BRAPI_TOKEN.

    Exemplos:
        >>> b3 = B3()  # lê BRAZILFI_BRAPI_TOKEN se existir
        >>> b3.quote("PETR4")
        >>> b3.quote(["PETR4", "VALE3", "ITUB4"])
        >>> b3.history("PETR4", range_="1y", interval="1d")
        >>> b3.list_tickers(type_="stock", limit=20)
    """

    def __init__(
        self,
        token: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.token = token or os.environ.get("BRAZILFI_BRAPI_TOKEN")
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self.client = HttpClient(base_url=BRAPI_BASE, timeout=timeout, headers=headers)

    # ---------- Cotações ----------

    def quote(self, tickers: str | list[str]) -> list[Quote]:
        """Cotação atual de um ou mais ativos."""
        if isinstance(tickers, str):
            tickers_str = tickers.upper()
            tickers_list = [tickers_str]
        else:
            tickers_list = [t.upper() for t in tickers]
            tickers_str = ",".join(tickers_list)

        self._check_free_tier(tickers_list)

        data = self.client.get(f"quote/{tickers_str}")
        results = data.get("results", []) if isinstance(data, dict) else []
        if not results:
            raise DataNotFoundError(f"Sem cotação para: {tickers_str}")

        quotes: list[Quote] = []
        for r in results:
            try:
                quotes.append(self._parse_quote(r))
            except (KeyError, ValueError, TypeError):
                continue
        return quotes

    def price(self, ticker: str) -> Decimal:
        """Atalho: só o preço atual de um ticker."""
        quotes = self.quote(ticker)
        if not quotes:
            raise DataNotFoundError(f"Sem preço para {ticker}")
        return quotes[0].price

    # ---------- Histórico ----------

    def history(
        self,
        ticker: str,
        range_: str = "1mo",
        interval: str = "1d",
    ) -> pd.DataFrame:
        """
        Histórico OHLCV de um ativo.

        Args:
            ticker: código do ativo (ex: "PETR4")
            range_: período ("1d", "5d", "1mo", "3mo", "6mo", "1y", "5y", "max")
            interval: intervalo do candle ("1d", "1wk", "1mo")
        """
        ticker = ticker.upper()
        self._check_free_tier([ticker])

        if range_ not in VALID_RANGES:
            raise ValueError(f"range inválido. Use um de: {sorted(VALID_RANGES)}")
        if interval not in VALID_INTERVALS:
            raise ValueError(f"interval inválido. Use um de: {sorted(VALID_INTERVALS)}")

        data = self.client.get(
            f"quote/{ticker}",
            params={"range": range_, "interval": interval},
        )
        results = data.get("results", []) if isinstance(data, dict) else []
        if not results:
            raise DataNotFoundError(f"Histórico vazio para {ticker}")

        historical = results[0].get("historicalDataPrice", [])
        if not historical:
            raise DataNotFoundError(
                f"Sem historicalDataPrice para {ticker} ({range_}/{interval})"
            )

        rows: list[dict[str, Any]] = []
        for h in historical:
            try:
                rows.append({
                    "date": datetime.fromtimestamp(h["date"], tz=UTC).date(),
                    "open": float(h.get("open", 0)),
                    "high": float(h.get("high", 0)),
                    "low": float(h.get("low", 0)),
                    "close": float(h.get("close", 0)),
                    "volume": int(h.get("volume", 0)),
                    "adjusted_close": float(h["adjustedClose"]) if h.get("adjustedClose") else None,
                })
            except (KeyError, ValueError, TypeError):
                continue

        if not rows:
            raise DataNotFoundError(f"Nenhum candle válido para {ticker}")

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date").sort_index()

    # ---------- Listagem ----------

    def list_tickers(
        self,
        type_: str | None = None,
        sector: str | None = None,
        search: str | None = None,
        limit: int = 50,
    ) -> pd.DataFrame:
        """
        Lista tickers disponíveis, com filtros.

        Args:
            type_: "stock" (ações), "fund" (FIIs), "bdr"
            sector: filtra por setor (ex: "Energy", "Financial Services")
            search: busca parcial no ticker
            limit: máximo de resultados
        """
        params: dict[str, Any] = {"limit": limit}
        if type_:
            params["type"] = type_
        if sector:
            params["sector"] = sector
        if search:
            params["search"] = search

        data = self.client.get("quote/list", params=params)
        stocks = data.get("stocks", []) if isinstance(data, dict) else []
        if not stocks:
            raise DataNotFoundError("Nenhum ticker retornado pela listagem")

        return pd.DataFrame(stocks)

    # ---------- Internals ----------

    def _check_free_tier(self, tickers: list[str]) -> None:
        """Avisa se tentar ticker fora do free tier sem token."""
        if self.token:
            return
        invalid = [t for t in tickers if t not in FREE_TIER_TICKERS]
        if invalid:
            raise ProviderError(
                f"Tickers {invalid} exigem token BrAPI. "
                f"Free tier cobre só: {sorted(FREE_TIER_TICKERS)}. "
                "Obtenha token gratuito em https://brapi.dev/register e use "
                "B3(token=...) ou env BRAZILFI_BRAPI_TOKEN."
            )

    @staticmethod
    def _parse_quote(r: dict[str, Any]) -> Quote:
        def _dec(key: str) -> Decimal | None:
            v = r.get(key)
            return Decimal(str(v)) if v is not None else None

        return Quote(
            ticker=str(r["symbol"]),
            name=str(r.get("shortName", r["symbol"])),
            price=Decimal(str(r["regularMarketPrice"])),
            change_pct=_dec("regularMarketChangePercent"),
            day_high=_dec("regularMarketDayHigh"),
            day_low=_dec("regularMarketDayLow"),
            volume=int(r["regularMarketVolume"]) if r.get("regularMarketVolume") else None,
            market_cap=_dec("marketCap"),
            currency=str(r.get("currency", "BRL")),
            updated_at=r.get("regularMarketTime"),
        )
