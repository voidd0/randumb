# P14 Customer Journey + Reply Hardening Report

Generated: 2026-05-26 19:25 IDT

## Scope

P14 extended the autonomous revenue system beyond mail control by hardening paid customer journey visibility and reply handling.

## Code Changes

- `apps/api/migrations/018_p14_customer_journey.sql`
- `apps/api/app/customer_journey.py`
- `apps/api/app/inbox.py`
- `apps/api/app/main.py`
- `apps/api/app/p0.py`
- `apps/api/app/autonomous_agents.py`
- `apps/api/tests/test_p14_customer_reply_journey.py`
- `apps/web/app/admin/page.tsx`

## New Table

- `customer_journey_snapshots`

## Customer Journey

Implemented `customer_journey_snapshot`:

- locates customer by id, email, or Paddle customer id
- includes payments and subscriptions
- includes onboarding tasks
- includes monitoring targets
- includes fix requests
- ensures each paid fix request has a linked `customer_fix_request` Codex task
- writes a snapshot for admin/customer review

Protected endpoint:

- `GET /admin/customers/{customer_id}/journey`

## Reply Handling

Reply classification now covers:

- `interested`
- `ask_price`
- `ask_details`
- `unsubscribe`
- `wrong_person`
- `angry`
- `legal_threat`
- `security_accusation`

Safe categories prepare only gated drafts/actions. Unsafe categories stop the thread and require review. No auto-reply is sent by these tests or handlers.

## Admin Control Room

Admin now shows:

- latest autonomous mailer status
- next safe mail action
- customer journey snapshot count
- live outreach gate remains blocked

## Verification

- API tests: `132 passed`
- smoke: PASS, includes `132 passed`
- Huanshu: PASS
- extra QA plugins: PASS or non-blocking warning
- warmup sent: `0`
- live outreach sent: `0`

## Current Decision

State remains `WARMUP_SCHEDULED_NO_OUTREACH`.

The system is stronger, but still not live-outreach ready while recent bounce/DSN and SMTP rate-limit signals remain in the 24h window.

