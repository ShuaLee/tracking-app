# Configurable Portfolio Views

## Product contract

A View is a saved analytical presentation of a portfolio. It does not own or copy holdings, values, themes, or income. No View is created automatically, and users can use the portfolio normally without creating themes or income rules.

The creation flow is:

1. Create and name a View.
2. Include all holdings or choose a reusable subset of holdings.
3. Start blank, copy an optional starter template, or copy an existing View.
4. Add table, list, or summary blocks.
5. Select a data source and approved fields.
6. Configure filters, grouping, aggregation, sorting, and layout.
7. Render against current portfolio data.

Deleting a View cascades only to its blocks. It never deletes portfolio data. Deleting a theme unassigns its directly assigned holdings, while a theme with children must be reorganized before deletion.

## Permanent and derived data

Permanent optional data:

- `Theme`: a user-created portfolio classification with an optional parent and allocation target.
- `ThemeAssignment`: assigns one Holding to one leaf classification, preventing double counting.
- `IncomeRule`: a user-provided recurring expected-income assumption attached to a Holding.
- `PortfolioView`: a named saved View.
- `ViewHoldingSelection`: an optional selected-holding scope for a View; `ALL` Views need no selection rows.
- `ViewBlock`: layout and validated query configuration.
- Asset `country_code`, `sector`, and `industry`: editable classifications used by breakdowns. Market-linked security creation can seed them from provider profile data.

Derived data:

- current holding values and gains;
- trailing-twelve-month dividends;
- annual and monthly-equivalent expected income;
- current yield and yield on cost;
- theme and Group values, income, allocations, and target gaps;
- filtered, grouped, and aggregated block rows.

Actual cash receipts are not represented by `IncomeRule`. A future transaction/history domain can persist received cash without changing expected-income assumptions.

## Block configuration

Supported data sources are `HOLDINGS`, `INCOME`, `THEMES`, and `GROUPS`. Supported presentations are `TABLE`, `LIST`, and `SUMMARY`. A block always inherits its parent View's all-or-selected holding scope, so holdings, income, theme allocation, and Group totals describe the same asset set.

Configuration example:

```json
{
  "fields": ["asset_name", "theme", "annual_income", "current_yield"],
  "filters": [
    {"field": "annual_income", "operator": "greater_than", "value": "0"}
  ],
  "group_by": ["currency", "theme"],
  "aggregations": [
    {"field": "annual_income", "function": "sum"}
  ],
  "sort": [
    {"field": "annual_income", "direction": "desc"}
  ],
  "limit": 100
}
```

The server maintains the field and operation allowlist. Unknown keys, fields, operations, raw formulas, and SQL are rejected. A client should read `/api/v1/view-schema/` rather than maintain a separate allowlist.

`group_by` accepts one field or up to three fields. Income money aggregations must either group by `currency` or filter to exactly one currency, preventing mixed-currency totals.

## Currency behavior

Holding, theme, and Group analytics operate in the Portfolio base currency. Values in another currency remain visible in the underlying holding/income data but are not silently mixed into a base-currency total. Income projections retain their own currency so a View can filter or group them safely. FX conversion requires a future explicit exchange-rate source.

## Templates

`overview`, `income`, `themes`, `yield`, and `country` are optional starter configurations. Choosing one copies its blocks into a normal user-owned View. `yield` focuses on expected income, current yield, and yield on cost; `country` groups value, expected income, and holding count by country. Templates do not remain linked to the View and do not create classification or income records. Every copied block can be edited, moved, or deleted.

An existing View can also be supplied as `source_view_id` when creating a View. Its description, scope, holding selection, and blocks are copied; the new View has no ongoing link to its source. The caller can override `scope_mode`, including converting a selected copy to `ALL`.

## Classification behavior

Country uses a normalized two-letter ISO code. Country, sector, and industry can be updated through `PATCH /api/v1/portfolios/{portfolioId}/holdings/{holdingId}/classification/`, including for provider-synced holdings. This changes the portfolio-owned Asset classification only; it does not mutate provider-controlled quantity, cost, or value fields. An empty classification remains valid and appears as an unclassified value in grouped output.
