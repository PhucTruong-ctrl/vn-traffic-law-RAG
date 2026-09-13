-- Safe demo seed for a fresh Supabase project.
-- No auth users or credentials are created here. Run after schema.sql and only
-- when a matching auth.users row already exists.
--
-- Usage:
--   psql "$SUPABASE_DB_URL" -v demo_user_id="<auth user UUID>" -f supabase/seed.sql
-- or paste the INSERT statements into the SQL editor after replacing the
-- placeholder UUID with an existing auth.users.id.

-- The variable is intentionally not given a default: this script refuses to
-- create data unless the operator supplies an authenticated user id.
\if :{?demo_user_id}
\else
\echo 'Set demo_user_id to an existing auth.users UUID; no seed rows inserted.'
\quit
\endif

insert into public.profiles (id, display_name)
values (:'demo_user_id'::uuid, 'Demo user')
on conflict (id) do update
set display_name = excluded.display_name;

with new_session as (
  insert into public.chat_sessions (user_id, title)
  values (:'demo_user_id'::uuid, 'Demo traffic-law chat')
  returning id
)
insert into public.messages (session_id, user_id, role, content, status)
select id, :'demo_user_id'::uuid, 'user', 'Demo question: What documents should a driver carry?', 'complete'
from new_session;

-- This seed deliberately omits feedback/bookmarks: those rows should be
-- created through the application flow after a real message is reviewed.
