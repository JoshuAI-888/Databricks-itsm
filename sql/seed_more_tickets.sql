-- ============================================================================
-- Milford Support Desk — additional sample tickets for time-period reporting
-- ----------------------------------------------------------------------------
-- Adds 50 tickets spread across the last ~12 months, each with 1–4 messages,
-- so the reporting views have enough history to be meaningful.
--
-- IMPORTANT — this script is ADDITIVE and RE-RUNNABLE:
--   * It does NOT truncate. Existing tickets (including the 5 from
--     sql/seed_data.sql) are left untouched.
--   * Each ticket is inserted only WHERE NOT EXISTS a ticket with the same
--     title, so running it twice does not create duplicates.
--
-- Contrast with sql/seed_data.sql, which DOES truncate and is meant for
-- rebuilding a clean demo dataset from scratch.
--
-- Run after sql/schema.sql (and usually after sql/seed_data.sql).
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Tickets
--   days_ago drives created_at, spreading rows over roughly the last year.
--   age_hours is how long after creation the ticket was last touched; it is
--   clamped below so updated_at never lands in the future.
-- ---------------------------------------------------------------------------
WITH seed (title, status, priority, category, created_by, days_ago, age_hours) AS (
    VALUES
    -- ---- ~11-12 months ago -------------------------------------------------
    ('Laptop fan running constantly',                 'closed',      'low',    'hardware', 'tama.walker@milford.co.nz',     352, 96),
    ('Cannot open shared drive from home',            'closed',      'medium', 'access',   'aroha.ngata@milford.co.nz',      344, 48),
    ('Payroll export missing final column',           'closed',      'high',   'bug',      'grace.thompson@milford.co.nz',   337, 72),
    ('Request second monitor for reception',          'closed',      'low',    'hardware', 'nikau.rangi@milford.co.nz',      330, 120),
    ('Outlook calendar not syncing on phone',         'closed',      'medium', 'bug',      'priya.sharma@milford.co.nz',     322, 36),
    -- ---- ~9-10 months ago --------------------------------------------------
    ('Slow login to trading terminal',                'closed',      'high',   'bug',      'liam.osullivan@milford.co.nz',   301, 60),
    ('Add contractor to Fund Ops distribution list',  'closed',      'low',    'access',   'mereana.hall@milford.co.nz',     294, 24),
    ('Duplicate invoice from stationery supplier',    'closed',      'medium', 'billing',  'grace.thompson@milford.co.nz',   287, 96),
    ('Docking station not charging',                  'closed',      'medium', 'hardware', 'tama.walker@milford.co.nz',      279, 30),
    ('Two-factor prompt loops on new phone',          'closed',      'urgent', 'access',   'aroha.ngata@milford.co.nz',      271, 12),
    ('Client statement PDF renders blank page',       'closed',      'high',   'bug',      'priya.sharma@milford.co.nz',     264, 84),
    ('Meeting room display shows no signal',          'closed',      'low',    'hardware', 'nikau.rangi@milford.co.nz',      258, 18),
    -- ---- ~7-8 months ago ---------------------------------------------------
    ('Bulk upload rejects valid IRD numbers',         'open',        'urgent', 'bug',      'liam.osullivan@milford.co.nz',   239, 5700),
    ('Access to Compliance SharePoint site',          'closed',      'medium', 'access',   'mereana.hall@milford.co.nz',     231, 26),
    ('Corporate card declined at conference',         'closed',      'high',   'billing',  'grace.thompson@milford.co.nz',   224, 14),
    ('Keyboard keys sticking after spill',            'closed',      'low',    'hardware', 'tama.walker@milford.co.nz',      217, 40),
    ('Fund performance widget shows stale data',      'closed',      'high',   'bug',      'priya.sharma@milford.co.nz',     209, 66),
    ('New starter setup for Auckland office',         'closed',      'medium', 'general',  'nikau.rangi@milford.co.nz',      202, 90),
    -- ---- ~5-6 months ago ---------------------------------------------------
    ('VPN drops when switching networks',             'closed',      'high',   'access',   'aroha.ngata@milford.co.nz',      181, 52),
    ('Request Bloomberg terminal access',             'closed',      'medium', 'access',   'liam.osullivan@milford.co.nz',   174, 120),
    ('Expense report rejects NZD amounts',            'closed',      'medium', 'billing',  'grace.thompson@milford.co.nz',   167, 34),
    ('Printer on level 3 offline',                    'closed',      'low',    'hardware', 'mereana.hall@milford.co.nz',     159, 8),
    ('Client search returns no results for macrons',  'closed',      'high',   'bug',      'priya.sharma@milford.co.nz',     152, 70),
    -- Deliberately long-running: raised months ago but still being worked on, so
    -- the "Last activity" date basis visibly differs from "Date raised" in
    -- reporting. Without a few of these, both bases return the same rows.
    ('Add SSO for the new reporting portal',          'in_progress', 'medium', 'feature',  'liam.osullivan@milford.co.nz',   145, 3384),
    -- ---- ~3-4 months ago ---------------------------------------------------
    ('Mobile app crashes on portfolio tab',           'resolved',    'urgent', 'bug',      'aroha.ngata@milford.co.nz',      118, 44),
    ('Request standing desk for Wellington',          'resolved',    'low',    'hardware', 'tama.walker@milford.co.nz',      111, 150),
    ('Incorrect GST on adviser invoices',             'resolved',    'high',   'billing',  'grace.thompson@milford.co.nz',   104, 58),
    ('Export to CSV truncates long notes',            'resolved',    'medium', 'bug',      'priya.sharma@milford.co.nz',      97, 30),
    ('Grant read access to KiwiSaver dashboards',     'resolved',    'medium', 'access',   'mereana.hall@milford.co.nz',      90, 22),
    ('Add dark mode to internal tools',               'in_progress', 'low',    'feature',  'nikau.rangi@milford.co.nz',       83, 1896),
    ('Headset microphone not detected in Teams',      'resolved',    'medium', 'hardware', 'tama.walker@milford.co.nz',       76, 16),
    ('Nightly reconciliation job failed twice',       'resolved',    'urgent', 'bug',      'liam.osullivan@milford.co.nz',    69, 10),
    -- ---- ~1-2 months ago ---------------------------------------------------
    ('Shared mailbox missing from new laptop',        'resolved',    'medium', 'access',   'aroha.ngata@milford.co.nz',       58, 20),
    ('Adviser portal times out on large clients',     'resolved',    'high',   'bug',      'priya.sharma@milford.co.nz',      51, 40),
    ('Request additional storage for Fund Ops',       'resolved',    'low',    'general',  'mereana.hall@milford.co.nz',      44, 64),
    ('Card reader not recognised at front desk',      'resolved',    'medium', 'hardware', 'nikau.rangi@milford.co.nz',       37, 12),
    ('Bulk email to clients stuck in outbox',         'resolved',    'urgent', 'bug',      'grace.thompson@milford.co.nz',    33,  6),
    ('Add audit log export to admin console',         'in_progress', 'medium', 'feature',  'liam.osullivan@milford.co.nz',    29, 96),
    -- ---- last month --------------------------------------------------------
    ('Password reset email never arrives',            'in_progress', 'high',   'access',   'aroha.ngata@milford.co.nz',       24, 18),
    ('Duplicate charge on travel booking',            'in_progress', 'high',   'billing',  'grace.thompson@milford.co.nz',    21, 30),
    ('Reporting page slow after latest release',      'in_progress', 'medium', 'bug',      'priya.sharma@milford.co.nz',      18, 26),
    ('Replace failing SSD in analyst workstation',    'in_progress', 'urgent', 'hardware', 'tama.walker@milford.co.nz',       15,  9),
    ('Access request for new compliance analyst',     'in_progress', 'medium', 'access',   'mereana.hall@milford.co.nz',      12, 14),
    ('Add bulk status update to support desk',        'open',        'low',    'feature',  'nikau.rangi@milford.co.nz',       10, 48),
    -- ---- last two weeks ----------------------------------------------------
    ('Teams call quality poor in board room',         'open',        'medium', 'hardware', 'liam.osullivan@milford.co.nz',     8, 10),
    ('Client onboarding form rejects PO Box',         'open',        'high',   'bug',      'priya.sharma@milford.co.nz',       6,  5),
    ('Request access to Risk data warehouse',         'open',        'medium', 'access',   'mereana.hall@milford.co.nz',       5, 20),
    ('Monthly fee run produced zero rows',            'open',        'urgent', 'billing',  'grace.thompson@milford.co.nz',     3,  2),
    ('Laptop will not wake from sleep',               'open',        'low',    'hardware', 'tama.walker@milford.co.nz',        2,  4),
    ('Add saved filters to the ticket list',          'open',        'low',    'feature',  'aroha.ngata@milford.co.nz',        1,  1)
),
-- Only insert titles that aren't already present, so re-runs are harmless.
fresh AS (
    SELECT s.*
    FROM seed s
    WHERE NOT EXISTS (SELECT 1 FROM tickets t WHERE t.title = s.title)
),
inserted AS (
    INSERT INTO tickets (title, status, priority, category, created_by, created_at, updated_at)
    SELECT
        title, status, priority, category, created_by,
        now() - make_interval(days => days_ago),
        -- last touched age_hours after creation, but never in the future
        LEAST(
            now() - make_interval(days => days_ago) + make_interval(hours => age_hours),
            now() - interval '1 minute'
        )
    FROM fresh
    RETURNING ticket_id, title, status, created_by, created_at, updated_at
)
-- -------------------------------------------------------------------------
-- Messages: 1–4 per new ticket, spaced between created_at and updated_at.
-- -------------------------------------------------------------------------
INSERT INTO ticket_messages (ticket_id, message_text, author, created_at)
SELECT
    i.ticket_id,
    CASE n
        WHEN 1 THEN 'Logged via the service desk. ' || i.title || '. Reproduced and triaged.'
        WHEN 2 THEN 'Thanks for raising this — assigned to the platform team for investigation.'
        WHEN 3 THEN 'Update: root cause identified, change scheduled for the next maintenance window.'
        ELSE        'Closing the loop here. Please reopen if it recurs.'
    END,
    CASE WHEN n = 1 THEN i.created_by ELSE 'support.desk@milford.co.nz' END,
    -- spread messages evenly across the ticket's lifetime
    i.created_at + (i.updated_at - i.created_at) * (n::numeric / 5)
FROM inserted i
CROSS JOIN generate_series(1, 4) AS n
-- Older, closed tickets get the full thread; recent ones get fewer messages.
WHERE n <= 1 + (i.ticket_id % 4);
