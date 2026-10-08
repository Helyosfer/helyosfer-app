# Security and reliability status

This document is the single current security and reliability summary.
Helysofer is pre-release: the points below describe the core layers, which are
covered by the test suite. Packaging checks will be added with the first
packaged build.

## Current verified protections

- **Financial correctness:** dashboard period/30-day metrics and budget totals
  do not count corrupt encrypted records as zero. A shared Decimal policy
  defines fiat, quantity, and percentage boundaries where migration is
  complete.
- **Data protection:** new sensitive values are written only with AEAD. Backup
  validates the database and password-protected recovery key together; restore
  is rollback-safe. The database records which schema generation wrote it, and
  an older build refuses to open a newer one rather than writing to a schema it
  does not understand.
- **Dependency vulnerabilities:** the packaged dependency set is scanned on
  every pull request and the scan blocks. The published SBOM remains the
  authoritative component inventory.
- **External price data:** third-party price results carry source, age, and
  freshness status rather than being presented as guaranteed current values.
- **Credentials:** new and changed passwords use the shared strong-password
  policy. A user who successfully authenticates with an older weak credential
  must renew it before reaching financial screens.

## Known limitations

- Stable describes the verified software and recovery scope. It is not banking
  or accounting certification, and verified backups remain the user's
  responsibility.
- The legacy CBC reader remains deprecated for compatibility with old profiles
  and backups. New data cannot be written in that format.
- Yahoo Finance is the primary price provider. When it returns nothing for a
  symbol, cryptocurrency falls back to CoinGecko and foreign currency to
  Frankfurter (ECB), and the reported source names whichever provider actually
  answered. **BIST equities and gold have no fallback** — no free source for
  them is currently integrated, so those stay on Yahoo Finance alone. A very
  old cache is not presented as a definitively current price.
- Some broad exception handlers remain in services. CI blocks new broad or
  silent handlers and freezes a decreasing baseline.
- Windows DPAPI key storage is implemented; it is not yet exercised through a
  packaged application.
  Linux Secret Service/KWallet integrations exist and have an explicit,
  visible permission-restricted file fallback; desktop keyring availability
  still varies by Linux distribution and session configuration.

Losing both the active key and usable recovery material can make encrypted
records unrecoverable. See [Key management](KEY_MANAGEMENT.md) and
[Backup and recovery](BACKUP_RECOVERY.md).
