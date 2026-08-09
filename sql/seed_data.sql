-- ============================================================================
-- Milford Support Desk — sample data
-- ----------------------------------------------------------------------------
-- 5 tickets across multiple statuses / priorities / categories,
-- each with 2+ messages. Run AFTER sql/schema.sql.
--
-- NOTE: the TRUNCATE below wipes existing rows so this script is re-runnable
-- and gives a clean demo dataset. Remove it if you want to keep prior data.
-- ============================================================================

TRUNCATE ticket_messages, tickets RESTART IDENTITY CASCADE;

-- ---------------------------------------------------------------------------
-- Tickets
-- ---------------------------------------------------------------------------
INSERT INTO tickets (title, status, priority, category, created_by, created_at, updated_at) VALUES
  ('VPN disconnects every few minutes',        'open',        'high',   'access',   'aroha.ngata@milford.co.nz',   now() - interval '3 days',  now() - interval '2 hours'),
  ('Request access to Portfolio Analytics',    'in_progress', 'medium', 'access',   'liam.osullivan@milford.co.nz', now() - interval '2 days',  now() - interval '5 hours'),
  ('Dashboard shows stale NAV figures',        'open',        'urgent', 'bug',      'priya.sharma@milford.co.nz',   now() - interval '1 day',   now() - interval '40 minutes'),
  ('New monitor for standing desk',            'resolved',    'low',    'hardware', 'tama.walker@milford.co.nz',    now() - interval '9 days',  now() - interval '6 days'),
  ('Duplicate charge on corporate card',       'in_progress', 'high',   'billing',  'grace.thompson@milford.co.nz', now() - interval '4 days',  now() - interval '1 day');

-- ---------------------------------------------------------------------------
-- Messages (ticket_id looked up by title so this stays readable)
-- ---------------------------------------------------------------------------
INSERT INTO ticket_messages (ticket_id, message_text, author, created_at)
SELECT ticket_id, m.message_text, m.author, m.created_at
FROM tickets t
JOIN (VALUES
  -- Ticket 1: VPN
  ('VPN disconnects every few minutes', 'The VPN drops roughly every 5 minutes and I have to reconnect. Started this morning.', 'aroha.ngata@milford.co.nz',  now() - interval '3 days'),
  ('VPN disconnects every few minutes', 'Thanks for reporting. Which office / network are you on, and are you on Wi-Fi or wired?', 'support.desk@milford.co.nz', now() - interval '3 days' + interval '30 minutes'),
  ('VPN disconnects every few minutes', 'Auckland office, on Wi-Fi. A colleague next to me has the same issue.', 'aroha.ngata@milford.co.nz',  now() - interval '2 hours'),

  -- Ticket 2: Portfolio Analytics access
  ('Request access to Portfolio Analytics', 'Could I get read access to the Portfolio Analytics workspace? I''m joining the reporting project.', 'liam.osullivan@milford.co.nz', now() - interval '2 days'),
  ('Request access to Portfolio Analytics', 'Raised with your manager for approval. Will provision once approved.', 'support.desk@milford.co.nz',   now() - interval '5 hours'),

  -- Ticket 3: Stale NAV
  ('Dashboard shows stale NAV figures', 'The NAV dashboard is showing yesterday''s figures during market hours. This is client-facing.', 'priya.sharma@milford.co.nz', now() - interval '1 day'),
  ('Dashboard shows stale NAV figures', 'Escalating to the data platform team — the pricing feed job looks delayed.', 'support.desk@milford.co.nz', now() - interval '20 hours'),
  ('Dashboard shows stale NAV figures', 'Confirmed the 06:00 feed failed to run. Re-running now, ETA 15 minutes.', 'dataops@milford.co.nz',      now() - interval '40 minutes'),

  -- Ticket 4: Monitor (resolved)
  ('New monitor for standing desk', 'Requesting a second 27" monitor for my standing desk setup.', 'tama.walker@milford.co.nz',  now() - interval '9 days'),
  ('New monitor for standing desk', 'Approved. Collect from IT store room, level 3.',              'support.desk@milford.co.nz', now() - interval '7 days'),
  ('New monitor for standing desk', 'Picked up and installed. Thanks!',                            'tama.walker@milford.co.nz',  now() - interval '6 days'),

  -- Ticket 5: Duplicate charge
  ('Duplicate charge on corporate card', 'I was charged twice for the same conference ticket on the corporate card.', 'grace.thompson@milford.co.nz', now() - interval '4 days'),
  ('Duplicate charge on corporate card', 'We can see the duplicate. Raising a dispute with the card provider.',       'finance.ops@milford.co.nz',    now() - interval '1 day')
) AS m(title, message_text, author, created_at)
  ON t.title = m.title;
