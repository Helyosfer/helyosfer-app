import uuid

from database.db import get_connection
from datetime import date
from database.models import ASSET_PRICE_CACHE_SCHEMA
from utils.errors import FinancialDataIntegrityError, SchemaTooNewError


SCHEMA_VERSION = 2


SCHEMA_TOO_NEW_MESSAGE = (
    "Bu veritabanı uygulamanın daha yeni bir sürümü tarafından oluşturulmuş. "
    "Verilerinizi bozmamak için açılış durduruldu; hiçbir dosyaya "
    "dokunulmadı. Lütfen uygulamanın güncel sürümünü kullanın."
)


DATA_INTEGRITY_MESSAGE = (
    "Veritabanı bütünlüğü doğrulanamadı. Verilerinizi korumak için açılış "
    "durduruldu; hiçbir kayıt değiştirilmedi veya silinmedi. Doğrulanmış bir "
    "yedeği geri yükleyin ya da onarım için destek alın."
)


SAVINGS_GOALS_DDL = """
    CREATE TABLE {exists}{table} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        goal_name TEXT NOT NULL,
        target_amount REAL NOT NULL,
        current_amount REAL DEFAULT 0,
        target_date TEXT,
        status TEXT DEFAULT 'aktif',
        goal_uid TEXT NOT NULL,
        color TEXT,
        auto_deposit INTEGER NOT NULL DEFAULT 0,
        created_at TEXT
    )
"""


SAVINGS_GOALS_COLUMNS = (
    "id, goal_name, target_amount, current_amount, target_date, status,"
    " goal_uid, color, auto_deposit, created_at"
)


def initialize_database():
    """Creates/updates the schema -- closing the connection ON EVERY EXIT PATH.

    The body was moved into a separate function so the `try/finally` sits in
    one place and 600 lines do not have to be re-indented. Without the
    wrapper, any exception raised mid-setup left the connection OPEN; that is
    not theoretical: migration steps such as `_maybe_backfill_account_type`
    can raise deliberately (see tests/test_migration_retry_safety.py,
    interruption injection) and `initialize_database` is called TWICE in the
    same process (startup plus the reset flow). On Linux a leaked
    handle is only a descriptor; on Windows it is a lock held on finance.db,
    which would block the next restore/rename/delete step.
    """
    conn = get_connection()
    try:
        _initialize_database(conn)
    finally:
        conn.close()


_FK_VIOLATION_SAMPLE = 5


def _foreign_key_violations(conn, limit=_FK_VIOLATION_SAMPLE):
    """Reads at most `limit` violations. Also reports whether more remain.

    Returns: `(samples, more_remain)`.
    """
    cursor = conn.execute("PRAGMA foreign_key_check")
    try:
        sample = [tuple(row)[:3] for row in cursor.fetchmany(limit)]
        more = bool(cursor.fetchmany(1))
    finally:
        cursor.close()
    return sample, more


def _require_no_foreign_key_violations(conn):
    """Stops FAIL-CLOSED if there are orphan rows -- repairing nothing.

    `PRAGMA foreign_key_check` returns `(table, rowid, parent_table, fkid)`
    for every violation.

    WHY WE DO NOT REPAIR: the options would be to DELETE the orphan row, to
    ATTACH it to ANOTHER account, or to INVENT the missing parent. All three
    mean rewriting the user's financial history without their knowledge -- if
    a TRY 12,400 transaction belonging to no account is silently deleted, the
    user can never find out where their money went. Stopping and saying WHAT
    we found is better than guessing.

    The message has to be diagnosable: which table, which rowid, which
    parent. The user should be able to take those and decide for themselves.
    """
    sample, more = _foreign_key_violations(conn)
    if not sample:
        return
    table, rowid, parent = sample[0]
    from utils.logging_config import get_logger

    get_logger().error(
        "[VERİ BÜTÜNLÜĞÜ] foreign key ihlali (ilk %d örnek%s): %s",
        len(sample), ", devamı var" if more else "", sample,
    )
    count = f"{len(sample)}+" if more else str(len(sample))
    raise FinancialDataIntegrityError(
        table, rowid, "account_id",
        reason=(
            f"{count} kayıt bağlı olduğu {parent} satırını kaybetmiş "
            f"(ilk: {table} rowid={rowid} -> {parent}). "
            "Hiçbir kayıt değiştirilmedi."
        ),
    )


