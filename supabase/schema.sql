-- Supabase tables already created in your connected project.
-- Project URL: https://gdwfsdmheymfhwberted.supabase.co

create extension if not exists pgcrypto;

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
  tags jsonb not null default '[]'::jsonb,
  stats jsonb not null default '{}'::jsonb,
  score integer not null default 0,
  visibility text not null default 'public' check (visibility in ('public', 'private')),
  seed_key text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists qfin_builder_models_visibility_score_idx
  on public.qfin_builder_models (visibility, score desc, created_at desc);
