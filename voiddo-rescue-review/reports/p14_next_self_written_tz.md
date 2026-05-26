# P14 Self-Written TZ: Mailer Clean-Window Execution + Customer Journey Hardening

Generated: 2026-05-26 19:13 IDT

## Goal

When the delivery-risk window clears, let the autonomous mailer recover safely and prepare the next customer journey improvements. Do not send cold outreach and do not force warmup.

## Tasks

1. Clean-window execution check
   - Detect when bounce/DSN/rate-limit counts are zero for 24h.
   - Rerun mail QA without diagnostics.
   - Apply provider spacing if safe.
   - Record recovery result.

2. Admin mailer control room
   - Show latest mailer status, lessons, clean-window recovery status, and next safe action.
   - Keep live outreach blocked in UI.

3. Customer journey scenario hardening
   - Extend scenario tests from Paddle paid mock to customer dashboard and fix task visibility.
   - Verify onboarding task is visible through admin/customer surfaces.

4. Reply handling hardening
   - Add scenario tests for interested, ask_price, unsubscribe, angry, legal/security, and wrong_person replies.
   - Confirm safe auto-replies remain paused unless explicitly enabled.

5. Reports
   - Update runtime, launch, smoke, mailer, and blocker reports.
   - Export a clean review package.

## Acceptance

- At least 132 passing tests.
- Huanshu PASS.
- Extra QA plugins PASS or non-blocking warning only.
- Clean-window recovery remains no-send.
- Customer journey scenario is stronger.
- Warmup sent remains `0` unless existing timer naturally sends after gates pass.
- Live outreach remains `0`.
- Non-Rescue projects untouched.

