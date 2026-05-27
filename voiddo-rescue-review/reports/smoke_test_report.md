# Smoke Test Report

Generated: 2026-05-27 05:29 IDT

- pass: `P61 policy trend reporting`
- targeted P61 tests: `46 passed`
- docker compose API tests: `310 passed`
- smoke command: `bash scripts/run_smoke_tests.sh`
- smoke result: `310 passed, ok`
- services healthy: `api`, `web`, `worker`, `postgres`, `redis`
- API container rebuilt before verification: `true`
- warmup sent count: `0`
- live outreach sent count: `0`
- mailer action queue rows after cleanup: `0`
- mailer send ledger rows after cleanup: `0`
- recipient resolver audit rows after cleanup: `0`
- mailer policy score history rows: `2`
- mailer policy score agent runs: `2`
- mailer policy score retention agent runs: `1`
- mailer policy score regression guard agent runs: `1`
- policy trend reporting agent runs: `1`
- mailer policy score: `100`
- mailer policy decision: `NO_SEND_READY_FOR_MONITORED_WARMUP_WINDOW`
- mailer policy score trend direction: `stable`
- mailer policy regression guard: `PASS_NO_SEND`
- mailer policy regression count: `0`
- daily business report includes policy trend: `true`
- blockers report includes policy trend and regression guard: `true`
- runtime state report includes policy trend: `true`
- Huanshu adapter status: `PASS`
- frontend visual surface changed in P61: `false`
- secrets exposed: `false`
- raw recipients exposed: `false`
