"""Recurring payment / subscription rules -- an interface-independent service layer.

The SINGLE record location for subscriptions is the `recurring_payments`
table. A second table named `subscriptions` was created at one point but was
never read from anywhere; keeping two sources of truth (one the UI reads, the
other empty) would produce silent inconsistency, so this service works only on
`recurring_payments`.

"""

import calendar
from datetime import date, datetime

from database.db import (
    SECRET_KEY, _advance_due_date, adjust_account_balance, get_connection,
)
from utils.crypto import decrypt, encrypt
from utils.errors import (
    DecryptionError,
    FinancialDataIntegrityError,
    KeyUnavailableError,
)
from utils.financial_decimal import fiat


SUBSCRIPTION_CATEGORY = "Dijital Abonelik"


SUBSCRIPTION_CATEGORIES = {
    "Dijital Abonelik",
    "Dijital Platformlar",
    "Yazılım & Lisans",
    "Eğitim & Kurs",
    "Spor & Sağlık (Abonelik)",
    "Bağış (Düzenli)",
}


KNOWN_BRANDS = [

    "netflix", "spotify", "youtube premium", "youtube music", "amazon prime",
    "prime video", "disney+", "disney plus", "blutv", "exxen", "mubi",
    "deezer", "tabii", "hbo max", "apple music", "apple tv", "apple one",
    "twitch", "paramount plus", "paramount+", "peacock", "crunchyroll",
    "tidal", "soundcloud go", "soundcloud",
    # Books / audiobooks
    "storytel", "audible", "kindle unlimited", "blinkist",

    "adobe", "creative cloud", "microsoft 365", "office 365", "icloud",
    "google one", "dropbox", "notion", "figma", "canva", "jetbrains",
    "github", "1password", "lastpass", "nordvpn", "expressvpn",
    "proton vpn", "protonvpn", "proton mail", "protonmail", "proton pass",
    "protonpass", "proton drive", "protondrive", "proton calendar",
    "protoncalendar", "proton unlimited", "proton duo", "proton family",
    "proton visionary", "proton",

    "türk telekom", "turk telekom", "türktelekom", "turktelekom", "ttnet",
    "vodafone türkiye", "vodafone turkey", "vodafone net", "vodafone",
    "turkcell superonline", "superonline", "turkcell",
    "chatgpt", "openai", "claude", "anthropic", "gemini advanced",
    "slack", "zoom", "linkedin premium", "meta verified",

    "udemy", "coursera", "duolingo", "skillshare",

    "macfit", "club sporium", "clubsporium", "sporium", "strava",
    "headspace", "spotify premium",

    "patreon", "wikipedia",
    # Oyun
    "playstation plus", "ps plus", "xbox game pass", "game pass",
    "nintendo online", "ea play", "ubisoft+", "ubisoft plus",
]


def apply_category_trigger(category, recurring_switch) -> bool:
    """Turns the switch on once if a digital subscription category was selected.

    No permanent binding is installed afterwards; the user can turn the switch
    back off manually.
    """
    should_enable = str(category).strip() == SUBSCRIPTION_CATEGORY
    if should_enable:
        recurring_switch.active = True
    return should_enable


def next_due_for_recurrence(
        from_date: str | date, frequency: str, recurrence_day: int) -> str:
    """Returns the next period, pinned to the selected day of the month."""
    day = int(recurrence_day)
    if not 1 <= day <= 31:
        raise ValueError("Tekrarlama günü 1 ile 31 arasında olmalıdır.")
    source = from_date if isinstance(from_date, date) else date.fromisoformat(from_date)
    advanced = date.fromisoformat(_advance_due_date(source.isoformat(), frequency))
    valid_day = min(day, calendar.monthrange(advanced.year, advanced.month)[1])
    return advanced.replace(day=valid_day).isoformat()


def initial_recurring_income_date(
        reference_date: date, recurrence_day: int, include_current_month: bool
) -> date | None:
    """Determines the date of the first salary record according to the user's choice.

    If the selected day of the month has passed, "include this month" writes
    it to today; if it has not arrived yet, a pending transaction is scheduled
    for that day. Choices of 29-31 are clamped to the last day of the month in
    short months. A month that is not included produces no transaction at
    all.
    """
    if not include_current_month:
        return None
    day = int(recurrence_day)
    if not 1 <= day <= 31:
        raise ValueError("Tekrarlama günü 1 ile 31 arasında olmalıdır.")
    valid_day = min(
        day,
        calendar.monthrange(reference_date.year, reference_date.month)[1],
    )
    occurrence = reference_date.replace(day=valid_day)
    return occurrence if occurrence > reference_date else reference_date


