# P119 Live Queue Policy Gate Report

Generated: 2026-05-29T14:22:33+03:00

## Objective

Extend the campaign preflight policy-version gate into live-queue candidate selection and canary batch quality, so stale preflight PASS evidence cannot make a candidate look stageable.

## Changes

- Live outreach queue candidates now require `PASS_NO_SEND_PREFLIGHT` with the current policy version.
- Canary batch quality now records `campaign_preflight_policy_stale` as a blocker when the latest preflight PASS was produced under an old policy.
- Existing transport-level blocking remains in place as a final gate.

## Safety

- No cold outreach sent.
- No warmup forced.
- No existing non-Rescue projects touched.
- No recipient addresses or mailbox secrets included in committed output.

## Verification

- Launch/canary focused suite: `21 passed`.
- Runtime service health: API, worker, web, postgres, redis healthy.
- Runtime live-queue candidate selector still returns candidates only with current-policy preflight evidence.
- Runtime canary batch quality decision remains `PASS_CANARY_BATCH_QUALITY` for current-policy candidates, while stale-policy fixtures fail in tests.

## Current Launch State

Outreach remains paused by the separate canary resume planner due recent bounce/DSN signals. This change does not clear `pause_outreach`.
