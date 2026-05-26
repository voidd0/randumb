# Smoke Test Report

Updated: 2026-05-26 12:45 IDT

## Commands

- `docker compose config`: PASS
- `docker compose exec -T api sh -lc 'python -m py_compile app/*.py'`: PASS
- `docker compose exec -T worker sh -lc 'python -m py_compile worker/*.py'`: PASS
- `docker compose exec -T api python -m app.db`: PASS
- `docker compose exec -T api python -m pytest -q`: PASS, `35 passed`
- `bash scripts/run_smoke_tests.sh`: PASS

## Runtime Health

- `voiddo_rescue_postgres`: healthy
- `voiddo_rescue_redis`: healthy
- `voiddo_rescue_api`: healthy
- `voiddo_rescue_worker`: healthy
- `voiddo_rescue_web`: healthy

## Public Route Smoke

- `https://rescue.voiddo.com/`: `200`
- `https://app.rescue.voiddo.com/admin`: `401` expected
- `https://api.rescue.voiddo.com/health`: `200`
- `https://audit.rescue.voiddo.com/r/demo`: `200`
- `https://go.rescue.voiddo.com/unsubscribe/test`: `200`
- `https://status.rescue.voiddo.com/`: `200`
- `https://app.rescue.voiddo.com/admin?token=...`: `401` expected
- `https://app.rescue.voiddo.com/admin` with Bearer auth: `200`
- `https://app.rescue.voiddo.com/admin` with Basic auth: `200`
- `https://go.rescue.voiddo.com/checkout/{product_key}?audit=demo`: `302` for all six products
- `https://app.rescue.voiddo.com/checkout/contact_form_repair?audit=demo`: `200`

## Functional Smoke

- Real scanner job created and completed.
- Worker wrote audit/issues/screenshots to DB.
- `GET /audits/{slug}` returned real audit data.
- `/r/{slug}` rendered through web and public audit domain.
- `/admin` is protected without token and works with token.
- Paddle transaction/subscription handlers wrote records in tests.
- Go checkout endpoint redirects to Paddle.js checkout page when client checkout token is configured.
- Inbox persistence/idempotency passed tests.
- Owner command SAFE_AUTO/MEDIUM_RISK/HIGH_RISK gates passed tests.
- Visual QA unresolved-template detection passed tests.
- Huanshu visual QA passed public route coverage.
- Mail QA missing-DKIM block path passed tests.
- Warmup no-recipient-pool block passed tests.
- Outreach send endpoint remains blocked while launch flag is false.

## Blocked Gates

- Deliverability test is blocked until approved test inbox pool exists.
- Warmup is blocked until approved recipient pool exists.
- Live outreach is not launch-ready.
