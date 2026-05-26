CREATE TABLE IF NOT EXISTS mailer_ops_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  action text NOT NULL,
  status text NOT NULL,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  raw_recipient_addresses_included boolean NOT NULL DEFAULT false,
  send_mail boolean NOT NULL DEFAULT false,
  smtp_called boolean NOT NULL DEFAULT false,
  live_outreach_allowed boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mailer_ops_runs_action_created ON mailer_ops_runs(action, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mailer_ops_runs_status_created ON mailer_ops_runs(status, created_at DESC);

