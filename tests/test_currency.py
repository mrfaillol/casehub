"""
Tests for core.currency - Currency formatting and symbol helpers.
"""
import pytest
from core.currency import format_currency, currency_symbol


class TestFormatCurrency:
    """Tests for format_currency()."""

    def test_usd_basic(self):
        assert format_currency(1500.00, "USD") == "$1,500.00"

    def test_brl_basic(self):
        assert format_currency(1500.00, "BRL") == "R$ 1.500,00"

    def test_usd_zero(self):
        assert format_currency(0, "USD") == "$0.00"

    def test_brl_zero(self):
        assert format_currency(0, "BRL") == "R$ 0,00"

    def test_brl_large_number(self):
        assert format_currency(1234567.89, "BRL") == "R$ 1.234.567,89"

    def test_usd_large_number(self):
        assert format_currency(1234567.89, "USD") == "$1,234,567.89"

    def test_eur_basic(self):
        result = format_currency(99.99, "EUR")
        assert result == "\u20ac 99,99"

    def test_eur_thousands(self):
        result = format_currency(1500.50, "EUR")
        assert result == "\u20ac 1.500,50"

    def test_gbp_basic(self):
        result = format_currency(1500.50, "GBP")
        assert result == "\u00a31,500.50"

    def test_unknown_currency_defaults_to_usd_format(self):
        # Unknown currencies use USD format (dollar sign)
        assert format_currency(100, "CAD") == "$100.00"

    def test_negative_amount_usd(self):
        result = format_currency(-500.00, "USD")
        assert result == "$-500.00"

    def test_negative_amount_brl(self):
        result = format_currency(-1500.50, "BRL")
        assert result == "R$ -1.500,50"

    def test_none_amount_treated_as_zero(self):
        assert format_currency(None, "USD") == "$0.00"

    def test_invalid_string_amount_treated_as_zero(self):
        assert format_currency("abc", "USD") == "$0.00"

    def test_string_numeric_amount(self):
        assert format_currency("1500.50", "USD") == "$1,500.50"

    def test_default_currency_is_usd(self):
        assert format_currency(100) == "$100.00"

    def test_small_cents_usd(self):
        assert format_currency(0.01, "USD") == "$0.01"

    def test_small_cents_brl(self):
        assert format_currency(0.01, "BRL") == "R$ 0,01"


class TestCurrencySymbol:
    """Tests for currency_symbol()."""

    def test_usd(self):
        assert currency_symbol("USD") == "$"

    def test_brl(self):
        assert currency_symbol("BRL") == "R$"

    def test_eur(self):
        assert currency_symbol("EUR") == "\u20ac"

    def test_gbp(self):
        assert currency_symbol("GBP") == "\u00a3"

    def test_unknown_returns_code(self):
        assert currency_symbol("UNKNOWN") == "UNKNOWN"

    def test_jpy_returns_code(self):
        assert currency_symbol("JPY") == "JPY"

    def test_default_is_usd(self):
        assert currency_symbol() == "$"
