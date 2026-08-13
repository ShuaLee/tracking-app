from django.apps import AppConfig


class MarketDataConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "integrations.market_data"

    def ready(self):
        from integrations import checks  # noqa: F401
