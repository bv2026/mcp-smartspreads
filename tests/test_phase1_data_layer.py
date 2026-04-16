from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from sqlalchemy import select

from newsletter_mcp import server
from newsletter_mcp.database import (
    Database,
    IssueBrief,
    IssueDelta,
    Newsletter,
    NewsletterSection,
    ParserRun,
    PublicationRun,
    WatchlistEntry,
    WatchlistReferenceRecord,
)
from newsletter_mcp.models import ParsedNewsletter, SectionSummary, WatchlistReference, WatchlistRow


def _make_watchlist_row(
    *,
    commodity_name: str = "Corn",
    spread_code: str = "CU26-CZ26",
    side: str = "SELL",
    section_name: str = "intra_commodity",
    enter_date: date = date(2026, 4, 17),
    exit_date: date = date(2026, 8, 30),
    trade_quality: str | None = "Tier 1",
    portfolio: str | None = None,
    risk_level: int | None = None,
    volatility_structure: str | None = "High",
) -> WatchlistRow:
    return WatchlistRow(
        commodity_name=commodity_name,
        spread_code=spread_code,
        side=side,
        legs=1,
        category="Grain",
        enter_date=enter_date,
        exit_date=exit_date,
        win_pct=93.0,
        avg_profit=642,
        avg_best_profit=910,
        avg_worst_loss=-220,
        avg_draw_down=-140,
        apw_pct=12.0,
        ridx=1.4,
        five_year_corr=4,
        portfolio=portfolio,
        risk_level=risk_level,
        trade_quality=trade_quality,
        volatility_structure=volatility_structure,
        section_name=section_name,
        page_number=8,
        raw_row="raw row",
    )


def _make_parsed_newsletter(
    *,
    base_dir: Path,
    week_ended: date,
    rows: list[WatchlistRow],
    title: str | None = None,
) -> ParsedNewsletter:
    source_file = base_dir / f"issue-{week_ended.isoformat()}.pdf"
    source_file.write_bytes(f"pdf-{week_ended.isoformat()}".encode("utf-8"))
    return ParsedNewsletter(
        source_file=source_file,
        file_hash=f"hash-{week_ended.isoformat()}",
        title=title or f"Week Ended {week_ended.isoformat()}",
        week_ended=week_ended,
        raw_text=f"Raw text for {week_ended.isoformat()}",
        metadata={"page_count": 12, "source_filename": source_file.name},
        overall_summary=f"Summary for {week_ended.isoformat()}",
        section_summaries=[
            SectionSummary(
                name="Watch List",
                page_start=8,
                page_end=8,
                raw_text="Watch List page",
                summary_text="Watch List summary",
            )
        ],
        watchlist_reference=WatchlistReference(
            page_number=7,
            raw_text="Reference page",
            summary_text="Reference summary",
            column_definitions=[{"column": "Win %", "meaning": "Winning rate"}],
            trading_rules=["BUY means buy first leg"],
            classification_rules=["Tier 1 is strongest"],
        ),
        watchlist_rows=rows,
    )


def _make_entry(
    *,
    newsletter_id: int,
    week_ended: date,
    commodity_name: str = "Corn",
    spread_code: str = "CU26-CZ26",
    side: str = "SELL",
    exit_date: date = date(2026, 8, 30),
    section_name: str = "intra_commodity",
    trade_quality: str | None = "Tier 1",
) -> WatchlistEntry:
    row = _make_watchlist_row(
        commodity_name=commodity_name,
        spread_code=spread_code,
        side=side,
        section_name=section_name,
        exit_date=exit_date,
        trade_quality=trade_quality,
    )
    return WatchlistEntry(
        newsletter_id=newsletter_id,
        commodity_name=row.commodity_name,
        spread_code=row.spread_code,
        side=row.side,
        legs=row.legs,
        category=row.category,
        enter_date=row.enter_date,
        exit_date=row.exit_date,
        win_pct=row.win_pct,
        avg_profit=row.avg_profit,
        avg_best_profit=row.avg_best_profit,
        avg_worst_loss=row.avg_worst_loss,
        avg_draw_down=row.avg_draw_down,
        apw_pct=row.apw_pct,
        ridx=row.ridx,
        five_year_corr=row.five_year_corr,
        portfolio=row.portfolio,
        risk_level=row.risk_level,
        trade_quality=row.trade_quality,
        volatility_structure=row.volatility_structure,
        section_name=row.section_name,
        page_number=row.page_number,
        raw_row=row.raw_row,
        entry_key=server._build_entry_key(week_ended, row),
        publication_state="candidate",
        metadata_json={},
    )


