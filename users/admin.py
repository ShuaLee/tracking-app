from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .forms import UserChangeForm, UserCreationForm
from .models import Profile, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    list_display = ("email", "is_active", "is_staff", "date_joined")
    list_filter = ("is_active", "is_staff", "is_superuser")
    ordering = ("email",)
    search_fields = ("email",)
    readonly_fields = ("date_joined", "updated_at", "last_login")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Status", {"fields": ("is_active", "is_staff", "is_superuser")}),
        ("Permissions", {"fields": ("groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2", "is_staff", "is_active"),
            },
        ),
    )


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "updated_at")
    search_fields = ("name", "user__email")
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")

