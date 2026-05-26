# P26 Self-Written TZ — Real Customer Mail Transport Gate

Generated: 2026-05-26 21:45 IDT

## Goal

Add the final real customer-mail transport gate, still disabled by default, so `send_ready` customer actions can be delivered only when all mail gates and an explicit real-send flag pass.

## Tasks

1. Add env flag `CUSTOMER_MAIL_REAL_SEND_ENABLED=false`.
2. Add protected real-send endpoint:
   - `POST /admin/mailer/action-queue/send-customer-mail`
3. Real-send gate:
   - action status `send_ready`
   - customer mail sending flag true
   - real-send flag true
   - mail QA PASS
   - no bounce/DSN/rate-limit in 24h
   - throttle pass
   - template QA pass
4. Transport:
   - use existing SMTP abstraction
   - record provider Message-ID
   - update action status `sent` or `transport_blocked`
5. Tests:
   - default real-send blocked
   - missing flag blocks
   - mocked SMTP send records `sent`
   - SMTP failure records `failed`
   - raw customer email not exposed in summaries

## Acceptance

- At least 195 tests pass.
- Default real-send blocked.
- Mocked real-send path works without using real SMTP.
- No live outreach sent.
- Warmup remains gated.
- Non-Rescue projects untouched.
