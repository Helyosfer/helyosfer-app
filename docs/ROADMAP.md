# Roadmap

Where Helysofer stands and what is left before the first release. Nothing here
is a promise of a date; the order is the order of work.

## Where it stands

Working and covered by tests:

- Sign-in, first-run setup, password change, lock.
- Accounts and credit cards; adding, changing and removing transactions;
  pending transactions that apply themselves on their day.
- Debts and installments, recurring payments, savings goals.
- Portfolio with live prices for BIST shares, gold, currencies and crypto.
- Budget plan, calendar, calculators (loan with PDF schedule, deposit
  interest, compound growth, time to a goal), insights, what-if, past balance.
- Overview with search, upcoming items and a balance chart drawn from the
  dates of the transactions.
- Categories: the user's own can be added, renamed and removed.
- Encrypted backup and restore, CSV export and import.
- Dark and light themes.

Tried by hand in a real window on Windows as well as by the test suite. Not
yet tried by anyone but the author.

## Before the first release

1. **Try the Windows package on a computer without Python.** The package
   builds (`python scripts/build_windows.py --zip`), and on the build
   computer it was driven through setup and every section with real keyboard
   and mouse input, and fetched a price. It has not been started anywhere
   else. The installer script (`packaging/installer.iss`) has never been
   compiled.
2. **Run the test workflow on GitHub for the first time**, in a private
   repository, and fix what only shows up there.
3. **README with screenshots** and plain installation steps.
4. **Use it for real for a few weeks.** Items that settle themselves over
   time (pending transactions, recurring payments, installments) have tests
   but have not been watched across real days.
5. **Pick a file in the native dialogs by hand** once for each of backup,
   restore, CSV and PDF; the dialogs were opened but their choice was fed in
   by the test.

## Open decisions

- **Interface language.** The interface is English; built-in categories are
  stored in Turkish and shown in English. A Turkish interface is possible and
  not started.
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
- A category that is in use cannot be removed, only renamed. Built-in
  categories cannot be changed.
- A back-dated transaction moves only its own account's history back; other
  accounts join the chart on the day they were opened.
- Changing a repeating budget item changes that month only.
- Amount fields take two decimals; asset unit prices are left free for
  smaller values.

## Later

- Automatic contributions to a savings goal.
- Removing a category together with moving its records to another.
- Linux and macOS packages.
