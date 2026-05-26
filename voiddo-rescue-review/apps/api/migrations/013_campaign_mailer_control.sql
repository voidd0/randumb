CREATE TABLE IF NOT EXISTS campaign_readiness_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  campaign_id uuid REFERENCES campaigns(id) ON DELETE CASCADE,
  status text NOT NULL,
  lead_count integer NOT NULL DEFAULT 0,
  qualified_count integer NOT NULL DEFAULT 0,
  min_audit_strength integer NOT NULL DEFAULT 0,
  economics_decision text NOT NULL DEFAULT 'missing',
  mail_safety_decision text NOT NULL DEFAULT 'missing',
  visual_safety_decision text NOT NULL DEFAULT 'missing',
  blockers_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  summary_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS outbound_mailer_decisions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  outreach_message_id uuid REFERENCES outreach_messages(id) ON DELETE SET NULL,
  campaign_id uuid REFERENCES campaigns(id) ON DELETE SET NULL,
  mailbox text NOT NULL DEFAULT 'audit@voiddorescue.com',
  recipient_hash text NOT NULL DEFAULT '',
  template_key text NOT NULL DEFAULT '',
  status text NOT NULL,
  action text NOT NULL,
  reason text NOT NULL,
  checks_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS reply_action_plans (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  mailbox text NOT NULL DEFAULT 'support@voiddorescue.com',
  classification text NOT NULL,
  confidence numeric NOT NULL DEFAULT 0,
  safe_action text NOT NULL,
  auto_reply_allowed boolean NOT NULL DEFAULT false,
  human_review_required boolean NOT NULL DEFAULT true,
  reason text NOT NULL DEFAULT '',
  evidence_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS scout_provenance_scores (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scout_run_id uuid REFERENCES scout_runs(id) ON DELETE CASCADE,
  status text NOT NULL,
  score integer NOT NULL DEFAULT 0,
  source_url_coverage numeric NOT NULL DEFAULT 0,
  confidence_average numeric NOT NULL DEFAULT 0,
  duplicate_or_rejected_count integer NOT NULL DEFAULT 0,
  issues_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
