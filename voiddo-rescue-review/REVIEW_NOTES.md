# Vøiddo Rescue Review Notes

Generated: 2026-05-26 21:50 IDT

## Package

- source path: `/opt/voiddo-rescue`
- target folder: `voiddo-rescue-review/`
- file count after manifest regeneration: `254`
- branch: `voiddo-rescue-mvp-review-20260526-files`

## P26 Summary

- Added `CUSTOMER_MAIL_REAL_SEND_ENABLED=false`.
- Added protected customer mail real-send endpoint:
  - `POST /admin/mailer/action-queue/send-customer-mail`
- Real transport now requires customer send flags, mail QA PASS, clean recent mail signals, throttle pass, and template QA pass.
- Mocked SMTP success records `sent`; SMTP exceptions record `failed`; missing flags or missing recipient resolver record `transport_blocked`.
- Raw customer email remains excluded from queue summaries/results.

## Verification

- focused P24-P26 tests: `15 passed`
- full API tests: `196 passed`
- smoke script: PASS
- Docker services: API/web/worker/postgres/redis healthy
- live outreach sent: `0`
- warmup sent: `0`
- customer real-send default: blocked

## Exclusions

Excluded from review/export: `.env`, `*.env`, mailbox passwords, private keys, `.venv`, `venv`, `.pytest_cache`, `__pycache__`, `*.pyc`, `node_modules`, `.next`, runtime storage, screenshots, exports, backups, logs.

## Secret And Artifact Scan

Secret/artifact scan is run before push/export. No secrets, private keys, raw mailbox passwords, virtualenv, cache directories, runtime storage, screenshots, or export artifacts are intended for the review tree.

## Notes

This package is still not launch-ready. Real customer mail, warmup, auto-replies, and cold outreach remain blocked by default until the relevant flags and runtime gates are clean.
