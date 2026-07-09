-- QFin financial data warehouse reference migration.
-- This mirrors the live Supabase migration `add_financial_data_warehouse`.
-- Purpose: store reusable fundamentals, valuation, bank KPIs, source runs, coverage, and manual overrides.

CREATE TABLE IF NOT EXISTS public.qfin_company_profiles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol text NOT NULL UNIQUE,
  yahoo_symbol text,
  company_name text NOT NULL,
  exchange text,
  market text,
  country text,
  currency text,
  sector text,
  industry text,
  website text,
  description text,
  provider_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  source text NOT NULL DEFAULT 'manual',
  source_confidence numeric(5,2) NOT NULL DEFAULT 0.70 CHECK (source_confidence >= 0 AND source_confidence <= 1),
  retrieved_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.qfin_market_prices_daily (
  id bigserial PRIMARY KEY,
  symbol text NOT NULL,
  price_date date NOT NULL,
  open numeric,
  high numeric,
  low numeric,
  close numeric,
  adjusted_close numeric,
  volume numeric,
  currency text,
  source text NOT NULL DEFAULT 'unknown',
  source_confidence numeric(5,2) NOT NULL DEFAULT 0.70 CHECK (source_confidence >= 0 AND source_confidence <= 1),
  retrieved_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(symbol, price_date, source)
);

CREATE TABLE IF NOT EXISTS public.qfin_financial_statements (
  id bigserial PRIMARY KEY,
  symbol text NOT NULL,
  company_name text,
  fiscal_year integer NOT NULL,
  fiscal_period text NOT NULL DEFAULT 'FY',
  period_type text NOT NULL DEFAULT 'annual' CHECK (period_type IN ('annual', 'quarterly', 'ttm')),
  period_end_date date,
  statement_type text NOT NULL CHECK (statement_type IN ('income_statement', 'balance_sheet', 'cash_flow')),
  metric_name text NOT NULL,
  metric_label text,
  metric_value numeric,
  metric_unit text NOT NULL DEFAULT 'currency',
  currency text,
  source text NOT NULL DEFAULT 'unknown',
  source_url text,
  source_confidence numeric(5,2) NOT NULL DEFAULT 0.70 CHECK (source_confidence >= 0 AND source_confidence <= 1),
  retrieval_run_id uuid,
  provider_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  retrieved_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(symbol, fiscal_year, fiscal_period, period_type, statement_type, metric_name, source)
);

CREATE TABLE IF NOT EXISTS public.qfin_valuation_snapshots (
  id bigserial PRIMARY KEY,
  symbol text NOT NULL,
  snapshot_date date NOT NULL DEFAULT current_date,
  fiscal_year integer,
  fiscal_period text DEFAULT 'TTM',
  price numeric,
  shares_outstanding numeric,
  market_cap numeric,
  total_debt numeric,
  cash_and_equivalents numeric,
  minority_interest numeric,
  preferred_equity numeric,
  enterprise_value numeric,
  revenue numeric,
  ebitda numeric,
  net_income numeric,
  total_equity numeric,
  eps numeric,
  book_value_per_share numeric,
  pe_ratio numeric,
  pb_ratio numeric,
  ps_ratio numeric,
  ev_ebitda numeric,
  dividend_yield numeric,
  currency text,
  calculation_method text NOT NULL DEFAULT 'provider_or_calculated',
  source text NOT NULL DEFAULT 'unknown',
  source_confidence numeric(5,2) NOT NULL DEFAULT 0.70 CHECK (source_confidence >= 0 AND source_confidence <= 1),
  data_quality text NOT NULL DEFAULT 'partial' CHECK (data_quality IN ('complete', 'partial', 'estimated', 'missing')),
  notes text,
  retrieval_run_id uuid,
  provider_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  retrieved_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(symbol, snapshot_date, fiscal_period, source)
);

CREATE TABLE IF NOT EXISTS public.qfin_bank_kpis (
  id bigserial PRIMARY KEY,
  symbol text NOT NULL,
  fiscal_year integer NOT NULL,
  fiscal_period text NOT NULL DEFAULT 'FY',
  period_type text NOT NULL DEFAULT 'annual' CHECK (period_type IN ('annual', 'quarterly', 'ttm')),
  period_end_date date,
  total_loans numeric,
  total_deposits numeric,
  customer_deposits numeric,
  net_interest_income numeric,
  non_interest_income numeric,
  operating_income numeric,
  provision_expense numeric,
  net_income numeric,
  total_assets numeric,
  total_equity numeric,
  earning_assets numeric,
  npl_amount numeric,
  nim numeric,
  roe numeric,
  roa numeric,
  npl_ratio numeric,
  loan_to_deposit_ratio numeric,
  casa_ratio numeric,
  car numeric,
  cost_to_income_ratio numeric,
  currency text,
  source text NOT NULL DEFAULT 'unknown',
  source_confidence numeric(5,2) NOT NULL DEFAULT 0.70 CHECK (source_confidence >= 0 AND source_confidence <= 1),
  retrieval_run_id uuid,
  provider_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  retrieved_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(symbol, fiscal_year, fiscal_period, period_type, source)
);

