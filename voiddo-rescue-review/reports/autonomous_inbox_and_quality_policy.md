# Autonomous Inbox And Quality Policy

Generated: 2026-05-26 07:06 IDT

## Core Rule

Vøiddo Rescue owns its own mail loop. The owner should not need direct access to Rescue mailboxes for normal operations.

## Inbox Autonomy

The system must:

- Read `audit@voiddorescue.com`, `fix@voiddorescue.com`, and `support@voiddorescue.com` by IMAP.
- Classify every inbound thread.
- Apply suppression on unsubscribe.
- Send safe auto-replies only for approved categories.
- Stop automation for angry/legal/security/custom/paid/wants-call cases.
- Alert `alerts@voiddorescue.com` for unsafe categories.
- Create dashboard items and Codex tasks when action is needed.

## Email Quality Agent

Before any outbound email can leave the queue, a blocking email QA check must pass:

- spelling/readability check
- formatting check
- factual/proof-link check
- required beautiful signature
- unsubscribe link
- soft/non-threatening language
- no fake urgency
- no hidden-security-vulnerability claims
- no owner personal Gmail
- no risky/free-form generated copy outside approved templates

Current MVP has deterministic checks in `apps/api/app/email_quality.py`. Later AI-assisted review may be added, but deterministic gates remain mandatory.

## Visual QA Agent

Before any Rescue page is published:

- huanshu-design protocol is mandatory.
- frontend-design/review skills are mandatory.
- desktop screenshot required.
- mobile screenshot required.
- no overlap/no horizontal overflow check required.
- visual QA report required.

Current MVP has a publish gate in `apps/api/app/visual_quality.py`; deployment scripts must require it before live Nginx/public publish.
