# P137 Inbox Control Signal Hygiene Report

Generated: 2026-05-29

## Change

Added `inbox_control_signal_hygiene_agent`.

The agent reclassifies warmup/diagnostic control replies that were previously stored as `human_review_required` into `control_mail_signal`.

It handles messages such as:

- requested mail delivery diagnostics
- neutral warmup checks
- "No action is required" control replies

## Safety

- It does not reclassify ordinary client replies.
- It does not auto-reply.
- It does not send mail.
- It does not expose raw previews; output uses hashes.

## Runtime Integration

The fast host core loop now runs this hygiene agent before clean-window/canary checks.

## Verification

- `tests/test_p137_inbox_control_hygiene.py`
- `tests/test_p96_autonomous_loop_scheduler.py`

