"""The exception policy of the legacy raw card number cleanup.

`database/init_db.py` runs a one-off cleanup at every startup: the mask and the
card network are derived from the RAW PAN older versions encrypted into the
`accounts.card_number_full` column, and then the raw columns are nulled.

These tests pin that step's exception policy, because the policy has to
distinguish two different FAULTS:

    corrupt / unverifiable ciphertext   ->   CONTINUE the cleanup
    the encryption key is unreachable   ->   STOP, do not delete the data

The distinction is security-motivated. A corrupt record can never be decrypted
again; leaving the raw PAN on disk for its sake preserves the real risk when
the only thing lost is display information. An unreachable key, on the other
hand, is TEMPORARY -- the same ciphertext decrypts fine once the key is back, so
deleting now would permanently lose every card's mask.

"""
import os
import sqlite3
import tempfile
import unittest
from unittest import mock


class LegacyCardCleanupPolicyTest(unittest.TestCase):

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._patcher = mock.patch("database.db.DB_NAME", self.db_path)
        self._patcher.start()
        self.addCleanup(self._patcher.stop)
        self.addCleanup(lambda: os.path.exists(self.db_path) and os.unlink(self.db_path))

        from database.init_db import initialize_database
        initialize_database()

    def _seed(self, stored_pan):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO accounts(name, type, balance, account_type,"
                " card_number_full) VALUES('Eski Kart','credit',0,"
                "'credit_card',?)",
                (stored_pan,),
            )
            conn.commit()
        finally:
            conn.close()

    def _card(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            return dict(conn.execute(
                "SELECT card_number_full, masked_number, network_logo"
                " FROM accounts WHERE name='Eski Kart'").fetchone())
        finally:
            conn.close()

    def _encrypted_pan(self, pan="4532015112830366"):
        from database.db import SECRET_KEY
        from utils.crypto import encrypt
        return encrypt(pan, SECRET_KEY)

    # ─── Mutlu yol ───────────────────────────────────────────────────────────

    def test_readable_pan_is_reduced_to_mask_and_network(self):
        from database.init_db import initialize_database

        self._seed(self._encrypted_pan())
        initialize_database()

        card = self._card()
        self.assertIsNone(card["card_number_full"], "ham PAN diskte kaldı")
        self.assertEqual(card["masked_number"], "**** **** **** 0366")
        self.assertEqual(card["network_logo"], "assets/visa.png")

    # ─── Corrupt ciphertext: continue ────────────────────────────────────────

    def test_corrupt_ciphertext_does_not_stop_the_cleanup(self):
        """An undecryptable record must NOT CRASH startup, and no raw PAN may be left."""
        from database.init_db import initialize_database

        self._seed("bu-base64-bile-degil!!!")
        initialize_database()

        card = self._card()
        self.assertIsNone(card["card_number_full"])
        self.assertIsNone(card["masked_number"])

    def test_integrity_failure_does_not_stop_the_cleanup(self):
        """A tampered AEAD envelope (IntegrityVerificationError) is cleaned up too."""
        from database.init_db import initialize_database

        blob = self._encrypted_pan()
        tampered = blob[:-6] + ("A" if blob[-6] != "A" else "B") + blob[-5:]
        self._seed(tampered)
        initialize_database()

        card = self._card()
        self.assertIsNone(card["card_number_full"])
        self.assertIsNone(card["masked_number"])

    def test_one_unreadable_row_does_not_block_a_readable_one(self):
        from database.init_db import initialize_database

        self._seed("bu-base64-bile-degil!!!")
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO accounts(name, type, balance, account_type,"
                " card_number_full) VALUES('Sağlam Kart','credit',0,"
                "'credit_card',?)",
                (self._encrypted_pan(),),
            )
            conn.commit()
        finally:
            conn.close()

        initialize_database()

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = {
                row["name"]: dict(row) for row in conn.execute(
                    "SELECT name, card_number_full, masked_number FROM accounts")
            }
        finally:
            conn.close()
        self.assertIsNone(rows["Eski Kart"]["card_number_full"])
        self.assertIsNone(rows["Sağlam Kart"]["card_number_full"])
        self.assertEqual(rows["Sağlam Kart"]["masked_number"],
                         "**** **** **** 0366")

    # ─── No key: STOP ─────────────────────────────────────────────────

    def test_missing_key_aborts_without_destroying_the_ciphertext(self):
        """With the key unreachable the cleanup is NOT DONE and can complete later."""
        from database.init_db import initialize_database
        from utils.errors import KeyUnavailableError

        self._seed(self._encrypted_pan())
        with mock.patch("utils.crypto._get_aead_key",
                        side_effect=KeyUnavailableError("anahtar yok")):
            with self.assertRaises(KeyUnavailableError):
                initialize_database()

        card = self._card()
        self.assertIsNotNone(
            card["card_number_full"],
            "anahtar geçici olarak yokken şifreli veri silindi",
        )


        initialize_database()
        card = self._card()
        self.assertIsNone(card["card_number_full"])
        self.assertEqual(card["masked_number"], "**** **** **** 0366")


if __name__ == "__main__":
    unittest.main()
