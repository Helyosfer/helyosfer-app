"""Changing and removing a transaction keeps balance, ledger and row together."""

import datetime
import os
import tempfile
import unittest
from unittest import mock


def _day(offset):
    return (datetime.date.today() - datetime.timedelta(days=offset)).isoformat()


class TransactionEditServiceTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._patch = mock.patch("database.db.DB_NAME", self.db_path)
        self._patch.start()
        from database.init_db import initialize_database
        from services.account_service import AccountService

        initialize_database()
        self.account = AccountService.create_account("Main", "checking", 10000.0)

    def tearDown(self):
        self._patch.stop()
        os.unlink(self.db_path)

    # -- helpers -------------------------------------------------------------
    def _add(self, kind="expense", amount=500.0, offset=0, account=None, category=None,
             installments=None):
        from database.db import get_connection
        from services.transaction_service import TransactionService

        TransactionService.add_transaction(
            account_id=account or self.account, amount=amount, transaction_type=kind,
            category=category or ("Maaş" if kind == "income" else "Taksi"),
            description="Not", transaction_date=f"{_day(offset)} 09:30:00",
            installments=installments, detect_subscription=False,
        )
        conn = get_connection()
        try:
            return conn.execute("SELECT MAX(id) FROM transactions").fetchone()[0]
        finally:
            conn.close()

    def _numbers(self):
        """(account balance, ledger total, transaction count)."""
        from database.db import get_connection

        conn = get_connection()
        try:
            balance = conn.execute(
                "SELECT balance FROM accounts WHERE id = ?", (self.account,)).fetchone()[0]
            ledger = conn.execute(
                "SELECT SUM(delta) FROM balance_events WHERE entity_id = ?",
                (self.account,)).fetchone()[0]
            count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        finally:
            conn.close()
        return round(balance, 2), round(ledger, 2), count

    def _balance_at(self, offset):
        from services.history_service import get_balance_at

        return get_balance_at(_day(offset))["total_balance"]

    # -- reading -------------------------------------------------------------
    def test_a_plain_transaction_is_read_back_unlocked(self):
        from services.transaction_edit_service import get_transaction

        found = get_transaction(self._add(amount=1250.5, offset=3))
        self.assertEqual(
            (found["amount"], found["type"], found["category"], found["description"],
             found["date"], found["locked"]),
            (1250.5, "expense", "Taksi", "Not", f"{_day(3)} 09:30:00", ""),
        )

    def test_a_missing_transaction_is_refused(self):
        from services.transaction_edit_service import NOT_FOUND, get_transaction

        with self.assertRaises(ValueError) as caught:
            get_transaction(999)
        self.assertEqual(str(caught.exception), NOT_FOUND)

    # -- removing ------------------------------------------------------------
    def test_removing_an_expense_gives_the_money_back(self):
        from services.transaction_edit_service import delete_transaction

        tx = self._add(amount=500.0)
        self.assertEqual(self._numbers(), (9500.0, 9500.0, 1))
        delete_transaction(tx)
        self.assertEqual(self._numbers(), (10000.0, 10000.0, 0))

    def test_removing_an_income_takes_it_out(self):
        from services.transaction_edit_service import delete_transaction

        tx = self._add("income", 2000.0)
        delete_transaction(tx)
        self.assertEqual(self._numbers(), (10000.0, 10000.0, 0))

    def test_removing_a_past_transaction_clears_it_from_that_day_on(self):
        from services.transaction_edit_service import delete_transaction

        tx = self._add(amount=500.0, offset=40)
        self.assertEqual(self._balance_at(20), 9500.0)
        delete_transaction(tx)
        self.assertEqual(self._balance_at(40), 10000.0)
        self.assertEqual(self._balance_at(20), 10000.0)
        self.assertEqual(self._balance_at(0), 10000.0)

    def test_removing_twice_is_refused_and_changes_nothing(self):
        from services.transaction_edit_service import delete_transaction

        tx = self._add(amount=500.0)
        delete_transaction(tx)
        with self.assertRaises(ValueError):
            delete_transaction(tx)
        self.assertEqual(self._numbers(), (10000.0, 10000.0, 0))

    # -- moving and turning ----------------------------------------------------
    def _balance_of(self, account):
        from database.db import get_connection

        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT a.balance, (SELECT SUM(delta) FROM balance_events"
                " WHERE entity_id = a.id) FROM accounts a WHERE a.id = ?", (account,)).fetchone()
        finally:
            conn.close()
        return round(row[0], 2), round(row[1], 2)

    def test_moving_to_another_account_takes_the_effect_along(self):
        from services.account_service import AccountService
        from services.transaction_edit_service import get_transaction, update_transaction

        other = AccountService.create_account("Second", "checking", 3000.0)
        tx = self._add(amount=500.0, offset=5)
        update_transaction(tx, 500.0, "Taksi", "Not", _day(5), account_id=other)
        self.assertEqual(self._balance_of(self.account), (10000.0, 10000.0))
        self.assertEqual(self._balance_of(other), (2500.0, 2500.0))
        self.assertEqual(get_transaction(tx)["account_id"], other)
        # The total is what it was on every day; only the account differs.
        self.assertEqual(self._balance_at(2), 12500.0)
        self.assertEqual(self._balance_at(0), 12500.0)

    def test_turning_spending_into_income_moves_the_balance_twice_the_amount(self):
        from services.transaction_edit_service import get_transaction, update_transaction

        tx = self._add(amount=500.0)
        update_transaction(tx, 500.0, "Maaş", "Not", _day(0), kind="income")
        self.assertEqual(self._numbers(), (10500.0, 10500.0, 1))
        self.assertEqual(get_transaction(tx)["type"], "income")
        update_transaction(tx, 200.0, "Taksi", "Not", _day(0), kind="expense")
        self.assertEqual(self._numbers(), (9800.0, 9800.0, 1))

    def test_a_turned_transaction_needs_a_category_of_its_new_kind(self):
        from services.transaction_edit_service import (
            BAD_CATEGORY, BAD_KIND, update_transaction,
        )

        tx = self._add(amount=500.0)
        for kind, category, message in (
            ("income", "Taksi", BAD_CATEGORY), ("transfer", "Taksi", BAD_KIND),
        ):
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError) as caught:
                    update_transaction(tx, 500.0, category, "Not", _day(0), kind=kind)
                self.assertEqual(str(caught.exception), message)
                self.assertEqual(self._numbers(), (9500.0, 9500.0, 1))

    def test_a_move_the_new_account_cannot_carry_changes_nothing(self):
        from services.account_service import AccountService
        from services.transaction_edit_service import update_transaction

        card = AccountService.create_account("Card", "credit_card", 0.0, credit_limit=300.0)
        tx = self._add(amount=500.0)
        for target in (card, 9999):
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    update_transaction(tx, 500.0, "Taksi", "Not", _day(0), account_id=target)
                self.assertEqual(self._numbers(), (9500.0, 9500.0, 1))
        self.assertEqual(self._balance_of(card)[0], 0.0)
        # Within the limit the card takes it, as a debt.
        update_transaction(tx, 250.0, "Taksi", "Not", _day(0), account_id=card)
        self.assertEqual(self._numbers(), (10000.0, 10000.0, 1))
        self.assertEqual(self._balance_of(card)[0], -250.0)

    # -- changing ------------------------------------------------------------
    def test_changing_the_amount_moves_the_balance_by_the_difference(self):
        from services.transaction_edit_service import get_transaction, update_transaction

        tx = self._add(amount=500.0)
        update_transaction(tx, 800.0, "Süpermarket", "Yeni not", _day(0))
        self.assertEqual(self._numbers(), (9200.0, 9200.0, 1))
        found = get_transaction(tx)
        self.assertEqual(
            (found["amount"], found["category"], found["description"]),
            (800.0, "Süpermarket", "Yeni not"),
        )
        self.assertEqual(found["date"], f"{_day(0)} 09:30:00")

    def test_moving_the_date_back_redraws_the_days_between(self):
        from services.transaction_edit_service import update_transaction

        tx = self._add(amount=500.0, offset=10)
        update_transaction(tx, 500.0, "Taksi", "Not", _day(60))
        self.assertEqual(self._balance_at(60), 9500.0)
        self.assertEqual(self._balance_at(30), 9500.0)
        self.assertEqual(self._numbers(), (9500.0, 9500.0, 1))

    def test_moving_the_date_forward_frees_the_days_before(self):
        from services.transaction_edit_service import update_transaction

        tx = self._add(amount=500.0, offset=60)
        update_transaction(tx, 500.0, "Taksi", "Not", _day(10))
        self.assertEqual(self._balance_at(30), 10000.0)
        self.assertEqual(self._balance_at(10), 9500.0)

    def test_bad_changes_are_refused_and_change_nothing(self):
        from services.transaction_edit_service import update_transaction

        tx = self._add(amount=500.0)
        tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        for amount, category, date in (
            (0, "Taksi", _day(0)), (-5, "Taksi", _day(0)), (float("nan"), "Taksi", _day(0)),
            (500.0, "Maaş", _day(0)), (500.0, "Yok Böyle", _day(0)), (500.0, "Kredi Taksiti", _day(0)),
            (500.0, "Taksi", tomorrow), (500.0, "Taksi", "dün"),
        ):
            with self.subTest(amount=amount, category=category, date=date):
                with self.assertRaises(ValueError):
                    update_transaction(tx, amount, category, "x", date)
                self.assertEqual(self._numbers(), (9500.0, 9500.0, 1))

    def test_a_card_change_counts_only_the_difference_against_the_limit(self):
        from services.account_service import AccountService
        from services.transaction_edit_service import update_transaction

        card = AccountService.create_account("Card", "credit_card", 0.0, credit_limit=1000.0)
        tx = self._add(amount=900.0, account=card)
        update_transaction(tx, 1000.0, "Taksi", "Not", _day(0))
        with self.assertRaises(ValueError):
            update_transaction(tx, 1000.01, "Taksi", "Not", _day(0))
        self.assertEqual(AccountService.get_account(card)["balance"], -1000.0)

    # -- records the application wrote ---------------------------------------------
    def _last(self, count=1):
        from database.db import get_connection

        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT id FROM transactions ORDER BY id DESC LIMIT ?", (count,)).fetchall()
        finally:
            conn.close()
        return [row[0] for row in rows][::-1]

    def _debt(self):
        from database.db import get_connection

        conn = get_connection()
        try:
            return tuple(conn.execute(
                "SELECT paid_installments, is_active FROM active_debts").fetchone())
        finally:
            conn.close()

    def _holdings(self):
        from database.db import SECRET_KEY, get_connection
        from utils.crypto import decrypt

        conn = get_connection()
        try:
            return [
                (row["id"], row["asset_code"], float(decrypt(row["quantity"], SECRET_KEY)),
                 float(decrypt(row["purchase_price"], SECRET_KEY)))
                for row in conn.execute("SELECT * FROM active_assets ORDER BY id")
            ]
        finally:
            conn.close()

    def test_only_the_date_of_an_application_record_can_change(self):
        from services.debt_payment_service import DebtPaymentService
        from services.transaction_edit_service import get_transaction, update_transaction

        DebtPaymentService.create_debt("Loan", 500.0, 6)
        DebtPaymentService.pay_manual(1, self.account, 2)
        tx = self._last()[0]
        found = get_transaction(tx)
        self.assertEqual((found["kind"], found["locked"]), ("debt_payment", ""))
        self.assertEqual(
            found["fixed"], ("amount", "category", "description", "account", "kind"))
        # Whatever else is asked for, only the day moves.
        update_transaction(tx, 1.0, "Taksi", "changed", _day(12), account_id=999, kind="income")
        after = get_transaction(tx)
        self.assertEqual(
            (after["amount"], after["category"], after["type"], after["account_id"],
             after["description"], after["date"][:10]),
            (1000.0, "Kredi Taksiti", "expense", self.account, found["description"], _day(12)),
        )
        self.assertEqual(self._numbers(), (9000.0, 9000.0, 1))
        # The payment now belongs to that day, and the history starts with it.
        self.assertIsNone(self._balance_at(13))
        self.assertEqual(self._balance_at(12), 9000.0)
        self.assertEqual(self._balance_at(0), 9000.0)
        self.assertEqual(self._debt(), (2, 1))

    def test_removing_a_debt_payment_gives_the_installments_back(self):
        from services.debt_payment_service import DebtPaymentService
        from services.transaction_edit_service import delete_transaction

        DebtPaymentService.create_debt("Loan", 500.0, 3)
        DebtPaymentService.pay_manual(1, self.account, 1)
        first = self._last()[0]
        # Paying the rest closes the debt; undoing that opens it again.
        DebtPaymentService.pay_manual(1, self.account)
        closing = self._last()[0]
        self.assertEqual((self._debt(), self._numbers()[0]), ((3, 0), 8500.0))
        delete_transaction(closing)
        self.assertEqual((self._debt(), self._numbers()), ((1, 1), (9500.0, 9500.0, 1)))
        delete_transaction(first)
        self.assertEqual((self._debt(), self._numbers()), ((0, 1), (10000.0, 10000.0, 0)))

    def test_removing_an_automatic_installment_does_not_take_it_again(self):
        import datetime

        from services.debt_payment_service import DebtPaymentService
        from services.scheduled_service import process_due_items
        from services.transaction_edit_service import delete_transaction

        today = datetime.date.today()
        DebtPaymentService.create_debt(
            "Loan", 500.0, 6, True, today.day, auto_pay_account_id=self.account)
        self.assertTrue(process_due_items())
        self.assertEqual(self._debt(), (1, 1))
        delete_transaction(self._last()[0])
        self.assertEqual((self._debt(), self._numbers()), ((0, 1), (10000.0, 10000.0, 0)))
        self.assertFalse(process_due_items())
        self.assertEqual(self._debt(), (0, 1))

    def test_removing_either_half_of_a_card_payment_undoes_both(self):
        from services.account_service import AccountService
        from services.transaction_edit_service import (
            delete_transaction, get_transaction, update_transaction,
        )

        card = AccountService.create_account("Card", "credit_card", 0.0, credit_limit=50000.0)
        self._add(amount=1000.0, account=card)
        for half in (0, 1):
            with self.subTest(half=half):
                AccountService.pay_credit_card_debt(card, self.account, 300.0)
                pair = self._last(2)
                self.assertEqual(self._balance_of(card)[0], -700.0)
                self.assertEqual(self._numbers()[0], 9700.0)
                self.assertEqual(get_transaction(pair[half])["kind"], "card_payment")
                # Moving one half to another day moves the other with it.
                update_transaction(pair[half], 1.0, "", "", _day(4))
                self.assertEqual(
                    [get_transaction(tx)["date"][:10] for tx in pair], [_day(4), _day(4)])
                self.assertEqual(self._balance_of(card), (-700.0, -700.0))
                delete_transaction(pair[half])
                self.assertEqual(self._balance_of(card), (-1000.0, -1000.0))
                self.assertEqual(self._numbers(), (10000.0, 10000.0, 1))

    def test_a_card_payment_whose_card_is_gone_is_still_undone(self):
        from services.account_service import AccountService
        from services.transaction_edit_service import delete_transaction

        card = AccountService.create_account("Card", "credit_card", 0.0, credit_limit=50000.0)
        self._add(amount=1000.0, account=card)
        AccountService.pay_credit_card_debt(card, self.account, 300.0)
        paid_from = self._last(2)[0]
        AccountService.delete_credit_card(card)
        delete_transaction(paid_from)
        self.assertEqual(self._numbers(), (10000.0, 10000.0, 0))

    def test_removing_an_asset_purchase_removes_the_holding(self):
        from services.asset_purchase_service import AssetPurchaseService
        from services.transaction_edit_service import (
            delete_transaction, get_transaction, update_transaction,
        )

        bought = AssetPurchaseService.create_purchase(
            asset_name="Altin", asset_code="GRAM", asset_type="Altın",
            purchase_price=250.0, quantity=4, account_id=self.account)
        tx = bought["transaction_id"]
        self.assertEqual(self._numbers(), (9000.0, 9000.0, 1))
        self.assertEqual(get_transaction(tx)["kind"], "asset_purchase")
        update_transaction(tx, 1.0, "", "", _day(6))
        self.assertEqual(self._balance_at(6), 9000.0)
        self.assertEqual(self._holdings(), [(bought["asset_id"], "GRAM", 4.0, 250.0)])
        delete_transaction(tx)
        self.assertEqual(self._holdings(), [])
        self.assertEqual(self._numbers(), (10000.0, 10000.0, 0))

    def test_a_purchase_cannot_be_removed_while_part_of_it_is_sold(self):
        from services.asset_purchase_service import AssetPurchaseService
        from services.asset_sale_service import AssetSaleService
        from services.transaction_edit_service import SOLD_SINCE, delete_transaction

        bought = AssetPurchaseService.create_purchase(
            asset_name="Altin", asset_code="GRAM", asset_type="Altın",
            purchase_price=250.0, quantity=4, account_id=self.account)
        AssetSaleService.sell(bought["asset_id"], 300.0, self.account, quantity=1)
        sale = self._last()[0]
        with self.assertRaises(ValueError) as caught:
            delete_transaction(bought["transaction_id"])
        self.assertEqual(str(caught.exception), SOLD_SINCE)
        self.assertEqual(self._numbers(), (9300.0, 9300.0, 2))
        # With the sale undone the holding is whole again and can go.
        delete_transaction(sale)
        self.assertEqual(self._holdings(), [(bought["asset_id"], "GRAM", 4.0, 250.0)])
        delete_transaction(bought["transaction_id"])
        self.assertEqual((self._holdings(), self._numbers()), ([], (10000.0, 10000.0, 0)))

    def test_sales_are_undone_in_any_order_even_when_the_holding_was_emptied(self):
        from services.asset_purchase_service import AssetPurchaseService
        from services.asset_sale_service import AssetSaleService
        from services.transaction_edit_service import delete_transaction, get_transaction

        bought = AssetPurchaseService.create_purchase(
            asset_name="Altin", asset_code="GRAM", asset_type="Altın",
            purchase_price=250.0, quantity=4, account_id=self.account)
        asset = bought["asset_id"]
        AssetSaleService.sell(asset, 300.0, self.account, quantity=1)
        first = self._last()[0]
        AssetSaleService.sell(asset, 320.0, self.account)
        second = self._last()[0]
        self.assertEqual(self._holdings(), [])
        self.assertEqual(self._numbers()[0], 9000.0 + 300.0 + 960.0)
        self.assertEqual(get_transaction(second)["kind"], "asset_sale")
        # The earlier sale first: the holding comes back with what it took.
        delete_transaction(first)
        self.assertEqual(self._holdings(), [(asset, "GRAM", 1.0, 250.0)])
        delete_transaction(second)
        self.assertEqual(self._holdings(), [(asset, "GRAM", 4.0, 250.0)])
        self.assertEqual(self._numbers(), (9000.0, 9000.0, 1))

    def test_a_purchase_in_installments_is_changed_and_removed_with_its_plan(self):
        from database.db import SECRET_KEY, get_connection
        from services.account_service import AccountService
        from services.transaction_edit_service import (
            delete_transaction, get_transaction, update_transaction,
        )
        from utils.crypto import decrypt

        def plans():
            conn = get_connection()
            try:
                return [
                    (float(decrypt(row["total_amount"], SECRET_KEY)),
                     float(decrypt(row["monthly_amount"], SECRET_KEY)), row["created_at"][:10])
                    for row in conn.execute("SELECT * FROM installment_plans")
                ]
            finally:
                conn.close()

        card = AccountService.create_account("Card", "credit_card", 0.0, credit_limit=50000.0)
        other = AccountService.create_account("Other", "checking", 0.0)
        tx = self._add(amount=1200.0, account=card, installments=6)
        found = get_transaction(tx)
        self.assertEqual((found["kind"], found["fixed"]), ("installment", ("account", "kind")))
        self.assertEqual(plans(), [(1200.0, 200.0, _day(0))])
        # The amount, the wording and the day change; the card and the
        # direction do not, whatever is asked for.
        update_transaction(tx, 1800.0, "Kıyafet", "Coat", _day(3), account_id=other, kind="income")
        after = get_transaction(tx)
        self.assertEqual(
            (after["amount"], after["category"], after["account_id"], after["type"]),
            (1800.0, "Kıyafet", card, "expense"),
        )
        self.assertEqual(plans(), [(1800.0, 300.0, _day(3))])
        self.assertEqual(self._balance_of(card), (-1800.0, -1800.0))
        self.assertEqual(get_transaction(tx)["kind"], "installment")
        delete_transaction(tx)
        self.assertEqual((plans(), self._balance_of(card)), ([], (0.0, 0.0)))

    def test_records_that_cannot_be_traced_stay_locked(self):
        from services.transaction_edit_service import (
            LINKED, PENDING, delete_transaction, get_transaction, update_transaction,
        )

        cases = [
            # Filed under one of the application's categories with nothing
            # to say what it belongs to, as a record from an older version is.
            (self._add(amount=100.0, category="Kredi Taksiti"), LINKED),
            (self._add(amount=100.0, offset=-5), PENDING),
        ]

        before = self._numbers()
        for tx, reason in cases:
            with self.subTest(tx=tx, reason=reason):
                self.assertEqual(get_transaction(tx)["locked"], reason)
                with self.assertRaises(ValueError):
                    delete_transaction(tx)
                with self.assertRaises(ValueError):
                    update_transaction(tx, 1.0, "Taksi", "x", _day(0))
        self.assertEqual(self._numbers(), before)


if __name__ == "__main__":
    unittest.main()
