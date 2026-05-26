# Owner Command Inbox Report

Updated: 2026-05-26 12:45 IDT

## Implemented

Owner command processor accepts commands only from the private runtime value:

- `OWNER_COMMAND_EMAIL`

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
- `SHOW MAIL QA`
- `SHOW DELIVERABILITY`
- `SHOW WARMUP`
- `RUN DELIVERABILITY TEST`
- `START WARMUP DAY=1`

## Risk Gates

- `SAFE_AUTO`: may execute automatically.
- `MEDIUM_RISK`: may prepare a draft/action only.
- `HIGH_RISK`: creates review-required state only.

Arbitrary shell execution is not supported. Shell-like command text is classified as `HIGH_RISK`.

## Verification

- Sample `STATUS` command from `OWNER_COMMAND_EMAIL` with passing auth summary was stored as `SAFE_AUTO` / `executed`.
- Sample `RUN MAIL QA` command was stored as `MEDIUM_RISK` / `prepared` and created a mail QA action.
- Sample `RUN VISUAL QA` command was stored as `MEDIUM_RISK` / `prepared` and created a visual QA action.
- Sample `RUN SHELL rm -rf /` command was stored as `HIGH_RISK` / `review_required`.
- API command intake now generates a unique uid/message id when an owner command arrives without IMAP ids, avoiding collisions between ad-hoc command submissions.
- Tests verify `RUN SHELL` is `HIGH_RISK` and blocked for review.
- `REPORT TODAY` creates a private runtime report artifact.
- `PAUSE ALL` writes persistent runtime pause controls for scanner, outreach, warmup, auto-replies, and workers.
- `START WARMUP DAY=1` is blocked unless pool, mail QA, deliverability, and authenticated owner gates pass.
- `SEND OUTREACH` remains `HIGH_RISK` and blocked.
