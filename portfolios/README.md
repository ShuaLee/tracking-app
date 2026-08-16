# Portfolios application

This Django application owns the user's financial structure and analytical configuration. External providers enrich this data but do not replace it as the system of record.

## Package map

- `models/` contains persistent ownership and analytics records.
- `services/` contains write use cases, invariants, market enrichment, and valuation.
- `analytics/` contains expected-income calculations and the configurable View engine.
- `api/` converts HTTP requests and domain objects to JSON.
- `tests/` verifies models, services, integrations, analytics, and API behavior.
- `migrations/` is immutable database history; migration filenames retain their generated names.

Code outside this application should normally import models from `portfolios.models` and call a named service module. HTTP modules should remain thin and must not own financial rules.

## Dependency direction

`api` calls `services` and `analytics`; those layers use `models`. Models do not import API code. Provider-specific behavior remains under `integrations` and is accessed through its normalized service interfaces.
