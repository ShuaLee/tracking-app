from django.contrib import admin

from .models import Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "status", "updated_at")
    list_filter = ("plan", "status")
    search_fields = ("user__email",)
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")

