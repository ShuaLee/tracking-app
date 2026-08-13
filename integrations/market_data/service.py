import hashlib
import logging
from dataclasses import replace

from django.conf import settings
from django.core.cache import caches

from integrations.exceptions import IntegrationError, ResourceNotFoundError
from .contracts import QuoteBatch
from .providers.fmp import FMPMarketDataAdapter


logger = logging.getLogger(__name__)
MISSING = {"__market_data_missing__": True}
NOT_CACHED = object()


class MarketDataService:
    cache_version = "v1"

    def __init__(self, *, adapter=None, cache_backend=None):
        config = settings.MARKET_DATA
        self.adapter = adapter or FMPMarketDataAdapter(
            api_key=config.get("FMP_API_KEY", ""),
            base_url=config["FMP_BASE_URL"],
            timeout=config["HTTP_TIMEOUT"],
        )
        self.cache = cache_backend or caches[config["CACHE_ALIAS"]]
        self.ttls = config["TTLS"]

    def search(self, query, *, limit=10):
        normalized = " ".join(str(query).strip().lower().split())
        if not normalized:
            return []
        limit = max(1, min(int(limit), 25))
        digest = hashlib.sha256(normalized.encode()).hexdigest()[:24]
        key = self._key("search", f"{digest}:{limit}")
        return self._get_or_fetch(
            key,
            lambda: self.adapter.search(normalized, limit=limit),
            ttl=self.ttls["SEARCH"],
            stale_ttl=self.ttls["SEARCH_STALE"],
            empty_is_missing=False,
        )

    def get_quote(self, symbol, *, exchange=""):
        symbol = self._symbol(symbol)
        identifier = self._identifier(symbol, exchange)
        return self._get_or_fetch(
            self._key("quote", identifier),
            lambda: self.adapter.quote(symbol),
            ttl=self.ttls["QUOTE"],
            stale_ttl=self.ttls["QUOTE_STALE"],
        )

    def get_quotes(self, symbols):
        normalized = tuple(dict.fromkeys(self._symbol(symbol) for symbol in symbols))
        quotes = {}
        missing = []
        unavailable = []
        for symbol in normalized:
            key = self._key("quote", self._identifier(symbol))
            value = self._cache_get(key)
            if value is NOT_CACHED:
                missing.append(symbol)
            elif value == MISSING:
                unavailable.append(symbol)
            else:
                quotes[symbol] = value

        degraded = False
        provider_failed = False
        if missing:
            try:
                fetched = self.adapter.quotes(tuple(missing))
            except IntegrationError:
                fetched = {}
                degraded = True
                provider_failed = True
            for symbol in missing:
                quote = fetched.get(symbol)
                if quote is not None:
                    quotes[symbol] = quote
                    key = self._key("quote", self._identifier(symbol))
                    self._store(key, quote, self.ttls["QUOTE"], self.ttls["QUOTE_STALE"])
                    continue
                key = self._key("quote", self._identifier(symbol))
                stale = self._cache_get(self._stale_key(key))
                if stale is not NOT_CACHED and stale != MISSING:
                    quotes[symbol] = replace(stale, stale=True)
                    degraded = True
                else:
                    unavailable.append(symbol)
                    if not provider_failed:
                        self._cache_set(key, MISSING, self.ttls["NEGATIVE"])

        ordered = tuple(quotes[symbol] for symbol in normalized if symbol in quotes)
        return QuoteBatch(ordered, tuple(unavailable), degraded)

    def get_profile(self, symbol, *, exchange=""):
        symbol = self._symbol(symbol)
        identifier = self._identifier(symbol, exchange)
        return self._get_or_fetch(
            self._key("profile", identifier),
            lambda: self.adapter.profile(symbol),
            ttl=self.ttls["PROFILE"],
            stale_ttl=self.ttls["PROFILE_STALE"],
        )

    def get_dividends(self, symbol, *, exchange=""):
        symbol = self._symbol(symbol)
        identifier = self._identifier(symbol, exchange)
        return self._get_or_fetch(
            self._key("dividends", identifier),
            lambda: self.adapter.dividends(symbol),
            ttl=self.ttls["DIVIDENDS"],
            stale_ttl=self.ttls["DIVIDENDS_STALE"],
            empty_is_missing=False,
        )

    def _get_or_fetch(self, key, fetch, *, ttl, stale_ttl, empty_is_missing=True):
        cached = self._cache_get(key)
        if cached == MISSING:
            raise ResourceNotFoundError("Market data is unavailable for this identifier.")
        if cached is not NOT_CACHED:
            return cached
        try:
            value = fetch()
        except ResourceNotFoundError:
            self._cache_set(key, MISSING, self.ttls["NEGATIVE"])
            raise
        except IntegrationError:
            stale = self._cache_get(self._stale_key(key))
            if stale is not NOT_CACHED and stale != MISSING:
                if isinstance(stale, list):
                    return [replace(item, stale=True) for item in stale]
                return replace(stale, stale=True)
            raise
        if empty_is_missing and value is None:
            self._cache_set(key, MISSING, self.ttls["NEGATIVE"])
            raise ResourceNotFoundError("Market data is unavailable for this identifier.")
        self._store(key, value, ttl, stale_ttl)
        return value

    def _store(self, key, value, ttl, stale_ttl):
        self._cache_set(key, value, ttl)
        self._cache_set(self._stale_key(key), value, stale_ttl)

    def _cache_get(self, key):
        try:
            return self.cache.get(key, NOT_CACHED)
        except Exception:
            logger.warning("Market-data cache read failed.", exc_info=True)
            return NOT_CACHED

    def _cache_set(self, key, value, timeout):
        try:
            self.cache.set(key, value, timeout)
        except Exception:
            logger.warning("Market-data cache write failed.", exc_info=True)

    def _key(self, data_type, identifier):
        provider = getattr(self.adapter, "provider_name", "provider")
        return f"market:{self.cache_version}:{provider}:{data_type}:{identifier}"

    @staticmethod
    def _stale_key(key):
        return f"{key}:stale"

    @staticmethod
    def _symbol(symbol):
        normalized = str(symbol).strip().upper()
        if not normalized or len(normalized) > 64:
            raise ValueError("A valid market symbol is required.")
        return normalized

    @staticmethod
    def _identifier(symbol, exchange=""):
        normalized_exchange = str(exchange).strip().upper()
        if len(normalized_exchange) > 64:
            raise ValueError("A valid market exchange is required.")
        return f"{normalized_exchange or '_'}:{symbol}"
