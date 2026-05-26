# P44 Self-Written TZ — Mailer Ops Digest Retention Admin Visibility

Generated: 2026-05-27 00:51 IDT

## Goal

Expose `digest_history_cleanup` mailer ops evidence in the protected admin Mailer Ops Controls panel.

## Tasks

1. Add a protected admin button for `digest_history_cleanup`.
2. Ensure latest ops list naturally shows the cleanup action.
3. Add tests or source assertions:
   - action button exists
   - endpoint remains protected
   - no-send flags remain false
4. Run Huanshu + Playwright + axe + pa11y because this touches admin UI.

## Acceptance

- Admin can trigger digest history cleanup as a no-send ops action.
- Visual QA passes.
- Full smoke passes.
- Warmup sent remains `0`.
- Live outreach sent remains `0`.
