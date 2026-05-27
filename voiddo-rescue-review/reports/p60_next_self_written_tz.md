# P60 Self-Written TZ: Policy Score Retention and Regression Alerts

Generated: 2026-05-27 04:31 IDT

## Goal

Add retention and regression-alert logic for `mailer_policy_score_history` so the autonomous mailer can keep durable evidence without unbounded growth and can create review tasks when policy score drops.

## Tasks

1. Add `cleanup_mailer_policy_score_history(keep=120)`.
2. Add `mailer_policy_score_regression_guard()` that compares the latest score/decision against recent clean history.
3. Add `mailer_policy_score_retention_agent` and `mailer_policy_score_regression_guard_agent`.
4. Wire both agents into the daily loop after policy scoring.
5. Add protected admin rows for policy score retention and regression state.
6. Add tests for retention, regression detection, no-send guarantees, endpoint auth, and admin visibility.
7. Run full API tests, smoke, Huanshu, Playwright, axe, pa11y, hygiene scan, export, push, and memory updates.

## Acceptance

- Policy score history stays bounded.
- Regressions create no-send review evidence.
- Admin shows latest retention/regression state.
- No SMTP/warmup/outreach sends occur.
- Live outreach remains `0`.
- Non-Rescue projects remain untouched.
