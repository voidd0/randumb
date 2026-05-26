# P47 Self-Written TZ — Mailer Ops Retention Report File

Generated: 2026-05-27 01:06 IDT

## Goal

Write a dedicated runtime report for `mailer_ops_retention_agent`, matching the digest-agent report pattern.

## Tasks

1. Add `write_mailer_ops_retention_agent_report()`.
2. When `mailer_ops_retention_agent` runs, write:
   - agent run ID
   - deleted synthetic count
   - retained real count
   - retained latest real action
   - send flags false
   - raw recipient exposure false
3. Persist report metadata in the agent result.
4. Add tests:
   - report file written
   - report omits raw recipients/secrets
   - daily loop exposes report metadata
5. Update runtime/smoke/launch reports.

## Acceptance

- Mailer ops retention agent has a dedicated report file.
- Full smoke passes.
- Warmup sent remains `0`.
- Live outreach sent remains `0`.
