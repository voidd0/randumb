# P38 Self-Written TZ — Mailer Digest Admin Report Link

Generated: 2026-05-26 23:49 IDT

## Goal

Expose the latest `mailer_digest_agent_report.md` metadata in the protected admin digest evidence endpoint and dashboard without exposing raw recipients or secrets.

## Tasks

1. Extend `mailer_digest_summary()` with digest-agent report metadata:
   - report path
   - exists
   - last modified timestamp if available
   - email_sent false
   - raw recipients included false
2. Add a small protected admin panel row under Daily Digest Evidence.
3. Add tests:
   - digest summary includes runtime report metadata
   - admin payload omits raw recipients
   - endpoint remains auth-protected
   - no send flags remain false
4. Run Huanshu + Playwright/axe/pa11y because this touches the admin UI.

## Acceptance

- Runtime report metadata visible only behind admin auth.
- No raw addresses, secrets, message bodies, or mailbox passwords are exposed.
- Huanshu and secondary design checks pass for authenticated admin.
- Full smoke remains green.
- Warmup sent remains `0`.
- Live outreach sent remains `0`.
