CREATE TABLE IF NOT EXISTS audit_evidence_remediation_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  status text NOT NULL,
  candidate_count integer NOT NULL DEFAULT 0,
  queued_scanner_jobs integer NOT NULL DEFAULT 0,
  codex_task_count integer NOT NULL DEFAULT 0,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  send_mail boolean NOT NULL DEFAULT false,
  smtp_called boolean NOT NULL DEFAULT false,
  live_outreach_allowed boolean NOT NULL DEFAULT false,
  raw_recipient_addresses_included boolean NOT NULL DEFAULT false,
  secrets_included boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
