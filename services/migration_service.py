"""Data import/export (migration) service.

For users coming from another platform: the existing data is written
decrypted into a single readable CSV, and transactions from an incoming CSV
are taken in through TransactionService.add_transaction -- so that encryption
and the accounts.balance synchronisation both run atomically from one place.

The CSV schema (a single file, with `kayit_turu` as the discriminating column):
    kayit_turu in {islem, varlik, borc, tekrarlanan}
    islem       -> date, type(income/expense), category, amount, description
    varlik      -> date=purchase date, type=asset type, category=symbol,
                   amount=unit purchase price, quantity=count,
                   description=asset name
    borc        -> amount=total debt, description=debt name,
                   detail="aylik_odeme=..;toplam_taksit=..;odenen_taksit=.."
    tekrarlanan -> date=next due, type=frequency, amount, description=name,
                   detail="otomatik=0/1"

The import reads transaction rows only (asset/debt structures differ too much
to carry across platforms one-to-one); it recognises both this file's own
format and generic CSVs with a "Tarih,Tür,Kategori,Tutar,Açıklama" header.

The column and value names above are the literal strings written to and read
from the file, which is why they are not translated.

"""

import csv
import math
from collections import Counter
import os
import tempfile
from pathlib import Path
from datetime import datetime

from database.db import (
    DEFAULT_ACCOUNT_ID,
    SECRET_KEY,
    managed_connection,
)
from utils.crypto import decrypt
from utils.errors import DecryptionError, KeyUnavailableError


CSV_VERSION_COLUMN = "_helyosfer_csv_version"


CSV_ESCAPE_VERSION = 2


SUPPORTED_CSV_VERSIONS = frozenset({2})

CSV_HEADER = [
    CSV_VERSION_COLUMN,
    "kayit_turu", "tarih", "tur", "kategori", "tutar", "miktar", "aciklama",
    "detay",
]


_RECORD_KINDS = frozenset({"islem", "varlik", "borc", "tekrarlanan"})


_COLUMN_ALIASES = {
    "tarih": "tarih", "date": "tarih",
    "tur": "tur", "tür": "tur", "type": "tur",
    "kategori": "kategori", "category": "kategori",
    "tutar": "tutar", "miktar": "tutar", "amount": "tutar",
    "aciklama": "aciklama", "açıklama": "aciklama", "description": "aciklama",
}

_INCOME_WORDS = {"gelir", "income"}
_EXPENSE_WORDS = {"gider", "expense", "harcama"}

_DATE_FORMATS = [
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
    "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
    "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y",
]


_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


_CSV_ESCAPE_CHAR = "'"


_CSV_TEXT_COLUMNS = ("tur", "kategori", "aciklama", "detay")
_CSV_TEXT_INDEXES = tuple(
    CSV_HEADER.index(column) for column in _CSV_TEXT_COLUMNS
)


def escape_csv_text(value):
    """Makes user text safe to hand to a spreadsheet without it being
    delivered as a formula. On harmless text it is THE IDENTITY -- no cell is
    corrupted for nothing.
    """
    text = "" if value is None else str(value)
    if text.startswith(_FORMULA_PREFIXES) or text.startswith(_CSV_ESCAPE_CHAR):
        return _CSV_ESCAPE_CHAR + text
    return text


def unescape_csv_text(value):
    """The exact inverse of `escape_csv_text`: strips the leading single apostrophe."""
    text = "" if value is None else str(value)
    if text.startswith(_CSV_ESCAPE_CHAR):
        return text[1:]
    return text


def _escape_row(row):
    """Prepares a row for export: the version marker plus text escaping.

    `row` arrives WITHOUT the version column (the callers produce the data
    columns); the marker is added here, in one place, so that no row goes out
    unmarked.
    """
    escaped = [str(CSV_ESCAPE_VERSION)] + list(row)
    for index in _CSV_TEXT_INDEXES:
        escaped[index] = escape_csv_text(escaped[index])
    return escaped


_AMBIGUOUS = object()


