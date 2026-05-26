# P29 Self-Written TZ — Customer Mail Send Simulation Matrix

Generated: 2026-05-26 22:12 IDT

## Goal

Build a full customer lifecycle mail simulation matrix that proves onboarding, fix request, monitoring reminder, suppression, resolver, throttle, and failure paths behave correctly before any real customer SMTP send can be enabled.

## Tasks

1. Add simulation runner for customer mail products:
   - `monitor_monthly`
   - `fix_lite_monthly`
   - `rescue_pro_monthly`
   - `audit_onetime`
   - `contact_form_repair`
   - `emergency_fix`
2. Simulate lifecycle actions:
   - payment onboarding
   - fix request created
   - monitoring setup reminder
3. Validate gates:
   - flags false
   - flags true but recent signals
   - suppression
   - throttle
   - resolver missing
   - mocked SMTP success
   - mocked SMTP failure
4. Add protected endpoint:
   - `POST /admin/mailer/customer-simulation`
5. Add report:
   - `reports/p29_customer_mail_simulation_report.md`

## Acceptance

- At least 214 tests pass.
- Simulation covers all paid product keys.
- Real runtime sends 0.
- Raw recipient addresses are absent from simulation reports.
- Non-Rescue projects untouched.
