# DNS Required Records

Generated: 2026-05-26 06:58 IDT

## voiddo.com Nested Rescue Records

Still needed unless already added elsewhere:

| Host | Type | Value |
| --- | --- | --- |
| `app.rescue` | A | `69.62.122.223` |
| `api.rescue` | A | `69.62.122.223` |
| `audit.rescue` | A | `69.62.122.223` |
| `go.rescue` | A | `69.62.122.223` |
| `status.rescue` | A | `69.62.122.223` |

`rescue.voiddo.com` is reported as already existing and pointing to `69.62.122.223`.

## voiddorescue.com Records

Owner reported these as configured in Namecheap and live DNS readback confirms the main host records:

| Host | Type | Expected | Observed |
| --- | --- | --- | --- |
| `@` | A | `69.62.122.223` | `69.62.122.223` |
| `mail` | A | `69.62.122.223` | `69.62.122.223` |
| `go` | A | `69.62.122.223` | `69.62.122.223` |
| `track` | A | `69.62.122.223` | `69.62.122.223` |
| `www` | CNAME | `voiddorescue.com.` | `voiddorescue.com.` |
| `autoconfig` | CNAME | `mail.voiddorescue.com.` | `mail.voiddorescue.com.` |
| `autodiscover` | CNAME | `mail.voiddorescue.com.` | `mail.voiddorescue.com.` |
| `@` | MX | `10 mail.voiddorescue.com.` | `10 mail.voiddorescue.com.` |
| `@` | TXT | `v=spf1 mx ~all` | `v=spf1 mx ~all` |

## DMARC Status

Current checks no longer show the previous stray `TTL: Automatic` text. Namecheap should continue to contain exactly this value:

```text
v=DMARC1; p=none; rua=mailto:dmarc@voiddorescue.com; fo=1; adkim=r; aspf=r
```

## DKIM Record To Add

Mailcow generated DKIM selector: `dkim`

Namecheap TXT record:

| Host | Type | Value |
| --- | --- | --- |
| `dkim._domainkey` | TXT | `v=DKIM1;k=rsa;t=s;s=email;p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAwKOa2h7Hj0wWxFq/JDpaGE+TQ2ugGg4lm6lbH5nop7D0vnV5HML04UjGOPh/0c/gASIJqAMiPXmWkSRAbyOwYrXk5YkfJ8VhL6yY9JoRKDxh88yKHVsa596lqQlnUCbE1lWQpJeP0N736stt54Lw3r6hYtq5+zjrPEadC9ysDgFacmK89YDTU9PASVF9MI3sWLAGYSbcDk3za07ehPPkx2L3gkp3IY/+u9FIo1L8OltEc4E+iExffhP5A2K2vmePfbBIyP6aLbqUmOK3Brep7LtD3PLALIvw+BP0Ox4TCZemHBk3P12LX2FEFkS+bXreY8u6R2fRnOQu6nDy6zQs6QIDAQAB` |

Observed DKIM DNS: published.

## SRV

SRV records are not required for MVP. Use direct settings:

- SMTP host: `mail.voiddo.com`
- SMTP port: `587`
- IMAP host: `mail.voiddo.com`
- IMAP port: `993`
