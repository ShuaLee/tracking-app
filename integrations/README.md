# Integrations

External systems are isolated behind normalized internal contracts.

- `market_data/` provides security search, profiles, quotes, and dividends.
- `brokerage/` provides connection persistence, normalized accounts/positions, and reconciliation.
- `checks.py`, `http.py`, `utils.py`, and `exceptions.py` provide shared integration infrastructure.

Portfolio code should depend on normalized services and contracts, never directly on provider SDK response objects.
