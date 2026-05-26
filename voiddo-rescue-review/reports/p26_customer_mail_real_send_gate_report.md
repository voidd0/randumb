# P26 Customer Mail Real Send Gate Report

Generated: 2026-05-26 21:50 IDT

## Summary

P26 adds the final customer-mail transport gate. The system now has a protected real-send endpoint for customer lifecycle mail, but real SMTP delivery remains disabled by default and requires explicit customer-mail flags plus clean agent checks.

## Implemented

- Added `CUSTOMER_MAIL_REAL_SEND_ENABLED=false` config flag.
- Added protected endpoint:
  - `POST /admin/mailer/action-queue/send-customer-mail`
- Added `send_customer_mail()` gate and transport flow in `apps/api/app/mailer_action_queue.py`.
- Added mocked-safe SMTP transport boundary:
  - records `sent` only when mocked/all gates pass
  - records `transport_blocked` when flags/gates/recipient resolver are missing
  - records `failed` on SMTP exception
- Kept raw customer email out of queue summaries/results.

## Required Gates

- action status is `send_ready`
- action type is customer mail
- `CUSTOMER_MAIL_SENDING_ENABLED=true`
- `CUSTOMER_MAIL_REAL_SEND_ENABLED=true`
- latest mail QA decision is `PASS`
- no bounce/DSN in last 24h
- no SMTP rate-limit signal in last 24h
- customer-mail throttle allows send
- rendered template QA passes

## Verification

- focused P24-P26 tests: `15 passed`
- full API tests: `196 passed`
- smoke script: PASS, output `ok`
- services: API/web/worker/postgres/redis healthy
- export ZIP: `/opt/voiddo-rescue/storage/exports/voiddo-rescue-p26-customer-mail-real-send-gate-2026-05-26.zip`

## Runtime Safety State

- customer real-send flag default: `false`
- live outreach sent: `0`
- warmup sent: `0`
- customer mail actions sent by real transport: `0`
- current mailer action queue rows after test cleanup: `0`
- recent bounce/DSN count: `2`
- recent SMTP rate-limit count: `1`

## Decision

P26 is accepted as a gated implementation. It does not make the system launch-ready. Real customer mail remains blocked until explicit flags are enabled and recent mail risk signals clear.
