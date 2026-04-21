"""Testes do provider B3 (BrAPI.dev)."""
from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
import respx

from brazilfi.core.exceptions import ProviderError
from brazilfi.providers.b3 import B3, BRAPI_BASE

FAKE_QUOTE = {
    "results": [
        {
            "symbol": "PETR4",
            "shortName": "PETROBRAS PN",
            "currency": "BRL",
            "regularMarketPrice": 37.85,
            "regularMarketChange": 0.45,
            "regularMarketChangePercent": 1.2,
            "regularMarketDayHigh": 38.20,
            "regularMarketDayLow": 37.10,
            "regularMarketVolume": 45678900,
            "marketCap": 485000000000,
        }
    ],
    "requestedAt": "2026-04-20T14:30:00.000Z",
}

FAKE_HISTORY = {
    "results": [
        {
            "symbol": "PETR4",
            "historicalDataPrice": [
                {
                    "date": 1745020800,  # 2026-04-19
                    "open": 37.50,
                    "high": 38.10,
                    "low": 37.20,
                    "close": 37.85,
                    "volume": 45000000,
                    "adjustedClose": 37.85,
                },
                {
                    "date": 1744934400,  # 2026-04-18
                    "open": 37.00,
                    "high": 37.60,
                    "low": 36.80,
                    "close": 37.50,
                    "volume": 41000000,
                    "adjustedClose": 37.50,
                },
            ],
        }
    ],
}

FAKE_LIST = {
    "stocks": [
        {"stock": "PETR4", "name": "Petrobras PN", "close": 37.85, "sector": "Energy"},
        {"stock": "VALE3", "name": "Vale ON", "close": 62.10, "sector": "Basic Materials"},
    ],
}


@respx.mock
def test_quote_single() -> None:
    respx.get(f"{BRAPI_BASE}/quote/PETR4").mock(
        return_value=httpx.Response(200, json=FAKE_QUOTE)
    )
    b3 = B3(token="fake")  # força bypass do free tier check
    quotes = b3.quote("PETR4")
    assert len(quotes) == 1
    assert quotes[0].ticker == "PETR4"
    assert quotes[0].price == Decimal("37.85")


@respx.mock
def test_quote_multi() -> None:
    respx.get(f"{BRAPI_BASE}/quote/PETR4,VALE3").mock(
        return_value=httpx.Response(200, json=FAKE_QUOTE)
    )
    b3 = B3(token="fake")
    quotes = b3.quote(["PETR4", "VALE3"])
    assert len(quotes) >= 1


@respx.mock
def test_price_shortcut() -> None:
    respx.get(f"{BRAPI_BASE}/quote/PETR4").mock(
        return_value=httpx.Response(200, json=FAKE_QUOTE)
    )
    b3 = B3(token="fake")
    assert b3.price("PETR4") == Decimal("37.85")


@respx.mock
def test_history_returns_dataframe() -> None:
    respx.get(url__regex=rf"{BRAPI_BASE}/quote/PETR4.*").mock(
        return_value=httpx.Response(200, json=FAKE_HISTORY)
    )
    b3 = B3(token="fake")
    df = b3.history("PETR4", range_="5d", interval="1d")
    assert len(df) == 2
    assert "close" in df.columns
    assert df["close"].dtype.kind == "f"


@respx.mock
def test_list_tickers() -> None:
    respx.get(url__regex=rf"{BRAPI_BASE}/quote/list.*").mock(
        return_value=httpx.Response(200, json=FAKE_LIST)
    )
    b3 = B3(token="fake")
    df = b3.list_tickers(type_="stock", limit=10)
    assert len(df) == 2
    assert "stock" in df.columns


def test_free_tier_blocks_unknown_ticker() -> None:
    """Sem token, BBAS3 não está no free tier — deve levantar."""
    b3 = B3(token=None)
    b3.token = None  # garante
    with pytest.raises(ProviderError, match=r"free tier|token"):
        b3.quote("BBAS3")


def test_invalid_range_raises() -> None:
    b3 = B3(token="fake")
    with pytest.raises(ValueError, match="range"):
        b3.history("PETR4", range_="999y")
