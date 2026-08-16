"""Build and render scoped analytics rows from current portfolio data."""

from decimal import Decimal, InvalidOperation

from .income import projections_for_holding
from ..models import Holding, ThemeAssignment
from ..services.valuation import value_holding
from .configuration import NUMERIC_FIELDS, effective_configuration


class ViewAnalyticsContext:
    """Lazily builds consistent analytics rows for a portfolio and View scope."""

    def __init__(self, portfolio, *, market_service=None, holding_ids=None):
        self.portfolio = portfolio
        self.market_service = market_service
        self.holding_ids = None if holding_ids is None else set(holding_ids)
        self._rows = {}

    def rows(self, data_source):
        if data_source not in self._rows:
            builders = {
                "HOLDINGS": self._holding_rows,
                "INCOME": self._income_rows,
                "THEMES": self._theme_rows,
                "GROUPS": self._group_rows,
            }
            self._rows[data_source] = builders[data_source]()
        return self._rows[data_source]

    def _holdings(self):
        if "_holdings" not in self._rows:
            queryset = Holding.objects.filter(
                    group__portfolio=self.portfolio,
                    status=Holding.Status.ACTIVE,
                )
            if self.holding_ids is not None:
                queryset = queryset.filter(pk__in=self.holding_ids)
            self._rows["_holdings"] = list(
                queryset.select_related(
                    "group", "asset", "asset__asset_type", "theme_assignment__theme"
                )
                .prefetch_related("income_rules")
            )
        return self._rows["_holdings"]

    def _metrics(self):
        if "_metrics" in self._rows:
            return self._rows["_metrics"]
        metrics = {}
        base = self.portfolio.base_currency
        for holding in self._holdings():
            valuation = value_holding(holding, service=self.market_service)
            projections = projections_for_holding(
                holding, market_service=self.market_service
            )
            annual_income = sum(
                (
                    projection.annual_amount
                    for projection in projections
                    if projection.currency == base
                ),
                Decimal("0"),
            )
            value = valuation.value if valuation.currency == base else None
            cost_basis = (
                holding.quantity * holding.average_cost
                if holding.average_cost is not None
                and (
                    holding.cost_currency or holding.asset.native_currency or base
                ) == base
                else None
            )
            metrics[holding.pk] = {
                "valuation": valuation,
                "projections": projections,
                "value": value,
                "cost_basis": cost_basis,
                "annual_income": annual_income,
                "monthly_income": annual_income / Decimal("12"),
            }
        self._rows["_metrics"] = metrics
        return metrics

    @staticmethod
    def _theme_for(holding):
        try:
            return holding.theme_assignment.theme
        except (AttributeError, ThemeAssignment.DoesNotExist):
            return None

    def _holding_rows(self):
        rows = []
        metrics = self._metrics()
        for holding in self._holdings():
            item = metrics[holding.pk]
            value = item["value"]
            cost_basis = item["cost_basis"]
            annual_income = item["annual_income"]
            theme = self._theme_for(holding)
            rows.append({
                "holding_id": str(holding.pk),
                "asset_name": holding.asset.name,
                "group": holding.group.name,
                "asset_type": holding.asset.asset_type.name,
                "theme": theme.name if theme else None,
                "country": holding.asset.country_code or None,
                "sector": holding.asset.sector or None,
                "industry": holding.asset.industry or None,
                "symbol": holding.asset.market_symbol or None,
                "quantity": holding.quantity,
                "average_cost": holding.average_cost,
                "cost_basis": cost_basis,
                "value": value,
                "currency": self.portfolio.base_currency,
                "gain_loss": (
                    value - cost_basis
                    if value is not None and cost_basis is not None
                    else None
                ),
                "annual_income": annual_income,
                "current_yield": (
                    annual_income / value * Decimal("100") if value else None
                ),
                "yield_on_cost": (
                    annual_income / cost_basis * Decimal("100") if cost_basis else None
                ),
                "source": holding.source,
                "valuation_source": item["valuation"].source,
                "stale": item["valuation"].stale,
            })
        return rows

    def _income_rows(self):
        rows = []
        metrics = self._metrics()
        for holding in self._holdings():
            theme = self._theme_for(holding)
            for projection in metrics[holding.pk]["projections"]:
                rows.append({
                    "holding_id": str(holding.pk),
                    "asset_name": holding.asset.name,
                    "group": holding.group.name,
                    "theme": theme.name if theme else None,
                    "income_name": projection.name,
                    "income_type": projection.category,
                    "annual_income": projection.annual_amount,
                    "monthly_income": projection.annual_amount / Decimal("12"),
                    "currency": projection.currency,
                    "source": projection.source,
                    "frequency": projection.frequency,
                    "stale": projection.stale,
                })
        return rows

    def _descendant_ids(self, theme, by_parent):
        result = {theme.pk}
        for child in by_parent.get(theme.pk, []):
            result.update(self._descendant_ids(child, by_parent))
        return result

    def _theme_rows(self):
        themes = list(self.portfolio.themes.select_related("parent"))
        by_parent = {}
        for theme in themes:
            by_parent.setdefault(theme.parent_id, []).append(theme)
        metrics = self._metrics()
        assigned = {}
        for holding in self._holdings():
            theme = self._theme_for(holding)
            if theme:
                assigned.setdefault(theme.pk, []).append(holding)
        total_value = sum(
            (item["value"] for item in metrics.values() if item["value"] is not None),
            Decimal("0"),
        )
        rows = []
        for theme in themes:
            ids = self._descendant_ids(theme, by_parent)
            holdings = [
                holding for theme_id in ids for holding in assigned.get(theme_id, [])
            ]
            value = sum(
                (
                    metrics[holding.pk]["value"]
                    for holding in holdings
                    if metrics[holding.pk]["value"] is not None
                ),
                Decimal("0"),
            )
            annual_income = sum(
                (metrics[holding.pk]["annual_income"] for holding in holdings),
                Decimal("0"),
            )
            allocation = value / total_value * Decimal("100") if total_value else None
            rows.append({
                "theme_id": str(theme.pk),
                "theme": theme.name,
                "parent_theme": theme.parent.name if theme.parent else None,
                "target_percentage": theme.target_percentage,
                "value": value,
                "currency": self.portfolio.base_currency,
                "annual_income": annual_income,
                "monthly_income": annual_income / Decimal("12"),
                "holding_count": Decimal(len(holdings)),
                "allocation_percentage": allocation,
                "target_gap": (
                    theme.target_percentage - allocation
                    if theme.target_percentage is not None and allocation is not None
                    else None
                ),
            })
        return rows

    def _group_rows(self):
        metrics = self._metrics()
        total_value = sum(
            (item["value"] for item in metrics.values() if item["value"] is not None),
            Decimal("0"),
        )
        rows = []
        for group in self.portfolio.groups.all():
            holdings = [item for item in self._holdings() if item.group_id == group.pk]
            value = sum(
                (
                    metrics[holding.pk]["value"]
                    for holding in holdings
                    if metrics[holding.pk]["value"] is not None
                ),
                Decimal("0"),
            )
            annual_income = sum(
                (metrics[holding.pk]["annual_income"] for holding in holdings),
                Decimal("0"),
            )
            rows.append({
                "group_id": str(group.pk),
                "group": group.name,
                "mode": group.mode,
                "value": value,
                "currency": self.portfolio.base_currency,
                "annual_income": annual_income,
                "monthly_income": annual_income / Decimal("12"),
                "holding_count": Decimal(len(holdings)),
                "allocation_percentage": (
                    value / total_value * Decimal("100") if total_value else None
                ),
            })
        return rows


