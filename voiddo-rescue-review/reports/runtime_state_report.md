# Vøiddo Rescue Runtime State

Generated: 2026-05-26T14:21:21+03:00

- current branch HEAD before P5 commit: 3515e11ee3d360d85a3932e73805787a018b2f07
- current ZIP SHA for P5 export: see adjacent `.sha256` generated after packaging
- checkout status: READY
- mail auth status: PASS
- latest mail QA decision: PASS
- approved test inbox count: 7
- approved warmup recipient count: 7
- scheduled warmup count: 28
- deliverability diagnostic sent count: 7 owner-approved diagnostics plus prior disabled/test rows retained in DB history
- warmup sent count: 0
- live outreach sent count: 0
- bounce/DSN count, last 24h: 2
- rate-limit signal count, last 24h: 1
- spam signal count, last 24h: 0
- next allowed action: wait until the recent bounce/DSN and rate-limit window clears, rerun mail QA, then allow the scheduled warmup timer to proceed through the pre-send gate.
- launch readiness state: WARMUP_SCHEDULED_NO_OUTREACH

Canonical decision: not live-outreach-ready. Warmup is scheduled but safety-blocked by recent mail signals.

Raw recipient addresses are intentionally omitted.
