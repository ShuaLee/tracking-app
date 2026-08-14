from copy import deepcopy

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.checks import Tags, run_checks
from django.test import SimpleTestCase, override_settings


def integration_messages():
    return [
        message
        for message in run_checks(
            tags=[Tags.security], include_deployment_checks=True
        )
        if message.id.startswith("integrations.")
    ]


class IntegrationDeploymentCheckTests(SimpleTestCase):
    @override_settings(
        REDIS_URL="",
        MARKET_DATA={"FMP_API_KEY": "", "FMP_BASE_URL": "http://fmp.example", "TTLS": {}},
        BROKERAGE={"SNAPTRADE_CLIENT_ID": "", "SNAPTRADE_CONSUMER_KEY": ""},
    )
    def test_reports_missing_or_insecure_production_configuration(self):
        identifiers = {message.id for message in integration_messages()}

        self.assertTrue(
            {
                "integrations.E001", "integrations.E003", "integrations.E004",
                "integrations.E005", "integrations.E006",
            }
            <= identifiers
        )
        self.assertIn("integrations.W001", identifiers)

    def test_accepts_complete_production_configuration(self):
        market_data = deepcopy(settings.MARKET_DATA)
        market_data["FMP_API_KEY"] = "configured"
        brokerage = {
            "SNAPTRADE_CLIENT_ID": "configured",
            "SNAPTRADE_CONSUMER_KEY": "configured",
        }
        with override_settings(
            REDIS_URL="rediss://redis.example/1",
            MARKET_DATA=market_data,
            BROKERAGE=brokerage,
            BROKERAGE_CREDENTIAL_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
        ):
            self.assertEqual(integration_messages(), [])