def _decimal(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _matches(row, item):
    actual = row.get(item["field"])
    operator = item["operator"]
    expected = item.get("value")
    if operator == "is_null":
        return (actual is None) is bool(expected if "value" in item else True)
    if operator == "in":
        if item["field"] in NUMERIC_FIELDS:
            actual = _decimal(actual)
            expected = [_decimal(value) for value in expected]
        return actual in expected
    if item["field"] in NUMERIC_FIELDS:
        actual = _decimal(actual)
        expected = _decimal(expected)
        if actual is None or expected is None:
            return False
    if operator == "equals":
        return actual == expected
    if operator == "not_equals":
        return actual != expected
    if operator == "greater_than":
        return actual > expected
    if operator == "greater_or_equal":
        return actual >= expected
    if operator == "less_than":
        return actual < expected
    if operator == "less_or_equal":
        return actual <= expected
    if operator == "contains":
        return str(expected).casefold() in str(actual or "").casefold()
    return False


def _aggregate(rows, specification):
    field = specification["field"]
    function = specification["function"]
    values = [row.get(field) for row in rows if row.get(field) is not None]
    if function == "count":
        return Decimal(len(values))
    if not values:
        return None
    if function == "sum":
        return sum(values, Decimal("0"))
    if function == "average":
        return sum(values, Decimal("0")) / Decimal(len(values))
    if function == "minimum":
        return min(values)
    if function == "maximum":
        return max(values)


def render_block(block, *, context=None):
    context = context or ViewAnalyticsContext(block.view.portfolio)
    config = effective_configuration(
        block.data_source, block.presentation, block.configuration
    )
    rows = [
        row for row in context.rows(block.data_source)
        if all(_matches(row, item) for item in config.get("filters", []))
    ]
    aggregations = config.get("aggregations", [])
    group_by = config.get("group_by")
    group_fields = (
        group_by
        if isinstance(group_by, list)
        else [group_by]
        if group_by is not None
        else []
    )
    sorting = config.get("sort", [])
    if aggregations:
        buckets = {None: rows}
        if group_fields:
            buckets = {}
            for row in rows:
                key = tuple(row.get(field) for field in group_fields)
                buckets.setdefault(key, []).append(row)
        rendered = []
        for group_value, items in buckets.items():
            result = (
                dict(zip(group_fields, group_value, strict=True))
                if group_fields
                else {}
            )
            for item in aggregations:
                result[f"{item['function']}_{item['field']}"] = _aggregate(items, item)
            rendered.append(result)
        rows = rendered
    else:
        for sort in reversed(sorting):
            field = sort["field"]
            rows.sort(
                key=lambda row: (row.get(field) is None, row.get(field)),
                reverse=sort["direction"] == "desc",
            )
        fields = config.get("fields", [])
        rows = [{field: row.get(field) for field in fields} for row in rows]

    if aggregations:
        for sort in reversed(sorting):
            field = sort["field"]
            if field not in group_fields:
                matching = next(
                    (item for item in aggregations if item["field"] == field), None
                )
                if matching:
                    field = f"{matching['function']}_{field}"
            rows.sort(
                key=lambda row: (row.get(field) is None, row.get(field)),
                reverse=sort["direction"] == "desc",
            )
    total_row_count = len(rows)
    rows = rows[: config.get("limit", 100)]
    return {
        "data_source": block.data_source,
        "presentation": block.presentation,
        "configuration": config,
        "rows": rows,
        "row_count": len(rows),
        "total_row_count": total_row_count,
    }


def render_view(view, *, market_service=None):
    holding_ids = None
    if view.scope_mode == view.ScopeMode.SELECTED:
        holding_ids = view.holding_selections.values_list("holding_id", flat=True)
    context = ViewAnalyticsContext(
        view.portfolio,
        market_service=market_service,
        holding_ids=holding_ids,
    )
    return [render_block(block, context=context) for block in view.blocks.all()]
