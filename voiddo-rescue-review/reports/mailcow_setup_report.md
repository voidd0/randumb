# Mailcow Setup Report

Generated: 2026-05-26 06:58 IDT

## Actions Performed

- Safely inspected Mailcow API schema locally.
- Read Mailcow API key internally from `/opt/mailcow-dockerized/mailcow.conf` without printing it.
- Added `voiddorescue.com` domain to Mailcow because it was missing.
- Created eight requested mailboxes.
- Generated DKIM key for `voiddorescue.com`.
- Stored mailbox passwords privately in `/root/.voiddo-secrets/voiddorescue-mailboxes.env`.

## Actions Not Performed

- Did not restart Mailcow.
- Did not edit existing `voiddo.com` mailboxes or mail flows.
- Did not send any email.
- Did not modify DNS automatically.
- Did not expose passwords or API keys.

## Mailboxes

- `hello@voiddorescue.com`: created
- `audit@voiddorescue.com`: created
- `fix@voiddorescue.com`: created
- `support@voiddorescue.com`: created
- `alerts@voiddorescue.com`: created
- `billing@voiddorescue.com`: created
- `dmarc@voiddorescue.com`: created
- `unsubscribe@voiddorescue.com`: created

## DKIM

- Selector: `dkim`
- Key length: `2048`
- DNS status: not published yet

Namecheap record:

```text
Host: dkim._domainkey
Type: TXT
Value: v=DKIM1;k=rsa;t=s;s=email;p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAwKOa2h7Hj0wWxFq/JDpaGE+TQ2ugGg4lm6lbH5nop7D0vnV5HML04UjGOPh/0c/gASIJqAMiPXmWkSRAbyOwYrXk5YkfJ8VhL6yY9JoRKDxh88yKHVsa596lqQlnUCbE1lWQpJeP0N736stt54Lw3r6hYtq5+zjrPEadC9ysDgFacmK89YDTU9PASVF9MI3sWLAGYSbcDk3za07ehPPkx2L3gkp3IY/+u9FIo1L8OltEc4E+iExffhP5A2K2vmePfbBIyP6aLbqUmOK3Brep7LtD3PLALIvw+BP0Ox4TCZemHBk3P12LX2FEFkS+bXreY8u6R2fRnOQu6nDy6zQs6QIDAQAB
```

## DNS Verification

- `A voiddorescue.com`: OK
- `A mail.voiddorescue.com`: OK
- `A go.voiddorescue.com`: OK
- `A track.voiddorescue.com`: OK
- `CNAME www.voiddorescue.com`: OK
- `CNAME autoconfig.voiddorescue.com`: OK
- `CNAME autodiscover.voiddorescue.com`: OK
- `MX voiddorescue.com`: OK
- `TXT SPF`: OK
- `TXT DMARC`: published; no trailing `TTL: Automatic` observed in current checks.
- `TXT DKIM`: published.

## SMTP/IMAP Tests

- Strict TLS SMTP/IMAP login now passes via `mail.voiddo.com`.
- Rescue sending identities remain on `voiddorescue.com`.
- `voiddorescue.com` MVP mailboxes passed strict IMAP login after the TLS fix.

## Remaining Blockers

1. Provide approved deliverability test inbox pool.
2. Provide approved warmup recipient pool.
3. Configure Paddle checkout base/client flow.
