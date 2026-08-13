from integrations.exceptions import IntegrationConfigurationError, ResourceNotFoundError
from integrations.http import JsonHttpClient
from integrations.utils import as_date, as_datetime, as_decimal
from integrations.market_data.contracts import (
    DividendEvent,
    Quote,
    SecurityProfile,
    SecuritySearchResult,
)


class FMPMarketDataAdapter:
    provider_name = "fmp"

    def __init__(self, *, api_key, base_url="https://financialmodelingprep.com/stable", timeout=10, client=None):
        if not api_key:
            raise IntegrationConfigurationError("FMP_API_KEY is not configured.")
        self.client = client or JsonHttpClient(
            base_url=base_url,
            timeout=timeout,
            default_headers={"apikey": api_key, "Accept": "application/json"},
        )

    def search(self, query, *, limit=10):
        payload = self.client.get("search-name", {"query": query, "limit": limit})
        if not isinstance(payload, list):
            return []
        results = []
        for item in payload[:limit]:
            if not isinstance(item, dict) or not item.get("symbol"):
                continue
            results.append(
                SecuritySearchResult(
                    symbol=str(item["symbol"]).upper(),
                    name=str(item.get("name") or item["symbol"]),
                    exchange=str(item.get("exchange") or item.get("exchangeShortName") or ""),
                    currency=str(item.get("currency") or "").upper(),
                    security_type=str(item.get("type") or ""),
                    identity=self._identity(item),
                )
            )
        return results

    def quote(self, symbol):
        payload = self.client.get("quote", {"symbol": symbol})
        item = self._first(payload, symbol)
        price = as_decimal(item.get("price"))
        if price is None:
            raise ResourceNotFoundError(f"No quote is available for {symbol}.")
        return Quote(
            symbol=str(item.get("symbol") or symbol).upper(),
            price=price,
            currency=str(item.get("currency") or "").upper(),
            exchange=str(item.get("exchange") or item.get("exchangeShortName") or ""),
            as_of=as_datetime(item.get("timestamp")),
            change=as_decimal(item.get("change")),
            change_percent=as_decimal(item.get("changePercentage") or item.get("changesPercentage")),
            volume=as_decimal(item.get("volume")),
        )

    def quotes(self, symbols):
        normalized = [symbol.upper() for symbol in symbols]
        if not normalized:
            return {}
        payload = self.client.get("batch-quote", {"symbols": ",".join(normalized)})
        if not isinstance(payload, list):
            return {}
        quotes = {}
        for item in payload:
            if not isinstance(item, dict) or not item.get("symbol"):
                continue
            try:
                quote = self._quote_from_item(item)
            except ResourceNotFoundError:
                continue
            quotes[quote.symbol] = quote
        return quotes

    def profile(self, symbol):
        payload = self.client.get("profile", {"symbol": symbol})
        item = self._first(payload, symbol)
        item_symbol = str(item.get("symbol") or symbol).upper()
        security_type = "ETF" if item.get("isEtf") else "FUND" if item.get("isFund") else "STOCK"
        return SecurityProfile(
            symbol=item_symbol,
            name=str(item.get("companyName") or item.get("name") or item_symbol),
            exchange=str(item.get("exchange") or item.get("exchangeShortName") or ""),
            currency=str(item.get("currency") or "").upper(),
            security_type=security_type,
            sector=str(item.get("sector") or ""),
            industry=str(item.get("industry") or ""),
            description=str(item.get("description") or ""),
            website=str(item.get("website") or ""),
            identity=self._identity(item),
            active=item.get("isActivelyTrading"),
        )

    def dividends(self, symbol):
        payload = self.client.get("dividends", {"symbol": symbol})
        if not isinstance(payload, list):
            return []
        events = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            ex_date = as_date(item.get("date") or item.get("exDividendDate"))
            amount = as_decimal(item.get("dividend"))
            if ex_date is None or amount is None:
                continue
            events.append(
                DividendEvent(
                    symbol=str(item.get("symbol") or symbol).upper(),
                    ex_date=ex_date,
                    amount=amount,
                    adjusted_amount=as_decimal(item.get("adjDividend")),
                    declaration_date=as_date(item.get("declarationDate")),
                    record_date=as_date(item.get("recordDate")),
                    payment_date=as_date(item.get("paymentDate")),
                    currency=str(item.get("currency") or "").upper(),
                    frequency=str(item.get("frequency") or ""),
                )
            )
        return sorted(events, key=lambda event: event.ex_date, reverse=True)

    def _quote_from_item(self, item):
        symbol = str(item.get("symbol") or "").upper()
        price = as_decimal(item.get("price"))
        if not symbol or price is None:
            raise ResourceNotFoundError("Quote payload is incomplete.")
        return Quote(
            symbol=symbol,
            price=price,
            currency=str(item.get("currency") or "").upper(),
            exchange=str(item.get("exchange") or item.get("exchangeShortName") or ""),
            as_of=as_datetime(item.get("timestamp")),
            change=as_decimal(item.get("change")),
            change_percent=as_decimal(item.get("changePercentage") or item.get("changesPercentage")),
            volume=as_decimal(item.get("volume")),
        )

    @staticmethod
    def _first(payload, symbol):
        if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
            raise ResourceNotFoundError(f"Provider has no data for {symbol}.")
        return payload[0]

    @staticmethod
    def _identity(item):
        return {
            key: item[key]
            for key in ("isin", "cusip", "cik")
            if item.get(key) not in (None, "")
        }
