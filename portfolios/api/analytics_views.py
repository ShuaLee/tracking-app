"""HTTP endpoints for themes, income projections, and configurable views."""

from django.http import JsonResponse
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_GET, require_http_methods

from users.http import api_error, api_login_required, parse_json

from ..exceptions import PortfolioDomainError
from ..models import Holding, IncomeRule, Portfolio, ViewBlock
from .analytics_serializers import (
    assignment_data,
    income_rule_data,
    json_value,
    rendered_view_data,
    theme_data,
    view_data,
    block_data,
)
from ..analytics.services import (
    assign_theme,
    create_block,
    create_income_rule,
    create_theme,
    create_view_from_template,
    delete_block,
    delete_income_rule,
    delete_theme,
    delete_view,
    require_advanced_sheets,
    unassign_theme,
    update_block,
    update_asset_classification,
    update_income_rule,
    update_theme,
    update_view,
)
from ..analytics.engine import ViewAnalyticsContext, render_view
from ..analytics.configuration import (
    AGGREGATIONS,
    FILTER_OPERATORS,
    NUMERIC_FIELDS,
    SOURCE_FIELDS,
)
from ..analytics.templates import VIEW_TEMPLATES


def _json(request):
    try:
        return parse_json(request), None
    except ValueError as exc:
        return None, api_error(str(exc), code="invalid_json")


def _domain_error(exc):
    status = 403 if exc.code == "entitlement_required" else 400
    return api_error(str(exc), code=exc.code, fields=exc.fields, status=status)


def _unknown(data, allowed):
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        return api_error(
            "Request data is invalid.",
            fields={field: ["Unknown field."] for field in unknown},
        )


def _access(user, portfolio_id):
    portfolio = Portfolio.objects.filter(owner=user, pk=portfolio_id).first()
    if portfolio is None:
        return None, api_error("Portfolio was not found.", code="not_found", status=404)
    try:
        require_advanced_sheets(user)
    except PortfolioDomainError as exc:
        return None, _domain_error(exc)
    return portfolio, None


def _by_pk(queryset, value):
    if not value:
        return None
    try:
        return queryset.filter(pk=value).first()
    except (ValidationError, ValueError, TypeError):
        return None


@require_GET
@api_login_required
def view_templates(request):
    try:
        require_advanced_sheets(request.user)
    except PortfolioDomainError as exc:
        return _domain_error(exc)
    return JsonResponse({
        "templates": [
            {
                "key": key,
                "name": value["name"],
                "description": value["description"],
                "blocks": value["blocks"],
            }
            for key, value in VIEW_TEMPLATES.items()
        ]
    })


@require_GET
@api_login_required
def view_schema(request):
    try:
        require_advanced_sheets(request.user)
    except PortfolioDomainError as exc:
        return _domain_error(exc)
    return JsonResponse({
        "data_sources": {
            source: [
                {
                    "name": field,
                    "type": (
                        "number" if field in NUMERIC_FIELDS
                        else "boolean" if field == "stale"
                        else "text"
                    ),
                }
                for field in sorted(fields)
            ]
            for source, fields in SOURCE_FIELDS.items()
        },
        "presentations": ["TABLE", "LIST", "SUMMARY"],
        "filter_operators": sorted(FILTER_OPERATORS),
        "aggregation_functions": sorted(AGGREGATIONS),
        "scope_modes": ["ALL", "SELECTED"],
        "maximum_group_fields": 3,
        "can_copy_existing_view": True,
    })


