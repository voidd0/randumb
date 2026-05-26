# Lead Scoring Report

Generated: 2026-05-26 15:18 IDT

## Decision

`IMPLEMENTED`

Lead scoring now produces explainable 0-100 scores and writes structured `reasoning_json`.

## Inputs

- Technical issue severity from audit issues.
- Sales potential from niche, country, business type, and contactability.
- Urgency from critical/high issues and contact/CTA failures.
- Value from niche and likely lead value.
- Deliverability from email type, suppression, and domain quality.

## Outputs

Table: `lead_scores`

- `technical_score`
- `sales_score`
- `urgency_score`
- `value_score`
- `deliverability_score`
- `final_score`
- `reasoning_json`

## Campaign Rule

Campaign preparation uses score threshold filtering. The default launch threshold remains `>= 70`, and no live sending is enabled by scoring.

## Verification

- Unit/integration tests validate scoring range and reasoning fields.
- Campaign preview test validates scored lead selection.

## Limitations

- The scoring model is deterministic and rules-based.
- It is ready for MVP operation, but should be calibrated after real reply/payment data.
