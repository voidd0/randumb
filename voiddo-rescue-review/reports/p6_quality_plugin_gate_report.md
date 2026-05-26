# P6 Quality Plugin Gate Report

Generated: 2026-05-26 17:43 IDT

## Decision

`PASS_WITH_LIGHTHOUSE_WARNINGS`

Huanshu remains canonical and passed. Four extra design/quality plugins were installed and used.

## Installed Local QA Packages

- `@axe-core/playwright`
- `pa11y`
- `@lhci/cli`
- `pixelmatch`
- `pngjs`
- `playwright`

These are local dev dependencies in `apps/web`, not global packages.

## Gate Results

Huanshu:

- `/`: PASS
- `/r/demo`: PASS
- `/customer`: PASS
- `/status`: PASS
- `/unsubscribe/demo-token`: PASS
- authenticated `/admin`: PASS

Additional plugin gate:

- axe-core/playwright: PASS
- pa11y: PASS
- pixelmatch: PASS
- Lighthouse CI: PASS_WITH_WARNINGS

No plugin produced a launch-blocking issue after runner fixes.

## Self-Fix During Gate

- Playwright browser binary was missing after package install; installed Chromium for local QA.
- `@axe-core/playwright` required `browser.newContext()`; runner fixed.
- pa11y required Chromium `--no-sandbox` in this root VPS runtime; runner fixed.

## Dependency Risk

`npm audit` reports 5 dev-dependency vulnerabilities through `@lhci/cli`:

- low: 3
- moderate: 2
- high/critical: 0

No production runtime dependency is introduced by the QA runner. Do not run `npm audit fix --force` without review because npm suggests a semver-major downgrade/rewrite path for Lighthouse CI.

## Artifacts

Runtime-only artifacts live under storage and are excluded from review/export packages.
