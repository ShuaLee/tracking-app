from datetime import date, timezone
from decimal import Decimal
from unittest.mock import Mock

from django.test import SimpleTestCase

from integrations.exceptions import IntegrationConfigurationError, ResourceNotFoundError
from integrations.market_data.providers.fmp import FMPMarketDataAdapter


class FMPAdapterTests(SimpleTestCase):
    def setUp(self):
        self.client = Mock()
        self.adapter = FMPMarketDataAdapter(api_key="secret", client=self.client)

    def test_requires_api_key(self):
        with self.assertRaises(IntegrationConfigurationError):
            FMPMarketDataAdapter(api_key="")

    def test_search_normalizes_provider_payload(self):
        self.client.get.return_value = [
            {
                "symbol": "AAPL",
                "name": "Apple Inc.",
                "currency": "USD",
                "exchangeShortName": "NASDAQ",
                "type": "stock",
                "cik": "0000320193",
            },
            {"name": "Incomplete"},
        ]

        results = self.adapter.search("apple", limit=5)

        self.client.get.assert_called_once_with(
            "search-name", {"query": "apple", "limit": 5}
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].symbol, "AAPL")
        self.assertEqual(results[0].exchange, "NASDAQ")
        self.assertEqual(results[0].identity, {"cik": "0000320193"})

    def test_quote_normalizes_decimal_and_timestamp(self):
        self.client.get.return_value = [
            {
                "symbol": "AAPL",
                "price": 227.16,
                "change": "1.25",
                "changePercentage": "0.55",
                "volume": 12345,
                "timestamp": 1723500000,
                "currency": "USD",
                "exchange": "NASDAQ",
            }
        ]

        quote = self.adapter.quote("AAPL")

        self.assertEqual(quote.price, Decimal("227.16"))
        self.assertEqual(quote.change, Decimal("1.25"))
        self.assertEqual(quote.as_of.tzinfo, timezone.utc)

    def test_quote_rejects_empty_or_incomplete_payload(self):
        self.client.get.return_value = []
        with self.assertRaises(ResourceNotFoundError):
            self.adapter.quote("MISSING")

        self.client.get.return_value = [{"symbol": "MISSING"}]
        with self.assertRaises(ResourceNotFoundError):
            self.adapter.quote("MISSING")

    def test_batch_quotes_ignores_incomplete_rows(self):
        self.client.get.return_value = [
            {"symbol": "AAPL", "price": 200},
            {"symbol": "BAD"},
        ]

        quotes = self.adapter.quotes(["aapl", "bad"])

        self.client.get.assert_called_once_with(
            "batch-quote", {"symbols": "AAPL,BAD"}
        )
        self.assertEqual(list(quotes), ["AAPL"])

    def test_profile_preserves_identity_fingerprint(self):
        self.client.get.return_value = [
            {
                "symbol": "AAPL",
                "companyName": "Apple Inc.",
                "exchange": "NASDAQ",
                "currency": "USD",
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "description": "Description",
                "website": "https://apple.com",
                "isin": "US0378331005",
                "cusip": "037833100",
                "cik": "0000320193",
                "isActivelyTrading": True,
            }
        ]

        profile = self.adapter.profile("AAPL")

        self.assertEqual(profile.name, "Apple Inc.")
        self.assertEqual(profile.security_type, "STOCK")
        self.assertEqual(profile.identity["isin"], "US0378331005")
        self.assertTrue(profile.active)

    def test_dividends_normalize_and_sort_valid_events(self):
        self.client.get.return_value = [
            {"symbol": "AAPL", "date": "2025-02-07", "dividend": 0.25},
            {
                "symbol": "AAPL",
                "date": "2025-05-12",
                "dividend": "0.26",
                "adjDividend": "0.26",
                "recordDate": "2025-05-12",
                "paymentDate": "2025-05-15",
                "declarationDate": "2025-05-01",
                "frequency": "Quarterly",
            },
            {"symbol": "AAPL", "date": "invalid", "dividend": 1},
        ]

        dividends = self.adapter.dividends("AAPL")

        self.assertEqual(len(dividends), 2)
        self.assertEqual(dividends[0].ex_date, date(2025, 5, 12))
        self.assertEqual(dividends[0].amount, Decimal("0.26"))

