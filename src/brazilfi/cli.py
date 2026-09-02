"""CLI da biblioteca — `brazilfi <comando>`."""
from __future__ import annotations

from typing import cast

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from brazilfi.core.exceptions import BrazilFiError
from brazilfi.core.models import TimeSeries
from brazilfi.providers.anbima import ANBIMA
from brazilfi.providers.b3 import B3
from brazilfi.providers.bacen import Bacen
from brazilfi.providers.cvm import CVM
from brazilfi.providers.ibge import IBGE
from brazilfi.providers.ipea import IPEA
from brazilfi.providers.tesouro import TesouroDireto

app = typer.Typer(
    name="brazilfi",
    help="SDK unificado para mercados brasileiros.",
    no_args_is_help=True,
)
console = Console()

LOCALIDADE_HELP = "Nível territorial SIDRA. Ex: N3[35] (UF SP), N6[3550308] (município SP)"


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


@app.command()
def focus(
    indicador: str = typer.Argument("IPCA", help="IPCA, Selic, Câmbio, PIB Total, IGP-M..."),
    freq: str = typer.Option("anual", "--freq", help="anual, mensal, trimestral, selic..."),
    start: str = typer.Option("", "--start", help="Data de coleta inicial YYYY-MM-DD"),
) -> None:
    """Expectativas de mercado do boletim Focus (Bacen)."""
    df = Bacen().focus(indicador, freq=freq, start=start or None)
    table = Table(title=f"Focus — {indicador} ({freq})", show_lines=False)
    table.add_column("Coleta", style="cyan")
    table.add_column("Referência", style="magenta")
    table.add_column("Mediana", justify="right", style="green")
    table.add_column("Média", justify="right")
    table.add_column("Mín", justify="right", style="red")
    table.add_column("Máx", justify="right", style="blue")
    table.add_column("Resp.", justify="right")
    ref_col = "meeting" if "meeting" in df.columns else "reference"
    for _, row in df.tail(40).iterrows():
        d = cast("pd.Timestamp", row["date"])
        table.add_row(
            d.strftime("%d/%m/%Y"),
            str(row.get(ref_col, "—")),
            f"{row['median']:.2f}",
            f"{row['mean']:.2f}",
            f"{row['min']:.2f}",
            f"{row['max']:.2f}",
            str(int(row["respondents"])),
        )
    console.print(table)
    console.print(f"[dim]Total: {len(df)} linhas. Últimas 40 exibidas.[/dim]")


# ---------- IBGE ----------


@app.command()
def pib(last: int = typer.Option(8, help="Últimos N trimestres")) -> None:
    """PIB trimestral — índice de volume (IBGE)."""
    _render_series(IBGE().pib(last=last), "PIB")


@app.command()
def desemprego(
    last: int = typer.Option(4),
    localidade: str = typer.Option("N1[all]", help=LOCALIDADE_HELP),
) -> None:
    """Taxa de desocupação — PNAD Contínua."""
    _render_series(IBGE().desemprego(last=last, localidade=localidade), "Desemprego")


@app.command()
def ipca(
    last: int = typer.Option(12),
    source: str = typer.Option("bacen", help="bacen | ibge"),
    acum: bool = typer.Option(False, help="Acumulado 12 meses"),
    localidade: str = typer.Option("N1[all]", help=f"{LOCALIDADE_HELP} (só IBGE)"),
) -> None:
    """IPCA — escolhe fonte (Bacen ou IBGE)."""
    if source == "ibge":
        _render_series(
            IBGE().ipca(last=last, acum_12m=acum, localidade=localidade), "IPCA (IBGE)"
        )
    else:
        _render_series(Bacen().ipca(last=last, acum_12m=acum), "IPCA (Bacen)")


@app.command()
def populacao(
    last: int = typer.Option(5),
    localidade: str = typer.Option("N1[all]", help=LOCALIDADE_HELP),
) -> None:
    """População estimada (IBGE)."""
    _render_series(IBGE().populacao(last=last, localidade=localidade), "População")


# ---------- IPEA ----------


@app.command()
def ipea(code: str = typer.Argument(..., help="Código da série. Ex: PRECOS12_IPCAG12")) -> None:
    """Série do Ipeadata (IPEA)."""
    _render_series(IPEA().serie(code), "IPEA")


@app.command("ipea-search")
def ipea_search(
    term: str = typer.Argument(..., help="Texto no nome ou código"),
    freq: str = typer.Option("", "--freq", help="Mensal, Trimestral, Anual, Diária"),
    limit: int = typer.Option(20, "--limit"),
) -> None:
    """Busca séries no catálogo do Ipeadata."""
    df = IPEA().search(term, freq=freq or None).head(limit)
    table = Table(title=f"Ipeadata — '{term}'", show_lines=False)
    table.add_column("Código", style="cyan", no_wrap=True)
    table.add_column("Nome", style="white")
    table.add_column("Freq.", style="yellow")
    table.add_column("Unidade", style="magenta")
    table.add_column("Fonte", style="blue")
    for _, row in df.iterrows():
        table.add_row(
            str(row["code"]), str(row["name"])[:60], str(row["freq"]),
            str(row["unit"] or ""), str(row["source"] or ""),
        )
    console.print(table)


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


