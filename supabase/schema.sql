-- Supabase tables already created in your connected project.
-- Project URL: https://gdwfsdmheymfhwberted.supabase.co

create extension if not exists pgcrypto;
create extension if not exists pg_trgm;

create table if not exists public.qfin_reports (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  title text not null,
  company_name text,
  ticker text,
  source_type text not null,
  raw_input jsonb not null default '{}'::jsonb,
  computed_metrics jsonb not null default '{}'::jsonb,
  risk_flags jsonb not null default '[]'::jsonb,
  ai_report jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.qfin_forum_threads (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  body text not null,
  author text not null,
  score integer not null default 1,
  upvotes integer not null default 1,
  downvotes integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists qfin_forum_threads_score_created_idx
  on public.qfin_forum_threads (score desc, created_at desc);

create table if not exists public.qfin_builder_models (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  author text not null,
  summary text not null default '',
  code text not null,
  ticker text,
  tags jsonb not null default '[]'::jsonb,
  stats jsonb not null default '{}'::jsonb,
  profile jsonb not null default '{}'::jsonb,
  series jsonb not null default '[]'::jsonb,
  highlights jsonb not null default '[]'::jsonb,
  status text not null default 'research',
  last_run_result jsonb not null default '{}'::jsonb,
  score integer not null default 0,
  visibility text not null default 'public' check (visibility in ('public', 'private')),
  seed_key text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.qfin_builder_models
  add column if not exists ticker text,
  add column if not exists profile jsonb not null default '{}'::jsonb,
  add column if not exists series jsonb not null default '[]'::jsonb,
  add column if not exists highlights jsonb not null default '[]'::jsonb,
  add column if not exists status text not null default 'research',
  add column if not exists last_run_result jsonb not null default '{}'::jsonb;

create index if not exists qfin_builder_models_visibility_score_idx
  on public.qfin_builder_models (visibility, score desc, created_at desc);

create table if not exists public.qfin_symbol_master (
  id uuid primary key default gen_random_uuid(),
  symbol text not null unique,
  yahoo_symbol text not null,
  name text not null,
  exchange text not null default '',
  market text not null default '',
  country text not null default '',
  currency text not null default '',
  aliases jsonb not null default '[]'::jsonb,
  search_text text not null default '',
  source text not null default 'manual',
  priority integer not null default 50,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.qfin_symbol_master
  add column if not exists yahoo_symbol text not null default '',
  add column if not exists exchange text not null default '',
  add column if not exists market text not null default '',
  add column if not exists country text not null default '',
  add column if not exists currency text not null default '',
  add column if not exists aliases jsonb not null default '[]'::jsonb,
  add column if not exists search_text text not null default '',
  add column if not exists source text not null default 'manual',
  add column if not exists priority integer not null default 50,
  add column if not exists active boolean not null default true,
  add column if not exists updated_at timestamptz not null default now();

create unique index if not exists qfin_symbol_master_symbol_idx
  on public.qfin_symbol_master (symbol);

create index if not exists qfin_symbol_master_yahoo_symbol_idx
  on public.qfin_symbol_master (yahoo_symbol);

create index if not exists qfin_symbol_master_active_priority_idx
  on public.qfin_symbol_master (active, priority desc);

create index if not exists qfin_symbol_master_search_text_trgm_idx
  on public.qfin_symbol_master using gin (search_text gin_trgm_ops);

alter table public.qfin_symbol_master enable row level security;

drop policy if exists "qfin_symbol_master_service_role_all" on public.qfin_symbol_master;
create policy "qfin_symbol_master_service_role_all"
  on public.qfin_symbol_master
  for all
  to service_role
  using (true)
  with check (true);
