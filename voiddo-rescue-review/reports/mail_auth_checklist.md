# Mail Auth Checklist

Generated: 2026-05-26 06:58 IDT

## Domain

- Mail domain: `voiddorescue.com`
- Mailcow domain status: created
- Existing `voiddo.com` mail flow: not modified
- Mailcow restart: not performed

## Mailboxes

Created or verified in Mailcow:

- `hello@voiddorescue.com`
- `audit@voiddorescue.com`
- `fix@voiddorescue.com`
- `support@voiddorescue.com`
- `alerts@voiddorescue.com`
- `billing@voiddorescue.com`
- `dmarc@voiddorescue.com`
- `unsubscribe@voiddorescue.com`

Passwords are stored locally in:

- `/root/.voiddo-secrets/voiddorescue-mailboxes.env`

Passwords were not printed in terminal output or reports.

## DNS Auth

- SPF: published and correct: `v=spf1 mx ~all`
- DMARC: published, but needs cleanup because DNS currently includes trailing `TTL: Automatic` inside the TXT value.
- DKIM: generated in Mailcow, not yet published in DNS.

Required DKIM:

```text
Host: dkim._domainkey
Type: TXT
Value: v=DKIM1;k=rsa;t=s;s=email;p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAwKOa2h7Hj0wWxFq/JDpaGE+TQ2ugGg4lm6lbH5nop7D0vnV5HML04UjGOPh/0c/gASIJqAMiPXmWkSRAbyOwYrXk5YkfJ8VhL6yY9JoRKDxh88yKHVsa596lqQlnUCbE1lWQpJeP0N736stt54Lw3r6hYtq5+zjrPEadC9ysDgFacmK89YDTU9PASVF9MI3sWLAGYSbcDk3za07ehPPkx2L3gkp3IY/+u9FIo1L8OltEc4E+iExffhP5A2K2vmePfbBIyP6aLbqUmOK3Brep7LtD3PLALIvw+BP0Ox4TCZemHBk3P12LX2FEFkS+bXreY8u6R2fRnOQu6nDy6zQs6QIDAQAB
```

## SMTP/IMAP

Requested direct config:

- SMTP: `mail.voiddorescue.com:587`
- IMAP: `mail.voiddorescue.com:993`

Login tests:

- Strict TLS verification: failed due current Mailcow mail-service certificate.
- Diagnostic auth test with TLS verification disabled: passed for `audit@voiddorescue.com` and `support@voiddorescue.com` over SMTP and IMAP.

Current certificate readback on IMAP:

- Subject/CN: `mail.voiddo.com`
- Issuer/CN: `mail.voiddo.com`
- No SubjectAltName extension
- Validity: 2026-04-19 to 2027-04-19

This means mailbox credentials work, but strict TLS clients will reject `mail.voiddorescue.com` until the Mailcow mail-service certificate is updated to cover that hostname with a trusted cert.

## MVP Gate

Do not send live outreach until:

- DKIM TXT is published.
- DMARC TXT is corrected.
- DNS has propagated.
- SMTP/IMAP production configuration is accepted by the app with an explicit TLS policy.
- Suppression, unsubscribe, and rate-limit tests pass.
