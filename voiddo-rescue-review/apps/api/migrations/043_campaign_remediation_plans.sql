CREATE TABLE IF NOT EXISTS campaign_remediation_plans (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  campaign_id uuid REFERENCES campaigns(id) ON DELETE SET NULL,
  status text NOT NULL,
  blocker_count integer NOT NULL DEFAULT 0,
  task_count integer NOT NULL DEFAULT 0,
  plan_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  send_mail boolean NOT NULL DEFAULT false,
  smtp_called boolean NOT NULL DEFAULT false,
  live_outreach_allowed boolean NOT NULL DEFAULT false,
  raw_recipient_addresses_included boolean NOT NULL DEFAULT false,
  secrets_included boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_campaign_remediation_plans_campaign_created
  ON campaign_remediation_plans(campaign_id, created_at DESC);
