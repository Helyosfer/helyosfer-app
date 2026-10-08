# Architecture

This document describes the repository boundaries and the contracts that
changes should preserve.

## Repository map

```text
app/         Desktop interface: Qt Quick views (`app/qml`) and controllers
database/    SQLite schema, migrations, models, connections, and ledger
services/    Domain operations, pricing, insights, projections, and recovery
security/    Local authentication, password policy, and login throttling
utils/       Decimal, encryption, key storage, paths, logging, and formatting
ui/          English text catalog and chart localization
tests/       Unit, integration, security, and recovery tests
```

The desktop interface is PySide6 with Qt Quick. It is a thin layer: QML views
bind to controllers in `app/controllers.py`, which hold display-ready state
and forward user actions. Controllers never compute a financial figure and
never touch the database on the interface thread; domain rules live in
services with direct tests.

## Application flow

```text
Qt Quick views and events
        ↓
View models (no widgets, testable without a window)
        ↓
Domain and orchestration services
        ↓
Ledger operations and SQLite persistence
        ↓
Authenticated field encryption and OS-backed key storage
```

## Persistence and financial integrity

SQLite is the local system of record. Connection helpers and service-level
transactions protect operations that must update balances, financial records,
and ledger events together.

Important contracts include:

- balance changes and corresponding ledger events are atomic;
- due-transaction settlement uses transaction or savepoint boundaries;
- migrations are guarded and must preserve existing profiles;
- unreadable encrypted values that feed totals fail closed instead of becoming
  a confident zero;
- daily snapshots and ledger replay support historical balance views;
- financial-number boundaries use the shared Decimal policy where migration is
  complete, with remaining paths tracked as stabilization work;
- **savings goals have a single source of truth: SQLite.** They used to be
  displayed from `savings_goals.json` while the money lived in SQL, so the two
  could drift apart. Restore replaces `finance.db` whole, which rewinds
  `sqlite_sequence`, so a goal created after a restore could reclaim the
  numeric id a stale JSON card still pointed at — and a deposit made from that
  card landed on a different goal. Every goal now carries a permanent
  `goal_uid` (UUIDv4), every card operation is verified against it, and the
  service refuses fail-closed when the numeric id and the uid disagree. The
  numeric id remains as the internal key because `balance_events.entity_id`
  depends on it.

Financial-logic pull requests should prove these contracts with regression
tests covering success, rollback, and failure paths.

## Encryption and key storage

Sensitive fields are written with the versioned AEAD format implemented under
`utils/`. Key-provider selection uses Windows DPAPI, Linux Secret Service or
KWallet through `keyring`, or a permission-restricted local-file fallback when
no suitable OS key store is available.

Legacy CBC data remains read-only compatibility input and is migrated through a
backup-first transactional workflow. Key rotation, backup, and restore validate
key/database compatibility before replacing active material.

See [Key management](KEY_MANAGEMENT.md),
[Backup and recovery](BACKUP_RECOVERY.md), and
[Legacy encryption migration](ENCRYPTION_MIGRATION.md) for the detailed
security contracts.

## Background and external data

Asset-price work runs outside the main UI path. Provider fallbacks, caching,
and freshness metadata are service responsibilities; UI code should render the
result without hiding its source or age. External requests are limited to price
and selected visual metadata features.

Background work must report failures through the persistent logger and return
UI updates through `utils.ui_dispatch.run_on_main_thread`, where the interface
registers its own scheduler at startup. It must not touch the interface from a
worker thread.

## Text catalog and UI

`ui/` owns the English text catalog. Reusable business rules belong in
`services/`, not in translated strings or view callbacks.

UI changes should be checked in light and dark themes and at representative
display scaling.

### Text catalog contract

Legacy catalog source text remains the internal lookup key so existing stored
labels and migrations stay compatible. The public UI supports English only.
Two functions share one rule:

- `tr(text)` performs an **exact key match only**. Unknown text returns
  unchanged. It never rewrites fragments inside a longer string.
- `trf(template, **params)` translates the **template first**, then substitutes
  the parameters. Parameter values never pass through the translator again.

```python
# Wrong: user data reaches the catalog lookup.
_t(f"{payment['name']} aboneliği durduruldu.")
# Right: translate the template, then insert the user-owned name.
_tf("{name} aboneliği durduruldu.", name=payment["name"])
```

`tr()` used to fall back to replacing every known Turkish fragment it could
find inside the string. Because callers built the f-string before translating,
that fallback rewrote **user data**: an account named `Nakit` was displayed as
`Cash`, `Ayarlar` as `Settings`, and `Tür Seç: Hisse Senedi` came out as the
half-translated `Select Type: Stock Senedi`. The fallback is gone.

Classify every value before it reaches a sentence:

| Class | Examples | Rule |
|---|---|---|
| User data | account/card name, goal name, debt name, subscription name, transaction description, file path, `str(exc)` detail | **Never translated.** Passed as a `trf` parameter |
| Controlled value | amount, percentage, instalment count, day/month count, date, counter | Formatted by the caller, passed as a parameter |
| Enum / label | asset type, month name, account type label, category, frequency, status | Translated separately with `tr()` by exact key, then passed as a parameter |

Further rules:

- Number, date and currency formatting stays at the call site
  (`amount=f"{value:,.2f}"`); the translation layer never reformats.
- `trf` substitutes only `{name}` placeholders, in a single pass, without
  `str.format`. The reason is a deliberately narrow contract — no format
  specs, no attribute or index access inside a translatable string — plus a
  verified placeholder set and an order-independent result. It is **not**
  that `str.format` would re-interpret an inserted value: it does not
  (`"{x}".format(x="{test}") == "{test}"`).
- Placeholder **sets** must match between the legacy source key and English;
  the order is free, and English word order may differ
  (`"{name} hesabı eklendi."` → `"Account added: {name}"`).
- User data entering a `markup=True` widget goes through
  `ui.i18n.escape_markup` first.
- `tests/test_i18n_static_gate.py` enforces all of this: f-strings, string
  concatenation and `%`/`str.format()` results cannot be passed to a
  translation function , every template exists in the
  English dictionary with matching placeholders and renders in English,
  and user-supplied name fields cannot be handed to `tr()`.

## Test and CI boundaries

`python run_tests.py` is the primary suite entry point. It establishes the
sandboxed data directories before discovery and preserves test reporting and
exit status.

Discovery covers `tests/` only. `scripts/audit/` holds diagnostic and
adversarial reproduction tools that are deliberately outside the suite; CI
runs them as their own steps.

The Tests workflow runs the suite on Linux and Windows. Linux jobs also enforce
critical lint rules, the broad-exception baseline, and selected type checks.

Tests should be placed close to the contract they protect:

- services and database tests for financial state transitions;
- migration and recovery tests for rollback and compatibility;
- encryption tests for tamper, corruption, and unavailable-key behavior;
- view-model tests for workflow contracts.

## Change checklist

Before changing a boundary, answer these questions:

1. Can the rule move into a service that can be tested without a live window?
2. Does the operation update all related balances and ledger entries atomically?
3. Does a failure preserve the previous database and key state?
4. Are external data source, age, and failure behavior still visible?
5. Does the change need a migration or previous-release compatibility test?
6. Are English UI and packaged-runtime behavior covered where relevant?
