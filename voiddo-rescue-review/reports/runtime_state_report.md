# Runtime State Report

Generated: 2026-05-26 19:13 IDT

## Canonical Latest State

- branch: `voiddo-rescue-mvp-review-20260526-files`
- checkout status: `READY`
- mail auth status: `PASS`
- latest mail QA decision: `PASS`
- approved test inbox count: `7`
- approved warmup recipient count: `7`
- scheduled warmup count: `28`
- deliverability diagnostic sent count: `8`
- warmup sent count: `0`
- live outreach sent count: `0`
- bounce/DSN count, last 24h: `2`
- SMTP rate-limit signal count, last 24h: `1`
- spam signal count, last 24h: `0`
- launch readiness state: `WARMUP_SCHEDULED_NO_OUTREACH`

## Autonomous Mailer

- latest mailer status: `blocked_recent_mail_signals`
- next safe action: `wait_until_recent_signal_window_clears`
- clean-window recovery: `blocked_recent_signals`
- recovery sends started: `false`
- email template QA: PASS, `17` rendered samples checked
- signal learning: active
- daily loop agents executed: `19`

## Service Health

- `voiddo_rescue_api`: healthy
- `voiddo_rescue_web`: healthy
- `voiddo_rescue_worker`: healthy
- `voiddo_rescue_postgres`: healthy
- `voiddo_rescue_redis`: healthy

## Visual And Design QA

- Huanshu local adapter: PASS on public routes and authenticated admin
- `axe-core-playwright`: PASS
- `pa11y`: PASS
- `pixelmatch`: PASS
- `lighthouse-ci`: PASS_WITH_WARNINGS, no blocker

## Verification

- API tests: `126 passed`
- smoke test: PASS
- public health endpoints: PASS
- admin auth route checked with bearer token

