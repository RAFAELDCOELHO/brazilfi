"""Provider B3: cotações/histórico/listagem via BrAPI.dev; opções via COTAHIST diário da B3."""
from __future__ import annotations

import os
import zipfile
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd

from brazilfi.core.cache import CACHE_ROOT, cached_download
from brazilfi.core.exceptions import DataNotFoundError, ProviderError
from brazilfi.core.http_client import HttpClient
from brazilfi.core.models import Quote

BRAPI_BASE = "https://brapi.dev/api"

# Tickers acessíveis sem token (tier gratuito de teste)
FREE_TIER_TICKERS = {"PETR4", "VALE3", "ITUB4", "MGLU3"}

# Ranges e intervalos válidos no BrAPI
VALID_RANGES = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}
VALID_INTERVALS = {"1m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"}

# Opções: arquivo COTAHIST diário da B3 (layout fixo de 245 colunas, latin-1).
# Público, sem token, publicado à noite com todos os instrumentos negociados no dia.
COTAHIST_URL = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/{name}"
COTAHIST_CACHE_DIR = CACHE_ROOT / "cotahist"
COTAHIST_LOOKBACK_DAYS = 10  # quantos dias recuar procurando o último pregão publicado
_SPOT_MARKET = "010"
_OPTION_MARKETS = {"070": "call", "080": "put"}


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
        >>> b3.options("PETR4")                       # cadeia de opções (sem token)
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

    # ---------- Opções ----------

    def options(
        self,
        ticker: str,
        on: str | date | None = None,
        kind: str | None = None,
    ) -> pd.DataFrame:
        """
        Cadeia de opções negociadas sobre `ticker` num pregão (COTAHIST diário da B3).

        Não usa BrAPI nem token. Só aparecem séries que tiveram negócio no dia.
        PETR4 e PETR3 são separadas pela classe do papel (PN/ON).

        Args:
            ticker: ativo-objeto (ex: "PETR4", "BOVA11").
            on: data do pregão. Sem `on`, usa o último arquivo publicado — o do
                dia sai à noite, então durante o pregão você recebe D-1.
            kind: "call", "put" ou None (ambas).
        """
        ticker = ticker.upper()
        if kind is not None and kind not in _OPTION_MARKETS.values():
            raise ValueError('kind deve ser "call", "put" ou None')

        lines, day = self._cotahist(on)
        spot = next(
            (ln for ln in lines if ln[24:27] == _SPOT_MARKET and ln[12:24].strip() == ticker),
            None,
        )
        if spot is None:
            raise DataNotFoundError(f"{ticker} não negociou em {day:%d/%m/%Y} (COTAHIST)")
        klass = self._especi(spot)  # "PN" / "ON" / "CI"
        root = ticker[:4]

        rows = [
            self._parse_option(ln, day)
            for ln in lines
            if ln[24:27] in _OPTION_MARKETS and ln[12:16] == root and self._especi(ln) == klass
        ]
        if kind:
            rows = [r for r in rows if r["kind"] == kind]
        if not rows:
            raise DataNotFoundError(f"Nenhuma opção de {ticker} negociada em {day:%d/%m/%Y}")

        df = pd.DataFrame(rows)
        df["expiry"] = pd.to_datetime(df["expiry"])
        return df.sort_values(["expiry", "kind", "strike"]).reset_index(drop=True)

    # ---------- Internals ----------

    def _cotahist(self, on: str | date | None) -> tuple[list[str], date]:
        """Registros de cotação (tipo 01) do COTAHIST diário e a data do pregão."""
        if on is not None:
            day = on if isinstance(on, date) else date.fromisoformat(on)
            return self._read_cotahist(day), day
        day = date.today()
        for _ in range(COTAHIST_LOOKBACK_DAYS):
            try:
                return self._read_cotahist(day), day
            except DataNotFoundError:
                day -= timedelta(days=1)
        raise DataNotFoundError(
            f"Nenhum COTAHIST diário publicado nos últimos {COTAHIST_LOOKBACK_DAYS} dias"
        )

    @staticmethod
    def _read_cotahist(day: date) -> list[str]:
        name = f"COTAHIST_D{day:%d%m%Y}.ZIP"
        # Pregão passado nunca muda: cache permanente.
        path = cached_download(
            COTAHIST_URL.format(name=name), COTAHIST_CACHE_DIR / name, max_age_days=None
        )
        with zipfile.ZipFile(path) as zf:
            raw = zf.read(zf.namelist()[0]).decode("latin-1")
        return [ln for ln in raw.splitlines() if ln.startswith("01")]

    @staticmethod
    def _especi(line: str) -> str:
        """Primeiro token da especificação (PN, ON, CI...) — casa opção com ativo-objeto."""
        tokens = line[39:49].split()
        return tokens[0] if tokens else ""

    @staticmethod
    def _parse_option(line: str, day: date) -> dict[str, Any]:
        def money(start: int, end: int) -> float:
            return int(line[start:end]) / 100

        return {
            "date": day,
            "ticker": line[12:24].strip(),
            "kind": _OPTION_MARKETS[line[24:27]],
            "strike": money(188, 201),
            "expiry": date(int(line[202:206]), int(line[206:208]), int(line[208:210])),
            "open": money(56, 69),
            "high": money(69, 82),
            "low": money(82, 95),
            "close": money(108, 121),
            "bid": money(121, 134),
            "ask": money(134, 147),
            "trades": int(line[147:152]),
            "quantity": int(line[152:170]),
            "volume": money(170, 188),
            "isin": line[230:242],
        }

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
