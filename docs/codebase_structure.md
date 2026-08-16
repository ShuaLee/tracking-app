# Codebase Structure

The project is organized by business domain first and technical layer second.

```text
config/                    Django configuration
users/                     identity and Profile
subscriptions/             plans, entitlements, and limits
integrations/
  market_data/             provider-neutral market data and FMP adapter
  brokerage/               provider-neutral brokerage sync and SnapTrade adapter
portfolios/
  models/                  persistent ownership and analytics records
  services/                ownership mutations, market linking, and valuation
  analytics/               income and configurable View behavior
  api/                     HTTP parsing and JSON presentation
  tests/                   portfolio behavior by layer
docs/                      product and architecture documentation
```

## Dependency rules

1. API modules delegate business decisions to services.
2. Services enforce multi-record invariants and entitlements.
3. Models own local record constraints and relationships.
4. Portfolio integrations use normalized provider services, not provider SDK objects.
5. Analytics reads portfolio truth and stores only user configuration or explicit assumptions.
6. Migrations are historical database records and are not reorganized after release.
