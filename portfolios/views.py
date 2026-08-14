from django.db.models import Count, Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods

from integrations.exceptions import (
    IntegrationError,
    ProviderRateLimitError,
    ResourceNotFoundError,
)
from integrations.market_data.service import MarketDataService

from users.http import api_error, api_login_required, parse_json

from .exceptions import PortfolioDomainError
from .models import AssetType, Group, Holding, Portfolio
from .serializers import (
    asset_type_data,
    group_data,
    holding_data,
    overview_data,
    portfolio_data,
)
from .services import (
    create_custom_asset_type,
    create_manual_group,
    create_manual_holding,
    create_portfolio,
    delete_custom_asset_type,
    delete_manual_group,
    delete_manual_holding,
    delete_portfolio,
    portfolio_overview,
    update_custom_asset_type,
    update_manual_group,
    update_manual_holding,
    update_portfolio,
)
from .market import create_market_holding, relink_market_holding


def _json(request):
    try:
        return parse_json(request), None
    except ValueError as exc:
        return None, api_error(str(exc), code="invalid_json")


def _domain_error(exc):
    return api_error(str(exc), code=exc.code, fields=exc.fields)


def _integration_error(exc):
    if isinstance(exc, ProviderRateLimitError):
        status = 429
    elif isinstance(exc, ResourceNotFoundError):
        status = 404
    else:
        status = 503
    response = api_error(str(exc), code=exc.code, status=status)
    if exc.retry_after:
        response["Retry-After"] = str(exc.retry_after)
    return response


def _portfolio(user, portfolio_id):
    return Portfolio.objects.filter(owner=user, pk=portfolio_id).first()


def _not_found(resource="Resource"):
    return api_error(f"{resource} was not found.", code="not_found", status=404)


def _unknown_fields(data, allowed):
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        return api_error(
            "Request data is invalid.",
            fields={field: ["Unknown field."] for field in unknown},
        )
    return None


