# Tracking App — Application Foundations

This repository contains the complete Stage 1 identity/account domain, Stage 2 external-data foundation, Stage 3 manual portfolio core, Stage 4 market-linked and brokerage-synced workflows, and Stage 5 configurable analytics Views. It provides secure identity, centralized entitlements, provider-neutral integrations, permanent ownership models, optional income and themes, and user-defined analytical surfaces.

Manual ownership remains usable when every external provider and cache is offline. Stage 4 enriches that permanent data without making a provider the system of record.

See [Codebase Structure](docs/codebase_structure.md) for the package map and dependency rules. Each major application and each `portfolios` subpackage also has a local README describing its responsibilities.

## Local setup

Requirements: Python 3.12+ and the dependencies in `requirements.txt`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

For Redis-backed market-data caching, start Redis and set `REDIS_URL`. The included Compose service provides a local instance:

```powershell
docker compose up -d redis
```

Without `REDIS_URL`, development and tests use process-local memory caching. Production should configure Redis so cached market data is shared across application workers and users.

Development email is written to the console. Configure the default mailer for a real email provider before deployment.

Run verification with:

```powershell
python manage.py check
python manage.py test
python manage.py makemigrations --check --dry-run
python manage.py check --deploy
```

## Environment

Copy `.env.example` into your environment manager or configure the variables through your deployment platform. Django does not load `.env` files directly.

| Variable | Purpose |
|---|---|
| `DJANGO_SECRET_KEY` | Required production signing secret. |
| `DJANGO_DEBUG` | Use `false` in production. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated host names. |
| `DEFAULT_FROM_EMAIL` | Password-reset sender. |
| `PASSWORD_RESET_CONFIRM_URL` | Frontend URL template; must retain `{uid}` and `{token}`. |
| `DJANGO_SECURE_SSL_REDIRECT` | Defaults to enabled when debug is disabled. |
| `DJANGO_EMAIL_BACKEND` | Console in development; SMTP by default in production. |
| `EMAIL_HOST`, `EMAIL_PORT` | Production SMTP server. |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | SMTP credentials. |
| `EMAIL_USE_TLS`, `EMAIL_USE_SSL` | SMTP transport security; enable at most one. |
| `EMAIL_TIMEOUT` | SMTP timeout in seconds. |
| `REDIS_URL` | Shared market-data Redis connection URL. |
| `FMP_API_KEY` | Backend-only Financial Modeling Prep API key. |
| `SNAPTRADE_CLIENT_ID` | Backend-only SnapTrade commercial client ID. |
| `SNAPTRADE_CONSUMER_KEY` | Backend-only SnapTrade signing secret. |
| `BROKERAGE_CREDENTIAL_ENCRYPTION_KEY` | Fernet key used to encrypt per-user brokerage secrets at rest; required in production. |

Production mode enables secure cookies, HTTPS redirection, HSTS, MIME sniffing protection, and frame denial. Deploy behind HTTPS and set the correct proxy/security configuration for the hosting environment.

## Authentication model

- Email is the unique, normalized login identifier.
- Passwords use Django hashing and configured password validators.
- Authentication uses HTTP-only session cookies.
- CSRF middleware remains enabled. Browser clients should first request `GET /api/v1/auth/csrf/`, then submit the returned token in the `X-CSRFToken` header for unsafe requests.
- Signup atomically creates `User`, `Profile`, a `FREE/ACTIVE` `Subscription`, `My Portfolio`, and its system Ungrouped group exactly once.
- Account deletion currently means authenticated deactivation. It preserves account-related data for the future financial-data deletion policy.

## API

All request bodies are JSON and all routes are under `/api/v1/`.

| Method | Route | Authentication | Responsibility |
|---|---|---|---|
| `GET` | `auth/csrf/` | No | Establish CSRF cookie and return token. |
| `POST` | `auth/signup/` | No | Create and authenticate an account. |
| `POST` | `auth/login/` | No | Start a session. |
| `POST` | `auth/logout/` | Yes | End the session. |
| `POST` | `auth/password/change/` | Yes | Change password and retain the session. |
| `POST` | `auth/password/reset/` | No | Send reset instructions without account enumeration. |
| `POST` | `auth/password/reset/confirm/` | No | Validate reset token and set a new password. |
| `GET` | `me/` | Yes | Return safe current-user data. |
| `PATCH` | `me/` | Yes | Update name or email; email changes require the current password. |
| `DELETE` | `me/` | Yes | Deactivate account after password confirmation. |
| `GET` | `me/subscription/` | Yes | Read subscription state. |
| `GET` | `me/entitlements/` | Yes | Read effective capabilities and limits. |

