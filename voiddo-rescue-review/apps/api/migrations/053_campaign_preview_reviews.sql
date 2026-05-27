CREATE TABLE IF NOT EXISTS campaign_preview_reviews (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  campaign_lead_id uuid NOT NULL REFERENCES campaign_leads(id) ON DELETE CASCADE,
  action text NOT NULL CHECK (action IN ('approved', 'held', 'rejected')),
  reason text NOT NULL DEFAULT '',
  actor text NOT NULL DEFAULT 'admin',
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  send_mail boolean NOT NULL DEFAULT false,
  smtp_called boolean NOT NULL DEFAULT false,
  live_outreach_allowed boolean NOT NULL DEFAULT false,
  raw_recipient_addresses_included boolean NOT NULL DEFAULT false,
  secrets_included boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_campaign_preview_reviews_campaign_lead
  ON campaign_preview_reviews(campaign_lead_id, created_at DESC);

