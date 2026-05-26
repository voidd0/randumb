# P50 Next Self-Written TZ: Mailer Retention History Admin Surface

Generated: 2026-05-27 01:47 IDT

## Objective

Expose `mailer_ops_retention_reports` safely in the protected admin/API surface so the autonomous mailer can prove its own retention/report history without leaking addresses or secrets.

## Tasks

1. Add a protected API summary for latest retention history rows.
2. Add admin UI metadata for retention history count/latest row.
3. Keep all send flags false and block raw recipient exposure.
4. Add tests for auth, redaction, and no-send flags.
5. Run Huanshu + Playwright/axe/pa11y only if the admin UI changes are visible.
6. Run full pytest and smoke.
7. Export a clean package and continue the loop.

## Acceptance

- protected endpoint requires admin auth
- admin metadata shows retention history evidence
- no raw email addresses, passwords, or secrets appear
- warmup sent remains `0` unless natural gated timer sends later
- live outreach remains `0`
