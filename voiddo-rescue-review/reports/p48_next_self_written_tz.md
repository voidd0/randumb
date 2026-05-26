# P48 Self-Written TZ — Mailer Ops Retention Report Admin Metadata

Generated: 2026-05-27 01:13 IDT

## Goal

Expose sanitized `mailer_ops_retention_agent_report.md` metadata in the protected admin dashboard.

## Tasks

1. Add protected API summary metadata for the retention report:
   - exists
   - path stored/not stored
   - modified_at
   - email/send flags false
   - raw recipient exposure false
2. Render metadata in Mailer Ops Controls or Daily Digest Evidence.
3. Add tests or source assertions.
4. Run Huanshu + Playwright + axe + pa11y because this touches admin UI.

## Acceptance

- Admin can see retention report metadata.
- Visual QA passes.
- Full smoke passes.
- Warmup sent remains `0`.
- Live outreach sent remains `0`.
