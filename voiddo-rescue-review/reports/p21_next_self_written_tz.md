# P21 Self-Written TZ — Autonomous Mailer Closed-Loop Execution Evidence

Generated: 2026-05-26 20:47 IDT

## Goal

Strengthen the fully autonomous mailer loop so every inbound message, outbound candidate, owner instruction, warmup slot, diagnostic, and customer email is processed through one evidence-backed control layer.

## Tasks

1. Add a mailer event ledger summary that joins inbound threads, email events, mail signals, throttle state, warmup schedule, owner commands, and outbound preview decisions.
2. Add a protected `/admin/mailer/autonomy-ledger` endpoint and an admin dashboard panel.
3. Ensure the ledger proves:
   - no cold outreach is sent while `OUTREACH_PAUSED=true` or `FIRST_LIVE_SEND_FLAG=false`
   - auto-replies remain paused unless explicitly enabled
   - owner commands from the approved owner address are parsed and gated
   - recent bounce/DSN/rate-limit signals block diagnostics and warmup
   - customer/payment/onboarding email tasks are prepared but still pass mailer gates
4. Add tests:
   - ledger reports live outreach `0`
   - ledger reports warmup `0` when risk signals block
   - ledger includes owner command, inbound, outbound preview, and throttle sections
   - ledger never includes raw recipient addresses
5. Run QA:
   - pytest
   - smoke
   - Huanshu
   - extra visual/design plugins

## Acceptance

- At least 172 tests pass.
- Admin shows autonomous mailer ledger.
- Reports do not expose raw recipient addresses.
- Live outreach remains `0`.
- Warmup remains `0` unless the existing natural timer later passes all gates.
- Non-Rescue projects untouched.
