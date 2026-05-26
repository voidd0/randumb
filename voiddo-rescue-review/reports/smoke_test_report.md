# Smoke Test Report

Generated: 2026-05-27 02:49 IDT

- targeted P53 tests: `39 passed`
- docker compose API tests: `287 passed`
- smoke command: `bash scripts/run_smoke_tests.sh`
- smoke result: `287 passed, ok`
- Next production build: `PASS`
- services healthy: `api`, `web`, `worker`, `postgres`, `redis`
- warmup sent count: `0`
- live outreach sent count: `0`
- mailer action queue rows after cleanup: `0`
- mailer ops retention history rows: `1`
- mailer digest history rows: `1`
- mailer digest trend guard: `PASS_NO_SEND`
- mailer digest trend guard regressions: `0`
- secrets exposed: `false`
- raw recipients exposed: `false`
