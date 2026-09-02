"""Testes do provider B3 (BrAPI.dev + COTAHIST para opções)."""
from __future__ import annotations

import io
import zipfile
from datetime import date, timedelta
from decimal import Decimal

import httpx
import pytest
import respx

from brazilfi.core.exceptions import DataNotFoundError, ProviderError
from brazilfi.providers import b3 as b3_module
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


# ---------- Opções (COTAHIST diário) ----------

# Linhas reais do COTAHIST_D01092026 (245 colunas fixas): PETR3/PETR4/BOVA11 à vista,
# call/put de PETR4 (PN), uma call de PETR3 (ON), uma de VALE3 e uma de BOVA11 (CI).
FAKE_COTAHIST = """\
00COTAHIST.2026BOVESPA 20260901
012026090102PETR3       010PETROBRAS   ON  EDJ N2   R$  000000000510000000000052470000000005082000000000517300000000052370000000005236000000000523726948000000000010985700000000056836696800000000000000009999123100000010000000000000BRPETRACNOR9215
012026090102PETR4       010PETROBRAS   PN  EDJ N2   R$  000000000455000000000046940000000004550000000000464300000000046870000000004686000000000468775161000000000049726600000000230881483100000000000000009999123100000010000000000000BRPETRACNPR6230
012026090178PETRK312    070PETRE    /EDPN      N2000R$  000000000170600000000017060000000001706000000000170600000000017060000000000000000000000000000001000000000000000300000000000000511800000000000301602026111900000010000000000000BRPETRACNPR6229
012026090182PETRX501    080PETRE    /EDPN      N2000R$  000000000032200000000003220000000000299000000000030300000000003030000000000290000000000030300009000000000000008600000000000002608500000000000464102026121800000010000000000000BRPETRACNPR6219
012026090178PETRI531    070PETR  FM/EDJON      N2000R$  000000000012600000000002080000000000126000000000016300000000002080000000000005000000000000000036000000000000044400000000000007242600000000000519402026091800000010000000000000BRPETRACNOR9214
012026090178VALEK850    070VALE        ON      NM000R$  000000000034400000000003470000000000320000000000033500000000003220000000000297000000000034100009000000000000000900000000000000301800000000000833902026111900000010000000000000BRVALEACNOR0221
012026090114BOVA11      010ISHARES BOVACI           R$  000000001754700000000178250000000017448000000001774300000000177100000000017688000000001771070821000000000005629246000000099882394400000000000000009999123100000010000000000000BRBOVACTF003120
012026090178BOVAK141    070BOVA        CI        000R$  000000000381800000000040000000000003818000000000394000000000040000000000000000000000000000000002000000000000000888000000000003499584000000001410002026111900000010000000000000BRBOVACTF003112
99COTAHIST.2026BOVESPA 2026090100000017785
"""


def _cotahist_zip(body: str = FAKE_COTAHIST, name: str = "COTAHIST_D01092026.TXT") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, body.replace("\n", "\r\n").encode("latin-1"))
    return buf.getvalue()


COTAHIST_ANY = r"https://bvmf\.bmfbovespa\.com\.br/InstDados/SerHist/COTAHIST_D\d{8}\.ZIP"


@pytest.fixture(autouse=True)
def _tmp_cotahist_cache(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(b3_module, "COTAHIST_CACHE_DIR", tmp_path)


@respx.mock
def test_options_filters_by_root_and_share_class() -> None:
    route = respx.get(url__regex=COTAHIST_ANY).mock(
        return_value=httpx.Response(200, content=_cotahist_zip())
    )
    df = B3().options("petr4", on="2026-09-01")

    assert route.calls[0].request.url.path.endswith("/COTAHIST_D01092026.ZIP")
    assert list(df["ticker"]) == ["PETRK312", "PETRX501"]  # sem PETRI531 (ON), VALE, BOVA
    call = df.iloc[0]
    assert call["kind"] == "call"
    assert call["strike"] == pytest.approx(30.16)
    assert str(call["expiry"].date()) == "2026-11-19"
    assert call["close"] == pytest.approx(17.06)
    assert (call["trades"], call["quantity"]) == (1, 300)
    assert call["volume"] == pytest.approx(5118.0)  # 300 x 17.06
    assert call["isin"] == "BRPETRACNPR6"
    assert str(call["date"]) == "2026-09-01"


@respx.mock
def test_options_on_and_etf_underlyings() -> None:
    respx.get(url__regex=COTAHIST_ANY).mock(
        return_value=httpx.Response(200, content=_cotahist_zip())
    )
    assert list(B3().options("PETR3", on=date(2026, 9, 1))["ticker"]) == ["PETRI531"]
    assert list(B3().options("BOVA11", on="2026-09-01")["ticker"]) == ["BOVAK141"]


@respx.mock
def test_options_kind_filter_and_validation() -> None:
    respx.get(url__regex=COTAHIST_ANY).mock(
        return_value=httpx.Response(200, content=_cotahist_zip())
    )
    puts = B3().options("PETR4", on="2026-09-01", kind="put")
    assert list(puts["ticker"]) == ["PETRX501"]
    assert puts.iloc[0]["strike"] == pytest.approx(46.41)
    with pytest.raises(ValueError, match="kind"):
        B3().options("PETR4", on="2026-09-01", kind="straddle")


@respx.mock
def test_options_ticker_not_traded_raises() -> None:
    respx.get(url__regex=COTAHIST_ANY).mock(
        return_value=httpx.Response(200, content=_cotahist_zip())
    )
    with pytest.raises(DataNotFoundError, match="ITUB4"):
        B3().options("ITUB4", on="2026-09-01")


@respx.mock
def test_options_walks_back_to_last_published_session() -> None:
    """Sem `on`: o arquivo de hoje ainda não saiu (404) → usa o de ontem."""
    route = respx.get(url__regex=COTAHIST_ANY).mock(
        side_effect=[httpx.Response(404), httpx.Response(200, content=_cotahist_zip())]
    )
    df = B3().options("PETR4")
    assert route.call_count == 2
    assert df["date"].iloc[0] == date.today() - timedelta(days=1)


@respx.mock
def test_options_past_session_is_cached_forever() -> None:
    route = respx.get(url__regex=COTAHIST_ANY).mock(
        return_value=httpx.Response(200, content=_cotahist_zip())
    )
    B3().options("PETR4", on="2026-09-01")
    B3().options("PETR3", on="2026-09-01")
    assert route.call_count == 1
