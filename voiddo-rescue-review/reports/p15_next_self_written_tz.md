# P15 Self-Written TZ: Customer Token Access + Real Monitoring Loop

Generated: 2026-05-26 19:25 IDT

## Goal

Move the customer experience from admin-only proof to gated customer-facing access and add real monitoring target execution. Do not send cold outreach and do not force warmup.

## Tasks

1. Customer token access
   - Add customer access tokens or signed dashboard links.
   - Expose a customer-safe dashboard API that reveals only that customer’s audit, products, fix requests, onboarding, and monitoring.
   - Keep admin-only data behind admin auth.

2. Monitoring loop
   - Add monitoring job table if needed.
   - Queue monitoring targets from paid products.
   - Run safe public scanner checks on monitoring targets.
   - Record monitoring events and daily report state.

3. Fix workflow visibility
   - Show linked Codex task state in customer and admin surfaces.
   - Keep unsafe website fixes gated.

4. Scenario tests
   - payment -> customer token -> dashboard
   - payment -> monitoring target -> safe check
   - fix request -> Codex task visible
   - customer cannot access another customer’s data

5. Reports/export
   - Update runtime, launch, smoke, customer journey, monitoring, and blocker reports.
   - Export clean review package.

## Acceptance

- At least 138 passing tests.
- Huanshu PASS.
- Extra QA plugins PASS or non-blocking warning only.
- Customer-safe token access exists.
- Monitoring loop exists and is safe.
- Warmup sent remains `0` unless existing timer naturally sends after gates pass.
- Live outreach remains `0`.
- Non-Rescue projects untouched.

