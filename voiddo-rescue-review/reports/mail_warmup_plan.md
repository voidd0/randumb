# Mail Warmup Plan

Generated: 2026-05-26 06:58 IDT

## Sending Domain

- Outreach domain: `voiddorescue.com`
- Cold outreach must not use `voiddo.com`.

## Caps

- Day 1 live max: 20 emails total.
- Day 2 live max: 40 emails total.
- Day 3 live max: 70 emails total.
- Per-domain max: 5 emails/hour/domain.
- No sends to bounced, unsubscribed, suppressed, excluded, or unqualified leads.

## Stop Conditions

Pause automatically if any of these occurs:

- Abnormal bounce rate.
- Complaint signal.
- Angry/legal/security accusation reply.
- Mail auth failure.
- DNS auth regression.
- Unsubscribe endpoint failure.
- Suppression-list failure.
- Global kill switch enabled.

## Required Before First Send

- DKIM record published and verified.
- DMARC value corrected.
- Mail transport TLS decision documented.
- Dry-run first batch preview generated.
- Unsubscribe endpoint live and tested.
- Suppression insert/check tested.
- Rate limits tested.
- Owner launch flag set.

## Mailboxes

- `audit@voiddorescue.com`: audit outreach and replies.
- `fix@voiddorescue.com`: fix workflow.
- `support@voiddorescue.com`: customer support.
- `alerts@voiddorescue.com`: unsafe reply/system alerts.
- `billing@voiddorescue.com`: payment/onboarding support.
- `unsubscribe@voiddorescue.com`: unsubscribe and compliance.
- `dmarc@voiddorescue.com`: aggregate DMARC reports.
- `hello@voiddorescue.com`: general identity.
