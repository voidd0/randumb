# Vøiddo Rescue Review Notes

Generated: 2026-05-27 05:54 IDT

## Package

- pass: P62 mailer business KPI trend
- source path: /opt/voiddo-rescue
- review folder: voiddo-rescue-review/
- branch before commit: b5c864488e289c87ef3ea1830757a65d03b374ac
- filelist sha256: af3d5a7cb6f49fb0bf094bdf3b7da91f4edd72e71040d6abfa8df6d99aed3f38

## Included

- application code
- migrations
- scripts
- WordPress plugin source
- redacted reports
- .env.example
- docker-compose.yml
- P62 runtime, daily business, blockers, launch, smoke, KPI, and next-TZ reports

## Excluded

- .env and *.env secrets except .env.example
- mailbox passwords and private keys
- .venv, .pytest_cache, __pycache__, *.pyc
- node_modules and .next
- runtime storage, exports, logs, screenshots, PNG screenshots

## Safety

- live outreach sent: 0
- warmup sent manually in this pass: 0
- FIRST_LIVE_SEND_FLAG remains false
- OUTREACH_PAUSED remains true
- AUTO_REPLIES_PAUSED remains true
- non-Rescue projects touched: false

## Verification

- targeted tests: 49 passed
- full API tests: 313 passed
- smoke: 313 passed, ok
- Huanshu adapter: PASS
- services: api/web/worker/postgres/redis healthy
- secret/artifact scan: clean for raw secrets and blocked artifacts; code-level env variable names are present only as configuration references

## Commit

The exact pushed commit SHA is reported in the final operator output after commit creation.
