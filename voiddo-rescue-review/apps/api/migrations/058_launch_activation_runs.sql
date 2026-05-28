CREATE TABLE IF NOT EXISTS launch_activation_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  status TEXT NOT NULL,
  decision TEXT NOT NULL,
  requested_by TEXT NOT NULL DEFAULT 'system',
  confirm_text_hash TEXT NOT NULL DEFAULT '',
  dry_run BOOLEAN NOT NULL DEFAULT TRUE,
  applied BOOLEAN NOT NULL DEFAULT FALSE,
  scoreboard_state TEXT NOT NULL DEFAULT '',
  scoreboard_score INTEGER NOT NULL DEFAULT 0,
  blocker_count INTEGER NOT NULL DEFAULT 0,
  preview_message_count INTEGER NOT NULL DEFAULT 0,
  approved_preview_count INTEGER NOT NULL DEFAULT 0,
  live_outreach_sent_count INTEGER NOT NULL DEFAULT 0,
  warmup_sent_count INTEGER NOT NULL DEFAULT 0,
  result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  send_mail BOOLEAN NOT NULL DEFAULT FALSE,
  smtp_called BOOLEAN NOT NULL DEFAULT FALSE,
  live_outreach_allowed BOOLEAN NOT NULL DEFAULT FALSE,
  raw_recipient_addresses_included BOOLEAN NOT NULL DEFAULT FALSE,
  secrets_included BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_launch_activation_runs_created ON launch_activation_runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_launch_activation_runs_decision ON launch_activation_runs(decision);
