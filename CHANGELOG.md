# Changelog

All notable changes to brazilfi will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Planned
- B3 provider (cotações, histórico, opções)
- CLI tests
- ANBIMA provider (curvas IMA)

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

[Unreleased]: https://github.com/RAFAELDCOELHO/brazilfi/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/RAFAELDCOELHO/brazilfi/releases/tag/v0.2.1
[0.1.0]: https://github.com/RAFAELDCOELHO/brazilfi/releases/tag/v0.1.0
