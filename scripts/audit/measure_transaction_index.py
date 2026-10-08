"""A DIAGNOSTIC TOOL -- NOT a permanent gate. Measures the `transactions.account_id` index.

The schema had `transactions.account_id REFERENCES accounts(id)` but there was
NO INDEX on that column. SQLite forces an index on the parent side (PRIMARY
KEY) but not on the CHILD side -- so `WHERE account_id = ?` did a full scan
every time:

    SELECT ... WHERE account_id = ?           ->  SCAN transactions
    SELECT COUNT(*) ... WHERE account_id = ?  ->  SCAN transactions

This script compares the indexed/unindexed plan and the median time over the
same synthetic data set. The data is produced directly with `sqlite3` (it does
not go through the application's encryption path): what is measured is the
query plan, not the cost of encryption.

DELIBERATELY NOT A CI GATE: the timing depends on the machine and the disk
cache. The permanent guarantee is the query-plan gate in
`tests/test_transaction_index.py`.

    python scripts/audit/measure_transaction_index.py --rows 100000

"""

import argparse
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_transactions_account_id "
    "ON transactions(account_id)"
)

QUERIES = (
    ("hesap ekstresi",
     "SELECT id, amount, transaction_date FROM transactions "
     "WHERE account_id = ? ORDER BY transaction_date DESC LIMIT 50"),
    ("bağımlılık sayımı",
     "SELECT COUNT(*) FROM transactions WHERE account_id = ?"),
    ("hesap silme taraması",
     "SELECT id FROM transactions WHERE account_id = ?"),
)


def _seed(path, rows, accounts):
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE accounts (id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " name TEXT NOT NULL, type TEXT NOT NULL, balance REAL DEFAULT 0)"
        )
        conn.execute(
            "CREATE TABLE transactions ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " account_id INTEGER NOT NULL, amount TEXT NOT NULL,"
            " type TEXT NOT NULL, category TEXT, description TEXT,"
            " transaction_date TEXT NOT NULL,"
            " FOREIGN KEY(account_id) REFERENCES accounts(id))"
        )
        conn.executemany(
            "INSERT INTO accounts (id, name, type) VALUES (?, ?, 'checking')",
            [(index + 1, f"Hesap {index + 1}") for index in range(accounts)],
        )
        conn.executemany(
            "INSERT INTO transactions"
            " (account_id, amount, type, category, description, transaction_date)"
            " VALUES (?, ?, 'expense', 'Market', ?, ?)",
            [
                (
                    (index % accounts) + 1,
                    f"AEADv1:{index:08d}",
                    f"aciklama-{index}",
                    f"2026-01-{(index % 28) + 1:02d} 09:00:00",
                )
                for index in range(rows)
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _plan(conn, sql):
    return " | ".join(
        str(row[-1]) for row in conn.execute("EXPLAIN QUERY PLAN " + sql, (1,))
    )


def _median_ms(conn, sql, repeats):
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        conn.execute(sql, (1,)).fetchall()
        samples.append((time.perf_counter() - started) * 1000)
    return statistics.median(samples)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--accounts", type=int, default=8)
    parser.add_argument("--repeats", type=int, default=15)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="helysofer-index-bench-") as temp:
        path = str(Path(temp) / "finance.db")
        _seed(path, args.rows, args.accounts)
        print(f"{args.rows:,} işlem / {args.accounts} hesap "
              f"(hesap başına ~{args.rows // args.accounts:,})")
        print(f"her sorgu {args.repeats} kez, medyan raporlanıyor")
        print()

        conn = sqlite3.connect(path)
        try:
            before = {
                label: (_plan(conn, sql), _median_ms(conn, sql, args.repeats))
                for label, sql in QUERIES
            }
            conn.execute(INDEX_SQL)
            conn.commit()
            conn.execute("ANALYZE")
            after = {
                label: (_plan(conn, sql), _median_ms(conn, sql, args.repeats))
                for label, sql in QUERIES
            }
        finally:
            conn.close()

    for label, sql in QUERIES:
        old_plan, old_ms = before[label]
        new_plan, new_ms = after[label]
        speedup = old_ms / new_ms if new_ms else float("inf")
        print(f"── {label}")
        print(f"   önce : {old_ms:8.3f} ms   {old_plan}")
        print(f"   sonra: {new_ms:8.3f} ms   {new_plan}")
        print(f"   oran : {speedup:.1f}x")
        print()


if __name__ == "__main__":
    main()
