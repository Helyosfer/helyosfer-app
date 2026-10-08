"""Synchronisation between the account list (the in-memory snapshot) and the real database balances.

THE BUG: when a user added a new account, the total on the home screen updated
but the "My Cards" list stayed as it was -- the new account did not appear at
all, or its balance was drawn with the old value.

THE ROOT CAUSE was not how the numbers were computed but the READ PATHS
diverging:

  * The home screen total (`_compute_dashboard_metrics`) reads fresh from the
    database on every call -> it sees the new account immediately.
  * `render_accounts` runs no SQL at all for speed and draws only from the
    `asset_service._asset_data_cache` snapshot -> if nobody refreshes the
    snapshot after a write, it draws OLD data.

Refreshing had been left to each writing flow by hand and most had forgotten:
only adding a transaction and deleting a card behaved correctly; adding an
account, paying card debt and transferring savings had been missed.

THE FIX: the writing side lowers the flag with `mark_account_cache_stale()`
(from one place -- `record_balance_event`, since the ledger invariant means
every path that touches a balance goes through there), and the reading side
refreshes if necessary with `ensure_account_cache_fresh()`. These tests verify
that the flag really is lowered and that the read returns fresh data.

"""
import os
import tempfile
import unittest
from unittest import mock



class AccountCacheSyncTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._patcher = mock.patch("database.db.DB_NAME", self.db_path)
        self._patcher.start()
        from database.init_db import initialize_database
        initialize_database()

    def tearDown(self):
        self._patcher.stop()
        os.unlink(self.db_path)

    def _warm_cache(self):
        """Imitates the warmed snapshot from application startup."""
        import services.asset_service as asset_service
        asset_service.refresh_account_cache_snapshot()
        self.assertFalse(asset_service._account_cache_stale)
        return asset_service

    def _cached_names(self, asset_service):
        cache = asset_service.ensure_account_cache_fresh()
        return {a["name"] for a in (cache.get("accounts") or [])}

    def test_new_account_appears_in_cached_list(self):
        """The original bug: an added account did not appear in the list at all."""
        from services.account_service import AccountService

        asset_service = self._warm_cache()
        self.assertNotIn("Yeni Hesap", self._cached_names(asset_service))

        AccountService.create_account("Yeni Hesap", "checking",
                                      initial_balance=5000)

        self.assertTrue(asset_service._account_cache_stale,
                        "hesap açılışı snapshot'ı bayat işaretlemeli")
        self.assertIn("Yeni Hesap", self._cached_names(asset_service))

    def test_cached_summary_matches_db_after_account_added(self):
        """The list and the home screen total must show the same number."""
        from services.account_service import AccountService
        from services.queries import DashboardService

        asset_service = self._warm_cache()
        AccountService.create_account("Vadesiz", "checking",
                                      initial_balance=12500)

        cache = asset_service.ensure_account_cache_fresh()
        self.assertAlmostEqual(
            cache["summary"]["net"],
            DashboardService.get_total_balance(),
            places=2,
        )

    def test_transaction_updates_cached_balance(self):
        """The balance in the list must change after a transaction too (it used to stay old)."""
        from services.account_service import AccountService
        from services.transaction_service import TransactionService

        account_id = AccountService.create_account("Vadesiz", "checking",
                                                   initial_balance=1000)
        asset_service = self._warm_cache()

        TransactionService.add_transaction(
            account_id=account_id, amount=250, transaction_type="expense",
            category="Market", description="test",
        )

        self.assertTrue(asset_service._account_cache_stale)
        cache = asset_service.ensure_account_cache_fresh()
        balance = next(a["balance"] for a in cache["accounts"]
                       if a["id"] == account_id)
        self.assertAlmostEqual(balance, 750.0, places=2)

    def test_card_payment_updates_both_cached_accounts(self):
        """A card debt payment affects two accounts; both must be refreshed."""
        from services.account_service import AccountService

        checking_id = AccountService.create_account("Vadesiz", "checking",
                                                    initial_balance=5000)
        card_id = AccountService.create_account("Kart", "credit_card",
                                                initial_balance=2000,
                                                credit_limit=10000)
        asset_service = self._warm_cache()

        AccountService.pay_credit_card_debt(card_id, checking_id, 500)

        self.assertTrue(asset_service._account_cache_stale)
        cache = asset_service.ensure_account_cache_fresh()
        by_id = {a["id"]: a for a in cache["accounts"]}
        self.assertAlmostEqual(by_id[checking_id]["balance"], 4500.0, places=2)
        self.assertAlmostEqual(by_id[card_id]["debt"], 1500.0, places=2)

    def test_savings_deposit_updates_cached_balance(self):
        """A savings transfer also reduces the balance; the list must show it."""
        from services.account_service import AccountService
        from services.savings_service import SavingsService

        account_id = AccountService.create_account("Vadesiz", "checking",
                                                   initial_balance=3000)
        goal_id = SavingsService.create_goal("Tatil", 10000)
        asset_service = self._warm_cache()

        SavingsService.deposit_to_goal(goal_id, 800, account_id)

        self.assertTrue(asset_service._account_cache_stale)
        cache = asset_service.ensure_account_cache_fresh()
        balance = next(a["balance"] for a in cache["accounts"]
                       if a["id"] == account_id)
        self.assertAlmostEqual(balance, 2200.0, places=2)

    def test_fresh_read_is_skipped_when_nothing_changed(self):
        """If the flag was not lowered, no refresh happens -- instant render is preserved."""
        asset_service = self._warm_cache()

        with mock.patch.object(
            asset_service, "refresh_account_cache_snapshot"
        ) as refresh:
            asset_service.ensure_account_cache_fresh()
            refresh.assert_not_called()

    def test_unwarmed_cache_is_left_to_the_warmup_worker(self):
        """With ready=False nothing steps in; the startup worker will read fresh anyway.

        Had it stepped in, the `active_assets_result` field, which needs the
        network, would have dropped to None (the My Assets card would have been
        drawn empty).
        """
        import services.asset_service as asset_service

        asset_service._asset_data_cache = {
            "summary": {}, "accounts": [], "recent": {},
            "active_assets_result": None, "ready": False,
        }
        asset_service.mark_account_cache_stale()

        with mock.patch.object(
            asset_service, "refresh_account_cache_snapshot"
        ) as refresh:
            asset_service.ensure_account_cache_fresh()
            refresh.assert_not_called()
        self.assertTrue(asset_service._account_cache_stale,
                        "bayrak düşmemeli — tazeleme hâlâ borçlu")


if __name__ == "__main__":
    unittest.main()
