# P11 Self-Written TZ: Sender Rotation Repair + Warmup Scheduler Precision

Generated: 2026-05-26 18:34 IDT

## Goal

Fix the readiness issues discovered by P10 without sending mail manually. Sender rotation should become able to plan provider-spaced warmup slots once the clean window clears.

## Tasks

1. Provider-spaced warmup calendar
   - Add schedule planner that avoids same-provider adjacent slots where possible.
   - Prefer owner mailbox only when policy allows, but do not create provider bursts.
   - Do not send; only reschedule future unsent slots if safe and reversible.

2. Sender health depth
   - Split mailbox health by sender mailbox instead of global recent signal only.
   - Keep global recent signal as hard blocker.
   - Add credential/source diagnostics with redacted outputs.

3. Clean-window post-clear path
   - When signals clear, rerun no-send mail QA.
   - If PASS, mark warmup scheduler ready.
   - Do not send immediately from the transition agent.

4. Scenario tests
   - Add provider-spacing repair tests.
   - Add clean-window post-clear transition tests with no sends.
   - Add mailbox health tests for per-mailbox signals.

5. Admin UI
   - Show latest clean-window transition status.
   - Show sender rotation status and next safe action.

## Acceptance

- At least 112 passing tests.
- Huanshu PASS.
- Extra visual/design plugins PASS or PASS_WITH_WARNINGS with no blockers.
- Provider spacing planner exists.
- Clean-window transition remains no-send.
- Warmup sent remains unchanged unless the scheduler naturally sends after all gates pass.
- Live outreach remains `0`.
