-- Migrate feedback ratings from the legacy 1..5 scale to binary like/dislike.
-- Existing out-of-range rows are intentionally preserved and cause a clear failure;
-- callers must handle that data explicitly before rerunning this migration.
do $$
declare
  invalid_count bigint;
  constraint_record record;
begin
  select count(*)
    into invalid_count
    from public.feedback
   where rating not in (0, 1);

  if invalid_count > 0 then
    raise exception using
      errcode = 'check_violation',
      message = format(
        'Cannot migrate public.feedback.rating: %s existing row(s) have ratings outside (0, 1)',
        invalid_count
      ),
      hint = 'Handle or remove invalid feedback rows explicitly, then rerun the migration.';
  end if;

  for constraint_record in
    select c.conname
      from pg_constraint c
      join pg_class t on t.oid = c.conrelid
      join pg_namespace n on n.oid = t.relnamespace
     where n.nspname = 'public'
       and t.relname = 'feedback'
       and c.contype = 'c'
       and pg_get_constraintdef(c.oid) ~* '\\mrating\\M'
       and c.conname <> 'feedback_rating_binary_check'
  loop
    execute format(
      'alter table public.feedback drop constraint %I',
      constraint_record.conname
    );
  end loop;

  if not exists (
    select 1
      from pg_constraint c
      join pg_class t on t.oid = c.conrelid
      join pg_namespace n on n.oid = t.relnamespace
     where n.nspname = 'public'
       and t.relname = 'feedback'
       and c.conname = 'feedback_rating_binary_check'
  ) then
    alter table public.feedback
      add constraint feedback_rating_binary_check check (rating in (0, 1));
  end if;
end
$$;
