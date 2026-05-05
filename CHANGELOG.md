# Changelog

## [unreleased] — 2026-05-05

### Adicionado
- `src/collectors/base.py`: `BaseCollector` (ABC) + `CollectorResult` (Pydantic)
- `src/collectors/schemas.py`: `FundamentosSnapshotSchema` + `CotacaoDiariaSchema` com coerção de tipos sujos de scraping (`%`, `B`, `M`, vírgulas, `"-"`, `"N/A"`)