Signup body:

```json
{
  "email": "user@example.com",
  "password": "a-strong-password",
  "name": "Josh"
}
```

Safe current-user response:

```json
{
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "profile": {"name": "Josh"},
    "subscription": {"plan": "FREE", "status": "ACTIVE"}
  }
}
```

Errors use a stable envelope:

```json
{
  "error": {
    "code": "invalid_request",
    "message": "Signup data is invalid.",
    "fields": {"email": ["Enter a valid email address."]}
  }
}
```

## Entitlements

Call `subscriptions.entitlements.has(user, capability)` and `subscriptions.entitlements.limit(user, resource)` rather than checking plan names throughout the application. Default policy supports `FREE`, `PRO`, and the future `MANAGER` value. Exact limits can be overridden centrally with the `ENTITLEMENT_POLICY` Django setting.

The Manager plan value does not enable unimplemented professional features. Organizations, memberships, roles, and client portfolios belong to the future professional domain.

## Architectural assumptions

- `User` owns authentication and security state.
- `Profile` contains non-security personal/product information and currently stores only one display name.
- `Subscription` contains commercial state and never changes user identity.
- UUID primary keys are used for account-domain models.
- Public APIs cannot modify subscription plans or statuses; development-time changes are available through Django admin.
- The app exposes only current-user resources, so there is no user-supplied object identifier that could cross account boundaries.
- Billing and professional organizations remain out of scope for these foundation stages.

## Stage 2 external-data foundation

Stage 2 deliberately does not create portfolio, asset, holding, or global security tables. It proves and normalizes provider behavior so the portfolio domain can consume stable internal contracts later.

### Market data

`MarketDataService` provides:

- company/security search;
- individual and bulk quotes;
- security profiles and small identity fingerprints;
- dividend events;
- normalized Decimal/date/datetime values;
- Redis-backed shared cache keys;
- separate fresh and stale lifetimes;
- negative caching for missing identifiers;
- stale-data fallback during provider outages;
- provider access when Redis is unavailable;
- normalized authentication, rate-limit, unavailable, response, and not-found errors.

The FMP adapter uses the current stable `/search-name`, `/quote`, `/batch-quote`, `/profile`, and `/dividends` endpoints. The API key is sent in a backend request header and is never exposed through a browser API.

```python
from integrations.market_data import MarketDataService

market_data = MarketDataService()
results = market_data.search("Apple")
quote = market_data.get_quote("AAPL")
tsx_quote = market_data.get_quote("SHOP", exchange="TSX")
quotes = market_data.get_quotes(["AAPL", "MSFT"])
profile = market_data.get_profile("AAPL")
dividends = market_data.get_dividends("AAPL")
```

Run a read-only live provider check after configuring `FMP_API_KEY`:

```powershell
python manage.py verify_market_data --query Apple --symbol AAPL
```

### Brokerage data

`BrokerageService` and the SnapTrade adapter provide:

- provider health checking;
- commercial-user registration, secret rotation, and deletion;
- connection-portal link generation and reconnect support;
- connection listing, refresh, and disconnect behavior;
- normalized accounts;
- normalized account positions using stable account/security identifiers;
- compatibility with current and legacy SnapTrade position payloads;
- provider-reported values and average-cost data when supplied;
- provider-neutral errors and partial/empty field handling.

```python
from integrations.brokerage import BrokerageService

brokerage = BrokerageService()
registered = brokerage.register_user("immutable-app-user-uuid")
# Store registered.user_secret securely; its repr intentionally omits the value.
portal = brokerage.create_connection_portal(registered)
accounts = brokerage.list_accounts(registered)
positions = brokerage.list_positions(registered, accounts[0].provider_account_id)
```

