CREATE TABLE IF NOT EXISTS mailer_business_kpi_history (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_run_id uuid,
    replies_count integer NOT NULL DEFAULT 0,
    safe_actions_queued integer NOT NULL DEFAULT 0,
    blocked_actions integer NOT NULL DEFAULT 0,
    action_queue_rows integer NOT NULL DEFAULT 0,
    send_ledger_rows integer NOT NULL DEFAULT 0,
    resolver_audit_rows integer NOT NULL DEFAULT 0,
    policy_score integer,
    policy_decision text NOT NULL DEFAULT 'MISSING',
    policy_trend_direction text NOT NULL DEFAULT 'insufficient_history',
    warmup_scheduled_count integer NOT NULL DEFAULT 0,
    warmup_sent_count integer NOT NULL DEFAULT 0,
    live_outreach_sent_count integer NOT NULL DEFAULT 0,
    mail_qa_decision text NOT NULL DEFAULT 'unknown',
    launch_readiness_state text NOT NULL DEFAULT 'unknown',
    summary_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    send_mail boolean NOT NULL DEFAULT false,
    smtp_called boolean NOT NULL DEFAULT false,
    live_outreach_allowed boolean NOT NULL DEFAULT false,
    raw_recipient_addresses_included boolean NOT NULL DEFAULT false,
    secrets_included boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mailer_business_kpi_history_created_at
    ON mailer_business_kpi_history(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_mailer_business_kpi_history_agent_run
    ON mailer_business_kpi_history(agent_run_id);
