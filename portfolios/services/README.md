# Portfolio services

- `holdings.py`: portfolio, Group, asset-type, and manual-holding use cases.
- `market_data.py`: creation and relinking of market-enriched holdings.
- `valuation.py`: current valuation resolution and fallback behavior.

Services are the mutation boundary. They enforce entitlements, lock records where concurrency matters, validate complete models, and raise domain exceptions that the API translates into responses.
