# P120 Bounce Domain Suppression Report

Generated: 2026-05-29T14:25:24+03:00

## Objective

Make DSN bounce recovery more autonomous by suppressing recipient domains when a delivery-status notification proves `domain_not_found`, while keeping all reporting redacted.

## Changes

- `bounce_dsn_backfill_agent` now upserts `suppression_list.domain` with source `inbox_bounce_domain` for `domain_not_found` DSNs.
- Exact bounced recipient suppression remains in place.
- Canary bounce recovery output no longer includes raw linked audit domains; it emits hashes and booleans only.

## Runtime Result

- Recent `inbox_bounce_domain` suppression rows: `2`.
- Canary bounce recovery remains `KEEP_PAUSED_RECOVER_BOUNCES`.
- `pause_outreach` remains enabled.
- No live outreach sent.

## Verification

- Bounce recovery tests: `6 passed`.
- Runtime recovery redaction check: no raw `domain` field in linked sample, hashed audit-domain evidence present.
