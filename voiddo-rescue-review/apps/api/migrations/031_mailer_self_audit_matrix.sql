CREATE TABLE IF NOT EXISTS mailer_self_audit_matrix_history (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_run_id uuid,
    coverage_score integer NOT NULL DEFAULT 0,
    checked_count integer NOT NULL DEFAULT 0,
    pass_count integer NOT NULL DEFAULT 0,
    fail_count integer NOT NULL DEFAULT 0,
    coverage_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    summary_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    send_mail boolean NOT NULL DEFAULT false,
    smtp_called boolean NOT NULL DEFAULT false,
    live_outreach_allowed boolean NOT NULL DEFAULT false,
    raw_recipient_addresses_included boolean NOT NULL DEFAULT false,
    secrets_included boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mailer_self_audit_matrix_history_created_at
    ON mailer_self_audit_matrix_history(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_mailer_self_audit_matrix_history_agent_run
    ON mailer_self_audit_matrix_history(agent_run_id);
