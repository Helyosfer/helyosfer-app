"""The account/category search contract -- Turkish folding especially.

WHY IT EXISTS: the search bar on the home screen was bound to no handler for a
long time and its only gate measured merely how it LOOKED. This suite measures
that the search box DOES SOMETHING.

Most of the tests here are devoted to Turkish case folding, because that is
where it breaks: `"I".casefold()` -> `"i"` but `"ı".casefold()` -> `"ı"`. So with
plain `casefold`, a user typing "ISI" CANNOT FIND the record "ısı". This
suite pins that the search service does not fall into that trap.

"""
import os
import sqlite3
import tempfile
import unittest
from unittest import mock


from services.search_service import (
    ACCOUNT, CATEGORY, match_names, matches, normalize,
)


class MatchesTest(unittest.TestCase):
    """The shared helper for callers that FILTER a list.

    Unlike `search()`, an EMPTY QUERY lets everything through: this function is
    for "filter", not for "search".
    """

    def test_empty_query_lets_everything_through(self):
        for query in ("", "   ", None):
            with self.subTest(query=query):
                self.assertTrue(matches(query, "herhangi bir sey"))

    def test_matches_any_of_the_given_fields(self):
        self.assertTrue(matches("btc", "BTC", "Bitcoin"))
        self.assertTrue(matches("bitcoin", "BTC", "Bitcoin"))
        self.assertFalse(matches("ethereum", "BTC", "Bitcoin"))

    def test_turkish_bist_name_is_found_without_special_characters(self):
        """This was the real bug: with `.lower()` this search returned EMPTY."""
        self.assertTrue(matches("is bankasi", "ISCTR", "İŞ BANKASI"))
        self.assertTrue(matches("İŞ", "ISCTR", "İŞ BANKASI"))
        self.assertTrue(matches("tupras", "TUPRS", "TÜPRAŞ"))

    def test_dotless_and_dotted_i_are_interchangeable_in_filters(self):
        self.assertTrue(matches("ISI", "Isıtma"))
        self.assertTrue(matches("ısı", "ISITMA"))

    def test_no_candidates_means_no_match_unless_query_is_empty(self):
        self.assertFalse(matches("btc"))
        self.assertTrue(matches(""))

    def test_none_fields_do_not_raise(self):
        self.assertFalse(matches("btc", None, ""))


class NormalizeTest(unittest.TestCase):
    def test_dotted_and_dotless_i_all_fold_together(self):
        """Where Turkish search breaks most often.

        All four spellings are the same word; whichever the user types, they
        must find the others.
        """
        forms = ["ISI", "ısı", "İSİ", "Isı", "isi"]
        normalized = {normalize(form) for form in forms}
        self.assertEqual(
            normalized, {"isi"},
            f"ı/İ/I/i aynı yere inmedi: {normalized}",
        )

    def test_capital_dotted_i_does_not_leave_a_combining_mark(self):
        """`"İ".casefold()` produces "i" + U+0307 -- visually an "i", not equal to one."""
        self.assertEqual(normalize("İstanbul"), "istanbul")
        self.assertNotIn("̇", normalize("İ"))

    def test_diacritics_are_folded_so_plain_typing_finds_them(self):
        self.assertEqual(normalize("Şirket"), "sirket")
        self.assertEqual(normalize("Günlük"), "gunluk")
        self.assertEqual(normalize("Öğrenci"), "ogrenci")
        self.assertEqual(normalize("Çanta"), "canta")

    def test_whitespace_is_collapsed_and_trimmed(self):
        self.assertEqual(normalize("  Kredi   Kartı  "), "kredi karti")

    def test_none_and_empty_are_safe(self):
        self.assertEqual(normalize(None), "")
        self.assertEqual(normalize(""), "")
        self.assertEqual(normalize("   "), "")


