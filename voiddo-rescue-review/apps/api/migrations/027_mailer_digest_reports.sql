CREATE TABLE IF NOT EXISTS mailer_digest_reports (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_run_id uuid,
    report_path text NOT NULL,
    owner_report_action_id uuid,
    email_sent boolean NOT NULL DEFAULT false,
    warmup_sent_count integer NOT NULL DEFAULT 0,
    live_outreach_sent_count integer NOT NULL DEFAULT 0,
    bounce_or_dsn_count_24h integer NOT NULL DEFAULT 0,
    rate_limit_signal_count_24h integer NOT NULL DEFAULT 0,
    blockers_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mailer_digest_reports_created ON mailer_digest_reports(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mailer_digest_reports_agent_run ON mailer_digest_reports(agent_run_id);
