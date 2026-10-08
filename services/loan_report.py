"""Writes a loan's repayment schedule to a PDF file."""

from __future__ import annotations

_COLUMNS = (
    ("Month", 14, "month"),
    ("Installment", 30, "payment"),
    ("Extra charges", 30, "extra"),
    ("Total", 30, "total"),
    ("Principal", 28, "principal"),
    ("Interest and tax", 30, "interest"),
    ("Remaining", 28, "balance"),
)
_UPFRONT_NAMES = {
    "allocation_fee": "Allocation fee (with tax)",
    "insurance": "Life insurance (estimate)",
}


def _money(value: float) -> str:
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _plain(text: str) -> str:
    """The built-in PDF font is Latin-1 only; anything else becomes '?'."""
    return str(text).encode("latin-1", "replace").decode("latin-1")


def write_loan_schedule_pdf(path: str, result: dict, *, principal: float, title: str = "") -> str:
    """Saves the schedule in `result` (from `calculate_loan`) to `path`."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()
    pdf.set_font("Helvetica", style="B", size=15)
    pdf.cell(0, 10, text=_plain(title or "Loan repayment schedule"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    for label, value in (
        ("Loan amount", principal),
        ("Monthly installment", result["monthly_payment"]),
        ("Total repaid", result["total_repayment"]),
        ("Cost of borrowing", result["total_cost"]),
    ):
        pdf.cell(0, 6, text=f"{label}: {_money(value)} TL", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", style="B", size=8)
    for heading, width, _key in _COLUMNS:
        pdf.cell(width, 8, text=heading, border=1, align="C")
    pdf.ln()
    pdf.set_font("Helvetica", size=8)
    for row in result["schedule"]:
        for _heading, width, key in _COLUMNS:
            text = str(row[key]) if key == "month" else _money(row[key])
            pdf.cell(width, 7, text=text, border=1, align="C" if key == "month" else "R")
        pdf.ln()

    if result["upfront"]:
        pdf.ln(6)
        pdf.set_font("Helvetica", style="B", size=11)
        pdf.cell(0, 8, text="Deducted up front", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=10)
        for item in result["upfront"]:
            name = _UPFRONT_NAMES.get(item["name"], item["name"])
            pdf.cell(0, 6, text=_plain(f"- {name}: {_money(item['amount'])} TL"),
                     new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", style="B", size=10)
        pdf.cell(0, 7, text=f"Total deducted: {_money(result['upfront_total'])} TL",
                 new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 7, text=f"Cash you receive: {_money(result['net_cash'])} TL",
                 new_x="LMARGIN", new_y="NEXT")

    pdf.output(path)
    return path
