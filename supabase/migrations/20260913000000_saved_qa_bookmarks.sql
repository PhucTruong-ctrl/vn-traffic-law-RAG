-- Convert insert-only bookmarks into durable saved Q&A snapshots.
-- Existing bookmarks are retained; message-derived fields are backfilled where possible.
alter table public.bookmarks
  add column if not exists source_session_id uuid,
  add column if not exists user_message_id uuid,
  add column if not exists assistant_message_id uuid,
  add column if not exists question text,
  add column if not exists answer text,
  add column if not exists citations jsonb not null default '[]'::jsonb,
  add column if not exists response jsonb;

-- These references are intentionally nullable: saved snapshots survive chat/message deletion.
alter table public.bookmarks
  drop constraint if exists bookmarks_message_id_fkey,
  drop constraint if exists bookmarks_source_session_id_fkey,
  drop constraint if exists bookmarks_user_message_id_fkey,
  drop constraint if exists bookmarks_assistant_message_id_fkey;

alter table public.bookmarks
  add constraint bookmarks_source_session_id_fkey
    foreign key (source_session_id) references public.chat_sessions (id) on delete set null,
  add constraint bookmarks_user_message_id_fkey
    foreign key (user_message_id) references public.messages (id) on delete set null,
  add constraint bookmarks_assistant_message_id_fkey
    foreign key (assistant_message_id) references public.messages (id) on delete set null;

update public.bookmarks b
   set source_session_id = coalesce(b.source_session_id, m.session_id),
       assistant_message_id = coalesce(b.assistant_message_id, b.message_id),
       answer = coalesce(b.answer, m.content),
       citations = coalesce(nullif(b.citations, '[]'::jsonb), m.citations),
       response = coalesce(b.response, m.response)
  from public.messages m
 where m.id = b.message_id;

update public.bookmarks b
   set user_message_id = coalesce(
         b.user_message_id,
         (
           select u.id
             from public.messages u
            where u.session_id = b.source_session_id
              and u.user_id = b.user_id
              and u.role = 'user'
              and u.created_at <= coalesce(a.created_at, u.created_at)
            order by u.created_at desc
            limit 1
         )
       ),
       question = coalesce(
         b.question,
         (
           select u.content
             from public.messages u
            where u.session_id = b.source_session_id
              and u.user_id = b.user_id
              and u.role = 'user'
              and u.created_at <= coalesce(a.created_at, u.created_at)
            order by u.created_at desc
            limit 1
         )
       )
  from public.messages a
 where a.id = b.assistant_message_id;

alter table public.bookmarks drop column if exists message_id;

create unique index if not exists bookmarks_user_assistant_idx
  on public.bookmarks (user_id, assistant_message_id)
  where assistant_message_id is not null;
create index if not exists bookmarks_user_created_idx
  on public.bookmarks (user_id, created_at desc);
create index if not exists bookmarks_source_session_idx
  on public.bookmarks (source_session_id);
create index if not exists bookmarks_assistant_message_idx
  on public.bookmarks (assistant_message_id);

alter table public.bookmarks enable row level security;
drop policy if exists bookmarks_select_own on public.bookmarks;
create policy bookmarks_select_own on public.bookmarks for select using (user_id = auth.uid());
drop policy if exists bookmarks_insert_own on public.bookmarks;
create policy bookmarks_insert_own on public.bookmarks for insert with check (user_id = auth.uid());
drop policy if exists bookmarks_update_own on public.bookmarks;
create policy bookmarks_update_own on public.bookmarks for update using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists bookmarks_delete_own on public.bookmarks;
create policy bookmarks_delete_own on public.bookmarks for delete using (user_id = auth.uid());
