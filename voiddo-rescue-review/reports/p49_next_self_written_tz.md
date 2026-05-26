# P49 Self-Written TZ — Mailer Ops Retention Report History

Generated: 2026-05-27 01:22 IDT

## Goal

Persist `mailer_ops_retention_agent_report.md` generation history so retention reports are auditable like digest reports.

## Tasks

1. Add migration/table `mailer_ops_retention_reports`.
2. Persist report metadata:
   - agent_run_id
   - report_path
   - deleted_synthetic_count
   - retained_real_count
   - retained_synthetic_count
   - send flags false
   - raw recipient exposure false
3. Add summary metadata to protected API/admin later.
4. Add tests:
   - row written on agent run
   - row omits raw recipients/secrets
   - no-send flags remain false
5. Update runtime/smoke/launch reports.

## Acceptance

- Retention report history persists in DB.
- Full smoke passes.
- Warmup sent remains `0`.
- Live outreach sent remains `0`.
