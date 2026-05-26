# P16 Self-Written TZ: Monitoring Scheduler + Customer UI Wiring

Generated: 2026-05-26 19:35 IDT

## Goal

Wire the new customer token and monitoring APIs into the worker/admin/customer surfaces and make monitoring scheduler-ready. Do not send cold outreach and do not force warmup.

## Tasks

1. Monitoring scheduler
   - Add a scheduler-safe agent for due monitoring targets.
   - Respect kill switches.
   - Run only safe checks.
   - Record monitoring failures and Codex tasks.

2. Customer UI wiring
   - Add token dashboard route in the web app.
   - Show purchased products, fix requests, onboarding, and monitoring status from API data.
   - Keep admin-only details hidden.

3. Admin monitoring control
   - Show monitoring targets and latest run counts.
   - Show customer token count and customer journey count.

4. Scenario tests
   - token dashboard page smoke
   - monitoring scheduler due target
   - monitoring failure creates system event/task
   - customer dashboard does not expose other customers

5. Reports/export
   - Update runtime, launch, smoke, visual, monitoring, and customer reports.
   - Export clean review package.

## Acceptance

- At least 144 passing tests.
- Huanshu PASS.
- Extra QA plugins PASS or non-blocking warning only.
- Customer token web route exists.
- Monitoring scheduler exists and remains safe.
- Warmup sent remains `0` unless existing timer naturally sends after gates pass.
- Live outreach remains `0`.
- Non-Rescue projects untouched.

