# Smoke Test Report

Generated: 2026-05-27 05:54 IDT

- pass: `P62 mailer business KPI trend`
- targeted P62 tests: `49 passed`
- docker compose API tests: `313 passed`
- smoke command: `bash scripts/run_smoke_tests.sh`
- smoke result: `313 passed, ok`
- services healthy: `api`, `web`, `worker`, `postgres`, `redis`
- API container rebuilt before verification: `true`
- migration 030 applied: `true`
- warmup sent count: `0`
- live outreach sent count: `0`
- mailer action queue rows after cleanup: `0`
- mailer send ledger rows after cleanup: `0`
- recipient resolver audit rows after cleanup: `0`
- mailer policy score history rows: `2`
- mailer business KPI history rows: `1`
- mailer policy score: `100`
- mailer policy decision: `NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW`
- mailer policy score trend direction: `stable`
- mailer policy regression guard: `PASS_NO_SEND`
- mailer business KPI latest queue rows: `0`
- mailer business KPI latest safe actions: `0`
- mailer business KPI latest blocked actions: `0`
- mailer business KPI latest send mail: `false`
- Huanshu adapter status: `PASS`
- frontend visual surface changed in P62: `false`
- secrets exposed: `false`
- raw recipients exposed: `false`
