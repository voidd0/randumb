# Mail QA Agent Report

Updated: 2026-05-26 12:45 IDT

## Host Decision

- SMTP host: `mail.voiddo.com`
- IMAP host: `mail.voiddo.com`
- TLS verification: `true`
- Sending identities remain on `voiddorescue.com`, e.g. `audit@voiddorescue.com`

## TLS Fix

Strict TLS previously failed because Mailcow presented a self-signed certificate. P2 fixed this by copying the existing trusted Let’s Encrypt certificate for `mail.voiddo.com` into Mailcow `data/assets/ssl/` and restarting only:

- `postfix-mailcow`
- `dovecot-mailcow`
- `nginx-mailcow`

Mailcow config discovery:

- `MAILCOW_HOSTNAME=mail.voiddo.com`
- `SKIP_LETS_ENCRYPT=y`
- `ADDITIONAL_SAN=`

Current served certificate:

- Subject/CN: `mail.voiddo.com`
- Issuer: Let’s Encrypt E7
- OpenSSL verify return code: `0 (ok)`

## Agent Results

- `dns_mail_auth_agent`: PASS
- `smtp_agent`: PASS
- `imap_agent`: PASS
- `deliverability_agent`: FAIL_BLOCK_LAUNCH
- `reply_classifier_agent`: PASS
- `outreach_safety_agent`: PASS

## DNS Checks

- A/MX/SPF/DKIM/DMARC/autoconfig/autodiscover records are present.
- DKIM TXT has propagated. The public key is not repeated in this report.
- DMARC does not contain literal `TTL: Automatic`.

## Strict Login Checks

- SMTP strict TLS login: PASS.
- IMAP strict TLS login: PASS.

## Mailbox Checks

- Rescue `audit@voiddorescue.com`: strict SMTP/IMAP login PASS via app mail QA.
- All `voiddorescue.com` MVP mailboxes: strict IMAP login PASS.
- Existing `em@voiddo.com`: strict SMTP/IMAP login PASS.

## Remaining Blocker

Approved deliverability test inbox pool is missing.

## Decision

`FAIL_BLOCK_LAUNCH`

Latest agent run: `FAIL_BLOCK_LAUNCH` with only `approved_test_inbox_pool_missing`.

P3 checkout is ready, but mail launch gate remains blocked until an approved deliverability test inbox pool exists.

Live outreach remains blocked until the approved test inbox pool exists and deliverability diagnostics are run.
