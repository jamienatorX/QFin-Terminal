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
