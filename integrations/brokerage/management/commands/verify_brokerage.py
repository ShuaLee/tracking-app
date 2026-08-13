import os

from django.core.management.base import BaseCommand, CommandError

from integrations.brokerage.contracts import BrokerageCredentials
from integrations.brokerage.service import BrokerageService
from integrations.exceptions import IntegrationError


class Command(BaseCommand):
    help = "Run a read-only live verification against SnapTrade."

    def handle(self, *args, **options):
        try:
            service = BrokerageService()
            service.check_status()
            account_count = 0
            position_count = 0
            user_id = os.environ.get("SNAPTRADE_TEST_USER_ID", "")
            user_secret = os.environ.get("SNAPTRADE_TEST_USER_SECRET", "")
            if user_id or user_secret:
                if not user_id or not user_secret:
                    raise CommandError(
                        "Configure both SNAPTRADE_TEST_USER_ID and "
                        "SNAPTRADE_TEST_USER_SECRET."
                    )
                credentials = BrokerageCredentials(
                    user_id, user_secret
                )
                accounts = service.list_accounts(credentials)
                account_count = len(accounts)
                for account in accounts:
                    position_count += len(
                        service.list_positions(
                            credentials, account.provider_account_id
                        ).positions
                    )
        except IntegrationError as exc:
            raise CommandError(f"Brokerage verification failed ({exc.code}): {exc}") from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"SnapTrade verified: accounts={account_count}; positions={position_count}"
            )
        )
