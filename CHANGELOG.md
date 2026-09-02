# Changelog

All notable changes to brazilfi will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Planned
- Dividendos e fundamentalistas (BrAPI módulos)

## [0.4.0] — 2026-09-02

Cobre o que o roadmap chamava de v0.4 (CVM), v0.5 (ANBIMA) e v0.6 (CDA/FII), mais Focus,
IPEA e opções/COTAHIST da B3. Tem uma quebra pequena no IBGE (abaixo).

### Added
- **CVM**: `carteira(cnpj, month=None)` — composição da carteira (CDA) com os 8 blocos
  unificados, `asset`/`issuer` normalizados e `weight_pct` sobre o PL; `fii(year, cnpj,
  section)` — informe mensal de FII (complemento, ativo_passivo, geral)
- **B3**: `cotahist(ticker, year=None)` — OHLCV diário pelo COTAHIST anual, sem BrAPI nem
  token (streaming do ZIP de ~70 MB, cache local)
- CLI: `cotahist`, `carteira`, `fii`
- **Bacen**: `focus(indicador, freq=...)` — expectativas de mercado do boletim Focus via
  Olinda/OData (anual, mensal, trimestral, por reunião do Copom, inflação 12m, Top 5)
- **IPEA provider** (Ipeadata OData): `search()` no catálogo (~3.600 séries, filtrado
  localmente porque a API ignora `$filter`), `serie()` como `TimeSeries`, `dataframe()` com
  território para séries regionais, `metadata()`
- CLI: `focus`, `ipea`, `ipea-search`
- **ANBIMA**: `curva_ima(index=...)` aceita toda a família IMA (IMA-B, IMA-B 5, IMA-B 5+,
  IRF-M, IRF-M 1, IRF-M 1+, IMA-S, IMA-GERAL, IMA-GERAL-EX-C); `debentures(on=None)` — taxas
  indicativas do mercado secundário de debêntures (arquivo diário `db{aammdd}.txt`), com
  indexador e cupom separados, NTN-B de referência e cache permanente por dia útil
- CLI: `curva-ima --indice`, `debentures`
- **CVM provider** (dados abertos, sem token): `CVM().fundos()` (cadastro de classes da
  Resolução CVM 175, com administrador/gestor do fundo-mãe), `cotas()` (informe diário:
  cota, PL, captação, resgate, cotistas — aceita o layout antigo `CNPJ_FUNDO` e o novo
  `CNPJ_FUNDO_CLASSE`), `companhias()` (cadastro de cias abertas), `dfp()` e `itr()`
  (BPA, BPP, DRE, DRA, DFC, DMPL, DVA; valores já em reais; só a última reapresentação)
- **B3**: `B3().options(ticker, on=None, kind=None)` — cadeia de opções negociadas num
  pregão a partir do COTAHIST diário da B3 (público, sem BrAPI). Separa PETR4/PETR3 pela
  classe do papel e recua até o último pregão publicado quando `on` é omitido
- `core.cache.cached_download()`: download atômico com cache em disco e TTL opcional
  (`None` = arquivo imutável), usado pela CVM e pelo COTAHIST
- CLI: `opcoes`, `fundos`, `cotas`, `dfp` (com `--itr` e `--individual`)
- **ANBIMA provider**: `ANBIMA().curva_ima()` — curva de juros do IMA-B total a partir do
  arquivo completo do IMA (`anbima.com.br/informacoes/ima/arqs/ima_completo.txt`)
- New Pydantic models: `YieldCurve`, `CurvePoint`
- `HttpClient.get_text()` para fontes que servem CSV/TXT em latin-1
- CLI command: `curva-ima`
- **IBGE**: parâmetro `localidade` em `ipca()`, `desemprego()` e `populacao()` —
  UF (`N3[35]`), município (`N6[3550308]`), região metropolitana etc. Default
  continua `N1[all]` (Brasil). `pib()` segue sem o parâmetro porque o SIDRA só
  serve o agregado 1620 em N1, e o IPCA não aceita N3 (apuração por município/RM)
- `IBGE.agregado()` valida o nível territorial contra os metadados do SIDRA e
  levanta `ValueError` em vez de deixar a API devolver série vazia
- Notebook de exemplo `docs/examples/01_analise_macro.ipynb`: SELIC (Bacen) + IPCA e PIB
  (IBGE), juro real ex-post e gráfico; extra opcional `brazilfi[examples]` com matplotlib

### Changed
- `HttpClient` agora repete a requisição também em HTTP 5xx (não só timeout/rede) e segue
  redirects em todos os métodos; `User-Agent` reflete a versão instalada
