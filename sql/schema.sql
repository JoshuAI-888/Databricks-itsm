-- ============================================================================
-- Milford Support Desk — Lakebase (PostgreSQL) schema
-- ----------------------------------------------------------------------------
-- Two related tables:
--   tickets           one row per support ticket
--   ticket_messages   one row per message; each references a ticket
--
-- Safe to run more than once (uses IF NOT EXISTS). Loading sample data is a
-- separate step: sql/seed_data.sql.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- tickets
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title       TEXT        NOT NULL,
    status      TEXT        NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'in_progress', 'resolved', 'closed')),
    priority    TEXT        NOT NULL DEFAULT 'medium'
                CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    category    TEXT        NOT NULL DEFAULT 'general'
                CHECK (category IN ('general', 'access', 'bug', 'hardware',
                                    'billing', 'feature')),
    created_by  TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- ticket_messages
--   ticket_id references tickets(ticket_id).
--   ON DELETE CASCADE: deleting a ticket removes its messages automatically.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ticket_messages (
    message_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ticket_id    BIGINT      NOT NULL
                 REFERENCES tickets (ticket_id) ON DELETE CASCADE,
    message_text TEXT        NOT NULL,
    author       TEXT        NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Indexes for the access patterns the app uses.
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_ticket_messages_ticket_id
    ON ticket_messages (ticket_id);

CREATE INDEX IF NOT EXISTS idx_tickets_status
    ON tickets (status);

CREATE INDEX IF NOT EXISTS idx_tickets_updated_at
    ON tickets (updated_at DESC);
