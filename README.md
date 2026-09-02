<div align="center">

# brazilfi


**SDK Python unificado para APIs de mercados financeiros brasileiros.**

Bacen · IBGE · Tesouro Direto · B3 · ANBIMA — uma única biblioteca, uma única API.

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
from brazilfi import ANBIMA, B3, Bacen, IBGE, TesouroDireto

# SELIC dos últimos 30 dias
Bacen().selic(last=30).to_dataframe()

# PIB trimestral
IBGE().pib(last=8).to_dataframe()

# Títulos do Tesouro Direto no último pregão (D-1)
TesouroDireto().available_dataframe()

# Cotação PETR4 (B3 via BrAPI)
B3().quote("PETR4")

# Curva de juros do IMA-B (ANBIMA)
ANBIMA().curva_ima_dataframe()
```

Ou via CLI:

```bash
brazilfi selic --last 30
brazilfi pib --last 8
brazilfi tesouro
brazilfi quote PETR4,VALE3
brazilfi curva-ima
```

---

## Por que brazilfi

Dados brasileiros estão espalhados em **APIs fragmentadas, mal documentadas e sem SDK oficial**. Cada dev que quer construir algo financeiro reinventa a roda: parser de XML do Bacen, scraping de CSV do Tesouro, SIDRA aninhado do IBGE.

`brazilfi` resolve isso com uma API única, tipada e testada.

| | brazilfi | python-bcb | sidrapy | investpy |
|---|:---:|:---:|:---:|:---:|
| **Bacen (SGS)** | ✅ | ✅ | ❌ | ❌ |
| **IBGE (SIDRA)** | ✅ | ❌ | ✅ | ❌ |
| **Tesouro Direto** | ✅ | ❌ | ❌ | ❌ |
| **B3** (cotações, OHLCV) | ✅ | ❌ | ❌ | ✅ |
| **ANBIMA** (curva IMA-B) | ✅ | ❌ | ❌ | ❌ |
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

> **Nota:** o provider B3 usa a [BrAPI.dev](https://brapi.dev). Sem token, apenas
> 4 tickers (PETR4, VALE3, ITUB4, MGLU3). Token gratuito libera todos os ativos.

---

## Providers

| Provider | Cobertura | Fonte |
|----------|-----------|-------|
| ✅ **Bacen** (SGS) | SELIC, CDI, IPCA, IGP-M, câmbio | `api.bcb.gov.br` |
| ✅ **IBGE** (SIDRA) | PIB, PNAD, IPCA, população | `servicodados.ibge.gov.br` |
| ✅ **Tesouro Direto** | Títulos ativos + histórico | `tesourotransparente.gov.br` |
| ✅ **B3** (BrAPI.dev) | Cotações, histórico OHLCV, listagem | `brapi.dev` |
| ✅ **ANBIMA** (IMA) | Curva de juros do IMA-B total | `anbima.com.br` |
| 🔜 **CVM** *(v0.4)* | Fundos, DFPs | — |
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
| `ipca [--source bacen\|ibge] [--last N] [--acum] [--localidade N6[...]]` | IPCA mensal |
| `pib [--last N]` | PIB trimestral (índice de volume) |
| `desemprego [--last N] [--localidade N3[35]]` | Taxa de desocupação (PNAD Contínua) |
| `populacao [--last N] [--localidade N6[...]]` | População estimada |
| `tesouro` | Tesouro Direto — títulos do último pregão |
| `quote PETR4[,VALE3]` | Cotação atual (B3) |
| `history PETR4 [--range 1y] [--interval 1d]` | Histórico OHLCV (B3) |
| `tickers [--type stock\|fund\|bdr] [--search X] [--limit N]` | Lista tickers (B3) |
| `curva-ima` | Curva de juros do IMA-B (ANBIMA) |

Erros de rede ou de dados saem como uma linha `Erro: ...` com exit code 1, sem traceback.

---

## Arquitetura

```
src/brazilfi/
├── core/              # HttpClient (retry + backoff), modelos Pydantic, exceções
├── providers/         # Bacen, IBGE, TesouroDireto, B3, ANBIMA
└── cli.py             # typer + rich
```

Princípios:

- **Async-ready**: `HttpClient` suporta sync e async, com retry em timeout, erro de rede e 5xx.
- **Modelos Pydantic v2**: todos os retornos são tipados e serializáveis.
- **Cache local**: o CSV histórico do Tesouro (~15 MB) fica em `~/.cache/brazilfi/` por 24h.
- **Sem credenciais obrigatórias**: Bacen, IBGE, Tesouro e ANBIMA são públicos. Só o B3
  (BrAPI) pede um token gratuito para ir além dos 4 tickers do free tier.

---

## Roadmap

- **v0.4** — Provider CVM (fundos, DFPs, informes)
- **v0.5** — ANBIMA: debêntures, IMA-B 5 e IMA-B 5+
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
