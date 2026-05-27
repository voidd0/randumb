CREATE TABLE IF NOT EXISTS contact_enrichment_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provider text NOT NULL,
  status text NOT NULL,
  scanned_count integer NOT NULL DEFAULT 0,
  enriched_count integer NOT NULL DEFAULT 0,
  skipped_count integer NOT NULL DEFAULT 0,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  send_mail boolean NOT NULL DEFAULT false,
  smtp_called boolean NOT NULL DEFAULT false,
  live_outreach_allowed boolean NOT NULL DEFAULT false,
  raw_recipient_addresses_included boolean NOT NULL DEFAULT false,
  secrets_included boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
