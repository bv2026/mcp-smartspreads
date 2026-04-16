from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Iterator

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    inspect,
    select,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


class Newsletter(Base):
    __tablename__ = "newsletters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_file: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    week_ended: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    overall_summary: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    issue_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    issue_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    issue_status: Mapped[str] = mapped_column(String(24), nullable=False, default="ingested")
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_modified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    supersedes_newsletter_id: Mapped[int | None] = mapped_column(
        ForeignKey("newsletters.id", ondelete="SET NULL"),
        nullable=True,
    )

    sections: Mapped[list["NewsletterSection"]] = relationship(
        back_populates="newsletter",
        cascade="all, delete-orphan",
    )
    watchlist_entries: Mapped[list["WatchlistEntry"]] = relationship(
        back_populates="newsletter",
        cascade="all, delete-orphan",
    )
    watchlist_reference: Mapped["WatchlistReferenceRecord | None"] = relationship(
        back_populates="newsletter",
        cascade="all, delete-orphan",
        uselist=False,
    )
    parser_runs: Mapped[list["ParserRun"]] = relationship(
        back_populates="newsletter",
        cascade="all, delete-orphan",
    )
    issue_brief: Mapped["IssueBrief | None"] = relationship(
        back_populates="newsletter",
        cascade="all, delete-orphan",
        uselist=False,
    )
    issue_delta: Mapped["IssueDelta | None"] = relationship(
        back_populates="newsletter",
        cascade="all, delete-orphan",
        uselist=False,
        foreign_keys="IssueDelta.newsletter_id",
    )
    publication_runs: Mapped[list["PublicationRun"]] = relationship(
        back_populates="newsletter",
        cascade="all, delete-orphan",
    )


