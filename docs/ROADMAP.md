# Roadmap

Where Helyosfer stands and what is left before the first release. Nothing here
is a promise of a date; the order is the order of work.

## Where it stands

Working and covered by tests:

- Sign-in, first-run setup, password change, lock.
- Accounts and credit cards; adding, changing (amount, date, category,
  account, direction) and removing transactions;
  pending transactions that apply themselves on their day.
- Debts and installments, recurring payments, savings goals with an optional
  monthly contribution.
- Portfolio with live prices for shares (BIST first, then other exchanges,
  converted into lira), gold, currencies and crypto.
- Budget plan, calendar, calculators (loan with PDF schedule, deposit
  interest, compound growth, time to a goal), insights, what-if, past balance.
- Overview with search, upcoming items and a balance chart drawn from the
  dates of the transactions.
- Categories: added, renamed and removed, the ones the application came
  with included; one that is in use hands its records to another.
- Encrypted backup and restore, CSV export and import.
- Dark and light themes; English and Turkish; motion that can be turned off.

Tried by hand in a real window on Windows as well as by the test suite, which
also runs on GitHub on Linux and Windows. Installed with its setup program on
a second computer, where it runs. Not yet tried by anyone but the author.

## Before the first release

1. **Try the Windows package on other computers.** Installed with the setup
   program on a second computer (Windows 11, another graphics card, 100%
   scaling against 125% here): the program's own check passed there, the
   window came up in under a second, everything it loaded came from its own
   folder or from Windows, and a price was fetched. Both computers run the
   same build of Windows 11 in English; Windows 10 and a computer set to
   Turkish have not been tried. On such a computer the interface starts in
   Turkish when either Windows is displayed in Turkish or Turkish is its
   regional format; that rule is tested, the computer is not. What the build
   itself checks: the package
   builds (`python scripts/build_windows.py --zip`), and on the build
   computer it was driven with real keyboard and mouse input through setup,
   every section, saving a transaction, and a CSV, a PDF, a backup and a
   restore through the Windows file dialogs. The build also starts it with
   nothing but Windows on the path and fails if it loads a single file from
   the build computer's Python or a C++ runtime from outside its own folder.
   The setup program
   (`--installer`) is tried by the build as well: it is installed without a
   question, the installed program is checked, and uninstalling has to
   remove everything it put in place. Installing over an older installation
   was tried by hand.
2. **Use it for real for a few weeks.** Items that settle themselves over
   time (pending transactions, recurring payments, installments, savings
   contributions) are played through months of days by the test suite, over
   a new year and a leap day, opened daily and opened now and then, and must
   leave the same books either way. They have not been watched across real
   days.

## Open decisions

- **Signing.** Decided against for now. Neither the program nor its setup
  is signed, so Windows warns before either runs for the first time.
- **Fonts.** The interface uses the fonts Windows ships. Bundling its own
  would make it look the same everywhere and add to the package.

## Known limits

- A record the application writes itself (a debt payment, a card payment,
  an asset trade) can be moved to another day and removed, which undoes its
  other half as well. Its amount and account are decided by that other half
  and cannot be changed; to correct them the record is removed and made
  again.
- The five categories the application files its own records under, or
  recognises a subscription by, cannot be renamed or removed. A category
  that was removed does not come back by itself; it is added again by name.
- A purchase in installments is charged to the card in full on its day.
  The card screen shows how many installments the statements have carried,
  worked out from the statement day; they are not separate records.
- A back-dated transaction moves back the history of its own account and of
  the accounts opened on the profile's first day. An account opened on a
  later day joins the chart on that day.
- Amount fields take two decimals; asset unit prices are left free for
  smaller values.
- Automatic payments, installments and savings contributions missed while
  the application was closed are recorded on the days they were due. A
  savings contribution waits while its account cannot cover it.
- The first automatic installment of a new debt, and the first automatic
  contribution of a new savings plan, is the next time its day comes round;
  one that has passed this month is not taken.
- The loan schedule PDF takes its font from Windows. Elsewhere it falls back
  to a font without Turkish letters.

## Later

- Linux and macOS packages.
