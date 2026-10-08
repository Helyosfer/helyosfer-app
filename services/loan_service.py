"""Loan instalment calculation with a full repayment schedule.

The annuity formula: instalment = P * i * (1 + i)^n / ((1 + i)^n - 1), where
`i` is the monthly rate the borrower actually pays. For consumer loans in
Türkiye the interest carries two taxes (KKDF and BSMV), so the effective rate
is the stated monthly rate times (1 + KKDF + BSMV).

The detailed mode adds what a bank takes on top: an allocation fee and life
insurance deducted up front, plus any charges the borrower enters, either
taken once or spread over a number of months.

Arithmetic is in Decimal and only the outputs are rounded to the kurus.
"""

from __future__ import annotations

from decimal import Decimal

from utils.financial_decimal import decimal_from, fiat

KKDF = Decimal("0.15")
BSMV = Decimal("0.15")
MAX_MONTHS = 360

ALLOCATION_FEE_RATE = Decimal("0.005")
ALLOCATION_FEE_TAX = Decimal("0.15")
INSURANCE_RATE = Decimal("0.008")

CONSUMER, VEHICLE, HOUSING = "consumer", "vehicle", "housing"
MAX_TERM = {CONSUMER: 36, VEHICLE: 48, HOUSING: 120}

UPFRONT, SPREAD = "upfront", "spread"


def _charges(raw_charges) -> list[dict]:
    """Validates the borrower's own charges: [{name, amount, kind, months}]."""
    charges = []
    for charge in raw_charges or ():
        name = str(charge.get("name") or "").strip()
        if not name:
            raise ValueError("Masraf adı boş olamaz.")
        try:
            amount = decimal_from(charge.get("amount"))
        except (TypeError, ValueError, ArithmeticError) as exc:
            raise ValueError("Masraf tutarı 0'dan büyük olmalıdır.") from exc
        if amount <= 0:
            raise ValueError("Masraf tutarı 0'dan büyük olmalıdır.")
        kind = charge.get("kind")
        if kind not in (UPFRONT, SPREAD):
            raise ValueError("Masraf türü geçersiz.")
        raw_months = charge.get("months")
        months = 1 if raw_months is None else int(raw_months)
        if kind == SPREAD and not 1 <= months <= MAX_MONTHS:
            raise ValueError("Masraf vadesi 1 ile 360 ay arasında olmalıdır.")
        charges.append({"name": name, "amount": amount, "kind": kind, "months": months})
    return charges


def calculate_loan(principal, monthly_rate_percent, months, include_taxes=True,
                   *, loan_kind=None, bank_fees=False, charges=()) -> dict:
    """Returns the instalment, the totals and the month-by-month schedule.

    `monthly_payment` and `total_repayment` describe the loan itself: the
    total is the ROUNDED instalment times the count -- exactly what a debt
    recorded from this result will hold. Charges are reported separately in
    `total_cost` and `net_cash`, because they are not part of the instalment.

    `loan_kind` enforces the longest term allowed for that kind of loan.
    `bank_fees` deducts the allocation fee and life insurance up front.
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
    if loan_kind is not None:
        if loan_kind not in MAX_TERM:
            raise ValueError("Kredi türü geçersiz.")
        if count > MAX_TERM[loan_kind]:
            raise ValueError("Seçtiğiniz kredi türü için vade çok uzun.")
    extra = _charges(charges)

    tax = (KKDF + BSMV) if include_taxes else Decimal(0)
    effective = rate * (1 + tax)
    growth = (1 + effective) ** count
    instalment = amount * effective * growth / (growth - 1)
    monthly = fiat(instalment)
    total = monthly * count

    upfront = []
    if bank_fees:
        upfront.append({
            "name": "allocation_fee",
            "amount": fiat(amount * ALLOCATION_FEE_RATE * (1 + ALLOCATION_FEE_TAX)),
        })
        upfront.append({"name": "insurance", "amount": fiat(amount * INSURANCE_RATE)})
    upfront += [
        {"name": c["name"], "amount": fiat(c["amount"])} for c in extra if c["kind"] == UPFRONT
    ]
    spread = [c for c in extra if c["kind"] == SPREAD]
    upfront_total = sum((item["amount"] for item in upfront), Decimal(0))
    spread_total = sum((fiat(c["amount"]) for c in spread), Decimal(0))

    schedule = []
    balance = amount
    for month in range(1, count + 1):
        interest = balance * rate
        taxed_interest = interest * (1 + tax)
        repaid = instalment - taxed_interest
        balance = max(balance - repaid, Decimal(0))
        extra_this_month = sum(
            (c["amount"] / c["months"] for c in spread if month <= c["months"]), Decimal(0)
        )
        schedule.append({
            "month": month,
            "payment": float(monthly),
            "extra": float(fiat(extra_this_month)),
            "total": float(fiat(monthly + extra_this_month)),
            "principal": float(fiat(repaid)),
            "interest": float(fiat(taxed_interest)),
            "balance": float(fiat(balance)) if month < count else 0.0,
        })

    return {
        "monthly_payment": float(monthly),
        "total_repayment": float(total),
        "total_cost": float(total + upfront_total + spread_total - fiat(amount)),
        "months": count,
        "upfront": [{"name": i["name"], "amount": float(i["amount"])} for i in upfront],
        "upfront_total": float(upfront_total),
        "spread_total": float(spread_total),
        "net_cash": float(fiat(amount) - upfront_total),
        "schedule": schedule,
    }
