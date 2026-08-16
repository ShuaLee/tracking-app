"""Optional starter configurations copied into user-owned portfolio views."""

VIEW_TEMPLATES = {
    "overview": {
        "name": "Overview",
        "description": "Portfolio values and holdings.",
        "blocks": [
            {
                "title": "Total value",
                "data_source": "HOLDINGS",
                "presentation": "SUMMARY",
                "configuration": {
                    "aggregations": [{"field": "value", "function": "sum"}]
                },
            },
            {
                "title": "Holdings",
                "data_source": "HOLDINGS",
                "presentation": "TABLE",
                "configuration": {},
            },
        ],
    },
    "income": {
        "name": "Income",
        "description": "Expected annual income without persisting received cash.",
        "blocks": [
            {
                "title": "Expected annual income",
                "data_source": "INCOME",
                "presentation": "SUMMARY",
                "configuration": {
                    "aggregations": [
                        {"field": "annual_income", "function": "sum"}
                    ]
                },
            },
            {
                "title": "Income sources",
                "data_source": "INCOME",
                "presentation": "TABLE",
                "configuration": {},
            },
        ],
    },
    "themes": {
        "name": "Themes",
        "description": "Optional theme allocations and target gaps.",
        "blocks": [
            {
                "title": "Theme allocation",
                "data_source": "THEMES",
                "presentation": "TABLE",
                "configuration": {},
            },
            {
                "title": "Unassigned holdings",
                "data_source": "HOLDINGS",
                "presentation": "TABLE",
                "configuration": {
                    "filters": [
                        {"field": "theme", "operator": "is_null", "value": True}
                    ]
                },
            },
        ],
    },
    "yield": {
        "name": "Yield",
        "description": "Income, current yield, and yield on cost by holding.",
        "blocks": [
            {
                "title": "Expected income",
                "data_source": "HOLDINGS",
                "presentation": "SUMMARY",
                "configuration": {
                    "aggregations": [
                        {"field": "annual_income", "function": "sum"}
                    ]
                },
            },
            {
                "title": "Yield by holding",
                "data_source": "HOLDINGS",
                "presentation": "TABLE",
                "configuration": {
                    "fields": [
                        "asset_name", "group", "annual_income", "current_yield",
                        "yield_on_cost", "value", "currency"
                    ],
                    "sort": [{"field": "current_yield", "direction": "desc"}],
                    "limit": 100,
                },
            },
        ],
    },
    "country": {
        "name": "Country Breakdown",
        "description": "Portfolio value and income grouped by asset country.",
        "blocks": [
            {
                "title": "Country allocation",
                "data_source": "HOLDINGS",
                "presentation": "TABLE",
                "configuration": {
                    "group_by": "country",
                    "aggregations": [
                        {"field": "value", "function": "sum"},
                        {"field": "annual_income", "function": "sum"},
                        {"field": "holding_id", "function": "count"}
                    ],
                    "sort": [{"field": "value", "direction": "desc"}],
                    "limit": 100,
                },
            }
        ],
    },
}