def looks_like_subscription(category, description="", is_credit_card=False):
    """Does the transaction look like a recurring subscription?

    Three signals are looked for (any one is enough):
      1. The category is explicitly one of the subscription categories.
      2. A recognised brand name appears in the description (KNOWN_BRANDS).
      3. The spend went through a credit card and its category is a
         subscription.

    The credit-card signal is NOT enough ON ITS OWN: if every supermarket run
    on the card counted as a subscription the radar would fill with rubbish.
    The card only reinforces the category/brand signal.
    """
    normalized_category = str(category or "").strip()
    if normalized_category in SUBSCRIPTION_CATEGORIES:
        return True

    if KNOWN_BRANDS:
        haystack = f"{description or ''} {normalized_category}".casefold()
        for brand in KNOWN_BRANDS:
            if str(brand).casefold() in haystack:
                return True


    return False


def register_subscription_from_transaction(
        account_id, amount, category, description, frequency="monthly",
        recurrence_day=None, transaction_date=None, is_credit_card=False):
    """Writes a transaction that looks like a subscription onto the `recurring_payments` radar.

    Writing to the transaction ledger (transactions) is THE CALLER's job; this
    function only adds the "My Active Subscriptions" record. That way one
    transaction both appears as a normal expense and lands on the radar.

    If an active subscription with the same name exists it does nothing
    (idempotent) -- even if the user enters the same subscription by hand every
    month, the radar keeps a single record.

    Returns the id of the new row if it was recorded, None if it was
    skipped.
    """
    from database.db import (
        get_active_recurring_payments, has_active_recurring_payment,
        insert_recurring_payment,
    )


    if not is_credit_card:
        return None
    if not looks_like_subscription(category, description, is_credit_card):
        return None

    name = (description or category or "").strip()
    if not name:
        return None
    if has_active_recurring_payment(name):
        return None

    reference = (
        date.fromisoformat(str(transaction_date)[:10])
        if transaction_date else date.today()
    )
    day = int(recurrence_day or reference.day)
    next_due = next_due_for_recurrence(reference, frequency, day)

    insert_recurring_payment(
        name, float(amount), category, frequency, next_due,
        auto_deduct=0, account_id=account_id, recurrence_day=day,
    )
    match = [
        payment for payment in get_active_recurring_payments()
        if payment["name"] == name
    ]
    return match[0]["id"] if match else None


def _get_payment(cursor, payment_id):
    """Reads the subscription as a raw row (name/amount still encrypted)."""
    cursor.execute(
        "SELECT * FROM recurring_payments WHERE id = ?", (int(payment_id),)
    )
    return cursor.fetchone()


def _plain_name(raw):
    try:
        return decrypt(str(raw), SECRET_KEY) or ""
    except KeyUnavailableError:


        raise
    except (DecryptionError, ValueError, TypeError):
        from utils.logging_config import get_logger
        get_logger().exception(
            "[VERİ BÜTÜNLÜĞÜ] recurring_payments adı çözülemedi")
        return ""


def _plain_amount(raw):
    try:
        return float(decrypt(str(raw), SECRET_KEY))
    except KeyUnavailableError:
        raise
    except (DecryptionError, ValueError, TypeError):
        from utils.logging_config import get_logger
        get_logger().exception("[VERİ BÜTÜNLÜĞÜ] recurring_payments tutarı çözülemedi")
        return 0.0


def update_subscription_amount(payment_id, new_amount):
    """Changes the subscription's current fee (the price-rise case).

    A user should not have to delete and recreate a subscription when the
    price goes up; deleting and recreating would also reset the due history
    and the `next_due_date` alignment. Only the amount is updated; the due
    date is untouched.
    """


    try:
        amount = fiat(new_amount)
    except (TypeError, ValueError) as exc:
        raise ValueError("Abonelik ücreti geçerli bir sayı olmalıdır.") from exc
    if amount <= 0:
        raise ValueError("Abonelik ücreti 0'dan büyük olmalıdır.")

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE recurring_payments SET amount = ?"
            " WHERE id = ? AND is_active = 1",
            (encrypt(str(amount), SECRET_KEY), int(payment_id)),
        )
        updated = cursor.rowcount
        conn.commit()
    finally:
        conn.close()
    return updated > 0


