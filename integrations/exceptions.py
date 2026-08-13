class IntegrationError(Exception):
    """Base exception exposed by provider-neutral integration services."""

    code = "integration_error"

    def __init__(self, message=None, *, retry_after=None):
        self.retry_after = retry_after
        super().__init__(message or "An integration error occurred.")


class IntegrationConfigurationError(IntegrationError):
    code = "configuration_error"


class ProviderAuthenticationError(IntegrationError):
    code = "provider_authentication_error"


class ProviderRateLimitError(IntegrationError):
    code = "provider_rate_limit"


class ProviderUnavailableError(IntegrationError):
    code = "provider_unavailable"


class ProviderResponseError(IntegrationError):
    code = "provider_response_error"


class ResourceNotFoundError(IntegrationError):
    code = "resource_not_found"

