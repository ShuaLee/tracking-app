from decimal import Decimal
from unittest.mock import Mock

from django.test import TestCase

from integrations.market_data.contracts import Quote, SecurityProfile
from portfolios.market import create_market_holding, relink_market_holding
from portfolios.models import Asset, Holding
from portfolios.tests.factories import portfolio, user
from portfolios.valuation import value_holding


class MarketLinkedHoldingTests(TestCase):
    def setUp(self):
        self.user = user()
        self.portfolio = portfolio(self.user)
        self.service = Mock()
        self.profile = SecurityProfile(
            symbol="AAPL",
            name="Apple Inc.",
            exchange="NASDAQ",
            currency="USD",
            security_type="stock",
            identity={"isin": "US0378331005"},
        )
        self.service.get_profile.return_value = self.profile

    def test_create_uses_canonical_profile_and_market_quote(self):
        self.service.get_quote.return_value = Quote(
            symbol="AAPL", price=Decimal("210.50"), currency="USD"
        )
        holding = create_market_holding(
            portfolio=self.portfolio,
            symbol="aapl",
            quantity="2",
            average_cost="100",
            service=self.service,
        )

        valuation = value_holding(holding, service=self.service)

        self.assertEqual(holding.asset.name, "Apple Inc.")
        self.assertEqual(holding.asset.market_data_status, Asset.MarketDataStatus.LINKED)
        self.assertEqual(holding.asset.market_identity["isin"], "US0378331005")
        self.assertEqual(valuation.value, Decimal("421.00"))
        self.assertEqual(valuation.source, "MARKET")

    def test_identity_change_blocks_market_value_until_explicit_relink(self):
        holding = create_market_holding(
            portfolio=self.portfolio, symbol="AAPL", service=self.service
        )
        self.service.get_profile.return_value = SecurityProfile(
            symbol="AAPL",
            name="Different Issuer",
            exchange="NASDAQ",
            currency="USD",
            identity={"isin": "US0000000000"},
        )

        valuation = value_holding(holding, service=self.service)

        holding.asset.refresh_from_db()
        self.assertEqual(valuation.source, "UNAVAILABLE")
        self.assertEqual(
            holding.asset.market_data_status, Asset.MarketDataStatus.NEEDS_RELINK
        )
        self.service.get_quote.assert_not_called()

        relink_market_holding(
            holding=holding, symbol="AAPL", service=self.service
        )
        holding.asset.refresh_from_db()
        self.assertEqual(holding.asset.name, "Different Issuer")
        self.assertEqual(holding.asset.market_data_status, Asset.MarketDataStatus.LINKED)

    def test_provider_value_precedes_manual_value(self):
        holding = create_market_holding(
            portfolio=self.portfolio, symbol="AAPL", service=self.service
        )
        holding.asset.market_linked = False
        holding.asset.market_data_status = Asset.MarketDataStatus.UNLINKED
        holding.asset.market_symbol = ""
        holding.asset.market_exchange = ""
        holding.asset.market_identity = {}
        holding.asset.save()
        holding.provider_value = Decimal("50")
        holding.manual_value = Decimal("40")
        holding.save()

        valuation = value_holding(holding, service=self.service)

        self.assertEqual(valuation.value, Decimal("50"))
        self.assertEqual(valuation.source, "PROVIDER")
