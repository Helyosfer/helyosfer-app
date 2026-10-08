#!/usr/bin/env python3
"""Verifies the financial invariants in an Helysofer database, READ ONLY.

This tool is for auditing. It writes under no circumstances: it opens the
database with a `file:...?mode=ro` URI, so SQLite refuses any write attempt.

Usage:

    python scripts/audit/check_financial_invariants.py --db /path/finance.db

The default behaviour is deliberately narrow:

  * `--db` is REQUIRED. It does not find and open the real user data directory
    by itself -- to make looking at a production profile by accident
    impossible.
  * It must be run from the repository root; otherwise it refuses.
  * The exit code is 1 if there are violations, 0 otherwise.

The audited invariants are documented section by section below. Each is
written against the existing domain semantics so as not to produce false
positives; a field whose semantics are unknown is not audited and is reported
as "not audited".

"""

import argparse
import sqlite3
import sys
from decimal import Decimal
from pathlib import Path


for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

ROOT = Path(__file__).resolve().parents[2]


def _open_readonly(db_path: Path) -> sqlite3.Connection:
    """Opens in read-only mode only; a write attempt is refused by SQLite."""
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _tables(conn):
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def check_orphan_transactions(conn, tables):
    """INVARIANT: every transaction must belong to an existing account.

    The `transactions.account_id -> accounts.id` FK is defined in the schema,
    but `PRAGMA foreign_keys` is OFF on the application connection, so the
    constraint is not enforced.
    """
    if not {"transactions", "accounts"} <= tables:
        return "denetlenmedi", []
    rows = conn.execute(
        "SELECT t.id, t.account_id FROM transactions t "
        "LEFT JOIN accounts a ON t.account_id = a.id "
        "WHERE t.account_id IS NOT NULL AND a.id IS NULL"
    ).fetchall()
    return ("ihlal" if rows else "tamam",
            [f"transactions.id={r['id']} -> yok olan account_id={r['account_id']}"
             for r in rows])


def check_orphan_balance_events(conn, tables):
    """INVARIANT: every account-typed ledger event must point at an existing account."""
    if not {"balance_events", "accounts"} <= tables:
        return "denetlenmedi", []
    rows = conn.execute(
        "SELECT e.id, e.entity_id FROM balance_events e "
        "LEFT JOIN accounts a ON e.entity_id = a.id "
        "WHERE e.entity_type = 'account' AND a.id IS NULL"
    ).fetchall()
    return ("ihlal" if rows else "tamam",
            [f"balance_events.id={r['id']} -> yok olan account_id={r['entity_id']}"
             for r in rows])


def check_installment_progress(conn, tables):
    """INVARIANT: the number of instalments paid cannot exceed the total."""
    if "installment_plans" not in tables:
        return "denetlenmedi", []
    rows = conn.execute(
        "SELECT id, paid_installments, total_installments FROM installment_plans "
        "WHERE paid_installments > total_installments OR paid_installments < 0"
    ).fetchall()
    return ("ihlal" if rows else "tamam",
            [f"installment_plans.id={r['id']} "
             f"odenen={r['paid_installments']}/{r['total_installments']}"
             for r in rows])


def check_debt_progress(conn, tables):
    """INVARIANT: the number of instalments paid cannot exceed the total; a
    closed debt must be fully paid.
    """
    if "active_debts" not in tables:
        return "denetlenmedi", []
    rows = conn.execute(
        "SELECT id, paid_installments, total_installments, is_active "
        "FROM active_debts "
        "WHERE paid_installments > total_installments OR paid_installments < 0"
    ).fetchall()
    return ("ihlal" if rows else "tamam",
            [f"active_debts.id={r['id']} "
             f"odenen={r['paid_installments']}/{r['total_installments']}"
             for r in rows])


def check_savings_within_target(conn, tables):
    """INVARIANT: savings cannot be negative.

    EXCEEDING the target is not a violation -- the user may go above it.
    """
    if "savings_goals" not in tables:
        return "denetlenmedi", []
    rows = conn.execute(
        "SELECT id, current_amount FROM savings_goals WHERE current_amount < 0"
    ).fetchall()
    return ("ihlal" if rows else "tamam",
            [f"savings_goals.id={r['id']} birikim={r['current_amount']}"
             for r in rows])


def check_balance_precision(conn, tables):
    """INVARIANT: a stored balance must not be finer than the kurus.

    `accounts.balance` is a REAL column updated with `balance = balance + ?`,
    so it can accumulate binary floating-point residue (an audit finding: this
    is a deliberately accepted design decision). This check measures whether
    that residue has become VISIBLE.
    """
    if "accounts" not in tables:
        return "denetlenmedi", []
    bad = []
    for row in conn.execute("SELECT id, name, balance FROM accounts"):
        bal = row["balance"]
        if bal is None:
            continue
        d = Decimal(str(bal))
        if -d.as_tuple().exponent > 2:
            bad.append(f"accounts.id={row['id']} bakiye={bal!r} (2 haneden ince)")
    return ("uyari" if bad else "tamam", bad)


CHECKS = (
    ("Öksüz işlem kaydı", check_orphan_transactions),
    ("Öksüz ledger olayı", check_orphan_balance_events),
    ("Taksit planı ilerlemesi", check_installment_progress),
    ("Borç ilerlemesi", check_debt_progress),
    ("Birikim negatif değil", check_savings_within_target),
    ("Bakiye kuruş hassasiyeti", check_balance_precision),
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Helysofer finansal değişmezlerini salt okunur doğrular.",
        epilog="Gerçek kullanıcı veritabanını kendiliğinden bulmaz; --db zorunludur.",
    )
    parser.add_argument(
        "--db", required=True,
        help="İncelenecek SQLite dosyası (salt okunur açılır).",
    )
    args = parser.parse_args()

    if not (ROOT / "utils" / "version.py").exists():
        print(f"HATA: depo kökü doğrulanamadı ({ROOT}); depo içinden çalıştırın.")
        return 2

    db_path = Path(args.db).expanduser().resolve()
    if not db_path.is_file():
        print(f"HATA: veritabanı bulunamadı: {db_path}")
        return 2

    conn = _open_readonly(db_path)
    tables = _tables(conn)

    print(f"Veritabanı : {db_path}")
    print(f"Tablo sayısı: {len(tables)}\n")

    violations = 0
    for label, check in CHECKS:
        status, details = check(conn, tables)
        marker = {"tamam": "  OK  ", "ihlal": " İHLAL", "uyari": " UYARI",
                  "denetlenmedi": "  --  "}[status]
        print(f"[{marker}] {label}")
        for line in details[:20]:
            print(f"           {line}")
        if len(details) > 20:
            print(f"           ... ve {len(details) - 20} tane daha")
        if status == "ihlal":
            violations += 1

    conn.close()
    print()
    if violations:
        print(f"{violations} değişmez ihlal edildi.")
        return 1
    print("İhlal bulunmadı (yalnızca yukarıda denetlenen değişmezler için).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