class NewsletterSection(Base):
    __tablename__ = "newsletter_sections"
    __table_args__ = (
        UniqueConstraint("newsletter_id", "name", "page_start", name="uq_newsletter_section"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    newsletter_id: Mapped[int] = mapped_column(ForeignKey("newsletters.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    section_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    parser_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("parser_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)

    newsletter: Mapped["Newsletter"] = relationship(back_populates="sections")
    parser_run: Mapped["ParserRun | None"] = relationship(back_populates="sections")


class WatchlistEntry(Base):
    __tablename__ = "watchlist_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    newsletter_id: Mapped[int] = mapped_column(ForeignKey("newsletters.id", ondelete="CASCADE"), nullable=False)
    commodity_name: Mapped[str] = mapped_column(String(255), nullable=False)
    spread_code: Mapped[str] = mapped_column(String(120), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    legs: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    enter_date: Mapped[date] = mapped_column(Date, nullable=False)
    exit_date: Mapped[date] = mapped_column(Date, nullable=False)
    win_pct: Mapped[float] = mapped_column(Float, nullable=False)
    avg_profit: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_best_profit: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_worst_loss: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_draw_down: Mapped[int] = mapped_column(Integer, nullable=False)
    apw_pct: Mapped[float] = mapped_column(Float, nullable=False)
    ridx: Mapped[float] = mapped_column(Float, nullable=False)
    five_year_corr: Mapped[int] = mapped_column(Integer, nullable=False)
    portfolio: Mapped[str | None] = mapped_column(String(24), nullable=True)
    risk_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trade_quality: Mapped[str | None] = mapped_column(String(24), nullable=True)
    volatility_structure: Mapped[str | None] = mapped_column(String(16), nullable=True)
    section_name: Mapped[str] = mapped_column(String(40), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_row: Mapped[str] = mapped_column(Text, nullable=False)
    entry_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tradeable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    parser_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("parser_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    publication_state: Mapped[str | None] = mapped_column(String(24), nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)

    newsletter: Mapped["Newsletter"] = relationship(back_populates="watchlist_entries")
    parser_run: Mapped["ParserRun | None"] = relationship(back_populates="watchlist_entries")


class WatchlistReferenceRecord(Base):
    __tablename__ = "watchlist_references"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    newsletter_id: Mapped[int] = mapped_column(
        ForeignKey("newsletters.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    column_definitions_json: Mapped[list] = mapped_column("column_definitions", JSON, nullable=False, default=list)
    trading_rules_json: Mapped[list] = mapped_column("trading_rules", JSON, nullable=False, default=list)
    classification_rules_json: Mapped[list] = mapped_column("classification_rules", JSON, nullable=False, default=list)
    parser_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("parser_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    reference_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)

    newsletter: Mapped["Newsletter"] = relationship(back_populates="watchlist_reference")
    parser_run: Mapped["ParserRun | None"] = relationship(back_populates="watchlist_references")


class ParserRun(Base):
    __tablename__ = "parser_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    newsletter_id: Mapped[int] = mapped_column(ForeignKey("newsletters.id", ondelete="CASCADE"), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    run_started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    run_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    page_count_detected: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pages_parsed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    watchlist_entry_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warnings_json: Mapped[list] = mapped_column("warnings", JSON, nullable=False, default=list)
    metrics_json: Mapped[dict] = mapped_column("metrics", JSON, nullable=False, default=dict)

    newsletter: Mapped["Newsletter"] = relationship(back_populates="parser_runs")
    sections: Mapped[list["NewsletterSection"]] = relationship(back_populates="parser_run")
    watchlist_entries: Mapped[list["WatchlistEntry"]] = relationship(back_populates="parser_run")
    watchlist_references: Mapped[list["WatchlistReferenceRecord"]] = relationship(back_populates="parser_run")
    issue_briefs: Mapped[list["IssueBrief"]] = relationship(back_populates="parser_run")


class IssueBrief(Base):
    __tablename__ = "issue_briefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    newsletter_id: Mapped[int] = mapped_column(
        ForeignKey("newsletters.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    parser_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("parser_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    brief_status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    headline: Mapped[str | None] = mapped_column(Text, nullable=True)
    executive_summary: Mapped[str] = mapped_column(Text, nullable=False)
    key_themes_json: Mapped[list] = mapped_column("key_themes", JSON, nullable=False, default=list)
    notable_risks_json: Mapped[list] = mapped_column("notable_risks", JSON, nullable=False, default=list)
    notable_opportunities_json: Mapped[list] = mapped_column(
        "notable_opportunities",
        JSON,
        nullable=False,
        default=list,
    )
    watchlist_summary_json: Mapped[dict] = mapped_column("watchlist_summary", JSON, nullable=False, default=dict)
    change_summary_json: Mapped[dict] = mapped_column("change_summary", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    newsletter: Mapped["Newsletter"] = relationship(back_populates="issue_brief")
    parser_run: Mapped["ParserRun | None"] = relationship(back_populates="issue_briefs")


class IssueDelta(Base):
    __tablename__ = "issue_deltas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    newsletter_id: Mapped[int] = mapped_column(
        ForeignKey("newsletters.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    previous_newsletter_id: Mapped[int | None] = mapped_column(
        ForeignKey("newsletters.id", ondelete="SET NULL"),
        nullable=True,
    )
    delta_status: Mapped[str] = mapped_column(String(24), nullable=False, default="generated")
    added_entries_json: Mapped[list] = mapped_column("added_entries", JSON, nullable=False, default=list)
    removed_entries_json: Mapped[list] = mapped_column("removed_entries", JSON, nullable=False, default=list)
    changed_entries_json: Mapped[list] = mapped_column("changed_entries", JSON, nullable=False, default=list)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    newsletter: Mapped["Newsletter"] = relationship(
        back_populates="issue_delta",
        foreign_keys=[newsletter_id],
    )
    previous_newsletter: Mapped["Newsletter | None"] = relationship(foreign_keys=[previous_newsletter_id])


class PublicationRun(Base):
    __tablename__ = "publication_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    newsletter_id: Mapped[int] = mapped_column(ForeignKey("newsletters.id", ondelete="CASCADE"), nullable=False)
    publication_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    published_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    output_root: Mapped[str | None] = mapped_column(Text, nullable=True)
    manifest_json: Mapped[dict] = mapped_column("manifest", JSON, nullable=False, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    newsletter: Mapped["Newsletter"] = relationship(back_populates="publication_runs")
    artifacts: Mapped[list["PublicationArtifact"]] = relationship(
        back_populates="publication_run",
        cascade="all, delete-orphan",
    )


class PublicationArtifact(Base):
    __tablename__ = "publication_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    publication_run_id: Mapped[int] = mapped_column(
        ForeignKey("publication_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_type: Mapped[str] = mapped_column(String(48), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)

    publication_run: Mapped["PublicationRun"] = relationship(back_populates="artifacts")


class SchwabFuturesCatalog(Base):
    __tablename__ = "schwab_futures_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol_root: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    options_tradable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    multiplier: Mapped[str | None] = mapped_column(String(80), nullable=True)
    minimum_tick_size: Mapped[str | None] = mapped_column(String(120), nullable=True)
    settlement_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    trading_hours: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_micro: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    stream_supported: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    native_spread_support: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    manual_legs_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    support_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_file: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_modified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)


class NewsletterCommodityCatalog(Base):
    __tablename__ = "newsletter_commodity_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    newsletter_root: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    commodity_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    exchange: Mapped[str | None] = mapped_column(String(120), nullable=True)
    preferred_schwab_root: Mapped[str | None] = mapped_column(String(32), nullable=True)
    alternate_schwab_roots_json: Mapped[list] = mapped_column(
        "alternate_schwab_roots",
        JSON,
        nullable=False,
        default=list,
    )
    is_tradeable_by_policy: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    policy_block_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    mapping_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    mapping_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_issue_week: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)


class ContractMonthCode(Base):
    __tablename__ = "contract_month_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    month_code: Mapped[str] = mapped_column(String(4), nullable=False, unique=True)
    month_name: Mapped[str] = mapped_column(String(32), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    source_issue_week: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)


class Database:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, future=True, connect_args=connect_args)
        self._sessionmaker = sessionmaker(bind=self.engine, expire_on_commit=False)

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)
        self._apply_additive_migrations()
        self._create_phase1_indexes()

    def _apply_additive_migrations(self) -> None:
        self._ensure_newsletters_phase1_columns()
        self._ensure_newsletter_sections_phase1_columns()
        self._ensure_watchlist_entries_phase1_columns()
        self._ensure_watchlist_references_phase1_columns()
        self._ensure_schwab_futures_catalog_columns()
        self._ensure_newsletter_commodity_catalog_columns()
        self._ensure_contract_month_codes_columns()

    def _ensure_newsletters_phase1_columns(self) -> None:
        self._add_column_if_missing("newsletters", "issue_code", self._column_sql("text"))
        self._add_column_if_missing("newsletters", "issue_version", self._column_sql("text"))
        self._add_column_if_missing(
            "newsletters",
            "issue_status",
            self._column_sql("text", nullable=False, default="'ingested'"),
        )
        self._add_column_if_missing("newsletters", "page_count", self._column_sql("integer"))
        self._add_column_if_missing(
            "newsletters",
            "source_modified_at",
            self._column_sql("datetime"),
        )
        self._add_column_if_missing("newsletters", "approved_at", self._column_sql("datetime"))
        self._add_column_if_missing("newsletters", "published_at", self._column_sql("datetime"))
        self._add_column_if_missing(
            "newsletters",
            "supersedes_newsletter_id",
            self._column_sql("integer"),
        )

    def _ensure_newsletter_sections_phase1_columns(self) -> None:
        self._add_column_if_missing("newsletter_sections", "section_type", self._column_sql("text"))
        self._add_column_if_missing(
            "newsletter_sections",
            "extraction_confidence",
            self._column_sql("float"),
        )
        self._add_column_if_missing("newsletter_sections", "parser_run_id", self._column_sql("integer"))
        self._add_column_if_missing(
            "newsletter_sections",
            "metadata",
            self._column_sql("json", nullable=False, default="'{}'"),
        )

    def _ensure_watchlist_entries_phase1_columns(self) -> None:
        self._add_column_if_missing("watchlist_entries", "entry_key", self._column_sql("text"))
        self._add_column_if_missing("watchlist_entries", "tradeable", self._column_sql("boolean"))
        self._add_column_if_missing("watchlist_entries", "blocked_reason", self._column_sql("text"))
        self._add_column_if_missing("watchlist_entries", "parser_run_id", self._column_sql("integer"))
        self._add_column_if_missing(
            "watchlist_entries",
            "publication_state",
            self._column_sql("text"),
        )
        self._add_column_if_missing(
            "watchlist_entries",
            "metadata",
            self._column_sql("json", nullable=False, default="'{}'"),
        )

    def _ensure_watchlist_references_phase1_columns(self) -> None:
        self._add_column_if_missing("watchlist_references", "parser_run_id", self._column_sql("integer"))
        self._add_column_if_missing(
            "watchlist_references",
            "reference_version",
            self._column_sql("text"),
        )
        self._add_column_if_missing(
            "watchlist_references",
            "metadata",
            self._column_sql("json", nullable=False, default="'{}'"),
        )

    def _ensure_schwab_futures_catalog_columns(self) -> None:
        self._add_column_if_missing("schwab_futures_catalog", "symbol_root", self._column_sql("text"))
        self._add_column_if_missing("schwab_futures_catalog", "display_name", self._column_sql("text"))
        self._add_column_if_missing("schwab_futures_catalog", "category", self._column_sql("text"))
        self._add_column_if_missing("schwab_futures_catalog", "options_tradable", self._column_sql("boolean"))
        self._add_column_if_missing("schwab_futures_catalog", "multiplier", self._column_sql("text"))
        self._add_column_if_missing("schwab_futures_catalog", "minimum_tick_size", self._column_sql("text"))
        self._add_column_if_missing("schwab_futures_catalog", "settlement_type", self._column_sql("text"))
        self._add_column_if_missing("schwab_futures_catalog", "trading_hours", self._column_sql("text"))
        self._add_column_if_missing(
            "schwab_futures_catalog",
            "is_micro",
            self._column_sql("boolean", nullable=False, default="0"),
        )
        self._add_column_if_missing("schwab_futures_catalog", "stream_supported", self._column_sql("boolean"))
        self._add_column_if_missing("schwab_futures_catalog", "native_spread_support", self._column_sql("boolean"))
        self._add_column_if_missing("schwab_futures_catalog", "manual_legs_required", self._column_sql("boolean"))
        self._add_column_if_missing("schwab_futures_catalog", "support_notes", self._column_sql("text"))
        self._add_column_if_missing("schwab_futures_catalog", "source_file", self._column_sql("text"))
        self._add_column_if_missing(
            "schwab_futures_catalog",
            "source_modified_at",
            self._column_sql("datetime"),
        )
        self._add_column_if_missing(
            "schwab_futures_catalog",
            "is_active",
            self._column_sql("boolean", nullable=False, default="1"),
        )
        self._add_column_if_missing(
            "schwab_futures_catalog",
            "metadata",
            self._column_sql("json", nullable=False, default="'{}'"),
        )

    def _ensure_newsletter_commodity_catalog_columns(self) -> None:
        self._add_column_if_missing("newsletter_commodity_catalog", "newsletter_root", self._column_sql("text"))
        self._add_column_if_missing("newsletter_commodity_catalog", "commodity_name", self._column_sql("text"))
        self._add_column_if_missing("newsletter_commodity_catalog", "category", self._column_sql("text"))
        self._add_column_if_missing("newsletter_commodity_catalog", "exchange", self._column_sql("text"))
        self._add_column_if_missing(
            "newsletter_commodity_catalog",
            "preferred_schwab_root",
            self._column_sql("text"),
        )
        self._add_column_if_missing(
            "newsletter_commodity_catalog",
            "alternate_schwab_roots",
            self._column_sql("json", nullable=False, default="'[]'"),
        )
        self._add_column_if_missing(
            "newsletter_commodity_catalog",
            "is_tradeable_by_policy",
            self._column_sql("boolean"),
        )
        self._add_column_if_missing(
            "newsletter_commodity_catalog",
            "policy_block_reason",
            self._column_sql("text"),
        )
        self._add_column_if_missing(
            "newsletter_commodity_catalog",
            "mapping_confidence",
            self._column_sql("float"),
        )
        self._add_column_if_missing("newsletter_commodity_catalog", "mapping_notes", self._column_sql("text"))
        self._add_column_if_missing(
            "newsletter_commodity_catalog",
            "source_issue_week",
            self._column_sql("date"),
        )
        self._add_column_if_missing(
            "newsletter_commodity_catalog",
            "source_page_number",
            self._column_sql("integer"),
        )
        self._add_column_if_missing(
            "newsletter_commodity_catalog",
            "metadata",
            self._column_sql("json", nullable=False, default="'{}'"),
        )

    def _ensure_contract_month_codes_columns(self) -> None:
        self._add_column_if_missing("contract_month_codes", "month_code", self._column_sql("text"))
        self._add_column_if_missing("contract_month_codes", "month_name", self._column_sql("text"))
        self._add_column_if_missing("contract_month_codes", "sort_order", self._column_sql("integer"))
        self._add_column_if_missing(
            "contract_month_codes",
            "source_issue_week",
            self._column_sql("date"),
        )
        self._add_column_if_missing(
            "contract_month_codes",
            "source_page_number",
            self._column_sql("integer"),
        )
        self._add_column_if_missing(
            "contract_month_codes",
            "metadata",
            self._column_sql("json", nullable=False, default="'{}'"),
        )

    def _create_phase1_indexes(self) -> None:
        index_statements = [
            "create index if not exists idx_newsletters_issue_status on newsletters (issue_status)",
            "create index if not exists idx_newsletter_sections_section_type on newsletter_sections (section_type)",
            "create index if not exists idx_newsletter_sections_parser_run_id on newsletter_sections (parser_run_id)",
            "create index if not exists idx_watchlist_entries_section_name on watchlist_entries (section_name)",
            "create index if not exists idx_watchlist_entries_entry_key on watchlist_entries (entry_key)",
            "create index if not exists idx_watchlist_entries_publication_state on watchlist_entries (publication_state)",
            "create index if not exists idx_watchlist_entries_parser_run_id on watchlist_entries (parser_run_id)",
            "create index if not exists idx_watchlist_references_parser_run_id on watchlist_references (parser_run_id)",
            "create index if not exists idx_parser_runs_newsletter_id on parser_runs (newsletter_id)",
            "create index if not exists idx_parser_runs_status on parser_runs (status)",
            "create index if not exists idx_issue_deltas_previous_newsletter_id on issue_deltas (previous_newsletter_id)",
            "create index if not exists idx_publication_runs_newsletter_id on publication_runs (newsletter_id)",
            "create index if not exists idx_publication_artifacts_publication_run_id on publication_artifacts (publication_run_id)",
            "create unique index if not exists idx_schwab_futures_catalog_symbol_root on schwab_futures_catalog (symbol_root)",
            "create index if not exists idx_schwab_futures_catalog_category on schwab_futures_catalog (category)",
            "create unique index if not exists idx_newsletter_commodity_catalog_root on newsletter_commodity_catalog (newsletter_root)",
            "create index if not exists idx_newsletter_commodity_catalog_preferred_root on newsletter_commodity_catalog (preferred_schwab_root)",
            "create unique index if not exists idx_contract_month_codes_code on contract_month_codes (month_code)",
        ]
        with self.engine.begin() as connection:
            for statement in index_statements:
                connection.execute(text(statement))

    def _column_names(self, table_name: str) -> set[str]:
        return {column["name"] for column in inspect(self.engine).get_columns(table_name)}

    def _add_column_if_missing(self, table_name: str, column_name: str, definition: str) -> None:
        if column_name in self._column_names(table_name):
            return
        statement = f"alter table {table_name} add column {column_name} {definition}"
        with self.engine.begin() as connection:
            connection.execute(text(statement))

    def _column_sql(self, logical_type: str, nullable: bool = True, default: str | None = None) -> str:
        type_map = {
            "text": "text",
            "integer": "integer",
            "float": "double precision" if self.engine.dialect.name == "postgresql" else "real",
            "datetime": "timestamptz" if self.engine.dialect.name == "postgresql" else "datetime",
            "boolean": "boolean" if self.engine.dialect.name == "postgresql" else "integer",
            "json": "jsonb" if self.engine.dialect.name == "postgresql" else "text",
            "date": "date",
        }
        sql = type_map[logical_type]
        if default is not None:
            sql += f" default {default}"
        if not nullable:
            sql += " not null"
        return sql

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self._sessionmaker()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def newsletter_exists(self, file_hash: str) -> bool:
        with self.session() as session:
            stmt = select(Newsletter.id).where(Newsletter.file_hash == file_hash)
            return session.execute(stmt).first() is not None
