CREATE TABLE IF NOT EXISTS revenue_simulation_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  status text NOT NULL DEFAULT 'created',
  lead_count integer NOT NULL DEFAULT 0,
  accepted_count integer NOT NULL DEFAULT 0,
  scanner_jobs_count integer NOT NULL DEFAULT 0,
  audits_count integer NOT NULL DEFAULT 0,
  campaign_id uuid NULL,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS campaign_economics_checks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  campaign_id uuid NULL,
  product_key text NOT NULL,
  lead_count integer NOT NULL DEFAULT 0,
  expected_conversion_rate numeric NOT NULL DEFAULT 0,
  expected_revenue_cents integer NOT NULL DEFAULT 0,
  expected_cost_cents integer NOT NULL DEFAULT 0,
  expected_margin_percent numeric NOT NULL DEFAULT 0,
  risk_score integer NOT NULL DEFAULT 0,
  decision text NOT NULL DEFAULT 'review',
  reasoning_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mail_clean_window_checks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  status text NOT NULL,
  window_hours integer NOT NULL DEFAULT 24,
  bounce_or_dsn_count integer NOT NULL DEFAULT 0,
  rate_limit_count integer NOT NULL DEFAULT 0,
  spam_signal_count integer NOT NULL DEFAULT 0,
  mail_qa_decision text NOT NULL DEFAULT '',
  next_action text NOT NULL DEFAULT '',
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mailer_drafts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  direction text NOT NULL,
  category text NOT NULL,
  mailbox text NOT NULL DEFAULT '',
  recipient_hash text NOT NULL DEFAULT '',
  subject text NOT NULL,
  body text NOT NULL,
  status text NOT NULL DEFAULT 'draft',
  qa_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_campaign_economics_campaign ON campaign_economics_checks(campaign_id);
CREATE INDEX IF NOT EXISTS idx_mail_clean_window_created ON mail_clean_window_checks(created_at);
CREATE INDEX IF NOT EXISTS idx_mailer_drafts_status ON mailer_drafts(status);
