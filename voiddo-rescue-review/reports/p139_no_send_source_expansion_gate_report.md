# P139 No-Send Source Expansion Gate Report

Generated: 2026-05-29

## Change

Scout/source expansion is no longer blocked by launch-only mail-risk warnings in the self-audit matrix.

The source expansion gate still blocks if:

- the self-audit matrix is missing;
- the matrix reports `send_mail`;
- the matrix reports `live_outreach_allowed`;
- raw recipient addresses or secrets are included.

The gate now treats lower coverage score and matrix failures as warnings for no-send lead discovery. Those warnings still block live outreach through launch readiness and mailer policy gates.

## Reason

Recent bounce/DSN signals must stop sending, not lead discovery. While the mail domain is waiting for a clean window, the system should keep finding/scanning/qualifying leads.

## Safety

- No SMTP send path changed.
- No live outreach flag changed.
- No suppression or unsubscribe rule changed.
- This only affects no-send scout/source expansion.

