# P117 Campaign Preflight Policy Version Report

Generated: 2026-05-29T14:13:37+03:00

## Objective

Prevent stale campaign preflight `PASS_NO_SEND_PREFLIGHT` rows from authorizing or visually implying readiness after the MX and bounce-aware lead policy changed.

## Changes

- Added campaign preflight policy version `20260529_mx_bounce_v1`.
- New preflight runs store the policy version in `result_json.policy_version`.
- API preflight status now requires both freshness and the current policy version.
- Worker outreach transport now blocks stale-policy PASS rows with `campaign_preflight_policy_stale`.
- Admin campaign preview rows now show legacy PASS rows as `PASS_STALE_POLICY` instead of a usable PASS.

## Safety

- No live outreach sent.
- No warmup send forced.
- No raw recipient addresses written to this report.
- No non-Rescue project touched.
- Existing preflight rows were not deleted or modified; they are only treated as non-authorizing when the policy is stale.

## Verification

- API focused suite: `25 passed`.
- Worker pause/preflight gate suite: `3 passed`.
- Runtime worker queue check while `pause_outreach=true`: `processed=0`, `sent=0`, `blocked=0`, `paused=true`.
- Runtime service health: API, worker, web, postgres, and redis healthy.

## Current Runtime Decision

Launch remains blocked by recent bounce/DSN signals. The correct next action is to keep `pause_outreach=true` until the clean-window gate passes, then rerun current-policy campaign preflight and compliance checks before any canary resume.
