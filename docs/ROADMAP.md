# Roadmap

Where Helyosfer stands and what is left before the first release. Nothing here
is a promise of a date; the order is the order of work.

## Where it stands

Working and covered by tests:

- Sign-in, first-run setup, password change, lock.
- Accounts and credit cards; adding, changing and removing transactions;
  pending transactions that apply themselves on their day.
- Debts and installments, recurring payments, savings goals with an optional
  monthly contribution.
- Portfolio with live prices for BIST shares, gold, currencies and crypto.
- Budget plan, calendar, calculators (loan with PDF schedule, deposit
  interest, compound growth, time to a goal), insights, what-if, past balance.
- Overview with search, upcoming items and a balance chart drawn from the
  dates of the transactions.
- Categories: the user's own can be added, renamed and removed; one that is
  in use hands its records to another.
- Encrypted backup and restore, CSV export and import.
- Dark and light themes; English and Turkish.

Tried by hand in a real window on Windows as well as by the test suite, which
also runs on GitHub on Linux and Windows. Not yet tried by anyone but the
author.

## Before the first release

1. **Try the Windows package on a computer without Python.** The package
   builds (`python scripts/build_windows.py --zip`), and on the build
   computer it was driven with real keyboard and mouse input through setup,
   every section, saving a transaction, and a CSV, a PDF, a backup and a
   restore through the Windows file dialogs. It has not been started
   anywhere else. The installer script (`packaging/installer.iss`) has never been
   compiled.
2. **Use it for real for a few weeks.** Items that settle themselves over
   time (pending transactions, recurring payments, installments) have tests
   but have not been watched across real days.

## Open decisions

- **Foreign shares.** Only BIST prices are looked up. Others need a currency
  conversion as well as a second symbol lookup.
- **Installer or archive.** For now the package is a zip of its folder. An
  installer needs Inno Setup on the build computer.
- **Signing.** The executable is not signed, so Windows warns before it runs
  for the first time.
- **Fonts.** The interface uses the fonts Windows ships. Bundling its own
  would make it look the same everywhere and add to the package.

## Known limits

- A transaction cannot be moved to another account or turned from spending
  into income; it is removed and entered again.
- Records the application writes itself (loan installments, card payments,
  asset trades, installment purchases) cannot be changed from the
  transaction form.
- Built-in categories cannot be renamed or removed.
- A back-dated transaction moves back the history of its own account and of
  the accounts opened on the profile's first day. An account opened on a
  later day joins the chart on that day.
- Changing a repeating budget item changes that month only.
- Amount fields take two decimals; asset unit prices are left free for
  smaller values.
- The loan schedule PDF takes its font from Windows. Elsewhere it falls back
  to a font without Turkish letters.

## Later

- Linux and macOS packages.
