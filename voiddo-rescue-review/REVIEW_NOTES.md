# Vøiddo Rescue Review Notes

Generated: 2026-05-26 19:55 IDT

## Scope

This review tree contains the Vøiddo Rescue MVP source tree after P16 monitoring scheduler and customer-token dashboard work.

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

- API tests: `144 passed`
- smoke: PASS
- Huanshu: PASS, including token dashboard and admin-auth screenshots
- extra design/QA plugins: PASS or non-blocking warning; blockers `0`
- live outreach sent: `0`
- warmup sent: `0`

## Launch State

`WARMUP_SCHEDULED_NO_OUTREACH`. Recent bounce/DSN and SMTP rate-limit signals still block sending.

## Secrets

No raw secrets are intentionally included. `.env.example` is included as a template only.

## P16 Export

- zip path: /opt/voiddo-rescue/storage/exports/voiddo-rescue-p16-monitoring-scheduler-customer-ui-2026-05-26.zip
- initial zip SHA256 before metadata refresh: 04be7baae7f9f0b178c375129f7fc10358fcaab6b03e9cf3ce0b64e507b815e1
- branch before commit: 4329e362a878965b069400e3ba43d1a812a9d437
