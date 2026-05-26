# Vøiddo Rescue Review Notes

Original source path: `/opt/voiddo-rescue`

Export package is generated from this folder after artifact cleanup.

## Excluded

- `.env` and `*.env` except `.env.example`
- mailbox passwords, API keys, private keys
- `.venv`, `venv`, `.pytest_cache`, `__pycache__`, `*.pyc`
- `node_modules`, `.next`
- runtime `storage`, `exports`, `screenshots`, `logs`, `backups`
- generated image artifacts

## Secret Scan

Result: no raw secrets intentionally included. Reports are redacted. Runtime addresses and private mailbox credentials are excluded.

## Functional Status

- Tests: 61 passed
- Smoke: PASS
- Huanshu visual checks: PASS for landing, audit demo, customer, status, unsubscribe, authenticated admin
- Live outreach sent: 0
- Warmup sent: 0
- Launch readiness: WARMUP_SCHEDULED_NO_OUTREACH

## Commit SHA

Filled after commit in final response.
