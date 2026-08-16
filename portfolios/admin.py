"""Django admin configuration for portfolio-domain records."""

from django.contrib import admin

from .models import (
    Asset,
    AssetType,
    Group,
    Holding,
    IncomeRule,
    Portfolio,
    PortfolioView,
    Theme,
    ThemeAssignment,
    ViewBlock,
    ViewHoldingSelection,
)
from .services.holdings import delete_portfolio


@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "base_currency", "created_at")
    search_fields = ("name", "owner__email")
    autocomplete_fields = ("owner",)
    readonly_fields = ("created_at", "updated_at")

    def delete_model(self, request, obj):
        delete_portfolio(portfolio=obj)

    def delete_queryset(self, request, queryset):
        for portfolio in queryset:
            delete_portfolio(portfolio=portfolio)


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("name", "portfolio", "mode", "is_ungrouped", "provider")
    list_filter = ("mode", "is_ungrouped", "provider")
    search_fields = ("name", "portfolio__name", "portfolio__owner__email")
    autocomplete_fields = ("portfolio",)
    readonly_fields = ("is_ungrouped", "created_at", "updated_at")

    def has_delete_permission(self, request, obj=None):
        allowed = super().has_delete_permission(request, obj)
        return allowed and (obj is None or obj.mode == Group.Mode.MANUAL)


@admin.register(AssetType)
class AssetTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "system_category", "owner", "is_active")
    list_filter = ("system_category", "is_active")
    search_fields = ("name", "owner__email")
    autocomplete_fields = ("owner",)
    readonly_fields = ("created_at", "updated_at")

    def has_delete_permission(self, request, obj=None):
        allowed = super().has_delete_permission(request, obj)
        return allowed and (obj is None or not obj.is_system)


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = (
        "name", "portfolio", "asset_type", "country_code", "status", "market_linked"
    )
    list_filter = (
        "status", "market_linked", "country_code", "asset_type__system_category"
    )
    search_fields = ("name", "portfolio__name", "portfolio__owner__email")
    autocomplete_fields = ("portfolio", "asset_type")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Holding)
class HoldingAdmin(admin.ModelAdmin):
    list_display = ("asset", "group", "source", "status", "quantity", "manual_value")
    list_filter = ("source", "status", "group__mode")
    search_fields = ("asset__name", "group__name", "group__portfolio__owner__email")
    autocomplete_fields = ("group", "asset")
    readonly_fields = ("created_at", "updated_at")

    def has_delete_permission(self, request, obj=None):
        allowed = super().has_delete_permission(request, obj)
        return allowed and (obj is None or obj.source == Holding.Source.MANUAL)


@admin.register(Theme)
class ThemeAdmin(admin.ModelAdmin):
    list_display = ("name", "portfolio", "parent", "target_percentage")
    search_fields = ("name", "portfolio__name", "portfolio__owner__email")
    autocomplete_fields = ("portfolio", "parent")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ThemeAssignment)
class ThemeAssignmentAdmin(admin.ModelAdmin):
    list_display = ("theme", "holding", "created_at")
    search_fields = ("theme__name", "holding__asset__name")
    autocomplete_fields = ("theme", "holding")
    readonly_fields = ("created_at", "updated_at")


@admin.register(IncomeRule)
class IncomeRuleAdmin(admin.ModelAdmin):
    list_display = (
        "name", "holding", "category", "amount_per_payment", "currency",
        "frequency", "is_active",
    )
    list_filter = ("category", "frequency", "is_active", "currency")
    search_fields = ("name", "holding__asset__name")
    autocomplete_fields = ("holding",)
    readonly_fields = ("created_at", "updated_at")


class ViewBlockInline(admin.TabularInline):
    model = ViewBlock
    extra = 0
    readonly_fields = ("created_at", "updated_at")


class ViewHoldingSelectionInline(admin.TabularInline):
    model = ViewHoldingSelection
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(PortfolioView)
class PortfolioViewAdmin(admin.ModelAdmin):
    list_display = ("name", "portfolio", "scope_mode", "created_at")
    search_fields = ("name", "portfolio__name", "portfolio__owner__email")
    autocomplete_fields = ("portfolio",)
    readonly_fields = ("created_at", "updated_at")
    inlines = (ViewHoldingSelectionInline, ViewBlockInline)


@admin.register(ViewHoldingSelection)
class ViewHoldingSelectionAdmin(admin.ModelAdmin):
    list_display = ("view", "holding", "created_at")
    search_fields = ("view__name", "holding__asset__name")
    autocomplete_fields = ("view", "holding")
    readonly_fields = ("created_at",)


@admin.register(ViewBlock)
class ViewBlockAdmin(admin.ModelAdmin):
    list_display = ("title", "view", "data_source", "presentation", "position", "width")
    list_filter = ("data_source", "presentation")
    search_fields = ("title", "view__name")
    autocomplete_fields = ("view",)
    readonly_fields = ("created_at", "updated_at")
