# brazilfi

> SDK Python unificado para APIs de mercados financeiros brasileiros.

[![CI](https://github.com/RAFAELDCOELHO/brazilfi/workflows/CI/badge.svg)](https://github.com/RAFAELDCOELHO/brazilfi/actions)
[![PyPI](https://img.shields.io/pypi/v/brazilfi.svg)](https://pypi.org/project/brazilfi/)
[![Python](https://img.shields.io/pypi/pyversions/brazilfi.svg)](https://pypi.org/project/brazilfi/)

Dados do Banco Central, B3, CVM, Tesouro Direto e IBGE em uma única API limpa, tipada e assíncrona.

## Instalação

```bash
pip install brazilfi
```

## Uso rápido

```python
from brazilfi import Bacen, IBGE, TesouroDireto

# Bacen
selic = Bacen().selic(last=30).to_dataframe()

# IBGE
pib = IBGE().pib(last=8).to_dataframe()
desemprego = IBGE().desemprego(last=4).to_dataframe()

# Tesouro Direto
bonds = TesouroDireto().available_dataframe()
historico_ipca = TesouroDireto().history(bond_type="IPCA+", maturity=2029)
```

## CLI

```bash
brazilfi selic --last 30
brazilfi pib --last 4
brazilfi desemprego
brazilfi ipca --source ibge
brazilfi tesouro
```

## Providers

| Provider | Status | Cobertura |
|----------|--------|-----------|
| Bacen (SGS) | ✅ v0.1 | SELIC, CDI, IPCA, IGP-M, câmbio |
| IBGE (SIDRA) | ✅ v0.2 | PIB, PNAD, IPCA, população |
| Tesouro Direto | ✅ v0.2 | Títulos disponíveis + histórico |
| B3 | 🚧 v0.3 | Cotações, histórico, opções |
| CVM | 🔜 v0.4 | Fundos, DFPs |

## Contribuindo

PRs bem-vindos. Rode `uv sync --all-extras && uv run pytest` antes de abrir.

## Licença

MIT
