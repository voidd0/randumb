# P37 Self-Written TZ — Digest Agent Runtime Report File

Generated: 2026-05-26 23:34 IDT

## Goal

Write a dedicated digest-agent runtime report file after each `mailer_digest_agent` run, separate from the owner-facing status report.

## Tasks

1. Add helper to write `reports/mailer_digest_agent_report.md`.
2. Include:
   - generated_at
   - agent run id
   - owner report path
   - owner report action id
   - email_sent false
   - warmup sent count
   - live outreach sent count
   - current mail blockers
3. Add tests:
   - report file is written
   - report omits raw recipients
   - report confirms no-send
   - daily loop still includes digest agent
4. Update reports:
   - `reports/p37_digest_agent_runtime_report_file.md`

## Acceptance

- At least 247 tests pass.
- Runtime report exists.
- Raw recipients omitted.
- Real runtime customer SMTP sends remain `0`.
- Warmup sent remains `0`.
- Live outreach sent remains `0`.

