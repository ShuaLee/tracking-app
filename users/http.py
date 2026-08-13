import json
from functools import wraps

from django.http import JsonResponse


def api_error(message, *, code="invalid_request", status=400, fields=None):
    error = {"code": code, "message": message}
    if fields:
        error["fields"] = fields
    return JsonResponse({"error": error}, status=status)


def parse_json(request):
    if request.content_type != "application/json":
        raise ValueError("Content-Type must be application/json.")
    try:
        data = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Request body must contain valid JSON.") from exc
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object.")
    return data


def api_login_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return api_error(
                "Authentication is required.",
                code="authentication_required",
                status=401,
            )
        return view(request, *args, **kwargs)

    return wrapped

