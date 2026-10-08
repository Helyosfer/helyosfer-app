"""The translation engine must not touch USER DATA.

THE MEASURED DEFECT: when `ui/i18n.py::tr()` found no exact match it replaced
the Turkish fragments from the translation dictionary inside the text one by
one. The callers, meanwhile, built the f-string FIRST and handed it to the
translation -- so the user's account name, goal name, subscription name and
transaction description all passed through the translation engine.

The output measured on HEAD:

    tr("Nakit eklendi", "en")                 -> "Cash added"
    tr("Ayarlar aboneliği durduruldu.", "en") -> "Settings subscription stopped."
    tr("Tür Seç: Hisse Senedi", "en")         -> "Select Type: Stock Senedi"

An account the user named "Nakit" showing as "Cash" in the English interface is
the application changing the user's own data. The third example also breaks the
sentence: it produces a half-translated hybrid.

THE NEW CONTRACT:
  * `tr()` does an exact key match ONLY; on unknown text it returns the source.
  * Dynamic sentences are built with `trf(template, **parameter)`: the template
    is translated FIRST and the parameters substituted AFTERWARDS.
  * Parameter values NEVER pass through `tr()` again.

The tests in this suite measure the defect FROM WHERE THE USER SEES IT: real
service records and the text the interface is handed.

"""

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


COLLIDING_NAMES = ("Nakit", "Ayarlar", "Gelir", "Maaş", "Banka", "Kripto")


