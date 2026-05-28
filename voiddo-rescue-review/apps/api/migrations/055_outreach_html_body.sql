ALTER TABLE outreach_messages
  ADD COLUMN IF NOT EXISTS html_body text NOT NULL DEFAULT '';
