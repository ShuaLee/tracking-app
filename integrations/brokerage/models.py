import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class BrokerageUser(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="brokerage_user",
    )
    provider = models.CharField(max_length=40, default="snaptrade")
    provider_user_id = models.CharField(max_length=255, unique=True)
    encrypted_user_secret = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email}: {self.provider}"


class BrokerageConnection(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        DISABLED = "DISABLED", "Disabled"
        DISCONNECTED = "DISCONNECTED", "Disconnected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="brokerage_connections",
    )
    portfolio = models.ForeignKey(
        "portfolios.Portfolio",
        on_delete=models.CASCADE,
        related_name="brokerage_connections",
    )
    provider = models.CharField(max_length=40, default="snaptrade")
    provider_connection_id = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    institution = models.CharField(max_length=255, blank=True)
    brokerage_slug = models.CharField(max_length=120, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.ACTIVE
    )
    metadata = models.JSONField(default=dict, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=80, blank=True)
    last_error_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("user", "provider", "provider_connection_id"),
                name="unique_provider_connection_per_user",
            )
        ]

    def clean(self):
        errors = {}
        if self.portfolio_id and self.user_id and self.portfolio.owner_id != self.user_id:
            errors["portfolio"] = "Connection portfolio must belong to the same user."
        if not isinstance(self.metadata, dict):
            errors["metadata"] = "Connection metadata must be a JSON object."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.name} ({self.user.email})"
