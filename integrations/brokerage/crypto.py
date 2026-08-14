import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

from integrations.exceptions import IntegrationConfigurationError


def _fernet():
    configured = getattr(settings, "BROKERAGE_CREDENTIAL_ENCRYPTION_KEY", "")
    if configured:
        key = configured.encode("ascii")
    elif settings.DEBUG:
        digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest)
    else:
        raise IntegrationConfigurationError(
            "BROKERAGE_CREDENTIAL_ENCRYPTION_KEY is required in production."
        )
    try:
        return Fernet(key)
    except (ValueError, TypeError) as exc:
        raise IntegrationConfigurationError(
            "BROKERAGE_CREDENTIAL_ENCRYPTION_KEY must be a valid Fernet key."
        ) from exc


def encrypt_secret(secret):
    if not secret:
        raise ValueError("A brokerage user secret is required.")
    return _fernet().encrypt(str(secret).encode("utf-8")).decode("ascii")


def decrypt_secret(token):
    try:
        return _fernet().decrypt(str(token).encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise IntegrationConfigurationError(
            "Stored brokerage credentials cannot be decrypted with the configured key."
        ) from exc
