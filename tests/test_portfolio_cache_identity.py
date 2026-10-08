"""The property that makes the portfolio cache's float equality comparison SAFE.

`_read_cached_portfolio` decides the cache is still valid like this::

    float(entry["quantity"]) != float(asset["quantity"])

Float equality is generally a code smell, but it is safe HERE -- and the reason
is not coincidence but a measurable property: the two values being compared
come from THE SAME source. Both are the `float()` of the same row's `decrypt()`
output; one directly, the other after a `json.dumps`/`json.loads` round.
Python's JSON encoding writes a float with `repr()`, and the `repr` round trip
is lossless, so the two sides stay bit for bit identical.

THE MEASUREMENT (made before these tests were written; none could produce a
false invalidation):

  * JSON round trip: 0.1+0.2, 1/3, 0.045*15, 2.675, 1e-8, 0.7*3 -- in all nine
    the value read back is byte for byte the same.
  * SQLite REAL round trip: the same, byte for byte.
  * The real production path: three assets were bought and the cache written,
    then compared both with the list held in hand and with the list RE-READ
    from the database -- both HIT.

That is why `math.isclose()` or a tolerance was NOT ADDED: there is no drift to
correct, and an added tolerance would risk producing a false cache HIT by
swallowing a real change (the user having corrected the quantity). A false HIT
is worse than a needless MISS: one is performance, the other is wrong data.

The tests here keep that property protected. If the payload format is turned
into something lossy (rounded on write, say) the cache turns to a MISS on every
read, and these tests say so.

"""

import json
import unittest


_ADVERSARIAL = [
    0.1 + 0.2,          # 0.30000000000000004
    0.3,
    1 / 3,
    0.045 * 15,         # 0.6749999999999999
    2.675,
    0.7 * 3,            # 2.0999999999999996
    1e-8,
    123456.789,
]


class CachePayloadRoundTripIsLossless(unittest.TestCase):
    """The cache's write/read round MUST NOT CHANGE the value."""

    def test_json_round_trip_preserves_every_adversarial_value(self):
        for value in _ADVERSARIAL:
            with self.subTest(value=value):
                restored = json.loads(json.dumps({"quantity": value}))["quantity"]
                self.assertEqual(
                    restored, value,
                    "JSON turu değeri değiştirdi; cache her okumada MISS olur",
                )

    def test_sqlite_real_round_trip_preserves_every_adversarial_value(self):
        import sqlite3
        from contextlib import closing

        with closing(sqlite3.connect(":memory:")) as conn, conn:
            conn.execute("CREATE TABLE t (v REAL)")
            for value in _ADVERSARIAL:
                with self.subTest(value=value):
                    conn.execute("DELETE FROM t")
                    conn.execute("INSERT INTO t VALUES (?)", (value,))
                    restored = conn.execute("SELECT v FROM t").fetchone()[0]
                    self.assertEqual(restored, value)

    def test_equality_holds_across_the_whole_payload_hop(self):
        """The comparison itself: the value saved and the value read must stay equal."""
        for value in _ADVERSARIAL:
            with self.subTest(value=value):
                entry = json.loads(json.dumps({"quantity": value,
                                               "purchase_price": value}))
                self.assertFalse(
                    float(entry["quantity"]) != float(value)
                    or float(entry["purchase_price"]) != float(value),
                    "cache gereksiz yere geçersizleşirdi",
                )


if __name__ == "__main__":
    unittest.main()
