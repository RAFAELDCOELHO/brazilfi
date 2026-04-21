"""CLI da biblioteca — `brazilfi <comando>`."""
from __future__ import annotations

from typing import cast

import pandas as pd

import typer
from rich.console import Console
from rich.table import Table

from brazilfi.core.models import TimeSeries
from brazilfi.providers.b3 import B3
from brazilfi.providers.bacen import Bacen
from brazilfi.providers.ibge import IBGE
from brazilfi.providers.tesouro import TesouroDireto

app = typer.Typer(
    name="brazilfi",
    help="SDK unificado para mercados brasileiros.",
    no_args_is_help=True,
)
console = Console()


def _render_series(ts: TimeSeries, title: str) -> None:
    table = Table(title=f"{title} — {ts.name} ({ts.unit})", show_lines=False)
    table.add_column("Data", style="cyan")
    table.add_column("Valor", style="green", justify="right")
    for p in ts.points[-50:]:
        table.add_row(p.date.strftime("%d/%m/%Y"), f"{p.value}")
    console.print(table)
    console.print(f"[dim]Total: {len(ts)} pontos. Fonte: {ts.source}[/dim]")


# ---------- Bacen ----------


@app.command()
def selic(
    last: int = typer.Option(30, help="Últimos N dias"),
    meta: bool = typer.Option(False, help="Meta Copom"),
) -> None:
    """Série SELIC."""
    _render_series(Bacen().selic(last=last, meta=meta), "SELIC")


@app.command()
def cdi(last: int = typer.Option(30)) -> None:
    """Série CDI."""
    _render_series(Bacen().cdi(last=last), "CDI")


@app.command()
def dolar(last: int = typer.Option(30)) -> None:
    """Dólar comercial (Bacen)."""
    _render_series(Bacen().dolar(last=last), "Dólar")


# ---------- IBGE ----------


@app.command()
def pib(
    last: int = typer.Option(8, help="Últimos N trimestres"),
    volume: bool = typer.Option(False, help="Variação de volume"),
) -> None:
    """PIB trimestral (IBGE)."""
    _render_series(IBGE().pib(last=last, volume=volume), "PIB")


@app.command()
def desemprego(last: int = typer.Option(4)) -> None:
    """Taxa de desocupação — PNAD Contínua."""
    _render_series(IBGE().desemprego(last=last), "Desemprego")


@app.command()
def ipca(
    last: int = typer.Option(12),
    source: str = typer.Option("bacen", help="bacen | ibge"),
    acum: bool = typer.Option(False, help="Acumulado 12m (Bacen)"),
) -> None:
    """IPCA — escolhe fonte (Bacen ou IBGE)."""
    if source == "ibge":
        _render_series(IBGE().ipca(last=last), "IPCA (IBGE)")
    else:
        _render_series(Bacen().ipca(last=last, acum_12m=acum), "IPCA (Bacen)")


@app.command()
def populacao(last: int = typer.Option(5)) -> None:
    """População estimada (IBGE)."""
    _render_series(IBGE().populacao(last=last), "População")


# ---------- Tesouro Direto ----------


@app.command()
def tesouro() -> None:
    """Títulos do Tesouro Direto disponíveis agora."""
    bonds = TesouroDireto().available()
    table = Table(title="Tesouro Direto — disponíveis", show_lines=False)
    table.add_column("Título", style="cyan")
    table.add_column("Tipo", style="yellow")
    table.add_column("Vencimento", style="magenta")
    table.add_column("Taxa Compra", style="green", justify="right")
    table.add_column("Preço Compra", style="green", justify="right")
    for b in bonds:
        if not b.available:
            continue
        rate = f"{b.buy_rate}%" if b.buy_rate is not None else "—"
        price = f"R$ {b.buy_price}" if b.buy_price is not None else "—"
        table.add_row(
            b.name, b.bond_type, b.maturity.strftime("%d/%m/%Y"), rate, price
        )
    console.print(table)
    console.print(f"[dim]Total: {len(bonds)} títulos[/dim]")


if __name__ == "__main__":
    app()


# ---------- B3 ----------


@app.command()
def quote(tickers: str = typer.Argument(..., help="Ticker(s). Ex: PETR4 ou PETR4,VALE3")) -> None:
    """Cotação atual (B3)."""
    ticker_list = [t.strip().upper() for t in tickers.split(",")]
    quotes = B3().quote(ticker_list)
    table = Table(title="B3 — Cotações", show_lines=False)
    table.add_column("Ticker", style="cyan")
    table.add_column("Nome", style="white")
    table.add_column("Preço", style="green", justify="right")
    table.add_column("Variação", style="yellow", justify="right")
    table.add_column("Volume", style="blue", justify="right")
    for q in quotes:
        change = f"{q.change_pct}%" if q.change_pct is not None else "—"
        volume = f"{q.volume:,}" if q.volume else "—"
        table.add_row(q.ticker, q.name[:30], f"R$ {q.price}", change, volume)
    console.print(table)


@app.command()
def history(
    ticker: str = typer.Argument(..., help="Ticker. Ex: PETR4"),
    range_: str = typer.Option("1mo", "--range", help="1d, 1mo, 3mo, 1y, 5y, max"),
    interval: str = typer.Option("1d", "--interval", help="1d, 1wk, 1mo"),
) -> None:
    """Histórico OHLCV (B3)."""
    df = B3().history(ticker.upper(), range_=range_, interval=interval)
    table = Table(title=f"B3 — {ticker.upper()} ({range_}/{interval})", show_lines=False)
    table.add_column("Data", style="cyan")
    table.add_column("Open", justify="right")
    table.add_column("High", justify="right", style="green")
    table.add_column("Low", justify="right", style="red")
    table.add_column("Close", justify="right", style="yellow")
    table.add_column("Volume", justify="right", style="blue")
    for d, row in df.tail(30).iterrows():
        dt = cast("pd.Timestamp", d)
        table.add_row(
            dt.strftime("%d/%m/%Y"),
            f"{row['open']:.2f}",
            f"{row['high']:.2f}",
            f"{row['low']:.2f}",
            f"{row['close']:.2f}",
            f"{int(row['volume']):,}",
        )
    console.print(table)
    console.print(f"[dim]Total: {len(df)} candles. Últimos 30 exibidos.[/dim]")


@app.command()
def tickers(
    type_: str = typer.Option("stock", "--type", help="stock, fund, bdr"),
    search: str = typer.Option("", "--search", help="Filtro parcial no ticker"),
    limit: int = typer.Option(20, "--limit"),
) -> None:
    """Lista tickers disponíveis na B3."""
    df = B3().list_tickers(type_=type_, search=search or None, limit=limit)
    cols = [c for c in ["stock", "name", "close", "change", "volume", "sector"] if c in df.columns]
    table = Table(title=f"B3 — Tickers ({type_})", show_lines=False)
    for c in cols:
        table.add_column(c, style="cyan" if c == "stock" else "white")
    for _, row in df.iterrows():
        table.add_row(*[str(row.get(c, "—"))[:30] for c in cols])
    console.print(table)



if __name__ == "__main__":
    app()
