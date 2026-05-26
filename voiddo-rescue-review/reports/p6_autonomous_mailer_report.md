# P6 Autonomous Mailer Report

Generated: 2026-05-26 17:43 IDT

## Decision

`AUTONOMOUS_MAILER_READY_BLOCKED_BY_LAUNCH_GATES`

The mailer is now a policy-driven autonomous decision loop, not a raw send queue.

## Implemented

- `apps/api/app/autonomous_mailer.py`
- `autonomous_mailer_decisions` table
- Admin endpoints:
  - `POST /admin/mailer/autonomous-cycle`
  - `POST /admin/mailer/decide-outbound`
  - `POST /admin/mailer/decide-inbound`
- Agent:
  - `autonomous_mailer_agent`

## Outbound Policy

Outbound campaign mail is blocked if any of these are true:

- outreach paused
- dry-run enabled
- first live send flag false
- recent bounce/DSN signal
- recent SMTP rate-limit signal
- transport gate fails
- unsubscribe is missing
- suppression/rate-limit/visual/mail QA fails

Current outbound decision:

- status: `blocked`
- action: `do_not_send`
- reason: `outreach_paused`
- sent: `0`

## Inbound Policy

Inbound mail is classified before action.

Safe categories can only draft or auto-reply if auto-replies are explicitly unpaused:

- ask_price
- ask_details
- wrong_person
- out_of_office
- unsubscribe

Unsafe categories stop automation and create review/alert state:

- angry
- legal threat
- security accusation
- custom technical request
- wants call

Current auto-replies remain paused.

## Verification

- Inbound price sample routes to draft-only while auto-replies are paused.
- Legal/security style sample routes to review-required.
- Full autonomous mailer cycle sends `0`.
- Tests pass.
