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
