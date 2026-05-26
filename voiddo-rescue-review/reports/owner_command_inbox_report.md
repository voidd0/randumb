# Owner Command Inbox Report

Updated: 2026-05-26 13:00 IDT

## Implemented

Owner command processor accepts commands only from the private runtime value `OWNER_COMMAND_EMAIL`.

It records mailbox, uid, message-id, sender, reply-to, subject/body, parsed command, arguments, risk level, status, authentication summary, result JSON, and system events.

## Supported P4 Commands

- `STATUS`
- `REPORT TODAY`
- `SHOW MAIL QA`
- `SHOW DELIVERABILITY`
- `SHOW WARMUP`
- `PAUSE ALL`
- `RUN DELIVERABILITY TEST`
- `PREPARE WARMUP`
- `START WARMUP DAY=1`

`SEND OUTREACH` remains `HIGH_RISK` and blocked.

## Risk Gates

- `SAFE_AUTO`: may execute controlled read/report/pause actions.
- `MEDIUM_RISK`: may run controlled QA or warmup prep/start gates with no cold outreach.
- `HIGH_RISK`: creates review-required state only.

Arbitrary shell execution is not supported. Shell-like command text is classified as `HIGH_RISK`.

## P4 Verification

- `STATUS` returns metrics.
- `REPORT TODAY` creates a private runtime report.
- `PAUSE ALL` writes runtime controls and test cleanup prevents hidden pause state from leaking into the working DB.
- `RUN DELIVERABILITY TEST` runs mail QA/deliverability preflight.
- `START WARMUP DAY=1` has a real send executor, but real runtime is blocked because approved pools are missing.
- Test coverage verifies day-1 warmup sends max five messages only when all gates are mocked PASS.
- `RUN SHELL` remains review-required.
