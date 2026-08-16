# Portfolio models

- `portfolio.py`: `Portfolio` and ownership `Group` records.
- `assets.py`: asset types, portfolio-scoped asset identity, and owned `Holding` positions.
- `analytics.py`: themes, expected-income rules, saved Views, blocks, and selected-holding scope.
- `validators.py`: shared currency and country-code validators.
- `__init__.py`: the stable public import surface (`from portfolios.models import ...`).

Cross-model ownership checks belong in `clean()`. Multi-record operations, permissions, limits, and provider calls belong in services rather than model methods.
