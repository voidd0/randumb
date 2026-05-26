CREATE TABLE IF NOT EXISTS scout_sources (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  source_type text NOT NULL,
  country text,
  language text,
  niche text,
  status text NOT NULL DEFAULT 'active',
  config_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS scout_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id uuid REFERENCES scout_sources(id) ON DELETE SET NULL,
  status text NOT NULL DEFAULT 'queued',
  country text,
  city text,
  niche text,
  language text,
  found_count integer NOT NULL DEFAULT 0,
  accepted_count integer NOT NULL DEFAULT 0,
  rejected_count integer NOT NULL DEFAULT 0,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  error text,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS scout_leads (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scout_run_id uuid REFERENCES scout_runs(id) ON DELETE SET NULL,
  business_name text,
  domain text,
  website_url text,
  email text,
  phone text,
  country text,
  city text,
  language text,
  niche text,
  source_url text,
  confidence integer NOT NULL DEFAULT 50,
  status text NOT NULL DEFAULT 'new',
  rejection_reason text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_scout_leads_domain_email
  ON scout_leads(lower(coalesce(domain, '')), lower(coalesce(email, '')));

CREATE TABLE IF NOT EXISTS lead_scores (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id uuid REFERENCES leads(id) ON DELETE CASCADE,
  audit_id uuid REFERENCES audits(id) ON DELETE SET NULL,
  technical_score integer NOT NULL DEFAULT 0,
  sales_score integer NOT NULL DEFAULT 0,
  urgency_score integer NOT NULL DEFAULT 0,
  value_score integer NOT NULL DEFAULT 0,
  deliverability_score integer NOT NULL DEFAULT 0,
  final_score integer NOT NULL DEFAULT 0,
  reasoning_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lead_scores_lead_created ON lead_scores(lead_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_lead_scores_final ON lead_scores(final_score DESC);

CREATE TABLE IF NOT EXISTS campaigns (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  status text NOT NULL DEFAULT 'draft',
  country text,
  language text,
  niche text,
  offer_key text,
  max_daily_sends integer NOT NULL DEFAULT 20,
  max_hourly_sends integer NOT NULL DEFAULT 5,
  dry_run boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS campaign_leads (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  campaign_id uuid REFERENCES campaigns(id) ON DELETE CASCADE,
  lead_id uuid REFERENCES leads(id) ON DELETE CASCADE,
  audit_id uuid REFERENCES audits(id) ON DELETE SET NULL,
  status text NOT NULL DEFAULT 'preview',
  score integer NOT NULL DEFAULT 0,
  preview_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(campaign_id, lead_id)
);

CREATE TABLE IF NOT EXISTS agent_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agent text NOT NULL,
  status text NOT NULL DEFAULT 'queued',
  started_at timestamptz,
  completed_at timestamptz,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  error text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_agent_created ON agent_runs(agent, created_at DESC);

CREATE TABLE IF NOT EXISTS mail_throttle_state (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scope text NOT NULL,
  scope_key text NOT NULL,
  last_sent_at timestamptz,
  sent_last_hour integer NOT NULL DEFAULT 0,
  sent_today integer NOT NULL DEFAULT 0,
  backoff_until timestamptz,
  reason text,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(scope, scope_key)
);

CREATE TABLE IF NOT EXISTS onboarding_tasks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id uuid REFERENCES customers(id) ON DELETE CASCADE,
  product_key text,
  status text NOT NULL DEFAULT 'open',
  task_type text NOT NULL,
  title text NOT NULL,
  payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS monitoring_targets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id uuid REFERENCES customers(id) ON DELETE CASCADE,
  domain text NOT NULL,
  site_url text NOT NULL,
  status text NOT NULL DEFAULT 'active',
  last_checked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
