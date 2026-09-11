# Supabase setup

This directory contains the application database definition for the VN traffic-law RAG app. Qdrant remains the retrieval store; Supabase stores auth-linked profiles and chat data.

## Dashboard setup (empty project)

1. Create or open a Supabase project.
2. In **Authentication → Providers**, enable **Email**. Keep email/password enabled; configure email confirmation and SMTP according to your deployment policy. The app does not require a custom auth hook.
3. Open **SQL Editor → New query**, paste `supabase/schema.sql`, and run it once. The script is idempotent for a fresh project and does not contain credentials or destructive table drops.
4. Optional: create a test account in **Authentication → Users → Add user**. Copy its UUID.
5. Optional: use **SQL Editor** with `supabase/seed.sql`. If using the Supabase SQL editor, replace `:demo_user_id` with the quoted UUID in both statements (the `\if` guard is intended for `psql`; the SQL statements themselves are ordinary PostgreSQL).
6. In **Project Settings → API**, configure only the project URL and publishable/anon key in browser clients. Keep the service-role key server-side and out of Git.

## CLI setup

From the repository root, install and authenticate the Supabase CLI, then link the project:

```bash
supabase login
supabase link --project-ref "$SUPABASE_PROJECT_REF"
```

Apply the schema explicitly (this is not automatic in the application):

```bash
supabase db query < supabase/schema.sql
```

For a local Supabase instance, start it first and run the same SQL through the local SQL editor or `psql` connection shown by `supabase status`. To seed an existing auth user with the CLI:

```bash
psql "$SUPABASE_DB_URL" -v demo_user_id="<auth-user-uuid>" -f supabase/seed.sql
```

`schema.sql` is the source of truth for tables, indexes, triggers, and row-level security. Do not run arbitrary destructive reset commands against a shared project. The backend check command only probes endpoints and reports missing schema; it never applies DDL.

## Expected environment

The backend checker accepts `SUPABASE_URL` (for example `https://project-ref.supabase.co`) and either `SUPABASE_ANON_KEY` or `SUPABASE_PUBLISHABLE_KEY`. It can optionally use `SUPABASE_SERVICE_ROLE_KEY` for a server-side table probe. Keys are read from the environment and are never printed. A service-role key bypasses RLS, so use it only on a trusted machine.

```bash
SUPABASE_URL=https://project-ref.supabase.co \
SUPABASE_ANON_KEY=... \
python backend/scripts/supabase_check.py
```

The script checks the public REST root, Auth settings endpoint, and each required table. A table response of `404`/`42P01` means the schema has not been applied; `401`/`403` usually means the endpoint exists but the selected key cannot read protected rows. It reports status without exposing response bodies or key material.
