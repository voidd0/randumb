# P4 Deliverability Diagnostics + Warmup Day 1 Report

Updated: 2026-05-26 14:02 IDT

## Decision

`CHECKOUT_READY_NOT_WARMED`

P4 runtime import and send gates were executed with owner-approved internal/external control inboxes. The system remains below `WARMUP_ACTIVE_NO_OUTREACH` because the diagnostic pass hit Mailcow/Rspamd rate limiting and inbox polling observed bounce/DSN messages.

Owner corrected one external address typo after the first diagnostic pass. The typo address was disabled and suppressed; the corrected Gmail address was imported and received one neutral diagnostic with no immediate SMTP error and no immediate bounce on the follow-up inbox poll.

After owner clarified the system must operate autonomously, regular delivery observations are handled as autonomous mail signals, not human blockers. A low-volume warmup calendar was configured instead of waiting for manual start.

## Implemented

- Approved deliverability test inbox import validation.
- Approved warmup recipient import validation.
- Diagnostic mail body normalized to neutral requested-diagnostic copy.
- Diagnostic messages now set a Message-ID and remain max one per approved test inbox.
- Warmup day-1 executor added.
- Warmup day-1 cap enforced at `5`.
- Warmup messages are neutral and contain no sales copy, no lead/audit pitch, no tracking pixel, and no audit link.
- Warmup sends write `email_events`, `system_events`, and update `warmup_runs`.
- `START WARMUP DAY=1` now executes only after all gates pass.

## Real Runtime P4 Preflight

- SPF/DKIM/DMARC: PASS
- SMTP strict TLS: PASS
- IMAP strict TLS: PASS
- Approved test inboxes: `0`
- Approved warmup recipients: `0`
- Approved test inboxes after import: `7`
- Approved warmup recipients after import: `7`
- Mail QA decision: `FAIL_BLOCK_LAUNCH`
- Mail QA issues: `deliverability_diagnostic_failed`, `bounce_detected_or_dsn_seen`
- Deliverability diagnostics: partial send, then Mailcow/Rspamd rate limit `5 / 1m`
- Corrected-address diagnostic: sent `1`, SMTP errors `0`, immediate bounce `0`
- Warmup day 1 gate: blocked
- Warmup calendar: `28` scheduled messages, `2/day`, starts after cooldown
- Inbox poll: completed
- New inbox messages seen during poll: `3`

## Sends

- Deliverability diagnostic sent count on currently approved pool: `7`
- Total diagnostic rows including disabled typo address: `8`
- Warmup sent count: `0`
- Live outreach sent count: `0`
- Bounce count: `2`
- Spam signal count: `0` observed; placement cannot be measured without test inboxes.

## Runtime Import

- `TEST_INBOX_POOL` import accepted: `7`
- `TEST_INBOX_POOL` import rejected: `0`
- `WARMUP_RECIPIENT_POOL` import accepted: `7`
- `WARMUP_RECIPIENT_POOL` import rejected: `0`

Provider-level pool:

- internal control: `4`
- Gmail: `2`
- typo custom domain: disabled and suppressed
- Clalit corporate: `1`

Raw recipient addresses are intentionally not repeated in this report.

## Verification

- API tests: `37 passed`
- Smoke script: last full smoke before pool send PASS; focused post-fix API tests PASS, `37 passed`
- DB live counters after tests:
- approved test inboxes: `7`
- approved warmup recipients: `7`
- outreach sent: `0`
- warmup sent events: `0`

## Blockers

- Mailcow/Rspamd rate limit was hit during diagnostics.
- Inbox poll observed bounce/DSN messages after the diagnostic attempt.
- Warmup is throttled to `2/day` through the autonomous calendar to avoid repeat rate-limit bursts.

No cold outreach was sent. No warmup was sent. No sales copy was sent.
