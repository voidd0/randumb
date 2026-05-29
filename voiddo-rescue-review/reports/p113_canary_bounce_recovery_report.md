# P113 Canary Bounce Recovery Report

Generated: 2026-05-29 13:46 IDT

## Status

- Live outreach canary remains paused.
- `pause_outreach=true`.
- No extra outreach or warmup sends were started by this pass.
- Raw recipient addresses, mailbox passwords and message bodies are not included.

## Runtime Evidence

- Recent bounce/DSN signals, 24h: `3`
- DSN backfill processed: `3`
- DSN backfill enriched: `3`
- Suppression upsert attempts: `3`
- DSNs linked to original outreach message: `1`
- Linked outreach rows marked bounced: `1`
- DSNs still unlinked: `2`
- Blocked/bounced outreach rows present: `2`
- Recovery decision: `KEEP_PAUSED_RECOVER_BOUNCES`
- Canary scale decision: `PAUSE_AND_REVIEW_CANARY`
- Provider output is bucketed as `other_external`; private recipient domains are not reported.

## Code Changes

- Added `apps/api/app/canary_bounce_recovery.py`
- Added protected admin routes:
  - `GET /admin/outreach/bounce-recovery`
  - `POST /admin/outreach/bounce-recovery/run`
  - `POST /admin/outreach/bounce-dsn-backfill`
- Added autonomous agents:
  - `canary_bounce_recovery_agent`
  - `bounce_dsn_backfill_agent`
- Linked DSNs now mark matching `outreach_messages` and `leads` as `bounced`.
- Canary scale treats `bounced` as part of the canary count and also as a stop/block state.
- Added SAFE_AUTO owner command:
  - `SHOW CANARY BOUNCE RECOVERY`
- Added tests in `apps/api/tests/test_p112_canary_bounce_recovery.py`

## Verification

- Focused container tests: `22 passed`
- Runtime recovery run: completed and kept canary paused.
- API rebuilt and healthy.
- Non-Rescue projects untouched.
