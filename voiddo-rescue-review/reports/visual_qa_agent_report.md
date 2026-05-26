# Visual QA Agent Report

Updated: 2026-05-26 12:45 IDT

## Agents

- `landing_visual_agent`
- `app_visual_agent`
- `audit_page_visual_agent`
- `screenshot_evidence_agent`
- `email_visual_agent`
- `checkout_visual_agent`

## Checks Implemented

- Playwright desktop screenshot.
- Playwright mobile screenshot.
- Console error capture.
- Horizontal overflow check.
- CTA above-fold check.
- Broken image check.
- Placeholder/lorem text check against visible text.
- Raw JSON visibility check.
- Unresolved template variable check against visible text.
- DOM bounding-box overlap heuristic with parent/child elements excluded.
- Huanshu local adapter execution against generated screenshot artifacts.

## Huanshu Adapter

- Spelling normalized to `Huanshu`.
- Host executable installed:
  - `/usr/local/bin/huanshu`
  - `/usr/local/bin/huashu` symlink
- Container executables installed:
  - API: `/app/app/huanshu_cli.py`
  - Worker: `/app/worker/huanshu_cli.py`
- Version output verified:
  - `huanshu-local-adapter 0.1.0 (huashu-design verify compatible)`
- Adapter basis: local Huashu/Huanshu design plugin assets plus Playwright-backed artifact checks.
- This is not a remote Huanshu SaaS/API integration.

## Latest Route Coverage

Latest worker visual run covered:

- landing `/`
- audit demo `/r/demo`
- one real audit slug
- admin `/admin` with tokenized access
- customer `/customer`
- EN email preview
- scanner screenshot evidence route
- Paddle.js checkout page

Latest decisions:

- `landing_visual_agent`: `PASS`, Huanshu `PASS`
- `audit_page_visual_agent`: `PASS`, Huanshu `PASS`
- `app_visual_agent`: `PASS`, Huanshu `PASS`
- `email_visual_agent`: `PASS`, Huanshu `PASS`
- `screenshot_evidence_agent`: `PASS`, Huanshu `PASS`
- `checkout_visual_agent`: `PASS`, Huanshu `PASS`

P3 checkout visual smoke captured the public checkout page with no horizontal overflow and no console errors.

## Notes

The previous `BLOCKED_HUANSHU_NOT_AVAILABLE` state is resolved for the local Rescue P1 gate. Live-domain/public-route visual QA now passes on the Rescue subdomains listed in `reverse_proxy_rescue_routes_report.md`.