SnapTrade recommends an immutable identifier rather than an email for its `userId`. The application User UUID is used. User secrets are encrypted at rest and are never logged or returned to the browser.

Run a read-only provider status check after configuring partner credentials:

```powershell
python manage.py verify_brokerage
```

To include account and position reads, configure `SNAPTRADE_TEST_USER_ID` and `SNAPTRADE_TEST_USER_SECRET` in the process environment. The command intentionally does not accept the secret as a command-line argument, which would expose it to process listings.

### Provider contracts

Provider payloads stop at the adapter boundary. Future portfolio code should depend only on dataclasses in:

- `integrations.market_data.contracts`
- `integrations.brokerage.contracts`

This keeps FMP and SnapTrade replaceable and prevents either provider's schema from becoming the permanent ownership model.

## Stage 3 manual portfolio core

The permanent ownership hierarchy is:

```text
User
└── Portfolio
    └── Group [SYSTEM | MANUAL | SYNCED]
        └── Holding
            └── Asset
                └── AssetType
```

Stage 3 includes:

- one automatic system Ungrouped group per portfolio;
- user-created manual groups;
- seeded built-in asset types and isolated custom types;
- arbitrary manual assets using flexible JSON metadata;
- quantity, average cost, total manual value, cost basis, and gain/loss;
- safe movement between manual/system groups;
- safe manual-group deletion by moving holdings to Ungrouped;
- protected system groups, synced groups, and provider-owned holdings;
- duplicate holdings by design;
- portfolio totals grouped by Group and AssetType;
- explicit unknown-value counts rather than treating missing values as zero;
- FREE/PRO/MANAGER portfolio and holding limit enforcement;
- object-level authorization on every portfolio-scoped API.

`manual_value` represents the holding's total current value. `average_cost` is a per-unit cost, so cost basis is `quantity × average_cost`. This supports both single real-world assets and divisible holdings without implying false unit pricing.

### Portfolio API

All routes require an authenticated session:

| Method | Route | Responsibility |
|---|---|---|
| `GET/POST` | `/api/v1/portfolios/` | List or create portfolios. |
| `GET/PATCH/DELETE` | `/api/v1/portfolios/{id}/` | Read, edit, or delete a portfolio. |
| `GET/POST` | `/api/v1/portfolios/{id}/groups/` | List or create manual groups. |
| `GET/PATCH/DELETE` | `/api/v1/portfolios/{id}/groups/{groupId}/` | Manage a manual group. |
| `GET/POST` | `/api/v1/asset-types/` | List available types or create a custom type. |
| `GET/PATCH/DELETE` | `/api/v1/asset-types/{id}/` | Read or manage a custom type. |
| `GET/POST` | `/api/v1/portfolios/{id}/holdings/` | List or create manual holdings. |
| `GET/PATCH/DELETE` | `/api/v1/portfolios/{id}/holdings/{holdingId}/` | Read or manage a manual holding. |
| `GET` | `/api/v1/portfolios/{id}/overview/` | Current valuation rollups. |

Example manual holding request:

```json
{
  "name": "123 Main Street",
  "asset_type_id": "home-asset-type-uuid",
  "group_id": "real-estate-group-uuid",
  "native_currency": "CAD",
  "quantity": "1",
  "average_cost": "500000",
  "cost_currency": "CAD",
  "manual_value": "750000",
  "metadata": {"city": "Toronto"}
}
```

Omit `group_id` to place the holding in Ungrouped. Stage 3 endpoints never create market-linked or synced ownership; those flows must enter through the Stage 4 services so provider-controlled state cannot be corrupted by manual CRUD.

## Stage 4 market and brokerage workflows

Market-linked holdings store a canonical symbol, exchange, and small issuer identity fingerprint. Each valuation validates that fingerprint before accepting a quote. If identity changes, the asset enters `NEEDS_RELINK`; only the explicit relink endpoint can accept the new identity. Valuation preference is live/cached market quote, provider value, manual value, then unavailable.

Overview totals include only values already denominated in the portfolio base currency. Until a dedicated FX source is introduced, other currencies remain visible on individual holdings and are counted as currency mismatches instead of being silently added to an invalid total.

