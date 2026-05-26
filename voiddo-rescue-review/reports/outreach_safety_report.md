# Vøiddo Rescue Outreach Safety Report

Generated: 2026-05-26

Current state:
- Live outreach: paused
- Dry-run mode: enabled
- First live send flag: disabled
- Auto-replies: paused
- Inbox worker: disabled by default until mail auth/TLS blockers are cleared

Safety gates implemented:
- Template-based emails only.
- Email QA gate checks risky phrases, unsubscribe presence, signature, and basic meaning/format constraints.
- Localized template structure prepared for English, Hebrew, and Estonian.
- Suppression endpoint exists.
- Unsubscribe endpoint exists.
- Rate-limit guard blocks sending while outreach is paused.
- Global kill switch and per-worker pause flags exist.
- Inbox classifier marks unsafe categories for human review/no auto-reply.

Safe auto-reply categories:
- `ask_price`
- `ask_details`
- `wrong_person`
- `out_of_office`
- `unsubscribe`

Never auto-reply categories:
- `angry`
- `legal_threat`
- `security_accusation`
- `custom_technical_request`
- `wants_call`
- confused/paid-customer cases

Dry-run preview checked:
- Subject: `Possible issue on Example Dental website`
- Body includes specific issue, audit URL, prices, signature, public-check legal note, and unsubscribe URL.
- Generated preview passed email QA.

Launch blockers:
- Approved deliverability test inbox pool is missing.
- Approved warmup recipient pool is missing.
- Paddle checkout config is missing.
- Live sending must remain disabled until deliverability diagnostics, warmup prep, suppression, unsubscribe, rate limits, visual gate, and Paddle checkout tests all pass on public domains.