def _row_escape_version(raw):
    """Resolves the row's version marker.

    Returns: the supported version number, `None` (no marker), or
    `_AMBIGUOUS` (there is a marker but it cannot be read or is
    unsupported).
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return _AMBIGUOUS
    try:
        version = int(text)
    except ValueError:
        return _AMBIGUOUS
    if version not in SUPPORTED_CSV_VERSIONS:
        return _AMBIGUOUS
    return version


def get_export_path():
    """Returns the export target: the desktop if there is one, otherwise the user-data directory."""
    home = os.path.expanduser("~")
    for candidate in ("Masaüstü", "Desktop"):
        desktop = os.path.join(home, candidate)
        if os.path.isdir(desktop):
            return os.path.join(desktop, "helyosfer_export.csv")


    from utils.app_paths import data_dir
    return os.path.join(data_dir(), "helyosfer_export.csv")


def _dec(value):
    """Decrypts an encrypted column; returns empty for an old or corrupt
    record that cannot be decrypted, so that one broken row does not bring
    down the whole export.
    """
    try:
        return decrypt(str(value), SECRET_KEY)
    except KeyUnavailableError:


        raise
    except (DecryptionError, ValueError, TypeError):
        from utils.logging_config import get_logger
        get_logger().exception(
            "[VERİ BÜTÜNLÜĞÜ] CSV dışa aktarımında bir alan çözülemedi")
        return ""


def export_all_to_csv(path=None):
    """Writes the transactions + active_assets + active_debts +
    recurring_payments tables, decrypted, into a single CSV. Returns
    (path, row_count).
    """
    path = path or get_export_path()
    rows_out = []


    with managed_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT transaction_date, type, category, amount, description "
            "FROM transactions ORDER BY id"
        )
        for r in cursor.fetchall():
            tur = "gelir" if r["type"] in ("income", "Gelir") else "gider"
            rows_out.append([
                "islem", r["transaction_date"] or "", tur, r["category"] or "",
                _dec(r["amount"]), "", _dec(r["description"]), "",
            ])

        cursor.execute(
            "SELECT asset_name, asset_code, asset_type, purchase_price, quantity, purchase_date "
            "FROM active_assets ORDER BY id"
        )
        for r in cursor.fetchall():
            rows_out.append([
                "varlik", r["purchase_date"] or "", r["asset_type"] or "", r["asset_code"] or "",
                _dec(r["purchase_price"]), _dec(r["quantity"]), _dec(r["asset_name"]), "",
            ])

        cursor.execute(
            "SELECT debt_name, total_amount, monthly_payment, total_installments, "
            "paid_installments FROM active_debts WHERE is_active = 1 ORDER BY id"
        )
        for r in cursor.fetchall():
            detay = (
                f"aylik_odeme={_dec(r['monthly_payment'])};"
                f"toplam_taksit={r['total_installments']};"
                f"odenen_taksit={r['paid_installments']}"
            )
            rows_out.append([
                "borc", "", "", "", _dec(r["total_amount"]), "", _dec(r["debt_name"]), detay,
            ])

        cursor.execute(
            "SELECT name, amount, category, frequency, next_due_date, "
            "recurrence_day, auto_deduct "
            "FROM recurring_payments WHERE is_active = 1 ORDER BY id"
        )
        for r in cursor.fetchall():
            rows_out.append([
                "tekrarlanan", r["next_due_date"] or "", r["frequency"] or "", r["category"] or "",
                _dec(r["amount"]), "", _dec(r["name"]),
                f"otomatik={r['auto_deduct']};gun={r['recurrence_day']}",
            ])


    # Plaintext finance exports are private files, irrespective of umask.
    # Stage beside the target so replace is atomic and never follows an
    # existing symlink target.
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, staged = tempfile.mkstemp(prefix=".helyosfer-export-", dir=target.parent)
    fd_handed_off = False
    try:


        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", newline="", encoding="utf-8-sig") as f:

            fd_handed_off = True
            writer = csv.writer(f)
            writer.writerow(CSV_HEADER)
            writer.writerows(_escape_row(row) for row in rows_out)
            f.flush(); os.fsync(f.fileno())
        os.replace(staged, target)
        if hasattr(os, "fchmod"):
            os.chmod(target, 0o600)


    except Exception:


        if not fd_handed_off:
            try: os.close(fd)
            except OSError: pass
        try: os.unlink(staged)
        except (FileNotFoundError, PermissionError): pass
        raise

    return path, len(rows_out)


def _normalize_date(raw):
    """Converts a date in one of the supported formats into the form the
    database uses; returns None if it is unrecognised (the row is skipped -- we
    do not invent dates).
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return None


