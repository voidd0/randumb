# Visual QA Agent Report

Generated: 2026-05-26 20:47 IDT

## Canonical Gate

Huanshu local adapter remains the canonical visual gate for Rescue.

## Huanshu Results

- landing `/`: PASS
- audit demo `/r/demo`: PASS
- customer `/customer`: PASS
- customer token dashboard `/customer/dashboard/[token]`: PASS
- status `/status`: PASS
- unsubscribe `/unsubscribe/demo-token`: PASS
- authenticated admin `/admin`: PASS

## Additional Plugin Results

- `axe-core-playwright`: PASS
- `pa11y`: PASS
- `pixelmatch`: PASS
- `lighthouse-ci`: PASS_WITH_WARNINGS, no blocker

## P20 Notes

The authenticated admin panel, including post-window timer/readiness evidence, was screenshot-tested with auth headers. Blocking visual issues: `0`.
