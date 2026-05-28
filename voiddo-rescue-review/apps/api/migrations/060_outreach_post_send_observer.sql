CREATE TABLE IF NOT EXISTS outreach_post_send_observer_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  status TEXT NOT NULL,
  decision TEXT NOT NULL,
  observed_sent_count INTEGER NOT NULL DEFAULT 0,
  reply_count INTEGER NOT NULL DEFAULT 0,
  bounce_or_dsn_count INTEGER NOT NULL DEFAULT 0,
  rate_limit_count INTEGER NOT NULL DEFAULT 0,
  spam_signal_count INTEGER NOT NULL DEFAULT 0,
  pause_outreach_applied BOOLEAN NOT NULL DEFAULT FALSE,
  result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  send_mail BOOLEAN NOT NULL DEFAULT FALSE,
  smtp_called BOOLEAN NOT NULL DEFAULT FALSE,
  live_outreach_allowed BOOLEAN NOT NULL DEFAULT FALSE,
  raw_recipient_addresses_included BOOLEAN NOT NULL DEFAULT FALSE,
  secrets_included BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_outreach_post_send_observer_runs_created ON outreach_post_send_observer_runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_outreach_post_send_observer_runs_decision ON outreach_post_send_observer_runs(decision);
