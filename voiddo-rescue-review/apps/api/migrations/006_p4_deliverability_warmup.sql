ALTER TABLE test_inboxes ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'owner_provided';
ALTER TABLE test_inboxes ADD COLUMN IF NOT EXISTS approved boolean NOT NULL DEFAULT true;

ALTER TABLE warmup_recipients ADD COLUMN IF NOT EXISTS approved boolean NOT NULL DEFAULT true;
