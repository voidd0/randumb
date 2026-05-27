CREATE TABLE IF NOT EXISTS campaign_preflight_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  campaign_id uuid REFERENCES campaigns(id) ON DELETE SET NULL,
  status text NOT NULL,
  decision text NOT NULL,
  checked_count integer NOT NULL DEFAULT 0,
  ready_count integer NOT NULL DEFAULT 0,
  blocker_count integer NOT NULL DEFAULT 0,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  send_mail boolean NOT NULL DEFAULT false,
  smtp_called boolean NOT NULL DEFAULT false,
  live_outreach_allowed boolean NOT NULL DEFAULT false,
  raw_recipient_addresses_included boolean NOT NULL DEFAULT false,
  secrets_included boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_campaign_preflight_runs_campaign_created
  ON campaign_preflight_runs(campaign_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_campaign_preflight_runs_created
  ON campaign_preflight_runs(created_at DESC);
