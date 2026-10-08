"""The producer, the consumer and the deletion must use the same key type in the snapshot cache.

WHY IT EXISTS: the producer side writes into the `_asset_data_cache["recent"]`
dictionary with `recent[account["id"]]` -- and `id` arrives from sqlite3 as an
**int**. The UI reads with `recent.get(acc["id"])`, the same type. But the card
deletion path did `recent.pop(str(account_id), None)`: because the string key
never matched, the deleted account's transactions STAYED in the snapshot.

It does not reach the user today, because the same operation also removes the
account from the `accounts` list and the UI walks only that list -- so the stale
entry is not drawn. Even so, the snapshot carries a state that no longer
describes the profile; if `recent` is ever consumed independently of the
`accounts` list, this turns into a silent stale-state problem.

A NOTE ON THE FIX: when this finding was first reported it also carried the
rationale "if a deleted id is reused, the new account will see the old
transactions". That WAS WRONG and was removed: the `accounts` table uses
`id INTEGER PRIMARY KEY AUTOINCREMENT`, so SQLite does not hand out deleted ids
again. It was a claim written without reading the schema.

The type side was closed along with this test: the `_AssetDataCache` TypedDict
types the `recent` key as `int`, so the same mismatch can no longer pass type
checking either.

"""

import unittest

import services.asset_service as asset_service


class RecentCacheKeyType(unittest.TestCase):

    def setUp(self):
        self._saved = asset_service._asset_data_cache
        self.addCleanup(self._restore)

    def _restore(self):
        asset_service._asset_data_cache = self._saved

    def _seed(self):
        asset_service._asset_data_cache = {
            "summary": {"cash": 100.0, "card_debt": 50.0, "net": 50.0},
            "accounts": [{"id": 42, "name": "Kart"}, {"id": 7, "name": "Nakit"}],
            "recent": {42: ["silinen-kartin-islemi"], 7: ["kalan-hesabin-islemi"]},
            "active_assets_result": None,
            "ready": True,
        }

    def test_deleting_an_account_drops_its_recent_entry(self):
        """THE ORIGINAL BUG: a deleted account's transactions must not stay in the snapshot."""
        self._seed()
        asset_service.invalidate_asset_data_cache(
            deleted_account_id=42, deleted_card_debt=50.0)

        cache = asset_service._asset_data_cache
        self.assertNotIn(
            42, cache["recent"],
            "silinen hesabın recent girdisi snapshot'ta kaldı",
        )

    def test_other_accounts_keep_their_recent_entries(self):
        """The complementary case: the fix must not delete more than it should."""
        self._seed()
        asset_service.invalidate_asset_data_cache(
            deleted_account_id=42, deleted_card_debt=50.0)

        cache = asset_service._asset_data_cache
        self.assertEqual(cache["recent"], {7: ["kalan-hesabin-islemi"]})
        self.assertEqual([a["id"] for a in cache["accounts"]], [7])

    def test_string_account_id_is_normalised(self):
        """The int key must be deleted even if the caller passes a string.

        `invalidate_asset_data_cache` already normalises `deleted_account_id`
        with `int(...)`; this test prevents that normalisation being
        removed.
        """
        self._seed()
        asset_service.invalidate_asset_data_cache(
            deleted_account_id="42", deleted_card_debt=50.0)
        self.assertNotIn(42, asset_service._asset_data_cache["recent"])


if __name__ == "__main__":
    unittest.main()
