# P45 Self-Written TZ — Mailer Ops Retention Agent Evidence

Generated: 2026-05-27 00:47 IDT

## Goal

Make mailer ops run retention part of the autonomous evidence loop, not only a manual admin cleanup capability.

## Tasks

1. Add a `mailer_ops_retention_agent`.
2. Agent must run no-send cleanup/reporting for synthetic mailer ops runs only.
3. Persist an `agent_runs` row with deleted count, retained real count, and send flags false.
4. Add the agent to the autonomous daily loop.
5. Add tests:
   - agent exists in registry
   - agent deletes synthetic runs only
   - real ops evidence remains retained
   - no send flags remain false
6. Update runtime/smoke/launch reports.

## Acceptance

- Synthetic mailer ops rows can be cleaned by an autonomous agent.
- Real retained ops evidence is not deleted.
- Full smoke passes.
- Warmup sent remains `0`.
- Live outreach sent remains `0`.
