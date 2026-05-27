# Smoke Test Report

Generated: 2026-05-27 04:53 IDT

- targeted P60 tests: `36 passed`
- docker compose API tests: `308 passed`
- smoke command: `bash scripts/run_smoke_tests.sh`
- smoke result: `308 passed, ok`
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
- mailer policy score agent runs: `3`
- mailer policy score retention agent runs: `2`
- mailer policy score regression guard agent runs: `2`
- mailer policy score history rows: `3`
- latest trend guard compact summary: `PASS_NO_SEND`
- latest trend guard raw history rows included: `false`
- protected admin trend guard summary: `visible`
- Huanshu P60: `PASS`
- axe P60: `0`
- pa11y P60: `0`
- mailer policy score: `100`
- mailer policy decision: `NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW`
- mailer policy blockers: `0`
- protected admin policy score summary: `visible`
- protected admin policy score history summary: `visible`
- digest policy score history evidence: `visible`
- protected admin policy score retention summary: `visible`
- protected admin policy score regression guard summary: `visible`
- daily loop policy score agent order: `after trend guard`
- secrets exposed: `false`
- raw recipients exposed: `false`
