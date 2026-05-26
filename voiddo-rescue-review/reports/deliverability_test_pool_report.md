# Deliverability Test Pool Report

Updated: 2026-05-26 13:52 IDT

## Status

Owner-approved deliverability test inbox pool is configured in DB. It contains internal controls plus external control providers.

## Implemented

- `TEST_INBOXES` and `TEST_INBOX_POOL` runtime config support.
- `test_inboxes` DB table with `approved=true` and `source=owner_provided` tracking.
- Protected API endpoint: `POST /deliverability/test-inboxes/import`.
- Import validation rejects invalid and suppressed addresses.
- `deliverability_agent` sends only to approved test inboxes.
- Policy: max one neutral diagnostic message per approved mailbox.
- Diagnostic content contains no sales copy, no audit link, and no tracking pixel.

## Current Preflight

- Approved test inboxes: `7`
- Runtime import accepted: `7`
- Runtime import rejected: `0`
- SMTP strict TLS: `PASS`
- IMAP strict TLS: `PASS`
- SPF/DKIM/DMARC: `PASS`
- Deliverability diagnostic sends on currently approved pool: `7`
- Total diagnostic rows including disabled typo address: `8`
- Cold outreach sends: `0`
- Bounce count after inbox poll: `2`

Provider-level status:

- internal control: `4` approved, local delivery accepted/saved
- Gmail: `2` approved, remote SMTP accepted by Gmail for the correction diagnostic
- typo custom domain: disabled and suppressed after owner correction
- Clalit corporate: `1` approved, accepted/pending observation

Correction note:

- One owner-provided address had a domain typo. It was disabled from test and warmup pools, suppressed, and replaced with the corrected Gmail address.
- Corrected Gmail diagnostic sent: `1`
- Corrected Gmail immediate SMTP errors: `0`
- Corrected Gmail immediate bounce poll: `0`

## Decision

`FAIL_BLOCK_LAUNCH`

Blocking reasons:

- `deliverability_diagnostic_failed`
- `bounce_detected_or_dsn_seen`
- Mailcow/Rspamd rate limit `5 / 1m`

External deliverability must not be marked PASS yet. Gmail SMTP acceptance is useful signal, but the pass is blocked by rate-limit and bounce/DSN observations.