class MatchNamesTest(unittest.TestCase):
    def setUp(self):
        self.items = [
            {"name": "Nakit"},
            {"name": "Nakit Olmayan"},
            {"name": "Banka Hesabı"},
            {"name": "Şirket Kartı"},
            {"name": "Ísı Gideri"},
        ]

    def test_empty_query_matches_nothing(self):
        """Focusing must not dump the whole profile."""
        for query in ("", "   ", None):
            with self.subTest(query=query):
                self.assertEqual(match_names(query, self.items), [])

    def test_exact_match_outranks_prefix_and_substring(self):
        names = [item["name"] for item in match_names("Nakit", self.items)]
        self.assertEqual(names[0], "Nakit")
        self.assertIn("Nakit Olmayan", names)

    def test_prefix_outranks_substring(self):
        items = [{"name": "Olmayan Nakit"}, {"name": "Nakit Akışı"}]
        names = [item["name"] for item in match_names("nakit", items)]
        self.assertEqual(names, ["Nakit Akışı", "Olmayan Nakit"])

    def test_turkish_query_finds_differently_cased_record(self):
        """The user typed without dots, the record has dots -- it must still be found."""
        names = [item["name"] for item in match_names("isi", self.items)]
        self.assertIn("Ísı Gideri", names)

    def test_accentless_query_finds_accented_record(self):
        names = [item["name"] for item in match_names("sirket", self.items)]
        self.assertEqual(names, ["Şirket Kartı"])

    def test_no_match_returns_empty(self):
        self.assertEqual(match_names("kripto", self.items), [])

    def test_ties_keep_caller_ordering(self):
        """Tied scores must preserve the caller's order -- the result is deterministic."""
        items = [{"name": "A Kart"}, {"name": "B Kart"}, {"name": "C Kart"}]
        names = [item["name"] for item in match_names("kart", items)]
        self.assertEqual(names, ["A Kart", "B Kart", "C Kart"])

    def test_input_dicts_are_not_mutated(self):
        original = [{"name": "Nakit", "id": 7}]
        match_names("nakit", original)
        self.assertEqual(original, [{"name": "Nakit", "id": 7}])

    def test_extra_fields_survive_into_results(self):
        results = match_names("nakit", [{"name": "Nakit", "id": 7, "kind": ACCOUNT}])
        self.assertEqual(results[0]["id"], 7)
        self.assertEqual(results[0]["kind"], ACCOUNT)


