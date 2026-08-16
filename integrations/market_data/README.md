# Market-data integration

- `contracts.py`: provider-neutral security, quote, profile, and dividend values.
- `service.py`: cache-aware facade used by the portfolio domain.
- `providers/`: provider adapters; currently FMP.
- `management/commands/verify_market_data.py`: live configuration verification.
- `tests/`: adapter normalization, caching, HTTP, and system-check coverage.

Frequently changing market data remains external/cache data rather than permanent portfolio ownership state.
