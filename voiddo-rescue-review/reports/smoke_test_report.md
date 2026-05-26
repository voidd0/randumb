# Smoke Test Report

Updated: 2026-05-26 IDT

## Commands

- `python -m py_compile` for API and worker modules: PASS
- `npm run build` for web: PASS
- `docker compose up -d --build` for Rescue services only: PASS
- `docker compose exec -T api python -m app.db`: PASS
- `docker compose exec -T api env PYTHONPATH=/app pytest -q`: PASS, `17 passed`

## Runtime Health

- `voiddo_rescue_postgres`: healthy
- `voiddo_rescue_redis`: healthy
- `voiddo_rescue_api`: healthy
- `voiddo_rescue_worker`: healthy
- `voiddo_rescue_web`: healthy

## Functional Smoke

- Real scanner job created and completed.
- Worker wrote audit/issues/screenshots to DB.
- `GET /audits/{slug}` returned real audit data.
- `/r/{slug}` rendered through web container.
- `/admin` rendered through web container with DB metrics.
- Paddle transaction/subscription handlers wrote records in tests.
- Inbox persistence/idempotency passed tests.
- Owner command SAFE_AUTO/HIGH_RISK gates passed tests.
- Visual QA unresolved-template detection passed tests.
- Mail QA missing-DKIM block path passed tests.
- Warmup no-recipient-pool block passed tests.
- Outreach send endpoint remains blocked while launch flag is false.

## Blocked Gates

- Strict SMTP/IMAP TLS login fails.
- Huanshu adapter is blocked because real Huanshu tool is not available.
- Deliverability test is blocked until approved test inbox pool exists.
- Live outreach is not launch-ready.
