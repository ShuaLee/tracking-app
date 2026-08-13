from django.urls import path

from . import views


app_name = "users"

urlpatterns = [
    path("auth/csrf/", views.csrf, name="csrf"),
    path("auth/signup/", views.signup, name="signup"),
    path("auth/login/", views.login_view, name="login"),
    path("auth/logout/", views.logout_view, name="logout"),
    path("auth/password/change/", views.password_change, name="password-change"),
    path("auth/password/reset/", views.password_reset, name="password-reset"),
    path(
        "auth/password/reset/confirm/",
        views.password_reset_confirm,
        name="password-reset-confirm",
    ),
    path("me/", views.me, name="me"),
    path("me/subscription/", views.subscription, name="subscription"),
    path("me/entitlements/", views.entitlements, name="entitlements"),
]

