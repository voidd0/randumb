# Visual QA Agent Report

Updated: 2026-05-26 IDT

## Agents

- `landing_visual_agent`
- `app_visual_agent`
- `audit_page_visual_agent`
- `screenshot_evidence_agent`
- `email_visual_agent`

## Checks Implemented

- Playwright desktop screenshot.
- Playwright mobile screenshot.
- Console error capture.
- Horizontal overflow check.
- CTA above-fold check.
- Broken image check.
- Placeholder text check.
- Raw JSON visibility check.
- Unresolved template variable check.
- DOM bounding-box overlap heuristic.

## Huanshu Adapter

- Spelling normalized to `Huanshu`.
- Adapter checks for configured `HUANSHU_CLI` or local `huanshu` executable.
- Current status: `BLOCKED_HUANSHU_NOT_AVAILABLE`.
- No Huanshu PASS was claimed.

## Latest Decisions

All visual agents currently return `FAIL_BLOCK_LAUNCH` because the real Huanshu tool is not available.

This is intentional and blocks launch/public visual readiness until Huanshu is installed or a real adapter is configured.
