CREATE TABLE IF NOT EXISTS outreach_send_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  status TEXT NOT NULL,
  decision TEXT NOT NULL,
  requested_by TEXT NOT NULL DEFAULT 'system',
  dry_run BOOLEAN NOT NULL DEFAULT TRUE,
  requested_limit INTEGER NOT NULL DEFAULT 0,
  candidate_count INTEGER NOT NULL DEFAULT 0,
  staged_count INTEGER NOT NULL DEFAULT 0,
  sent_count INTEGER NOT NULL DEFAULT 0,
  blocked_count INTEGER NOT NULL DEFAULT 0,
  result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  send_mail BOOLEAN NOT NULL DEFAULT FALSE,
  smtp_called BOOLEAN NOT NULL DEFAULT FALSE,
  live_outreach_allowed BOOLEAN NOT NULL DEFAULT FALSE,
  raw_recipient_addresses_included BOOLEAN NOT NULL DEFAULT FALSE,
  secrets_included BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_outreach_send_runs_created ON outreach_send_runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_outreach_send_runs_decision ON outreach_send_runs(decision);
CREATE INDEX IF NOT EXISTS idx_outreach_messages_live_queue ON outreach_messages(status, created_at) WHERE status IN ('queued', 'sending', 'transport_blocked');
