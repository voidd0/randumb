# P13 Self-Written TZ: Autonomous Mailer Completion + Clean-Window Recovery

Generated: 2026-05-26 18:58 IDT

## Goal

Finish the autonomous mailer loop so Vøiddo Rescue can safely operate mail, warmup, owner commands, reply handling, reports, and future outreach without manual mailbox access. Do not send cold outreach and do not force warmup.

## Tasks

1. Autonomous mailer control plane
   - Add a single mailer status endpoint/report combining mail QA, signals, throttle, warmup, inbox, owner commands, and campaign gates.
   - Make the admin dashboard show the next safe mail action.
   - Keep all live-send flags blocked by default.

2. Clean-window recovery automation
   - When the 24h bounce/rate-limit window clears, rerun mail QA without diagnostic sends.
   - If PASS, run provider-spacing apply gate.
   - Do not start warmup automatically unless the scheduler slot is naturally due and every pre-send gate passes.

3. Mail signal learning
   - Convert bounce/DSN/rate-limit patterns into persistent lessons.
   - Prevent future diagnostic bursts by learning provider spacing and throttle state.
   - Keep raw recipient addresses out of public reports and review exports.

4. Email QA hardening
   - Re-run QA on all outbound templates.
   - Confirm no AI/operator/build-process language appears.
   - Confirm studio-only voice: `Vøiddo Rescue`.
   - Confirm every customer/outreach mail has clean plain text, safe copy, signature, unsubscribe where required, and no risky claims.

5. Scenario expansion
   - Add tests for clean-window transition -> spacing apply -> rollback.
   - Add tests for inbound owner command -> mailer status report.
   - Add tests for bounce learning preventing future sends.
   - Keep SEND OUTREACH high-risk and blocked.

## Acceptance

- At least 124 passing tests.
- Huanshu PASS.
- Extra QA plugins PASS or non-blocking warning only.
- Autonomous mailer status report exists.
- Clean-window recovery is no-send and gated.
- Warmup sent remains `0` unless the existing timer naturally sends after all gates pass.
- Live outreach remains `0`.
- Non-Rescue projects untouched.

