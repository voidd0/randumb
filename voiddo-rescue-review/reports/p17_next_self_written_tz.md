# P17 Self-Written TZ — Mailer Autonomy Control Room + Monitoring Evidence

Generated: 2026-05-26 19:55 IDT

## Goal

Make the autonomous mailer and monitoring surfaces easier to operate without owner mailbox access, while keeping sends blocked until recent mail signals clear.

## Tasks

1. Add admin control-room sections for:
   - monitoring due targets
   - latest monitoring runs
   - mailer status snapshots
   - mail signal lessons
   - clean-window recovery state
2. Add API summary endpoint for safe mailer autonomy state:
   - latest mail QA
   - recent bounce/DSN count
   - recent rate-limit count
   - next allowed action
   - warmup blocked/unblocked reason
3. Add autonomous inbox/report path:
   - daily status report to owner only after strict mail gates allow safe report sending
   - otherwise report file only
4. Add tests:
   - admin mailer summary auth
   - monitoring summary auth
   - no owner report email sent while recent signals block mail
   - clean-window recovery stays no-send
5. Run:
   - full pytest
   - smoke
   - Huanshu + extra design QA plugins

## Acceptance

- At least 148 tests pass.
- Live outreach remains `0`.
- Warmup sent remains `0` unless an existing scheduled worker naturally passes all gates.
- No non-Rescue projects touched.
- Reports honestly keep launch below live-ready while mail signals remain recent.
