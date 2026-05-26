# P36 Self-Written TZ — Mailer Digest Scheduler Agent

Generated: 2026-05-26 23:24 IDT

## Goal

Make daily digest generation part of the autonomous agent loop as a no-send report action.

## Tasks

1. Add `mailer_digest_agent` to autonomous agents.
2. Agent should call owner status report generation with `send_if_safe=false`.
3. Agent result must include:
   - report path
   - email_sent false
   - owner report action id
   - live outreach count
   - warmup count
4. Add tests:
   - agent exists and runs
   - agent writes owner report
   - agent queues no-send owner report action
   - daily loop includes digest agent
   - no live outreach/warmup/customer SMTP send
5. Update reports:
   - `reports/p36_mailer_digest_scheduler_agent_report.md`

## Acceptance

- At least 243 tests pass.
- Digest agent appears in `agent_runs`.
- Owner report is generated without email send.
- Real runtime customer SMTP sends remain `0`.
- Warmup sent remains `0`.
- Live outreach sent remains `0`.

