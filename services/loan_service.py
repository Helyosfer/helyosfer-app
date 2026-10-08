"""Loan instalment calculation with a full repayment schedule.

The annuity formula: instalment = P * i * (1 + i)^n / ((1 + i)^n - 1), where
`i` is the monthly rate the borrower actually pays. For consumer loans in
Türkiye the interest carries two taxes (KKDF and BSMV), so the effective rate
is the stated monthly rate times (1 + KKDF + BSMV).

Arithmetic is in Decimal and only the outputs are rounded to the kurus.
"""

from __future__ import annotations

from decimal import Decimal

from utils.financial_decimal import decimal_from, fiat

KKDF = Decimal("0.15")
BSMV = Decimal("0.15")
MAX_MONTHS = 360


def calculate_loan(principal, monthly_rate_percent, months, include_taxes=True) -> dict:
    """Returns the instalment, the totals and the month-by-month schedule.

    The total repaid is the ROUNDED instalment times the count -- exactly what
    the borrower's payments add up to, and what a debt recorded from this
    result will hold.
    """
    try:
        amount = decimal_from(principal)
        rate = decimal_from(monthly_rate_percent) / 100
        count = int(months)
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise ValueError("Lütfen 0'dan büyük değerler girin!") from exc
    if amount <= 0 or rate <= 0 or count <= 0:
        raise ValueError("Lütfen 0'dan büyük değerler girin!")
    if count > MAX_MONTHS:
        raise ValueError("Vade en fazla 360 ay olabilir.")

    tax = (KKDF + BSMV) if include_taxes else Decimal(0)
    effective = rate * (1 + tax)
    growth = (1 + effective) ** count
    instalment = amount * effective * growth / (growth - 1)
    monthly = fiat(instalment)
    total = monthly * count

    schedule = []
    balance = amount
    for month in range(1, count + 1):
        interest = balance * rate
        charges = interest * (1 + tax)
        repaid = instalment - charges
        balance = max(balance - repaid, Decimal(0))
        schedule.append({
            "month": month,
            "payment": float(monthly),
            "principal": float(fiat(repaid)),
            "interest": float(fiat(charges)),
            "balance": float(fiat(balance)) if month < count else 0.0,
        })

    return {
        "monthly_payment": float(monthly),
        "total_repayment": float(total),
        "total_cost": float(total - fiat(amount)),
        "months": count,
        "schedule": schedule,
    }
