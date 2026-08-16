"""Asset taxonomy, asset identity, and owned-position models."""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower

from .portfolio import Group, Portfolio
from .validators import country_code_validator, currency_validator


class AssetType(models.Model):
    """Built-in or user-defined category used to classify an Asset."""

    class Category(models.TextChoices):
        SECURITY = "SECURITY", "Security"
        CASH = "CASH", "Cash"
        REAL_ESTATE = "REAL_ESTATE", "Real estate"
        VEHICLE = "VEHICLE", "Vehicle"
        COMMODITY = "COMMODITY", "Commodity"
        COLLECTIBLE = "COLLECTIBLE", "Collectible"
        PRIVATE_ASSET = "PRIVATE_ASSET", "Private asset"
        OTHER = "OTHER", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="custom_asset_types",
    )
    name = models.CharField(max_length=120)
    system_category = models.CharField(max_length=20, choices=Category.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("system_category", "name")
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                condition=models.Q(owner__isnull=True),
                name="unique_system_asset_type_name_ci",
            ),
            models.UniqueConstraint(
                Lower("name"),
                "owner",
                condition=models.Q(owner__isnull=False),
                name="unique_user_asset_type_name_ci",
            ),
        ]

    @property
    def is_system(self):
        return self.owner_id is None

    def __str__(self):
        return self.name


