# Portfolio analytics

- `income.py`: normalized expected-income projections from manual rules and public dividends.
- `configuration.py`: safe declarative filtering, grouping, aggregation, sorting, and validation.
- `engine.py`: scoped rows and rendering for holdings, income, themes, and Groups.
- `services.py`: theme, income-rule, saved-View, and block lifecycle operations.
- `templates.py`: optional starter configurations copied into user-owned Views.

Analytics never owns holdings or market data. A saved View stores presentation and scope; rendering always reads the portfolio's current underlying records.
