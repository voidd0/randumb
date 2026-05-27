# Smoke Test Report

Generated: 2026-05-27 03:47 IDT

- targeted P57 tests: `43 passed`
- docker compose API tests: `297 passed`
- smoke command: `bash scripts/run_smoke_tests.sh`
- smoke result: `297 passed, ok`
- Next production build: `PASS`
- services healthy: `api`, `web`, `worker`, `postgres`, `redis`
- warmup sent count: `0`
- live outreach sent count: `0`
- mailer action queue rows after cleanup: `0`
- mailer ops retention history rows: `1`
- mailer digest history rows: `1`
- mailer digest trend guard: `PASS_NO_SEND`
- mailer digest trend guard regressions: `0`
- mailer digest trend guard agent runs: `1`
- latest trend guard compact summary: `PASS_NO_SEND`
- latest trend guard raw history rows included: `false`
- protected admin trend guard summary: `visible`
- Huanshu P56: `PASS`
- axe P56: `0`
- pa11y P56: `0`
- mailer policy score: `100`
- mailer policy decision: `NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW`
- mailer policy blockers: `0`
- secrets exposed: `false`
- raw recipients exposed: `false`
