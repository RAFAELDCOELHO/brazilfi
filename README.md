<div align="center">

# brazilfi


**SDK Python unificado para APIs de mercados financeiros brasileiros.**

Bacen · IBGE · Tesouro Direto · B3 · ANBIMA · CVM · IPEA — uma única biblioteca, uma única API.

[![PyPI](https://img.shields.io/pypi/v/brazilfi.svg?color=blue)](https://pypi.org/project/brazilfi/)
[![Python](https://img.shields.io/pypi/pyversions/brazilfi.svg)](https://pypi.org/project/brazilfi/)
[![CI](https://github.com/RAFAELDCOELHO/brazilfi/workflows/CI/badge.svg)](https://github.com/RAFAELDCOELHO/brazilfi/actions)
[![License](https://img.shields.io/pypi/l/brazilfi.svg)](https://github.com/RAFAELDCOELHO/brazilfi/blob/main/LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/brazilfi.svg)](https://pypi.org/project/brazilfi/)

</div>

---

## Instalação

```bash
pip install brazilfi
```

## 60 segundos

```python
from brazilfi import ANBIMA, B3, CVM, IBGE, IPEA, Bacen, TesouroDireto

# SELIC dos últimos 30 dias
Bacen().selic(last=30).to_dataframe()

# Expectativas do Focus para o IPCA (mediana por ano de referência)
Bacen().focus("IPCA")

# Qualquer série do Ipeadata (IPCA mensal desde 1980)
IPEA().serie("PRECOS12_IPCAG12").to_dataframe()

# PIB trimestral
IBGE().pib(last=8).to_dataframe()

# Títulos do Tesouro Direto no último pregão (D-1)
TesouroDireto().available_dataframe()

# Cotação PETR4 (B3 via BrAPI)
B3().quote("PETR4")

# Opções de PETR4 negociadas no último pregão (B3, sem token)
B3().options("PETR4")

# DRE consolidada 2025 do Banco do Brasil (CVM, código CVM 1023)
CVM().dfp(1023, 2025, statement="DRE")

# Curva de juros do IMA-B (ANBIMA) — ou "IMA-B 5+", "IRF-M", "IMA-S"...
ANBIMA().curva_ima_dataframe()

# Debêntures no mercado secundário (ANBIMA), último dia útil
ANBIMA().debentures()
```

Ou via CLI:

```bash
brazilfi selic --last 30
brazilfi focus IPCA
brazilfi ipea-search "taxa de câmbio" --freq Mensal
brazilfi pib --last 8
brazilfi tesouro
brazilfi quote PETR4,VALE3
brazilfi opcoes PETR4 --tipo call
brazilfi curva-ima --indice "IMA-B 5+"
brazilfi debentures --indexador "IPCA +"
brazilfi fundos --search verde
brazilfi dfp 1023 --ano 2025
```

---

## Por que brazilfi

Dados brasileiros estão espalhados em **APIs fragmentadas, mal documentadas e sem SDK oficial**. Cada dev que quer construir algo financeiro reinventa a roda: parser de XML do Bacen, scraping de CSV do Tesouro, SIDRA aninhado do IBGE.

`brazilfi` resolve isso com uma API única, tipada e testada.

| | brazilfi | python-bcb | sidrapy | investpy |
|---|:---:|:---:|:---:|:---:|
| **Bacen (SGS + Focus)** | ✅ | ✅ | ❌ | ❌ |
| **IPEA (Ipeadata)** | ✅ | ❌ | ❌ | ❌ |
| **IBGE (SIDRA)** | ✅ | ❌ | ✅ | ❌ |
| **Tesouro Direto** | ✅ | ❌ | ❌ | ❌ |
| **B3** (cotações, OHLCV, opções) | ✅ | ❌ | ❌ | ✅ |
| **ANBIMA** (curvas IMA, debêntures) | ✅ | ❌ | ❌ | ❌ |
| **CVM** (fundos, DFP/ITR) | ✅ | ❌ | ❌ | ❌ |
| **Modelos tipados (Pydantic)** | ✅ | ❌ | ❌ | ❌ |
| **CLI integrada** | ✅ | ❌ | ❌ | ❌ |
| **Async-ready** | ✅ | ❌ | ❌ | ❌ |
| **Status** | Ativo | Ativo | Ativo | **Deprecated** |

---

## Exemplos reais

> Notebook completo em [`docs/examples/01_analise_macro.ipynb`](docs/examples/01_analise_macro.ipynb):
> SELIC + IPCA + PIB, juro real e gráfico (`pip install "brazilfi[examples]"`).

### Comparar SELIC vs CDI (últimos 30 dias)

```python
import pandas as pd
from brazilfi import Bacen

bc = Bacen()
df = pd.concat([
    bc.selic(last=30).to_dataframe().rename(columns={"value": "SELIC"}),
    bc.cdi(last=30).to_dataframe().rename(columns={"value": "CDI"}),
], axis=1)

print(df.describe())
```

### Rendimento real dos Prefixados vs inflação

```python
from brazilfi import TesouroDireto, IBGE

# Prefixados disponíveis
prefixados = [b for b in TesouroDireto().available() if b.bond_type == "LTN"]

# Inflação acumulada últimos 12 meses
ipca_12m = float(IBGE().ipca(last=12).to_dataframe().sum().iloc[0])

for bond in sorted(prefixados, key=lambda b: b.maturity):
    rendimento_real = float(bond.buy_rate) - ipca_12m
    print(f"{bond.name}: {bond.buy_rate}% nominal, {rendimento_real:.2f}% real")
```

### Focus vs realizado: o mercado acertou o IPCA? (Bacen)

```python
from brazilfi import Bacen

bc = Bacen()
focus = bc.focus("IPCA", start="2025-01-01")             # coleta semanal, por ano de referência
esperado_2025 = focus[focus["reference"] == "2025"].set_index("date")["median"]
realizado_2025 = float(bc.ipca(start="2025-01-01", end="2025-12-31").to_dataframe().add(1).prod().iloc[0] - 1) * 100
print(f"Focus (última mediana): {esperado_2025.iloc[-1]:.2f}%  |  IPCA 2025: {realizado_2025:.2f}%")

# Por reunião do Copom
bc.focus("Selic", freq="selic")[["date", "meeting", "median"]].tail()
```

### Séries longas do Ipeadata (IPEA)

```python
from brazilfi import IPEA

ipea = IPEA()
ipea.search("câmbio", freq="Mensal")                 # catálogo filtrado localmente
cambio = ipea.serie("BM12_ERC12").to_dataframe()     # R$/US$ comercial, média mensal, desde 1953
ipea.dataframe("PIBPMCE")                            # séries regionais vêm com `territory`
```

### Correlação PIB vs desemprego

```python
from brazilfi import IBGE

ibge = IBGE()
pib = ibge.pib(last=20).to_dataframe().rename(columns={"value": "pib"})
desemprego = ibge.desemprego(last=20).to_dataframe().rename(columns={"value": "desemprego"})

merged = pib.join(desemprego, how="inner")
print(f"Correlação PIB x desemprego: {merged.corr().iloc[0,1]:.3f}")
```



### IPCA e desemprego por município ou UF (IBGE)

```python
from brazilfi import IBGE

ibge = IBGE()
ibge.ipca(last=12, localidade="N6[3550308]")        # IPCA de São Paulo-SP
ibge.desemprego(last=4, localidade="N3[35]")        # Desocupação na UF de SP
ibge.populacao(last=1, localidade="N6[3304557]")    # População do Rio de Janeiro
```

> **Nota:** os níveis vêm dos metadados do SIDRA. IPCA (agregado 7060) só é
> apurado em N1, N6 (município) e N7 (região metropolitana) — **não existe IPCA
> por UF**. PIB trimestral (1620) é servido apenas para o Brasil, por isso
> `pib()` não aceita `localidade`. Níveis inválidos levantam `ValueError`.

### Analisar portfólio: variação do dia em múltiplos ativos (B3)

```python
from brazilfi import B3

b3 = B3()  # Lê BRAZILFI_BRAPI_TOKEN se disponível
quotes = b3.quote(["PETR4", "VALE3", "ITUB4", "MGLU3"])

for q in quotes:
    direcao = "▲" if q.change_pct and float(q.change_pct) > 0 else "▼"
    print(f"{q.ticker} {direcao} R$ {q.price} ({q.change_pct}%)")
```

> **Nota:** cotações e histórico usam a [BrAPI.dev](https://brapi.dev). Sem token, apenas
> 4 tickers (PETR4, VALE3, ITUB4, MGLU3). Token gratuito libera todos os ativos.

### Cadeia de opções: calls de PETR4 por vencimento (B3)

```python
from brazilfi import B3

calls = B3().options("PETR4", kind="call")   # último pregão publicado, sem token
print(calls.groupby("expiry")[["trades", "volume"]].sum())

# Só as séries perto do dinheiro, num pregão específico
spot = float(B3().price("PETR4"))
chain = B3().options("PETR4", on="2026-09-01")
print(chain[chain["strike"].between(spot * 0.9, spot * 1.1)])
```

> **Nota:** a fonte é o arquivo COTAHIST diário da B3 (público, fim de dia). Só aparecem
> séries que tiveram negócio no pregão; o arquivo do dia sai à noite, então durante o pregão
> você recebe D-1. Opções de PETR4 e PETR3 são separadas pela classe do papel (PN/ON).

### Spread de crédito: debêntures IPCA+ contra a NTN-B de referência (ANBIMA)

```python
from brazilfi import ANBIMA

an = ANBIMA()
deb = an.debentures()                                   # último dia útil
ipca = deb[deb["indexer"] == "IPCA +"].dropna(subset=["indicative_rate", "ntnb_reference"])

ntnb = an.curva_ima_dataframe("IMA-B")["rate"]          # taxa indicativa por vencimento
ipca["ntnb_rate"] = ipca["ntnb_reference"].map(ntnb)
ipca["spread_bps"] = (ipca["indicative_rate"] - ipca["ntnb_rate"]) * 100
print(ipca.sort_values("spread_bps", ascending=False)[["code", "issuer", "maturity", "spread_bps"]].head(10))
```

### Rentabilidade de um fundo pela cota diária (CVM)

```python
from brazilfi import CVM

cvm = CVM()
fundo = cvm.fundos(search="verde").iloc[0]          # cadastro (Resolução CVM 175)
cotas = cvm.cotas(fundo["cnpj"], start="2026-01-01")
rentab = cotas["quota"].iloc[-1] / cotas["quota"].iloc[0] - 1
print(f"{fundo['name']}: {rentab:.2%} no ano, PL R$ {cotas['net_assets'].iloc[-1]:,.0f}")
```

### Margem líquida pela DFP (CVM)

```python
from brazilfi import CVM

dre = CVM().dfp("33.000.167/0001-01", 2025, statement="DRE")   # Petrobras, consolidado
receita = dre.loc[dre["account"] == "3.01", "value"].iloc[0]
lucro = dre.loc[dre["account"] == "3.11", "value"].iloc[0]
print(f"Margem líquida 2025: {lucro / receita:.1%}")

# Trimestral (ITR): trimestre isolado vs acumulado no ano ficam na mesma tabela
itr = CVM().itr(9512, 2026, statement="DRE")
print(itr[itr["account"] == "3.01"][["period_start", "period_end", "value"]])
```

> **Nota:** `value` já vem em reais (a CVM publica em milhares). Reapresentações são
> resolvidas automaticamente: fica só a versão mais recente de cada demonstração.

---

## Providers

| Provider | Cobertura | Fonte |
|----------|-----------|-------|
| ✅ **Bacen** (SGS + Olinda) | SELIC, CDI, IPCA, IGP-M, câmbio; expectativas do Focus | `api.bcb.gov.br`, `olinda.bcb.gov.br` |
| ✅ **IPEA** (Ipeadata) | ~3.600 séries macro, regionais e sociais; busca no catálogo | `ipeadata.gov.br` |
| ✅ **IBGE** (SIDRA) | PIB, PNAD, IPCA, população | `servicodados.ibge.gov.br` |
| ✅ **Tesouro Direto** | Títulos ativos + histórico | `tesourotransparente.gov.br` |
| ✅ **B3** (BrAPI.dev + COTAHIST) | Cotações, histórico OHLCV, listagem, opções | `brapi.dev`, `bvmf.bmfbovespa.com.br` |
| ✅ **ANBIMA** | Curvas de toda a família IMA (IMA-B, IMA-B 5/5+, IRF-M, IMA-S, IMA-GERAL), debêntures no secundário | `anbima.com.br` |
| ✅ **CVM** (dados abertos) | Cadastro de fundos e cias abertas, cota diária, DFP, ITR | `dados.cvm.gov.br` |
| 🔜 **ANBIMA** *(v0.5)* | Debêntures, IMA-B 5 e IMA-B 5+ | — |

---

## CLI

```bash
brazilfi --help
```

| Comando | Descrição |
|---------|-----------|
| `selic [--last N] [--meta]` | Taxa SELIC (diária ou meta Copom) |
| `cdi [--last N]` | CDI diário |
| `dolar [--last N]` | Cotação dólar comercial (PTAX) |
| `focus [IPCA] [--freq anual\|mensal\|selic] [--start]` | Expectativas do boletim Focus (Bacen) |
| `ipea CODIGO` | Série do Ipeadata (IPEA) |
| `ipea-search TERMO [--freq Mensal]` | Busca no catálogo do Ipeadata |
| `ipca [--source bacen\|ibge] [--last N] [--acum] [--localidade N6[...]]` | IPCA mensal |
| `pib [--last N]` | PIB trimestral (índice de volume) |
| `desemprego [--last N] [--localidade N3[35]]` | Taxa de desocupação (PNAD Contínua) |
| `populacao [--last N] [--localidade N6[...]]` | População estimada |
| `tesouro` | Tesouro Direto — títulos do último pregão |
| `quote PETR4[,VALE3]` | Cotação atual (B3) |
| `history PETR4 [--range 1y] [--interval 1d]` | Histórico OHLCV (B3) |
| `tickers [--type stock\|fund\|bdr] [--search X] [--limit N]` | Lista tickers (B3) |
| `opcoes PETR4 [--data YYYY-MM-DD] [--tipo call\|put]` | Opções negociadas no pregão (B3) |
| `curva-ima [--indice IMA-B]` | Curva de juros de um índice IMA (ANBIMA) |
| `debentures [--data] [--search X] [--indexador "IPCA +"]` | Debêntures no mercado secundário (ANBIMA) |
| `fundos [--search X] [--limit N]` | Classes de fundos em funcionamento (CVM) |
| `cotas CNPJ [--start] [--end]` | Cota diária de um fundo (CVM) |
| `dfp EMPRESA --ano 2025 [--demonstracao DRE] [--individual] [--itr]` | DFP/ITR de uma companhia (CVM) |

Erros de rede ou de dados saem como uma linha `Erro: ...` com exit code 1, sem traceback.

---

## Arquitetura

```
src/brazilfi/
├── core/              # HttpClient (retry + backoff), cache de arquivos, modelos Pydantic, exceções
├── providers/         # Bacen, IBGE, TesouroDireto, B3, ANBIMA, CVM, IPEA
└── cli.py             # typer + rich
```

Princípios:

- **Async-ready**: `HttpClient` suporta sync e async, com retry em timeout, erro de rede e 5xx.
- **Modelos Pydantic v2**: todos os retornos são tipados e serializáveis.
- **Cache local**: arquivos grandes (CSV do Tesouro, ZIPs da CVM, COTAHIST da B3) ficam em
  `~/.cache/brazilfi/`. Download atômico; pregões passados nunca são rebaixados, o resto
  expira em 24h.
- **Sem credenciais obrigatórias**: Bacen, IBGE, Tesouro, ANBIMA, CVM, IPEA e as opções da B3
  são públicos. Só cotação/histórico via BrAPI pedem um token gratuito para ir além dos 4
  tickers do free tier.

---

## Roadmap

- **v0.6** — CVM: informes de FII, composição de carteira (CDA)
- **v1.0** — API estável, docs completas, async nativo

---

## Contribuindo

```bash
git clone https://github.com/RAFAELDCOELHO/brazilfi.git
cd brazilfi
uv sync --all-extras
uv run ruff check src tests && uv run mypy src && uv run pytest
```

---

## Licença

MIT © Rafael Coelho
