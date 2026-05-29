# P135 Core Timer Fail-Soft Report

Generated: 2026-05-29

## Change

The fast Rescue core systemd unit now passes `--allow-agent-failures` to `scripts/rescue_autonomous_loop.py`.

This does not allow live outreach. The runner still exits non-zero if any agent reports unexpected live outreach permission or if the loop itself fails.

## Reason

The core timer can overlap routine API rebuilds or transient agent failures. Those failures should be recorded by the agent-run layer without disabling the next autonomous safety heartbeat.

## Safety

- Live/send safety remains hard-fail.
- No cold outreach was enabled.
- No warmup was forced.
- No non-Rescue service was touched.