- CLI: `desemprego`, `populacao` e `ipca --source ibge` aceitam `--localidade`
- CLI: erros da biblioteca (`BrazilFiError`) viram `Erro: ...` + exit code 1 em vez de traceback
- Versão única em `brazilfi.__version__` (hatch `dynamic = ["version"]`)
- CI roda também em Python 3.13

### Fixed
- IBGE: agregados trimestrais (PIB 1620, PNAD 4099) tinham o período `YYYYQQ` lido como
  ano-mês — `202602` virava 2026-02-01 em vez de 2026-04-01 (2º trimestre). Novo
  `AGREGADOS_TRIMESTRAIS` + parâmetro `trimestral` em `agregado()` para outros agregados
- IBGE: `pib(volume=True)` (variável 584) e `ipca(indice=True)` (variável 2266) davam HTTP 500 —
  essas variáveis não existem nos agregados 1620/7060. `pib()` agora se descreve como o que
  sempre foi (índice de volume, média 1995 = 100, única variável do 1620) e
  `ipca(acum_12m=True)` usa a 2265 (acumulado em 12 meses), espelhando `Bacen.ipca()`
- `pyproject.toml`: URLs `SEU_USER` placeholder trocadas pelo repositório real; descrição não
  anuncia mais CVM (ainda não existe)
- Tesouro: download do CSV histórico é atômico (`.part` + rename), com headers de navegador e
  `follow_redirects` — um Ctrl+C no meio não deixa um cache truncado válido por 24h
- README: subtítulo, tabela comparativa e arquitetura cobrem os 5 providers; ANBIMA e v0.4
  não aparecem mais duplicados; "zero credentials" corrigido (B3 pede token fora do free tier)

### Removed
- **Breaking:** `IBGE.pib(volume=...)`, `IBGE.ipca(indice=...)` e `brazilfi pib --volume` —
  estavam quebrados (HTTP 500) desde o 0.2.1
- Tesouro: código morto do endpoint JSON antigo (`_fetch_csv`, `_parse_bond`, URLs
  `rendimento-*-csv`), que nunca era chamado

## [0.3.0] — 2026-04-20

### Added
- **B3 provider** (via BrAPI.dev): cotações ao vivo, histórico OHLCV, listagem de tickers, FIIs, BDRs, ETFs
- New Pydantic models: `Quote`, `OHLCV`
- CLI commands: `quote`, `history`, `tickers`
- Free tier support (4 tickers sem token): PETR4, VALE3, ITUB4, MGLU3
- Token opcional via `BRAZILFI_BRAPI_TOKEN` env var (grátis em https://brapi.dev/register)
- 7 new tests (22 total, 61% coverage)

## [0.2.1] — 2026-04-20

### Added
- **IBGE provider** (SIDRA v3): PIB trimestral, PNAD desemprego, IPCA mensal, população, acesso genérico a qualquer agregado
- **Tesouro Direto provider**: títulos ativos + histórico completo via CSV oficial do Tesouro Transparente (gov.br)
- New Pydantic models: `Bond`, `BondQuote`
- CLI commands: `pib`, `desemprego`, `ipca --source`, `populacao`, `tesouro`
- 10 new tests (15 total)

### Fixed
- IBGE: captura `decimal.InvalidOperation` quando o SIDRA retorna markers de dados faltantes (X, .., -)
- IBGE PIB: adiciona parâmetro obrigatório `classificacao=11255[90707]`
- Tesouro: endpoint JSON antigo substituído por CSV do Tesouro Transparente (mais estável, sem Cloudflare)
- Type hints completos + mypy strict passing

## [0.1.0] — 2026-04-20

### Added
- Initial release
- **Bacen provider** (SGS): SELIC, CDI, IPCA, IGP-M, câmbio, acesso genérico a qualquer série SGS
- Core: `HttpClient` (sync + async), `TimeSeries` model, exceptions hierarchy
- CLI: `selic`, `cdi`, `dolar`, `ipca`
- CI: lint (ruff) + type check (mypy) + tests (pytest) on Python 3.11 and 3.12
- 5 tests, 66% coverage

[Unreleased]: https://github.com/RAFAELDCOELHO/brazilfi/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/RAFAELDCOELHO/brazilfi/releases/tag/v0.4.0
[0.3.0]: https://github.com/RAFAELDCOELHO/brazilfi/releases/tag/v0.3.0
[0.2.1]: https://github.com/RAFAELDCOELHO/brazilfi/releases/tag/v0.2.1
[0.1.0]: https://github.com/RAFAELDCOELHO/brazilfi/releases/tag/v0.1.0
