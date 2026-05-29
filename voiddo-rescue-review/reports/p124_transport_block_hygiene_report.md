# P124 Transport Block Hygiene Report

Generated: 2026-05-29

## Change

Added `outreach_transport_block_hygiene_agent` to recover outreach rows that were consumed by a pause/live-flag gate before the worker pause-preservation fix existed.

The agent:

- Requeues only `transport_blocked` rows whose latest transport event shows a pause/dry-run/live-approval gate.
- Keeps suppressed, malformed, unknown, and true preflight-failed rows blocked.
- Emits redacted system events only.
- Sends no mail and does not clear runtime pauses.

Added protected endpoint:

- `POST /admin/outreach/live-queue/transport-block-hygiene`

Added owner command:

- `SHOW TRANSPORT BLOCK HYGIENE`

## Runtime Result

The runtime queue had one pause-gate `transport_blocked` canary row. Hygiene restored it to `queued`, while `pause_outreach` remained enabled.

Current runtime evidence:

- `smtp_sent_count`: 11
- `bounced_count`: 1
- `sent_or_bounced_count`: 12
- `queued_count`: 8
- `active_blocked_count`: 0
- Resume decision: `KEEP_PAUSED`
- Remaining blockers: recent bounce/DSN risk window and canary scale readiness.

Queued campaign preflight validation was also aligned to staged-queue semantics: queued rows now require an existing current-policy PASS preflight within the last 24 hours, instead of using the latest post-bounce preflight failure caused by global mailer policy.

## Verification

- `tests/test_p124_transport_block_hygiene.py`
- `tests/test_p109_canary_scale_plan.py`
- `tests/test_p118_canary_resume_plan.py`
- Result: `16 passed` for the hygiene/scale/resume focused suite, then `10 passed` for the resume/hygiene regression suite after the queued-preflight semantic alignment.

## Safety

- No cold outreach was sent.
- No warmup was forced.
- `pause_outreach` was not cleared.
- No raw recipient addresses or secrets are included.
- Non-Rescue projects were not touched.

