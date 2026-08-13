from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock

from django.core.cache import caches
from django.test import SimpleTestCase

from integrations.exceptions import ProviderUnavailableError, ResourceNotFoundError
from integrations.market_data.contracts import Quote, SecuritySearchResult
from integrations.market_data.service import MarketDataService


class FailingCache:
    def get(self, *args, **kwargs):
        raise ConnectionError("cache down")

    def set(self, *args, **kwargs):
        raise ConnectionError("cache down")


class MarketDataServiceTests(SimpleTestCase):
    def setUp(self):
        self.cache = caches["market_data"]
        self.cache.clear()
        self.adapter = Mock(provider_name="fake")
        self.service = MarketDataService(adapter=self.adapter, cache_backend=self.cache)
        self.quote = Quote(
            symbol="AAPL",
            price=Decimal("200"),
            currency="USD",
            as_of=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )

    def tearDown(self):
        self.cache.clear()

    def test_quote_cache_hit_avoids_provider_call(self):
        self.adapter.quote.return_value = self.quote

        first = self.service.get_quote("aapl")
        second = self.service.get_quote(" AAPL ")

        self.assertEqual(first, second)
        self.adapter.quote.assert_called_once_with("AAPL")

    def test_negative_cache_avoids_repeated_provider_calls(self):
        self.adapter.quote.side_effect = ResourceNotFoundError("missing")

        with self.assertRaises(ResourceNotFoundError):
            self.service.get_quote("NONE")
        with self.assertRaises(ResourceNotFoundError):
            self.service.get_quote("NONE")

        self.adapter.quote.assert_called_once_with("NONE")

    def test_stale_quote_is_returned_during_provider_outage(self):
        self.adapter.quote.return_value = self.quote
        self.service.get_quote("AAPL")
        self.cache.delete(self.service._key("quote", "_:AAPL"))
        self.adapter.quote.side_effect = ProviderUnavailableError("down")

        stale = self.service.get_quote("AAPL")

        self.assertTrue(stale.stale)
        self.assertEqual(stale.price, self.quote.price)

    def test_provider_error_is_raised_without_stale_data(self):
        self.adapter.quote.side_effect = ProviderUnavailableError("down")

        with self.assertRaises(ProviderUnavailableError):
            self.service.get_quote("AAPL")

    def test_exchange_is_part_of_single_security_cache_identity(self):
        nasdaq = self.quote
        neo = Quote(symbol="AAPL", price=Decimal("28"), exchange="NEO")
        self.adapter.quote.side_effect = [nasdaq, neo]

        first = self.service.get_quote("AAPL", exchange="NASDAQ")
        second = self.service.get_quote("AAPL", exchange="NEO")
        cached = self.service.get_quote("AAPL", exchange="NASDAQ")

        self.assertEqual(first.price, Decimal("200"))
        self.assertEqual(second.price, Decimal("28"))
        self.assertEqual(cached, first)
        self.assertEqual(self.adapter.quote.call_count, 2)

    def test_cache_outage_does_not_block_fresh_provider_data(self):
        self.adapter.quote.return_value = self.quote
        service = MarketDataService(adapter=self.adapter, cache_backend=FailingCache())

        with self.assertLogs("integrations.market_data.service", level="WARNING"):
            result = service.get_quote("AAPL")

        self.assertEqual(result, self.quote)

    def test_search_normalizes_query_and_caches_empty_results(self):
        self.adapter.search.return_value = []

        self.assertEqual(self.service.search("  Apple   Inc ", limit=100), [])
        self.assertEqual(self.service.search("apple inc", limit=25), [])

        self.adapter.search.assert_called_once_with("apple inc", limit=25)

    def test_bulk_quotes_combines_cached_fetched_and_missing_data(self):
        self.adapter.quote.return_value = self.quote
        self.service.get_quote("AAPL")
        msft = Quote(symbol="MSFT", price=Decimal("410"))
        self.adapter.quotes.return_value = {"MSFT": msft}

        result = self.service.get_quotes(["aapl", "MSFT", "NONE", "AAPL"])

        self.assertEqual([quote.symbol for quote in result.quotes], ["AAPL", "MSFT"])
        self.assertEqual(result.unavailable_symbols, ("NONE",))
        self.adapter.quotes.assert_called_once_with(("MSFT", "NONE"))

        second = self.service.get_quotes(["AAPL", "MSFT", "NONE"])
        self.assertEqual(second.unavailable_symbols, ("NONE",))
        self.adapter.quotes.assert_called_once()

    def test_bulk_quotes_return_stale_partial_result_on_outage(self):
        self.adapter.quote.return_value = self.quote
        self.service.get_quote("AAPL")
        self.cache.delete(self.service._key("quote", "_:AAPL"))
        self.adapter.quotes.side_effect = ProviderUnavailableError("down")

        result = self.service.get_quotes(["AAPL", "MSFT"])

        self.assertTrue(result.degraded)
        self.assertTrue(result.quotes[0].stale)
        self.assertEqual(result.unavailable_symbols, ("MSFT",))

        self.service.get_quotes(["MSFT"])
        self.assertEqual(self.adapter.quotes.call_count, 2)

    def test_rejects_invalid_symbol(self):
        with self.assertRaises(ValueError):
            self.service.get_quote(" ")
