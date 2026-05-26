# P51 Next Self-Written TZ: Mailer Retention History Daily Loop Evidence

Generated: 2026-05-27 02:04 IDT

## Objective

Wire retention-history evidence into the autonomous daily loop and owner/reporting digest without sending email, so the mailer can prove daily self-maintenance over time.

## Tasks

1. Include latest `mailer_ops_retention_reports` metadata in `mailer_digest_summary()` and owner status report file.
2. Add tests that daily loop creates/retains one no-send retention history row.
3. Keep owner report action as draft/no-send unless mail gates explicitly allow later.
4. Run full API tests and smoke.
5. If admin/digest visible UI changes are made, run Huanshu + Playwright + axe + pa11y.
6. Export clean package and continue the self-written loop.

## Acceptance

- daily loop surfaces retention history evidence
- owner report includes no raw recipients/secrets
- warmup sent remains `0` unless natural pre-send gates execute later
- live outreach remains `0`
