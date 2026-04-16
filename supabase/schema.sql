create table if not exists public.newsletters (
  id bigserial primary key,
  source_file text not null unique,
  file_hash text not null unique,
  title text not null,
  week_ended date not null unique,
  raw_text text not null,
  overall_summary text not null,
  metadata jsonb not null default '{}'::jsonb,
  ingested_at timestamptz not null default timezone('utc', now()),
  issue_code text,
  issue_version text,
  issue_status text not null default 'ingested',
  page_count integer,
  source_modified_at timestamptz,
  approved_at timestamptz,
  published_at timestamptz,
  supersedes_newsletter_id bigint references public.newsletters(id) on delete set null
);

create table if not exists public.parser_runs (
  id bigserial primary key,
  newsletter_id bigint not null references public.newsletters(id) on delete cascade,
  parser_version text not null,
  status text not null,
  run_started_at timestamptz not null default timezone('utc', now()),
  run_completed_at timestamptz,
  page_count_detected integer,
  pages_parsed integer,
  watchlist_entry_count integer,
  section_count integer,
  warning_count integer not null default 0,
  warnings jsonb not null default '[]'::jsonb,
  metrics jsonb not null default '{}'::jsonb
);

create table if not exists public.newsletter_sections (
  id bigserial primary key,
  newsletter_id bigint not null references public.newsletters(id) on delete cascade,
  name text not null,
  page_start integer not null,
  page_end integer not null,
  raw_text text not null,
  summary_text text not null,
  section_type text,
  extraction_confidence double precision,
  parser_run_id bigint references public.parser_runs(id) on delete set null,
  metadata jsonb not null default '{}'::jsonb,
  unique (newsletter_id, name, page_start)
);

create table if not exists public.watchlist_entries (
  id bigserial primary key,
  newsletter_id bigint not null references public.newsletters(id) on delete cascade,
  commodity_name text not null,
  spread_code text not null,
  side text not null,
  legs integer not null,
  category text not null,
  enter_date date not null,
  exit_date date not null,
  win_pct numeric not null,
  avg_profit integer not null,
  avg_best_profit integer not null,
  avg_worst_loss integer not null,
  avg_draw_down integer not null,
  apw_pct numeric not null,
  ridx numeric not null,
  five_year_corr integer not null,
  portfolio text,
  risk_level integer,
  trade_quality text,
  volatility_structure text,
  section_name text not null,
  page_number integer not null,
  raw_row text not null,
  entry_key text,
  tradeable boolean,
  blocked_reason text,
  parser_run_id bigint references public.parser_runs(id) on delete set null,
  publication_state text,
  metadata jsonb not null default '{}'::jsonb
);

create table if not exists public.watchlist_references (
  id bigserial primary key,
  newsletter_id bigint not null unique references public.newsletters(id) on delete cascade,
  page_number integer not null,
  raw_text text not null,
  summary_text text not null,
  column_definitions jsonb not null default '[]'::jsonb,
  trading_rules jsonb not null default '[]'::jsonb,
  classification_rules jsonb not null default '[]'::jsonb,
  parser_run_id bigint references public.parser_runs(id) on delete set null,
  reference_version text,
  metadata jsonb not null default '{}'::jsonb
);

