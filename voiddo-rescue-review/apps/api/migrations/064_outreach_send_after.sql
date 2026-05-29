ALTER TABLE outreach_messages
  ADD COLUMN IF NOT EXISTS send_after timestamptz;

CREATE INDEX IF NOT EXISTS idx_outreach_messages_due_queue
  ON outreach_messages(status, send_after, created_at)
  WHERE status = 'queued';
