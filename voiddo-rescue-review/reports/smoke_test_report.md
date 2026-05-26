# Smoke Test Report

Updated: 2026-05-26 14:02 IDT

## Commands

- `docker compose config`: PASS
- `docker compose exec -T api sh -lc 'python -m py_compile app/*.py'`: PASS
- `docker compose exec -T worker sh -lc 'python -m py_compile worker/*.py'`: PASS
- `docker compose exec -T api python -m app.db`: PASS
- `docker compose exec -T api python -m pytest -q`: PASS, `38 passed`
- `bash scripts/run_smoke_tests.sh`: PASS before runtime pool send, `36 passed`

## Runtime Health

- `voiddo_rescue_postgres`: healthy
- `voiddo_rescue_redis`: healthy
- `voiddo_rescue_api`: healthy
- `voiddo_rescue_worker`: healthy
- `voiddo_rescue_web`: healthy

## P4 Functional Smoke

- Deliverability diagnostic refuses empty approved test inbox pool.
- Deliverability diagnostic sends max one neutral message per approved test inbox in tests.
- Warmup refuses empty approved warmup pool.
- Warmup day-1 executor sends max five neutral messages in tests when all gates are mocked PASS.
- Deliverability diagnostic result records Message-ID, SMTP result, and pending bounce state in tests.
- Mail QA now blocks if deliverability diagnostics return SMTP/rate-limit errors.
- Tests no longer send to real runtime pools while checking missing-DKIM behavior.
- Inbox classifier treats delivery observations as autonomous signals, not human blockers.
- Warmup calendar runner installed and first timer check returned `sent: 0` because no slot was due yet.
- Owner command `START WARMUP DAY=1` remains blocked in real runtime because pools are missing.
- `SEND OUTREACH` remains high risk and blocked.
- Mail QA strict SMTP/IMAP remains PASS, but final decision is blocked by missing approved test inbox pool.

## Live Counters

- Deliverability diagnostic sends: `0`
- Warmup sends: `0`
- Live outreach sends: `0`

## P5 Smoke

Updated: 2026-05-26 14:21 IDT

- `docker compose exec -T api python -m app.db`: PASS
- migration order includes `005_p3_checkout_manifest.sql` and `008_p5_mail_signals.sql`: PASS
- `docker compose exec -T api python -m pytest -q`: PASS, `46 passed`
- warmup blocks on recent bounce/DSN: PASS
- warmup blocks on recent rate-limit signal: PASS
- warmup skips suppressed recipient: PASS
- warmup blocks when mail QA is not PASS: PASS
- diagnostic minute cap `1/min`: PASS
- runtime state report generation: PASS
- `SEND OUTREACH` remains high risk: PASS

Live counters after P5: warmup sent `0`, live outreach sent `0`.

## Production Autonomy Build Smoke

Updated: 2026-05-26 15:18 IDT

- `docker compose exec -T api python -m pytest -q`: PASS, `61 passed`
- `bash scripts/run_smoke_tests.sh`: PASS, includes compose/API/worker/DB checks and `61 passed`
- API/web/worker/postgres/redis health: PASS
- Huanshu visual checks:
  - landing: PASS
  - audit demo: PASS
  - customer: PASS
  - status: PASS
  - unsubscribe: PASS
  - authenticated admin: PASS
- Manual safe daily loop: PASS, 7/7 agents completed
- warmup sent: `0`
- live outreach sent: `0`

## P7 Revenue Simulation Smoke

Updated: 2026-05-26 17:56 IDT

- `docker compose exec -T api python -m pytest -q`: PASS, `81 passed`
- `bash scripts/run_smoke_tests.sh`: PASS, `81 passed`
- Huanshu: PASS
- axe-core/playwright: PASS
- pa11y: PASS
- pixelmatch: PASS
- Lighthouse CI: PASS_WITH_WARNINGS
- revenue simulation: PASS
- campaign economics gate: PASS
- mail clean-window watcher: PASS, blocked by current signals
- mailer draft persistence: PASS
- warmup sent: `0`
- live outreach sent: `0`
- recent bounce/DSN still blocks warmup: `2`
- recent rate-limit still blocks warmup: `1`

## P6 Self-Operating Smoke

Updated: 2026-05-26 17:43 IDT

