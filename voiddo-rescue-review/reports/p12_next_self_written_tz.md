# P12 Self-Written TZ: Safe Schedule Application + Revenue Scenario Expansion

Generated: 2026-05-26 18:44 IDT

## Goal

Prepare the system to apply the provider-spaced warmup schedule automatically after the mail clean window clears, while expanding revenue scenario tests. Do not send cold outreach or force warmup.

## Tasks

1. Safe schedule application gate
   - Apply provider-spacing plan only when recent mail signals are clean.
   - Require mail QA PASS.
   - Require no due-now warmup rows.
   - Record old/new schedule map for rollback.
   - Do not send as part of application.

2. Warmup rollback support
   - Add rollback function for the latest applied spacing repair.
   - Store repair id on affected schedule rows.
   - Test rollback restores old scheduled times.

3. Revenue scenario expansion
   - Add scenario: scout import -> scan/audit -> campaign readiness -> checkout mock -> customer/fix task.
   - Add scenario: unsafe reply -> no auto-reply -> system event/review action.

4. Admin UI
   - Surface latest spacing plan counts.
   - Surface next safe action: wait, apply spacing, rerun mail QA, or scheduler ready.

## Acceptance

- At least 118 passing tests.
- Huanshu PASS.
- Extra design plugins PASS or PASS_WITH_WARNINGS with no blockers.
- Spacing application gate exists and is no-send.
- Rollback exists and is tested.
- Warmup sent remains unchanged unless scheduler naturally sends after all gates pass.
- Live outreach remains `0`.
