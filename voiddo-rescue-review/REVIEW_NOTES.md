# Vøiddo Rescue Review Notes

Generated: 2026-05-26 22:12 IDT

## Package

- source path: `/opt/voiddo-rescue`
- target folder: `voiddo-rescue-review/`
- file count after manifest regeneration: `263`
- branch: `voiddo-rescue-mvp-review-20260526-files`

## P28 Summary

- Added migration `024_recipient_resolver_audit.sql`.
- Added private customer recipient resolver boundary.
- Customer email is resolved from the private `customers` table only inside the transport path.
- Resolver audit stores hash/status/reason only.
- Transport now blocks cleanly on missing, invalid, unknown, or suppressed customers.

## Verification

- focused P27-P28 tests: `11 passed`
- full API tests: `207 passed`
- smoke script: PASS
- docker compose config: PASS
- Docker services: API/web/worker/postgres/redis healthy
- migration `024_recipient_resolver_audit.sql`: applied
- live outreach sent: `0`
- warmup sent: `0`
- real customer SMTP sends: `0`

## Exclusions

Excluded from review/export: `.env`, `*.env`, mailbox passwords, private keys, `.venv`, `venv`, `.pytest_cache`, `__pycache__`, `*.pyc`, `node_modules`, `.next`, runtime storage, screenshots, exports, backups, logs.

## Secret And Artifact Scan

Secret/artifact scan is run before push/export. No secrets, private keys, raw mailbox passwords, virtualenv, cache directories, runtime storage, screenshots, or export artifacts are intended for the review tree.

## Notes

This package is still not launch-ready. Recipient resolution is now available for future customer mail transport, but real sends remain blocked by flags and recent mail-signal gates.
