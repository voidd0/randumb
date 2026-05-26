# P43 Self-Written TZ — Mailer Digest Retention Ops Evidence

Generated: 2026-05-27 00:38 IDT

## Goal

Record digest retention agent runs into the mailer operations evidence layer so housekeeping actions are auditable alongside other no-send mailer ops.

## Tasks

1. Add a `digest_history_cleanup` action to `run_mailer_ops_action()`.
2. Persist result in `mailer_ops_runs` with:
   - action
   - source
   - status
   - send_mail false
   - deleted_count
   - before/after total rows
3. Add tests:
   - ops action runs cleanup
   - ops action persists sanitized result
   - action is no-send
   - action does not touch mailer action queue/send ledger
4. No UI change unless existing ops summary already displays it naturally.

## Acceptance

- Digest retention cleanup is auditable in ops evidence.
- Full smoke passes.
- Warmup sent remains `0`.
- Live outreach sent remains `0`.
