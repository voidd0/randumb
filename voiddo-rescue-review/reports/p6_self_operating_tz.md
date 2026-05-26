# P6 Self-Operating Revenue Engine TZ

Generated: 2026-05-26 15:35 IDT

## Goal

Turn Vøiddo Rescue from a gated MVP into a self-operating revenue machine foundation: economics-aware, self-auditing, self-fixing, self-learning, self-building, and mailer-autonomous while keeping live outreach blocked until gates prove safe.

## Non-Negotiable Rules

- Do not touch non-Rescue projects.
- Do not expose secrets or raw recipient addresses.
- Do not commit `.env`, mailbox passwords, private keys, runtime storage, screenshots, exports, `.venv`, caches, `node_modules`, or `.next`.
- Do not send cold outreach.
- Do not manually force warmup.
- Keep `OUTREACH_PAUSED=true`, `FIRST_LIVE_SEND_FLAG=false`, and `AUTO_REPLIES_PAUSED=true` unless a later explicit gated test changes that.
- Use `Vøiddo` spelling with slashed o in product-facing copy.
- Do not expose AI/operator language in customer-facing pages or emails.

## Required Modules

1. `economics-engine`
   - Track price, cost, margin, payback, and revenue-readiness.
   - Block campaigns that cannot clear margin rules.

2. `self-audit-engine`
   - Audit all modules, gates, tests, mail signals, visual QA, and export hygiene.
   - Write DB records and reports.

3. `self-fix-engine`
   - Convert failed audits/tests/signals into fix tasks.
   - Never execute unsafe shell or non-Rescue changes.

4. `self-learning-engine`
   - Record mistakes/signals and create durable prevention rules.
   - Learn from bounces, rate limits, visual failures, template QA failures, and checkout failures.

5. `self-building-engine`
   - Convert roadmap gaps into prioritized build queue items.
   - Keep scope bounded and reviewable.

6. `autonomous-mailer-engine`
   - Own inbound/outbound mail decisions, reply classification, suppression, throttles, warmup gates, and report routing.
   - Never send live outreach until all gates pass.

7. `quality-plugin-gate`
   - Huanshu remains canonical.
   - Add at least four extra design/quality plugin adapters:
     - `@axe-core/playwright`
     - `pa11y`
     - `@lhci/cli`
     - `pixelmatch`/`pngjs`

## Acceptance Criteria

- New DB tables exist for economics, self-audit, self-fix, self-learning, self-building, mailer autonomy, and quality plugin runs.
- Admin APIs expose safe runs for each engine.
- Agents can run these engines and record outcomes.
- Full tests pass.
- Smoke passes.
- Huanshu + extra plugin gate has a runnable script and report.
- Live outreach remains 0.
- Warmup remains not manually forced.
- Review/export remains clean.

## Audit Loop

After implementation:

1. Run DB migrations.
2. Run tests.
3. Run smoke.
4. Run Huanshu and plugin gates.
5. Run self-audit.
6. Fix failures.
7. Produce P6 audit report.
8. Create next-cycle TZ.