class SearchAgainstDatabaseTest(unittest.TestCase):
    """`search()`'s real SQL and the merge order."""

    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT, "
            "account_type TEXT)"
        )
        conn.execute("CREATE TABLE categories (name TEXT, type TEXT)")


        conn.execute(
            "CREATE TABLE transactions (id INTEGER PRIMARY KEY, "
            "account_id INTEGER, description TEXT, category TEXT, "
            "transaction_date TEXT)"
        )
        conn.executemany(
            "INSERT INTO accounts (id, name, account_type) VALUES (?, ?, ?)",
            [(1, "Ziraat Vadesiz", "checking"),
             (2, "Şirket Kartı", "credit_card"),
             (3, "Isıtma Fonu", "checking")],
        )
        conn.executemany(
            "INSERT INTO categories (name, type) VALUES (?, ?)",
            [("Market", "expense"), ("Isınma", "expense"), ("Maaş", "income")],
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        os.unlink(self.db_path)

    def _search(self, query, **kwargs):
        from services import search_service

        conn = sqlite3.connect(self.db_path)

        class _Ctx:
            def __enter__(self_inner):
                return conn

            def __exit__(self_inner, *_exc):
                return False

        with mock.patch.object(
            search_service, "managed_connection", lambda: _Ctx()
        ):
            try:
                return search_service.search(query, **kwargs)
            finally:
                conn.close()

    def test_empty_query_never_touches_the_database(self):
        from services import search_service

        def _boom():
            raise AssertionError("boş sorgu için DB açılmamalı")

        with mock.patch.object(
            search_service, "managed_connection", _boom
        ):
            self.assertEqual(search_service.search("  "), [])

    def test_finds_account_and_category_in_one_list(self):
        results = self._search("isi")
        kinds = {item["kind"] for item in results}
        names = [item["name"] for item in results]
        self.assertEqual(kinds, {ACCOUNT, CATEGORY})
        self.assertIn("Isıtma Fonu", names)
        self.assertIn("Isınma", names)

    def test_accounts_come_before_categories(self):
        """The user's own account must not stay below a category that comes first
        alphabetically.
        """
        results = self._search("isi")
        first_category = next(
            index for index, item in enumerate(results)
            if item["kind"] == CATEGORY
        )
        last_account = max(
            index for index, item in enumerate(results)
            if item["kind"] == ACCOUNT
        )
        self.assertLess(last_account, first_category)

    def test_account_results_carry_id_and_type(self):
        results = self._search("ziraat")
        self.assertEqual(results[0]["id"], 1)
        self.assertEqual(results[0]["detail"], "checking")

    def test_category_results_carry_type_and_no_id(self):
        results = self._search("maas")
        self.assertEqual(results[0]["kind"], CATEGORY)
        self.assertEqual(results[0]["detail"], "income")
        self.assertIsNone(results[0]["id"])

    def test_limit_is_honoured(self):
        self.assertEqual(len(self._search("a", limit=2)), 2)

    def test_unmatched_query_returns_empty(self):
        self.assertEqual(self._search("kripto"), [])


class TransactionDescriptionSearchTest(unittest.TestCase):
    """Search over encrypted descriptions -- the window boundary included.

    This suite's real job is to pin that the boundary is REALLY applied. The
    window is the very security trade-off chosen instead of a write-time index:
    if it silently grows we end up decrypting all the data on every keystroke
    (1.1 s on 50,000 transactions); if it silently shrinks the user stops
    finding things they can find.
    """

    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "CREATE TABLE transactions (id INTEGER PRIMARY KEY, "
            "account_id INTEGER, description TEXT, category TEXT, "
            "transaction_date TEXT)"
        )
        self.conn = conn

    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_path)

    def _insert(self, rows):
        """`rows`: (id, plain_description, category, date)."""
        from utils.crypto import encrypt
        from database.db import SECRET_KEY

        self.conn.executemany(
            "INSERT INTO transactions (id, account_id, description, category,"
            " transaction_date) VALUES (?, 1, ?, ?, ?)",
            [(i, encrypt(text, SECRET_KEY), cat, date)
             for i, text, cat, date in rows],
        )
        self.conn.commit()

    def _search(self, query, **kwargs):
        from services import search_service

        conn = sqlite3.connect(self.db_path)

        class _Ctx:
            def __enter__(self_inner):
                return conn

            def __exit__(self_inner, *_exc):
                return False

        with mock.patch.object(
            search_service, "managed_connection", lambda: _Ctx()
        ):
            try:
                return search_service.search_transactions(query, **kwargs)
            finally:
                conn.close()

    def test_finds_a_description_and_decrypts_it_for_display(self):
        self._insert([(1, "Market alışverişi", "Market", "2026-08-01")])
        results = self._search("market")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "Market alışverişi")
        self.assertEqual(results[0]["kind"], "transaction")
        self.assertEqual(results[0]["detail"], "Market")

    def test_turkish_folding_applies_to_descriptions_too(self):
        self._insert([(1, "ISITMA faturası", "Fatura", "2026-08-01")])
        self.assertEqual(len(self._search("ısıtma")), 1)
        self.assertEqual(len(self._search("isitma")), 1)

    def test_empty_query_never_decrypts_anything(self):
        from services import search_service

        def _boom():
            raise AssertionError("boş sorgu için DB açılmamalı")

        with mock.patch.object(search_service, "managed_connection", _boom):
            self.assertEqual(search_service.search_transactions("  "), [])

    def test_window_bounds_how_far_back_the_search_reaches(self):
        """A row OUTSIDE the window must not be found -- the visible cost of the trade-off."""
        self._insert([
            (1, "eski kayit hedef", "X", "2020-01-01"),
            (2, "yeni kayit", "X", "2026-08-01"),
            (3, "yeni kayit", "X", "2026-08-02"),
        ])
        self.assertEqual(self._search("hedef", window=2), [])
        found = self._search("hedef", window=3)
        self.assertEqual(len(found), 1)

    def test_newest_rows_are_the_ones_inside_the_window(self):
        self._insert([
            (1, "alfa", "X", "2020-01-01"),
            (2, "beta", "X", "2026-08-02"),
        ])
        self.assertEqual(len(self._search("beta", window=1)), 1)
        self.assertEqual(self._search("alfa", window=1), [])

    def test_undecryptable_row_is_skipped_not_fatal(self):
        """One corrupt row must not make the whole box entirely unusable."""
        self._insert([(1, "market", "X", "2026-08-01")])
        self.conn.execute(
            "INSERT INTO transactions (id, account_id, description, category,"
            " transaction_date) VALUES (2, 1, 'AEADv1:bozuk', 'X', '2026-08-02')"
        )
        self.conn.commit()
        self.assertEqual(len(self._search("market")), 1)

    def test_limit_stops_the_decrypt_loop(self):
        self._insert([
            (i, f"market {i}", "X", f"2026-08-{i:02d}") for i in range(1, 6)
        ])
        self.assertEqual(len(self._search("market", limit=2)), 2)

    def test_missing_key_is_not_swallowed(self):
        """If the key is missing that is not a row problem; it must not be swallowed as empty."""
        from services import search_service
        from utils.errors import KeyUnavailableError

        self._insert([(1, "market", "X", "2026-08-01")])
        conn = sqlite3.connect(self.db_path)

        class _Ctx:
            def __enter__(self_inner):
                return conn

            def __exit__(self_inner, *_exc):
                return False

        def _no_key(*_a, **_k):
            raise KeyUnavailableError("anahtar yok")

        with mock.patch.object(
            search_service, "managed_connection", lambda: _Ctx()
        ), mock.patch("utils.crypto.decrypt", _no_key):
            with self.assertRaises(KeyUnavailableError):
                search_service.search_transactions("market")
        conn.close()


if __name__ == "__main__":
    unittest.main()
