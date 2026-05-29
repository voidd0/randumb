# P128 DSN Recipient-Hash Linking Report

Generated: 2026-05-29

## Change

Bounce/DSN recovery can now link a DSN to an outreach row even when the DSN lacks the original outbound `Message-ID`, as long as the failed recipient can be extracted.

Behavior:

- First match by original outbound `Message-ID`.
- If missing, match by failed recipient to the latest sent/bounced outreach row for that lead.
- Runtime recovery also reports `hash_linked_sent_message_count` and redacted hash-linked samples.

## Reason

Some DSN messages omit or mangle the original message ID. Recipient-hash linking lets the system learn from those failures and mark affected leads/outreach rows without exposing raw addresses in reports.

## Safety

- No mail was sent.
- No pause was cleared.
- Public/review output stays redacted.
- Non-Rescue projects were not touched.

