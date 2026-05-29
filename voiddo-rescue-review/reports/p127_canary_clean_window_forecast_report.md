# P127 Canary Clean Window Forecast Report

Generated: 2026-05-29

## Change

Added `canary_clean_window_forecast_agent` and protected admin endpoint:

- `GET /admin/outreach/live-queue/clean-window`

Added owner command:

- `SHOW CANARY CLEAN WINDOW`

The forecast exposes:

- latest blocking mail signal timestamp.
- clean-window eligibility time.
- seconds remaining.
- signal counts.
- queued/sent/bounced canary counts.
- next autonomous action.

## Safety

- The forecast is read-only except for agent-run logging.
- It sends no mail.
- It does not clear `pause_outreach`.
- It does not expose raw recipient addresses.

## Runtime Purpose

The daily loop now records this forecast before the auto-resume agent runs. This gives the autonomous system a precise waiting/recheck signal while keeping live canary paused during the bounce/DSN risk window.

