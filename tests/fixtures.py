"""Shared fixture helpers so tests can set up their own accounts.

WHY: for a long time the tests relied on the three default accounts
`initialize_database()` opened (Nakit 2500 / Banka 15000 / Kredi Kartı -3500).
When those "dummy" seed records were removed from production (the user was
seeing 2500 lira they had not added themselves), 14 tests collapsed at once --
the tests were coupled to the production seed.

The helpers here set up the test world's accounts EXPLICITLY. So even if the
default data in `database/init_db.py` changes again, the test suite does not
break: each test states what it needs itself.

The accounts are deliberately written with direct SQL (rather than
AccountService.create_account): the fixture's purpose is not to exercise the
service layer's validation rules but to set up a known initial state -- a card
with a negative balance, say, or an old migration record with no limit, cases
the service layer would reject.

"""

from database.db import ACCOUNT, get_connection, record_balance_event


LEGACY_SEED_ACCOUNTS = [
    ("Nakit", "cash", 2500.0, "checking", 0, None),
    ("Banka", "bank", 15000.0, "checking", 0, None),
    ("Kredi Kartı", "credit", -3500.0, "credit_card", 20000, 15),
]


LEGACY_SEED_TOTAL = 14000.0


class AccountFixtureMixin:
    """A test mixin providing `create_test_account` (alongside unittest.TestCase).

    The class using it is expected to have patched `database.db.DB_NAME` and
    called `initialize_database()`; this mixin only inserts rows and does not
    create the schema.
    """

    def create_test_account(self, name="Test Hesabı", balance=0.0,
                            account_type="checking", account_kind=None,
                            credit_limit=0, statement_date=None):
        """Creates an account with a known balance and returns its id.

        `account_type` is the logical type ('checking' | 'credit_card'), while
        `account_kind` is the old `type` column ('cash'/'bank'/'credit'); if it
        is not given, a sensible value is derived from the account type.
        """
        if account_kind is None:
            account_kind = "credit" if account_type == "credit_card" else "cash"

        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO accounts(name, type, balance, account_type,"
                " credit_limit, statement_date) VALUES(?,?,?,?,?,?)",
                (name, account_kind, float(balance), account_type,
                 credit_limit, statement_date),
            )
            account_id = cursor.lastrowid


            record_balance_event(
                cursor, ACCOUNT, account_id, float(balance), float(balance),
                "account_opened",
            )
            conn.commit()
        finally:
            conn.close()
        return account_id

    def create_legacy_seed_accounts(self):
        """Sets up the three accounts `initialize_database()` used to open.

        For tests that rely on the trio whose net total is `LEGACY_SEED_TOTAL`
        (14000.0); it returns their ids in insertion order.
        """
        return [
            self.create_test_account(
                name=name, account_kind=kind, balance=balance,
                account_type=acc_type, credit_limit=limit,
                statement_date=statement_day,
            )
            for name, kind, balance, acc_type, limit, statement_day
            in LEGACY_SEED_ACCOUNTS
        ]
