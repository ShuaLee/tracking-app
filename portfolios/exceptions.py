"""Domain-specific exceptions translated by the portfolio API boundary."""


class PortfolioDomainError(Exception):
    def __init__(self, message, *, code="invalid_request", fields=None):
        self.code = code
        self.fields = fields or {}
        super().__init__(message)


class EntitlementLimitError(PortfolioDomainError):
    def __init__(self, message, *, resource):
        super().__init__(
            message,
            code="entitlement_limit_reached",
            fields={resource: [message]},
        )


class ProtectedOperationError(PortfolioDomainError):
    def __init__(self, message):
        super().__init__(message, code="protected_operation")
