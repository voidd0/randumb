# Vøiddo Rescue Runtime Recovery Report

Generated: 2026-05-27 22:20 IDT

## Incident

During a large monolithic API regression run, the Rescue runtime became unavailable and `/opt/voiddo-rescue` was found absent. No non-Rescue project path was modified by the recovery work.

## Recovery Actions

- Restored `/opt/voiddo-rescue` from the GitHub review tree.
- Recreated Rescue-only runtime directories under `/opt/voiddo-rescue/storage`, `/opt/voiddo-rescue/logs`, and `/opt/voiddo-rescue/backups`.
- Rebuilt private runtime `.env` from local secret sources without printing or committing values.
- Rebuilt and started only the `voiddo_rescue_*` Docker services.
- Recreated the Rescue PostgreSQL volume and applied all SQL migrations.
- Reimported approved test/warmup pools from private runtime env.
- Recreated a 28-slot neutral warmup calendar, starting 2026-05-28.
- Reinstalled and started only Rescue systemd timers:
  - `voiddo-studio-mail-monitor.timer`
  - `voiddo-rescue-warmup-due.timer`
  - `voiddo-rescue-post-window-recheck.timer`

## Code Fixes

- `scripts/sync_runtime_env.py` now restores strict TLS settings:
  - `SMTP_HOST=mail.voiddo.com`
  - `IMAP_HOST=mail.voiddo.com`
  - `MAIL_TLS_VERIFY=true`
- `scripts/run_smoke_tests.sh` now runs pytest in small batches to avoid VPS memory pressure.
- Added `apps/api/migrations/051_schema_migrations_manifest.sql` so Docker-entrypoint SQL initialization also creates and populates `schema_migrations`.

## Verification

- Focused recovery regression: 29 tests passed.
- Segmented API regression: 73 test files passed.
- Updated smoke script: passed end-to-end with 73 test files.
- Services healthy:
  - `voiddo_rescue_api`
  - `voiddo_rescue_web`
  - `voiddo_rescue_worker`
  - `voiddo_rescue_postgres`
  - `voiddo_rescue_redis`
- Latest strict mail QA decision: PASS.

## Runtime State

- Approved test inboxes: 10
- Approved warmup recipients: 10
- Warmup scheduled slots: 28
- Warmup sent count: 0 after recovery
- Live outreach sent count: 0
- Mailer send ledger count: 0
- Launch readiness: warmup scheduled, no outreach

## Safety Confirmation

- No cold outreach was sent.
- No warmup send was forced manually.
- No raw recipient addresses are included in this report.
- No secrets are included in this report.
- Non-Rescue projects were not touched.
