# P123 Canary Scale Metric Semantics Report

Generated: 2026-05-29

## Change

The canary scale and resume planners now expose live outreach canary volume with explicit semantics:

- `smtp_sent_count`: messages accepted as sent by SMTP.
- `bounced_count`: messages later marked bounced.
- `sent_or_bounced_count`: total canary evidence volume.
- `sent_count`: retained as a backward-compatible alias for `sent_or_bounced_count`.
- `blocked_count`: now counts only active failed/blocked/transport-blocked queue rows, not historical bounced rows.

## Reason

A bounced canary message is still evidence that the canary attempted a real send, but it must not become a permanent active queue blocker after the mail-risk signal window clears. Recent bounce/DSN signals still block resume through the 24-hour mail signal gate.

## Safety

- No mail was sent.
- No warmup was forced.
- No runtime pause was cleared.
- No raw recipient addresses or secrets are included.
- Non-Rescue projects were not touched.

## Verification

Focused tests added/updated for:

- explicit sent/bounced/sent-or-bounced canary fields.
- bounced rows not counted as active blocked queue rows.
- resume planner carrying explicit canary count fields.

Runtime focused verification:

- `tests/test_p109_canary_scale_plan.py`
- `tests/test_p110_canary_next_batch_preparer.py`
- `tests/test_p118_canary_resume_plan.py`
- Result: `15 passed`

Current runtime canary counters:

- `smtp_sent_count`: 11
- `bounced_count`: 1
- `sent_or_bounced_count`: 12
- `queued_count`: 7
- `active_blocked_count`: 1

Current runtime decision remains conservative:

- Scale decision: `PAUSE_AND_REVIEW_CANARY`
- Resume decision: `KEEP_PAUSED`
- Reason: recent bounce/DSN window is still active and one active transport-blocked row remains for review.
