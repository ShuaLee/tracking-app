from django.contrib import admin

from .models import BrokerageConnection, BrokerageUser


@admin.register(BrokerageUser)
class BrokerageUserAdmin(admin.ModelAdmin):
    list_display = ("user", "provider", "provider_user_id", "updated_at")
    search_fields = ("user__email", "provider_user_id")
    readonly_fields = ("encrypted_user_secret", "created_at", "updated_at")


@admin.register(BrokerageConnection)
class BrokerageConnectionAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "portfolio", "provider", "status", "last_synced_at")
    list_filter = ("provider", "status")
    search_fields = ("name", "institution", "user__email", "provider_connection_id")
    readonly_fields = ("provider_connection_id", "last_synced_at", "created_at", "updated_at")
