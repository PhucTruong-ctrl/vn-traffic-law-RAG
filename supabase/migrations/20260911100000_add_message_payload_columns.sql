-- Restore message payload columns on projects created from the older schema.
-- Safe to run repeatedly and harmless when the columns already exist.
alter table public.messages add column if not exists response jsonb;
alter table public.messages add column if not exists citations jsonb not null default '[]'::jsonb;
alter table public.messages add column if not exists metadata jsonb not null default '{}'::jsonb;
