from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from typing import Iterator

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


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
    ingested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

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

    newsletter: Mapped["Newsletter"] = relationship(back_populates="sections")


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

    newsletter: Mapped["Newsletter"] = relationship(back_populates="watchlist_entries")


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

    newsletter: Mapped["Newsletter"] = relationship(back_populates="watchlist_reference")


class Database:
    def __init__(self, database_url: str) -> None:
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, future=True, connect_args=connect_args)
        self._sessionmaker = sessionmaker(bind=self.engine, expire_on_commit=False)

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

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
