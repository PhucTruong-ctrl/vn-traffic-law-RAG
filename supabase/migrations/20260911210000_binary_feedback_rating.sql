-- Migrate feedback ratings from legacy 1..5 scale to binary like/dislike.
-- Legacy positive ratings map to LIKE; zero and negative values map to DISLIKE.
do $$
declare
  constraint_record record;
begin
  for constraint_record in
    select c.conname
      from pg_constraint c
      join pg_class t on t.oid = c.conrelid
      join pg_namespace n on n.oid = t.relnamespace
     where n.nspname = 'public'
       and t.relname = 'feedback'
       and c.contype = 'c'
       and c.conname <> 'feedback_rating_binary_check'
  loop
    execute format(
      'alter table public.feedback drop constraint %I',
      constraint_record.conname
    );
  end loop;

  update public.feedback
     set rating = case when rating >= 3 then 1 else 0 end
   where rating not in (0, 1);

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