class _Profile(unittest.TestCase):
    """A real SQLite profile plus an English interface language."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = os.path.join(self._tmp.name, "finance.db")
        self.key = os.urandom(32)

        self._db_patch = mock.patch("database.db.DB_NAME", self.db_path)
        self._db_patch.start()
        self.addCleanup(self._db_patch.stop)
        self._key_patch = mock.patch(
            "utils.crypto._get_aead_key", return_value=self.key
        )
        self._key_patch.start()
        self.addCleanup(self._key_patch.stop)

        from database.init_db import initialize_database
        from ui import i18n

        initialize_database()
        self._previous_language = i18n.get_language()
        self.addCleanup(i18n.set_language, self._previous_language)
        i18n.set_language("en")


class ExactMatchOnlyTest(unittest.TestCase):
    """`tr()` must not replace substrings -- there is NO "approximate translation"."""

    def setUp(self):
        from ui import i18n

        self._previous = i18n.get_language()
        self.addCleanup(i18n.set_language, self._previous)

    def test_a_sentence_built_around_a_dictionary_key_is_not_rewritten(self):
        from ui.i18n import tr

        self.assertEqual(tr("Nakit eklendi", "en"), "Nakit eklendi")

    def test_a_user_sentence_containing_a_key_is_left_alone(self):
        from ui.i18n import tr

        self.assertEqual(
            tr("Ayarlar aboneliği durduruldu.", "en"),
            "Ayarlar aboneliği durduruldu.",
        )

    def test_an_exact_key_still_translates(self):
        """The other half of the contract: an exact match must GO ON working."""
        from ui.i18n import tr

        self.assertEqual(tr("Nakit", "en"), "Cash")
        self.assertEqual(tr("Gelir", "en"), "Income")

    def test_unknown_text_falls_back_to_the_source(self):
        from ui.i18n import tr

        unknown = "Bu cümle sözlükte yok — 42 ₺"
        self.assertEqual(tr(unknown, "en"), unknown)

    def test_retired_locale_code_uses_the_english_catalog(self):
        from ui.i18n import tr

        for name in COLLIDING_NAMES:
            self.assertEqual(tr(name, "tr"), tr(name, "en"))


class TemplateFormattingTest(unittest.TestCase):
    """`trf()`: translate FIRST, then substitute the parameters."""

    def test_parameters_work_at_the_start_middle_and_end(self):
        from ui.i18n import trf

        self.assertEqual(
            trf("{name} aboneliği durduruldu.", language="tr", name="Ayarlar"),
            "Ayarlar subscription stopped.",
        )
        self.assertEqual(
            trf("Kalan: {count} Taksit", language="tr", count=3),
            "Remaining: 3 instalments",
        )
        self.assertEqual(
            trf("{a} · {b} · {c}", language="tr", a="1", b="2", c="3"),
            "1 · 2 · 3",
        )

    def test_the_same_parameter_can_appear_more_than_once(self):
        from ui.i18n import trf

        self.assertEqual(
            trf("{name} → {name}", language="tr", name="Nakit"),
            "Nakit → Nakit",
        )

    def test_user_values_are_inserted_verbatim(self):
        """The value goes through no processing: curly braces, %, emoji, line breaks."""
        from ui.i18n import trf

        hostile = "{test} %s %% {name} 🎉 çğışüö\nikinci satır"
        self.assertEqual(
            trf("Hesap: {name}", language="tr", name=hostile),
            f"Account: {hostile}",
        )

    def test_a_value_that_looks_like_a_placeholder_is_not_substituted(self):
        """A single pass: a `{name}` inside a value is not evaluated a second time.

        NOTE: `str.format` does not reinterpret the value it substitutes either
        (`"{x}".format(x="{test}") == "{test}"`). What is pinned here is not a
        fear of a crash but PREDICTABILITY: the result stays independent of
        parameter order.
        """
        from ui.i18n import trf

        self.assertEqual(
            trf("{name} eklendi", language="tr", name="{name}"),
            "{name} added",
        )

    def test_the_template_is_translated_before_substitution(self):
        from ui.i18n import trf

        self.assertEqual(
            trf("Tür Seç: {type}", language="en", type="Nakit"),
            "Select Type: Nakit",
        )

    def test_parameters_never_pass_through_the_translator(self):
        """A parameter is not translated EVEN IF it is in the dictionary -- it could be user data."""
        from ui.i18n import trf

        self.assertEqual(
            trf("Hesap eklendi: {name}", language="en", name="Nakit"),
            "Account added: Nakit",
        )


class AccountNameSurvivesTest(_Profile):
    """The user's account name must not change on its way into the card text.

    What this test measures is not a widget but the code path producing the
    TEXT written to the card.
    """


    def test_the_account_type_label_is_still_translated(self):
        """The other half of the contract: the TYPE LABEL is an enum and must be translated."""
        from services.account_service import AccountService
        from ui.i18n import tr

        AccountService.create_account("Nakit", "checking", initial_balance=1.0)
        account = AccountService.get_accounts()[0]
        self.assertEqual(account["type_label"], "Nakit / Vadesiz")
        self.assertEqual(tr(account["type_label"], "en"), "Cash / Checking")


class SubscriptionNameSurvivesTest(_Profile):
    def test_the_stop_message_keeps_the_subscription_name(self):
        """A subscription named `Ayarlar` must stay exactly so in the English sentence."""
        from ui.i18n import trf

        message = trf(
            "{name} aboneliği durduruldu.", language="en", name="Ayarlar"
        )
        self.assertIn("Ayarlar", message)
        self.assertNotIn("Settings", message)
        self.assertEqual(message, "Ayarlar subscription stopped.")

    def test_a_subscription_named_maas_is_not_translated(self):
        from ui.i18n import trf

        message = trf(
            "{name} bu ay için atlandı.", language="en", name="Maaş"
        )
        self.assertIn("Maaş", message)
        self.assertNotIn("Salary", message)


class SavingsGoalNameSurvivesTest(_Profile):

    def test_the_delete_dialog_title_keeps_the_goal_name(self):
        from ui.i18n import trf

        title = trf("Hedefi Sil: {name}", language="en", name="Gelir")
        self.assertIn("Gelir", title)
        self.assertNotIn("Income", title)


class DebtAndTransactionTextSurvivesTest(_Profile):
    def test_a_card_named_like_a_dictionary_phrase_is_untouched(self):
        from ui.i18n import trf

        title = trf("{name} Borç Ödeme", language="en", name="Kredi Kartı")
        self.assertIn("Kredi Kartı", title)

    def test_turkish_fragments_inside_a_description_are_untouched(self):
        from ui.i18n import trf

        description = "Nakit çekim — Ayarlar aboneliği, Gelir kaydı"
        line = trf("{description} iptal edildi.", language="en",
                   description=description)
        self.assertTrue(line.startswith(description), line)
        for english in ("Cash", "Settings", "Income"):
            self.assertNotIn(english, line)


class AssetTypeIsTranslatedAsAnEnumTest(unittest.TestCase):
    """The enum is translated SEPARATELY; the sentence comes from the template."""

    def test_a_known_asset_type_is_fully_english(self):
        from ui.i18n import tr, trf

        text = trf("Tür Seç: {type}", language="en", type=tr("Hisse", "en"))
        self.assertEqual(text, "Select Type: Stock")

    def test_the_reported_hybrid_is_gone(self):
        """The reported `Stock Senedi` hybrid can never be produced again."""
        from ui.i18n import tr, trf

        text = trf(
            "Tür Seç: {type}", language="en",
            type=tr("Hisse Senedi", "en"),
        )
        self.assertNotIn("Senedi", text)
        self.assertEqual(text, "Select Type: Stock")


if __name__ == "__main__":
    unittest.main()
