CREATE TABLE IF NOT EXISTS mailer_ops_retention_reports (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_run_id uuid,
    report_path text NOT NULL,
    deleted_synthetic_count integer NOT NULL DEFAULT 0,
    retained_real_count integer NOT NULL DEFAULT 0,
    retained_synthetic_count integer NOT NULL DEFAULT 0,
    send_mail boolean NOT NULL DEFAULT false,
    smtp_called boolean NOT NULL DEFAULT false,
    live_outreach_allowed boolean NOT NULL DEFAULT false,
    raw_recipient_addresses_included boolean NOT NULL DEFAULT false,
    secrets_included boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mailer_ops_retention_reports_created_at
    ON mailer_ops_retention_reports(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_mailer_ops_retention_reports_agent_run
    ON mailer_ops_retention_reports(agent_run_id);