# ---------- ANBIMA ----------


@app.command("curva-ima")
def curva_ima(
    indice: str = typer.Option("IMA-B", "--indice", help="IMA-B, IMA-B 5, IMA-B 5+, IRF-M, IMA-S"),
) -> None:
    """Curva de juros de um índice IMA (ANBIMA)."""
    curva = ANBIMA().curva_ima(indice)
    ref = curva.reference_date.strftime("%d/%m/%Y")
    table = Table(title=f"ANBIMA — {curva.index} ({ref})", show_lines=False)
    table.add_column("Vencimento", style="magenta")
    table.add_column("Título", style="yellow")
    table.add_column(f"Taxa ({curva.unit})", style="green", justify="right")
    table.add_column("PU", style="green", justify="right")
    table.add_column("Peso (%)", style="blue", justify="right")
    for p in curva.points:
        table.add_row(
            p.maturity.strftime("%d/%m/%Y"),
            p.bond_type,
            f"{p.rate}",
            f"R$ {p.price}" if p.price is not None else "—",
            f"{p.weight_pct}" if p.weight_pct is not None else "—",
        )
    console.print(table)
    console.print(
        f"[dim]Total: {len(curva)} vértices. "
        f"Número-índice: {curva.index_number}. Fonte: {curva.source}[/dim]"
    )


@app.command()
def debentures(
    data: str = typer.Option("", "--data", help="Dia útil YYYY-MM-DD (default: último publicado)"),
    search: str = typer.Option("", "--search", help="Filtro no código ou emissor"),
    indexador: str = typer.Option("", "--indexador", help="DI +, IPCA +, PREFIXADO, % DI"),
) -> None:
    """Mercado secundário de debêntures (ANBIMA)."""
    df = ANBIMA().debentures(on=data or None)
    if search:
        mask = df["code"].str.contains(search, case=False) | df["issuer"].str.contains(
            search, case=False
        )
        df = df[mask]
    if indexador:
        df = df[df["indexer"].str.upper() == indexador.upper()]
    day = pd.Timestamp(df["date"].iloc[0]) if len(df) else None
    title = f"ANBIMA — Debêntures ({day:%d/%m/%Y})" if day is not None else "ANBIMA — Debêntures"
    table = Table(title=title, show_lines=False)
    table.add_column("Código", style="cyan", no_wrap=True)
    table.add_column("Emissor", style="white")
    table.add_column("Vencimento", style="magenta")
    table.add_column("Indexador", style="yellow")
    table.add_column("Taxa ind.", justify="right", style="green")
    table.add_column("PU", justify="right")
    table.add_column("Duration", justify="right", style="blue")
    for _, row in df.head(60).iterrows():
        mat = row["maturity"]
        table.add_row(
            str(row["code"]),
            str(row["issuer"])[:35],
            mat.strftime("%d/%m/%Y") if pd.notna(mat) else "—",
            str(row["index"]),
            f"{row['indicative_rate']:.4f}" if pd.notna(row["indicative_rate"]) else "—",
            f"{row['price']:,.2f}" if pd.notna(row["price"]) else "—",
            f"{row['duration']:,.0f}" if pd.notna(row["duration"]) else "—",
        )
    console.print(table)
    console.print(f"[dim]Total: {len(df)} papéis. Primeiros 60 exibidos.[/dim]")


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


@app.command()
def opcoes(
    ticker: str = typer.Argument(..., help="Ativo-objeto. Ex: PETR4"),
    data: str = typer.Option("", "--data", help="Pregão YYYY-MM-DD (default: último publicado)"),
    tipo: str = typer.Option("", "--tipo", help="call | put"),
) -> None:
    """Opções negociadas sobre um ativo (B3, COTAHIST)."""
    df = B3().options(ticker.upper(), on=data or None, kind=tipo or None)
    day = pd.Timestamp(df["date"].iloc[0])
    table = Table(title=f"B3 — Opções de {ticker.upper()} ({day:%d/%m/%Y})", show_lines=False)
    table.add_column("Série", style="cyan")
    table.add_column("Tipo", style="yellow")
    table.add_column("Strike", justify="right")
    table.add_column("Vencimento", style="magenta")
    table.add_column("Último", justify="right", style="green")
    table.add_column("Negócios", justify="right", style="blue")
    table.add_column("Volume", justify="right", style="blue")
    for _, row in df.head(60).iterrows():
        expiry = cast("pd.Timestamp", row["expiry"])
        table.add_row(
            str(row["ticker"]),
            str(row["kind"]),
            f"{row['strike']:.2f}",
            expiry.strftime("%d/%m/%Y"),
            f"{row['close']:.2f}",
            f"{int(row['trades']):,}",
            f"{row['volume']:,.2f}",
        )
    console.print(table)
    console.print(f"[dim]Total: {len(df)} séries negociadas. Primeiras 60 exibidas.[/dim]")


