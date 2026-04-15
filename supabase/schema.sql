create table if not exists public.newsletters (
  id bigserial primary key,
  source_file text not null unique,
  file_hash text not null unique,
  title text not null,
  week_ended date not null unique,
  raw_text text not null,
  overall_summary text not null,
  metadata jsonb not null default '{}'::jsonb,
  ingested_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.newsletter_sections (
  id bigserial primary key,
  newsletter_id bigint not null references public.newsletters(id) on delete cascade,
  name text not null,
  page_start integer not null,
  page_end integer not null,
  raw_text text not null,
  summary_text text not null,
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
  raw_row text not null
);

create table if not exists public.watchlist_references (
  id bigserial primary key,
  newsletter_id bigint not null unique references public.newsletters(id) on delete cascade,
  page_number integer not null,
  raw_text text not null,
  summary_text text not null,
  column_definitions jsonb not null default '[]'::jsonb,
  trading_rules jsonb not null default '[]'::jsonb,
  classification_rules jsonb not null default '[]'::jsonb
);

create index if not exists idx_newsletters_week_ended on public.newsletters (week_ended desc);
create index if not exists idx_watchlist_entries_newsletter_id on public.watchlist_entries (newsletter_id);
create index if not exists idx_watchlist_entries_trade_quality on public.watchlist_entries (trade_quality);
create index if not exists idx_watchlist_entries_category on public.watchlist_entries (category);
create index if not exists idx_watchlist_references_newsletter_id on public.watchlist_references (newsletter_id);

alter table public.newsletters enable row level security;
alter table public.newsletter_sections enable row level security;
alter table public.watchlist_entries enable row level security;
alter table public.watchlist_references enable row level security;

create policy "service role full access newsletters"
on public.newsletters
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
