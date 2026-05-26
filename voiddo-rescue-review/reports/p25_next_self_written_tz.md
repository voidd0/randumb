# P25 Self-Written TZ — Customer Mail Transport Dry-Run Boundary

Generated: 2026-05-26 21:33 IDT

## Goal

Add the customer-mail transport boundary that can convert send-ready actions into dry-run delivery records and later real sends only after explicit gates pass.

## Tasks

1. Add transport result statuses:
   - `dry_run_recorded`
   - `transport_blocked`
   - `sent`
   - `failed`
2. Add protected endpoint:
   - `POST /admin/mailer/action-queue/transport-dry-run`
3. Dry-run behavior:
   - render template
   - record sanitized Message-ID placeholder
   - update action result JSON
   - never call SMTP
4. Real-send remains disabled unless:
   - customer mail flag true
   - mail QA PASS
   - no recent signals
   - throttle pass
   - action status `send_ready`
   - explicit transport flag added later
5. Tests:
   - dry-run does not call SMTP
   - dry-run records sanitized result
   - real-send remains blocked
   - raw customer email omitted

## Acceptance

- At least 190 tests pass.
- Customer mail transport dry-run exists.
- No SMTP send occurs.
- Live outreach remains `0`.
- Warmup remains `0` unless existing natural gates pass.
- Non-Rescue projects untouched.
