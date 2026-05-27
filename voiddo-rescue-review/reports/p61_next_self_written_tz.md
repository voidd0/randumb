# P61 Self-Written TZ: Mailer Policy Score Trend Digest and Business Loop

Generated: 2026-05-27 04:53 IDT

## Goal

Use the policy score history and regression guard in the daily business/reporting loop so operator reports show whether mailer autonomy is improving, stable, or degrading.

## Tasks

1. Add compact policy score trend fields to `runtime_state_snapshot()` or the reporting layer.
2. Add trend fields to `daily_business_report.md` and `blockers_report.md`.
3. Add admin rows for latest policy score trend state if not already covered.
4. Add tests that a no-send daily loop includes policy trend, retention, and regression guard output.
5. Ensure the generated reports contain no raw recipients, secrets, or owner personal email.
6. Run full API tests, smoke, Huanshu, Playwright, axe, pa11y, hygiene scan, export, push, and memory updates.

## Acceptance

- Daily runtime/business/blocker reports show policy score trend.
- Trend report is redacted and no-send.
- Regression guard remains PASS on clean evidence.
- Live outreach remains `0`.
- Non-Rescue projects remain untouched.