- `docker compose exec -T api python -m pytest -q`: PASS, `71 passed`
- `bash scripts/run_smoke_tests.sh`: PASS, `71 passed`
- Huanshu:
  - landing: PASS
  - audit demo: PASS
  - customer: PASS
  - status: PASS
  - unsubscribe: PASS
  - authenticated admin: PASS
- extra quality plugins:
  - axe-core/playwright: PASS
  - pa11y: PASS
  - pixelmatch: PASS
  - Lighthouse CI: PASS_WITH_WARNINGS
- autonomous mailer cycle: PASS, sent `0`
- daily loop: PASS, 10 agents completed
- warmup sent: `0`
- live outreach sent: `0`

## P8 Real Source + Quality Smoke

Updated: 2026-05-26 18:12 IDT

- `docker compose exec -T api python -m app.db`: PASS
- `docker compose exec -T api python -m pytest -q`: PASS, `92 passed`
- `bash scripts/run_smoke_tests.sh`: PASS, `92 passed`, `ok`
- P8 migrations applied: PASS
- source adapter tests: PASS
- scout self-check tests: PASS
- audit strength tests: PASS
- public-language gate tests: PASS
- protected admin endpoint tests: PASS
- Huanshu:
  - landing: PASS
  - audit demo: PASS
  - customer: PASS
  - status: PASS
  - unsubscribe: PASS
  - authenticated admin screenshots: PASS
- extra quality plugins:
  - axe-core/playwright: PASS
  - pa11y: PASS
  - pixelmatch: PASS
  - Lighthouse CI: PASS_WITH_WARNINGS
- warmup sent: `0`
- live outreach sent: `0`

## P9 Campaign + Mailer Control Smoke

Updated: 2026-05-26 18:24 IDT

- `docker compose exec -T api python -m app.db`: PASS
- `docker compose exec -T api python -m pytest -q`: PASS, `100 passed`
- `bash scripts/run_smoke_tests.sh`: PASS, `100 passed`, `ok`
- campaign readiness snapshot tests: PASS
- outbound mailer decision tests: PASS
- reply action plan tests: PASS
- scout provenance tests: PASS
- protected admin endpoint tests: PASS
- daily loop: PASS, 12 agents completed
- Huanshu:
  - landing: PASS
  - audit demo: PASS
  - customer: PASS
  - status: PASS
  - unsubscribe: PASS
  - authenticated admin screenshots: PASS
- extra quality plugins:
  - axe-core/playwright: PASS
  - pa11y: PASS
  - pixelmatch: PASS
  - Lighthouse CI: PASS_WITH_WARNINGS
- warmup sent: `0`
- live outreach sent: `0`

## P10 Mail Clean Window + Readiness Smoke

Updated: 2026-05-26 18:34 IDT

- `docker compose exec -T api python -m app.db`: PASS
- `docker compose exec -T api python -m pytest -q`: PASS, `107 passed`
- `bash scripts/run_smoke_tests.sh`: PASS, `107 passed`, `ok`
- clean-window transition tests: PASS
- mailbox health tests: PASS
- sender rotation tests: PASS
- interested reply -> mocked checkout/onboarding/fix scenario: PASS
- protected admin endpoint tests: PASS
- daily loop: PASS, 14 agents completed
- Huanshu:
  - landing: PASS
  - audit demo: PASS
  - customer: PASS
  - status: PASS
  - unsubscribe: PASS
  - authenticated admin screenshots: PASS
- extra quality plugins:
  - axe-core/playwright: PASS
  - pa11y: PASS
  - pixelmatch: PASS
  - Lighthouse CI: PASS_WITH_WARNINGS
- warmup sent: `0`
- live outreach sent: `0`

## P5 Cleanup Smoke

Updated: 2026-05-26 14:52 IDT

- `docker compose exec -T api python -m pytest -q`: PASS, `46 passed`
- `bash scripts/run_smoke_tests.sh`: PASS, includes compose config, API compile, worker compile, and pytest `46 passed`
- API/web/worker/postgres/redis health: PASS
- warmup calendar still scheduled: 28 rows
- warmup sent: `0`
- live outreach sent: `0`
- recent bounce/DSN still blocks warmup: `2`
- recent rate-limit still blocks warmup: `1`
