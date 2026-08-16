# Portfolio tests

- `test_models.py`: database constraints and model invariants.
- `test_services.py`: ownership lifecycle behavior and entitlements.
- `test_market.py`: market linking and valuation fallbacks.
- `test_api.py`: ownership HTTP contracts and access control.
- `test_analytics.py`: themes, income, View configuration, and rendering.
- `test_analytics_api.py`: analytics HTTP workflows.
- `factories.py`: small shared test constructors.

Tests should be added at the lowest layer that proves an invariant, with API coverage added for public request/response contracts.
