CREATE TABLE IF NOT EXISTS campaign_action_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  campaign_id uuid REFERENCES campaigns(id) ON DELETE SET NULL,
  action text NOT NULL,
  status text NOT NULL,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  send_mail boolean NOT NULL DEFAULT false,
  smtp_called boolean NOT NULL DEFAULT false,
  live_outreach_allowed boolean NOT NULL DEFAULT false,
  raw_recipient_addresses_included boolean NOT NULL DEFAULT false,
  secrets_included boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_campaign_action_runs_created_at ON campaign_action_runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_campaign_action_runs_campaign_id ON campaign_action_runs(campaign_id);
