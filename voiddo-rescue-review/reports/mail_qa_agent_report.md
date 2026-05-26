# Mail QA Agent Report

Updated: 2026-05-26 13:55 IDT

## Host Decision

- SMTP host: `mail.voiddo.com`
- IMAP host: `mail.voiddo.com`
- TLS verification: `true`
- Rescue sending identity remains `audit@voiddorescue.com`.

## Current Agent Results

- `dns_mail_auth_agent`: PASS
- `smtp_agent`: PASS
- `imap_agent`: PASS
- `reply_classifier_agent`: PASS
- `outreach_safety_agent`: PASS
- `deliverability_agent`: FAIL_BLOCK_LAUNCH

## DNS Checks

- A/MX/SPF/DKIM/DMARC/autoconfig/autodiscover records are present.
- DKIM TXT has propagated. The public key is intentionally not repeated here.
- DMARC no longer contains literal `TTL: Automatic`.

## Strict TLS Checks

- SMTP strict TLS login: PASS.
- IMAP strict TLS login: PASS.

## P4 Preflight

Latest real mail QA run:

- Decision: `FAIL_BLOCK_LAUNCH`
- Issues: `deliverability_diagnostic_failed`, `bounce_detected_or_dsn_seen`
- Approved test inboxes: `7`
- Deliverability diagnostic sends: `7`
- Inbox poll after runtime gate: PASS, `3` messages seen
- Bounce count after poll: `2`
- Warmup sent: `0`

## Safety State

- Live outreach sent: `0`
- Warmup sent: `0`
- Customer-facing auto-replies remain paused.

## Decision

`FAIL_BLOCK_LAUNCH`

Exact blocker: Mailcow/Rspamd rate limit and bounce/DSN observation after diagnostics.
