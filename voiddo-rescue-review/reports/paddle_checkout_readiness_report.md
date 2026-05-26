# Paddle Checkout Readiness Report

Updated: 2026-05-26 12:05 IDT

## Status

`FAIL_CLOSED`

Paddle API key, webhook secret, and all six Rescue price IDs are configured, but no hosted checkout base URL or client checkout config is configured yet.

Current public behavior:

- `GET /billing/config`: reports all price keys present.
- `GET /checkout/{product_key}`: redirects only if checkout base/config is present.
- Without checkout base/config, it returns `503 checkout_not_configured`.

## Product Price Coverage

- `monitor_monthly`: configured
- `fix_lite_monthly`: configured
- `rescue_pro_monthly`: configured
- `audit_onetime`: configured
- `contact_form_repair`: configured
- `emergency_fix`: configured

## Required Next Config

Preferred simple path:

- Set `PADDLE_HOSTED_CHECKOUT_BASE_URL` to the approved Paddle hosted checkout link.

Alternative:

- Add Paddle.js client checkout configuration and a verified checkout page, then route `/checkout/{product_key}` to that page with price ID and audit metadata.

## Notes

Paddle documentation says hosted checkout links accept `price_id` and `user_email` query parameters, but live hosted checkout access may require Paddle approval. No fake hosted URL was inserted.

## Safety

- No real customer charge was created in this pass.
- Live outreach remains blocked.