def parse_transactions_csv(path):
    """Extracts the importable transaction rows from a CSV."""
    records, skipped = [], 0

    with open(path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return [], 0


        header_map = {}
        for name in reader.fieldnames:
            key = (name or "").strip().lower()
            if key and key not in header_map:
                header_map[key] = name
        field_map = {}
        for key, raw_name in header_map.items():
            alias = _COLUMN_ALIASES.get(key)
            if alias and alias not in field_map:
                field_map[alias] = raw_name

        type_col = header_map.get("kayit_turu")
        version_col = header_map.get(CSV_VERSION_COLUMN)


        def _text(row, key, unescape):
            raw = row.get(field_map.get(key, ""), "") or ""
            return unescape_csv_text(raw) if unescape else raw

        for row in reader:
            unescape = False
            if version_col is not None:
                version = _row_escape_version(row.get(version_col))
                if version is _AMBIGUOUS:


                    skipped += 1
                    continue
                unescape = version is not None

            if type_col is not None:
                kayit_turu = (row.get(type_col) or "").strip().lower()
                if kayit_turu not in _RECORD_KINDS:


                    skipped += 1
                    continue
                if kayit_turu != "islem":
                    continue

            raw_tur = _text(row, "tur", unescape).strip().lower()
            if raw_tur in _INCOME_WORDS:
                tx_type = "income"
            elif raw_tur in _EXPENSE_WORDS:
                tx_type = "expense"
            else:
                skipped += 1
                continue

            date = _normalize_date(row.get(field_map.get("tarih", ""), ""))
            if not date:
                skipped += 1
                continue

            raw_amount = (row.get(field_map.get("tutar", ""), "") or "").strip()
            try:

                if "," in raw_amount and raw_amount.count(",") == 1:
                    raw_amount = raw_amount.replace(".", "").replace(",", ".")
                amount = float(raw_amount)


                if not math.isfinite(amount) or amount <= 0:
                    raise ValueError
            except ValueError:
                skipped += 1
                continue

            records.append({
                "date": date,
                "type": tx_type,
                "category": _text(row, "kategori", unescape).strip() or "Diğer",
                "amount": amount,
                "description": _text(row, "aciklama", unescape).strip(),
            })

    return records, skipped


def import_transactions_from_csv(path, account_id=DEFAULT_ACCOUNT_ID):
    """Imports the transactions in a CSV through TransactionService.

    Because encryption and the accounts.balance update happen atomically
    inside add_transaction, nothing extra is done here -- every back-dated
    record affects the balance in its own direction (income +, expense -).
    A row that is already in the account -- same moment, direction, category,
    amount and description -- is left out, so importing a file twice does not
    double it. Rows that repeat inside the file itself are all kept.

    Returns (imported_count, skipped_count, net_balance_effect, duplicate_count).
    """
    from services.transaction_service import TransactionService

    records, skipped = parse_transactions_csv(path)
    present = _existing_transaction_keys(account_id) if records else Counter()
    net_delta = 0.0
    imported = 0
    duplicates = 0
    for rec in records:
        key = _transaction_key(
            rec["date"], rec["type"], rec["category"], rec["amount"],
            rec["description"] or rec["category"],
        )
        if present[key] > 0:
            present[key] -= 1
            duplicates += 1
            continue
        TransactionService.add_transaction(
            account_id=account_id,
            amount=rec["amount"],
            transaction_type=rec["type"],
            category=rec["category"],
            description=rec["description"] or rec["category"],
            transaction_date=rec["date"],


            enforce_credit_limit=False,
        )
        net_delta += rec["amount"] if rec["type"] == "income" else -rec["amount"]
        imported += 1

    return imported, skipped, net_delta, duplicates


def _transaction_key(date, kind, category, amount, description):
    return (str(date)[:19], kind, category, round(float(amount), 2), description)


def _existing_transaction_keys(account_id) -> Counter:
    """How many times each transaction already appears in the account."""
    from database.db import SECRET_KEY, get_connection
    from utils.crypto import decrypt
    from utils.errors import DecryptionError

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT transaction_date, type, category, amount, description"
            " FROM transactions WHERE account_id = ?", (account_id,),
        ).fetchall()
    finally:
        conn.close()
    present: Counter = Counter()
    for row in rows:
        try:
            amount = float(decrypt(row[3], SECRET_KEY))
            description = decrypt(row[4], SECRET_KEY) if row[4] else ""
        except (DecryptionError, ValueError, TypeError):
            continue
        present[_transaction_key(row[0], row[1], row[2], amount, description)] += 1
    return present
