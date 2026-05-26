# P10 Self-Written TZ: Mail Clean Window + Campaign Scenario Depth

Generated: 2026-05-26 18:24 IDT

## Goal

Keep improving toward a revenue-ready autonomous system without sending cold outreach. P10 should deepen scenario coverage and make the mail clean-window transition automatic: when the 24-hour bounce/rate-limit window clears, the system should rerun mail QA, re-score campaign readiness, and prepare warmup/campaign previews without enabling live outreach.

## Tasks

1. Mail clean-window transition
   - Add clean-window scheduler state.
   - If no bounce/DSN/rate-limit/spam signals remain, automatically rerun mail QA.
   - If mail QA passes, mark warmup as ready for scheduler-only send, not manual force-send.

2. Campaign scenario depth
   - Add scenario tests for scout -> campaign readiness -> outbound decision refusal.
   - Add scenario tests for interested reply -> action plan -> onboarding/fix task after mocked checkout.

3. Campaign UI
   - Show campaign readiness snapshots in admin.
   - Show top blockers and next safe action.

4. Mailer autonomy
   - Add mailbox health score.
   - Add sender rotation readiness.
   - Add provider-spacing readiness.
   - Keep all sends blocked while recent mail signals exist.

5. Quality gates
   - Keep Huanshu canonical PASS requirement.
   - Keep axe/pa11y/pixelmatch/Lighthouse secondary gates.
   - Maintain at least 105 passing tests.

## Acceptance

- Clean-window transition exists and does not send by itself.
- Campaign readiness is visible in admin.
- Mailer health and sender readiness exist.
- Tests pass.
- Huanshu and extra plugins pass.
- Warmup sent remains `0` unless scheduler naturally sends after all gates pass.
- Live outreach remains `0`.
