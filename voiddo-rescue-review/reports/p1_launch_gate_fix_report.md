# P1 Launch-Gate Fix Report

Updated: 2026-05-26 IDT

## Completed In This Pass

- Installed Huanshu local adapter on host and inside Rescue API/worker containers.
- Added executable Huanshu adapter scripts:
  - `apps/worker/worker/huanshu_cli.py`
  - `apps/api/app/huanshu_cli.py`
- Updated Huanshu discovery:
  - worker now checks `/app/worker/huanshu_cli.py`
  - API now checks `/app/app/huanshu_cli.py`
- Fixed visual QA hard-block logic so unresolved template variables cannot pass as warnings.
- Fixed visual QA false positives by checking visible DOM text instead of full Next.js runtime HTML.
- Improved text-overlap heuristic to ignore parent/child bounding-box containment.
- Added above-fold CTA actions to admin and customer pages.
- Moved audit-page CTAs above fold.
- Added localhost-only Rescue compose ports for nginx proxying:
  - `127.0.0.1:18081` web
  - `127.0.0.1:18082` API
- Added Rescue-only nginx reverse proxy routes for nested subdomains.
- Issued Let’s Encrypt certificate for nested Rescue subdomains.
- Kept Rescue ZIP artifact download URLs working while moving `rescue.voiddo.com/` to the product landing.
- Added gated `/checkout/{product_key}` endpoint: redirects only when `PADDLE_HOSTED_CHECKOUT_BASE_URL` is configured, otherwise returns controlled 503.
- Fixed owner command API collision when ad-hoc commands arrive without IMAP uid/message-id.
- Fixed smoke test script to run tests inside the API/worker containers.

## Verification

- Host Huanshu CLI version check: PASS.
- API container Huanshu CLI version check: PASS.
- Worker container Huanshu CLI version check: PASS.
- API test suite: `25 passed`.
- Updated API/smoke suite after checkout and command-id fixes: `26 passed`.
- Visual route QA:
  - landing: PASS
  - audit demo: PASS
  - real audit slug: PASS
  - admin: PASS
  - customer: PASS
  - email preview: PASS
  - screenshot evidence: PASS
- Public route smoke:
  - `rescue.voiddo.com`: 200
  - `app.rescue.voiddo.com/admin`: 401 expected
  - `api.rescue.voiddo.com/health`: 200
  - `audit.rescue.voiddo.com/r/demo`: 200
  - `go.rescue.voiddo.com/unsubscribe/test`: 200
  - `status.rescue.voiddo.com`: 200

## Still Blocked

- Strict SMTP TLS login still blocked by Mailcow certificate trust/SAN setup.
- Strict IMAP TLS login still blocked by Mailcow certificate trust/SAN setup.
- Deliverability test inbox pool is still missing.
- Warmup recipient pool is still missing.
- Public nested Rescue reverse proxy routes are still incomplete.

## Safety

- Existing non-Rescue projects were not modified.
- Live outreach sent: `0`.
- Warmup sent: `0`.
- No `.env` or mailbox passwords were committed.
