# P15 Customer Token Access + Monitoring Report

Generated: 2026-05-26 19:35 IDT

## Scope

P15 added customer-safe token access and a safe monitoring loop.

## Code Changes

- `apps/api/migrations/019_p15_customer_access_monitoring.sql`
- `apps/api/app/customer_access.py`
- `apps/api/app/monitoring.py`
- `apps/api/app/customer_journey.py`
- `apps/api/app/main.py`
- `apps/api/app/p0.py`
- `apps/api/app/autonomous_agents.py`
- `apps/api/tests/test_p15_customer_access_monitoring.py`
- `apps/web/app/admin/page.tsx`

## New Tables

- `customer_access_tokens`
- `monitoring_runs`

## Customer Token Access

Implemented:

- active customer access token creation
- token hashing before storage
- public token dashboard endpoint: `GET /customer/dashboard/{token}`
- protected admin token endpoint: `POST /admin/customers/{customer_id}/access-token`
- invalid token returns `404`
- token dashboard exposes only that customer’s journey payload

## Monitoring Loop

Implemented:

- protected monitoring target creation
- dry-run safe monitoring check
- monitoring run persistence
- monitoring target `last_checked_at`
- optional scanner-job queue path for non-dry monitoring

Protected endpoints:

- `POST /admin/customers/{customer_id}/monitoring-targets`
- `POST /admin/monitoring/{target_id}/run`

## Verification

- API tests: `138 passed`
- smoke: PASS, includes `138 passed`
- Huanshu: PASS
- extra QA plugins: PASS or non-blocking warning
- warmup sent: `0`
- live outreach sent: `0`

## Current Decision

State remains `WARMUP_SCHEDULED_NO_OUTREACH`.

The customer journey is now customer-accessible through signed-style opaque tokens, and monitoring can run safe checks, but cold outreach remains blocked by recent delivery-risk signals.

