# P125 Autonomous Canary Resume Gate Report

Generated: 2026-05-29

## Change

The bounded daily autonomous loop now calls `canary_resume_plan_agent` with `apply=true`.

This does not send mail directly. It only allows the agent to clear `pause_outreach` after all resume gates pass:

- no bounce/DSN in the configured clean window.
- no rate-limit, spam, auth, TLS, DKIM, or DMARC signal in the clean window.
- mail QA is `PASS`.
- mail send compliance is `PASS`.
- canary scale is ready or continuing.
- queued campaign context has current-policy PASS preflight evidence.
- queued campaign context is not missing.

## Current Runtime Result

The agent still returns `KEEP_PAUSED` today because recent bounce/DSN signals are inside the 24-hour window.

Current state:

- `smtp_sent_count`: 11
- `bounced_count`: 1
- `sent_or_bounced_count`: 12
- `queued_count`: 8
- `active_blocked_count`: 0
- `pause_outreach`: remains enabled

## Safety

- No cold outreach was sent by this change.
- No warmup was forced.
- `FIRST_LIVE_SEND_FLAG` was not changed.
- `pause_outreach` can only be cleared by the agent after all gates pass.
- Non-Rescue projects were not touched.

