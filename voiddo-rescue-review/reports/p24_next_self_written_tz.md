# P24 Self-Written TZ — Customer Mail Router Gate Completion

Generated: 2026-05-26 21:23 IDT

## Goal

Finish the customer-mail execution gate so prepared customer messages can move from queue to send-ready evidence only when mail safety is clean, throttle passes, and customer-mail sending is explicitly enabled.

## Tasks

1. Add customer-mail gate evaluator:
   - latest mail QA PASS
   - no bounce/DSN in 24h
   - no SMTP rate-limit in 24h
   - throttle pass
   - `CUSTOMER_MAIL_SENDING_ENABLED=true`
2. Add customer-mail dry-run renderer:
   - payment onboarding
   - fix request created
   - monitoring setup reminder
3. Add admin queue details:
   - customer mail prepared/blocked/send-ready
   - top blockers
   - template QA status
4. Tests:
   - customer mail stays prepared with flag false
   - customer mail becomes send-ready under mocked clean gates and flag true
   - throttle failure blocks send-ready
   - rendered messages pass email QA
   - no raw customer email in reports

## Acceptance

- At least 186 tests pass.
- Customer mail can become send-ready under mocked clean gates.
- No live outreach sent.
- No warmup forced.
- Non-Rescue projects untouched.
