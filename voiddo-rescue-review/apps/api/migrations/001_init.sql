CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS businesses (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  country text,
  city text,
  language text,
  niche text,
  source text,
  website_url text,
  domain text,
  email text,
  phone text,
  status text NOT NULL DEFAULT 'new',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS leads (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id uuid REFERENCES businesses(id) ON DELETE SET NULL,
  email text,
  contact_name text,
  role text,
  source text,
  status text NOT NULL DEFAULT 'new',
  score integer NOT NULL DEFAULT 0,
  language text,
  country text,
  city text,
  niche text,
  last_scanned_at timestamptz,
  last_contacted_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audits (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id uuid REFERENCES businesses(id) ON DELETE SET NULL,
  lead_id uuid REFERENCES leads(id) ON DELETE SET NULL,
  domain text NOT NULL,
  url text NOT NULL,
  status text NOT NULL DEFAULT 'queued',
  score integer NOT NULL DEFAULT 0,
  summary text,
  public_slug text UNIQUE NOT NULL,
  checked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_issues (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  audit_id uuid NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
  issue_type text NOT NULL,
  severity text NOT NULL,
  title text NOT NULL,
  public_text text NOT NULL,
  internal_notes text,
  evidence_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  recommendation text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS screenshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  audit_id uuid NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
  type text NOT NULL,
  file_path text NOT NULL,
  public_url text,
  viewport text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS outreach_messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id uuid REFERENCES leads(id) ON DELETE SET NULL,
  audit_id uuid REFERENCES audits(id) ON DELETE SET NULL,
  mailbox text NOT NULL,
  subject text NOT NULL,
  body text NOT NULL,
  status text NOT NULL DEFAULT 'queued',
  provider_message_id text,
  sent_at timestamptz,
  opened_at timestamptz,
  clicked_at timestamptz,
  bounced_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS email_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  outreach_message_id uuid REFERENCES outreach_messages(id) ON DELETE CASCADE,
  event_type text NOT NULL,
  payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS inbox_threads (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id uuid REFERENCES leads(id) ON DELETE SET NULL,
  mailbox text NOT NULL,
  external_thread_id text,
  classification text,
  human_review_required boolean NOT NULL DEFAULT false,
  last_message_preview text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS suppression_list (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text,
  domain text,
  reason text NOT NULL,
  source text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT suppression_email_or_domain CHECK (email IS NOT NULL OR domain IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS customers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text NOT NULL,
  business_id uuid REFERENCES businesses(id) ON DELETE SET NULL,
  paddle_customer_id text,
  status text NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS payments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id uuid REFERENCES customers(id) ON DELETE SET NULL,
  paddle_transaction_id text UNIQUE,
  amount numeric(12,2),
  currency text,
  product_key text,
  status text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS subscriptions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id uuid REFERENCES customers(id) ON DELETE SET NULL,
  paddle_subscription_id text UNIQUE,
  product_key text,
  status text NOT NULL,
  current_period_start timestamptz,
  current_period_end timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fix_requests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id uuid REFERENCES customers(id) ON DELETE SET NULL,
  audit_id uuid REFERENCES audits(id) ON DELETE SET NULL,
  issue_id uuid REFERENCES audit_issues(id) ON DELETE SET NULL,
  product_key text,
  status text NOT NULL DEFAULT 'new',
  priority text NOT NULL DEFAULT 'P2',
  title text NOT NULL,
  description text,
  evidence_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  codex_task_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS system_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  type text NOT NULL,
  severity text NOT NULL,
  message text NOT NULL,
  payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS codex_tasks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  type text NOT NULL,
  priority text NOT NULL,
  status text NOT NULL DEFAULT 'open',
  title text NOT NULL,
  description text,
  input_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  output_path text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_leads_status_score ON leads(status, score);
CREATE INDEX IF NOT EXISTS idx_audits_public_slug ON audits(public_slug);
CREATE INDEX IF NOT EXISTS idx_suppression_email ON suppression_list(lower(email));
CREATE INDEX IF NOT EXISTS idx_suppression_domain ON suppression_list(lower(domain));
CREATE INDEX IF NOT EXISTS idx_outreach_status ON outreach_messages(status, created_at);
