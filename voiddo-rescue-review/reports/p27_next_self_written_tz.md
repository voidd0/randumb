# P27 Self-Written TZ — Autonomous Mailer Closed-Loop Executor

Generated: 2026-05-26 21:50 IDT

## Goal

Turn the gated mailer pieces into a complete closed-loop executor that can autonomously handle customer lifecycle mail, owner reports, inbound replies, and safe follow-up preparation while preserving all launch gates and no-send defaults.

## Tasks

1. Add mailer executor agent run that processes:
   - inbound reply classifications
   - owner command results
   - customer mail action queue
   - safe report generation
2. Add recipient resolver design that never exposes raw customer email in public/review artifacts.
3. Add send ledger rows for every attempted, blocked, failed, or sent customer mail action.
4. Add idempotency protection per action/template/customer/event.
5. Add admin summary for:
   - ready customer actions
   - blocked customer actions
   - failed customer transport
   - unresolved inbound risk threads
6. Add tests for:
   - idempotency
   - safe resolver missing blocks
   - closed-loop agent records action
   - blocked signals prevent all sends
   - no raw recipients in summaries

## Acceptance

- At least 202 tests pass.
- Real send remains disabled by default.
- Closed-loop executor creates evidence but sends nothing under current runtime.
- Live outreach remains `0`.
- Warmup remains gated.
- Non-Rescue projects untouched.