def _preflight_foreign_keys(conn):
    """The integrity gate -- BEFORE A SINGLE WRITE."""
    _require_no_foreign_key_violations(conn)


def _initialize_database(conn):
    cursor = conn.cursor()


    found = cursor.execute("PRAGMA user_version").fetchone()[0]
    if found > SCHEMA_VERSION:
        raise SchemaTooNewError(found, SCHEMA_VERSION)


    _preflight_foreign_keys(conn)

    # 1. Hesaplar Tablosu
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            balance REAL DEFAULT 0,
            account_type TEXT NOT NULL DEFAULT 'checking',
            credit_limit REAL DEFAULT 0,
            statement_date INTEGER
        )
    """)


    cursor.execute("PRAGMA table_info(accounts)")
    existing_account_cols = {row[1] for row in cursor.fetchall()}


    if "account_type" not in existing_account_cols:
        cursor.execute("ALTER TABLE accounts ADD COLUMN account_type TEXT")
    cursor.execute(
        "SELECT COUNT(*) FROM accounts "
        "WHERE account_type IS NULL OR TRIM(account_type) = ''"
    )
    if cursor.fetchone()[0]:
        cursor.execute("""
            UPDATE accounts
            SET account_type = CASE WHEN type = 'credit' THEN 'credit_card' ELSE 'checking' END
            WHERE account_type IS NULL OR TRIM(account_type) = ''
        """)

    if "credit_limit" not in existing_account_cols:
        cursor.execute("ALTER TABLE accounts ADD COLUMN credit_limit REAL DEFAULT 0")

    cursor.execute("UPDATE accounts SET credit_limit = 0 WHERE credit_limit IS NULL")
    if "statement_date" not in existing_account_cols:
        cursor.execute("ALTER TABLE accounts ADD COLUMN statement_date INTEGER")

    if "card_number_full" not in existing_account_cols:
        cursor.execute("ALTER TABLE accounts ADD COLUMN card_number_full TEXT")
    if "expiry_date" not in existing_account_cols:
        cursor.execute("ALTER TABLE accounts ADD COLUMN expiry_date TEXT")
    if "cvc_code" not in existing_account_cols:
        cursor.execute("ALTER TABLE accounts ADD COLUMN cvc_code TEXT")


    if "masked_number" not in existing_account_cols:
        cursor.execute("ALTER TABLE accounts ADD COLUMN masked_number TEXT")
    if "network_logo" not in existing_account_cols:
        cursor.execute("ALTER TABLE accounts ADD COLUMN network_logo TEXT")
    if "is_frozen" not in existing_account_cols:
        cursor.execute(
            "ALTER TABLE accounts ADD COLUMN is_frozen INTEGER DEFAULT 0"
        )
        cursor.execute(
            "UPDATE accounts SET is_frozen = 0 WHERE is_frozen IS NULL"
        )
    if "online_payments_enabled" not in existing_account_cols:
        cursor.execute(
            "ALTER TABLE accounts ADD COLUMN "
            "online_payments_enabled INTEGER DEFAULT 1"
        )
        cursor.execute(
            "UPDATE accounts SET online_payments_enabled = 1 "
            "WHERE online_payments_enabled IS NULL"
        )


    cursor.execute(
        "SELECT id, card_number_full FROM accounts WHERE card_number_full IS NOT NULL"
    )
    rows_to_migrate = cursor.fetchall()
    if rows_to_migrate:
        from utils.crypto import decrypt
        from database.db import SECRET_KEY
        from services.account_service import AccountService
        from utils.errors import DecryptionError, KeyUnavailableError

        for row in rows_to_migrate:
            account_id, enc_number = row[0], row[1]
            try:
                dec_num = decrypt(enc_number, SECRET_KEY)
                network_logo = AccountService.check_card_network(dec_num)
                last4 = dec_num[-4:] if len(dec_num) >= 4 else dec_num
                masked_number = f"**** **** **** {last4}"
            except KeyUnavailableError:


                raise
            except (DecryptionError, ValueError, TypeError):


                from utils.logging_config import get_logger
                get_logger().exception(f"[VERİ BÜTÜNLÜĞÜ] accounts id={account_id} kart no migration'ı başarısız")
                masked_number, network_logo = None, None
            cursor.execute(
                "UPDATE accounts SET masked_number = ?, network_logo = ? WHERE id = ?",
                (masked_number, network_logo, account_id),
            )
    cursor.execute(
        "UPDATE accounts SET card_number_full = NULL, expiry_date = NULL, cvc_code = NULL "
        "WHERE card_number_full IS NOT NULL OR expiry_date IS NOT NULL OR cvc_code IS NOT NULL"
    )


    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER,
            amount TEXT NOT NULL,
            type TEXT NOT NULL,
            category TEXT,
            description TEXT,
            transaction_date TEXT,
            FOREIGN KEY(account_id) REFERENCES accounts(id)
        )
    """)


    cursor.execute("PRAGMA table_info(transactions)")
    existing_trans_cols = {row[1] for row in cursor.fetchall()}
    if "status" not in existing_trans_cols:
        cursor.execute("ALTER TABLE transactions ADD COLUMN status TEXT DEFAULT 'completed'")
    if "execution_date" not in existing_trans_cols:
        cursor.execute("ALTER TABLE transactions ADD COLUMN execution_date TEXT")

    # Durable financial-operation identities.  UI state is not an idempotency
    # boundary: retries and two processes must be rejected by SQLite itself.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recurring_operation_markers (
            recurring_payment_id INTEGER NOT NULL,
            due_date TEXT NOT NULL,
            operation_type TEXT NOT NULL,
            transaction_id INTEGER,
            PRIMARY KEY (recurring_payment_id, due_date, operation_type)
        )
    """)


    # 3. Categories table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            importance TEXT DEFAULT 'extra'
        )
    """)


    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monthly_budget_plan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            name TEXT NOT NULL,
            amount REAL NOT NULL,
            target_month INTEGER DEFAULT 1,
            target_year INTEGER,
            category_name TEXT,
            rollover_enabled INTEGER DEFAULT 0,
            is_template INTEGER DEFAULT 0,
            alert_threshold_pct INTEGER DEFAULT 80
        )
    """)
    cursor.execute("PRAGMA table_info(monthly_budget_plan)")
    existing_budget_cols = {row[1] for row in cursor.fetchall()}
    if "target_month" not in existing_budget_cols:
        cursor.execute(
            "ALTER TABLE monthly_budget_plan "
            "ADD COLUMN target_month INTEGER DEFAULT 1"
        )
    budget_migrations = {
        "target_year": "INTEGER",
        "category_name": "TEXT",
        "rollover_enabled": "INTEGER DEFAULT 0",
        "is_template": "INTEGER DEFAULT 0",
        "alert_threshold_pct": "INTEGER DEFAULT 80",
    }
    for column, definition in budget_migrations.items():
        if column not in existing_budget_cols:
            cursor.execute(
                f"ALTER TABLE monthly_budget_plan "
                f"ADD COLUMN {column} {definition}"
            )
    cursor.execute(
        "UPDATE monthly_budget_plan SET target_year = ? "
        "WHERE target_year IS NULL",
        (date.today().year,),
    )
    cursor.execute(
        "UPDATE monthly_budget_plan SET rollover_enabled = 0 "
        "WHERE rollover_enabled IS NULL"
    )
    cursor.execute(
        "UPDATE monthly_budget_plan SET is_template = 0 "
        "WHERE is_template IS NULL"
    )
    cursor.execute(
        "UPDATE monthly_budget_plan SET alert_threshold_pct = 80 "
        "WHERE alert_threshold_pct IS NULL"
    )


    cursor.execute("""
        CREATE TABLE IF NOT EXISTS active_debts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            debt_name TEXT NOT NULL,
            total_amount TEXT NOT NULL,
            monthly_payment TEXT NOT NULL,
            total_installments INTEGER NOT NULL,
            paid_installments INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1
        )
    """)


    cursor.execute("PRAGMA table_info(active_debts)")
    existing_debt_cols = {row[1] for row in cursor.fetchall()}
    if "name" in existing_debt_cols and "debt_name" not in existing_debt_cols:
        cursor.execute("ALTER TABLE active_debts RENAME COLUMN name TO debt_name")


    if "is_auto_pay" not in existing_debt_cols:
        cursor.execute("ALTER TABLE active_debts ADD COLUMN is_auto_pay INTEGER DEFAULT 0")
    if "auto_pay_day" not in existing_debt_cols:
        cursor.execute("ALTER TABLE active_debts ADD COLUMN auto_pay_day INTEGER DEFAULT 1")
    if "last_auto_pay_date" not in existing_debt_cols:
        cursor.execute("ALTER TABLE active_debts ADD COLUMN last_auto_pay_date TEXT")


    cursor.execute("""
        CREATE TABLE IF NOT EXISTS active_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_name TEXT NOT NULL,
            asset_code TEXT NOT NULL,
            asset_type TEXT NOT NULL DEFAULT 'Diğer',
            purchase_price TEXT NOT NULL,
            quantity TEXT NOT NULL,
            purchase_date TEXT
        )
    """)


    cursor.execute("PRAGMA table_info(active_assets)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    if "purchase_date" not in existing_cols:
        cursor.execute("ALTER TABLE active_assets ADD COLUMN purchase_date TEXT")


    cursor.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='asset_price_cache'"
    )
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(asset_price_cache)")
        price_cache_cols = {row[1] for row in cursor.fetchall()}
        if not {"price", "asset_type"}.issubset(price_cache_cols):
            cursor.execute(
                "ALTER TABLE asset_price_cache "
                "RENAME TO asset_price_cache_legacy"
            )
            cursor.execute(ASSET_PRICE_CACHE_SCHEMA)
            if "price_try" in price_cache_cols:
                cursor.execute("""
                    INSERT OR REPLACE INTO asset_price_cache
                        (symbol, price, asset_type, updated_at)
                    SELECT symbol, price_try, 'UNKNOWN',
                           datetime(updated_at, 'unixepoch', 'localtime')
                      FROM asset_price_cache_legacy
                """)
            cursor.execute("DROP TABLE asset_price_cache_legacy")


        cursor.execute("PRAGMA table_info(asset_price_cache)")
        if "source" not in {row[1] for row in cursor.fetchall()}:
            cursor.execute(
                "ALTER TABLE asset_price_cache ADD COLUMN source TEXT")
    else:
        cursor.execute(ASSET_PRICE_CACHE_SCHEMA)


    cursor.execute("DROP TABLE IF EXISTS subscriptions")


    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recurring_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            amount TEXT NOT NULL,
            category TEXT,
            frequency TEXT NOT NULL DEFAULT 'monthly',
            next_due_date TEXT NOT NULL,
            recurrence_day INTEGER CHECK (recurrence_day BETWEEN 1 AND 31),
            auto_deduct INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            account_id INTEGER DEFAULT 1,
            transaction_type TEXT NOT NULL DEFAULT 'expense'
        )
    """)
    cursor.execute("PRAGMA table_info(recurring_payments)")
    existing_recurring_cols = {row[1] for row in cursor.fetchall()}
    if "recurrence_day" not in existing_recurring_cols:
        cursor.execute(
            "ALTER TABLE recurring_payments ADD COLUMN recurrence_day INTEGER"
        )
    if "transaction_type" not in existing_recurring_cols:

        cursor.execute(
            "ALTER TABLE recurring_payments ADD COLUMN transaction_type TEXT "
            "NOT NULL DEFAULT 'expense'"
        )
    cursor.execute("""
        UPDATE recurring_payments
        SET recurrence_day = CAST(strftime('%d', next_due_date) AS INTEGER)
        WHERE recurrence_day IS NULL
    """)


    cursor.execute(
        SAVINGS_GOALS_DDL.format(table="savings_goals", exists="IF NOT EXISTS ")
    )


    cursor.execute("PRAGMA table_info(savings_goals)")
    existing_goal_cols = {row[1] for row in cursor.fetchall()}
    if "goal_uid" not in existing_goal_cols:
        cursor.execute("ALTER TABLE savings_goals ADD COLUMN goal_uid TEXT")
    if "color" not in existing_goal_cols:
        cursor.execute("ALTER TABLE savings_goals ADD COLUMN color TEXT")
    if "auto_deposit" not in existing_goal_cols:


        cursor.execute(
            "ALTER TABLE savings_goals "
            "ADD COLUMN auto_deposit INTEGER NOT NULL DEFAULT 0"
        )
    if "created_at" not in existing_goal_cols:
        cursor.execute("ALTER TABLE savings_goals ADD COLUMN created_at TEXT")


    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_savings_goals_uid "
        "ON savings_goals(goal_uid)"
    )


    cursor.execute("SELECT id FROM savings_goals WHERE goal_uid IS NULL")
    for (goal_id,) in cursor.fetchall():
        cursor.execute(
            "UPDATE savings_goals SET goal_uid = ? WHERE id = ? "
            "AND goal_uid IS NULL",
            (str(uuid.uuid4()), goal_id),
        )


    cursor.execute("PRAGMA table_info(savings_goals)")
    goal_columns = {row[1]: row for row in cursor.fetchall()}
    uid_column = goal_columns.get("goal_uid")
    if uid_column is not None and not uid_column[3]:  # notnull == 0
        cursor.execute(
            "SELECT COUNT(*) FROM savings_goals WHERE goal_uid IS NULL"
        )
        if cursor.fetchone()[0] == 0:


            cursor.execute(
                "SELECT seq FROM sqlite_sequence WHERE name = 'savings_goals'"
            )
            row = cursor.fetchone()
            previous_seq = row[0] if row else None

            cursor.execute(
                SAVINGS_GOALS_DDL.format(
                    table="savings_goals_uid_migration", exists=""
                )
            )
            cursor.execute(
                f"INSERT INTO savings_goals_uid_migration ({SAVINGS_GOALS_COLUMNS}) "
                f"SELECT {SAVINGS_GOALS_COLUMNS} FROM savings_goals"
            )
            cursor.execute("DROP TABLE savings_goals")
            cursor.execute(
                "ALTER TABLE savings_goals_uid_migration RENAME TO savings_goals"
            )

            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_savings_goals_uid "
                "ON savings_goals(goal_uid)"
            )
            if previous_seq is not None:
                cursor.execute(
                    "SELECT seq FROM sqlite_sequence WHERE name = 'savings_goals'"
                )
                current = cursor.fetchone()
                if current is None:
                    cursor.execute(
                        "INSERT INTO sqlite_sequence(name, seq) VALUES(?, ?)",
                        ("savings_goals", previous_seq),
                    )
                elif current[0] < previous_seq:
                    cursor.execute(
                        "UPDATE sqlite_sequence SET seq = ? WHERE name = ?",
                        (previous_seq, "savings_goals"),
                    )
            conn.commit()


    cursor.execute("""
        CREATE TABLE IF NOT EXISTS savings_migration_quarantine (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quarantined_at TEXT NOT NULL,
            reason TEXT NOT NULL,
            source TEXT NOT NULL,
            legacy_id INTEGER,
            goal_name TEXT,
            target_amount REAL,
            current_amount REAL,
            payload TEXT,
            acknowledged INTEGER NOT NULL DEFAULT 0
        )
    """)


    cursor.execute("""
        CREATE TABLE IF NOT EXISTS savings_migration_state (
            marker TEXT PRIMARY KEY,
            completed_at TEXT NOT NULL,
            detail TEXT
        )
    """)


    cursor.execute("""
        CREATE TABLE IF NOT EXISTS financial_health_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            score REAL NOT NULL,
            breakdown_json TEXT
        )
    """)


    cursor.execute("PRAGMA table_info(financial_health_history)")
    existing_health_cols = {row[1] for row in cursor.fetchall()}
    if "breakdown_json" not in existing_health_cols:
        cursor.execute("ALTER TABLE financial_health_history ADD COLUMN breakdown_json TEXT")


    cursor.execute("""
        DELETE FROM financial_health_history
        WHERE id NOT IN (
            SELECT MAX(id)
            FROM financial_health_history
            GROUP BY substr(date, 1, 10)
        )
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_health_history_day
        ON financial_health_history(substr(date, 1, 10))
    """)


    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recurring_candidate_dismissals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_key TEXT NOT NULL,
            dismissed_at TEXT NOT NULL
        )
    """)

    cursor.execute("PRAGMA table_info(recurring_candidate_dismissals)")
    existing_dismissal_cols = {row[1] for row in cursor.fetchall()}
    if "dismissed_at" not in existing_dismissal_cols:
        cursor.execute("ALTER TABLE recurring_candidate_dismissals ADD COLUMN dismissed_at TEXT")


    cursor.execute("""
        CREATE TABLE IF NOT EXISTS anomaly_dismissals (
            transaction_id INTEGER PRIMARY KEY,
            dismissed_at TEXT NOT NULL
        )
    """)


    cursor.execute("""
        CREATE TABLE IF NOT EXISTS balance_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            delta REAL NOT NULL,
            resulting_value REAL,
            source TEXT,
            ref_id INTEGER
        )
    """)


    cursor.execute("PRAGMA table_info(balance_events)")
    existing_event_cols = {row[1] for row in cursor.fetchall()}
    if "ref_id" not in existing_event_cols:
        cursor.execute("ALTER TABLE balance_events ADD COLUMN ref_id INTEGER")
    if "resulting_value" not in existing_event_cols:
        cursor.execute("ALTER TABLE balance_events ADD COLUMN resulting_value REAL")


    cursor.execute("CREATE INDEX IF NOT EXISTS idx_balance_events_ts ON balance_events(ts)")


    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_transactions_account_id "
        "ON transactions(account_id)"
    )


    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_balance_snapshot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL UNIQUE,
            total_balance REAL NOT NULL,
            breakdown_json TEXT
        )
    """)

    cursor.execute("PRAGMA table_info(daily_balance_snapshot)")
    existing_snap_cols = {row[1] for row in cursor.fetchall()}
    if "breakdown_json" not in existing_snap_cols:
        cursor.execute("ALTER TABLE daily_balance_snapshot ADD COLUMN breakdown_json TEXT")

    conn.commit()


    def _backfill_ledger_baseline():
        """Writes one baseline event for every entity with no opening line.

        Asking "is the ledger completely empty" is not enough: the ledger can
        also be partly filled (for example, the application was updated after
        some movements had been recorded). It is therefore examined PER ENTITY,
        and the baseline is computed as:

            opening = today's value - the sum of the ledger deltas for that entity

        The ledger total is thereby always brought into line with the real
        balance; entities that already have an opening line are not written
        again (idempotent).
        """
        from database.db import ACCOUNT, SAVINGS_GOAL, record_balance_event


        allowed_columns = {
            "accounts": "balance",
            "savings_goals": "current_amount",
        }

        def _baseline(entity_type, table, value_column, marker_source):
            if allowed_columns.get(table) != value_column:
                raise ValueError(
                    f"Defter baseline'ı yalnızca {sorted(allowed_columns)} "
                    f"tablolarında çalışır; verilen: {table}.{value_column}"
                )


            cursor.execute(
                f"SELECT id, {value_column} AS value FROM {table}"  # nosec B608
            )
            rows = [(r["id"], r["value"] or 0.0) for r in cursor.fetchall()]
            for entity_id, current_value in rows:
                cursor.execute(
                    "SELECT COUNT(*) FROM balance_events"
                    " WHERE entity_type = ? AND entity_id = ? AND source = ?",
                    (entity_type, entity_id, marker_source),
                )
                if cursor.fetchone()[0] > 0:
                    continue

                cursor.execute(
                    "SELECT COALESCE(SUM(delta), 0) AS total, MIN(ts) AS first_ts"
                    " FROM balance_events WHERE entity_type = ? AND entity_id = ?",
                    (entity_type, entity_id),
                )
                agg = cursor.fetchone()
                recorded = agg["total"] or 0.0
                opening = current_value - recorded


                baseline_event_id = record_balance_event(
                    cursor, entity_type, entity_id, opening,
                    opening, marker_source)


                if agg["first_ts"]:
                    cursor.execute(
                        "UPDATE balance_events SET ts = ? WHERE id = ?",
                        (f"{agg['first_ts'][:10]} 00:00:00", baseline_event_id),
                    )

        _baseline(ACCOUNT, "accounts", "balance", "account_opened")
        _baseline(SAVINGS_GOAL, "savings_goals", "current_amount", "savings_goal_created")
        conn.commit()


    cursor.execute("SELECT COUNT(*) FROM accounts")
    if cursor.fetchone()[0] == 0:

        pass


    cursor.execute("SELECT COUNT(*) FROM categories")
    if cursor.fetchone()[0] == 0:
        default_categories = [

            ("Maaş", "income", "main"), ("Avans", "income", "main"), ("Prim", "income", "extra"), ("Mesai", "income", "extra"), ("Kıdem Tazminatı", "income", "extra"), ("İhbar Tazminatı", "income", "extra"),
            ("Freelance", "income", "extra"), ("Danışmanlık", "income", "extra"), ("Proje Bedeli", "income", "extra"), ("Ürün Satışı", "income", "extra"), ("E-Ticaret", "income", "extra"), ("Hak Ediş", "income", "extra"),
            ("Ev Kirası (Gelir)", "income", "extra"), ("Dükkan Kirası", "income", "extra"), ("Araç Kirası", "income", "extra"), ("Faiz Getirisi", "income", "extra"), ("Temettü", "income", "extra"), ("Kripto Kazancı", "income", "extra"), ("Fon Getirisi", "income", "extra"), ("Kupon Ödemesi", "income", "extra"),
            ("Emekli Maaşı", "income", "main"), ("İşsizlik Maaşı", "income", "extra"), ("Çocuk Yardımı", "income", "extra"), ("Burs", "income", "extra"), ("Nafaka", "income", "extra"), ("Devlet Teşviki", "income", "extra"),
            ("Piyango/Loto", "income", "extra"), ("Miras", "income", "extra"), ("Borç Tahsilatı", "income", "extra"), ("Nakit Hediye", "income", "extra"), ("İade", "income", "extra"), ("Varlık Satışı", "income", "extra"),


            ("Ev Kirası", "expense", "main"), ("Aidat", "expense", "main"), ("Emlak Vergisi", "expense", "extra"), ("Ev Bakım/Onarım", "expense", "extra"), ("Ev Eşyası", "expense", "extra"),
            ("Elektrik", "expense", "main"), ("Su", "expense", "main"), ("Doğalgaz", "expense", "main"), ("İnternet", "expense", "main"), ("Cep Telefonu", "expense", "main"), ("Dijital Platformlar", "expense", "extra"), ("Dijital Abonelik", "expense", "extra"),
            ("Akaryakıt", "expense", "main"), ("Toplu Taşıma", "expense", "main"), ("Taksi", "expense", "extra"), ("Araç Bakım", "expense", "extra"), ("MTV", "expense", "extra"), ("Sigorta/Kasko", "expense", "extra"), ("Otopark/Köprü", "expense", "extra"),
            ("Süpermarket", "expense", "main"), ("Pazaryeri", "expense", "main"), ("Dışarıda Yemek", "expense", "extra"), ("Paket Servis", "expense", "extra"), ("Su Siparişi", "expense", "main"),
            ("Hastane", "expense", "main"), ("İlaç/Eczane", "expense", "main"), ("Sağlık Sigortası", "expense", "main"), ("Kişisel Bakım", "expense", "extra"), ("Kuaför/Berber", "expense", "extra"), ("Spor Salonu", "expense", "extra"),
            ("Okul/Kurs", "expense", "main"), ("Kitap/Kırtasiye", "expense", "extra"), ("Sınav Ücretleri", "expense", "extra"),
            ("Sinema/Tiyatro", "expense", "extra"), ("Oyun/Uygulama", "expense", "extra"), ("Tatil/Konaklama", "expense", "extra"), ("Hobiler", "expense", "extra"),
            ("Kıyafet", "expense", "extra"), ("Ayakkabı", "expense", "extra"), ("Çanta", "expense", "extra"), ("Takı/Aksesuar", "expense", "extra"),
            ("Kredi Kartı", "expense", "main"), ("Kredi Taksiti", "expense", "main"), ("Borç Ödeme", "expense", "main"), ("Vergi Ödemeleri", "expense", "main"), ("Bağış/Zekat", "expense", "extra"),
            ("Çocuk Bakımı", "expense", "main"), ("Evcil Hayvan", "expense", "main"), ("Varlık Alımı", "expense", "extra")
        ]
        cursor.executemany(
            "INSERT INTO categories(name, type, importance) VALUES(?,?,?)",
            default_categories,
        )
        conn.commit()


    cursor.execute("SELECT name FROM categories WHERE name='Varlık Alımı'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO categories(name, type, importance) VALUES(?,?,?)",
                       ("Varlık Alımı", "expense", "extra"))
    cursor.execute("SELECT name FROM categories WHERE name='Varlık Satışı'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO categories(name, type, importance) VALUES(?,?,?)",
                       ("Varlık Satışı", "income", "extra"))
    cursor.execute(
        "SELECT 1 FROM categories WHERE name = ? AND type = ?",
        ("Dijital Abonelik", "expense"),
    )
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO categories(name, type, importance) VALUES(?,?,?)",
            ("Dijital Abonelik", "expense", "extra"),
        )
    conn.commit()


    _backfill_ledger_baseline()


    cursor.execute(f"PRAGMA user_version = {int(SCHEMA_VERSION)}")  # nosec B608
    conn.commit()