create table if not exists public.issue_briefs (
  id bigserial primary key,
  newsletter_id bigint not null unique references public.newsletters(id) on delete cascade,
  parser_run_id bigint references public.parser_runs(id) on delete set null,
  brief_status text not null default 'draft',
  headline text,
  executive_summary text not null,
  key_themes jsonb not null default '[]'::jsonb,
  notable_risks jsonb not null default '[]'::jsonb,
  notable_opportunities jsonb not null default '[]'::jsonb,
  watchlist_summary jsonb not null default '{}'::jsonb,
  change_summary jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.issue_deltas (
  id bigserial primary key,
  newsletter_id bigint not null unique references public.newsletters(id) on delete cascade,
  previous_newsletter_id bigint references public.newsletters(id) on delete set null,
  delta_status text not null default 'generated',
  added_entries jsonb not null default '[]'::jsonb,
  removed_entries jsonb not null default '[]'::jsonb,
  changed_entries jsonb not null default '[]'::jsonb,
  summary_text text,
  created_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.publication_runs (
  id bigserial primary key,
  newsletter_id bigint not null references public.newsletters(id) on delete cascade,
  publication_version text not null,
  status text not null default 'draft',
  published_by text,
  published_at timestamptz,
  output_root text,
  manifest jsonb not null default '{}'::jsonb,
  notes text,
  created_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.publication_artifacts (
  id bigserial primary key,
  publication_run_id bigint not null references public.publication_runs(id) on delete cascade,
  artifact_type text not null,
  file_path text not null,
  file_hash text,
  row_count integer,
  metadata jsonb not null default '{}'::jsonb
);

create table if not exists public.schwab_futures_catalog (
  id bigserial primary key,
  symbol_root text not null unique,
  display_name text not null,
  category text not null,
  options_tradable boolean,
  multiplier text,
  minimum_tick_size text,
  settlement_type text,
  trading_hours text,
  is_micro boolean not null default false,
  stream_supported boolean,
  source_file text,
  source_modified_at timestamptz,
  is_active boolean not null default true,
  metadata jsonb not null default '{}'::jsonb
);

create table if not exists public.newsletter_commodity_catalog (
  id bigserial primary key,
  newsletter_root text not null unique,
  commodity_name text not null,
  category text,
  exchange text,
  preferred_schwab_root text,
  alternate_schwab_roots jsonb not null default '[]'::jsonb,
  is_tradeable_by_policy boolean,
  policy_block_reason text,
  mapping_confidence double precision,
  mapping_notes text,
  source_issue_week date,
  source_page_number integer,
  metadata jsonb not null default '{}'::jsonb
);

create table if not exists public.contract_month_codes (
  id bigserial primary key,
  month_code text not null unique,
  month_name text not null,
  sort_order integer not null,
  source_issue_week date,
  source_page_number integer,
  metadata jsonb not null default '{}'::jsonb
);

create index if not exists idx_newsletters_week_ended on public.newsletters (week_ended desc);
create index if not exists idx_newsletters_issue_status on public.newsletters (issue_status);
create index if not exists idx_parser_runs_newsletter_id on public.parser_runs (newsletter_id);
create index if not exists idx_parser_runs_status on public.parser_runs (status);
create index if not exists idx_newsletter_sections_section_type on public.newsletter_sections (section_type);
create index if not exists idx_newsletter_sections_parser_run_id on public.newsletter_sections (parser_run_id);
create index if not exists idx_watchlist_entries_newsletter_id on public.watchlist_entries (newsletter_id);
create index if not exists idx_watchlist_entries_section_name on public.watchlist_entries (section_name);
create index if not exists idx_watchlist_entries_trade_quality on public.watchlist_entries (trade_quality);
create index if not exists idx_watchlist_entries_category on public.watchlist_entries (category);
create index if not exists idx_watchlist_entries_entry_key on public.watchlist_entries (entry_key);
create index if not exists idx_watchlist_entries_publication_state on public.watchlist_entries (publication_state);
create index if not exists idx_watchlist_entries_parser_run_id on public.watchlist_entries (parser_run_id);
create index if not exists idx_watchlist_references_newsletter_id on public.watchlist_references (newsletter_id);
create index if not exists idx_watchlist_references_parser_run_id on public.watchlist_references (parser_run_id);
create index if not exists idx_issue_deltas_previous_newsletter_id on public.issue_deltas (previous_newsletter_id);
create index if not exists idx_publication_runs_newsletter_id on public.publication_runs (newsletter_id);
create index if not exists idx_publication_artifacts_publication_run_id on public.publication_artifacts (publication_run_id);
create unique index if not exists idx_schwab_futures_catalog_symbol_root on public.schwab_futures_catalog (symbol_root);
create index if not exists idx_schwab_futures_catalog_category on public.schwab_futures_catalog (category);
create unique index if not exists idx_newsletter_commodity_catalog_root on public.newsletter_commodity_catalog (newsletter_root);
create index if not exists idx_newsletter_commodity_catalog_preferred_root on public.newsletter_commodity_catalog (preferred_schwab_root);
create unique index if not exists idx_contract_month_codes_code on public.contract_month_codes (month_code);

alter table public.newsletters enable row level security;
alter table public.parser_runs enable row level security;
alter table public.newsletter_sections enable row level security;
alter table public.watchlist_entries enable row level security;
alter table public.watchlist_references enable row level security;
alter table public.issue_briefs enable row level security;
alter table public.issue_deltas enable row level security;
alter table public.publication_runs enable row level security;
alter table public.publication_artifacts enable row level security;
alter table public.schwab_futures_catalog enable row level security;
alter table public.newsletter_commodity_catalog enable row level security;
alter table public.contract_month_codes enable row level security;

create policy "service role full access newsletters"
on public.newsletters
for all
to service_role
using (true)
with check (true);

create policy "service role full access parser_runs"
on public.parser_runs
for all
to service_role
using (true)
with check (true);

create policy "service role full access newsletter_sections"
on public.newsletter_sections
for all
to service_role
using (true)
with check (true);

create policy "service role full access watchlist_entries"
on public.watchlist_entries
for all
to service_role
using (true)
with check (true);

create policy "service role full access watchlist_references"
on public.watchlist_references
for all
to service_role
using (true)
with check (true);

create policy "service role full access issue_briefs"
on public.issue_briefs
for all
to service_role
using (true)
with check (true);

create policy "service role full access issue_deltas"
on public.issue_deltas
for all
to service_role
using (true)
with check (true);

create policy "service role full access publication_runs"
on public.publication_runs
for all
to service_role
using (true)
with check (true);

create policy "service role full access publication_artifacts"
on public.publication_artifacts
for all
to service_role
using (true)
with check (true);

create policy "service role full access schwab_futures_catalog"
on public.schwab_futures_catalog
for all
to service_role
using (true)
with check (true);

create policy "service role full access newsletter_commodity_catalog"
on public.newsletter_commodity_catalog
for all
to service_role
using (true)
with check (true);

create policy "service role full access contract_month_codes"
on public.contract_month_codes
for all
to service_role
using (true)
with check (true);
