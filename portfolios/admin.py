from django.contrib import admin

from .models import Asset, AssetType, Group, Holding, Portfolio
from .services import delete_portfolio


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
    list_display = ("name", "portfolio", "asset_type", "status", "market_linked")
    list_filter = ("status", "market_linked", "asset_type__system_category")
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
