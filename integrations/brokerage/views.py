from django.http import JsonResponse
from django.views.decorators.http import require_http_methods, require_POST

from integrations.exceptions import IntegrationError, ProviderRateLimitError, ResourceNotFoundError
from portfolios.models import Portfolio
from subscriptions.entitlements import has
from users.http import api_error, api_login_required, parse_json

from .models import BrokerageConnection
from .serializers import connection_data
from .sync import (
    create_portal,
    disconnect_connection,
    import_connections,
    refresh_connection,
    sync_connection,
)


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


def _entitled(request):
    if not has(request.user, "brokerage_sync"):
        return api_error(
            "Your plan does not include brokerage sync.",
            code="entitlement_required",
            status=403,
        )


def _json(request):
    try:
        return parse_json(request), None
    except ValueError as exc:
        return None, api_error(str(exc), code="invalid_json")


def _portfolio(user, value):
    return Portfolio.objects.filter(owner=user, pk=value).first()


def _connection(user, value):
    return BrokerageConnection.objects.filter(user=user, pk=value).first()


@require_POST
@api_login_required
def portal(request):
    if error := _entitled(request):
        return error
    data, error = _json(request)
    if error:
        return error
    portfolio = _portfolio(request.user, data.get("portfolio_id"))
    if not portfolio:
        return api_error("Portfolio was not found.", code="not_found", status=404)
    try:
        result = create_portal(
            request.user,
            broker=data.get("broker"),
            custom_redirect=data.get("custom_redirect"),
            reconnect=data.get("reconnect"),
        )
    except IntegrationError as exc:
        return _integration_error(exc)
    return JsonResponse({"redirect_url": result.redirect_url})


@require_http_methods(["GET", "POST"])
@api_login_required
def connections(request):
    if error := _entitled(request):
        return error
    if request.method == "GET":
        items = BrokerageConnection.objects.filter(user=request.user)
        return JsonResponse({"connections": [connection_data(item) for item in items]})
    data, error = _json(request)
    if error:
        return error
    portfolio = _portfolio(request.user, data.get("portfolio_id"))
    if not portfolio:
        return api_error("Portfolio was not found.", code="not_found", status=404)
    try:
        items = import_connections(request.user, portfolio)
    except IntegrationError as exc:
        return _integration_error(exc)
    return JsonResponse(
        {"connections": [connection_data(item) for item in items]}, status=201
    )


@require_POST
@api_login_required
def sync(request, connection_id):
    if error := _entitled(request):
        return error
    connection = _connection(request.user, connection_id)
    if not connection:
        return api_error("Connection was not found.", code="not_found", status=404)
    try:
        result = sync_connection(connection)
    except IntegrationError as exc:
        return _integration_error(exc)
    except ValueError as exc:
        return api_error(str(exc), code="invalid_connection_state")
    return JsonResponse({"connection": connection_data(connection), "sync": result})


@require_POST
@api_login_required
def refresh(request, connection_id):
    if error := _entitled(request):
        return error
    connection = _connection(request.user, connection_id)
    if not connection:
        return api_error("Connection was not found.", code="not_found", status=404)
    try:
        refresh_connection(connection)
    except IntegrationError as exc:
        return _integration_error(exc)
    return JsonResponse({"status": "queued"}, status=202)


@require_http_methods(["DELETE"])
@api_login_required
def disconnect(request, connection_id):
    if error := _entitled(request):
        return error
    connection = _connection(request.user, connection_id)
    if not connection:
        return api_error("Connection was not found.", code="not_found", status=404)
    try:
        disconnect_connection(connection)
    except IntegrationError as exc:
        return _integration_error(exc)
    return JsonResponse({"connection": connection_data(connection)})
