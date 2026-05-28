CREATE TABLE IF NOT EXISTS paid_customer_watchdog_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  status TEXT NOT NULL,
  decision TEXT NOT NULL,
  checked_customer_count INTEGER NOT NULL DEFAULT 0,
  repaired_customer_count INTEGER NOT NULL DEFAULT 0,
  blocker_count INTEGER NOT NULL DEFAULT 0,
  result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  send_mail BOOLEAN NOT NULL DEFAULT FALSE,
  smtp_called BOOLEAN NOT NULL DEFAULT FALSE,
  live_outreach_allowed BOOLEAN NOT NULL DEFAULT FALSE,
  raw_recipient_addresses_included BOOLEAN NOT NULL DEFAULT FALSE,
  secrets_included BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_paid_customer_watchdog_runs_created ON paid_customer_watchdog_runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_paid_customer_watchdog_runs_decision ON paid_customer_watchdog_runs(decision);
