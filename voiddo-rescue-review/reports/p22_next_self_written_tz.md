# P22 Self-Written TZ — Mailer Action Ledger To Safe Execution Router

Generated: 2026-05-26 20:59 IDT

## Goal

Connect the mailer autonomy ledger to a safe execution router that can prepare, simulate, and later execute allowed mail actions while proving each gate decision.

## Tasks

1. Add a `mailer_action_queue` table for prepared actions:
   - owner report
   - customer onboarding email
   - safe reply draft
   - deliverability diagnostic
   - warmup slot
   - outreach preview
2. Add `action_type`, `risk_level`, `status`, `gate_result_json`, `send_after`, `attempt_count`, and `result_json`.
3. Add a protected endpoint:
   - `GET /admin/mailer/action-queue`
   - `POST /admin/mailer/action-queue/process`
4. Router rules:
   - no cold outreach while `FIRST_LIVE_SEND_FLAG=false`
   - no auto-reply while `AUTO_REPLIES_PAUSED=true`
   - no warmup while recent bounce/DSN/rate-limit exists
   - no raw recipient addresses in reports
   - no burst sends
5. Admin UI:
   - show queued/prepared/blocked/sent counts
   - show top gate blockers
6. Tests:
   - cold outreach action remains blocked
   - safe owner report becomes prepared but not sent while mail signals block
   - warmup action blocked by recent signals
   - queue summary omits raw addresses
   - endpoint auth enforced

## Acceptance

- At least 177 tests pass.
- Mailer queue can prepare actions without sending.
- Live outreach remains `0`.
- Warmup remains `0` unless existing natural gates pass.
- Non-Rescue projects untouched.
