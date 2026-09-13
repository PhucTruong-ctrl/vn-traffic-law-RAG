-- VN traffic-law RAG application schema for Supabase.
-- Run in SQL Editor or with `supabase db query < supabase/schema.sql`.
-- Qdrant/RAG documents remain outside this database. No credentials belong here.

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
  updated_at timestamptz not null default now(),
  unique (id, user_id)
);

create table if not exists public.messages (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null,
  user_id uuid not null references auth.users (id) on delete cascade,
  role text not null default 'user' check (role in ('user', 'assistant')),
  content text not null check (char_length(btrim(content)) > 0),
  status text not null default 'complete' check (char_length(btrim(status)) between 1 and 30),
  response jsonb,
  citations jsonb not null default '[]'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint messages_session_user_fk foreign key (session_id, user_id)
    references public.chat_sessions (id, user_id) on delete cascade
);

create table if not exists public.feedback (
  id uuid primary key default gen_random_uuid(),
  message_id uuid not null references public.messages (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  rating integer not null check (rating in (0, 1)),
  comment text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (message_id, user_id)
);

create table if not exists public.bookmarks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  source_session_id uuid references public.chat_sessions (id) on delete set null,
  user_message_id uuid references public.messages (id) on delete set null,
  assistant_message_id uuid references public.messages (id) on delete set null,
  question text not null check (char_length(btrim(question)) > 0),
  answer text not null check (char_length(btrim(answer)) > 0),
  citations jsonb not null default '[]'::jsonb,
  response jsonb,
  created_at timestamptz not null default now(),
  unique (user_id, assistant_message_id)
);

create index if not exists chat_sessions_user_updated_idx on public.chat_sessions (user_id, updated_at desc) where deleted = false;
create index if not exists messages_session_created_idx on public.messages (session_id, created_at);
create index if not exists messages_user_created_idx on public.messages (user_id, created_at);
create index if not exists feedback_user_created_idx on public.feedback (user_id, created_at desc);
create index if not exists bookmarks_user_created_idx on public.bookmarks (user_id, created_at desc);
create index if not exists bookmarks_source_session_idx on public.bookmarks (source_session_id);
create index if not exists bookmarks_assistant_message_idx on public.bookmarks (assistant_message_id);

alter table public.profiles enable row level security;
alter table public.chat_sessions enable row level security;
alter table public.messages enable row level security;
alter table public.feedback enable row level security;
alter table public.bookmarks enable row level security;

drop policy if exists bookmarks_select_own on public.bookmarks;
create policy bookmarks_select_own on public.bookmarks for select using (user_id = auth.uid());
drop policy if exists bookmarks_insert_own on public.bookmarks;
create policy bookmarks_insert_own on public.bookmarks for insert with check (user_id = auth.uid());
drop policy if exists bookmarks_update_own on public.bookmarks;
create policy bookmarks_update_own on public.bookmarks for update using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists bookmarks_delete_own on public.bookmarks;
create policy bookmarks_delete_own on public.bookmarks for delete using (user_id = auth.uid());
