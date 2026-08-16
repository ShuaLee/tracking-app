"""Reusable validators shared by portfolio model modules."""

from django.core.validators import RegexValidator


currency_validator = RegexValidator(
    regex=r"^[A-Z]{3}$",
    message="Currency must be a three-letter ISO 4217 code.",
)
country_code_validator = RegexValidator(
    regex=r"^[A-Z]{2}$",
    message="Country must be a two-letter ISO 3166-1 code.",
)

