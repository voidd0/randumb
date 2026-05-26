# Visual QA Agent Report

Generated: 2026-05-26 20:34 IDT

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

## P19 Notes

The updated admin post-window transition panel was screenshot-tested with auth headers. Blocking visual issues: `0`.
