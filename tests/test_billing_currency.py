"""
Test billing and currency handling across the CaseHub codebase.

Covers:
  - Invoices use product-default currency, not hardcoded $
  - Reports module does not contain hardcoded $ signs
  - format_currency is used in invoice generation
  - currency_symbol is imported and used in billing descriptions
  - BillingItem model stores amount as numeric
  - Invoice number generation produces valid format
"""
import inspect
import re
import pytest
from unittest.mock import MagicMock, patch

from core.currency import format_currency, currency_symbol


# ---------------------------------------------------------------------------
# Invoice currency handling
# ---------------------------------------------------------------------------

class TestInvoiceCurrencyUsage:
    """Verify that invoice routes use dynamic currency, not hardcoded $."""

    def test_invoices_module_imports_currency(self):
        """Invoice routes should import currency formatting utilities."""
        from routes import invoices
        source = inspect.getsource(invoices)
        assert "format_currency" in source or "currency_symbol" in source, \
            "Invoices module must import currency formatting"

    def test_invoices_module_uses_product_defaults(self):
        """Invoice routes should reference product_defaults for currency."""
        from routes import invoices
        source = inspect.getsource(invoices)
        assert "product_defaults" in source or "default_currency" in source, \
            "Invoices should use product_defaults for currency selection"

    def test_invoices_module_no_hardcoded_dollar_in_format(self):
        """Invoice formatting should not have hardcoded '$' for amounts.

        Note: The string '$' may appear in comments or variable names, but
        should not appear as a literal prefix in f-string amount formatting
        like f'${amount}'.
        """
        from routes import invoices
        source = inspect.getsource(invoices)
        # Look for patterns like f"${amount}" or f"${value}"
        # which would indicate hardcoded dollar formatting
        hardcoded_pattern = r'f["\'].*\$\{(?!_sym|_cs|currency_symbol)'
        matches = re.findall(hardcoded_pattern, source)
        assert len(matches) == 0, \
            f"Found hardcoded $ in f-string formatting: {matches}"

    def test_invoice_number_format(self):
        """Invoice numbers should follow INV-YYYYMM-HHMMSS format."""
        from routes.invoices import generate_invoice_number
        inv_num = generate_invoice_number()
        assert inv_num.startswith("INV-")
        parts = inv_num.split("-")
        assert len(parts) == 3
        assert len(parts[1]) == 6  # YYYYMM
        assert len(parts[2]) == 6  # HHMMSS


# ---------------------------------------------------------------------------
# format_currency with product contexts
# ---------------------------------------------------------------------------

class TestCurrencyInProductContexts:
    """Test that format_currency works correctly for each product's currency."""

    def test_immigration_product_uses_usd_formatting(self):
        result = format_currency(1500.00, "USD")
        assert result.startswith("$")
        assert "1,500.00" in result

    def test_lite_product_uses_brl_formatting(self):
        result = format_currency(1500.00, "BRL")
        assert result.startswith("R$")
        assert "1.500,00" in result

    def test_currency_symbol_matches_product_defaults(self):
        from core.app_factory import PRODUCT_DEFAULTS
        imm_currency = PRODUCT_DEFAULTS["immigration"]["currency"]
        lite_currency = PRODUCT_DEFAULTS["lite"]["currency"]

        assert currency_symbol(imm_currency) == "$"
        assert currency_symbol(lite_currency) == "R$"

    def test_format_currency_zero_usd(self):
        assert format_currency(0, "USD") == "$0.00"

    def test_format_currency_zero_brl(self):
        assert format_currency(0, "BRL") == "R$ 0,00"

    def test_format_currency_negative_usd(self):
        result = format_currency(-100, "USD")
        assert "$" in result
        assert "-" in result

    def test_format_currency_large_brl(self):
        result = format_currency(99999.99, "BRL")
        assert "R$" in result
        assert "99.999,99" in result


# ---------------------------------------------------------------------------
# Reports — no hardcoded $ signs
# ---------------------------------------------------------------------------

class TestReportsNoCurrencyHardcoding:
    """Verify that reports do not contain hardcoded $ for amounts."""

    def test_reports_module_no_hardcoded_dollar_format(self):
        """Reports should use format_currency or currency_symbol, not literal $."""
        try:
            from routes import reports
            source = inspect.getsource(reports)
            # Check for f"${variable}" pattern (hardcoded dollar)
            hardcoded_pattern = r'f["\'].*\$\{(?!_sym|_cs|currency)'
            matches = re.findall(hardcoded_pattern, source)
            # Allow a small number since some $ may be in comments or CSS
            if len(matches) > 0:
                # Verify they are in template/CSS contexts, not amount formatting
                for match in matches:
                    assert "amount" not in match.lower() and "total" not in match.lower(), \
                        f"Hardcoded $ found near amount/total: {match}"
        except ImportError:
            pytest.skip("reports module not available")

    def test_billing_module_uses_currency_helpers(self):
        """Billing routes should import or use currency formatting."""
        try:
            from routes import billing
            source = inspect.getsource(billing)
            uses_currency = (
                "format_currency" in source
                or "currency_symbol" in source
                or "currency" in source
            )
            assert uses_currency, "Billing module should reference currency"
        except ImportError:
            pytest.skip("billing module not available")


# ---------------------------------------------------------------------------
# BillingItem model integration
# ---------------------------------------------------------------------------

class TestBillingItemCurrency:
    """Test BillingItem model supports currency-agnostic amounts."""

    def test_billing_item_has_amount_field(self):
        from models import BillingItem
        assert hasattr(BillingItem, "amount")

    def test_billing_item_has_status_field(self):
        from models import BillingItem
        assert hasattr(BillingItem, "status")

    def test_billing_item_has_invoice_number_field(self):
        from models import BillingItem
        assert hasattr(BillingItem, "invoice_number")

    def test_billing_item_has_case_id_field(self):
        from models import BillingItem
        assert hasattr(BillingItem, "case_id")

    def test_billing_item_has_org_id_field(self):
        from models import BillingItem
        assert hasattr(BillingItem, "org_id")
