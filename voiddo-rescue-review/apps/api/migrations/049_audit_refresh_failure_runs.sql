CREATE TABLE IF NOT EXISTS audit_refresh_failure_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  status text NOT NULL,
  dry_run boolean NOT NULL DEFAULT true,
  failed_count integer NOT NULL DEFAULT 0,
  retryable_count integer NOT NULL DEFAULT 0,
  requeued_count integer NOT NULL DEFAULT 0,
  exhausted_count integer NOT NULL DEFAULT 0,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  send_mail boolean NOT NULL DEFAULT false,
  smtp_called boolean NOT NULL DEFAULT false,
  live_outreach_allowed boolean NOT NULL DEFAULT false,
  raw_recipient_addresses_included boolean NOT NULL DEFAULT false,
  secrets_included boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_refresh_failure_runs_created
  ON audit_refresh_failure_runs(created_at DESC);
