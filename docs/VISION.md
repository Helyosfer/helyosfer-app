# Helysofer — product vision and scope

> See `docs/SECURITY_RELIABILITY_STATUS.md` for the current security and
> reliability summary.

## Product

Helysofer is a **local-first, offline-capable** personal-finance desktop
application. User data remains on the user's computer; the application does
not send financial records to an Helysofer server. Amount and description
fields are encrypted at rest.

The product covers accounts and credit cards, income and expense transactions,
budget planning, savings goals, portfolio tracking (stocks, precious metals,
foreign currencies, and cryptocurrencies), subscription and recurring-payment
detection, balance history, and scenario projections.

## Brand

The product name is **Helysofer**. Its icon is an “H” monogram.
`assets/icon_source.svg` is the source of truth; `icon.png` and `icon.ico` are
derived from it. The letterform is deliberately solid so it stays legible down
to 16 pixels (taskbar and tray size). Evaluate the icon using the real `.ico`
sizes, not only the large PNG.

## Release line and the meaning of “stable”

Helysofer is **pre-release (0.x)**. Nothing is published until the first
stable version. Stable means that supported packages, data integrity,
upgrades, backup, restore, and recovery are guarded by release tests and
verified acceptance paths. It does not remove the need for backups or turn the
application into a regulated financial service.

Every stable release must continue to meet these conditions:

- No known defect may corrupt user data, especially any defect that records a
  value different from the value entered by the user.
- The upgrade path must be measured: opening a previous-release profile in the
  new release must preserve its data.
- Backup and restore must be verified.
- Windows and Linux packages must be shown to install and launch successfully.

“Stable” does not mean banking or accounting certification. It describes
package and usage stability together with the verified data-integrity and
recovery scope.

## Platform scope

Windows is the primary target and Linux is supported. macOS is out of scope
until `.dmg`, signing, and notarization work is explicitly planned.

## Durable engineering decisions

- **Python 3.12 is the supported version** for development and packaging.
- **Run tests through `run_tests.py`.** Direct `python -m unittest` calls skip
  the sandboxed data directories the runner sets up.
- **The interface is PySide6 with Qt Quick.** Domain rules stay in services
  that can be tested without a window.
- **Financial reads fail closed.** An unreadable record is never counted as
  zero; its metric becomes invalid or partial. Showing no total is safer than
  showing a false total.

## Out of scope for now

Mobile applications, cloud synchronization, multi-user/shared budgets, open
banking integrations, and automatic receipt or invoice recognition.
