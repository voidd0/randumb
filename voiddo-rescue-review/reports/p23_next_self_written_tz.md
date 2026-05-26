# P23 Self-Written TZ — Customer Mail Tasks And Onboarding Router

Generated: 2026-05-26 21:10 IDT

## Goal

Connect paid-customer onboarding and fix-request notifications to the mailer action queue so customer-facing email tasks are prepared autonomously while respecting all mail gates.

## Tasks

1. On Paddle transaction/subscription provisioning, enqueue customer mail actions:
   - payment onboarding
   - fix request created
   - monitoring setup reminder
2. Add action types:
   - `customer_onboarding`
   - `fix_request_created`
   - `monitoring_report`
3. Ensure payloads store redacted/sanitized metadata only.
4. Router rules:
   - prepare customer mail when recent mail signals block
   - send only when mail QA PASS, no recent bounce/rate-limit, throttle passes, and customer-mail sending flag is enabled
   - never send cold outreach from this path
5. Admin UI:
   - show customer mail tasks prepared/blocked/sent
6. Tests:
   - mock Paddle paid event enqueues onboarding action
   - one-time fix purchase enqueues fix action
   - customer mail action prepared but not sent while recent signals block
   - raw customer email omitted from queue summary

## Acceptance

- At least 181 tests pass.
- Customer mail actions are autonomously prepared.
- Live outreach remains `0`.
- Warmup remains `0` unless existing natural gates pass.
- Non-Rescue projects untouched.
