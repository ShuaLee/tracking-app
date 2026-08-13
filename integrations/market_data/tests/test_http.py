import json
from email.message import Message
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from django.test import SimpleTestCase

from integrations.exceptions import (
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderUnavailableError,
    ResourceNotFoundError,
)
from integrations.http import JsonHttpClient


class JsonHttpClientTests(SimpleTestCase):
    def setUp(self):
        self.client = JsonHttpClient(
            base_url="https://provider.example/stable",
            default_headers={"apikey": "secret"},
        )

    @patch("integrations.http.urlopen")
    def test_get_encodes_query_and_decodes_json(self, urlopen):
        response = Mock()
        response.read.return_value = json.dumps([{"symbol": "AAPL"}]).encode()
        urlopen.return_value.__enter__.return_value = response

        result = self.client.get("search-name", {"query": "Apple Inc"})

        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://provider.example/stable/search-name?query=Apple+Inc",
        )
        self.assertEqual(request.headers["Apikey"], "secret")
        self.assertEqual(result, [{"symbol": "AAPL"}])

    @patch("integrations.http.urlopen")
    def test_maps_http_errors_without_exposing_response_body(self, urlopen):
        cases = [
            (403, ProviderAuthenticationError),
            (404, ResourceNotFoundError),
            (429, ProviderRateLimitError),
            (503, ProviderUnavailableError),
            (422, ProviderResponseError),
        ]
        for status, expected in cases:
            headers = Message()
            headers["Retry-After"] = "30"
            urlopen.side_effect = HTTPError(
                "https://provider.example", status, "reason", headers, None
            )
            with self.subTest(status=status), self.assertRaises(expected) as context:
                self.client.get("quote", {"symbol": "AAPL"})
            if status == 429:
                self.assertEqual(context.exception.retry_after, "30")

    @patch("integrations.http.urlopen", side_effect=URLError("offline"))
    def test_maps_network_error(self, urlopen):
        with self.assertRaises(ProviderUnavailableError):
            self.client.get("quote")

    @patch("integrations.http.urlopen")
    def test_rejects_invalid_json_and_provider_error_payload(self, urlopen):
        response = Mock()
        urlopen.return_value.__enter__.return_value = response
        response.read.return_value = b"not-json"
        with self.assertRaises(ProviderResponseError):
            self.client.get("quote")

        response.read.return_value = b'{"Error Message":"bad key"}'
        with self.assertRaises(ProviderResponseError):
            self.client.get("quote")

