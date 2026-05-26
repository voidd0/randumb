# Visual QA Agent Report

Generated: 2026-05-26 19:55 IDT

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

## P16 Fix

Huanshu initially blocked the token dashboard because the CTA was not visible above the fold on mobile. The customer dashboard hero was tightened and rechecked to PASS.

## Decision

PASS for P16 visual gate. Blocking visual issues: `0`.
