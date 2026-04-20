"""CLI da biblioteca — `brazilfi <comando>`."""
from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from brazilfi.core.models import TimeSeries
from brazilfi.providers.bacen import Bacen

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
    for p in ts.points[-50:]:  # últimos 50 para não poluir
        table.add_row(p.date.strftime("%d/%m/%Y"), f"{p.value}")
    console.print(table)
    console.print(f"[dim]Total: {len(ts)} pontos. Fonte: {ts.source}[/dim]")


@app.command()
def selic(
    last: int = typer.Option(30, help="Últimos N dias"),
    meta: bool = typer.Option(False, help="Meta Copom em vez da diária"),
) -> None:
    """Série SELIC (diária ou meta Copom)."""
    ts = Bacen().selic(last=last, meta=meta)
    _render_series(ts, "SELIC")


@app.command()
def ipca(
    last: int = typer.Option(12, help="Últimos N meses"),
    acum: bool = typer.Option(False, help="IPCA acumulado 12 meses"),
) -> None:
    """Série IPCA."""
    ts = Bacen().ipca(last=last, acum_12m=acum)
    _render_series(ts, "IPCA")


@app.command()
def cdi(last: int = typer.Option(30, help="Últimos N dias")) -> None:
    """Série CDI."""
    ts = Bacen().cdi(last=last)
    _render_series(ts, "CDI")


@app.command()
def dolar(last: int = typer.Option(30, help="Últimos N dias")) -> None:
    """Cotação dólar comercial (venda)."""
    ts = Bacen().dolar(last=last)
    _render_series(ts, "Dólar")


if __name__ == "__main__":
    app()
