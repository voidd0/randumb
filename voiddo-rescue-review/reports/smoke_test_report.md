# Smoke Test Report

Generated: 2026-05-27 02:16 IDT

- targeted P51 tests: `35 passed`
- docker compose API tests: `282 passed`
- smoke command: `bash scripts/run_smoke_tests.sh`
- smoke result: `282 passed, ok`
- services healthy: `api`, `web`, `worker`, `postgres`, `redis`
- warmup sent count: `0`
- live outreach sent count: `0`
- mailer action queue rows after cleanup: `0`
- mailer ops retention history rows: `1`
- mailer digest history rows: `1`
- secrets exposed: `false`
- raw recipients exposed: `false`
