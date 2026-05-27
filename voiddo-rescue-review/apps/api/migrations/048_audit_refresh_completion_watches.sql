CREATE TABLE IF NOT EXISTS audit_refresh_completion_watches (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  status text NOT NULL,
  dry_run boolean NOT NULL DEFAULT true,
  tracked_count integer NOT NULL DEFAULT 0,
  queued_count integer NOT NULL DEFAULT 0,
  running_count integer NOT NULL DEFAULT 0,
  completed_count integer NOT NULL DEFAULT 0,
  failed_count integer NOT NULL DEFAULT 0,
  new_completed_count integer NOT NULL DEFAULT 0,
  rescored_audit_count integer NOT NULL DEFAULT 0,
  preflight_run_count integer NOT NULL DEFAULT 0,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  send_mail boolean NOT NULL DEFAULT false,
  smtp_called boolean NOT NULL DEFAULT false,
  live_outreach_allowed boolean NOT NULL DEFAULT false,
  raw_recipient_addresses_included boolean NOT NULL DEFAULT false,
  secrets_included boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_refresh_completion_watches_created
  ON audit_refresh_completion_watches(created_at DESC);
