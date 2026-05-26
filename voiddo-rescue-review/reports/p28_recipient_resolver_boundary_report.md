# P28 Recipient Resolver Vault Boundary Report

Generated: 2026-05-26 22:12 IDT

## Summary

P28 adds the private recipient resolver boundary for customer lifecycle mail. Customer email can now be resolved only inside the transport boundary from the private `customers` table; public/admin summaries, review exports, ledgers, and reports still expose only hashes/status/reasons.

## Implemented

- Added migration `024_recipient_resolver_audit.sql`.
- Added `recipient_resolver_audit` table with hash-only/status-only records.
- Added `resolve_customer_recipient()` in `mailer_action_queue.py`.
- Updated customer SMTP transport to resolve recipients from `customers.email` only inside the transport boundary.
- Added controlled blockers:
  - `customer_id_missing`
  - `customer_id_invalid`
  - `customer_not_found`
  - `recipient_suppressed`
- Added P28 resolver privacy and suppression tests.

## Safety

- Raw customer email is not included in queue summaries.
- Raw customer email is not included in resolver audit rows.
- Missing/invalid customer records block transport instead of throwing unhandled failures.
- Suppressed customers block transport.
- Default runtime still sends nothing because customer mail flags remain false.

## Verification

- focused P27-P28 tests: `11 passed`
- full API tests: `207 passed`
- smoke script: PASS, output `ok`
- services: API/web/worker/postgres/redis healthy
- migration `024_recipient_resolver_audit.sql`: applied

## Runtime State After Test Cleanup

- mailer action queue rows: `0`
- mailer send ledger rows: `0`
- recipient resolver audit rows from tests: `0`
- warmup sent: `0`
- live outreach sent: `0`
- real customer SMTP sends: `0`
- recent bounce/DSN count: `2`
- recent SMTP rate-limit count: `1`

## Decision

P28 is accepted as a private resolver boundary. It does not make the system launch-ready; explicit send flags and a clean mail-signal window are still required.
