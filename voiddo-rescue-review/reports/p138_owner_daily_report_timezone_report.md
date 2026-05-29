# P138 Owner Daily Report Timezone Report

Generated: 2026-05-29

## Change

Owner daily report idempotency now uses `Asia/Jerusalem` date instead of UTC date.

## Reason

The report metrics already use the Israel business day. The idempotency key must use the same day boundary so the owner receives one "result of the day" report per local day, not per UTC day.

## Safety

- No cold outreach changed.
- No extra owner send was forced.
- Sale alerts remain per payment/subscription id.

