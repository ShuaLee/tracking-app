"""Validation and execution primitives for declarative view-block queries."""

from copy import deepcopy

from django.core.exceptions import ValidationError


SOURCE_FIELDS = {
    "HOLDINGS": {
        "holding_id", "asset_name", "group", "asset_type", "theme",
        "country", "sector", "industry", "symbol",
        "quantity", "average_cost", "cost_basis", "value", "currency",
        "gain_loss", "annual_income", "current_yield", "yield_on_cost", "source",
        "monthly_income", "valuation_source", "stale",
    },
    "INCOME": {
        "holding_id", "asset_name", "group", "theme", "income_name",
        "income_type", "annual_income", "monthly_income", "currency", "source", "frequency",
        "stale",
    },
    "THEMES": {
        "theme_id", "theme", "parent_theme", "target_percentage", "value",
        "currency", "annual_income", "monthly_income", "holding_count", "allocation_percentage",
        "target_gap",
    },
    "GROUPS": {
        "group_id", "group", "mode", "value", "currency", "annual_income",
        "monthly_income", "holding_count", "allocation_percentage",
    },
}

NUMERIC_FIELDS = {
    "quantity", "average_cost", "cost_basis", "value", "gain_loss",
    "annual_income", "monthly_income", "current_yield", "yield_on_cost", "target_percentage",
    "holding_count", "allocation_percentage", "target_gap",
}

FILTER_OPERATORS = {
    "equals", "not_equals", "greater_than", "greater_or_equal", "less_than",
    "less_or_equal", "contains", "in", "is_null",
}
AGGREGATIONS = {"sum", "average", "count", "minimum", "maximum"}
CONFIGURATION_KEYS = {"fields", "filters", "group_by", "aggregations", "sort", "limit"}

DEFAULTS = {
    ("HOLDINGS", "TABLE"): {
        "fields": ["asset_name", "group", "asset_type", "value", "currency"],
        "sort": [{"field": "asset_name", "direction": "asc"}],
        "limit": 100,
    },
    ("HOLDINGS", "LIST"): {
        "fields": ["asset_name", "value", "currency"], "limit": 100
    },
    ("HOLDINGS", "SUMMARY"): {
        "aggregations": [{"field": "value", "function": "sum"}]
    },
    ("INCOME", "TABLE"): {
        "fields": [
            "asset_name", "income_name", "income_type", "annual_income", "currency"
        ],
        "sort": [{"field": "annual_income", "direction": "desc"}],
        "limit": 100,
    },
    ("INCOME", "LIST"): {
        "fields": ["asset_name", "annual_income", "currency"], "limit": 100
    },
    ("INCOME", "SUMMARY"): {
        "group_by": "currency",
        "aggregations": [{"field": "annual_income", "function": "sum"}]
    },
    ("THEMES", "TABLE"): {
        "fields": [
            "theme", "value", "allocation_percentage", "target_percentage", "target_gap"
        ],
        "sort": [{"field": "theme", "direction": "asc"}],
        "limit": 100,
    },
    ("THEMES", "LIST"): {
        "fields": ["theme", "value", "allocation_percentage"], "limit": 100
    },
    ("THEMES", "SUMMARY"): {
        "aggregations": [{"field": "value", "function": "sum"}]
    },
    ("GROUPS", "TABLE"): {
        "fields": ["group", "mode", "value", "allocation_percentage", "annual_income"],
        "sort": [{"field": "group", "direction": "asc"}],
        "limit": 100,
    },
    ("GROUPS", "LIST"): {
        "fields": ["group", "value", "allocation_percentage"], "limit": 100
    },
    ("GROUPS", "SUMMARY"): {
        "aggregations": [{"field": "value", "function": "sum"}]
    },
}


def effective_configuration(data_source, presentation, configuration):
    result = deepcopy(DEFAULTS.get((data_source, presentation), {}))
    result.update(configuration or {})
    if configuration and (
        "aggregations" in configuration or "group_by" in configuration
    ) and "sort" not in configuration:
        result.pop("sort", None)
    return result


