<div align="center">

# brazilfi

**SDK Python unificado para APIs de mercados financeiros brasileiros.**

Bacen · IBGE · Tesouro Direto — uma única biblioteca, uma única API.

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
from brazilfi import Bacen, IBGE, TesouroDireto

# SELIC dos últimos 30 dias
Bacen().selic(last=30).to_dataframe()

# PIB trimestral
IBGE().pib(last=8).to_dataframe()

# Todos os títulos do Tesouro Direto disponíveis hoje
TesouroDireto().available_dataframe()
```

Ou via CLI:

```bash
brazilfi selic --last 30
brazilfi pib --last 8
brazilfi tesouro
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
| **Modelos tipados (Pydantic)** | ✅ | ❌ | ❌ | ❌ |
| **CLI integrada** | ✅ | ❌ | ❌ | ❌ |
| **Async-ready** | ✅ | ❌ | ❌ | ❌ |
| **Status** | Ativo | Ativo | Ativo | **Deprecated** |

---

## Exemplos reais

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

---

## Providers

| Provider | Cobertura | Fonte |
|----------|-----------|-------|
| ✅ **Bacen** (SGS) | SELIC, CDI, IPCA, IGP-M, câmbio | `api.bcb.gov.br` |
| ✅ **IBGE** (SIDRA) | PIB, PNAD, IPCA, população | `servicodados.ibge.gov.br` |
| ✅ **Tesouro Direto** | Títulos ativos + histórico | `tesourotransparente.gov.br` |
| 🚧 **B3** *(v0.3)* | Cotações, histórico, opções | — |
| 🔜 **CVM** *(v0.4)* | Fundos, DFPs | — |
| 🔜 **ANBIMA** *(v0.5)* | Debêntures, IMA | — |

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
| `ipca [--source bacen\|ibge] [--last N]` | IPCA mensal |
| `pib [--last N] [--volume]` | PIB trimestral |
| `desemprego [--last N]` | Taxa de desocupação (PNAD Contínua) |
| `populacao [--last N]` | População estimada |
| `tesouro` | Tesouro Direto — títulos ativos |

---

## Arquitetura
src/brazilfi/
├── core/              # HttpClient, Pydantic models, exceptions
├── providers/         # Bacen, IBGE, TesouroDireto
└── cli.py             # typer + rich

Princípios:

- **Async-ready**: HttpClient suporta sync e async.
- **Modelos Pydantic v2**: todos retornos são tipados e serializáveis.
- **Cache local**: CSVs grandes são cacheados em `~/.cache/brazilfi/`.
- **Zero credentials**: todas as APIs são públicas e gratuitas.

---

## Roadmap

- **v0.3** — Provider B3 (cotações, histórico, opções)
- **v0.4** — Provider CVM (fundos, DFPs)
- **v0.5** — Provider ANBIMA (debêntures, curvas de juros)
- **v1.0** — API estável, docs completas, async nativo

---

## Contribuindo

```bash
git clone https://github.com/RAFAELDCOELHO/brazilfi.git
cd brazilfi
uv sync --all-extras
uv run pytest
```

---

## Licença

MIT © Rafael Coelho
