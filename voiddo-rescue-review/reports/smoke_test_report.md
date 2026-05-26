# Smoke Test Report

Updated: 2026-05-26 13:00 IDT

## Commands

- `docker compose config`: PASS
- `docker compose exec -T api sh -lc 'python -m py_compile app/*.py'`: PASS
- `docker compose exec -T worker sh -lc 'python -m py_compile worker/*.py'`: PASS
- `docker compose exec -T api python -m app.db`: PASS
- `docker compose exec -T api python -m pytest -q`: PASS, `36 passed`
- `bash scripts/run_smoke_tests.sh`: PASS, `36 passed`

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
- Owner command `START WARMUP DAY=1` remains blocked in real runtime because pools are missing.
- `SEND OUTREACH` remains high risk and blocked.
- Mail QA strict SMTP/IMAP remains PASS, but final decision is blocked by missing approved test inbox pool.

## Live Counters

- Deliverability diagnostic sends: `0`
- Warmup sends: `0`
- Live outreach sends: `0`
