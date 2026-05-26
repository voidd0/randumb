# P9 Campaign + Mailer Control Report

Generated: 2026-05-26 18:24 IDT

## Self-Written TZ

P9 objective was to make campaign preparation and the autonomous mailer explainable and structurally gated before any live sends. The owner explicitly reminded that the mailer must become fully autonomous, so this pass focused on decision records, refusal reasons, reply action plans, campaign readiness snapshots, and scout provenance scoring.

## Implemented

- Added migration `013_campaign_mailer_control.sql`.
- Added `campaign_readiness_snapshots`.
- Added `outbound_mailer_decisions`.
- Added `reply_action_plans`.
- Added `scout_provenance_scores`.
- Added modules:
  - `campaign_control.py`
  - `mailer_control.py`
  - `reply_actions.py`
- Extended `scout_quality.py` with provenance scoring.
- Added protected admin endpoints:
  - `POST /admin/campaigns/{campaign_id}/readiness`
  - `POST /admin/mailer/outbound-decision`
  - `POST /admin/replies/action-plan`
  - `POST /admin/scouts/runs/{run_id}/provenance`
- Added admin metrics for campaign readiness, outbound gates, reply plans, and scout provenance.
- Added autonomous agents:
  - `outbound_mailer_gate_agent`
  - `reply_action_agent`

## Mailer Autonomy State

The mailer now records structured outbound decisions per message/payload with:

- recipient hash, not raw address in reports
- mailbox
- template key
- template QA result
- unsubscribe presence
- suppression state
- throttle state
- transport gate state
- final action
- refusal reason

Current real decision is correctly blocked:

- action: `do_not_send`
- reason: `outreach_dry_run_enabled,recent_bounce_or_dsn`
- live outreach sent: `0`

Replies now produce action plans:

- safe categories create safe draft actions
- unsubscribe creates suppression action
- legal/security/unclear replies stop automation and create review action
- auto-replies remain paused by runtime policy

## Campaign Control State

Campaign readiness now combines:

- lead count
- qualified count
- audit strength
- campaign economics
- mail safety
- visual safety
- blockers

This makes campaign previews inspectable before any future live-send gate can consider them.

## Verification

- DB migrations: PASS
- Full pytest: `100 passed`
- Smoke: PASS, `100 passed`, `ok`
- Huanshu:
  - landing: PASS
  - audit demo: PASS
  - customer: PASS
  - status: PASS
  - unsubscribe: PASS
  - authenticated admin screenshots: PASS
- Extra design/QA plugins:
  - axe-core/playwright: PASS
  - pa11y: PASS
  - pixelmatch: PASS
  - Lighthouse CI: PASS_WITH_WARNINGS, score `80`, no failed checks
- Daily loop: PASS, `12` agents completed
- Warmup sent: `0`
- Live outreach sent: `0`

## Blockers

- Recent bounce/DSN signals in the last 24 hours: `2`.
- Recent SMTP rate-limit signals in the last 24 hours: `1`.
- The mailer is intentionally autonomous but safety-blocked until the mail clean window clears and mail QA is rerun.

## Decision

P9 is accepted as a campaign-control and autonomous-mailer hardening pass. Launch readiness remains `WARMUP_SCHEDULED_NO_OUTREACH`.