Brokerage access is gated by the `brokerage_sync` entitlement. A connection is imported into exactly one user-owned portfolio. Each provider account becomes a synced group and each position is reconciled by stable provider identifiers. Successful complete snapshots close missing positions instead of deleting them. Provider failures leave the last successful snapshot intact. Refresh is a separate asynchronous provider operation and never implies that reconciliation completed.

| Method | Route | Responsibility |
|---|---|---|
| `GET` | `/api/v1/market/search/?q={query}` | Search provider-backed securities. |
| `POST` | `/api/v1/portfolios/{id}/market-holdings/` | Create a canonical market-linked holding. |
| `POST` | `/api/v1/portfolios/{id}/holdings/{holdingId}/relink/` | Explicitly accept a replacement market identity. |
| `POST` | `/api/v1/brokerage/portal/` | Register the brokerage identity if needed and create a connection portal URL. |
| `GET/POST` | `/api/v1/brokerage/connections/` | List saved connections or import provider connections into a portfolio. |
| `POST` | `/api/v1/brokerage/connections/{id}/sync/` | Reconcile accounts and positions. |
| `POST` | `/api/v1/brokerage/connections/{id}/refresh/` | Queue a provider refresh without claiming sync completion. |
| `DELETE` | `/api/v1/brokerage/connections/{id}/` | Disconnect while preserving imported history. |

Generate the production encryption secret once and place it in the deployment secret manager:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Stage 5 configurable Views

Stage 5 does not create permanent Theme or Cash Flow pages. A user explicitly creates and names a View, starts blank, copies an optional starter, or copies one of their existing Views. Each View can include every portfolio holding or an explicit reusable selection of holdings. Copying a View creates independent configuration that can then be renamed and changed.

Blocks support `HOLDINGS`, `INCOME`, `THEMES`, and `GROUPS` data sources with `TABLE`, `LIST`, and `SUMMARY` presentations. Holdings expose theme, country, sector, industry, symbol, yield, income, value, and gain dimensions. Configuration is a validated declarative query containing approved fields, filters, up to three grouping dimensions, aggregations, sorting, and a result limit. Arbitrary SQL and formulas are rejected. The schema endpoint lets a client build the editor without duplicating the server's allowlist.

Expected income consists of optional manual recurring rules plus a trailing-twelve-month dividend projection for safely linked public securities. It is distinct from actual received cash, which is intentionally not persisted yet. Income, valuation, yield, theme allocation, target gaps, and group totals are calculated from underlying holdings when a View is rendered.

| Method | Route | Responsibility |
|---|---|---|
| `GET` | `/api/v1/view-schema/` | Discover supported data sources, fields, operations, and presentations. |
| `GET` | `/api/v1/view-templates/` | List optional starter configurations. |
| `GET/POST` | `/api/v1/portfolios/{id}/views/` | List or create named Views, blank, from a starter, or copied from another View. |
| `GET/PATCH/DELETE` | `/api/v1/portfolios/{id}/views/{viewId}/` | Manage a View without touching financial data. |
| `GET/POST` | `/api/v1/portfolios/{id}/views/{viewId}/blocks/` | List or add configured blocks. |
| `GET/PATCH/DELETE` | `/api/v1/portfolios/{id}/views/{viewId}/blocks/{blockId}/` | Configure, move, or remove a block. |
| `GET` | `/api/v1/portfolios/{id}/views/{viewId}/render/` | Resolve the complete View from current portfolio data. |
| `GET/POST` | `/api/v1/portfolios/{id}/themes/` | List or create optional themes/subthemes. |
| `POST` | `/api/v1/portfolios/{id}/themes/{themeId}/holdings/` | Assign or move a holding to one theme. |
| `DELETE` | `/api/v1/portfolios/{id}/holdings/{holdingId}/theme/` | Return a holding to the unassigned state. |
| `PATCH` | `/api/v1/portfolios/{id}/holdings/{holdingId}/classification/` | Set country, sector, and industry used by custom breakdowns. |
| `GET/POST` | `/api/v1/portfolios/{id}/income-rules/` | Manage optional recurring expected-income inputs. |
| `GET` | `/api/v1/portfolios/{id}/income-projections/` | Read manual and market-derived expected income. |

The complete model, query contract, and lifecycle rules are documented in `docs/configurable_portfolio_views.md`.
