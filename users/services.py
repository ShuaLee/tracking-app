from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import User


class AccountValidationError(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("Account data is invalid.")


@transaction.atomic
def create_account(*, email, password, name=""):
    email = User.objects.normalize_email(email)
    candidate = User(email=email)
    errors = {}

    try:
        candidate.full_clean(exclude={"password"})
    except ValidationError as exc:
        errors.update(exc.message_dict)

    try:
        validate_password(password, user=candidate)
    except ValidationError as exc:
        errors["password"] = list(exc.messages)

    if not isinstance(name, str):
        errors["name"] = ["Name must be a string."]
    elif len(name.strip()) > 150:
        errors["name"] = ["Name must be 150 characters or fewer."]

    if errors:
        raise AccountValidationError(errors)

    try:
        user = User.objects.create_user(email=email, password=password)
    except ValidationError as exc:
        raise AccountValidationError(exc.message_dict) from exc

    user.profile.name = name.strip()
    user.profile.save(update_fields=["name", "updated_at"])
    # Portfolio bootstrap is added here now that the Stage 3 domain exists.
    # The local import keeps the identity models independent of portfolio models.
    from portfolios.services.holdings import create_portfolio

    create_portfolio(owner=user, name="My Portfolio", base_currency="USD")
    return user


@transaction.atomic
def deactivate_account(*, user):
    user.is_active = False
    user.save(update_fields=["is_active", "updated_at"])
