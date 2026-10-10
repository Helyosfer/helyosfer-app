<div align="center">

<img src="assets/icon.png" width="96" alt="Helyosfer">

# Helyosfer

A desktop app for personal finance. Your records stay on your own computer.

**English** · [Türkçe](README.tr.md)

[![Tests](https://github.com/Helyosfer/helyosfer-app/actions/workflows/tests.yml/badge.svg)](https://github.com/Helyosfer/helyosfer-app/actions/workflows/tests.yml)
![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-5646d4)
![Python 3.12](https://img.shields.io/badge/python-3.12-5646d4)
![Windows 10 or later](https://img.shields.io/badge/platform-Windows%2010%2B-5646d4)

</div>

![The overview screen](docs/images/en/overview.png)

I wrote Helyosfer to see my own accounts, card debt and savings in one place.
It does not connect to a bank and does not ask you to sign up for anything;
it holds what you type in. The data sits in an encrypted file on your computer,
and the only thing it goes online for is the price of shares, gold and
currencies.

> [!NOTE]
> This is the first release (0.1.0). So far I am the only one who has used it,
> and not for long. I installed it on two computers and the tests pass, but
> there are bound to be things I missed. Take a backup now and then
> (Settings → Create backup) if the records matter to you. If something goes
> wrong, [open an issue](https://github.com/Helyosfer/helyosfer-app/issues).

## What it is for

- **Accounts and credit cards.** You add your accounts and cards and enter
  income and spending. A card shows its limit, its statement day and how far
  along each purchase in installments is.
- **Debts.** It keeps track of loans and other debts paid in monthly
  installments. You can pay an installment by hand or have it taken from an
  account of your choice every month.
- **Subscriptions and regular payments.** Rent, bills, a salary: anything that
  repeats, from weekly to yearly.
- **Savings goals.** You set a target and put money aside for it, with a fixed
  amount moved every month if you like.
- **Investments.** Shares, gold, currencies and crypto. It fetches the current
  price and shows what you hold in lira, with the profit or loss.
- **Budget and other tools.** A monthly budget plan, a calendar, loan and
  deposit calculators, a summary of your spending, and an answer to "how much
  did I have on the 15th of last month".

Amounts are in Turkish lira. The interface is in English and Turkish, with a
dark and a light theme.

## Screenshots

| Cards and accounts | Investments |
| --- | --- |
| ![Accounts and a credit card](docs/images/en/accounts.png) | ![Holdings with their current price and profit or loss](docs/images/en/portfolio.png) |
| **Budget plan** | **Summary and forecast** |
| ![Spending against the monthly plan](docs/images/en/budget.png) | ![A financial-health score and a month-end forecast](docs/images/en/insights.png) |
| **Savings goals** | **Light theme** |
| ![Two savings goals](docs/images/en/savings.png) | ![The overview in the light theme](docs/images/en/overview-light.png) |

## A few things worth knowing

You can enter records for the past. Type in a January expense today and the
chart is redrawn from January; the balance history goes by the date of the
transaction, not the day you entered it.

You do not have to open it every day. Leave it closed for a month, and the
automatic payments, installments and savings transfers you missed are recorded
with the dates they were due.

Anything you got wrong can be changed or deleted. Delete a debt payment and the
installment goes back to the debt; delete the sale of an asset and the asset is
back in the portfolio.

If a record cannot be read, the app does not count it as zero and show a wrong
total. It shows no total and tells you why.

## Your data

- Everything is kept on your computer, in a database in your Windows user
  folder. Nothing is sent to a server.
- Amounts and descriptions are encrypted on disk (AES-256-GCM). Windows
  protects the encryption key (DPAPI).
- The app opens with a password. The password itself is not stored, only its
  hash (Argon2id). If you forget it, there is no way to recover it.
- A backup is a single file protected by a password of its own. To move to
  another computer, restore the backup there.
- It collects no usage data and shows no ads.

More detail in [key management](docs/KEY_MANAGEMENT.md),
[backup and recovery](docs/BACKUP_RECOVERY.md) and [SECURITY.md](SECURITY.md).

## Installing

Download `Helyosfer-<version>-setup.exe` from the
[latest release](https://github.com/Helyosfer/helyosfer-app/releases/latest)
and run it. It does not ask for administrator rights, and the computer does not
need Python or anything else installed. Windows 10 or later, 64-bit.

The file is not signed, so Windows warns about an unknown publisher the first
time. Click **More info**, then **Run anyway**. The SHA-256 of each file is on
the release page if you want to check your download.

If you would rather not install it, unpack the zip from the same page into a
folder and start `Helyosfer.exe`; keep the `_internal` folder next to it.

On first start you choose a password and add your first account. It opens in
Turkish on a Turkish Windows and in English otherwise; you can change the
language in Settings.

Removing or updating the program does not touch your records. They are kept in
a separate folder.

## Running from source

You need Python 3.12.

```bash
python -m pip install -r requirements-runtime.txt
```

```bash
python -m app
```

To build the package yourself:

```bash
python -m pip install pyinstaller
```

```bash
python scripts/build_windows.py --zip
```

That writes the zip under `dist/`. The setup program needs
[Inno Setup 6](https://jrsoftware.org/isinfo.php) installed:

```bash
python scripts/build_windows.py --installer
```

## For developers

Python 3.12, PySide6 (Qt Quick) for the interface, SQLite for the database.

```text
app/         The interface: Qt Quick screens, controllers, Turkish text
database/    SQLite schema, migrations and the balance ledger
services/    The logic: transactions, prices, budget, backup
security/    Sign-in, password rules, login throttling
utils/       Money arithmetic, encryption, key storage, file paths
ui/          English wording for the services' messages
tests/       Tests
scripts/     Build and audit scripts
```

To install the development dependencies and run the tests:

```bash
python -m pip install -r requirements.txt
```

```bash
python run_tests.py
```

The tests run on Linux and Windows for every change. Architecture notes are in
[docs](docs/), contribution rules in [CONTRIBUTING.md](CONTRIBUTING.md), and
what has and has not been tried in the [roadmap](docs/ROADMAP.md).

## License

[Apache 2.0](LICENSE). See also [NOTICE](NOTICE).
