"""Interface-independent formatting helpers for monetary values."""


def format_try(value: float) -> str:
    """Returns a lira amount with Turkish separators, preserving the sign."""
    sign = "-" if value < 0 else ""
    amount = f"{abs(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sign}₺{amount}"
