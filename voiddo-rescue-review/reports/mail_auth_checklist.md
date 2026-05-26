# Vøiddo Rescue Mail Auth Checklist

Updated: 2026-05-26 12:05 IDT

## Production Host Decision

- Sending domain: `voiddorescue.com`
- Sending identity remains: `audit@voiddorescue.com`
- Preferred production SMTP host set in runtime/example env: `mail.voiddo.com`
- Preferred production IMAP host set in runtime/example env: `mail.voiddo.com`
- `MAIL_TLS_VERIFY=true`

## DNS Status

- `A mail.voiddorescue.com`: present, points to `69.62.122.223`
- `MX voiddorescue.com`: present, points to `mail.voiddorescue.com`
- SPF: present, `v=spf1 mx ~all`
- DMARC: present, no literal `TTL: Automatic`
- DKIM: present at `dkim._domainkey.voiddorescue.com` (value redacted here; public TXT exists)
- `autoconfig`: present
- `autodiscover`: present
- SRV: skipped for MVP per owner instruction

## Strict TLS Login

- SMTP strict TLS login using `mail.voiddo.com:587`: PASS after P2 Mailcow TLS fix.
- IMAP strict TLS login using `mail.voiddo.com:993`: PASS after P2 Mailcow TLS fix.

## Launch Gate

Live outreach remains blocked until approved deliverability test inbox pool, warmup recipient pool, and Paddle checkout config pass.

Current safety flags:

- `OUTREACH_DRY_RUN=true`
- `OUTREACH_PAUSED=true`
- `AUTO_REPLIES_PAUSED=true`
- `FIRST_LIVE_SEND_FLAG=false`
- No warmup started
- No live outreach sent
