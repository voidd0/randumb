# Visual QA Agent Report

Generated: 2026-05-26 22:59 IDT

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

## P24 Notes

The authenticated admin panel, including post-window timer/readiness evidence, mailer ledger, mailer action queue, customer mail task counts, and send-ready evidence, was screenshot-tested with auth headers. Blocking visual issues: `0`.

## P30 Notes

The authenticated admin panel now includes the customer-mail gate visibility panel. It was screenshot-tested on desktop and mobile with auth headers.

- Huanshu local adapter: PASS
- Playwright screenshots: 2, both nonblank
- `axe-core-playwright`: PASS, 0 violations
- `pa11y`: PASS, 0 issues
- horizontal overflow: `false`
- broken images: `0`
- unresolved template variables: `false`
- raw recipient exposure: `false`
- blocking visual issues: `0`

## P31 Notes

The authenticated admin panel now includes the Mailer Ops Controls panel with four protected no-send actions.

- Huanshu local adapter: PASS
- Playwright screenshots: 2, both nonblank
- `axe-core-playwright`: PASS, 0 violations
- `pa11y`: PASS, 0 issues
- horizontal overflow: `false`
- broken images: `0`
- unresolved template variables: `false`
- raw recipient exposure: `false`
- required controls visible: `Run simulation`, `Closed-loop dry run`, `Transport dry run`, `Prepare owner report`
- blocking visual issues: `0`

## P32 Notes

The authenticated admin panel now reads persisted `mailer_ops_runs` history for the Mailer Ops Controls panel.

- Huanshu local adapter: PASS
- Playwright screenshots: 2, both nonblank
- `axe-core-playwright`: PASS, 0 violations
- `pa11y`: PASS, 0 issues
- horizontal overflow: `false`
- broken images: `0`
- unresolved template variables: `false`
- raw recipient exposure: `false`
- no-send status visible: `true`
- blocking visual issues: `0`
