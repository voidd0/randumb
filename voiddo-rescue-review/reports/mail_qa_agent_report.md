# Mail QA Agent Report

Updated: 2026-05-26 11:10 IDT

## Host Decision

- SMTP host: `mail.voiddo.com`
- IMAP host: `mail.voiddo.com`
- TLS verification: `true`
- Sending identities remain on `voiddorescue.com`, e.g. `audit@voiddorescue.com`

## TLS Root Cause

Strict TLS fails because Mailcow presents a self-signed certificate:

- Subject/CN: `mail.voiddo.com`
- Issuer: same self-signed Mailcow certificate
- OpenSSL verify return code: `18 (self-signed certificate)`

Mailcow config discovery:

- `MAILCOW_HOSTNAME=mail.voiddo.com`
- `SKIP_LETS_ENCRYPT=y`
- `ADDITIONAL_SAN=`

## Agent Results

- `dns_mail_auth_agent`: PASS
- `smtp_agent`: FAIL_BLOCK_LAUNCH
- `imap_agent`: FAIL_BLOCK_LAUNCH
- `deliverability_agent`: FAIL_BLOCK_LAUNCH
- `reply_classifier_agent`: PASS
- `outreach_safety_agent`: PASS

## DNS Checks

- A/MX/SPF/DKIM/DMARC/autoconfig/autodiscover records are present.
- DKIM TXT has propagated. The public key is not repeated in this report.
- DMARC does not contain literal `TTL: Automatic`.

## Strict Login Checks

- SMTP strict TLS login: FAIL, certificate verification error.
- IMAP strict TLS login: FAIL, certificate verification error.

## Exact Fix Path

Do not disable TLS verification.

Fix Mailcow certificate by enabling a trusted certificate for `mail.voiddo.com` and, if desired, `mail.voiddorescue.com`:

1. Set `SKIP_LETS_ENCRYPT=n` in Mailcow config or install a trusted certificate into Mailcow's expected SSL path.
2. If using the Rescue mail hostname, set `ADDITIONAL_SAN=mail.voiddorescue.com`.
3. Run Mailcow ACME/certificate renewal following Mailcow procedure.
4. Restart/reload only the Mailcow services required by Mailcow's certificate procedure.
5. Re-run `smtp_agent` and `imap_agent`.

No Mailcow restart or certificate mutation was performed in this pass.

## Decision

`FAIL_BLOCK_LAUNCH`

Latest agent run: `FAIL_BLOCK_LAUNCH` with `smtp_strict_tls_login_failed`, `imap_strict_tls_login_failed`, and `approved_test_inbox_pool_missing`.

Live outreach remains blocked. Mailcow certificate repair requires explicit approval before touching the shared Mailcow runtime.
