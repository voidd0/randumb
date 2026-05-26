# Email Template Rebuild Report

Generated: 2026-05-26 15:18 IDT

## Decision

`IMPLEMENTED_AND_QA_PASS`

Template rendering and QA now live in `apps/api/app/email_templates.py`.

## Templates

- `first_audit_notice`
- `followup_1_soft`
- `followup_2_value`
- `reply_ask_price`
- `reply_ask_details`
- `reply_wrong_person`
- `unsubscribe_confirmed`
- `payment_onboarding`
- `fix_request_created`
- `warmup_neutral`
- `deliverability_diagnostic`

## Languages

- English
- Hebrew
- Estonian

Operational templates are English-first where localized customer copy is not yet required.

## QA Rules

- No unresolved `{{vars}}`
- Subject length checked
- Risk phrases blocked
- Outreach templates require proof URL
- Outreach templates require unsubscribe URL
- Warmup and diagnostic templates must stay neutral
- Plain text is always present

## Verification

- `email_template_agent` rendered 17 samples.
- QA result: all pass.
- Full test suite includes template rendering and QA checks.
