"""
CaseHub - Currency Formatting Helpers

Provides locale-aware currency formatting for multi-currency support.
Supports USD, BRL, EUR, GBP out of the box.
"""


def format_currency(amount, currency: str = "USD") -> str:
    """
    Format amount with currency symbol and locale-appropriate separators.

    Examples:
        format_currency(1500.50, "USD") -> "$1,500.50"
        format_currency(1500.50, "BRL") -> "R$ 1.500,50"
        format_currency(1500.50, "EUR") -> "1.500,50 EUR"
        format_currency(1500.50, "GBP") -> "GBP 1,500.50"
    """
    try:
        amount = float(amount or 0)
    except (TypeError, ValueError):
        amount = 0.0

    if currency == "BRL":
        # Brazilian format: R$ 1.500,00
        formatted = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {formatted}"
    elif currency == "EUR":
        # European format: 1.500,00 EUR (symbol after)
        formatted = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"\u20ac {formatted}"
    elif currency == "GBP":
        # British format: same separators as USD
        return f"\u00a3{amount:,.2f}"
    else:
        # USD format (default): $1,500.00
        return f"${amount:,.2f}"


def currency_symbol(currency: str = "USD") -> str:
    """Return the symbol for a given currency code."""
    symbols = {
        "USD": "$",
        "BRL": "R$",
        "EUR": "\u20ac",
        "GBP": "\u00a3",
    }
    return symbols.get(currency, currency)