@require_http_methods(["GET", "POST"])
@api_login_required
def portfolios(request):
    if request.method == "GET":
        items = Portfolio.objects.filter(owner=request.user)
        return JsonResponse({"portfolios": [portfolio_data(item) for item in items]})
    data, error = _json(request)
    if error:
        return error
    if error := _unknown_fields(data, {"name", "base_currency"}):
        return error
    try:
        portfolio = create_portfolio(
            owner=request.user,
            name=data.get("name", ""),
            base_currency=data.get("base_currency", "USD"),
        )
    except PortfolioDomainError as exc:
        return _domain_error(exc)
    return JsonResponse({"portfolio": portfolio_data(portfolio)}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
@api_login_required
def portfolio_detail(request, portfolio_id):
    portfolio = _portfolio(request.user, portfolio_id)
    if portfolio is None:
        return _not_found("Portfolio")
    if request.method == "GET":
        return JsonResponse({"portfolio": portfolio_data(portfolio)})
    if request.method == "DELETE":
        delete_portfolio(portfolio=portfolio)
        return JsonResponse({}, status=204)
    data, error = _json(request)
    if error:
        return error
    if error := _unknown_fields(data, {"name", "base_currency"}):
        return error
    try:
        portfolio = update_portfolio(
            portfolio=portfolio,
            name=data.get("name"),
            base_currency=data.get("base_currency"),
        )
    except PortfolioDomainError as exc:
        return _domain_error(exc)
    return JsonResponse({"portfolio": portfolio_data(portfolio)})


@require_http_methods(["GET", "POST"])
@api_login_required
def groups(request, portfolio_id):
    portfolio = _portfolio(request.user, portfolio_id)
    if portfolio is None:
        return _not_found("Portfolio")
    if request.method == "GET":
        items = portfolio.groups.annotate(holding_count=Count("holdings"))
        return JsonResponse(
            {"groups": [group_data(item, include_count=True) for item in items]}
        )
    data, error = _json(request)
    if error:
        return error
    if error := _unknown_fields(data, {"name"}):
        return error
    try:
        group = create_manual_group(portfolio=portfolio, name=data.get("name", ""))
    except PortfolioDomainError as exc:
        return _domain_error(exc)
    return JsonResponse({"group": group_data(group)}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
@api_login_required
def group_detail(request, portfolio_id, group_id):
    portfolio = _portfolio(request.user, portfolio_id)
    if portfolio is None:
        return _not_found("Portfolio")
    group = portfolio.groups.filter(pk=group_id).first()
    if group is None:
        return _not_found("Group")
    if request.method == "GET":
        return JsonResponse({"group": group_data(group, include_count=True)})
    try:
        if request.method == "DELETE":
            delete_manual_group(group=group)
            return JsonResponse({}, status=204)
        data, error = _json(request)
        if error:
            return error
        if error := _unknown_fields(data, {"name"}):
            return error
        group = update_manual_group(group=group, name=data.get("name", group.name))
    except PortfolioDomainError as exc:
        return _domain_error(exc)
    return JsonResponse({"group": group_data(group)})


@require_http_methods(["GET", "POST"])
@api_login_required
def asset_types(request):
    if request.method == "GET":
        items = AssetType.objects.filter(
            Q(owner__isnull=True) | Q(owner=request.user), is_active=True
        )
        return JsonResponse({"asset_types": [asset_type_data(item) for item in items]})
    data, error = _json(request)
    if error:
        return error
    if error := _unknown_fields(data, {"name", "system_category"}):
        return error
    try:
        asset_type = create_custom_asset_type(
            owner=request.user,
            name=data.get("name", ""),
            system_category=data.get("system_category", ""),
        )
    except PortfolioDomainError as exc:
        return _domain_error(exc)
    return JsonResponse({"asset_type": asset_type_data(asset_type)}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
@api_login_required
def asset_type_detail(request, asset_type_id):
    asset_type = AssetType.objects.filter(
        Q(owner__isnull=True) | Q(owner=request.user), pk=asset_type_id
    ).first()
    if asset_type is None:
        return _not_found("Asset type")
    if request.method == "GET":
        return JsonResponse({"asset_type": asset_type_data(asset_type)})
    try:
        if request.method == "DELETE":
            delete_custom_asset_type(asset_type=asset_type)
            return JsonResponse({}, status=204)
        data, error = _json(request)
        if error:
            return error
        if error := _unknown_fields(data, {"name", "system_category"}):
            return error
        asset_type = update_custom_asset_type(
            asset_type=asset_type,
            name=data.get("name"),
            system_category=data.get("system_category"),
        )
    except PortfolioDomainError as exc:
        return _domain_error(exc)
    return JsonResponse({"asset_type": asset_type_data(asset_type)})


@require_http_methods(["GET", "POST"])
@api_login_required
def holdings(request, portfolio_id):
    portfolio = _portfolio(request.user, portfolio_id)
    if portfolio is None:
        return _not_found("Portfolio")
    queryset = Holding.objects.filter(group__portfolio=portfolio).select_related(
        "group", "asset", "asset__asset_type"
    )
    if request.method == "GET":
        group_id = request.GET.get("group_id")
        if group_id:
            queryset = queryset.filter(group_id=group_id)
        return JsonResponse({"holdings": [holding_data(item) for item in queryset]})
    data, error = _json(request)
    if error:
        return error
    allowed = {
        "name", "asset_type_id", "group_id", "native_currency", "metadata",
        "quantity", "average_cost", "cost_currency", "manual_value",
    }
    if error := _unknown_fields(data, allowed):
        return error
    asset_type = AssetType.objects.filter(
        Q(owner__isnull=True) | Q(owner=request.user),
        pk=data.get("asset_type_id"),
        is_active=True,
    ).first()
    if asset_type is None:
        return api_error(
            "Holding data is invalid.",
            fields={"asset_type_id": ["A valid available asset type is required."]},
        )
    group = None
    if data.get("group_id"):
        group = portfolio.groups.filter(pk=data["group_id"]).first()
        if group is None:
            return api_error(
                "Holding data is invalid.",
                fields={"group_id": ["Group was not found in this portfolio."]},
            )
    try:
        holding = create_manual_holding(
            portfolio=portfolio,
            asset_type=asset_type,
            group=group,
            name=data.get("name", ""),
            native_currency=data.get("native_currency", ""),
            metadata=data.get("metadata", {}),
            quantity=data.get("quantity", 1),
            average_cost=data.get("average_cost"),
            cost_currency=data.get("cost_currency", ""),
            manual_value=data.get("manual_value"),
        )
    except PortfolioDomainError as exc:
        return _domain_error(exc)
    return JsonResponse({"holding": holding_data(holding)}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
@api_login_required
def holding_detail(request, portfolio_id, holding_id):
    portfolio = _portfolio(request.user, portfolio_id)
    if portfolio is None:
        return _not_found("Portfolio")
    holding = (
        Holding.objects.filter(group__portfolio=portfolio, pk=holding_id)
        .select_related("group", "asset", "asset__asset_type", "asset__portfolio")
        .first()
    )
    if holding is None:
        return _not_found("Holding")
    if request.method == "GET":
        return JsonResponse({"holding": holding_data(holding)})
    try:
        if request.method == "DELETE":
            delete_manual_holding(holding=holding)
            return JsonResponse({}, status=204)
        data, error = _json(request)
        if error:
            return error
        allowed = {
            "name", "asset_type_id", "group_id", "native_currency", "metadata",
            "quantity", "average_cost", "cost_currency", "manual_value",
            "asset_status", "holding_status",
        }
        if error := _unknown_fields(data, allowed):
            return error
        changes = dict(data)
        if "group_id" in changes:
            group = portfolio.groups.filter(pk=changes.pop("group_id")).first()
            if group is None:
                return api_error(
                    "Holding data is invalid.",
                    fields={"group_id": ["Group was not found in this portfolio."]},
                )
            changes["group"] = group
        if "asset_type_id" in changes:
            asset_type = AssetType.objects.filter(
                Q(owner__isnull=True) | Q(owner=request.user),
                pk=changes.pop("asset_type_id"),
                is_active=True,
            ).first()
            if asset_type is None:
                return api_error(
                    "Holding data is invalid.",
                    fields={"asset_type_id": ["A valid available asset type is required."]},
                )
            changes["asset_type"] = asset_type
        holding = update_manual_holding(holding=holding, **changes)
    except PortfolioDomainError as exc:
        return _domain_error(exc)
    return JsonResponse({"holding": holding_data(holding)})


@require_GET
@api_login_required
def overview(request, portfolio_id):
    portfolio = _portfolio(request.user, portfolio_id)
    if portfolio is None:
        return _not_found("Portfolio")
    return JsonResponse(
        {"overview": overview_data(portfolio, portfolio_overview(portfolio))}
    )


@require_GET
@api_login_required
def market_search(request):
    query = request.GET.get("q", "")
    if not query.strip():
        return api_error(
            "A search query is required.", fields={"q": ["This field is required."]}
        )
    try:
        results = MarketDataService().search(query, limit=request.GET.get("limit", 10))
    except (IntegrationError, ValueError) as exc:
        if isinstance(exc, IntegrationError):
            return _integration_error(exc)
        return api_error(str(exc))
    return JsonResponse({"results": [
        {
            "symbol": item.symbol,
            "name": item.name,
            "exchange": item.exchange,
            "currency": item.currency,
            "security_type": item.security_type,
            "identity": item.identity,
            "stale": item.stale,
        }
        for item in results
    ]})


@require_http_methods(["POST"])
@api_login_required
def market_holdings(request, portfolio_id):
    portfolio = _portfolio(request.user, portfolio_id)
    if portfolio is None:
        return _not_found("Portfolio")
    data, error = _json(request)
    if error:
        return error
    if error := _unknown_fields(
        data, {"symbol", "exchange", "group_id", "quantity", "average_cost", "cost_currency"}
    ):
        return error
    group = None
    if data.get("group_id"):
        group = portfolio.groups.filter(pk=data["group_id"]).first()
        if group is None:
            return api_error(
                "Holding data is invalid.",
                fields={"group_id": ["Group was not found in this portfolio."]},
            )
    try:
        holding = create_market_holding(
            portfolio=portfolio,
            symbol=data.get("symbol", ""),
            exchange=data.get("exchange", ""),
            group=group,
            quantity=data.get("quantity", 1),
            average_cost=data.get("average_cost"),
            cost_currency=data.get("cost_currency", ""),
        )
    except PortfolioDomainError as exc:
        return _domain_error(exc)
    except (IntegrationError, ValueError) as exc:
        if isinstance(exc, IntegrationError):
            return _integration_error(exc)
        return api_error(str(exc))
    return JsonResponse({"holding": holding_data(holding)}, status=201)


@require_http_methods(["POST"])
@api_login_required
def relink_holding(request, portfolio_id, holding_id):
    portfolio = _portfolio(request.user, portfolio_id)
    if portfolio is None:
        return _not_found("Portfolio")
    holding = Holding.objects.filter(
        group__portfolio=portfolio, pk=holding_id
    ).select_related("asset", "group", "asset__asset_type").first()
    if holding is None:
        return _not_found("Holding")
    data, error = _json(request)
    if error:
        return error
    if error := _unknown_fields(data, {"symbol", "exchange"}):
        return error
    try:
        holding = relink_market_holding(
            holding=holding,
            symbol=data.get("symbol", ""),
            exchange=data.get("exchange", ""),
        )
    except PortfolioDomainError as exc:
        return _domain_error(exc)
    except (IntegrationError, ValueError) as exc:
        if isinstance(exc, IntegrationError):
            return _integration_error(exc)
        return api_error(str(exc))
    return JsonResponse({"holding": holding_data(holding)})
