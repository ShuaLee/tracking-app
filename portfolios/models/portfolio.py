"""Portfolio and ownership-group models."""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .validators import currency_validator


class Portfolio(models.Model):
    """Top-level container for one owner's assets and analytical views."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="portfolios",
    )
    name = models.CharField(max_length=120)
    base_currency = models.CharField(
        max_length=3, default="USD", validators=[currency_validator]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at",)

    def save(self, *args, **kwargs):
        self.base_currency = self.base_currency.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Group(models.Model):
    """Ownership grouping, either manual, system-managed, or provider-synced."""

    class Mode(models.TextChoices):
        SYSTEM = "SYSTEM", "System"
        MANUAL = "MANUAL", "Manual"
        SYNCED = "SYNCED", "Synced"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    portfolio = models.ForeignKey(
        Portfolio,
        on_delete=models.CASCADE,
        related_name="groups",
    )
    name = models.CharField(max_length=120)
    mode = models.CharField(max_length=10, choices=Mode.choices)
    is_ungrouped = models.BooleanField(default=False, editable=False)
    provider = models.CharField(max_length=40, blank=True)
    provider_account_id = models.CharField(max_length=255, blank=True)
    provider_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("portfolio",),
                condition=models.Q(is_ungrouped=True),
                name="unique_portfolio_ungrouped_group",
            ),
            models.CheckConstraint(
                condition=(models.Q(is_ungrouped=False) | models.Q(mode="SYSTEM")),
                name="ungrouped_group_must_be_system",
            ),
            models.UniqueConstraint(
                fields=("portfolio", "provider", "provider_account_id"),
                condition=(
                    models.Q(mode="SYNCED")
                    & ~models.Q(provider="")
                    & ~models.Q(provider_account_id="")
                ),
                name="unique_synced_provider_account_per_portfolio",
            ),
        ]

    def clean(self):
        errors = {}
        if not isinstance(self.provider_metadata, dict):
            errors["provider_metadata"] = "Provider metadata must be a JSON object."
        if self.is_ungrouped and self.mode != self.Mode.SYSTEM:
            errors["mode"] = "The Ungrouped group must use SYSTEM mode."
        if self.mode == self.Mode.SYNCED and (
            not self.provider or not self.provider_account_id
        ):
            errors["provider"] = (
                "Synced groups require provider and provider_account_id."
            )
        if self.mode != self.Mode.SYNCED and (
            self.provider or self.provider_account_id or self.provider_metadata
        ):
            errors["provider"] = "Provider fields are reserved for synced groups."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.portfolio}: {self.name}"