class Phase1DataLayerTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        server.database.engine.dispose()

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base_dir = Path(self.temp_dir.name)
        self.database = Database(f"sqlite:///{(self.base_dir / 'test.db').as_posix()}")
        self.database.create_schema()
        self.addCleanup(self.database.engine.dispose)
        self.database_patch = mock.patch.object(server, "database", self.database)
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)

    def test_build_entry_key_normalizes_text(self) -> None:
        row = _make_watchlist_row(
            commodity_name="S&P 500 VIX",
            spread_code="VXN26-VXU26",
            section_name="intra_commodity",
            side="SELL",
        )

        key = server._build_entry_key(date(2026, 4, 10), row)

        self.assertEqual(
            key,
            "intra-commodity|s-p-500-vix|vxn26-vxu26|sell",
        )

    def test_save_parsed_newsletter_creates_phase1_records(self) -> None:
        parsed = _make_parsed_newsletter(
            base_dir=self.base_dir,
            week_ended=date(2026, 4, 10),
            rows=[_make_watchlist_row()],
        )

        result = server._save_parsed_newsletter(parsed)

        self.assertEqual(result["status"], "ingested")
        with self.database.session() as session:
            self.assertEqual(session.execute(select(ParserRun)).scalars().all().__len__(), 1)
            self.assertEqual(session.execute(select(IssueBrief)).scalars().all().__len__(), 1)
            self.assertEqual(session.execute(select(IssueDelta)).scalars().all().__len__(), 1)
            self.assertEqual(session.execute(select(PublicationRun)).scalars().all().__len__(), 1)

            entry = session.execute(select(WatchlistEntry)).scalar_one()
            self.assertIsNotNone(entry.entry_key)
            self.assertEqual(entry.publication_state, "candidate")

            brief = session.execute(select(IssueBrief)).scalar_one()
            self.assertEqual(brief.watchlist_summary_json["entry_count"], 1)
            self.assertEqual(brief.change_summary_json["added_count"], 0)

    def test_save_second_issue_computes_added_and_changed_delta(self) -> None:
        first = _make_parsed_newsletter(
            base_dir=self.base_dir,
            week_ended=date(2026, 4, 3),
            rows=[_make_watchlist_row(exit_date=date(2026, 8, 30))],
        )
        second = _make_parsed_newsletter(
            base_dir=self.base_dir,
            week_ended=date(2026, 4, 10),
            rows=[
                _make_watchlist_row(exit_date=date(2026, 9, 2)),
                _make_watchlist_row(
                    commodity_name="Soybeans",
                    spread_code="SU26-SF27",
                    exit_date=date(2026, 7, 13),
                ),
            ],
        )

        server._save_parsed_newsletter(first)
        server._save_parsed_newsletter(second)

        with self.database.session() as session:
            newsletter = session.execute(
                select(Newsletter).where(Newsletter.week_ended == date(2026, 4, 10))
            ).scalar_one()
            delta = session.execute(
                select(IssueDelta).where(IssueDelta.newsletter_id == newsletter.id)
            ).scalar_one()

            self.assertEqual(len(delta.added_entries_json), 1)
            self.assertEqual(len(delta.removed_entries_json), 0)
            self.assertEqual(len(delta.changed_entries_json), 1)
            self.assertIn("changed 1 carried entries", delta.summary_text)

    def test_backfill_phase1_intelligence_seeds_existing_history(self) -> None:
        with self.database.session() as session:
            newsletter = Newsletter(
                source_file=str(self.base_dir / "legacy.pdf"),
                file_hash="legacy-hash",
                title="Legacy issue",
                week_ended=date(2026, 1, 2),
                raw_text="Legacy raw text",
                overall_summary="Legacy summary",
                metadata_json={"page_count": 9},
                issue_status="ingested",
                page_count=9,
            )
            session.add(newsletter)
            session.flush()

            session.add(
                NewsletterSection(
                    newsletter_id=newsletter.id,
                    name="Watch List",
                    page_start=6,
                    page_end=6,
                    raw_text="Legacy watch list section",
                    summary_text="Legacy section summary",
                )
            )
            session.add(
                WatchlistReferenceRecord(
                    newsletter_id=newsletter.id,
                    page_number=5,
                    raw_text="Legacy reference",
                    summary_text="Legacy reference summary",
                    column_definitions_json=[],
                    trading_rules_json=[],
                    classification_rules_json=[],
                )
            )
            session.add(
                _make_entry(
                    newsletter_id=newsletter.id,
                    week_ended=newsletter.week_ended,
                )
            )

        result = server.backfill_phase1_intelligence()

        self.assertEqual(result["issue_count"], 1)
        with self.database.session() as session:
            parser_run = session.execute(select(ParserRun)).scalar_one()
            brief = session.execute(select(IssueBrief)).scalar_one()
            delta = session.execute(select(IssueDelta)).scalar_one()
            publication_run = session.execute(select(PublicationRun)).scalar_one()
            entry = session.execute(select(WatchlistEntry)).scalar_one()
            section = session.execute(select(NewsletterSection)).scalar_one()
            reference = session.execute(select(WatchlistReferenceRecord)).scalar_one()

            self.assertEqual(parser_run.metrics_json["backfilled"], True)
            self.assertEqual(brief.brief_status, "draft")
            self.assertEqual(delta.summary_text, "No prior issue available for comparison.")
            self.assertEqual(publication_run.status, "draft")
            self.assertEqual(entry.publication_state, "candidate")
            self.assertIsNotNone(entry.entry_key)
            self.assertEqual(section.section_type, "watchlist_page")
            self.assertEqual(reference.reference_version, "v1")

    def test_backfill_phase1_intelligence_refreshes_existing_brief_and_delta(self) -> None:
        first = _make_parsed_newsletter(
            base_dir=self.base_dir,
            week_ended=date(2026, 4, 3),
            rows=[_make_watchlist_row(exit_date=date(2026, 8, 30))],
        )
        second = _make_parsed_newsletter(
            base_dir=self.base_dir,
            week_ended=date(2026, 4, 10),
            rows=[
                _make_watchlist_row(exit_date=date(2026, 9, 2)),
                _make_watchlist_row(
                    commodity_name="Soybeans",
                    spread_code="SU26-SF27",
                    exit_date=date(2026, 7, 13),
                ),
            ],
        )

        server._save_parsed_newsletter(first)
        server._save_parsed_newsletter(second)

        with self.database.session() as session:
            newsletter = session.execute(
                select(Newsletter).where(Newsletter.week_ended == date(2026, 4, 10))
            ).scalar_one()
            brief = session.execute(
                select(IssueBrief).where(IssueBrief.newsletter_id == newsletter.id)
            ).scalar_one()
            delta = session.execute(
                select(IssueDelta).where(IssueDelta.newsletter_id == newsletter.id)
            ).scalar_one()

            brief.key_themes_json = []
            brief.notable_risks_json = []
            brief.notable_opportunities_json = []
            brief.watchlist_summary_json = {"entry_count": 2}
            brief.change_summary_json = {"added_count": 99}
            delta.added_entries_json = []
            delta.removed_entries_json = []
            delta.changed_entries_json = []
            delta.summary_text = "stale summary"

        result = server.backfill_phase1_intelligence()

        self.assertEqual(result["issue_count"], 2)
        with self.database.session() as session:
            newsletter = session.execute(
                select(Newsletter).where(Newsletter.week_ended == date(2026, 4, 10))
            ).scalar_one()
            brief = session.execute(
                select(IssueBrief).where(IssueBrief.newsletter_id == newsletter.id)
            ).scalar_one()
            delta = session.execute(
                select(IssueDelta).where(IssueDelta.newsletter_id == newsletter.id)
            ).scalar_one()

            self.assertTrue(brief.key_themes_json)
            self.assertTrue(brief.notable_risks_json)
            self.assertTrue(brief.notable_opportunities_json)
            self.assertIn("volatility_counts", brief.watchlist_summary_json)
            self.assertEqual(brief.change_summary_json["added_count"], 1)
            self.assertEqual(len(delta.added_entries_json), 1)
            self.assertEqual(len(delta.removed_entries_json), 0)
            self.assertEqual(len(delta.changed_entries_json), 1)
            self.assertIn("changed 1 carried entries", delta.summary_text)


if __name__ == "__main__":
    unittest.main()