# ---------- CVM ----------


@app.command()
def fundos(
    search: str = typer.Option("", "--search", help="Filtro na razão social"),
    limit: int = typer.Option(20, "--limit"),
) -> None:
    """Classes de fundos em funcionamento (CVM)."""
    df = CVM().fundos(search=search or None).head(limit)
    table = Table(title="CVM — Fundos", show_lines=False)
    table.add_column("CNPJ", style="cyan", no_wrap=True)
    table.add_column("Nome", style="white")
    table.add_column("Tipo", style="yellow")
    table.add_column("PL", justify="right", style="green")
    table.add_column("Gestor", style="white")
    for _, row in df.iterrows():
        pl = f"R$ {row['net_assets']:,.0f}" if pd.notna(row["net_assets"]) else "—"
        table.add_row(
            str(row["cnpj"]), str(row["name"])[:50], str(row["type"])[:25], pl,
            str(row["manager"] if pd.notna(row["manager"]) else "—")[:30],
        )
    console.print(table)


@app.command()
def cotas(
    cnpj: str = typer.Argument(..., help="CNPJ da classe do fundo"),
    start: str = typer.Option("", "--start", help="YYYY-MM-DD (default: 3 meses atrás)"),
    end: str = typer.Option("", "--end", help="YYYY-MM-DD (default: hoje)"),
) -> None:
    """Cota diária de um fundo (CVM, informe diário)."""
    df = CVM().cotas(cnpj, start=start or None, end=end or None)
    table = Table(title=f"CVM — Cotas {cnpj}", show_lines=False)
    table.add_column("Data", style="cyan")
    table.add_column("Cota", justify="right", style="green")
    table.add_column("PL", justify="right")
    table.add_column("Captação", justify="right", style="blue")
    table.add_column("Resgate", justify="right", style="red")
    table.add_column("Cotistas", justify="right")
    for d, row in df.tail(30).iterrows():
        dt = cast("pd.Timestamp", d)
        table.add_row(
            dt.strftime("%d/%m/%Y"),
            f"{row['quota']:.6f}",
            f"{row['net_assets']:,.2f}",
            f"{row['inflow']:,.2f}",
            f"{row['outflow']:,.2f}",
            f"{int(row['shareholders']):,}",
        )
    console.print(table)
    console.print(f"[dim]Total: {len(df)} dias. Últimos 30 exibidos.[/dim]")


@app.command()
def dfp(
    empresa: str = typer.Argument(..., help="CNPJ ou código CVM. Ex: 1023 ou 33.000.167/0001-01"),
    ano: int = typer.Option(..., "--ano", help="Exercício. Ex: 2025"),
    demonstracao: str = typer.Option("DRE", "--demonstracao", help="BPA, BPP, DRE, DFC_MI..."),
    individual: bool = typer.Option(False, "--individual", help="Individual em vez de consolidado"),
    trimestral: bool = typer.Option(False, "--itr", help="ITR (trimestral) em vez de DFP"),
) -> None:
    """Demonstração financeira de uma companhia aberta (CVM)."""
    company: str | int = int(empresa) if empresa.isdigit() and len(empresa) < 14 else empresa
    cvm = CVM()
    fetch = cvm.itr if trimestral else cvm.dfp
    df = fetch(company, ano, statement=demonstracao, consolidated=not individual)
    name = str(df["company"].iloc[0])
    title = f"CVM — {'ITR' if trimestral else 'DFP'} {demonstracao.upper()} {ano} — {name}"
    table = Table(title=title, show_lines=False)
    table.add_column("Conta", style="cyan")
    table.add_column("Descrição", style="white")
    table.add_column("Período", style="magenta")
    table.add_column("Valor (R$)", justify="right", style="green")
    for _, row in df.iterrows():
        end_ = cast("pd.Timestamp", row["period_end"])
        table.add_row(
            str(row["account"]),
            str(row["description"])[:50],
            end_.strftime("%d/%m/%Y"),
            f"{row['value']:,.0f}",
        )
    console.print(table)
    console.print(f"[dim]Total: {len(df)} contas.[/dim]")


def main() -> None:
    """Entry point do console script: erros da lib viram mensagem curta, não traceback."""
    try:
        app()
    except (BrazilFiError, ValueError) as e:  # ValueError = argumento inválido (ex: localidade)
        console.print(f"[red]Erro:[/red] {e}")
        raise SystemExit(1) from e


if __name__ == "__main__":
    main()