CREATE TABLE IF NOT EXISTS public.qfin_data_source_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol text NOT NULL,
  requested_symbol text,
  provider text NOT NULL,
  endpoint text,
  request_params jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'started' CHECK (status IN ('started', 'success', 'partial', 'failed')),
  http_status integer,
  rows_inserted integer NOT NULL DEFAULT 0,
  rows_updated integer NOT NULL DEFAULT 0,
  missing_fields text[] NOT NULL DEFAULT '{}',
  warnings text[] NOT NULL DEFAULT '{}',
  error_message text,
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.qfin_metric_coverage (
  id bigserial PRIMARY KEY,
  symbol text NOT NULL,
  fiscal_year integer,
  fiscal_period text DEFAULT 'FY',
  metric_group text NOT NULL,
  metric_name text NOT NULL,
  status text NOT NULL CHECK (status IN ('available', 'missing', 'estimated', 'manual', 'not_applicable')),
  source text,
  source_confidence numeric(5,2) CHECK (source_confidence >= 0 AND source_confidence <= 1),
  note text,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(symbol, fiscal_year, fiscal_period, metric_group, metric_name)
);

CREATE TABLE IF NOT EXISTS public.qfin_manual_overrides (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  symbol text NOT NULL,
  fiscal_year integer,
  fiscal_period text DEFAULT 'FY',
  metric_group text NOT NULL,
  metric_name text NOT NULL,
  metric_value numeric,
  metric_text text,
  currency text,
  source_document text,
  source_url text,
  reason text,
  approval_status text NOT NULL DEFAULT 'pending' CHECK (approval_status IN ('pending', 'approved', 'rejected')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_qfin_company_profiles_symbol ON public.qfin_company_profiles(symbol);
CREATE INDEX IF NOT EXISTS idx_qfin_market_prices_daily_symbol_date ON public.qfin_market_prices_daily(symbol, price_date DESC);
CREATE INDEX IF NOT EXISTS idx_qfin_financial_statements_symbol_year_type ON public.qfin_financial_statements(symbol, fiscal_year DESC, statement_type);
CREATE INDEX IF NOT EXISTS idx_qfin_financial_statements_metric ON public.qfin_financial_statements(symbol, metric_name, fiscal_year DESC);
CREATE INDEX IF NOT EXISTS idx_qfin_valuation_snapshots_symbol_date ON public.qfin_valuation_snapshots(symbol, snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_qfin_bank_kpis_symbol_year ON public.qfin_bank_kpis(symbol, fiscal_year DESC, fiscal_period);
CREATE INDEX IF NOT EXISTS idx_qfin_data_source_runs_symbol_provider ON public.qfin_data_source_runs(symbol, provider, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_qfin_metric_coverage_symbol_status ON public.qfin_metric_coverage(symbol, status, metric_group);
CREATE INDEX IF NOT EXISTS idx_qfin_manual_overrides_symbol_status ON public.qfin_manual_overrides(symbol, approval_status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_qfin_manual_overrides_owner ON public.qfin_manual_overrides(owner_id);

ALTER TABLE public.qfin_company_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.qfin_market_prices_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.qfin_financial_statements ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.qfin_valuation_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.qfin_bank_kpis ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.qfin_data_source_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.qfin_metric_coverage ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.qfin_manual_overrides ENABLE ROW LEVEL SECURITY;

-- Public reads for non-user-specific financial data. Service role writes/ingests.
CREATE POLICY "company_profiles_public_read" ON public.qfin_company_profiles FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "company_profiles_service_role_all" ON public.qfin_company_profiles FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "market_prices_public_read" ON public.qfin_market_prices_daily FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "market_prices_service_role_all" ON public.qfin_market_prices_daily FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "financial_statements_public_read" ON public.qfin_financial_statements FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "financial_statements_service_role_all" ON public.qfin_financial_statements FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "valuation_snapshots_public_read" ON public.qfin_valuation_snapshots FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "valuation_snapshots_service_role_all" ON public.qfin_valuation_snapshots FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "bank_kpis_public_read" ON public.qfin_bank_kpis FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "bank_kpis_service_role_all" ON public.qfin_bank_kpis FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "data_source_runs_service_role_all" ON public.qfin_data_source_runs FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "metric_coverage_public_read" ON public.qfin_metric_coverage FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "metric_coverage_service_role_all" ON public.qfin_metric_coverage FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "manual_overrides_owner_read" ON public.qfin_manual_overrides FOR SELECT TO authenticated USING (owner_id = (select auth.uid()));
CREATE POLICY "manual_overrides_owner_insert" ON public.qfin_manual_overrides FOR INSERT TO authenticated WITH CHECK (owner_id = (select auth.uid()));
CREATE POLICY "manual_overrides_owner_update_pending" ON public.qfin_manual_overrides FOR UPDATE TO authenticated USING (owner_id = (select auth.uid()) AND approval_status = 'pending') WITH CHECK (owner_id = (select auth.uid()) AND approval_status = 'pending');
CREATE POLICY "manual_overrides_service_role_all" ON public.qfin_manual_overrides FOR ALL TO service_role USING (true) WITH CHECK (true);
