# P42 Self-Written TZ — Digest Retention Agent

Generated: 2026-05-27 00:27 IDT

## Goal

Wire digest history retention cleanup into the autonomous agent loop as a no-send housekeeping agent.

## Tasks

1. Add `mailer_digest_retention_agent` to `run_agent()`.
2. Include it in `run_daily_loop()`.
3. The agent must:
   - run `cleanup_mailer_digest_history(90)`
   - return send_mail false
   - return live_outreach_allowed false
   - expose before/after retention summary
4. Add tests:
   - agent exists
   - agent deletes old digest history rows
   - daily loop includes the agent
   - no send flags remain false
   - action queue/send ledger are not touched

## Acceptance

- Digest history retention runs autonomously.
- Full smoke passes.
- Warmup sent remains `0`.
- Live outreach sent remains `0`.
