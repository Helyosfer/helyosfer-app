"""The money boundary, transaction and record-relationship invariants -- in one place.

Rather than hunting bugs one by one, this file closes THREE CLASSES of
regression together. All three are classes of bug that really happened, not
theoretical ones:

  1. THE MONEY BOUNDARY -- `float("nan")` and `float("inf")` raise no exception
     and EVERY comparison made with `nan` is False, so every gate of the form
     `amount <= 0` lets them through. The measured results: a subscription
     could be recorded with an `inf` fee, a card payment reached the first SQL
     write with NaN, and a subscription refund made an account permanently
     `inf`. The matrix here tries EVERY money boundary with the same three
     values and does not settle for "it was rejected": no row in any table and
     no balance in any account may have changed.

  2. THE TRANSACTION BOUNDARY -- opening a SECOND connection while a write
     transaction is open and making a financial decision from it splits the
     decision and the write into separate snapshots. The charging path was
     doing exactly that.

  3. THE RECORD RELATIONSHIP -- `cursor.lastrowid` belongs to the CURSOR, not
     to the statement; any intervening INSERT overwrites it.
     `recurring_operation_markers` therefore pointed at the ledger row instead
     of the transaction.

The policy is per service and NOT uniform: `add_transaction`'s amount has to be
positive, but `balance_events.delta` is signed and a P/L can be negative. The
matrix is therefore common only for FINITENESS and looks at each boundary's own
rule for positivity.

"""
import os
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from datetime import date
from unittest import mock

from tests.test_connection_ownership_contract import connection_ledger

NON_FINITE = (float("nan"), float("inf"), float("-inf"))


STATE_TABLES = (
    "accounts", "transactions", "balance_events", "active_assets",
    "recurring_payments", "recurring_operation_markers", "savings_goals",
    "active_debts", "monthly_budget_plan",
)


@contextmanager
def no_connection_opened_inside_a_transaction():
    """Catches a NEW connection being opened while a transaction is open.

    `sqlite3.Connection.in_transaction` reads SQLite's own state directly, so
    it answers "did BEGIN IMMEDIATE run" without guessing. If another
    still-living connection is inside a transaction AT THE MOMENT a connection
    is opened, that moment is a violation.
    """
    real_connect = sqlite3.connect
    live = []
    violations = []

    def _connect(*args, **kwargs):
        for existing in live:
            try:
                if existing.in_transaction:
                    violations.append(existing)
            except sqlite3.ProgrammingError:
                continue
        conn = real_connect(*args, **kwargs)
        live.append(conn)
        return conn

    with mock.patch("sqlite3.connect", _connect):
        yield violations


