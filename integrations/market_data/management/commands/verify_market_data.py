from django.core.management.base import BaseCommand, CommandError

from integrations.exceptions import IntegrationError
from integrations.market_data.service import MarketDataService


class Command(BaseCommand):
    help = "Run a read-only live verification against the configured market-data provider."

    def add_arguments(self, parser):
        parser.add_argument("--query", default="Apple")
        parser.add_argument("--symbol", default="AAPL")

    def handle(self, *args, **options):
        try:
            service = MarketDataService()
            results = service.search(options["query"], limit=5)
            quote = service.get_quote(options["symbol"])
            profile = service.get_profile(options["symbol"])
            dividends = service.get_dividends(options["symbol"])
        except IntegrationError as exc:
            raise CommandError(f"Market-data verification failed ({exc.code}): {exc}") from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Market data verified: {len(results)} search results; "
                f"{quote.symbol}={quote.price} {quote.currency}; "
                f"profile={profile.name}; dividends={len(dividends)}"
            )
        )

