# P141 Campaign Candidate Readiness Order Report

Generated: 2026-05-29

## Change

`qualified_campaign_lead_candidates()` now orders campaign candidates by audit readiness before lead score:

1. candidates with `audit_strength_score >= 70`;
2. higher audit strength;
3. higher lead score;
4. newer audits.

## Reason

The previous ordering could fill the bounded campaign candidate window with high-score leads whose audit evidence was not yet campaign-ready, hiding lower-score leads that already had sufficient public audit proof. This slowed no-send stockpile growth.

## Verification

- Focused campaign control room tests passed: `15`.
- The new regression test proves a ready candidate remains selected before a higher-score but low-strength candidate when the limit is tight.

## Safety

- No outreach transport changed.
- No SMTP send path changed.
- No quality threshold was lowered.
- Candidate outputs remain redacted and no raw recipient addresses are included.

