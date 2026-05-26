# P35 Self-Written TZ — Mailer Ops Digest UI Surface

Generated: 2026-05-26 23:14 IDT

## Goal

Expose the new daily digest mailer ops evidence in the protected admin UI without introducing send controls or raw recipient exposure.

## Tasks

1. Add admin rows for:
   - daily digest owner report action status
   - mailer ops real count
   - mailer ops synthetic count
   - blocked unsafe ops count
   - latest owner report generated state
2. Add protected API summary if current payload is insufficient.
3. Run Huanshu plus Playwright/axe/pa11y checks on admin.
4. Add tests:
   - admin summary includes digest evidence
   - no raw recipients
   - no send flags
   - owner-report draft stays no-send
5. Update reports:
   - `reports/p35_mailer_ops_digest_ui_surface_report.md`

## Acceptance

- At least 238 tests pass.
- Huanshu PASS for authenticated admin.
- Extra visual/accessibility plugins PASS with 0 blockers.
- Real runtime customer SMTP sends remain `0`.
- Warmup sent remains `0`.
- Live outreach sent remains `0`.

