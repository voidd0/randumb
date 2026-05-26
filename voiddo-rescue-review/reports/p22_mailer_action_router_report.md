# P22 Mailer Action Queue Router Report

Generated: 2026-05-26 21:10 IDT

## Scope

P22 adds a safe mailer action queue and router. It prepares or blocks mail actions with explicit gate evidence while keeping all sends disabled under the current launch state.

## Files Changed

- `apps/api/migrations/022_mailer_action_queue.sql`
- `apps/api/app/mailer_action_queue.py`
- `apps/api/app/main.py`
- `apps/api/tests/test_p22_mailer_action_queue.py`
- `apps/web/app/admin/page.tsx`

## API

- `GET /admin/mailer/action-queue`
- `POST /admin/mailer/action-queue`
- `POST /admin/mailer/action-queue/process`

All endpoints require admin auth.

## Router Rules

- cold outreach remains blocked while `FIRST_LIVE_SEND_FLAG=false`
- outreach remains blocked while `OUTREACH_PAUSED=true`
- auto-replies remain blocked while `AUTO_REPLIES_PAUSED=true`
- warmup actions are blocked by `natural_warmup_timer_only`
- recent bounce/DSN and SMTP rate-limit signals block mail actions
- action summaries omit raw recipient addresses
- router sends no mail in this pass

## Current Queue Snapshot

- queued: `0`
- prepared: `0`
- blocked: `0`
- sent: `0`
- raw recipient addresses included: `false`
- send_mail: `false`
- live_outreach_allowed: `false`
- active blockers:
  - `outreach_paused_env`
  - `first_live_send_flag_false`
  - `auto_replies_paused_env`
  - `recent_bounce_or_dsn`
  - `recent_rate_limit`

## Verification

- focused P22 tests: `5 passed`
- full API tests: `177 passed`
- smoke script: PASS, output `ok`
- Huanshu: PASS on landing, audit demo, customer, customer token dashboard, status, unsubscribe, authenticated admin
- extra QA plugins: PASS with `0` blockers
- test data cleanup: completed

## Safety

The action router is currently a preparation and blocking layer only. It does not send live outreach, does not force warmup, does not unpause auto-replies, and does not expose raw recipient addresses.

