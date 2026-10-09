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


# A font with the letters of every language the interface has. The PDF
# standard's own fonts stop at Latin-1, which has no Turkish dotless i or
# s-cedilla. Windows always has these two files; elsewhere the built-in font
# is used and anything outside Latin-1 is replaced.
_SYSTEM_FONTS = (
    ("arial.ttf", "arialbd.ttf"),
    ("segoeui.ttf", "segoeuib.ttf"),
)


def _system_font() -> tuple[str, str] | None:
    """Paths of a regular and a bold font file, or None when there are none."""
    import os

    folder = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    for regular, bold in _SYSTEM_FONTS:
        paths = os.path.join(folder, regular), os.path.join(folder, bold)
        if all(os.path.isfile(path) for path in paths):
            return paths
    return None


def write_loan_schedule_pdf(path: str, result: dict, *, principal: float, title: str = "",
                            labels: dict | None = None) -> str:
    """Saves the schedule in `result` (from `calculate_loan`) to `path`.

    `labels` maps the English text written here to the text to print, for a
    schedule in another language; anything it leaves out is printed as it is.
    """
    from fpdf import FPDF

    labels = labels or {}

    def shown(text: str) -> str:
        return labels.get(text, text)

    pdf = FPDF()
    fonts = _system_font()
    if fonts:
        pdf.add_font("Body", fname=fonts[0])
        pdf.add_font("Body", style="B", fname=fonts[1])
        family = "Body"

        def safe(text: str) -> str:
            return str(text)
    else:
        family = "Helvetica"

        def safe(text: str) -> str:
            return str(text).encode("latin-1", "replace").decode("latin-1")

    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()
    pdf.set_font(family, style="B", size=15)
    pdf.cell(0, 10, text=safe(title or shown("Loan repayment schedule")),
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(family, size=10)
    for label, value in (
        ("Loan amount", principal),
        ("Monthly installment", result["monthly_payment"]),
        ("Total repaid", result["total_repayment"]),
        ("Cost of borrowing", result["total_cost"]),
    ):
        pdf.cell(0, 6, text=safe(f"{shown(label)}: {_money(value)} TL"),
                 new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font(family, style="B", size=8)
    for heading, width, _key in _COLUMNS:
        pdf.cell(width, 8, text=safe(shown(heading)), border=1, align="C")
    pdf.ln()
    pdf.set_font(family, size=8)
    for row in result["schedule"]:
        for _heading, width, key in _COLUMNS:
            text = str(row[key]) if key == "month" else _money(row[key])
            pdf.cell(width, 7, text=text, border=1, align="C" if key == "month" else "R")
        pdf.ln()

    if result["upfront"]:
        pdf.ln(6)
        pdf.set_font(family, style="B", size=11)
        pdf.cell(0, 8, text=safe(shown("Deducted up front")), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(family, size=10)
        for item in result["upfront"]:
            name = shown(_UPFRONT_NAMES.get(item["name"], item["name"]))
            pdf.cell(0, 6, text=safe(f"- {name}: {_money(item['amount'])} TL"),
                     new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(family, style="B", size=10)
        pdf.cell(0, 7, text=safe(f"{shown('Total deducted')}: {_money(result['upfront_total'])} TL"),
                 new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 7, text=safe(f"{shown('Cash you receive')}: {_money(result['net_cash'])} TL"),
                 new_x="LMARGIN", new_y="NEXT")

    pdf.output(path)
    return path


# Every text the schedule prints, for a caller that wants to translate it.
PRINTED_TEXT = (
    "Loan repayment schedule", "Loan amount", "Monthly installment", "Total repaid",
    "Cost of borrowing", "Deducted up front", "Total deducted", "Cash you receive",
    *(heading for heading, _width, _key in _COLUMNS), *_UPFRONT_NAMES.values(),
)