def validate_block_configuration(data_source, presentation, configuration):
    fields_available = SOURCE_FIELDS.get(data_source)
    if fields_available is None:
        raise ValidationError({"data_source": "Unsupported block data source."})
    if presentation not in {"TABLE", "LIST", "SUMMARY"}:
        raise ValidationError({"presentation": "Unsupported block presentation."})
    if not isinstance(configuration, dict):
        raise ValidationError({"configuration": "Configuration must be an object."})
    unknown = sorted(set(configuration) - CONFIGURATION_KEYS)
    if unknown:
        raise ValidationError({
            "configuration": f"Unknown configuration key(s): {', '.join(unknown)}."
        })
    config = effective_configuration(data_source, presentation, configuration)
    fields = config.get("fields", [])
    if not isinstance(fields, list) or len(fields) > 30 or any(
        field not in fields_available for field in fields
    ):
        raise ValidationError({"configuration": "Fields contain unsupported values."})

    filters = config.get("filters", [])
    if not isinstance(filters, list) or len(filters) > 20:
        raise ValidationError({"configuration": "Filters must be a list of at most 20 items."})
    for item in filters:
        if not isinstance(item, dict) or set(item) - {"field", "operator", "value"}:
            raise ValidationError({"configuration": "Each filter has an invalid shape."})
        if item.get("field") not in fields_available or item.get("operator") not in FILTER_OPERATORS:
            raise ValidationError({"configuration": "Filter field or operator is unsupported."})
        if item["operator"] != "is_null" and "value" not in item:
            raise ValidationError({"configuration": "Filter value is required."})
        if item["operator"] == "in" and not isinstance(item.get("value"), list):
            raise ValidationError({"configuration": "The in operator requires a list value."})
        if (
            item["operator"] == "is_null"
            and "value" in item
            and not isinstance(item["value"], bool)
        ):
            raise ValidationError({
                "configuration": "The is-null operator requires a boolean value."
            })

    group_by = config.get("group_by")
    group_fields = (
        group_by
        if isinstance(group_by, list)
        else [group_by]
        if group_by is not None
        else []
    )
    if (isinstance(group_by, list) and not group_by) or len(group_fields) > 3 or any(
        not isinstance(field, str) or field not in fields_available
        for field in group_fields
    ):
        raise ValidationError({"configuration": "Group-by field is unsupported."})

    aggregations = config.get("aggregations", [])
    if not isinstance(aggregations, list) or len(aggregations) > 10:
        raise ValidationError({
            "configuration": "Aggregations must be a list of at most 10 items."
        })
    for item in aggregations:
        if not isinstance(item, dict) or set(item) != {"field", "function"}:
            raise ValidationError({"configuration": "Each aggregation has an invalid shape."})
        field = item.get("field")
        function = item.get("function")
        if field not in fields_available or function not in AGGREGATIONS:
            raise ValidationError({"configuration": "Aggregation is unsupported."})
        if function != "count" and field not in NUMERIC_FIELDS:
            raise ValidationError({
                "configuration": "Only numeric fields can use this aggregation."
            })
    if presentation == "SUMMARY" and not aggregations:
        raise ValidationError({"configuration": "Summary blocks require an aggregation."})
    if group_by is not None and not aggregations:
        raise ValidationError({"configuration": "Grouped blocks require an aggregation."})
    income_money_aggregation = data_source == "INCOME" and any(
        item["field"] in {"annual_income", "monthly_income"}
        and item["function"] != "count"
        for item in aggregations
    )
    currency_filter = any(
        item.get("field") == "currency"
        and (
            item.get("operator") == "equals"
            or (
                item.get("operator") == "in"
                and len(item.get("value", [])) == 1
            )
        )
        for item in filters
    )
    if income_money_aggregation and "currency" not in group_fields and not currency_filter:
        raise ValidationError({
            "configuration": (
                "Income totals must group by currency or filter to one currency."
            )
        })

    sorting = config.get("sort", [])
    if not isinstance(sorting, list) or len(sorting) > 3:
        raise ValidationError({"configuration": "Sort must be a list of at most 3 items."})
    for item in sorting:
        if (
            not isinstance(item, dict)
            or set(item) != {"field", "direction"}
            or item.get("field") not in fields_available
            or item.get("direction") not in {"asc", "desc"}
        ):
            raise ValidationError({"configuration": "Sort configuration is unsupported."})

    limit = config.get("limit", 100)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValidationError({"configuration": "Limit must be an integer from 1 to 500."})
    return config
