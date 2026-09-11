-- Supabase dashboard setup:
-- 1. Open SQL Editor in the project dashboard.
-- 2. Run this file once after enabling Email/Password (or another auth provider).
-- 3. Keep Qdrant separate; this schema stores only auth-linked application data.

create extension if not exists pgcrypto;

create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  display_name text,
  avatar_url text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.chat_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  title text not null default 'New chat' check (char_length(btrim(title)) between 1 and 200),
  deleted boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.messages (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.chat_sessions (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  role text not null default 'user' check (role in ('user', 'assistant')),
  content text not null check (char_length(btrim(content)) > 0),
  status text not null default 'complete' check (char_length(btrim(status)) between 1 and 30),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint messages_session_user_fk foreign key (session_id, user_id)
    references public.chat_sessions (id, user_id) on delete cascade
);

create table if not exists public.feedback (
  id uuid primary key default gen_random_uuid(),
  message_id uuid not null references public.messages (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  rating integer not null check (rating between 1 and 5),
  comment text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (message_id, user_id)
);

create table if not exists public.bookmarks (
  id uuid primary key default gen_random_uuid(),
  message_id uuid not null references public.messages (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  created_at timestamptz not null default now(),
  unique (message_id, user_id)
);

create index if not exists chat_sessions_user_updated_idx
  on public.chat_sessions (user_id, updated_at desc)
  where deleted = false;
create index if not exists messages_session_created_idx
  on public.messages (session_id, created_at);
create index if not exists messages_user_created_idx
  on public.messages (user_id, created_at);
create index if not exists feedback_user_created_idx
  on public.feedback (user_id, created_at desc);
create index if not exists bookmarks_user_created_idx
  on public.bookmarks (user_id, created_at desc);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists profiles_set_updated_at on public.profiles;
create trigger profiles_set_updated_at
before update on public.profiles
for each row execute function public.set_updated_at();

drop trigger if exists chat_sessions_set_updated_at on public.chat_sessions;
create trigger chat_sessions_set_updated_at
before update on public.chat_sessions
for each row execute function public.set_updated_at();

drop trigger if exists messages_set_updated_at on public.messages;
create trigger messages_set_updated_at
before update on public.messages
for each row execute function public.set_updated_at();

drop trigger if exists feedback_set_updated_at on public.feedback;
create trigger feedback_set_updated_at
before update on public.feedback
for each row execute function public.set_updated_at();

alter table public.profiles enable row level security;
alter table public.chat_sessions enable row level security;
alter table public.messages enable row level security;
alter table public.feedback enable row level security;
alter table public.bookmarks enable row level security;

-- Policies intentionally use auth.uid() ownership on every operation.
drop policy if exists profiles_select_own on public.profiles;
create policy profiles_select_own on public.profiles for select using (id = auth.uid());
drop policy if exists profiles_insert_own on public.profiles;
create policy profiles_insert_own on public.profiles for insert with check (id = auth.uid());
drop policy if exists profiles_update_own on public.profiles;
create policy profiles_update_own on public.profiles for update using (id = auth.uid()) with check (id = auth.uid());
drop policy if exists profiles_delete_own on public.profiles;
create policy profiles_delete_own on public.profiles for delete using (id = auth.uid());

drop policy if exists chat_sessions_select_own on public.chat_sessions;
create policy chat_sessions_select_own on public.chat_sessions for select using (user_id = auth.uid());
drop policy if exists chat_sessions_insert_own on public.chat_sessions;
create policy chat_sessions_insert_own on public.chat_sessions for insert with check (user_id = auth.uid());
drop policy if exists chat_sessions_update_own on public.chat_sessions;
create policy chat_sessions_update_own on public.chat_sessions for update using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists chat_sessions_delete_own on public.chat_sessions;
create policy chat_sessions_delete_own on public.chat_sessions for delete using (user_id = auth.uid());

drop policy if exists messages_select_own on public.messages;
create policy messages_select_own on public.messages for select using (user_id = auth.uid());
drop policy if exists messages_insert_own on public.messages;
create policy messages_insert_own on public.messages for insert with check (user_id = auth.uid());
drop policy if exists messages_update_own on public.messages;
create policy messages_update_own on public.messages for update using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists messages_delete_own on public.messages;
create policy messages_delete_own on public.messages for delete using (user_id = auth.uid());

drop policy if exists feedback_select_own on public.feedback;
create policy feedback_select_own on public.feedback for select using (user_id = auth.uid());
drop policy if exists feedback_insert_own on public.feedback;
create policy feedback_insert_own on public.feedback for insert with check (user_id = auth.uid());
drop policy if exists feedback_update_own on public.feedback;
create policy feedback_update_own on public.feedback for update using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists feedback_delete_own on public.feedback;
create policy feedback_delete_own on public.feedback for delete using (user_id = auth.uid());

drop policy if exists bookmarks_select_own on public.bookmarks;
create policy bookmarks_select_own on public.bookmarks for select using (user_id = auth.uid());
drop policy if exists bookmarks_insert_own on public.bookmarks;
create policy bookmarks_insert_own on public.bookmarks for insert with check (user_id = auth.uid());
drop policy if exists bookmarks_update_own on public.bookmarks;
create policy bookmarks_update_own on public.bookmarks for update using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists bookmarks_delete_own on public.bookmarks;
create policy bookmarks_delete_own on public.bookmarks for delete using (user_id = auth.uid());