@require_http_methods(["GET", "POST"])
@api_login_required
def themes(request, portfolio_id):
    portfolio, error = _access(request.user, portfolio_id)
    if error:
        return error
    if request.method == "GET":
        return JsonResponse({"themes": [theme_data(item) for item in portfolio.themes.all()]})
    data, error = _json(request)
    if error or (error := _unknown(data, {"name", "parent_id", "target_percentage", "color"})):
        return error
    parent = None
    if data.get("parent_id"):
        parent = _by_pk(portfolio.themes, data["parent_id"])
        if parent is None:
            return api_error("Parent theme was not found.", code="not_found", status=404)
    try:
        theme = create_theme(
            portfolio=portfolio,
            name=data.get("name", ""),
            parent=parent,
            target_percentage=data.get("target_percentage"),
            color=data.get("color", ""),
        )
    except PortfolioDomainError as exc:
        return _domain_error(exc)
    return JsonResponse({"theme": theme_data(theme)}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
@api_login_required
def theme_detail(request, portfolio_id, theme_id):
    portfolio, error = _access(request.user, portfolio_id)
    if error:
        return error
    theme = portfolio.themes.filter(pk=theme_id).first()
    if theme is None:
        return api_error("Theme was not found.", code="not_found", status=404)
    if request.method == "GET":
        return JsonResponse({"theme": theme_data(theme)})
    try:
        if request.method == "DELETE":
            delete_theme(theme)
            return JsonResponse({}, status=204)
        data, error = _json(request)
        if error or (error := _unknown(data, {"name", "parent_id", "target_percentage", "color"})):
            return error
        changes = dict(data)
        if "parent_id" in changes:
            parent_id = changes.pop("parent_id")
            parent = _by_pk(portfolio.themes, parent_id) if parent_id else None
            if parent_id and parent is None:
                return api_error("Parent theme was not found.", code="not_found", status=404)
            changes["parent"] = parent
        theme = update_theme(theme, **changes)
    except PortfolioDomainError as exc:
        return _domain_error(exc)
    return JsonResponse({"theme": theme_data(theme)})


@require_http_methods(["POST"])
@api_login_required
def theme_assignments(request, portfolio_id, theme_id):
    portfolio, error = _access(request.user, portfolio_id)
    if error:
        return error
    theme = portfolio.themes.filter(pk=theme_id).first()
    if theme is None:
        return api_error("Theme was not found.", code="not_found", status=404)
    data, error = _json(request)
    if error or (error := _unknown(data, {"holding_id"})):
        return error
    holding = _by_pk(
        Holding.objects.filter(group__portfolio=portfolio), data.get("holding_id")
    )
    if holding is None:
        return api_error("Holding was not found.", code="not_found", status=404)
    try:
        assignment = assign_theme(theme=theme, holding=holding)
    except PortfolioDomainError as exc:
        return _domain_error(exc)
    return JsonResponse({"assignment": assignment_data(assignment)}, status=201)


@require_http_methods(["DELETE"])
@api_login_required
def theme_unassign(request, portfolio_id, holding_id):
    portfolio, error = _access(request.user, portfolio_id)
    if error:
        return error
    holding = Holding.objects.filter(group__portfolio=portfolio, pk=holding_id).first()
    if holding is None:
        return api_error("Holding was not found.", code="not_found", status=404)
    try:
        unassign_theme(holding=holding)
    except PortfolioDomainError as exc:
        return _domain_error(exc)
    return JsonResponse({}, status=204)


@require_http_methods(["PATCH"])
@api_login_required
def holding_classification(request, portfolio_id, holding_id):
    portfolio, error = _access(request.user, portfolio_id)
    if error:
        return error
    holding = Holding.objects.filter(
        group__portfolio=portfolio, pk=holding_id
    ).select_related("group__portfolio__owner", "asset", "asset__asset_type").first()
    if holding is None:
        return api_error("Holding was not found.", code="not_found", status=404)
    data, error = _json(request)
    if error or (error := _unknown(data, {"country_code", "sector", "industry"})):
        return error
    try:
        asset = update_asset_classification(holding, **data)
    except PortfolioDomainError as exc:
        return _domain_error(exc)
    from .serializers import asset_data

    return JsonResponse({"asset": asset_data(asset)})


@require_GET
@api_login_required
def theme_analytics(request, portfolio_id, theme_id):
    portfolio, error = _access(request.user, portfolio_id)
    if error:
        return error
    if not portfolio.themes.filter(pk=theme_id).exists():
        return api_error("Theme was not found.", code="not_found", status=404)
    rows = ViewAnalyticsContext(portfolio).rows("THEMES")
    row = next(item for item in rows if item["theme_id"] == str(theme_id))
    return JsonResponse({"analytics": json_value(row)})


@require_http_methods(["GET", "POST"])
@api_login_required
def income_rules(request, portfolio_id):
    portfolio, error = _access(request.user, portfolio_id)
    if error:
        return error
    if request.method == "GET":
        items = IncomeRule.objects.filter(holding__group__portfolio=portfolio)
        return JsonResponse({"income_rules": [income_rule_data(item) for item in items]})
    data, error = _json(request)
    allowed = {
        "holding_id", "name", "category", "amount_per_payment", "currency",
        "frequency", "payments_per_year", "is_active",
    }
    if error or (error := _unknown(data, allowed)):
        return error
    holding = _by_pk(
        Holding.objects.filter(group__portfolio=portfolio), data.get("holding_id")
    )
    if holding is None:
        return api_error("Holding was not found.", code="not_found", status=404)
    try:
        rule = create_income_rule(
            holding=holding,
            name=data.get("name", ""),
            category=data.get("category", ""),
            amount_per_payment=data.get("amount_per_payment"),
            currency=data.get("currency", portfolio.base_currency),
            frequency=data.get("frequency", ""),
            payments_per_year=data.get("payments_per_year"),
            is_active=data.get("is_active", True),
        )
    except PortfolioDomainError as exc:
        return _domain_error(exc)
    return JsonResponse({"income_rule": income_rule_data(rule)}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
@api_login_required
def income_rule_detail(request, portfolio_id, rule_id):
    portfolio, error = _access(request.user, portfolio_id)
    if error:
        return error
    rule = IncomeRule.objects.filter(
        holding__group__portfolio=portfolio, pk=rule_id
    ).select_related("holding__group__portfolio").first()
    if rule is None:
        return api_error("Income rule was not found.", code="not_found", status=404)
    if request.method == "GET":
        return JsonResponse({"income_rule": income_rule_data(rule)})
    try:
        if request.method == "DELETE":
            delete_income_rule(rule)
            return JsonResponse({}, status=204)
        data, error = _json(request)
        allowed = {
            "name", "category", "amount_per_payment", "currency", "frequency",
            "payments_per_year", "is_active",
        }
        if error or (error := _unknown(data, allowed)):
            return error
        rule = update_income_rule(rule, **data)
    except PortfolioDomainError as exc:
        return _domain_error(exc)
    return JsonResponse({"income_rule": income_rule_data(rule)})


@require_GET
@api_login_required
def income_projections(request, portfolio_id):
    portfolio, error = _access(request.user, portfolio_id)
    if error:
        return error
    rows = ViewAnalyticsContext(portfolio).rows("INCOME")
    totals = {}
    for row in rows:
        totals[row["currency"]] = totals.get(row["currency"], 0) + row["annual_income"]
    return JsonResponse({"projections": json_value(rows), "totals": json_value(totals)})


@require_http_methods(["GET", "POST"])
@api_login_required
def saved_views(request, portfolio_id):
    portfolio, error = _access(request.user, portfolio_id)
    if error:
        return error
    if request.method == "GET":
        return JsonResponse({
            "views": [view_data(item, include_blocks=True) for item in portfolio.saved_views.all()]
        })
    data, error = _json(request)
    allowed = {
        "name", "description", "template", "source_view_id", "scope_mode",
        "holding_ids",
    }
    if error or (error := _unknown(data, allowed)):
        return error
    source_view = None
    if data.get("source_view_id"):
        source_view = _by_pk(portfolio.saved_views, data["source_view_id"])
        if source_view is None:
            return api_error("Source View was not found.", code="not_found", status=404)
    try:
        view = create_view_from_template(
            portfolio=portfolio,
            name=data.get("name", ""),
            description=data.get("description", ""),
            template=data.get("template"),
            source_view=source_view,
            scope_mode=data.get("scope_mode"),
            holding_ids=data.get("holding_ids"),
        )
    except PortfolioDomainError as exc:
        return _domain_error(exc)
    return JsonResponse({"view": view_data(view, include_blocks=True)}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
@api_login_required
def saved_view_detail(request, portfolio_id, view_id):
    portfolio, error = _access(request.user, portfolio_id)
    if error:
        return error
    view = portfolio.saved_views.filter(pk=view_id).first()
    if view is None:
        return api_error("View was not found.", code="not_found", status=404)
    if request.method == "GET":
        return JsonResponse({"view": view_data(view, include_blocks=True)})
    try:
        if request.method == "DELETE":
            delete_view(view)
            return JsonResponse({}, status=204)
        data, error = _json(request)
        if error or (
            error := _unknown(
                data, {"name", "description", "scope_mode", "holding_ids"}
            )
        ):
            return error
        view = update_view(view, **data)
    except PortfolioDomainError as exc:
        return _domain_error(exc)
    return JsonResponse({"view": view_data(view, include_blocks=True)})


@require_http_methods(["GET", "POST"])
@api_login_required
def view_blocks(request, portfolio_id, view_id):
    portfolio, error = _access(request.user, portfolio_id)
    if error:
        return error
    view = portfolio.saved_views.filter(pk=view_id).first()
    if view is None:
        return api_error("View was not found.", code="not_found", status=404)
    if request.method == "GET":
        return JsonResponse({"blocks": [block_data(item) for item in view.blocks.all()]})
    data, error = _json(request)
    allowed = {"title", "data_source", "presentation", "position", "width", "configuration"}
    if error or (error := _unknown(data, allowed)):
        return error
    try:
        block = create_block(
            view=view,
            title=data.get("title", ""),
            data_source=data.get("data_source", ""),
            presentation=data.get("presentation", ""),
            position=data.get("position"),
            width=data.get("width", 12),
            configuration=data.get("configuration", {}),
        )
    except (PortfolioDomainError, ValueError, TypeError) as exc:
        if isinstance(exc, PortfolioDomainError):
            return _domain_error(exc)
        return api_error("View block is invalid.")
    return JsonResponse({"block": block_data(block)}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
@api_login_required
def view_block_detail(request, portfolio_id, view_id, block_id):
    portfolio, error = _access(request.user, portfolio_id)
    if error:
        return error
    block = ViewBlock.objects.filter(
        view__portfolio=portfolio, view_id=view_id, pk=block_id
    ).select_related("view__portfolio__owner").first()
    if block is None:
        return api_error("View block was not found.", code="not_found", status=404)
    if request.method == "GET":
        return JsonResponse({"block": block_data(block)})
    try:
        if request.method == "DELETE":
            delete_block(block)
            return JsonResponse({}, status=204)
        data, error = _json(request)
        allowed = {"title", "data_source", "presentation", "position", "width", "configuration"}
        if error or (error := _unknown(data, allowed)):
            return error
        block = update_block(block, **data)
    except (PortfolioDomainError, ValueError, TypeError) as exc:
        if isinstance(exc, PortfolioDomainError):
            return _domain_error(exc)
        return api_error("View block is invalid.")
    return JsonResponse({"block": block_data(block)})


@require_GET
@api_login_required
def render_saved_view(request, portfolio_id, view_id):
    portfolio, error = _access(request.user, portfolio_id)
    if error:
        return error
    view = portfolio.saved_views.filter(pk=view_id).first()
    if view is None:
        return api_error("View was not found.", code="not_found", status=404)
    return JsonResponse({"view": rendered_view_data(view, render_view(view))})
