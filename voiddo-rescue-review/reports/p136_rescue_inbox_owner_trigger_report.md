# P136 Rescue Inbox Owner Trigger Report

Generated: 2026-05-29

## Change

Rescue mailbox polling now treats messages from configured owner addresses as command input instead of ordinary prospect/customer replies.

When `audit@`, `fix@`, or `support@voiddorescue.com` receives an owner message:

- the worker classifies it as `owner_command`;
- the worker submits it to protected API endpoint `/owner/commands`;
- the message is not persisted as a client `human_review_required` inbox thread;
- no auto-reply is sent.

If the protected API submission fails, the worker records `owner_command_api_failed` without exposing the raw owner address.

## Command Alias

Russian owner alias added:

- `Не спамь` / `СТОП СПАМ` / `СТОП РАССЫЛКА` / `СТОП РАССЫЛКУ` -> `PAUSE OUTREACH`

This makes the owner's personal mailbox usable as a direct operational trigger for Rescue mailboxes, not only the main studio mailbox.

## Safety

- No shell execution is introduced.
- High-risk owner commands remain review-gated.
- Cold outreach remains gated by existing launch flags and clean-window checks.
- Auto-replies remain paused unless explicitly enabled elsewhere.

## Verification

- Worker owner-routing tests: `10 passed`
- API owner-command/launch-gate tests: `21 passed`

