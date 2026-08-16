"""Models for classifications, expected income, and saved analytical views."""

import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower

from .assets import Holding
from .portfolio import Portfolio
from .validators import currency_validator


class Theme(models.Model):
    """Optional hierarchical investment classification within one portfolio."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    portfolio = models.ForeignKey(
        Portfolio, on_delete=models.CASCADE, related_name="themes"
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="children",
    )
    name = models.CharField(max_length=120)
    target_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    color = models.CharField(max_length=16, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "portfolio",
                name="unique_theme_name_per_portfolio_ci",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(target_percentage__isnull=True)
                    | (
                        models.Q(target_percentage__gte=0)
                        & models.Q(target_percentage__lte=100)
                    )
                ),
                name="theme_target_percentage_range",
            ),
        ]

    def clean(self):
        errors = {}
        if self.parent_id:
            if self.parent_id == self.id:
                errors["parent"] = "A theme cannot be its own parent."
            elif self.parent.portfolio_id != self.portfolio_id:
                errors["parent"] = "Parent theme belongs to another portfolio."
            else:
                ancestor = self.parent
                seen = {self.id}
                while ancestor is not None:
                    if ancestor.id in seen:
                        errors["parent"] = "Theme hierarchy cannot contain a cycle."
                        break
                    seen.add(ancestor.id)
                    ancestor = ancestor.parent
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.name


class ThemeAssignment(models.Model):
    """Exclusive assignment of a Holding to one Theme."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    theme = models.ForeignKey(
        Theme, on_delete=models.CASCADE, related_name="assignments"
    )
    holding = models.OneToOneField(
        Holding, on_delete=models.CASCADE, related_name="theme_assignment"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if (
            self.theme_id
            and self.holding_id
            and self.theme.portfolio_id != self.holding.group.portfolio_id
        ):
            raise ValidationError(
                {"holding": "Theme and holding must belong to the same portfolio."}
            )

    def __str__(self):
        return f"{self.holding} -> {self.theme}"


class IncomeRule(models.Model):
    """User-entered recurring expected-income assumption for a Holding."""

    class Category(models.TextChoices):
        RENT = "RENT", "Rent"
        INTEREST = "INTEREST", "Interest"
        ROYALTY = "ROYALTY", "Royalty"
        STAKING = "STAKING", "Staking"
        DIVIDEND = "DIVIDEND", "Dividend"
        OTHER = "OTHER", "Other"

    class Frequency(models.TextChoices):
        WEEKLY = "WEEKLY", "Weekly"
        MONTHLY = "MONTHLY", "Monthly"
        QUARTERLY = "QUARTERLY", "Quarterly"
        SEMIANNUAL = "SEMIANNUAL", "Semiannual"
        ANNUAL = "ANNUAL", "Annual"
        CUSTOM = "CUSTOM", "Custom"

    FREQUENCY_MULTIPLIERS = {
        Frequency.WEEKLY: Decimal("52"),
        Frequency.MONTHLY: Decimal("12"),
        Frequency.QUARTERLY: Decimal("4"),
        Frequency.SEMIANNUAL: Decimal("2"),
        Frequency.ANNUAL: Decimal("1"),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    holding = models.ForeignKey(
        Holding, on_delete=models.CASCADE, related_name="income_rules"
    )
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=12, choices=Category.choices)
    amount_per_payment = models.DecimalField(max_digits=24, decimal_places=2)
    currency = models.CharField(max_length=3, validators=[currency_validator])
    frequency = models.CharField(max_length=12, choices=Frequency.choices)
    payments_per_year = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_per_payment__gte=0),
                name="income_amount_nonnegative",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(payments_per_year__isnull=True)
                    | models.Q(payments_per_year__gt=0)
                ),
                name="income_payments_per_year_positive",
            ),
        ]

    @property
    def annual_amount(self):
        multiplier = (
            self.payments_per_year
            if self.frequency == self.Frequency.CUSTOM
            else self.FREQUENCY_MULTIPLIERS.get(self.frequency)
        )
        return self.amount_per_payment * multiplier if multiplier is not None else None

    def clean(self):
        errors = {}
        if self.frequency == self.Frequency.CUSTOM and self.payments_per_year is None:
            errors["payments_per_year"] = "Custom frequency requires payments per year."
        if self.frequency != self.Frequency.CUSTOM and self.payments_per_year is not None:
            errors["payments_per_year"] = (
                "Payments per year is only accepted for custom frequency."
            )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.currency = self.currency.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name}: {self.holding}"


class PortfolioView(models.Model):
    """Named analytical presentation over all or selected portfolio holdings."""

    class ScopeMode(models.TextChoices):
        ALL = "ALL", "All holdings"
        SELECTED = "SELECTED", "Selected holdings"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    portfolio = models.ForeignKey(
        Portfolio, on_delete=models.CASCADE, related_name="saved_views"
    )
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=500, blank=True)
    scope_mode = models.CharField(
        max_length=10, choices=ScopeMode.choices, default=ScopeMode.ALL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "portfolio",
                name="unique_portfolio_view_name_ci",
            )
        ]

    def __str__(self):
        return self.name


class ViewHoldingSelection(models.Model):
    """Holding included when a PortfolioView uses selected-holding scope."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    view = models.ForeignKey(
        PortfolioView, on_delete=models.CASCADE, related_name="holding_selections"
    )
    holding = models.ForeignKey(
        Holding, on_delete=models.CASCADE, related_name="view_selections"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("view", "holding"),
                name="unique_holding_selection_per_view",
            )
        ]

    def clean(self):
        if (
            self.view_id
            and self.holding_id
            and self.view.portfolio_id != self.holding.group.portfolio_id
        ):
            raise ValidationError(
                {"holding": "Selected holding belongs to another portfolio."}
            )

    def __str__(self):
        return f"{self.view}: {self.holding}"


class ViewBlock(models.Model):
    """Positioned presentation block with a validated declarative query."""

    class DataSource(models.TextChoices):
        HOLDINGS = "HOLDINGS", "Holdings"
        INCOME = "INCOME", "Income"
        THEMES = "THEMES", "Themes"
        GROUPS = "GROUPS", "Groups"

    class Presentation(models.TextChoices):
        TABLE = "TABLE", "Table"
        LIST = "LIST", "List"
        SUMMARY = "SUMMARY", "Summary"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    view = models.ForeignKey(
        PortfolioView, on_delete=models.CASCADE, related_name="blocks"
    )
    title = models.CharField(max_length=120, blank=True)
    data_source = models.CharField(max_length=12, choices=DataSource.choices)
    presentation = models.CharField(max_length=12, choices=Presentation.choices)
    position = models.PositiveIntegerField(default=0)
    width = models.PositiveSmallIntegerField(default=12)
    configuration = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("position", "created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("view", "position"), name="unique_block_position_per_view"
            ),
            models.CheckConstraint(
                condition=models.Q(width__gte=1) & models.Q(width__lte=12),
                name="view_block_width_range",
            ),
        ]

    def clean(self):
        if not isinstance(self.configuration, dict):
            raise ValidationError(
                {"configuration": "Block configuration must be a JSON object."}
            )
        from ..analytics.configuration import validate_block_configuration

        validate_block_configuration(
            self.data_source, self.presentation, self.configuration
        )

    def __str__(self):
        return self.title or f"{self.get_data_source_display()} block"
