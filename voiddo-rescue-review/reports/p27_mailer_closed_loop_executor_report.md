# P27 Mailer Closed-Loop Executor Report

Generated: 2026-05-26 22:01 IDT

## Summary

P27 turns the mailer control pieces into an autonomous closed-loop executor. It can process queued mailer actions, attempt gated customer mail transport, record a send ledger, summarize inbound/owner-command risk, and write a runtime report while keeping all real sending blocked by default.

## Implemented

- Added migration `023_mailer_closed_loop.sql`.
- Added `idempotency_key` to `mailer_action_queue`.
- Added `mailer_send_ledger` for attempted, blocked, failed, and sent customer mail actions.
- Added customer mail idempotency for direct queue inserts and Paddle provisioning inserts.
- Added `apps/api/app/mailer_closed_loop.py`.
- Added protected endpoints:
  - `GET /admin/mailer/closed-loop`
  - `POST /admin/mailer/closed-loop/run`
- Added `autonomous_mailer_executor_agent` to agent registry and daily loop.
- Closed-loop report writes privately under runtime storage.

## Safety

- Real customer mail remains disabled by default.
- Cold outreach remains disabled.
- Auto replies remain disabled.
- Raw recipient addresses are not returned in summaries.
- Missing recipient resolver blocks transport with `recipient_resolver_missing`.
- Recent bounce/DSN/rate-limit still blocks sending.

## Verification

- focused P26-P27 tests: `12 passed`
- full API tests: `202 passed`
- smoke script: PASS, output `ok`
- docker compose config: PASS
- services: API/web/worker/postgres/redis healthy
- migration `023_mailer_closed_loop.sql`: applied

## Runtime State After Test Cleanup

- mailer action queue rows: `0`
- mailer send ledger rows: `0`
- autonomous mailer executor agent runs: `7`
- warmup sent: `0`
- live outreach sent: `0`
- real customer SMTP sends: `0`
- recent bounce/DSN count: `2`
- recent SMTP rate-limit count: `1`

## Decision

P27 is accepted as a closed-loop executor layer. It does not make the system launch-ready because recent mail risk signals and default send flags still block real sending.
