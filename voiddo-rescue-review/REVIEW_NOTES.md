# Vøiddo Rescue Review Notes

Generated: 2026-05-26 20:21 IDT

## Scope

This review tree contains the Vøiddo Rescue source tree after P18 clean-window recheck automation and safe resume timestamp work.

## Included

- `docker-compose.yml`
- `.env.example`
- API, worker, web, shared package, scripts, migrations, WP plugin source
- redacted reports
- test suite

## Excluded

- `.env` and `*.env`
- mailbox passwords, API keys, private keys
- `storage/`, runtime screenshots, exports, logs
- `.venv`, `.pytest_cache`, `__pycache__`, `*.pyc`
- `node_modules`, `.next`

## Verification

- API tests: `156 passed`
- smoke: PASS
- Huanshu: PASS, including updated authenticated admin clean-window panel
- extra design/QA plugins: PASS or non-blocking warning; blockers `0`
- clean-window recheck status: `blocked_recent_signals`
- live outreach sent: `0`
- warmup sent: `0`

## Launch State

`WARMUP_SCHEDULED_NO_OUTREACH`. Recent bounce/DSN and SMTP rate-limit signals still block sending; next safe recheck timestamp is recorded in reports.

## Secrets

No raw secrets are intentionally included. `.env.example` is included as a template only.

## P18 Export

- zip path: /opt/voiddo-rescue/storage/exports/voiddo-rescue-p18-clean-window-recheck-2026-05-26.zip
- initial zip SHA256 before metadata refresh: abb6795a76d44e0c6a4b71b6b9be25e87e727ea3c6cf28e63f56af6bff184730
- branch before commit: 73232586bdd03feaf2a81e57c0e210b7f09e2cdb
