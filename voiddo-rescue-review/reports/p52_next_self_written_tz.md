# P52 Next Self-Written TZ: Mailer Digest Retention-History Admin Visibility

Generated: 2026-05-27 02:16 IDT

## Objective

Expose the owner/digest retention-history evidence in protected admin without expanding send capability.

## Tasks

1. Add admin rows under Daily Digest Evidence for `mailer_ops_retention_history` count/latest send/privacy/secrets state.
2. Add protected API tests confirming digest summary includes the retention history evidence and remains no-send.
3. Run Next build, targeted tests, full API tests, and smoke.
4. Because this changes visible admin UI, run Huanshu + Playwright desktop/mobile + axe + pa11y.
5. Clean synthetic runtime rows, keep one real no-send retention and digest evidence chain, export clean package, push, update memories.

## Acceptance

- admin digest panel surfaces retention-history evidence
- endpoint requires admin auth through existing digest summary endpoint
- raw recipients/secrets remain omitted
- warmup sent remains `0` unless natural gated timer sends later
- live outreach remains `0`
