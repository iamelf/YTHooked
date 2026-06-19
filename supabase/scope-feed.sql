-- Burrfeed — per-user feed scoping (Part 2)
--
-- RLS already restricts reads to `owner_id is null OR owner_id = auth.uid()`
-- (see schema.sql), so scoping a teaser to one person is just a matter of
-- stamping its owner_id. Shared/demo teasers keep owner_id = null and stay
-- visible to everyone.
--
-- The husband's personalized teasers are the "-db" combos (external_id ends in
-- '-db'). Point them at his account. Run this in the Supabase SQL editor AFTER
-- he has signed in at least once (sign-in creates his auth.users row).
--
-- 1) Replace the email with the Google account he signs in with.

with owner as (
  select id from auth.users where email = 'HUSBAND_EMAIL_HERE'
)
update public.feed_items
   set owner_id = (select id from owner)
 where external_id like '%-db'
   and (select id from owner) is not null;

-- 2) Sanity check — should list only the -db rows, now owned:
-- select external_id, owner_id, title from public.feed_items where external_id like '%-db';

-- To make an item shared again (visible to all), set owner_id back to null:
-- update public.feed_items set owner_id = null where external_id = 'SOME_ID';
