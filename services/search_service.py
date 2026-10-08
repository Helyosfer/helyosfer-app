"""Search over account and category names.

THE SCOPE IS DELIBERATELY NARROW. Only `accounts.name` and `categories.name`
are searched -- both plain text (see the note at the top of
account_service.py: the account name is not encrypted). Transaction
descriptions are OUT OF SCOPE, and that is not an omission but a deliberate
boundary: those fields are held AES-encrypted, so searching them means
decrypting a working set into memory instead of pushing the filter down to
SQL. On a profile with 50,000 transactions, decrypting everything takes 1.1 s
(docs/performance/benchmark-results-windows.json). That cost is deliberately not taken.

TURKISH FOLDING IS THIS FILE'S REAL JOB. A plain `.casefold()` gives the WRONG result in Turkish: `"I".casefold()` ->
`"i"` but `"ı".casefold()` -> `"ı"`, so a user typing "ISI" cannot find the
record "ısı". `"İ".casefold()` in turn produces `"i"` + U+0307 (a combining
dot) -- visually an "i" but not equal to one. `normalize()` brings all three to
the same place.

"""

import unicodedata

from database.db import managed_connection


DEFAULT_LIMIT = 20

ACCOUNT = "account"
CATEGORY = "category"
TRANSACTION = "transaction"


DEFAULT_DESCRIPTION_WINDOW = 500


def normalize(text):
    """Reduces text to a single comparable form for searching.

    THE ORDER MATTERS and the steps are:

    1. `casefold()` -- drops the upper/lower case distinction.
    2. NFKD -- splits composed letters into base plus combining mark
       (`ş` -> `s` + cedilla, `ğ` -> `g` + breve, `ö` -> `o` + diaeresis).
    3. Drop the combining marks -- so a user typing without accents finds it
       too: "sirket" -> "Şirket", "gunluk" -> "Günlük".
    4. `ı` -> `i` -- NFKD does not decompose this, because dotless i is a
       separate letter in Unicode rather than a composition. Without this line
       step 2 does not resolve the ı/i distinction, and this is where Turkish
       search breaks most often.

    `is_read_only_asset_account` (ui/components.py) uses the same chain;
    deliberately identical, because normalising differently in two places
    produces silent inconsistency.
    """
    folded = unicodedata.normalize("NFKD", str(text or "").casefold())
    stripped = "".join(
        char for char in folded if not unicodedata.combining(char)
    )
    return " ".join(stripped.replace("ı", "i").split())


def matches(query, *candidates):
    """Does the query appear in ANY of the given fields.

    For callers that FILTER a list (the budget category picker, the BIST and
    crypto pickers). Unlike `search()`, AN EMPTY QUERY returns `True`: there,
    an empty query meant "show nothing"; here it means "no filtering, show
    everything". The two opposite defaults are in separate functions on
    purpose; adding a flag to a single function would make it unreadable at
    the call site which behaviour applied.
    """
    needle = normalize(query)
    if not needle:
        return True
    return any(needle in normalize(candidate) for candidate in candidates)


def _rank(needle, haystack):
    """Returns how good the match is, or None if there is no match.

    0 = exact, 1 = prefix match, 2 = contained. Lower comes first. So that
    when the user types "Nakit" the result "Nakit" appears above "Nakit
    Olmayan"; a pure containment check did not give that order.
    """
    if not needle:
        return None
    if haystack == needle:
        return 0
    if haystack.startswith(needle):
        return 1
    if needle in haystack:
        return 2
    return None


def match_names(query, items):
    """Pure matching -- it does not touch the database, so it is directly testable.

    `items`: a sequence of `{"name": ..., ...}` dictionaries. The input
    dictionaries are NOT MODIFIED; copies of the matches are returned.
    """
    needle = normalize(query)
    if not needle:
        return []
    scored = []
    for position, item in enumerate(items):
        rank = _rank(needle, normalize(item.get("name")))
        if rank is None:
            continue


        scored.append((rank, position, dict(item)))
    scored.sort(key=lambda entry: (entry[0], entry[1]))
    return [item for _rank_value, _position, item in scored]


def search_transactions(query, limit=DEFAULT_LIMIT,
                        window=DEFAULT_DESCRIPTION_WINDOW):
    """Searches the DESCRIPTION of the most recent `window` transactions.

    Because the description is encrypted, matching happens in Python; ordering
    and windowing happen in SQL over a plain column (`transaction_date`). For
    why the window exists and what it costs, see
    `DEFAULT_DESCRIPTION_WINDOW`.

    A single row that cannot be decrypted does not drop the search; it is
    skipped -- one broken or old record must not render the box entirely
    unusable. But if the key itself is missing, that is not a row problem and
    `KeyUnavailableError` propagates upward; the same distinction as in
    `get_pending_transactions`.
    """
    needle = normalize(query)
    if not needle:
        return []

    from utils.crypto import decrypt
    from utils.errors import DecryptionError, KeyUnavailableError
    from database.db import SECRET_KEY

    with managed_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, account_id, description, category, transaction_date "
            "FROM transactions WHERE description IS NOT NULL "
            "ORDER BY date(transaction_date) DESC, id DESC LIMIT ?",
            (int(window),),
        )
        rows = cursor.fetchall()

    results = []
    for row in rows:
        try:
            description = decrypt(str(row[2]), SECRET_KEY)
        except KeyUnavailableError:
            raise
        except (DecryptionError, ValueError, TypeError):
            continue
        if _rank(needle, normalize(description)) is None:
            continue
        results.append({
            "kind": TRANSACTION,
            "id": row[0],
            "name": description,
            "detail": row[3] or "",
            "date": row[4],
        })


        if len(results) >= limit:
            break
    return results


def search(query, limit=DEFAULT_LIMIT):
    """Searches account and category names and returns a single ordered list.

    An empty or whitespace-only query returns an EMPTY list -- "list
    everything" behaviour is deliberately absent: focusing the search box must
    not dump the whole profile.
    """
    needle = normalize(query)
    if not needle:
        return []

    with managed_connection() as conn:
        cursor = conn.cursor()


        cursor.execute(
            "SELECT id, name, account_type FROM accounts "
            "ORDER BY CASE WHEN account_type = 'credit_card' THEN 1 ELSE 0 END, id"
        )
        accounts = [
            {"kind": ACCOUNT, "id": row[0], "name": row[1], "detail": row[2]}
            for row in cursor.fetchall()
        ]
        cursor.execute(
            "SELECT name, type FROM categories ORDER BY name"
        )
        categories = [
            {"kind": CATEGORY, "id": None, "name": row[0], "detail": row[1]}
            for row in cursor.fetchall()
        ]


    results = match_names(query, accounts) + match_names(query, categories)
    if len(results) < limit:
        results += search_transactions(query, limit=limit - len(results))
    return results[:limit]
