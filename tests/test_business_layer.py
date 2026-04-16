from __future__ import annotations

import tempfile
import unittest
from dataclasses import asdict
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from sqlalchemy import select

from newsletter_mcp import server
from newsletter_mcp.business import IssueBriefService
from newsletter_mcp.database import Database, IssueBrief
from newsletter_mcp.models import ParsedNewsletter, SectionSummary, WatchlistReference, WatchlistRow


def _make_watchlist_row(
    *,
    commodity_name: str = "Corn",
    spread_code: str = "CU26-CZ26",
    category: str = "Grain",
    section_name: str = "intra_commodity",
    trade_quality: str | None = "Tier 1",
    ridx: float = 35.0,
) -> WatchlistRow:
    return WatchlistRow(
        commodity_name=commodity_name,
        spread_code=spread_code,
        side="SELL",
        legs=1,
        category=category,
        enter_date=date(2026, 4, 17),
        exit_date=date(2026, 8, 30),
        win_pct=93.0,
        avg_profit=642,
        avg_best_profit=910,
        avg_worst_loss=-220,
        avg_draw_down=-140,
        apw_pct=12.0,
        ridx=ridx,
        five_year_corr=4,
        portfolio=None,
        risk_level=None,
        trade_quality=trade_quality,
        volatility_structure="High",
        section_name=section_name,
        page_number=8,
        raw_row="raw row",
    )


def _make_service_row(
    *,
    commodity_name: str = "Corn",
    spread_code: str = "CU26-CZ26",
    category: str = "Grain",
    section_name: str = "intra_commodity",
    trade_quality: str | None = "Tier 1",
    ridx: float = 35.0,
    tradeable: bool | None = True,
    blocked_reason: str | None = None,
) -> SimpleNamespace:
    row = _make_watchlist_row(
        commodity_name=commodity_name,
        spread_code=spread_code,
        category=category,
        section_name=section_name,
        trade_quality=trade_quality,
        ridx=ridx,
    )
    return SimpleNamespace(**asdict(row), tradeable=tradeable, blocked_reason=blocked_reason)


def _make_parsed_newsletter(base_dir: Path) -> ParsedNewsletter:
    source_file = base_dir / "brief-issue.pdf"
    source_file.write_bytes(b"pdf")
    return ParsedNewsletter(
        source_file=source_file,
        file_hash="brief-hash",
        title="Week Ended 2026-04-10",
        week_ended=date(2026, 4, 10),
        raw_text="Raw text",
        metadata={"page_count": 12, "source_filename": source_file.name},
        overall_summary="This week focuses on grains and volatility structures.",
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
        watchlist_rows=[
            _make_watchlist_row(category="Grain", commodity_name="Corn"),
            _make_watchlist_row(category="Energy", commodity_name="Natural Gas", spread_code="NGZ26-NGF27"),
        ],
    )


class IssueBriefServiceTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        server.database.engine.dispose()

    def test_build_issue_brief_generates_business_summary(self) -> None:
        rows = [
            _make_service_row(category="Grain", commodity_name="Corn"),
            _make_service_row(
                category="Energy",
                commodity_name="Gasoil",
                spread_code="GOU26-GOZ26",
                tradeable=False,
                blocked_reason="Gasoil is not available in TOS.",
                ridx=24.0,
                trade_quality="Tier 3",
            ),
        ]
        delta = type(
            "Delta",
            (),
            {
                "added_entries_json": [{"entry_key": "new"}],
                "removed_entries_json": [],
                "changed_entries_json": [],
                "summary_text": "Added 1 entries, removed 0 entries, and changed 0 carried entries versus the prior issue.",
            },
        )()
        reference = type("Reference", (), {"trading_rules_json": ["BUY means buy first leg"], "classification_rules_json": []})()

        brief = IssueBriefService.build_issue_brief(
            title="Week Ended 2026-04-10",
            executive_summary="Weekly summary",
            entries=rows,
            delta=delta,
            reference=reference,
        )

        self.assertEqual(brief.watchlist_summary["entry_count"], 2)
        self.assertEqual(brief.watchlist_summary["category_counts"]["Grain"], 1)
        self.assertEqual(brief.change_summary["added_count"], 1)
        self.assertTrue(brief.key_themes)
        self.assertTrue(any("blocked" in risk.lower() for risk in brief.notable_risks))
        self.assertTrue(brief.notable_opportunities)

    def test_save_parsed_newsletter_persists_business_brief_fields(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        base_dir = Path(temp_dir.name)
        database = Database(f"sqlite:///{(base_dir / 'business.db').as_posix()}")
        database.create_schema()
        self.addCleanup(database.engine.dispose)
        database_patch = mock.patch.object(server, "database", database)
        database_patch.start()
        self.addCleanup(database_patch.stop)

        parsed = _make_parsed_newsletter(base_dir)
        server._save_parsed_newsletter(parsed)

        with database.session() as session:
            brief = session.execute(select(IssueBrief)).scalar_one()
            self.assertEqual(brief.watchlist_summary_json["entry_count"], 2)
            self.assertIn("category_counts", brief.watchlist_summary_json)
            self.assertTrue(brief.key_themes_json)
            self.assertTrue(brief.notable_opportunities_json)


if __name__ == "__main__":
    unittest.main()
