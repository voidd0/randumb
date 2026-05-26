# P12 Spacing Application + Revenue Scenario Report

Generated: 2026-05-26 18:58 IDT

## Scope

P12 implemented the next self-written build cycle for Vøiddo Rescue:

- no-send provider-spacing application gate for the warmup calendar
- rollback support for applied spacing repairs
- expanded scout -> campaign -> checkout synthetic revenue scenario
- unsafe reply action scenario
- admin endpoints for spacing apply/rollback
- daily-loop agent wiring for the spacing apply gate

## Code Changes

- `apps/api/migrations/016_warmup_spacing_rollback.sql`
- `apps/api/app/warmup_planner.py`
- `apps/api/app/main.py`
- `apps/api/app/p0.py`
- `apps/api/app/autonomous_agents.py`
- `apps/api/tests/test_p12_spacing_apply_revenue.py`
- `apps/web/app/admin/page.tsx`

## Mailer Autonomy

The mailer remains an autonomous gated subsystem:

- inbound mail is persisted/classified by the inbox layer
- owner commands remain parsed and gated
- outgoing messages must pass template QA, suppression, unsubscribe, rate limits, mail QA, and visual/email checks
- warmup is scheduled but pre-send gated
- recent bounce/DSN or SMTP rate-limit signals block warmup and outreach
- provider-spacing application does not send mail
- live outreach remains paused

## P12 Runtime Result

- spacing apply gate result: `blocked_safety_gate`
- applied: `false`
- rollback-ready table: present
- due-now warmup rows: `0`
- latest mail QA decision: `PASS`
- recent bounce/DSN signals, last 24h: `2`
- recent SMTP rate-limit signals, last 24h: `1`
- warmup sent: `0`
- live outreach sent: `0`

The gate is behaving correctly: it refuses to alter the active schedule while recent mail signals indicate risk.

## Revenue Scenario Coverage

Added scenario coverage for:

- manual CSV scout import
- accepted lead creation
- scanner job creation
- audit and issue evidence creation
- lead scoring after audit
- campaign preview selection
- campaign readiness snapshot
- Paddle `transaction.paid` mock
- customer/payment/fix-request/onboarding persistence

This is a sandbox/mock scenario only. No real charge was created.

## Visual QA

Huanshu local adapter:

- `/`: PASS
- `/r/demo`: PASS
- `/customer`: PASS
- `/status`: PASS
- `/unsubscribe/demo-token`: PASS
- authenticated `/admin`: PASS

Additional design/QA plugins:

- `axe-core-playwright`: PASS
- `pa11y`: PASS
- `pixelmatch`: PASS
- `lighthouse-ci`: PASS_WITH_WARNINGS, score `80`, no blocker

## Verification

- API tests: `118 passed`
- smoke tests: `PASS`, includes `118 passed`
- API health: PASS
- web health: PASS
- Docker services healthy: API, web, worker, Postgres, Redis

## Launch Decision

State: `WARMUP_SCHEDULED_NO_OUTREACH`

Not launch-ready for live cold outreach. Exact current blocker is recent delivery risk:

- bounce/DSN signals in the last 24h
- SMTP rate-limit signal in the last 24h

Next safe action: wait until the recent signal window clears, rerun mail QA, then let the spacing apply gate re-evaluate without sending.