class Asset(models.Model):
    """Portfolio-scoped identity and classification of something owned."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"
        ARCHIVED = "ARCHIVED", "Archived"

    class MarketDataStatus(models.TextChoices):
        UNLINKED = "UNLINKED", "Unlinked"
        LINKED = "LINKED", "Linked"
        NEEDS_RELINK = "NEEDS_RELINK", "Needs relink"
        UNAVAILABLE = "UNAVAILABLE", "Unavailable"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    portfolio = models.ForeignKey(
        Portfolio,
        on_delete=models.CASCADE,
        related_name="assets",
    )
    asset_type = models.ForeignKey(
        AssetType,
        on_delete=models.PROTECT,
        related_name="assets",
    )
    name = models.CharField(max_length=255)
    native_currency = models.CharField(
        max_length=3, blank=True, validators=[currency_validator]
    )
    country_code = models.CharField(
        max_length=2, blank=True, validators=[country_code_validator]
    )
    sector = models.CharField(max_length=120, blank=True)
    industry = models.CharField(max_length=120, blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE
    )
    market_linked = models.BooleanField(default=False)
    market_data_status = models.CharField(
        max_length=16,
        choices=MarketDataStatus.choices,
        default=MarketDataStatus.UNLINKED,
    )
    market_symbol = models.CharField(max_length=64, blank=True)
    market_exchange = models.CharField(max_length=64, blank=True)
    market_identity = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(market_linked=True)
                    | (
                        models.Q(market_symbol="")
                        & models.Q(market_exchange="")
                        & models.Q(market_identity={})
                    )
                ),
                name="manual_asset_has_no_market_fields",
            ),
            models.CheckConstraint(
                condition=(
                    (
                        models.Q(market_linked=False)
                        & models.Q(market_data_status="UNLINKED")
                    )
                    | (
                        models.Q(market_linked=True)
                        & ~models.Q(market_data_status="UNLINKED")
                        & ~models.Q(market_symbol="")
                    )
                ),
                name="market_link_status_consistent",
            ),
        ]

    def clean(self):
        errors = {}
        if not isinstance(self.metadata, dict):
            errors["metadata"] = "Asset metadata must be a JSON object."
        if not isinstance(self.market_identity, dict):
            errors["market_identity"] = "Market identity must be a JSON object."
        if self.asset_type_id and self.asset_type.owner_id not in (
            None,
            self.portfolio.owner_id,
        ):
            errors["asset_type"] = "Asset type is not available to this portfolio owner."
        if not self.market_linked and (
            self.market_symbol or self.market_exchange or self.market_identity
        ):
            errors["market_linked"] = "Unlinked assets cannot contain market identity fields."
        if self.market_linked and (
            not self.market_symbol
            or self.market_data_status == self.MarketDataStatus.UNLINKED
        ):
            errors["market_linked"] = (
                "Linked assets require a symbol and linked market-data status."
            )
        if not self.market_linked and self.market_data_status != self.MarketDataStatus.UNLINKED:
            errors["market_data_status"] = "Unlinked assets must use UNLINKED status."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.native_currency = self.native_currency.strip().upper()
        self.country_code = self.country_code.strip().upper()
        self.market_symbol = self.market_symbol.strip().upper()
        self.market_exchange = self.market_exchange.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Holding(models.Model):
    """A manual or synced position connecting an Asset to an ownership Group."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        CLOSED = "CLOSED", "Closed"
        ARCHIVED = "ARCHIVED", "Archived"

    class Source(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        SYNCED = "SYNCED", "Synced"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey(
        Group,
        on_delete=models.PROTECT,
        related_name="holdings",
    )
    asset = models.ForeignKey(
        Asset,
        on_delete=models.PROTECT,
        related_name="holdings",
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE
    )
    source = models.CharField(
        max_length=10, choices=Source.choices, default=Source.MANUAL
    )
    quantity = models.DecimalField(max_digits=28, decimal_places=10, default=1)
    average_cost = models.DecimalField(
        max_digits=24, decimal_places=8, null=True, blank=True
    )
    cost_currency = models.CharField(
        max_length=3, blank=True, validators=[currency_validator]
    )
    manual_value = models.DecimalField(
        max_digits=24, decimal_places=2, null=True, blank=True
    )
    provider_value = models.DecimalField(
        max_digits=24, decimal_places=2, null=True, blank=True
    )
    provider_value_as_of = models.DateTimeField(null=True, blank=True)
    provider_position_id = models.CharField(max_length=255, blank=True)
    provider_security_id = models.CharField(max_length=255, blank=True)
    provider_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=0),
                name="holding_quantity_nonnegative",
            ),
            models.CheckConstraint(
                condition=(models.Q(average_cost__isnull=True) | models.Q(average_cost__gte=0)),
                name="holding_average_cost_nonnegative",
            ),
            models.CheckConstraint(
                condition=(models.Q(manual_value__isnull=True) | models.Q(manual_value__gte=0)),
                name="holding_manual_value_nonnegative",
            ),
            models.UniqueConstraint(
                fields=("group", "provider_position_id"),
                condition=(
                    models.Q(source="SYNCED")
                    & ~models.Q(provider_position_id="")
                ),
                name="unique_synced_provider_position_in_group",
            ),
            models.UniqueConstraint(
                fields=("group", "provider_security_id"),
                condition=(
                    models.Q(source="SYNCED")
                    & models.Q(provider_position_id="")
                    & ~models.Q(provider_security_id="")
                ),
                name="unique_synced_provider_security_without_position",
            ),
        ]

    def clean(self):
        errors = {}
        if not isinstance(self.provider_metadata, dict):
            errors["provider_metadata"] = "Provider metadata must be a JSON object."
        if self.group_id and self.asset_id:
            if self.group.portfolio_id != self.asset.portfolio_id:
                errors["asset"] = "Holding group and asset must belong to the same portfolio."
            if self.source == self.Source.SYNCED and self.group.mode != Group.Mode.SYNCED:
                errors["source"] = "Synced holdings must belong to a synced group."
            if self.source == self.Source.MANUAL and self.group.mode == Group.Mode.SYNCED:
                errors["group"] = "Manual holdings cannot belong to a synced group."
        provider_state = any(
            (
                self.provider_value is not None,
                self.provider_value_as_of is not None,
                self.provider_position_id,
                self.provider_security_id,
                self.provider_metadata,
            )
        )
        if self.source == self.Source.MANUAL and provider_state:
            errors["source"] = "Manual holdings cannot contain provider-owned state."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.cost_currency = self.cost_currency.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.asset} in {self.group}"
