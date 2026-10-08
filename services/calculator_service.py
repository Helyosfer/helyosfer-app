"""Deposit interest, compound growth and time-to-goal calculations.

Pure functions: nothing here reads or writes the profile. Arithmetic is in
Decimal and only the outputs are rounded to the kurus.
"""

from __future__ import annotations

import math
from decimal import Decimal

from utils.financial_decimal import decimal_from, fiat

WITHHOLDING_TAX = Decimal("0.05")
DAYS_IN_YEAR = Decimal(365)
MAX_YEARS = 100

DAILY, MONTHLY = "daily", "monthly"
_NOT_POSITIVE = "Lütfen 0'dan büyük değerler girin!"


def _positive(value) -> Decimal:
    try:
        number = decimal_from(value)
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise ValueError(_NOT_POSITIVE) from exc
    if number <= 0:
        raise ValueError(_NOT_POSITIVE)
    return number


def deposit_interest(principal, annual_rate_percent, days) -> dict:
    """Simple interest on a term deposit, after withholding tax.

    gross = P * rate * days / 365; the tax is taken from the interest only.
    """
    amount = _positive(principal)
    rate = _positive(annual_rate_percent) / 100
    term = int(days)
    if not 1 <= term <= 365 * MAX_YEARS:
        raise ValueError(_NOT_POSITIVE)
    gross = amount * rate * term / DAYS_IN_YEAR
    tax = gross * WITHHOLDING_TAX
    net = gross - tax
    return {
        "gross_interest": float(fiat(gross)),
        "tax": float(fiat(tax)),
        "net_interest": float(fiat(net)),
        "maturity_value": float(fiat(amount + net)),
    }


def compound_growth(principal, annual_rate_percent, years, monthly_deposit=0) -> dict:
    """Growth of a starting amount compounded yearly, with optional monthly
    contributions compounded monthly. Returns the year-end values as well.
    """
    amount = _positive(principal)
    rate = _positive(annual_rate_percent) / 100
    term = int(years)
    if not 1 <= term <= MAX_YEARS:
        raise ValueError("Süre 1 ile 100 yıl arasında olmalıdır.")
    try:
        deposit = decimal_from(monthly_deposit or 0)
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise ValueError("Aylık katkı negatif olamaz.") from exc
    if deposit < 0:
        raise ValueError("Aylık katkı negatif olamaz.")

    monthly_rate = rate / 12
    series = []
    for year in range(term + 1):
        value = amount * (1 + rate) ** year
        if deposit > 0:
            value += deposit * (((1 + monthly_rate) ** (year * 12) - 1) / monthly_rate)
        series.append(float(fiat(value)))
    invested = amount + deposit * term * 12
    final = Decimal(str(series[-1]))
    return {
        "invested": float(fiat(invested)),
        "final_value": float(final),
        "gain": float(final - fiat(invested)),
        "series": series,
    }


def time_to_goal(target, regular_deposit, period=MONTHLY, already_saved=0) -> dict:
    """How many regular deposits reach a target, and how long that takes."""
    wanted = _positive(target)
    deposit = _positive(regular_deposit)
    if period not in (DAILY, MONTHLY):
        raise ValueError("Dönem geçersiz.")
    try:
        saved = decimal_from(already_saved or 0)
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise ValueError("Birikim tutarı negatif olamaz") from exc
    if saved < 0:
        raise ValueError("Birikim tutarı negatif olamaz")
    remaining = max(wanted - saved, Decimal(0))
    deposits = math.ceil(remaining / deposit)
    days = deposits if period == DAILY else deposits * 30
    return {
        "deposits": deposits,
        "period": period,
        "days": days,
        "remaining": float(fiat(remaining)),
    }
