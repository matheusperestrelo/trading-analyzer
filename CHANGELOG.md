# Changelog

## [unreleased] — 2026-05-05

### Adicionado
- `src/collectors/base.py`: `BaseCollector` (ABC) + `CollectorResult` (Pydantic)
- `src/collectors/schemas.py`: `FundamentosSnapshotSchema` + `CotacaoDiariaSchema` com coerção de tipos sujos de scraping (`%`, `B`, `M`, vírgulas, `"-"`, `"N/A"`)
- `src/collectors/finviz_collector.py`: `FinvizCollector` com scraping httpx + selectolax, cache Redis (TTL 86400s), degradação graciosa sem Redis, log DEBUG por campo
- `src/collectors/yfinance_collector.py`: `YfinanceCollector` com fallback `.info` → `fast_info`, `collect_history()` retornando `list[CotacaoDiariaSchema]`, cache Redis (TTL 300s), sanitização de NaN/inf
- `tests/test_collectors.py`: suite pytest com 11 testes (FinvizCollector, YfinanceCollector, Schemas) — totalmente isolada via mocks, sem dependência de rede ou Docker

### Corrigido
- `config/settings.yaml`: sintaxe YAML inválida em `port:6379` (faltava espaço)