def skip_next_occurrence(payment_id):
    """Skips just the next charge WITHOUT cancelling the subscription.

    The spec's "delete for this month only" option: the record stays active
    and the due date moves forward one period. The user can skip a single
    period without losing the following months. Returns the new due date, or
    None if there is no such subscription.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        row = _get_payment(cursor, payment_id)
        if row is None or not row["is_active"]:
            return None
        new_due = next_due_for_recurrence(
            row["next_due_date"],
            row["frequency"],
            row["recurrence_day"] or int(str(row["next_due_date"])[8:10]),
        )
        cursor.execute(
            "UPDATE recurring_payments SET next_due_date = ? WHERE id = ?",
            (new_due, int(payment_id)),
        )
        conn.commit()
    finally:
        conn.close()
    return new_due


def cancel_subscription(payment_id):
    """Stops the subscription permanently (this month and every month after).

    The row is NOT DELETED; `is_active` is set to 0: past transactions and the
    subscription radar's "this is already tracked" check both rely on the
    record existing, and a physical delete would turn the history back into a
    "candidate to be discovered".
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE recurring_payments SET is_active = 0 WHERE id = ?",
            (int(payment_id),),
        )
        updated = cursor.rowcount
        conn.commit()
    finally:
        conn.close()
    return updated > 0


def find_current_period_charge(payment_id, today=None):
    """Finds the automatic charge taken for this subscription this month.

    `process_due_recurring_payment` writes the description ENCRYPTED as
    `"{name} (Otomatik)"`; the description therefore cannot be searched in
    SQL, so candidate rows are fetched and decrypted in Python (the general
    pattern in this project). Returns {'id', 'amount', 'date'} if found,
    otherwise None.
    """
    reference = date.fromisoformat(today) if today else date.today()

    conn = get_connection()
    try:
        cursor = conn.cursor()
        row = _get_payment(cursor, payment_id)
        if row is None:
            return None
        name = _plain_name(row["name"])
        expected_description = f"{name} (Otomatik)"

        cursor.execute(
            "SELECT id, amount, description, transaction_date FROM transactions"
            " WHERE account_id = ? AND type = 'expense'"
            "   AND COALESCE(category, '') = COALESCE(?, '')"
            "   AND strftime('%Y-%m', transaction_date) = ?"
            " ORDER BY id DESC",
            (row["account_id"], row["category"], reference.strftime("%Y-%m")),
        )
        candidates = cursor.fetchall()
    finally:
        conn.close()

    for candidate in candidates:
        try:
            description = decrypt(str(candidate["description"]), SECRET_KEY)
        except KeyUnavailableError:
            raise
        except (DecryptionError, ValueError, TypeError):


            from utils.logging_config import get_logger
            get_logger().exception(
                "[VERİ BÜTÜNLÜĞÜ] aday işlem id=%s açıklaması çözülemedi",
                candidate["id"] if "id" in candidate.keys() else "?")
            continue
        if description == expected_description:
            return {
                "id": candidate["id"],
                "amount": _plain_amount(candidate["amount"]),
                "date": candidate["transaction_date"],
            }
    return None


def refund_current_period_charge(payment_id, today=None):
    """Adds this month's subscription fee back to the balance.

    When the user has actually cancelled the subscription and forgotten to
    delete it from the application, the money has been deducted for nothing.
    The original expense row is NOT DELETED; a compensating income transaction
    is written (double-entry logic) -- we reverse rather than rewrite history,
    so the ledger and the balance stay consistent.

    Returns the amount refunded, or 0.0 if there was no charge this month.
    Raises `FinancialDataIntegrityError` if the STORED amount of the charge to
    be refunded cannot be read or is not a valid monetary value -- "no charge
    this month" and "there is a charge but its amount is corrupt" are not
    collapsed into the same outcome.
    """
    charge = find_current_period_charge(payment_id, today=today)
    if not charge:
        return 0.0


    try:
        amount_decimal = fiat(charge["amount"])
    except (TypeError, ValueError) as exc:
        raise FinancialDataIntegrityError(
            "transactions", charge["id"], "amount"
        ) from exc
    if amount_decimal <= 0:
        raise FinancialDataIntegrityError(
            "transactions", charge["id"], "amount"
        )

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute(
            "INSERT OR IGNORE INTO recurring_operation_markers "
            "(recurring_payment_id, due_date, operation_type) VALUES (?, ?, 'refund')",
            (payment_id, str(charge["id"])),
        )
        if cursor.rowcount == 0:
            conn.rollback()
            return 0.0
        row = _get_payment(cursor, payment_id)
        if row is None:
            return 0.0
        name = _plain_name(row["name"])
        amount = float(amount_decimal)

        cursor.execute(
            "INSERT INTO transactions"
            " (account_id, amount, type, category, description,"
            "  transaction_date, status, execution_date)"
            " VALUES (?, ?, 'income', ?, ?, ?, 'completed', ?)",
            (
                row["account_id"],
                encrypt(str(amount), SECRET_KEY),
                row["category"],
                encrypt(f"{name} aboneliği iadesi", SECRET_KEY),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )


        transaction_id = cursor.lastrowid

        adjust_account_balance(
            cursor, row["account_id"], "income", amount,
            ref_id=transaction_id, source="subscription_refund",
        )
        conn.commit()
    finally:
        conn.close()
    return amount
