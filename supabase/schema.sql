-- QFin Terminal Supabase schema
-- Keep this file in sync with the connected Supabase project.
-- Project URL: https://gdwfsdmheymfhwberted.supabase.co

create schema if not exists extensions;
create extension if not exists pgcrypto;
create extension if not exists pg_trgm with schema extensions;

create table if not exists public.qfin_reports (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  title text not null,
  company_name text,
  ticker text,
  source_type text not null,
  period_label text,
  currency text,
  raw_input jsonb not null default '{}'::jsonb,
  computed_metrics jsonb not null default '{}'::jsonb,
  risk_flags jsonb not null default '[]'::jsonb,
  ai_report jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists qfin_reports_owner_created_idx
  on public.qfin_reports (owner_id, created_at desc);

create table if not exists public.qfin_watchlist (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  ticker text not null,
  company_name text,
  notes text,
  tags text[] not null default '{}',
  last_snapshot jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists qfin_watchlist_owner_idx
  on public.qfin_watchlist (owner_id, created_at desc);

create table if not exists public.qfin_model_templates (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid references auth.users(id) on delete set null,
  title text not null,
  description text,
  category text not null default 'general',
  is_public boolean not null default false,
  template_schema jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_qfin_model_templates_owner_id
  on public.qfin_model_templates(owner_id);

create table if not exists public.qfin_community_posts (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  title text not null,
  body text not null,
  post_type text not null default 'discussion',
  related_ticker text,
  related_report_id uuid references public.qfin_reports(id) on delete set null,
  model_template_id uuid references public.qfin_model_templates(id) on delete set null,
  is_public boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists qfin_community_posts_created_idx
  on public.qfin_community_posts (created_at desc);

create index if not exists idx_qfin_community_posts_owner_id
  on public.qfin_community_posts(owner_id);

create index if not exists idx_qfin_community_posts_related_report_id
  on public.qfin_community_posts(related_report_id);

create index if not exists idx_qfin_community_posts_model_template_id
  on public.qfin_community_posts(model_template_id);

create table if not exists public.qfin_forum_threads (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid default auth.uid() references auth.users(id) on delete set null,
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

create index if not exists idx_qfin_forum_threads_owner_id
  on public.qfin_forum_threads(owner_id);

create table if not exists public.qfin_builder_models (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid default auth.uid() references auth.users(id) on delete set null,
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

create index if not exists qfin_builder_models_visibility_score_idx
  on public.qfin_builder_models (visibility, score desc, created_at desc);

create index if not exists idx_qfin_builder_models_owner_id
  on public.qfin_builder_models(owner_id);

create index if not exists idx_qfin_builder_models_visibility_owner
  on public.qfin_builder_models(visibility, owner_id);

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

create index if not exists qfin_symbol_master_yahoo_symbol_idx
  on public.qfin_symbol_master (yahoo_symbol);

create index if not exists qfin_symbol_master_active_priority_idx
  on public.qfin_symbol_master (active, priority desc);

create index if not exists qfin_symbol_master_search_text_trgm_idx
  on public.qfin_symbol_master using gin (search_text extensions.gin_trgm_ops);

alter table public.qfin_reports enable row level security;
alter table public.qfin_watchlist enable row level security;
alter table public.qfin_model_templates enable row level security;
alter table public.qfin_community_posts enable row level security;
alter table public.qfin_forum_threads enable row level security;
alter table public.qfin_builder_models enable row level security;
alter table public.qfin_symbol_master enable row level security;

-- RLS policies. Use (select auth.uid()) for better planner behavior at scale.
drop policy if exists "qfin_reports_select_own" on public.qfin_reports;
create policy "qfin_reports_select_own"
  on public.qfin_reports for select to authenticated
  using ((select auth.uid()) = owner_id);

drop policy if exists "qfin_reports_insert_own" on public.qfin_reports;
create policy "qfin_reports_insert_own"
  on public.qfin_reports for insert to authenticated
  with check ((select auth.uid()) = owner_id);

drop policy if exists "qfin_reports_update_own" on public.qfin_reports;
create policy "qfin_reports_update_own"
  on public.qfin_reports for update to authenticated
  using ((select auth.uid()) = owner_id)
  with check ((select auth.uid()) = owner_id);

drop policy if exists "qfin_watchlist_select_own" on public.qfin_watchlist;
create policy "qfin_watchlist_select_own"
  on public.qfin_watchlist for select to authenticated
  using ((select auth.uid()) = owner_id);

drop policy if exists "qfin_watchlist_insert_own" on public.qfin_watchlist;
create policy "qfin_watchlist_insert_own"
  on public.qfin_watchlist for insert to authenticated
  with check ((select auth.uid()) = owner_id);

drop policy if exists "qfin_watchlist_update_own" on public.qfin_watchlist;
create policy "qfin_watchlist_update_own"
  on public.qfin_watchlist for update to authenticated
  using ((select auth.uid()) = owner_id)
  with check ((select auth.uid()) = owner_id);

drop policy if exists "qfin_model_templates_read_public_or_own" on public.qfin_model_templates;
create policy "qfin_model_templates_read_public_or_own"
  on public.qfin_model_templates for select to authenticated
  using (is_public = true or (select auth.uid()) = owner_id);

drop policy if exists "qfin_model_templates_insert_own" on public.qfin_model_templates;
create policy "qfin_model_templates_insert_own"
  on public.qfin_model_templates for insert to authenticated
  with check ((select auth.uid()) = owner_id);

drop policy if exists "qfin_model_templates_update_own" on public.qfin_model_templates;
create policy "qfin_model_templates_update_own"
  on public.qfin_model_templates for update to authenticated
  using ((select auth.uid()) = owner_id)
  with check ((select auth.uid()) = owner_id);

drop policy if exists "qfin_community_posts_read_public_or_own" on public.qfin_community_posts;
create policy "qfin_community_posts_read_public_or_own"
  on public.qfin_community_posts for select to authenticated
  using (is_public = true or (select auth.uid()) = owner_id);

drop policy if exists "qfin_community_posts_insert_own" on public.qfin_community_posts;
create policy "qfin_community_posts_insert_own"
  on public.qfin_community_posts for insert to authenticated
  with check ((select auth.uid()) = owner_id);

drop policy if exists "qfin_community_posts_update_own" on public.qfin_community_posts;
create policy "qfin_community_posts_update_own"
  on public.qfin_community_posts for update to authenticated
  using ((select auth.uid()) = owner_id)
  with check ((select auth.uid()) = owner_id);

drop policy if exists "forum_threads_public_read" on public.qfin_forum_threads;
create policy "forum_threads_public_read"
  on public.qfin_forum_threads for select to anon, authenticated
  using (true);

drop policy if exists "forum_threads_authenticated_insert" on public.qfin_forum_threads;
create policy "forum_threads_authenticated_insert"
  on public.qfin_forum_threads for insert to authenticated
  with check (
    owner_id = (select auth.uid())
    and nullif(btrim(title), '') is not null
    and nullif(btrim(body), '') is not null
    and nullif(btrim(author), '') is not null
  );

drop policy if exists "forum_threads_owner_update" on public.qfin_forum_threads;
create policy "forum_threads_owner_update"
  on public.qfin_forum_threads for update to authenticated
  using (owner_id = (select auth.uid()))
  with check (
    owner_id = (select auth.uid())
    and nullif(btrim(title), '') is not null
    and nullif(btrim(body), '') is not null
    and nullif(btrim(author), '') is not null
  );

drop policy if exists "forum_threads_owner_delete" on public.qfin_forum_threads;
create policy "forum_threads_owner_delete"
  on public.qfin_forum_threads for delete to authenticated
  using (owner_id = (select auth.uid()));

drop policy if exists "builder_models_public_or_owner_read" on public.qfin_builder_models;
create policy "builder_models_public_or_owner_read"
  on public.qfin_builder_models for select to anon, authenticated
  using (visibility = 'public' or owner_id = (select auth.uid()));

drop policy if exists "builder_models_authenticated_insert" on public.qfin_builder_models;
create policy "builder_models_authenticated_insert"
  on public.qfin_builder_models for insert to authenticated
  with check (
    owner_id = (select auth.uid())
    and nullif(btrim(name), '') is not null
    and nullif(btrim(author), '') is not null
    and nullif(btrim(code), '') is not null
    and visibility in ('public', 'private')
  );

drop policy if exists "builder_models_owner_update" on public.qfin_builder_models;
create policy "builder_models_owner_update"
  on public.qfin_builder_models for update to authenticated
  using (owner_id = (select auth.uid()))
  with check (
    owner_id = (select auth.uid())
    and nullif(btrim(name), '') is not null
    and nullif(btrim(author), '') is not null
    and nullif(btrim(code), '') is not null
    and visibility in ('public', 'private')
  );

drop policy if exists "builder_models_owner_delete" on public.qfin_builder_models;
create policy "builder_models_owner_delete"
  on public.qfin_builder_models for delete to authenticated
  using (owner_id = (select auth.uid()));

drop policy if exists "qfin_symbol_master_service_role_all" on public.qfin_symbol_master;
create policy "qfin_symbol_master_service_role_all"
  on public.qfin_symbol_master
  for all
  to service_role
  using (true)
  with check (true);

grant select, insert, update, delete on table public.qfin_symbol_master to service_role;

create table if not exists public.qfin_data_source_runs (
  id uuid primary key default gen_random_uuid(),
  symbol text not null,
  requested_symbol text,
  provider text not null,
  endpoint text not null,
  request_params jsonb not null default '{}'::jsonb,
  status text not null default 'started',
  rows_inserted integer not null default 0,
  warnings jsonb not null default '[]'::jsonb,
  error_message text,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists qfin_data_source_runs_symbol_provider_idx
  on public.qfin_data_source_runs (symbol, provider, created_at desc);

create table if not exists public.qfin_company_profiles (
  id uuid primary key default gen_random_uuid(),
  symbol text not null unique,
  provider_symbol text,
  company_name text,
  exchange text,
  sector text,
  industry text,
  country text,
  currency text,
  ipo_date date,
  website text,
  description text,
  source text not null default 'fmp',
  retrieved_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.qfin_financial_statements (
  id uuid primary key default gen_random_uuid(),
  retrieval_run_id uuid references public.qfin_data_source_runs(id) on delete set null,
  symbol text not null,
  provider_symbol text,
  fiscal_year integer not null,
  fiscal_period text not null,
  period_type text not null,
  statement_type text not null,
  metric_name text not null,
  metric_value double precision,
  report_date date,
  accepted_date date,
  currency text,
  source text not null default 'fmp',
  retrieved_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists qfin_financial_statements_row_idx
  on public.qfin_financial_statements (
    symbol,
    fiscal_year,
    fiscal_period,
    period_type,
    statement_type,
    metric_name,
    source
  );

create index if not exists qfin_financial_statements_symbol_year_idx
  on public.qfin_financial_statements (symbol, fiscal_year desc, statement_type, metric_name);

create table if not exists public.qfin_valuation_snapshots (
  id uuid primary key default gen_random_uuid(),
  retrieval_run_id uuid references public.qfin_data_source_runs(id) on delete set null,
  symbol text not null,
  provider_symbol text,
  snapshot_date date not null,
  fiscal_period text not null default 'TTM',
  market_cap double precision,
  enterprise_value double precision,
  shares_outstanding double precision,
  pe_ratio double precision,
  pb_ratio double precision,
  ps_ratio double precision,
  ev_ebitda double precision,
  dividend_yield double precision,
  roe double precision,
  roa double precision,
  data_quality text,
  source text not null default 'fmp',
  retrieved_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists qfin_valuation_snapshots_row_idx
  on public.qfin_valuation_snapshots (symbol, snapshot_date, fiscal_period, source);

create table if not exists public.qfin_bank_kpis (
  id uuid primary key default gen_random_uuid(),
  retrieval_run_id uuid references public.qfin_data_source_runs(id) on delete set null,
  symbol text not null,
  provider_symbol text,
  fiscal_year integer not null,
  fiscal_period text not null,
  period_type text not null,
  return_on_assets double precision,
  return_on_equity double precision,
  debt_to_equity double precision,
  price_to_book double precision,
  tier1_proxy double precision,
  nim double precision,
  loan_to_deposit double precision,
  efficiency_ratio double precision,
  note text,
  source text not null default 'fmp',
  retrieved_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists qfin_bank_kpis_row_idx
  on public.qfin_bank_kpis (symbol, fiscal_year, fiscal_period, period_type, source);

create table if not exists public.qfin_metric_coverage (
  id uuid primary key default gen_random_uuid(),
  retrieval_run_id uuid references public.qfin_data_source_runs(id) on delete set null,
  symbol text not null,
  fiscal_year integer not null,
  fiscal_period text not null,
  metric_group text not null,
  metric_name text not null,
  status text not null,
  note text,
  source text not null default 'fmp',
  updated_at timestamptz not null default now()
);

create unique index if not exists qfin_metric_coverage_row_idx
  on public.qfin_metric_coverage (symbol, fiscal_year, fiscal_period, metric_group, metric_name);

create table if not exists public.qfin_manual_overrides (
  id uuid primary key default gen_random_uuid(),
  symbol text not null,
  fiscal_year integer,
  fiscal_period text,
  metric_group text not null,
  metric_name text not null,
  metric_value double precision,
  currency text,
  source_document text,
  extraction_method text,
  status text not null default 'pending' check (status in ('pending', 'approved', 'rejected')),
  note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists qfin_manual_overrides_symbol_idx
  on public.qfin_manual_overrides (symbol, fiscal_year desc, metric_group, metric_name);

alter table public.qfin_data_source_runs enable row level security;
alter table public.qfin_company_profiles enable row level security;
alter table public.qfin_financial_statements enable row level security;
alter table public.qfin_valuation_snapshots enable row level security;
alter table public.qfin_bank_kpis enable row level security;
alter table public.qfin_metric_coverage enable row level security;
alter table public.qfin_manual_overrides enable row level security;

drop policy if exists "qfin_data_source_runs_service_role_all" on public.qfin_data_source_runs;
create policy "qfin_data_source_runs_service_role_all"
  on public.qfin_data_source_runs
  for all
  to service_role
  using (true)
  with check (true);

drop policy if exists "qfin_company_profiles_service_role_all" on public.qfin_company_profiles;
create policy "qfin_company_profiles_service_role_all"
  on public.qfin_company_profiles
  for all
  to service_role
  using (true)
  with check (true);

drop policy if exists "qfin_financial_statements_service_role_all" on public.qfin_financial_statements;
create policy "qfin_financial_statements_service_role_all"
  on public.qfin_financial_statements
  for all
  to service_role
  using (true)
  with check (true);

drop policy if exists "qfin_valuation_snapshots_service_role_all" on public.qfin_valuation_snapshots;
create policy "qfin_valuation_snapshots_service_role_all"
  on public.qfin_valuation_snapshots
  for all
  to service_role
  using (true)
  with check (true);

drop policy if exists "qfin_bank_kpis_service_role_all" on public.qfin_bank_kpis;
create policy "qfin_bank_kpis_service_role_all"
  on public.qfin_bank_kpis
  for all
  to service_role
  using (true)
  with check (true);

drop policy if exists "qfin_metric_coverage_service_role_all" on public.qfin_metric_coverage;
create policy "qfin_metric_coverage_service_role_all"
  on public.qfin_metric_coverage
  for all
  to service_role
  using (true)
  with check (true);

drop policy if exists "qfin_manual_overrides_service_role_all" on public.qfin_manual_overrides;
create policy "qfin_manual_overrides_service_role_all"
  on public.qfin_manual_overrides
  for all
  to service_role
  using (true)
  with check (true);
