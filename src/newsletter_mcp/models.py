from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class WatchlistRow:
    commodity_name: str
    spread_code: str
    side: str
    legs: int
    category: str
    enter_date: date
    exit_date: date
    win_pct: float
    avg_profit: int
    avg_best_profit: int
    avg_worst_loss: int
    avg_draw_down: int
    apw_pct: float
    ridx: float
    five_year_corr: int
    portfolio: str | None
    risk_level: int | None
    trade_quality: str | None
    volatility_structure: str | None
    section_name: str
    page_number: int
    raw_row: str


@dataclass(slots=True)
class SectionSummary:
    name: str
    page_start: int
    page_end: int
    raw_text: str
    summary_text: str


@dataclass(slots=True)
class WatchlistReference:
    page_number: int
    raw_text: str
    summary_text: str
    column_definitions: list[dict[str, str]]
    trading_rules: list[str]
    classification_rules: list[str]


@dataclass(slots=True)
class ParsedNewsletter:
    source_file: Path
    file_hash: str
    title: str
    week_ended: date
    raw_text: str
    metadata: dict[str, Any]
    overall_summary: str
    section_summaries: list[SectionSummary]
    watchlist_reference: WatchlistReference | None
    watchlist_rows: list[WatchlistRow]
