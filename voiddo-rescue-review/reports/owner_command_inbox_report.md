# Owner Command Inbox Report

Updated: 2026-05-26 IDT

## Implemented

Owner command processor accepts commands only from:

- `gkorner@gmail.com`

It records:

- mailbox
- uid
- message-id
- sender
- reply-to
- subject/body
- parsed command
- arguments
- risk level
- status
- authentication summary
- result JSON

## Supported Commands

- `STATUS`
- `REPORT TODAY`
- `PAUSE OUTREACH`
- `PAUSE WARMUP`
- `PAUSE SCANNER`
- `PAUSE AUTO REPLIES`
- `PAUSE ALL`
- `RUN VISUAL QA`
- `RUN MAIL QA`
- `PREPARE WARMUP`
- `SHOW HUMAN REVIEW`
- `SHOW PAYMENTS`
- `SHOW REPLIES`
- `PREPARE LEADS COUNTRY=... NICHE=... LIMIT=...`

## Risk Gates

- `SAFE_AUTO`: may execute automatically.
- `MEDIUM_RISK`: may prepare a draft/action only.
- `HIGH_RISK`: creates review-required state only.

Arbitrary shell execution is not supported. Shell-like command text is classified as `HIGH_RISK`.

## Verification

- Sample `STATUS` command from `gkorner@gmail.com` with passing auth summary was stored as `SAFE_AUTO` / `executed`.
- Tests verify `RUN SHELL` is `HIGH_RISK` and blocked for review.
