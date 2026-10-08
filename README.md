# Helysofer

A privacy-first, local-first desktop workspace for personal finance, cash flow,
and portfolio tracking.

> [!IMPORTANT]
> Helysofer is in development. There is no installable release yet: the core
> (data, encryption, backup, pricing, insights) is in place and tested, and the
> desktop interface is being built with PySide6 and Qt Quick.

## What it covers

- Accounts and credit cards, income and expense transactions.
- Budget planning, savings goals, debts, and recurring payments.
- Portfolio tracking for stocks, precious metals, foreign currencies, and
  cryptocurrencies.
- Subscription detection, balance history, insights, and scenario projections.

## Principles

- **Local-first:** records live in a local SQLite database on your computer.
- **Private:** amount and description fields are encrypted at rest; there are
  no analytics or advertising trackers. Network access is limited to asset
  prices and brand logos.
- **Fail closed:** an unreadable record is never counted as zero. Showing no
  total is safer than showing a false one.

## Repository layout

```text
database/    SQLite schema, migrations, connections, and ledger
services/    Domain operations, pricing, insights, projections, backup, recovery
security/    Local authentication, password policy, and login throttling
utils/       Decimal policy, encryption, key storage, paths, logging, formatting
ui/          English text catalog and chart localization
tests/       Unit, integration, security, and recovery tests
scripts/     Audit and benchmark tools
```

## Development

Python 3.12 is the supported version.

```bash
python -m pip install -r requirements.txt
```

```bash
python run_tests.py
```

See the [documentation](docs/) for architecture, backup and recovery, and key
management, and [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow.

## Security

Report vulnerabilities as described in [SECURITY.md](SECURITY.md).

## License

Helysofer is available under the [Apache License 2.0](LICENSE); see
[NOTICE](NOTICE).
