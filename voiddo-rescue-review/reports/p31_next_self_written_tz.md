# P31 Self-Written TZ — Mailer Ops Action Controls

Generated: 2026-05-26 22:38 IDT

## Goal

Add protected admin controls for running safe no-send mailer operations directly from the control room while preserving the current safety posture.

## Tasks

1. Add protected admin actions:
   - run customer mail simulation
   - run closed-loop executor dry-run
   - run customer transport dry-run
   - generate owner report action
2. Add visible result cards for each action.
3. Keep every action gated:
   - no raw recipients
   - no cold outreach
   - no warmup send
   - no real SMTP unless customer real-send flags and clean gates are explicitly present
4. Run Huanshu and secondary visual plugins on the updated admin page.
5. Add tests:
   - admin action controls require auth
   - controls call only no-send endpoints by default
   - payload summaries omit raw recipients
   - live outreach remains blocked
   - customer SMTP remains disabled by default
6. Update reports:
   - `reports/p31_mailer_ops_action_controls_report.md`

## Acceptance

- At least 222 tests pass.
- Huanshu PASS for authenticated admin.
- Extra visual/accessibility plugins PASS with 0 blockers.
- Real runtime customer SMTP sends remain `0`.
- Warmup sent remains `0`.
- Live outreach sent remains `0`.

