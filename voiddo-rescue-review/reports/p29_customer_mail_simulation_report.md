# P29 Customer Mail Simulation Matrix Report

Generated: 2026-05-26 22:19 IDT

## Summary

P29 adds a customer lifecycle mail simulation matrix across all paid products, all customer mail actions, and the key gate/transport scenarios. It proves the customer-mail path can be exercised without real SMTP, raw recipients, warmup, or cold outreach.

## Implemented

- Added `apps/api/app/customer_mail_simulation.py`.
- Added protected endpoint:
  - `POST /admin/mailer/customer-simulation`
- Added `customer_mail_simulation_agent` to agent registry and daily loop.
- Added P29 tests for product coverage, scenario coverage, template QA, endpoint auth, no raw recipients, and no real SMTP.

## Matrix

- products covered: `6`
- customer mail actions covered: `3`
- scenarios covered: `7`
- total simulation cases: `126`
- blocking failures: `0`

## Scenarios

- `flags_false`
- `flags_true_recent_signals`
- `suppressed_customer`
- `throttle_blocked`
- `resolver_missing`
- `mocked_smtp_success`
- `mocked_smtp_failure`

## Verification

- focused P29 tests: `7 passed`
- full API tests: `214 passed`
- smoke script: PASS, output `ok`
- services: API/web/worker/postgres/redis healthy

## Runtime State After Test Cleanup

- mailer action queue rows: `0`
- mailer send ledger rows: `0`
- recipient resolver audit rows: `0`
- warmup sent: `0`
- live outreach sent: `0`
- real customer SMTP sends: `0`
- recent bounce/DSN count: `2`
- recent SMTP rate-limit count: `1`

## Decision

P29 is accepted as a no-send customer mail simulation layer. It does not make the system launch-ready; live/customer sends still require explicit flags and a clean mail-signal window.
