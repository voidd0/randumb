# Full Scenario Test Report

Generated: 2026-05-26 15:18 IDT

## Decision

`MVP_SCENARIO_SUITE_PASS_NOT_PRODUCTION_READY`

The suite is materially broader than P5, but it does not prove full autonomous production readiness.

## Test Count

- `docker compose exec -T api python -m pytest -q`: 61 passed
- `bash scripts/run_smoke_tests.sh`: PASS, includes 61 pytest tests

## Covered Scenarios

- Scout CSV/domain import to leads and scanner jobs.
- Scout dedupe.
- Excluded niche rejection.
- Lead scoring and reasoning.
- Campaign preview.
- Scanner job lifecycle.
- Audit page API.
- DB writes for audits/issues/screenshots.
- Paddle transaction paid.
- Paddle subscription.
- Payment failure event.
- Inbox persistence/idempotency.
- Owner command safe execution and high-risk block.
- Visual QA placeholder detection.
- Mail QA missing DKIM block.
- Warmup cannot start without pool.
- Warmup blocked by bounce/rate-limit.
- Diagnostic throttling.
- Outreach send remains blocked.
- Admin auth enforced.
- Checkout configured/unconfigured behavior.
- Email template rendering and QA.
- Agent run recording.
- Daily loop safe execution.

## Not Yet Proven

- Real external prospect discovery at scale.
- Real external mailbox placement across major providers after warmup.
- Real customer checkout charge.
- Real customer WP plugin connection.
- Real paid fix completion workflow.

Live outreach remains 0.
