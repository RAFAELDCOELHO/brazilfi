"""Testes da CLI usando typer.testing.CliRunner."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pandas as pd
from typer.testing import CliRunner

from brazilfi.cli import app
from brazilfi.core.models import Bond, Quote, SeriesPoint, TimeSeries

runner = CliRunner()


# ---------- Fixtures ----------


def _fake_timeseries(code: str = "11", name: str = "SELIC", unit: str = "%") -> TimeSeries:
    return TimeSeries(
        code=code,
        name=name,
        unit=unit,
        source="bacen",
        points=[
            SeriesPoint(date=pd.Timestamp("2026-04-01").date(), value=Decimal("0.05")),
            SeriesPoint(date=pd.Timestamp("2026-04-02").date(), value=Decimal("0.05")),
        ],
    )


def _fake_quote(ticker: str = "PETR4") -> Quote:
    return Quote(
        ticker=ticker,
        name=f"{ticker} SA",
        price=Decimal("37.85"),
        change_pct=Decimal("1.2"),
        day_high=Decimal("38.20"),
        day_low=Decimal("37.10"),
        volume=45678900,
    )


def _fake_bond() -> Bond:
    return Bond(
        name="Tesouro Prefixado 2027",
        bond_type="LTN",
        maturity=pd.Timestamp("2027-01-01").date(),
        index="Prefixado",
        buy_rate=Decimal("11.25"),
        buy_price=Decimal("850.34"),
        available=True,
    )


# ---------- Help & smoke ----------


def test_cli_help_shows_all_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ["selic", "cdi", "dolar", "pib", "desemprego", "ipca", "tesouro", "quote"]:
        assert cmd in result.stdout


# ---------- Bacen commands ----------


@patch("brazilfi.cli.Bacen")
def test_selic_default(mock_bacen) -> None:
    mock_bacen.return_value.selic.return_value = _fake_timeseries(name="SELIC")
    result = runner.invoke(app, ["selic", "--last", "2"])
    assert result.exit_code == 0
    assert "SELIC" in result.stdout


@patch("brazilfi.cli.Bacen")
def test_cdi(mock_bacen) -> None:
    mock_bacen.return_value.cdi.return_value = _fake_timeseries(code="12", name="CDI")
    result = runner.invoke(app, ["cdi", "--last", "2"])
    assert result.exit_code == 0
    assert "CDI" in result.stdout


@patch("brazilfi.cli.Bacen")
def test_dolar(mock_bacen) -> None:
    mock_bacen.return_value.dolar.return_value = _fake_timeseries(
        code="1", name="Dolar", unit="BRL"
    )
    result = runner.invoke(app, ["dolar", "--last", "5"])
    assert result.exit_code == 0


# ---------- IBGE commands ----------


@patch("brazilfi.cli.IBGE")
def test_pib(mock_ibge) -> None:
    mock_ibge.return_value.pib.return_value = _fake_timeseries(
        code="1620.583", name="PIB"
    )
    result = runner.invoke(app, ["pib", "--last", "4"])
    assert result.exit_code == 0
    assert "PIB" in result.stdout


@patch("brazilfi.cli.IBGE")
def test_desemprego(mock_ibge) -> None:
    mock_ibge.return_value.desemprego.return_value = _fake_timeseries(
        code="4099.4099", name="Desemprego"
    )
    result = runner.invoke(app, ["desemprego"])
    assert result.exit_code == 0


@patch("brazilfi.cli.Bacen")
def test_ipca_source_bacen(mock_bacen) -> None:
    mock_bacen.return_value.ipca.return_value = _fake_timeseries(
        code="433", name="IPCA"
    )
    result = runner.invoke(app, ["ipca", "--source", "bacen"])
    assert result.exit_code == 0
    assert "IPCA" in result.stdout


@patch("brazilfi.cli.IBGE")
def test_ipca_source_ibge(mock_ibge) -> None:
    mock_ibge.return_value.ipca.return_value = _fake_timeseries(
        code="7060.63", name="IPCA"
    )
    result = runner.invoke(app, ["ipca", "--source", "ibge"])
    assert result.exit_code == 0


@patch("brazilfi.cli.IBGE")
def test_populacao(mock_ibge) -> None:
    mock_ibge.return_value.populacao.return_value = _fake_timeseries(
        code="6579.9324", name="Populacao", unit="habitantes"
    )
    result = runner.invoke(app, ["populacao"])
    assert result.exit_code == 0


# ---------- Tesouro ----------


@patch("brazilfi.cli.TesouroDireto")
def test_tesouro(mock_td) -> None:
    mock_td.return_value.available.return_value = [_fake_bond()]
    result = runner.invoke(app, ["tesouro"])
    assert result.exit_code == 0
    assert "Prefixado 2027" in result.stdout


# ---------- B3 ----------


@patch("brazilfi.cli.B3")
def test_quote_single(mock_b3) -> None:
    mock_b3.return_value.quote.return_value = [_fake_quote("PETR4")]
    result = runner.invoke(app, ["quote", "PETR4"])
    assert result.exit_code == 0
    assert "PETR4" in result.stdout


@patch("brazilfi.cli.B3")
def test_quote_multi(mock_b3) -> None:
    mock_b3.return_value.quote.return_value = [
        _fake_quote("PETR4"),
        _fake_quote("VALE3"),
    ]
    result = runner.invoke(app, ["quote", "PETR4,VALE3"])
    assert result.exit_code == 0
    assert "PETR4" in result.stdout
    assert "VALE3" in result.stdout


@patch("brazilfi.cli.B3")
def test_history(mock_b3) -> None:
    df = pd.DataFrame(
        {
            "open": [37.50, 37.00],
            "high": [38.10, 37.60],
            "low": [37.20, 36.80],
            "close": [37.85, 37.50],
            "volume": [45000000, 41000000],
        },
        index=pd.to_datetime(["2026-04-19", "2026-04-18"]),
    )
    df.index.name = "date"
    mock_b3.return_value.history.return_value = df
    result = runner.invoke(app, ["history", "PETR4", "--range", "5d"])
    assert result.exit_code == 0


@patch("brazilfi.cli.B3")
def test_tickers(mock_b3) -> None:
    df = pd.DataFrame(
        {
            "stock": ["PETR4", "VALE3"],
            "name": ["Petrobras", "Vale"],
            "close": [37.85, 62.10],
        }
    )
    mock_b3.return_value.list_tickers.return_value = df
    result = runner.invoke(app, ["tickers", "--limit", "10"])
    assert result.exit_code == 0
