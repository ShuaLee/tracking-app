import binascii

from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from subscriptions.entitlements import entitlements_for

from .http import api_error, api_login_required, parse_json
from .models import User
from .serializers import subscription_data, user_data
from .services import AccountValidationError, create_account, deactivate_account


def _json(request):
    try:
        return parse_json(request), None
    except ValueError as exc:
        return None, api_error(str(exc), code="invalid_json")


@require_GET
@ensure_csrf_cookie
def csrf(request):
    return JsonResponse({"csrfToken": get_token(request)})


@require_POST
def signup(request):
    data, error = _json(request)
    if error:
        return error
    required = {field: data.get(field) for field in ("email", "password")}
    missing = {key: ["This field is required."] for key, value in required.items() if not value}
    if missing:
        return api_error("Signup data is invalid.", fields=missing)
    try:
        user = create_account(
            email=data["email"],
            password=data["password"],
            name=data.get("name", ""),
        )
    except AccountValidationError as exc:
        return api_error("Signup data is invalid.", fields=exc.errors)
    except IntegrityError:
        return api_error(
            "Signup data is invalid.",
            fields={"email": ["An account with this email already exists."]},
        )
    login(request, user)
    return JsonResponse({"user": user_data(user)}, status=201)


@require_POST
def login_view(request):
    data, error = _json(request)
    if error:
        return error
    email = User.objects.normalize_email(data.get("email", ""))
    password = data.get("password", "")
    user = authenticate(request, email=email, password=password)
    if user is None:
        return api_error(
            "Invalid email or password.",
            code="invalid_credentials",
            status=401,
        )
    login(request, user)
    return JsonResponse({"user": user_data(user)})


@require_POST
@api_login_required
def logout_view(request):
    logout(request)
    return JsonResponse({}, status=204)


@require_http_methods(["GET", "PATCH", "DELETE"])
@api_login_required
def me(request):
    if request.method == "GET":
        return JsonResponse({"user": user_data(request.user)})

    data, error = _json(request)
    if error:
        return error

    if request.method == "DELETE":
        if not request.user.check_password(data.get("current_password", "")):
            return api_error(
                "Current password is incorrect.",
                code="invalid_password",
                status=403,
            )
        deactivate_account(user=request.user)
        logout(request)
        return JsonResponse({}, status=204)

    allowed = {"email", "name"}
    unknown = sorted(set(data) - allowed - {"current_password"})
    if unknown:
        return api_error(
            "Profile data is invalid.",
            fields={key: ["Unknown field."] for key in unknown},
        )

    errors = {}
    if "name" in data:
        if not isinstance(data["name"], str):
            errors["name"] = ["Name must be a string."]
        elif len(data["name"].strip()) > 150:
            errors["name"] = ["Name must be 150 characters or fewer."]

    new_email = None
    if "email" in data:
        new_email = User.objects.normalize_email(data["email"])
        if not request.user.check_password(data.get("current_password", "")):
            errors["current_password"] = ["Current password is required to change email."]
        else:
            candidate = User(email=new_email)
            try:
                candidate.full_clean(
                    exclude={"password"},
                    validate_unique=False,
                    validate_constraints=False,
                )
            except ValidationError as exc:
                errors.update(exc.message_dict)
            if User.objects.exclude(pk=request.user.pk).filter(email=new_email).exists():
                errors["email"] = ["An account with this email already exists."]

    if errors:
        return api_error("Profile data is invalid.", fields=errors)

    with transaction.atomic():
        if new_email is not None:
            request.user.email = new_email
            request.user.save(update_fields=["email", "updated_at"])
        if "name" in data:
            request.user.profile.name = data["name"].strip()
            request.user.profile.save(update_fields=["name", "updated_at"])
    return JsonResponse({"user": user_data(request.user)})


@require_POST
@api_login_required
def password_change(request):
    data, error = _json(request)
    if error:
        return error
    if not request.user.check_password(data.get("current_password", "")):
        return api_error(
            "Current password is incorrect.",
            code="invalid_password",
            status=403,
        )
    new_password = data.get("new_password", "")
    try:
        validate_password(new_password, user=request.user)
    except ValidationError as exc:
        return api_error(
            "New password is invalid.",
            fields={"new_password": list(exc.messages)},
        )
    request.user.set_password(new_password)
    request.user.save(update_fields=["password", "updated_at"])
    update_session_auth_hash(request, request.user)
    return JsonResponse({"message": "Password changed."})


@require_POST
def password_reset(request):
    data, error = _json(request)
    if error:
        return error
    email = User.objects.normalize_email(data.get("email", ""))
    user = User.objects.filter(email=email, is_active=True).first()
    if user:
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        reset_url = settings.PASSWORD_RESET_CONFIRM_URL.format(uid=uid, token=token)
        send_mail(
            subject="Reset your Tracking App password",
            message=f"Use this link to reset your password: {reset_url}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
        )
    return JsonResponse(
        {"message": "If an active account exists, password reset instructions have been sent."}
    )


@require_POST
def password_reset_confirm(request):
    data, error = _json(request)
    if error:
        return error
    try:
        user_id = force_str(urlsafe_base64_decode(data.get("uid", "")))
        user = User.objects.get(pk=user_id, is_active=True)
    except (ValueError, TypeError, OverflowError, UnicodeDecodeError, binascii.Error, User.DoesNotExist):
        user = None

    token = data.get("token", "")
    if user is None or not default_token_generator.check_token(user, token):
        return api_error(
            "The password reset link is invalid or expired.",
            code="invalid_reset_token",
        )

    new_password = data.get("new_password", "")
    try:
        validate_password(new_password, user=user)
    except ValidationError as exc:
        return api_error(
            "New password is invalid.",
            fields={"new_password": list(exc.messages)},
        )
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])
    return JsonResponse({"message": "Password reset complete."})


@require_GET
@api_login_required
def subscription(request):
    return JsonResponse({"subscription": subscription_data(request.user.subscription)})


@require_GET
@api_login_required
def entitlements(request):
    return JsonResponse({"entitlements": entitlements_for(request.user)})