class _MonetaryProfile(unittest.TestCase):
    """A known initial state: an account, a card, a goal, an asset, a subscription, a debt."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._patcher = mock.patch("database.db.DB_NAME", self.db_path)
        self._patcher.start()
        self.addCleanup(self._patcher.stop)
        self.addCleanup(lambda: os.path.exists(self.db_path) and os.unlink(self.db_path))

        from database.init_db import initialize_database
        initialize_database()

        from services.account_service import AccountService
        from services.asset_purchase_service import AssetPurchaseService
        from services.savings_service import SavingsService
        from database.db import get_active_recurring_payments, insert_recurring_payment

        self.account_id = AccountService.create_account(
            "Vadesiz", "checking", initial_balance=100000.0)
        self.card_id = AccountService.create_account(
            "Kart", "credit_card", initial_balance=500.0, credit_limit=5000.0)
        self.goal_id = SavingsService.create_goal(
            "Hedef", 1000.0, current_amount=500.0)
        self.asset = AssetPurchaseService.create_purchase(
            asset_name="Altın", asset_code="XAU", asset_type="Altın",
            purchase_price=100.0, quantity=2, account_id=self.account_id)
        insert_recurring_payment(
            "Abonelik", 50.0, "Dijital Platformlar", "monthly",
            date.today().isoformat(), False,
            account_id=self.account_id, recurrence_day=date.today().day)
        self.payment = get_active_recurring_payments()[0]

    def state(self):
        conn = sqlite3.connect(self.db_path)
        try:
            counts = tuple(
                conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in STATE_TABLES
            )
            balances = conn.execute(
                "SELECT id, balance FROM accounts ORDER BY id").fetchall()
            goals = conn.execute(
                "SELECT id, current_amount FROM savings_goals ORDER BY id"
            ).fetchall()
            assets = conn.execute(
                "SELECT id, purchase_price, quantity FROM active_assets"
                " ORDER BY id").fetchall()
        finally:
            conn.close()
        return counts, balances, goals, assets

    def rows(self, sql, *params):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in conn.execute(sql, params)]
        finally:
            conn.close()


class NonFiniteRejectionMatrix(_MonetaryProfile):
    """Every money boundary: non-finite input -> rejection plus NO WRITE AT ALL."""

    def _boundaries(self):
        """(name, call) pairs. The call takes a single monetary argument."""
        from database.db import (insert_asset, insert_debt,
                                 insert_recurring_payment,
                                 process_due_recurring_payment)
        from services.account_service import AccountService
        from services.asset_purchase_service import AssetPurchaseService
        from services.asset_sale_service import AssetSaleService
        from services.budget_service import save_plan_item
        from services.recurring_service import update_subscription_amount
        from services.savings_service import SavingsService
        from services.transaction_service import TransactionService

        return [
            ("TransactionService.add_transaction", lambda v:
                TransactionService.add_transaction(
                    self.account_id, v, "expense", "Market", "x",
                    detect_subscription=False)),
            ("AccountService.create_account/initial_balance", lambda v:
                AccountService.create_account("Yeni", "checking", v)),
            ("AccountService.create_account/credit_limit", lambda v:
                AccountService.create_account(
                    "Yeni Kart", "credit_card", 0, credit_limit=v)),
            ("AccountService.pay_credit_card_debt", lambda v:
                AccountService.pay_credit_card_debt(
                    self.card_id, self.account_id, v)),
            ("SavingsService.create_goal/target", lambda v:
                SavingsService.create_goal("G", v)),
            ("SavingsService.create_goal/current", lambda v:
                SavingsService.create_goal("G2", 100.0, current_amount=v)),
            ("SavingsService.deposit_to_goal", lambda v:
                SavingsService.deposit_to_goal(self.goal_id, v, self.account_id)),
            ("SavingsService.withdraw_from_goal", lambda v:
                SavingsService.withdraw_from_goal(self.goal_id, v, self.account_id)),
            ("AssetPurchaseService.create_purchase/price", lambda v:
                AssetPurchaseService.create_purchase(
                    asset_name="A", asset_code="A", asset_type="Altın",
                    purchase_price=v, quantity=1, account_id=self.account_id)),
            ("AssetPurchaseService.create_purchase/quantity", lambda v:
                AssetPurchaseService.create_purchase(
                    asset_name="B", asset_code="B", asset_type="Altın",
                    purchase_price=1.0, quantity=v, account_id=self.account_id)),
            ("AssetSaleService.sell/price", lambda v:
                AssetSaleService.sell(self.asset["asset_id"], v, self.account_id)),
            ("AssetSaleService.sell/quantity", lambda v:
                AssetSaleService.sell(
                    self.asset["asset_id"], 100.0, self.account_id, quantity=v)),
            ("db.insert_recurring_payment", lambda v:
                insert_recurring_payment(
                    "R", v, "Dijital", "monthly", date.today().isoformat(),
                    False, account_id=self.account_id, recurrence_day=1)),
            ("recurring.update_subscription_amount", lambda v:
                update_subscription_amount(self.payment["id"], v)),
            ("db.process_due_recurring_payment", lambda v:
                process_due_recurring_payment(dict(self.payment, amount=v))),
            ("db.insert_debt/total", lambda v: insert_debt("D", v, 10.0, 12)),
            ("db.insert_debt/monthly", lambda v: insert_debt("D2", 100.0, v, 12)),


            ("db.insert_asset/price", lambda v:
                insert_asset("A", "A", "Altın", v, 1.0)),
            ("db.insert_asset/quantity", lambda v:
                insert_asset("A", "A", "Altın", 1.0, v)),


            ("budget.save_plan_item", lambda v:
                save_plan_item(
                    item_type="expense", name="Market", amount=v,
                    month=date.today().month, year=date.today().year,
                    category="Market")),
        ]

    def test_every_monetary_boundary_rejects_non_finite_without_writing(self):
        before = self.state()
        for name, call in self._boundaries():
            for value in NON_FINITE:
                with self.subTest(boundary=name, value=repr(value)):
                    with self.assertRaises(
                        (ValueError, TypeError, ArithmeticError),
                        msg=f"{name} sonlu olmayan tutarı kabul etti",
                    ):
                        call(value)
                    self.assertEqual(
                        self.state(), before,
                        f"{name} reddetti ama kalıcı durumu değiştirdi",
                    )

    def test_the_matrix_actually_covers_every_boundary_it_claims(self):
        """If the matrix goes empty the test silently turns green -- pin the count."""
        self.assertEqual(len(self._boundaries()), 20)


class TransactionConnectionInvariant(_MonetaryProfile):
    """The financial decision and the write must be under THE SAME transaction/connection."""

    def _write_paths(self):
        from database.db import process_due_recurring_payment
        from services.account_service import AccountService
        from services.asset_purchase_service import AssetPurchaseService
        from services.asset_sale_service import AssetSaleService
        from services.recurring_service import refund_current_period_charge
        from services.savings_service import SavingsService
        from services.transaction_service import TransactionService

        return [
            ("add_transaction", lambda: TransactionService.add_transaction(
                self.account_id, 10.0, "expense", "Market", "x",
                detect_subscription=False)),
            ("card_expense", lambda: TransactionService.add_transaction(
                self.card_id, 10.0, "expense", "Market", "x",
                detect_subscription=False)),
            ("pay_credit_card_debt", lambda:
                AccountService.pay_credit_card_debt(
                    self.card_id, self.account_id, 100.0)),
            ("asset_purchase", lambda: AssetPurchaseService.create_purchase(
                asset_name="C", asset_code="C", asset_type="Altın",
                purchase_price=10.0, quantity=1, account_id=self.account_id)),
            ("asset_sale", lambda: AssetSaleService.sell(
                self.asset["asset_id"], 120.0, self.account_id, quantity=1)),
            ("savings_deposit", lambda: SavingsService.deposit_to_goal(
                self.goal_id, 10.0, self.account_id)),
            ("savings_withdraw", lambda: SavingsService.withdraw_from_goal(
                self.goal_id, 10.0, self.account_id)),
            ("recurring_charge", lambda: process_due_recurring_payment(
                self.payment)),
            ("subscription_refund", lambda: refund_current_period_charge(
                self.payment["id"])),
        ]

    def test_no_write_path_opens_a_connection_mid_transaction(self):
        for name, call in self._write_paths():
            with self.subTest(path=name):
                with no_connection_opened_inside_a_transaction() as violations:
                    call()
                self.assertEqual(
                    violations, [],
                    f"{name}: açık bir transaction varken yeni bağlantı açıldı — "
                    "karar ve yazma farklı snapshot'lardan bakıyor",
                )

    def test_recurring_charge_uses_exactly_one_connection(self):
        """The charge: both the decision and the write from a single connection (a regression lock)."""
        from database.db import process_due_recurring_payment

        with connection_ledger() as ledger:
            process_due_recurring_payment(self.payment)
        self.assertEqual(len(ledger.opened), 1)
        self.assertEqual(ledger.leaked, [])


class LedgerReferenceInvariant(_MonetaryProfile):
    """`balance_events.ref_id` must really point at the transaction that wrote that movement."""

    def _event(self, source):
        events = self.rows(
            "SELECT * FROM balance_events WHERE source=? ORDER BY id", source)
        self.assertEqual(len(events), 1, f"{source}: tek defter satırı bekleniyor")
        return events[0]

    def _last_transaction(self, category):
        rows = self.rows(
            "SELECT id FROM transactions WHERE category=? ORDER BY id DESC LIMIT 1",
            category)
        self.assertTrue(rows, f"{category}: işlem satırı yazılmamış")
        return rows[0]["id"]

    def test_recurring_charge_marker_and_event_agree(self):
        from database.db import process_due_recurring_payment

        process_due_recurring_payment(self.payment)
        transaction_id = self._last_transaction("Dijital Platformlar")
        marker = self.rows(
            "SELECT * FROM recurring_operation_markers"
            " WHERE operation_type='charge'")[0]
        self.assertEqual(self._event("recurring_payment")["ref_id"], transaction_id)
        self.assertEqual(marker["transaction_id"], transaction_id)

    def test_subscription_refund_event_points_at_the_refund_transaction(self):
        from database.db import process_due_recurring_payment
        from services.recurring_service import refund_current_period_charge

        process_due_recurring_payment(self.payment)
        refund_current_period_charge(self.payment["id"])
        refund_transaction = self.rows(
            "SELECT id FROM transactions WHERE type='income' ORDER BY id DESC"
        )[0]["id"]
        self.assertEqual(
            self._event("subscription_refund")["ref_id"], refund_transaction)

    def test_asset_sale_event_points_at_the_sale_transaction(self):
        from services.asset_sale_service import AssetSaleService

        AssetSaleService.sell(self.asset["asset_id"], 120.0, self.account_id)
        self.assertEqual(
            self._event("asset_sale")["ref_id"],
            self._last_transaction("Varlık Satışı"),
        )

    def test_debt_payment_event_points_at_the_instalment_transaction(self):
        from database.db import insert_debt
        from services.debt_payment_service import DebtPaymentService

        insert_debt("Kredi", 1200.0, 100.0, 12)
        debt_id = self.rows("SELECT id FROM active_debts ORDER BY id DESC")[0]["id"]
        self.assertTrue(DebtPaymentService.pay_auto(
            debt_id, self.account_id, 1, "2026-08"))
        self.assertEqual(
            self._event("debt_payment")["ref_id"],
            self._last_transaction("Kredi Taksiti"),
        )

    def test_asset_purchase_event_points_at_the_purchase_transaction(self):
        from services.asset_purchase_service import AssetPurchaseService

        result = AssetPurchaseService.create_purchase(
            asset_name="D", asset_code="D", asset_type="Altın",
            purchase_price=10.0, quantity=1, account_id=self.account_id)
        events = self.rows(
            "SELECT * FROM balance_events WHERE source='asset_purchase'"
            " ORDER BY id DESC")
        self.assertEqual(events[0]["ref_id"], result["transaction_id"])

    def test_opening_baseline_rewrites_its_own_event(self):
        """The opening line must carry the row `record_balance_event` RETURNS.

        The id used to be read after the call with `cursor.lastrowid`; that
        rested on the assumption that there was exactly one INSERT inside the
        helper. Had the assumption broken, another event's timestamp would have
        been overwritten.
        """
        from database.db import ACCOUNT
        from database.init_db import initialize_database


        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("DELETE FROM balance_events WHERE source='account_opened'")
            conn.commit()
        finally:
            conn.close()

        initialize_database()

        events = self.rows(
            "SELECT * FROM balance_events WHERE entity_type=? AND entity_id=?"
            " ORDER BY id", ACCOUNT, self.account_id)
        openings = [e for e in events if e["source"] == "account_opened"]
        self.assertEqual(len(openings), 1)
        others = [e for e in events if e["source"] != "account_opened"]
        for event in others:
            self.assertGreaterEqual(
                event["ts"], openings[0]["ts"],
                "açılış çizgisi başka bir olayın zaman damgasını ezmiş olabilir",
            )


class LedgerReconciliationInvariant(_MonetaryProfile):
    """`database/init_db.py` CLAIMS this; here it is MEASURED.

        "EVERY point that touches accounts.balance and
         savings_goals.current_amount writes a row here ... so the ledger and
         the real balance can never diverge."

    A comment cannot carry that claim: when a new write path is added the
    comment silently becomes false. After every financial write path the ledger
    total is compared against the real balance.
    """

    def _totals(self):
        conn = sqlite3.connect(self.db_path)
        try:
            accounts = conn.execute(
                "SELECT COALESCE(SUM(balance), 0) FROM accounts").fetchone()[0]
            account_ledger = conn.execute(
                "SELECT COALESCE(SUM(delta), 0) FROM balance_events"
                " WHERE entity_type='account'").fetchone()[0]
            goals = conn.execute(
                "SELECT COALESCE(SUM(current_amount), 0) FROM savings_goals"
            ).fetchone()[0]
            goal_ledger = conn.execute(
                "SELECT COALESCE(SUM(delta), 0) FROM balance_events"
                " WHERE entity_type='savings_goal'").fetchone()[0]
        finally:
            conn.close()
        return (accounts, account_ledger), (goals, goal_ledger)

    def test_every_write_path_keeps_the_ledger_equal_to_the_balances(self):
        from database.db import insert_debt, process_due_recurring_payment
        from services.account_service import AccountService
        from services.asset_purchase_service import AssetPurchaseService
        from services.asset_sale_service import AssetSaleService
        from services.debt_payment_service import DebtPaymentService
        from services.recurring_service import refund_current_period_charge
        from services.savings_service import SavingsService
        from services.transaction_service import TransactionService

        insert_debt("Kredi", 1200.0, 100.0, 12)
        debt_id = self.rows("SELECT id FROM active_debts ORDER BY id DESC")[0]["id"]

        steps = [
            ("expense", lambda: TransactionService.add_transaction(
                self.account_id, 250.0, "expense", "Market", "x",
                detect_subscription=False)),
            ("income", lambda: TransactionService.add_transaction(
                self.account_id, 900.0, "income", "Maaş", "x",
                detect_subscription=False)),
            ("card_expense", lambda: TransactionService.add_transaction(
                self.card_id, 75.0, "expense", "Market", "x",
                detect_subscription=False)),
            ("card_payment", lambda: AccountService.pay_credit_card_debt(
                self.card_id, self.account_id, 200.0)),
            ("savings_deposit", lambda: SavingsService.deposit_to_goal(
                self.goal_id, 120.0, self.account_id)),
            ("savings_withdraw", lambda: SavingsService.withdraw_from_goal(
                self.goal_id, 40.0, self.account_id)),
            ("asset_purchase", lambda: AssetPurchaseService.create_purchase(
                asset_name="E", asset_code="E", asset_type="Altın",
                purchase_price=30.0, quantity=2, account_id=self.account_id)),
            ("asset_sale", lambda: AssetSaleService.sell(
                self.asset["asset_id"], 130.0, self.account_id, quantity=1)),
            ("recurring_charge", lambda: process_due_recurring_payment(
                self.payment)),
            ("subscription_refund", lambda: refund_current_period_charge(
                self.payment["id"])),
            ("debt_instalment", lambda: DebtPaymentService.pay_auto(
                debt_id, self.account_id, 1, "2026-08")),
            ("new_account", lambda: AccountService.create_account(
                "Sonradan", "checking", initial_balance=4321.0)),
            ("goal_deleted", lambda: SavingsService.delete_goal(self.goal_id)),
        ]

        for name, call in steps:
            call()
            (accounts, account_ledger), (goals, goal_ledger) = self._totals()
            self.assertAlmostEqual(
                accounts, account_ledger, places=2,
                msg=f"{name}: hesap defteri gerçek bakiyeden ayrıştı")
            self.assertAlmostEqual(
                goals, goal_ledger, places=2,
                msg=f"{name}: birikim defteri gerçek tutardan ayrıştı")


class PersistedCorruptionErrorTyping(_MonetaryProfile):
    """A corrupt RECORD and invalid INPUT must not be reduced to the same error type.

    The same corrupt `active_assets` row produced two different types in two
    readers: `get_all_assets` a typed `FinancialDataIntegrityError`, while
    `AssetSaleService.sell` gave a plain `ValueError` (with an English internal
    message, at that). The two readers now meet in a single
    classification.
    """

    def _corrupt_asset(self, field, raw):
        from database.db import SECRET_KEY
        from utils.crypto import encrypt
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(f"UPDATE active_assets SET {field}=? WHERE id=?",
                         (encrypt(raw, SECRET_KEY), self.asset["asset_id"]))
            conn.commit()
        finally:
            conn.close()

    def test_sale_reports_a_corrupt_row_as_a_data_integrity_failure(self):
        from services.asset_sale_service import AssetSaleService
        from utils.errors import FinancialDataIntegrityError

        for field, raw in (("quantity", "bozuk-veri"), ("quantity", "nan"),
                           ("purchase_price", "bozuk-veri"),
                           ("purchase_price", "inf")):
            with self.subTest(field=field, raw=raw):
                self.setUp()
                self._corrupt_asset(field, raw)
                before = self.state()
                with self.assertRaises(FinancialDataIntegrityError):
                    AssetSaleService.sell(
                        self.asset["asset_id"], 120.0, self.account_id)
                self.assertEqual(self.state(), before,
                                 "bozuk satır üzerinden satış yazdı")

    def test_caller_supplied_values_stay_plain_value_errors(self):
        """User input IS NOT a corrupt record -- its type must stay different too."""
        from services.asset_sale_service import AssetSaleService
        from utils.errors import FinancialDataIntegrityError

        for bad_price in (0, -1.0, float("nan")):
            with self.subTest(price=bad_price):
                with self.assertRaises(ValueError) as ctx:
                    AssetSaleService.sell(
                        self.asset["asset_id"], bad_price, self.account_id)
                self.assertNotIsInstance(ctx.exception, FinancialDataIntegrityError)


if __name__ == "__main__":
    unittest.main()
