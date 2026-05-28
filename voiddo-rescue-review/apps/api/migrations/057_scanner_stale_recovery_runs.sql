CREATE TABLE IF NOT EXISTS scanner_stale_recovery_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    status text NOT NULL,
    dry_run boolean NOT NULL DEFAULT true,
    candidate_count integer NOT NULL DEFAULT 0,
    requeued_count integer NOT NULL DEFAULT 0,
    failed_count integer NOT NULL DEFAULT 0,
    older_than_minutes integer NOT NULL DEFAULT 15,
    result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    send_mail boolean NOT NULL DEFAULT false,
    smtp_called boolean NOT NULL DEFAULT false,
    live_outreach_allowed boolean NOT NULL DEFAULT false,
    raw_recipient_addresses_included boolean NOT NULL DEFAULT false,
    secrets_included boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_scanner_stale_recovery_runs_created
    ON scanner_stale_recovery_runs(created_at DESC);
