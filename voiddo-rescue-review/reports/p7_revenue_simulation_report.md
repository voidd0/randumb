# P7 Revenue Simulation And Mail Recovery Report

Generated: 2026-05-26 17:56 IDT

## Decision

`P7_PASS_WITH_MAIL_SIGNAL_BLOCKERS`

P7 built the first dry-run revenue simulation and mail recovery gate. It still sends nothing.

## Implemented

- `revenue_simulation_runs`
- `campaign_economics_checks`
- `mail_clean_window_checks`
- `mailer_drafts`
- Synthetic lead simulation:
  - lead creation
  - scanner job creation
  - synthetic audit creation
  - lead scoring
  - campaign preview
- Campaign economics gate:
  - expected revenue
  - expected cost
  - margin percent
  - risk score
  - low expected sales block
- Mail clean-window watcher:
  - bounce/DSN check
  - SMTP rate-limit check
  - spam signal check
  - mail QA decision check
- Mailer draft persistence:
  - template render
  - QA result
  - recipient hash only

## Verification

- tests: `81 passed`
- smoke: PASS, `81 passed`
- Huanshu: PASS
- extra plugins:
  - axe-core/playwright: PASS
  - pa11y: PASS
  - pixelmatch: PASS
  - Lighthouse CI: PASS_WITH_WARNINGS

## Current Mail Recovery State

- clean window status: `blocked`
- bounce/DSN count: `2`
- SMTP rate-limit count: `1`
- spam signal count: `0`
- latest mail QA: `PASS`
- next action: `wait_for_clean_window`

## Live Activity

- warmup sent: `0`
- live outreach sent: `0`
- manual warmup force: not performed

## Fixes During P7

- Synthetic simulation now explicitly marks qualified synthetic leads campaign-ready.
- Campaign test isolation was fixed so simulations do not pollute unrelated campaign tests.
- Campaign economics now blocks expected-sales-below-1 scenarios.

## Result

P7 is accepted as a simulation/recovery pass, not a launch pass.
