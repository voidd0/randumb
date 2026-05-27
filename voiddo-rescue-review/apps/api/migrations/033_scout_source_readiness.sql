CREATE TABLE IF NOT EXISTS scout_source_readiness_checks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id uuid NOT NULL REFERENCES scout_sources(id) ON DELETE CASCADE,
  status text NOT NULL,
  score integer NOT NULL DEFAULT 0,
  row_count integer NOT NULL DEFAULT 0,
  parseable_count integer NOT NULL DEFAULT 0,
  domain_coverage numeric(6,4) NOT NULL DEFAULT 0,
  source_url_coverage numeric(6,4) NOT NULL DEFAULT 0,
  confidence_average numeric(6,4) NOT NULL DEFAULT 0,
  duplicate_domain_count integer NOT NULL DEFAULT 0,
  excluded_niche_count integer NOT NULL DEFAULT 0,
  suppressed_email_count integer NOT NULL DEFAULT 0,
  invalid_email_count integer NOT NULL DEFAULT 0,
  issues_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  send_mail boolean NOT NULL DEFAULT false,
  smtp_called boolean NOT NULL DEFAULT false,
  live_outreach_allowed boolean NOT NULL DEFAULT false,
  raw_recipient_addresses_included boolean NOT NULL DEFAULT false,
  secrets_included boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_scout_source_readiness_source_created
  ON scout_source_readiness_checks(source_id, created_at DESC);
