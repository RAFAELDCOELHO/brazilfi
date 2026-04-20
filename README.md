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
from brazilfi import Bacen

bc = Bacen()

# SELIC últimos 30 dias
selic = bc.selic(last=30)
print(selic.to_dataframe())

# IPCA acumulado 12 meses
ipca = bc.ipca(last=12, acum_12m=True)

# Qualquer série SGS pelo código
cambio_real_euro = bc.series(code=21619, last=100, name="Euro/BRL")
```

## CLI

```bash
brazilfi selic --last 30
brazilfi ipca --acum
brazilfi dolar --last 7
```

## Providers

| Provider | Status | Cobertura |
|----------|--------|-----------|
| Bacen (SGS) | v0.1 | SELIC, CDI, IPCA, IGP-M, câmbio |
| IBGE | v0.2 | PIB, PNAD, séries macro |
| Tesouro Direto | v0.3 | Preços e taxas de títulos |
| B3 | v0.4 | Cotações, histórico, opções |
| CVM | v0.5 | Fundos, DFPs |

## Contribuindo

PRs bem-vindos. Rode `uv sync --all-extras && uv run pytest` antes de abrir.

## Licença

MIT
