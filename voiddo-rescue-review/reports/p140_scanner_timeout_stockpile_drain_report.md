# P140 Scanner Timeout And Stockpile Drain Report

Generated: 2026-05-29

## Change

The Rescue worker compose config now sets `SCANNER_JOB_TIMEOUT_SECONDS=75` by default.

## Reason

Revenue stockpile growth was blocked by safe public scanner jobs that could hold a worker lane for the previous 150 second default. Timed-out public scans already persist a partial audit with a clear timeout issue, so a shorter default keeps the autonomous pipeline moving without weakening scan safety.

## Safety

- No invasive scan behavior was added.
- No forms are submitted.
- No SMTP or outreach flags changed.
- Timed-out jobs still produce explicit partial audit evidence instead of silent success.

